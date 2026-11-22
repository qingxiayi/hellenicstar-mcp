# Distribution and platform builds

The current GitHub source release is [v0.1.15](https://github.com/qingxiayi/hellenicstar-mcp/releases/tag/v0.1.15) (2026-11-22). It includes the WorkBuddy input schema and solar return validation fixes. See the [compatibility and verification notes](release-status.md#workbuddy-5113).

The previous [v0.1.14 verification](validation/house-systems-release-2026-11-16.md) covers the maintainer HTTPS service and Glama on 2026-11-16.
Awesome MCP Servers PR #16607 is still open; Smithery is not a confirmed
published channel.

## Source release

GitHub releases distribute the source archive, per-file `source-manifest.json`, and
`SHA256SUMS`. Build with `python scripts/build_release.py`. Verify the archive hash
against the manifest and checksum list before extraction. The archive excludes Git
history, credentials, databases and runtime state. Start with [quickstart](quickstart.md).
A source release version is distinct from individual calculation schema versions.

## Glama

The first Glama release, `0.1.0`, was published on 2026-10-24 from
`2a04efba21b3425e16cfd32d5ce350a0faa6b2fc`. The Glama build and MCP startup/discovery
test succeeded. Publishing does not itself establish a completed TDQS grade.
See the [listing](https://glama.ai/mcp/servers/qingxiayi/hellenicstar-mcp) and its admin
TDQS page for current discovery/evaluation status.

[glama-build-spec.json](glama-build-spec.json) records the administrator form values
used by the successful build. Copy `buildSteps`, versions and `cmdArguments` into the
Glama Dockerfile form. Glama adds `mcp-proxy --` itself: do not add that prefix to the
form's command arguments. `pinnedCommit: null` selects the latest synchronized commit;
set it to the desired full commit SHA for a fixed source build. The platform's base
images and package tooling may change, so this is a reproducible configuration,
not a promise of byte-identical container images.

This build uses stdio and has no required credentials. City-name search requires an
optional database not present in the image; coordinate resolution works without it.
The repository Dockerfile serves HTTP and is a separate recipe. `glama.json` records
the existing maintainer; it is not a deployment specification.

## Direct hosted connection

The maintainer's Streamable HTTP endpoint is `https://hellenicstar.com/mcp`.
Clients connecting to this address use the maintainer deployment directly; they do
not depend on Smithery proxy URLs. GitHub source releases and Glama builds remain
separate distribution channels. For local installation, see [quickstart](quickstart.md).

## Smithery — former publishing workflow retired

Checked on 2026-11-16 against Smithery's [official transition notice](https://www.smithery.ai/future).
Smithery shut down connection management on 2026-10-31, including its MCP proxy,
managed identity, accounts/API keys, API, Connect and Toolbox. Its CLI/SDKs are
deprecated. Smithery remains a public, non-proxied directory powered by Arcade;
retained verified entries show direct server URLs.

The former project URL currently displays the transition notice rather than
a HellenicStar listing. The old `/docs/build/publish` guide was unavailable at
the preceding check. No HellenicStar listing or current self-service submission path
was confirmed. Do not follow the former account/CLI publishing instructions or
report this as a queued version update. A retained public directory is not evidence
that this project's listing was accepted. If Smithery provides a new submission
process, verify that process separately before using it.

This platform change does not prevent direct use of the maintainer HTTPS endpoint,
GitHub installation or the published Glama build.
