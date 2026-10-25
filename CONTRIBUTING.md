# 参与贡献 / Contributing

欢迎报告问题、提出建议、修正文档、分享用途或提交代码；不会编程也可以参与。
反馈和贡献都是自愿的。使用本项目不需要登记，商用和二次开发须遵守 [AGPL-3.0](LICENSE)，
无需因为商用另行取得本项目作者的批准。本指南不替代或增加许可证的使用限制。

## 选择合适的入口

- [问题反馈](https://github.com/qingxiayi/hellenicstar-mcp/issues/new?template=bug_report.md)：安装失败、调用报错、计算差异或星图问题。
- [建议与需求](https://github.com/qingxiayi/hellenicstar-mcp/issues/new?template=feature_request.md)：说明想解决什么问题，不必提供实现方案。
- [分享用途](https://github.com/qingxiayi/hellenicstar-mcp/issues/new?template=showcase.md)：自愿介绍你的项目，帮助维护者了解实际用途。转载展示需你在模板中明确同意。
- 提交代码：通过 Pull Request（PR）把修改送回本仓库，维护者审核后决定是否合并。

## 报告问题

先搜索已有 [Issues](https://github.com/qingxiayi/hellenicstar-mcp/issues)，同一问题可补充已有讨论。
新问题请填写工具名称、项目版本或提交号、使用环境、复现步骤、实际与预期结果。
计算差异请尽量提供原始依据或对照软件及版本，并核对时区、夏令时、宫制、黄道体系、交点类型和容许度。
规则口径不同不一定是程序错误；不确定的设置直接注明不确定。

Issue、PR、截图和附件均可能公开。请使用虚构或可合法公开的测试案例，不要上传客户出生资料、
私人经历、密钥或完整未脱敏日志。仅删除姓名不能保证出生资料匿名。
安全漏洞或涉及私人数据的问题，请按 [SECURITY.md](SECURITY.md) 联系受影响服务的运营者，勿公开敏感细节。

## 提交代码或文档

1. 小型修复或文档纠错可直接提交 PR。新工具、计算规则或接口的大改动请先开 Issue 讨论范围，避免做完后无法接纳。
2. Fork 本仓库，在独立分支完成修改。一次 PR 尽量解决一个问题。
3. 按下方开发说明准备环境；计算与接口改动需补充相关回归案例，并运行项目要求的验证。
   仅改文档或反馈模板时，检查格式、链接和模板字段即可；说明哪些检查未运行。
4. 向本仓库的 `main` 分支提交 PR，写清问题、改动后的行为、关联 Issue、验证结果及兼容性影响。
5. 维护者会核实复现、计算依据、测试和维护成本，再决定合并、要求修改或暂缓。
   提交建议或 PR 不保证接纳或完成时间，也不会自动修改官方版本。

问题修复发布后，应在相关 Issue/PR 中注明修复版本或提交；贡献记录用于保留署名。
希望在发行说明中采用特定公开署名时，可在 PR 中说明，勿填写私人联系方式。

## 贡献的许可与署名

你保留自己贡献内容的版权。提交贡献即表示你有权按本项目 AGPL-3.0 许可提供相应改动；
本项目不要求将版权转让给维护者。第三方代码、数据和资产须单独注明来源与许可，不能只改标为 AGPL。
原有版权和必要声明应保留，详见 [NOTICE.md](NOTICE.md)。

AGPL 在适用的分发或修改版网络服务情形下规定对应源码义务，但不要求把改动作为 PR 提交给本仓库。
别人使用、自行修改和本项目接纳贡献是不同的事情；没有反馈，并不代表没有人使用。

## English guide

Bug reports, ideas, documentation fixes, use cases and code contributions are welcome; coding is not required.
Use the linked templates above, which include English prompts. Feedback and registration are optional.
Commercial use and modification are permitted under the project's [AGPL-3.0 license](LICENSE), without separate
commercial approval from this project's author. This guide does not replace or add usage restrictions to that license.

Search existing issues first. Include the tool, project version or commit, environment, minimal reproduction,
actual result and expected result. For calculation differences, identify the source or reference software/version
and compare timezone, DST, house system, zodiac, node type and orbs. Mark unknown settings as unknown.
Use synthetic or lawfully public cases. Never post private birth records, personal stories, credentials or unredacted logs;
removing a name alone does not anonymize a birth record. Follow [SECURITY.md](SECURITY.md) for sensitive reports.

For small fixes, open a PR directly. Discuss substantial changes in an issue first, then fork the repository,
work on a separate branch and submit a focused PR to `main`. Describe the problem, resulting behavior,
validation and compatibility impact. Follow the development requirements below for code changes;
documentation-only changes need relevant formatting, link and template checks. Disclose checks not run.
Maintainers review evidence, tests and maintenance cost before accepting changes; acceptance and timing are not guaranteed.
When a fix ships, its issue/PR should identify the release or commit. Contribution history preserves authorship;
you may state a preferred public credit in your PR. Showcases are voluntary and require explicit permission for republication.

You retain copyright in your contributions and must have the right to provide them under this project's AGPL-3.0 license.
No copyright assignment is required. Identify third-party sources and their licenses separately, and retain required notices.
AGPL source-availability duties do not require submitting an upstream PR. Silent use does not imply lack of adoption.

## 开发环境与验证 / Development and validation

Use Python 3.12 and install `requirements-dev.lock` for the complete regression suite,
including the optional Astrologica and Stellium comparisons. Install Node.js,
`rsvg-convert` and Chinese/symbol fonts for render tests. Build the optional GeoNames
database as described in README before running `bash scripts/verify.sh`.

Keep calculation changes separate from transport/presentation changes. Preserve exact
birth-time and DST ambiguity handling. Add regression cases for changed behavior;
do not regenerate snapshots merely to hide an unexplained difference. The initial
standalone release intentionally removes the legacy `bottom_drive` and
`manifest_event` interpretation fields from classical results and rendered Jones
calculation metadata. Other baseline calculation fields remain covered by snapshots.

Never commit birth records, credentials, caches, local databases or generated charts.
Use fictional test inputs or clearly attributed public benchmark cases.

Core regression tests were migrated from the predecessor calculation project at
commit `2bbdf9a55de30d6b1a769c07605045d5bbfea95f`. Flask authentication, membership,
course authorization and predecessor-document-format checks were excluded; rendering
test adapters now target the standalone renderer. MCP transport tests and calculation
tests run together here. A passing schema check is not an independent astronomy proof.
