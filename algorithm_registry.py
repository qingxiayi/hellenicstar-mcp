"""希腊星智算法注册表 (Algorithm Registry).

登记本命基础算法及后续计算模块的实际源码、计算约定与边界。
登记不代表独立精度验证，也不代表某次请求执行了全部依赖。
"""
from dataclasses import dataclass, asdict
from typing import Dict, Any, Optional


@dataclass(frozen=True)
class AlgorithmEntry:
    key: str                        # 唯一标识键
    name: str                       # 算法名称
    category: str                   # 分类
    source: str                     # 底层来源分类: kerykeion / pyswisseph / proprietary / hybrid
    implementation: str             # 实际执行类/函数描述
    file_path: str                  # 核心实现代码文件路径
    code_anchor: str                # 源码中的特征锚点字符串，用于鲁棒测试断言
    code_location: str              # 核心代码位置 (文件:行号)，供审计查阅
    coordinate_system: str          # 坐标系 / 黄道定义
    calculation_model: str          # 计算模型与要素说明
    fallback: Optional[str]         # 降级或兜底实现
    precision: str                  # 精度说明 (查无官方数据填 UNKNOWN)
    version_history: str            # 版本历史 (查无官方数据填 UNKNOWN)
    notes: Optional[str] = None     # 审计备注


ALGORITHM_REGISTRY: Dict[str, AlgorithmEntry] = {
    # 1. 行星经度
    "planetary_longitudes": AlgorithmEntry(
        key="planetary_longitudes",
        name="Planetary Longitudes",
        category="celestial_body",
        source="kerykeion",
        implementation="kerykeion.AstrologicalSubjectFactory",
        file_path="engine/natal_chart.py",
        code_anchor="AstrologicalSubjectFactory",
        code_location="engine/natal_chart.py:3800",
        coordinate_system="Tropical Zodiac, Geocentric",
        calculation_model="通过 kerykeion subject 提取十大行星 (Sun, Moon, Mercury, Venus, Mars, Jupiter, Saturn, Uranus, Neptune, Pluto) 经度与逆行状态",
        fallback=None,
        precision="UNKNOWN",
        version_history="UNKNOWN",
        notes="先尝试 KrInstance（5.12.9 中不存在），except 分支使用 AstrologicalSubjectFactory (engine/natal_chart.py:3770-3783)；行星经度提取位于 engine/natal_chart.py:3800-3806",
    ),

    # 2. 四轴与普拉西度宫位
    "axes_and_placidus_houses": AlgorithmEntry(
        key="axes_and_placidus_houses",
        name="Axes and Placidus Houses",
        category="axes_and_houses",
        source="pyswisseph",
        implementation="swe.houses(jd, lat, lng, b'P')",
        file_path="engine/natal_chart.py",
        code_anchor="swe.houses(jd, lat, lng, b'P')",
        code_location="engine/natal_chart.py:2674",
        coordinate_system="Tropical Zodiac (回归黄道)",
        calculation_model="瑞士星历表 houses 函数计算普拉西度分宫制，四轴由 ascmc 输出派生 (ASC=ascmc[0], MC=ascmc[1], DESC=ASC+180, IC=MC+180)",
        fallback=None,
        precision="UNKNOWN",
        version_history="UNKNOWN",
        notes="四轴提取与规范化逻辑位于 engine/natal_chart.py:2677-2680",
    ),

    # 3. 整宫制
    "whole_sign_houses": AlgorithmEntry(
        key="whole_sign_houses",
        name="Whole Sign Houses",
        category="houses",
        source="proprietary",
        implementation="hellenistic.whole_sign_house(lon, asc_lon)",
        file_path="hellenistic.py",
        code_anchor="def whole_sign_house(lon: float, asc_lon: float) -> int:",
        code_location="hellenistic.py:104",
        coordinate_system="Tropical Zodiac (回归黄道)",
        calculation_model="自研整宫算法：以上升点所在星座 (int(asc_lon // 30)) 为第 1 宫，每 30° 递增一宫",
        fallback=None,
        precision="UNKNOWN",
        version_history="UNKNOWN",
        notes="实现为纯数学取模计算：(int(lon // 30) - int(asc_lon // 30) + 12) % 12 + 1",
    ),

    # 4. 月交点
    "lunar_nodes": AlgorithmEntry(
        key="lunar_nodes",
        name="Lunar Nodes (North Node)",
        category="celestial_body",
        source="pyswisseph",
        implementation="swe.calc_ut(jd_node, swe.MEAN_NODE)",
        file_path="engine/natal_chart.py",
        code_anchor="swe.calc_ut(jd_node, swe.MEAN_NODE)",
        code_location="engine/natal_chart.py:3820",
        coordinate_system="Tropical Zodiac, Geocentric",
        calculation_model="瑞士星历表计算平均交点 (MEAN_NODE)，南交点为北交点对冲 180°",
        fallback="kerykeion subject.true_north_lunar_node (engine/natal_chart.py:3837)",
        precision="UNKNOWN",
        version_history="UNKNOWN",
        notes="主路径代码使用 swe.MEAN_NODE（平均交点）；swisseph 失败时兜底读取 kerykeion 的 true_north_lunar_node（真交点），两者口径不一致",
    ),

    # 5. 凯龙星
    "chiron": AlgorithmEntry(
        key="chiron",
        name="Chiron Position",
        category="celestial_body",
        source="hybrid",
        implementation="swe.calc_ut(jd, swe.CHIRON)",
        file_path="engine/natal_chart.py",
        code_anchor="swe.calc_ut(jd, swe.CHIRON)",
        code_location="engine/natal_chart.py:3853",
        coordinate_system="Tropical Zodiac, Geocentric",
        calculation_model="瑞士星历表 swe.CHIRON（常数 15，依赖 ephe/seas_18.se1 小行星历表）",
        fallback="JPL Horizons 补算 _jpl_chiron (services/calculator.py:900-948)；使用 ObsEclLon（其黄道参考系是否与主路径一致为 UNKNOWN）；该兜底依赖外网连接与 astroquery，若缺失库则静默跳过，网络失败时打印 Warning 跳过",
        precision="UNKNOWN",
        version_history="UNKNOWN",
        notes="当 engine 未能产出 chiron（如缺 seas_18.se1）时，由 calculator.py 捕获并调用 astroquery.jplhorizons 获取小行星 2060 数据",
    ),
}


def get_algorithm_entry(key: str) -> Optional[Dict[str, Any]]:
    entry = ALGORITHM_REGISTRY.get(key)
    return asdict(entry) if entry else None


def list_algorithms() -> Dict[str, Dict[str, Any]]:
    return {k: asdict(v) for k, v in ALGORITHM_REGISTRY.items()}


# Source locators for the calculation families added after the original natal
# registry. This is declared provenance, not an independent accuracy certificate.
def _register_calculation(key, name, file_path, symbol, model, *,
                          source='hybrid', version='UNKNOWN', precision='UNKNOWN',
                          fallback=None, notes=None):
    ALGORITHM_REGISTRY[key] = AlgorithmEntry(
        key=key, name=name, category='calculation', source=source,
        implementation=f'{file_path[:-3].replace("/", ".")}.{symbol}',
        file_path=file_path, code_anchor=f'def {symbol}(',
        code_location=f'{file_path}::{symbol}',
        coordinate_system='Tropical Zodiac; geocentric longitudes and declared local houses where applicable',
        calculation_model=model, fallback=fallback, precision=precision,
        version_history=version,
        notes=notes or 'Declared source dependency; runtime execution path and independent numerical accuracy are not established by this registration.')


_register_calculation('natal_structure_graph', 'Natal structure graph',
    'services/natal_structure_graph.py', 'calculate_structure_graph',
    'Validated natal source; directed traditional/modern dispositors, cycles and basins; symmetric aspect layers, motifs, house rulers and source-fact dependencies. No ranking or psychological inference.',
    version='natal-structure-v1',
    fallback='On unavailable Placidus houses, house-independent partial graph with explicit unavailable axes and houses.')
_register_calculation('natal_salience', 'Natal priority selection',
    'services/natal_salience.py', 'build_salience',
    'Versioned engineering selection rules over the full natal graph. Separate candidate planets, terminal/configuration groups, complete ten-planet profiles and dependency evidence. No importance score, unique core or psychological diagnosis.',
    source='proprietary', version='natal-priorities-v4')
_register_calculation('natal_aspect_dynamics', 'Natal aspect dynamics',
    'services/natal_aspect_dynamics.py', 'calculate_dynamics',
    'Swiss Ephemeris positions and speeds; applying/separating geometry and bounded first exact contacts with station/sign-change context. Search horizon is a caller setting, not a prediction.')
_register_calculation('jones_pattern', 'Jones pattern and parallel natal view',
    'services/jones_pattern.py', 'calculate_jones_pattern',
    'Ten-planet circular distribution classified by the local Jones/Sellar implementation. natal_jones_view projects classification, roles, uncertainty and selected-orb contacts separately from natal priority selection.',
    source='proprietary', version='jones-miniapp-5 / natal-jones-view-v1',
    notes='Local operationalization of Jones/Sellar methods; see docs/natal-jones-parallel-view.md. No independent vote, natal promotion or psychological verification.')
_register_calculation('planetary_aspect_scan', 'Planetary aspect interval scan',
    'services/planetary_aspect_scan.py', 'scan',
    'Shared transit_utils ephemeris positions; unwrap directed relative longitudes, split relative-speed reversals, bracket and bisect exact and orb-boundary crossings. Node convention and interval bounds are explicit.',
    precision='Numerical stopping criteria TIME_TOL=0.05/86400 Julian days and ANGLE_TOL=1e-7 degrees; these are solver tolerances, not a guarantee of astronomical accuracy.')
_register_calculation('current_sky', 'Current sky and lunar phase',
    'services/sky_now.py', 'sky_at',
    'Swiss Ephemeris at a fixed instant: longitudes, phase/illumination, lunation and event searches under local declared aspect and visibility conventions.')
_register_calculation('aspect_windows', 'Active aspect windows',
    'services/aspect_windows.py', 'aspect_groups',
    'PointResolver and transit_utils bracket roots of absolute angular deviation minus configured orb. Uses sky_now orb policy; includes derived lots where location permits. Bounded searches expose availability.')
_register_calculation('lunar_return', 'Lunar return',
    'services/lunar_return.py', 'compute_lunar_return_full',
    'Resolve birth JD, solve transiting Moon longitude equal to natal Moon, compute return houses at residence and explicit natal/return overlays and aspects.')
_register_calculation('secondary_progressions', 'Secondary progressions',
    'services/secondary_progressions.py', 'compute_secondary_progressions',
    'Day-for-year symbolic technique, Swiss Ephemeris progressed positions; Naibod or solar-arc-in-RA progressed angles are explicitly selected. Internal and natal comparison aspects use declared orb matrices.',
    notes='Symbolic time mapping is a technique convention, not a physical causal claim; angle methods are distinct. See services/secondary_progressions.py.')
_register_calculation('timeline_synthesis', 'Timeline synthesis',
    'services/timeline_synthesis.py', 'compute_timeline_synthesis',
    'Merge bounded time-lord, secondary-progression and transit events in stable order. Resonance groups share explicit time windows and focus; they are not independent evidence or predictions.')
_register_calculation('relationship_observation', 'Relationship observation',
    'services/relationship_observation.py', 'calculate_observation_data',
    'Two natal geometries; unique direct contacts, directional paths, bounded one-hop context, overlays and explicit scenario lenses. John Green source locators and ENGINE_DECISION boundaries are returned by provenance().',
    version='john-green-observation-v0.14',
    notes='See docs/relationship-observation.md and per-result provenance. No compatibility score, diagnosis, inferred human history or automatic IFS mapping. Human notes are caller statements, never calculation facts.')
_register_calculation('relationship_observation_timing', 'Relationship timing observations',
    'services/relationship_observation_timing.py', 'calculate_timing_sources',
    'Optional fixed-time transit/progression observations and bounded interval scanning with explicit orbs. Natal mean-node versus explicit-date true-node conventions are disclosed; date-only noon samples are illustrative.',
    notes='Potential dependency only: include_timing=false does not execute it. See timing_provenance(), relationship_observation_windows.py and docs/relationship-observation-timing.md; no outcome prediction.')
