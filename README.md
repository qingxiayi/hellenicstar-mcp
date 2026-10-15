# HellenicStar Astrology MCP Server（希腊星智）

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](LICENSE)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)

独立的占星计算与星图渲染 MCP 服务，提供 **42 个工具**，支持 stdio 和
Streamable HTTP。客户端负责交互与解读，服务返回可核对的计算数据和 PNG。
不包含课程、会员、登录、支付或 AI 报告服务，不需要模型 API Key。

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

- 本命盘、普拉西度与整宫制、历史时区和夏令时歧义处理。
- 古典要素、三分主星、福点/精神点、宫主星链、琼斯格局。
- 黄道释放 L1–L4、法达、年小限、太阳弧、次限、次限月相。
- 行运、土木周期、返照盘、关系盘、戴维森盘、重置盘与年度时间线。
- 本命及双轮 PNG、天象、相位窗口、结构化计算事实核对。

完整列表：[docs/tools.md](docs/tools.md)。使用协议：[docs/mcp-agent-protocol.md](docs/mcp-agent-protocol.md)。
核对工具检查提交的计算事实，不独立验证心理解释，也不代表整个报告已经正确。

## 安装

克隆或下载解压本项目，进入 `hellenicstar-mcp`。推荐使用 Python 3.12：

```bash
# 推荐方式（使用 uv 极速安装，能有效避免新版 pip 编译源码包报 EEXIST 错误）：
uv venv
uv pip install -r requirements.lock

# 或传统 pip 方式：
python3.12 -m venv .venv
source .venv/bin/activate  # Windows 为: .venv\Scripts\activate
python -m pip install -r requirements.lock
```

PNG 需要 `rsvg-convert` 和中文/符号字体；琼斯几何计算需要 Node.js。
macOS 安装 `brew install librsvg node`；Ubuntu/Debian 安装
`librsvg2-bin nodejs fonts-noto-cjk fonts-noto-core fonts-noto-extra`。
安装字体后，运行图像测试并检查实际版式。坐标排盘不需要地名库或高德 Key。

## 接入

支持通用 MCP stdio 配置的客户端可添加以下配置，替换两处绝对路径：

```json
{
  "mcpServers": {
    "hellenicstar": {
      "command": "/absolute/path/hellenicstar-mcp/.venv/bin/python",
      "args": ["/absolute/path/hellenicstar-mcp/mcp_server.py"]
    }
  }
}
```

stdio 直接返回图片内容，不提供 HTTP 图片链接；需要支持 MCP 图片内容的客户端才能显示。HTTP 图片链接只有运行对应 HTTP 服务时才可访问。
本地 HTTP：

```bash
.venv/bin/python -m uvicorn mcp_server:app --host 127.0.0.1 --port 5000 --workers 1
```

端点为 `http://127.0.0.1:5000/mcp`。公开部署须设置域名、支持联系和对应源代码地址，
并配置 HTTPS 代理，见 [部署说明](docs/deployment.md) 和 [SECURITY.md](SECURITY.md)。
默认没有用户认证；并发设置是单进程配置，不是已测量的用户容量。

### 云端一键部署（面向 Notion / 移动端 AI 接入）

如果你希望将本 MCP 部署为全天候在线的 Streamable HTTP 服务，以便在 **Notion AI、手机端 Claude 或远程 Agent** 中调用，推荐通过 [Railway](https://railway.app) 或支持 Docker 的云托管平台一键运行：

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/template)

1. 点击上方按钮或在 Railway 中导入本 GitHub 仓库；
2. 平台会自动读取仓库自带的 `Dockerfile` 构建并拉起服务，对外分配专属的 HTTPS 网址；
3. 你的云端 MCP 服务入口即为：`https://你的域名/mcp`；
4. 将该链接填入 Notion 连接器或移动端客户端即可在线使用。

> **重要说明（本地使用 vs 云端自建的成本与边界）**：
> 1. **个人电脑本地运行（完全永久免费）**：推荐将代码克隆到本地（Mac / Windows），通过 stdio 配合 Claude Desktop、Cursor、Codex 本地运行，不产生任何服务器成本、隐私完全留在本地，无使用时长限制。
> 2. **云端托管部署（Notion / 移动端专用）**：若为了手机端或 Notion 远程调用而部署至 Railway、Render 等云平台，各平台通常提供初始免费试用额度；试用期结束或额度耗尽后，若需全天候 24 小时保持在线，需用户自行在所选云平台绑定支付方式维系云主机运行，或选择转为本地运行。
> 3. **安全提醒**：云端公开部署建议在环境变量中配置 `MCP_HTTP_BEARER_TOKEN` 开启 Token 访问鉴权，防止公网被他人滥用消耗你的云端资源，详见 [SECURITY.md](SECURITY.md)。


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

- **问题反馈**：欢迎通过 GitHub [Issues](https://github.com/qingxiayi/hellenicstar-mcp/issues) 提交 Bug 或功能建议。
- **开源支持**：如果这个项目对你的学习或探索有所启发，欢迎在页面右上角为我们点一颗 **⭐️ Star** 支持一下！
