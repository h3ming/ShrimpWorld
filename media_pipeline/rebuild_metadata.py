#!/usr/bin/env python3
"""
rebuild_metadata.py
===================
Scans the processed/ folder and rebuilds metadata.json from scratch
using the same date logic as process_media.py.

Does not move, copy, or modify any files.

Usage:
  python3 rebuild_metadata.py
  python3 rebuild_metadata.py --dry-run
"""

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

try:
    from PIL import Image
    from PIL.ExifTags import TAGS
except ImportError:
    sys.exit("Missing Pillow — run: pip install Pillow --break-system-packages")

try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:
    pass

# ── Config ────────────────────────────────────────────────────────────────────

TANK_START_DATE    = datetime(2026, 4, 22)
DAY_BOUNDARY_HOUR  = 5
ORIGINALS_DIR      = "/Users/heming/Desktop/tank-media"
REPO_DIR           = "/Users/heming/Desktop/ShrimpWorld"

# ─────────────────────────────────────────────────────────────────────────────

STILL_EXTS = {".jpg", ".jpeg", ".png", ".heic", ".webp"}
VIDEO_EXTS = {".mov", ".mp4"}


def shrimp_date(dt: datetime):
    if dt.hour < DAY_BOUNDARY_HOUR:
        dt = dt - timedelta(days=1)
    return dt.date()


def tank_day(dt: datetime) -> int:
    return (shrimp_date(dt) - TANK_START_DATE.date()).days + 1


def get_image_datetime(path: Path) -> Optional[datetime]:
    try:
        img = Image.open(path)
        exif = img.getexif()
        if exif:
            fallback = None
            for tag_id, value in exif.items():
                tag = TAGS.get(tag_id)
                if tag == "DateTimeOriginal":
                    return datetime.strptime(value, "%Y:%m:%d %H:%M:%S")
                if tag == "DateTime":
                    fallback = value
            if fallback:
                return datetime.strptime(fallback, "%Y:%m:%d %H:%M:%S")
    except Exception:
        pass
    return None


def get_video_datetime(path: Path) -> Optional[datetime]:
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json",
             "-show_entries", "format_tags", str(path)],
            capture_output=True, text=True, timeout=10
        )
        tags = json.loads(result.stdout).get("format", {}).get("tags", {})
        quicktime_date = tags.get("com.apple.quicktime.creationdate")
        if quicktime_date:
            return datetime.fromisoformat(quicktime_date).replace(tzinfo=None)
        creation_time = tags.get("creation_time")
        if creation_time:
            creation_time = creation_time.replace("Z", "+00:00")
            return datetime.fromisoformat(creation_time).astimezone().replace(tzinfo=None)
    except Exception:
        pass
    return None


def img_number(path: Path) -> Optional[int]:
    m = re.search(r"(\d+)", path.stem)
    return int(m.group(1)) if m else None


def build_date_index(files: list) -> dict:
    index = {}
    for f in files:
        n = img_number(f)
        if n is None:
            continue
        ext = f.suffix.lower()
        dt = None
        if ext in STILL_EXTS:
            dt = get_image_datetime(f)
        elif ext in VIDEO_EXTS:
            dt = get_video_datetime(f)
        if dt:
            index[n] = dt
    return index


def interpolate_datetime(path: Path, date_index: dict) -> Optional[datetime]:
    n = img_number(path)
    if n is None or not date_index:
        return None
    known = sorted(date_index.keys())
    below = [k for k in known if k < n]
    above = [k for k in known if k > n]
    dt_below = date_index[below[-1]] if below else None
    dt_above = date_index[above[0]]  if above else None
    if dt_below and dt_above:
        return min(dt_below, dt_above)
    return dt_below or dt_above


def output_stem_for(path: Path, existing_metadata: dict) -> Optional[str]:
    """
    Find the output stem that process_media.py would have assigned.
    Look it up in existing metadata first, then derive from filename pattern.
    """
    # Check existing metadata by original filename
    if path.name in existing_metadata:
        return existing_metadata[path.name].get("output")
    return None


def run(originals_dir: Path, repo_dir: Path, dry_run: bool):
    processed_dir = originals_dir / "processed"
    metadata_path = repo_dir / "media_pipeline/metadata.json"
    flagged_path  = repo_dir / "media_pipeline/flagged.json"

    if not processed_dir.exists():
        sys.exit(f"Processed folder not found: {processed_dir}")

    # Load existing metadata — we'll merge into this
    existing_metadata = {}
    if metadata_path.exists():
        with open(metadata_path) as f:
            raw = f.read().strip()
            if raw:
                existing_metadata = json.loads(raw)

    print("\n====================================")
    print(" REBUILD METADATA")
    if dry_run:
        print(" DRY RUN — metadata.json will not be written")
    print("====================================\n")

    files = sorted(f for f in processed_dir.iterdir() if f.is_file())
    print(f"Found {len(files)} files in processed/\n")

    # Build date index for interpolation
    date_index = build_date_index(files)
    print(f"  {len(date_index)} files have reliable dates\n")

    metadata = {}
    flagged  = {}

    for file in files:
        ext = file.suffix.lower()
        if ext not in STILL_EXTS and ext not in VIDEO_EXTS:
            continue

        is_flagged = False

        if ext in STILL_EXTS:
            dt = get_image_datetime(file)
            ftype = "image"
        else:
            dt = get_video_datetime(file)
            ftype = "video"

        if dt is None:
            dt = interpolate_datetime(file, date_index)
            is_flagged = dt is not None
            if dt is None:
                dt = datetime.fromtimestamp(file.stat().st_mtime)
                is_flagged = True

        # Get output stem from existing metadata if available
        output = None
        if file.name in existing_metadata:
            output = existing_metadata[file.name].get("output")

        if output is None:
            # Derive from what we know — best guess from date
            day  = shrimp_date(dt)
            tday = tank_day(dt)
            output = f"{day.strftime('%Y-%m-%d')}-day{tday}-??"
            print(f"  ⚠  {file.name} — no existing output stem, using: {output}")
        else:
            flag_marker = "~" if is_flagged else ""
            print(f"  {'📸' if ftype == 'image' else '🎬'}{flag_marker} {file.name} → {output}")

        record = {
            "type":               ftype,
            "output":             output,
            "tank_day":           tank_day(dt),
            "capture_date":       dt.isoformat(),
            "date_interpolated":  is_flagged,
        }
        metadata[file.name] = record
        if is_flagged:
            flagged[file.name] = record

    # Merge with existing (existing takes priority for already-known files)
    merged = {**metadata, **existing_metadata}
    merged_flagged = {k: v for k, v in merged.items() if v.get("date_interpolated")}

    print(f"\n{len(merged)} total records ({len(merged) - len(existing_metadata)} new)")

    if dry_run:
        print("\n(dry run — nothing written)")
    else:
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        with open(metadata_path, "w") as f:
            json.dump(merged, f, indent=2)
        with open(flagged_path, "w") as f:
            json.dump(merged_flagged, f, indent=2)
        print(f"\n✅ metadata.json written ({len(merged)} records)")
        if merged_flagged:
            print(f"⚠  flagged.json updated ({len(merged_flagged)} interpolated dates)")

    print("\nDone.")


def main():
    parser = argparse.ArgumentParser(description="Rebuild metadata.json from processed/ folder")
    parser.add_argument("--originals", default=ORIGINALS_DIR)
    parser.add_argument("--repo",      default=REPO_DIR)
    parser.add_argument("--dry-run",   action="store_true")
    args = parser.parse_args()

    run(
        Path(args.originals).expanduser().resolve(),
        Path(args.repo).expanduser().resolve(),
        dry_run=args.dry_run
    )


if __name__ == "__main__":
    main()