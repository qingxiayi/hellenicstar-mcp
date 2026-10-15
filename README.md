# HellenicStar Astrology MCP Server（希腊星智）

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](LICENSE)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)

独立的占星计算与星图渲染 MCP 服务，提供 **42 个工具**，支持 stdio 和
Streamable HTTP。客户端负责交互与解读，服务返回可核对的计算数据和 PNG。
不包含课程、会员、登录、支付或 AI 报告服务，不需要模型 API Key。

## 功能

- 本命盘、普拉西度与整宫制、历史时区和夏令时歧义处理。
- 古典要素、三分主星、福点/精神点、宫主星链、琼斯格局。
- 黄道释放 L1–L4、法达、年小限、太阳弧、次限、次限月相。
- 行运、土木周期、返照盘、关系盘、戴维森盘、重置盘与年度时间线。
- 本命及双轮 PNG、天象、相位窗口、结构化计算事实核对。

完整列表：[docs/tools.md](docs/tools.md)。使用协议：[docs/mcp-agent-protocol.md](docs/mcp-agent-protocol.md)。
核对工具检查提交的计算事实，不独立验证心理解释，也不代表整个报告已经正确。

## 安装

下载并解压源码发行包，进入 `hellenicstar-mcp`。使用 Python 3.12：

```bash
python3.12 -m venv .venv
source .venv/bin/activate
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
