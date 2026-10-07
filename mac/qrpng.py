"""Código QR en PNG, en Python puro: igual en macOS y en Linux, sin programas aparte.

El código lo arma qrcodegen (Project Nayuki, licencia MIT: mac/qrcodegen.py y LICENSES/qrcodegen.txt), con corrección
de errores «M» y un cuadro de margen, como lo hacía CoreImage en la Mac. La imagen es como la de siempre en One TV:
cuadritos claros (el color del texto) sobre negro, todos del mismo tamaño y nítidos, centrados con margen negro.
La cámara del teléfono lo lee igual que uno negro sobre blanco.
"""

import os
import struct
import zlib
from pathlib import Path

from qrcodegen import QrCode, QrSegment

LIGHT = (242, 242, 237)   # el color del texto de One TV
DARK = (0, 0, 0)


def modules(text):
    """Los cuadros del código, con un cuadro de margen alrededor (como CoreImage): lista de filas de True/False."""
    qr = QrCode.encode_segments(QrSegment.make_segments(text), QrCode.Ecc.MEDIUM, boostecl=False)
    n = qr.get_size()
    return [[0 <= x < n and 0 <= y < n and qr.get_module(x, y) for x in range(-1, n + 1)] for y in range(-1, n + 1)]


def png_bytes(width, height, rows):
    """PNG de color (RGB, 8 bits) a partir de sus filas de bytes."""
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + row for row in rows)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def qr_png(text, size, margin=64):
    """PNG cuadrado de size px: cada cuadro del código mide lo mismo (lo más grande que cabe dejando al menos
    `margin` px de margen en total) y el código va centrado."""
    grid = modules(text)
    n = len(grid)
    scale = max(1, (size - margin) // n)
    off = (size - n * scale) // 2
    light, dark = bytes(LIGHT), bytes(DARK)
    blank = dark * size
    rows = [blank] * off
    for line in grid:
        row = dark * off + b"".join((light if on else dark) * scale for on in line) + dark * (size - off - n * scale)
        rows += [row] * scale
    rows += [blank] * (size - len(rows))
    return png_bytes(size, size, rows)


def write_qr(text, path, size, margin=64):
    """Escribe el PNG (de una vez: quien lo pida a la mitad no ve un archivo a medias)."""
    path = Path(path)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_bytes(qr_png(text, size, margin))
    tmp.replace(path)
    return path
