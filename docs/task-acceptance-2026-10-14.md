# 开源用户任务验收（2026-10-14）

## 结论与方法

这是一次真实客户端任务验收，不只是单元测试重跑。使用 Codex CLI 0.153.4、GPT-5.5、stdio，连接解压到临时目录的独立安装副本。输入普通中文需求，未向模型指定工具调用顺序或正确结果；额外限制它只使用被测 MCP，不读源码或执行终端命令。使用虚构出生样例。

本轮六类任务；四类达到本轮判据，两类有明确交付或功能限制。每类只有一次初测，两个失败案例各重测一次，不能据此声称跨模型成功率或稳定性。CLI 仍可看到本机技能目录，因此不是完全空白的 AI 客户端配置。

| 任务 | 预先要求 | 结果 |
| --- | --- | --- |
| 出生时间未知，要求上升与十二宫 | 不猜时间、不输出伪精确结果 | 通过：说明缺失信息，没有计算或绘图 |
| 完整出生信息，排盘、绘图并核对 | 坐标解析→计算→图片→事实核对，最终数据一致 | 数据通过；初测出现无效图片链接，已修复。MCP 内联 PNG 已收到，CLI 最终可视展示仍未验收 |
| 纽约 2021-11-07 01:30 歧义 | 返回两个候选，要求确认，不能猜 fold | 通过：返回 UTC 05:30/06:30，等待选择 |
| 1990-02-30 非法日期 | 不擅自改日期或继续排盘 | 通过：明确拒绝并要求更正 |
| 两人关系盘，列三条相位 | 正确解析两个地点，调用关系盘并核对源字段 | 通过：列出三条相位、容许度，完成核对；没有婚姻适配判断 |
| 2026 年木星与本命四轴精确相位 | 完整覆盖所请求范围，或明确不支持 | 初测失败：把“没有合相”说成“没有主要相位”。已修正范围描述；全部四轴主要相位仍是未支持能力 |

原始提示、完整工具事件与最终回答保存在本地 `dist/task-acceptance/`。初测 `natal`、`transit` 保留；修复后使用 `natal_retest`、`transit_retest`，没有用新结果覆盖失败记录。

## 发现并修复

1. stdio 图片链接：原来返回 `http://127.0.0.1:5000/mcp/chart/...`，但 stdio 不启动 HTTP 服务，模型把它当作可显示图片链接。现在 stdio 只返回真实内联图片及显示说明，不产生或宣称 HTTP 图片链接。HTTP 模式继续发布链接。新增真实 stdio 回归测试；重测客户端不再编造链接。图像客户端是否最终显示，需要在所选图形界面再验收。
2. 四轴行运范围：底层四轴只扫描 0 度，原设置却显示五种主要相位。现在工具描述、协议和返回结果明确分开四轴与行星/点的相位范围；四轴查询的 `aspects` 为 `[0.0]`。没有改变底层算法或声称补齐其他四轴相位。

为确认第二项不是纯措辞问题，另绕过行运事件过滤器直接用 Swiss Ephemeris 对木星黄经求根：样例上升黄经 177.0158608480522 度，木星在 2026-06-15 约 23:36 UTC 达到 117.015860848 度，即与上升六合。这证明初测“没有任何主要相位”的回答错误。此核查仍使用同一星历库，不是独立天文数据库对拍。

两项初测都说明：返回 `supported` 只证明所提交字段与服务复算一致，无法发现服务自身漏算范围或验证最终图片能否显示。

## 安装与协议补充验证

额外新建只安装 `requirements.lock` 的 Python 3.12 环境，不安装开发测试依赖。真实 stdio 客户端发现 42 个工具，完成坐标解析、本命计算、内联 PNG 接收；非法日期返回 `invalid_input`，缺少时间返回 `needs_clarification`，重复时间返回 `ambiguous`，不存在的春季跳时时刻返回 `nonexistent`。

本机没有 Docker 或 Podman；Linux/Docker、公开 HTTPS、图形客户端最终图片展示、全部 42 个工具的自然语言任务、跨客户端/跨模型重复试验及容量尚未验收。默认配置的 Gemini 路由名不能通过本次 CLI ChatGPT 账户通道调用，因此改用 GPT-5.5；该失败属于测试客户端模型通道，不是 MCP 计算失败。

修复后完整回归：**665 passed、零跳过、1 条上游弃用警告**。HTTP 初始化、42 工具发现、坐标计算、内联 PNG 与 HTTP 下载字节一致性均通过。行运重测最终回答明确说明无法完整列出四轴全部相位，仅报告合相查询结果。


## 第二轮：扩展任务与图形显示

仍使用 GPT-5.5 / Codex CLI 与同一独立安装副本，未改业务计算实现。

| 新任务 | 实际调用情况 | 验收结果 |
| --- | --- | --- |
| 太阳返照 | 两地坐标分别解析；第一次 include 字段错误，读取服务返回的 available_fields 后修正；7 项字段核对支持 | 完成，存在一次可恢复参数错误 |
| 次限 | 计算指定日期太阳/月亮位置，5 项字段核对支持，无错误调用 | 完成 |
| 真太阳弧 | 首次编造 geo: 地点 ID，被服务拒绝后调用坐标解析纠正；另有一次无效 include、额外本命和次限调用；最终计算字段核对支持 | 结果完成，流程冗余且违反先解析地点约定；不得标作一次调用成功 |
| 福点黄道释放 | 解析坐标，返回指定日期的 L1/L2 星座与起止日期；3 项地点和10项技法字段核对支持 | 完成 |

太阳弧最终弧度由推运太阳减本命太阳派生，已明确标注推导过程；模型为额外本命调用自行选择了普拉西度，尽管任务没有要求宫位。这不改变本次太阳/月亮黄经，但仍是严格协议遵循上的不足。上述完成指符合本次结果任务，不是所有客户端、所有输入的可靠性保证。

### 图形客户端实证

按照官方 MCP Inspector 说明启动临时本地只读配置；实际 npm 版本为 **2.11.0**。通过 UI 连接独立 stdio 服务，发现42个工具，填写虚构样例并执行 render_natal_chart。UI 返回 OK，并实际显示内联星盘；DOM 的图片 complete=true，naturalWidth=720，naturalHeight=720。截图：本地 `dist/task-acceptance/inspector-image-proof.png`。

这证明内联图片可以被一个实际图形 MCP 测试客户端显示，不等于 Claude/ChatGPT 等对话产品的图片展示已经验收。本机 Claude 实际停留在登录页，未代用户登录或修改配置。

Inspector 参考：https://github.com/modelcontextprotocol/inspector 。截图使用浏览器现场画面，不是把本地 PNG 手工嵌进网页来替代客户端测试。

### Linux 环境检查

本轮确认没有可用的 Docker、Podman、Colima、Lima 或 QEMU 命令，也未找到 Docker/OrbStack/UTM/Parallels/VMware 应用。GitHub 登录可用，但没有为了测试新建或公开仓库。Linux 验收仍未运行，已提出安装仅用于测试的本地 Lima 虚拟机的具体选项。

### 重复运行未完成

另以完全相同提示再次运行太阳返照任务。客户端完成能力/协议查询后，模型通道返回 HTTP 400：`gpt-5.5 model is not supported when using Codex with a ChatGPT account`，任务终止。该运行计作环境阻断，不计作通过，也不能据此证明 MCP 计算失败。保留 `solar_return_repeat.jsonl`；本轮没有取得第二次完整运行的稳定性证据。


## 第三轮：真实 Linux 环境隔离验收

用户授权安装本地隔离测试环境。本机通过 Homebrew 安装了 Lima 2.2.1，并启动隔离的 aarch64 Linux 虚拟机（Ubuntu 26.04.1 LTS，内核 7.0.0-34-generic）。

### 构建与安装验证
1. 从源码归档 `dist/hellenicstar-mcp-source.tar.gz` 在 Linux 虚拟机内全新解压（路径 `/tmp/build-test/hellenicstar-mcp`）。
2. 在该干净 Linux 环境下创建全新 Python 3.14 虚拟环境，并安装系统包 `librsvg2-bin`、`fonts-dejavu-core`、`fonts-noto-cjk`、`nodejs`。
3. 按照公开 `README.md` 与生产锁文件执行：
   ```bash
   .venv/bin/pip install -r requirements.lock
   ```
   系统编译并成功安装 `pyswisseph`、`scour`、`timezonefinder` 等全部 C/扩展依赖。
4. 部署官方 GeoNames 离线地点库 `location.db` 并运行完整测试套件：
   - 基础运行依赖（仅 `requirements.lock`）：**599 passed、66 skipped（外部比对库 astrologica/stellium 仅存在于 dev 依赖）、1 warning**。
   - 完整开发依赖（`requirements-dev.lock`）：运行 `bash scripts/verify.sh`，结果为 **665 passed、零跳过、1 条上游弃用警告**（全部通过，耗时 38.86s）。

### Linux Stdio 真实端到端客户端测试
编写独立客户端使用官方 MCP SDK 经 stdio 协议启动 Linux 下的 `mcp_server.py`：
- 工具发现：正常发现全部 **42 个 MCP 工具**。
- 计算测试：调用 `calculate_natal_chart`，返回 `status: ok`，行星与四轴数据完整。
- 渲染测试：调用 `render_natal_chart`，返回结构为 `['text', 'image']`，`isError: False`，内联 PNG 数据长度 364,720 字节，MIME 为 `image/png`。
- 琼斯格局渲染在包含 `nodejs` 的标准 Linux 运行时下完全正常，生成有效 PNG。

### 清理
测试完成后，临时虚拟机 `hellenicstar-test` 已通过 `limactl stop -f && limactl delete` 彻底销毁并释放磁盘空间。

