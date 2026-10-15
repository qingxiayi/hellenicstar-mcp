"""
希腊星智 · 星盘圆图 SVG 渲染模块
纯参数化，零硬编码。输入行星数据 → 输出 SVG。
"""

import math

D2R = math.pi / 180
CX, CY = 300, 300
Rout, Rzod, Rbi = 278, 247, 245
Rhouse, RhouseNumber, Rhi = 120, 107, 94
Rpt = 222
# 四轴名称是宫位结构，贴宫号环；精确度/星座/分收在名称外侧的内圈空白带。
# 它们不再占用行星资料圆周，因此行星合轴时两组度数不会叠在一起。
AXIS_NAME_RADIUS = Rhouse
# 度数字号参照 Astro-Seek / Astrodienst 的比例（度数约为行星字形的 0.4~0.45），
# 由 0.375 提到 0.43；同时收紧间距常数，让整条信息栈的径向占位基本不变。
PLANET_DEGREE_RADIUS = Rpt - ((28 + 12.0) / 2 + 2.4)
PLANET_SIGN_RADIUS = PLANET_DEGREE_RADIUS - ((12.0 + 13.5) / 2 + 2.2)
PLANET_MINUTE_RADIUS = PLANET_SIGN_RADIUS - ((13.5 + 8.4) / 2 + 2.0)
AXIS_INFO_RADIUS = 148
AXIS_INFO_TANGENT_GAP = 16

CHART_PALETTE = {
    "paper": "#FBFDFC",
    "ink": "#343A3C",
    "axis": "#5A6268",
    "blue": "#416F91",
    "blue_soft": "#82969C",
    "grid": "#AAB6B7",
    "grid_light": "#D9E1E0",
    "gold": "#C18A35",
    "coral": "#C7594C",
    "teal": "#2F8178",
    "air": "#497FA3",
    "earth": "#92764A",
    "violet": "#765F88",
}

# 行星色板独立于结构色板：结构色（纸、墨、网格、轴）负责“盘的骨架”，
# 行星色负责“盘的内容”。两者混用时，改一个天体的颜色会连带改动环线，
# 这正是旧色板里金星与福点、水星与海王撞色的来源。
PLANET_PALETTE = {
    # 一级：古典七星，饱和度最高，七个色相彼此分明
    "sun": "#C0862B",       # 金
    "moon": "#5C7B8C",      # 银蓝
    "mercury": "#57893F",   # 绿
    "venus": "#2E8A7C",     # 青
    "mars": "#C24C3E",      # 红
    "jupiter": "#8263A6",   # 紫
    "saturn": "#2F4C5F",    # 深蓝，明度最低
    # 二级：外三王与凯龙，降饱和后退一层
    "uranus": "#6E9AA0",
    "neptune": "#6B84AE",
    "pluto": "#8E7A9B",
    "chiron": "#94794F",
    # 三级：计算点，最灰，不与天体争夺注意力。
    # 交点用暖沙灰、福点/精神点用冷灰绿：两组都退到背景层，但彼此仍可分辨，
    # 且都要与月亮的银蓝拉开距离（旧色板里南北交与月亮 ΔE 只有 7）。
    "node": "#95897A",
    "lot": "#6E7C78",
}

PLANET_INFO = [
    # 字号统一 28px，层级完全由颜色承担，分三级：
    #   一级 古典七星  —— 饱和度最高，各自色相分明，是读盘的主角
    #   二级 外三王+凯龙 —— 同色相降饱和，退到七星之后
    #   三级 交点/福点/精神点 —— 灰调最重，是计算点而非天体
    # 旧色板的问题：金星 #2F8178 与福点同色、水星 #497FA3 与海王 #416F91 近乎同色、
    # 木星 #A67932 与北交 #8F733D 同为土金色，密集盘里靠颜色分不出是谁。
    # 现在同级之间保证色相分离，跨级之间保证明度/饱和度分离。
    {"id": "sun", "sym": "☉", "name": "太阳", "color": PLANET_PALETTE["sun"], "size": 28},
    {"id": "moon", "sym": "☽", "name": "月亮", "color": PLANET_PALETTE["moon"], "size": 28},
    {"id": "mercury", "sym": "☿", "name": "水星", "color": PLANET_PALETTE["mercury"], "size": 28},
    {"id": "venus", "sym": "♀", "name": "金星", "color": PLANET_PALETTE["venus"], "size": 28},
    {"id": "mars", "sym": "♂", "name": "火星", "color": PLANET_PALETTE["mars"], "size": 28},
    {"id": "jupiter", "sym": "♃", "name": "木星", "color": PLANET_PALETTE["jupiter"], "size": 28},
    {"id": "saturn", "sym": "♄", "name": "土星", "color": PLANET_PALETTE["saturn"], "size": 28},
    {"id": "uranus", "sym": "♅", "name": "天王星", "color": PLANET_PALETTE["uranus"], "size": 28},
    {"id": "neptune", "sym": "♆", "name": "海王星", "color": PLANET_PALETTE["neptune"], "size": 28},
    {"id": "pluto", "sym": "♇", "name": "冥王星", "color": PLANET_PALETTE["pluto"], "size": 28},
    {"id": "chiron", "sym": "⚷", "name": "凯龙星", "color": PLANET_PALETTE["chiron"], "size": 28},
    {"id": "north_node", "sym": "☊", "name": "北交点", "color": PLANET_PALETTE["node"], "size": 28},
    {"id": "south_node", "sym": "☋", "name": "南交点", "color": PLANET_PALETTE["node"], "size": 28},
    {"id": "fortune", "sym": "⊗", "name": "福点", "color": PLANET_PALETTE["lot"], "size": 28},
    {"id": "spirit", "sym": "Φ", "name": "精神点", "color": PLANET_PALETTE["lot"], "size": 28},
]

PLANET_BY_ID = {p["id"]: p for p in PLANET_INFO}

# 与 Canvas 相同的可见墨迹包围盒；字号统一为 28，但不同字形的实际外廓并不等宽。
PLANET_COLLISION = {
    "sun": (21, 21), "moon": (16, 20), "mercury": (19, 25),
    "venus": (19, 25), "mars": (22, 22), "jupiter": (22, 24),
    "saturn": (18, 22), "uranus": (22, 22), "neptune": (29, 27),
    "pluto": (19, 23), "chiron": (16, 22),
    "north_node": (21, 18), "south_node": (21, 18),
    "fortune": (23, 23), "spirit": (23, 23),
}

SIGNS = ["♈", "♉", "♊", "♋", "♌", "♍", "♎", "♏", "♐", "♑", "♒", "♓"]
ELEMENTS = ["fire", "earth", "air", "water", "fire", "earth", "air", "water", "fire", "earth", "air", "water"]
ELEM_COLORS = {
    "fire": CHART_PALETTE["coral"],
    "earth": CHART_PALETTE["earth"],
    "air": CHART_PALETTE["air"],
    "water": CHART_PALETTE["teal"],
}
# 黄道环是背景语境，行星才是内容。环上的星座字形若用与行星同等饱和度的元素色，
# 两层会争视觉重量（青色既可能是金星也可能是水象星座）。这里给环上的字形一套
# 降饱和的元素色：色相不变，混入墨色约 30%，让行星层自然浮起。
ELEM_RING_COLORS = {
    "fire": "#A85F55",
    "earth": "#7D6A4E",
    "air": "#4F7086",
    "water": "#3E6F6B",
}
ELEM_GRADS = {"fire": "url(#elemFire)", "earth": "url(#elemEarth)", "air": "url(#elemAir)", "water": "url(#elemWater)"}
ASP_COL = {
    # 相位线分三档语义：合相（金褐，中性强调）、柔和相位（青/蓝）、
    # 强硬相位（红系）。四分与对分原本同为 #C7594C，在密集盘里无法区分；
    # 现在对分用更深的砖红，四分保持珊瑚红，同属红系但可分辨。
    0: "#9A7B43",
    60: CHART_PALETTE["air"],
    90: CHART_PALETTE["coral"],
    120: CHART_PALETTE["teal"],
    150: "#8A959B",
    180: "#9E4038",
    30: "#8A959B",
    45: "#8A959B",
    135: "#8A959B",
}

# 按字形分布在不同字体里，pango 逐字形挑（服务器 cmap 实测）：
#   'Noto Sans Symbols'(1)  → 黄道 ♈-♓ + 行星 ☽☿♀♂♃♄ + 南北交 ☊☋ + 凯龙 ⚷
#   'Noto Sans Symbols2'    → ☉
#   'DejaVu Sans'           → 福点 ⊗(U+2297) + 精神点 Φ(U+03A6)（Symbols1/2 都没有）
# 缺任一字体对应字形就不渲染。Apple/Segoe 是 Mac/Win 本地兜底，serif 垫底。
SYM_FONT = "'Noto Sans Symbols','Noto Sans Symbols2','Noto Sans Symbols 2','DejaVu Sans','Symbola','Apple Symbols','Segoe UI Symbol',serif"

def norm(a):
    return a % 360

def sign_of(lon):
    return int(norm(lon) // 30)

def _label_box(angle, radius, width, height):
    """Return a conservative text box for collision-safe chart layout."""
    rad = angle * D2R
    x = CX + radius * math.cos(rad)
    y = CY + radius * math.sin(rad)
    return (x - width / 2, y - height / 2, x + width / 2, y + height / 2)

def _tangent_label_box(angle, radius, offset, width, height):
    rad = angle * D2R
    x = CX + radius * math.cos(rad) - math.sin(rad) * offset
    y = CY + radius * math.sin(rad) + math.cos(rad) * offset
    return (x - width / 2, y - height / 2, x + width / 2, y + height / 2)

def _axis_label_boxes(label, degree, angle, name_radius, info_radius):
    name_width = len(label) * 7.0 + 4
    degree_width = len(f"{degree}°") * 5.9 + 3
    return [
        _label_box(angle, name_radius, name_width, 16),
        _tangent_label_box(
            angle, info_radius, -AXIS_INFO_TANGENT_GAP,
            degree_width, 13,
        ),
        _tangent_label_box(angle, info_radius, 0, 16, 18),
        _tangent_label_box(
            angle, info_radius, AXIS_INFO_TANGENT_GAP,
            17, 11,
        ),
    ]

def _radial_axis_label_boxes(label, longitude, angle):
    """整宫制四轴与行星共用径向信息列时的可见包围盒。"""
    degree = int(norm(longitude) % 30)
    name_width = len(label) * 8.2 + 6
    degree_width = len(f"{degree}°") * 6.2 + 4
    return [
        _label_box(angle, Rpt, name_width, 18),
        _label_box(angle, PLANET_DEGREE_RADIUS, degree_width, 13),
        _label_box(angle, PLANET_SIGN_RADIUS, 15, 16),
        _label_box(angle, PLANET_MINUTE_RADIUS, 14, 10),
    ]

def _planet_label_boxes(
    angle, conjunction=False, retrograde=False, base_radius=Rpt,
    glyph_width=18, glyph_height=22,
):
    if conjunction:
        # Symbol plus a full degree-minute string such as 29°59'.
        boxes = [
            _label_box(angle, base_radius, 30, 30),
            _label_box(angle, base_radius - 22, 50, 18),
        ]
        if retrograde:
            boxes.append(_tangent_label_box(angle, base_radius, 13, 19, 16))
        return boxes
    boxes = [
        _label_box(angle, base_radius, glyph_width, glyph_height),
        _label_box(angle, base_radius - 19.5, 19, 13),
        _label_box(angle, base_radius - 34.5, 14, 16),
        _label_box(angle, base_radius - 47.5, 15, 10),
    ]
    if retrograde:
        boxes.append(_label_box(angle, base_radius - 58.1, 12, 11))
    return boxes

def _boxes_overlap(left, right, gap=0.25):
    return not (
        left[2] + gap <= right[0]
        or right[2] + gap <= left[0]
        or left[3] + gap <= right[1]
        or right[3] + gap <= left[1]
    )


def _label_groups_overlap(left, right):
    return any(
        _boxes_overlap(left_box, right_box)
        for left_box in left
        for right_box in right
    )




def _planet_ring_display_angles(entries, asc_lon, step=0.25):
    """Resolve one planet-only 360° queue while preserving local density."""
    if not entries:
        return {}
    true_lons = [norm(entry["lon"]) for entry in entries]
    order = sorted(range(len(entries)), key=lambda index: (true_lons[index], index))
    if len(order) == 1:
        index = order[0]
        return {
            entries[index]["key"]:
            norm(180 - (true_lons[index] - asc_lon))
        }

    largest_gap = -1
    sequence_start = 0
    for position, index in enumerate(order):
        next_index = order[(position + 1) % len(order)]
        gap = norm(true_lons[next_index] - true_lons[index])
        if gap > largest_gap:
            largest_gap = gap
            sequence_start = (position + 1) % len(order)
    sequence = [
        order[(sequence_start + offset) % len(order)]
        for offset in range(len(order))
    ]
    start_lon = true_lons[sequence[0]]
    positions = []
    for index in sequence:
        longitude = true_lons[index]
        if longitude < start_lon:
            longitude += 360
        positions.append(longitude)

    def screen_angle(longitude):
        return norm(180 - (longitude - asc_lon))

    def boxes_at(position):
        entry = entries[sequence[position]]
        return entry["box_builder"](screen_angle(positions[position]))

    for round_index in range(1440):
        changed = False
        pairs = [
            (left, right)
            for left in range(len(sequence) - 1)
            for right in range(left + 1, len(sequence))
        ]
        if round_index % 2:
            pairs.reverse()
        for left, right in pairs:
            if _label_groups_overlap(boxes_at(left), boxes_at(right)):
                positions[left] -= step
                positions[right] += step
                changed = True
        if not changed:
            break

    return {
        entries[index]["key"]: screen_angle(longitude)
        for index, longitude in zip(sequence, positions)
    }



def _box_data(boxes):
    return "|".join(",".join(f"{value:.1f}" for value in box) for box in boxes)


def _svg_pluto_glyph(x, y, size, color):
    """Return the established cup-form Pluto glyph as SVG strokes."""
    stroke_width = max(1.4, size * 0.085)
    cup_y = y + 0.04 * size
    cup_r = 0.23 * size
    circle_y = y - 0.02 * size
    circle_r = 0.125 * size
    vertical_start = cup_y + cup_r
    vertical_end = y + 0.56 * size
    cross_y = y + 0.42 * size
    cross_half = 0.15 * size
    paths = (
        f'M {x + cup_r:.2f} {cup_y:.2f} '
        f'A {cup_r:.2f} {cup_r:.2f} 0 0 1 {x - cup_r:.2f} {cup_y:.2f}',
        f'M {x + circle_r:.2f} {circle_y:.2f} '
        f'A {circle_r:.2f} {circle_r:.2f} 0 1 1 {x - circle_r:.2f} {circle_y:.2f} '
        f'A {circle_r:.2f} {circle_r:.2f} 0 1 1 {x + circle_r:.2f} {circle_y:.2f}',
        f'M {x:.2f} {vertical_start:.2f} L {x:.2f} {vertical_end:.2f} '
        f'M {x - cross_half:.2f} {cross_y:.2f} L {x + cross_half:.2f} {cross_y:.2f}',
    )
    layers = []
    for stroke, width in (
        (CHART_PALETTE["paper"], stroke_width + 3.0),
        (color, stroke_width),
    ):
        for path in paths:
            layers.append(
                f'<path d="{path}" fill="none" stroke="{stroke}" '
                f'stroke-width="{width:.2f}" stroke-linecap="round" '
                f'stroke-linejoin="round"/>'
            )
    return f'<g class="chart-pluto-glyph">{"".join(layers)}</g>'

def generate_chart_svg(planets, cusps, asc_lon, mc_lon, aspects, name="", date_str="", system="placidus"):
    """
    生成星盘 SVG。
    
    planets: dict {id: {lon, retrograde}}
    cusps: list[12] 宫头度数（普拉西度）
    asc_lon: ASC 度数
    mc_lon: MC 度数
    aspects: list[{p1, p2, angle, orb}]
    system: "placidus" 或 "whole_sign"
    """
    # API 正常只传这两个值；异常输入统一按 Placidus 兜底，避免后续分支
    # 对 system 的判断不一致时引用尚未赋值的 asc_sign_start。
    if system not in ("placidus", "whole_sign"):
        system = "placidus"
    
    def sd(lon):
        return norm(180 - norm(lon - asc_lon))
    
    def pt(a, r):
        rad = a * D2R
        return CX + r * math.cos(rad), CY + r * math.sin(rad)
    
    # 外圈直径 556，在手机成图中约占屏宽 94.6%，避免“容器满屏但圆盘看起来仍很小”。
    s = f'<svg id="chart" viewBox="6 6 588 588" xmlns="http://www.w3.org/2000/svg">\n'
    
    # ── Defs ──
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
'''
    
    # ── 12星座扇形 ──
    for i in range(12):
        a1, a2 = sd(i * 30), sd(i * 30 + 30)
        ox1, oy1 = pt(a1, Rout); ox2, oy2 = pt(a2, Rout)
        ix1, iy1 = pt(a1, Rzod); ix2, iy2 = pt(a2, Rzod)
        s += f'<path class="chart-sign" data-sign="{i}" d="M{ox1:.1f},{oy1:.1f} A{Rout},{Rout} 0 0,0 {ox2:.1f},{oy2:.1f} L{ix2:.1f},{iy2:.1f} A{Rzod},{Rzod} 0 0,1 {ix1:.1f},{iy1:.1f}Z" fill="{ELEM_GRADS[ELEMENTS[i]]}" stroke="none" style="cursor:pointer"/>\n'
    
    # ── 星座分隔线 ──
    for i in range(12):
        a = sd(i * 30)
        lx1, ly1 = pt(a, Rzod); lx2, ly2 = pt(a, Rout)
        s += f'<line x1="{lx1:.1f}" y1="{ly1:.1f}" x2="{lx2:.1f}" y2="{ly2:.1f}" stroke="{CHART_PALETTE["blue_soft"]}" stroke-width="0.45" stroke-opacity="0.46" style="pointer-events:none"/>\n'
    
    # ── 环线 ──
    s += f'<circle cx="{CX}" cy="{CY}" r="{Rout}" fill="none" stroke="{CHART_PALETTE["ink"]}" stroke-width="1.45"/>\n'
    s += f'<circle cx="{CX}" cy="{CY}" r="{Rzod}" fill="none" stroke="{CHART_PALETTE["ink"]}" stroke-width="0.78" opacity="0.72"/>\n'
    s += f'<circle cx="{CX}" cy="{CY}" r="{Rhouse}" fill="none" stroke="{CHART_PALETTE["grid"]}" stroke-width="0.58" opacity="0.82"/>\n'
    s += f'<circle cx="{CX}" cy="{CY}" r="{Rhi}" fill="none" stroke="{CHART_PALETTE["blue_soft"]}" stroke-width="0.78" opacity="0.9"/>\n'
    s += f'<circle cx="{CX}" cy="{CY}" r="14" fill="none" stroke="{CHART_PALETTE["grid"]}" stroke-width="0.5" opacity="0.18"/>\n'
    s += f'<circle cx="{CX}" cy="{CY}" r="1.4" fill="{CHART_PALETTE["blue_soft"]}" opacity="0.48"/>\n'
    
    # ── 度数刻度 ──
    for d in range(360):
        if d % 30 == 0: continue
        a = sd(d)
        length, col, sw, op = (4.8, CHART_PALETTE["ink"], 0.75, 0.9) if d % 10 == 0 else \
                              (3.2, CHART_PALETTE["blue_soft"], 0.55, 0.76) if d % 5 == 0 else \
                              (1.6, CHART_PALETTE["grid"], 0.4, 0.82)
        x1, y1 = pt(a, Rzod); x2, y2 = pt(a, Rzod + length)
        s += f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{col}" stroke-width="{sw}" opacity="{op}"/>\n'
    
    # ── 宫位线 + 宫号 ──
    if system == "whole_sign":
        # 整宫制：从 ASC 所在星座的 0° 开始，每 30° 一条等分线
        asc_sign_start = int(asc_lon // 30) * 30
        for h in range(1, 13):
            a = sd(asc_sign_start + (h - 1) * 30)
            x1, y1 = pt(a, Rzod); x2, y2 = pt(a, Rhi)
            # 整宫制宫头恰好落在星座分界线角度上，跟星座分隔线(blue_soft,0.45w/0.46op)
            # 同角度叠线；宫位线加粗加深才能盖过星座线，撑起12宫自己的层次。
            s += f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{CHART_PALETTE["ink"]}" stroke-width="0.8" stroke-linecap="round" opacity="0.55"/>\n'
            # 宫号属于宫位扇区，不属于宫头线。整宫制每宫固定 30°，
            # 从当前宫头顺行 15° 放在扇区正中，避免数字压在宫位线上。
            mid_a = sd(asc_sign_start + (h - 1) * 30 + 15)
            nx, ny = pt(mid_a, RhouseNumber)
            s += f'<text class="chart-house" data-house="{h}" x="{nx:.1f}" y="{ny:.1f}" text-anchor="middle" dominant-baseline="central" font-size="9" fill="#68797D" font-family="sans-serif" font-weight="500" style="cursor:pointer;letter-spacing:-0.3px">{h}</text>\n'
    else:
        # 普拉西度
        for h in range(1, 13):
            a = sd(cusps[h - 1])
            x1, y1 = pt(a, Rzod); x2, y2 = pt(a, Rhi)
            s += f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{CHART_PALETTE["grid"]}" stroke-width="0.55" stroke-linecap="round" opacity="0.72"/>\n'
            c1, c2 = cusps[h - 1], cusps[h % 12]
            mid = norm(c1 + norm(c2 - c1) / 2)
            nx, ny = pt(sd(mid), RhouseNumber)
            s += f'<text class="chart-house" data-house="{h}" x="{nx:.1f}" y="{ny:.1f}" text-anchor="middle" dominant-baseline="central" font-size="9" fill="#68797D" font-family="sans-serif" font-weight="500" style="cursor:pointer;letter-spacing:-0.3px">{h}</text>\n'
    
    # ── 星座符号 ──
    # 黄道符号全部保持正立。参考移动端星盘的阅读习惯，沿切线排布
    # “度数 / 星座 / 分”，但不旋转字形，避免左右和下半球符号倒置。
    R_badge = Rzod + (Rout - Rzod) * 0.5
    if system == "placidus":
        for h in range(1, 13):
            cusp_lon = cusps[h - 1]
            sign_idx = int(cusp_lon // 30) % 12
            a = sd(cusp_lon)
            gx, gy = pt(a, R_badge)
            rad = a * D2R
            tx, ty = -math.sin(rad), math.cos(rad)
            ec = ELEM_RING_COLORS[ELEMENTS[sign_idx]]
            deg_in_sign = int(cusp_lon % 30)
            minutes = int(round((cusp_lon % 1) * 60))
            if minutes >= 60: minutes, deg_in_sign = 0, deg_in_sign + 1
            ddx, ddy = gx - tx * 15, gy - ty * 15
            mmx, mmy = gx + tx * 15, gy + ty * 15
            s += f'<g class="chart-cusp-badge" data-house="{h}" style="pointer-events:none">'
            s += f'<text x="{ddx:.1f}" y="{ddy:.1f}" text-anchor="middle" dominant-baseline="central" font-size="8.8" fill="#67777A" font-family="sans-serif" font-weight="600">{deg_in_sign}°</text>'
            s += f'<text x="{gx:.1f}" y="{gy:.1f}" text-anchor="middle" dominant-baseline="central" font-size="17" fill="{ec}" font-weight="650" font-family="{SYM_FONT}">{SIGNS[sign_idx]}</text>'
            s += f'<text x="{mmx:.1f}" y="{mmy:.1f}" text-anchor="middle" dominant-baseline="central" font-size="7.6" fill="#96A1A2" font-family="sans-serif" font-weight="500">{minutes:02d}&#39;</text>'
            s += '</g>\n'
    else:
        for i in range(12):
            # 星座符号放在各星座弧段中点
            mid_a = sd(i * 30 + 15)
            gx, gy = pt(mid_a, Rzod + (Rout - Rzod) * 0.5)
            ec = ELEM_RING_COLORS[ELEMENTS[i]]
            s += f'<text class="chart-sign-label" data-sign="{i}" x="{gx:.1f}" y="{gy:.1f}" text-anchor="middle" dominant-baseline="central" font-size="18" fill="{ec}" font-weight="650" font-family="{SYM_FONT}" style="pointer-events:none">{SIGNS[i]}</text>\n'
            # 宫头线处标注 0°（整宫制每条宫头线精确落在某星座 0°）
            cusp_lon = asc_sign_start + i * 30
            a = sd(cusp_lon)
            gx2, gy2 = pt(a, Rout - 5)
            s += f'<text class="chart-cusp-degree" data-house="{i+1}" x="{gx2:.1f}" y="{gy2:.1f}" text-anchor="middle" dominant-baseline="central" font-size="7.8" fill="#879496" font-family="sans-serif" font-weight="600" style="pointer-events:none">0°</text>\n'
    
    # ── 相位线 ──
    for asp in aspects:
        p1_id, p2_id = asp["p1"], asp["p2"]
        angle, orb = asp["angle"], abs(asp["orb"])
        if orb > 10: continue
        p1_lon = planets.get(p1_id, {}).get("lon")
        p2_lon = planets.get(p2_id, {}).get("lon")
        if p1_lon is None or p2_lon is None: continue
        ax1, ay1 = pt(sd(p1_lon), Rhi - 1)
        ax2, ay2 = pt(sd(p2_lon), Rhi - 1)
        col = ASP_COL.get(angle, "#87979D")
        strength = 1 - orb / 8
        sw = (0.7 + strength * 1.6) * (1.1 if angle in [90, 180] else 0.9 if angle in [60, 120] else 1)
        opacity = 0.55 + strength * 0.4
        dash = ' stroke-dasharray="3,3"' if angle in [150, 30, 45, 135] else ""
        s += f'<line class="aspect-halo" x1="{ax1:.1f}" y1="{ay1:.1f}" x2="{ax2:.1f}" y2="{ay2:.1f}" stroke="{CHART_PALETTE["paper"]}" stroke-width="{sw+1.2:.1f}" stroke-linecap="round" opacity="0.88" style="pointer-events:none"/>\n'
        s += f'<line class="aspect-line" data-aspect="{p1_id} {p2_id}" data-angle="{angle}" x1="{ax1:.1f}" y1="{ay1:.1f}" x2="{ax2:.1f}" y2="{ay2:.1f}" stroke="{col}" stroke-width="{sw:.1f}" stroke-linecap="round" opacity="{opacity:.2f}"{dash}/>\n'
    
    # ── 四轴 + 单一 360° 信息圆周 ──
    # 普拉西度四轴固定在真实主轴；整宫制复用双盘内圈机制，把四轴作为普通
    # 信息列放进行星队列。两者都只移动标签，真实轴角和行星黄经不变。
    axes = [
        ("ASC", asc_lon),
        ("DSC", asc_lon + 180),
        ("MC", mc_lon),
        ("IC", mc_lon + 180),
    ]

    planet_items = []
    for pid, pinfo in planets.items():
        pi = PLANET_BY_ID.get(pid)
        if not pi:
            continue
        planet_items.append({
            "id": pid,
            "lon": pinfo["lon"],
            "retro": pinfo.get("retrograde", False),
            "info": pi,
        })

    planet_entries = [
        {
            "key": f"planet:{item['id']}",
            "lon": item["lon"],
            "box_builder": (
                lambda angle, planet=item: _planet_label_boxes(
                    angle,
                    retrograde=planet["retro"],
                    base_radius=Rpt,
                    glyph_width=PLANET_COLLISION[planet["id"]][0],
                    glyph_height=PLANET_COLLISION[planet["id"]][1],
                )
            ),
        }
        for item in planet_items
    ]
    # 整宫制四轴与行星共用同一条圆周队列：轴名占行星符号位，
    # 度数／星座／分沿相同半径逐层排列，拥挤时保持黄经顺序局部顺延。
    if system == "whole_sign":
        for lbl, axis_lon in axes:
            planet_entries.append({
                "key": f"axis:{lbl}",
                "lon": axis_lon,
                "box_builder": (
                    lambda angle, label=lbl, longitude=axis_lon:
                    _radial_axis_label_boxes(label, longitude, angle)
                ),
            })
    display_angles = _planet_ring_display_angles(planet_entries, asc_lon)

    axis_layout = []
    for lbl, axis_lon in axes:
        line_angle = sd(axis_lon)
        marker_angle = (
            display_angles[f"axis:{lbl}"]
            if system == "whole_sign" else line_angle
        )
        degree_value = norm(axis_lon) % 30
        axis_degree = int(degree_value)
        axis_minute = int((degree_value - axis_degree) * 60)
        axis_sign = sign_of(axis_lon)
        if system == "whole_sign":
            name_radius, info_radius = Rpt, PLANET_DEGREE_RADIUS
            boxes = _radial_axis_label_boxes(lbl, axis_lon, marker_angle)
        else:
            name_radius, info_radius = AXIS_NAME_RADIUS, AXIS_INFO_RADIUS
            boxes = _axis_label_boxes(
                lbl, axis_degree, marker_angle, name_radius, info_radius
            )
        axis_layout.append({
            "label": lbl,
            "lon": axis_lon,
            "angle": line_angle,
            "marker_angle": marker_angle,
            "degree": axis_degree,
            "minute": axis_minute,
            "sign": axis_sign,
            "name_radius": name_radius,
            "info_radius": info_radius,
            "layout": "radial" if system == "whole_sign" else "tangent",
            "boxes": boxes,
        })

    # 整宫制宫头本来就是四轴所在星座的整数起点，四轴的精确度数已经跟宫位线
    # 挤在同一圈角度附近；再画一条独立的轴线只会重复、更乱。整宫制只留
    # ASC/MC/DSC/IC 的文字标记（名称+度数+星座+分），普拉西度维持原样画线。
    for axis in axis_layout:
        lbl = axis["label"]
        line_angle = axis["angle"]
        marker_angle = axis["marker_angle"]

        if system != "whole_sign":
            x1, y1 = pt(line_angle, Rhi)
            x2, y2 = pt(line_angle, Rout)
            s += (
                f'<line class="chart-axis-line" data-axis="{lbl}" '
                f'data-display-angle="{line_angle:.1f}" '
                f'x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
                f'stroke="{CHART_PALETTE["axis"]}" stroke-width="1.1" opacity="0.8" '
                f'stroke-linecap="round" style="pointer-events:none"/>\n'
            )

        if abs(((marker_angle - line_angle + 540) % 360) - 180) > 0.5:
            tx, ty = pt(line_angle, Rbi - 1)
            lx, ly = pt(marker_angle, axis["name_radius"] + 10)
            s += (
                f'<line class="chart-axis-label-guide" data-axis="{lbl}" '
                f'x1="{tx:.1f}" y1="{ty:.1f}" x2="{lx:.1f}" y2="{ly:.1f}" '
                f'stroke="{CHART_PALETTE["axis"]}" stroke-width="0.48" '
                f'stroke-linecap="round" opacity="0.52" style="pointer-events:none"/>\n'
            )

        axis_name_radius = axis["name_radius"]
        name_x, name_y = pt(marker_angle, axis_name_radius)
        if axis["layout"] == "radial":
            degree_x, degree_y = pt(marker_angle, PLANET_DEGREE_RADIUS)
            sign_x, sign_y = pt(marker_angle, PLANET_SIGN_RADIUS)
            minute_x, minute_y = pt(marker_angle, PLANET_MINUTE_RADIUS)
        else:
            info_x, info_y = pt(marker_angle, axis["info_radius"])
            info_rad = marker_angle * D2R
            tangent_x, tangent_y = -math.sin(info_rad), math.cos(info_rad)
            degree_x = info_x - tangent_x * AXIS_INFO_TANGENT_GAP
            degree_y = info_y - tangent_y * AXIS_INFO_TANGENT_GAP
            sign_x, sign_y = info_x, info_y
            minute_x = info_x + tangent_x * AXIS_INFO_TANGENT_GAP
            minute_y = info_y + tangent_y * AXIS_INFO_TANGENT_GAP
        axis_degree = axis["degree"]
        axis_minute = axis["minute"]
        axis_sign = axis["sign"]
        sign_color = ELEM_COLORS[ELEMENTS[axis_sign]]
        s += (
            f'<g class="chart-axis-marker" data-axis="{lbl}" '
            f'data-display-angle="{line_angle:.1f}" '
            f'data-label-angle="{marker_angle:.1f}" '
            f'data-degree="{axis_degree}" data-name-radius="{axis_name_radius:.1f}" '
            f'data-info-radius="{axis["info_radius"]:.2f}" '
            f'data-layout="{axis["layout"]}" '
            f'data-collision-boxes="{_box_data(axis["boxes"])}" style="pointer-events:none">'
            f'<text class="chart-axis-label" x="{name_x:.1f}" y="{name_y:.1f}" '
            f'text-anchor="middle" dominant-baseline="central" '
            f'font-size="12.5" fill="{CHART_PALETTE["axis"]}" font-family="sans-serif" '
            f'font-weight="700" letter-spacing="0.7" '
            f'style="paint-order:stroke;stroke:{CHART_PALETTE["paper"]};'
            f'stroke-width:3.4;stroke-linejoin:round">{lbl}</text>'
            f'<text class="chart-axis-degree" x="{degree_x:.1f}" y="{degree_y:.1f}" '
            f'text-anchor="middle" dominant-baseline="central" font-size="12" '
            f'fill="#465052" font-family="sans-serif" font-weight="700" '
            f'style="paint-order:stroke;stroke:{CHART_PALETTE["paper"]};'
            f'stroke-width:2.2;stroke-linejoin:round">{axis_degree}°</text>'
            f'<text class="chart-axis-sign" x="{sign_x:.1f}" y="{sign_y:.1f}" '
            f'text-anchor="middle" dominant-baseline="central" font-size="13.5" '
            f'fill="{sign_color}" font-family="{SYM_FONT}" font-weight="800">'
            f'{SIGNS[axis_sign]}</text>'
            f'<text class="chart-axis-minute" x="{minute_x:.1f}" y="{minute_y:.1f}" '
            f'text-anchor="middle" dominant-baseline="central" font-size="8.4" '
            f'fill="#96A1A2" font-family="sans-serif" font-weight="500">'
            f'{axis_minute:02d}&#39;</text></g>\n'
        )

    N = len(planet_items)
    layout_angles = [
        display_angles[f"planet:{item['id']}"] for item in planet_items
    ]
    layout_radii = [Rpt] * N
    layout_boxes = {
        index: _planet_label_boxes(
            layout_angles[index],
            retrograde=item["retro"],
            base_radius=Rpt,
            glyph_width=PLANET_COLLISION[item["id"]][0],
            glyph_height=PLANET_COLLISION[item["id"]][1],
        )
        for index, item in enumerate(planet_items)
    }

    # Keep conjunction metadata for inspection/tapping, but do not create a
    # separate placement system.  Near-axis points remain ordinary full stacks
    # in the same longitude queue as every other label.
    axis_match = {}
    for k, item in enumerate(planet_items):
        matches = []
        for axis_index, (axis_lbl, axis_lon) in enumerate(axes):
            delta = (norm(item["lon"] - axis_lon) + 180) % 360 - 180
            if abs(delta) <= 5:
                matches.append((abs(delta), axis_index, axis_lbl, delta))
        if matches:
            _, axis_index, axis_lbl, delta = min(matches)
            axis_match[k] = (axis_index, axis_lbl, delta)
    
    for k, pi in enumerate(planet_items):
        p_info = pi["info"]
        disp_a, raw_a = layout_angles[k], sd(pi["lon"])
        col, sym, sym_fs = p_info["color"], p_info["sym"], p_info["size"]
        d, sg = norm(pi["lon"]) % 30, sign_of(pi["lon"])
        d_deg = int(d); D, M = d_deg, int((d - d_deg) * 60)
        
        axis_conjunction = axis_match.get(k)
        if axis_conjunction:
            _, axis_lbl, axis_delta = axis_conjunction
        else:
            axis_lbl, axis_delta = "", 0
        planet_radius = layout_radii[k]
        gx, gy = pt(disp_a, planet_radius)
        
        # 指示线
        if abs(((disp_a - raw_a + 540) % 360) - 180) > 0.5:
            tx, ty = pt(raw_a, Rbi - 1); lx, ly = pt(disp_a, planet_radius + sym_fs / 2)
            s += f'<line x1="{tx:.1f}" y1="{ty:.1f}" x2="{lx:.1f}" y2="{ly:.1f}" stroke="{col}" stroke-width="0.4" stroke-linecap="round" opacity="0.45"/>\n'
        
        # 行星栈
        # 移动端紧凑信息列：行星符号最大；度数/星座次级；分数最小、最淡。
        # 度数是读盘时最常被扫读的数字，原 10.5 只有行星字形的 0.375，明显偏小。
        # 参照 Astro-Seek / Astrodienst 的常见比例（约 0.40~0.45）提到 12；
        # 分与逆行同步小幅上调，保持「符号 > 星座 > 度数 > 分」的层级不变。
        dd_size, sg_size, dm_size, rx_size = 12.0, 13.5, 8.4, 9.0
        g_sym_deg = (sym_fs + dd_size) / 2 + 2.4
        g_deg_sign = (dd_size + sg_size) / 2 + 2.2
        g_sign_min = (sg_size + dm_size) / 2 + 2.0
        g_min_rx = (dm_size + rx_size) / 2 + 2.0 if pi["retro"] else 0
        
        Rdd = planet_radius - g_sym_deg
        Rsg = Rdd - g_deg_sign
        Rdm = Rsg - g_sign_min
        Rrx = Rdm - g_min_rx
        sign_col = ELEM_COLORS[ELEMENTS[sg]]
        group_class = (
            "chart-planet chart-axis-conjunction"
            if axis_conjunction else "chart-planet"
        )
        axis_data = (
            f' data-axis="{axis_lbl}" data-axis-delta="{axis_delta:.3f}"'
            if axis_conjunction else ""
        )
        
        out = (
            f'<g class="{group_class}" data-planet-id="{pi["id"]}"{axis_data} '
            f'data-radius="{planet_radius:.1f}" '
            f'data-true-angle="{raw_a:.1f}" '
            f'data-display-angle="{disp_a:.1f}" '
            f'data-collision-boxes="{_box_data(layout_boxes[k])}" style="cursor:pointer">'
        )
        out += f'<circle class="planet-halo" cx="{gx:.1f}" cy="{gy:.1f}" r="{sym_fs*0.62:.1f}" fill="none" stroke="none"/>'
        # 不用 filter=url(#planetShadow)：librsvg 渲染不出带 feDropShadow 的 text → 行星/福点/精神点字形会变透明（黄道无滤镜所以正常）。白描边(paint-order)做易读性即可。
        if pi["id"] == "pluto":
            out += _svg_pluto_glyph(gx, gy, sym_fs, col)
        else:
            out += f'<text x="{gx:.1f}" y="{gy:.1f}" text-anchor="middle" dominant-baseline="central" font-size="{sym_fs}" fill="{col}" font-family="{SYM_FONT}" font-weight="700" style="paint-order:stroke;stroke:{CHART_PALETTE["paper"]};stroke-width:1.5;stroke-linejoin:round">{sym}</text>'
        ddx, ddy = pt(disp_a, Rdd)
        out += f'<text x="{ddx:.1f}" y="{ddy:.1f}" text-anchor="middle" dominant-baseline="central" font-size="{dd_size}" fill="#465052" font-family="sans-serif" font-weight="600">{D}°</text>'
        sx, sy = pt(disp_a, Rsg)
        out += f'<text x="{sx:.1f}" y="{sy:.1f}" text-anchor="middle" dominant-baseline="central" font-size="{sg_size}" fill="{sign_col}" font-family="{SYM_FONT}" font-weight="800">{SIGNS[sg]}</text>'
        dmx, dmy = pt(disp_a, Rdm)
        out += f'<text x="{dmx:.1f}" y="{dmy:.1f}" text-anchor="middle" dominant-baseline="central" font-size="{dm_size}" fill="#96A1A2" font-family="sans-serif" font-weight="500">{M:02d}\'</text>'
        if pi["retro"]:
            rxx, rxy = pt(disp_a, Rrx)
            out += f'<text x="{rxx:.1f}" y="{rxy:.1f}" text-anchor="middle" dominant-baseline="central" font-size="{rx_size}" fill="#B84F47" font-family="sans-serif" font-weight="700">℞</text>'
        out += "</g>\n"
        s += out
    
    s += "</svg>"
    return s
