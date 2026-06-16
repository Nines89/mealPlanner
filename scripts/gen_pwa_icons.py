"""Genera icone PNG semplici per la PWA (stdlib, niente Pillow)."""
import struct
import zlib
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
OUT = BASE_DIR / "static" / "pwa"


def _chunk(tag: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(tag + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)


def write_png(path: Path, width: int, height: int, r: int, g: int, b: int) -> None:
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    row = b"\x00" + bytes([r, g, b]) * width
    raw = row * height
    idat = zlib.compress(raw, 9)
    path.write_bytes(sig + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", idat) + _chunk(b"IEND", b""))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    # Verde smeraldo vicino a theme_color #059669
    write_png(OUT / "icon-192.png", 192, 192, 5, 150, 105)
    write_png(OUT / "icon-512.png", 512, 512, 5, 150, 105)
    print("Written:", OUT / "icon-192.png", OUT / "icon-512.png")


if __name__ == "__main__":
    main()
