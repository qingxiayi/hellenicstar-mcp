#!/usr/bin/env python3
"""
Astrology Engine Adapter
封装对 astrology_engine 的调用，提供统一接口和增强功能
"""

import sys
import os
from typing import Dict, Any, List, Tuple, Optional
import math


def _ensure_import_path():
    """李孟浩项目：确保本地 engine 模块在路径中"""
    skill_dir = os.path.join(os.path.expanduser("~"), ".hermes/skills/menghao-natal-chart")
    if skill_dir not in sys.path:
        sys.path.insert(0, skill_dir)


def get_natal_chart(year: int, month: int, day: int,
                    hour: int, minute: int, city: str,
                    country_code: str = "CN") -> Dict[str, Any]:
    """
    计算本命盘的统一入口

    Args:
        year, month, day, hour, minute: 出生时间
        city: 城市名
        country_code: 国家代码，默认"CN"

    Returns:
        {
            "success": True/False,
            "data": {...}  # 成功时包含数据
            "error": "..."  # 失败时错误信息
        }
    """
    try:
        # 确保导入路径
        _ensure_import_path()

        # 导入 astrology_engine
        # 李孟浩项目：导入本地 engine（启用福点计算）
        from engine.natal_chart import calculate_natal_chart

        # 城市名中英文映射，确保引擎内部的CITY_COORDINATES能匹配
        CITY_NAME_MAP = {
            "Beijing": "北京", "Shanghai": "上海", "Guangzhou": "广州",
            "Shenzhen": "深圳", "Hangzhou": "杭州", "Nanjing": "南京",
            "Chengdu": "成都", "Chongqing": "重庆", "Xi'an": "西安",
            "Wuhan": "武汉", "Tianjin": "天津", "Shenyang": "沈阳",
            "Qingdao": "青岛", "Suzhou": "苏州", "Jinan": "济南",
            "Zhengzhou": "郑州", "Changsha": "长沙", "Hefei": "合肥",
            "Fuzhou": "福州", "Xiamen": "厦门", "Kunming": "昆明",
            "Guiyang": "贵阳", "Nanning": "南宁", "Lanzhou": "兰州",
            "Xining": "西宁", "Yinchuan": "银川", "Lhasa": "拉萨",
            "Urumqi": "乌鲁木齐", "Hohhot": "呼和浩特", "Harbin": "哈尔滨",
            "Changchun": "长春", "Taiyuan": "太原", "Shijiazhuang": "石家庄",
            "Nanchang": "南昌", "Haikou": "海口", "Sanya": "三亚",
            "Datong": "大同", "Baotou": "包头", "Wenzhou": "温州",
            "Ningbo": "宁波", "Dalian": "大连", "Yantai": "烟台",
            "Xuzhou": "徐州", "Luoyang": "洛阳", "Kaifeng": "开封",
            "Anyang": "安阳", "Nanyang": "南阳", "Dezhou": "德州",
            "Hong Kong": "香港", "Macau": "澳门", "Taipei": "台北",
            "Kaohsiung": "高雄",
        }
        mapped_city = CITY_NAME_MAP.get(city, city)

        # 调用原始计算函数
        raw_result = calculate_natal_chart(year, month, day, hour, minute, mapped_city, country_code)

        if raw_result["status"] != "success":
            return {
                "success": False,
                "error": raw_result.get("message", "计算失败")
            }

        # 增强数据：添加相位格局检测（包括Yod、大十字等）
        enhanced_result = _enhance_with_patterns(raw_result)

        return {
            "success": True,
            "data": enhanced_result
        }

    except ImportError as e:
        return {
            "success": False,
            "error": f"无法导入 astrology_engine 模块: {str(e)}"
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"计算过程中发生错误: {str(e)}"
        }


def _enhance_with_patterns(raw_result: Dict[str, Any]) -> Dict[str, Any]:
    """
    增强原始结果，添加相位格局检测
    """
    # 复制原始结果
    result = raw_result.copy()

    # 准备所有点用于相位检测
    all_points = _prepare_all_points(result)

    # 检测相位格局
    patterns = {
        "grand_trine": _detect_grand_trine(all_points),
        "t_square": _detect_t_square(all_points),
        "yod": _detect_yod(all_points),
        "grand_cross": _detect_grand_cross(all_points),
        "kite": _detect_kite(all_points),
        "empty_planets": _detect_empty_planets(all_points)
    }

    # 过滤：纯虚点格局不保留（至少含一个行星实体）
    virtual_zh_set = {"上升点", "中天", "下降点", "天底", "北交点", "南交点"}
    patterns = {
        k: [entry for entry in v if not all(p in virtual_zh_set for p in entry)]
        for k, v in patterns.items()
    }

    # 将格局检测结果添加到结果中
    if "patterns" not in result:
        result["patterns"] = {}

    result["patterns"]["phase_patterns_enhanced"] = patterns

    return result


def _prepare_all_points(result: Dict[str, Any]) -> List[Tuple[str, Dict[str, Any]]]:
    """
    准备所有点用于相位检测
    包括：十大行星、特殊点（南北交、凯龙）、四轴
    """
    points = []

    # 星座缩写到中文的映射
    signs_zh = {
        "Ari": "白羊座", "Tau": "金牛座", "Gem": "双子座", "Can": "巨蟹座",
        "Leo": "狮子座", "Vir": "处女座", "Lib": "天秤座", "Sco": "天蝎座",
        "Sag": "射手座", "Cap": "摩羯座", "Aqu": "水瓶座", "Pis": "双鱼座"
    }

    # 行星中文名称映射
    planets_zh = {
        "sun": "太阳", "moon": "月亮", "mercury": "水星", "venus": "金星",
        "mars": "火星", "jupiter": "木星", "saturn": "土星", "uranus": "天王星",
        "neptune": "海王星", "pluto": "冥王星",
        "true_north_lunar_node": "北交点", "true_south_lunar_node": "南交点",
        "chiron": "凯龙星",
        "ascendant": "上升点", "midheaven": "中天",
        "descendant": "下降点", "imum_coeli": "天底"
    }

    # 1. 添加十大行星
    planets = result.get("planets", {})
    for planet_name in ["sun", "moon", "mercury", "venus", "mars",
                       "jupiter", "saturn", "uranus", "neptune", "pluto"]:
        if planet_name in planets:
            planet = planets[planet_name]
            point_info = {
                "name": planet_name,
                "name_zh": planets_zh.get(planet_name, planet_name),
                "longitude": planet.get("longitude", 0),
                "sign": planet.get("sign", ""),
                "sign_zh": planet.get("sign_zh", signs_zh.get(planet.get("sign", ""), "")),
                "position": planet.get("position", 0),
                "type": "planet"
            }
            points.append((planet_name, point_info))

    # 2. 添加特殊点（北交点、凯龙星）
    special_points = result.get("special_points", {})
    for point_name in ["true_north_lunar_node", "chiron"]:
        if point_name in special_points:
            point = special_points[point_name]
            point_info = {
                "name": point_name,
                "name_zh": planets_zh.get(point_name, point_name),
                "longitude": point.get("longitude", 0),
                "sign": point.get("sign", ""),
                "sign_zh": point.get("sign_zh", signs_zh.get(point.get("sign", ""), "")),
                "position": point.get("position", 0),
                "type": "special_point"
            }
            points.append((point_name, point_info))

    # 3. 添加南交点（如果原始数据中没有，需要计算）
    # 注意：南交点 = 北交点 + 180°
    if "true_north_lunar_node" in special_points:
        north_node = special_points["true_north_lunar_node"]
        south_node_lon = (north_node.get("longitude", 0) + 180) % 360
        sign_num = int(south_node_lon // 30)
        zodiac_abbrs = ["Ari", "Tau", "Gem", "Can", "Leo", "Vir",
                       "Lib", "Sco", "Sag", "Cap", "Aqu", "Pis"]
        sign = zodiac_abbrs[sign_num]
        position = south_node_lon - (sign_num * 30)

        point_info = {
            "name": "true_south_lunar_node",
            "name_zh": "南交点",
            "longitude": south_node_lon,
            "sign": sign,
            "sign_zh": signs_zh.get(sign, sign),
            "position": position,
            "type": "special_point"
        }
        points.append(("true_south_lunar_node", point_info))

    # 4. 添加四轴
    axes = result.get("axes", {})
    for axis_name in ["ascendant", "midheaven"]:
        if axis_name in axes:
            axis = axes[axis_name]
            point_info = {
                "name": axis_name,
                "name_zh": planets_zh.get(axis_name, axis_name),
                "longitude": axis.get("longitude", 0),
                "sign": axis.get("sign", ""),
                "sign_zh": axis.get("sign_zh", signs_zh.get(axis.get("sign", ""), "")),
                "position": axis.get("position", 0),
                "type": "axis"
            }
            points.append((axis_name, point_info))

    return points


def _angular_difference(lon1: float, lon2: float) -> float:
    """计算两个经度之间的最小角度差 (0-180度)"""
    diff = abs(lon1 - lon2) % 360
    return min(diff, 360 - diff)


def _has_aspect(point1: Dict[str, Any], point2: Dict[str, Any],
                target_angle: float, orb: float) -> bool:
    """检查两点之间是否有指定角度和容许度的相位"""
    diff = _angular_difference(point1["longitude"], point2["longitude"])
    return abs(diff - target_angle) <= orb


def _detect_grand_trine(points: List[Tuple[str, Dict[str, Any]]]) -> List[List[str]]:
    """
    检测大三角：三个点两两120度相位
    容许度：±6°
    """
    grand_trines = []
    n = len(points)

    for i in range(n):
        for j in range(i + 1, n):
            for k in range(j + 1, n):
                name1, p1 = points[i]
                name2, p2 = points[j]
                name3, p3 = points[k]

                # 检查是否两两120度相位
                if (_has_aspect(p1, p2, 120, 7.0) and
                    _has_aspect(p1, p3, 120, 7.0) and
                    _has_aspect(p2, p3, 120, 7.0)):

                    grand_trines.append([
                        p1["name_zh"],
                        p2["name_zh"],
                        p3["name_zh"]
                    ])

    return grand_trines


def _detect_t_square(points: List[Tuple[str, Dict[str, Any]]]) -> List[List[str]]:
    """
    检测T三角：一个对分相 + 两个四分相指向顶点
    容许度：对分相±7°，四分相±7°
    """
    t_squares = []
    n = len(points)

    # 先找出所有对分相
    oppositions = []
    for i in range(n):
        for j in range(i + 1, n):
            name1, p1 = points[i]
            name2, p2 = points[j]
            if _has_aspect(p1, p2, 180, 7.0):
                oppositions.append((i, j))

    # 对每个对分相，找第三个点构成两个四分相
    for i, j in oppositions:
        name1, p1 = points[i]
        name2, p2 = points[j]

        for k in range(n):
            if k == i or k == j:
                continue

            name3, p3 = points[k]

            # 检查是否与两个端点都成四分相
            if (_has_aspect(p1, p3, 90, 7.0) and
                _has_aspect(p2, p3, 90, 7.0)):

                t_squares.append([
                    p3["name_zh"],  # 顶点
                    p1["name_zh"],  # 对分端点1
                    p2["name_zh"]   # 对分端点2
                ])

    return t_squares


def _detect_yod(points: List[Tuple[str, Dict[str, Any]]]) -> List[List[str]]:
    """
    检测Yod（上帝手指/梅花格局）：
    - 两个150°梅花相位共同指向一个顶点
    - 两个基点之间是60°六分相
    容许度：梅花相位±3°，六分相±5°
    """
    yods = []
    n = len(points)

    # 收集所有150度梅花相位
    quincunxes = []
    for i in range(n):
        for j in range(i + 1, n):
            name1, p1 = points[i]
            name2, p2 = points[j]
            if _has_aspect(p1, p2, 150, 3.0):
                quincunxes.append((i, j, p1, p2))

    # 统计每个点被150度相位指向的次数
    vertex_count = {}
    for i, j, p1, p2 in quincunxes:
        vertex_count[i] = vertex_count.get(i, 0) + 1
        vertex_count[j] = vertex_count.get(j, 0) + 1

    # 检查每个顶点是否被至少两个梅花相位指向
    for vertex_idx, count in vertex_count.items():
        if count >= 2:
            # 收集所有指向这个顶点的基点
            bases = []
            for i, j, p1, p2 in quincunxes:
                if i == vertex_idx:
                    bases.append((j, p2))
                if j == vertex_idx:
                    bases.append((i, p1))

            # 检查每对基点之间是否有60度相位
            for (b1_idx, p1), (b2_idx, p2) in _pairwise_combinations(bases):
                if _has_aspect(p1, p2, 60, 5.0):
                    vertex_name = points[vertex_idx][1]["name_zh"]
                    base1_name = p1["name_zh"]
                    base2_name = p2["name_zh"]

                    yods.append([vertex_name, base1_name, base2_name])

    return yods


def _detect_grand_cross(points: List[Tuple[str, Dict[str, Any]]]) -> List[List[str]]:
    """
    检测大十字：四个点两两形成四分相和对分相
    容许度：四分相±7°，对分相±7°
    """
    grand_crosses = []
    n = len(points)

    # 检查所有可能的四个点组合
    for i in range(n):
        for j in range(i + 1, n):
            for k in range(j + 1, n):
                for l in range(k + 1, n):
                    name1, p1 = points[i]
                    name2, p2 = points[j]
                    name3, p3 = points[k]
                    name4, p4 = points[l]

                    # 检查是否形成大十字结构
                    # 需要两对对分相和四个四分相
                    oppositions = []
                    squares = []

                    # 检查所有对分相
                    pairs = [(p1, p2), (p1, p3), (p1, p4),
                            (p2, p3), (p2, p4), (p3, p4)]

                    for pa, pb in pairs:
                        if _has_aspect(pa, pb, 180, 7.0):
                            oppositions.append((pa, pb))
                        if _has_aspect(pa, pb, 90, 7.0):
                            squares.append((pa, pb))

                    # 大十字需要至少两对对分相和四个四分相
                    if len(oppositions) >= 2 and len(squares) >= 4:
                        # 检查是否形成完整的十字结构
                        # 简化：如果找到足够多的相位就认为是潜在的大十字
                        point_names = sorted([p1["name_zh"], p2["name_zh"],
                                             p3["name_zh"], p4["name_zh"]])
                        grand_crosses.append(point_names)

    # 去重
    unique_crosses = []
    seen = set()
    for cross in grand_crosses:
        key = tuple(sorted(cross))
        if key not in seen:
            seen.add(key)
            unique_crosses.append(cross)

    return unique_crosses


def _detect_kite(points: List[Tuple[str, Dict[str, Any]]]) -> List[List[str]]:
    """
    检测大风筝格局：大三角 + 第四个点（筝顶）
    - 筝顶与大三角的两个顶点形成六分相（60°）
    - 筝顶与第三个顶点（筝尾）形成对分相（180°）
    容许度：六分相±5°，对分相±7°
    """
    kites = []
    grand_trines = _detect_grand_trine(points)
    
    for trine_names in grand_trines:
        # 找大三角三个点的实际数据
        trine_pts = []
        for name in trine_names:
            for _, pdata in points:
                if pdata["name_zh"] == name:
                    trine_pts.append(pdata)
                    break
        if len(trine_pts) != 3:
            continue
        
        # 对每个剩余点，尝试作为筝顶
        for _, ptop in points:
            if ptop["name_zh"] in trine_names:
                continue
            
            # 尝试每个大三角顶点作为筝尾（对分相目标）
            for ti in range(3):
                tail = trine_pts[ti]
                wings = [trine_pts[i] for i in range(3) if i != ti]
                
                if (_has_aspect(ptop, tail, 180, 7.0) and
                    _has_aspect(ptop, wings[0], 60, 5.0) and
                    _has_aspect(ptop, wings[1], 60, 5.0)):
                    
                    kites.append([
                        ptop["name_zh"],      # 筝顶
                        wings[0]["name_zh"],  # 筝翼1
                        wings[1]["name_zh"],  # 筝翼2
                        tail["name_zh"]       # 筝尾
                    ])
                    break  # 一个大三角只需一个筝顶
    
    return kites


def _detect_empty_planets(points: List[Tuple[str, Dict[str, Any]]]) -> List[str]:
    """
    检测空相行星：没有任何主要相位的行星
    主要相位：合相(0°)、六分相(60°)、四分相(90°)、三分相(120°)、对分相(180°)
    容许度：合相/对分相/四分相±7°，三分相±6°，六分相±5°
    """
    empty_planets = []
    planet_names = ["太阳", "月亮", "水星", "金星", "火星",
                   "木星", "土星", "天王星", "海王星", "冥王星"]

    for name, point in points:
        if point["name_zh"] not in planet_names:
            continue

        has_aspect = False

        # 检查与所有其他点之间是否有主要相位
        for other_name, other_point in points:
            if other_name == name:
                continue

            # 检查所有主要相位
            for target_angle, orb in [(0, 7.0), (60, 5.0), (90, 7.0),
                                     (120, 6.0), (180, 7.0)]:
                if _has_aspect(point, other_point, target_angle, orb):
                    has_aspect = True
                    break

            if has_aspect:
                break

        if not has_aspect:
            empty_planets.append(point["name_zh"])

    return empty_planets


def _pairwise_combinations(items):
    """生成列表中所有两两组合"""
    from itertools import combinations
    return list(combinations(items, 2))

