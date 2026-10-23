# 本命行星状态与尊贵口径对照

`calculate_natal_salience` 新增 `planet_condition_assessments`，版本 `natal-condition-views-v1`。发布状态见[本轮验收](validation/natal-jones-release-2026-10-23.md)。默认结构图、定位终端、互容判据和重点筛选不变。

## 计算范围

每颗星均保留三组事实，而不是把状态压成一个重要性分数：

- `placement_and_motion`：两宫制落宫、掌管宫位、角续果、6/8/12宫联系、顺逆、尊贵多标签、原太阳状态与东西出。
- `angularity_and_triplicity`：到真实四轴的最短黄经距离、当前配置内的轴点相位、完整三分主星身份与昼夜次序。
- `relationship_context`：定位星自身的状态及尊贵对照引用、全部当前相位、已有入出相与有界精确时刻搜索、互容与单向接纳。

另列 `solar_distance_test`：由原始黄经判断距日是否至少15度，便于与另一口径对照；它不是实际肉眼可见性或偕日升落算法。原引擎的17度日光下阈值保留，太阳本身明确“不适用”。

外行星保留几何、落宫和顺逆事实，但不伪造古典尊贵分数。缺宫位与轴点时对应项标不可用；未提供动态搜索不等于没有入出相。所有字段通过 `source_refs` 回指原计算事实。

## 两套尊贵计分并列

| 项目 | `active_sect_only`（原规则） | `weighted_triplicity_321`（对照） |
|---|---:|---:|
| 入庙 | +5 | +5 |
| 擢升 | +4 | +4 |
| 当下昼夜主导三分星 | +3 | +3 |
| 另一昼夜三分星 | 0 | +2 |
| 参与三分星 | 0 | +1 |
| 界 | +2 | +2 |
| 外观 | +1 | +1 |
| 失势（detriment） | −5 | −5 |
| 落弱（fall） | −4 | −4 |

每个命中分别列 `contributions`，相加得到 `total`。入庙与擢升可以同时计入。游离按该口径是否具有任何正尊贵判断；没有额外游离扣分，也不把互容加入此分数。未知昼夜时对照总分为 `null`，不能当作零。

对照规则依据2026-10-22查看的[自在占星公开页面](https://zizaiastro.com/tools/chart.html)中尊贵计分函数，三分表、界、外观与星历继续使用本项目已有实现。因此声明的是**计分口径对照**，不是宣称与该网站所有计算完全相同，也不是所有古典流派通用的公式。

`score_delta` 与 `peregrine_changes` 直接标出口径切换的影响。`planet_profiles.condition.essential` 保持原值；下游必须同时显示口径名称，不能把对照分数与旧互容、游离或重点名单混成一次“新默认计算”。

## 与PNA的关系

[Curtis Manwaring关于PNA的说明](https://www.astrology-x-files.com/hellenistic/preliminary-natal-analysis.html)区分行星能力与发挥动力。本层借鉴这种分项检查思路，但没有实现完整PNA九格或十八格，也没有采用第三方的汇总权重。

状态对照是完整的本轮功能；PNA偕日升落事件、完成度判断、综合评分、用药效果和心理解释均不在本轮范围。输出 `pna_replication=false`，`importance_score=null`、`resource_verdict=null`。尊贵分数不会改变 `attention_layers` 或 `core_structures`，更不代表哪颗星是有效资源。

验证见[本地验证记录](validation/natal-condition-views-v1.md)。私人出生资料与结果只保存在本机临时文件，不进入开源测试样本。
