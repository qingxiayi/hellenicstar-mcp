# -*- coding: utf-8 -*-
"""今日月相日历：独立天象计算服务。"""
import json
import os
import sys
import tempfile


from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest
import swisseph as swe

from services import sky_now
from engine.natal_chart import NatalChartCalculator






def test_sky_at_known_epoch_returns_compact_calendar_contract():
    # 首页日历返回月相与低频行星事件，但不返回完整十大行星黄经表。
    payload = sky_now.sky_at(2451545.0, timestamp="2000-01-01T12:00:00Z")
    assert payload["timestamp"] == "2000-01-01T12:00:00Z"
    assert "bodies" not in payload
    phase = payload["moon_phase"]
    assert phase["phase_name"] in sky_now.PHASE_NAMES
    assert 1 <= phase["phase_num"] <= 8
    assert 0 <= phase["illumination_pct"] <= 100
    expected_illumination = swe.pheno_ut(2451545.0, swe.MOON, swe.FLG_SWIEPH)[1] * 100
    assert phase["illumination_pct"] == pytest.approx(expected_illumination, abs=0.01)
    assert phase["illumination_source"] == "swiss_ephemeris_pheno"
    assert phase["exact_at"] is None or phase["exact_at"].endswith("Z")
    assert 0 <= phase["cycle_progress_pct"] < 100
    assert isinstance(phase["is_waxing"], bool)
    assert isinstance(payload["retrograde_planets"], list)
    assert isinstance(payload["stations_today"], list)
    assert isinstance(payload["planet_aspects_today"], list)
    assert payload["moon_motion"]["state"] in ("fast", "slow")
    assert payload["moon_motion"]["state_cn"] in ("快", "慢")
    assert payload["moon_motion"]["speed_deg_per_day"] > 0
    assert payload["moon_node_distance"]["nearest"] in ("north", "south")
    assert 0 <= payload["moon_node_distance"]["distance_deg"] <= 90


def test_sky_at_direct_calls_are_sun_moon_and_mean_node_only(monkeypatch):
    """`sky_at` 直接查询日、月与平均北交点；月空亡判定另外临时取其余九大
    行星这件事委托给 transit_utils，不在这条调用链里发生。"""
    calls = []

    def fake_position(planet, jd_ut):
        calls.append(planet)
        if planet == swe.SUN:
            return 0.0, 1.0
        if planet == swe.MEAN_NODE:
            return 45.0, -0.05
        return (90.0 + 13.0 * (jd_ut - 2451545.0)) % 360.0, 13.0  # swe.MOON

    monkeypatch.setattr(sky_now, "body_position", fake_position)
    monkeypatch.setattr(sky_now, "last_exact_before", lambda *a, **k: None)
    payload = sky_now.sky_at(2451545.0)
    assert calls[0] == swe.SUN
    assert set(calls) == {swe.SUN, swe.MOON, swe.MEAN_NODE}
    assert "bodies" not in payload
    assert payload["moon_phase"]["phase_name"] == "上弦月"
    assert payload["moon_motion"]["state"] == "slow"
    assert payload["moon_node_distance"] == {
        "nearest": "north", "nearest_cn": "北交点",
        "distance_deg": 45.0, "nearest_lon": 45.0,
    }


def test_moon_motion_and_node_distance_choose_nearest_node(monkeypatch):
    monkeypatch.setattr(
        sky_now, "body_position",
        lambda planet, jd: (10.0, -0.05) if planet == swe.MEAN_NODE else (0.0, 0.0),
    )
    fast, north = sky_now._moon_motion_and_node_distance(18.0, 13.8, 2451545.0)
    assert fast["state"] == "fast"
    assert fast["state_cn"] == "快"
    assert north["nearest"] == "north"
    assert north["distance_deg"] == 8.0

    slow, south = sky_now._moon_motion_and_node_distance(195.0, 12.4, 2451545.0)
    assert slow["state"] == "slow"
    assert slow["state_cn"] == "慢"
    assert south["nearest"] == "south"
    assert south["nearest_cn"] == "南交点"
    assert south["distance_deg"] == 5.0


def test_voc_bodies_are_all_nine_planets_excluding_moon():
    """月空亡判定范围锁死在日水金火木土天海冥全九大行星（不碰月亮自身/交点/
    凯龙）——主流现代占星软件口径（对拍过 moontracks.com 验证），不是古典七星
    限定，这是政策断言不是调用拦截，改了这个常量测试就会炸。"""
    assert set(sky_now._VOC_BODIES) == {
        swe.SUN, swe.MERCURY, swe.VENUS, swe.MARS, swe.JUPITER, swe.SATURN,
        swe.URANUS, swe.NEPTUNE, swe.PLUTO,
    }
    assert swe.MOON not in sky_now._VOC_BODIES


def test_moon_phase_octants():
    new = sky_now.moon_phase(0.0, 10.0)
    assert new["phase_name"] == "新月"
    assert new["illumination_pct"] < 2
    assert new["is_waxing"] is True
    assert sky_now.moon_phase(0.0, 100.0)["phase_name"] == "上弦月"
    full = sky_now.moon_phase(0.0, 180.0)
    assert full["phase_name"] == "满月"
    assert full["illumination_pct"] == 100
    assert full["is_waxing"] is False
    assert sky_now.moon_phase(0.0, 270.0)["phase_name"] == "下弦月"
    assert sky_now.moon_phase(350.0, 10.0)["phase_num"] == 1


def test_phase_after_exact_full_stays_in_full_band_with_real_illumination():
    """209° 仍在丹露雅尔满月段（180°–225°）内，阶段名不提前跳到亏凸月；
    「已经不圆了」由真实照明率和 exact_at 派生的已过时长表达，不靠挪边界。"""
    phase = sky_now.moon_phase(0.0, 209.0, illuminated_fraction=0.937503)
    assert phase["phase_name"] == "满月"
    assert phase["phase_num"] == 5
    assert phase["phase_progress_deg"] == 29.0
    assert phase["is_waxing"] is False
    assert phase["illumination_pct"] == 93.75
    assert phase["illumination_source"] == "swiss_ephemeris_pheno"


def test_phase_boundaries_sit_on_the_exact_aspects_not_their_midpoints():
    """边界即精确相位：满月段起于 180°、止于 225°，与 engine/natal_chart.py
    的本命月相、services/progressed_phase.py 的次限月相同口径。"""
    assert sky_now.moon_phase(0.0, 179.99)["phase_name"] == "盈凸月"
    assert sky_now.moon_phase(0.0, 180.0)["phase_name"] == "满月"
    assert sky_now.moon_phase(0.0, 224.99)["phase_name"] == "满月"
    assert sky_now.moon_phase(0.0, 225.0)["phase_name"] == "亏凸月"
    assert sky_now.moon_phase(0.0, 314.99)["phase_name"] == "下弦月"
    assert sky_now.moon_phase(0.0, 315.0)["phase_name"] == "残月"


def test_phase_octants_match_natal_engine_across_the_whole_cycle():
    """首页与本命盘必须逐度同名——口径分裂过一次（首页中心分区 vs 本命 45° 带），
    这条锁死两边不再各走各的。"""
    natal = NatalChartCalculator()
    for tenth_degree in range(0, 3600):
        diff = tenth_degree / 10.0
        assert (sky_now.moon_phase(0.0, diff)["phase_name"]
                == natal.calculate_moon_phase(0.0, diff)["phase_name"]), diff


def test_sky_at_reports_when_the_current_phase_became_exact():
    """exact_at 是当前阶段的起点（上一次 45° 整数倍的精确日月相位）。
    2026-07-29 22:35 CST 的精确满月，往后数小时仍是同一个阶段起点。"""
    jd = swe.julday(2026, 8, 2, 0.0)  # 2026-08-02 00:00 UT，日月角约 219°
    phase = sky_now.sky_at(jd)["moon_phase"]
    assert phase["phase_name"] == "满月"
    assert phase["exact_at"].startswith("2026-07-29T14:35")
    assert phase["hours_since_exact"] == pytest.approx(81.4, abs=0.2)


def test_sky_at_reports_the_next_phase_switch_with_target_phase():
    """换段预告的事实层：下一次 45° 精确相位的时刻 + 切过去是哪个阶段。
    2026-08-02 11:46:30Z（19:46 CST）日月拉开 225°，满月转亏凸月。"""
    jd = swe.julday(2026, 8, 2, 0.0)
    phase = sky_now.sky_at(jd)["moon_phase"]
    assert phase["phase_name"] == "满月"
    assert phase["next_phase_name"] == "亏凸月"
    assert phase["next_at"].startswith("2026-08-02T11:46")
    assert phase["hours_to_next"] == pytest.approx(11.8, abs=0.2)


def test_next_phase_name_wraps_from_balsamic_back_to_new_moon():
    """残月（第 8 段）的下一段是新月，不能越界取到第 9 个名字。"""
    jd = swe.julday(2026, 8, 12, 0.0)  # 新月前，日月角约 340°
    phase = sky_now.sky_at(jd)["moon_phase"]
    assert phase["phase_name"] == "残月"
    assert phase["next_phase_name"] == "新月"
    assert phase["hours_to_next"] > 0


def test_phase_switch_lookahead_never_returns_a_past_moment():
    """前瞻窗只往后找：hours_to_next 恒为正，且 next_at 晚于 exact_at。"""
    for day in (1, 6, 11, 16, 21, 26):
        phase = sky_now.sky_at(swe.julday(2026, 8, day, 6.0))["moon_phase"]
        assert phase["hours_to_next"] > 0, day
        assert phase["next_at"] > phase["exact_at"], day


def test_chiron_is_in_the_aspect_tables_but_not_voc_or_stations():
    """凯龙补进相位口径（本命盘一直算，天象板块此前漏了）；月空亡仍是九大行星
    的主流口径，逆行/转向表也不动——补相位不等于顺手改另外两套判定。"""
    assert swe.CHIRON in sky_now._PLANET_ASPECT_BODIES
    assert swe.CHIRON in sky_now._ACTIVE_ASPECT_BODIES
    assert swe.CHIRON not in sky_now._VOC_BODIES
    assert swe.CHIRON not in sky_now._MOTION_BODIES
    assert sky_now._PLANET_KEY[swe.CHIRON] == "chiron"
    assert sky_now._PLANET_CN[swe.CHIRON] == "凯龙星"


def test_chiron_aspects_use_the_strict_three_degree_orb():
    """凯龙体量小走得慢，用行星那套 6–8° 会让它长期霸榜；一律收到 3°。"""
    jd = swe.julday(2026, 8, 5, 0.0)
    rows = sky_now._active_planet_aspects(jd)
    chiron_rows = [r for r in rows if "chiron" in (r["p1"], r["p2"])]
    assert chiron_rows, "2026-08-05 有月亮合凯龙"
    for row in chiron_rows:
        assert row["orb_deg"] <= sky_now._CHIRON_ORB, row


def test_sky_at_exposes_transit_patterns():
    """格局块的数据源；判定逻辑本身在 tests/test_transit_patterns.py。"""
    payload = sky_now.sky_at(swe.julday(2026, 8, 11, 0.0))
    assert isinstance(payload["patterns"], list)
    assert payload["patterns"], "2026-08-11 天上有风筝"
    kite = [r for r in payload["patterns"] if r["kind"] == "kite"]
    assert kite and len(kite[0]["points"]) == 4


def test_current_sky_recomputes_every_call():
    """实时天象：不做进程内缓存——即使两次调用落在同一分钟内，也必须各自
    重新计算、返回不同 payload 对象，时间戳跟着走。"""
    now = 1_800_000_000.0  # 固定时刻，避免依赖系统时钟
    first = sky_now.current_sky(now)
    second = sky_now.current_sky(now + 30)  # 同一分钟桶内也必须重算
    assert first is not second
    assert first["timestamp"] != second["timestamp"]
    third = sky_now.current_sky(now + 300)
    assert third["timestamp"] != first["timestamp"]
    assert third["moon_phase"]["phase_name"] in sky_now.PHASE_NAMES






# ── Phase 0：月座 / 换座 / 月空亡（v2 架构重设计方案 §3.4）──────────────────


def test_moon_sign_and_ingress_known_epoch():
    """固定 JD 2451545.0（2000-01-01 12:00 UT）：月亮在天蝎座，即将换入射手座。"""
    payload = sky_now.sky_at(2451545.0)
    assert payload["moon"]["sign_cn"] == "天蝎座"
    assert payload["moon"]["glyph"] == "♏"
    assert payload["moon"]["deg_in_sign"] == pytest.approx(13.32, abs=0.01)
    assert payload["sun"]["sign_cn"] == "摩羯座"
    assert payload["ingress"]["next_sign_cn"] == "射手座"


def test_ingress_time_matches_independent_swisseph_crossing():
    """换座时刻不是自证——独立用 swe.calc_ut 在报告的时刻直接算月亮黄经，须落在 30° 边界上。"""
    payload = sky_now.sky_at(2451545.0)
    at = payload["ingress"]["at"]
    y, m, d = int(at[0:4]), int(at[5:7]), int(at[8:10])
    hh, mm, ss = int(at[11:13]), int(at[14:16]), int(at[17:19])
    jd = swe.julday(y, m, d, hh + mm / 60.0 + ss / 3600.0)
    xx, _ = swe.calc_ut(jd, swe.MOON, swe.FLG_SWIEPH)
    assert xx[0] % 30.0 < 0.01 or xx[0] % 30.0 > 29.99


def test_voc_not_yet_active_before_last_aspect():
    """参照时刻早于最后一个主相位 → 尚未空亡，start 在 now 之后。"""
    payload = sky_now.sky_at(2451545.0)
    voc = payload["voc"]
    assert voc["active"] is False
    assert voc["start"] > "2000-01-01T12:00:00Z"
    assert voc["start"] < voc["end"] == payload["ingress"]["at"]


def test_voc_active_between_last_aspect_and_ingress():
    """参照时刻落在 [start, end) 之间 → 空亡中。"""
    payload = sky_now.sky_at(2451546.333)
    voc = payload["voc"]
    assert voc["active"] is True
    assert voc["start"] < "2000-01-02T20:00:00Z" < voc["end"]


def test_voc_resets_after_ingress_into_new_sign():
    """跨过换座点后，月亮进入下一星座，voc 窗口整体重算（不是上一窗口的残留）。"""
    payload = sky_now.sky_at(2451546.40)
    assert payload["moon"]["sign_cn"] == "射手座"
    assert payload["voc"]["active"] is False
    assert payload["voc"]["end"] == payload["ingress"]["at"]


# ── 今日月亮相位列表（自然日，北京时间）────────────────────────────────────


def test_moon_aspects_today_stays_within_beijing_calendar_day():
    """JD 2451545.0 = 2000-01-01 12:00 UT，北京时间落在同一天(01-01 20:00)。
    自然日边界 = 北京 01-01 00:00~24:00，换算 UTC 应为
    [1999-12-31T16:00:00Z, 2000-01-01T16:00:00Z)——独立算一遍边界，不是
    自证；所有事件时间戳必须落在这个区间内。"""
    payload = sky_now.sky_at(2451545.0)
    events = payload["moon_aspects_today"]
    assert isinstance(events, list)
    for ev in events:
        assert "1999-12-31T16:00:00Z" <= ev["at"] < "2000-01-01T16:00:00Z"
        assert ev["planet_cn"] in sky_now._PLANET_CN.values()
        assert ev["aspect_cn"] in set(sky_now._ASPECT_CN.values())
    ats = [ev["at"] for ev in events]
    assert ats == sorted(ats)  # 按时间升序


def test_planet_aspects_today_are_exact_unique_non_lunar_pairs():
    """2026-01-01 北京日有水星四分海王星：独立用 Swiss Ephemeris 回算角距，
    同时锁住无月亮、无交换重复与北京自然日边界。"""
    payload = sky_now.sky_at(swe.julday(2026, 1, 1, 4.0))
    events = payload["planet_aspects_today"]
    assert events
    seen = set()
    for ev in events:
        assert ev["p1"] != "moon" and ev["p2"] != "moon"
        assert "2025-12-31T16:00:00Z" <= ev["at"] < "2026-01-01T16:00:00Z"
        pair = frozenset((ev["p1"], ev["p2"]))
        identity = (pair, ev["angle"], ev["at"])
        assert identity not in seen
        seen.add(identity)
        y, m, d = map(int, ev["at"][:10].split("-"))
        hh, mm, ss = map(int, ev["at"][11:19].split(":"))
        jd = swe.julday(y, m, d, hh + mm / 60 + ss / 3600)
        p1 = next(pid for pid, key in sky_now._PLANET_KEY.items() if key == ev["p1"])
        p2 = next(pid for pid, key in sky_now._PLANET_KEY.items() if key == ev["p2"])
        lon1 = swe.calc_ut(jd, p1, swe.FLG_SWIEPH)[0][0]
        lon2 = swe.calc_ut(jd, p2, swe.FLG_SWIEPH)[0][0]
        sep = abs((lon2 - lon1 + 180) % 360 - 180)
        assert sep == pytest.approx(ev["angle"], abs=0.002)


def test_station_event_is_real_speed_zero_with_direction():
    """2026-02-04 北京日天王星转顺；在报告时刻独立回算速度应接近零，稍后为正。"""
    payload = sky_now.sky_at(swe.julday(2026, 2, 4, 4.0))
    event = next(ev for ev in payload["stations_today"] if ev["planet"] == "uranus")
    assert event["direction"] == "direct"
    y, m, d = map(int, event["at"][:10].split("-"))
    hh, mm, ss = map(int, event["at"][11:19].split(":"))
    jd = swe.julday(y, m, d, hh + mm / 60 + ss / 3600)
    speed = swe.calc_ut(jd, swe.URANUS, swe.FLG_SWIEPH | swe.FLG_SPEED)[0][3]
    after = swe.calc_ut(jd + 0.01, swe.URANUS, swe.FLG_SWIEPH | swe.FLG_SPEED)[0][3]
    assert abs(speed) < 1e-6
    assert after > 0


def test_current_retrogrades_include_position_and_next_direct_station():
    payload = sky_now.sky_at(swe.julday(2026, 7, 26, 4.0))
    retrogrades = payload["retrograde_planets"]
    assert retrogrades
    for item in retrogrades:
        assert item["speed"] < 0
        assert 0 <= item["longitude"] < 360
        assert item["next_station"]["direction"] == "direct"
        assert item["next_station"]["at"] > "2026-07-26T04:00:00Z"


def test_voc_window_covers_entire_sign_when_no_aspect_found(monkeypatch):
    """`last_exact_before` 返回 None（罕见：整段星座内无任何主相位）→ 空亡覆盖整个星座在留时间。"""
    monkeypatch.setattr(sky_now, "last_exact_before", lambda *a, **k: None)
    payload = sky_now.sky_at(2451545.0)
    voc = payload["voc"]
    assert voc["active"] is True
    assert voc["end"] == payload["ingress"]["at"]


# ── 2026-07-30：行星区口径与月亮区对齐（planet_aspects_active）────────────
# 本页月亮区用八分法「相位带」模型（满月带宽 45°，横跨近 4 天，不要求精确），
# 行星区却只收「精确根落在今天窗口内」的相位——同一页两套模型。真实后果：
# 2026-07-30 太阳合木星 0.48°（比月亮区门槛紧一百倍），因精确时刻在前一晚
# 20:18（北京）而整个行星区显示"今日暂无"。planet_aspects_active 补的是
# 「此刻天上正挂着什么」，与 planet_aspects_today「今天几点有事发生」互补。
# NLM 核验：Hand Rule 2 说行运不存在 orb of influence，但 Rule 3 自己用
# "average orb approaches zero"；容许度只用于决定收录什么，不断言影响期。

_FIXED_JD = 2461251.6666666665  # 2026-07-30 04:00 UTC（北京 12:00）


def _active(jd=_FIXED_JD):
    return sky_now.sky_at(jd, timestamp="2026-07-30T04:00:00Z")["planet_aspects_active"]


def test_planet_broadcast_adds_quincunx_without_changing_voc_aspects():
    """行星播报扩展梅花相位，但月空亡仍严格只看托勒密五主相位。"""
    assert 150.0 in sky_now._PLANET_ASPECTS_WITH_MIRRORS
    assert 210.0 in sky_now._PLANET_ASPECTS_WITH_MIRRORS
    assert 150.0 not in sky_now._VOC_ASPECTS
    assert 210.0 not in sky_now._VOC_ASPECTS
    assert sky_now._ASPECT_CN[150.0] == "梅花相位"
    assert sky_now._ASPECT_CN[210.0] == "梅花相位"


def test_active_aspects_emit_quincunx_with_three_degree_orb(monkeypatch):
    """150°±3° 的对子进入 active 契约，并保留统一的 canonical angle=150。"""
    longitudes = {
        swe.MOON: 312.0, swe.SUN: 0.0, swe.MERCURY: 150.0, swe.VENUS: 34.0, swe.MARS: 75.0,
        swe.JUPITER: 112.0, swe.SATURN: 198.0, swe.URANUS: 246.0,
        swe.NEPTUNE: 278.0, swe.PLUTO: 325.0,
        # 凯龙进了 active 相位表（见 test_chiron_is_in_the_aspect_tables_...），
        # 这里给一个不与上面任何一颗成主相位的位置，免得给本用例引入无关行。
        swe.CHIRON: 17.0,
    }
    monkeypatch.setattr(
        sky_now.transit_engine, "body_position",
        lambda body, _jd: (longitudes[body], 0.0),
    )
    monkeypatch.setattr(sky_now, "_nearest_exact_jd", lambda *_args: 2451545.0)

    rows = sky_now._active_planet_aspects(2451545.0)
    row = next(r for r in rows if {r["p1"], r["p2"]} == {"sun", "mercury"})
    assert row["angle"] == 150.0
    assert row["aspect_cn"] == "梅花相位"
    assert row["orb_deg"] == 0.0
    assert row["tier"] == "event"


def test_august_first_moon_jupiter_quincunx_is_in_active_and_today_contracts():
    """用户指出的真实回归：2026-08-01 月木约 150.28°，两条月亮链都必须返回。"""
    jd = swe.julday(2026, 8, 1, 1.0)
    payload = sky_now.sky_at(jd, timestamp="2026-08-01T01:00:00Z")

    active = [r for r in payload["planet_aspects_active"]
              if {r["p1"], r["p2"]} == {"moon", "jupiter"}]
    assert len(active) == 1
    assert active[0]["angle"] == 150.0
    assert active[0]["aspect_cn"] == "梅花相位"
    assert active[0]["orb_deg"] < 0.3
    assert active[0]["exact_at"] == "2026-08-01T01:32:30Z"

    today = [r for r in payload["moon_aspects_today"] if r["planet_cn"] == "木星"]
    assert any(r["aspect_cn"] == "梅花相位" for r in today)


def test_planet_today_quincunx_payload_folds_210_to_150(monkeypatch):
    """求根器命中镜像 210° 时，API 仍返回前端统一使用的 angle=150。"""
    monkeypatch.setattr(
        sky_now.transit_engine, "body_position",
        lambda body, _jd: ({swe.SUN: 0.0, swe.MERCURY: 210.0}[body], 0.0),
    )
    row = sky_now._planet_aspect_payload(2451545.0, swe.SUN, swe.MERCURY, 210.0)
    assert row["angle"] == 150.0
    assert row["aspect_cn"] == "梅花相位"


def test_active_aspects_surface_tight_aspect_whose_exact_moment_was_yesterday():
    """核心回归：日木 0.48° 必须出现，且带上前一日的精确时刻。"""
    rows = [r for r in _active() if {r["p1"], r["p2"]} == {"sun", "jupiter"}]
    assert len(rows) == 1, "太阳合木星应恰好出现一次"
    row = rows[0]
    assert row["angle"] == 0.0 and row["aspect_cn"] == "合相"
    assert row["orb_deg"] < 1.0
    assert row["exact_at"].startswith("2026-07-29"), "精确时刻在前一天，仍须报出"
    assert row["applying"] is False, "已过精确，应为出相"


def test_active_aspects_find_exact_moment_for_mirror_angles():
    """镜像角回归：六分/四分/三分的精确时刻落在 60 还是 300 取决于谁领先，
    只传一半会系统性漏掉约 3/8（transit_utils 的注释专门警告过）。初版只传
    (angle,)，导致海王六合冥王 0.06° 这种几乎正精确的对子都报不出精确时刻。"""
    rows = [r for r in _active() if r["angle"] in (60.0, 90.0, 120.0)]
    assert rows, "应有六分/四分/三分相在容许度内"
    tight = [r for r in rows if r["orb_deg"] <= 3.0 and r["exact_at"] is None]
    assert not tight, f"紧密的镜像角相位必须查到精确时刻，漏了: {tight}"


def test_active_aspect_orbs_match_natal_page_convention():
    """容许度与 services/calculator.py::_phase_defs 同口径，不另立一套——
    同一相位在本命页与天象页给出不同判断，比取值出入更糟。"""
    assert sky_now._ACTIVE_ORB_BY_ANGLE == {
        0.0: 8.0, 60.0: 6.0, 90.0: 7.0, 120.0: 8.0, 150.0: 3.0, 180.0: 8.0,
    }
    for row in _active():
        assert row["orb_deg"] <= sky_now._ACTIVE_ORB_BY_ANGLE[row["angle"]]


def test_active_aspects_tag_speed_tier_for_frontend_routing():
    """含内行星的对子几天走完容许度=event；纯外行星对子可持续数月=background。
    后端只打标，不替前端决定展示位置。"""
    rows = _active()
    by_pair = {frozenset((r["p1"], r["p2"])): r["tier"] for r in rows}
    assert by_pair[frozenset(("sun", "jupiter"))] == "event"
    assert by_pair[frozenset(("neptune", "pluto"))] == "background"
    assert all(r["tier"] in ("event", "background") for r in rows)


def test_active_aspects_sorted_tightest_first():
    rows = _active()
    assert rows == sorted(rows, key=lambda r: (r["orb_deg"], r["tier"] != "event"))


def test_active_aspects_allow_none_exact_when_retrograde_loop_parks_the_orb():
    """水星逆行环（2026-06-30 转逆 / 07-24 转顺）把它停在四分土星附近，
    精确四分在 2026-06-10、远在 ±20 天搜索窗外 → exact_at=None 是正确结果，
    不是漏算；前端此时只显示当前角距。"""
    rows = [r for r in _active()
            if {r["p1"], r["p2"]} == {"mercury", "saturn"} and r["angle"] == 90.0]
    assert len(rows) == 1
    assert rows[0]["exact_at"] is None
    assert rows[0]["orb_deg"] <= 7.0


def test_planet_aspects_today_still_exact_only_and_unchanged():
    """新增层不得污染原有「今日精确成相」语义：该日无精确成相，仍应为空。"""
    payload = sky_now.sky_at(_FIXED_JD, timestamp="2026-07-30T04:00:00Z")
    assert payload["planet_aspects_today"] == []
    assert payload["planet_aspects_active"], "但当前生效相位不应为空"


# ── 月亮栏专属读数：月龄 / 朔望 / 距离 / 日月食 ──────────────────────────
# 这一组只描述月亮自身的周期，跟行星间相位无关——月相栏与天象盘的分工边界。


def test_lunation_reports_moon_age_from_actual_new_moon_not_average():
    """月龄必须来自求根得到的精确朔时刻，不能用平均朔望月估算。

    2026-07-30 04:00 UTC 的上一次朔是 2026-07-14 09:43 UTC，
    月龄 = 两者之差 ≈ 15.76 天。若改成 29.53 平均值推算会漂移半天以上。
    """
    lunation = sky_now.sky_at(_FIXED_JD)["lunation"]
    assert lunation["last_new_moon_at"] == "2026-07-14T09:43:37Z"
    assert lunation["moon_age_days"] == pytest.approx(15.761, abs=0.01)
    # 本轮实际朔望月长度与平均值不同，这个差异本身要能被读出来
    assert lunation["lunation_length_days"] == pytest.approx(29.329, abs=0.01)
    assert lunation["mean_synodic_month_days"] == sky_now._SYNODIC_MONTH_DAYS
    assert lunation["lunation_length_days"] != lunation["mean_synodic_month_days"]


def test_lunation_reports_both_sides_of_full_moon():
    """刚过满月时「下次满月」在 29 天后，必须同时给出刚过去的那次。

    2026-07-30 04:00 UTC 距 07-29 14:35 的满月只过了 13 小时，
    但下一次满月要等到 08-28。只报未来会让用户以为满月很遥远。
    """
    lunation = sky_now.sky_at(_FIXED_JD)["lunation"]
    # 断言到分钟即可：求根到秒级收敛，但秒位会随采样步长的实现细节微动
    assert lunation["last_full_moon_at"].startswith("2026-07-29T14:35")
    assert lunation["days_since_last_full_moon"] == pytest.approx(0.56, abs=0.02)
    assert lunation["days_to_next_full_moon"] == pytest.approx(29.01, abs=0.02)
    # 两侧都在，展示层才能挑更近的那个说
    assert lunation["days_since_last_full_moon"] < lunation["days_to_next_full_moon"]


def test_moon_distance_matches_swisseph_and_stays_in_orbital_range():
    dist = sky_now.sky_at(_FIXED_JD)["moon_distance"]
    expected_km = swe.calc_ut(_FIXED_JD, swe.MOON, swe.FLG_SWIEPH)[0][2] * sky_now._AU_KM
    assert dist["distance_km"] == round(expected_km)
    # 近地点约 356,500 km、远地点约 406,700 km，任何时刻都必须落在这个区间
    assert 355000 <= dist["distance_km"] <= 408000
    # 视直径随距离在 29–34 角分之间变化
    assert 28.0 <= dist["apparent_diameter_arcmin"] <= 35.0
    # 照明比例与 moon_phase 同源，不能出现两套数
    phase = sky_now.sky_at(_FIXED_JD)["moon_phase"]
    assert dist["illuminated_fraction"] * 100 == pytest.approx(
        phase["illumination_pct"], abs=0.01,
    )


def test_eclipse_reports_nearest_past_and_future_with_type():
    """日月食是朔望的特例，归月相栏。只报食别/时刻/黄道位置，不解释影响。"""
    eclipse = sky_now.sky_at(_FIXED_JD)["eclipse"]
    assert eclipse["next"]["kind_cn"] == "日食"
    assert eclipse["next"]["type_cn"] == "日全食"
    assert eclipse["next"]["at"] == "2026-08-12T17:45:59Z"
    assert eclipse["next"]["sun"]["sign_cn"] == "狮子座"
    # recent 在过去、next 在未来，符号不能弄反
    assert eclipse["recent"]["days_from_now"] < 0
    assert eclipse["next"]["days_from_now"] > 0


def test_eclipse_coincides_with_the_lunation_it_belongs_to():
    """食必然发生在朔或望：2026-08-28 的月偏食与当天满月应当几乎同时。

    两条独立求根路径（食求根 vs 日月 180° 求根）互相印证；差超过一小时
    说明其中一条算错了。
    """
    jd = swe.julday(2026, 8, 20, 4.0)
    payload = sky_now.sky_at(jd)
    eclipse_at = payload["eclipse"]["next"]
    assert eclipse_at["kind_cn"] == "月食"
    full_moon_jd = sky_now._lunation_exact(jd, 180.0, backward=False)
    eclipse_jd = swe.julday(2026, 8, 28, 4.0) + (
        eclipse_at["days_from_now"] - (swe.julday(2026, 8, 28, 4.0) - jd)
    )
    assert abs(eclipse_jd - full_moon_jd) * 24.0 < 1.0


def test_moon_column_carries_no_planet_to_planet_readings():
    """月相栏的新增字段只描述月亮自身，不得混入行星间关系。

    行星相位/格局/逆行归天象盘；这条断言防止以后有人图省事把它们
    塞回这三个字段里。
    """
    payload = sky_now.sky_at(_FIXED_JD)
    blob = json.dumps(
        {k: payload[k] for k in ("lunation", "moon_distance", "eclipse")},
        ensure_ascii=False,
    )
    for planet in ("水星", "金星", "火星", "木星", "土星", "天王星", "海王星", "冥王星"):
        assert planet not in blob
