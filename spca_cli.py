#!/usr/bin/env python3
"""Command-line interface for the SPCA prototype.

  python spca_cli.py test FILE [FILE ...]      compare SPCA vs zlib/bz2/lzma, verify round-trip
  python spca_cli.py compress IN [OUT]         write IN -> OUT (default IN.spca)
  python spca_cli.py decompress IN [OUT]       restore (default: strip .spca)
"""
import sys, os, time, zlib, bz2, lzma
import spca

WARN = 2_000_000  # pure-Python prototype: large files are slow and memory hungry

def read(p):
    with open(p, 'rb') as f: data = f.read()
    if len(data) > WARN:
        print(f"warning: {p} is {len(data):,} bytes; the prototype is slow on large files "
              f"(try a file under ~1 MB first)", file=sys.stderr)
    return data

def cmd_test(paths):
    print(f"{'file':32}{'orig':>11}{'zlib':>11}{'bz2':>11}{'lzma':>11}{'SPCA':>11}  mode          ok   time")
    for p in paths:
        d = read(p); rep = {}
        t = time.time(); blob = spca.compress(d, rep); dt = time.time() - t
        ok = spca.decompress(blob) == d
        z = len(zlib.compress(d, 9)); b = len(bz2.compress(d, 9)); l = len(lzma.compress(d, preset=9))
        print(f"{os.path.basename(p)[:31]:32}{len(d):>11,}{z:>11,}{b:>11,}{l:>11,}{len(blob):>11,}  "
              f"{rep.get('best','-'):13} {'Y' if ok else 'N'}  {dt:.1f}s")

def main(a):
    if len(a) < 2 or a[0] not in ('test', 'compress', 'decompress'):
        print(__doc__); return 1
    cmd, args = a[0], a[1:]
    if cmd == 'test':
        cmd_test(args)
    elif cmd == 'compress':
        out = args[1] if len(args) > 1 else args[0] + '.spca'
        d = read(args[0]); blob = spca.compress(d)
        open(out, 'wb').write(blob)
        print(f"{args[0]}: {len(d):,} -> {len(blob):,} bytes ({out})")
    else:
        src = args[0]
        out = args[1] if len(args) > 1 else (src[:-5] if src.endswith('.spca') else src + '.out')
        d = spca.decompress(open(src, 'rb').read()); open(out, 'wb').write(d)
        print(f"{src} -> {out} ({len(d):,} bytes, checksum verified)")
    return 0

if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
