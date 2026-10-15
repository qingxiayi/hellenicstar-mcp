"""Render the Mini Program's Saturn-Jupiter cycles timeline as an SVG / PNG image.

Faithfully implements the layout, axes, waveforms, nodes, and collision-avoidance
labels from miniprogram/utils/transit_wave.js with clean top banner and ruler spacing.
"""

from __future__ import annotations

import html
import math
from typing import Any, Mapping


def _esc(val: object) -> str:
    return html.escape(str(val if val is not None else ""))


def render_transit_wave_svg(
    report: Mapping[str, Any],
    *,
    width: int = 1200,
    height: int = 660,
    birth_year: int | None = None,
    start_age: float | None = 0.0,
    end_age: float | None = None,
    person_name: str | None = None,
) -> str:
    W = float(width)
    H = float(height)

    all_sat = [e for e in report.get("saturn_events", []) if e.get("age_years") is not None]
    all_jup = [e for e in report.get("jupiter_events", []) if e.get("age_years") is not None]

    report_max_age = float(report.get("range", {}).get("max_age", 80) or 80)
    min_age = max(0.0, float(start_age if start_age is not None else 0.0))
    max_age = float(end_age) if end_age is not None else report_max_age
    if max_age <= min_age:
        max_age = report_max_age

    sat_events = [e for e in all_sat if min_age <= float(e["age_years"]) <= max_age]
    jup_events = [e for e in all_jup if min_age <= float(e["age_years"]) <= max_age]

    cur = report.get("current", {})
    cur_age = float(cur["as_of_age"]) if cur.get("as_of_age") is not None else None

    if birth_year is None:
        ctx = report.get("birth_context", {})
        if ctx and "civil_dt" in ctx:
            try:
                birth_year = int(str(ctx["civil_dt"])[:4])
            except (ValueError, TypeError):
                pass
        if birth_year is None:
            natal = report.get("natal", {})
            if natal and "civil_datetime" in natal:
                try:
                    birth_year = int(str(natal["civil_datetime"])[:4])
                except (ValueError, TypeError):
                    pass

    # 布局几何划分
    # 顶部工具栏：0 ~ 46px
    HEADER_H = 46.0
    # 标尺区域：48 ~ 92px
    RULER_TOP = 52.0
    RULER_BOTTOM = 92.0
    # 波浪舞台：
    PL = 88.0
    PR = 32.0
    IW = max(1.0, W - PL - PR)

    # 三条轴的 Y 坐标
    YMC = 165.0
    YMID = 360.0
    YIC = 555.0

    SAT_COL = "#1c607e"
    JUP_COL = "#d0a44d"
    BG = "#f8f7f4"
    AXLINE = "#d5d5d5"
    TXT = "#6a7378"
    TXTDIM = "#9aa5aa"
    FONT = "system-ui, -apple-system, 'Noto Sans CJK SC', 'Noto Sans CJK', 'PingFang SC', sans-serif"

    AY = {"MC": YMC, "ASC": YMID, "Asc": YMID, "DSC": YMID, "Dsc": YMID, "IC": YIC}
    age_span = max(1.0, max_age - min_age)

    def x_of(age: float) -> float:
        bounded = min(max(float(age or 0.0), min_age), max_age)
        return PL + (bounded - min_age) / age_span * IW

    def y_of(axis: str) -> float:
        return AY.get(axis, YMID)

    svg_parts: list[str] = []
    svg_parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{int(W)}" height="{int(H)}" '
        f'viewBox="0 0 {int(W)} {int(H)}">'
    )
    svg_parts.append(f'<rect width="{int(W)}" height="{int(H)}" fill="{BG}"/>')

    # 1. 顶部独立标题与图例栏 (0 ~ 46px)
    svg_parts.append(f'<rect x="0" y="0" width="{int(W)}" height="{int(HEADER_H)}" fill="#ffffff" fill-opacity="0.75"/>')
    svg_parts.append(f'<line x1="0" y1="{HEADER_H:.1f}" x2="{int(W)}" y2="{HEADER_H:.1f}" stroke="#e5e5e5" stroke-width="1"/>')

    title_text = f"{person_name} · 土木流年全景时间轴" if person_name else "土木流年 · 全景时间轴"
    range_text = f"0 – {int(max_age)} 岁"
    svg_parts.append(
        f'<text x="{PL:.1f}" y="28" font-family="{FONT}" font-size="16" '
        f'font-weight="700" fill="#26383f">{_esc(title_text)}</text>'
    )
    svg_parts.append(
        f'<text x="{PL + len(title_text)*16 + 18:.1f}" y="27" font-family="{FONT}" font-size="12" '
        f'fill="{TXTDIM}">({range_text})</text>'
    )

    # 图例 (右上角)
    leg_x = W - PR
    # 现在
    svg_parts.append(
        f'<line x1="{leg_x-55:.1f}" y1="23" x2="{leg_x-32:.1f}" y2="23" '
        f'stroke="{JUP_COL}" stroke-width="2" stroke-dasharray="4,3"/>'
        f'<text x="{leg_x-24:.1f}" y="27" font-family="{FONT}" font-size="12" fill="{TXT}">现在</text>'
    )
    # 木星
    svg_parts.append(
        f'<circle cx="{leg_x-130:.1f}" cy="23" r="5" fill="{JUP_COL}"/>'
        f'<text x="{leg_x-118:.1f}" y="27" font-family="{FONT}" font-size="12" fill="{TXT}">木星</text>'
    )
    # 土星
    svg_parts.append(
        f'<circle cx="{leg_x-205:.1f}" cy="23" r="6" fill="{SAT_COL}"/>'
        f'<text x="{leg_x-193:.1f}" y="27" font-family="{FONT}" font-size="12" fill="{TXT}">土星</text>'
    )

    # 2. 年龄与年份标尺网格 (RULER_TOP=52 ~ RULER_BOTTOM=92)
    start_grid = int(math.ceil(min_age / 5.0) * 5)
    for age in range(start_grid, int(max_age) + 1, 5):
        x = x_of(age)
        major = (age % 10 == 0)
        line_color = "rgba(28,96,126,0.14)" if major else "rgba(28,96,126,0.06)"
        line_width = 1.0 if major else 0.5
        # 竖向网格贯穿舞台
        svg_parts.append(
            f'<line x1="{x:.1f}" y1="{RULER_BOTTOM:.1f}" x2="{x:.1f}" y2="{YIC + 25:.1f}" '
            f'stroke="{line_color}" stroke-width="{line_width}"/>'
        )
        if major:
            if birth_year:
                svg_parts.append(
                    f'<text x="{x:.1f}" y="68" text-anchor="middle" '
                    f'font-family="{FONT}" font-size="11" font-weight="600" fill="{TXT}">{birth_year + age}年</text>'
                )
            age_y = 83 if birth_year else 72
            svg_parts.append(
                f'<text x="{x:.1f}" y="{age_y}" text-anchor="middle" '
                f'font-family="{FONT}" font-size="10" fill="{TXTDIM}">{age}岁</text>'
            )

    # 3. 三条水平基准轴：MC、ASC / DSC、IC
    axes_data = [(YMC, "MC"), (YMID, "ASC / DSC"), (YIC, "IC")]
    for y, label in axes_data:
        svg_parts.append(
            f'<line x1="{PL - 8:.1f}" y1="{y:.1f}" x2="{W - PR:.1f}" y2="{y:.1f}" '
            f'stroke="{AXLINE}" stroke-width="1.5"/>'
        )
        svg_parts.append(
            f'<text x="{PL - 14:.1f}" y="{y + 4:.1f}" text-anchor="end" '
            f'font-family="{FONT}" font-size="12" font-weight="700" fill="#26383f">{label}</text>'
        )

    # 4. 连续折线连线 (Saturn & Jupiter)
    def make_connections(nodes: list[dict], color: str, stroke_width: float):
        sorted_nodes = sorted(nodes, key=lambda n: float(n["age_years"]))
        for i in range(len(sorted_nodes) - 1):
            a = sorted_nodes[i]
            b = sorted_nodes[i + 1]
            if float(b["age_years"]) < min_age or float(a["age_years"]) > max_age:
                continue
            x1 = x_of(float(a["age_years"]))
            y1 = y_of(str(a.get("axis", "")))
            x2 = x_of(float(b["age_years"]))
            y2 = y_of(str(b.get("axis", "")))
            svg_parts.append(
                f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
                f'stroke="{color}" stroke-width="{stroke_width:.1f}" stroke-linecap="round"/>'
            )

    make_connections(all_sat, SAT_COL, 3.2)
    make_connections(all_jup, JUP_COL, 2.4)

    # 5. “现在” 竖虚线
    if cur_age is not None and min_age <= cur_age <= max_age:
        cx = x_of(cur_age)
        svg_parts.append(
            f'<line x1="{cx:.1f}" y1="{RULER_BOTTOM:.1f}" x2="{cx:.1f}" y2="{YIC + 25:.1f}" '
            f'stroke="{JUP_COL}" stroke-width="1.8" stroke-dasharray="6,4"/>'
        )
        # “现在”小标签在标尺下方
        svg_parts.append(
            f'<rect x="{cx - 28:.1f}" y="{RULER_BOTTOM + 2:.1f}" width="56" height="18" rx="9" '
            f'fill="{JUP_COL}" fill-opacity="0.15" stroke="{JUP_COL}" stroke-width="1"/>'
        )
        svg_parts.append(
            f'<text x="{cx:.1f}" y="{RULER_BOTTOM + 15:.1f}" text-anchor="middle" '
            f'font-family="{FONT}" font-size="10" font-weight="700" fill="{JUP_COL}">'
            f'现在 {cur_age:.1f}岁</text>'
        )

    # 6. 节点圆点绘制
    def draw_node_points(nodes: list[dict], color: str, radius: float):
        sorted_nodes = sorted(nodes, key=lambda n: float(n["age_years"]))
        for node in sorted_nodes:
            x = x_of(float(node["age_years"]))
            y = y_of(str(node.get("axis", "")))
            # 外层浅光环
            svg_parts.append(
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius + 7:.1f}" fill="{color}" opacity="0.16"/>'
            )
            # 内层实心圆
            svg_parts.append(
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius:.1f}" fill="{color}" '
                f'stroke="#ffffff" stroke-width="2"/>'
            )

    draw_node_points(sat_events, SAT_COL, 6.0)
    draw_node_points(jup_events, JUP_COL, 5.0)

    # 7. 节点标签与防重叠避让
    label_boxes: list[dict] = []
    CARD_PAD_X = 3.0
    CARD_PAD_Y = 2.0
    CARD_STROKE = 0.8

    def overlaps(a: dict, b: dict) -> bool:
        # Compare the painted cards, including padding and stroke, rather than
        # only the inner text boxes. Leave a further 4px gap between cards.
        gap_x = 2 * CARD_PAD_X + CARD_STROKE + 4.0
        gap_y = 2 * CARD_PAD_Y + CARD_STROKE + 4.0
        return (
            a["left"] < b["right"] + gap_x
            and a["right"] + gap_x > b["left"]
            and a["top"] < b["bottom"] + gap_y
            and a["bottom"] + gap_y > b["top"]
        )

    def find_label_position(x: float, y: float, r: float, width: float, height: float, preferred_above: bool) -> dict:
        shifts = [0.0]
        max_shift_steps = int(math.ceil(W / max(width * 0.72, 1.0)))
        for step in range(1, max_shift_steps + 1):
            shifts.extend([-0.72 * step, 0.72 * step])
        sides = [preferred_above, not preferred_above]
        candidates = []
        for above in sides:
            for lane in [0, 1, 2, 3]:
                for factor in shifts:
                    candidates.append({"above": above, "lane": lane, "factor": factor})

        for cand in candidates:
            center_x = max(PL + width / 2.0, min(W - PR - width / 2.0, x + cand["factor"] * width))
            edge_y = y - r - 6.0 if cand["above"] else y + r + 6.0
            lane_offset = cand["lane"] * (height + 4.0)
            top = edge_y - height - lane_offset if cand["above"] else edge_y + lane_offset
            box = {
                "left": center_x - width / 2.0,
                "right": center_x + width / 2.0,
                "top": top,
                "bottom": top + height,
                "center_x": center_x,
                "above": cand["above"],
            }
            if box["left"] < PL or box["right"] > W - PR or box["top"] < RULER_BOTTOM + 22.0 or box["bottom"] > H - 8.0:
                continue
            if not any(overlaps(box, b) for b in label_boxes):
                return box

        # 兜底
        above = preferred_above
        center_x = max(PL + width / 2.0, min(W - PR - width / 2.0, x))
        top = y - r - 6.0 - height if above else y + r + 6.0
        top = max(RULER_BOTTOM + 22.0, min(H - 8.0 - height, top))
        return {
            "left": center_x - width / 2.0,
            "right": center_x + width / 2.0,
            "top": top,
            "bottom": top + height,
            "center_x": center_x,
            "above": above,
        }

    def draw_node_labels(nodes: list[dict], color: str, radius: float, planet: str):
        sorted_nodes = sorted(nodes, key=lambda n: float(n["age_years"]))
        for index, node in enumerate(sorted_nodes):
            x = x_of(float(node["age_years"]))
            axis = str(node.get("axis", ""))
            y = y_of(axis)
            r = radius

            if axis == "MC":
                above = True
            elif axis == "IC":
                above = False
            else:
                prev = sorted_nodes[index - 1] if index > 0 else None
                above = (y_of(str(prev.get("axis", ""))) > YMID) if prev else True

            local_date = str(node.get("local_date") or node.get("date") or "")
            year_text = local_date[:4] + "年" if len(local_date) >= 4 else ""
            age_val = float(node.get("age_years", 0))
            age_text = f"{age_val:.1f}岁"

            label_w = max(len(year_text) * 8.5, len(age_text) * 7.5, 48.0)
            label_h = 28.0

            box = find_label_position(x, y, r, label_w, label_h, above)
            label_boxes.append(box)

            # 引导细线
            edge_y = y - r if box["above"] else y + r
            target_y = box["bottom"] if box["above"] else box["top"]
            svg_parts.append(
                f'<line x1="{x:.1f}" y1="{edge_y:.1f}" x2="{box["center_x"]:.1f}" y2="{target_y:.1f}" '
                f'stroke="{color}" stroke-width="1.0" opacity="0.4"/>'
            )

            # 背景小卡片
            svg_parts.append(
                f'<rect x="{box["left"]-CARD_PAD_X:.1f}" y="{box["top"]-CARD_PAD_Y:.1f}" '
                f'width="{label_w+2*CARD_PAD_X:.1f}" height="{label_h+2*CARD_PAD_Y:.1f}" '
                f'rx="4" fill="{BG}" fill-opacity="0.96" stroke="{AXLINE}" stroke-width="{CARD_STROKE}"/>'
            )

            # 年份与年龄文字
            if year_text:
                svg_parts.append(
                    f'<text x="{box["center_x"]:.1f}" y="{box["top"]+11:.1f}" text-anchor="middle" '
                    f'font-family="{FONT}" font-size="11" font-weight="700" fill="{color}">'
                    f'{year_text}</text>'
                )
            svg_parts.append(
                f'<text x="{box["center_x"]:.1f}" y="{box["top"]+23:.1f}" text-anchor="middle" '
                f'font-family="{FONT}" font-size="10" fill="{TXTDIM}">{age_text}</text>'
            )

    draw_node_labels(sat_events, SAT_COL, 6.0, "saturn")
    draw_node_labels(jup_events, JUP_COL, 5.0, "jupiter")

    svg_parts.append("</svg>")
    return "\n".join(svg_parts)


def _svg_to_png_rect(svg: str, width: int = 1200, height: int = 660) -> bytes | None:
    import shutil
    import subprocess
    rsvg = shutil.which("rsvg-convert")
    if not rsvg:
        return None
    try:
        proc = subprocess.run(
            [rsvg, "-w", str(width), "-h", str(height), "--format=png"],
            input=svg.encode("utf-8"),
            capture_output=True,
            timeout=30,
        )
        if proc.returncode == 0 and proc.stdout:
            return proc.stdout
    except (subprocess.SubprocessError, OSError):
        pass
    return None

