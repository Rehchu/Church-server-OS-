#!/usr/bin/env python3
"""Draws the boot splash's pictures with no image library: the Arise flame
(the same seven-point shape the desktop uses), the progress bar and its box.
Pure Python PNG writer (zlib + struct). Run by install.sh; output goes next to
the Plymouth theme.

    python3 scripts/gen-plymouth-art.py /usr/share/plymouth/themes/ariseos
"""
import struct
import sys
import zlib
from pathlib import Path

INK = (10, 10, 12)
RED = (214, 34, 45)
BONE = (244, 242, 240)
# 50% 0, 80% 35%, 100% 70%, 70% 100%, 30% 100%, 0 70%, 20% 35%  (x, y as fractions)
FLAME = [(0.50, 0.00), (0.80, 0.35), (1.00, 0.70), (0.70, 1.00), (0.30, 1.00), (0.00, 0.70), (0.20, 0.35)]


def png(path: Path, w: int, h: int, pixels):
    """pixels: list of rows, each a list of (r, g, b, a)."""
    raw = b"".join(b"\x00" + bytes(c for px in row for c in px) for row in pixels)

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def inside(poly, x, y) -> bool:
    """Even-odd point-in-polygon."""
    hit = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            xi = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < xi:
                hit = not hit
    return hit


def flame(size: int, colour, pad: int = 12, ss: int = 3):
    """The flame on a transparent square, supersampled for soft edges."""
    poly = [(pad + fx * (size - 2 * pad), pad + fy * (size - 2 * pad)) for fx, fy in FLAME]
    rows = []
    for y in range(size):
        row = []
        for x in range(size):
            cover = 0
            for sy in range(ss):
                for sx in range(ss):
                    if inside(poly, x + (sx + 0.5) / ss, y + (sy + 0.5) / ss):
                        cover += 1
            a = round(255 * cover / (ss * ss))
            row.append((*colour, a))
        rows.append(row)
    return rows


def bar(w: int, h: int, colour, alpha: int = 255):
    return [[(*colour, alpha)] * w for _ in range(h)]


def main(out: str):
    d = Path(out)
    d.mkdir(parents=True, exist_ok=True)
    png(d / "flame.png", 160, 160, flame(160, RED))
    png(d / "progress_box.png", 240, 4, bar(240, 4, (38, 38, 44)))
    png(d / "progress_bar.png", 240, 4, bar(240, 4, RED))
    png(d / "dot.png", 6, 6, bar(6, 6, BONE))
    print(f"wrote flame.png, progress_box.png, progress_bar.png, dot.png in {d}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "config/plymouth/ariseos")
