from pathlib import Path

from PIL import Image

from lol.core.media_curator import (
    analyze_image_aesthetic,
    batch_delete_files,
    classify_filename,
    scan_media_folder,
)


def test_classify_filename():
    assert classify_filename("Screenshot_20261110_104520.png") == "screenshot"
    assert classify_filename("Screen_Shot_2026-11-10.jpg") == "screenshot"
    assert classify_filename("tiktok_save_129048.mp4.jpg") == "social_save"
    assert classify_filename("snaptik_fun.png") == "social_save"
    assert classify_filename("IMG_20261110_091230.jpg") == "camera"
    assert classify_filename("PXL_20261110_143015.jpg") == "camera"


def test_analyze_image_aesthetic_and_scoring(tmp_path: Path):
    # Create test image: 1080 x 1350 (4:5 portrait)
    img_path = tmp_path / "test_portrait.jpg"
    img = Image.new("RGB", (1080, 1350), color=(180, 140, 120))
    img.save(img_path)

    report = analyze_image_aesthetic(str(img_path))
    assert 0 <= report.score <= 100
    assert report.aspect_ratio_str == "4:5 Portrait"
    assert report.resolution_str == "1080 x 1350"
    assert "Ideal IG Ratio 📐" in report.badges


def test_scan_and_batch_delete(tmp_path: Path):
    # Create dummy files
    f1 = tmp_path / "Screenshot_1.jpg"
    f2 = tmp_path / "tiktok_save_2.png"
    f3 = tmp_path / "Camera_3.jpg"

    f1.write_bytes(b"dummy")
    f2.write_bytes(b"dummy")
    f3.write_bytes(b"dummy")

    items = scan_media_folder(str(tmp_path))
    assert len(items) == 3

    # Batch delete 2 files
    succ, fail = batch_delete_files([str(f1), str(f2)])
    assert succ == 2
    assert fail == 0
    assert not f1.exists()
    assert not f2.exists()
    assert f3.exists()

