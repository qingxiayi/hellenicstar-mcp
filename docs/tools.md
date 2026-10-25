# MCP tools

## 按任务选择 / Choose by task

先区分“现在天空是什么”“它与某个人的本命盘有什么关系”和“何时精确成相”：

| 任务 / Task | 数据 / Data | 图片 / Image |
| --- | --- | --- |
| 天空星体位置，不需要本命或当地宫位 / Sky positions only | `get_current_sky` | — |
| 指定时刻、地点的天象盘 / Sky chart with local houses | `calculate_sky_chart` | `render_sky_chart` |
| 一个时刻的行运对本命相位 / Transit-to-natal snapshot | `get_transit_snapshot` | `render_transit_biwheel` |
| 一段时间内精确行运日期 / Exact transit dates over a range | `calculate_transits_to_natal` | — |
| 次限月相周期 / Progressed lunation cycle | `calculate_progressed_lunation` | — |
| 法达与年小限 / Firdaria and annual profections | `calculate_time_lords` | — |
| 黄道释放 / Zodiacal releasing | `calculate_zodiacal_releasing` | — |
| 琼斯分布格局 / Jones distribution | `calculate_classical_factors` includes Jones | `render_jones_pattern` |

`moment` 是带时区的时刻；`as_of` 是 YYYY-MM-DD 参考日期，以上相关工具按 UTC 中午评估。出生年月日时分使用出生地民用时间，不能把行运时刻填进出生字段。天象盘的地点是观察地点，不要求是出生地。精确行运工具的四轴事件只支持合相，不能把空结果解释为没有其他四轴相位。

Render tools calculate and validate their own source; a preceding data call is unnecessary solely to draw the image. Choose data tools when structured fields are needed. Image display requires a client supporting MCP image content. For a broader task, start with `recommend_workflow` and follow `get_agent_protocol`.

本地本命重点接口新增 `planet_condition_assessments`（状态事实与三分3/2/1尊贵计分对照，非重要性排名）；见[计算口径](natal-condition-views.md)。线上工具与字段以实际返回和发布验收记录为准。

- `search_birthplace`
- `resolve_birth_coordinates`
- `calculate_natal_chart`
- `calculate_natal_structure_graph`
- `calculate_natal_salience`
- `render_natal_chart`
- `render_jones_pattern`
- `calculate_classical_factors`
- `calculate_lots`
- `calculate_zodiacal_releasing`
- `calculate_time_lords`
- `calculate_solar_arc`
- `calculate_transits_to_natal`
- `calculate_timeline_synthesis`
- `get_transit_snapshot`
- `calculate_saturn_jupiter_cycles`
- `calculate_house_ingresses`
- `calculate_progressed_lunation`
- `calculate_solar_return`
- `render_solar_return_chart`
- `calculate_lunar_return`
- `render_lunar_return_chart`
- `calculate_secondary_progressions`
- `render_secondary_progressions_chart`
- `calculate_relationship_charts`
- `calculate_relationship_observation`
- `prepare_relationship_observation_note`
- `render_composite_chart`
- `calculate_davison_chart`
- `render_davison_chart`
- `calculate_relocation_chart`
- `render_relocation_chart`
- `get_current_sky`
- `calculate_house_rulers`
- `calculate_zodiacal_releasing_l4`
- `calculate_lifetime_transit_summary`
- `calculate_aspect_windows`
- `calculate_sky_chart`
- `render_sky_chart`
- `render_transit_biwheel`
- `render_solar_arc_biwheel`
- `render_saturn_jupiter_cycles`
- `verify_natal_claims`
- `verify_calculation_claims`
- `scan_planetary_aspects`
- `get_capabilities`
- `get_agent_protocol`
- `recommend_workflow`

## Natal priorities

`calculate_natal_salience` is separate from the graph tool. It defaults to an inclusive 6-degree `orb_view` for all ten planets and five major aspects; 8/10-degree views remain explicit alternatives. It accepts `scope`, `rulership`, `orb_view`, `tight_orb`, `axis_orb`, `include_mc_ruler`, `distribution_points`, `reception_policy`, and `dynamics_days` (1–90, default 30). It returns core structures, main external entries, classified candidates, complete profiles, semantic evidence links and availability. No configurable weights or global importance scores; explicitly labeled dignity-policy totals are returned separately in `planet_condition_assessments`. See [rules and examples](natal-salience.md).

Profiles also disclose day/night/participating triplicity roles without changing the engine's active-sect dignity policy. `resource_review` retains dispositor, mutual-reception, directed dignity, all five major-aspect and shared-configuration counterparts with their full condition/aspect context; these are associations for review, never remedy or efficacy verdicts.

`relationship_views` separates `dependency_review`, `direct_aspect_review`, and `context_review`, preserving `all_associations`, directed routes and both endpoint states. Request `include=["relationship_views"]` to receive this layer on its own; its state references resolve inside the layer. Dependency and direct-aspect lists may overlap and are not ranked. The selected `orb_view` governs direct contacts (default inclusive 6 degrees). See [fields and limitations](natal-relationship-views.md). Remote availability is verified against the actual response in the release record.

Additive `reading_plan`, `evidence_matrix` and `resource_checks` outputs provide a structure-first reading order, linked selection/context evidence, and candidate connections referenced to specific conditions or square/opposition pairs. Maximal configurations expand to contained motifs; no objects are deleted or scored. Candidate coverage can include all ten planets and is not a validated shortlist.

`priority_decisions` v4 indexes all terminal, dispositor, identity, axis, configuration, house and resource-connection roles without an importance tier. `resource_decisions` v3 separates established relationships, counterpart state and topic applicability. Missing classical dignity affects the state dimension only; retrograde, difficult-house links and unrelated hard aspects do not downgrade a relationship. The unreleased v1 tier and global resource-grade fields have been removed. See [the specification and migration](natal-salience.md).


`reception_facts` distinguishes directed dignity relations, sign geometry, and current degree-aspect membership. `resource_review` includes intrinsic conditions plus dispositor, dignity, conjunction, sextile/trine, square/opposition and shared-configuration routes, without efficacy judgments. The unreleased interpretation policy is withdrawn; no psychological hypotheses or action advice are returned.

`aspect_dynamics` reports instantaneous phase and bounded first exact hits, with individual/relative stations and sign changes. Missing ephemeris coverage remains explicit. Four reception policies expose satisfied, failed and unknown checks without deleting structural facts or implying efficacy.

## Parallel Jones perspective (v4)

`calculate_natal_salience` now returns `jones_view` and `view_comparison`. Request both with `include=["jones_view", "view_comparison"]`; add `schema_version` if needed in a selective response. These retain upstream shape roles, uncertainty and actual selected-orb contacts, alongside natal roles. They never promote natal focus, combine scores, or declare independent corroboration. The old `chart_pattern` natal selection family is removed; focal membership may change while complete profiles remain. Upstream core-opposition thresholds are disclosed separately from the default 6-degree contact view. See [contract and migration](natal-jones-parallel-view.md). See the release verification record for deployment status.

关系观察和人工记录参数见 [relationship-observation.md](relationship-observation.md)，时间层见 [relationship-observation-timing.md](relationship-observation-timing.md)。
