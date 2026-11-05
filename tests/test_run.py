"""GPS run/walk tracker: filtering, totals, energy/steps, ladder, safety advice, save."""

import json
import math
from datetime import date, timedelta
from pathlib import Path

import pytest

from lol.core import game as game_mod
from lol.core import run, run_sim, runlog, storage
from lol.core import run_cues as rc
from lol.core.game import Game
from lol.core.models import RunEntry
from lol.core.run import Fix, Tracker, haversine_m

D = date(2026, 11, 5)
LAT0, LON0 = 14.5826, 120.9787  # Rizal Park, Manila
M_PER_DEG = math.pi / 180 * run.EARTH_RADIUS_M


def north(m: float) -> float:
    return LAT0 + m / M_PER_DEG


def line(speed: float, seconds: int, *, acc: float = 5.0, t0: float = 0.0, start: float = 0.0,
         alt=None) -> list[Fix]:
    """A straight run due north, one fix per second."""
    return [Fix(north(start + speed * i), LON0, acc, t0 + i, alt(i) if alt else None)
            for i in range(seconds + 1)]


def feed(tr: Tracker, fixes) -> dict[str, int]:
    out: dict[str, int] = {}
    for f in fixes:
        r = tr.add(f)
        out[r] = out.get(r, 0) + 1
    return out


def tiers():
    return [(t.id, t.meters) for t in runlog.TIERS]


# --- geometry ------------------------------------------------------------------------------------
def test_haversine_known_distances():
    assert haversine_m(0, 0, 0, 1) == pytest.approx(111_195, rel=1e-3)  # 1 deg at the equator
    assert haversine_m(0, 0, 1, 0) == pytest.approx(111_195, rel=1e-3)
    assert haversine_m(LAT0, LON0, LAT0, LON0) == 0
    # Manila (Rizal Park) -> Quezon Memorial Circle is ~11.5 km
    assert haversine_m(LAT0, LON0, 14.6516, 121.0493) == pytest.approx(10_900, rel=0.08)


def test_simplify_drops_collinear_keeps_corners():
    pts = [(north(i * 10), LON0) for i in range(20)] + [(north(190), LON0 + 0.001)]
    out = run.simplify(pts, 4.0)
    assert out[0] == pts[0] and out[-1] == pts[-1]
    assert len(out) == 3  # start, the corner, end
    assert run.simplify(pts[:2]) == pts[:2]


# --- filter --------------------------------------------------------------------------------------
def test_straight_run_distance_time_pace():
    tr = Tracker("run", 0)
    feed(tr, line(3.0, 600))  # 1.8 km in 10 min
    assert tr.distance_m == pytest.approx(1800, rel=0.02)
    assert tr.moving_s == pytest.approx(600, abs=5)
    assert run.pace_s_per_km(tr.distance_m, tr.moving_s) == pytest.approx(333, rel=0.03)
    assert tr.current_pace(600) == pytest.approx(333, rel=0.05)


def test_inaccurate_fixes_are_dropped():
    tr = Tracker("run", 0)
    fixes = line(3.0, 60)
    bad = [Fix(f.lat + 0.001, f.lon, 40.0, f.t + 0.5) for f in fixes[5:10]]
    res = feed(tr, sorted(fixes + bad, key=lambda f: f.t))
    assert res["inaccurate"] == 5 and tr.dropped == 5
    assert tr.distance_m == pytest.approx(180, rel=0.05)


def test_teleport_jump_dropped():
    tr = Tracker("run", 0)
    fixes = line(3.0, 60)
    glitch = Fix(north(90 + 300), LON0, 5.0, 30.5)  # 300 m in half a second
    res = feed(tr, sorted([*fixes, glitch], key=lambda f: f.t))
    assert res["jump"] == 1
    assert tr.distance_m == pytest.approx(180, rel=0.05)


def test_relock_after_consistent_jumps_starts_new_segment():
    tr = Tracker("run", 0)
    feed(tr, line(3.0, 20))
    d = tr.distance_m
    far = line(3.0, 20, t0=21, start=2000)  # GPS re-locks 2 km away and stays there
    res = feed(tr, far)
    assert res["jump"] == run.JUMP_RESET_AFTER - 1 and res["relock"] == 1
    assert tr.seg == 1
    # the 2 km gap is not counted; the new stretch is
    assert d < tr.distance_m < d + 80


def test_standing_still_adds_no_distance_and_autopauses():
    tr = Tracker("walk", 0)
    feed(tr, line(1.4, 60))
    d, m = tr.distance_m, tr.moving_s
    # 2 minutes standing with ~2 m of drifting error
    still = [Fix(north(84 + 2 * math.sin(i / 7)), LON0 + 0.00001 * math.cos(i / 9), 6.0, 61 + i)
             for i in range(120)]
    feed(tr, still)
    assert tr.distance_m - d < 8
    assert tr.moving_s - m < 15
    assert tr.auto_paused(181) is True
    assert tr.current_pace(181) is None


def test_manual_pause_gap_not_counted():
    tr = Tracker("run", 0)
    feed(tr, line(3.0, 100))
    tr.pause(100)
    assert tr.add(Fix(north(400), LON0, 5, 150)) == "paused"
    tr.resume(200)
    feed(tr, line(3.0, 100, t0=200, start=1000))  # resumed 700 m further on
    assert tr.distance_m == pytest.approx(600, rel=0.03)
    assert tr.moving_s == pytest.approx(200, abs=8)
    assert tr.elapsed_s(300) == 300
    assert len(tr.route()) == 2


def test_splits_and_best_effort():
    tr = Tracker("run", 0)
    fast = line(4.0, 250)  # 1 km in 250 s
    slow = line(2.5, 800, t0=251, start=1004)  # then 2 km at 400 s/km
    feed(tr, fast + slow)
    sp = run.splits(tr.points)
    assert len(sp) == 3  # 3 km; a remainder would not be a split
    assert sp[0] == pytest.approx(250, abs=10)
    assert sp[1] == pytest.approx(400, abs=15) and sp[2] == pytest.approx(400, abs=15)
    assert run.best_effort(tr.points, 1000) == pytest.approx(250, abs=10)
    assert run.best_effort(tr.points, 5000) is None


def test_elevation_gain_hysteresis():
    tr = Tracker("run", 0)
    # climbs 20 m with +-1 m noise, then descends: only the climb counts, the noise doesn't
    feed(tr, line(3.0, 200, alt=lambda i: min(i, 100) * 0.2 + (1 if i % 2 else -1)
                  - max(0, i - 100) * 0.2))
    assert tr.elev_gain == pytest.approx(20, abs=4)
    tr2 = Tracker("run", 0)
    feed(tr2, line(3.0, 50))
    assert run.summarize(tr2, 50).elev_gain_m is None


def test_mode_must_be_known():
    with pytest.raises(ValueError):
        Tracker("swim")
    with pytest.raises(ValueError):
        run.met_for(10, "swim")


# --- energy and steps ----------------------------------------------------------------------------
def test_met_values_from_compendium():
    assert run.met_for(9.7, "run") == pytest.approx(9.8)  # 12050, 6 mph
    assert run.met_for(8.0, "run") == pytest.approx(8.3)  # 12030, 5 mph
    assert run.met_for(4.8, "walk") == pytest.approx(3.5)  # 17190
    assert run.met_for(5.6, "walk") == pytest.approx(4.3)  # 17200, brisk
    assert run.met_for(5.0, "run") < 5  # a run-mode walk break uses the walking table
    assert run.met_for(9.0, "walk") > 8.3  # a walk that turned into a jog
    assert 9.8 < run.met_for(10.0, "run") < 10.5  # interpolated
    assert run.met_for(0, "run") == 1.0
    assert run.met_for(40, "run") == 23.0  # clamped to the table


def test_step_length():
    assert run.step_length_m(1.3, 180, "walk") == pytest.approx(0.415 * 1.8)
    s10 = run.step_length_m(2.78, 180, "run")
    assert s10 == pytest.approx(0.55 * 1.8, rel=0.01)
    assert run.step_length_m(4.0, 180, "run") > s10
    assert run.step_length_m(20, 180, "run") == pytest.approx(0.95 * 1.8)
    assert run.step_length_m(1.3, 180, "run") == pytest.approx(0.415 * 1.8)  # walking pace


def test_kcal_steps_rest_and_net():
    tr = Tracker("run", 0)
    feed(tr, line(10 / 3.6, 3600))  # 1 h at 10 km/h
    s = run.summarize(tr, 3600, weight_kg=70, height_cm=175, bmr_kcal_day=1680)
    met = run.met_for(10, "run")
    assert s.kcal == pytest.approx(met * 70, rel=0.04)
    assert s.rest_kcal == pytest.approx(70, rel=0.01)  # 1680 / 24
    assert s.net_kcal == pytest.approx(s.kcal - s.rest_kcal)
    assert s.steps == pytest.approx(10_000 / run.step_length_m(10 / 3.6, 175), rel=0.04)
    assert not s.weight_assumed and s.rest_from_bmr
    d = run.summarize(tr, 3600)  # no body data: labelled defaults, rest = 1 MET
    assert d.weight_assumed and d.height_assumed and not d.rest_from_bmr
    assert d.weight_kg == run.DEFAULT_WEIGHT_KG
    assert d.rest_kcal == pytest.approx(run.DEFAULT_WEIGHT_KG, rel=0.01)


def test_formatting():
    assert run.fmt_pace(342) == "5:42" and run.fmt_pace(None) == "-:--"
    assert run.fmt_duration(65) == "1:05" and run.fmt_duration(3725) == "1:02:05"


# --- the Rizal Park replay -----------------------------------------------------------------------
@pytest.mark.parametrize("mode", ["run", "walk"])
def test_sim_replay_is_close_to_truth(mode):
    tr = Tracker(mode, 0)
    res = feed(tr, run_sim.simulate(mode, 0, seconds=1800))
    moving_truth = 1800 - run_sim.STOP_FOR_S
    truth = moving_truth * 1000 / run_sim.SIM_PACE_S_PER_KM[mode]
    assert tr.distance_m == pytest.approx(truth, rel=0.06)
    assert res["inaccurate"] >= 30 and res["jump"] >= 1
    assert tr.moving_s < 1800 - 10  # the stop at the crossing was not moving time
    s = run.summarize(tr, 1800, tiers=tiers())
    assert s.route and len(s.route[0]) < len(tr.points)  # simplified for the save
    assert s.elev_gain_m is not None


def test_sim_loop_is_a_real_loop():
    loop = run_sim.RIZAL_PARK_LOOP
    assert loop[0] == loop[-1]
    assert 2000 < run_sim.loop_length_m() < 3000


# --- game: logging, ladder, advice ---------------------------------------------------------------
def stats(km: float, mode: str = "run", pace: float = 360.0):
    tr = Tracker(mode, 0)
    secs = int(km * pace)
    feed(tr, line(1000 / pace, secs))
    return run.summarize(tr, secs, tiers=tiers())


def test_challenge_rewards_match_hard_quests():
    assert runlog.CHALLENGE_XP == game_mod.XP_BY_DIFFICULTY[3]
    assert runlog.CHALLENGE_COINS == game_mod.COINS_BY_DIFFICULTY[3]


def test_log_run_saves_workout_and_challenge_bonus():
    g = Game()
    c = g.log_run(stats(3.2), D, started="06:00", goal="1k")
    r = g.run(c.ref_id)
    assert r.cleared == ["1k", "3k"] and r.mode == "run" and r.goal == "1k"
    w = g.workout(r.workout_id)
    assert w.type == "cardio" and w.minutes == pytest.approx(19, abs=1)
    assert c.xp == w.xp + runlog.CHALLENGE_XP and c.coins == w.coins + runlog.CHALLENGE_COINS
    assert r.xp == c.xp and g.profile.path_xp["warrior"] == c.xp
    # Insights count it as a workout
    ins = next(i for i in g.insights(D - timedelta(days=6), D) if i.kind == "workouts_per_week")
    assert "1 workouts" in ins.text
    # a second, shorter run clears nothing new: no bonus
    c2 = g.log_run(stats(2.0), D + timedelta(days=1))
    assert g.run(c2.ref_id).cleared == [] and c2.xp == g.workout(g.run(c2.ref_id).workout_id).xp


def test_walk_and_run_climb_separately():
    g = Game()
    g.log_run(stats(3.1, "walk", 660), D)
    assert [s.state for s in g.ladder("walk")][:3] == ["cleared", "cleared", "open"]
    assert g.ladder("run")[0].state == "open"


def test_ladder_states_badges_and_next_day_unlock():
    g = Game()
    g.log_run(stats(5.1), D)
    lad = g.ladder("run")
    assert [s.state for s in lad[:5]] == ["cleared"] * 3 + ["open", "locked"]
    assert lad[2].cleared_on == D.isoformat() and lad[2].best_s == pytest.approx(1800, abs=30)
    assert lad[2].badge == "Steady"  # 6:00 /km
    assert lad[3].available_from == D + timedelta(days=1)
    assert [s.tier.id for s in g.personal_bests("run")] == ["1k", "3k", "5k"]
    assert runlog.pace_badge("run", 1200, 5000) == "Blaze"  # 4:00 /km
    assert runlog.pace_badge("walk", 3000, 5000) == "Brisk"  # 10:00 /km


def test_advice_first_run_suggests_1k():
    a = Game().run_advice("run", D)
    assert a.suggest_challenge and a.challenge.tier.id == "1k" and not a.reason
    assert runlog.HEAT_NOTE in a.notes and runlog.PAIN_NOTE in a.notes


def test_advice_never_same_day_and_not_after_a_session():
    g = Game()
    g.log_run(stats(1.1), D)
    a = g.run_advice("run", D)
    assert not a.suggest_challenge and "tomorrow" in a.reason
    assert a.easy_km == 0  # already moved today: no extra suggestion


def test_advice_ramp_limits_weekly_volume():
    g = Game()
    g.log_run(stats(1.1), D)
    g.log_run(stats(3.1), D + timedelta(days=2))
    # 4.2 km this week, start room 6 km: the 5K doesn't fit this week
    a = g.run_advice("run", D + timedelta(days=4))
    assert not a.suggest_challenge and "volume" in a.reason
    assert a.week_km == pytest.approx(4.2, abs=0.2) and a.cap_km == 6.0
    # a week later the window has rolled: base 4.2 km -> room 6 km, the 5K fits
    a2 = g.run_advice("run", D + timedelta(days=10))
    assert a2.suggest_challenge and a2.challenge.tier.id == "5k"


def test_advice_ramp_is_ten_percent_of_base():
    g = Game()
    for k in range(4):  # 20 km a week for 4 weeks
        for d in (0, 2, 4, 6):
            g.data.runs.append(RunEntry(f"r{k}{d}", (D - timedelta(days=28 - 7 * k - d))
                                        .isoformat(), mode="run", distance_m=5000))
    _week, base, cap = g.weekly_volume("run", D)
    assert base == pytest.approx(20000) and cap == pytest.approx(22000)


def test_advice_holds_back_youth_low_energy_and_streaks():
    g = Game()
    g.set_age(16, D)
    a = g.run_advice("run", D)
    assert not a.suggest_challenge and a.reason == runlog.YOUTH_NOTE
    assert runlog.YOUTH_NOTE in a.notes

    g2 = Game()
    g2.check_in("low", D)
    a2 = g2.run_advice("run", D)
    assert not a2.suggest_challenge and a2.reason == runlog.LOW_ENERGY_NOTE
    assert a2.easy_km <= 3

    g3 = Game()
    for i in range(3):
        g3.log_run(stats(1.1 if i == 0 else 0.5), D - timedelta(days=3 - i))
    a3 = g3.run_advice("run", D)
    assert a3.rest_nudge and "in a row" in a3.rest_nudge and not a3.suggest_challenge


def test_advice_rest_after_big_day():
    g = Game()
    g.data.runs.append(RunEntry("r1", (D - timedelta(days=1)).isoformat(), mode="run",
                                distance_m=16000, cleared=["1k", "3k", "5k", "10k", "15k"]))
    a = g.run_advice("run", D)
    assert a.rest_nudge and "yesterday" in a.rest_nudge


def test_log_run_validates_and_delete_removes_workout():
    g = Game()
    with pytest.raises(ValueError):
        g.log_run(stats(1), D, goal="ultra")
    c = g.log_run(stats(1.2), D)
    wid = g.run(c.ref_id).workout_id
    xp = g.profile.path_xp["warrior"]
    g.delete_run(c.ref_id)
    assert g.runs() == [] and all(w.id != wid for w in g.data.workouts)
    assert g.profile.path_xp["warrior"] == xp  # earned XP stays


def test_run_settings_and_body():
    g = Game()
    g.set_run_settings(mode="walk", keep_awake=False)
    assert g.data.run_settings.mode == "walk" and not g.data.run_settings.keep_awake
    with pytest.raises(ValueError):
        g.set_run_settings(mode="swim")
    assert g.run_body(D) == {"weight_kg": None, "height_cm": None, "bmr": None}
    g.set_body(height_cm=175, sex="male")
    g.set_age(30, D)
    g.log_weight(70, "kg", D)
    assert g.run_body(D)["bmr"] == pytest.approx(10 * 70 + 6.25 * 175 - 5 * 30 + 5)


# --- save ----------------------------------------------------------------------------------------
def test_runs_roundtrip_and_csv(tmp_path):
    g = Game()
    g.set_run_settings(mode="walk")
    c = g.log_run(stats(1.5), D, started="05:45")
    p = g.save(tmp_path / "save.json")
    g2 = Game.load(p)
    r = g2.run(c.ref_id)
    assert r == g.run(c.ref_id)
    assert r.route and isinstance(r.route[0][0], list) and r.bests["1k"] > 0
    assert g2.data.run_settings.mode == "walk"
    assert storage.summary(g2.data)["runs"] == 1
    csv = storage.export_csv(g2.data)["runs.csv"]
    assert csv.splitlines()[0].startswith("id,day,started,mode,distance_km")
    assert c.ref_id in csv


def test_schema5_save_without_runs_loads_with_defaults():
    g = Game()
    raw = storage.to_dict(g.data)
    del raw["runs"], raw["run_settings"]
    raw["profile"]["modules"] = {m: True for m in ("workout", "sleep", "water", "energy",
                                                   "insights", "body", "meals")}
    data = storage.from_dict(json.loads(json.dumps(raw)))
    assert data.runs == [] and data.run_settings.mode == "run"
    assert data.run_settings.keep_awake is True and data.profile.modules["run"] is True


def test_import_rejects_bad_run_data():
    raw = storage.to_dict(Game().data)
    raw["run_settings"] = []
    with pytest.raises(ValueError, match="run_settings"):
        storage.import_json(json.dumps(raw))
    raw = storage.to_dict(Game().data)
    raw["runs"] = [{"id": "r1", "day": "not-a-day"}]
    with pytest.raises(ValueError, match="run r1"):
        storage.import_json(json.dumps(raw))


# --- spoken cues ---------------------------------------------------------------------------------
def test_cue_5k_at_28_10():
    keys = rc.update_keys(5000, 28 * 60 + 10, 338, 5240)
    assert keys == ["distance", "n5", "kilometres", "time", "n28", "minutes",
                    "pace", "n5", "n38", "per_kilometre",
                    "steps", "about", "n5", "thousand", "n2", "hundred"]


def test_cue_number_words():
    assert rc.number_keys(0) == ["n0"] and rc.number_keys(59) == ["n59"]
    assert rc.number_keys(61) == ["n60", "n1"] and rc.number_keys(90) == ["n90"]
    assert rc.number_keys(342) == ["n3", "hundred", "n42"]
    assert rc.number_keys(2005) == ["n2", "thousand", "n5"]
    with pytest.raises(ValueError):
        rc.number_keys(-1)


def test_cue_parts():
    assert rc.distance_keys(1000) == ["distance", "n1", "kilometre"]
    assert rc.distance_keys(2540) == ["distance", "n2", "point", "n5", "kilometres"]
    assert rc.distance_keys(42195) == ["distance", "n42", "point", "n2", "kilometres"]
    assert rc.time_keys(3900) == ["time", "n1", "hour", "n5", "minutes"]
    assert rc.time_keys(7200) == ["time", "n2", "hours"]
    assert rc.time_keys(61) == ["time", "n1", "minute"]
    assert rc.time_keys(42) == ["time", "n42", "seconds"]
    assert rc.pace_keys(305) == ["pace", "n5", "oh", "n5", "per_kilometre"]
    assert rc.pace_keys(360) == ["pace", "n6", "minutes", "per_kilometre"]
    assert rc.pace_keys(None) == []
    assert rc.steps_keys(40) == [] and rc.steps_keys(860) == ["steps", "about", "n9", "hundred"]
    assert rc.steps_keys(12000) == ["steps", "about", "n12", "thousand"]
    assert rc.tier_keys("10k") == ["n10", "k"] and rc.tier_keys("half") == ["half_marathon"]


def test_every_cue_key_has_a_clip_line():
    lines = json.loads((Path(__file__).parents[1] / "tools" / "voice" / "cues.json")
                       .read_text(encoding="utf-8"))
    assert set(lines) == set(rc.ALL_KEYS)
    assert not any(n in t.lower() for t in lines.values() for n in ("lumen", "luma"))
    used = rc.keys_used([rc.update_keys(m, m * 0.37, 0.37 * 1000, int(m * 1.3))
                         for m in range(0, 42300, 137)])
    used |= {k for t in runlog.TIERS for k in rc.tier_keys(t.id)}
    assert used <= set(rc.ALL_KEYS)


def test_coach_interval_halfway_goal_tier_water():
    c = rc.CueCoach("run", "1km", goal_m=5000, tiers=[("5k", 5000)])
    assert c.update(900, 300, 333, 1100) == []
    out = c.update(1010, 340, 336, 1200)
    assert len(out) == 1 and out[0][:3] == ["distance", "n1", "kilometre"]
    assert c.update(1500, 500, 336, 1800) == []  # same km: nothing new
    out = c.update(2600, 870, 335, 3000)
    assert out[0][0] == "distance" and ["halfway"] in out
    out = c.update(5005, 1190, 238, 5300)
    assert ["goal_reached"] in out and ["tier_cleared", "n5", "k"] in out
    assert c.update(5010, 1195, 238, 5310) == []  # each fires once
    out = c.update(5300, 20 * 60 + 1, 238, 5600)
    assert out == [["water"]]


def test_coach_half_km_and_five_minutes():
    c = rc.CueCoach("walk", "0.5km")
    assert len(c.update(520, 300, 600, 700)) == 1
    t = rc.CueCoach("walk", "5min")
    assert t.update(400, 299, 600, 500) == [] and len(t.update(420, 301, 600, 520)) == 1
    with pytest.raises(ValueError):
        rc.CueCoach("run", "2km")


def test_coach_ease_off_when_going_out_hot():
    c = rc.CueCoach("run", "1km", goal_m=10000)
    c.update(3000, 1080, 360, 3000, splits=[360, 360, 360])
    out = c.update(4000, 1370, 290, 4000, splits=[360, 360, 360, 290])
    assert ["ease_off"] in out
    # no nag: not again within 3 km, and never without a long goal
    assert ["ease_off"] not in c.update(5000, 1660, 290, 5000, splits=[360] * 3 + [290, 290])
    free = rc.CueCoach("run", "1km")
    assert ["ease_off"] not in free.update(4000, 1370, 290, 4000, splits=[360] * 3 + [290])


def test_cue_settings():
    g = Game()
    assert g.data.run_settings.voice_cues and g.data.run_settings.cue_every == "1km"
    g.set_run_settings(voice_cues=False, cue_every="5min")
    assert not g.data.run_settings.voice_cues and g.data.run_settings.cue_every == "5min"
    with pytest.raises(ValueError):
        g.set_run_settings(cue_every="10km")
