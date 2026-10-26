import os, io, glob, random, time, zlib, bz2, lzma, json
import numpy as np
from PIL import Image, ImageDraw
import spca

random.seed(1); np.random.seed(1)
C = {}
LIM = 150_000

def rd(p, lim=LIM):
    with open(p, 'rb') as f: return f.read(lim)

# text / source / docs from the system
py = sorted(glob.glob('/usr/lib/python3.12/*.py'), key=os.path.getsize)
C['source_code.py'] = rd('/usr/lib/python3.12/argparse.py')
C['source_code_c.h'] = rd(glob.glob('/usr/include/stdio.h')[0]) if os.path.exists('/usr/include/stdio.h') else b''
txt = [p for p in glob.glob('/usr/share/common-licenses/*') if os.path.isfile(p)]
if txt: C['english_text.txt'] = rd('/usr/share/common-licenses/' + ('GPL-3' if os.path.exists('/usr/share/common-licenses/GPL-3') else os.path.basename(txt[0])))
# structured records
rows = ['id,name,city,score,flag']
cities = ['Pune', 'Mumbai', 'Delhi', 'Mulshi', 'Nashik']
for i in range(4000):
    rows.append(f"{i},user{random.randint(0,300)},{random.choice(cities)},{random.randint(0,100)},{random.choice('YN')}")
C['records.csv'] = '\n'.join(rows).encode()
C['json_records.json'] = json.dumps([{"id": i, "type": random.choice(["a", "b", "c"]), "v": random.randint(0, 9)} for i in range(3000)]).encode()
# periodic / repeated / random
C['repeated_byte.bin'] = b'\x00' * 100_000
C['periodic_abcd.bin'] = b'ABCD' * 25_000
C['periodic_irregular.bin'] = (b'xy' + b'.' * 3 + b'z') * 20_000
C['sawtooth.bin'] = bytes(i % 251 for i in range(100_000))
C['random.bin'] = os.urandom(100_000)
# already compressed
C['already_zlib.bin'] = zlib.compress(C['english_text.txt'] if 'english_text.txt' in C else C['source_code.py'], 9)
# binary executable
for p in ['/bin/ls', '/usr/bin/python3']:
    if os.path.exists(p): C['executable_elf'] = rd(os.path.realpath(p), 100_000); break

# images (W x H)
W = H = 256
def save(img, name, fmt, **kw):
    b = io.BytesIO(); img.save(b, fmt, **kw); C[name] = b.getvalue()
# 1 flat graphics / screenshot-like
g = Image.new('RGB', (W, H), (255, 255, 255)); d = ImageDraw.Draw(g)
for i in range(12):
    d.rectangle([i * 20, i * 15, i * 20 + 60, i * 15 + 40], fill=(random.randint(0, 255), 50, 200))
d.text((10, 200), "Hello SPCA test image", fill=(0, 0, 0))
save(g, 'graphic_flat.bmp', 'BMP'); save(g, 'graphic_flat.png', 'PNG')
# 2 smooth gradient
x = np.linspace(0, 255, W); grad = np.stack([np.tile(x, (H, 1)), np.tile(x[:, None], (1, W)), np.full((H, W), 128)], -1).astype(np.uint8)
gi = Image.fromarray(grad); save(gi, 'gradient.bmp', 'BMP'); save(gi, 'gradient.png', 'PNG')
# 3 photo-like: smooth noise field
yy, xx = np.mgrid[0:H, 0:W]
f = (np.sin(xx / 17.0) * 60 + np.cos(yy / 23.0) * 60 + 128 + np.random.normal(0, 6, (H, W)))
ph = np.stack([f, np.roll(f, 20, 0), np.roll(f, 40, 1)], -1).clip(0, 255).astype(np.uint8)
pi = Image.fromarray(ph); save(pi, 'photolike.bmp', 'BMP'); save(pi, 'photolike.png', 'PNG'); save(pi, 'photolike.jpg', 'JPEG', quality=85)
# 4 pure noise image
ni = Image.fromarray(np.random.randint(0, 256, (H, W, 3), dtype=np.uint8)); save(ni, 'noise.bmp', 'BMP')
# 5 tiled pattern
tile = np.random.randint(0, 256, (16, 16, 3), dtype=np.uint8)
ti = Image.fromarray(np.tile(tile, (16, 16, 1))); save(ti, 'tiled_pattern.bmp', 'BMP'); save(ti, 'tiled_pattern.png', 'PNG')

C = {k: v for k, v in C.items() if v}
rows = []
print(f"{'file':24}{'orig':>8}{'zlib':>8}{'bz2':>8}{'lzma':>8}{'SPCA':>8}  best-mode      ok  t(s)")
for name, data in C.items():
    rep = {}
    t = time.time(); blob = spca.compress(data, rep); tc = time.time() - t
    ok = spca.decompress(blob) == data
    z = len(zlib.compress(data, 9)); b = len(bz2.compress(data, 9)); l = len(lzma.compress(data, preset=9))
    rows.append(dict(name=name, orig=len(data), zlib=z, bz2=b, lzma=l, spca=len(blob), best=rep.get('best'), ok=ok, t=round(tc, 1), rep=rep))
    print(f"{name:24}{len(data):>8}{z:>8}{b:>8}{l:>8}{len(blob):>8}  {rep.get('best','-'):14} {'Y' if ok else 'N'}  {tc:.1f}")
json.dump(rows, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'results.json'), 'w'), indent=1)
