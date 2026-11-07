# Jones bowl-axis correction

The Jones engine now exposes `bowl_axis` for Bowl, Bucket, Sling, Fanhandle,
ConjHandle and TwoHandle. The TwoHandle path derived from a See-Saw uses the
occupied main-group arc for the bowl bottom, including when it crosses 0°.

Each handle is evaluated individually for conjunction with the void midpoint
and opposition to the geometric bowl bottom. These are two descriptions of one
axis contact, not independent evidence. Pair conjunction, the ConjHandle group
midpoint and opposition to actual planets near the bowl bottom remain separate.
The result includes matched/unmatched status, deviation and the relevant orb.
The 8° geometric axis tolerance is not a replacement for natal aspect policy.

MCP exposes these facts through:

- `calculate_classical_factors`: `jones_pattern.bowl_axis` and per-role
  `jones_pattern.key_roles[].geometry_marks`.
- `calculate_natal_structure_graph`: `jones.observation_details.geometry.bowl_axis`
  and per-role `geometry_marks`.
- `calculate_natal_salience`: `jones_view.geometry.bowl_axis` and
  `jones_view.observation_roles[].geometry_marks`.

Interpretation text remains excluded from factual MCP projections. Jones data
remains a parallel observation view and does not change natal priority scoring.
Tool names and input schemas are unchanged. Existing consumers can ignore the
additive fields. The shared Jones adapter version is `jones-miniapp-7`.

Local release verification (2026-11-07): 1396 tests and 11 subtests passed, with
one existing upstream datetime deprecation warning. Regression cases cover all
handle families, rotated charts, the inclusive axis boundary, and geometric
contacts that do not imply an actual planetary opposition.
