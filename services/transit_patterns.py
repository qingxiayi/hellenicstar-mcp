# -*- coding: utf-8 -*-
"""行运相位格局：大三角 / 大风筝 / T三角 / 大十字 / Yod。

天象板块专用，跟本命盘的 `engine/natal_chart.py::detect_phase_patterns` 是两套：
本命那套服务于「一张固定的盘」，主相位一律 10° 容许度；行运这套要回答「此刻天上
挂着什么能持续一段时间的配置」，口径不同——

- **不含月亮**：月亮两三天就换一组格局，天天播报等于噪音。慢星组成的格局才能
  持续几周到几个月，也才是「今天值得知道」的天象。月亮参与的配置由「此刻生效
  相位」那一层负责。
- **含凯龙**：与 sky_now 的相位口径一致（本命盘一直算凯龙，天象板块此前漏了）。
- **容许度比本命紧**：三四颗星每条边都松到 10°，图形早就不成形了。主相位边
  6°，Yod 的 150° 边 3°（跟 sky_now / calculator 的梅花相位同口径）。

被更大图形完全包含的小图形不重复报（风筝里的大三角、大十字里的两个 T三角），
否则同一组星会在卡片上刷出三四行，读者以为天上有好几个格局。
"""
from itertools import combinations

import swisseph as swe

from services.transit_utils import body_position

# 参与格局判定的星体：日 + 内行星 + 外行星 + 凯龙，不含月亮（见模块 docstring）。
PATTERN_BODIES = (
    swe.SUN, swe.MERCURY, swe.VENUS, swe.MARS, swe.JUPITER, swe.SATURN,
    swe.URANUS, swe.NEPTUNE, swe.PLUTO, swe.CHIRON,
)

_BODY_CN = {
    swe.SUN: "太阳", swe.MERCURY: "水星", swe.VENUS: "金星", swe.MARS: "火星",
    swe.JUPITER: "木星", swe.SATURN: "土星", swe.URANUS: "天王星",
    swe.NEPTUNE: "海王星", swe.PLUTO: "冥王星", swe.CHIRON: "凯龙星",
}
_BODY_KEY = {
    swe.SUN: "sun", swe.MERCURY: "mercury", swe.VENUS: "venus", swe.MARS: "mars",
    swe.JUPITER: "jupiter", swe.SATURN: "saturn", swe.URANUS: "uranus",
    swe.NEPTUNE: "neptune", swe.PLUTO: "pluto", swe.CHIRON: "chiron",
}

# 主相位边 6°、150° 边 3°。150° 单独收紧与 sky_now._ACTIVE_ORB_BY_ANGLE、
# calculator._phase_defs 的梅花相位同口径，不是随手定的。
MAJOR_EDGE_ORB = 6.0
QUINCUNX_EDGE_ORB = 3.0

_ZODIAC_ZH = (
    "白羊座", "金牛座", "双子座", "巨蟹座", "狮子座", "处女座",
    "天秤座", "天蝎座", "射手座", "摩羯座", "水瓶座", "双鱼座",
)
_ELEMENT_ZH = ("火象", "土象", "风象", "水象")
_MODALITY_ZH = ("基本", "固定", "变动")

_PATTERN_META = {
    # kind: (中文名, 图形符号, 一句话读法)
    "grand_trine": ("大三角", "△", "三颗星彼此三分，能量顺畅流通，容易顺手但也容易停在舒适区。"),
    "kite": ("大风筝", "♦", "大三角接上一颗对分星，把顺畅的循环推出一个出口。"),
    "t_square": ("T三角", "□", "一组对分同时四分第三颗，张力集中在顶点那颗星上。"),
    "grand_cross": ("大十字", "✖", "两组对分互相四分，四个方向同时拉扯，最考验取舍。"),
    "yod": ("上帝手指", "⋆", "两颗六分的星同时以 150° 指向第三颗，指向的那颗要做出调整。"),
}


def _separation(lon1: float, lon2: float) -> float:
    """两点黄经角距，折回 0–180°。"""
    diff = abs((lon1 - lon2) % 360.0)
    return min(diff, 360.0 - diff)


def _edge(lons, i: int, j: int, angle: float):
    """(i,j) 这条边与目标角的偏差；超容许度返回 None。"""
    orb_limit = QUINCUNX_EDGE_ORB if angle == 150.0 else MAJOR_EDGE_ORB
    delta = abs(_separation(lons[i], lons[j]) - angle)
    return delta if delta <= orb_limit else None


def _point(body: int, lon: float) -> dict:
    sign_idx = int((lon % 360.0) // 30.0)
    return {
        "key": _BODY_KEY[body],
        "cn": _BODY_CN[body],
        "longitude": round(lon % 360.0, 4),
        "sign_cn": _ZODIAC_ZH[sign_idx],
        "deg_in_sign": round(lon % 30.0, 2),
        "element_cn": _ELEMENT_ZH[sign_idx % 4],
        "modality_cn": _MODALITY_ZH[sign_idx % 3],
    }


def _shared(points, field: str):
    """四颗/三颗星是否共用同一个元素或模式；不共用返回 None。"""
    values = {p[field] for p in points}
    return values.pop() if len(values) == 1 else None


# 慢星：木以外都要好几周才走完 6° 容许度，全由它们组成的图形能挂几周到几个月。
# 一旦有日水金火参与，图形只维持几天——同一张卡片上这两种寿命不该并列显示，
# 与「此刻生效相位」的 event / background 分层是同一套语言。
_SLOW_BODIES = frozenset((
    swe.JUPITER, swe.SATURN, swe.URANUS, swe.NEPTUNE, swe.PLUTO, swe.CHIRON,
))


def _row(kind: str, members, edges, lons, apex_body=None) -> dict:
    """组装一条格局记录。`edges` 是 [(i, j, 目标角, 偏差)]，用于算最松边。"""
    name_cn, glyph, reading = _PATTERN_META[kind]
    worst = max(delta for _i, _j, _angle, delta in edges)
    points = [_point(body, lons[body]) for body in members]
    return {
        "kind": kind,
        "kind_cn": name_cn,
        "glyph": glyph,
        "reading": reading,
        "points": points,
        "keys": sorted(p["key"] for p in points),
        "apex": _point(apex_body, lons[apex_body]) if apex_body is not None else None,
        # 最松的一条边决定整个图形有多松，比平均值诚实。
        "orb_deg": round(worst, 2),
        # 紧密度只作展示（进度条），不参与任何判定。
        "tightness": max(0, min(100, round((1 - worst / MAJOR_EDGE_ORB) * 100))),
        "element_cn": _shared(points, "element_cn"),
        "modality_cn": _shared(points, "modality_cn"),
        "tier": "background" if all(b in _SLOW_BODIES for b in members) else "event",
    }


def _detect(lons: dict) -> list:
    bodies = [b for b in PATTERN_BODIES if b in lons]
    rows = []

    # 大三角：三条 120° 边。
    trines = []
    for combo in combinations(bodies, 3):
        i, j, k = combo
        e1, e2, e3 = _edge(lons, i, j, 120.0), _edge(lons, i, k, 120.0), _edge(lons, j, k, 120.0)
        if e1 is not None and e2 is not None and e3 is not None:
            trines.append((combo, [(i, j, 120.0, e1), (i, k, 120.0, e2), (j, k, 120.0, e3)]))

    # 大风筝：大三角 + 一颗与其中一角对分、与另两角六分的星。
    kite_covered = set()
    for combo, edges in trines:
        for tail in bodies:
            if tail in combo:
                continue
            for apex in combo:
                others = [b for b in combo if b != apex]
                opp = _edge(lons, tail, apex, 180.0)
                sx1 = _edge(lons, tail, others[0], 60.0)
                sx2 = _edge(lons, tail, others[1], 60.0)
                if opp is None or sx1 is None or sx2 is None:
                    continue
                rows.append(_row(
                    "kite", list(combo) + [tail],
                    edges + [(tail, apex, 180.0, opp),
                             (tail, others[0], 60.0, sx1),
                             (tail, others[1], 60.0, sx2)],
                    lons, apex_body=tail,
                ))
                kite_covered.add(frozenset(combo))
    # 已经并进风筝的大三角不再单独占一行。
    for combo, edges in trines:
        if frozenset(combo) not in kite_covered:
            rows.append(_row("grand_trine", list(combo), edges, lons))

    # 大十字：两组对分，且两组之间互相四分。
    oppositions = []
    for i, j in combinations(bodies, 2):
        delta = _edge(lons, i, j, 180.0)
        if delta is not None:
            oppositions.append(((i, j), delta))

    cross_covered = set()
    for (pair_a, delta_a), (pair_b, delta_b) in combinations(oppositions, 2):
        if set(pair_a) & set(pair_b):
            continue
        squares = []
        for a in pair_a:
            for b in pair_b:
                sq = _edge(lons, a, b, 90.0)
                if sq is None:
                    squares = None
                    break
                squares.append((a, b, 90.0, sq))
            if squares is None:
                break
        if not squares:
            continue
        members = list(pair_a) + list(pair_b)
        rows.append(_row(
            "grand_cross", members,
            [(pair_a[0], pair_a[1], 180.0, delta_a),
             (pair_b[0], pair_b[1], 180.0, delta_b)] + squares,
            lons,
        ))
        # 大十字天然含四个 T三角，四个都报出来只会淹没主图形。
        for a in pair_a:
            for b in pair_b:
                cross_covered.add(frozenset((pair_a[0], pair_a[1], b)))
                cross_covered.add(frozenset((pair_b[0], pair_b[1], a)))

    # T三角：一组对分 + 同时四分两端的顶点星。
    for (pair, delta_opp) in oppositions:
        for apex in bodies:
            if apex in pair:
                continue
            sq1 = _edge(lons, apex, pair[0], 90.0)
            sq2 = _edge(lons, apex, pair[1], 90.0)
            if sq1 is None or sq2 is None:
                continue
            if frozenset((pair[0], pair[1], apex)) in cross_covered:
                continue
            rows.append(_row(
                "t_square", [pair[0], pair[1], apex],
                [(pair[0], pair[1], 180.0, delta_opp),
                 (apex, pair[0], 90.0, sq1), (apex, pair[1], 90.0, sq2)],
                lons, apex_body=apex,
            ))

    # Yod：底边六分，两条 150° 边同时指向顶点。
    for base1, base2 in combinations(bodies, 2):
        base = _edge(lons, base1, base2, 60.0)
        if base is None:
            continue
        for apex in bodies:
            if apex in (base1, base2):
                continue
            q1 = _edge(lons, apex, base1, 150.0)
            q2 = _edge(lons, apex, base2, 150.0)
            if q1 is None or q2 is None:
                continue
            rows.append(_row(
                "yod", [base1, base2, apex],
                [(base1, base2, 60.0, base),
                 (apex, base1, 150.0, q1), (apex, base2, 150.0, q2)],
                lons, apex_body=apex,
            ))

    # 慢星长期配置排前（它们才是「这阵子天上的底色」），其次越紧越靠前，
    # 同样紧时星数多的优先（大十字 > 风筝 > 三星图形）。
    rows.sort(key=lambda r: (r["tier"] != "background", r["orb_deg"], -len(r["points"])))
    return rows


def patterns_at(jd_ut: float) -> list:
    """指定时刻天上成立的相位格局列表（可能是空列表）。"""
    lons = {}
    for body in PATTERN_BODIES:
        lon, _speed = body_position(body, jd_ut)
        lons[body] = lon % 360.0
    return _detect(lons)


def patterns_from_longitudes(longitudes: dict) -> list:
    """纯几何入口：{swe 常量: 黄经} → 格局列表。测试与离线核对用，不碰星历。"""
    return _detect({b: lon % 360.0 for b, lon in longitudes.items()})
