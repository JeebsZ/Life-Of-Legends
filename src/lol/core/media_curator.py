"""LUMA Media Studio & Aesthetic Lens: Smart Gallery Declutter & Instagram Post Scorer.

Provides offline, private computer vision analysis using Pillow for:
1. Smart Categorization (Screenshots, TikTok/Social Saves, Blurry/Low-res, Camera).
2. Instagram Aesthetic Scorer (Sharpness, Lighting balance, Color vibrancy, Composition/Ratio).
3. Batch Purge / Declutter operations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageFilter, ImageStat

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".heic"}


@dataclass
class AestheticReport:
    score: int  # 0..100
    rating_label: str  # e.g. "Feed Worthy ✨", "Good Post 👍"
    sharpness_score: int  # 0..100
    lighting_score: int  # 0..100
    vibrancy_score: int  # 0..100
    framing_score: int  # 0..100
    aspect_ratio_str: str  # "4:5", "1:1", "9:16", etc.
    resolution_str: str  # "1080 x 1350"
    badges: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)


@dataclass
class MediaFileItem:
    path: str
    filename: str
    category: str  # "screenshot", "social_save", "blurry", "camera"
    file_size_kb: int
    modified_time: str
    is_selected: bool = False
    report: AestheticReport | None = None


def classify_filename(filename: str) -> str:
    """Classify an image file into category based on filename patterns."""
    lower = filename.lower()

    # 1. Screenshots
    if any(k in lower for k in ("screenshot", "screen_shot", "screencap", "capture", "snip")):
        return "screenshot"

    # 2. TikTok & Social downloads
    if any(k in lower for k in ("tiktok", "snaptik", "instagram", "facebook", "fb_img", "download", "save_")):
        return "social_save"

    # 3. Default to Camera / Personal
    return "camera"


def scan_media_folder(folder_path: str, max_items: int = 100) -> list[MediaFileItem]:
    """Scan folder and return classified image items."""
    p = Path(folder_path)
    if not p.exists() or not p.is_dir():
        return []

    items: list[MediaFileItem] = []
    try:
        entries = sorted(
            [f for f in p.iterdir() if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS],
            key=lambda x: x.stat().st_mtime,
            reverse=True,
        )
    except (OSError, ValueError, TypeError):
        return []

    for entry in entries[:max_items]:
        cat = classify_filename(entry.name)
        size_kb = int(entry.stat().st_size / 1024)
        mtime_str = str(entry.stat().st_mtime)
        items.append(
            MediaFileItem(
                path=str(entry.resolve()),
                filename=entry.name,
                category=cat,
                file_size_kb=size_kb,
                modified_time=mtime_str,
            )
        )
    return items


def batch_delete_files(paths: list[str]) -> tuple[int, int]:
    """Safely delete selected files. Returns (success_count, fail_count)."""
    succeeded = 0
    failed = 0
    for file_path in paths:
        try:
            p = Path(file_path)
            if p.exists() and p.is_file():
                p.unlink()
                succeeded += 1
            else:
                failed += 1
        except (OSError, ValueError):
            failed += 1
    return succeeded, failed


def analyze_image_aesthetic(image_path: str) -> AestheticReport:
    """Analyze image with local computer vision and score for Instagram readiness."""
    try:
        with Image.open(image_path) as im:
            im = im.convert("RGB")
            # Downscale for fast, responsive analysis
            w, h = im.size
            analysis_im = im.copy()
            analysis_im.thumbnail((600, 600))
    except (OSError, ValueError):
        return AestheticReport(
            score=50,
            rating_label="Unanalyzable",
            sharpness_score=50,
            lighting_score=50,
            vibrancy_score=50,
            framing_score=50,
            aspect_ratio_str="Unknown",
            resolution_str="0 x 0",
            badges=[],
            suggestions=["Could not decode image format."],
        )

    # 1. Aspect Ratio & Framing Score (0..100)
    ratio = w / max(1, h)
    aspect_str = f"{w}:{h}"
    framing_score = 70
    ratio_tips: list[str] = []

    if 0.78 <= ratio <= 0.83:  # 4:5 portrait (ideal IG feed post: 80% screen coverage)
        framing_score = 100
        aspect_str = "4:5 Portrait"
    elif 0.95 <= ratio <= 1.05:  # 1:1 square
        framing_score = 95
        aspect_str = "1:1 Square"
    elif 0.54 <= ratio <= 0.58:  # 9:16 story/reel
        framing_score = 90
        aspect_str = "9:16 Story"
    elif ratio > 1.2:
        framing_score = 72
        aspect_str = "Landscape"
        ratio_tips.append("Landscape photos take up less feed space. Consider cropping to 4:5 vertical portrait for higher engagement!")
    else:
        aspect_str = f"{ratio:.2f}:1"
        ratio_tips.append("Crop to 4:5 portrait (1080x1350) to maximize Instagram feed coverage.")

    # Resolution check
    if min(w, h) >= 1080:
        framing_score = min(100, framing_score + 5)
    elif min(w, h) < 720:
        framing_score = max(40, framing_score - 20)
        ratio_tips.append("Resolution is below 720p. Instagram may compress or blur this image.")

    # 2. Sharpness Score (0..100) via edge Laplacian variance
    gray = analysis_im.convert("L")
    edges = gray.filter(ImageFilter.FIND_EDGES)
    edge_stat = ImageStat.Stat(edges)
    edge_var = edge_stat.var[0] if edge_stat.var else 0.0
    # Normal edge variance ranges roughly from 10 (blurry) to 250+ (ultra sharp)
    sharpness_score = int(min(100, max(20, (edge_var / 220.0) * 100)))

    # 3. Lighting & Exposure Score (0..100)
    stat = ImageStat.Stat(gray)
    mean_lum = stat.mean[0] if stat.mean else 128.0
    hist = gray.histogram()
    total_pixels = max(1, sum(hist))
    shadow_ratio = sum(hist[:25]) / total_pixels  # Crushed black pixels
    highlight_ratio = sum(hist[235:]) / total_pixels  # Blown out white pixels

    lighting_score = 90
    light_tips: list[str] = []
    if shadow_ratio > 0.35:
        lighting_score -= 25
        light_tips.append("Shadows are crushed (>35% dark areas). Lift shadows slightly.")
    if highlight_ratio > 0.20:
        lighting_score -= 20
        light_tips.append("Highlights are blown out (>20% overexposed). Tone down exposure.")
    if mean_lum < 70:
        lighting_score -= 15
        light_tips.append("Overall scene is dark. A little brightening will make it pop on OLED screens.")
    elif mean_lum > 195:
        lighting_score -= 15
        light_tips.append("Scene is quite bright. Slightly reduce brightness for richer contrast.")

    lighting_score = max(25, min(100, lighting_score))

    # 4. Vibrancy & Saturation Score (0..100)
    hsv = analysis_im.convert("HSV")
    s_channel = hsv.split()[1]
    s_stat = ImageStat.Stat(s_channel)
    mean_sat = s_stat.mean[0] if s_stat.mean else 80.0
    vibrancy_score = int(min(100, max(30, (mean_sat / 140.0) * 100)))
    vib_tips: list[str] = []
    if vibrancy_score < 50:
        vib_tips.append("Colors are somewhat muted. A +10% vibrancy or warmth boost would enhance appeal.")

    # 5. Composite Weighted Score (0..100)
    overall = int(
        sharpness_score * 0.30
        + lighting_score * 0.30
        + vibrancy_score * 0.20
        + framing_score * 0.20
    )
    overall = max(0, min(100, overall))

    # Badges & Rating Label
    badges: list[str] = []
    if overall >= 88:
        rating_label = "🌟 Feed Masterpiece"
    elif overall >= 80:
        rating_label = "✨ Instagram Ready"
    elif overall >= 70:
        rating_label = "👍 Good Post / Story"
    else:
        rating_label = "📸 Needs Light Edit"

    if sharpness_score >= 85:
        badges.append("Crisp Focus 🎯")
    if lighting_score >= 85:
        badges.append("Balanced Light ☀️")
    if vibrancy_score >= 82:
        badges.append("Vivid Colors 🎨")
    if framing_score >= 95:
        badges.append("Ideal IG Ratio 📐")
    if min(w, h) >= 1080:
        badges.append("HD Quality 💎")

    suggestions = ratio_tips + light_tips + vib_tips
    if not suggestions:
        suggestions.append("Outstanding framing, lighting, and detail. Ready to post directly!")

    return AestheticReport(
        score=overall,
        rating_label=rating_label,
        sharpness_score=sharpness_score,
        lighting_score=lighting_score,
        vibrancy_score=vibrancy_score,
        framing_score=framing_score,
        aspect_ratio_str=aspect_str,
        resolution_str=f"{w} x {h}",
        badges=badges,
        suggestions=suggestions[:3],
    )
