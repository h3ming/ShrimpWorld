#!/usr/bin/env python3
"""
Walstad Shrimp Log — Media Processing Pipeline
===============================================
Processes AirDropped iPhone media (JPEG, HEIC, MOV) into web-ready
assets named by shrimp-day, with a 5am day boundary.

Output naming: YYYY-MM-DD-dayN-01, -02, etc.
  - YYYY-MM-DD : the shrimp day (rolls over at 5am, not midnight)
  - dayN       : tank day number counted from TANK_START_DATE
  - 01, 02...  : index within that day, sorted by capture time

Files where the date had to be interpolated from neighbors get a ~
suffix: e.g. 2026-04-17-day3-02~.webp — review these manually.

─────────────────────────────────────────────
EDIT THESE SETTINGS BEFORE RUNNING:
─────────────────────────────────────────────
"""

from datetime import datetime

# When did the tank start? Day 1 is this date.
TANK_START_DATE = datetime(2026, 4, 22)

# Folder of AirDropped originals (outside the repo)
ORIGINALS_DIR = "/Users/heming/Desktop/tank-media"

# Jekyll repo root
REPO_DIR = "/Users/heming/Desktop/ShrimpWorld"

"""─────────────────────────────────────────────
Usage:
  python3 process_media.py            ← process all unprocessed originals
  python3 process_media.py --dry-run  ← preview without writing anything
─────────────────────────────────────────────
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import timedelta
from io import BytesIO
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
    pass  # HEIC will fall back to ffmpeg

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

DAY_BOUNDARY_HOUR = 5        # photos before 5am belong to the previous day

MAX_WIDTH     = 1400          # medium image max width (px)
THUMB_WIDTH   = 400           # thumbnail max width (px)
WEBP_QUALITY  = 82            # medium WebP quality
THUMB_QUALITY = 72            # thumbnail WebP quality

VIDEO_WIDTH = 1280            # output video max width (px)
VIDEO_CRF   = 28              # H.264 CRF — lower = better quality / larger file

STILL_EXTS = {".jpg", ".jpeg", ".png", ".heic", ".webp"}
VIDEO_EXTS = {".mov", ".mp4"}

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

def make_paths(repo_dir: Path) -> dict:
    return {
        "med":      repo_dir / "assets/images/photos/med",
        "thumb":    repo_dir / "assets/images/photos/thumb",
        "video":    repo_dir / "assets/images/photos/video",
        "metadata": repo_dir / "media_pipeline/metadata.json",
        "flagged":  repo_dir / "media_pipeline/flagged.json",
    }

# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------

def shrimp_date(dt: datetime):
    """Return the shrimp-day date — before 5am counts as the previous day."""
    if dt.hour < DAY_BOUNDARY_HOUR:
        dt = dt - timedelta(days=1)
    return dt.date()


def tank_day(dt: datetime) -> int:
    """Days since tank start, 1-indexed."""
    day = shrimp_date(dt)
    return (day - TANK_START_DATE.date()).days + 1


def get_mdls_datetime(path: Path) -> Optional[datetime]:
    """
    Read kMDItemContentCreationDate via macOS mdls (Spotlight metadata).
    This is what Finder shows in Get Info, and survives edits better than EXIF.
    """
    try:
        result = subprocess.run(
            ["mdls", "-name", "kMDItemContentCreationDate", "-raw", str(path)],
            capture_output=True, text=True, timeout=5
        )
        raw = result.stdout.strip()
        if raw and raw != "(null)":
            # mdls returns: 2026-04-17 21:11:32 +0000
            raw = raw.split(".")[0]  # strip fractional seconds if present
            # Parse, then convert from UTC to local time
            dt_utc = datetime.strptime(raw, "%Y-%m-%d %H:%M:%S +0000")
            # Convert UTC → local
            import calendar, time
            timestamp = calendar.timegm(dt_utc.timetuple())
            return datetime.fromtimestamp(timestamp)
    except Exception:
        pass
    return None


def get_image_datetime(path: Path) -> Optional[datetime]:
    """
    Try in order:
      1. mdls kMDItemContentCreationDate (Spotlight — survives edits, what Finder shows)
      2. EXIF DateTimeOriginal (original capture time)
      3. EXIF DateTime (set on edit — last resort)
    Returns None if nothing found.
    """
    # 1. Spotlight metadata
    dt = get_mdls_datetime(path)
    if dt:
        return dt

    # 2 & 3. EXIF
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
    """
    Extract capture datetime from video metadata via ffprobe.
    Tries in order:
      1. com.apple.quicktime.creationdate — iPhone local time, most accurate
      2. creation_time — UTC, converted to local (fallback)
    """
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json",
             "-show_entries", "format_tags", str(path)],
            capture_output=True, text=True, timeout=10
        )
        tags = json.loads(result.stdout).get("format", {}).get("tags", {})

        # 1. Prefer Apple's local-time field — format: 2026-05-21T23:33:31-0500
        quicktime_date = tags.get("com.apple.quicktime.creationdate")
        if quicktime_date:
            return datetime.fromisoformat(quicktime_date).replace(tzinfo=None)

        # 2. Fall back to creation_time (UTC) and convert to local
        creation_time = tags.get("creation_time")
        if creation_time:
            creation_time = creation_time.replace("Z", "+00:00")
            return datetime.fromisoformat(creation_time).astimezone().replace(tzinfo=None)

    except Exception:
        pass
    return None

# ---------------------------------------------------------------------------
# IMG number extraction
# ---------------------------------------------------------------------------

def img_number(path: Path) -> Optional[int]:
    """Extract the number from IMG_NNNN style filenames. Returns None if not found."""
    m = re.search(r"(\d+)", path.stem)
    return int(m.group(1)) if m else None

# ---------------------------------------------------------------------------
# Date interpolation
# ---------------------------------------------------------------------------

def build_date_index(files: list[Path]) -> dict[int, datetime]:
    """
    Build a map of { img_number: datetime } for all files that have a real date.
    Used to interpolate dates for files that don't.
    """
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


def interpolate_datetime(path: Path, date_index: dict[int, datetime]) -> Optional[datetime]:
    """
    Given a file with no date, find the nearest neighbors by IMG number
    that do have dates and return the earlier one's datetime.
    Returns None if no neighbors exist at all.
    """
    n = img_number(path)
    if n is None or not date_index:
        return None

    known_numbers = sorted(date_index.keys())

    # Find closest below and above
    below = [k for k in known_numbers if k < n]
    above = [k for k in known_numbers if k > n]

    dt_below = date_index[below[-1]] if below else None
    dt_above = date_index[above[0]]  if above else None

    if dt_below and dt_above:
        return min(dt_below, dt_above)   # conservative: use earlier neighbor
    return dt_below or dt_above

# ---------------------------------------------------------------------------
# Naming
# ---------------------------------------------------------------------------

def next_index(base: str, output_dir: Path, ext: str, video: bool = False) -> int:
    """Return the next available 1-based index for base-NN*.ext in output_dir.
    Videos use a 'v' prefix on the index: base-v01.mp4"""
    existing = list(output_dir.glob(f"{base}-*.{ext}"))
    numbers = []
    for f in existing:
        stem = f.stem.rstrip("~")
        part = stem.split("-")[-1].lstrip("v")
        try:
            numbers.append(int(part))
        except ValueError:
            pass
    return max(numbers, default=0) + 1


def make_stem(dt: datetime, out_dir: Path, ext: str,
              flagged: bool = False, video: bool = False) -> str:
    """
    Build the full output stem: YYYY-MM-DD-dayN-NN
    Videos get a v prefix on the index: YYYY-MM-DD-dayN-vNN
    Appends ~ if flagged (date was interpolated).
    """
    day  = shrimp_date(dt)
    tday = tank_day(dt)
    base = f"{day.strftime('%Y-%m-%d')}-day{tday}"
    idx  = next_index(base, out_dir, ext, video=video)
    index_str = f"v{idx:02d}" if video else f"{idx:02d}"
    stem = f"{base}-{index_str}"
    if flagged:
        stem += "~"
    return stem

# ---------------------------------------------------------------------------
# Image helpers
# ---------------------------------------------------------------------------

def open_image(path: Path) -> Image.Image:
    """Open image; fall back to ffmpeg for HEIC if pillow_heif isn't installed."""
    try:
        img = Image.open(path)
        img.load()
        return img
    except Exception:
        result = subprocess.run(
            ["ffmpeg", "-v", "quiet", "-i", str(path),
             "-f", "image2pipe", "-vcodec", "mjpeg", "pipe:1"],
            capture_output=True, timeout=30
        )
        if result.returncode == 0:
            return Image.open(BytesIO(result.stdout))
        raise RuntimeError(f"Cannot open image: {path}")


def save_webp(img: Image.Image, dest: Path, quality: int):
    dest.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(dest, "WEBP", quality=quality)

# ---------------------------------------------------------------------------
# Processors
# ---------------------------------------------------------------------------

def extract_video_thumbnail(video_path: Path, thumb_path: Path, med_path: Path):
    """Extract first frame from video and save as WebP thumbnail and med."""
    import tempfile
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

def process_image(path: Path, paths: dict, metadata: dict,
                  flagged: dict, date_index: dict, dry_run: bool):
    dt = get_image_datetime(path)
    is_flagged = False

    if dt is None:
        dt = interpolate_datetime(path, date_index)
        if dt is None:
            print(f"  ✗  No date, no neighbors — skipping {path.name}")
            return
        is_flagged = True
        print(f"  📸~ {path.name} → interpolated from neighbors  [day {tank_day(dt)}]")
    else:
        print(f"  📸 {path.name}  [day {tank_day(dt)}]")

    stem       = make_stem(dt, paths["med"], "webp", flagged=is_flagged)
    med_path   = paths["med"]   / f"{stem}.webp"
    thumb_path = paths["thumb"] / f"{stem}.webp"

    print(f"     → {stem}")

    if dry_run:
        return

    img = open_image(path)
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")

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

    record = {
        "type": "image",
        "output": stem,
        "tank_day": tank_day(dt),
        "capture_date": dt.isoformat(),
        "date_interpolated": is_flagged,
    }
    metadata[path.name] = record
    if is_flagged:
        flagged[path.name] = record

    shutil.move(str(path), paths["processed"] / path.name)
    print(f"     ✓ saved + moved to processed/")


def process_video(path: Path, paths: dict, metadata: dict,
                  flagged: dict, date_index: dict, dry_run: bool):
    dt = get_video_datetime(path)
    is_flagged = False

    if dt is None:
        dt = interpolate_datetime(path, date_index)
        if dt is None:
            dt = datetime.fromtimestamp(path.stat().st_mtime)
            is_flagged = True
        else:
            is_flagged = True

    if is_flagged:
        print(f"  🎬~ {path.name} → interpolated  [day {tank_day(dt)}]")
    else:
        print(f"  🎬 {path.name}  [day {tank_day(dt)}]")

    stem     = make_stem(dt, paths["video"], "mp4", flagged=is_flagged, video=True)
    out_path = paths["video"] / f"{stem}.mp4"

    print(f"     → {stem}")

    if dry_run:
        return

    paths["video"].mkdir(parents=True, exist_ok=True)

    # scale=VIDEO_WIDTH:-2  : resize to max width, height rounded to even (H.264 req)
    # transpose via autorotate: ffmpeg respects the display matrix rotation flag
    # trunc(iw/2)*2:trunc(ih/2)*2 ensures both dimensions are even after any rotation
    scale_filter = (
        f"scale={VIDEO_WIDTH}:-2,"
        f"scale=trunc(iw/2)*2:trunc(ih/2)*2"
    )
    subprocess.run([
        "ffmpeg", "-i", str(path),
        "-vf", scale_filter,
        "-vcodec", "libx264",
        "-crf", str(VIDEO_CRF),
        "-an",
        "-movflags", "+faststart",
        str(out_path)
    ], check=True)

    record = {
        "type": "video",
        "output": stem,
        "tank_day": tank_day(dt),
        "capture_date": dt.isoformat(),
        "date_interpolated": is_flagged,
    }
    metadata[path.name] = record
    if is_flagged:
        flagged[path.name] = record

    # Extract thumbnail from the processed video
    thumb_path = paths["thumb"] / f"{stem}.webp"
    med_path   = paths["med"]   / f"{stem}.webp"
    try:
        extract_video_thumbnail(out_path, thumb_path, med_path)
        print(f"     ✓ thumbnail extracted")
    except Exception as e:
        print(f"     ⚠ thumbnail extraction failed: {e}")

    shutil.move(str(path), paths["processed"] / path.name)
    print(f"     ✓ saved + moved to processed/")

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(originals_dir: Path, repo_dir: Path, dry_run: bool):
    paths = make_paths(repo_dir)
    paths["processed"] = originals_dir / "processed"

    if not dry_run:
        for key in ("med", "thumb", "video", "processed"):
            paths[key].mkdir(parents=True, exist_ok=True)
        paths["metadata"].parent.mkdir(parents=True, exist_ok=True)

    # Load existing metadata
    metadata = {}
    if paths["metadata"].exists():
        with open(paths["metadata"]) as f:
            metadata = json.load(f)

    flagged = {}
    if paths["flagged"].exists():
        with open(paths["flagged"]) as f:
            flagged = json.load(f)

    print("\n====================================")
    print(" SHRIMP MEDIA PIPELINE")
    if dry_run:
        print(" DRY RUN — nothing will be written")
    print("====================================\n")

    # Collect all unprocessed files
    all_files = sorted(f for f in originals_dir.iterdir() if f.is_file())
    files = [f for f in all_files if f.name not in metadata]
    skipped = len(all_files) - len(files)

    # Build date index from ALL files (including already-processed ones won't
    # be on disk, but unprocessed ones are enough for interpolation)
    print("🔎 Building date index for interpolation…")
    date_index = build_date_index(files)
    print(f"   {len(date_index)} files have reliable dates, "
          f"{len(files) - len(date_index)} will be interpolated\n")

    for file in files:
        ext = file.suffix.lower()
        if ext in STILL_EXTS:
            process_image(file, paths, metadata, flagged, date_index, dry_run)
        elif ext in VIDEO_EXTS:
            process_video(file, paths, metadata, flagged, date_index, dry_run)

    if skipped:
        print(f"\n(skipped {skipped} already-processed files)")

    if not dry_run:
        with open(paths["metadata"], "w") as f:
            json.dump(metadata, f, indent=2)
        with open(paths["flagged"], "w") as f:
            json.dump(flagged, f, indent=2)
        n_flagged = len(flagged)
        if n_flagged:
            print(f"\n⚠️  {n_flagged} files had interpolated dates → review flagged.json")
            print(f"   (look for ~ in filenames in assets/images/photos/)")
        print(f"\n✅ metadata.json updated")

    print("\nDone.")


def main():
    parser = argparse.ArgumentParser(description="Shrimp media pipeline")
    parser.add_argument("--originals", default=ORIGINALS_DIR,
                        help="Folder of AirDropped originals")
    parser.add_argument("--repo",      default=REPO_DIR,
                        help="Jekyll repo root")
    parser.add_argument("--dry-run",   action="store_true",
                        help="Preview without writing or moving any files")
    args = parser.parse_args()

    originals_dir = Path(args.originals).expanduser().resolve()
    repo_dir      = Path(args.repo).expanduser().resolve()

    if not originals_dir.exists():
        sys.exit(f"Originals folder not found: {originals_dir}")

    run(originals_dir, repo_dir, dry_run=args.dry_run)


if __name__ == "__main__":
    main()