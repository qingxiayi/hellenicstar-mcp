# Distribution and platform builds

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

## Smithery

A configuration file or GitHub link alone does not establish a published Smithery
entry. The current [publishing guide](https://smithery.ai/docs/build/publish) supports
an existing public HTTPS Streamable HTTP service or a prebuilt local MCPB bundle.
Record the actual listing and scan result after publication. A directory entry,
a successful scan, and a real calculation call are separate checks.
