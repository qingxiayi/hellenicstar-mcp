# 按用途查看关系（v1）

`calculate_natal_salience` 新增 `relationship_views`，版本
`natal-relationship-views-v1`。这是既有事实的查看层，不改变占星计算、
重点提取、完整候选、状态判断或接纳规则。发布状态见[本轮验收](validation/natal-jones-release-2026-10-23.md)。

客户端可以请求 `include=["relationship_views"]`，再选
`relationship_views.planets[目标行星]`：

| 字段 | 展示用途 |
|---|---|
| `dependency_review` | 查看定位／尊贵依赖及互容交换。由 `host_of_target ∪ exchange` 组成；两类关系分别标注，不把互容等同于严格接纳。 |
| `direct_aspect_review` | 查看当前档内直接主要相位，包括合、六合、刑、拱、冲；不因为刑冲或对方状态而删除。 |
| `context_review` | 两类清单之外的完整背景，例如仅被目标承接的客星、仅共享构型的对象、未知路线。 |
| `all_associations` / `relations` | 全部既有外部联系及其来源、方向分组、相位与动态事实。 |

两类清单允许重叠，一颗星在每份清单只出现一次。按行星标识稳定排序，
没有强弱排名或票数。原始 `planet_profiles[*].resource_review` 保持不变。
自身定位不是外部关系；自身状态仍在状态表中。空清单不能解释为“无资源”。

`relations[对象].target_state_ref` 与 `counterpart_state_ref` 均指向本层
`states` 表。即使只请求这一层，双方状态仍完整返回，不需要再次请求画像。
状态表保留原画像中除递归 `resource_review` 之外的全部字段，另附
`condition_context`；缺失宫位、未知状态和外行星不适用的古典尊贵保留原标记，
不填成零或正常。`source_refs` 保留指向完整计算结果的来源引用；它们可能指向
被 `include` 排除的其他层，核对时可请求相应层或使用 `verify_calculation_claims`。

每条关系保留原路线的事实与来源，尊贵主客双方的原始方向另列于
`dignity_directions`；直接相位保留度数、容许度及已有动态搜索。
缺少动态时 `phase.status=unknown`、`search.status=not_supplied`。
仅共享构型不产生直接相位，无相位互容不产生相位。

默认沿用 `orb_view=6`（含边界）；既有合法的显式 `8`、`10` 选项继续生效，
新层会披露实际档位。未改默认参数、星历、尊贵阈值或作者规则。
重复路线只在新视图中归并；未知路线进入 `unclassified`，不静默删除。

`efficacy=not_evaluated`。入相不证明必然精确成相或没有第三体阻断，
接纳不自动成为缓解结论。这不是报告作者“药”的算法，也不是专业有效性验证。
本次不增加针对刑冲第三对象的全新筛选政策，既有主题层继续保留。

## 验证

定向测试：`pytest tests/test_natal_relationship_views.py -q`。
合成样本审计：`python scripts/audit_natal_relationship_views.py`（可用
`--output` 指定报告位置）；沿用离线试验的固定种子及 152 张样本。
全量入口：`bash scripts/verify.sh`。
结果见 [本地验收记录](validation/natal-relationship-views-v1.md)。
