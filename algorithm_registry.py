"""希腊星智算法注册表 (Algorithm Registry).

本次 Sprint 1 Step 2 阶段依照审计基线只登记 5 项核心基础算法：
1. planetary_longitudes (行星经度)
2. axes_and_placidus_houses (四轴与普拉西度宫位)
3. whole_sign_houses (整宫制)
4. lunar_nodes (月交点)
5. chiron (凯龙星)
相位、绘图、组合盘、返照盘、月相、流年等自研算法留待后续补登。
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
