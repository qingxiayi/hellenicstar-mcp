"""希腊星智 · 双圈星盘 SVG（内圈本命 / 外圈行运或推运）。

复用 chart_svg 的字形、色板与行星避让逻辑，只重新安排半径分层：
黄道环 → 外圈天体 → 分隔环 → 内圈天体 → 宫位环 → 跨盘相位。
"""

import math

from services.chart_svg import (
    ASP_COL, CHART_PALETTE, CX, CY, D2R, ELEMENTS, ELEM_GRADS, ELEM_RING_COLORS,
    PLANET_BY_ID, PLANET_COLLISION, Rout, Rzod, SIGNS, SYM_FONT,
    _label_box, _planet_ring_display_angles, _svg_pluto_glyph, norm,
)

R_OUTER_GLYPH = 216
R_OUTER_DEGREE = 197
R_DIVIDER = 184
R_INNER_GLYPH = 158
R_INNER_DEGREE = 139
R_HOUSE = 118
R_HOUSE_NUMBER = 105
R_HUB = 95
GLYPH_SIZE = 23
GLYPH_SCALE = GLYPH_SIZE / 28.0

AXES = (("asc", "ASC"), ("mc", "MC"), ("dsc", "DSC"), ("ic", "IC"))


def _pt(angle, radius):
    rad = angle * D2R
    return CX + radius * math.cos(rad), CY + radius * math.sin(rad)


def _degree_label(lon, retrograde):
    degree = int(lon % 30)
    minute = int(round((lon % 30 - degree) * 60))
    if minute == 60:
        degree, minute = degree + 1, 0
    return f"{degree}\u00b0{minute:02d}'" + (" \u211e" if retrograde else "")


def _ring_entries(planets, glyph_radius, degree_radius):
    """Build declustering entries for one planet ring."""
    entries = []
    for key, value in planets.items():
        if key not in PLANET_BY_ID or value is None:
            continue
        lon = value.get("lon") if isinstance(value, dict) else value
        if lon is None:
            continue
        lon = norm(float(lon))
        retrograde = bool(isinstance(value, dict) and value.get("retrograde"))
        width, height = PLANET_COLLISION.get(key, (20, 22))
        width, height = width * GLYPH_SCALE, height * GLYPH_SCALE
        # 度数串比字形宽，避让必须按它的实际宽度算，否则两颗邻星的度数会压在一起。
        label_width = len(_degree_label(lon, retrograde)) * 5.9 + 4

        def box_builder(angle, w=width, h=height, lw=label_width,
                        gr=glyph_radius, dr=degree_radius):
            return [_label_box(angle, gr, w, h), _label_box(angle, dr, lw, 13)]

        entries.append({"key": key, "lon": lon, "box_builder": box_builder,
                        "retrograde": retrograde})
    return entries


def _draw_ring(entries, angles, asc_lon, glyph_radius, degree_radius,
               lead_radius, dim=False):
    out = ""
    for entry in entries:
        key = entry["key"]
        info = PLANET_BY_ID[key]
        angle = angles[key]
        true_angle = norm(180 - (entry["lon"] - asc_lon))
        color = info["color"]
        opacity = 0.72 if dim else 1.0
        # 连到真实度数的细引线：避让后字形会偏离真实位置，必须标回去。
        tx, ty = _pt(true_angle, lead_radius)
        lx, ly = _pt(angle, glyph_radius + GLYPH_SIZE * 0.55)
        out += (f'<line x1="{tx:.1f}" y1="{ty:.1f}" x2="{lx:.1f}" y2="{ly:.1f}" '
                f'stroke="{color}" stroke-width="0.5" opacity="0.4"/>\n')
        gx, gy = _pt(angle, glyph_radius)
        if key == "pluto":
            out += _svg_pluto_glyph(gx, gy, GLYPH_SIZE, color)
        else:
            out += (f'<text x="{gx:.1f}" y="{gy:.1f}" font-family="{SYM_FONT}" '
                    f'font-size="{GLYPH_SIZE}" fill="{color}" opacity="{opacity}" '
                    f'text-anchor="middle" dominant-baseline="central">{info["sym"]}</text>\n')
        dx, dy = _pt(angle, degree_radius)
        label = _degree_label(entry["lon"], entry["retrograde"])
        out += (f'<text x="{dx:.1f}" y="{dy:.1f}" font-size="10.5" fill="{color}" '
                f'opacity="{0.78 if dim else 0.92}" text-anchor="middle" '
                f'dominant-baseline="central">{label}</text>\n')
    return out


def generate_biwheel_svg(*, inner_planets, outer_planets, cusps, asc_lon, mc_lon,
                         cross_aspects=(), system="placidus",
                         inner_label="", outer_label="", outer_axes=None):
    """Render a two-ring chart: natal inside, directed or transiting outside.

    inner_planets / outer_planets: {planet_id: {"lon": float, "retrograde": bool}}
    cusps: twelve natal house cusps; aspects are cross-chart only.
    """
    if system not in ("placidus", "whole_sign"):
        system = "placidus"
    asc_lon = norm(float(asc_lon))

    def sd(lon):
        return norm(180 - norm(lon - asc_lon))

    s = '<svg id="biwheel" viewBox="6 6 588 588" xmlns="http://www.w3.org/2000/svg">\n'
    inner_stop = round((Rzod / Rout) * 100, 1)
    s += f'''<defs>
<radialGradient id="elemFire" cx="{CX}" cy="{CY}" r="{Rout}" gradientUnits="userSpaceOnUse">
  <stop offset="{inner_stop}%" stop-color="rgba(199,93,80,0.025)"/>
  <stop offset="100%" stop-color="rgba(199,93,80,0.105)"/>
</radialGradient>
<radialGradient id="elemEarth" cx="{CX}" cy="{CY}" r="{Rout}" gradientUnits="userSpaceOnUse">
  <stop offset="{inner_stop}%" stop-color="rgba(150,123,74,0.025)"/>
  <stop offset="100%" stop-color="rgba(150,123,74,0.105)"/>
</radialGradient>
<radialGradient id="elemAir" cx="{CX}" cy="{CY}" r="{Rout}" gradientUnits="userSpaceOnUse">
  <stop offset="{inner_stop}%" stop-color="rgba(79,130,164,0.025)"/>
  <stop offset="100%" stop-color="rgba(79,130,164,0.105)"/>
</radialGradient>
<radialGradient id="elemWater" cx="{CX}" cy="{CY}" r="{Rout}" gradientUnits="userSpaceOnUse">
  <stop offset="{inner_stop}%" stop-color="rgba(63,127,122,0.025)"/>
  <stop offset="100%" stop-color="rgba(63,127,122,0.105)"/>
</radialGradient>
</defs>
<rect x="6" y="6" width="588" height="588" fill="{CHART_PALETTE["paper"]}"/>
'''

    for i in range(12):
        a1, a2 = sd(i * 30), sd(i * 30 + 30)
        ox1, oy1 = _pt(a1, Rout); ox2, oy2 = _pt(a2, Rout)
        ix1, iy1 = _pt(a1, Rzod); ix2, iy2 = _pt(a2, Rzod)
        s += (f'<path d="M{ox1:.1f},{oy1:.1f} A{Rout},{Rout} 0 0,0 {ox2:.1f},{oy2:.1f} '
              f'L{ix2:.1f},{iy2:.1f} A{Rzod},{Rzod} 0 0,1 {ix1:.1f},{iy1:.1f}Z" '
              f'fill="{ELEM_GRADS[ELEMENTS[i]]}" stroke="none"/>\n')
        mx, my = _pt(sd(i * 30 + 15), (Rout + Rzod) / 2)
        s += (f'<text x="{mx:.1f}" y="{my:.1f}" font-family="{SYM_FONT}" font-size="19" '
              f'fill="{ELEM_RING_COLORS[ELEMENTS[i]]}" text-anchor="middle" '
              f'dominant-baseline="central">{SIGNS[i]}</text>\n')
        lx1, ly1 = _pt(a1, Rzod); lx2, ly2 = _pt(a1, Rout)
        s += (f'<line x1="{lx1:.1f}" y1="{ly1:.1f}" x2="{lx2:.1f}" y2="{ly2:.1f}" '
              f'stroke="{CHART_PALETTE["blue_soft"]}" stroke-width="0.45" stroke-opacity="0.46"/>\n')

    for d in range(360):
        if d % 30 == 0:
            continue
        a = sd(d)
        length, col, sw, op = (4.8, CHART_PALETTE["ink"], 0.75, 0.9) if d % 10 == 0 else \
                              (3.2, CHART_PALETTE["blue_soft"], 0.55, 0.76) if d % 5 == 0 else \
                              (1.6, CHART_PALETTE["grid"], 0.4, 0.82)
        x1, y1 = _pt(a, Rzod); x2, y2 = _pt(a, Rzod + length)
        s += (f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
              f'stroke="{col}" stroke-width="{sw}" opacity="{op}"/>\n')

    for radius, width, color, opacity in (
        (Rout, 1.45, CHART_PALETTE["ink"], 1.0),
        (Rzod, 0.78, CHART_PALETTE["ink"], 0.72),
        (R_DIVIDER, 0.9, CHART_PALETTE["blue_soft"], 0.75),
        (R_HOUSE, 0.58, CHART_PALETTE["grid"], 0.82),
        (R_HUB, 0.78, CHART_PALETTE["blue_soft"], 0.9),
    ):
        s += (f'<circle cx="{CX}" cy="{CY}" r="{radius}" fill="none" stroke="{color}" '
              f'stroke-width="{width}" opacity="{opacity}"/>\n')

    house_starts = ([int(asc_lon // 30) * 30 + i * 30 for i in range(12)]
                    if system == "whole_sign" else [norm(float(c)) for c in cusps])
    for index, cusp in enumerate(house_starts):
        a = sd(cusp)
        x1, y1 = _pt(a, R_DIVIDER); x2, y2 = _pt(a, R_HUB)
        s += (f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
              f'stroke="{CHART_PALETTE["grid"]}" stroke-width="0.6" opacity="0.8"/>\n')
        nxt = house_starts[(index + 1) % 12]
        span = norm(nxt - cusp) or 30.0
        nx, ny = _pt(sd(cusp + span / 2), R_HOUSE_NUMBER)
        s += (f'<text x="{nx:.1f}" y="{ny:.1f}" font-size="11" '
              f'fill="{CHART_PALETTE["blue_soft"]}" text-anchor="middle" '
              f'dominant-baseline="central">{index + 1}</text>\n')

    axis_lons = {"asc": asc_lon, "mc": norm(float(mc_lon)),
                 "dsc": norm(asc_lon + 180), "ic": norm(float(mc_lon) + 180)}
    for key, label in AXES:
        a = sd(axis_lons[key])
        x1, y1 = _pt(a, R_DIVIDER); x2, y2 = _pt(a, R_HUB)
        s += (f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
              f'stroke="{CHART_PALETTE["axis"]}" stroke-width="1.1" opacity="0.9"/>\n')
        tx, ty = _pt(a, R_HOUSE + 11)
        s += (f'<text x="{tx:.1f}" y="{ty:.1f}" font-size="11.5" font-weight="600" '
              f'fill="{CHART_PALETTE["axis"]}" text-anchor="middle" '
              f'dominant-baseline="central">{label}</text>\n')

    # 次限盘有独立推进的四轴；仅调用者明确传入时绘制，其他双圈盘保持原样。
    if outer_axes:
        for key, label in AXES:
            if key not in outer_axes:
                continue
            a = sd(float(outer_axes[key]))
            x1, y1 = _pt(a, R_DIVIDER - 2)
            x2, y2 = _pt(a, R_DIVIDER + 9)
            tx, ty = _pt(a, R_DIVIDER - 12)
            s += (f'<line class="progressed-axis" x1="{x1:.1f}" y1="{y1:.1f}" '
                  f'x2="{x2:.1f}" y2="{y2:.1f}" stroke="{CHART_PALETTE["axis"]}" '
                  f'stroke-width="1.5"/>\n')
            s += (f'<text class="progressed-axis-label" x="{tx:.1f}" y="{ty:.1f}" '
                  f'font-size="9" font-weight="600" fill="{CHART_PALETTE["axis"]}" '
                  f'text-anchor="middle" dominant-baseline="central">次{label}</text>\n')

    for aspect in cross_aspects or ():
        lon1 = aspect.get("outer_lon")
        lon2 = aspect.get("inner_lon")
        if lon1 is None or lon2 is None:
            continue
        x1, y1 = _pt(sd(float(lon1)), R_HUB)
        x2, y2 = _pt(sd(float(lon2)), R_HUB)
        color = ASP_COL.get(int(round(float(aspect.get("angle", 0)))), CHART_PALETTE["grid"])
        s += (f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
              f'stroke="{color}" stroke-width="0.85" opacity="0.62"/>\n')

    inner_entries = _ring_entries(inner_planets, R_INNER_GLYPH, R_INNER_DEGREE)
    outer_entries = _ring_entries(outer_planets, R_OUTER_GLYPH, R_OUTER_DEGREE)
    s += _draw_ring(inner_entries,
                    _planet_ring_display_angles(inner_entries, asc_lon), asc_lon,
                    R_INNER_GLYPH, R_INNER_DEGREE, R_DIVIDER - 2, dim=True)
    s += _draw_ring(outer_entries,
                    _planet_ring_display_angles(outer_entries, asc_lon), asc_lon,
                    R_OUTER_GLYPH, R_OUTER_DEGREE, Rzod - 2)

    # 图例放在圆外的左上角：中心是跨盘相位线的地盘，压上文字会看不清。
    if inner_label or outer_label:
        for index, (text, color) in enumerate(
            ((outer_label, CHART_PALETTE["ink"]), (inner_label, CHART_PALETTE["blue_soft"]))
        ):
            if not text:
                continue
            y = 34 + index * 17
            s += (f'<circle cx="30" cy="{y - 4}" r="3.4" fill="{color}"/>\n'
                  f'<text x="41" y="{y}" font-size="12" fill="{CHART_PALETTE["ink"]}" '
                  f'opacity="0.85">{text}</text>\n')
    return s + '</svg>\n'

