# 本命结构与琼斯格局：平行观察

2026-10-23。`natal-priorities-v4`。发布状态见[本轮验收](validation/natal-jones-release-2026-10-23.md)。

## 两套系统分别回答问题

本命结构层继续计算定位终端、主要入口、日月与命主、轴点、相位构型、尊贵、宫位与宫主、接纳关系。原有工程提取规则保留，只有此前混入的 `chart_pattern` 入口及其汇聚作用被移除。

琼斯视角单独读取同一底层盘的整体形态及其观察角色，不参与本命单星选择、结构族汇聚或注意力分组。两套视角共享黄经与部分相位，不能将同一个位置或相位当成两份独立证明。

## 输出

| 输出 | 用途 |
|---|---|
| 原 `core_structures`、`priority_planets`、`attention_layers` 等 | 原本命结构视角，已排除琼斯入口 |
| `jones_view.classification` | 上游格局、版本、置信信息、交界与替代候选；未知字段不补成确定 |
| `jones_view.upstream_focus` | 原有单一焦点及识别状态。无焦点时不猜一颗 |
| `jones_view.observation_roles` | 完整格局角色与来源；合相伙伴单独标为关联成员，不冒称同等角色 |
| `jones_view.geometry` | 既有边界／中点／中心等几何信息，不推断人生资源 |
| `jones_view.core_opposition` | 上游实际供应的核心对分及原门槛；另列当前相位档是否包含 |
| `jones_view.direct_contacts` | 观察角色或上游焦点所涉及的当前档真实主要相位，不因此加入原重点相位榜 |
| `view_comparison.rows` | 十星逐项并列其本命角色、琼斯角色、已有直接联系；没有总分、共同名次或自动升级 |

琼斯引擎附带的历史心理描述与建议不进入新增事实层。`description`、`guide` 不被复制。公开角色名称仍标识原引擎角色，不等于已核实所有作者原典规则或效果。

## 允许度与不确定性

默认本命主要相位档仍是6°（含边界）。现有琼斯引擎的 Sellar 补充核心对分选择使用10°和对冲星座要求、固定速度次序；本次没有改写这套格局算法。`upstream_orb_limit` 如实披露该门槛，`current_view` 独立检验实际是否属于当前6°／8°／10°主要相位集。超过6°的上游核心对分不能悄悄进入默认直接相位列表。

格局空白、跨度、聚群与中心距离是形态阈值，不等于相位允许度。格局交界标记及替代候选必须同时展示；旧图谱若没有完整角色或交界资料，返回 `not_supplied` 或缺失字段，不假装为标准形态。

## 兼容与迁移

- 版本：`natal-priorities-v4`、`natal-focus-v4`、`natal-attention-v3`、`natal-priority-policy-v4`、`natal-reading-v3`、`natal-evidence-matrix-v2`。新层独立版本为 `natal-jones-view-v1` 与 `natal-view-comparison-v1`。
- `priority_planets`、入选理由、部分注意力标签可能改变：仅因琼斯角色入选的星会退出原名单，但完整画像及琼斯角色仍在。无需保证前后重点名单完全相同。
- 原 `pattern:jones:focus` 不再出现在本命证据表；`reading_plan.identity_and_local.pattern_evidence_ids` 保留空列表并增加 `parallel_pattern_ref`。
- `availability.chart_pattern_focus` 保留迁移标记 `moved_to_parallel_view`，动态状态改读 `jones_view.upstream_focus`；此迁移标记不参与本命分组。
- `source_graph.jones` 保留原摘要，并新增 `observation_details` 纯事实投影。旧图谱缺少详细角色仍可运行；单一焦点不会被臆造为把手或车头。
- 请求 `include=["jones_view", "view_comparison"]` 可单独拿到这两层；选择性返回如需总契约版本，请同时指定 `schema_version`。跨层来源引用指向完整结果，被排除的层可另行请求，或使用 `verify_calculation_claims` 核验。
- 读取新响应的引用与版本，不能沿用旧数组下标。新字段可由客户端并列展示；本轮未修改网页或小程序。

## 验证要求

删除或替换琼斯结果，不得改变任一原本命输出层。相位、尊贵、定位链及资源关系与修改前逐项比对；只允许入选和其派生阅读标签改变。真实MCP须验证发现、选择性返回、声明核验和篡改拒绝。

记录见[本地验证](validation/natal-jones-parallel-v1.md)。
