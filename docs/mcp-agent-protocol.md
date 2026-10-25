# 希腊星智 MCP Agent Protocol

## 用途与边界

本服务提供西洋占星排盘与技法数据。计算结果是盘面和传统技法的结构化数据，不是事件预测、心理诊断或对整篇解读的验证。仅将用户实际提供的出生资料用于计算，不补猜城市、出生时刻、分钟、夏令时 fold、宫制或太阳返照所在地。

## 发现与选用工具

先调用 `get_capabilities` 读取当前工具、参数结构及已登记算法。它来自运行中的工具注册表；不要依据旧工具名单臆测现有能力。根据用户目标选择最小必要工具：地点先用 `search_birthplace`，经纬度用 `resolve_birth_coordinates`；本命盘用 `calculate_natal_chart`；古典要素、黄道释放、法达、行运、太阳弧、返照、关系盘和天象各用其对应工具。只有用户需要看图时调用 `render_*` 工具。

不确定该走哪条已支持的计算路径时，可调用 `recommend_workflow(goal=用户的需求)`。它只提供现有工具的调用顺序和所需资料，不做计算，也不替用户选缺失的出生时间或地点。返回 `needs_clarification` 时，根据 `question` 澄清；若用户已明确需要全部候选内容，分别为每个目标取得流程，不再强迫只选一个，也不要丢弃其中任何一项。

推荐结果的 `status=ok` 只表示路径已确定。`input_readiness=not_checked` 表示推荐器没有检查用户资料；调用方须结合对话核对 `required_information`，只追问缺失或含糊的必需项，已有确认资料直接复用。用户回答后继续原目标，不必从头重复询问。`output_mode=image_only` 时可直接调用流程中的绘图工具，其内部计算并校验来源；仅数据请求不需要绘图工具。该推荐器不保存对话、不直接向用户发送问题，也不能保证客户端 AI 遵循指引；计算工具的参数检查仍然生效。

出生地搜索出现多个候选时请用户选择。工具返回 `needs_clarification`、`required_fields` 或 DST fold 候选时，要求用户补齐并重新调用。不要把失败或 `validation_failed` 响应当作正常计算结果。

数据工具可选传 `detail_level="summary"`，让对象行列表最多显示前 5 项；行星 ID、结构成员等标量列表保留完整，避免把成员名单误当成预览；`include` 可传顶层内容字段名列表，例如本命盘的 `["planets", "aspects"]`。省略两个参数时返回原有完整结果。结果的 `presentation.is_truncated` 标明是否发生截断，`presentation.omitted_array_items` 标明各数组省略项数；需要全部条目时用 `detail_level="full"` 重新调用。`include` 不影响计算，服务端仍对完整结果做检查；`calculation_reference` 与本命 `fact_reference` 始终指向完整结果。引用已显示字段时仍按原结果路径核验，不要把摘要当成完整数据集。

## 版本、算法出处与不确定性

成功结果的 `calculation_envelope` 给出协议、引擎、数据 schema、插件和子模块版本，并列出当前注册表已审计的算法依赖。`registered_algorithms` 只是已登记子集：相位、返照、行运、绘图等实现尚未全部登记。`execution_path: UNKNOWN` 表示未记录本次缓存和兜底分支；不能把静态依赖说成逐次运行轨迹。算法项的 `precision` 或 `version_history` 为 `UNKNOWN` 时，保持未知，不推造精度或算法版本。

`calculation_reference` 和本命的 `fact_reference` 用于结果复算及字段核验；其 fingerprint 不是签名，也不证明算法独立正确。新引用使用 `calculation-reference-v2`：数值 `3` 与 `3.0`、`0` 与 `-0.0` 在指纹和字段比较中等价，不舍入其他数值，也不把布尔值或字符串当作数字。未改动的 v1 引用仍按旧指纹规则核验；经过数值表示转换而失配的旧引用需重新计算取得 v2。

Envelope 是元数据，不能当成占星事实提交核验。

## 引用计算事实

解释本命盘之前，把草稿中引用的星座、宫位、逆行和相位事实与原样 `fact_reference` 一起提交给 `verify_natal_claims`。其他数据工具的事实，用原样 `calculation_reference`、准确的 JSON Pointer 路径和原值提交给 `verify_calculation_claims`。冲突项依据证据修正后重新核验；未核实的事实明确标出。两种核验只覆盖已提交的结构化字段，不检查引文语义、遗漏内容、心理解释或整篇报告。

## 表达

注明盘面所用的时刻、地点、宫制与技法口径。时间主星和行运返回的是传统技法的周期与相位表，不把它们写成必然发生的事件。心理占星解释与可核对的计算事实分开表达。心理解释遵循 Anti-Barnum 纪律：不使用放之四海皆准的模棱两可套话或空洞大词；所有心理推论必须强锚定于已核验的具体盘面配置，并给出具体的现实情境机制、两难张力以及可供当事人检验反思的条件边界，不作宿命判断或医学诊断。

## 行运四轴范围

`calculate_transits_to_natal` 对四轴只计算合相（0度）。`target_scope=axes` 的空结果仅代表没有四轴合相；不能推断没有六合、刑、拱或冲。用户要求四轴全部主要相位时，明确说明本工具不能完整完成，不能将合相查询冒充全相位查询。


## 本命结构图谱

需要定位链、闭环、汇聚、构型或共享依赖时调用 `calculate_natal_structure_graph`。检查 `completeness` 和 `layer_availability`；`status=ok` 不等于宫位层完整。结构中心性不直接等于心理核心。用原样 `calculation_reference` 核验所引用的图谱字段。
