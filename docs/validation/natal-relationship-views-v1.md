# 按用途查看关系：本地验收（2026-10-23）

本次仅本地实现及验证，未推送、未发布、未部署、未接触生产环境。
原工作区包含已有未提交改动，HEAD `63e1bcf21c4cfd65fe0913ffb622d70d5e2bbac2`
不是本次完整代码版本。测试在从当前工作区复制的独立临时副本执行，使用已有Python 3.12环境；回写前检查原文件指纹未变，只回写本次列明文件。

## 对应代码

完整Python源码指纹：`7872ecfc7f977003dba7cdaaf8c1560a1d7bb90204adcd56d6ba7f2b11db4930`。
[逐文件指纹](natal-relationship-views-v1-fingerprint.json)覆盖根目录、services、scripts和tests中的Python源码。
这些指纹不代表Git提交或部署版本。

## 已通过

- 定向测试：`python -m pytest tests/test_natal_relationship_views.py -q`，12项通过。
  包括方向交换、互容与直接相位分离、6/8/10度边界、未知路线、重复与乱序、
  不按状态删关系、双方完整状态、极地缺宫位以及新输出被篡改时的校验。
- 真正的本地stdio MCP子进程：初始化、工具发现、普通盘和极地盘实际调用，
  `include=["relationship_views"]`单独返回本层，双方状态引用可解析；
  有动态的直接相位返回相位阶段；真实清单声明获supported，错误清单获contradicted。
- 重跑原种子152张合成盘：120张完整、32张部分；1,520份单星视图。
  全部5,887个有向关系保留，两类清单并集4,995个，背景892个；失败0。
  与原离线试验逐项比对分组、清单和背景，并检查重复路线、乱序及无输入变更。
  [机器审计](natal-relationship-views-v1-audit.json)。
- 修改前后5组完整输出SHA256比对：去掉新增`relationship_views`后逐字节规范化JSON一致。
  覆盖默认、显式8/10度、modern/ten以及极地部分数据，不仅比对部分重点字段。
- `UV_CACHE_DIR=<临时目录>/uv-cache PYTHONDONTWRITEBYTECODE=1 bash scripts/verify.sh`：
  65个依赖包一致性检查通过；**981 passed，零失败、零跳过**（68.03秒）。
  一项原有Kerykeion `datetime.utcnow`弃用警告。
  首次启动因默认uv缓存目录不可写停在依赖检查；使用任务临时缓存后完整执行通过，未改全局配置或安装依赖。

## 本次文件范围

新增关系查看模块、定向测试、合成审计脚本及对应说明／验收材料；
在`natal_salience.py`末尾组装新层，在`mcp_validation.py`注册字段，
更新`mcp_server.py`工具说明和`docs/natal-salience.md`。
原研究脚本、原关系生成、状态算法、星历、尊贵及重点提取规则均未修改。

## 限制与未执行

仅是分类、完整性和接口验证，不是有效资源、缓解结果或报告“药”的准确率。
首屏减少约15.2%来自既有合成样本，不是优化目标或人群结论。
未重新处理三张私人家庭盘；未进行远端CI、Linux运行或公网验证；未部署。
默认仍为6度，合法8/10度显式请求保留。新字段为可选查看层；既有客户端需主动显示它。
