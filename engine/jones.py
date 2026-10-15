"""
Jones Pattern Calculator — 琼斯格局 + 变形格局自动识别算法
==========================================================
基于 Marc Edmund Jones 七种格局体系及 Jansky/Sellar 等人扩展的变形格局。

规则来源：NotebookLM「占星学图表格局」笔记本。

核心规则：
  - 仅使用十大主要行星（太阳/月亮/水星/金星/火星/木星/土星/天王星/海王星/冥王星）
  - 不包含上升（ASC）、天顶（MC）、南北交点、凯龙星等虚点
  - 三分法则（Tripolar）优先于二四法则（Bipolar）

七种基础格局：
  Bundle   丛聚型  — 最大空白 ≥ 240°（所有行星在 ~120° 内）
  Bowl     碗型    — 最大空白 ≥ 175°（跨度 ≤ 185°），无孤立把手星
  Bucket   提桶型  — 9星形成碗（跨度 ≤ 190°），1星独立且距碗两端各 ≥ 60°
  Loco     火车头型— 一个主导空白 115°~175°，次级空白 < 65°（三分法则优先）
  Splay    展开型  — 3 个及以上 ≥ 60° 的间隔（三分法则优先）
  Seesaw   跷跷板型— 恰好 2 个 ≥ 60° 的间隔，两组各含多颗行星
  Splash   散落型  — 均匀分布，无显著空白

变形格局（detect_with_variants 才会检测）：
  Fanhandle  扇柄型     — Bundle变体：主群 ≤90°，把手 ≥60°（最紧凑把手格局）
  Sling      弹弓型     — Bucket变体：主群 ≤120°，把手 ≥60°
  ConjHandle 合相把手型  — 2星合相（≤8°）共同充当把手
  TwoHandle  双把手型   — 2颗独立行星分别充当把手（间距 >8°）
  Hourglass  沙漏型     — Seesaw变体：两侧空白均 ≥90°
  Butterfly  蝴蝶型     — 1颗孤星等距嵌于两群之间，三段空白均 ≥90°
  Tripod     三脚架型   — Splay变体：三群规则分布，各空白均 ≥90°

优先级（源自 Jones 三分法则）：
  Tripolar: Bundle > Locomotive > Splay > Splash
  Bipolar:  Bowl > Bucket > Seesaw
  Tripolar 优先于 Bipolar（模糊时取三分格局）

  基础检测顺序：Bundle → Bowl/Bucket → Locomotive → Bucket(次) → Splay → Seesaw → Splash
  变形精化顺序：Fanhandle → Sling → ConjHandle → TwoHandle → Hourglass → Butterfly → Tripod
"""

from __future__ import annotations
import math
import threading
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Tuple


# ──────────────────────────────────────────────────────────────
# 常量
# ──────────────────────────────────────────────────────────────

PLANET_NAMES_ZH = ["太阳☉", "月亮☽", "水星☿", "金星♀", "火星♂",
                   "木星♃", "土星♄", "天王星♅", "海王星♆", "冥王星♇"]
PLANET_NAMES_EN = ["Sun", "Moon", "Mercury", "Venus", "Mars",
                   "Jupiter", "Saturn", "Uranus", "Neptune", "Pluto"]

# 行星运行速度排名（数字越小 = 越快）：月亮最快，冥王星最慢
# 用于 Splash / Seesaw 中确定高焦点行星
PLANET_SPEED_RANK = {
    "Moon": 0, "Mercury": 1, "Venus": 2, "Sun": 3,
    "Mars": 4, "Jupiter": 5, "Saturn": 6,
    "Uranus": 7, "Neptune": 8, "Pluto": 9,
}

# ── 阈值常量 ────────────────────────────────────────────────────
BUNDLE_THRESHOLD    = 230.0  # 最大空白 ≥ 此值 → 丛聚型（NotebookLM 推荐放宽：Eduard Benes span=122.6° max_gap=237.4°）
BOWL_THRESHOLD      = 175.0  # 最大空白 ≥ 此值 → 碗型（即跨度 ≤ 185°）。
# 依据（2026-09-28 原典复核，取代此前的 150°）：
#   Jones《Essentials of Astrological Analysis》碗型定义："found when the ten PLANETS
#   lie in a half of the circle or when if two of them are in OPPOSITION the others all
#   are found on one side of the line formed by the aspect." —— 半圆 180° 是本体，
#   原典允许碗口对分相附近的偏差，但没有给出统一的 5° 截止线；
#   这里取跨度 185° 是工程阈值，需与外部样本和交界提示一起使用。
#   Sellar《Chart Shapes》第 4 章："within 180° of arc, maximum 190°"。
#   外部实测：AstroMansion 在 span 183.8° 判 Bowl、185.8° 判 Locomotive（容差≈5°，与本值一致）；
#   Augurine 为 180° 硬切（span 179.5 判 Bowl、182.3 判 Locomotive）。
#   旧值 150° 的两条注释依据均不成立：Sellar 原文无「120↔180 取中点」之说，
#   且全书 23 个案例盘中没有 Biden。
BOWL_MAX_SPAN       = 200.0  # 碗型：9颗星的跨度上限（NotebookLM 推荐 190→200°，救散 Bucket：George Michael bowl_span=198.8°/Evangeline Adams bowl_span=191.2°）
BOWL_MAX_INTERNAL_VOID = 90.0  # 碗/把手的"碗"内部最大允许空洞：碗须是连续弧，内部裂口≥90°说明剩余行星其实分成多群、不构成碗（如 Baudelaire 碗内 93° 洞实为三群→应判 Splay 而非扇柄）。实测全样本仅 Baudelaire 越界。
SEESAW_BOWL_SPAN_LIMIT = 194.0  # 旧碗型上限的防御性闸门；当前 Bowl span≤185°，不会触发。若日后放宽 Bowl 阈值，须连同此闸门重新审查。
LOCO_MIN_GAP        = 115.0  # 火车头型：最大空白下限
LOCO_MAX_GAP        = 175.0  # 火车头型：最大空白上限（与碗型共享边界，与 BOWL_THRESHOLD 同步）
LOCO_SOFT_MIN_GAP   = 90.0   # 经典案例容差：Jansky 标准显著空白（海灵93.7°等边缘案例）
LOCO_SOFT_SECONDARY_MAX = 75.0  # 软火车头允许端点附近略大的内部断裂
LOCO_SECONDARY_MAX  = 60.0   # 火车头型：次级空白的最大容许值（MECE 防死锁：与 CLUSTER_SEP=60° 严格互斥，See-Saw 灰区不再被 Loco 抢；NotebookLM 原典认证）
LOCO_DOMINANCE      = 1.7    # 火车头型：主空白 / 次空白 的最低比值
CLUSTER_SEP         = 60.0   # 星群分隔阈值（跷跷板 / 展开 / 把手距离）
BUCKET_MIN_DIST     = 60.0   # 把手行星距碗两端的最小度数
COG_ANCHOR_ORB      = 3.0    # 碗底/占据半球重心：严格锚定容许度（≤此值升级为「碗底锚点」而非泛泛「承重墙」）
COG_PARTNER_ORB     = 6.0    # 碗中心复合合相：伙伴行星与已选碗中心行星的最大间距。产品阈值，非原典数字：
                             # Jones《Guide》Jay Gould 例称 8° 合相“大多各自起作用”，不能当整体；
                             # March & McEvers 称 5° 内为紧密、8° 内为一般；Huber 以约 3° 分紧密/宽松。
SELLAR_OPPOSITION_ORB = 10.0  # Jones/Sabian 主要相位标准：非日月行星容许度 10°；Sellar 未另设核心对分相阈值

# ── 变形格局阈值 ─────────────────────────────────────────────────
FANHANDLE_MAX_SPAN  = 90.0   # 扇柄型：主群跨度上限（极紧凑 Fan）
FANHANDLE_SOURCE_MAX_SPAN = 120.0  # 来源案例：Fan 主群可放宽至 120°
FANHANDLE_BALANCE_MAX = 20.0  # 放宽 Fan 时，把手须大致居中于两段空白
SLING_MAX_SPAN      = 125.0  # 弹弓型：主群跨度上限（Bucket 衍生，含案例容差）
CONJ_HANDLE_ORB     = 8.0    # 合相把手：两颗把手星的最大容许间距
FAN_CONJ_ORB        = 3.0    # 扇柄型合相把手：更严格的容许度
TWO_HANDLE_MIN_SEP  = 8.0    # 双把手：两颗把手星的最小间距（避免被认定为合相）
HOURGLASS_MIN_GAP   = 90.0   # 沙漏型：两侧空白的最小度数
BUTTERFLY_MIN_GAP   = 90.0   # 蝴蝶型：三段空白的最小度数
TRIPOD_MIN_GAP      = 90.0   # 三脚架型：三段空白的严格判定
TRIPOD_LOOSE_GAP    = 50.0   # 来源案例容差：三群结构可由约 50° 空白分隔
TRIPOD_VISUAL_GAP   = 45.0   # 视觉三脚架：近50°空白可切出独立支点
RAYLIKE_MAX_SPAN    = 12.0   # raylike bunching：小星群极度压缩的跨度

# 仅这些「无天然焦点」的格局才使用核心整合轴线（Sellar 核心对分相）。
# 其余格局各有把手/引导星/孤星顶点作焦点，叠加轴线属误用。
SELLAR_PATTERNS = {"Splash", "See-Saw", "Hourglass", "Splay"}


# ──────────────────────────────────────────────────────────────
# 数据类
# ──────────────────────────────────────────────────────────────

@dataclass
class PatternResult:
    """格局识别结果"""
    pattern_en: str                           # 英文名
    pattern_zh: str                           # 中文名
    confidence: str                           # "clear" | "moderate" | "ambiguous"
    max_gap: float                            # 最大空白度数
    span: float                               # 行星总跨度（360 - max_gap）
    details: str                              # 判断说明
    high_focus_planet: Optional[str] = None  # 高焦点行星名称
    high_focus_long: Optional[float] = None  # 高焦点行星度数
    extra: Dict = field(default_factory=dict) # 附加信息

    def __str__(self) -> str:
        lines = [
            f"【琼斯格局】{self.pattern_zh} ({self.pattern_en})",
            f"置信度：{self.confidence}",
            f"最大空白：{self.max_gap:.1f}°  行星跨度：{self.span:.1f}°",
            f"说明：{self.details}",
        ]
        if self.high_focus_planet:
            lines.append(
                f"高焦点行星（HFP）：{self.high_focus_planet}"
                f"（{self.high_focus_long:.1f}°）"
            )
        return "\n".join(lines)


# ──────────────────────────────────────────────────────────────
# 工具函数
# ──────────────────────────────────────────────────────────────

def _norm(deg: float) -> float:
    """归一化到 [0, 360)"""
    return deg % 360


def _circular_mean(longs: List[float]) -> float:
    """星群重心：圆周平均黄经（矢量和法，跨 0°/360° 边界也准确）。"""
    if not longs:
        return 0.0
    sx = sum(math.cos(math.radians(l)) for l in longs)
    sy = sum(math.sin(math.radians(l)) for l in longs)
    return _norm(math.degrees(math.atan2(sy, sx)))


def _validate_planetary_inputs(
    planetary_longitudes: List[float],
    planet_names: Optional[List[str]],
    lang: str,
) -> Tuple[List[float], List[str]]:
    """把不可信 API 输入收口为 10 个有限黄经与 10 个稳定名称。"""
    if not isinstance(planetary_longitudes, (list, tuple)) or len(planetary_longitudes) != 10:
        raise ValueError("必须提供恰好 10 颗行星的经度。")
    normalized = []
    for value in planetary_longitudes:
        if isinstance(value, bool):
            raise ValueError("行星经度必须是有限数字。")
        try:
            number = float(value)
        except (TypeError, ValueError):
            raise ValueError("行星经度必须是有限数字。")
        if not math.isfinite(number):
            raise ValueError("行星经度必须是有限数字。")
        normalized.append(_norm(number))
    names = planet_names or (PLANET_NAMES_ZH if lang == "zh" else PLANET_NAMES_EN)
    if not isinstance(names, (list, tuple)) or len(names) != 10:
        raise ValueError("必须提供恰好 10 个行星名称。")
    if not all(isinstance(name, str) and name.strip() for name in names):
        raise ValueError("行星名称必须是非空字符串。")
    return normalized, list(names)


def _calc_gaps(sorted_longs: List[float]) -> List[float]:
    """
    计算 n 颗行星之间的 n 个连续间隔（含首尾环绕间隔）。
    输入须已排序，单位：度。
    """
    n = len(sorted_longs)
    gaps = [sorted_longs[i + 1] - sorted_longs[i] for i in range(n - 1)]
    gaps.append(360.0 - sorted_longs[-1] + sorted_longs[0])
    return gaps


def _bowl_internal_void(bowl_gaps: List[float]) -> float:
    """碗内最大空洞：排除最大间隔（=虚空开口侧）后的次大间隔。
    ≥ BOWL_MAX_INTERNAL_VOID 说明剩余行星裂成多群、不构成连续碗弧。"""
    if len(bowl_gaps) < 2:
        return 0.0
    return sorted(bowl_gaps, reverse=True)[1]


def _cw(a: float, b: float) -> float:
    """顺时针从 a 到 b 的角距（0~360）"""
    return (b - a) % 360.0


def _find_name(
    target: float,
    orig_longs: List[float],
    names: List[str],
    tol: float = 0.05,
) -> str:
    """按黄道度数找行星名（精确匹配，容许 tol° 误差；找不到则取最近）"""
    t = _norm(target)
    for i, l in enumerate(orig_longs):
        if abs(_norm(l) - t) < tol:
            return names[i]
    diffs = [abs(_norm(l) - t) for l in orig_longs]
    return names[diffs.index(min(diffs))]


def _find_pair_names(
    first: float,
    second: float,
    orig_longs: List[float],
    names: List[str],
) -> Tuple[str, str, int, int]:
    """为两颗角色星选择不同的稳定身份。

    旧实现分别按黄经反查名称；两颗行星完全同度时，两次都会命中第一颗。
    这里在所有不同索引组合中选择总角距最小者，并以原始行星顺序稳定破同分。
    """
    if len(orig_longs) != len(names):
        raise ValueError("行星经度与名称数量必须一致。")

    def distance(a: float, b: float) -> float:
        delta = abs(_norm(a) - _norm(b))
        return min(delta, 360.0 - delta)

    candidates = []
    for first_idx, first_lon in enumerate(orig_longs):
        for second_idx, second_lon in enumerate(orig_longs):
            if first_idx == second_idx:
                continue
            candidates.append((
                distance(first, first_lon) + distance(second, second_lon),
                first_idx,
                second_idx,
            ))
    if not candidates:
        raise ValueError("至少需要两颗具有稳定身份的行星。")
    _, first_idx, second_idx = min(candidates)
    return names[first_idx], names[second_idx], first_idx, second_idx


def _fastest_planet(
    planet_indices: List[int],
    en_names: List[str],
) -> Tuple[int, str]:
    """从给定下标中找运动最快的行星（返回下标和英文名）"""
    ranks = {i: PLANET_SPEED_RANK.get(en_names[i], 99) for i in planet_indices}
    best = min(ranks, key=ranks.get)
    return best, en_names[best]


# ──────────────────────────────────────────────────────────────
# 提桶型检测（通用，不依赖 max_gap 阈值）
# ──────────────────────────────────────────────────────────────

def _check_bucket(
    sorted_longs: List[float],
    orig_longs: List[float],
    names: List[str],
    max_span: float = BOWL_MAX_SPAN,
    asymmetry_min: float = 0.55,
) -> Optional[Dict]:
    """
    通用提桶型检测：
    逐一尝试将每颗行星视作「把手」并移除，检查：
      1. 剩余 9 颗能否构成碗型（跨度 ≤ max_span，默认 BOWL_MAX_SPAN=190°）
      2. 把手在空白区内，且距碗两端各 ≥ BUCKET_MIN_DIST = 60°

    本函数不依赖全局 max_gap，可在任何阶段调用。
    """
    n = len(sorted_longs)
    for hi in range(n):
        rem = [sorted_longs[j] for j in range(n) if j != hi]
        r_gaps  = _calc_gaps(rem)
        r_max   = max(r_gaps)
        r_mi    = r_gaps.index(r_max)
        bowl_span = 360.0 - r_max

        if bowl_span > max_span:
            continue

        handle     = sorted_longs[hi]
        left_edge  = rem[r_mi]
        right_edge = rem[(r_mi + 1) % len(rem)]

        dist_left  = _cw(left_edge, handle)   # 把手距碗左边界（顺时针）
        dist_right = _cw(handle, right_edge)  # 把手距碗右边界（顺时针）

        # 把手须在空白区内（两段之和 ≈ r_max），且距两端各 ≥ 60°
        # asymmetry 0.55 保护：FDR 0.52 (handle 严重偏一边实为 Tripod 缰绳星) 排除；
        # 真 Bucket 都 ≥ 0.55（Lennon 0.85/Eastwood 0.72/GM 0.62/EA 0.63）。
        asymmetry = min(dist_left, dist_right) / max(dist_left, dist_right)
        if (abs(dist_left + dist_right - r_max) < 1.5
                and dist_left  >= BUCKET_MIN_DIST
                and dist_right >= BUCKET_MIN_DIST
                and asymmetry >= asymmetry_min):
            # 把手偏向哪一端边界星（NLM 核验 Sellar《Chart Shapes》：把手偏领头端＝更谨慎、
            # 更有准备，偏尾随端＝更冲动、更愿意冒险；接近正中＝边界星中点落在把手上，聚焦力最强）。
            # right_edge 是领头端（空白后第一颗，同 Bowl leader 语义），left_edge 是尾随端。
            # centered 判据必须复用真实中点角距（与 _bucket_void_midpoint 同口径 offset ≤ 8°），
            # 不能用两侧距离比——大空白下 0.85 比值可对应 >8° 偏差，会把没落中点的把手误标"正落在把手上"。
            _void_mid = (left_edge + r_max / 2) % 360
            _mid_offset = min((handle - _void_mid) % 360, (_void_mid - handle) % 360)
            if _mid_offset <= 8.0:
                handle_tilt = "centered"
            elif dist_right < dist_left:
                handle_tilt = "leading"
            else:
                handle_tilt = "trailing"
            return {
                "handle_long":  handle,
                "handle_name":  _find_name(handle, orig_longs, names),
                "bowl_span":    bowl_span,
                "bowl_gap":     r_max,
                "left_edge":    left_edge,
                "right_edge":   right_edge,
                "left_name":    _find_name(left_edge,  orig_longs, names),
                "right_name":   _find_name(right_edge, orig_longs, names),
                "dist_left":    dist_left,
                "dist_right":   dist_right,
                "handle_tilt":  handle_tilt,
            }
    return None


def _bucket_void_midpoint(
    left_edge: float,
    right_edge: float,
    handle_long: float,
    left_name: str,
    right_name: str,
    orb: float = 8.0,
) -> Dict:
    """提桶虚空中点：碗体两边界星之间空白半球（left_edge→right_edge 正向）的几何中点。

    Sellar《Chart Shapes》Ch.5：若把手星落于此中点（或他星与之相联），格局聚焦
    特征更显著。因此本中点的主要价值在 ``handle_on_midpoint`` 判定，而非作"靶点"。
    """
    gap = (right_edge - left_edge) % 360
    mid = (left_edge + gap / 2) % 360
    offset = min((handle_long - mid) % 360, (mid - handle_long) % 360)
    return {
        "long":               round(mid, 2),
        "left_name":          left_name,
        "left_long":          left_edge,
        "right_name":         right_name,
        "right_long":         right_edge,
        "handle_on_midpoint": offset <= orb,
        "handle_offset":      round(offset, 2),
    }


# ──────────────────────────────────────────────────────────────
# 火车头引导星
# ──────────────────────────────────────────────────────────────

def _find_leader(
    sorted_longs: List[float],
    gaps: List[float],
    orig_longs: List[float],
    names: List[str],
) -> Dict:
    """
    火车头型引导星（切割星）：
    从最大空白的右边界（逆时针方向）第一颗行星。
    即：从空白区逆时针（黄道正向）移动遇到的第一颗星。
    同时记录空白区起点（车尾）。
    """
    mg_idx      = gaps.index(max(gaps))
    leader_idx  = (mg_idx + 1) % len(sorted_longs)
    leader_long = sorted_longs[leader_idx]
    tail_long   = sorted_longs[mg_idx]
    return {
        "leader_long":  leader_long,
        "leader_name":  _find_name(leader_long, orig_longs, names),
        "tail_long":    tail_long,
        "tail_name":    _find_name(tail_long, orig_longs, names),
        "empty_start":  tail_long,
        "empty_end":    leader_long,
    }


# ──────────────────────────────────────────────────────────────
# 展开型：孤立星检测
# ──────────────────────────────────────────────────────────────

def _find_isolated(
    sorted_longs: List[float],
    gaps: List[float],
    orig_longs: List[float],
    names: List[str],
) -> Optional[Dict]:
    """
    展开型中，找两侧间隔均 ≥ 60° 的「孤立星」（缰绳行星）。
    """
    n = len(sorted_longs)
    for i in range(n):
        prev_gap = gaps[(i - 1) % n]
        curr_gap = gaps[i]
        if prev_gap >= CLUSTER_SEP and curr_gap >= CLUSTER_SEP:
            long = sorted_longs[i]
            return {
                "name":      _find_name(long, orig_longs, names),
                "long":      long,
                "prev_gap":  prev_gap,
                "next_gap":  curr_gap,
            }
    return None


# ──────────────────────────────────────────────────────────────
# 星群规模计算（供跷跷板型使用）
# ──────────────────────────────────────────────────────────────

def _group_sizes(
    gaps: List[float],
    sig_gap_indices: List[int],
) -> List[int]:
    """
    按显著间隔索引将行星分成若干组，返回各组行星数量。
    """
    n = len(gaps)
    sgi = sorted(sig_gap_indices)
    sizes = []
    for k, idx in enumerate(sgi):
        prev = sgi[k - 1]
        # 从 prev+1 到 idx（含）之间的行星数
        cnt = (idx - prev) % n
        sizes.append(cnt)
    return sizes


def _group_members(
    sorted_longs: List[float],
    gaps: List[float],
    sig_gap_indices: List[int],
) -> List[List[float]]:
    """按显著间隔索引把行星黄经分成若干组（与 _group_sizes 同一套切法，返回实际度数）。"""
    n = len(gaps)
    sgi = sorted(sig_gap_indices)
    groups = []
    for k, idx in enumerate(sgi):
        prev = sgi[k - 1]
        members = [sorted_longs[(prev + 1 + step) % n] for step in range((idx - prev) % n)]
        groups.append(members)
    return groups


def _would_form_valid_seesaw(gaps: List[float]) -> Optional[Dict]:
    """两组对立星群且每组至少3颗时，优先保留跷跷板/沙漏家族。"""
    sig_list = [(i, g) for i, g in enumerate(gaps) if g >= CLUSTER_SEP]
    if len(sig_list) != 2:
        return None
    sig_idxs = [i for i, _ in sig_list]
    sig_vals = [g for _, g in sig_list]
    sizes = _group_sizes(gaps, sig_idxs)
    if min(sizes) >= 3:
        return {"sig_idxs": sig_idxs, "sig_vals": sig_vals, "sizes": sizes}
    return None


def _clusters_from_gaps(sig_idxs: List[int], n: int) -> List[List[int]]:
    """
    按空白索引切分星群，返回每组在 sorted_longs 中的下标。
    clusters[k] 位于 sig_idxs[k-1] 与 sig_idxs[k] 两段空白之间。
    """
    sgi = sorted(sig_idxs)
    clusters = []
    for k, idx in enumerate(sgi):
        prev = sgi[k - 1]
        clusters.append([(prev + 1 + off) % n for off in range((idx - prev) % n)])
    return clusters


def _cluster_span(cluster: List[int], sorted_longs: List[float]) -> float:
    """计算单个星群自身跨度；cluster 来自 _clusters_from_gaps，顺序按圆周连续。"""
    if len(cluster) <= 1:
        return 0.0
    first = sorted_longs[cluster[0]]
    last = sorted_longs[cluster[-1]]
    return _cw(first, last)



def _count_occupied_signs(orig_longs: List[float]) -> int:
    """计算 10 颗行星落在几个不同的 30° 星座中（Jones Splash 判据）。"""
    return len({int(l // 30) % 12 for l in orig_longs})


def _max_cluster_30deg(sorted_longs: List[float], gaps: List[float]) -> int:
    """按"相邻 ≤30° 算一群"分群，返回最大群行星数（Splash 兜底判据）。
    Jones 原典 Trotsky：最大群 ≤ 3 颗 + 占据星座 ≥ 7 → 强制 Splash。"""
    sig_idxs_30 = [i for i, g in enumerate(gaps) if g >= 30.0]
    if not sig_idxs_30:
        return 10
    clusters = _clusters_from_gaps(sig_idxs_30, len(gaps))
    return max(len(c) for c in clusters) if clusters else 10


def _raylike_tripod(
    sorted_longs: List[float],
    gaps: List[float],
    sig_idxs: List[int],
) -> Optional[Dict]:
    """
    Splay/Tripod 边界：两个标准显著空白之外，若一个 45°~60° 的
    视觉空白能切出单星支点，并且另一个小群呈 raylike 极压缩，
    则不应按二分 See-Saw 处理。
    """
    if len(sig_idxs) != 2:
        return None

    near_gaps = [
        (i, g) for i, g in enumerate(gaps)
        if i not in sig_idxs and TRIPOD_VISUAL_GAP <= g < CLUSTER_SEP
    ]
    for near_idx, near_gap in near_gaps:
        tripod_idxs = sorted(sig_idxs + [near_idx])
        clusters = _clusters_from_gaps(tripod_idxs, len(gaps))
        sizes = [len(c) for c in clusters]
        if sorted(sizes) != [1, 4, 5]:
            continue

        multi_spans = [
            _cluster_span(cluster, sorted_longs)
            for cluster in clusters
            if len(cluster) > 1
        ]
        if min(multi_spans) > RAYLIKE_MAX_SPAN:
            continue

        vals = [gaps[i] for i in tripod_idxs]
        return {
            "idxs": tripod_idxs,
            "vals": vals,
            "sizes": sizes,
            "visual_gap": near_gap,
            "cluster_spans": multi_spans,
        }
    return None


# ──────────────────────────────────────────────────────────────
# 主识别函数
# ──────────────────────────────────────────────────────────────

def detect_jones_pattern(
    planetary_longitudes: List[float],
    planet_names: Optional[List[str]] = None,
    lang: str = "zh",
) -> PatternResult:
    """
    自动识别琼斯格局（七种）。

    参数
    ----
    planetary_longitudes : list[float]
        10 颗行星的黄道经度（度，0~360 或带负值均可），
        顺序：太阳、月亮、水星、金星、火星、木星、土星、天王星、海王星、冥王星。
    planet_names : list[str], optional
        行星名称列表（中文或英文），默认使用内置中文名。
    lang : "zh" | "en"
        名称显示语言（不影响逻辑），默认中文。

    返回
    ----
    PatternResult
    """
    orig_longs, names = _validate_planetary_inputs(planetary_longitudes, planet_names, lang)
    en_names = PLANET_NAMES_EN  # 用于速度排名

    # ── 数据准备 ────────────────────────────────────────────────
    sorted_longs = sorted(orig_longs)
    gaps         = _calc_gaps(sorted_longs)
    max_gap      = max(gaps)
    mg_idx       = gaps.index(max_gap)
    span         = 360.0 - max_gap

    # 双相决策法预计算（NotebookLM 原典认证 — Stage 2 硬路由参数）
    gaps_desc    = sorted(gaps, reverse=True)
    g2 = gaps_desc[1] if len(gaps_desc) >= 2 else 0.0
    g3 = gaps_desc[2] if len(gaps_desc) >= 3 else 0.0
    g4 = gaps_desc[3] if len(gaps_desc) >= 4 else 0.0
    occupied_signs   = _count_occupied_signs(orig_longs)
    max_cluster_30   = _max_cluster_30deg(sorted_longs, gaps)

    # 显著间隔（星群分隔候选，阈值 60°）
    sig_list  = [(i, g) for i, g in enumerate(gaps) if g >= CLUSTER_SEP]
    n_sig     = len(sig_list)
    sig_vals  = [g for _, g in sig_list]
    sig_idxs  = [i for i, _ in sig_list]

    # 次级大间隔（排除最大间隔，阈值 LOCO_SECONDARY_MAX = 65°）
    secondary = [g for i, g in enumerate(gaps)
                 if g >= LOCO_SECONDARY_MAX and i != mg_idx]

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 1. BUNDLE 丛聚型
    #    max_gap ≥ BUNDLE_THRESHOLD(230°)，即十颗星都在 confining trine 内（跨度 ≤130°）。
    #    2026-09-28 下线了原先的「lax Bundle」通道(max_gap ≥200° + g2 ≥55°)：它以
    #    Pierre Laval 为依据，但琼斯本人在《Essentials of Astrological Analysis》中
    #    把这张盘连同 Jeff Davis、William McKinley 一并从丛聚改判为碗型——
    #    "are reclassified as BOWL because the segments of the zodiac occupied by the
    #    PLANETS exceed what can be embraced in a defining TRINE."
    #    即该通道引用的是作者已撤回的旧判例。Sellar《Chart Shapes》同样写明
    #    "If less than 130° it's more likely to be a Wedge"，与 230° 严格门槛一致。
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    if max_gap >= BUNDLE_THRESHOLD:
        conf = "clear" if max_gap >= 250 else "moderate"
        leader = _find_leader(sorted_longs, gaps, orig_longs, names)
        # Sellar 原典：Bundle 解读起点是两端边界 + 中点（虚拟几何点）。
        # 因 Bundle 紧凑度 ≤ 120°（max_gap ≥ 240°），内部弧 = 360 - max_gap，
        # 中点 = leader 沿 CCW（经度递增）走 内部弧/2，是丛聚跨度的几何中心。
        inner_arc = 360 - max_gap
        mid_lon = (leader["leader_long"] + inner_arc / 2) % 360
        midpoint = {
            "long":       round(mid_lon, 2),
            "inner_arc":  round(inner_arc, 2),
            "left_name":  leader["leader_name"],
            "left_long":  leader["leader_long"],
            "right_name": leader["tail_name"],
            "right_long": leader["tail_long"],
        }
        return PatternResult(
            pattern_en="Bundle", pattern_zh="丛聚型",
            confidence=conf, max_gap=max_gap, span=span,
            details=(
                f"所有行星集中在 {span:.1f}° 范围内（最大空白 {max_gap:.1f}°）。"
                f"【内驱型·三分原则】能量高度专注，在选定领域可达到惊人深度；"
                f"能量呈闭环运作，对领域之外的事物天然缺乏感知雷达。"
            ),
            extra={"leader": leader, "midpoint_bundle": midpoint},
        )

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 1.4 SPLASH 硬路由 (NotebookLM 原典认证 - 理想散落通道)
    #    Jones 原典：Splash 看分布广度而非 max_gap
    #    通道 A 判据 (T.Roosevelt 81° / Brady 76° 同型)：
    #      max_gap<95° + g2<75° + g3<60° + g4≥41° + signs≥7
    #    精确避开 G.Harrison(See-Saw 6:4) g4=40° 边界
    #    前置于 See-Saw 硬路由：边缘 4:6/5:5 但分布广 (8 signs) 应判 Splash
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 两个显著空白切出 2:8 双群时，优先保留 Jones 明确允许的 See-Saw。
    # Grace Kelly 的 83.8°/66.1° 曾被「占据八宫」的 Splash 通道提前截走；
    # 两家独立计算器均将其归为 See-Saw。4:6 的 T. Roosevelt 仍可走广布通道。
    split_2_8 = (n_sig == 2 and sorted(_group_sizes(gaps, sig_idxs)) == [2, 8])
    # 第三段空白已贴近 60° 时，不能仅因它差不到几度便把 4:6/5:5 双群
    # 提前归入 Splash。1935-01-14 12:00 伦敦盘的三段为 64.4°/61.1°/59.6°，
    # Augurine 与 AstroMansion 均判 See-Saw；罗斯福 Splash 的第三段仅 44.1°。
    near_third_group_gap = (n_sig == 2 and g3 >= 55
                            and min(_group_sizes(gaps, sig_idxs)) >= 3)
    if (max_gap < 95 and g2 < 75 and g3 < 60
            and g4 >= 41 and occupied_signs >= 8
            and not split_2_8 and not near_third_group_gap):
        # Sellar 原典：Splash HFP = 核心对分相较快端（若无对分相则 None）
        _sellar_sp = _sellar_focus(orig_longs, names)
        return PatternResult(
            pattern_en="Splash", pattern_zh="散落型",
            confidence="clear" if max_gap <= 70 else "moderate",
            max_gap=max_gap, span=span,
            details=(
                f"行星广泛均匀分布于 {occupied_signs} 个不同星座（最大空白仅 {max_gap:.1f}°）。"
                f"【独立型·世界主义】核心心理动力是「世界主义者」气质——"
                f"自我与外部世界无锐利边界，博览各领域，能量多向分散。"
                f"核心挑战：整合多元才华，避免「样样精通却无一专精」。"
            ),
            high_focus_planet=_sellar_sp["name"] if _sellar_sp else None,
            high_focus_long=_sellar_sp["lon"] if _sellar_sp else None,
            extra={"sellar_focus": _sellar_sp},
        )

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 1.5 SEE-SAW 硬路由 (NotebookLM 原典认证)
    #    Jones 铁律："5:5/4:6/3:7/2:8 + 双段≥60°空白 + 两群各≥2颗"
    #    前置于 Bowl/Loco/Splay 防止双群对立被错抢
    #    (救 Karl Marx 3:7, 武汉 5:5, Hindenburg 5:5 等)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    if n_sig == 2 and (max_gap < BOWL_THRESHOLD or min(sig_vals) >= HOURGLASS_MIN_GAP):
        _ss_sizes = _group_sizes(gaps, sig_idxs)
        # min ≥ 3：救 3:7/4:6/5:5（Marx/Hindenburg/武汉/Philby/Harrison/Chopin）
        # 2:8 留给 ConjHandle/TwoHandle 路径（Christie/Earhart 等含合相把手者）
        if min(_ss_sizes) >= 3:
            _g1, _g2 = sig_vals
            _conf = "clear" if min(_g1, _g2) >= 70 else "moderate"
            _i_big = sig_idxs[0] if _g1 >= _g2 else sig_idxs[1]
            _g_big = max(_g1, _g2)
            _g_sml = min(_g1, _g2)
            _pole_a_long = sorted_longs[_i_big]
            _pole_b_long = sorted_longs[(_i_big + 1) % 10]
            _pole_a = _find_name(_pole_a_long, orig_longs, names)
            _pole_b = _find_name(_pole_b_long, orig_longs, names)
            # Sellar 原典：See-Saw HFP = 核心对分相较快端
            _sellar_ss = _sellar_focus(orig_longs, names)
            # 两组各自的重心连线（NLM 核验 Jones 原典）：跟 pole_a/b（最大空白两侧边界星）
            # 是两个不同概念——重心轴回答「没有其他焦点星时，人生份量偏向哪一组」，
            # Jones 原文：偏向行星更多的一组，数量打平则偏向更紧密聚集的一组。
            _ss_groups = _group_members(sorted_longs, gaps, sig_idxs)
            _center_a = _circular_mean(_ss_groups[0])
            _center_b = _circular_mean(_ss_groups[1])
            # 组内跨度用圆周首尾顺时针角距（组成员按环形遍历顺序排列，不能用 min/max，
            # 否则跨 0°/360° 边界的组会算出虚假的大跨度）。
            _span_a = _cw(_ss_groups[0][0], _ss_groups[0][-1]) if len(_ss_groups[0]) > 1 else 0.0
            _span_b = _cw(_ss_groups[1][0], _ss_groups[1][-1]) if len(_ss_groups[1]) > 1 else 0.0
            if len(_ss_groups[0]) != len(_ss_groups[1]):
                _heavier = "a" if len(_ss_groups[0]) > len(_ss_groups[1]) else "b"
            else:
                _heavier = "a" if _span_a <= _span_b else "b"
            _heavier_group = _ss_groups[0] if _heavier == "a" else _ss_groups[1]
            _heavier_pole_name = _pole_a if _pole_a_long in _heavier_group else (
                _pole_b if _pole_b_long in _heavier_group else "")
            # NLM 核验 Jones《Guide to Horoscope Interpretation》p.91-92：没有核心对分相时，
            # "the life tends to be significant at the side of the greater number of planets,
            # or sometimes where they are concentrated most closely"——退回到份量更重那组
            # 边界星，而不是留空。group_axis.heavier_pole_name 本就是这条原文算出来的，
            # 此前只当旁路展示，没接进 HFP 判定链路。
            if _sellar_ss:
                _hfp_name, _hfp_long = _sellar_ss["name"], _sellar_ss["lon"]
            elif _heavier_pole_name:
                _hfp_name = _heavier_pole_name
                _hfp_long = _pole_a_long if _heavier_pole_name == _pole_a else _pole_b_long
            else:
                _hfp_name, _hfp_long = None, None
            return PatternResult(
                pattern_en="See-Saw", pattern_zh="跷跷板型",
                confidence=_conf, max_gap=max_gap, span=span,
                details=(
                    f"行星分为两个对立星群（主空白 {_g_big:.1f}°，次空白 {_g_sml:.1f}°），"
                    f"星群规模约 {_ss_sizes[0]}颗 vs {_ss_sizes[1]}颗。"
                    f"【外激型·二/四分原则】天生的调停者与战略家；"
                    f"人生通常经历两个交替主导的阶段，终极功课是在两极张力中找到自己的重心。"
                ),
                high_focus_planet=_hfp_name,
                high_focus_long=_hfp_long,
                extra={"group_sizes": _ss_sizes, "gaps": [_g1, _g2],
                       "pole_a": _pole_a, "pole_b": _pole_b,
                       "sellar_focus": _sellar_ss,
                       "group_axis": {"center_a": round(_center_a, 2), "center_b": round(_center_b, 2),
                                      "heavier": _heavier, "heavier_pole_name": _heavier_pole_name}},
            )

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 1.7 1v9 SLING 硬路由 (NotebookLM 原典认证)
    #    Sling 边缘形态：1v9 split + 主群紧凑 (≤125°) + 把手距碗两端各 ≥60°
    #    与 Bucket 区别：主群浓度更高 (Bucket bowl_span≈180-200°, Sling ≤125°)
    #    Sling 的把手对称度天然较低 (asymmetry 阈值放宽到 0.30)
    #    前置于 Bowl 防止紧凑 1v9 形态被 Bowl 主路径抢 (救 北京 1972)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    if n_sig == 2:
        _sl_sizes = _group_sizes(gaps, sig_idxs)
        if 1 in _sl_sizes:
            _sling_cand = _check_bucket(
                sorted_longs, orig_longs, names,
                max_span=SLING_MAX_SPAN, asymmetry_min=0.30,
            )
            # Sellar 铁律：主群 ≤90° 强制升级为扇柄型 Fanhandle（楔形/丛聚族），
            # 不归弹弓型 Sling（提桶族）。让位后 base 判 Bucket → _refine_to_variant 精化为 Fanhandle。
            # 放宽通道同样让位：span ≤FANHANDLE_SOURCE_MAX_SPAN(120°) 且把手居中
            # （两侧空白差 ≤FANHANDLE_BALANCE_MAX(20°)）——这两个常数从初始提交
            # 就是为来源案例 Wozniak(span 112.9°/差 0.5°) 写的，但本硬路由只查了
            # 90° 一档就抢判 Sling，语料库该用例从未通过过（born-failing）。
            _fan_relaxed = bool(
                _sling_cand
                and _sling_cand["bowl_span"] <= FANHANDLE_SOURCE_MAX_SPAN
                and abs(_sling_cand["dist_left"] - _sling_cand["dist_right"])
                    <= FANHANDLE_BALANCE_MAX)
            if (_sling_cand and _sling_cand["bowl_span"] > FANHANDLE_MAX_SPAN
                    and not _fan_relaxed):
                return PatternResult(
                    pattern_en="Sling", pattern_zh="弹弓型",
                    confidence="clear" if _sling_cand["bowl_span"] <= 115 else "moderate",
                    max_gap=max_gap, span=span,
                    details=(
                        f"9颗行星高度浓缩在 {_sling_cand['bowl_span']:.1f}° 内（≤125° Sling 极限），"
                        f"把手「{_sling_cand['handle_name']}」独立对面，"
                        f"距碗两端「{_sling_cand['left_name']}」{_sling_cand['dist_left']:.1f}°/"
                        f"「{_sling_cand['right_name']}」{_sling_cand['dist_right']:.1f}°。"
                        f"【外激型·使命驱动】兼具丛聚型的极度专精与提桶型的明确方向感，"
                        f"把手星是不可动摇的人生使命领域。"
                    ),
                    high_focus_planet=_sling_cand["handle_name"],
                    high_focus_long=_sling_cand["handle_long"],
                    extra={"bucket": _sling_cand, "sling": True},
                )

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 2. BOWL 碗型 / BUCKET 提桶型（当 max_gap ≥ BOWL_THRESHOLD）
    #    检测顺序：合相把手 → 单星把手 → 纯碗型
    #    合相把手须先于单星把手检测，否则两颗合相星中的一颗会让单星
    #    把手检测因「另一颗星仍在碗中」而计算出过大的 bowl_span 并失败。
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    if max_gap >= BOWL_THRESHOLD:
        # ── 2a. 合相把手（两颗合相行星共同充当把手）────────────────
        conj_h = _check_conjunction_handle(sorted_longs, orig_longs, names)
        if conj_h:
            conf = "clear" if conj_h["bowl_span"] <= 182 else "moderate"
            return PatternResult(
                pattern_en="Bucket", pattern_zh="提桶型",
                confidence=conf, max_gap=max_gap, span=span,
                details=(
                    f"8颗行星形成碗形（跨度 {conj_h['bowl_span']:.1f}°），"
                    f"「{conj_h['h1_name']}」与「{conj_h['h2_name']}」"
                    f"以 {conj_h['sep']:.1f}° 合相共同充当把手，"
                    f"组合把手距碗两端各 ≥ 60°。"
                    f"【外激型·二/四分原则】合相把手双星合力聚焦全盘方向，使命叙事双重叠加，目标指向极为清晰。"
                ),
                # 合相把手无单星 HFP（Sellar："These two High Focus Planets"，复数整体）
                high_focus_planet=None,
                high_focus_long=None,
                extra={
                    "conj_handle": conj_h,
                    # 提供伪 bucket 供 _refine_to_variant 的 bowl_span 判断
                    "bucket": {
                        "bowl_span":   conj_h["bowl_span"],
                        "handle_name": f'{conj_h["h1_name"]}+{conj_h["h2_name"]}',
                        "handle_long": conj_h["h1_long"],
                        "left_name":   conj_h.get("left_name",  ""),
                        "right_name":  conj_h.get("right_name", ""),
                    },
                },
            )

        # ── 2b. 单星把手 ──────────────────────────────────────────
        bucket = _check_bucket(sorted_longs, orig_longs, names)
        if bucket:
            conf = "clear" if bucket["bowl_span"] <= 182 else "moderate"
            return PatternResult(
                pattern_en="Bucket", pattern_zh="提桶型",
                confidence=conf, max_gap=max_gap, span=span,
                details=(
                    f"9颗行星形成碗形（跨度 {bucket['bowl_span']:.1f}°），"
                    f"把手行星「{bucket['handle_name']}」（{bucket['handle_long']:.1f}°）"
                    f"独立于空白区中，"
                    f"距碗左端「{bucket['left_name']}」{bucket['dist_left']:.1f}°、"
                    f"距碗右端「{bucket['right_name']}」{bucket['dist_right']:.1f}°。"
                    f"【外激型·二/四分原则】把手星是全盘能量的泄压口，象征「不得不完成」的宿命领域。"
                ),
                high_focus_planet=bucket["handle_name"],
                high_focus_long=bucket["handle_long"],
                extra={"bucket": bucket},
            )

        # 原典护栏：碗口对分相散架 + 内部再裂出 ≥60° 空白 = 实为(非对称)跷跷板，不判碗。
        # 2026-09-28 起 BOWL_THRESHOLD=175° 把碗型跨度封顶在 185°，已低于本护栏的
        # 194° 触发线，因此这道闸门在当前阈值下不再可能被触发——原本由它拦下的盘
        # (span>194) 现在根本进不到碗型分支，会在上面的 max_gap 判据就落入火车头/
        # 跷跷板。保留为防御性空转，若日后调高碗型上限它会重新生效。
        _second_gap = sorted(gaps, reverse=True)[1] if len(gaps) > 1 else 0.0
        if not (span > SEESAW_BOWL_SPAN_LIMIT and _second_gap >= CLUSTER_SEP):
            # 纯碗型
            conf = "clear" if 175 <= max_gap <= 200 and span <= 185 else "moderate"
            left_long  = sorted_longs[mg_idx]
            right_long = sorted_longs[(mg_idx + 1) % 10]
            left_name  = _find_name(left_long,  orig_longs, names)
            right_name = _find_name(right_long, orig_longs, names)
            leader = _find_leader(sorted_longs, gaps, orig_longs, names)
            # Bowl 虚空中点：空白半球（max_gap）的几何中点，走空弧方向
            mid_lon = (left_long + max_gap / 2) % 360
            midpoint_bowl = {
                "long":       round(mid_lon, 2),
                "left_name":  left_name,
                "left_long":  left_long,
                "right_name": right_name,
                "right_long": right_long,
            }
            # 占据半球重心（center of gravity, Rudhyar）：虚空中点的对点 = 有星半球几何正中。
            # 若有行星落其 10° 内（可跨星座），该星即「绝对底牌/承重墙」——资源最集中、
            # 主观最掌控、供能去填对面虚空（Jones：碗段倾斜/重心比引导星更核心，引导星次要）。
            cog_lon = (mid_lon + 180.0) % 360
            _cg = sorted(
                (min(abs(_norm(l) - cog_lon), 360 - abs(_norm(l) - cog_lon)), i)
                for i, l in enumerate(orig_longs))
            cog_dist, cog_i = _cg[0]
            cog_bowl = {"long": round(cog_lon, 2)}
            if cog_dist <= 10.0:
                cog_bowl["planet_name"] = names[cog_i]
                cog_bowl["planet_long"] = round(_norm(orig_longs[cog_i]), 2)
                cog_bowl["dist"] = round(cog_dist, 1)
            return PatternResult(
                pattern_en="Bowl", pattern_zh="碗型",
                confidence=conf, max_gap=max_gap, span=span,
                details=(
                    f"【外激型·二/四分原则】所有行星集中在 {span:.1f}° 的半球内（最大空白 {max_gap:.1f}°）。"
                    f"碗口边界：「{left_name}」与「{right_name}」。"
                    f"潜能被外部情境激活而非主动出击；核心动力是空白半球在潜意识中制造的「缺失感」，"
                    f"驱使持续向外寻找能让自己完整的人或事业。"
                ),
                high_focus_planet=leader["leader_name"],
                high_focus_long=leader["leader_long"],
                extra={"left_boundary": left_name, "right_boundary": right_name,
                       "leader": leader, "midpoint_bowl": midpoint_bowl,
                       "cog_bowl": cog_bowl},
            )

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 3a. 早期 BUCKET 1v9 检测 [BIPOLAR — 优先于 Locomotive/Seesaw]
    #    NotebookLM 推荐：1v9 几何（孤星把手 + 9 颗主群）必须优先于 Loco/SeeSaw。
    #    George Michael (bowl_span=198.8°) / Evangeline Adams (bowl_span=191.2°)
    #    属于松散 Bucket，主群虽 > 190° 但 ≤ 200°（BOWL_MAX_SPAN 已放宽），
    #    arc handles 距两端各 ≥ 60° + asymmetry ≥ 0.55 已命中 _check_bucket。
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    if n_sig == 2:
        sizes_check = _group_sizes(gaps, sig_idxs)
        if 1 in sizes_check:
            early_bucket = _check_bucket(sorted_longs, orig_longs, names)
            # 限定松散 Bucket：bowl_span >= 180° 才提前抢判（区别紧凑主群的 Locomotive）
            # Washington / Wagner 等 Loco 案例 bowl_span < 180° 不触发，仍走 Loco
            if early_bucket and early_bucket["bowl_span"] >= 180.0:
                conf = "clear" if early_bucket["bowl_span"] <= 180 else "moderate"
                return PatternResult(
                    pattern_en="Bucket", pattern_zh="提桶型",
                    confidence=conf, max_gap=max_gap, span=span,
                    details=(
                        f"9颗行星形成松散碗形（跨度 {early_bucket['bowl_span']:.1f}°），"
                        f"把手行星「{early_bucket['handle_name']}」"
                        f"距碗左端「{early_bucket['left_name']}」{early_bucket['dist_left']:.1f}°、"
                        f"距碗右端「{early_bucket['right_name']}」{early_bucket['dist_right']:.1f}°。"
                        f"【外激型·二/四分原则】把手星是全盘能量的泄压口，象征「不得不完成」的宿命领域。"
                    ),
                    high_focus_planet=early_bucket["handle_name"],
                    high_focus_long=early_bucket["handle_long"],
                    extra={"bucket": early_bucket},
                )

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 3. LOCOMOTIVE 火车头型 [TRIPOLAR — 优先于 Bucket/Seesaw]
    #    Jansky 原典铁律："内部断层绝对不能 > 65°（should not be any break
    #    larger than 65 degrees）" —— 这是 hard limit，无 dominance 救济。
    #    NotebookLM 核查 commit: FDR 的 secondary=71.9/68.9° > 65° 应否决 Loco；
    #    Gandhi 的 secondary 为空但 valid_seesaw 抢判 → 把 Loco 拦截放到 SeeSaw 之前。
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    is_loco = False
    conj_handle_candidate = _check_conjunction_handle(sorted_longs, orig_longs, names)
    valid_seesaw_candidate = _would_form_valid_seesaw(gaps)
    visual_splay_gaps = [g for g in gaps if g >= TRIPOD_VISUAL_GAP]
    loco_hard_ok = (LOCO_MIN_GAP <= max_gap < LOCO_MAX_GAP and not secondary)
    if conj_handle_candidate and secondary and max(secondary) > LOCO_SECONDARY_MAX:
        # 8星主群 + 2星紧密合相把手时，不能被火车头的主空白抢判。
        pass
    elif loco_hard_ok:
        # Jones 三分法则优先于二四法则——内部断层都 ≤ 65° 时 Loco 优先 SeeSaw。
        # 这一档救了 Gandhi（max=126, sec=空, ratio=2.05），让他走 Loco 而非 SeeSaw。
        is_loco = True
        loco_conf = "clear" if 118 <= max_gap <= 155 else "moderate"
        loco_note = ""
    elif valid_seesaw_candidate:
        # 二群对立结构，但因 Loco hard 条件不满足才轮到 SeeSaw 抢判。
        pass
    elif (LOCO_SOFT_MIN_GAP <= max_gap < LOCO_MIN_GAP
          and not (n_sig == 1 and len(visual_splay_gaps) >= 4)):
        # George Washington 等经典火车头案例会落在 114° 左右；
        # 若行星铺陈接近 240° 且次级断裂只略超 65°，按视觉完形保留火车头。
        if span >= 235 and (not secondary or max(secondary) <= LOCO_SOFT_SECONDARY_MAX):
            is_loco = True
            loco_conf = "moderate"
            loco_note = (
                f"（最大空白接近120°；次级空白 "
                f"{max(secondary) if secondary else 0:.1f}°，按经典案例容差）"
            )

    if is_loco:
        leader = _find_leader(sorted_longs, gaps, orig_longs, names)
        # Locomotive 虚空中点：空白扇区（max_gap）的几何中点，走空弧方向
        mid_lon = (leader["tail_long"] + max_gap / 2) % 360
        midpoint_loco = {
            "long":       round(mid_lon, 2),
            "left_name":  leader["tail_name"],
            "left_long":  leader["tail_long"],
            "right_name": leader["leader_name"],
            "right_long": leader["leader_long"],
        }
        return PatternResult(
            pattern_en="Locomotive", pattern_zh="火车头型",
            confidence=loco_conf, max_gap=max_gap, span=span,
            details=(
                f"行星跨越约 {span:.1f}°，留有 {max_gap:.1f}° 的空白{loco_note}。"
                f"【内驱型·三分原则】引导星「{leader['leader_name']}」是全盘的启动引擎，"
                f"空白区的缺失感转化为持续向前的内驱力，自发主动，目标感强烈。"
            ),
            high_focus_planet=leader["leader_name"],
            high_focus_long=leader["leader_long"],
            extra={"leader": leader, "midpoint_loco": midpoint_loco},
        )

    # 火车头软区内若另有三段 ≥45° 的空白，行星已形成多个独立结点，
    # 不宜因一段 90°–115° 的主空白就算作连续的火车头弧。
    # Dua Lipa 的空白为 107.3°/55.7°/48.0°/47.2°；两家公开计算器均判 Splay。
    if (n_sig == 1 and LOCO_SOFT_MIN_GAP <= max_gap < LOCO_MIN_GAP
            and len(visual_splay_gaps) >= 4):
        sellar = _sellar_focus(orig_longs, names)
        return PatternResult(
            pattern_en="Splay", pattern_zh="展开型", confidence="moderate",
            max_gap=max_gap, span=span,
            details=(f"主空白 {max_gap:.1f}° 之外仍有多段约 45° 以上的空白，"
                     "行星分成多个结点，未形成连续的火车头弧。"),
            high_focus_planet=sellar["name"] if sellar else None,
            high_focus_long=sellar["lon"] if sellar else None,
            extra={"cluster_count": len(visual_splay_gaps),
                   "sig_gaps": visual_splay_gaps,
                   "splay_gap_rule": TRIPOD_VISUAL_GAP,
                   "sellar_focus": sellar},
        )

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 4. BUCKET 提桶型（次级检测）[BIPOLAR]
    #    max_gap < 170°，三分格局（Locomotive）已在上方处理完毕
    #    检测顺序：合相把手 → 单星把手（同 Section 2）
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # ── 4a. 合相把手（次级）────────────────────────────────────
    conj_h = _check_conjunction_handle(sorted_longs, orig_longs, names)
    if conj_h:
        conf = "clear" if conj_h["bowl_span"] <= 180 else "moderate"
        return PatternResult(
            pattern_en="Bucket", pattern_zh="提桶型",
            confidence=conf, max_gap=max_gap, span=span,
            details=(
                f"8颗行星形成碗形（跨度 {conj_h['bowl_span']:.1f}°），"
                f"「{conj_h['h1_name']}」与「{conj_h['h2_name']}」"
                f"以 {conj_h['sep']:.1f}° 合相共同充当把手，"
                f"组合把手距碗两端各 ≥ 60°。"
                f"【外激型·二/四分原则】合相把手双星合力聚焦全盘方向，使命叙事双重叠加，目标指向极为清晰。"
            ),
            # 合相把手无单星 HFP（Sellar："These two High Focus Planets"，复数整体）
            high_focus_planet=None,
            high_focus_long=None,
            extra={
                "conj_handle": conj_h,
                "bucket": {
                    "bowl_span":   conj_h["bowl_span"],
                    "handle_name": f'{conj_h["h1_name"]}+{conj_h["h2_name"]}',
                    "handle_long": conj_h["h1_long"],
                    "left_name":   conj_h.get("left_name",  ""),
                    "right_name":  conj_h.get("right_name", ""),
                },
            },
        )

    # ── 4b. 单星把手（次级）────────────────────────────────────
    bucket = _check_bucket(sorted_longs, orig_longs, names)
    if bucket:
        conf = "clear" if bucket["bowl_span"] <= 180 else "moderate"
        return PatternResult(
            pattern_en="Bucket", pattern_zh="提桶型",
            confidence=conf, max_gap=max_gap, span=span,
            details=(
                f"9颗行星形成碗形（跨度 {bucket['bowl_span']:.1f}°），"
                f"把手行星「{bucket['handle_name']}」（{bucket['handle_long']:.1f}°）"
                f"独立于空白区，"
                f"距碗左端「{bucket['left_name']}」{bucket['dist_left']:.1f}°、"
                f"距碗右端「{bucket['right_name']}」{bucket['dist_right']:.1f}°。"
                f"【外激型·二/四分原则】把手星是全盘能量的泄压口，象征「不得不完成」的宿命领域。"
            ),
            high_focus_planet=bucket["handle_name"],
            high_focus_long=bucket["handle_long"],
            extra={"bucket": bucket},
        )

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 5. SPLAY 展开型 [TRIPOLAR — 优先于 Seesaw]
    #    3 个及以上 ≥ 60° 的间隔，形成三脚架式不规则分布
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    if n_sig >= 3:
        conf = "clear" if all(g >= 70 for g in sig_vals) else "moderate"
        gap_desc = "、".join(f"{g:.0f}°" for g in sorted(sig_vals, reverse=True))
        isolated   = _find_isolated(sorted_longs, gaps, orig_longs, names)
        sellar     = _sellar_focus(orig_longs, names)
        grand_trine = None
        # Sellar 第 7 章 HFP 优先级：孤立缰绳星 > 核心对分相较快端 > 大三角最快星
        hfp_name, hfp_long = None, None
        if isolated:
            hfp_name, hfp_long = isolated["name"], isolated["long"]
        elif sellar:
            hfp_name, hfp_long = sellar["name"], sellar["lon"]
        else:
            grand_trine = _find_grand_trine(orig_longs, names)
            if grand_trine:
                hfp_name = grand_trine["fastest"]["name"]
                hfp_long = grand_trine["fastest"]["long"]
        # Sellar 第 8 章 Tripod 定义："3 cluster + 1 standing alone"——
        # 几何上需要孤立行星 + 三个相对均衡的群（无单一主群超过 6 颗）。
        # FDR (sizes=[1,3,6], isolated=天王星): Tripod ✓（三脚架支柱均衡）
        # Jung (sizes=[2,1,7], isolated=土星):  Splay ✓（7-星主群压倒，Jones 称
        # "approaches Splash"，把它归 Splay 因为 raylike 合相群占主导而非三脚架）
        sizes = _cluster_sizes(gaps, sig_idxs)
        is_tripod = isolated is not None and max(sizes) <= 6
        return PatternResult(
            pattern_en=("Tripod" if is_tripod else "Splay"),
            pattern_zh=("三脚架型" if is_tripod else "展开型"),
            confidence=conf, max_gap=max_gap, span=span,
            details=(
                (f"行星呈 3 群独立分布外加 1 颗孤立缰绳星（共 {n_sig+1} 个分组，"
                 f"空白：{gap_desc}）。三脚架结构赋予多维度内在支撑，"
                 f"缰绳星「{isolated['name']}」是控制全盘的统治支点。"
                 if is_tripod else
                 f"行星形成 {n_sig} 个独立星群（各群间空白：{gap_desc}）。"
                 f"【内驱型·三分原则】强烈的个人独立性，拒绝被规训，"
                 f"在多个完全不相干的领域均有顽固的深度追求。")
            ),
            high_focus_planet=hfp_name,
            high_focus_long=hfp_long,
            extra={"cluster_count": n_sig, "sig_gaps": sig_vals,
                   "isolated": isolated,
                   # Sellar：展开型若有对分相则用核心对分相作整合轴线（HFP=较快者/缰绳星）
                   "sellar_focus": sellar,
                   "grand_trine":  grand_trine},
        )

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 6. SEE-SAW 跷跷板型 [BIPOLAR]
    #    恰好 2 个 ≥ 60° 的间隔，且两侧各含多颗行星
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    if n_sig == 2:
        g1, g2 = sig_vals
        sizes = _group_sizes(gaps, sig_idxs)
        # 两侧各须 ≥ 2 颗才是跷跷板；一侧仅1颗是提桶型漏网→落入 Splash
        if min(sizes) >= 2:
            conf = "clear" if min(g1, g2) >= 70 else "moderate"
            # 找主空白区（较大的那段）两侧的边界行星作为张力极点
            i_big = sig_idxs[0] if g1 >= g2 else sig_idxs[1]
            g_big = max(g1, g2)
            g_sml = min(g1, g2)
            pole_a_long = sorted_longs[i_big]
            pole_b_long = sorted_longs[(i_big + 1) % 10]
            pole_a = _find_name(pole_a_long, orig_longs, names)
            pole_b = _find_name(pole_b_long, orig_longs, names)
            # Sellar 原典：See-Saw HFP = 核心对分相较快端
            sellar_ss2 = _sellar_focus(orig_longs, names)
            # 两组各自重心连线（NLM 核验 Jones 原典）：与硬路由同口径——偏向行星更多的一组，
            # 数量打平则偏向更紧密聚集的一组。此路径接住 2:8 漏网型，此前缺 group_axis 字段。
            ss2_groups = _group_members(sorted_longs, gaps, sig_idxs)
            center_a = _circular_mean(ss2_groups[0])
            center_b = _circular_mean(ss2_groups[1])
            span_a = _cw(ss2_groups[0][0], ss2_groups[0][-1]) if len(ss2_groups[0]) > 1 else 0.0
            span_b = _cw(ss2_groups[1][0], ss2_groups[1][-1]) if len(ss2_groups[1]) > 1 else 0.0
            if len(ss2_groups[0]) != len(ss2_groups[1]):
                heavier = "a" if len(ss2_groups[0]) > len(ss2_groups[1]) else "b"
            else:
                heavier = "a" if span_a <= span_b else "b"
            heavier_group = ss2_groups[0] if heavier == "a" else ss2_groups[1]
            heavier_pole_name = pole_a if pole_a_long in heavier_group else (
                pole_b if pole_b_long in heavier_group else "")
            # NLM 核验 Jones 原文（同硬路由那条注释）：没有核心对分相时退回份量更重
            # 那组的边界星，不留空。
            if sellar_ss2:
                hfp_name2, hfp_long2 = sellar_ss2["name"], sellar_ss2["lon"]
            elif heavier_pole_name:
                hfp_name2 = heavier_pole_name
                hfp_long2 = pole_a_long if heavier_pole_name == pole_a else pole_b_long
            else:
                hfp_name2, hfp_long2 = None, None
            return PatternResult(
                pattern_en="See-Saw", pattern_zh="跷跷板型",
                confidence=conf, max_gap=max_gap, span=span,
                details=(
                    f"行星分为两个对立星群（主空白 {g_big:.1f}°，次空白 {g_sml:.1f}°），"
                    f"星群规模约 {sizes[0]}颗 vs {sizes[1]}颗。"
                    f"【外激型·二/四分原则】天生的调停者与战略家；"
                    f"人生通常经历两个交替主导的阶段，终极功课是在两极张力中找到自己的重心。"
                ),
                high_focus_planet=hfp_name2,
                high_focus_long=hfp_long2,
                extra={"group_sizes": sizes, "gaps": [g1, g2],
                       "pole_a": pole_a, "pole_b": pole_b,
                       "sellar_focus": sellar_ss2,
                       "group_axis": {"center_a": round(center_a, 2), "center_b": round(center_b, 2),
                                      "heavier": heavier, "heavier_pole_name": heavier_pole_name}},
            )

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 7. SPLASH 散落型（含孤星节点变体）
    #    行星均匀分布，无显著空白。
    #    特殊：n_sig==2 且一侧仅1颗星（9 vs 1，碗>190°已拒绝提桶），
    #    该孤星作为天然焦点节点升级为 HFP，而非速度最快的行星。
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    conf = "clear" if max_gap <= 60 else "moderate"
    all_idx = list(range(10))

    # 检测孤星节点（9 vs 1）
    # isolated_sorted_idx：孤立行星在 sorted_longs 里的下标
    isolated_sorted_idx = None
    if n_sig == 2:
        sizes = _group_sizes(gaps, sig_idxs)
        if min(sizes) == 1:
            i0, i1 = sorted(sig_idxs)
            group_a = list(range(i0 + 1, i1 + 1))
            group_b = [j for j in range(10) if j not in group_a]
            small = group_a if len(group_a) == 1 else group_b
            if len(small) == 1:
                isolated_sorted_idx = small[0]

    if isolated_sorted_idx is not None:
        # 反查孤星在 orig_longs 里的索引，以正确访问 names[]
        iso_lon = sorted_longs[isolated_sorted_idx]
        hfp_idx = next(
            (i for i, l in enumerate(orig_longs) if abs(l - iso_lon) < 0.01),
            all_idx[0],
        )
        g1, g2  = sig_vals
        bowl_sp = round(360 - g1 - g2, 1)
        details = (
            f"9颗行星弧形分布（跨度 {bowl_sp}°，超190°，不满足提桶条件），"
            f"「{names[hfp_idx]}」孤立于两段空白之间（{g1:.1f}° 与 {g2:.1f}°），"
            f"整体属散落型，但此孤星为全盘天然焦点节点，能量最终向它汇聚。"
        )
    else:
        hfp_idx = None
        details = (
            f"行星均匀分布于星盘各处，最大空白仅 {max_gap:.1f}°。"
            f"【独立型·世界主义】核心心理动力是「世界主义者」气质——自我与外部世界无锐利边界，博览各领域，能量多向分散。核心挑战：整合多元才华，避免「样样精通却无一专精」。"
        )

    splash_extra = {"isolated_node": names[hfp_idx]} if isolated_sorted_idx is not None else {}
    # 赛勒视角：仅普通散落型（非孤星节点）才附加；孤星节点已有自己的 HFP
    if isolated_sorted_idx is None:
        splash_extra["sellar_focus"] = _sellar_focus(orig_longs, names)
    # Sellar HFP fallback：孤星节点优先；无孤星但有对分相 → 取较快端
    if hfp_idx is not None:
        _hfp_n, _hfp_l = names[hfp_idx], orig_longs[hfp_idx]
    elif splash_extra.get("sellar_focus"):
        _sf = splash_extra["sellar_focus"]
        _hfp_n, _hfp_l = _sf["name"], _sf["lon"]
    else:
        _hfp_n, _hfp_l = None, None
    return PatternResult(
        pattern_en="Splash", pattern_zh="散落型",
        confidence=conf, max_gap=max_gap, span=span,
        details=details,
        high_focus_planet=_hfp_n,
        high_focus_long=_hfp_l,
        extra=splash_extra,
    )


# ──────────────────────────────────────────────────────────────
# 越轨行星 → 高焦点行星检测（模糊格局辅助）
# ──────────────────────────────────────────────────────────────

def find_outlier_hfp(
    planetary_longitudes: List[float],
    result: PatternResult,
    planet_names: Optional[List[str]] = None,
) -> Optional[Dict]:
    """
    当星盘接近某种格局但有一颗行星游离于边界之外时，
    将该「越轨行星」标注为高焦点行星（HFP）。

    返回 {"name": ..., "long": ..., "reason": ...} 或 None。
    """
    names = planet_names or PLANET_NAMES_ZH
    orig_longs   = [_norm(l) for l in planetary_longitudes]
    sorted_longs = sorted(orig_longs)
    gaps  = _calc_gaps(sorted_longs)
    max_gap = max(gaps)
    mg_idx  = gaps.index(max_gap)

    if result.pattern_en == "Locomotive":
        # 空白区内是否混入了行星？
        empty_start = sorted_longs[mg_idx]
        for i, long in enumerate(sorted_longs):
            if long == empty_start or long == sorted_longs[(mg_idx + 1) % 10]:
                continue
            d = _cw(empty_start, long)
            if 0 < d < max_gap:
                name = _find_name(long, orig_longs, names)
                return {
                    "name": name, "long": long,
                    "reason": (f"「{name}」位于火车头型空白区内"
                               f"（距起点 {d:.1f}°），成为全盘高焦点行星。"),
                }

    if result.pattern_en == "Bowl":
        empty_start = sorted_longs[mg_idx]
        for i, long in enumerate(sorted_longs):
            if long == empty_start:
                continue
            d = _cw(empty_start, long)
            if 0 < d < max_gap:
                name = _find_name(long, orig_longs, names)
                return {
                    "name": name, "long": long,
                    "reason": (f"「{name}」越入碗型空白区"
                               f"（距碗口 {d:.1f}°），成为高焦点行星。"),
                }
    return None


# ──────────────────────────────────────────────────────────────
# 便捷接口：字典输入
# ──────────────────────────────────────────────────────────────

def detect_from_dict(planet_dict: Dict[str, float], lang: str = "zh") -> PatternResult:
    """从字典输入检测格局（含变形格局）。"""
    order = ["Sun", "Moon", "Mercury", "Venus", "Mars",
             "Jupiter", "Saturn", "Uranus", "Neptune", "Pluto"]
    missing = [p for p in order if p not in planet_dict]
    if missing:
        raise ValueError(f"缺少行星数据：{missing}")
    return detect_with_variants(
        [planet_dict[p] for p in order],
        planet_names=(PLANET_NAMES_ZH if lang == "zh" else PLANET_NAMES_EN),
        lang=lang,
    )


# ──────────────────────────────────────────────────────────────
# 关键行星角色构建（供前端高亮）
# ──────────────────────────────────────────────────────────────

def _name_to_cn(name: str) -> str:
    """'太阳☉' → '太阳'（去掉符号，与 API 返回的 cn 字段匹配）"""
    for sym in "☉☽☿♀♂♃♄♅♆♇★◆◉⟺":
        name = name.replace(sym, "")
    return name.strip()


# 行星速度查找表（中英文均支持；数字越小速度越快）
_SPEED_RANK_MAP: Dict[str, int] = {
    "太阳": 3, "月亮": 0, "水星": 1, "金星": 2, "火星": 4,
    "木星": 5, "土星": 6, "天王星": 7, "海王星": 8, "冥王星": 9,
    "Sun": 3, "Moon": 0, "Mercury": 1, "Venus": 2, "Mars": 4,
    "Jupiter": 5, "Saturn": 6, "Uranus": 7, "Neptune": 8, "Pluto": 9,
}


def _planet_speed_rank(name: str) -> int:
    """返回行星速度排名（越小越快）；未知行星返回 99。"""
    clean = _name_to_cn(name)
    for k, v in _SPEED_RANK_MAP.items():
        if k in clean:
            return v
    return 99


def _is_opposite_sign(lon1: float, lon2: float) -> bool:
    """两颗行星是否在对冲星座（星座序号相差恰好 6）。"""
    s1 = int(lon1 / 30) % 12
    s2 = int(lon2 / 30) % 12
    return (s1 - s2) % 12 == 6 or (s2 - s1) % 12 == 6


def _sellar_focus(orig_longs: List[float], names: List[str]) -> Optional[Dict]:
    """
    赛勒视角（Wanda Sellar《Chart Shapes: The Code To Interpretation》）：
    在所有实际对分相中，找出由速度最快的两颗行星组成的"核心对分相"，
    取其中速度更快的那颗作为辅助解读切入点。

    对分相判定条件（双重限制）：
      1. 两星必须处于对冲星座（星座序号差 6，如巨蟹↔摩羯）
      2. 实际度数差在 180° ± 10°（容许度 10°）以内

    适用于：散落型（Splash）、跷跷板型（See-Saw）、沙漏型（Hourglass）、展开型（Splay）

    注意：这是后续发展视角，非琼斯原典定义。
    琼斯原著对这些格局明确表示"无法或不总是能确定单一焦点行星"。
    Sellar 没有为核心对分相另定数值阈值；这里沿用 Jones《The Guide to
    Horoscope Interpretation》附录与 Sabian 体系对非日月行星主要相位的 10°标准，
    并与本命盘普通对分相保持一致。

    返回 {"name": str, "lon": float, "opp_name": str, "opp_lon": float} 或 None。
    """
    n = len(orig_longs)
    best: Optional[Tuple[int, int, int, int]] = None
    best_key = (999, 999)

    for i in range(n):
        for j in range(i + 1, n):
            # 条件 1：必须在对冲星座
            if not _is_opposite_sign(orig_longs[i], orig_longs[j]):
                continue
            # 条件 2：实际度数差 180° ± 10°
            diff = abs(orig_longs[i] - orig_longs[j])
            if diff > 180:
                diff = 360 - diff
            if abs(diff - 180) > SELLAR_OPPOSITION_ORB:
                continue
            ri = _planet_speed_rank(names[i])
            rj = _planet_speed_rank(names[j])
            # 主键：速度排名之和（越小=整体越快）；次键：较慢的那颗排名
            key = (ri + rj, max(ri, rj))
            if key < best_key:
                best_key = key
                best = (i, j, ri, rj)

    if best is None:
        return None

    i, j, ri, rj = best
    focus_idx = i if ri <= rj else j
    opp_idx   = j if ri <= rj else i
    return {
        "name":     names[focus_idx],
        "lon":      orig_longs[focus_idx],
        "opp_name": names[opp_idx],
        "opp_lon":  orig_longs[opp_idx],
    }


def _find_grand_trine(
    orig_longs: List[float],
    names: List[str],
    orb: float = 6.0,
) -> Optional[Dict]:
    """
    大三角检测：3 颗行星互相形成 120° ± orb 三分相。
    返回最紧密的大三角（orb 总和最小）+ 其中速度最快的行星。

    用途：Sellar 第 7 章原典——Splay 无核心对分相但有大三角时，HFP 是大三角最快星。
    SELLAR HFP 优先级：孤立缰绳星 > 核心对分相较快端 > 大三角最快星

    返回 {"members": [{name, long}, ...], "fastest": {name, long}, "orb_sum"} 或 None。
    """
    n = len(orig_longs)
    best: Optional[Dict] = None
    best_orb_sum = 999.0

    for i in range(n):
        for j in range(i + 1, n):
            for k in range(j + 1, n):
                ok = True
                orbs = []
                for a, b in ((i, j), (j, k), (i, k)):
                    d = abs(orig_longs[a] - orig_longs[b])
                    if d > 180:
                        d = 360 - d
                    delta = abs(d - 120)
                    if delta > orb:
                        ok = False
                        break
                    orbs.append(delta)
                if not ok:
                    continue

                orb_sum = sum(orbs)
                if orb_sum < best_orb_sum:
                    best_orb_sum = orb_sum
                    ranks = sorted(
                        [(_planet_speed_rank(names[idx]), idx) for idx in (i, j, k)]
                    )
                    fastest_idx = ranks[0][1]
                    best = {
                        "members": [
                            {"name": names[idx], "long": orig_longs[idx]}
                            for idx in (i, j, k)
                        ],
                        "fastest": {
                            "name": names[fastest_idx],
                            "long": orig_longs[fastest_idx],
                        },
                        "orb_sum": round(orb_sum, 2),
                    }
    return best


# 各角色的中文标签与说明
_ROLE_META: Dict[str, Tuple[str, str]] = {
    "leader_loco":      ("车头 ★",  "顺时针穿越大空白区后的第一颗行星（cutting planet），是火车头型的启动引擎，具最强驱动力与目标感"),
    "tail_loco":        ("车尾",     "紧贴大空白区末端的行星，为火车头提供持续推力，代表积蓄与兜底力量"),
    "leader_bowl":      ("引导星 ★", "碗口边界、率先朝向空白半球的第一颗行星，代表你「如何伸手舀取未知经验」的战术姿态；属次要——碗的倾斜与占据半球重心（承重墙）才是根本焦点（Jones：引导星居次位）"),
    "tail_bowl":        ("尾随星",   "碗口另一端的边界行星，与引导星相对——代表事情如何收尾、落地的耐力；状态强则善始善终，弱则容易半途而废（Jones：尾随星决定结局走向）"),
    # Sellar 原典裁定：Bundle/Wedge 无单一 HFP/领头星，解读起点是两端边界星的限制相位 + 中点
    "boundary_bundle_left":  ("丛聚左端 ◆", "丛聚跨度的左边界行星，与右端边界共同形成限制性四分/三分相，定义全盘聚焦的力学边界"),
    "boundary_bundle_right": ("丛聚右端 ◆", "丛聚跨度的右边界行星，与左端边界相互限制，两端相位质地是丛聚解读的激活点"),
    "handle":           ("把手 ◆",  "孤立于碗外、漂浮在空白区的把手星，汇聚全盘能量并定向释放，是人生核心使命的焦点"),
    "handle1":          ("把手① ◆", "合相把手星之一，与另一颗合相行星共同引导全盘能量，双星合力聚焦使命方向"),
    "handle2":          ("把手② ◆", "合相把手星之二，与另一颗合相行星形成双重力量，强化把手的引导功能"),
    "handle_left":      ("左把手 ◆", "左侧把手行星，代表双轨使命中的其中一条主轴，提供独立的生命方向"),
    "handle_right":     ("右把手 ◆", "右侧把手行星，代表双轨使命中的另一条主轴，与左把手共同构成人生双焦点"),
    "bowl_edge_left":   ("碗左端",   "碗形星群的左边界行星，与另一端共同界定碗口边界，形成过滤外界经验的心理边界"),
    "bowl_edge_right":  ("碗右端",   "碗形星群的右边界行星，与另一端共同界定碗口边界，是外界经验进入内心前的另一道滤口"),
    "bowl_edge_leading":  ("领头端边界星", "提桶碗体的领头端边界，与把手偏向的判断挂钩——把手若偏这一端，行事更谨慎、更有准备"),
    "bowl_edge_trailing": ("尾随端边界星", "提桶碗体的尾随端边界，与把手偏向的判断挂钩——把手若偏这一端，行事更冲动、更愿意冒险"),
    "cog_bowl":         ("承重墙 ◈", "坐镇占据半球几何重心（虚空中点正对面）的行星——Rudhyar 所谓「绝对底牌」：资源最集中、最受自己掌控，是供能填补对面虚空的核心武器，比引导星更根本（引导星只说明你「如何伸手舀取」，承重墙才是兑换虚空的底牌）"),
    # NLM 核验 Sellar《Guide to Horoscope Interpretation》p.43："The midpoint pertaining
    # to the boundary planets is of particular importance, and can be judged by its
    # sign and house." ——虚点/未锚定重心点靠自身星座宫位独立成立，不必等行星合相。
    "void_bowl":        ("虚点 ◐", "空白半球的几何中点——Jones 原典：未占据的这一半是「the challenge to existence」，是持续投注意识的匮乏来源与终生凝视的方向；即便无行星合相，仅凭星座与宫位即可独立判读"),
    "cog_bowl_point":   ("碗底 ◈", "占据半球的几何重心（虚空中点正对面），此处未见行星锚定——Rudhyar 原典：即便无行星在场，这个点本身仍是「意识活动半球的重心」，凭星座与宫位即可独立判读，比引导星更根本"),
    "isolated_splay":    ("缰绳星 ◉",  "两侧皆有大间隔的孤立行星，是展开型中最不受约束的能量出口，代表独立的创造性冲动"),
    "isolated_tripod":   ("缰绳星 ◉",  "三组分布中两侧皆有大间隔的孤立行星，是贯通三脚架三条支柱的首要解读入口"),
    "isolated_butterfly":("顶点星 ◉",  "嵌于两对立群之间的孤星，常为T三角顶点，是两翼高压能量的汇聚与爆发口"),
    "isolated_splash":   ("孤星节点 ◉","9颗行星弧形分布时夹在两段空白之间的孤立行星，碗跨度超190°不足以构成提桶，但此星仍是全盘天然焦点"),
    "seesaw_pole_a":     ("张力极 ⟺",  "主空白区一侧的边界行星，与对面极点跨越最大虚空相对而立，是跷跷板对立张力的具象承载者"),
    "seesaw_pole_b":     ("张力极 ⟺",  "主空白区另一侧的边界行星，与对面极点共同撑起整盘辩证结构，两极之间的张力即人生核心功课"),
    # Sellar 体系的"核心对分相较快端"——只属 Splash/See-Saw/Hourglass/Splay 这 4 个无天然几何焦点的格局；
    # 概念上区别于 Jones 的几何 HFP（把手星/领头星/孤星顶点），用"整合焦点"突出其"在散乱能量中收拢脊梁"的功能。
    "sellar_hfp":        ("整合焦点 ✦", "核心对分相中速度较快的一端，是分散能量的整合切入点，提供解读的'星盘脊梁'（Sellar 体系）"),
    # Sellar 第 7 章 fallback：Splay 无对分相但有大三角时，HFP 是大三角最快星。
    # 与 sellar_hfp 同属 Sellar HFP 系统，但触发路径不同（和谐相位 vs 对立相位）。
    "sellar_hfp_trine":  ("整合焦点 △", "大三角中速度最快的行星——展开型无核心对分相时的 HFP，代表和谐流通能量的引领者（Sellar 体系）"),
}


def _conj_composite_note(ch: Dict, this_name: str) -> str:
    """合相把手卡的动态判读 note（NLM 逐字核验 Sellar 合相把手章节）。

    两条原文依据：① Agatha Christie 案例称两星为 "These two High Focus
    Planets"（复数）——单一复合焦点整体读，不拆主次先后；② 全书通则
    "When considering an aspect, the slower planet affects the faster one."
    ——较慢星为较快星的表达定调。"较快者优先"只属于双把手，不适用于此。

    ⚠️ 文案只给结论、不报规则名：慢/快法则用于**判断**谁给谁定调，但不写
    "按较慢影响较快法则"这类话——那是在卡片里给读者补相位课，且要求他先懂
    另一套体系。这张卡的职责是解读这组合相把手本身。
    """
    h1, h2 = ch.get("h1_name", ""), ch.get("h2_name", "")
    sep = ch.get("sep")
    if not h1 or not h2 or sep is None:
        return ""
    this_cn = _name_to_cn(this_name)
    h1_cn, h2_cn = _name_to_cn(h1), _name_to_cn(h2)
    other_cn = h2_cn if this_cn == h1_cn else h1_cn
    if _planet_speed_rank(h1) <= _planet_speed_rank(h2):
        faster_cn, slower_cn = h1_cn, h2_cn
    else:
        faster_cn, slower_cn = h2_cn, h1_cn
    return (f"本盘实际判定：与{other_cn}以{sep:.1f}°紧密合相构成单一复合焦点，"
            f"整体阅读、不拆主次先后；由{slower_cn}为{faster_cn}的表达定调，"
            f"合相越紧力量越强。")


def _cog_partner_note(cog: dict) -> str:
    """碗中心复合合相的角色说明。只描述几何事实，读法交给解读层。"""
    partners = (cog or {}).get("partners") or []
    if not partners:
        return ""
    parts = "、".join(f"{_name_to_cn(p['planet_name'])}（相距{p['orb']:.1f}°）" for p in partners)
    return (f"与{parts}合相，同在碗中心附近：作为复合的碗中心一起读，"
            f"不只取距离最近的一颗。")


def _handle_cog_opposition_note(cog: dict, handle_long, tilt: str) -> str:
    """Sellar Ch.5：把手正对碗中心＝高度聚焦；“especially if the handle is in opposition
    to a planet within the centre of the bowl”——后半句要求真实的对分相，不能只看把手居中。
    碗中心行星（含合相伙伴）与把手偏离正对分 ≤ SELLAR_OPPOSITION_ORB 才写成对分实心轴。"""
    if tilt != "centered" or handle_long is None:
        return ""
    longs = [(cog or {}).get("planet_long")] + [p.get("planet_long") for p in (cog or {}).get("partners") or []]
    devs = []
    for lon in longs:
        if lon is None:
            continue
        sep = abs(((float(lon) - float(handle_long) + 180.0) % 360) - 180.0)
        devs.append(abs(180.0 - sep))
    if not devs:
        return "把手正对碗中心，聚焦力极强。"
    dev = min(devs)
    if dev <= SELLAR_OPPOSITION_ORB:
        return f"碗中心行星与对面的把手成对分（偏离约{dev:.1f}°），连成一条实心轴，目标明确、专注力极强。"
    return (f"把手正对碗中心，聚焦力极强；但碗中心行星与把手偏离正对分约{dev:.1f}°，"
            f"没有构成对分相，不按对分来读。")


def _build_key_roles(
    result: PatternResult,
    planet_meta: Optional[Dict[str, Dict]] = None,
) -> List[Dict]:
    """
    从 PatternResult.extra 提取关键行星角色列表。
    每条记录基础字段：{"name_cn", "role_type", "role_label", "role_desc"}

    若提供 planet_meta（zh_name → {sign, house, abs_pos, ...}），
    每条角色记录会附加对应行星的星座/宫位/经度元数据，便于前端动态展示。

    planet_meta 来源：app.py 从 natalData['planets'] 构造。
    name_cn 已去符号，可直接与 API 返回的 p["cn"] 匹配。
    """
    roles: List[Dict] = []
    pat   = result.pattern_en
    extra = result.extra

    def add(name: str, rtype: str, note: str = "") -> None:
        if not name:
            return
        label, desc = _ROLE_META.get(rtype, (rtype, ""))
        cn = _name_to_cn(name)
        role: Dict = {
            "name_cn":   cn,
            "role_type":  rtype,
            "role_label": label,
            "role_desc":  f"{desc}{note}" if note else desc,
            # note 单独存一份：miniapp 侧用自己的公开版静态文案（jones_pattern_guide.py），
            # 不会读 role_desc，得靠这个字段把「这张盘特有」的动态判断（把手偏哪端/
            # 哪组更重/顶点星隐藏中点）接到公开文案后面，否则算出来也传不到前端。
            "note":       note,
        }
        if planet_meta:
            meta = planet_meta.get(cn)
            if meta:
                # 把星座/宫位/经度附加进去，前端可直接读 role.sign / role.house 等
                for k in ("sign", "house", "abs_pos", "pos_in_sign", "retrograde"):
                    if k in meta:
                        role[k] = meta[k]
        roles.append(role)

    def add_point(label_cn: str, long_: float, rtype: str, note: str = "") -> None:
        # 几何虚点专用（无行星可锚定）：NLM 核验 Sellar《Guide to Horoscope
        # Interpretation》p.43 原文——"The midpoint pertaining to the boundary planets
        # is of particular importance, and can be judged by its sign and house."
        # 即：先靠这个点自身的星座/宫位独立成立，"有没有行星合相"是后一层、可选的加成，
        # 不是这个点存不存在的前提。此前 add() 要求 name 非空才收录，虚点/未锚定重心点
        # 因此整条从「关键位置」消失，只留在环形图的图例里——这里补一条不靠行星名的路径。
        if long_ is None:
            return
        label, desc = _ROLE_META.get(rtype, (rtype, ""))
        roles.append({
            "name_cn":    label_cn,
            "role_type":  rtype,
            "role_label": label,
            "role_desc":  f"{desc}{note}" if note else desc,
            "note":       note,
            "abs_pos":    round(_norm(long_), 2),
        })

    # ── Locomotive ──────────────────────────────────────────────
    if pat == "Locomotive":
        ldr = extra.get("leader", {})
        add(ldr.get("leader_name", ""), "leader_loco")
        add(ldr.get("tail_name",   ""), "tail_loco")

    # ── Bundle ──────────────────────────────────────────────────
    # Sellar/Jones 原典裁定：Bundle 无单一领头星，解读起点是两端边界星 + 中点。
    # _find_leader 返回的 leader_name/tail_name 实际就是空白区两侧的边界星。
    elif pat == "Bundle":
        ldr = extra.get("leader", {})
        add(ldr.get("leader_name", ""), "boundary_bundle_left")
        add(ldr.get("tail_name",   ""), "boundary_bundle_right")

    # ── Bowl ────────────────────────────────────────────────────
    elif pat == "Bowl":
        ldr = extra.get("leader", {})
        leader_cn = _name_to_cn(ldr.get("leader_name", ""))
        add(ldr.get("leader_name", ""), "leader_bowl")
        # 碗的另一端（trailing 边界星，与 leader 一起是 _find_leader 已算好的一对）：
        # NLM 核验 Jones 原典——碗型是「领头星+尾随星」一对，此前 tail_name 只在
        # Locomotive 用过，Bowl 侧一直被落在通用 bowl_edge_left 里、丢了「尾随星＝收尾质地」
        # 这层专属含义。left_boundary/right_boundary 分别就是 tail_name/leader_name（同一星
        # 只是取名不同），故这里直接改用 leader/tail 语义，不再走 bowl_edge_left/right。
        tail_cn = _name_to_cn(ldr.get("tail_name", ""))
        add(ldr.get("tail_name", ""), "tail_bowl")
        # 承重墙/绝对底牌：占据半球几何重心（=虚空中点正对面）上坐镇的行星（cog_bowl，10° 内）。
        # Rudhyar：比引导星更核心——引导星只是「如何伸手」，承重墙才是兑换虚空的底牌资源。
        # 几何上重心居占据半球正中、边界星/引导星在两端，正常不重叠；仍加去重守卫防边缘情形。
        cog = extra.get("cog_bowl") or {}
        cog_cn = _name_to_cn(cog.get("planet_name", ""))
        if cog_cn and cog_cn not in (leader_cn, tail_cn):
            add(cog.get("planet_name", ""), "cog_bowl", note=_cog_partner_note(cog))
        elif not cog_cn and cog.get("long") is not None:
            # 只在「10° 内确实没有任何行星」时才落到几何虚点路径，不能让这个点从
            # 「关键位置」整条消失（原来 add() 要求行星名非空，重心点因此只留在环形图
            # 图例里）。若 cog_cn 非空但等于 leader/tail（去重命中的边缘情形），说明碗底
            # 其实是有行星的，只是跟引导/尾随星是同一颗——这里不该改口说"没有行星"。
            add_point("碗底", cog["long"], "cog_bowl_point")
        # 虚点（空白半球几何中点）：定义上从不会有行星落在这里（否则半球就不空了），
        # 因此从来不走 planet_meta 锚定路径，必须无条件补一条几何点角色卡。
        mid = extra.get("midpoint_bowl") or {}
        if mid.get("long") is not None:
            add_point("虚点", mid["long"], "void_bowl")

    # ── Bucket / Sling / Fanhandle ───────────────────────────────
    elif pat in ("Bucket", "Sling", "Fanhandle"):
        ch = extra.get("conj_handle")   # Fanhandle 合相把手 / ConjHandle 复用
        bk = extra.get("bucket", {})
        if ch:
            # 合相扇柄：两颗行星分别独立标注，前端可逐一匹配；
            # note 讲复合焦点+慢星定调（见 _conj_composite_note 的原文依据）
            add(ch.get("h1_name", ""), "handle1",
                note=_conj_composite_note(ch, ch.get("h1_name", "")))
            add(ch.get("h2_name", ""), "handle2",
                note=_conj_composite_note(ch, ch.get("h2_name", "")))
            add(ch.get("left_name",  ""), "bowl_edge_left")
            add(ch.get("right_name", ""), "bowl_edge_right")
        else:
            # 把手偏边界星哪一端（NLM 核验 Sellar 原文精确引用："If the handle planet is
            # closer to the leading boundary planet, then the individual is more cautious;
            # closer to the trailing planet, then more adventurous."）：正中＝聚焦力最强，
            # 偏领头端＝更谨慎，偏尾随端＝更冒险。三张卡都必须写「这张盘的实际判定」并
            # 点名行星——此前把手 note 只说"偏向尾随端"这种抽象方位、两张边界星卡只有
            # "把手若偏向这一端"的假设句，读者拿三张卡拼不出把手到底偏谁（真实反馈：
            # 伊斯特伍德盘看不出土星偏海王星还是天王星）。
            _handle_cn = _name_to_cn(bk.get("handle_name", ""))
            _lead_cn   = _name_to_cn(bk.get("right_name", ""))   # 领头端＝空白后第一颗
            _trail_cn  = _name_to_cn(bk.get("left_name",  ""))   # 尾随端
            _tilt = bk.get("handle_tilt", "")
            _tilt_note = {
                "centered": f"本盘实际判定：把手{_handle_cn}正落在两边界星中点上，不偏任何一端，聚焦力极强。",
                "leading":  f"本盘实际判定：把手{_handle_cn}偏向领头端{_lead_cn}，行事更谨慎、更有准备。",
                "trailing": f"本盘实际判定：把手{_handle_cn}偏向尾随端{_trail_cn}，行事更冲动、更愿意冒险。",
            }.get(_tilt, "")
            add(bk.get("handle_name", ""), "handle", note=_tilt_note)
            # 两颗边界星卡各自补一句实际结论，静态"若偏向"假设句之后读者不用再自己拼。
            _edge_notes = {
                "centered": (f"本盘把手{_handle_cn}正落中点，不偏这一端。",
                             f"本盘把手{_handle_cn}正落中点，不偏这一端。"),
                "leading":  (f"本盘把手{_handle_cn}实际偏向对面的领头端{_lead_cn}。",
                             f"本盘把手{_handle_cn}实际偏向这一端。"),
                "trailing": (f"本盘把手{_handle_cn}实际偏向这一端。",
                             f"本盘把手{_handle_cn}实际偏向对面的尾随端{_trail_cn}。"),
            }.get(_tilt, ("", ""))
            add(bk.get("left_name",   ""), "bowl_edge_trailing", note=_edge_notes[0])
            add(bk.get("right_name",  ""), "bowl_edge_leading",  note=_edge_notes[1])

    # ── ConjHandle ──────────────────────────────────────────────
    elif pat == "ConjHandle":
        ch = extra.get("conj_handle", {})
        add(ch.get("h1_name", ""), "handle1",
            note=_conj_composite_note(ch, ch.get("h1_name", "")))
        add(ch.get("h2_name", ""), "handle2",
            note=_conj_composite_note(ch, ch.get("h2_name", "")))
        add(ch.get("left_name",  ""), "bowl_edge_left")
        add(ch.get("right_name", ""), "bowl_edge_right")

    # ── TwoHandle ───────────────────────────────────────────────
    elif pat == "TwoHandle":
        tw = extra.get("two_handle", {})
        # 双把手不适用单把手那条「偏向领头/尾随端」判定——NLM 核验：Sellar 只把
        # 偏向规则写在单把手基础章节，双把手变体与丘吉尔案例都未改写它，硬套即臆造。
        # 双把手的等价判定是「谁先读」：原文 "The faster moving planetary handle
        # should be considered as the High Focus Planet, and chosen first in
        # interpretation"（丘吉尔海王星+冥王星双把手，海王星因较快而胜出）。
        # hfp_name 引擎早已按 _planet_speed_rank 算好，但两张把手卡文案此前完全
        # 对称，读者看不出谁是首要入口——与「把手偏向算了不显示」同一个病，一并说出口。
        _h1, _h2 = tw.get("h1_name", ""), tw.get("h2_name", "")
        _hfp_cn  = _name_to_cn(tw.get("hfp_name", ""))
        _h1_cn, _h2_cn = _name_to_cn(_h1), _name_to_cn(_h2)
        # 两把手同宫（Sellar 原文："If the two planets are in the same house,
        # this suggests one area of life has two separate influences, and
        # expressions."）——宫位由 planet_meta 透传，缺失时静默跳过。
        _m = planet_meta or {}
        _h1_house = (_m.get(_h1_cn) or {}).get("house")
        _h2_house = (_m.get(_h2_cn) or {}).get("house")
        _same_house = (f"两个把手同落第{_h1_house}宫——同一个生活领域里"
                       f"拥有两种独立的影响与表达方式。"
                       if _h1_house and _h1_house == _h2_house else "")
        def _hfp_note(this_cn: str) -> str:
            if not _hfp_cn:
                return _same_house
            other_cn = _h2_cn if this_cn == _h1_cn else _h1_cn
            if this_cn == _hfp_cn:
                base = (f"本盘实际判定：两个把手里{this_cn}运行较快，是首要解读入口，"
                        f"先读它、再对照{other_cn}。")
            else:
                base = (f"本盘实际判定：{other_cn}运行较快、解读顺序在前，"
                        f"{this_cn}作为第二条主轴对照着读。")
            return base + _same_house
        add(_h1, "handle_left",  note=_hfp_note(_h1_cn))
        add(_h2, "handle_right", note=_hfp_note(_h2_cn))
        # 桶身两端的边界星也是核心解读要素（Sellar：把手星始终与边界星相关联）
        add(tw.get("left_name", ""),  "bowl_edge_left")
        add(tw.get("right_name", ""), "bowl_edge_right")

    # ── See-Saw / Hourglass ────────────────────────────────────
    # 两套体系并存：张力极（Jones 几何）+ 整合焦点（Sellar 核心对分相）
    # 概念分离：seesaw_pole_a/b 标边界张力，sellar_hfp 标分散能量的整合切入点
    elif pat in ("See-Saw", "Hourglass"):
        # 两组各自重心连线（NLM 核验 Jones 原典）：没有其他焦点星时，人生份量偏向哪一组
        # ——偏向行星更多的一组，数量打平则偏向更紧密聚集的一组。这层此前完全没暴露。
        ga = extra.get("group_axis") or {}
        heavier_name = ga.get("heavier_pole_name", "")
        _weight_note = "这一侧行星更多/更紧密聚集，是两组重心连线里份量更重的一端。" if heavier_name else ""
        add(extra.get("pole_a", ""), "seesaw_pole_a",
            note=_weight_note if _name_to_cn(extra.get("pole_a", "")) == _name_to_cn(heavier_name) else "")
        add(extra.get("pole_b", ""), "seesaw_pole_b",
            note=_weight_note if _name_to_cn(extra.get("pole_b", "")) == _name_to_cn(heavier_name) else "")
        sf = extra.get("sellar_focus")
        if sf:
            add(sf.get("name", ""), "sellar_hfp")

    # ── Splay ───────────────────────────────────────────────────
    # Sellar HFP 优先级（原典第 7 章）：孤立缰绳星 > 核心对分相较快星 > 大三角最快星
    # 三档全部实现：1+2 主路径；3 作 base 没有 sellar_focus 时的 fallback。
    elif pat == "Splay":
        iso = extra.get("isolated")
        if iso:
            add(iso.get("name", ""), "isolated_splay")
        sf = extra.get("sellar_focus")
        if sf and (not iso or sf.get("name") != iso.get("name")):
            add(sf.get("name", ""), "sellar_hfp")
        # 第 3 档：无孤星无对分相时，大三角最快星就是 HFP
        gt = extra.get("grand_trine")
        if gt and not iso and not sf:
            add(gt["fastest"].get("name", ""), "sellar_hfp_trine")

    # ── Tripod ──────────────────────────────────────────────────
    # Sellar 原典：Tripod 的 HFP 优先级（继承 Splay 体系）——
    # 1) 单独站立的孤立行星（reins planet/缰绳星）
    # 2) 核心对分相较快端（loose_tripod 路径无孤星时 fallback）
    # 3) 大三角最快星（同上 fallback 第二档）
    elif pat == "Tripod":
        iso = extra.get("isolated")
        if iso:
            add(iso.get("name", ""), "isolated_tripod")
        else:
            # loose_tripod 路径（3 群均 ≥ 2 颗，无单独孤星）按 Sellar HFP 优先级 fallback
            sf = extra.get("sellar_focus")
            if sf:
                add(sf.get("name", ""), "sellar_hfp")
            else:
                gt = extra.get("grand_trine")
                if gt:
                    add(gt["fastest"].get("name", ""), "sellar_hfp_trine")

    # ── Butterfly ───────────────────────────────────────────────
    elif pat == "Butterfly":
        iso = extra.get("isolated")
        if iso:
            # 顶点星与较近一翼的交叉点近似真中点（NLM 核验 Sellar），此前没暴露这层。
            cp = extra.get("crossing_point") or {}
            _cp_note = (
                f"与较近一翼的「{_name_to_cn(cp['near_name'])}」之间还有一个隐藏中点，也值得留意。"
            ) if cp.get("near_name") else ""
            add(iso.get("name", ""), "isolated_butterfly", note=_cp_note)

    # ── Splash（孤星节点变体）───────────────────────────────────
    # Splash 的 Sellar HFP 是首要解读切入点（原典："核心对分相提供星盘脊梁"）
    elif pat == "Splash":
        iso_name = extra.get("isolated_node", "")
        if iso_name:
            add(iso_name, "isolated_splash")
        sf = extra.get("sellar_focus")
        if sf and sf.get("name") != iso_name:
            add(sf.get("name", ""), "sellar_hfp")

    # ── 把手族共用：承重墙 / 碗底卡 ─────────────────────────────
    # cog_bowl 的计算 Bowl 与把手族共用（result_to_dict 统一回填），但此前只有
    # Bowl 分支把它转成角色卡——把手族「算了不显示」。与 Bowl 同一套三态输出：
    # 10° 内有行星锚定 → 承重墙卡；确实无行星 → 纯几何碗底点卡（Sellar p.43：
    # 这个点先凭星座/宫位独立成立，行星合相是可选加成）。去重守卫：碗底行星可能
    # 恰好就是边界星或把手本身，已有卡片时不重复出卡、也不改口说"没有行星"。
    if pat in ("Bucket", "Sling", "Fanhandle", "ConjHandle", "TwoHandle"):
        cog = extra.get("cog_bowl") or {}
        cog_cn = _name_to_cn(cog.get("planet_name", ""))
        _taken = {r["name_cn"] for r in roles}
        if cog_cn and cog_cn not in _taken:
            # Sellar Ch.5（原文）："If the handle planet is directly above the centre of the
            # bowl, this is considered highly focused energy, especially if the handle is in
            # opposition to a planet within the centre of the bowl."——居中与对分分开判断：
            # 星座对冲而度数超出容许度时，不写成对分实心轴。
            _bk = extra.get("bucket") or {}
            _cog_note = _handle_cog_opposition_note(cog, _bk.get("handle_long"),
                                                    _bk.get("handle_tilt", ""))
            add(cog.get("planet_name", ""), "cog_bowl",
                note=(_cog_note + _cog_partner_note(cog)).strip())
        elif not cog_cn and cog.get("long") is not None:
            add_point("碗底", cog["long"], "cog_bowl_point")

    return roles


# ──────────────────────────────────────────────────────────────
# Flask / API 序列化
# ──────────────────────────────────────────────────────────────

def result_to_dict(
    result: PatternResult,
    planet_meta: Optional[Dict[str, Dict]] = None,
    houses: Optional[List[Dict]] = None,
) -> Dict:
    """将 PatternResult 序列化为 JSON 友好字典（供 Flask API 使用）。

    planet_meta（可选）：{zh_name → {sign, house, abs_pos, ...}}，传入后
    key_roles 每项会附加对应行星的星座/宫位/经度元数据，便于前端动态展示。

    houses（可选）：[{'abs_pos': cusp_lon}, ...] 共 12 个，用于为中点计算宫位。
    """
    # 辅助：给定经度，返回 sign_zh, pos_in_sign
    ZODIAC_ZH = ["白羊座","金牛座","双子座","巨蟹座","狮子座","处女座",
                 "天秤座","天蝎座","射手座","摩羯座","水瓶座","双鱼座"]
    def _sign_of(lon: float):
        norm = ((lon % 360) + 360) % 360
        idx = int(norm // 30)
        pos = norm - idx * 30
        return ZODIAC_ZH[min(idx, 11)], round(pos, 2)

    def _house_of(lon: float):
        if not houses or len(houses) < 12:
            return None
        norm = ((lon % 360) + 360) % 360
        cusps = [((h.get("abs_pos", 0) % 360) + 360) % 360 for h in houses[:12]]
        for i in range(12):
            start = cusps[i]
            end = cusps[(i + 1) % 12]
            if start <= end:
                if start <= norm < end:
                    return i + 1
            else:
                if norm >= start or norm < end:
                    return i + 1
        return None

    def _enrich_midpoint(mp: dict):
        if not mp:
            return None
        sign, pos = _sign_of(mp["long"])
        h = _house_of(mp["long"])
        # Sellar：中点解读「包含其对面宫位」(and that opposite)，附对位轴端供阅读层
        opp = (mp["long"] + 180) % 360
        opp_sign, _opp_pos = _sign_of(opp)
        opp_h = _house_of(opp)
        return {**mp, "sign_zh": sign, "pos_in_sign": pos, "house": h or "",
                "opp_long": round(opp, 2), "opp_sign_zh": opp_sign,
                "opp_house": opp_h or ""}

    def _scan_cog(mid_long: float) -> dict:
        """由虚空中点算「格局重心点」并检测实体行星锚定。

        重心点 = 虚空中点 +180°（占据半球几何重心，Rudhyar）。在 planet_meta 里
        找最近合相行星：≤10° 记为「承重墙」底牌（planet_name/dist）；
        ≤COG_ANCHOR_ORB 再升级 is_anchor=True（「碗底锚点/隐藏重心星」）。
        planet_meta 缺失（如纯几何单测）时只返回几何点 long。
        """
        cog_lon = (mid_long + 180.0) % 360
        cog = {"long": round(cog_lon, 2)}
        if not planet_meta:
            return cog
        best = None  # (dist, name)
        for sym_name in PLANET_NAMES_ZH:
            m = planet_meta.get(_name_to_cn(sym_name)) or planet_meta.get(sym_name)
            ap = m.get("abs_pos") if m else None
            if ap is None:
                continue
            d = abs(((ap - cog_lon + 180.0) % 360) - 180.0)
            if best is None or d < best[0]:
                best = (d, sym_name, ap)
        if best and best[0] <= 10.0:
            d, sym_name, ap = best
            cog["planet_name"] = sym_name
            cog["planet_long"] = round(((ap % 360) + 360) % 360, 2)
            cog["dist"]        = round(d, 1)
            cog["is_anchor"]   = d <= COG_ANCHOR_ORB
        return cog

    # 虚空中点只属于 4 个经典格局（Bowl/Bucket/Bundle/Locomotive）。变体精炼层
    # _refine_to_variant 用 {**result.extra} 整体继承父格局 extra，会把父格局的
    # midpoint_* 带进变体（如 Bowl→TwoHandle）。因此严格按最终 pattern_en 闸门，
    # 避免「同类盘有的显示有的不显示」的不一致。其余 10 格局有各自焦点机制
    # （sellar_focus / 把手），不画虚空中点。
    pe = result.pattern_en

    # 把手族（Bucket/Sling/Fanhandle/ConjHandle/TwoHandle）：碗体两边界星的空白半球
    # 中点（Sellar Ch.5：判定把手是否落于此中点 → 落上=高度聚焦/单一指向）。检测有
    # 多条返回路径，故在此集中从 extra 提取边界统一计算，避免在各 return 点散落逻辑。
    # 三种 extra 来源（bucket / conj_handle / two_handle）都带 left_edge/right_edge，
    # 全族适用；此前只算 Bucket，Sling·ConjHandle·TwoHandle 连带碗底重心一起缺失。
    _handle_family = pe in ("Bucket", "Sling", "Fanhandle", "ConjHandle", "TwoHandle")
    _mp_bowl = result.extra.get("midpoint_bowl")
    if _mp_bowl is None and _handle_family:
        _ch = result.extra.get("conj_handle") or result.extra.get("two_handle")
        _bk = result.extra.get("bucket")
        if _ch and "left_edge" in _ch:
            _hl = (_ch["h1_long"] + ((_ch["h2_long"] - _ch["h1_long"]) % 360) / 2) % 360
            _mp_bowl = _bucket_void_midpoint(
                _ch["left_edge"], _ch["right_edge"], _hl,
                _ch.get("left_name", ""), _ch.get("right_name", ""))
        elif _bk and "left_edge" in _bk:
            _mp_bowl = _bucket_void_midpoint(
                _bk["left_edge"], _bk["right_edge"], _bk["handle_long"],
                _bk.get("left_name", ""), _bk.get("right_name", ""))

    # 格局重心点（虚空中点正对面＝占据半球几何重心）+ 实体行星锚定检测。
    # Bowl / 把手族通用：把手族＝Bowl＋把手，底层半球几何两点位同样成立。
    # Bowl 检测层已直接算好 cog_bowl；把手族检测层没算，在此由虚空中点集中
    # 补算并回填 result.extra，供 _build_key_roles 生成角色。
    _cog = result.extra.get("cog_bowl")
    if _handle_family and _cog is None and _mp_bowl:
        _cog = result.extra["cog_bowl"] = _scan_cog(_mp_bowl["long"])
    # 补严格锚定标记：任何带 cog_bowl 的格局（Bowl 检测层直算 / Bucket 此处补算 /
    # Sling·Fanhandle 从 Bowl 父格局继承）统一升级——命中行星 ≤COG_ANCHOR_ORB 即锚点。
    if _cog and "dist" in _cog and "is_anchor" not in _cog:
        _cog["is_anchor"] = _cog["dist"] <= COG_ANCHOR_ORB
    # 碗中心复合合相：已选的最近行星之外，若还有行星与它合相（≤COG_PARTNER_ORB）
    # 且自身也在碗中心 10° 内，记为 partners。原字段 planet_name/dist/is_anchor 不变，
    # 只新增字段。依据：合相作为一个单位来读（Jones 合相把手、Sellar 合相把手变体、
    # Tyl 群星“measured as one unit”）。与香港 natal-chart 3a3d045 同一规则。
    if _cog and _cog.get("planet_name") and planet_meta and "partners" not in _cog:
        def _lon_cn(sym):
            m = planet_meta.get(_name_to_cn(sym)) or planet_meta.get(sym) or {}
            ap = m.get("abs_pos")
            return None if ap is None else float(ap) % 360

        def _sep(a, b):
            return abs(((a - b + 180.0) % 360) - 180.0)

        _chosen = _cog["planet_name"]
        _chosen_lon = _lon_cn(_chosen)
        _partners = []
        if _chosen_lon is not None:
            for _sym in PLANET_NAMES_ZH:
                if _name_to_cn(_sym) == _name_to_cn(_chosen):
                    continue
                _ap = _lon_cn(_sym)
                if _ap is None:
                    continue
                _orb = _sep(_ap, _chosen_lon)
                _d = _sep(_ap, _cog["long"])
                if _orb <= COG_PARTNER_ORB and _d <= 10.0:
                    _partners.append({"planet_name": _sym, "planet_long": round(_ap, 2),
                                      "dist": round(_d, 1), "orb": round(_orb, 2)})
        if _partners:
            _cog["partners"] = sorted(_partners, key=lambda p: p["orb"])

    return {
        "pattern_en":           result.pattern_en,
        "pattern_zh":           result.pattern_zh,
        "confidence":           result.confidence,
        "max_gap_deg":          round(result.max_gap, 2),
        "span_deg":             round(result.span, 2),
        "details":              result.details,
        "high_focus_planet":    result.high_focus_planet,
        "high_focus_longitude": (round(result.high_focus_long, 2)
                                  if result.high_focus_long is not None else None),
        "is_variant":           result.extra.get("parent_pattern") is not None,
        "parent_pattern":       result.extra.get("parent_pattern"),
        # 边界提示：格局落在相邻类型交界带时为 True，供前端提示个案肉眼复核（不影响分类）
        "borderline":           bool(result.extra.get("borderline")),
        "borderline_reasons":   result.extra.get("borderline_reasons", []),
        # 交界时的另一种读法：越过阈值后本盘会落到的形态，及当前距该阈值的度数差
        "borderline_alternates": result.extra.get("borderline_alternates", []),
        "key_roles":            _build_key_roles(result, planet_meta=planet_meta),
        # 赛勒视角（后续发展补充，仅 Splash / See-Saw / Hourglass / Splay 有值）
        # 出处：Wanda Sellar《Chart Shapes: The Code To Interpretation》
        "sellar_focus":         result.extra.get("sellar_focus"),
        # Sellar 第 9 章：Bundle/Wedge 解读起点是两端边界 + 中点（仅 Bundle）
        "midpoint_bundle":      _enrich_midpoint(result.extra.get("midpoint_bundle")) if pe == "Bundle" else None,
        # 碗型/提桶虚空中点：空白半球几何中点（仅 Bowl / Bucket）
        "midpoint_bowl":        _enrich_midpoint(_mp_bowl) if pe in ("Bowl", "Bucket") else None,
        # 占据半球重心：碗倾斜的几何核心；若 planet_name 有值=该星为"绝对底牌/承重墙"
        "cog_bowl":             _enrich_midpoint(result.extra.get("cog_bowl")),
        # 火车头型虚空中点：空白扇区几何中点（仅 Locomotive）
        "midpoint_loco":        _enrich_midpoint(result.extra.get("midpoint_loco")) if pe == "Locomotive" else None,
        # Sellar 第 7 章 fallback：Splay 无对分相时大三角最快星作 HFP（仅 Splay 有值）
        "grand_trine":          result.extra.get("grand_trine"),
        # 蝴蝶型顶点星与较近一翼的交叉点：近似真中点，落宫也有意义（仅 Butterfly 有值）
        "crossing_point":       _enrich_midpoint(result.extra.get("crossing_point")) if pe == "Butterfly" else None,
        # 跷跷板/沙漏两组各自重心连线：没有其他焦点星时，份量偏向哪一组（仅 See-Saw/Hourglass 有值）
        "group_axis":           result.extra.get("group_axis") if pe in ("See-Saw", "Hourglass") else None,
    }


# ══════════════════════════════════════════════════════════════
# 变形格局检测层
# ══════════════════════════════════════════════════════════════

def _cluster_sizes(gaps: List[float], sig_gap_indices: List[int]) -> List[int]:
    """
    按显著间隔索引将 n 颗行星分成 k 组，返回各组行星数量列表。

    结果顺序：clusters[i] = 紧随 sig_gap_indices[i] 之后的星群大小。
    """
    n   = len(gaps)
    sgi = sorted(sig_gap_indices)
    k   = len(sgi)
    return [(sgi[(i + 1) % k] - sgi[i]) % n for i in range(k)]


def _check_conjunction_handle(
    sorted_longs: List[float],
    orig_longs: List[float],
    names: List[str],
    max_orb: float = CONJ_HANDLE_ORB,
) -> Optional[Dict]:
    """
    合相把手检测：
    2 颗距离 ≤ max_orb 的行星共同作为把手，移除后剩余 8 颗构成碗型。
    两颗把手均须在碗型空白区内，且组合后距碗两端各 ≥ 60°。
    """
    n = len(sorted_longs)
    candidates = []
    for i in range(n):
        for j in range(i + 1, n):
            h1, h2 = sorted_longs[i], sorted_longs[j]
            sep = min(_cw(h1, h2), _cw(h2, h1))
            if sep > max_orb:
                continue

            rem   = [sorted_longs[k] for k in range(n) if k != i and k != j]
            r_g   = _calc_gaps(rem)
            r_max = max(r_g)
            if 360 - r_max > BOWL_MAX_SPAN:
                continue

            r_mi  = r_g.index(r_max)
            le    = rem[r_mi]
            re    = rem[(r_mi + 1) % len(rem)]

            # 两颗把手都须在空白区内
            d1l, d1r = _cw(le, h1), _cw(h1, re)
            d2l, d2r = _cw(le, h2), _cw(h2, re)
            in1 = abs(d1l + d1r - r_max) < 2.0
            in2 = abs(d2l + d2r - r_max) < 2.0
            if not (in1 and in2):
                continue

            # 组合把手距碗两端（取最外侧距离）
            outer_left  = min(d1l, d2l)
            outer_right = min(d1r, d2r)
            if outer_left >= BUCKET_MIN_DIST and outer_right >= BUCKET_MIN_DIST:
                h1_name, h2_name, h1_idx, h2_idx = _find_pair_names(
                    h1, h2, orig_longs, names)
                # ⚠️ 此处不选单星 HFP。曾有假引用注释称"Sellar Ch.5: ConjHandle
                # HFP = 较快端"——NLM 逐字复核：「较快者优先」只写在双把手
                # (Two Handle) 一节；合相把手整节无此规则，且 Agatha Christie
                # 案例原文称两星为 "These two High Focus Planets"（复数），
                # 应作单一复合焦点整体阅读，不拆主次。
                candidate = {
                    "h1_long": h1, "h1_name": h1_name,
                    "h2_long": h2, "h2_name": h2_name,
                    "sep":        sep,
                    "bowl_span":  360 - r_max,
                    "left_edge":  le,  "left_name":  _find_name(le, orig_longs, names),
                    "right_edge": re,  "right_name": _find_name(re, orig_longs, names),
                    "identity_indices": [h1_idx, h2_idx],
                    "handle_margin": min(outer_left, outer_right),
                }
                candidates.append(candidate)
    if not candidates:
        return None
    # 不按黄道排序中“第一个命中”裁决。优先选择离碗口最稳、碗体最紧、
    # 合相更紧的候选；最终用原始 planet id 顺序破同分，整体旋转不改变结果。
    return min(candidates, key=lambda item: (
        -item["handle_margin"],
        item["bowl_span"],
        item["sep"],
        item["identity_indices"],
    ))


def _check_two_handle(
    sorted_longs: List[float],
    orig_longs: List[float],
    names: List[str],
) -> Optional[Dict]:
    """
    双把手提桶型检测：
    2 颗相互不在合相（间距 > TWO_HANDLE_MIN_SEP = 8°）的行星分别充当把手，
    移除后剩余 8 颗构成碗型（跨度 ≤ 190°）。
    左把手距碗左端 ≥ 60°，右把手距碗右端 ≥ 60°。
    """
    n = len(sorted_longs)
    for i in range(n):
        for j in range(i + 1, n):
            h1, h2 = sorted_longs[i], sorted_longs[j]
            sep = min(_cw(h1, h2), _cw(h2, h1))
            if sep <= TWO_HANDLE_MIN_SEP:
                continue  # 太近 → 合相把手，不是双把手

            # 双把手须是真正脱离主群的两颗星。纯 Bowl 的两端边界星
            # 也会在移除后制造出一个"伪空白"，必须排除。
            h1_isolated = gaps_around(sorted_longs, i, min_gap=CLUSTER_SEP)
            h2_isolated = gaps_around(sorted_longs, j, min_gap=CLUSTER_SEP)
            if not (h1_isolated and h2_isolated):
                continue

            rem   = [sorted_longs[k] for k in range(n) if k != i and k != j]
            r_g   = _calc_gaps(rem)
            r_max = max(r_g)
            bowl_span = 360 - r_max
            if bowl_span > BOWL_MAX_SPAN:
                continue
            # 碗须为连续弧（与单把手路径同一道 BOWL_MAX_INTERNAL_VOID 约束）：
            # 拉出双把手后剩余 8 颗内部若仍有 ≥90° 裂口，说明实为三群以上结构、
            # 不构成双把手的碗。此前该校验只在单把手路径有，这里裸奔——语料库
            # 35 盘实测本守卫零误伤（另一条 _two_handle_from_two_group 产出路径
            # 因 len(sig)==2 的几何约束天然免疫，无需重复加）。
            if _bowl_internal_void(r_g) >= BOWL_MAX_INTERNAL_VOID:
                continue

            r_mi  = r_g.index(r_max)
            le    = rem[r_mi]
            re    = rem[(r_mi + 1) % len(rem)]

            d1l, d1r = _cw(le, h1), _cw(h1, re)
            d2l, d2r = _cw(le, h2), _cw(h2, re)
            in1 = abs(d1l + d1r - r_max) < 2.0
            in2 = abs(d2l + d2r - r_max) < 2.0
            if not (in1 and in2):
                continue

            # 两把手须分布在空白区两端：左把手距碗左端 ≥ 60°，右把手距碗右端 ≥ 60°。
            # i<j 的 sorted_longs 循环保证 h1 始终在 h2 的顺时针前方（d1l ≤ d2l），
            # 因此 h1 必为左把手，h2 必为右把手，只需检查各自最近碗口的距离。
            if d1l >= BUCKET_MIN_DIST and d2r >= BUCKET_MIN_DIST:
                h1_name, h2_name, h1_idx, h2_idx = _find_pair_names(
                    h1, h2, orig_longs, names)
                # NotebookLM 原典 (Sellar Ch.5 铁律): TwoHandle HFP = 较快端
                # Churchill (Neptune+Pluto 双把手) HFP = Neptune
                if _planet_speed_rank(h1_name) <= _planet_speed_rank(h2_name):
                    hfp_n, hfp_l = h1_name, h1
                else:
                    hfp_n, hfp_l = h2_name, h2
                return {
                    "h1_long": h1, "h1_name": h1_name,
                    "h2_long": h2, "h2_name": h2_name,
                    "sep": sep, "bowl_span": bowl_span,
                    "left_edge": le,  "left_name":  _find_name(le, orig_longs, names),
                    "right_edge": re, "right_name": _find_name(re, orig_longs, names),
                    "hfp_name": hfp_n, "hfp_long": hfp_l,
                    "d1l": d1l, "d2r": d2r,
                    "identity_indices": [h1_idx, h2_idx],
                }
    return None


def gaps_around(sorted_longs: List[float], idx: int, min_gap: float) -> bool:
    """指定行星两侧都至少有 min_gap 空白，才视作脱离主群。"""
    gaps = _calc_gaps(sorted_longs)
    return gaps[(idx - 1) % len(gaps)] >= min_gap and gaps[idx] >= min_gap


def _loose_tripod(gaps: List[float]) -> Optional[Dict]:
    """
    NotebookLM 来源案例中的 Tripod 不总是三段都达到 90°；
    Jonas Salk 一类案例是三个清楚星群，但较小分隔约 50°。
    """
    loose = [(i, g) for i, g in enumerate(gaps) if g >= TRIPOD_LOOSE_GAP]
    if len(loose) != 3:
        return None
    idxs = [i for i, _ in loose]
    vals = [g for _, g in loose]
    sizes = _cluster_sizes(gaps, idxs)
    if min(sizes) < 2:
        return None
    if max(sizes) - min(sizes) > 1:
        return None
    return {"idxs": idxs, "vals": vals, "sizes": sizes}


def _loose_splay(gaps: List[float]) -> Optional[Dict]:
    """Sellar/Jones 案例中的 Splay 可由 30°~60° 的多重分隔形成。"""
    loose = [(i, g) for i, g in enumerate(gaps) if g >= 30.0]
    if len(loose) < 4:
        return None
    idxs = [i for i, _ in loose]
    vals = [g for _, g in loose]
    sizes = _cluster_sizes(gaps, idxs)
    if min(sizes) < 2:
        return None
    return {"idxs": idxs, "vals": vals, "sizes": sizes}


def _split_by_two_gaps(sig_idxs: List[int], n: int) -> Tuple[List[int], List[int]]:
    """用两个显著空白把圆周切成两组，返回两组 sorted_longs 下标。"""
    i0, i1 = sorted(sig_idxs)
    group_a = list(range(i0 + 1, i1 + 1))
    group_b = list(range(i1 + 1, n)) + list(range(0, i0 + 1))
    return group_a, group_b


def _two_handle_from_two_group(
    sorted_longs: List[float],
    gaps: List[float],
    sig_idxs: List[int],
    orig_longs: List[float],
    names: List[str],
) -> Optional[Dict]:
    """
    2 vs 8 的两群结构更符合双把手提桶，而非标准跷跷板。
    两颗把手之间可以相隔较宽；关键是它们与 8 星主群两端各隔出大空白。
    """
    if len(sig_idxs) != 2:
        return None
    group_a, group_b = _split_by_two_gaps(sig_idxs, len(sorted_longs))
    small = group_a if len(group_a) <= len(group_b) else group_b
    if len(small) != 2:
        return None

    h1_idx, h2_idx = small
    h1, h2 = sorted_longs[h1_idx], sorted_longs[h2_idx]
    sep = _cw(h1, h2)
    if sep > 180:
        h1, h2 = h2, h1
        h1_idx, h2_idx = h2_idx, h1_idx
        sep = _cw(h1, h2)

    if sep <= CONJ_HANDLE_ORB:
        return None

    outer_gaps = [gaps[i] for i in sig_idxs]
    main_span = 360.0 - sum(outer_gaps) - sep
    # 两颗把手之外的八星主群须能放进一个半圆；超过 180° 已不是
    # 可承托双把手的「碗」。Grace Kelly 主群约 194°，两家计算器均判 See-Saw。
    if main_span > 180.0:
        return None

    # 主群（8 颗）两端的边界星——双把手解读须含（与 _check_two_handle 字段对齐）
    big = group_b if small is group_a else group_a
    le, re = sorted_longs[big[0]], sorted_longs[big[-1]]

    h1_name, h2_name, h1_idx, h2_idx = _find_pair_names(
        h1, h2, orig_longs, names)
    # NotebookLM 原典 (Sellar Ch.5): TwoHandle HFP = 较快端
    if _planet_speed_rank(h1_name) <= _planet_speed_rank(h2_name):
        hfp_n, hfp_l = h1_name, h1
    else:
        hfp_n, hfp_l = h2_name, h2
    return {
        "h1_long": h1, "h1_name": h1_name,
        "h2_long": h2, "h2_name": h2_name,
        "sep": sep,
        "bowl_span": main_span,
        "left_gap": outer_gaps[0],
        "right_gap": outer_gaps[1],
        "left_edge": le,  "left_name":  _find_name(le, orig_longs, names),
        "right_edge": re, "right_name": _find_name(re, orig_longs, names),
        "hfp_name": hfp_n, "hfp_long": hfp_l,
        "identity_indices": [h1_idx, h2_idx],
    }


def _splay_or_tripod_result(
    sorted_longs: List[float],
    gaps: List[float],
    orig_longs: List[float],
    names: List[str],
    max_gap: float,
    span: float,
) -> PatternResult:
    """构造 Splay/Tripod 结果（与 detect_jones_pattern 第 5 段同逻辑）。
    供"碗内有大裂口、实为多群"的提桶让位时复用，避免把三群结构画成破碗。"""
    sig_list = [(i, g) for i, g in enumerate(gaps) if g >= CLUSTER_SEP]
    n_sig    = len(sig_list)
    sig_vals = [g for _, g in sig_list]
    sig_idxs = [i for i, _ in sig_list]
    conf = "clear" if all(g >= 70 for g in sig_vals) else "moderate"
    gap_desc = "、".join(f"{g:.0f}°" for g in sorted(sig_vals, reverse=True))
    isolated   = _find_isolated(sorted_longs, gaps, orig_longs, names)
    sellar     = _sellar_focus(orig_longs, names)
    grand_trine = None
    hfp_name, hfp_long = None, None
    if isolated:
        hfp_name, hfp_long = isolated["name"], isolated["long"]
    elif sellar:
        hfp_name, hfp_long = sellar["name"], sellar["lon"]
    else:
        grand_trine = _find_grand_trine(orig_longs, names)
        if grand_trine:
            hfp_name = grand_trine["fastest"]["name"]
            hfp_long = grand_trine["fastest"]["long"]
    sizes = _cluster_sizes(gaps, sig_idxs)
    is_tripod = isolated is not None and max(sizes) <= 6
    return PatternResult(
        pattern_en=("Tripod" if is_tripod else "Splay"),
        pattern_zh=("三脚架型" if is_tripod else "展开型"),
        confidence=conf, max_gap=max_gap, span=span,
        details=(
            (f"行星呈 3 群独立分布外加 1 颗孤立缰绳星（共 {n_sig+1} 个分组，"
             f"空白：{gap_desc}）。三脚架结构赋予多维度内在支撑，"
             f"缰绳星「{isolated['name']}」是控制全盘的统治支点。"
             if is_tripod else
             f"行星形成 {n_sig} 个独立星群（各群间空白：{gap_desc}）。"
             f"【内驱型·三分原则】强烈的个人独立性，拒绝被规训，"
             f"在多个完全不相干的领域均有顽固的深度追求。")
        ),
        high_focus_planet=hfp_name,
        high_focus_long=hfp_long,
        extra={"cluster_count": n_sig, "sig_gaps": sig_vals,
               "isolated": isolated, "sellar_focus": sellar,
               "grand_trine": grand_trine},
    )


def _refine_to_variant(
    result: PatternResult,
    sorted_longs: List[float],
    gaps: List[float],
    orig_longs: List[float],
    names: List[str],
) -> PatternResult:
    """
    变形格局精化：在基础格局识别后，尝试升级为更具体的变形格局。
    返回精化后的 PatternResult（如无变形则返回原结果）。

    精化逻辑（按亲缘关系）：
      Locomotive → Fanhandle / Sling（若实为高度集中的把手格局）
      Bucket     → Fanhandle（主群≤90°）| Sling（主群≤120°）| ConjHandle（合相把手）
      Bowl       → TwoHandle（双把手）
      See-Saw    → Hourglass（两侧空白≥90°）
      Splay      → TwoHandle（8:1:1分布）| Butterfly（1孤星，三段≥90°）| Tripod（三段≥90°）
    """
    pat = result.pattern_en
    n   = len(sorted_longs)
    sig_list = [(i, g) for i, g in enumerate(gaps) if g >= CLUSTER_SEP]
    sig_idxs = [i for i, _ in sig_list]
    sig_vals = [g for _, g in sig_list]
    n_sig    = len(sig_list)
    loose_tripod = _loose_tripod(gaps)
    loose_splay = _loose_splay(gaps)
    two_group_handle = _two_handle_from_two_group(
        sorted_longs, gaps, sig_idxs, orig_longs, names)

    if pat == "See-Saw" and two_group_handle:
        return PatternResult(
            pattern_en="TwoHandle", pattern_zh="双把手提桶型",
            confidence="moderate", max_gap=result.max_gap, span=result.span,
            details=(
                f"8颗主星群跨度约 {two_group_handle['bowl_span']:.1f}°，"
                f"「{two_group_handle['h1_name']}」与「{two_group_handle['h2_name']}」"
                f"相距 {two_group_handle['sep']:.1f}° 分别充当双把手。"
                f"能量向双焦点分流，人生呈现两条并行的核心使命线。"
            ),
            high_focus_planet=two_group_handle.get("hfp_name", two_group_handle["h1_name"]),
            high_focus_long=two_group_handle.get("hfp_long", two_group_handle["h1_long"]),
            extra={**result.extra, "parent_pattern": "See-Saw",
                   "two_handle": two_group_handle},
        )

    if pat == "Locomotive" and two_group_handle:
        return PatternResult(
            pattern_en="TwoHandle", pattern_zh="双把手提桶型",
            confidence="moderate", max_gap=result.max_gap, span=result.span,
            details=(
                f"8颗主星群跨度约 {two_group_handle['bowl_span']:.1f}°，"
                f"「{two_group_handle['h1_name']}」与「{two_group_handle['h2_name']}」"
                f"相距 {two_group_handle['sep']:.1f}° 分别充当双把手。"
                f"能量向双焦点分流，人生呈现两条并行的核心使命线。"
            ),
            high_focus_planet=two_group_handle.get("hfp_name", two_group_handle["h1_name"]),
            high_focus_long=two_group_handle.get("hfp_long", two_group_handle["h1_long"]),
            extra={**result.extra, "parent_pattern": "Locomotive",
                   "two_handle": two_group_handle},
        )

    raylike_tripod = _raylike_tripod(sorted_longs, gaps, sig_idxs)
    if pat == "See-Saw" and raylike_tripod:
        gap_desc = "、".join(
            f"{g:.0f}°" for g in sorted(raylike_tripod["vals"], reverse=True))
        span_desc = "、".join(
            f"{s:.1f}°" for s in sorted(raylike_tripod["cluster_spans"]))
        # Sellar《Chart Shapes》第 8 章：Tripod 的 HFP 是「单独站立的孤立行星」
        # （reins planet/缰绳星），不需要找最快的星。从 [1,4,5] 三群里识别 size==1 的孤星。
        iso_data = None
        clusters = _clusters_from_gaps(raylike_tripod["idxs"], len(gaps))
        iso_cluster = next((c for c in clusters if len(c) == 1), None)
        if iso_cluster:
            iso_long = sorted_longs[iso_cluster[0]]
            iso_data = {"name": _find_name(iso_long, orig_longs, names),
                        "long": iso_long}
        return PatternResult(
            pattern_en="Tripod", pattern_zh="三脚架型",
            confidence="moderate", max_gap=result.max_gap, span=result.span,
            details=(
                f"行星呈三组独立分布（各群：{raylike_tripod['sizes']}颗，"
                f"空白：{gap_desc}）。"
                f"三脚架结构赋予极强的内在稳定性，"
                f"在互不相干的多个领域均能建立深度，形成独特自洽的人生格局。"
            ),
            high_focus_planet=iso_data["name"] if iso_data else result.high_focus_planet,
            high_focus_long=iso_data["long"]  if iso_data else result.high_focus_long,
            extra={**result.extra, "parent_pattern": "See-Saw",
                   "cluster_sizes": raylike_tripod["sizes"],
                   "tripod_gap_rule": TRIPOD_VISUAL_GAP,
                   "raylike_tripod": raylike_tripod,
                   "isolated": iso_data},
        )

    if pat == "Locomotive" and n_sig == 3:
        csizes = _cluster_sizes(gaps, sig_idxs)
        if sorted(csizes) == [1, 1, 8]:
            two = _check_two_handle(sorted_longs, orig_longs, names)
            if two:
                return PatternResult(
                    pattern_en="TwoHandle", pattern_zh="双把手提桶型",
                    confidence="moderate", max_gap=result.max_gap, span=result.span,
                    details=(
                        f"8颗主星群跨度 {two['bowl_span']:.1f}°，"
                        f"「{two['h1_name']}」与「{two['h2_name']}」分别独立为双把手。"
                        f"能量向双焦点分流，人生呈现两条并行的核心使命线。"
                    ),
                    high_focus_planet=two.get("hfp_name", two["h1_name"]),
                    high_focus_long=two.get("hfp_long", two["h1_long"]),
                    extra={**result.extra, "parent_pattern": "Locomotive",
                           "two_handle": two,
                           "cluster_sizes": csizes},
                )

    # loose_splay / loose_tripod 路径共用的 Sellar HFP 优先级计算
    # （base See-Saw 没有 HFP，refine 到 Splay/Tripod 时需补按 Sellar 三档判定）
    def _splay_sellar_hfp() -> Tuple[Optional[str], Optional[float], Optional[Dict], Optional[Dict], Optional[Dict]]:
        iso = _find_isolated(sorted_longs, gaps, orig_longs, names)
        sf  = result.extra.get("sellar_focus") or _sellar_focus(orig_longs, names)
        gt  = None
        if iso:
            return iso["name"], iso["long"], iso, sf, gt
        if sf:
            return sf["name"], sf["lon"], iso, sf, gt
        gt = _find_grand_trine(orig_longs, names)
        if gt:
            return gt["fastest"]["name"], gt["fastest"]["long"], iso, sf, gt
        return None, None, iso, sf, gt

    # See-Saw 锁定保护：稳定的 See-Saw 几何（min cluster ≥ 4）不允许 refine 走
    # NotebookLM 推荐：George Harrison sizes=[6,4] min=4 应锁定 See-Saw，不被 loose_splay 切碎
    # Annie Besant sizes=[7,3] min=3 仍允许 refine 到 Splay（其原典就是 Splay）
    seesaw_locked = (pat == "See-Saw" and result.extra.get("group_sizes")
                      and min(result.extra["group_sizes"]) >= 4)

    if pat == "See-Saw" and loose_splay and not seesaw_locked:
        gap_desc = "、".join(
            f"{g:.0f}°" for g in sorted(loose_splay["vals"], reverse=True))
        hfp_n, hfp_l, iso, sf, gt = _splay_sellar_hfp()
        return PatternResult(
            pattern_en="Splay", pattern_zh="展开型",
            confidence="moderate", max_gap=result.max_gap, span=result.span,
            details=(
                f"行星呈多个不规则星群（各群：{loose_splay['sizes']}颗，"
                f"空白：{gap_desc}）。"
                f"强烈的个人独立性，拒绝被归类，"
                f"在多个完全不同的领域均有深度追求。"
            ),
            high_focus_planet=hfp_n,
            high_focus_long=hfp_l,
            extra={**result.extra, "parent_pattern": "See-Saw",
                   "cluster_sizes": loose_splay["sizes"],
                   "splay_gap_rule": 30.0,
                   "isolated": iso, "sellar_focus": sf, "grand_trine": gt},
        )

    if pat == "See-Saw" and loose_tripod and not seesaw_locked:
        gap_desc = "、".join(
            f"{g:.0f}°" for g in sorted(loose_tripod["vals"], reverse=True))
        hfp_n, hfp_l, iso, sf, gt = _splay_sellar_hfp()
        return PatternResult(
            pattern_en="Tripod", pattern_zh="三脚架型",
            confidence="moderate", max_gap=result.max_gap, span=result.span,
            details=(
                f"三个星群清楚分布（各群：{loose_tripod['sizes']}颗，"
                f"空白：{gap_desc}）。"
                f"三脚架结构赋予极强的内在稳定性，"
                f"在互不相干的多个领域均能建立深度，形成独特自洽的人生格局。"
            ),
            high_focus_planet=hfp_n,
            high_focus_long=hfp_l,
            extra={**result.extra, "parent_pattern": pat,
                   "cluster_sizes": loose_tripod["sizes"],
                   "isolated": iso, "sellar_focus": sf, "grand_trine": gt,
                   "tripod_gap_rule": TRIPOD_LOOSE_GAP},
        )

    # ── Locomotive → Sling / Fanhandle 复判 ───────────────────
    # 三分优先可能将真正的弹弓型误判为火车头型。
    # 当存在有效的 Bucket 结构且主群跨度 ≤ 120° 时，以弹弓/扇柄型覆盖。
    if pat == "Locomotive":
        early = _check_bucket(sorted_longs, orig_longs, names)
        if early:
            bowl_span   = early["bowl_span"]
            handle_name = early["handle_name"]
            handle_long = early["handle_long"]
            handle_balance = abs(early["dist_left"] - early["dist_right"])
            if (bowl_span <= FANHANDLE_MAX_SPAN or
                    (bowl_span <= FANHANDLE_SOURCE_MAX_SPAN
                     and handle_balance <= FANHANDLE_BALANCE_MAX)):
                return PatternResult(
                    pattern_en="Fanhandle", pattern_zh="扇柄型",
                    confidence="clear", max_gap=result.max_gap, span=result.span,
                    details=(
                        f"主星群高度密集（跨度 {bowl_span:.1f}°，类丛聚型），"
                        f"把手行星「{handle_name}」与主群形成极强对立张力，"
                        f"能量高度聚焦于把手行星指向的生命议题。"
                    ),
                    high_focus_planet=handle_name,
                    high_focus_long=handle_long,
                    extra={**result.extra, "parent_pattern": "Locomotive",
                           "bucket": early},
                )
            elif bowl_span <= SLING_MAX_SPAN:
                return PatternResult(
                pattern_en="Sling", pattern_zh="弹弓型",
                confidence="clear", max_gap=result.max_gap, span=result.span,
                details=(
                    f"主星群紧密聚集（跨度 {bowl_span:.1f}°），"
                    f"把手行星「{handle_name}」精准释放全盘压缩能量，"
                    f"生命主轴极为清晰，目标感强烈而笃定。"
                    ),
                    high_focus_planet=handle_name,
                    high_focus_long=handle_long,
                    extra={**result.extra, "parent_pattern": "Locomotive",
                           "bucket": early},
                )

    # ── Bucket 变形 ────────────────────────────────────────────
    if pat == "Bucket":
        bk = result.extra.get("bucket", {})
        bowl_span   = bk.get("bowl_span", 360)
        handle_name = bk.get("handle_name", "")
        handle_long = bk.get("handle_long", 0.0)

        # TwoHandle 改判（原典：碗部任意两星须 <60°）：
        # 干净提桶只有 2 段显著空白（把手两侧）；出现第 3 段 ≥60° 大空白，
        # 说明「碗」里还有一颗离群星——它其实是第二个把手，整体为双把手提桶。
        # _check_two_handle 内部要求两把手两侧各 ≥60° 空白，故蝴蝶（仅 1 孤星）
        # 会返回 None，自然落到下方蝴蝶分支，不会被误抢。
        if n_sig >= 3:
            two = _check_two_handle(sorted_longs, orig_longs, names)
            if two:
                return PatternResult(
                    pattern_en="TwoHandle", pattern_zh="双把手提桶型",
                    confidence="moderate", max_gap=result.max_gap, span=result.span,
                    details=(
                        f"8颗行星形成碗形（跨度 {two['bowl_span']:.1f}°），"
                        f"左把手「{two['h1_name']}」距碗左端 {two['d1l']:.1f}°，"
                        f"右把手「{two['h2_name']}」距碗右端 {two['d2r']:.1f}°，"
                        f"两把手间距 {two['sep']:.1f}°。"
                        f"能量向双焦点分流，人生呈现双轨使命感。"
                    ),
                    high_focus_planet=two.get("hfp_name", two["h1_name"]),
                    high_focus_long=two.get("hfp_long", two["h1_long"]),
                    extra={**result.extra, "parent_pattern": "Bucket",
                           "two_handle": two},
                )

        # Butterfly 边界案例：有三段清楚空白与一颗孤星时，若 Bucket
        # 只是擦着 190° 上限成立，优先保留来源中的三群/蝴蝶结构。
        if n_sig == 3 and bowl_span >= 180:
            csizes = _cluster_sizes(gaps, sig_idxs)
            if 1 in csizes and min(sig_vals) >= 80:
                sgi = sorted(sig_idxs)
                clusters = _clusters_from_gaps(sgi, len(gaps))
                # 顶点须是几何上单独孤立、等距悬于两翼之间的那颗（Wanda Sellar 原典）。
                # 用簇的真实成员下标，避免「gap 下标 ↔ 星群」错位
                # （旧 bug：取到翼内边界星而非孤星）
                best_k, best_gap_sum = None, -1.0
                for k, cl in enumerate(clusters):
                    if len(cl) == 1 and gaps[sgi[k - 1]] + gaps[sgi[k]] > best_gap_sum:
                        best_gap_sum = gaps[sgi[k - 1]] + gaps[sgi[k]]
                        best_k = k
                iso_long = sorted_longs[clusters[best_k][0]]
                iso_name = _find_name(iso_long, orig_longs, names)
                gap_desc = "、".join(f"{g:.0f}°" for g in sorted(sig_vals, reverse=True))
                # 顶点星与较近一翼的交叉点（NLM 核验 Sellar，同下方 Splay 路由 Butterfly
                # 分支的算法）：这条经由 Bucket 边界案例走的路由此前漏了这一层。
                _prev_k, _next_k = (best_k - 1) % len(clusters), (best_k + 1) % len(clusters)
                _gap_before, _gap_after = gaps[sgi[best_k - 1]], gaps[sgi[best_k]]
                if _gap_before <= _gap_after:
                    _near_long = sorted_longs[clusters[_prev_k][-1]]
                else:
                    _near_long = sorted_longs[clusters[_next_k][0]]
                _near_name = _find_name(_near_long, orig_longs, names)
                _crossing_long = _circular_mean([iso_long, _near_long])
                return PatternResult(
                    pattern_en="Butterfly", pattern_zh="蝴蝶型",
                    confidence=("clear" if all(g >= BUTTERFLY_MIN_GAP for g in sig_vals) else "moderate"),
                    max_gap=result.max_gap, span=result.span,
                    details=(
                        f"三段空白：{gap_desc}，孤立行星「{iso_name}」"
                        f"嵌于两组行星之间，常为 T 三角顶点。"
                        f"天生的危机斡旋者，擅长在对立双方之间寻找平衡与出口。"
                    ),
                    high_focus_planet=iso_name,
                    high_focus_long=iso_long,
                    extra={**result.extra, "parent_pattern": "Bucket",
                           "cluster_sizes": csizes,
                           "isolated": {"name": iso_name, "long": iso_long},
                           "crossing_point": {"long": round(_crossing_long, 2), "near_name": _near_name}},
                )

        # 碗须连续：把手两侧的"主群"内部若有 ≥90° 大裂口，说明它其实裂成多群
        # （如 Baudelaire：7星丛聚团 + 孤月 + 天海合相，碗内 93° 洞），不是真把手碗。
        # 此时让位给 Splay/Tripod，避免把三群结构画成"破碗+把手"。
        # 已先于此分支返回的 Butterfly(Byron)/TwoHandle 不受影响；
        # 碗连续的 ConjHandle(Frida 62°)/Fanhandle(Amelia 41°) 也不受影响。
        _bowl_pl = [x for x in sorted_longs
                    if min(abs(x - handle_long), 360.0 - abs(x - handle_long)) > 10.0]
        if (n_sig >= 3
                and _bowl_internal_void(_calc_gaps(_bowl_pl)) >= BOWL_MAX_INTERNAL_VOID):
            return _splay_or_tripod_result(
                sorted_longs, gaps, orig_longs, names, result.max_gap, result.span)

        # Fanhandle：主群 ≤ 90°（Bundle 衍生，最紧凑）
        handle_balance = abs(bk.get("dist_left", 0.0) - bk.get("dist_right", 0.0))
        if (bowl_span <= FANHANDLE_MAX_SPAN or
                (bowl_span <= FANHANDLE_SOURCE_MAX_SPAN
                 and handle_balance <= FANHANDLE_BALANCE_MAX)):
            # 检查把手是否是超紧密合相（≤3°，Fan 的典型特征）
            conj = _check_conjunction_handle(
                sorted_longs, orig_longs, names, max_orb=FAN_CONJ_ORB)
            if conj:
                label = "Fan (合相扇柄)"
                detail_extra = (
                    f"「{conj['h1_name']}」与「{conj['h2_name']}」"
                    f"以 {conj['sep']:.1f}° 超紧密合相充当把手，"
                )
                conj_extra = {"conj_handle": conj}   # ← 保存供 key_roles 使用
            else:
                label = "Fanhandle"
                detail_extra = f"把手行星「{handle_name}」，"
                conj_extra = {}
            return PatternResult(
                pattern_en="Fanhandle", pattern_zh="扇柄型",
                confidence="clear", max_gap=result.max_gap, span=result.span,
                details=(
                    f"主星群高度密集（跨度 {bowl_span:.1f}°，类丛聚型），"
                    + detail_extra +
                    f"主群与把手对立张力极强，能量高度聚焦于把手行星指向的生命议题。"
                ),
                # 合相扇柄与 ConjHandle / Bucket-via-conj 同口径：合相把手无单星
                # HFP（Sellar："These two High Focus Planets"，复数整体），此前
                # 这里落的是 "海王星+冥王星" 拼接串——既非合法行星名、又与同族
                # 另两条路径不一致。非合相扇柄仍有真实单星把手，照常给值。
                high_focus_planet=None if conj else handle_name,
                high_focus_long=None if conj else handle_long,
                extra={**result.extra, "parent_pattern": "Bucket",
                       "sub_label": label, **conj_extra},
            )

        # Sling：主群 ≤ 120°
        # 若基础格局已确认把手为合相双星（extra 含 conj_handle），
        # 则跳过此步，交由下方合相把手检测处理（ConjHandle 优先于 Sling）。
        if bowl_span <= SLING_MAX_SPAN and not result.extra.get("conj_handle"):
            return PatternResult(
                pattern_en="Sling", pattern_zh="弹弓型",
                confidence="clear", max_gap=result.max_gap, span=result.span,
                details=(
                    f"主星群紧密聚集（跨度 {bowl_span:.1f}°），"
                    f"把手行星「{handle_name}」（{handle_long:.1f}°）"
                    f"距主群两端各 {bk.get('dist_left',0):.1f}° / {bk.get('dist_right',0):.1f}°。"
                    f"高度压缩的能量被把手星精准释放，生命主轴极为清晰。"
                ),
                high_focus_planet=handle_name,
                high_focus_long=handle_long,
                extra={**result.extra, "parent_pattern": "Bucket"},
            )

        # Conjunction Handle：把手由合相双星组成（≤8°）
        # 优先使用基础格局检测时已找到的合相数据，否则重新检测。
        conj = result.extra.get("conj_handle") or \
               _check_conjunction_handle(sorted_longs, orig_longs, names)
        if conj:
            return PatternResult(
                pattern_en="ConjHandle", pattern_zh="合相把手型",
                confidence="clear", max_gap=result.max_gap, span=result.span,
                details=(
                    f"8颗行星形成碗形（跨度 {conj['bowl_span']:.1f}°），"
                    f"「{conj['h1_name']}」与「{conj['h2_name']}」"
                    f"以 {conj['sep']:.1f}° 合相共同充当把手（≤8°），"
                    f"合相越紧密，引导能量越强。两星合力聚焦全盘方向，使命叙事双重叠加。"
                ),
                # 合相把手无单星 HFP（Sellar："These two High Focus Planets"，复数整体）
                high_focus_planet=None,
                high_focus_long=None,
                extra={**result.extra, "parent_pattern": "Bucket",
                       "conj_handle": conj},
            )

    # ── Bowl 变形 ──────────────────────────────────────────────
    if pat == "Bowl":
        two = _check_two_handle(sorted_longs, orig_longs, names)
        if two:
            return PatternResult(
                pattern_en="TwoHandle", pattern_zh="双把手提桶型",
                confidence="moderate", max_gap=result.max_gap, span=result.span,
                details=(
                    f"8颗行星形成碗形（跨度 {two['bowl_span']:.1f}°），"
                    f"左把手「{two['h1_name']}」距碗左端 {two['d1l']:.1f}°，"
                    f"右把手「{two['h2_name']}」距碗右端 {two['d2r']:.1f}°，"
                    f"两把手间距 {two['sep']:.1f}°（非合相）。"
                    f"能量向双焦点分流，人生呈现双轨使命。"
                ),
                high_focus_planet=two.get("hfp_name", two["h1_name"]),
                high_focus_long=two.get("hfp_long", two["h1_long"]),
                extra={**result.extra, "parent_pattern": "Bowl",
                       "two_handle": two},
            )

    # ── See-Saw 变形 ───────────────────────────────────────────
    if pat == "See-Saw" and n_sig == 2:
        g1, g2 = sig_vals
        if min(g1, g2) >= HOURGLASS_MIN_GAP:
            return PatternResult(
                pattern_en="Hourglass", pattern_zh="沙漏型",
                confidence="clear" if min(g1, g2) >= 100 else "moderate",
                max_gap=result.max_gap, span=result.span,
                details=(
                    f"两组对立星群，两侧空白分别为 {g1:.1f}° 与 {g2:.1f}°（均 ≥ 90°）。"
                    f"比标准跷跷板型更为紧密聚焦，中央轴线张力极强，"
                    f"人生的对立整合命题更为尖锐而清晰。"
                ),
                high_focus_planet=result.high_focus_planet,
                high_focus_long=result.high_focus_long,
                extra={**result.extra, "parent_pattern": "See-Saw"},
            )

    # ── Splay 变形 ─────────────────────────────────────────────
    if pat == "Splay" and n_sig >= 3:
        csizes = _cluster_sizes(gaps, sig_idxs)
        gap_desc = "、".join(f"{g:.0f}°" for g in sorted(sig_vals, reverse=True))

        # TwoHandle（双把手型）：Splay 中集群分布极度不均（如 8:1:1）
        # 2颗孤立行星作为双把手，8颗形成碗型
        if n_sig == 3 and sorted(csizes) == [1, 1, 8]:
            two = _check_two_handle(sorted_longs, orig_longs, names)
            if two:
                return PatternResult(
                    pattern_en="TwoHandle", pattern_zh="双把手提桶型",
                    confidence="moderate", max_gap=result.max_gap, span=result.span,
                    details=(
                        f"8颗行星形成碗形（跨度 {two['bowl_span']:.1f}°），"
                        f"左把手「{two['h1_name']}」距碗左端 {two['d1l']:.1f}°，"
                        f"右把手「{two['h2_name']}」距碗右端 {two['d2r']:.1f}°，"
                        f"两把手间距 {two['sep']:.1f}°。"
                        f"能量向双焦点分流，人生呈现双轨使命感。"
                    ),
                    high_focus_planet=two.get("hfp_name", two["h1_name"]),
                    high_focus_long=two.get("hfp_long", two["h1_long"]),
                    extra={**result.extra, "parent_pattern": "Splay",
                           "two_handle": two},
                )

        # Butterfly：n_sig==3，其中一群只有1颗星，三段空白均≥90°
        if n_sig == 3 and 1 in csizes and all(g >= BUTTERFLY_MIN_GAP for g in sig_vals):
            sgi = sorted(sig_idxs)
            clusters = _clusters_from_gaps(sgi, len(gaps))
            # clusters[k] 是 gap sgi[k-1] 与 gap sgi[k] 之间的星群（真实成员下标）。
            # 顶点须是单独孤立、等距居中的那颗（Sellar 原典）；
            # 若有多个单星群（如 [1,1,8]），取两侧空白之和最大的那个作为顶点
            best_k, best_gap_sum = None, -1.0
            for k, cl in enumerate(clusters):
                if len(cl) == 1 and gaps[sgi[k - 1]] + gaps[sgi[k]] > best_gap_sum:
                    best_gap_sum = gaps[sgi[k - 1]] + gaps[sgi[k]]
                    best_k = k
            iso_long = sorted_longs[clusters[best_k][0]]   # 单星簇的那颗孤星
            iso_name = _find_name(iso_long, orig_longs, names)
            wings    = [len(c) for j, c in enumerate(clusters) if j != best_k]
            # 顶点星与较近一翼「交叉点」（NLM 核验 Sellar 原典）：孤星穿过较近边界线的地方
            # 近似一个真中点——此前只标了顶点星本身，这层隐藏的中点关系被漏掉。
            _prev_k, _next_k = (best_k - 1) % len(clusters), (best_k + 1) % len(clusters)
            _gap_before, _gap_after = gaps[sgi[best_k - 1]], gaps[sgi[best_k]]
            if _gap_before <= _gap_after:
                _near_long = sorted_longs[clusters[_prev_k][-1]]
            else:
                _near_long = sorted_longs[clusters[_next_k][0]]
            _near_name = _find_name(_near_long, orig_longs, names)
            _crossing_long = _circular_mean([iso_long, _near_long])
            return PatternResult(
                pattern_en="Butterfly", pattern_zh="蝴蝶型",
                confidence=("clear" if all(g >= BUTTERFLY_MIN_GAP for g in sig_vals) else "moderate"),
                max_gap=result.max_gap, span=result.span,
                details=(
                    f"两组行星群（{wings[0]}颗 + {wings[1]}颗）"
                    f"夹住孤立行星「{iso_name}」（{iso_long:.1f}°），"
                    f"三段空白：{gap_desc}（均 ≥ 90°）。"
                    f"「{iso_name}」常为 T 三角顶点，是全盘高焦点行星，"
                    f"充当两对立群的能量出口与整合枢纽。"
                ),
                high_focus_planet=iso_name,
                high_focus_long=iso_long,
                extra={**result.extra, "parent_pattern": "Splay",
                       "cluster_sizes": csizes,
                       "isolated": {"name": iso_name, "long": iso_long},
                       "crossing_point": {"long": round(_crossing_long, 2), "near_name": _near_name}},
            )

        # Tripod：n_sig==3，三段空白均≥90°（规则三脚架）
        if n_sig == 3 and all(g >= TRIPOD_MIN_GAP for g in sig_vals):
            return PatternResult(
                pattern_en="Tripod", pattern_zh="三脚架型",
                confidence="clear", max_gap=result.max_gap, span=result.span,
                details=(
                    f"三个星群规则分布（各群：{csizes}颗，"
                    f"各空白：{gap_desc}，均 ≥ 90°）。"
                    f"星群间常形成大三角（Grand Trine），"
                    f"稳固三角架构赋予极强的内在整合力与自我完足感。"
                ),
                high_focus_planet=result.high_focus_planet,
                high_focus_long=result.high_focus_long,
                extra={**result.extra, "parent_pattern": "Splay",
                       "cluster_sizes": csizes},
            )

    return result  # 无变形，返回原始结果


# ──────────────────────────────────────────────────────────────
# 顶层接口：基础检测 + 变形精化（推荐使用）
# ──────────────────────────────────────────────────────────────

def _assess_borderline(
    pattern_en: str,
    gaps: List[float],
    span: float = 0.0,
    extra: Optional[Dict] = None,
) -> Tuple[bool, List[str]]:
    """判定该盘是否落在相邻格局的几何交界带。

    **不改变分类**（pattern_en 不动），仅产出一个旗标供前端提示个案肉眼复核。
    依据三轮准确率审计（2026-06-15）挖出的真实判定阈值：
      - 三元/二四交界：恰一个次级空白落在 58–73°（CLUSTER_SEP 60° 上下），
        Locomotive↔See-Saw↔Bucket↔Splay↔Tripod 在此最易互窜（含 Gandhi↔Karl Marx
        不可约对）。此前白名单漏了 Splay/Tripod——同一条 s2 判据其实也决定它们
        跟 See-Saw 的分叉（n_sig==3 vs 2），却只对 See-Saw 一侧生效。
      - 碗/半球交界：最大空白在 BOWL_THRESHOLD(175°) 以下 8° 内、或以上 3° 内
        （Bowl↔Loco/See-Saw）。2026-10-01 把门槛以下一侧由 ±3° 放宽到 8°：
        175°/185° 在本文件里就标注着"工程阈值，不是原典硬线"，交界带至少要
        覆盖阈值本身的不确定度，否则会出现琼斯本人按碗型讲、引擎判火车头型、
        却连交界提示都不给的情况（Jones500 第1章 Sally，max_gap=168.1°，
        距阈值 6.9°）。两侧不对称是有意的：门槛以下接近 175° 意味着"差一点
        就成碗"，是真边缘；门槛以上 175-183° 是碗型的正常腹地，连十颗星均匀
        铺满半圆的理想碗（max_gap=180°）都落在这里，不能标成交界。
      - 丛聚交界：最大空白距 BUNDLE_THRESHOLD(230°) 在 ±8° 内（Bundle↔Bowl）
      - 沙漏交界：两段显著空白中较小者距 HOURGLASS_MIN_GAP(90°) 在 ±6° 内
        （See-Saw↔Hourglass）。此前跟碗型 194° 是同一类漏洞：内部 confidence
        变量本就把 min(g1,g2) 90-100° 之间标 moderate，但从未传到前端。
      - 蝴蝶/三脚架交界：三段显著空白中最小者距 90° 在 ±6° 内（Splay↔Butterfly/
        Tripod，BUTTERFLY_MIN_GAP 与 TRIPOD_MIN_GAP 同为 90°，本是同一条线）。
      - 合相/双把手交界：把手行星间距距 8°（CONJ_HANDLE_ORB=TWO_HANDLE_MIN_SEP，
        本是同一条线的两侧定义）在 ±2° 内——8° 本身数值小，用绝对小容差而非
        跟其他规则一样的 ±6/±8°，否则容差会吃掉整个判定区间。
    实测命中率约 20%（76 案例），覆盖大部分边界错判与已知模糊盘。

    仍未覆盖（已知、暂缓）：散落型"通道A" g4≈41° 红线（注释里明确写着"精确
    避开 G.Harrison g4=40°边界"，只留 1° 容差）——散落型是多路径兜底分类，
    g4 单独接近 41° 不代表这张盘真的贴着那条通道A的复合判据（还有 max_gap/
    g2/g3/occupied_signs 四个联合条件），单独判会对根本没走过通道A的盘
    误报，需要更完整的联合判据才能安全接入，先记录不实现。
    """
    if not gaps:
        return False, []
    extra = extra or {}
    mg = max(gaps)
    mg_idx = gaps.index(mg)
    sec = sorted((g for i, g in enumerate(gaps) if i != mg_idx), reverse=True)
    s2 = sec[0] if sec else 0.0
    sig_vals = sorted((g for g in gaps if g >= CLUSTER_SEP), reverse=True)
    n_sig = len(sig_vals)
    reasons: List[str] = []
    if (pattern_en in ("Locomotive", "See-Saw", "Bucket", "Hourglass", "Sling",
                        "Splay", "Tripod")
            and 58.0 <= s2 <= 73.0 and n_sig <= 3):
        reasons.append("三元/二四交界")
    if (pattern_en in ("Bowl", "Locomotive", "See-Saw", "Bucket", "TwoHandle")
            and -8.0 <= (mg - BOWL_THRESHOLD) <= 3.0):
        reasons.append("碗/半球交界")
    if (pattern_en in ("Bundle", "Bowl", "Fanhandle")
            and abs(mg - BUNDLE_THRESHOLD) <= 8.0):
        reasons.append("丛聚交界")
    if (pattern_en in ("See-Saw", "Hourglass") and n_sig == 2
            and abs(min(sig_vals) - HOURGLASS_MIN_GAP) <= 6.0):
        reasons.append("沙漏交界")
    if (pattern_en in ("Splay", "Butterfly", "Tripod") and n_sig == 3
            and abs(min(sig_vals) - 90.0) <= 6.0):
        reasons.append("蝴蝶/三脚架交界")
    if pattern_en in ("ConjHandle", "TwoHandle"):
        handle = extra.get("conj_handle") or extra.get("two_handle")
        sep = handle.get("sep") if handle else None
        if sep is not None and abs(sep - CONJ_HANDLE_ORB) <= 2.0:
            reasons.append("合相/双把手交界")
    if (pattern_en == "ConjHandle" and n_sig == 2
            and min(sig_vals) >= 70.0
            and sorted(_group_sizes(gaps, [i for i, g in enumerate(gaps)
                                           if g >= CLUSTER_SEP])) == [2, 8]):
        # Jones 的 See-Saw 明确允许 2:8；Sellar 的合相把手又允许这两颗
        # 作为一个复合把手。两套形态在这里重叠，不是把手合相 8° 的数值边界。
        reasons.append("双星把手/跷跷板重叠")
    if pattern_en == "TwoHandle":
        # NLM 核验 Sellar 原文："If there should be a third planet acting as a
        # handle, away from the main group of planets, this begins to have the
        # character of a See-Saw pattern."——全盘两侧空白均 ≥CLUSTER_SEP 的孤立
        # 行星若有 ≥3 颗，引擎只挑得出两颗当把手、第三颗被并进碗里标"主群边界"，
        # 分类不动（原典是 begins to have the character of 的软措辞），但必须
        # 打交界旗标提示肉眼复核，不能报 clear/False 装没事。
        n_g = len(gaps)
        iso = sum(1 for i in range(n_g)
                  if gaps[(i - 1) % n_g] >= CLUSTER_SEP and gaps[i] >= CLUSTER_SEP)
        if iso >= 3:
            reasons.append("第三把手/跷跷板交界")
    return (len(reasons) > 0, reasons)


# 交界带的「另一种读法」：每条交界原因两侧各是哪一类形态。
# 键 = (交界原因, 当前格局)，值 = 越过该阈值后本盘会落到的另一类形态。
# 只列 _assess_borderline 白名单里实际会命中的格局，不做推断性外扩。
_BORDERLINE_ALT = {
    # 次级空白跨越 CLUSTER_SEP(60°)：连续分布 ↔ 分组分布
    "三元/二四交界": {
        "Locomotive": "See-Saw", "Bucket": "See-Saw", "Sling": "See-Saw",
        "See-Saw": "Locomotive", "Hourglass": "Locomotive",
        "Splay": "See-Saw", "Tripod": "See-Saw",
    },
    # 最大空白跨越 BOWL_THRESHOLD(175°)：半圆分布 ↔ 连续分布
    "碗/半球交界": {
        "Bowl": "Locomotive", "Locomotive": "Bowl",
        "See-Saw": "Bowl", "Bucket": "Bowl", "TwoHandle": "Bowl",
    },
    # 最大空白跨越 BUNDLE_THRESHOLD(230°)：窄扇区 ↔ 半圆
    "丛聚交界": {"Bundle": "Bowl", "Bowl": "Bundle", "Fanhandle": "Bowl"},
    # 两处显著空白中较小者跨越 HOURGLASS_MIN_GAP(90°)
    "沙漏交界": {"See-Saw": "Hourglass", "Hourglass": "See-Saw"},
    # 三处显著空白中最小者跨越 90°
    "蝴蝶/三脚架交界": {
        "Splay": "Tripod", "Tripod": "Splay", "Butterfly": "Splay",
    },
    # 把手间距跨越 CONJ_HANDLE_ORB / TWO_HANDLE_MIN_SEP(8°)：合成一个把手 ↔ 分成两个
    "合相/双把手交界": {"ConjHandle": "TwoHandle", "TwoHandle": "ConjHandle"},
    "双星把手/跷跷板重叠": {"ConjHandle": "See-Saw"},
    # 第三颗孤立行星：Sellar「begins to have the character of a See-Saw」
    "第三把手/跷跷板交界": {"TwoHandle": "See-Saw"},
}

_PATTERN_ZH = {
    "Splash": "散落型", "Bundle": "丛聚型", "Bowl": "碗型", "Bucket": "提桶型",
    "Locomotive": "火车头型", "See-Saw": "跷跷板型", "Splay": "展开型",
    "Fanhandle": "扇柄型", "Sling": "弹弓型", "ConjHandle": "合相把手型",
    "TwoHandle": "双把手提桶型", "Hourglass": "沙漏型", "Butterfly": "蝴蝶型",
    "Tripod": "三脚架型",
}


class _ProbeFlag(threading.local):
    """标记当前线程是否正处在交界探测里。

    _probe_alternate 会回调 detect_with_variants 做实算，若不加标记，实算又会
    触发交界探测，无限递归。用 threading.local 保证多 worker 下互不串扰。
    """

    def __init__(self) -> None:
        self.value = False


_PROBING = _ProbeFlag()


# 每条交界对应"把哪个量推过去就会改判"的旋钮。值 = (旋钮名, 目标阈值)：
#   max_gap     —— 最大空白；把最大空白撑大/压小（其余行星等比让位）
#   second_gap  —— 碗内/群内第二段空白；把次大空白撑到成群分隔
#   min_sig_gap —— 若干显著空白里最小的那段
#   handle_sep  —— 两颗把手行星之间的间距；跨过 8° 即在合相把手／双把手之间翻面
# 没有列在这里的交界没有可靠的几何旋钮，保留原查表方向。
_PROBE_KNOBS: Dict[str, Tuple[str, float]] = {
    "碗/半球交界": ("max_gap", BOWL_THRESHOLD),
    "丛聚交界": ("max_gap", BUNDLE_THRESHOLD),
    "三元/二四交界": ("second_gap", CLUSTER_SEP),
    "沙漏交界": ("min_sig_gap", HOURGLASS_MIN_GAP),
    "蝴蝶/三脚架交界": ("min_sig_gap", BUTTERFLY_MIN_GAP),
    "合相/双把手交界": ("handle_sep", CONJ_HANDLE_ORB),
}

# 旋钮的读者可懂说法：交界提示要能回答"在看哪个量"，否则界面上只剩一个
# 没有单位归属的度数差，读盘的人无从复核。
_KNOB_ZH: Dict[str, str] = {
    "max_gap": "最大空白",
    "second_gap": "群内第二段空白",
    "min_sig_gap": "最窄的显著空白",
    "handle_sep": "两颗把手之间的间距",
}


def _longs_from_gaps(gaps: List[float]) -> List[float]:
    """由间隔序列还原一组等价经度（从 0° 起算）。

    琼斯格局判定只看行星之间的相对间隔，整体旋转不影响分类，因此还原出的这组
    经度足以复跑引擎。
    """
    longs = [0.0]
    for gap in gaps[:-1]:
        longs.append(longs[-1] + gap)
    return longs


def _nudge_gaps(gaps: List[float], idx: int, target: float) -> Optional[List[float]]:
    """把第 idx 段间隔调到 target，差额由群内的小间隔分摊，总和保持 360°。

    吞吐方的选择是这个探测能否成立的关键，两种直觉做法都不行：
      · 按比例摊给所有间隔 —— 等于把整张盘揉匀，十颗行星被推成均布，引擎一律
        判成散落型；
      · 全部由最大间隔吞吐 —— 最大空白本身是 Bowl/Locomotive/Bundle 各条阈值
        的判据，压缩它会先触发别的改判，探到的是它的副作用而不是本旋钮。
    因此差额只摊给"其余小间隔"（小于 CLUSTER_SEP 的那些群内间隔），让最大空白
    与其余显著空白保持原样，等价于在盘内挪动行星。

    返回 None 表示这个目标做不到（小间隔不够吞吐）。
    """
    need = target - gaps[idx]
    donors = [i for i, g in enumerate(gaps) if i != idx and g < CLUSTER_SEP]
    pool = sum(gaps[i] for i in donors)
    # 留出余量：小间隔不能被压到 0，否则行星叠成一点，形态同样失真。
    if not donors or pool - need <= len(donors):
        return None
    scale = (pool - need) / pool
    out = list(gaps)
    out[idx] = target
    for i in donors:
        out[i] = gaps[i] * scale
    return out


def _widen_candidates(gaps: List[float], target: float) -> List[List[float]]:
    """把"某段间隔撑到 target"的所有落点都列出来，供探测逐个试。

    撑开的位置决定形态：同样是撑出一段 60° 空白，开在星群中间会把盘切成两群
    （跷跷板），开在最边上只切下孤零零一颗（散落）。因此不能只认某一段间隔，
    要把每个可行落点都试一遍，再由调用方按多数票取主流走向。
    """
    out = []
    for idx, gap in enumerate(gaps):
        if gap >= target:
            continue
        nudged = _nudge_gaps(gaps, idx, target)
        if nudged is not None:
            out.append(nudged)
    return out


def _vote_alternate(
    trials: List[List[float]],
    pattern_en: str,
    delta: Optional[float],
    knob_zh: Optional[str],
) -> Tuple[Optional[str], Optional[float], Optional[str]]:
    """把候选盘逐个喂回引擎，按多数票给出主流走向。

    多数票的意义：一条交界要回答的是"这类盘再走一步最常变成什么"。个别落点
    造成的极端形态（例如只切下孤零零一颗星）不应盖过主流方向。
    """
    votes: Dict[str, int] = {}
    _PROBING.value = True
    try:
        for probed in trials:
            try:
                alt = detect_with_variants(_longs_from_gaps(probed)).pattern_en
            except Exception:  # 探测失败绝不能拖垮主判定
                continue
            if alt == pattern_en:
                continue
            votes[alt] = votes.get(alt, 0) + 1
    finally:
        _PROBING.value = False
    if not votes:
        return None, None, None
    alt = max(votes.items(), key=lambda kv: kv[1])[0]
    return alt, delta, knob_zh


def _handle_sep_candidates(
    gaps: List[float],
    extra: Optional[Dict],
    goal: float,
) -> List[List[float]]:
    """把两颗把手之间的间距调到 goal，返回可复跑的间隔序列。

    把手间距不是 gaps 里的某一段（gaps 记的是相邻行星的间隔，而两颗把手正是
    相邻的一对），所以要先在 gaps 里认出它：把手两侧各有 ≥CLUSTER_SEP 的空白，
    夹在中间的那段小间隔就是把手间距。改动它时，差额由两侧的把手空白分摊——
    这两段远大于 8°，吞吐 1~2° 不会越过任何别的阈值。
    """
    handle = (extra or {}).get("conj_handle") or (extra or {}).get("two_handle") or {}
    sep = handle.get("sep")
    if sep is None:
        return []
    n = len(gaps)
    out: List[List[float]] = []
    for i, gap in enumerate(gaps):
        if abs(gap - float(sep)) > 0.5:
            continue
        left, right = (i - 1) % n, (i + 1) % n
        if gaps[left] < CLUSTER_SEP or gaps[right] < CLUSTER_SEP:
            continue
        need = goal - gap
        # 两侧把手空白各吞吐一半。它们必须始终保持 ≥CLUSTER_SEP，否则把手会被
        # 并回主群，探到的就不再是"间距翻面"而是把手消失。
        if (gaps[left] - need / 2 < CLUSTER_SEP
                or gaps[right] - need / 2 < CLUSTER_SEP):
            continue
        nudged = list(gaps)
        nudged[i] = goal
        nudged[left] -= need / 2
        nudged[right] -= need / 2
        out.append(nudged)
    return out


def _probe_alternate(
    reason: str,
    pattern_en: str,
    gaps: List[float],
    extra: Optional[Dict] = None,
) -> Tuple[Optional[str], Optional[float], Optional[str]]:
    """实算这条交界往前推会变成什么格局，以及还差多少度。

    做法：把触发该交界的那个量推过它的阈值，其余间隔让位，再把还原出来的盘喂回
    detect_with_variants，读引擎的真实判定。这样"另一种读法"不再依赖人工查表
    是否与改判闸门同步。

    返回 (另一类格局, 距改判还差多少度, 在看哪个量)：
      · (形态, 度数, 量名) —— 实算确认推过去会改判成该形态
      · (None, None, None) —— 该交界可实算，但推到阈值也不会改判
      · (False, None, None) —— 该交界没有可实算的旋钮，沿用查表方向
    """
    if reason == "双星把手/跷跷板重叠":
        sig_idxs = [i for i, gap in enumerate(gaps) if gap >= CLUSTER_SEP]
        if (pattern_en == "ConjHandle" and len(sig_idxs) == 2
                and min(gaps[i] for i in sig_idxs) >= 70.0
                and sorted(_group_sizes(gaps, sig_idxs)) == [2, 8]):
            # 直接复算 Jones 允许的 2:8 双群结构；两种读法同时成立，
            # 因而没有「距阈值几度」这一数值。
            return "See-Saw", None, None
        return None, None, None
    knob = _PROBE_KNOBS.get(reason)
    if knob is None or len(gaps) < 3:
        return False, None, None
    name, threshold = knob
    if name == "handle_sep":
        handle = (extra or {}).get("conj_handle") or (extra or {}).get("two_handle") or {}
        sep = handle.get("sep")
        if sep is None:
            return False, None, None
        delta = round(abs(float(sep) - threshold), 1)
        trials: List[List[float]] = []
        for margin in (0.5, -0.5):
            goal = threshold + margin
            if goal <= 0:
                continue
            trials.extend(_handle_sep_candidates(gaps, extra, goal))
        if not trials:
            return False, None, None
        return _vote_alternate(trials, pattern_en, delta, _KNOB_ZH.get(name))
    order = sorted(range(len(gaps)), key=lambda i: gaps[i], reverse=True)
    if name == "max_gap":
        idx = order[0]
    elif name == "second_gap":
        idx = order[1]
    else:  # min_sig_gap：若干显著空白里最小的那段
        sig = [i for i in order if gaps[i] >= CLUSTER_SEP]
        if not sig:
            return False, None, None
        idx = sig[-1]
    current = gaps[idx]
    delta = round(abs(current - threshold), 1)
    # 交界盘可能贴在阈值任意一侧，两个方向都要探：贴在下方就往上推，贴在上方
    # 就往下压。只探一个方向时，已经在上方的盘（如三段空白都 ≥90° 的蝴蝶型）
    # 推过去仍是同一格局，会错报成"没有另一种读法"。
    trials: List[List[float]] = []
    for margin in (0.5, -0.5):
        goal = threshold + margin
        if goal <= 0:
            continue
        if name == "second_gap" and margin > 0:
            # 撑开一段群内空白：落点决定形态（中间=切成两群，边上=切下一颗孤星），
            # 因此把每个落点都试一遍，由多数票给出主流走向。
            trials.extend(_widen_candidates(gaps, goal))
        else:
            nudged = _nudge_gaps(gaps, idx, goal)
            if nudged is not None:
                trials.append(nudged)
    if not trials:
        return None, None, None
    return _vote_alternate(trials, pattern_en, delta, _KNOB_ZH.get(name))


def _borderline_alternates(
    pattern_en: str,
    reasons: List[str],
    gaps: List[float],
    span: float = 0.0,
    extra: Optional[Dict] = None,
) -> List[Dict]:
    """把交界旗标展开成可对照的「另一种读法」。

    _assess_borderline 只回答「这张盘贴着某条阈值吗」，读盘的人接着要问的是
    「贴着哪条线、往哪边倒、还差多少」。本函数补的就是这三项：越过该阈值后
    本盘会落到的另一类形态，以及当前实测量距该阈值的度数差。

    与 _assess_borderline 一样**不改变分类**——阈值、白名单、命中条件全部复用
    上面那份判据，这里只做一次映射与差值计算，不新增任何判定路径。
    Sellar《Chart Shapes》第 1 章：边界盘"不是问题，反而对解读有帮助"，建议
    先定最接近的一类，再对照另一类的次序读一遍。

    _BORDERLINE_ALT 是一张人工维护的查表，个别条目的"另一类形态"与引擎真正的
    改判闸门并不完全同步（历史实例：已下线的「碗型跨度上限交界」曾报"跷跷板型
    差 0.3°"，但跨度越线本身根本不触发改判，真正缺的是碗内第二段 ≥60° 空白）。因此每条
    候选都再经 _probe_alternate 实算校验：沿该交界对应的那个量推过阈值，看引擎
    实际判成什么。校验通过的候选带上"还差多少度"，不通过的按引擎实判结果修正。
    """
    if not reasons or not gaps:
        return []
    extra = extra or {}
    mg = max(gaps)
    mg_idx = gaps.index(mg)
    sec = sorted((g for i, g in enumerate(gaps) if i != mg_idx), reverse=True)
    s2 = sec[0] if sec else 0.0
    sig_vals = sorted((g for g in gaps if g >= CLUSTER_SEP), reverse=True)
    handle = extra.get("conj_handle") or extra.get("two_handle") or {}
    # 每条原因对应的实测量与阈值——与 _assess_borderline 里的判据一一对齐。
    measured = {
        "三元/二四交界": (s2, CLUSTER_SEP),
        "碗/半球交界": (mg, BOWL_THRESHOLD),
        "丛聚交界": (mg, BUNDLE_THRESHOLD),
        "沙漏交界": (min(sig_vals) if sig_vals else None, HOURGLASS_MIN_GAP),
        "蝴蝶/三脚架交界": (min(sig_vals) if sig_vals else None, BUTTERFLY_MIN_GAP),
        "合相/双把手交界": (handle.get("sep"), CONJ_HANDLE_ORB),
    }
    out: List[Dict] = []
    for reason in reasons:
        alt_en = _BORDERLINE_ALT.get(reason, {}).get(pattern_en)
        if not alt_en:
            continue
        value, threshold = measured.get(reason, (None, None))
        delta = (round(abs(float(value) - threshold), 1)
                 if value is not None and threshold is not None else None)
        probed_en, probed_delta, probed_knob = _probe_alternate(
            reason, pattern_en, gaps, extra
        )
        knob_zh = None
        if isinstance(probed_en, str):
            # 实算结果优先：它同时给出真正的另一类形态与真正的改判距离。
            alt_en, delta, knob_zh = probed_en, probed_delta, probed_knob
        elif probed_en is None:
            # 该交界可实算，但推到阈值也不改判 → 不报方向，避免再次出现
            # "指着一个引擎永远不会走到的形态"。
            continue
        # probed_en is False：没有可实算的旋钮，沿用查表方向与阈值距离。
        out.append({
            "reason": reason,
            "pattern_en": alt_en,
            "pattern_zh": _PATTERN_ZH.get(alt_en, alt_en),
            "delta_deg": delta,
            # 这个度数差是在看哪个量：没有它，界面上的"差 15.7°"无从复核。
            "measure_zh": knob_zh,
        })
    return out
def detect_with_variants(
    planetary_longitudes: List[float],
    planet_names: Optional[List[str]] = None,
    lang: str = "zh",
) -> PatternResult:
    """
    完整格局识别：七种基础格局 + 七种变形格局。

    与 detect_jones_pattern() 的区别：
    - 本函数在基础识别后额外执行变形格局精化
    - 可能返回 Fanhandle / Sling / ConjHandle / TwoHandle /
               Hourglass / Butterfly / Tripod

    参数与 detect_jones_pattern() 相同。
    """
    orig_longs, names = _validate_planetary_inputs(planetary_longitudes, planet_names, lang)
    sorted_longs = sorted(orig_longs)
    gaps         = _calc_gaps(sorted_longs)

    # 1. 基础七种格局
    base = detect_jones_pattern(planetary_longitudes, names, lang)

    # 2. 变形精化
    result = _refine_to_variant(base, sorted_longs, gaps, orig_longs, names)

    # 3. 核心整合轴线收口（单一事实来源，按最终格局裁定）
    #    Jones/Sellar 原典：核心对分相整合轴线只属于缺乏天然焦点的弥散/对称格局。
    #    自带几何杠杆的格局（把手/引导星/孤星顶点）叠加轴线属误用，故清除从父格局
    #    extra 经 {**result.extra} 意外继承来的 sellar_focus。
    if result.pattern_en not in SELLAR_PATTERNS:
        result.extra.pop("sellar_focus", None)

    # 3.5 置信度补正：双把手各分支一律保守地标 moderate，但两把手各自被
    #     清晰空白(≥70°)分隔的"干净双把手"(如 Churchill 83.8°/78.8°)应判 clear。
    if result.pattern_en == "TwoHandle":
        _sig = sorted((g for g in gaps if g >= CLUSTER_SEP), reverse=True)
        if len(_sig) >= 2 and _sig[1] >= 70.0:
            result.confidence = "clear"

    # 4. 边界提示（不改变分类，仅标记是否贴着相邻格局阈值，供前端提示肉眼复核）
    #    _probe_alternate 会反过来调用本函数做实算，此时跳过本段，否则无限递归。
    if _PROBING.value:
        return result
    is_borderline, bl_reasons = _assess_borderline(result.pattern_en, gaps, result.span, result.extra)
    result.extra["borderline"] = is_borderline
    if is_borderline:
        result.extra["borderline_reasons"] = bl_reasons
        # 4.1 交界推荐：把旗标展开成「另一种读法 + 还差多少度」，供前端一行短句呈现。
        alts = _borderline_alternates(
            result.pattern_en, bl_reasons, gaps, result.span, result.extra
        )
        if alts:
            result.extra["borderline_alternates"] = alts
    return result


# ──────────────────────────────────────────────────────────────
# 测试用例（基础 + 变形）
# ──────────────────────────────────────────────────────────────

def _run_tests():
    """基础格局测试（使用 detect_jones_pattern，不含变形精化）"""
    base_cases = [
        ("散落型（Splash）—— 均匀分布",
         [15, 50, 88, 122, 161, 200, 241, 275, 315, 352], "Splash"),
        ("丛聚型（Bundle）—— 80° 内",
         [10, 18, 28, 40, 50, 58, 65, 72, 80, 88], "Bundle"),
        ("火车头型（Locomotive）—— 空白 ~118°",
         [0, 18, 45, 80, 110, 150, 175, 210, 228, 242], "Locomotive"),
        ("碗型（Bowl）",
         [10, 30, 55, 80, 110, 130, 150, 165, 175, 180], "Bowl"),
        ("提桶型（Bucket）max_gap≥170°",
         [10, 30, 55, 80, 110, 130, 150, 170, 180, 290], "Bucket"),
        ("提桶型（Bucket）max_gap<170°",
         [10, 30, 55, 80, 110, 130, 150, 165, 175, 275], "Bucket"),
        ("跷跷板型（See-Saw）",
         [10, 25, 40, 55, 70, 190, 205, 220, 235, 250], "See-Saw"),
        ("展开型（Splay）三星群",
         [10, 25, 40, 130, 145, 160, 252, 268, 282, 300], "Splay"),
        ("边界：max_gap=176°≥BOWL_THRESHOLD=175°（跨度184°≤185°）→碗型",
         [10, 30, 55, 80, 110, 130, 150, 165, 175, 194], "Bowl"),
        ("边界：max_gap=165°<175°（跨度195°>185°）→火车头",
         [10, 30, 55, 80, 110, 130, 150, 165, 175, 340], "Locomotive"),
    ]

    variant_cases = [
        # (名称, 度数列表, 期望变形格局)
        ("弹弓型（Sling）—— 主群 ≤120°",
         [10, 25, 40, 60, 75, 90, 105, 115, 120, 285],
         # 主群10~120=110°, 把手285°: 距120: 165°, 距10: 85°
         "Sling"),
        ("扇柄型（Fanhandle）—— 主群 ≤90°",
         [10, 20, 35, 50, 65, 75, 82, 88, 92, 265],
         # 主群10~92=82°, 把手265°: 距92: 173°, 距10: 105°
         "Fanhandle"),
        ("沙漏型（Hourglass）—— 两侧空白均≥90°",
         [5, 20, 35, 50, 65, 195, 210, 225, 240, 255],
         # gaps: ~120° and ~130°, both ≥90°
         "Hourglass"),
        ("三脚架型（Tripod）—— 三群各≥90°",
         [0, 10, 20, 120, 130, 140, 240, 252, 262, 270],
         # 群1: 0-20°, 群2: 120-140°, 群3: 240-270°
         # gap1=100°, gap2=100°, gap3=90° ← 全部≥90° ✓
         "Tripod"),
        ("双把手型（TwoHandle）—— 8碗+2独立把手",
         [0, 20, 40, 60, 80, 100, 120, 140, 240, 300],
         # 8星: 0~140=140°, 把手240°(距140:100°), 把手300°(距0:60°)
         "TwoHandle"),
        ("NotebookLM：Billie Jean King —— Bowl 不应误升 TwoHandle",
         [239.6, 180.7, 246.6, 193.1, 77.6, 146.3, 85.0, 67.1, 183.7, 128.7],
         "Bowl"),
        ("NotebookLM：Steve Wozniak —— Fanhandle",
         [138.4, 114.2, 164.0, 114.0, 210.6, 334.4, 168.4, 97.7, 195.1, 137.8],
         "Fanhandle"),
        ("NotebookLM：Humphry Davy —— Sling",
         [265.5, 247.0, 280.2, 294.5, 196.7, 176.2, 232.2, 77.3, 181.4, 300.4],
         "Sling"),
        ("NotebookLM：Annie Besant —— Splay",
         [187.9, 102.9, 196.7, 191.0, 45.2, 108.4, 337.5, 16.6, 328.0, 26.3],
         "Splay"),
        ("NotebookLM：Lord Byron —— Butterfly",
         [302.3, 115.1, 288.8, 325.4, 101.9, 77.1, 327.9, 118.0, 201.1, 315.4],
         "Butterfly"),
        ("1971-10-19 上海 —— 碗内75°大空白(木→火)，火星应为第二把手→双把手(非提桶)",
         [205.40, 206.72, 212.77, 219.36, 321.33, 246.28, 65.71, 194.68, 241.47, 180.51],
         "TwoHandle"),
        ("NotebookLM：Jonas Salk —— Tripod",
         [214.2, 333.5, 232.9, 250.5, 230.0, 313.0, 92.2, 307.7, 120.4, 92.1],
         "Tripod"),
        ("NotebookLM：1967-11-18 台湾桃园 —— 2vs8 应判双把手",
         [235.073, 65.109, 215.752, 188.724, 289.482,
          154.020, 6.051, 178.203, 234.119, 172.463],
         "TwoHandle"),
        ("NotebookLM：George Washington —— 软边界火车头",
         [333.313, 286.837, 306.559, 359.406, 233.230,
          188.618, 2.694, 250.059, 74.668, 197.697],
         "Locomotive"),
        ("NotebookLM：合相把手不应被火车头抢判",
         [0, 5, 150, 168, 174, 184, 211, 229, 234, 289],
         "ConjHandle"),
        ("NotebookLM：1/1/8 双单星支点应判双把手",
         [0, 75, 150, 164, 178, 192, 206, 220, 234, 248],
         "TwoHandle"),
        ("NotebookLM：非合相双把手不应被火车头抢判",
         [0, 20, 150, 168, 174, 184, 211, 229, 234, 289],
         "TwoHandle"),
        ("结构边界：近50°支点分隔+射线式小群应判三脚架",
         [30, 79, 150, 153, 157, 160, 240, 270, 303, 350],
         "Tripod"),
        ("结构边界：165°级近半球空白应判碗型",
         [30, 44, 73, 80, 81, 247, 269, 302, 313, 356],
         "Bowl"),
        ("三把手构型：仍判双把手但须带第三把手交界旗标（Sellar：begins to have "
         "the character of a See-Saw）",
         [0, 10, 20, 30, 40, 50, 60, 120, 200, 280],
         "TwoHandle"),
    ]

    bidirectional_cases = [
        ("正向：2vs8 应判双把手",
         [0, 59, 150, 168, 174, 184, 211, 229, 234, 289],
         {"TwoHandle"}),
        ("反向：5vs5 保持跷跷板/沙漏家族",
         [10, 25, 40, 55, 70, 190, 205, 220, 235, 250],
         {"See-Saw", "Hourglass"}),
        ("反向：4vs6 保持跷跷板/沙漏家族",
         [5, 20, 35, 50, 150, 165, 180, 195, 210, 225],
         {"See-Saw", "Hourglass"}),
        ("反向：3vs7 保持跷跷板/沙漏家族",
         [0, 15, 30, 130, 145, 160, 175, 190, 205, 220],
         {"See-Saw", "Hourglass"}),
        ("反向：1vs9 保持提桶家族",
         [10, 30, 55, 80, 110, 130, 150, 170, 180, 290],
         {"Bucket", "Sling", "Fanhandle"}),
        ("反向：纯碗型不误升双把手",
         [10, 30, 55, 80, 110, 130, 150, 165, 175, 180],
         {"Bowl"}),
        ("反向：合相把手不误判双把手",
         [172.2, 181.7, 195.2, 218.5, 264.7, 302.6, 159.2, 204.9, 66.8, 67.9],
         {"ConjHandle", "Bucket", "Sling", "Fanhandle"}),
        ("反向：合相把手不误判火车头",
         [0, 5, 150, 168, 174, 184, 211, 229, 234, 289],
         {"ConjHandle", "Bucket", "Sling", "Fanhandle"}),
        ("反向：5vs5 紧密双群不误判火车头",
         [0, 12, 24, 36, 48, 145, 157, 169, 181, 193],
         {"See-Saw", "Hourglass"}),
        ("正向：1/1/8 应判双把手",
         [0, 75, 150, 164, 178, 192, 206, 220, 234, 248],
         {"TwoHandle"}),
        ("正向：非合相双把手应判双把手",
         [0, 20, 150, 168, 174, 184, 211, 229, 234, 289],
         {"TwoHandle"}),
        ("反向：半球内6vs4仍优先碗型",
         [0, 12, 24, 36, 48, 60, 145, 157, 169, 181],
         {"Bowl"}),
        ("反向：半球内7vs3仍优先碗型",
         [0, 12, 24, 36, 48, 60, 72, 145, 157, 169],
         {"Bowl"}),
    ]

    sep = "=" * 68

    print("\n【基础格局测试】")
    passed = 0
    for name, longs, expect in base_cases:
        result = detect_jones_pattern(longs)
        ok = "✅" if result.pattern_en == expect else "❌"
        print(f"  {ok} {name}: 期望={expect}, 实际={result.pattern_en}")
        if result.pattern_en == expect:
            passed += 1
    print(f"  基础格局：{passed}/{len(base_cases)} 通过")

    print("\n【变形格局测试】")
    passed2 = 0
    for name, longs, expect in variant_cases:
        result = detect_with_variants(longs)
        ok = "✅" if result.pattern_en == expect else "❌"
        print(f"\n{sep}")
        print(f"  {ok} {name}")
        print(f"  度数: {longs}")
        print(f"  期望: {expect}  →  实际: {result.pattern_en}")
        print(result)
        if result.pattern_en == expect:
            passed2 += 1

    print("\n【双向回归测试】")
    passed3 = 0
    for name, longs, expects in bidirectional_cases:
        result = detect_with_variants(longs)
        ok_bool = result.pattern_en in expects
        ok = "✅" if ok_bool else "❌"
        expect_desc = "/".join(sorted(expects))
        print(f"  {ok} {name}: 期望∈{expect_desc}, 实际={result.pattern_en}")
        if ok_bool:
            passed3 += 1
    print(f"  双向回归：{passed3}/{len(bidirectional_cases)} 通过")

    print(f"\n{'─'*68}")
    total = len(base_cases) + len(variant_cases) + len(bidirectional_cases)
    print(f"  总计：{passed + passed2 + passed3}/{total} 通过")


if __name__ == "__main__":
    _run_tests()
