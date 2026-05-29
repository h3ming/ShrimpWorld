#!/usr/bin/env python3
"""
rotate_photo.py — fix orientation of already-processed images

Usage:
  python3 rotate_photo.py 2026-05-24-day33-01 90
  python3 rotate_photo.py 2026-05-24-day33-02~ 180
  python3 rotate_photo.py 2026-05-24-day33-03 -90

Rotates both the med and thumb versions in place.
Positive = clockwise, negative = counter-clockwise.
"""

import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    sys.exit("Missing Pillow — run: pip install Pillow --break-system-packages")

# ── Config ────────────────────────────────────────────────────────────────────

REPO_DIR = "/Users/heming/Desktop/ShrimpWorld"

# ─────────────────────────────────────────────────────────────────────────────

SIZES = {
    "med":   Path(REPO_DIR) / "assets/images/photos/med",
    "thumb": Path(REPO_DIR) / "assets/images/photos/thumb",
}


def rotate(stem, degrees):
    degrees = degrees % 360
    if degrees == 0:
        print("0 degrees — nothing to do.")
        return

    # PIL rotate is counter-clockwise, negate for intuitive clockwise input
    pil_degrees = -degrees

    found_any = False
    for size, folder in SIZES.items():
        path = folder / f"{stem}.webp"
        if not path.exists():
            print(f"  x not found: {path}")
            continue

        found_any = True
        img = Image.open(path)
        rotated = img.rotate(pil_degrees, expand=True)
        rotated.save(path, "WEBP", quality=85)
        print(f"  ok rotated {degrees} clockwise: {path.name}  ({size})")

    if not found_any:
        print(f"No files found for stem '{stem}' — check the name and try again.")


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)

    stem = sys.argv[1]
    try:
        degrees = int(sys.argv[2])
    except ValueError:
        sys.exit(f"Degrees must be an integer, got: {sys.argv[2]}")

    print(f"\nRotating {stem} by {degrees} degrees...")
    rotate(stem, degrees)
    print()


if __name__ == "__main__":
    main()