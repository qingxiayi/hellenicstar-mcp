# HellenicStar Astrology MCP Server（希腊星智）

[English](README_en.md) | [中文说明](README.md)

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](LICENSE)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)

独立的占星计算与星图渲染 MCP 服务，提供 **48 个工具**，支持 stdio 和
Streamable HTTP。客户端负责交互与解读，服务返回可核对的计算数据和 PNG。
不包含课程、会员、登录、支付或 AI 报告服务，不需要模型 API Key。

## 两种请求，同一套完整工具

可以用日常语言说明目标，由客户端 AI 确认必要信息；也可以直接指定工具、技法和专业参数。明确请求无需经过流程推荐器，多技法明确都要时分别执行。已确认资料直接复用，不支持的设置会明确说明。

针对具体问题可按需读取相关字段；专业研究仍可请求完整结果，接口默认完整输出不变。较大的关系结果可能受客户端长度限制，不能把计算成功等同于完整接收。调用与读取规则见 [AI 使用协议](docs/mcp-agent-protocol.md)。

## 本命结构图谱：先计算关系，再形成理解

`calculate_natal_structure_graph` 根据准确的出生年月日时和确认后的地点，计算十颗行星之间的结构关系，供后续核对与解读使用。

- **定位链与汇聚**：分别按传统、现代守护规则追踪每颗行星的去向，列出自定位、闭环、汇入集合和直接指入关系。
- **相位网络与构型**：提供 6°、8°、10° 三档筛选，输出连通分量、孤立节点，以及大三角、小三角、楔形、T 三角、风筝、神秘矩形、大十字。
- **其他关系层**：保留互容、古典尊贵与状态、Placidus／整宫宫主关系和 Jones 几何分类。
- **共享来源**：用来源字段与依赖边标明哪些关系重复使用同一底层事实，便于避免把重复关系当作多条独立证据。
- **部分图层可用**：高纬度导致 Placidus 失败时，保留仍能计算的行星关系，并用 `completeness=partial` 和 `layer_availability` 标记未计算的宫位、轴点层。

例如，可以让 MCP 客户端“计算我的本命结构图谱，分别列出传统和现代定位闭环，以及每个闭环有哪些行星汇入；再用原结果字段复核这些关系”。汇聚数量提供结构信息，心理主线需要另行检验。当前输出为结构化数据；此工具不生成可视化图谱图片。

输入示例、完整字段、复核方式与可复现测试见 [本命结构图谱说明](docs/natal-structure-graph.md)。

## 本命重点提取与琼斯平行观察

`calculate_natal_salience` 的 `natal-priorities-v4` 按定位、身份、轴点和相位构型提取重点，保留全部十星画像与来源。默认七星统计、传统守护和统一6°主要相位（含边界）；8°／10°须显式选择，没有统一重要性分数。

- `jones_view` 单独展示琼斯格局、观察角色、交界候选与当前档直接联系；`view_comparison` 并列两套视角，不合并加分。原先仅因琼斯角色入选的星可能退出本命重点名单，画像仍保留。
- `attention_layers` 分开呈现终端／构型组、角色交叉重点、单入口重点和背景；互容候选与命主星的直接定位星入口可追溯，不将同义闭环重复累计。
- `planet_condition_assessments` 对照尊贵与三分主星3／2／1规则，展示宫位、运动、轴点和定位星状态；状态计分不决定重点，也不冒称完整PNA算法。
- `relationship_views` 在单张本命盘内分别列出依赖关系、直接相位和其余背景，附双方状态与来源，不推断关系有效性或“药”。
- 接纳方向、尊贵依据、星座几何与度数相位分别输出；动态层保留有界的入出相、精确点、转向和换座计算，不声称无限期成相或疗效。

琼斯上游核心对分门槛单独披露，不能扩张默认6°相位列表。算法与迁移见[本命重点说明](docs/natal-salience.md)、[琼斯平行视角](docs/natal-jones-parallel-view.md)。当前发布验证见[本轮记录](docs/validation/natal-jones-release-2026-10-23.md)。

## 土木流年大表：从长期周期查到具体日期

围绕“土星、木星何时经过我的四轴、进入哪一宫、是否因逆行再次经过”，提供可查询的事件表和可直接展示的全景图，便于回顾经历、比较不同阶段，并继续查看某段时间的详细行运。

| 工具 | 返回内容 | 时间范围与选项 |
| --- | --- | --- |
| `calculate_saturn_jupiter_cycles` | 土星、木星与本命 ASC、IC、DSC、MC 的精确合轴事件；顺逆行方向与重复经过记录；两颗行运星之间的合相、上刑、冲相、下刑；各自的象限阶段与指定日期的周期位置 | 默认出生至 80 岁；`max_age` 可设为 1–120；`as_of` 指定观察日期 |
| `calculate_house_ingresses` | 土星、木星进入本命普拉西度十二宫的时间表，包含顺行进入、逆行返回、离开时间及停留时长 | 0—84 岁，截止于 85 岁生日前；可按星体及起止日期筛选 |
| `render_saturn_jupiter_cycles` | 1200 × 660 PNG 全景波形图：土木过轴节点、MC / ASC–DSC / IC 参照线、节点文字避让及观察日期对应的年龄指示线 | 默认出生至 80 岁；支持 `max_age`、`as_of` 和姓名标签 |

例如，在提供出生日期、时间和解析后的 `location_id` 后，可以让支持 MCP 的 AI：“先画我的土木流年全景图，再列出未来三年土木过四轴和进宫的日期，注明顺逆行与重复经过。”图表提供的是星体运行与本命几何关系；波形高低不代表人生好坏，过轴或进宫也不自动等于职业、婚姻等现实事件。

## 综合时间线与生涯行运概览

- **多技法综合时间线（`calculate_timeline_synthesis`）**：按出生地日历年查询 1–3 年，汇合法达主运／子运、黄道释放 L1/L2、次限月亮换座及对本命点的硬相位，以及木、土、天、海、冥合本命四轴的事件，并保留时间和来源字段。
- **30 天跨技法分组**：以精确事件为锚点，在其后 30 天窗口内查找同一目标点的事件，同时纳入在这些事件发生时有效的同目标周期；至少涉及两种技法才输出 `resonances`。这是供对照解读的规则分组，不是重大事件的概率、强度或已验证预测。
- **生涯行运概览（`calculate_lifetime_transit_summary`）**：将 0—84 岁的精确行运事件汇总为 12 个章节，按星体、快慢组及四轴／本命点统计次数。章节以七岁为步长，末章覆盖 77—84 岁并截止于 85 岁生日前；次数不等于压力或吉凶评分。
- **具体日期检索（`calculate_transits_to_natal`）**：查询最长三年的木、火、土、天、海、冥行运事件。四轴仅计算合相，本命点使用工具支持的主要相位；不能把四轴无合相结果解释为“四轴没有其他相位”。

完整工具清单见 [docs/tools.md](docs/tools.md)。


## 适用与不适用场景

### 适合谁

本项目是一个**本地优先**的占星计算与星图渲染 MCP 服务，适合：

- **个人开发者**：在本机用 Claude Desktop、Cursor 等 MCP 客户端搭建自己的工作流
- **占星师**：需要结构化、可复核的计算数据，而不是看不到过程的 App 输出
- **研究者**：需要本命、行运、返照、推运、合盘、Davison、迁移盘、时间主星等技法的结构化结果

设计取舍：

- **计算与解读分离**：服务端只返回可核对的计算数据和 PNG，解读交给客户端和使用者
- **输出契约**：每个数据工具都必须显式注册输出契约，没注册的工具无法暴露；校验不通过的结果直接拦下，不会和错误信息一起返回
- **先算后画**：渲染工具先调用对应的计算工具，并要求结果通过校验，然后才出图
- **可核验**：成功结果附带 `calculation_reference`，可以用 `verify_calculation_claims` / `verify_natal_claims` 按原始输入重新计算，逐条核对引用的字段
- **能力自发现**：`get_capabilities` 返回全部工具、输入 schema、版本和算法注册信息
- **不存储数据**：不保存报告、出生资料或快照
- **无需模型 API Key**，不包含课程、会员、登录、支付或 AI 报告服务

### 不适合谁

本项目**不是**：

- 多租户 SaaS 平台或商业云服务后端
- 带账号、订阅、计费的产品系统
- 开箱即可放到公网的匿名 API 服务
- 为水平扩展、分布式限流或大流量场景设计的系统

如果你需要内建认证、OAuth / API Key 管理、租户隔离或分布式配额，本项目默认不提供这些功能。

### 部署边界

- 推荐用法：**stdio**，或只绑定本机（loopback）的 **Streamable HTTP**
- HTTP 服务**默认匿名，没有用户认证**；`MCP_ALLOWED_HOSTS` 默认只允许 localhost / 127.0.0.1
- 如果你自己决定放到网络上，请放在可信的 HTTPS 反向代理或访问网关后面，自行加鉴权，并按 `SECURITY.md` 和部署文档配置域名、支持联系方式和 `MCP_SOURCE_URL`（源码地址）
- 并发闸门是**单进程**的（默认同时计算 2 个、排队 4 个、等待超时 15 秒，可通过环境变量配置），用来保护本机资源，不代表用户容量

### 核验能证明什么，不能证明什么

- 核验只检查你提交的**结构化计算字段**是否和重新计算的结果一致
- 它**不能**验证心理解释、事件预测或整篇解读
- 通过输出契约也**不等于**算法本身一定正确，它保证的是结果结构完整、内部一致

> 设计哲学：服务留在本地，计算保持严谨，输出可以核验，范围说清楚。

---

## Who this MCP is for / Not for

**For:** individual developers, astrologers, and researchers who run a local MCP server alongside Claude Desktop, Cursor, or other MCP clients, and want structured, re-checkable calculation data instead of opaque app output.

**What it does:**
- Returns calculation data and PNG charts; interpretation stays with the client and the user
- Every data tool must register an explicit output contract; results that fail validation are withheld
- Render tools draw only from validated calculation results
- Results carry a `calculation_reference`; `verify_calculation_claims` re-computes from the original input and checks cited fields
- `get_capabilities` exposes tools, input schemas, versions, and the algorithm registry
- Stores no reports, birth data, or snapshots; needs no model API key

**Not for:** multi-tenant SaaS, account/billing systems, public anonymous APIs, or horizontally scaled deployments. No built-in auth, OAuth, tenant isolation, or distributed rate limiting.

**Deployment boundary:** Use stdio or loopback-only HTTP. HTTP is anonymous by default. If you expose it on a network, put it behind your own HTTPS gateway with authentication, and set `MCP_SOURCE_URL`. The compute gate is per-process (2 active / 4 queued / 15 s timeout by default, configurable via env) and protects local resources; it is not a capacity guarantee.

**Verification scope:** Claim verification checks submitted structured fields only. It does not validate interpretations, predictions, or whole reports. Passing an output contract does not prove an algorithm is correct.

## 功能

- **本命结构图谱**：定位链、闭环与汇聚、互容、相位构型、宫主关系、状态与共享依赖，可用原始字段复算核对。

- **通用相位扫描与阿拉伯点**：
  - `scan_planetary_aspects`：跨百年任意星体对、自定义相位角及容许度窗口或年份摘要扫描。
  - `calculate_lots`：希腊化与阿拉伯特殊点（福点、精神点、爱神点、必然点、婚姻点等）按需计算与公式展示。

- 本命盘、普拉西度与整宫制、历史时区和夏令时歧义处理。
- 古典要素、三分主星、福点/精神点、宫主星链、琼斯格局。
- 黄道释放 L1–L4、法达、年小限、太阳弧、次限、次限月相。
- 行运、土木周期、返照盘、关系盘、戴维森盘、重置盘与年度时间线。
- 本命及双轮 PNG、天象、相位窗口、结构化计算事实核对。

完整列表：[docs/tools.md](docs/tools.md)。使用协议：[docs/mcp-agent-protocol.md](docs/mcp-agent-protocol.md)。
核对工具检查提交的计算事实，不独立验证心理解释，也不代表整个报告已经正确。

## 安装、接入和首次验证

先完成依赖安装，再配置客户端，最后用一个示例检查计算、图片和字段核验。
按 [快速开始（中文 / English）](docs/quickstart.md) 操作；首次验证使用坐标，
不需要地名库、高德 Key 或模型 API Key。已持续验证的平台为 macOS 和 Linux / Python 3.12；
Windows 原生安装及其他 Python 版本不属于当前 CI 覆盖范围。

也可以把下面的请求交给具有本机终端和 MCP 配置权限的 AI 助手：

> 帮我安装 https://github.com/qingxiayi/hellenicstar-mcp 。先阅读 docs/quickstart.md，
> 使用 Python 3.12 安装 requirements.lock 及所需系统依赖，运行
> `.venv/bin/python scripts/smoke_install.py`，再按当前客户端支持的方式配置 MCP。
> 分别报告安装、自检、客户端连接及图片显示结果；遇到缺失权限或依赖时说明具体原因。

能否自动配置取决于客户端支持、操作系统及已授予的权限，部分客户端需要手动配置或重启。
stdio 图片需要客户端支持 MCP image 内容；自检成功不代表每个客户端都能显示图片。
本地 HTTP 和公开部署的配置见 [部署说明](docs/deployment.md) 与 [SECURITY.md](SECURITY.md)。

## 地点与时间

- 已知 WGS-84 经纬度：调用 `resolve_birth_coordinates`，将返回的 `location_id` 用于计算。
- 已知地名：安装可选地名库后调用 `search_birthplace`；有同名选项时由用户选择。
- IANA 时区和出生日期共同确定历史 UTC 偏移；夏令时回拨的重复时刻需要确认 `fold`。
- 中国大陆的乌鲁木齐时区按项目规则归一为北京时间；新疆地方时间输入需要先核实口径。
- 可选高德查询由部署者提供自己的 `AMAP_KEY`。无需设置即可使用坐标和离线库。

### 可复现的离线地名库

源码不携带本地业务数据库。公开地名附件仅由 GeoNames 官方数据生成，不混入原项目的
人工补充记录。可自行构建：

```bash
curl --fail --location --retry 3 https://download.geonames.org/export/dump/cities500.zip -o /tmp/cities500.zip
.venv/bin/python scripts/build_location_db.py /tmp/cities500.zip --output data/location.db
```

构建器拒绝覆盖已有数据库；用 `--output` 指定新文件，再通过 `MCP_LOCATION_DB_PATH`
选择它。数据范围是 GeoNames cities500，不保证涵盖每个小村镇；未收录的地点可用坐标模式。
GeoNames 名称、坐标及更新时间可能变化，输入压缩包的 SHA256 会记录在数据库 metadata 中。

维护者生成附件：

```bash
.venv/bin/python scripts/location_db.py pack --source data/location.db --output dist/location.db.gz
```

使用者下载发行包中的压缩库和校验清单后，取清单的 `archive_sha256`：

```bash
.venv/bin/python scripts/location_db.py install /path/to/location.db.gz --sha256 <archive_sha256>
```

安装器检查 SHA256、SQLite 完整性、表结构和 WGS-84 标记，拒绝覆盖已有库。
运行期地理缓存默认为 `data/geocache.db`，与只读地名库分离。

## 验证与贡献

完整套件包含 MCP 契约、快照、实际 stdio/HTTP 会话、星历和算法回归、渲染，以及
Astrologica / Stellium 的指定技术对照。先按上节安装离线地名库，再运行：

```bash
.venv/bin/python -m pip install -r requirements-dev.lock
bash scripts/verify.sh
```

仅安装运行依赖也能执行测试，但会跳过缺少独立对照库的用例。测试通过不等于所有算法
都经过独立外部验证。当前实测平台和验收结果见 [release-status.md](docs/release-status.md)。
GitHub Actions 配有 Python 3.12 的 macOS/Linux 检查；实际执行结果以 CI 为准。

参见 [CONTRIBUTING.md](CONTRIBUTING.md)。开源源代码包可由下列命令生成：

```bash
.venv/bin/python scripts/build_release.py
```

输出 `dist/hellenicstar-mcp-source.tar.gz` 与逐文件哈希清单，不含本地 Git 历史、密钥、
数据库、生成图片和审计工作笔记。首次公开发布应从该干净包建立新仓库历史，
不要推送带有原业务模块的本地初始历史。

## 许可

项目源码采用 GNU AGPL-3.0。星历、字体、可选 GeoNames 数据的来源、许可和转换说明
见 [NOTICE.md](NOTICE.md)。公开服务须提供所部署版本的对应源代码。

已测任务与已知限制：[真实客户端任务验收](docs/task-acceptance-2026-10-14.md)。其中四轴精确行运目前仅支持合相，不覆盖四轴其他主要相位。

## 交流与支持

如果你在安装、使用或占星技法对接过程中有任何疑问，或者希望探讨心理占星与 AI 智能体结合的更多可能性，欢迎与我们交流：

<div align="center">
  <img src="assets/wechat_qrcode.jpg" width="180" alt="微信公众号二维码" />
  <p><b>关注微信公众号，获取最新案例实录与算法更新</b></p>
</div>

欢迎使用、商用和二次开发，请遵守 [AGPL-3.0](LICENSE) 及第三方许可。反馈和贡献都是自愿的，不需要登记才能使用。

- [报告问题](https://github.com/qingxiayi/hellenicstar-mcp/issues/new?template=bug_report.md)：安装、调用、计算或渲染异常；模板会引导你提供复现信息。
- [提出建议](https://github.com/qingxiayi/hellenicstar-mcp/issues/new?template=feature_request.md)：告诉我们想解决什么问题，不需要会写代码。
- [分享用途](https://github.com/qingxiayi/hellenicstar-mcp/issues/new?template=showcase.md)：自愿介绍用 HellenicStar 做了什么；经你明确同意后才在项目文档中展示。
- [贡献代码或文档](CONTRIBUTING.md)：提交 PR，由维护者审核后决定是否合并。贡献者保留版权，贡献沿用项目许可。

Issue 和 PR 是公开的，请勿上传真实客户出生资料、私人经历、密钥或未脱敏日志。
计算差异请说明对照来源与计算设置；使用虚构或可合法公开的测试案例。安全问题见 [SECURITY.md](SECURITY.md)。

- **开源支持**：如果这个项目对你的学习或探索有所启发，欢迎在页面右上角为我们点一颗 **⭐️ Star** 支持一下！


## 关系观察：双方本命结构的连接

新增 `calculate_relationship_observation` 和 `prepare_relationship_observation_note`。从一条跨盘接触分别查看双方的本命结构，保留亲密、友谊、工作与家庭场景；接触只计一次，人工陈述与计算分开。本命使用平均月交点，已发布的本命重点 v4 保持原行为，不输出匹配分数或心理诊断。

[API and boundaries](docs/relationship-observation.md) · [Timing options](docs/relationship-observation-timing.md)

## 发行与平台配置

[正式发行包](https://github.com/qingxiayi/hellenicstar-mcp/releases) · [Glama 构建与渠道说明](docs/distribution.md)
