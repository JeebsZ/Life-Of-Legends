from datetime import date

from lol.core.game import Game


def test_add_and_list_journal_entries():
    g = Game()
    d = date(2026, 11, 10)

    # 1. Add entry
    comp = g.add_journal(
        mood="great",
        gratitude="Sunny morning walk",
        highlight="Crushed morning workout",
        notes="High energy all day",
        today=d,
        time_str="09:30",
    )
    assert comp.xp == 20
    assert comp.path_id == "monk"
    assert comp.ref_id.startswith("jn")

    # 2. Query entries
    all_entries = g.journal_entries()
    assert len(all_entries) == 1
    assert all_entries[0].mood == "great"
    assert all_entries[0].gratitude == "Sunny morning walk"
    assert all_entries[0].time == "09:30"

    # Query by day
    today_entries = g.journal_entries(day=d)
    assert len(today_entries) == 1

    other_day = g.journal_entries(day=date(2026, 11, 11))
    assert len(other_day) == 0

    # 3. Delete entry
    g.delete_journal(comp.ref_id)
    assert len(g.journal_entries()) == 0

