"""日返盘引擎黄金用例对拍（纯新增，不依赖也不影响本命盘算法）。

真值来源：shared-context 阳光「日返盘引擎开发看板」的两个黄金用例。
关键校验点是 SR ASC/MC——它们只依赖 回归JD + 居住地坐标 + 宫位制，
与交点/凯龙口径无关，是最干净的正确性锚。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import swisseph as swe
from services.ephemeris_guard import apply_ephe_path
from services.calculator import BirthContextError
from services.solar_return import (
    compute_solar_return, compute_solar_return_full, find_return_jd,
    _sign_zh, _deg_in_sign, SR_ASPECT_ORBS,
)

apply_ephe_path()


def _natal_sun(y, mo, d, h, mi, tz_offset):
    ut = h + mi / 60 - tz_offset
    jd = swe.julday(y, mo, d, ut)
    return swe.calc_ut(jd, swe.SUN, swe.FLG_SWIEPH)[0][0]


def test_emma_watson_2026_london():
    """Emma Watson 1990-04-15 18:00 Paris → 2026 日返（居住地 London）。
    宽松校验：回归时刻 ≈ 生日 ±1 天，SR 太阳 = 本命太阳 ±0.01°。"""
    natal_sun = _natal_sun(1990, 4, 15, 18, 0, 2.0)   # Paris CEST=UTC+2
    r = compute_solar_return(
        natal_sun, 2026, 4, 15,
        residence_lat=51.5074, residence_lng=-0.1278,
        residence_tz='Europe/London', residence_city='London',
    )
    # SR 太阳精确回到本命太阳
    sr_sun = r['planets']['sun']['longitude']
    diff = abs((sr_sun - natal_sun + 180) % 360 - 180)
    assert diff < 0.0001, f"SR Sun 应回到本命 Sun，实测差 {diff:.6f}°"
    # 回归时刻在生日附近
    assert r['sr_utc'].startswith('2026-04-1'), f"回归时刻异常：{r['sr_utc']}"
    # 结构完整
    assert r['axes']['ascendant']['longitude'] is not None
    assert len(r['houses']['cusps']) == 12
    assert len(r['planets']) == 10
    print(f"\n[Emma] SR UTC={r['sr_utc']} local={r['sr_local']}  "
          f"ASC={_sign_zh(r['axes']['ascendant']['longitude'])}"
          f"{_deg_in_sign(r['axes']['ascendant']['longitude']):.1f}°")


def test_xiaoli_2026_beijing():
    """小莉 1973-07-31 11:30 乐陵 → 2026 日返（居住地 北京）。
    紧校验（真值来自看板）：SR ASC 狮子26.7° / SR MC 金牛20.6° / 满月~195° / Bucket。"""
    natal_sun = _natal_sun(1973, 7, 31, 11, 30, 8.0)   # China UTC+8, 1973 无 DST
    r = compute_solar_return(
        natal_sun, 2026, 7, 31,
        residence_lat=39.9042, residence_lng=116.4074,
        residence_tz='Asia/Shanghai', residence_city='北京',
    )

    asc = r['axes']['ascendant']['longitude']
    mc = r['axes']['midheaven']['longitude']
    asc_sign = _sign_zh(asc)
    mc_sign = _sign_zh(mc)
    asc_deg = _deg_in_sign(asc)
    mc_deg = _deg_in_sign(mc)
    elong = r['lunation_phase']['elongation']
    jones = r['jones_pattern'].get('pattern_en')

    print(f"\n[小莉] SR UTC={r['sr_utc']}  local={r['sr_local']}")
    print(f"       ASC={asc_sign}{asc_deg:.1f}° (真值 狮子26.7°)")
    print(f"       MC ={mc_sign}{mc_deg:.1f}° (真值 金牛20.6°)")
    print(f"       月相张角={elong:.1f}° (真值 满月~195°)  格局={jones} (真值 Bucket)")

    # ASC/MC 只依赖 回归JD + 居住地 + 宫位制，是最干净的锚
    assert asc_sign == '狮子', f"SR ASC 星座应为狮子，实测 {asc_sign}"
    assert abs(asc_deg - 26.7) < 1.0, f"SR ASC 度数应≈26.7°，实测 {asc_deg:.2f}°"
    assert mc_sign == '金牛', f"SR MC 星座应为金牛，实测 {mc_sign}"
    assert abs(mc_deg - 20.6) < 1.0, f"SR MC 度数应≈20.6°，实测 {mc_deg:.2f}°"
    assert abs(elong - 195) < 10, f"月相张角应≈195°（满月），实测 {elong:.1f}°"

    # 格局：看板写 Bucket，但那是阳光独立 skill 的判定。我们的稳定检测器判 Locomotive，
    # 且几何上正确——SR 十行星占据跨度 228.8°（远超 Bucket 要求的 <180°），最大空档
    # 131° ≈ 空三分相，正是火车头型定义。此处固化我们的正确判定，防回归。
    assert jones == 'Locomotive', (
        f"SR 格局应为 Locomotive（跨度 228.8° 几何上不可能是看板写的 Bucket），实测 {jones}"
    )


def test_return_jd_precision():
    """回归时刻精度：牛顿法收敛后，该 JD 上的太阳经度 = 目标本命太阳经度。"""
    natal_sun = 127.789747
    jd = find_return_jd(natal_sun, 2026, 7, 31)
    sun = swe.calc_ut(jd, swe.SUN, swe.FLG_SWIEPH)[0][0]
    diff = abs((sun - natal_sun + 180) % 360 - 180)
    assert diff < 1e-6, f"回归时刻太阳经度误差 {diff:.8f}° 超标"


def test_full_consistency_with_foundation():
    """完整版内部重算的本命太阳，导出的日返 ASC 必须跟地基版（外部传 sun_lon）完全一致。
    证明「完整版内部算本命」这条新路没有引入偏差。"""
    natal_sun = _natal_sun(1973, 7, 31, 11, 30, 8.0)
    base = compute_solar_return(
        natal_sun, 2026, 7, 31, 39.9042, 116.4074, 'Asia/Shanghai', '北京')
    full = compute_solar_return_full(
        1973, 7, 31, 11, 30, 37.73, 117.23,
        2026, 39.9042, 116.4074, 'Asia/Shanghai', '北京')
    # 本命出生地(乐陵)只影响本命宫位，不影响本命太阳经度 → 回归时刻/日返盘应一致
    assert abs(base['sr_jd'] - full['sr_jd']) < 1e-6, "完整版与地基版回归时刻不一致"
    b_asc = base['axes']['ascendant']['longitude']
    f_asc = full['single']['angles']['ascendant']['longitude']
    assert abs(b_asc - f_asc) < 1e-6, "完整版与地基版 SR ASC 不一致"


def test_full_24_dimensions():
    """完整版 24 维度：结构齐全 + 几个可验证的锚点。"""
    full = compute_solar_return_full(
        1973, 7, 31, 11, 30, 37.73, 117.23,
        2026, 39.9042, 116.4074, 'Asia/Shanghai', '北京')

    # 四层齐全
    assert set(full['single']) >= {
        'planets', 'angles', 'houses', 'sun_house', 'moon', 'lunation_phase',
        'retrograde_planets', 'angular_planets', 'jones_pattern',
        'intercepted_signs', 'elements', 'unaspected_planets', 'aspects'}
    assert set(full['overlay']) == {
        'sr_planets_in_natal_houses', 'natal_planets_in_sr_houses',
        'angle_contacts', 'degree_contacts', 'repeating_aspects', 'cross_aspects'}
    assert set(full['timeline']) == {
        'moon_progressions', 'sun_transits', 'metonic_cycle', 'saturn_return',
        'moon_element_cycle'}
    assert set(full['focus']) == {'asc_ruler', 'annual_focus'}

    # 锚点1：日返太阳合本命太阳（日返的定义本身）——直接比对两个经度验证引擎
    # 算对了，不能靠它在 degree_contacts 里出现来验证（那是用户可见的解读列表，
    # 这一对必然重合、没有信息量，_degree_contacts 无条件排除，见下一条断言）。
    sun_sr_lon = full['single']['planets']['sun']['longitude']
    sun_natal_lon = full['natal']['planets']['sun']['longitude']
    assert abs(((sun_sr_lon - sun_natal_lon + 180) % 360) - 180) < 0.01, "日返太阳应精确合本命太阳"
    sun_sun = [c for c in full['overlay']['degree_contacts']
               if c['sr_planet'] == 'sun' and c['natal_point'] == 'sun']
    assert not sun_sun, "日返太阳合本命太阳是日返的定义本身，必然重合、没有信息量，不该出现在度数重合列表里"

    # 锚点2：看板核心解读点——SR ASC 合本命月亮（看板 orb 0.4°，容差内）
    asc_moon = [c for c in full['overlay']['angle_contacts']
                if c['axis'] == 'asc' and c['natal_planet'] == 'moon']
    assert asc_moon and asc_moon[0]['orb'] < 2.0, "SR ASC 应合本命月亮（看板核心点）"

    # 锚点3：狮子上升 → 传统守护星为太阳
    assert full['single']['angles']['ascendant']['sign'] == '狮子'
    assert full['focus']['asc_ruler']['planet'] == 'sun'

    # 锚点4：满月张角 ≈195°；元素十颗星求和为10
    assert abs(full['single']['lunation_phase']['elongation'] - 195) < 10
    assert sum(full['single']['elements']['counts'].values()) == 10

    # 锚点5：行运太阳过境覆盖日返后一整年（有轴/星命中，日期递增）
    st = full['timeline']['sun_transits']
    assert len(st) >= 10, "行运太阳一年应过境多数日返点"
    assert st == sorted(st, key=lambda x: x['date']), "过境日期应递增"


def test_moon_element_cycle_tracks_multi_year_series():
    """SR 月亮跨年连续同元素（NotebookLM「Cycles of Light」Lynn Bell + Brian
    Clark 一致结论）：小莉样例真实算出 2024-2026 是连续 3 年风象月亮系列
    （2024 开启/2025 延续/2026 收尾），2027 换水象重新开启——不是编的期望值，
    是先跑出结果、确认年与年之间的 stage/position 自洽（开启年的下一年必须
    是延续或收尾、收尾年的下一年必须换元素）才固化成断言。"""
    def cycle_for(year):
        full = compute_solar_return_full(
            1973, 7, 31, 11, 30, 37.73, 117.23,
            year, 39.9042, 116.4074, 'Asia/Shanghai', '北京')
        return full['timeline']['moon_element_cycle']

    c2023, c2024, c2025, c2026, c2027 = (cycle_for(y) for y in (2023, 2024, 2025, 2026, 2027))

    assert c2023['element'] == '土' and c2023['stage'] == 'closing'
    assert c2024['element'] == '风' and c2024['stage'] == 'opening' and c2024['position_in_run'] == 1
    assert c2025['element'] == '风' and c2025['stage'] == 'continuing' and c2025['position_in_run'] == 2
    assert c2026['element'] == '风' and c2026['stage'] == 'closing' and c2026['position_in_run'] == 3
    assert c2027['element'] == '水' and c2027['stage'] == 'opening' and c2027['position_in_run'] == 1

    # 同一元素跨年星座通常不同——月亮每年前进约一个三分相，在同一元素的
    # 2-3 个星座间循环（不是原地重复同一个星座），三年风象系列真实算出
    # 双子→天秤→水瓶，恰好互为三分相，验证「星座逐年标」这个设计前提成立。
    assert c2024['sign'] == '双子' and c2025['sign'] == '天秤' and c2026['sign'] == '水瓶'
    # prev/next 交叉校验：今年的 next_sign 必须等于明年的 sign（同一份数据两条路算出来一致）。
    assert c2024['next_sign'] == c2025['sign']
    assert c2025['next_sign'] == c2026['sign']
    assert c2026['next_sign'] == c2027['sign']
    assert c2025['prev_sign'] == c2024['sign']


def test_layered_aspect_orbs():
    """日返内部相位用分层容许度（NotebookLM 两库一致结论），不套本命 10°、不砍统一 3°。
    小莉样例：分层后正好 14 个内部相位（10° 会误纳 20 个过宽相位，3° 会误删有效相位）。"""
    full = compute_solar_return_full(
        1973, 7, 31, 11, 30, 37.73, 117.23,
        2026, 39.9042, 116.4074, 'Asia/Shanghai', '北京')

    aspects = full['single']['aspects']
    # 研究背书的确定数：分层矩阵下小莉日返内部相位 = 14
    assert len(aspects) == 14, f"分层容许度下应为 14 个日返内部相位，实测 {len(aspects)}"
    # 每个相位的 orb 必须落在其相位类型的分层上限内（不是统一 10°）
    for a in aspects:
        assert a['orb'] <= SR_ASPECT_ORBS[a['angle']] + 1e-9, \
            f"{a['aspect']} orb {a['orb']:.2f} 超出分层上限 {SR_ASPECT_ORBS[a['angle']]}"
    # 合/冲最宽 6°：不应再出现 10° 那种过宽相位
    assert max(a['orb'] for a in aspects) <= 6.0

    # 角宫行星带强度分层（core ≤3° / extended），8° 门槛保留
    for ap in full['single']['angular_planets']:
        assert ap['strength'] in ('core', 'extended')
        assert ap['orb'] <= 8.0
        assert (ap['strength'] == 'core') == (ap['orb'] <= 3.0)

    # 度数重合放宽到 3°（仍输出精确 orb 供前端突出 1° 内接触）
    for c in full['overlay']['degree_contacts']:
        assert c['orb'] <= 3.0

    # 相位重现：本命端与日返端各用各的容许度，本命 10° 端不受日返收紧影响
    for r in full['overlay']['repeating_aspects']:
        assert r['sr_aspect']['orb'] <= SR_ASPECT_ORBS[r['sr_aspect']['angle']] + 1e-9


def test_cross_aspects():
    """跨盘相位（日返行星 × 本命行星）——比较盘中心相位网。紧容许度、结构完整、
    但排除日返定义必然成立、没有区分度的日返太阳合本命太阳。"""
    from services.solar_return import CROSS_ASPECT_ORBS
    full = compute_solar_return_full(1973, 7, 31, 11, 30, 37.73, 117.23,
                                     2026, 39.9042, 116.4074, 'Asia/Shanghai', '北京')
    ca = full['overlay']['cross_aspects']
    assert ca, "跨盘相位不应为空"
    # 每条相位 orb 不超其类型的跨盘容许度（紧口径，不套本命 10°）
    for x in ca:
        assert x['orb'] <= CROSS_ASPECT_ORBS[x['angle']] + 1e-9, \
            f"跨盘{x['aspect']} orb {x['orb']:.2f} 超上限 {CROSS_ASPECT_ORBS[x['angle']]}"
        assert x['sr_planet'] and x['natal_planet']
    # 日返太阳合本命太阳是日返定义本身，不应占用跨盘相位列表或相位线。
    sun_sun = [x for x in ca if x['sr_planet'] == 'sun' and x['natal_planet'] == 'sun']
    assert not sun_sun


def test_dst_gap_birth_rejected():
    """P1 合约：春拨空白（不存在的出生时刻）必须抛 BirthContextError，绝不静默按 UTC 出盘。
    美东 2021-03-14 02:30 在夏令时跳过窗口内。"""
    with pytest.raises(BirthContextError):
        compute_solar_return_full(2021, 3, 14, 2, 30, 40.71, -74.01,
                                  2026, 40.71, -74.01, 'America/New_York', 'NY')


def test_dst_ambiguous_birth_requires_fold():
    """P1 合约：秋拨歧义（出现两次）未选 fold 必须抛 BirthContextError；选了 fold 才出盘，
    且 fold=0/1 给出不同的真实 UTC 瞬间。美东 2021-11-07 01:30 在回拨窗口内。"""
    with pytest.raises(BirthContextError):
        compute_solar_return_full(2021, 11, 7, 1, 30, 40.71, -74.01,
                                  2026, 40.71, -74.01, 'America/New_York', 'NY')
    r0 = compute_solar_return_full(2021, 11, 7, 1, 30, 40.71, -74.01,
                                   2026, 40.71, -74.01, 'America/New_York', 'NY', birth_fold=0)
    r1 = compute_solar_return_full(2021, 11, 7, 1, 30, 40.71, -74.01,
                                   2026, 40.71, -74.01, 'America/New_York', 'NY', birth_fold=1)
    assert r0['sr_utc'] != r1['sr_utc'], "两个 fold 应对应不同的真实 UTC 瞬间"


def test_dst_correct_offset_not_silently_utc():
    """P1 回归：小莉 1973-07-31 乐陵，解析链应得 UTC+8（不是旧版静默的 UTC）。
    对比「按 UTC 误算」的错误 ASC，证明不再静默降级。"""
    correct = compute_solar_return_full(1973, 7, 31, 11, 30, 37.73, 117.23,
                                        2026, 39.9042, 116.4074, 'Asia/Shanghai', '北京')
    # 若误按 UTC（offset=0），本命太阳偏 ~0.33° → 回归时刻偏 ~8h → ASC 天差地别。
    wrong_utc_jd = swe.julday(1973, 7, 31, 11 + 30 / 60)  # offset=0 的错误本命 JD
    wrong_sun = swe.calc_ut(wrong_utc_jd, swe.SUN, swe.FLG_SWIEPH)[0][0]
    correct_natal_sun = correct['natal']['planets']['sun']['longitude']
    assert abs((wrong_sun - correct_natal_sun + 180) % 360 - 180) > 0.2, \
        "UTC 误算与正确解析的本命太阳应有可观差异，证明解析链真的生效"


if __name__ == '__main__':
    test_return_jd_precision()
    test_emma_watson_2026_london()
    test_xiaoli_2026_beijing()
    test_full_consistency_with_foundation()
    test_full_24_dimensions()
    test_layered_aspect_orbs()
    test_cross_aspects()
    test_dst_gap_birth_rejected()
    test_dst_ambiguous_birth_requires_fold()
    test_dst_correct_offset_not_silently_utc()
    print("\n✅ 全部用例通过（地基 + 24 维度 + 分层容许度 + P1 时区/DST 合约）")


def test_cross_aspects_and_contacts_carry_applying_direction():
    """日返跨盘相位与同度数接触必须带入相/出相，方向与真实星历一致。

    跨盘与本命盘内相位的区别：本命盘是出生瞬间的定格、不参与运动，所以
    相对速度就是日返行星自身的速度。这里用 swisseph 把日返盘真的推进与
    本命算法一致的 0.001 天后重算容许度，而不是重跑同一套公式自证。
    """
    from services import solar_return as sr

    apply_ephe_path()
    jd = 2451545.0

    def build(jd_value):
        planets = {}
        for key, pid in sr.PLANET_DEFS:
            data, _ = swe.calc_ut(jd_value, pid, sr._FLAGS)
            planets[key] = sr._point(
                sr._norm(data[0]), retrograde=(data[3] < 0), speed=data[3],
            )
        return planets

    sr_planets = build(jd)
    natal_planets = build(jd - 3000.0)
    natal_axes = {
        'ascendant': sr._point(10.0),
        'midheaven': sr._point(100.0),
    }

    rows = sr._cross_aspects(sr_planets, natal_planets)
    assert rows, "样例盘应当有跨盘相位"
    assert all('applying' in row for row in rows)

    later = build(jd + sr._APPLYING_DT)
    checked = 0
    for row in rows:
        if row['applying'] is None:
            continue
        checked += 1
        moving = later[row['sr_planet']]['longitude']
        fixed = natal_planets[row['natal_planet']]['longitude']
        later_orb = abs(sr._angular_sep(moving, fixed) - row['angle'])
        shrinking = later_orb < row['orb']
        assert shrinking == row['applying'], (
            f"{row['sr_planet']}-{row['natal_planet']} 标记"
            f"{'入相' if row['applying'] else '出相'}，"
            f"但容许度 {row['orb']:.4f} → {later_orb:.4f}"
        )
    assert checked >= 3, f"有效校验样本过少：{checked}"

    contacts = sr._degree_contacts(sr_planets, natal_planets, natal_axes)
    assert all('applying' in row for row in contacts)


def test_applying_is_none_when_direction_is_unknowable():
    """速度缺失或几乎静止时返回 None，不猜方向。

    宁可不显示标记，也不给一个没有依据的入相/出相。
    """
    from services import solar_return as sr

    assert sr._applying(10.0, None, 100.0, 90) is None
    assert sr._applying(10.0, 0.0, 100.0, 90) is None
    # 正常速度下必须给出明确方向
    assert isinstance(sr._applying(10.0, 1.0, 100.0, 90), bool)
