#!/usr/bin/env python3
"""Generate deterministic PWA icons and iOS splash images without Pillow.

The mark is a simple two-card split: two white rounded rectangles on the
application's primary green. Everything is drawn from integer coordinates so
the generated files are reproducible on any machine.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"
BACKGROUND = (11, 122, 91, 255)
FOREGROUND = (255, 255, 255, 255)


def rounded_rect(
    width: int,
    height: int,
    left: int,
    top: int,
    right: int,
    bottom: int,
    radius: int,
    color: tuple[int, int, int, int],
    pixels: bytearray,
) -> None:
    for y in range(max(0, top), min(height, bottom)):
        for x in range(max(0, left), min(width, right)):
            dx = 0
            dy = 0
            if x < left + radius:
                dx = left + radius - x
            elif x >= right - radius:
                dx = x - (right - radius - 1)
            if y < top + radius:
                dy = top + radius - y
            elif y >= bottom - radius:
                dy = y - (bottom - radius - 1)
            if dx * dx + dy * dy > radius * radius:
                continue
            offset = (y * width + x) * 4
            pixels[offset : offset + 4] = bytes(color)


def icon(size: int, *, maskable: bool = False, transparent_background: bool = False) -> bytes:
    pixels = bytearray(size * size * 4)
    if not transparent_background:
        background = BACKGROUND
        for y in range(size):
            for x in range(size):
                offset = (y * size + x) * 4
                pixels[offset : offset + 4] = bytes(background)

    # Maskable icons need the mark inside the 80% safe zone. Standard icons can
    # use a little more space.
    safe = 0.58 if maskable else 0.68
    mark_width = round(size * safe)
    mark_height = round(size * (safe + 0.06))
    left = (size - mark_width) // 2
    top = (size - mark_height) // 2
    gap = max(2, round(size * 0.035))
    card_width = (mark_width - gap) // 2
    radius = max(3, round(size * 0.07))

    rounded_rect(
        size,
        size,
        left,
        top,
        left + card_width,
        top + mark_height,
        radius,
        FOREGROUND,
        pixels,
    )
    rounded_rect(
        size,
        size,
        left + card_width + gap,
        top,
        left + mark_width,
        top + mark_height,
        radius,
        FOREGROUND,
        pixels,
    )
    # Punch a dark notch out of the right card so the mark reads as a split.
    notch = max(2, round(size * 0.025))
    rounded_rect(
        size,
        size,
        left + card_width + gap + card_width // 2 - notch // 2,
        top + mark_height // 2 - notch // 2,
        left + card_width + gap + card_width // 2 + notch - notch // 2,
        top + mark_height // 2 + notch - notch // 2,
        max(1, notch // 2),
        BACKGROUND,
        pixels,
    )
    return encode_png(size, size, pixels)


def encode_png(width: int, height: int, pixels: bytearray) -> bytes:
    raw = bytearray()
    stride = width * 4
    for y in range(height):
        raw.append(0)
        raw.extend(pixels[y * stride : (y + 1) * stride])

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + chunk(b"IEND", b"")
    )


def splash(width: int, height: int) -> bytes:
    pixels = bytearray(bytes(BACKGROUND) * (width * height))
    # Decode-free overlay: draw the same rounded cards centered instead of
    # embedding one PNG in another.
    mark_width = round(min(width, height) * 0.35)
    mark_height = round(mark_width * 1.1)
    left = (width - mark_width) // 2
    top = (height - mark_height) // 2
    gap = max(2, round(mark_width * 0.035))
    card_width = (mark_width - gap) // 2
    radius = max(3, round(mark_width * 0.07))
    rounded_rect(width, height, left, top, left + card_width, top + mark_height, radius, FOREGROUND, pixels)
    rounded_rect(
        width,
        height,
        left + card_width + gap,
        top,
        left + mark_width,
        top + mark_height,
        radius,
        FOREGROUND,
        pixels,
    )
    return encode_png(width, height, pixels)


def main() -> None:
    icons = PUBLIC / "icons"
    icons.mkdir(parents=True, exist_ok=True)
    (icons / "icon-192.png").write_bytes(icon(192))
    (icons / "icon-512.png").write_bytes(icon(512))
    (icons / "maskable-512.png").write_bytes(icon(512, maskable=True))
    (PUBLIC / "apple-touch-icon.png").write_bytes(icon(180))
    (PUBLIC / "favicon.png").write_bytes(icon(64))

    splash_dir = PUBLIC / "splash"
    splash_dir.mkdir(parents=True, exist_ok=True)
    for width, height, name in (
        (1170, 2532, "iphone-1170x2532.png"),
        (1290, 2796, "iphone-1290x2796.png"),
        (1536, 2048, "ipad-1536x2048.png"),
        (2048, 2732, "ipad-2048x2732.png"),
    ):
        (splash_dir / name).write_bytes(splash(width, height))

    print(f"Generated PWA icons in {icons} and splash images in {splash_dir}")


if __name__ == "__main__":
    main()
