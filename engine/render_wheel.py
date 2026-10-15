"""
希腊星智小程序 — 本命盘星图渲染（AstroChart 桥接层）
替换旧 astroseek_renderer.py 的 render_menghao_natal()
"""
import json, os, sys, subprocess, tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT = os.path.dirname(_HERE)
_RENDER_JS = os.path.join(_PROJECT, "astrochart_test", "render_chart.js")

# 引擎行星 key → AstroChart 英文名
_PLANET_MAP = {
    "sun": "Sun", "moon": "Moon", "mercury": "Mercury", "venus": "Venus",
    "mars": "Mars", "jupiter": "Jupiter", "saturn": "Saturn",
    "uranus": "Uranus", "neptune": "Neptune", "pluto": "Pluto",
}

def render_menghao_natal(name, year, month, day, hour, minute, city,
                         output_path=None, house_system="placidus", style="classical"):
    """
    生成希腊星智小程序本命盘星图 — 基于 AstroChart SVG 渲染。
    
    Args:
        name: 姓名
        year/month/day/hour/minute: 出生时间
        city: 城市（中文名）
        output_path: 输出 PNG 路径（None 则自动命名）
        house_system: "placidus" 或 "whole_sign"
        style: "classical" | "elegant" | "default"
    """
    # 确保项目根在 path
    if _PROJECT not in sys.path:
        sys.path.insert(0, _PROJECT)
    from engine.natal_chart import calculate_natal_chart
    
    cc = 'TW' if city in ('台北', '桃园') else 'CN'
    r = calculate_natal_chart(year, month, day, hour, minute, city, cc)
    
    # 转 AstroChart JSON
    planets = {}
    for key, info in r['planets'].items():
        en = _PLANET_MAP.get(key, key)
        lon = info['longitude']
        if info.get('is_retrograde', False):
            planets[en] = [round(lon, 2), -0.2]
        else:
            planets[en] = [round(lon, 2)]
    
    # 特殊点
    sp = r['special_points']
    # 福点
    pf = sp.get('part_of_fortune', {})
    if pf:
        planets['Fortune'] = [round(pf['longitude'], 2)]
    # 精神点
    ps = sp.get('part_of_spirit', {})
    if ps:
        planets['Spirit'] = [round(ps['longitude'], 2)]
    # 北交
    nn = sp.get('true_north_lunar_node', {})
    if nn:
        retro = nn.get('retrograde', False)
        planets['NNode'] = [round(nn['longitude'], 2), -0.2] if retro else [round(nn['longitude'], 2)]
    # 南交
    sn = sp.get('true_south_lunar_node', {})
    if sn:
        retro = sn.get('retrograde', False)
        planets['SNode'] = [round(sn['longitude'], 2), -0.2] if retro else [round(sn['longitude'], 2)]
    # 凯龙
    ch = sp.get('chiron', {})
    if ch:
        planets['Chiron'] = [round(ch['longitude'], 2)]
    
    # 宫头
    if house_system == "whole_sign":
        asc = r['axes']['ascendant']['longitude']
        asc_start = int(asc // 30) * 30
        cusps = [(asc_start + i * 30) % 360 for i in range(12)]
    else:
        cusps = [round(c, 2) for c in r['houses']['cusps']]
    
    chart_json = {"planets": planets, "cusps": cusps}
    
    # 写临时 JSON
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(chart_json, f)
        json_path = f.name
    
    # 确定输出路径
    if output_path is None:
        hs = "ws" if house_system == "whole_sign" else "placidus"
        output_path = os.path.join(_PROJECT, f"wheel_{name}_{hs}.png")
    
    # 调 Node.js 渲染
    result = subprocess.run(
        ["node", _RENDER_JS, json_path, output_path, style],
        capture_output=True, text=True, timeout=60,
        cwd=os.path.dirname(_RENDER_JS)
    )
    
    # 清理临时文件
    os.unlink(json_path)
    
    if result.returncode != 0:
        raise RuntimeError(f"AstroChart 渲染失败: {result.stderr}")
    
    print(f"✅ 星图已保存: {output_path}")
    return output_path


# 兼容旧调用
def render_natal_chart_wheel(*args, **kwargs):
    """兼容旧 astroseek_renderer 的调用方式"""
    return render_menghao_natal(*args, **kwargs)
