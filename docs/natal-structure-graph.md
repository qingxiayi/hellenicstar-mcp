# 本命结构图谱

`services/natal_structure_graph.py` 将已有本命计算投影为关系图谱。提供 Python 函数和独立 MCP 工具 `calculate_natal_structure_graph`。

```python
from services.natal_structure_graph import calculate_structure_graph

graph = calculate_structure_graph(
    year=2000, month=1, day=1, hour=12, minute=0,
    lat=39.9042, lng=116.4074,
)
```

支持已解析的 `location_id`、坐标或现有地点解析器可解析的城市。时间必须是准确的当地民用时刻；有重复时刻时需要明确 `fold=0/1`。日期时间接受整数，兼容旧调用方的纯数字整数字符串；拒绝浮点数、布尔值与小数文本。坐标必须成对提供，不能推测缺失时区或时刻。

## 输出

- `nodes`：十颗行星的黄经、落座、逆行与可用宫位。
- `dispositor`：传统和现代替代守护各自的有向边、逐星路径、自定位或闭环、汇入集合和直接指入数量。闭环成员集合经过排序，不能把该集合的顺序当作沿环次序；实际方向见 `edges`。
- `aspects`：原引擎托勒密相位列表的 6°、8°、10° 筛选，含邻星数、连通分量、孤立点，以及七类已实现的构型。
- `houses`：Placidus 与整宫制的宫头、宫内星、传统／现代宫主及落宫。
- `conditions`、`receptions`：复用现有古典因素规则，不合成心理重要性分数。
- `jones`：现有 Jones 引擎的结构分类；与定位、相位各层并列保存。
- `facts`、`source_pointer`、`depends_on`：来源字段和派生关系。不同规则的重复调用不自动表示独立证据。
- `source_sha256`：输入数据的复算指纹，不是来源真实性签名。

十行星构型包括大三角、小三角、楔形、T 三角、风筝、神秘矩形和大十字。轴点、交点、凯龙和特殊点不混入此层；旧引擎的扩展构型保存在独立字段。不同容许度会改变构型，不能将默认 8° 视为跨流派统一标准。

## 分层失败

正常结果返回 `status="ok"`。

Placidus 预检失败时，返回 `status="partial"`。定位、相位、尊贵／互容和 Jones 几何仍计算；`house_p/house_w=null`、`axes={}`、两个宫制的列表为空，`layer_availability` 给出明确原因。当前宫位与轴点层均不尝试替代计算，包括整宫层；这表示当前路径未计算该层，并不声称整宫制在高纬度数学上不可计算。没有将其他宫制伪装成 Placidus。

此路径使用同一 Swiss Ephemeris 文件计算十颗行星，并检查每颗行星的实际返回标志，拒绝静默 Moshier 回退。昼夜用真实太阳地平高度是否大于等于零判断，记录在 `source_metadata`。普通路径继续调用现有 `calculator.compute`；其他计算异常不会被隐藏成部分成功。

无效出生输入抛 `ValueError`。夏令时歧义继续抛 `BirthContextError` 并保留候选，调用方应要求选择。直接传入已计算数据时，`build_structure_graph(source)` 会先验证十行星完整性和唯一性、有限黄经、落座一致性、宫位、昼夜标记及相位几何等，矛盾来源抛 `StructureInputError`。

## 本次修复验证（2026-10-21）

将上一轮同一批 1,294 组输入重跑：1,245 组正常完成、36 组高纬度返回明确的部分结果、13 组无效或歧义输入被拒绝，无超时或意外接受。1,245 组正常结果的节点、定位、相位、宫位、尊贵、互容、Jones 和依赖字段逐项对比旧研究函数一致。

三个修复前保存的正常起盘源数据经 JSON 归一化后完全相同；宫头在 Python 中为元组，JSON 中为数组，测试按序列化值比较。

针对性测试覆盖高纬度、无效输入、重复行星、黄经／星座矛盾、宫位零值、未知昼夜、相位伪造、Swiss 文件模式、普通路径与无宫位路径的十行星一致性，以及不可隐藏的上游异常。

```sh
.venv/bin/python -m pytest tests/test_natal_structure_graph.py -q
```

旧本命接口仍依赖完整宫位计算；本次分层返回仅属于新图谱函数。测试不证明心理解释有效性，不提供服务器吞吐量承诺。部署证据另见发布验证记录。

## MCP 调用与核验

先用 `resolve_birth_coordinates` 或 `search_birthplace` 得到已确认的 `location_id`，再调用：

```json
{"year":2000,"month":1,"day":1,"hour":12,"minute":0,"location_id":"coord:39.904200,116.407400"}
```

接口没有 `house_system` 选择参数：同时计算 Placidus 与整宫两层。MCP 返回的 `status=ok` 表示计算请求成功，必须同时查看 `completeness=full|partial`。部分结果保留 `layer_availability`，即使请求摘要或只选择部分字段也不会隐藏缺失层。Python 底层函数仍使用 `status=partial`。

结果经过结构检查后附带 `calculation_reference`，可提交给 `verify_calculation_claims`。例如引用 `/dispositor/traditional/paths/sun/terminal` 的精确值，或 `/completeness`。`source_pointer` 指向起盘源数据中的字段；核验接口的 JSON Pointer 则指向图谱返回值，两者不可混用。`source_sha256` 和引用指纹只用于复算一致性，不是签名。

图谱规则尚未作为独立条目加入算法文献注册表，因此发现接口诚实标记 `provenance_coverage=unregistered`。复用既有星历不等于图谱规则已获独立验证。

可复现的合成样本验证：

```sh
python scripts/verify_natal_structure.py
```

使用随源代码发布的合成输入，覆盖 1,294 组民用出生时刻和 20,000 次独立可达性对照；不包含用户个人出生案例。
