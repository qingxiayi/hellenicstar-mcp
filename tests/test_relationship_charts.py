"""Geometry invariants, source example, library parity and authenticated API."""
import copy
import math

import pytest

from services.relationship_charts import (
    AXES, PLANETS, build_relationship_charts, house_of, midpoint, separation,
)


def summary(offset=0):
    cusps = [(offset + i * 30) % 360 for i in range(12)]
    return {'name': 'fixture', 'svg_data': {
        'planets': {p: {'lon': (offset + i * 27) % 360} for i, p in enumerate(PLANETS)},
        'cusps': cusps, 'asc_lon': cusps[0], 'mc_lon': cusps[9], 'aspects': []}}


@pytest.mark.parametrize('a,b,expected', [(350, 10, 0), (359, 1, 0), (120, 160, 140), (0, 0, 0)])
def test_midpoint_wrap(a, b, expected):
    assert separation(midpoint(a, b)['longitude'], expected) < 1e-9


@pytest.mark.parametrize('a', [0, 3.4, 90, 179.999, 250])
def test_antipodes_are_ambiguous_and_symmetric(a):
    r = midpoint(a, (a + 180) % 360)
    assert r['longitude'] is None
    assert r['status'] == 'ambiguous'
    assert r['candidates'] == pytest.approx(midpoint((a + 180) % 360, a)['candidates'])


@pytest.mark.parametrize('bad', [True, None, float('nan'), float('inf'), '23'])
def test_invalid_longitude(bad):
    with pytest.raises(ValueError):
        midpoint(bad, 0)


def test_identity_and_no_mutation():
    a = summary(350)
    original = copy.deepcopy(a)
    r = build_relationship_charts(a, a)
    assert a == original
    c = r['charts']['composite']
    assert c['houses']['status'] == 'ok'
    for p in PLANETS:
        assert separation(c['planets'][p]['longitude'], a['svg_data']['planets'][p]['lon']) < 1e-8
    # Same-name Sun contacts must survive, unlike the solar-return implementation.
    assert any(x['first_point'] == x['second_point'] == 'sun' and x['angle'] == 0
               for x in r['synastry']['aspects'])
    assert all(x['applying'] is None for x in r['synastry']['aspects'])
    assert 'relationship_score' not in r


def test_swap_symmetry_and_overlay_direction():
    a, b = summary(350), summary(20)
    ab, ba = build_relationship_charts(a, b), build_relationship_charts(b, a)
    assert ab['charts']['composite'] == ba['charts']['composite']
    left = {(r['first_point'], r['second_point'], r['angle']): r['orb'] for r in ab['synastry']['aspects']}
    right = {(r['second_point'], r['first_point'], r['angle']): r['orb'] for r in ba['synastry']['aspects']}
    assert left == pytest.approx(right)
    assert next(r['house'] for r in ab['synastry']['a_in_b'] if r['point'] == 'sun') == 12
    assert next(r['house'] for r in ab['synastry']['b_in_a'] if r['point'] == 'sun') == 2


def test_cusp_exact_boundary():
    cusps = summary(350)['svg_data']['cusps']
    assert house_of(350, cusps) == 1
    assert house_of(20, cusps) == 2
    assert house_of(349.999, cusps) == 12


def test_ambiguous_composite_preserves_synastry():
    r = build_relationship_charts(summary(), summary(180))
    c = r['charts']['composite']
    assert c['houses']['status'] == 'ambiguous'
    assert c['houses']['cusps'] is None
    assert set(c['ambiguous_points']) == set(PLANETS + AXES)
    assert c['aspects'] == []
    assert r['synastry']['aspects']
    assert r['composite_to_natal']['a']['aspects'] == []


def test_crossing_midpoint_cusps_are_not_relabelled():
    a, b = summary(), summary(170)
    # Both natal house sets are ordered and antipodally consistent, but short-arc
    # choices change sides between cusp 1 and 2, yielding multiple revolutions.
    b['svg_data']['cusps'] = [170, 220, 245, 260, 280, 320, 350, 40, 65, 80, 100, 140]
    b['svg_data']['mc_lon'] = 80
    c = build_relationship_charts(a, b)['charts']['composite']
    assert c['houses']['status'] == 'invalid_order'
    assert c['houses']['cusps'] is None
    assert c['axes']['ascendant']['longitude'] == pytest.approx(85)
    assert c['point_houses'] == []


def test_greene_hypothetical_arthur_brenda_and_evidence_links():
    a, b = summary(), summary(40)
    a['svg_data']['planets'].update(sun={'lon': 218}, uranus={'lon': 43})
    b['svg_data']['planets'].update(sun={'lon': 348}, uranus={'lon': 167}, moon={'lon': 105}, saturn={'lon': 105})
    r = build_relationship_charts(a, b)
    c = r['charts']['composite']
    assert c['planets']['sun']['longitude'] == pytest.approx(283)
    assert c['planets']['uranus']['longitude'] == pytest.approx(105)
    assert any(x['first_point'] == 'sun' and x['second_point'] == 'uranus' and x['angle'] == 180
               for x in c['aspects'])
    contacts = r['composite_to_natal']['b']['aspects']
    assert {x['second_point'] for x in contacts if x['first_point'] == 'uranus' and x['orb'] < 1e-8} >= {'moon', 'saturn'}
    ids = {a['id'] for chart in r['charts'].values() for a in chart['aspects']}
    for link in r['structure_links']:
        assert all(i in ids for group in link['natal_aspect_ids'].values() for i in group)
    assert any(x['points'] == ['sun', 'uranus'] and len(x['aspects_by_chart']) == 3 for x in r['repeated_pairs'])


def test_orb_limits_inclusive_and_outside_excluded():
    a, b = summary(), summary()
    b['svg_data']['planets']['sun']['lon'] = 100
    rows = build_relationship_charts(a, b)['synastry']['aspects']
    assert any(r['first_point'] == r['second_point'] == 'sun' and r['angle'] == 90 and r['orb'] == 10 for r in rows)
    b['svg_data']['planets']['sun']['lon'] = 100.0001
    rows = build_relationship_charts(a, b)['synastry']['aspects']
    assert not any(r['first_point'] == r['second_point'] == 'sun' for r in rows)


def test_against_kerykeion_factory_with_independent_birth_subjects():
    from kerykeion import AstrologicalSubjectFactory, CompositeSubjectFactory
    args = dict(lng=2.3522, lat=48.8566, tz_str='Europe/Paris', online=False)
    a = AstrologicalSubjectFactory.from_birth_data('A', 1990, 4, 15, 18, 0, **args)
    b = AstrologicalSubjectFactory.from_birth_data('B', 1985, 8, 20, 12, 0, **args)
    c = CompositeSubjectFactory(a, b).get_midpoint_composite_subject_model()
    for p in PLANETS[:10]:
        assert separation(midpoint(a[p].abs_pos, b[p].abs_pos)['longitude'], c[p].abs_pos) < 1e-9
    # Independent arithmetic short-arc oracle, beyond shared library parity.
    for i in range(0, 360, 7):
        for j in range(0, 360, 11):
            delta = (j - i + 180) % 360 - 180
            if abs(delta) != 180:
                assert separation(midpoint(i, j)['longitude'], (i + delta / 2) % 360) < 1e-8















def test_lunar_nodes_are_displayed_but_only_the_north_node_forms_aspects():
    """南北交进位置与落宫，但只有北交参与判相。

    2026-09-06 用户发现关系盘缺南北交。原因是首版把交点和福点/精神点一起排除了，
    理由写的是"避免把本命特殊点规则扩展到中点盘"——这对福点成立（它由上升+日月
    推导，先取中点与先推导结果不同），对交点不成立：交点是月球轨道与黄道的真实
    交点，可以像行星一样直接取中点。

    南交恒为北交对点，两者同时判相会让每条交点相位重复一次（太阳合北交必然
    同时是太阳冲南交）。因此沿用 transit_natal.py 的口径：只有北交判相。
    """
    from services.calculator import compute

    summary_a = compute(name="Emma", year=1990, month=4, day=15, hour=18, minute=0,
                        city="Paris", lat=48.8566, lng=2.3522)
    summary_b = compute(name="B", year=1985, month=8, day=20, hour=12, minute=0,
                        city="Paris", lat=48.8566, lng=2.3522)
    result = build_relationship_charts(summary_a, summary_b, "greene")
    charts = result["charts"]

    # 三张盘都要有南北交，且组合盘的交点仍严格保持 180° 对点关系。
    for chart_id in ("a", "b", "composite"):
        planets = charts[chart_id]["planets"]
        assert "north_node" in planets and "south_node" in planets, chart_id
        north = planets["north_node"]["longitude"]
        south = planets["south_node"]["longitude"]
        assert abs(abs((north - south + 180) % 360 - 180) - 180) < 1e-9, (
            f"{chart_id} 的南北交不再是对点")

    # 判相只认北交；南交一条相位都不该出现，否则就是同一几何事实数了两次。
    cross = result["synastry"]["aspects"]
    assert any("north_node" in (row["first_point"], row["second_point"]) for row in cross)
    assert not any("south_node" in (row["first_point"], row["second_point"]) for row in cross)
    for branch in ("a", "b"):
        rows = result["composite_to_natal"][branch]["aspects"]
        assert not any("south_node" in (r["first_point"], r["second_point"]) for r in rows)
    for chart_id in ("a", "b", "composite"):
        rows = charts[chart_id]["aspects"]
        assert not any("south_node" in (r["first_point"], r["second_point"]) for r in rows)

    # 但落宫必须两个都给：南交落在哪一宫是要读的，不能因为不判相就不给位置。
    for overlay_key in ("a_in_b", "b_in_a"):
        points = {row["point"] for row in result["synastry"][overlay_key]}
        assert {"north_node", "south_node"} <= points, overlay_key

    # 契约要自我说明：外部读者能看出南交为何没有相位。
    assert "north_node" in result["method"]["points"]
    assert "south_node" in result["method"]["points"]
    assert result["method"]["aspect_excluded_points"] == ["south_node"]


def test_derived_lots_stay_out_of_the_composite_chart():
    """福点/精神点仍不纳入：它们由上升+日月推导，中点口径未决，不能顺手加。"""
    from services.calculator import compute

    summary_a = compute(name="Emma", year=1990, month=4, day=15, hour=18, minute=0,
                        city="Paris", lat=48.8566, lng=2.3522)
    result = build_relationship_charts(summary_a, summary_a, "greene")
    for chart_id in ("a", "b", "composite"):
        planets = result["charts"][chart_id]["planets"]
        assert "fortune" not in planets and "spirit" not in planets


def test_natal_house_patterns_use_combined_own_house_occupancy_including_nodes():
    """格局只看各自本命落宫；南北交参与，度数、星座和四轴不参与。"""
    from services.relationship_charts import natal_house_patterns

    def chart(chart_id, planet_houses, extra=None):
        cusps = [i * 30 for i in range(12)]
        planets = {point: {'longitude': (house - 1) * 30 + 5}
                   for point, house in planet_houses.items()}
        planets.update(extra or {})
        return {
            'id': chart_id,
            'planets': planets,
            'axes': {'ascendant': {'longitude': 0}, 'midheaven': {'longitude': 270}},
            'houses': {'status': 'ok', 'cusps': cusps},
        }

    # A 的太阳占 3 宫、北交占 7 宫，B 用火星补足 11 宫，形成风象宫位大三角。
    # 南交也进入成员池，但落在 1 宫，不影响这一个格局。
    a = chart('a', {'sun': 3}, {
        'north_node': {'longitude': 185},
        'south_node': {'longitude': 5},
    })
    b = chart('b', {'mars': 11, 'venus': 4})
    result = natal_house_patterns(a, b)

    assert result['house_system'] == 'placidus'
    # 2026-09-06：四个三角与三个十字一律返回，complete 只是其中一个观察角度。
    # 此前只回传 complete 的那几个，读者无从知道其余结构缺在哪一宫。
    assert len(result['patterns']) == 7
    assert [p['id'] for p in result['patterns'] if p['complete']] == ['air_triplicity']
    pattern = next(p for p in result['patterns'] if p['id'] == 'air_triplicity')
    assert [row['house'] for row in pattern['houses']] == [3, 7, 11]
    assert pattern['houses'][1]['members'] == [{'chart': 'a', 'point': 'north_node'}]
    assert pattern['houses'][2]['members'] == [{'chart': 'b', 'point': 'mars'}]
    assert pattern['contributors'] == ['a', 'b'] and pattern['empty_houses'] == []


def test_natal_house_patterns_require_both_people_and_every_house():
    from services.relationship_charts import natal_house_patterns

    def chart(chart_id, placements):
        cusps = [i * 30 for i in range(12)]
        return {
            'id': chart_id,
            'planets': {point: {'longitude': (house - 1) * 30 + 5}
                        for point, house in placements.items()},
            'axes': {},
            'houses': {'status': 'ok', 'cusps': cusps},
        }

    # A 单独占满 1/5/9，但 B 没参与，不算成型；1/4/7/10 缺 10 宫也不算成型。
    # 成型判定规则本身没有放宽——变的只是这些结构现在也会被列出来（complete=False），
    # 让读者看到它们缺在哪一宫，而不是整条消失。
    a = chart('a', {'sun': 1, 'moon': 5, 'mercury': 9, 'venus': 4})
    b = chart('b', {'mars': 7})
    result = natal_house_patterns(a, b)
    assert len(result['patterns']) == 7
    assert [p['id'] for p in result['patterns'] if p['complete']] == []

    fire = next(p for p in result['patterns'] if p['id'] == 'fire_triplicity')
    assert fire['empty_houses'] == [], '1/5/9 三宫都有星，只是缺 B'
    assert fire['contributors'] == ['a'], '只有 A 贡献 ⇒ 不成型'

    cardinal = next(p for p in result['patterns'] if p['id'] == 'cardinal_cross')
    assert cardinal['empty_houses'] == [10], '10 宫空 ⇒ 不成型，且要指出空在哪'
