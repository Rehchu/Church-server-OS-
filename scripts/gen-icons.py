#!/usr/bin/env python3
"""Writes web/icons/*.png (the home-screen and PWA icons): the flame on ink,
pure Python (zlib + struct), no PIL. Re-run after changing the mark.

    python3 scripts/gen-icons.py
"""
import struct
import zlib
from pathlib import Path

INK = (10, 10, 12)
RED = (214, 34, 45)
OUT = Path(__file__).resolve().parents[1] / "web" / "icons"
FLAME = [(0.50, 0.00), (0.80, 0.35), (1.00, 0.70), (0.70, 1.00), (0.30, 1.00), (0.00, 0.70), (0.20, 0.35)]


def inside(px, py, poly):
    n, hit = len(poly), False
    for i in range(n):
        x1, y1 = poly[i]; x2, y2 = poly[(i + 1) % n]
        if (y1 > py) != (y2 > py) and px < (x2 - x1) * (py - y1) / (y2 - y1 + 1e-12) + x1:
            hit = not hit
    return hit


def png(size: int, pad: float = 0.22) -> bytes:
    rows = []
    s0, s1 = size * pad, size * (1 - pad)
    for y in range(size):
        row = bytearray([0])
        for x in range(size):
            fx, fy = (x - s0) / (s1 - s0), (y - s0) / (s1 - s0)
            # supersample 2x2 for a soft edge
            hits = sum(inside(fx + dx / size * 2, fy + dy / size * 2, FLAME) for dx in (-0.25, 0.25) for dy in (-0.25, 0.25))
            t = hits / 4
            row += bytes(int(INK[i] + (RED[i] - INK[i]) * t) for i in range(3))
        rows.append(bytes(row))
    raw = b"".join(rows)
    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for name, size in (("icon-192.png", 192), ("icon-512.png", 512), ("apple-touch-icon.png", 180), ("icon-maskable-512.png", 512)):
        (OUT / name).write_bytes(png(size, 0.30 if "maskable" in name else 0.22))
        print("wrote", OUT / name, size)
