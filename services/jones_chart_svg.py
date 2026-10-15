"""Draw the Mini Program's Jones distribution ring from its own JS geometry."""

from __future__ import annotations

import html
import math

from services.chart_svg import SYM_FONT


SIZE = 720
RING_LEFT = 70
RING_TOP = 96
RING_SIZE = 580
CX = RING_LEFT + RING_SIZE / 2
CY = RING_TOP + RING_SIZE / 2
BLUE = "#1C607E"
GOLD = "#B88B34"
FONT = "'Noto Sans CJK SC','Noto Sans CJK','PingFang SC',sans-serif"


def _text(value: object) -> str:
    return html.escape(str(value if value is not None else ""))


def _xy(x: object, y: object) -> tuple[float, float]:
    return (RING_LEFT + RING_SIZE * float(x) / 100,
            RING_TOP + RING_SIZE * float(y) / 100)


def _polar(angle: float, radius: float) -> tuple[float, float]:
    rad = math.radians(angle)
    return CX + radius * math.cos(rad), CY + radius * math.sin(rad)


def _arc_path(start: float, arc: float, radius: float, *, wedge: bool) -> str:
    steps = max(2, math.ceil(max(0.0, arc) / 3))
    points = [_polar(start + arc * i / steps, radius) for i in range(steps + 1)]
    prefix = f"M {CX:.2f} {CY:.2f} L " if wedge else "M "
    body = " L ".join(f"{x:.2f} {y:.2f}" for x, y in points)
    return prefix + body + (" Z" if wedge else "")


def _pill(x: float, y: float, label: str, *, pole: bool = False) -> str:
    width = max(46, 12 + sum(18 if ord(ch) > 127 else 11 for ch in label))
    fill, stroke, ink = ("#FFF8DC", GOLD, "#80601B") if pole else ("#F9FCFB", BLUE, BLUE)
    return (f'<rect x="{x-width/2:.2f}" y="{y-13:.2f}" width="{width}" height="26" '
            f'rx="13" fill="{fill}" stroke="{stroke}" stroke-width="1"/>'
            f'<text x="{x:.2f}" y="{y+5:.2f}" text-anchor="middle" '
            f'font-family="{FONT}" font-size="16" fill="{ink}">{_text(label)}</text>')


def render_jones_svg(geometry: dict) -> str:
    """Use mini-program point/fan coordinates; this layer only draws pixels."""
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{SIZE}" height="{SIZE}" '
        f'viewBox="0 0 {SIZE} {SIZE}">',
        '<rect width="720" height="720" fill="#FBFDFC"/>',
        f'<text x="360" y="42" text-anchor="middle" font-family="{FONT}" '
        f'font-size="29" font-weight="700" fill="#263D4B">{_text(geometry["pattern_zh"])}</text>',
        f'<text x="360" y="70" text-anchor="middle" font-family="{FONT}" '
        f'font-size="17" fill="{BLUE}">{_text(geometry["pattern_en"])} · '
        f'{_text(geometry["state_label"])}</text>',
        f'<circle cx="{CX}" cy="{CY}" r="{RING_SIZE/2}" fill="#FFFFFF" '
        f'stroke="{BLUE}" stroke-width="2"/>',
        f'<circle cx="{CX}" cy="{CY}" r="{RING_SIZE*.425}" fill="none" '
        f'stroke="{BLUE}" stroke-opacity=".18" stroke-width="1"/>',
        f'<circle cx="{CX}" cy="{CY}" r="{RING_SIZE*.20}" fill="none" '
        f'stroke="{BLUE}" stroke-opacity=".16" stroke-width="1" stroke-dasharray="3 5"/>',
    ]
    for fan in geometry.get("occupiedFans", []):
        if float(fan.get("arc") or 0) <= 0:
            continue
        parts.append(f'<path d="{_arc_path(float(fan["startAngle"]), float(fan["arc"]), RING_SIZE*.33, wedge=True)}" '
                     f'fill="{BLUE}" fill-opacity=".42"/>')
    asc = float(geometry["ascLongitude"])
    for index, lon in enumerate(geometry.get("cusps", [])[:12]):
        angle = (180 - ((float(lon) - asc) % 360)) % 360
        angular = index in (0, 3, 6, 9)
        start = RING_SIZE * (.136 if angular else .30)
        end = RING_SIZE * (.497 if angular else .41)
        x1, y1 = _polar(angle, start)
        x2, y2 = _polar(angle, end)
        parts.append(f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" '
                     f'stroke="{BLUE if angular else "#A9C2CB"}" '
                     f'stroke-width="{2 if angular else 1}"/>')
    gap = geometry.get("importantGap") or {}
    if float(gap.get("arc") or 0) > 0:
        angle = (180 - ((float(gap["start"]) - asc) % 360)) % 360
        arc = float(gap["arc"])
        parts.append(f'<path d="{_arc_path(angle, -arc, RING_SIZE*.32, wedge=False)}" '
                     f'fill="none" stroke="{BLUE}" stroke-opacity=".65" stroke-width="2"/>')
        x, y = _polar(angle - arc / 2, RING_SIZE*.285)
        parts.append(f'<text x="{x:.2f}" y="{y:.2f}" text-anchor="middle" '
                     f'font-family="{FONT}" font-size="17" fill="{BLUE}">{_text(gap.get("label"))}</text>')
    for point in geometry.get("points", []):
        tx, ty = _xy(point["trueX"], point["trueY"])
        x, y = _xy(point["x"], point["y"])
        parts.append(f'<circle cx="{tx:.2f}" cy="{ty:.2f}" r="4" fill="{BLUE}"/>')
        if point.get("moved"):
            parts.append(f'<line x1="{tx:.2f}" y1="{ty:.2f}" x2="{x:.2f}" y2="{y:.2f}" '
                         f'stroke="{BLUE}" stroke-opacity=".5" stroke-width="1"/>')
    parts.append(f'<circle cx="{CX}" cy="{CY}" r="79" fill="#FFFFFF" '
                 f'fill-opacity=".97" stroke="#D4E2E4" stroke-width="1"/>')
    parts.append(f'<text x="{CX}" y="{CY-23}" text-anchor="middle" font-family="{FONT}" '
                 f'font-size="17" fill="{GOLD}">{_text(geometry["family_zh"])}家族</text>')
    parts.append(f'<text x="{CX}" y="{CY+15}" text-anchor="middle" font-family="{FONT}" '
                 f'font-size="33" font-weight="700" fill="#263D4B">{_text(geometry["span_deg"])}°</text>')
    parts.append(f'<text x="{CX}" y="{CY+39}" text-anchor="middle" font-family="{FONT}" '
                 'font-size="14" fill="#677982">占据跨度</text>')
    for pole in geometry.get("bowlPoles", []):
        parts.append(_pill(*_xy(pole["x"], pole["y"]), str(pole["label"]), pole=True))
    for point in geometry.get("points", []):
        x, y = _xy(point["x"], point["y"])
        focus = bool(point.get("focus"))
        radius = 23 if focus else 21
        parts.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{radius}" '
                     f'fill="{GOLD if focus else "#FFFFFF"}" '
                     f'stroke="{GOLD if focus else BLUE}" stroke-width="2"/>')
        parts.append(f'<text x="{x:.2f}" y="{y+10:.2f}" text-anchor="middle" '
                     f'font-family="{SYM_FONT}" font-size="31" '
                     f'fill="{"#FFFFFF" if focus else BLUE}">{_text(point["glyph"])}</text>')
    for axis in geometry.get("axisLabels", []):
        parts.append(_pill(*_xy(axis["x"], axis["y"]), str(axis["label"])))
    parts.append(f'<text x="180" y="702" text-anchor="middle" font-family="{FONT}" '
                 f'font-size="17" fill="#667980">最大空白 {_text(geometry["max_gap_deg"])}°</text>')
    parts.append(f'<text x="540" y="702" text-anchor="middle" font-family="{FONT}" '
                 f'font-size="17" fill="#667980">占据星座 {_text(geometry["occupied_signs"])} / 12</text>')
    parts.append('</svg>')
    return "".join(parts)
