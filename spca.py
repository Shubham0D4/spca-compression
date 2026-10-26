"""SPCA prototype: Sequence-Position Compression Algorithm.

Container format:
  byte 0: method  0=stored 1=zlib(direct) 2=SPCA raw 3=SPCA+zlib 4=SPCA(positions only zlib'd)
  Direct methods: payload follows.
  SPCA methods: header(orig_len varint, crc32 4B) + body
Body (SPCA):
  N (segments, varint), D (dict size, varint)
  dict entries: len varint, bytes
  per token: pos-map (mode byte + params)
  remaining literal bytes (count = N - sum(token counts))
"""
import zlib, struct, bz2, lzma
from collections import defaultdict

# ---------- varints ----------
def pv(n, out):
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b); return

def rv(buf, i):
    n = 0; s = 0
    while True:
        b = buf[i]; i += 1
        n |= (b & 0x7F) << s; s += 7
        if not b & 0x80:
            return n, i

# ---------- Phase B/C: repeated-sequence discovery + tokenization ----------
LENGTHS = (64, 32, 16, 8, 6, 4)
MAX_DICT = 2048

def discover(data):
    n = len(data)
    cands = []
    for L in LENGTHS:
        if n < 2 * L: continue
        occ = defaultdict(list)
        for i in range(n - L + 1):
            occ[data[i:i + L]].append(i)
        for s, ps in occ.items():
            c = len(ps)
            if c < 2: continue
            # estimated net saving: bytes removed vs dictionary + position cost (~2B/occurrence worst-case)
            save = c * L - (L + 2) - c * 2
            if save > 0:
                cands.append((save, L, s, ps))
    cands.sort(key=lambda t: (-t[0], t[1], t[2]))  # deterministic
    used = bytearray(n)
    chosen = []  # (seq, [positions])
    for save, L, s, ps in cands:
        if len(chosen) >= MAX_DICT: break
        got = []
        for p in ps:
            if not any(used[p:p + L]):
                got.append(p)
                used[p:p + L] = b'\x01' * L
        # re-check true savings after overlap resolution
        if len(got) * (L - 2) - (L + 2) > 0:
            chosen.append((s, got))
        else:
            for p in got: used[p:p + L] = b'\x00' * L
    return chosen

# ---------- Phase D/E: position map ----------
def gaps_of(pos):
    return [pos[0]] + [pos[i] - pos[i - 1] for i in range(1, len(pos))]

def enc_posmap(pos):
    g = gaps_of(pos)
    cnt = len(pos)
    options = []
    # irregular: varint gaps
    o = bytearray([2]); pv(cnt, o)
    for x in g: pv(x, o)
    options.append(bytes(o))
    if cnt >= 3:
        rest = g[1:]
        if len(set(rest)) == 1:
            o = bytearray([0]); pv(g[0], o); pv(cnt, o); pv(rest[0], o)
            options.append(bytes(o))
        else:
            m = len(rest)
            for p in range(2, min(16, m // 2) + 1):
                if m % p == 0 and rest == rest[:p] * (m // p):
                    o = bytearray([1]); pv(g[0], o); pv(cnt, o); pv(p, o)
                    for x in rest[:p]: pv(x, o)
                    options.append(bytes(o)); break
    return min(options, key=len)

def dec_posmap(buf, i):
    mode = buf[i]; i += 1
    if mode == 0:
        f, i = rv(buf, i); c, i = rv(buf, i); gp, i = rv(buf, i)
        return [f + gp * k for k in range(c)], i
    if mode == 1:
        f, i = rv(buf, i); c, i = rv(buf, i); p, i = rv(buf, i)
        pat = []
        for _ in range(p):
            x, i = rv(buf, i); pat.append(x)
        pos = [f]
        rest = pat * ((c - 1) // p)
        for x in rest: pos.append(pos[-1] + x)
        return pos, i
    c, i = rv(buf, i)
    pos = []; cur = 0
    for k in range(c):
        x, i = rv(buf, i)
        cur = x if k == 0 else cur + x
        pos.append(cur)
    return pos, i

# ---------- SPCA encode/decode ----------
def spca_body(data):
    chosen = discover(data)
    # order dictionary deterministically: by first position
    chosen.sort(key=lambda t: t[1][0])
    start = {}  # byte position -> token id
    for tid, (s, ps) in enumerate(chosen):
        for p in ps: start[p] = tid
    seg_tokens = []  # token id or -1 per segment
    lits = bytearray()
    i = 0; n = len(data)
    lens = [len(s) for s, _ in chosen]
    while i < n:
        t = start.get(i)
        if t is not None:
            seg_tokens.append(t); i += lens[t]
        else:
            seg_tokens.append(-1); lits.append(data[i]); i += 1
    N = len(seg_tokens)
    tpos = [[] for _ in chosen]
    for idx, t in enumerate(seg_tokens):
        if t >= 0: tpos[t].append(idx)
    head = bytearray(); pv(N, head); pv(len(chosen), head)
    dic = bytearray()
    for s, _ in chosen:
        pv(len(s), dic); dic += s
    maps = bytearray()
    for ps in tpos: maps += enc_posmap(ps)
    return bytes(head), bytes(dic), bytes(maps), bytes(lits), len(chosen)

def spca_unbody(buf):
    i = 0
    N, i = rv(buf, i); D, i = rv(buf, i)
    entries = []
    for _ in range(D):
        l, i = rv(buf, i); entries.append(buf[i:i + l]); i += l
    seg = [None] * N
    for t in range(D):
        pos, i = dec_posmap(buf, i)
        for p in pos: seg[p] = entries[t]
    lit = buf[i:]; li = 0; out = bytearray()
    for s in seg:
        if s is None:
            out.append(lit[li]); li += 1
        else:
            out += s
    return bytes(out)

def compress(data, report=None):
    n = len(data)
    hdr = bytearray(); pv(n, hdr); hdr += struct.pack('<I', zlib.crc32(data))
    cands = {}
    cands['stored'] = bytes([0]) + data
    cands['zlib-direct'] = bytes([1]) + zlib.compress(data, 9)
    if n >= 16:
        head, dic, maps, lits, D = spca_body(data)
        raw = head + dic + maps + lits
        cands['spca-raw'] = bytes([2]) + hdr + raw
        cands['spca+zlib'] = bytes([3]) + hdr + zlib.compress(raw, 9)
        # structure (dict+maps) zlib'd separately, literals zlib'd separately
        sblob = zlib.compress(dic + maps, 9); lblob = zlib.compress(lits, 9)
        o = bytearray([4]) + hdr; pv(len(head), o); o += head
        pv(len(sblob), o); o += sblob; o += lblob
        cands['spca-split'] = bytes(o)
        if report is not None:
            report['dict_entries'] = D
            report['dict_bytes'] = len(dic); report['map_bytes'] = len(maps)
            report['lit_bytes'] = len(lits); report['segments'] = len(head)
    best = min(cands, key=lambda k: len(cands[k]))
    if report is not None:
        report['cands'] = {k: len(v) for k, v in cands.items()}
        report['best'] = best
    return cands[best]

def decompress(blob):
    m = blob[0]
    if m == 0: return blob[1:]
    if m == 1: return zlib.decompress(blob[1:])
    i = 1
    n, i = rv(blob, i); crc = struct.unpack('<I', blob[i:i + 4])[0]; i += 4
    if m == 2: out = spca_unbody(blob[i:])
    elif m == 3: out = spca_unbody(zlib.decompress(blob[i:]))
    elif m == 4:
        hl, i = rv(blob, i); head = blob[i:i + hl]; i += hl
        sl, i = rv(blob, i)
        sb = zlib.decompress(blob[i:i + sl]); i += sl
        lits = zlib.decompress(blob[i:])
        # head is N,D varints; reassemble body
        out = spca_unbody(head + sb + lits)
    else:
        raise ValueError('bad method')
    assert len(out) == n and zlib.crc32(out) == crc, 'integrity failure'
    return out
