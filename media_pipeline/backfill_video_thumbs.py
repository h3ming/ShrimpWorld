#!/usr/bin/env python3
"""
backfill_video_thumbs.py
========================
Extracts thumbnails for already-processed videos that don't have one.
Looks in assets/images/photos/video/ for MP4s, and for each one that
doesn't have a matching WebP in thumb/, extracts the first frame.

Usage:
  python3 backfill_video_thumbs.py
  python3 backfill_video_thumbs.py --dry-run
"""

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    sys.exit("Missing Pillow — run: pip install Pillow --break-system-packages")

# ── Config ────────────────────────────────────────────────────────────────────

REPO_DIR = "/Users/heming/Desktop/ShrimpWorld"

# ─────────────────────────────────────────────────────────────────────────────

MAX_WIDTH    = 1400
THUMB_WIDTH  = 400
WEBP_QUALITY = 82
THUMB_QUALITY = 72


def save_webp(img: Image.Image, dest: Path, quality: int):
    dest.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(dest, "WEBP", quality=quality)


def extract_thumbnail(video_path: Path, thumb_path: Path, med_path: Path):
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    try:
        subprocess.run([
            "ffmpeg", "-v", "quiet", "-y",
            "-i", str(video_path),
            "-vframes", "1",
            "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
            str(tmp_path)
        ], check=True, capture_output=True)

        img = Image.open(tmp_path)

        if img.width > MAX_WIDTH:
            ratio = MAX_WIDTH / img.width
            img_med = img.resize((MAX_WIDTH, int(img.height * ratio)), Image.LANCZOS)
        else:
            img_med = img.copy()
        save_webp(img_med, med_path, WEBP_QUALITY)

        if img.width > THUMB_WIDTH:
            ratio = THUMB_WIDTH / img.width
            img_thumb = img.resize((THUMB_WIDTH, int(img.height * ratio)), Image.LANCZOS)
        else:
            img_thumb = img.copy()
        save_webp(img_thumb, thumb_path, THUMB_QUALITY)

    finally:
        tmp_path.unlink(missing_ok=True)


def run(repo_dir: Path, dry_run: bool):
    video_dir = repo_dir / "assets/images/photos/video"
    thumb_dir = repo_dir / "assets/images/photos/thumb"
    med_dir   = repo_dir / "assets/images/photos/med"

    if not video_dir.exists():
        sys.exit(f"Video folder not found: {video_dir}")

    videos = sorted(video_dir.glob("*.mp4"))
    if not videos:
        print("No MP4 files found.")
        return

    print(f"Found {len(videos)} videos\n")

    done = skipped = failed = 0

    # Load metadata to check which thumbs came from videos vs photos
    metadata_path = repo_dir / "media_pipeline/metadata.json"
    video_stems = set()
    if metadata_path.exists():
        import json
        with open(metadata_path) as f:
            meta = json.load(f)
        video_stems = {v["output"].rstrip("~") for v in meta.values() if v.get("type") == "video"}

    for video in videos:
        thumb_path = thumb_dir / f"{video.stem}.webp"
        med_path   = med_dir   / f"{video.stem}.webp"

        stem_clean = video.stem.rstrip("~")
        if thumb_path.exists() and stem_clean in video_stems:
            print(f"  — {video.stem}  (already has thumbnail)")
            skipped += 1
            continue

        print(f"  🎬 {video.stem}")

        if dry_run:
            print(f"     → would extract thumbnail")
            done += 1
            continue

        try:
            extract_thumbnail(video, thumb_path, med_path)
            print(f"     ✓ thumbnail saved")
            done += 1
        except Exception as e:
            print(f"     ✗ failed: {e}")
            failed += 1

    print(f"\nDone. {done} extracted, {skipped} skipped, {failed} failed.")


def main():
    parser = argparse.ArgumentParser(description="Backfill thumbnails for processed videos")
    parser.add_argument("--repo",    default=REPO_DIR, help="Jekyll repo root")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    args = parser.parse_args()

    run(Path(args.repo).expanduser().resolve(), dry_run=args.dry_run)


if __name__ == "__main__":
    main()