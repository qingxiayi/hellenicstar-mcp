# MCP 宫制默认与告知（2026-11-16）

用户授权规则：支持宫制选择的工具，未指定时默认普拉西度，结果明确告知；可以提示
或询问其他偏好，但不阻塞本次出数据。已有明确选择应沿用。固定技法规则单独说明。

实现：

- MCP 所有 `house_system` 参数的 schema 默认值统一为 `placidus`，包括此前默认整宫的阿拉伯点。
- 缺参检查不再要求先提供宫制。参数归一化将可接受的空值转为普拉西度，计算引用保存实际使用值。
- 用户明确传入受支持宫制时不覆盖；不支持的参数仍报错，不能静默默认。
- 成功的数据和图片响应增加 `house_system_notice`：实际名称、默认规则、本工具可选项和重算提示。
- 字段筛选及摘要仍保留告知；MCP 全局指引、工具说明、Agent Protocol 与推荐流程同步更新。
- 年小限另外注明固定整宫星座推进，所选宫制仅用于主星本命落宫；服务不保存跨调用用户偏好。

本次不是向所有时间技术开放七宫制；原有方法范围参见 [宫制说明](../house-systems.md)。
没有改变出生时间、地点、DST fold、返照所在地等必要确认，也没有部署线上。

相关验证 155 passed：省略/空值、显式选择、摘要保留、引用复算、实际 HTTP MCP 调用、
图片与来源一致、阿拉伯点默认值、年小限方法说明、其他缺参及无效宫制拒绝。

```sh
.venv/bin/python -m pytest tests/test_mcp_house_default.py tests/test_mcp_guardrails.py tests/test_house_systems.py tests/test_mcp_discovery_protocol.py tests/test_mcp_workflow.py -q
bash scripts/verify.sh
```

全量回归曾发现提示字段被计入计算指纹，已将 `house_system_notice` 作为说明元数据排除，
并验证该字段不能冒充可核对的计算事实。相关复验 13 passed。
最终完整检查：**1559 passed，11 subtests passed**，110.77 秒；65 个依赖兼容，
仅有既有 Kerykeion 弃用警告。未上传或部署。
