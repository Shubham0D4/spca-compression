# SPCA: Sequence-Position Compression Algorithm

A prototype lossless compressor built on one idea: find repeated byte sequences, replace them with tokens, and compress the *structure of their positions* (first position + count + gap pattern) instead of storing every position.

## How it works
1. Find repeated substrings (lengths 4-64) and pick them by net estimated saving.
2. Tokenize non-overlapping occurrences with a deterministic greedy parse.
3. For each token, encode its positions as constant-gap, periodic-gap, or varint gaps, whichever is smallest.
4. Build several candidates (SPCA raw, SPCA+zlib, SPCA split, direct zlib, stored) and keep the smallest.
5. Decode reverses the steps and verifies length and CRC32.

## Usage
```python
import spca
blob = spca.compress(data)
assert spca.decompress(blob) == data
```

Command line (any file, no extra dependencies):
```
python3 spca_cli.py test myfile.png myfile.txt   # compare vs zlib/bz2/lzma and verify round-trip
python3 spca_cli.py compress myfile.txt          # writes myfile.txt.spca
python3 spca_cli.py decompress myfile.txt.spca   # restores myfile.txt
```
The prototype is pure Python, so start with files under about 1 MB.

Run the benchmark (needs `pip install -r requirements.txt`; it uses some Linux system files as test inputs):
```
python3 bench.py
```

## Results (bytes, 22 test files; full data in results.json)
| File | Original | zlib | bz2 | lzma | SPCA |
|---|---|---|---|---|---|
| repeated_byte | 100,000 | 120 | 47 | 148 | **32** |
| periodic_abcd | 100,000 | 125 | 51 | 152 | **37** |
| periodic_irregular | 120,000 | 203 | 55 | 156 | **62** |
| sawtooth | 100,000 | 713 | 924 | 376 | **321** |
| tiled_pattern.bmp | 196,662 | 1,896 | 2,063 | 1,356 | 1,450 |
| json_records | 103,890 | 9,773 | 7,542 | 5,896 | 9,664 |
| source_code.py | 101,750 | 21,428 | 18,133 | 19,592 | 21,429 |
| gradient.bmp | 196,662 | 139,088 | 18,624 | 16,648 | 139,089 |

All files round-trip exactly.

## Findings
- Big wins on strictly periodic or repeated data (4x+ smaller than zlib).
- On text, code and CSV the selector falls back to zlib, so SPCA is zlib + 1 byte.
- bz2 and lzma beat it on most real-world data. Smooth images (gradients, photos) are not helped, since they have numeric structure rather than exact repeats.

## Status and next steps
First-pass prototype. Ideas: smarter parsing than greedy longest-match, entropy coding of literals and dictionary, image-aware delta filters, larger and more varied benchmark files.
