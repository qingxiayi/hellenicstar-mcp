# 宫位制支持

通用排盘支持七种宫位制，使用回归黄道。宫制改变宫头与落宫，不改变同一时刻的地心行星黄经与真实 ASC/MC。等宫制的第十宫宫头不必等于 MC；整宫制第一宫从上升星座的 0° 开始。

| 参数 | 名称 | Swiss Ephemeris 代码 |
|---|---|---|
| `placidus` | 普拉西度 | P |
| `whole_sign` | 整宫制 | W |
| `equal` | 等宫制（上升点为第一宫宫头） | E |
| `koch` | Koch | K |
| `regiomontanus` | Regiomontanus | R |
| `porphyry` | Porphyry | O |
| `campanus` | Campanus | C |

## 工具范围

支持上述七种宫制的数据工具及其对应图片工具：

- `calculate_natal_chart` / `render_natal_chart`
- `calculate_house_rulers`
- `calculate_solar_return` / `render_solar_return_chart`
- `calculate_lunar_return` / `render_lunar_return_chart`
- `calculate_secondary_progressions` / `render_secondary_progressions_chart`
- `calculate_davison_chart` / `render_davison_chart`
- `calculate_relocation_chart` / `render_relocation_chart`
- `calculate_lots`（宫制仅决定落宫）
- `calculate_relationship_charts` / `render_composite_chart`
- `calculate_sky_chart` / `render_sky_chart`
- `calculate_time_lords`（所选宫制仅决定年度主星的本命落宫；年小限固定按整宫星座推进）

`calculate_classical_factors` 的现有综合评分接口仍只接受 `placidus` / `whole_sign`。本命结构图谱、显著性、综合时间线等保留其已有双制方法视图；关系观察与入宫扫描等保留其既定普拉西度口径。这些工具没有因此自动获得七宫制分析能力。主限的计算方法也不跟随这个通用选择改名或改公式。

## 方法与宫制分开

阿拉伯点沿用各条目声明的昼夜公式。派系取实际 ASC 与太阳的地平线几何关系，不根据太阳在所选宫制的宫位编号推定。黄经用未舍入位置计算；选定宫头仅用于落宫。未另外计算普拉西度时，兼容比较字段 `house_placidus` 为 null，不能用其他宫制的宫位冒充。

MCP 年小限采用逐年推进一个星座的传统整宫方法：年度主星由被推进星座的传统守护星决定。`annual_profections.house_system=whole_sign` 与 `method=annual_whole_sign` 明示这个定义；`natal_house_system` 和 `lord_natal_house` 表示所选本命宫制下年度主星的位置。法达周期不随宫制变化。**行为修正：**此前 MCP 选择 Placidus 时会用同序号宫头星座定年度主星；现在统一按整宫星座推进。小程序共享函数的旧双视图保留，MCP 不再选用宫头轮转分支。

关系比较盘使用双方各自的所选宫头做双向落宫，行星间相位不变。组合盘行星及四轴取短弧中点；象限宫制沿用对应宫头逐项取中点，整宫/等宫则从组合上升重新建立整宫/等分宫头，MC 独立保留。原始宫头中点不构成有效顺序或遇到正好对冲时，明确标记不可用，禁止排序伪造。不是以组合 ARMC 或参考地点重建宫位的方法。仅因方法不同不能判定外站结果错误。

[Solar Fire 的组合宫头设置](https://www.esotech.com.au/SFHelp/composite_chart_houses.htm)另提供锚定第一宫、第十宫或自动锚定后切换部分长弧中点的处理。本项目目前未实现这些锚定选项；遇到无效序列会报告不可用，不宣称与其自动修正结果一致。

古典综合接口还包含项目评分、喜乐、三分主星分期及福点宫位投射等规则；本次未把这些规则批量套用到五种新增宫制。尊贵、派系、行星相位不应因换宫制而改变；要扩展综合评分，需要分别验证其方法定义。黄道释放、主限、法达等时间方法也没有“七种宫制算法”的同义关系。

方法来源与实现选择：

- [Chris Brennan：Annual Profections Wheel](https://theastrologypodcast.com/wp-content/uploads/2019/09/Annual-Profections-Wheel.pdf)：按星座逐年推进的依据。
- [Solar Fire 官方计算方法](https://www.esotech.com.au/SFHelp/combined_charts.htm)：区分逐点中点、派生上升与戴维森方法。本站整宫/等宫从中点 ASC 建宫是按所选宫制定出的明确实现约定，不宣称与该软件所有设置一致。
- [Astrodienst：Multi-composite 方法说明](https://www.astro.com/astrology/in_multicomp_e.htm)：分别取 MC、ASC 与宫头中点的方法，与参考地点方法不同。
- [Swiss Ephemeris 官方接口](https://www.astro.com/swisseph/swephprg.htm)：宫头、独立四轴及 ARMC 排宫接口。

本轮验证见 [方法扩展记录](validation/house-method-scopes-2026-11-16.md)。

支持宫制选择的 MCP 工具统一默认 `placidus`，包括阿拉伯点；没有指定时不再先追问。输出的 `house_system_notice` 明示实际宫制及该工具可选范围，并提示可指定其他宫制重算。用户已明确选择时应传入并沿用该选择，不用默认值覆盖。服务器不保存跨调用偏好；由客户端按对话传参。未知或不支持的名称仍明确拒绝，禁止把错误名称当作普拉西度。出生时间、地点、DST 歧义和返照所在地的确认要求不变。

## 计算口径与高纬度

落宫按天体黄经在相邻宫头之间的半开区间判断：恰在宫头上归入由该宫头开始的宫。没有“提前若干度入下一宫”的容许度，也没有根据天体黄纬计算 mundane house position。因此与启用宫头容许度的网站比较时应关闭该选项。

宫位统一调用 `services/house_systems.py` 的注册表、宫头计算与落宫函数；本命位置通过 `services/natal_positions.py` 返回所选宫制的一套结果。绘图和宫主星使用同一个来源。旧双制古典分析保持兼容，但不再是通用位置计算的前置依赖。

普拉西度与 Koch 无法计算的极区时刻会明确返回错误，不静默替换为 Porphyry。其他宫制如在某些高纬度时刻出现退化或逆序宫头，也明确拒绝按黄经区间落宫。等宫制与整宫制不依赖普拉西度成功；地理极点本身不接受排宫。该限制不是宣称所有其他极区宫制在天文学上均无法定义。

Kerykeion 在高纬度内部可能限制其自用宫位的纬度。本项目只取其地心行星位置；输出四轴、宫头、落宫使用原始地理纬度调用 Swiss Ephemeris，不采用其限制后的宫位。

## 验证

[2026-11-16 验证记录](validation/house-systems-2026-11-16/README.md)记录原有行为回归、极区/DST/宫头边界、各工具与绘图，以及专业网站对拍。

来源：[Swiss Ephemeris 官方接口](https://www.astro.com/swisseph/swephprg.htm)。不同网站使用同一星历库的对照能发现设置或接入错误，不构成独立算法或占星解释有效性的证明。

兼容性细节：旧引擎在精确宫头处曾归入前一宫，部分其他模块则归入后一宫。本次统一为由宫头开始的宫，并提升计算缓存版本；普通旧案例结果保持回归兼容，精确边界的归属是有意修正。
