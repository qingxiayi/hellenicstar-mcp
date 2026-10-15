# Contributing

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
