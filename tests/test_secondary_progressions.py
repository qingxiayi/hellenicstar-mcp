import pytest
import swisseph as swe
from services.secondary_progressions import compute_secondary_progressions

def test_secondary_progressions_emma_watson():
    res = compute_secondary_progressions(
        birth_year=1990, birth_month=4, birth_day=15, birth_hour=18, birth_minute=0,
        birth_lat=48.8566, birth_lng=2.3522,
        as_of="2026-04-15",
        house_system="placidus"
    )
    assert round(res["age"]) == 36
    assert res["angle_progression_method"] == "naibod"
    chart = res["progressed_chart"]
    # 检查十大行星齐全
    for p in ("sun", "moon", "mercury", "venus", "mars", "jupiter", "saturn", "uranus", "neptune", "pluto"):
        assert p in chart["planets"]
        assert 0.0 <= chart["planets"][p]["longitude"] < 360.0
        assert 1 <= chart["planets"][p]["house"] <= 12
        assert 1 <= chart["planets"][p]["natal_house"] <= 12
    # 检查四轴齐全
    for ax in ("ascendant", "midheaven", "descendant", "imum_coeli"):
        assert ax in chart["axes"]
    # 检查月相
    assert 1 <= chart["lunation_phase"]["phase_num"] <= 8
    assert "mean_north_node" in chart["special_points"]
    # 检查对本命相位
    aspects = res["progressed_to_natal_aspects"]
    assert len(aspects) > 0
    for a in aspects:
        assert a["aspect"] in ("合", "六分", "刑", "三分", "梅花", "冲")
        assert a["orb"] <= 1.5

def test_secondary_progressions_by_age():
    res = compute_secondary_progressions(
        birth_year=1990, birth_month=4, birth_day=15, birth_hour=18, birth_minute=0,
        birth_lat=48.8566, birth_lng=2.3522,
        age=30.0,
        house_system="whole_sign"
    )
    assert res["age"] == 30.0
    assert res["house_system"] == "whole_sign"


def test_naibod_angles_and_true_solar_arc_are_distinct():
    args = dict(birth_year=1990, birth_month=4, birth_day=15, birth_hour=18,
                birth_minute=0, birth_lat=48.8566, birth_lng=2.3522, age=36)
    naibod = compute_secondary_progressions(**args)
    solar_arc = compute_secondary_progressions(**args, angle_progression_method="solar_arc_in_ra")
    nat_jd = naibod["progressed_jd"] - 36
    armc = (swe.sidtime(nat_jd) * 15 + args["birth_lng"] + 36 * 0.98564733) % 360
    eps = swe.calc_ut(naibod["progressed_jd"], swe.ECL_NUT)[0][0]
    _, expected = swe.houses_armc(armc, args["birth_lat"], eps, b'P')
    assert naibod["progressed_chart"]["axes"]["ascendant"]["longitude"] == pytest.approx(expected[0])
    assert abs(naibod["progressed_chart"]["axes"]["ascendant"]["longitude"] -
               solar_arc["progressed_chart"]["axes"]["ascendant"]["longitude"]) > 0.5


def test_age_only_calculation_reference_can_verify_claims():
    import mcp_server  # registers the live calculation tool
    from services.mcp_extended import secondary_progressions_data
    from services.mcp_result_facts import checked_result, verify_calculation_claims_data
    args = dict(year=1990, month=4, day=15, hour=18, minute=0,
                location_id="gn:2988507", age=36.0, as_of=None,
                house_system="placidus", fold=None, angle_progression_method="naibod")
    out = checked_result("calculate_secondary_progressions",
                         secondary_progressions_data(**args), args)
    assert out["status"] == "ok"
    checked = verify_calculation_claims_data(
        out["calculation_reference"],
        [{"path": "/settings/angle_progression_method", "value": "naibod", "quote": "四轴使用 Naibod 平均弧"}])
    assert checked["status"] == "ok"
    assert checked["counts"]["supported"] == 1


def test_age_and_date_cannot_disagree_silently():
    from services.mcp_extended import secondary_progressions_data
    out = secondary_progressions_data(
        year=1990, month=4, day=15, hour=18, minute=0,
        location_id="gn:2988507", age=35, as_of="2026-04-15")
    assert out["status"] == "invalid_input"


def test_progressed_biwheel_marks_four_progressed_axes_without_changing_legacy_wheel():
    from services.chart_biwheel_svg import generate_biwheel_svg
    kwargs = dict(inner_planets={"sun": {"lon": 10}},
                  outer_planets={"moon": {"lon": 80}},
                  cusps=[i * 30 for i in range(12)], asc_lon=0, mc_lon=90)
    legacy = generate_biwheel_svg(**kwargs)
    assert legacy == generate_biwheel_svg(**kwargs, outer_axes=None)
    assert 'class="progressed-axis"' not in legacy
    marked = generate_biwheel_svg(
        **kwargs, outer_axes={"asc": 30, "mc": 120, "dsc": 210, "ic": 300})
    assert marked.count('class="progressed-axis"') == 4
    for label in ("次ASC", "次MC", "次DSC", "次IC"):
        assert f">{label}</text>" in marked


def test_progressed_biwheel_uses_vector_zodiac_only_when_requested(monkeypatch):
    from services import mcp_compat_utils as calculate
    from services.mcp_extended import _biwheel_png
    captured = []
    monkeypatch.setattr(calculate, "_svg_to_png", lambda svg, size: captured.append(svg) or b"png")
    natal = {"planets": {}, "cusps": [i * 30 for i in range(12)],
             "asc_lon": 0, "mc_lon": 90}
    outer = {"planets": {}}
    assert _biwheel_png(natal, outer, [], "本命", "次限") == b"png"
    assert 'class="zodiac-outline"' not in captured[0]
    assert _biwheel_png(natal, outer, [], "本命", "次限", outline_zodiac=True) == b"png"
    assert captured[1].count('class="zodiac-outline"') == 12
    assert "♈</text>" not in captured[1]


@pytest.mark.parametrize('timing,expected', [
    ({'age': 36.0}, 'ok'),
    ({'age': 0.0}, 'ok'),
    ({'as_of': '2026-04-15'}, 'ok'),
    ({'age': 36.0, 'as_of': '2026-04-15'}, 'invalid_input'),
    ({}, 'ok'),
])
def test_secondary_public_entry_timing_and_verification(timing, expected):
    import asyncio
    import mcp_server
    birth = dict(year=1990, month=4, day=15, hour=18, minute=0,
                 location_id='gn:2988507', house_system='placidus')
    result = asyncio.run(mcp_server.calculate_secondary_progressions(**birth, **timing))
    assert result['status'] == expected
    if expected == 'ok':
        assert result['progressed_chart']['planets']
        if 'age' in timing:
            assert result['settings']['age'] == timing['age']
        check = asyncio.run(mcp_server.verify_calculation_claims(
            reference=mcp_server.CalculationReference(**result['calculation_reference']),
            claims=[mcp_server.CalculationClaim(path='/settings/age', value=result['settings']['age'], quote='次限年龄')]))
        assert check['counts']['supported'] == 1


def test_secondary_public_render_accepts_age_only():
    import asyncio
    import mcp_server
    result = asyncio.run(mcp_server.render_secondary_progressions_chart(
        year=1990, month=4, day=15, hour=18, minute=0,
        location_id='gn:2988507', house_system='placidus', age=36.0))
    assert result.structuredContent['status'] == 'ok'
    assert any(item.type == 'image' for item in result.content)


def test_secondary_normalization_does_not_change_other_tools():
    from services.mcp_result_facts import normalize_arguments
    args = {'age': 36, 'as_of': None}
    assert normalize_arguments(args, tool='calculate_solar_arc')['as_of'] is not None
    assert normalize_arguments(args, tool='calculate_secondary_progressions')['as_of'] is None
    assert normalize_arguments(args, tool='render_secondary_progressions_chart')['as_of'] is None


@pytest.mark.parametrize('angle', [319.9055] + [float(i * 45) + d
                         for i in range(8) for d in (-.0001, 0, .0001)])
def test_secondary_quality_checks_phase_sector(angle):
    from services.mcp_extended import secondary_progressions_data
    from services.mcp_validation import validate_output, PHASES, SIGNS
    args = dict(year=1990, month=4, day=15, hour=18, minute=0,
                location_id='gn:2988507', house_system='placidus', age=36)
    result = secondary_progressions_data(**args)
    chart = result['progressed_chart']
    angle %= 360
    chart['planets']['sun']['longitude'] = 0.0
    chart['planets']['moon']['longitude'] = angle
    chart['planets']['sun']['sign'] = SIGNS[0]
    chart['planets']['moon']['sign'] = SIGNS[int(angle // 30)]
    phase = chart['lunation_phase']
    idx = int(angle // 45)
    phase.update(elongation=round(angle, 4), phase_num=idx+1, phase_name=PHASES[idx])
    assert validate_output('calculate_secondary_progressions', result, args) == []
    wrong = (idx + 3) % 8
    phase.update(phase_num=wrong+1, phase_name=PHASES[wrong])
    assert validate_output('calculate_secondary_progressions', result, args) == [
        {'path': '/progressed_chart/lunation_phase', 'rule': 'rudhyar_45_degree_boundary'}]


@pytest.mark.parametrize('angle', [44.99996, 359.99996])
def test_secondary_quality_accepts_rounded_phase_boundary(angle):
    from services.mcp_extended import secondary_progressions_data
    from services.mcp_validation import validate_output, PHASES, SIGNS
    args = dict(year=1990, month=4, day=15, hour=18, minute=0,
                location_id='gn:2988507', house_system='placidus', age=36)
    result = secondary_progressions_data(**args)
    chart = result['progressed_chart']
    chart['planets']['sun']['longitude'] = 0.0
    chart['planets']['moon']['longitude'] = angle
    chart['planets']['sun']['sign'] = SIGNS[0]
    chart['planets']['moon']['sign'] = SIGNS[int(angle // 30)]
    idx = int(angle // 45)
    chart['lunation_phase'].update(elongation=round(angle, 4), phase_num=idx+1, phase_name=PHASES[idx])
    assert validate_output('calculate_secondary_progressions', result, args) == []
