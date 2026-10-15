#!/usr/bin/env python3
"""
Solar Return 扩展算法模块 —— 补上 NLM 框架中尚未实现的算法。

基于 swisseph 直接计算，不依赖 kerykeion/astro-adapter。
与现有 solar-return skill 的二分法引擎配套使用。

覆盖：
  - 角宫行星（orb<8° 合轴）
  - ASC 守护星（传统七曜管控 + 尊贵/落宫/逆行）
  - 逆行行星列表
  - 月相（Rudhyar 八分法）
  - 默冬周期检测（19/38/57 岁）
  - 度数重合（SR 行星合本命行星/轴，orb<3°）
  - 整体格局（散落/提桶/碗型/束型）
  - 小限法（Annual Profections）

用法：
  python3 solar_return_advanced.py   # 用姐姐 1976-02-01 09:50 北京实测 2026
"""

import swisseph as swe

# ── 常量 ──────────────────────────────────────────────────

PLANET_NAMES = {
    swe.SUN: "太阳☉", swe.MOON: "月亮☽", swe.MERCURY: "水星☿",
    swe.VENUS: "金星♀", swe.MARS: "火星♂", swe.JUPITER: "木星♃",
    swe.SATURN: "土星♄", swe.URANUS: "天王星♅", swe.NEPTUNE: "海王星♆",
    swe.PLUTO: "冥王星♇", swe.TRUE_NODE: "北交☊",
    -1: "凯龙⚷",  # swe.CHIRON 可能不是标准常量，用 id 判断
}

SIGNS = ["♈白羊", "♉金牛", "♊双子", "♋巨蟹", "♌狮子", "♍处女",
         "♎天秤", "♏天蝎", "♐射手", "♑摩羯", "♒水瓶", "♓双鱼"]

ELEMENTS = {0: "火", 1: "土", 2: "风", 3: "水"}

# 传统七曜管控（日管狮子，月管巨蟹，水星管双子+处女...）
TRAD_RULER = {
    "♈白羊": "火星♂", "♉金牛": "金星♀", "♊双子": "水星☿",
    "♋巨蟹": "月亮☽", "♌狮子": "太阳☉", "♍处女": "水星☿",
    "♎天秤": "金星♀", "♏天蝎": "火星♂", "♐射手": "木星♃",
    "♑摩羯": "土星♄", "♒水瓶": "土星♄", "♓双鱼": "木星♃",
}

PLANET_IDS = [swe.SUN, swe.MOON, swe.MERCURY, swe.VENUS, swe.MARS,
              swe.JUPITER, swe.SATURN, swe.URANUS, swe.NEPTUNE, swe.PLUTO]

RUDHYAR_PHASES = ["新月", "峨眉月", "上弦月", "盈凸月", "满月", "亏凸月", "下弦月", "残月"]

# ── 工具函数 ──────────────────────────────────────────────

swe.set_ephe_path("ephe")

def sign_str(lon):
    """经度 → 星座字符串"""
    s = int(lon / 30)
    return f"{SIGNS[s]} {lon % 30:.2f}°"

def sign_name(lon):
    """经度 → 星座名称（不含度数）"""
    return SIGNS[int(lon / 30)]

def element_of(lon):
    return ELEMENTS[int(lon / 30) % 4]

def norm_angle(a):
    """标准化到 [0, 360)"""
    return a % 360

def angular_distance(a, b):
    """两点间最短角度差"""
    d = abs(norm_angle(a) - norm_angle(b))
    return min(d, 360 - d)

def locate_house(lon, hcusps):
    """
    确定经度落入哪个宫位（1-12）。
    hcusps: tuple of 12 cusp longitudes (0-indexed).
    Placidus 宫头 = hcusps[0..11] 对应 1..12 宫。
    """
    for h in range(12):
        c = hcusps[h]
        n = hcusps[(h + 1) % 12]
        if c < n:
            if c <= lon < n:
                return h + 1
        else:  # 跨越 0° 边界
            if lon >= c or lon < n:
                return h + 1
    return 1


# ═══════════════════════════════════════════════════════════
#  核心：完整日返盘计算 + 所有扩展算法
# ═══════════════════════════════════════════════════════════

def compute_solar_return_full(natal_utc_jd, natal_lat, natal_lng,
                              birth_year, birth_month, birth_day,
                              target_year, residence_lat, residence_lng,
                              natal_sun_lon=None):
    """
    完整日返盘计算。

    返回 dict：
      sr_jd, sr_utc_str,
      planets: {id: {lon, sign, house, retro, speed}},
      houses: [12宫头经度],
      axes: {asc, mc, dsc, ic},
      natal: {sun_lon, planets: {id: lon}, axes: {asc, mc}},
      extra: 所有扩展数据
    """
    # ── 1. 先算本命数据 ──
    if natal_sun_lon is None:
        natal_sun_lon = swe.calc_ut(natal_utc_jd, swe.SUN)[0][0]

    natal_hcusps, natal_ascmc = swe.houses_ex(natal_utc_jd, natal_lat, natal_lng, b'P')
    natal_axes = {"asc": natal_ascmc[0], "mc": natal_ascmc[1],
                  "dsc": norm_angle(natal_ascmc[0] + 180), "ic": norm_angle(natal_ascmc[1] + 180)}

    natal_planets = {}
    for pid in PLANET_IDS:
        data, flag = swe.calc_ut(natal_utc_jd, pid)
        natal_planets[pid] = {"lon": data[0], "speed": data[3]}

    # ── 2. 二分法找回归时刻 ──
    target = natal_sun_lon
    jd_guess = swe.julday(target_year, birth_month, birth_day, 12.0)
    jd_step = 2.0

    for i in range(20):
        sun_current = swe.calc_ut(jd_guess, swe.SUN)[0][0]
        diff = sun_current - target
        if diff > 180: diff -= 360
        elif diff < -180: diff += 360
        if abs(diff) < 0.00001:
            break
        jd_guess -= diff * (365.25 / 360.0) * jd_step
        jd_step *= 0.5

    sr_jd = jd_guess
    sr_sun_lon = swe.calc_ut(sr_jd, swe.SUN)[0][0]

    # UTC 回显
    from datetime import datetime, timezone, timedelta
    jd1900 = 2415020.0
    sr_dt = datetime(1899, 12, 31, 12, tzinfo=timezone.utc) + timedelta(days=sr_jd - jd1900)
    sr_utc_str = sr_dt.strftime("%Y-%m-%d %H:%M:%S UTC")

    # ── 3. 居住地重算 SR 四轴/宫位 ──
    sr_hcusps, sr_ascmc = swe.houses_ex(sr_jd, residence_lat, residence_lng, b'P')
    sr_axes = {"asc": sr_ascmc[0], "mc": sr_ascmc[1],
               "dsc": norm_angle(sr_ascmc[0] + 180), "ic": norm_angle(sr_ascmc[1] + 180)}

    # ── 4. SR 行星 ──
    sr_planets = {}
    for pid in PLANET_IDS:
        data, flag = swe.calc_ut(sr_jd, pid)
        lon = data[0]
        speed = data[3]
        sr_planets[pid] = {
            "lon": lon,
            "sign": sign_name(lon),
            "house": locate_house(lon, sr_hcusps),
            "retro": speed < 0,
            "speed": speed,
        }

    # ── 5. 扩展算法 ──
    extra = compute_all_extras(sr_planets, sr_axes, sr_hcusps,
                                natal_planets, natal_axes, natal_hcusps,
                                birth_year, target_year)

    return {
        "sr_jd": sr_jd,
        "sr_utc": sr_utc_str,
        "sr_sun_lon": sr_sun_lon,
        "natal_sun_lon": natal_sun_lon,
        "deviation_arcsec": abs(sr_sun_lon - natal_sun_lon) * 3600,
        "planets": sr_planets,
        "houses": list(sr_hcusps),
        "axes": sr_axes,
        "natal": {"sun_lon": natal_sun_lon, "planets": natal_planets, "axes": natal_axes},
        "extra": extra,
    }


# ═══════════════════════════════════════════════════════════
#  扩展算法实现
# ═══════════════════════════════════════════════════════════

def compute_all_extras(sr_planets, sr_axes, sr_hcusps,
                       natal_planets, natal_axes, natal_hcusps,
                       birth_year, target_year):
    """一次性计算所有扩展维度，返回 dict。"""
    return {
        "angular_planets": angular_planets(sr_planets, sr_axes),
        "asc_ruler": asc_ruler_analysis(sr_axes["asc"], sr_planets, sr_hcusps),
        "retrograde_planets": retrograde_list(sr_planets),
        "moon_phase": moon_phase(sr_planets[swe.SUN]["lon"], sr_planets[swe.MOON]["lon"]),
        "metonic_cycle": metonic_check(birth_year, target_year, sr_planets[swe.MOON]["lon"],
                                        natal_planets.get(swe.MOON, {}).get("lon", 0)),
        "degree_contacts": degree_contacts(sr_planets, sr_axes, natal_planets, natal_axes),
        "chart_shape": chart_shape(sr_planets, sr_hcusps),
        "annual_profections": annual_profections(natal_axes["asc"], birth_year, target_year),
        "moon_house_element": {
            "house": sr_planets[swe.MOON]["house"],
            "element": element_of(sr_planets[swe.MOON]["lon"]),
            "sign": sign_name(sr_planets[swe.MOON]["lon"]),
        },
        "sun_house": sr_planets[swe.SUN]["house"],
    }


# ── 角宫行星 ──

def angular_planets(sr_planets, sr_axes, orb=8.0):
    """
    找出 SR 盘内 orb 内合轴的行星。
    检查四轴（ASC/DSC/MC/IC）+ 角宫（1/4/7/10宫）边缘。
    """
    result = []
    axis_names = {"asc": "ASC↑", "dsc": "DSC↓", "mc": "MC↑", "ic": "IC↓"}
    for pid, p in sr_planets.items():
        for ax_name, ax_lon in sr_axes.items():
            dist = angular_distance(p["lon"], ax_lon)
            if dist <= orb:
                result.append({
                    "planet": PLANET_NAMES.get(pid, f"ID{pid}"),
                    "axis": axis_names[ax_name],
                    "orb": round(dist, 2),
                    "house": p["house"],
                })
    # 去重（一粒行星可能同时合多轴），按 orb 排序
    result.sort(key=lambda x: x["orb"])
    return result


# ── ASC 守护星 ──

def asc_ruler_analysis(sr_asc_lon, sr_planets, sr_hcusps):
    """
    SR ASC 的守护星分析：
      - 守护星是谁
      - 其在 SR 中的落宫
      - 是否逆行
      - 相位（仅列出与 Sun/Moon 的硬相位部分）
    """
    asc_sign = sign_name(sr_asc_lon)
    ruler_name = TRAD_RULER.get(asc_sign, "未知")

    # 找到守护星对应的 pid
    ruler_pid = None
    for pid, name in PLANET_NAMES.items():
        if name == ruler_name:
            ruler_pid = pid
            break

    if ruler_pid is None or ruler_pid not in sr_planets:
        return {"sign": asc_sign, "ruler": ruler_name, "error": "守护星未找到"}

    rp = sr_planets[ruler_pid]
    return {
        "asc_sign": asc_sign,
        "ruler": ruler_name,
        "ruler_house": rp["house"],
        "ruler_sign": rp["sign"],
        "ruler_retro": rp["retro"],
        "ruler_lon": round(rp["lon"], 2),
    }


# ── 逆行行星 ──

def retrograde_list(sr_planets):
    """返回 SR 盘中所有逆行行星的列表。"""
    retro = []
    for pid, p in sr_planets.items():
        if p["retro"]:
            retro.append({
                "planet": PLANET_NAMES.get(pid, f"ID{pid}"),
                "sign": p["sign"],
                "house": p["house"],
                "speed_deg_day": round(p["speed"], 4),
            })
    return retro


# ── 月相 ──

def moon_phase(sun_lon, moon_lon):
    """Rudhyar 八分法月相。0=新月, 1=峨眉月, ... 7=残月。"""
    angle = norm_angle(moon_lon - sun_lon)
    phase_num = int(angle / 45)
    # 精确到 1 位小数
    return {
        "angle": round(angle, 1),
        "phase_num": phase_num,
        "phase_name": RUDHYAR_PHASES[phase_num],
        "meaning_hint": {
            0: "新开始、种子期",
            1: "萌发、向外宣告",
            2: "危机行动、突破",
            3: "积累、打磨",
            4: "高潮、结果、关系顶点",
            5: "传播、分享",
            6: "收割、转向内在",
            7: "清理、放手、结束",
        }.get(phase_num, ""),
    }


# ── 默冬周期 ──

def metonic_check(birth_year, target_year, sr_moon_lon, natal_moon_lon, orb=3.0):
    """
    检测是否处于默冬周期节点（19/38/57 岁）。
    判断标准：年龄 n 是 19 的倍数 + SR 月亮接近本命月亮（orb<3°）。
    """
    age = target_year - birth_year
    metonic_ages = [19, 38, 57, 76]
    result = {
        "age": age,
        "is_metonic_age": age in metonic_ages,
    }
    if age in metonic_ages:
        dist = angular_distance(sr_moon_lon, natal_moon_lon)
        result["moon_distance"] = round(dist, 2)
        result["is_metonic_return"] = dist <= orb
        result["sr_moon_sign"] = sign_name(sr_moon_lon)
        if natal_moon_lon > 0:
            result["natal_moon_sign"] = sign_name(natal_moon_lon)
    return result


# ── 度数重合 ──

def degree_contacts(sr_planets, sr_axes, natal_planets, natal_axes, orb=3.0):
    """
    SR 行星/轴 合本命行星/轴（orb<3°）。
    返回所有重合对，按 orb 排序。
    """
    contacts = []

    # SR 行星 → 本命行星
    for spid, sp in sr_planets.items():
        for npid, np in natal_planets.items():
            d = angular_distance(sp["lon"], np["lon"])
            if d <= orb and not (spid == swe.SUN and npid == swe.SUN and d < 0.01):
                contacts.append({
                    "type": "SR行星→本命行星",
                    "sr": PLANET_NAMES.get(spid, f"ID{spid}"),
                    "natal": PLANET_NAMES.get(npid, f"ID{np}"),
                    "orb": round(d, 2),
                })

    # SR 行星 → 本命轴
    natal_axis_names = {"asc": "本命ASC", "mc": "本命MC", "dsc": "本命DSC", "ic": "本命IC"}
    for spid, sp in sr_planets.items():
        for ax_name, ax_lon in natal_axes.items():
            d = angular_distance(sp["lon"], ax_lon)
            if d <= orb:
                contacts.append({
                    "type": "SR行星→本命轴",
                    "sr": PLANET_NAMES.get(spid, f"ID{spid}"),
                    "natal": natal_axis_names[ax_name],
                    "orb": round(d, 2),
                })

    # SR 轴 → 本命行星
    sr_axis_names = {"asc": "SR_ASC", "mc": "SR_MC", "dsc": "SR_DSC", "ic": "SR_IC"}
    for ax_name, ax_lon in sr_axes.items():
        for npid, np in natal_planets.items():
            d = angular_distance(ax_lon, np["lon"])
            if d <= orb:
                contacts.append({
                    "type": "SR轴→本命行星",
                    "sr": sr_axis_names[ax_name],
                    "natal": PLANET_NAMES.get(npid, f"ID{np}"),
                    "orb": round(d, 2),
                })

    contacts.sort(key=lambda x: x["orb"])
    return contacts


# ── 整体格局 ──

def chart_shape(sr_planets, sr_hcusps):
    """
    判断 SR 盘的整体行星分布格局。
    用行星在黄道上的经度分布：
      - 束型 (Bundle): 所有行星集中在 120° 内
      - 碗型 (Bowl):  所有行星集中在 180° 内
      - 提桶 (Bucket): 碗型 + 一颗行星单独在外（把手），即最大间隙把 1 颗行星与其余隔开
      - 散落 (Splash): 以上都不满足
    """
    lons = sorted([p["lon"] for p in sr_planets.values()])
    n = len(lons)
    if not lons:
        return {"shape": "无数据"}

    # 找最大间隙及其起止位置
    max_gap = 0
    gap_end_idx = 0  # 最大间隙结束端的行星 index（间隙另一侧）
    for i in range(n):
        next_i = (i + 1) % n
        gap = norm_angle(lons[next_i] - lons[i])
        if gap > max_gap:
            max_gap = gap
            gap_end_idx = next_i

    span = 360 - max_gap

    if span <= 120:
        shape = "束型 (Bundle)"
    elif span <= 180:
        # 数最大间隙另一侧有多少颗行星（= handle）
        # 从 gap_end_idx 出发，顺时针走，直到遇到 max_gap（即走完整个 minority 侧）
        handle_count = 0
        idx = gap_end_idx
        while True:
            handle_count += 1
            next_idx = (idx + 1) % n
            if norm_angle(lons[next_idx] - lons[idx]) >= max_gap * 0.9:
                break
            idx = next_idx
        if handle_count == 1 and n > 2:
            shape = "提桶 (Bucket)"
        else:
            shape = "碗型 (Bowl)"
    else:
        shape = "散落 (Splash)"

    return {"shape": shape, "span": round(span, 1), "max_gap": round(max_gap, 1)}


# ── 小限法 (Annual Profections) ──

def annual_profections(natal_asc_lon, birth_year, target_year):
    """
    古典小限法：本命 ASC 每年推进 1 个星座。
    第 1 年 = 出生年（0 岁），第 2 年 = 出生年+1（1 岁）...
    返回当年的小限星座 + 主星（Lord of the Year）。
    """
    age = target_year - birth_year
    # 本命 ASC 星座序号（0=Aries）
    natal_sign_idx = int(natal_asc_lon / 30)
    # 0 岁 = 本命 ASC 星座，1 岁 = 下一个... age 岁 = natal_sign_idx + age
    profection_sign_idx = (natal_sign_idx + age) % 12
    profection_sign = SIGNS[profection_sign_idx]
    loty = TRAD_RULER.get(profection_sign, "未知")

    return {
        "age": age,
        "profection_sign": profection_sign,
        "lord_of_year": loty,
        "natal_asc_sign": SIGNS[natal_sign_idx],
    }


# ═══════════════════════════════════════════════════════════
#  格式化输出
# ═══════════════════════════════════════════════════════════

def format_result(r):
    """把计算结果格式化为可读文本。"""
    lines = []
    p = r["planets"]
    e = r["extra"]

    lines.append("═══ 日返盘完整数据（扩展版） ═══")
    lines.append(f"\n回归时刻：{r['sr_utc']}")
    lines.append(f"精度偏差：{r['deviation_arcsec']:.2f} 角秒")

    # 行星
    lines.append("\n── 日返行星 ──")
    for pid in PLANET_IDS:
        if pid in p:
            pl = p[pid]
            rx = " ℞" if pl["retro"] else ""
            lines.append(f"  {PLANET_NAMES.get(pid, f'ID{pid}'):6s}  {pl['sign']:8s} {pl['lon']%30:5.2f}°  第{pl['house']}宫{rx}")

    # 四轴
    lines.append("\n── 日返四轴（居住地）──")
    ax = r["axes"]
    lines.append(f"  ASC ↑  {sign_str(ax['asc'])}")
    lines.append(f"  MC  ↑  {sign_str(ax['mc'])}")
    lines.append(f"  DSC ↓  {sign_str(ax['dsc'])}")
    lines.append(f"  IC  ↓  {sign_str(ax['ic'])}")

    # ====== 扩展算法输出 ======

    # 月相
    mp = e["moon_phase"]
    lines.append(f"\n── 月相（Rudhyar 八分法）──")
    lines.append(f"  日月夹角 {mp['angle']}° → 第{mp['phase_num']}阶段 {mp['phase_name']}")
    lines.append(f"  阶段含义：{mp['meaning_hint']}")

    # 太阳宫位 + 月亮宫位/元素
    lines.append(f"\n── 年度焦点 ──")
    lines.append(f"  SR太阳落在 SR 第{e['sun_house']}宫 → 年度注意力核心场域")
    lines.append(f"  SR月亮落在 SR 第{e['moon_house_element']['house']}宫 " +
                 f"({e['moon_house_element']['sign']}/{e['moon_house_element']['element']}元素) → 情绪易感领域")

    # ASC 守护星
    ar = e["asc_ruler"]
    rx_mark = " ℞" if ar.get("ruler_retro") else ""
    lines.append(f"\n── ASC 守护星 ──")
    lines.append(f"  SR ASC = {ar['asc_sign']} → 守护星 = {ar['ruler']}{rx_mark}")
    lines.append(f"  守护星在 SR {ar['ruler_sign']} 第{ar['ruler_house']}宫 → 全年驱动力来源")

    # 角宫行星
    lines.append(f"\n── 角宫行星（orb<8°）──")
    ang = e["angular_planets"]
    if ang:
        for a in ang:
            lines.append(f"  {a['planet']:6s} 合 {a['axis']:6s}  orb={a['orb']}°  在SR第{a['house']}宫")
    else:
        lines.append("  无角宫行星")

    # 逆行行星
    lines.append(f"\n── 逆行行星 ──")
    retro = e["retrograde_planets"]
    if retro:
        for rx in retro:
            lines.append(f"  {rx['planet']:6s}  {rx['sign']:8s} 第{rx['house']}宫  速度{rx['speed_deg_day']}°/天")
    else:
        lines.append("  无逆行行星")

    # 度数重合
    lines.append(f"\n── 度数重合（SR 合本命 orb<3°）──")
    dc = e["degree_contacts"]
    if dc:
        for c in dc:
            lines.append(f"  [{c['type']}] {c['sr']} 合 {c['natal']}  orb={c['orb']}°")
    else:
        lines.append("  无度数重合")

    # 默冬周期
    mc = e["metonic_cycle"]
    if mc["is_metonic_age"]:
        lines.append(f"\n── 默冬周期 ──")
        lines.append(f"  当前年龄 {mc['age']} 岁 → 是默冬节点年")
        lines.append(f"  SR月亮 {mc.get('sr_moon_sign','?')} vs 本命月亮 {mc.get('natal_moon_sign','?')} 差 {mc.get('moon_distance','?')}°")
        if mc.get("is_metonic_return"):
            lines.append(f"  ✅ 是默冬月亮回归年！情感记忆被唤醒。")

    # 整体格局
    cs = e["chart_shape"]
    lines.append(f"\n── 整体格局 ──")
    lines.append(f"  {cs['shape']}（行星跨度 {cs['span']}°，最大间隙 {cs['max_gap']}°）")

    # 小限法
    ap = e["annual_profections"]
    lines.append(f"\n── 小限法 ──")
    lines.append(f"  本命 ASC {ap['natal_asc_sign']} → {ap['age']}岁推进到 {ap['profection_sign']}")
    lines.append(f"  年度主星（Lord of the Year）= {ap['lord_of_year']}")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════
#  主入口
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    # 姐姐本命：1976-02-01 09:50 CST = 01:50 UTC, 北京
    natal_utc = swe.julday(1976, 2, 1, 1.833333)  # 09:50 CST = 01:50 UTC
    result = compute_solar_return_full(
        natal_utc_jd=natal_utc,
        natal_lat=39.9042,
        natal_lng=116.4074,
        birth_year=1976, birth_month=2, birth_day=1,
        target_year=2026,
        residence_lat=39.9042,
        residence_lng=116.4074,
    )

    print(format_result(result))

    # 也输出 JSON 方便调试
    import json
    print("\n\n── JSON（扩展字段）──")
    print(json.dumps(result["extra"], ensure_ascii=False, indent=2))
