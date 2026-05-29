#!/usr/bin/env python3
"""
rename_videos.py
================
Renames existing processed videos from the old naming (2026-04-23-day2-01.mp4)
to the new naming (2026-04-23-day2-v01.mp4), then extracts thumbnails.

Also updates metadata.json to reflect the new stems.

Usage:
  python3 rename_videos.py --dry-run   ← preview changes
  python3 rename_videos.py             ← apply changes
"""

import argparse
import json
import re
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

MAX_WIDTH     = 1400
THUMB_WIDTH   = 400
WEBP_QUALITY  = 82
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


def old_to_new_stem(stem: str) -> str:
    """
    Convert 2026-04-23-day2-01 → 2026-04-23-day2-v01
    Handles flagged stems too: 2026-04-23-day2-01~ → 2026-04-23-day2-v01~
    """
    flagged = stem.endswith("~")
    s = stem.rstrip("~")
    # Match the trailing -NN index (no v prefix already)
    m = re.match(r'^(.*-day\d+)-(\d+)$', s)
    if not m:
        return stem  # already has v or unrecognised format, leave alone
    base, idx = m.group(1), m.group(2)
    new = f"{base}-v{idx}"
    if flagged:
        new += "~"
    return new


def run(repo_dir: Path, dry_run: bool):
    video_dir = repo_dir / "assets/images/photos/video"
    thumb_dir = repo_dir / "assets/images/photos/thumb"
    med_dir   = repo_dir / "assets/images/photos/med"
    meta_path = repo_dir / "media_pipeline/metadata.json"

    if not video_dir.exists():
        sys.exit(f"Video folder not found: {video_dir}")

    # Load metadata
    metadata = {}
    if meta_path.exists():
        raw = meta_path.read_text().strip()
        if raw:
            metadata = json.loads(raw)

    # Build reverse map: old_stem → original_filename
    stem_to_key = {v["output"]: k for k, v in metadata.items() if v.get("type") == "video"}

    videos = sorted(video_dir.glob("*.mp4"))
    print(f"\nFound {len(videos)} MP4 files\n")

    renamed = 0
    thumbed = 0
    skipped = 0

    for video in videos:
        stem = video.stem
        new_stem = old_to_new_stem(stem)

        if new_stem == stem:
            print(f"  — {stem}  (already renamed or unrecognised)")
            skipped += 1
            continue

        new_video_path = video_dir / f"{new_stem}.mp4"
        new_thumb_path = thumb_dir / f"{new_stem}.webp"
        new_med_path   = med_dir   / f"{new_stem}.webp"

        print(f"  🎬 {stem} → {new_stem}")

        if dry_run:
            renamed += 1
            continue

        # Rename the MP4
        video.rename(new_video_path)
        renamed += 1

        # Extract thumbnail with new stem
        try:
            extract_thumbnail(new_video_path, new_thumb_path, new_med_path)
            print(f"     ✓ thumbnail extracted")
            thumbed += 1
        except Exception as e:
            print(f"     ⚠ thumbnail failed: {e}")

        # Update metadata
        if stem in stem_to_key:
            key = stem_to_key[stem]
            metadata[key]["output"] = new_stem
            print(f"     ✓ metadata updated")

    if not dry_run and renamed:
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        meta_path.write_text(json.dumps(metadata, indent=2))
        print(f"\n✅ metadata.json updated")

    action = "would rename" if dry_run else "renamed"
    print(f"\nDone. {renamed} {action}, {thumbed} thumbnails extracted, {skipped} skipped.")
    if dry_run:
        print("Run without --dry-run to apply changes.")


def main():
    parser = argparse.ArgumentParser(description="Rename videos to v-prefixed stems and extract thumbnails")
    parser.add_argument("--repo",    default=REPO_DIR)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    run(Path(args.repo).expanduser().resolve(), dry_run=args.dry_run)


if __name__ == "__main__":
    main()