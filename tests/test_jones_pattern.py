import json
import math

import pytest

from engine.jones import (
    PLANET_NAMES_EN,
    PLANET_NAMES_ZH,
    PatternResult,
    SELLAR_OPPOSITION_ORB,
    _check_bucket,
    _check_conjunction_handle,
    _find_pair_names,
    _sellar_focus,
    detect_with_variants,
    result_to_dict,
)
from services import jones_pattern
from services.jones_pattern_guide import PATTERN_GUIDES, ROLE_GUIDES


def _planets(longitudes):
    return {
        planet_id: {"longitude": longitude}
        for (planet_id, _name, _glyph), longitude
        in zip(jones_pattern.PLANETS, longitudes)
    }


def test_bundle_contract_is_pattern_scoped_and_json_safe():
    result = jones_pattern.calculate_jones_pattern(
        _planets([10, 18, 28, 40, 50, 58, 65, 72, 80, 88])
    )
    assert result["engine_version"] == jones_pattern.ENGINE_VERSION
    assert result["pattern_en"] == "Bundle"
    assert result["family_en"] == "Bundle"
    assert result["state"] == "standard"
    assert result["state_label"] == "标准格局"
    assert len(result["distribution"]) == 10
    assert "details" not in result
    assert "reading" not in result
    assert result["guide"]["structure"]
    assert result["guide"]["dynamics"]
    assert result["guide"]["native_state"]
    assert result["guide"]["observation"]
    assert [role["planet_name"] for role in result["key_roles"]] == ["太阳", "冥王星"]
    assert {role["role_label"] for role in result["key_roles"]} == {"星群边界"}
    assert all("role_desc" not in role for role in result["key_roles"])
    json.dumps(result, allow_nan=False)


def test_bowl_geometry_is_exposed_from_migrated_engine_without_reading_copy():
    result = jones_pattern.calculate_jones_pattern(
        _planets([0, 20, 40, 60, 80, 100, 120, 140, 160, 180])
    )
    assert result["pattern_en"] == "Bowl"
    assert result["midpoint_bowl"] == {"long": 270.0}
    assert set(result["midpoint_bowl"]) == {"long"}
    # 碗底点：Mars 落在 90°（占据半球重心）10° 内 → 承重墙锚定，但距离 10°
    # 超过 3° 严格容许度，不算「碗底锚点」。
    assert result["cog_bowl"] == {"long": 90.0, "planet_name": "火星", "is_anchor": False}


def test_bucket_midpoint_uses_nine_planet_bowl_boundaries_from_engine():
    """提桶型的碗底点(cog_bowl)由把手所在虚空中点回填补算——不是永远 None。

    此前(修复前)Bucket 检测层没有 _scan_cog 补算步骤，本测试断言
    `cog_bowl is None` 把这个缺口当成了"设计行为"锁死；跟香港服务器上
    natal-chart 项目已完工的琼斯格局引擎对拍后确认是真缺口，已补齐。
    """
    result = jones_pattern.calculate_jones_pattern(
        _planets([0, 20, 45, 70, 95, 120, 145, 170, 195, 285])
    )
    assert result["pattern_en"] == "Bucket"
    assert result["midpoint_bowl"] == {"long": 277.5}
    # 虚空中点(277.5°)正对面 = 97.5°，Mars(95°) 距离 2.5° ≤ 3° 严格容许度 → 碗底锚点。
    assert result["cog_bowl"] == {"long": 97.5, "planet_name": "火星", "is_anchor": True}


def test_locomotive_midpoint_is_exposed_only_for_locomotive():
    result = jones_pattern.calculate_jones_pattern(
        _planets([0, 30, 60, 90, 110, 130, 160, 190, 220, 250])
    )
    assert result["pattern_en"] == "Locomotive"
    assert result["midpoint_loco"] == {"long": 305.0}
    assert result["midpoint_bowl"] is None
    assert result["midpoint_bundle"] is None


def test_bundle_midpoint_is_exposed_only_for_bundle():
    result = jones_pattern.calculate_jones_pattern(
        _planets([10, 18, 28, 40, 50, 58, 65, 72, 80, 88])
    )
    assert result["pattern_en"] == "Bundle"
    assert result["midpoint_bundle"] == {"long": 49.0}
    assert result["midpoint_bowl"] is None
    assert result["midpoint_loco"] is None


def test_bundle_does_not_take_charts_whose_span_exceeds_a_defining_trine():
    """跨度超过 confining trine 的盘不得判丛聚——琼斯本人撤回过这类判例。

    《The Guide to Horoscope Interpretation》(1941) 曾把 Pierre Laval 当作丛聚范例
    （一颗星「passed outside the confining trine by a little over a sign」），但
    《Essentials of Astrological Analysis》(1960) 明确改判：
      "The horoscopes of Jeff Davis, Pierre Laval and William McKinley selected as
       examples of the BUNDLE TEMPERAMENT are reclassified as BOWL because the
       segments of the zodiac occupied by the PLANETS exceed what can be embraced
       in a defining TRINE."
    Sellar《Chart Shapes》第 4 章同样以 130° 划界。此前代码有一条以 Laval 为依据的
    「宽松丛聚」通道(max_gap ≥200° + 第二段 ≥55°)，会把跨度 150-160° 的盘判成丛聚，
    且不标交界；该通道已于 2026-09-28 下线，本用例守住它不被重新引入。
    """
    # 9 星压在 95° 内 + 1 星落在 150°（第二段空白 55°）——正是旧通道的形状
    result = jones_pattern.calculate_jones_pattern(
        _planets([0, 11.875, 23.75, 35.625, 47.5, 59.375, 71.25, 83.125, 95, 150])
    )
    assert result["span_deg"] == 150.0
    assert result["pattern_en"] != "Bundle"
    assert result["pattern_en"] == "Bowl"

    # 严格门槛本身不受影响：跨度 130°（max_gap=230°）仍是丛聚，
    # 这一侧有琼斯未曾改判的 Eduard Benes 作锚。
    still_bundle = jones_pattern.calculate_jones_pattern(
        _planets([0, 14.4, 28.8, 43.2, 57.6, 72, 86.4, 100.8, 115.2, 129.6])
    )
    assert still_bundle["pattern_en"] == "Bundle"


def test_public_guides_cover_every_supported_pattern_and_stay_pattern_scoped():
    assert set(PATTERN_GUIDES) == set(jones_pattern.FAMILY_BY_PATTERN)
    assert all(set(guide) == {"structure", "dynamics", "native_state", "observation"}
               for guide in PATTERN_GUIDES.values())
    forbidden = ("你", "性格", "人格", "命运", "人生", "使命", "职业", "心理", "能量")
    public_copy = " ".join(
        [text for guide in PATTERN_GUIDES.values() for text in guide.values()]
        + [text for guide in ROLE_GUIDES.values() for text in guide]
    )
    assert not any(word in public_copy for word in forbidden)
    bowl = PATTERN_GUIDES["Bowl"]
    assert "补足需求" in bowl["dynamics"]
    assert "持续投入" in bowl["dynamics"]
    assert "很难停下" in bowl["native_state"]
    assert "不同于火车头型的任务推进" in bowl["native_state"]


def test_named_variant_maps_to_family_and_variant_state():
    result = jones_pattern.calculate_jones_pattern(
        _planets([10, 20, 35, 50, 65, 75, 82, 88, 92, 265])
    )
    assert result["pattern_en"] == "Fanhandle"
    assert result["family_en"] == "Bundle"
    assert result["variant_en"] == "Fanhandle"
    assert result["state"] == "variant"
    assert result["state_label"] == "变形格局"


def test_grace_kelly_two_eight_groups_remain_seesaw():
    # 案例库盘：Augurine 与 AstroMansion 均判 Seesaw。两组为 2:8，
    # 两段空白 83.75°/66.15°；八星主群跨度约 194°，不足以成为双把手的碗。
    result = jones_pattern.calculate_jones_pattern(_planets([
        229.57, 351.85, 220.70, 208.85, 235.63,
        74.09, 268.10, 7.95, 153.42, 109.53,
    ]))
    assert result["pattern_en"] == "See-Saw"
    assert result["family_en"] == "See-Saw"


def test_dua_lipa_multiple_internal_gaps_prevent_soft_locomotive():
    # 案例库盘：两家公开计算器均判 Splay。除了约 107° 主空白，
    # 仍有约 56°/48°/47° 三段断裂，不能视作连续的火车头弧。
    result = jones_pattern.calculate_jones_pattern(_planets([
        148.42, 100.39, 169.85, 148.69, 199.40,
        246.09, 353.07, 297.33, 293.27, 237.87,
    ]))
    assert result["pattern_en"] == "Splay"
    assert result["family_en"] == "Splay"


def test_two_group_splash_boundary_matches_both_external_calculators():
    # 1935-01-14 12:00 伦敦：两段主空白 64.4°/61.1°，第三段 59.6°；
    # Augurine 与 AstroMansion 均判 See-Saw，本地不应被 Splash 硬路由抢先截走。
    result = jones_pattern.calculate_jones_pattern(_planets([
        293.4062, 55.3738, 302.4278, 306.9674, 195.1916,
        228.9908, 326.3851, 27.5262, 164.3669, 115.0018,
    ]))
    assert result["pattern_en"] == "See-Saw"
    assert result["family_en"] == "See-Saw"


def test_theodore_roosevelt_wide_splash_stays_splash():
    # 罗斯福第三段空白仅 44.1°，与上面贴近 60° 的双群盘不同。
    result = jones_pattern.calculate_jones_pattern(_planets([
        213.992, 102.0869, 212.4106, 258.0214, 287.8219,
        81.0977, 131.6537, 62.5257, 352.4962, 36.6362,
    ]))
    assert result["pattern_en"] == "Splash"


def test_borderline_state_has_priority_over_variant(monkeypatch):
    mocked = PatternResult(
        pattern_en="Fanhandle",
        pattern_zh="扇柄型",
        confidence="moderate",
        max_gap=220,
        span=140,
        details="not exposed",
        extra={"parent_pattern": "Bundle", "borderline": True,
               "borderline_reasons": ["丛聚交界"]},
    )
    monkeypatch.setattr(jones_pattern, "detect_with_variants", lambda *args, **kwargs: mocked)
    result = jones_pattern.calculate_jones_pattern(_planets(range(0, 300, 30)))
    assert result["is_variant"] is True
    assert result["state"] == "borderline"
    assert result["state_label"] == "交界待观察"


@pytest.mark.parametrize("value", [None, "bad", math.nan, math.inf, -math.inf, True])
def test_untrusted_longitudes_are_rejected(value):
    planets = _planets(range(0, 300, 30))
    planets["sun"]["longitude"] = value
    with pytest.raises(ValueError, match="有限数字"):
        jones_pattern.calculate_jones_pattern(planets)


def test_equal_longitudes_keep_distinct_planet_identities():
    names = ["Sun", "Moon", "Mercury", "Venus", "Mars",
             "Jupiter", "Saturn", "Uranus", "Neptune", "Pluto"]
    longs = [10, 20, 30, 40, 80, 100, 120, 80, 200, 240]
    first, second, first_idx, second_idx = _find_pair_names(80, 80, longs, names)
    assert first_idx != second_idx
    assert {first, second} == {"Mars", "Uranus"}


def test_conjunction_handle_candidate_is_stable_after_rotation():
    original = [0, 5, 150, 168, 174, 184, 211, 229, 234, 289]
    identities = []
    for shift in (0, 30, 90, 179):
        rotated = [(value + shift) % 360 for value in original]
        candidate = _check_conjunction_handle(
            sorted(rotated), rotated, PLANET_NAMES_EN
        )
        assert candidate is not None
        identities.append(tuple(candidate["identity_indices"]))
    assert identities == [(0, 1)] * 4


# ── 2026-07-20 核检回归：琼斯几何字段半闭环 + 把手中点判定 ────────────────────

def test_second_seesaw_path_emits_group_axis():
    """See-Saw 有两条返回路径：硬路由(min群≥3)已算 group_axis，但接住 4:6/2:8
    漏网型的第二条路径此前漏算，约 5.5% 的跷跷板/沙漏输出缺重心轴。
    这里的 4:6（主空白 160°、次空白 65°）绕过硬路由(max_gap≥150 且次 gap<90)，
    落到第二条路径——必须也带 group_axis。"""
    longs = [0, 20, 40, 60, 220, 235, 250, 265, 280, 295]
    result = detect_with_variants(longs, planet_names=PLANET_NAMES_ZH)
    assert result.pattern_en == "See-Saw"
    assert result.extra.get("group_sizes") == [4, 6]
    ga = result.extra.get("group_axis")
    assert ga is not None, "第二条 See-Saw 路径必须生成 group_axis"
    assert ga["heavier"] == "b"          # 6 颗 > 4 颗
    assert 29 <= ga["center_a"] <= 31    # (0+20+40+60)/4 ≈ 30
    assert ga["heavier_pole_name"]       # 重心较重端边界星非空

    # DTO 顶层字段 + 关键行星动态说明也须随之出现（此前为 None/空）。
    dto = result_to_dict(result)
    assert dto.get("group_axis") is not None
    heavier_notes = [r.get("note", "") for r in dto["key_roles"]
                     if r.get("role_type", "").startswith("seesaw") and r.get("note")]
    assert any("份量更重" in n for n in heavier_notes)


def test_bucket_handle_centered_uses_midpoint_offset_not_distance_ratio():
    """把手"正落在中点"必须用真实中点角距(≤8°)判定，不能用两侧距离比 0.85——
    大空白下 0.85 比值可对应 >8° 偏差，会把没落中点的把手误标"正落在把手上"。
    构造 dist 比≈0.85 但中点偏差 9° 的提桶：旧规则→centered，正确应为 trailing。"""
    bowl = [round(i * 138 / 8, 3) for i in range(9)]   # 9 星碗，跨度 138°
    longs = bowl + [240.0]                              # 把手，虚空中点=249°，偏差 9°
    bk = _check_bucket(sorted(longs), longs, list(PLANET_NAMES_ZH))
    assert bk is not None
    ratio = min(bk["dist_left"], bk["dist_right"]) / max(bk["dist_left"], bk["dist_right"])
    assert ratio >= 0.85                               # 旧规则会误判 centered
    assert bk["handle_tilt"] == "trailing"             # 新规则按中点偏差正确判定


def test_bucket_handle_centered_when_truly_on_midpoint():
    """把手真落在虚空中点(偏差≤8°)时仍判 centered。"""
    bowl = [round(i * 138 / 8, 3) for i in range(9)]   # 虚空中点=249°
    longs = bowl + [249.0]
    bk = _check_bucket(sorted(longs), longs, list(PLANET_NAMES_ZH))
    assert bk is not None
    assert bk["handle_tilt"] == "centered"


# ── 碗型跨度上限的边界提示 + 虚点/碗底无锚定角色卡 ──────────────────────────
# 2026-09-28 原典复核后碗型上限从 span≤210° 收到 span≤185°（BOWL_THRESHOLD 150→175）：
#   Jones《Essentials of Astrological Analysis》碗型定义："found when the ten PLANETS
#   lie in a half of the circle or when if two of them are in OPPOSITION the others all
#   are found on one side of the line formed by the aspect."——半圆 180° 是本体，
#   原典允许碗口对分相附近的偏差；185° 是结合外部样本采用的工程阈值，
#   不是琼斯原文明确规定的截止线。
#   Sellar《Chart Shapes》第 4 章："within 180° of arc, maximum 190°"。
#   外部实测：AstroMansion span 183.8° 判 Bowl、185.8° 判 Locomotive（容差≈5°）。
# 因此原「碗型跨度上限交界」(span 贴着 194°) 已不可能触发并随之下线；贴着新上限的盘
# 由「碗/半球交界」接管，且两侧对称提示（碗↔火车头），这正是前端「可能是什么、去观察」
# 所依赖的那条。
#   Sellar 同章："The midpoint pertaining to the boundary planets...can be judged
#   by its sign and house."；Rudhyar《Person-Centered Astrology》："the mid-point
#   between the two ends of the opposition...may be considered the 'center of
#   gravity'"——虚点/重心点靠自身星座宫位独立成立，不需要行星合相才算数。

def test_bowl_near_ceiling_flags_borderline_with_locomotive_alternate():
    # span=184°（max_gap=176°，距 BOWL_THRESHOLD=175° 仅 1°）：仍判碗型，
    # 但必须标交界并给出另一种读法＝火车头型，附「还差多少度」。
    result = jones_pattern.calculate_jones_pattern(
        _planets([0, 15, 30, 50, 70, 90, 110, 130, 150, 184])
    )
    assert result["pattern_en"] == "Bowl"
    assert result["span_deg"] == 184.0
    assert result["state"] == "borderline"
    assert result["state_label"] == "交界待观察"
    assert "碗/半球交界" in result["borderline_reasons"]
    alts = {item["pattern_en"]: item for item in result["borderline_alternates"]}
    assert alts["Locomotive"]["pattern_zh"] == "火车头型"
    assert alts["Locomotive"]["measure_zh"] == "最大空白"
    assert alts["Locomotive"]["delta_deg"] == pytest.approx(1.0, abs=0.05)


def test_span_just_over_ceiling_becomes_locomotive_and_points_back_at_bowl():
    # span=186°（max_gap=174°）：越过上限 1°，改判火车头型；交界提示对称回指碗型。
    result = jones_pattern.calculate_jones_pattern(
        _planets([0, 15, 30, 50, 70, 90, 110, 130, 150, 186])
    )
    assert result["pattern_en"] == "Locomotive"
    assert result["state"] == "borderline"
    alts = {item["pattern_en"]: item for item in result["borderline_alternates"]}
    assert alts["Bowl"]["pattern_zh"] == "碗型"
    assert alts["Bowl"]["delta_deg"] == pytest.approx(1.0, abs=0.05)


def test_bowl_span_within_safe_zone_not_flagged_borderline():
    # span=180°（干净的半圆碗）：落在上限内 5°，交界窗口(±3°)够不着，不该标交界。
    result = jones_pattern.calculate_jones_pattern(
        _planets([0, 20, 40, 60, 80, 100, 120, 140, 160, 180])
    )
    assert result["pattern_en"] == "Bowl"
    assert result["state"] == "standard"
    assert result["borderline_reasons"] == []


def test_bowl_key_roles_expose_void_and_cog_point_without_planet_anchor():
    # 碗底(重心点)10° 内没有行星锚定时，此前整条从「关键位置」消失，只留在
    # 环形图图例里；虚点按定义永远不会有行星（否则空白半球就不空了），此前
    # 从未在 key_roles 里出现过。两者现在都必须靠自身经度独立成卡。
    result = jones_pattern.calculate_jones_pattern(
        _planets([0, 15, 30, 50, 70, 40, 110, 130, 150, 182])
    )
    assert result["pattern_en"] == "Bowl"
    assert result["cog_bowl"] == {"long": 91.0}    # 无 planet_name → 确认未锚定
    roles_by_type = {r["role_type"]: r for r in result["key_roles"]}
    assert "cog_bowl" not in roles_by_type          # 未锚定时不该出现"承重墙"行星卡
    assert roles_by_type["cog_bowl_point"]["planet_name"] == "碗底"
    assert roles_by_type["cog_bowl_point"]["longitude"] == 91.0
    assert roles_by_type["void_bowl"]["planet_name"] == "虚点"
    assert roles_by_type["void_bowl"]["longitude"] == 271.0


def test_bowl_key_roles_keep_anchored_cog_and_still_add_void_point():
    # 碗底有行星锚定时（既有行为）：继续走 cog_bowl(行星名) 角色卡，不重复
    # 生成 cog_bowl_point；虚点角色卡现在无条件补上，两者不冲突。
    result = jones_pattern.calculate_jones_pattern(
        _planets([0, 20, 40, 60, 80, 100, 120, 140, 160, 180])
    )
    roles_by_type = {r["role_type"]: r for r in result["key_roles"]}
    assert roles_by_type["cog_bowl"]["planet_name"] == "火星"
    assert "cog_bowl_point" not in roles_by_type
    assert roles_by_type["void_bowl"]["planet_name"] == "虚点"
    assert roles_by_type["void_bowl"]["longitude"] == 270.0


def test_bowl_cog_point_not_falsely_unanchored_when_dedup_hides_planet():
    # 自查发现的真 bug：碗底(cog_bowl)10° 内确实有行星，但这颗行星恰好和引导星
    # 是同一颗（去重命中，不重复出卡）——这种情况必须整条跳过，不能改口说"没有
    # 行星"而生成 cog_bowl_point("碗底")卡片，那是在撒谎。
    from engine.jones import PatternResult, _build_key_roles
    result = PatternResult(
        pattern_en="Bowl", pattern_zh="碗型", confidence="clear",
        max_gap=170, span=190, details="",
        extra={
            "leader": {"leader_name": "太阳", "leader_long": 100.0,
                       "tail_name": "月亮", "tail_long": 280.0},
            "cog_bowl": {"long": 101.0, "planet_name": "太阳",
                         "planet_long": 100.0, "dist": 1.0},
            "midpoint_bowl": {"long": 281.0},
        },
    )
    roles = _build_key_roles(result, planet_meta=None)
    role_types = {r["role_type"] for r in roles}
    assert "cog_bowl" not in role_types      # 太阳已由 leader_bowl 报过，去重不重复
    assert "cog_bowl_point" not in role_types  # 不能谎称"没有行星"
    assert role_types == {"leader_bowl", "tail_bowl", "void_bowl"}


# ── 2026-07-20：交界标记覆盖全部14格局（不改分类算法，只补齐边界标记）───────
# 用户指出：格局判定本有"标准/变形/交界"三态框架，但只有 9/14 格局接了交界
# 判定，展开/三脚架/合相把手/双把手/蝴蝶型完全零覆盖——不管这些盘的数值多贴近
# 改判红线，state 永远只会是"标准/变形"。以下用随机搜索挖出的真实样本固定为
# 用例（比手算球面几何可靠），逐条验证新增规则真的接上了，且全程复用代码里
# 已有的常数(HOURGLASS_MIN_GAP/CONJ_HANDLE_ORB/90°三脚架门槛)——不新造红线
# 数值，只新造"多近算贴着红线"的容差宽度，跟已有 4 条规则同一套风格。
# 另有 300000 张随机盘的分类前后对拍（本次未固化为自动化测试，见 PR 说明）：
# pattern_en 零变化，证明这批改动完全没碰分类算法本身，只动了边界旗标。

def test_splay_and_tripod_now_covered_by_ternary_quaternary_rule():
    # 此前白名单漏了 Splay/Tripod——s2(次大空白) 58-73° 判据其实也决定它们
    # 跟 See-Saw 的三/二分叉(n_sig==3 vs 2)，规则写了却只对 See-Saw 生效。
    r = jones_pattern.calculate_jones_pattern(_planets(
        [95.9278, 179.4315, 34.7985, 269.1185, 148.0719, 161.7821, 5.0517, 0.077, 209.0304, 335.5842]
    ))
    assert r["pattern_en"] == "Tripod"
    assert "三元/二四交界" in r["borderline_reasons"]
    assert r["state"] == "borderline"
    tripod_reins = [role for role in r["key_roles"] if role["role_type"] == "isolated_tripod"]
    assert len(tripod_reins) == 1
    assert tripod_reins[0]["role_label"] == "缰绳星"
    assert "三脚架型" in tripod_reins[0]["description"]
    assert "展开型" not in tripod_reins[0]["description"]

    r2 = jones_pattern.calculate_jones_pattern(_planets(
        [236.8324, 4.1074, 352.1263, 169.3962, 349.2697, 244.4915, 310.3586, 333.8027, 326.1763, 143.6668]
    ))
    assert r2["pattern_en"] == "Splay"
    assert "三元/二四交界" in r2["borderline_reasons"]


def test_seesaw_hourglass_boundary_now_covered():
    # HOURGLASS_MIN_GAP=90° 改判线：此前跟碗型194°是同一类漏洞——内部 confidence
    # 公式本就把 min(g1,g2) 90-100° 标 moderate，但从未传到前端。
    r = jones_pattern.calculate_jones_pattern(_planets(
        [83.2805, 343.3226, 316.3035, 232.4445, 146.8809, 281.993, 305.8176, 241.3436, 346.0315, 126.7021]
    ))
    assert r["pattern_en"] == "See-Saw"
    assert "沙漏交界" in r["borderline_reasons"]

    r2 = jones_pattern.calculate_jones_pattern(_planets(
        [8.948, 237.3021, 220.2277, 353.1963, 5.3401, 263.0665, 257.4156, 48.285, 259.5393, 55.563]
    ))
    assert r2["pattern_en"] == "Hourglass"
    assert "沙漏交界" in r2["borderline_reasons"]


def test_butterfly_tripod_ninety_degree_boundary_now_covered():
    # BUTTERFLY_MIN_GAP 与 TRIPOD_MIN_GAP 同为 90°，是同一条线：Splay 三段
    # 空白全部达标才升级为蝴蝶/三脚架，此前该线附近的盘完全没有交界提示。
    r = jones_pattern.calculate_jones_pattern(_planets(
        [82.9854, 277.952, 76.9383, 65.3598, 189.3358, 20.2388, 5.1912, 74.608, 169.306, 13.7712]
    ))
    assert r["pattern_en"] == "Butterfly"
    assert "蝴蝶/三脚架交界" in r["borderline_reasons"]


def test_conjhandle_twohandle_eight_degree_boundary_now_covered():
    # CONJ_HANDLE_ORB(合相把手上限) 与 TWO_HANDLE_MIN_SEP(双把手下限) 同为 8°，
    # 本是一条线的两侧定义，此前完全没有交界提示。
    r = jones_pattern.calculate_jones_pattern(_planets(
        [336.7838, 258.7658, 170.5486, 331.8622, 330.1752, 54.6655, 163.5419, 320.189, 341.5544, 256.9359]
    ))
    assert r["pattern_en"] == "ConjHandle"
    assert "合相/双把手交界" in r["borderline_reasons"]

    r2 = jones_pattern.calculate_jones_pattern(_planets(
        [170.593, 345.1172, 353.2493, 65.1288, 268.2263, 84.8909, 8.8919, 179.2904, 295.3118, 357.0264]
    ))
    assert r2["pattern_en"] == "TwoHandle"
    assert "合相/双把手交界" in r2["borderline_reasons"]


def test_two_eight_conjunction_handle_also_exposes_seesaw_reading():
    # 奥巴马公开出生盘的十大行星：土木相距 5.53°，两组规模 2:8，
    # 两侧空白 76.72° / 122.50°。主分类仍可取合相把手，不能称没有交界。
    result = jones_pattern.calculate_jones_pattern(_planets(
        [132.5479, 63.3574, 122.3316, 91.7894, 172.5767,
         300.8586, 295.3307, 145.2703, 218.6060, 156.9794]
    ))
    assert result["pattern_en"] == "ConjHandle"
    assert result["borderline"] is True
    assert "双星把手/跷跷板重叠" in result["borderline_reasons"]
    assert any(item["pattern_en"] == "See-Saw" and item["delta_deg"] is None
               for item in result["borderline_alternates"])


def test_assess_borderline_never_influences_pattern_classification():
    # 硬约束回归：_assess_borderline 只产出旗标，绝不能反过来改变 pattern_en。
    # 用同一批输入分别跑通过/不通过交界判定的两张盘，分类必须只取决于
    # detect_jones_pattern/_refine_to_variant，不受 borderline 判定影响。
    from engine.jones import detect_with_variants, PLANET_NAMES_ZH
    r = detect_with_variants(
        [8.948, 237.3021, 220.2277, 353.1963, 5.3401, 263.0665, 257.4156, 48.285, 259.5393, 55.563],
        planet_names=PLANET_NAMES_ZH,
    )
    assert r.pattern_en == "Hourglass"
    assert r.extra.get("borderline") is True
    # extra["parent_pattern"] 等分类相关字段不受 borderline 判定污染
    assert r.extra.get("parent_pattern") == "See-Saw"


# ── 2026-07-20：跷跷板/沙漏型无对分相时的 HFP 兜底（讨论后按推荐方案落地）──
# 用户发现：散落型有对分相时能正确标出核心整合行星，但没有对分相时就找不到
# 焦点，问其他格局有没有类似问题。查 NLM 后确认：
#   - 散落型本身"没有技巧"是 Jones 原文明确说的（"offers no preliminary
#     technique"），不是 bug，不需要强行补一个焦点星。
#   - 展开型已有三层兜底（孤立缰绳星→对分相→大三角），跟原典一致，没有缺口。
#   - 跷跷板/沙漏型只有对分相一层，没有对分相时 HFP 直接是 None——但 Jones
#     原文明确给了下一层："If no such emphasis is present, the life tends to
#     be significant at the side of the greater number of planets, or
#     sometimes where they are concentrated most closely"（Guide to
#     Horoscope Interpretation, p.91-92）。这层代码里其实已经算出来了
#     （group_axis.heavier_pole_name），只是没接进 high_focus_planet。

def test_seesaw_falls_back_to_heavier_pole_when_no_opposition():
    result = detect_with_variants(
        [15.1465, 26.1557, 67.6763, 80.3351, 83.9358,
         223.7439, 230.1347, 282.8697, 299.7511, 302.0278],
        planet_names=PLANET_NAMES_ZH,
    )
    assert result.pattern_en == "See-Saw"
    assert result.extra.get("sellar_focus") is None  # 真的没有对分相
    ga = result.extra.get("group_axis") or {}
    assert result.high_focus_planet == ga["heavier_pole_name"]
    assert result.high_focus_long is not None


def test_hourglass_falls_back_to_heavier_pole_when_no_opposition():
    result = detect_with_variants(
        [58.1993, 145.5487, 142.1283, 159.7882, 126.1842, 269.5339, 72.2717, 148.5567, 299.8471, 278.7343],
        planet_names=PLANET_NAMES_ZH,
    )
    assert result.pattern_en == "Hourglass"
    assert result.extra.get("sellar_focus") is None
    ga = result.extra.get("group_axis") or {}
    assert result.high_focus_planet == ga["heavier_pole_name"]


def test_seesaw_still_prefers_opposition_over_heavier_pole_when_both_exist():
    # 有对分相时优先级不能变——对分相仍然是第一顺位，重心兜底只在没有
    # 对分相时才生效。
    result = detect_with_variants(
        [0, 20, 40, 60, 220, 235, 250, 265, 280, 295],  # 已有测试验证过含对分相
        planet_names=PLANET_NAMES_ZH,
    )
    assert result.pattern_en == "See-Saw"
    sf = result.extra.get("sellar_focus")
    assert sf is not None
    assert result.high_focus_planet == sf["name"]


def test_sellar_core_opposition_uses_jones_ten_degree_orb_inclusively():
    assert SELLAR_OPPOSITION_ORB == 10.0
    focus = _sellar_focus([20.0, 190.0], ["Venus", "Jupiter"])
    assert focus == {
        "name": "Venus",
        "lon": 20.0,
        "opp_name": "Jupiter",
        "opp_lon": 190.0,
    }


def test_sellar_core_opposition_rejects_more_than_ten_degrees():
    assert _sellar_focus([20.0, 189.99], ["Venus", "Jupiter"]) is None


def test_sellar_core_opposition_includes_reported_venus_jupiter_case():
    # 金星白羊 19°24′、木星天秤 12°45′：夹角 173°21′，距精确对分 6°39′。
    focus = _sellar_focus([19.4, 192.75], ["Venus", "Jupiter"])
    assert focus is not None
    assert focus["name"] == "Venus"
    assert focus["opp_name"] == "Jupiter"


# ── 2026-07-28：把手族碗底承重墙「算了不显示」──────────────────────
# cog_bowl 的计算 Bowl 与把手族共用，但 _build_key_roles 此前只有 Bowl 分支
# 出角色卡——提桶族数据层有 {'planet_name':..,'is_anchor':True} 而 key_roles
# 里没有这张卡，用户永远看不到。NLM 核验 Sellar Ch.5 原文："especially if the
# handle is in opposition to a planet within the centre of the bowl. There is
# very definite ambition and single-mindedness."
# 覆盖三种 extra 来源路径：bucket（Bucket/Sling）/ two_handle / conj_handle。
# Fanhandle 与 Sling 共用 bucket 源+同一分支，不另造盘。

def _role_types(dto):
    return {r["role_type"] for r in dto["key_roles"]}


def test_bucket_cog_anchor_card_present_with_opposition_note():
    # 火星恰在碗底重心(80°)，把手冥王星恰在虚空中点(260°) → 承重墙卡 + 对分实心轴 note
    dto = jones_pattern.calculate_jones_pattern(
        _planets([0, 20, 40, 60, 80, 100, 120, 140, 160, 260]))
    assert dto["pattern_en"] == "Bucket"
    cards = [r for r in dto["key_roles"] if r["role_type"] == "cog_bowl"]
    assert cards and cards[0]["planet_name"] == "火星"
    # 真对分（偏离 0°）才写成实心轴；说明里带出实际偏离度数。
    assert "成对分（偏离约0.0°）" in cards[0]["description"]
    assert "实心轴" in cards[0]["description"]


def test_bucket_cog_point_card_when_no_anchor():
    # 碗底重心 10° 内无行星 → 退为纯几何「碗底」点卡，不能整条消失
    dto = jones_pattern.calculate_jones_pattern(
        _planets([0, 20, 40, 55, 68, 95, 110, 135, 160, 260]))
    assert dto["pattern_en"] == "Bucket"
    assert "cog_bowl_point" in _role_types(dto)
    assert "cog_bowl" not in _role_types(dto)


def test_sling_cog_card_present():
    # 把手取 200°（两侧空白 100°/160°，差 60° > FANHANDLE_BALANCE_MAX）：
    # 原用 230°（完美居中，差 0°）踩在 Fanhandle 放宽通道（span≤120 且居中≤20°）
    # 的边界上——Wozniak born-failing 修复接通该通道后，居中盘正确升级 Fanhandle，
    # 本测试的目的是弹弓型碗底卡存在性，故改用偏置把手保持 Sling 判定。
    dto = jones_pattern.calculate_jones_pattern(
        _planets([i * 100 / 8 for i in range(9)] + [200]))
    assert dto["pattern_en"] == "Sling"
    assert "cog_bowl" in _role_types(dto)


def test_two_handle_cog_card_present():
    dto = jones_pattern.calculate_jones_pattern(
        _planets([0, 20, 40, 75, 95, 115, 135, 150, 210, 300]))
    assert dto["pattern_en"] == "TwoHandle"
    cards = [r for r in dto["key_roles"] if r["role_type"] == "cog_bowl"]
    assert cards and cards[0]["planet_name"] == "金星"


def test_conj_handle_cog_card_present():
    dto = jones_pattern.calculate_jones_pattern(
        _planets([0, 20, 40, 75, 95, 115, 135, 150, 254, 256]))
    assert dto["pattern_en"] == "ConjHandle"
    assert "cog_bowl" in _role_types(dto)


def test_bucket_tilt_notes_name_actual_planets_on_all_three_cards():
    # 真实反馈（伊斯特伍德盘）：把手/两边界星三张卡拼不出把手到底偏谁。
    # 三张卡都必须写「本盘实际判定」并点名行星，不能只留"若偏向这一端"假设句。
    dto = jones_pattern.calculate_jones_pattern(
        _planets([0, 20, 40, 60, 80, 100, 120, 140, 160, 240]))  # 把手偏尾随端
    assert dto["pattern_en"] == "Bucket"
    by_type = {r["role_type"]: r["description"] for r in dto["key_roles"]}
    assert "把手冥王星偏向尾随端海王星" in by_type["handle"]
    assert "本盘把手冥王星实际偏向这一端" in by_type["bowl_edge_trailing"]
    assert "实际偏向对面的尾随端海王星" in by_type["bowl_edge_leading"]


def test_two_handle_cards_state_which_handle_is_read_first():
    # Sellar 双把手铁律：较快的把手是 HFP、"chosen first in interpretation"
    # （丘吉尔海王星+冥王星，海王星因较快胜出）。引擎早已算出 hfp_name，但两张
    # 把手卡此前文案完全对称，读者看不出谁先读——与"把手偏向算了不显示"同一个病。
    # 双把手不套用单把手的"偏向领头/尾随端"（原典未改写该规则，硬套即臆造）。
    dto = jones_pattern.calculate_jones_pattern(
        _planets([0, 20, 40, 75, 95, 115, 135, 150, 210, 300]))
    assert dto["pattern_en"] == "TwoHandle"
    assert dto["high_focus_planet"] == "海王星"
    by_type = {r["role_type"]: r["description"] for r in dto["key_roles"]}
    assert "海王星运行较快，是首要解读入口" in by_type["handle_left"]
    assert "冥王星作为第二条主轴" in by_type["handle_right"]
    # 偏向措辞绝不能出现在双把手任何一张卡上
    assert not any("偏向" in d for d in by_type.values())


# ── 2026-07-28：双把手三条新增判定（NLM 核验 Sellar 双把手章节）──────────

def test_two_handle_rejects_bowl_with_internal_void():
    """碗须为连续弧：拉出双把手后剩余8颗内部有≥90°裂口 → 实为多群，拒判。
    与单把手路径同一道 BOWL_MAX_INTERNAL_VOID 约束，此前双把手路径裸奔。"""
    from engine.jones import _check_two_handle
    # 两簇 [0-30]+[130-160]（内部裂口100°）+ 双把手220/300 → 必须拒收
    longs = sorted([0, 10, 20, 30, 130, 140, 150, 160, 220, 300])
    assert _check_two_handle(longs, longs, list(PLANET_NAMES_ZH)) is None
    # 对照组：内部裂口收窄到80°（<90）→ 照常接受
    longs2 = sorted([0, 10, 20, 30, 110, 120, 130, 140, 200, 280])
    assert _check_two_handle(longs2, longs2, list(PLANET_NAMES_ZH)) is not None


def test_three_isolated_handles_flag_seesaw_borderline():
    """Sellar："If there should be a third planet acting as a handle...begins to
    have the character of a See-Saw pattern."——三颗孤立星只挑得出两颗当把手，
    分类不动（软措辞不硬改判），但不得报 clear/False 装没事，须打交界旗标。"""
    dto = jones_pattern.calculate_jones_pattern(
        _planets([0, 10, 20, 30, 40, 50, 60, 120, 200, 280]))
    assert dto["pattern_en"] == "TwoHandle"
    assert dto["borderline"] is True
    assert "第三把手/跷跷板交界" in dto["borderline_reasons"]


def test_clean_two_handle_has_no_third_handle_flag():
    """干净双把手（恰两颗孤立星）不得误报第三把手旗标。"""
    dto = jones_pattern.calculate_jones_pattern(
        _planets([0, 20, 40, 75, 95, 115, 135, 150, 210, 300]))
    assert dto["pattern_en"] == "TwoHandle"
    assert "第三把手/跷跷板交界" not in dto["borderline_reasons"]


def test_two_handle_same_house_note():
    """Sellar："If the two planets are in the same house, this suggests one area
    of life has two separate influences, and expressions."——宫位经 planet_meta
    透传（此前只传经度，宫位附加路径从未生效）；缺失时静默跳过。"""
    base = [0, 20, 40, 75, 95, 115, 135, 150, 210, 300]  # 海王210/冥王300双把手
    ids = [pid for pid, _n, _g in jones_pattern.PLANETS]
    # 同宫：两把手都标第7宫
    planets = {pid: {"longitude": lon} for pid, lon in zip(ids, base)}
    planets["neptune"]["house"] = 7
    planets["pluto"]["house"] = 7
    dto = jones_pattern.calculate_jones_pattern(planets)
    by_type = {r["role_type"]: r["description"] for r in dto["key_roles"]}
    assert "两个把手同落第7宫" in by_type["handle_left"]
    assert "两个把手同落第7宫" in by_type["handle_right"]
    # 异宫：不出现同宫文案
    planets["pluto"]["house"] = 9
    dto2 = jones_pattern.calculate_jones_pattern(planets)
    assert not any("同落第" in r["description"] for r in dto2["key_roles"])
    # 无宫位数据（纯几何输入）：不崩、不出现同宫文案
    dto3 = jones_pattern.calculate_jones_pattern(_planets(base))
    assert not any("同落第" in r["description"] for r in dto3["key_roles"])


# ── 2026-07-28：合相把手不套用双把手的「较快者优先」──────────────────
# NLM 逐字复核 Sellar：「The faster moving planetary handle should be considered
# as the High Focus Planet」只写在双把手(Two Handle)一节；合相把手整节无此规则，
# Agatha Christie 案例原文称两星为 "These two High Focus Planets"（复数整体）。
# 此前引擎带假引用注释"Sellar Ch.5: ConjHandle HFP = 较快端"，把隔壁规则安了过来。

def _conj_dto():
    return jones_pattern.calculate_jones_pattern(
        _planets([0, 20, 40, 75, 95, 115, 135, 150, 254, 256]))


def test_conj_handle_has_no_single_hfp():
    """合相把手不得指定单颗行星为 HFP——同族三条路径(ConjHandle / Bucket-via-conj
    / Fan-via-conj)统一置 None，故事由两张把手卡承载。"""
    assert _conj_dto()["high_focus_planet"] is None
    # Fan 合相扇柄同口径（此前落 "海王星+冥王星" 拼接串，既非合法行星名又不一致）
    fan = jones_pattern.calculate_jones_pattern(
        _planets([0, 10, 20, 30, 40, 50, 60, 80, 220, 222]))
    assert fan["pattern_en"] == "Fanhandle"
    assert fan["high_focus_planet"] is None


def test_non_conj_handles_keep_single_hfp():
    """对照组：真有单星把手的格局不受影响，仍给单星 HFP。"""
    fan = jones_pattern.calculate_jones_pattern(
        _planets([10, 20, 35, 50, 65, 75, 82, 88, 92, 265]))
    assert fan["pattern_en"] == "Fanhandle"
    assert fan["high_focus_planet"] == "冥王星"
    two = jones_pattern.calculate_jones_pattern(
        _planets([0, 20, 40, 75, 95, 115, 135, 150, 210, 300]))
    assert two["high_focus_planet"] == "海王星"   # 双把手「较快者优先」保留


def test_conj_handle_cards_state_composite_focus_not_precedence():
    """两张合相卡须讲「复合焦点+慢星定调」，且绝不出现先读/主次措辞。"""
    by_type = {r["role_type"]: r["description"] for r in _conj_dto()["key_roles"]}
    for key in ("handle1", "handle2"):
        desc = by_type[key]
        assert "单一复合焦点" in desc and "不拆主次先后" in desc
        # 慢星定调方向：冥王星(慢) 为 海王星(快) 定调，不可写反
        assert "冥王星为海王星的表达定调" in desc
        assert "合相越紧力量越强" in desc
        # 只给结论、不报规则名：慢/快法则用于判断，但不在卡片里给读者补相位课
        assert "法则" not in desc
        assert "较慢" not in desc and "较快" not in desc
        # 双把手专属措辞不得泄漏到合相把手
        assert "首要解读入口" not in desc
        assert "运行较快" not in desc
        assert "第二条主轴" not in desc


def test_borderline_exposes_the_alternate_reading_and_distance_to_the_threshold():
    """交界时除旗标外还要给出「另一种读法 + 距阈值多少度」。

    此前 borderline 只回答「贴着某条线吗」，读盘的人接着要问的「往哪边倒、
    还差多少」没有答案，前端只能写一句「建议自行核对」。本用例锁住三件事：
    有充分几何条件时，另一类形态必须是该阈值另一侧的那一类、度数差与引擎
    自己的阈值常量一致；只有理想形态边界而没有合法命名候选时不产出推荐。
    """
    # 碗型 span=183°（max_gap=177°）：贴着 BOWL_THRESHOLD=175° 的上方，另一种
    # 读法必须是阈值另一侧的火车头型，度数差要报真正的改判旋钮（最大空白），
    # 且与引擎自己的阈值常量算得上（177-175=2°）。
    bowl = jones_pattern.calculate_jones_pattern(
        _planets([0, 15, 30, 50, 70, 90, 110, 130, 150, 183])
    )
    assert bowl["pattern_en"] == "Bowl"
    alts = {item["pattern_en"]: item for item in bowl["borderline_alternates"]}
    assert "Locomotive" in alts
    assert alts["Locomotive"]["pattern_zh"] == "火车头型"
    assert alts["Locomotive"]["reason"] == "碗/半球交界"
    assert alts["Locomotive"]["measure_zh"] == "最大空白"
    assert alts["Locomotive"]["delta_deg"] == pytest.approx(2.0, abs=0.05)

    # 沙漏型贴着 HOURGLASS_MIN_GAP(90°) → 另一侧是其父格局跷跷板型
    hourglass = jones_pattern.calculate_jones_pattern(_planets(
        [8.948, 237.3021, 220.2277, 353.1963, 5.3401,
         263.0665, 257.4156, 48.285, 259.5393, 55.563]
    ))
    assert hourglass["pattern_en"] == "Hourglass"
    assert [item["pattern_zh"] for item in hourglass["borderline_alternates"]] == ["跷跷板型"]

    # 标准格局不产出推荐，避免给明确的盘凭空加一条「还有别的可能」。
    standard = jones_pattern.calculate_jones_pattern(
        _planets([0, 20, 40, 60, 80, 100, 120, 140, 160, 180])
    )
    assert standard["state"] == "standard"
    assert standard["borderline_alternates"] == []


def test_borderline_alternate_never_equals_or_overrides_the_primary_pattern():
    """推荐是对照项，不是改判：另一类形态不得与主标签同名。"""
    from engine.jones import _BORDERLINE_ALT
    for reason, mapping in _BORDERLINE_ALT.items():
        for current, alternate in mapping.items():
            assert current != alternate, (reason, current)

    result = jones_pattern.calculate_jones_pattern(_planets(
        [170.593, 345.1172, 353.2493, 65.1288, 268.2263,
         84.8909, 8.8919, 179.2904, 295.3118, 357.0264]
    ))
    assert result["pattern_en"] == "TwoHandle"
    assert result["state"] == "borderline"
    for item in result["borderline_alternates"]:
        assert item["pattern_en"] != result["pattern_en"]


def test_borderline_alternate_is_verified_by_replaying_the_engine():
    """方向必须实算得出：把旋钮推过阈值，引擎真的判成它说的那个形态。

    此前"另一种读法"完全依赖 _BORDERLINE_ALT 查表，个别条目与引擎的改判闸门
    不同步，会指向一个引擎永远不会走到的形态。本用例对随机盘逐张复核：凡是
    报出了方向的交界盘，都要能在实算里重现该方向。
    """
    import random
    from engine.jones import _calc_gaps, _probe_alternate, detect_with_variants

    random.seed(20260914)
    checked = 0
    for _ in range(400):
        longs = [random.uniform(0, 360) for _ in range(10)]
        result = jones_pattern.calculate_jones_pattern(_planets(longs))
        if result["state"] != "borderline":
            continue
        gaps = _calc_gaps(sorted(l % 360.0 for l in longs))
        # extra 必须传真值：把手间距不在 gaps 序列里，只能从 extra 认出来，
        # 传空字典会把「合相/双把手交界」整条路径漏过去。
        extra = detect_with_variants(longs).extra
        for item in result["borderline_alternates"]:
            probed, _delta, _knob = _probe_alternate(
                item["reason"], result["pattern_en"], gaps, extra
            )
            if isinstance(probed, str):
                # 实算得出的方向必须与 DTO 一致
                assert probed == item["pattern_en"], (result["pattern_en"], item)
                checked += 1
    assert checked > 50, f"实算校验样本过少：{checked}"


def test_every_borderline_reason_is_decided_by_the_engine_not_the_table():
    """每一条交界原因都要走实算，查表只能作为无旋钮时的兜底。

    2026-09 的事故只暴露在碗型那一条上，但同一类风险遍布整张 _BORDERLINE_ALT：
    表里写的是"阈值另一侧理论上是谁"，引擎实际的改判闸门往往另有条件。本用例
    扫一批随机盘，要求每条真实出现过的交界原因都有实算裁决的样本，并记录查表
    与实算分歧的规模——分歧存在正是不能回退到查表的理由。
    """
    import random
    import collections
    from engine.jones import _calc_gaps, _probe_alternate, detect_with_variants
    from engine.jones import _BORDERLINE_ALT

    random.seed(20260916)
    seen_reasons = collections.Counter()
    verified = collections.Counter()
    table_would_differ = 0
    for _ in range(1200):
        longs = [random.uniform(0, 360) for _ in range(10)]
        result = jones_pattern.calculate_jones_pattern(_planets(longs))
        if result["state"] != "borderline":
            continue
        res = detect_with_variants(longs)
        gaps = _calc_gaps(sorted(l % 360.0 for l in longs))
        for reason in result["borderline_reasons"]:
            seen_reasons[reason] += 1
        for item in result["borderline_alternates"]:
            probed, _delta, knob = _probe_alternate(
                item["reason"], res.pattern_en, gaps, res.extra
            )
            assert probed is not False, (
                f"交界「{item['reason']}」仍在走查表，没有实算旋钮：{item}"
            )
            assert probed == item["pattern_en"], (res.pattern_en, item, probed)
            # 报了度数差就必须说明在看哪个量；双群/把手结构重叠没有数值距离。
            if item.get("delta_deg") is not None:
                assert item.get("measure_zh"), item
            assert knob == item["measure_zh"], (knob, item)
            verified[item["reason"]] += 1
            table_dir = _BORDERLINE_ALT.get(item["reason"], {}).get(res.pattern_en)
            if table_dir and table_dir != probed:
                table_would_differ += 1

    # 覆盖面：样本里出现过的交界原因，只要能产出候选就必须有实算裁决记录
    assert len(verified) >= 5, dict(verified)
    assert sum(verified.values()) > 200, dict(verified)
    # 分歧规模是这套实算存在的理由；真为 0 时说明探测退化成了查表的复读
    assert table_would_differ > 0


def test_borderline_probe_never_changes_the_classification():
    """探测只读不写：开启/关闭"另一种读法"都不得影响主判定。"""
    import random
    import engine.jones as engine_jones

    random.seed(4242)
    charts = [[random.uniform(0, 360) for _ in range(10)] for _ in range(300)]
    original = engine_jones._borderline_alternates
    try:
        engine_jones._borderline_alternates = lambda *a, **k: []
        without = [engine_jones.detect_with_variants(c).pattern_en for c in charts]
    finally:
        engine_jones._borderline_alternates = original
    with_probe = [engine_jones.detect_with_variants(c).pattern_en for c in charts]
    assert without == with_probe
    # 探测标志必须复位，否则后续请求会被当成仍在探测而跳过交界提示
    assert engine_jones._PROBING.value is False
# 1993-02-20 13:20 中山：提桶型，碗中心附近天王星与海王星相距约 0.35°。
COMPOSITE_COG = [331.59, 317.15, 349.6, 13.59, 98.82, 193.92, 322.2, 290.5, 290.15, 235.51]


def test_bowl_centre_exposes_conjunct_partner_without_changing_nearest_planet():
    result = jones_pattern.calculate_jones_pattern(_planets(COMPOSITE_COG))
    assert result["pattern_en"] == "Bucket"
    cog = result["cog_bowl"]
    assert cog["planet_name"] == "海王星"
    assert [p["planet_name"] for p in cog["partners"]] == ["天王星"]
    role = next(r for r in result["key_roles"] if r["role_type"] == "cog_bowl")
    assert [p["planet_name"] for p in role["partners"]] == ["天王星"]
    assert "复合的碗中心" in role["description"]
    json.dumps(result, ensure_ascii=False)

    apart = list(COMPOSITE_COG)
    apart[7] = 310.5  # 天王星挪开 20°，不再与海王星合相
    result2 = jones_pattern.calculate_jones_pattern(_planets(apart))
    assert result2["cog_bowl"]["planet_name"] == "海王星"
    assert "partners" not in result2["cog_bowl"]
    role2 = next(r for r in result2["key_roles"] if r["role_type"] == "cog_bowl")
    assert "partners" not in role2
def test_bowl_centre_partner_orb_is_six_degrees():
    within = list(COMPOSITE_COG)
    within[7] = 284.5   # 天王星距海王星 5.65°
    result = jones_pattern.calculate_jones_pattern(_planets(within))
    assert [p["planet_name"] for p in result["cog_bowl"].get("partners", [])] == ["海王星"]

    beyond = list(COMPOSITE_COG)
    beyond[7] = 283.9   # 天王星距海王星 6.25°：超过 6°，不再当作一个整体
    result2 = jones_pattern.calculate_jones_pattern(_planets(beyond))
    assert "partners" not in result2["cog_bowl"]
def test_centered_handle_is_an_opposition_only_when_degrees_allow():
    # 1993 盘：火星与天海合相只是星座对冲，偏离对分 11° 以上。
    result = jones_pattern.calculate_jones_pattern(_planets(COMPOSITE_COG))
    role = next(r for r in result["key_roles"] if r["role_type"] == "cog_bowl")
    assert "没有构成对分相" in role["description"]
    assert "对分实心轴" not in role["description"]

    opposed = list(COMPOSITE_COG)
    opposed[4] = 110.15   # 火星正对分海王星，仍在虚点 8° 内
    result2 = jones_pattern.calculate_jones_pattern(_planets(opposed))
    assert result2["pattern_en"] == "Bucket"
    role2 = next(r for r in result2["key_roles"] if r["role_type"] == "cog_bowl")
    assert "成对分" in role2["description"] and "实心轴" in role2["description"]
