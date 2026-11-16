# 逆行中间精确接触漏列调查

日期：2026-11-16。初次调查后，用户明确了小程序首末展示与 MCP 全部接触的不同需求。
已按下文修正本地 MCP 路径，未部署线上。

## 修正前已确认的机制

`calculate_transits_to_natal` → `mcp_extended.transit_events_data` →
`transit_lifetime.compute_range_events` → `transit_natal.compute_filtered_events`。
最后一个函数的 `collapse_series` 默认为 `True`。底层先找到全部精确根并分配
`contact_index/contact_total`，再调用 `collapse_contact_rings`，只保留各序列的
首次与末次。中间逆行根会被主动删除，不是星历未算到。

修正前的工具说明承诺精确行运日期，但没有披露首末折叠，也没有开放逐次/首末选择。
返回值仍可能出现 `1/3`、`3/3`，却缺少 `2/3`。只查询中间接触所在窄窗口时，
甚至可能返回零条，因为分组与折叠在扩展时间窗完成后才裁切请求范围。

现有 `tests/test_transit_natal.py` 明确测试并要求这种折叠行为，说明它是既有产品
规则，而非本次宫位升级引入。相应生产源码在本次调查中未修改。

## 可复现证据

运行：`.venv/bin/python scripts/diagnose_transit_contact_filter.py`。

脚本用真实 Swiss 冥王星历，人工构造固定本命点。出生快照由合成数据代入，MCP
服务的区间查询、求根、分组、折叠和结果格式化均运行实际代码。
**这不是袀羽的出生盘，更不证明其真实相位为冲相。**

人为固定凯龙黄经 128.9407559857484°，设计为与 2029-08-14 12:00 UTC 冥王对冲。
完整求根返回：

| UTC | 方向 | 序号 | MCP 默认返回 |
|---|---|---|---|
| 2029-02-14 02:57:58 | 顺行 | 1/3 | 是 |
| 2029-08-14 12:00:00 | 逆行 | 2/3 | 否 |
| 2029-12-23 16:55:20 | 顺行 | 3/3 | 是 |

初次脚本断言了完整根存在、方向为逆行、MCP 输出仅有 1/3 与 3/3。运行通过。
修正后该脚本改为断言 MCP 返回三次、共享服务默认仍只返回首末。
该日期为人工构造条件，不得用作独立核实用户提供日期的证据。

## 本地修正与验证

`compute_range_events` 增加默认 True 的 `collapse_series` 参数，并转发给四轴与普通点
两条计算路径。仅 MCP 的 `transit_events_data` 显式传 False。原小程序默认、终身摘要
与过宫展示不随之改变。MCP 结果新增 `settings.contact_policy=all_exact_contacts`，
工具说明明确包含逆行重复命中。

新增四个实际星历回归案例：四轴合相/本命点对冲 × 全年/只含中间命中的窄窗口。
出生输入用合成快照代替，其余走实际 MCP 服务。修正前四例均失败：全年缺 2/3，
窄窗口返回空；修正后均通过，同时断言共享默认仍返回首末。
相关测试命令：`.venv/bin/python -m pytest tests/test_mcp_transit_scope.py tests/test_transit_natal.py tests/test_transit_lifetime.py -q`，结果 **32 passed**。

与后续宫位方法扩展合并的最终项目检查：**1552 passed，11 subtests passed**。

## 尚未确认

用户原始工具调用、返回结果、本命凯龙未舍入黄经、相位角和查询时间窗尚未提供。
因此还不能证明用户那次请求一定由这条路径导致，也没有核实 2029-08-14 的
具体分钟及外站几分钟差异。没有检查线上部署版本，不能把本地结论冒充线上复现。

本次把 MCP 精确事件明细与小程序首末摘要明确分开，未修改共享默认值。
当前多技术时间线已显式 `collapse_series=False`，但其本命目标范围不同，不能
把它当作包括凯龙的直接替代入口。待原始调用可用后，在实际 MCP 调用边界验证。
