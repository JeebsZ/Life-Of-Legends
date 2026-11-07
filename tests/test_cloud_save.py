from datetime import UTC, datetime, timedelta

from lol.core import cloud_save
from lol.core.models import SaveData


def test_iso_time_parsing():
    s = "2026-11-06T12:34:56.789Z"
    dt = cloud_save.parse_iso_time(s)
    assert dt is not None
    assert dt.year == 2026
    assert dt.month == 11
    assert dt.day == 6
    assert dt.hour == 12
    assert dt.minute == 34


def test_compare_saves_timestamps():
    now = datetime.now(UTC)
    older = now - timedelta(minutes=5)
    newer = now + timedelta(minutes=5)
    save = SaveData()

    assert cloud_save.compare_saves(save, now, older) == "local_newer"
    assert cloud_save.compare_saves(save, older, newer) == "cloud_newer"
    assert cloud_save.compare_saves(save, now, now) == "identical"
    assert cloud_save.compare_saves(save, now, None) == "local_newer"
    assert cloud_save.compare_saves(save, None, now) == "cloud_newer"


def test_serialize_and_deserialize():
    save = SaveData()
    save.profile.name = "CloudHero"
    save.profile.level = 10

    raw = cloud_save.serialize_for_cloud(save)
    valid, err = cloud_save.validate_cloud_json(raw)
    assert valid, err

    loaded = cloud_save.deserialize_from_cloud(raw)
    assert loaded.profile.name == "CloudHero"
    assert loaded.profile.level == 10


def test_validate_invalid_json():
    valid, _ = cloud_save.validate_cloud_json("")
    assert not valid

    valid, _ = cloud_save.validate_cloud_json("not json at all")
    assert not valid

    valid, _ = cloud_save.validate_cloud_json('{"some_other": "data"}')
    assert not valid
