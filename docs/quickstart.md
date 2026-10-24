# 快速开始 / Quick start

## 中文

按“安装 → 自检 → 接入 → 客户端验证”执行。macOS / Linux 的持续集成使用 Python 3.12；
Windows 原生安装和其他 Python 版本尚未纳入当前 CI。示例为合成测试资料，不代表真实用户。

### 1. 安装

先安装 Python 3.12、Git，以及系统依赖：

```bash
# macOS（已有 Homebrew）
brew install librsvg node
# Ubuntu / Debian
sudo apt-get update
sudo apt-get install -y build-essential librsvg2-bin nodejs fonts-noto-cjk fonts-noto-core fonts-noto-extra
```

PNG 需要 `rsvg-convert` 和可用的中文/符号字体，Jones 几何计算需要 Node.js。
macOS 若缺少所需字体，需安装字体并检查实际图片。然后克隆源码或解压正式发行包：

```bash
git clone https://github.com/qingxiayi/hellenicstar-mcp.git
cd hellenicstar-mcp
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
```

若使用 uv，可用 `uv venv --python 3.12` 和
`uv pip install --python .venv/bin/python -r requirements.lock` 替代上面两条 Python 命令。
地名库是可选项；本例使用 WGS-84 坐标，无需地名库、高德 Key 或模型 API Key。

### 2. 运行真实 MCP 自检

```bash
.venv/bin/python scripts/smoke_install.py
```

脚本通过 stdio 启动服务器，执行初始化、工具发现、坐标解析、本命计算、字段复核和 PNG 渲染。
原样字段应为 `supported`，刻意错误字段应为 `contradicted`，图片必须有 PNG 文件头。
成功时输出 JSON 检查摘要；失败时返回非零退出码。可指定 `--image /tmp/hellenicstar-smoke.png`
保存图片人工查看；脚本拒绝覆盖已有文件。它不检查特定 AI 客户端的图片显示，也不证明所有算法正确。

### 3. 接入客户端

在支持此格式的客户端中添加以下配置，替换两处绝对路径。配置位置和重启方式以客户端说明为准：

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

### 4. 在客户端验证

让客户端先调用 `get_capabilities`。再用 `resolve_birth_coordinates` 解析
`latitude=48.8566, longitude=2.3522`，把原样返回的 `location_id` 用于
`calculate_natal_chart`：2000-01-01 12:00，当地民用时间，`house_system=placidus`。
用原结果的 `calculation_reference` 向 `verify_calculation_claims` 提交实际字段及值；
也可让客户端调用 `render_natal_chart` 检查图片显示。不要让模型自行编造 location_id 或计算数值。

stdio 直接返回图片内容，没有可公开访问的图片 URL。
常见问题：缺少 `rsvg-convert` 时补系统依赖；地名搜索不可用时使用坐标或安装可选地名库；
自检通过但客户端不可用时检查绝对路径、配置位置、重启和 image 内容支持。
完整开发测试和部署边界见 [贡献说明](../CONTRIBUTING.md)、[部署说明](deployment.md)。

## English

Follow **install → smoke check → connect → verify in your client**. Current CI covers
macOS and Linux with Python 3.12; native Windows and other Python versions are not
covered by that matrix. Examples use synthetic birth data.

1. Install Python 3.12 and Git. On macOS with Homebrew, run `brew install librsvg node`.
   On Ubuntu/Debian, run `sudo apt-get update`, then
   `sudo apt-get install -y build-essential librsvg2-bin nodejs fonts-noto-cjk fonts-noto-core fonts-noto-extra`.
   PNG rendering needs `rsvg-convert` and suitable CJK/symbol fonts; install missing fonts
   and visually inspect rendered output on macOS. Jones geometry needs Node.js.
2. Clone or extract the source release and enter its directory. Run
   `python3.12 -m venv .venv`, then `.venv/bin/python -m pip install -r requirements.lock`.
   With uv, use `uv venv --python 3.12` and
   `uv pip install --python .venv/bin/python -r requirements.lock` instead.
3. Run `.venv/bin/python scripts/smoke_install.py`. It opens a real stdio MCP session,
   resolves coordinates, calculates a synthetic natal chart, verifies copied and deliberately
   wrong field claims, and checks a rendered PNG signature. Success prints JSON; failures exit
   nonzero. Optional `--image /tmp/hellenicstar-smoke.png` saves the image without overwriting
   an existing file. No city database, AMap key or model API key is required.
4. Add the `mcpServers` configuration shown above to a compatible client, replacing both
   absolute paths. Consult that client's configuration and restart instructions.
5. In the client, call `get_capabilities`, then `resolve_birth_coordinates` with
   latitude `48.8566`, longitude `2.3522`. Use its returned `location_id` with
   `calculate_natal_chart` for January 1, 2000 at 12:00 local civil time and `placidus` houses.
   Copy the result's `calculation_reference` and actual field values into
   `verify_calculation_claims`; use `render_natal_chart` to check image display.

A successful smoke check does not validate all algorithms or every client's image UI.
stdio returns inline images, not public image URLs. If city search is unavailable, use
coordinates or install the optional GeoNames database. If only the client fails, check paths,
configuration placement, restart requirements and MCP image support. See
[contributing](../CONTRIBUTING.md) and [deployment](deployment.md) for full checks and HTTP operation.
