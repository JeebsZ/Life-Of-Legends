"""core/nutrition.py: BMR, BMI, plan (floor, cap, gain, refusals), macros, units, ranges."""

from datetime import date

import pytest

from lol.core import nutrition as n

D = date(2026, 11, 4)


# --- BMR (Mifflin-St Jeor) ---------------------------------------------------------------------
def test_bmr_known_examples():
    assert n.bmr(70, 175, 30, "male") == pytest.approx(1648.75)
    assert n.bmr(60, 165, 25, "female") == pytest.approx(1345.25)
    # unspecified = the average of the two formulas
    avg = (n.bmr(80, 170, 40, "male") + n.bmr(80, 170, 40, "female")) / 2
    assert n.bmr(80, 170, 40, "unspecified") == pytest.approx(avg)


def test_bmr_rejects_unknown_sex():
    with pytest.raises(ValueError):
        n.bmr(70, 175, 30, "x")


def test_tdee_factors():
    assert n.tdee(1500, "sedentary") == pytest.approx(1800)
    assert n.tdee(1500, "very_active") == pytest.approx(2850)
    with pytest.raises(ValueError):
        n.tdee(1500, "couch")


# --- BMI ---------------------------------------------------------------------------------------
@pytest.mark.parametrize(("value", "cat"), [
    (18.49, "Underweight range"), (18.5, "Healthy range"), (24.99, "Healthy range"),
    (25.0, "Overweight range"), (29.99, "Overweight range"), (30, "Obesity class I range"),
    (35, "Obesity class II range"), (40, "Obesity class III range"),
])
def test_bmi_category_edges(value, cat):
    assert n.bmi_category(value) == cat


def test_bmi_and_healthy_range():
    assert n.bmi(70, 175) == pytest.approx(22.857, abs=1e-3)
    lo, hi = n.healthy_range_kg(175)
    assert lo == pytest.approx(56.66, abs=0.01) and hi == pytest.approx(76.26, abs=0.01)


# --- units ---------------------------------------------------------------------------------------
def test_units_round_trip():
    assert n.lb_to_kg(n.kg_to_lb(80)) == pytest.approx(80)
    assert n.to_kg(220.462, "lb") == pytest.approx(100, abs=1e-3)
    assert n.from_kg(100, "lb") == pytest.approx(220.462)
    assert n.ft_in_to_cm(5, 9) == pytest.approx(175.26)
    assert n.cm_to_ft_in(175.26) == (5, 9)
    with pytest.raises(ValueError):
        n.to_kg(1, "stone")


def test_age_or_birth_year():
    assert n.age_from(30, D) == (30, 1996)
    assert n.age_from(1990, D) == (36, 1990)


# --- plans ---------------------------------------------------------------------------------------
def test_steady_loss_plan():
    p = n.make_plan(90, 175, 30, "male", "moderate", 80, "steady", D)
    b = 10 * 90 + 6.25 * 175 - 150 + 5
    t = b * 1.55
    assert p.goal == "lose" and p.bmr == round(b) and p.tdee == round(t)
    assert p.target_kcal == round((t - 0.5 * 7700 / 7) / 10) * 10
    assert not p.floor_bound and p.weekly_kg == -0.5
    assert p.weeks == 20 and p.est_date == date(2027, 3, 24)
    assert p.kcal_low == p.target_kcal - 100 and p.kcal_high == p.target_kcal + 100


def test_pace_capped_at_one_percent():
    p = n.make_plan(50, 160, 30, "female", "active", 48, "fast", D)
    assert p.weekly_kg == pytest.approx(-0.5)  # 1 % of 50 kg, not 0.75
    assert any("1%" in note for note in p.notes)


def test_floor_binds_and_timeline_grows():
    # small sedentary woman: TDEE ~1520, fast pace would mean ~770 kcal -> floor 1200
    p = n.make_plan(62, 155, 45, "female", "sedentary", 57, "fast", D)
    assert p.floor_bound and p.floor == max(p.bmr, 1200)
    assert p.floor <= p.target_kcal < p.floor + 10
    assert -0.75 < p.weekly_kg < 0
    assert p.weeks is not None and p.weeks > (62 - 57) / 0.62  # slower than asked
    assert any("safe minimum" in note for note in p.notes)
    assert p.kcal_low >= p.floor


def test_floor_uses_bmr_when_higher():
    p = n.make_plan(120, 190, 25, "male", "sedentary", 100, "fast", D)
    assert p.floor == p.bmr > 1500


def test_floor_at_maintenance_means_no_loss():
    with_floor = n.make_plan(52, 150, 70, "female", "sedentary", 50, "gentle", D)
    # BMR ~ 1001, TDEE ~ 1201 -> floor 1200 ~ maintenance
    assert with_floor.floor_bound
    assert abs(with_floor.weekly_kg) < 0.01


def test_refuses_goal_under_healthy_bmi():
    with pytest.raises(n.PlanRefused):
        n.make_plan(60, 175, 30, "female", "light", 55, "gentle", D)  # BMI ~18.0


def test_refuses_loss_under_18_but_allows_maintain():
    with pytest.raises(n.PlanRefused):
        n.make_plan(80, 170, 16, "male", "light", 70, "gentle", D)
    p = n.make_plan(80, 170, 16, "male", "light", None, "gentle", D)
    assert p.goal == "maintain" and any("adults" in note for note in p.notes)


def test_gain_and_maintain():
    g = n.make_plan(55, 175, 25, "male", "moderate", 60, "steady", D)
    assert g.goal == "gain" and g.target_kcal == round((g.tdee + 375) / 10) * 10
    assert g.weekly_kg > 0 and g.est_date is not None
    m = n.make_plan(70, 175, 25, "male", "moderate", 70.3, "steady", D)
    assert m.goal == "maintain" and m.weekly_kg == 0 and m.est_date is None
    assert m.target_kcal == round(m.tdee / 10) * 10


def test_unspecified_sex_is_said():
    p = n.make_plan(70, 170, 30, "unspecified", "light", 65, "gentle", D)
    assert p.sex_assumed and p.floor >= 1350
    assert any("averaged" in note for note in p.notes)


def test_bad_inputs():
    with pytest.raises(ValueError):
        n.make_plan(10, 175, 30, "male", "light", None, "steady", D)
    with pytest.raises(ValueError):
        n.make_plan(70, 175, 30, "male", "light", None, "warp", D)


# --- macros --------------------------------------------------------------------------------------
def test_macros_normal_bmi():
    m = n.macros(2000, 70, 175)
    assert m.ref_weight_kg == 70
    assert m.protein_g == (112, 126, 154)
    assert m.fat_g[0] == round(2000 * 0.25 / 9) and m.fat_g[2] == round(2000 * 0.30 / 9)
    kcal = m.protein_g[1] * 4 + m.fat_g[1] * 9 + m.carbs_g[1] * 4
    assert kcal == pytest.approx(2000, abs=8)
    assert m.carbs_g[0] <= m.carbs_g[1] <= m.carbs_g[2]
    assert m.fiber_g == 28 and m.water_ml == (2100, 2400)
    assert sum(m.pct().values()) == pytest.approx(100, abs=2)


def test_macros_high_bmi_uses_bmi25_reference():
    m = n.macros(2200, 130, 170)  # BMI 45
    ref = 25 * 1.7 ** 2
    assert m.ref_weight_kg == pytest.approx(ref, abs=0.1)
    assert m.protein_g[1] == round(1.8 * ref)


def test_fat_minimum_per_kg():
    m = n.macros(1200, 90, 190)  # 25 % of 1200 kcal = 33 g < 0.6 g/kg * 90 = 54 g
    assert m.fat_g[0] == 54


# --- ranges --------------------------------------------------------------------------------------
def test_kcal_range_scale_is_narrower():
    lo_s, hi_s = n.kcal_range(400, 0.08, from_scale=True)
    lo_g, hi_g = n.kcal_range(400, 0.08, from_scale=False)
    assert lo_g < lo_s < 400 < hi_s < hi_g
    assert lo_s % 5 == 0 and hi_s % 5 == 0
