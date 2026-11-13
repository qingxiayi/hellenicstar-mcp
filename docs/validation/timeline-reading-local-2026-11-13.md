# Timeline reading v4 — local acceptance

2026-11-13. This candidate is local only. No public service, GitHub release,
Glama listing or Mini Program was updated in this step. The deployed timeline
engine remains v3 according to the preceding release verification.

## Scope

`timeline-synthesis-4` adds the project-defined `timeline-reading-1` projection:
real interval intersections, one-hop natal context, axis-equivalent grouping,
and a background / continuous configuration / exact-contact reading order.
It introduces no new forecasting techniques or psychological theme selection.
See [field rules](../timeline-synthesis.md).

## Reproducible checks

- `bash scripts/verify.sh`: dependency check passed; **1439 tests and 11 subtests
  passed**. One existing Kerykeion `datetime.utcnow()` deprecation warning.
- `tests/test_timeline_reading.py` exercises independent interval membership,
  half-open boundaries, no transitive group inflation, no-exact-hit backgrounds,
  direct natal edges, axis equivalence, repeated passes, house-ruler policies,
  complete raw-source coverage, corrupted output rejection, selective/summary
  views and claim recalculation.
- After the scoped patch was integrated into the original working tree,
  `pytest tests/test_timeline_reading.py tests/test_timeline_synthesis.py
  tests/test_timeline_windows.py -q`: **54 passed**.
- Real MCP stdio initialization, tool discovery, complete and selective
  calculations, and `verify_calculation_claims` passed for two charts over
  2026–2028. Personal birth inputs and outputs remain outside this repository.
  Each chart supported two correct claims and contradicted a deliberately
  false claim that a unique psychological theme had been selected.
- Public comparison fixture: 1990-04-15 18:00, Paris (`gn:2988507`). The result
  has 84 raw events, 84 raw intervals, 84 reading intervals, 70 exact-contact
  groups, 271 pair intersections and 147 concurrent segments. Its raw
  `events`, `aspect_windows`, `progressed_context` and `resonances` match the
  saved v3 result exactly. This comparison proves compatibility for the
  fixture, not all possible birth data.

- Local preview: case/date switching and detail expansion were exercised in
  the browser; 736px and 320px layouts were inspected. The private preview
  and personal calculation files are not tracked by the public repository.

## Limits

The new validation checks rule consistency and references; it does not
independently verify astronomical engines or psychological interpretation.
Natal background uses the existing ten-planet major-aspect list within 6°;
axis natal aspects are unavailable in this view. Three-year-long outer-planet
progression contacts are retained without a prominence score. Their duration
or number does not establish personal importance. Raw legacy resonances are
not axis-deduplicated and must not be added to the new view's counts.

Full and partial payloads retain indices into the complete response. Consumers
must retrieve full referenced arrays before resolving links. New reading
fields increase response size; use selective fields for initial inspection.
