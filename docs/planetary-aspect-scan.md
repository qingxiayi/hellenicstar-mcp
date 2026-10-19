# 通用星历相位扫描：scan_planetary_aspects

独立新增接口，不需要出生资料或地点。沿用 `transit_utils.body_position`：Swiss Ephemeris 文件模式、回归黄道、地心视黄经（FLG_SWIEPH | FLG_SPEED，无 TRUEPOS）。文件缺失或静默降级会报错，不返回伪精确结果。

| 参数 | 说明 |
| --- | --- |
| planet_a / planet_b | 星体名，不区分英文大小写；支持中文主要星体名称 |
| start_date / end_date | YYYY-MM-DD，UTC 日期，包含结束日期全天；1800–2399，每次最多 200 年 |
| aspects | 默认 [0,60,90,120,180]；允许 0–180 任意有限角度，最多 32 项，自动去重并扫描镜像方向 |
| mode | exact 或 orb_window，默认 exact |
| orb_deg | 默认 1°，大于 0、小于 30；exact 模式不用于筛选事件 |
| output_precision | exact_datetime / date / year_summary；底层始终计算精确根 |
| timezone_name | 可选 IANA 时区，例如 Asia/Shanghai；输入边界始终为 UTC 日期 |

支持 Sun、Moon、Mercury、Venus、Mars、Jupiter、Saturn、Uranus、Neptune、Pluto、Chiron、north_node、south_node；额外支持 Ceres、Pallas、Juno、Vesta、Pholus、true_north_node、true_south_node、mean_apogee。普通南北交点使用平均交点，南交点为北交点加 180°。福点、精神点和四轴依赖地点或出生资料，不属于该接口。相同星体和对应南北交点之间恒定角距没有离散 exact，明确拒绝。

精确结果包含星体、相位、UTC 时刻（可选当地时刻）、双方黄经、0–180°最小角距、逆行状态、hit_index 和 cycle_group_id。`applying_or_separating` 在精确时刻为 `exact`，不强行赋予入相或出相。

`date` 用 exact_date_utc / exact_date_local 代替时间戳，不合并同一天不同事件。`year_summary` 按指定当地时区（未指定则 UTC）的年份及相位统计 exact_count，events 为空，event_count 仍是精确命中总数。

orb_window 返回独立 windows 和 exact 结果；窗口可包含零个或多个 exact。进入/离开若超出查询范围，相应值为 null，并设置 start_truncated / end_truncated，clipped_start_utc / clipped_end_utc 只是截断边界。年份摘要模式下窗口仍保留精确边界，不把窗口碰到的年份当成 exact 年份。

## 重复命中与周期定义

相位有两个镜像方向（合冲除外）。对连续展开的相对黄经，同一个有向目标角对应同组；逆行反复穿过该目标角，分别返回并按时间编号。`cycle_group_id` 和 `hit_index` **仅在本次查询内有效**，编号从范围内第一次命中开始；不承诺代表完整历史周期，也不按“一年一次”合并。扫描范围外可能还有同组命中。

## 数值算法与精度

涉及月亮用 3 小时粗网格，其余星体用 12 小时；检查每格中点，并按相对黄经速度的变号定位驻点、分成单调区段。然后对 exact 或 ±orb 水平求根，二分的时间区间停止阈值为 0.05 秒。检测驻点可避免同一粗网格内往返两次穿越被端点同号掩盖；0/360 回绕在局部连续展开，不会误当相位。

0.05 秒是数值求根阈值，**不是历史天文时间误差保证**。算法的漏检控制依赖所支持星体在该细网格上的平滑运动；用更细网格对真实慢、快星体逐项比对，并用构造的双穿越及相切驻点回归测试。星历缓存固定 4096 个时刻，结果内存随真实命中数量增长，月亮跨百年仍可能生成很大的响应，宜使用 year_summary。

## 示例

```json
{"planet_a":"Pluto","planet_b":"Chiron","start_date":"1960-01-01","end_date":"2030-12-31","aspects":[0,60,90,120,180],"mode":"exact","output_precision":"date"}
```

```json
{"planet_a":"Saturn","planet_b":"Uranus","start_date":"2025-01-01","end_date":"2040-12-31","aspects":[0,90,180],"mode":"orb_window","orb_deg":2,"output_precision":"exact_datetime","timezone_name":"Asia/Shanghai"}
```

工具 schema 与 `get_capabilities` 均从注册函数实时生成。该工具纳入服务器输出校验、计算引用和来源字段复核；来源分类为独立计算，不借用本命盘算法登记条目冒充独立认证。
