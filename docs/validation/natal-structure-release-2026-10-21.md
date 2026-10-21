# 本命结构图谱发布验证（2026-10-21）

计算代码提交：`78ab9b162c12ba0a441f1808396e8fc49d8ddeec`。独立 MCP 增加 `calculate_natal_structure_graph`，公开仓库工具数从 44 增至 45。原线上服务为 43 个工具，本次也同步了公开仓库已有的 `calculate_lots`。

## 计算与接口验证

- 从公开仓库基线建立独立目录，只加入本次图谱实现、接口、契约、测试及说明。
- GitHub Actions：该计算提交的 [macOS 与 Ubuntu 两个作业均通过](https://github.com/qingxiayi/hellenicstar-mcp/actions/runs/39559621384)，包含依赖安装、离线地点库构建、全套验证及源码打包。
- 本机 Python 3.12 全量回归：767 passed，零跳过；一个 Kerykeion 弃用警告。
- 服务器 Python 3.10.12 全量回归：701 passed，66 skipped。跳过项是缺少 astrologica／stellium 的第三方对照；这些项目在本机套件中通过。跳过不计为服务器通过。
- 合成出生输入 1,294 组：1,245 完整图谱、36 部分图谱、13 次预期拒绝，零失败；另有 20,000 次独立可达性／终端汇入集合对照。
- 真实 stdio 测试覆盖工具发现、完整／部分图谱、事实复核、缺失参数、小数小时、无效日期和夏令时歧义。
- 服务器备用 HTTP 端口：初始化、发现 45 工具、图谱完整／部分返回、正确／错误／不可用字段核验、原本命接口、阿拉伯点、相位扫描与 PNG 下载均通过。PNG 下载字节与 MCP 内嵌图片一致，Cache-Control 为 no-store。

## 公网 HTTPS 验收

`https://hellenicstar.com/mcp` 经外部 MCP 客户端完成初始化与 45 工具发现，完整图谱和高纬度部分图谱计算及复核全部通过。正确字段返回 supported，伪造字段返回 contradicted，未计算的宫位字段返回 unverified。原本命接口、阿拉伯点与相位扫描返回经过检查的数据；PNG 下载与内嵌图像的 270,959 字节完全一致。缺参和无效日期仍返回可恢复的输入状态。

详见 [公网验收摘要](natal-structure-public-smoke.json)。最终服务 active、NRestarts=0；备用服务测试结束后已停止。

## 发布方式

部署至独立目录 `natal-structure-78ab9b1`，使用独立运行依赖副本及地点库副本；通过独立 systemd override 切换 `hellenicstar-mcp`，保留前版目录与旧图像缓存路径以便回退。小程序进程 PID 及启动时间前后相同。公开样本为合成数据；新增文件未包含本次用户出生案例。

## 证据与边界

复现批量验证可运行 `python scripts/verify_natal_structure.py`，全套测试运行 `bash scripts/verify.sh`。图谱规则的来源注册状态仍为 unregistered，计算结构核验不等于文献独立证明，也不核验心理解释。此次没有测定并发容量，没有验证 Docker 或所有客户端的图形显示。
