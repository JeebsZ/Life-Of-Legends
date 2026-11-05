from lol.ui import voice

SAMPLE = {"xp": 40, "path": "Warrior", "level": 3, "skill": "Onion Dicing", "title": "Read",
          "minutes": "10 min", "difficulty": "beginner-friendly", "bill": "Phone bill",
          "when": "is due in 2 days", "reward": "Movie night", "theme": "Ocean"}

GUILT = ("missed", "failed", "lazy", "should have", "behind", "disappoint")


def test_every_kind_has_rotating_variants_that_format():
    for kind, variants in voice.LINES.items():
        assert len(variants) >= 2, kind
        said = [voice.say(kind, **SAMPLE) for _ in variants]
        assert len(set(said)) == len(variants), kind  # rotates through each variant
        assert all(s and "{" not in s for s in said), kind


def test_voice_is_kind():
    for variants in voice.LINES.values():
        for line in variants:
            assert not any(word in line.lower() for word in GUILT), line


def test_spec_lines_and_helpers():
    assert "Luma Report" in voice.LINES["report_title"][0]
    assert voice.LINES["comeback"][0] == "Resuming is also a skill. Shall we continue?"
    assert voice.minutes_text(10) == "10 min" and voice.minutes_text(90) == "1 h 30 min"
    assert voice.minutes_text(None) == "a short while"
    assert voice.difficulty_text(1) == "beginner-friendly"
