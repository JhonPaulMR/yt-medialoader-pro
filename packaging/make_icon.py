"""
Gera assets/icon.ico (quadrado arredondado vermelho com seta de download branca)
sem depender do Pillow: desenha os pixels e grava o ICO/BMP direto.

Uso: python packaging/make_icon.py
"""

import struct
from pathlib import Path

SIZES = (16, 24, 32, 48, 64, 128, 256)
RED = (0x14, 0x09, 0xE5)  # BGR de #e50914
SAMPLES = 4               # supersampling para bordas suaves


def _coverage(size, x, y):
    """Retorna (alpha_fundo, alpha_triângulo) do pixel, de 0 a 1."""
    radius = size * 0.22
    bg = tri = 0
    for sy in range(SAMPLES):
        for sx in range(SAMPLES):
            px = x + (sx + 0.5) / SAMPLES
            py = y + (sy + 0.5) / SAMPLES
            # cantos arredondados
            cx = min(max(px, radius), size - radius)
            cy = min(max(py, radius), size - radius)
            if (px - cx) ** 2 + (py - cy) ** 2 > radius ** 2:
                continue
            bg += 1
            # seta de download: haste + ponta + base
            u, v = px / size, py / size
            shaft = 0.43 <= u <= 0.57 and 0.18 <= v <= 0.50
            head = 0.48 <= v <= 0.70 and abs(u - 0.5) <= (0.70 - v) * 1.15
            base = 0.24 <= u <= 0.76 and 0.76 <= v <= 0.84
            if shaft or head or base:
                tri += 1
    total = SAMPLES * SAMPLES
    return bg / total, tri / total


def _bitmap(size):
    rows = []
    for y in range(size - 1, -1, -1):  # BMP é de baixo para cima
        row = bytearray()
        for x in range(size):
            bg, tri = _coverage(size, x, y)
            if bg == 0:
                row += b"\0\0\0\0"
                continue
            b, g, r = (int(c * (1 - tri / bg) + 255 * (tri / bg)) for c in RED)
            row += bytes((b, g, r, int(255 * bg)))
        rows.append(bytes(row))
    pixels = b"".join(rows)
    mask_row = ((size + 31) // 32) * 4
    mask = b"\0" * (mask_row * size)  # transparência vem do canal alfa
    header = struct.pack("<IiiHHIIiiII", 40, size, size * 2, 1, 32, 0, len(pixels) + len(mask), 0, 0, 0, 0)
    return header + pixels + mask


def build(path):
    images = [_bitmap(size) for size in SIZES]
    out = bytearray(struct.pack("<HHH", 0, 1, len(SIZES)))
    offset = 6 + 16 * len(SIZES)
    for size, data in zip(SIZES, images):
        dim = 0 if size == 256 else size
        out += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    for data in images:
        out += data
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(out))
    return path


if __name__ == "__main__":
    target = Path(__file__).resolve().parent.parent / "assets" / "icon.ico"
    print(f"Ícone gerado: {build(target)}")
