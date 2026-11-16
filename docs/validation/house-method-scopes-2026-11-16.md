# 七宫制的方法范围扩展（2026-11-16）

在基础宫制升级完成后，用户要求其他计算按专业方法规则展开。本轮只更新本地代码，未部署。

## 新接入入口

阿拉伯点、关系比较与组合中点盘（含图）、天象盘（含图）、法达/年小限的本命主星落宫。
合计六个新增入口与前一轮十三个入口共用七宫制注册表。

阿拉伯点使用未舍入的真实 ASC/行星位置，派系不按所选宫位编号猜测。组合盘宫头
方法有单独标识，不把整宫宫头中点的 15° 当作整宫起点，不把独立 MC 强行变成
等宫制第十宫。年小限固定整宫星座推进；所选宫制只影响主星本命落宫，法达周期
不变。其他方法仍保持其明确边界，见 [规则与来源](../house-systems.md)。

没有改动小程序仓库。MCP 精确行运同时已改为返回全部重复接触，共享服务默认
首末折叠保持不变，见 [逆行接触记录](transit-middle-contact-2026-11-16.md)。

## 验证与边界

首轮新增方法及原有相关回归：135 passed。`tests/test_house_method_scopes.py` 覆盖：

- 七宫制下阿拉伯点公式/黄经不变，落宫匹配选定宫头；未计算的 Placidus 比较字段为空。
- 七宫制下法达和年小限主星/周期不变，年度主星本命宫位随所选宫制计算。
- 比较盘相位与组合行星中点不变，双向落宫使用目标盘宫头。
- 整宫组合宫头均在星座 0°；等宫每宫 30°；天象与组合图片实际生成 PNG。
- 极区整宫/等宫的阿拉伯点和时间主星计算不再以 Placidus 成功为前置条件。

这一轮是方法定义和端到端接入验证，不声称已经对所有新增工具做了外站逐字段
数值比较。宫头底层仍使用前轮已保存的 21 张 astro.com 与 6 张 Astrotheme
事实表格；Astrotheme 既有 Placidus 小差异依旧保留，不扩大容差掩盖。

可复现：

```sh
.venv/bin/python -m pytest tests/test_house_method_scopes.py tests/test_house_systems.py tests/test_relationship_charts.py tests/test_mcp_natal.py tests/test_classical_engine.py -q
.venv/bin/python scripts/diagnose_transit_contact_filter.py
bash scripts/verify.sh
```

最终完整验证：**1552 passed，11 subtests passed**，112.99 秒；65 个依赖兼容。
唯一警告是既有 Kerykeion `datetime.utcnow()` 弃用警告。新增数据、绘图、工具发现、
来源声明与旧功能回归均通过本地项目检查；未部署。
