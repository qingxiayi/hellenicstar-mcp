# 本命算法 v4 与琼斯平行视角发布验收

2026-10-23。独立发布候选从公开仓库当前主分支提取，仅纳入本命算法、测试和说明更新；保留已有HTTP连接、鉴权和其他工具。本轮不包含独立关系观察工具，不修改小程序。

## 发布范围

默认主要相位统一为6°（含边界）；互容与命主星定位承接入口、完整状态、交点接触、分组阅读、尊贵口径对照及本命关系分组一并更新。`natal-priorities-v4` 将琼斯角色从本命重点筛选中移出，用 `jones_view` 与 `view_comparison` 平行展示，无合并评分。46个工具保持不变；本命提取工具的 `orb_view` 默认由8变为6，其他输入保持不变。

## 已完成本地验证

- 独立公开发布候选全量回归：951项通过，无跳过；一个既有上游弃用警告。
- 工作目录全量991项通过包含本轮未发布的其他功能，因此不冒称本公开版本有991项测试。
- 44张盘修改前后15项基础输出保持一致；92张合成盘116组配置的平行视角隔离检查通过。详见[本地记录](natal-jones-parallel-v1.md)。

## 开源、CI与服务器验证

代码版本：[d37f6f8](https://github.com/qingxiayi/hellenicstar-mcp/commit/d37f6f80bff28c0ee55640a5c776451eaf25c2cd)，已推送公开仓库main。本记录随后以仅文档提交补充，不改变部署代码。

- [GitHub Actions](https://github.com/qingxiayi/hellenicstar-mcp/actions/runs/39897364671)：Ubuntu、macOS均成功，各951项通过，无跳过。
- 服务器候选：885项通过、66项跳过。服务器未安装可选 `astrologica`、`stellium` 对照库；跳过不计为通过。这些对照在上述本地及CI完整套件中已执行。
- 93个运行代码、星历及字体文件与公开代码逐个SHA校验一致。
- 公开源码未包含本机数据库、凭据或私有出生资料。示例与审计输入为合成资料。

## 公网验收

在 [HTTPS MCP入口](https://hellenicstar.com/mcp) 完成初始化、工具发现、实际调用和结果核验，见[机器结果](natal-jones-public-2026-10-23.json)。

- 工具数仍为46；46份输入schema逐项对比，唯一变化是本命重点工具 `orb_view` 默认8改为6。
- 普通盘返回full，高纬度盘返回partial；两者均为 `natal-priorities-v4`、6°、完整十星画像及十行平行对照。
- `jones_view`、`view_comparison` 可通过 `include` 单独请求；琼斯证据未混入本命证据表，当前直接相位未超出6°。
- 两个样本的真实格局声明均为supported，故意错误声明均为contradicted，没有unverified。
- 更新前后旧本命接口的行星、四轴、相位、宫头一致；图谱行星、定位、四轴、尊贵及宫位事实一致。重点筛选及默认相位档的预期变化不冒充“所有输出不变”。

## 部署和回退

2026-10-23 12:01:38 CST仅重启 `hellenicstar-mcp`；工作目录为 `natal-jones-d37f6f8`，进程981831。小程序进程仍为1086608，启动时间仍为2026-10-11 01:01:02 CST。

新增覆盖文件 `hellenicstar-mcp.service.d/zzzzzz-natal-jones.conf`，保留既有HTTP连接、鉴权及其他配置；`MCP_SOURCE_URL` 指向部署的公开代码提交。旧 `natal-focus-80179ca` 目录保留。回退时禁用本次覆盖文件、执行daemon-reload并只重启MCP即可恢复旧配置。

功能说明和字段迁移已更新。验证证明软件交付和所列事实一致性，不证明心理解释、资源有效性或原报告隐藏公式。
