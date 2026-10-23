# Relationship observation v0.14

`calculate_relationship_observation` returns observable geometry and linked natal context for two people. It separates one geometric contact from its two directional observation paths. It does not return relationship scores, predictions, psychological diagnoses, attachment classifications, or IFS part assignments.

The observation approach is informed by John Green, *Do You Love Me? The Astrology of Relationships*, and the supplied workshop *It's not them, it's you!*. The graph representation, stopping rules, grouping and display ordering are engineering decisions, not algorithms claimed to have been specified by the author. The source publications are not distributed here.

## Inputs and context

Both people need complete year/month/day/hour/minute and a resolved `location_id`; missing birth time is not guessed. Resolve ambiguous local times with `fold`. The tool currently supports Placidus houses only and returns unavailable if those houses cannot be computed.

Ask for relationship context before calling unless already given. `relationship_type` accepts `love`, `friendship`, `work`, or `family`. The compatibility default `love` does not establish the user's intent. Scenarios select observation angles and topics; they do not discard planets or geometric contacts.

`relationship_context` optionally accepts:

- `additional_types`: other supported contexts;
- `roles`: explicit `a`/`b` pairs of parent/child, sibling/sibling, supervisor/employee or colleague/colleague, consistent with the selected family/work context;
- `cohabiting`: shared-home context;
- `creative_project`: true/false/null for work;
- `early_or_sibling_like_friendship`: true/false/null for friendship.

Roles and experiential statements must come from the caller. Unknown optional conditions remain unknown.

```json
{
  "person_a": {"year":2000,"month":1,"day":1,"hour":12,"minute":0,"location_id":"coord:39.904200,116.407400"},
  "person_b": {"year":1995,"month":5,"day":12,"hour":12,"minute":0,"location_id":"coord:39.904200,116.407400"},
  "relationship_type":"friendship",
  "sextile_orb_degrees":6
}
```

This is a synthetic integration example. The 6-degree sextile value is an explicit example configuration, not an author default.

## Calculation and observation policies

| Input/policy | Behavior |
|---|---|
| `mode=synastry` | Two people; unique contacts, directional paths, overlays and configurations |
| `mode=natal` | One or two people; each natal observation profile, including untouched points; no cross-contacts |
| `orb_profile=john_green` | Conjunction/square/trine/opposition 10 degrees; tight display threshold 5 degrees |
| `sextile_orb_degrees` | Explicit 0–10 degrees; ordinary sextiles not evaluated if omitted |
| `include_minor_aspects` | Requires explicit `minor_orbs_degrees` for supported 30/45/135/150 degree angles; ambiguous overlapping windows rejected |
| `ruler_profile` | Traditional default, modern optional; parallel ruler background does not create direct contact |
| `parental_house_mapping_profile` | `john_green` default or `reversed`; symbolic observation background, not family biography |
| `sort_by` | `orb`, `relationship_indicators`, or `natal_hard_aspects`; display ordering only |
| Natal node convention | Mean lunar nodes, checked against the source ephemeris; legacy upstream field names do not override the verified convention |
| `include_timing` | Optional, requires explicit timing and orb inputs; see [timing reference](relationship-observation-timing.md) |

The old `greene` profile and `calculate_relationship_charts` are unchanged. Composite calculation is not required.

One contact is stored once; `observation_paths` contains two perspectives referencing its ID. Axis endpoints are equivalent representations, not independent evidence. An enabled trine to one end of an axis may appear as a canonical sextile to the other end; this does not silently enable ordinary sextiles.

Ordinary natal context stops at one hop. Separate bounded complexes describe conjunction neighborhoods and named patterns with conjunction satellites. They do not recursively traverse the entire connected graph. Members connected through natal structure are not additional direct cross-contacts, and overlapping complexes must not be summed as independent evidence. Supported patterns include axis/Chiron participation where explicitly evaluated; a Yod requires explicit sextile and quincunx orbs.

Actual houses are retained. A planet in the sixth house within 5 degrees before the seventh cusp receives a separate effective-seventh flag and projection reference; other house cusps have distance data without automatic reassignment. Element/modality counts use Sun through Saturn plus ASC and MC. Outer planets return their actual personal-planet natal connections, without an "unintegrated" diagnosis.

## Output and verification

The main outputs are `source_geometry`, `relationship_profiles`, `contacts`, `observation_paths`, `activation_clusters`, `house_overlays`, `projected_planet_overlays`, `observation_complexes`, `observation_complex_links`, `scenario_observation_lenses`, and `natal_observation_entries`. Other views reuse these facts through IDs or pointers. Layer availability explicitly distinguishes computed, unsupported, unrequested and rule-undefined results.

`completeness=partial` is intentional. Semantic seeking/carrier prominence, lack/abundance cutoffs, qualitative similarity/complementarity matching and interpretation are not inferred. Counters describe structures, not strength, compatibility or independent corroboration. An empty optional layer is not evidence that the corresponding real-life theme is absent.

Successful results expose a `calculation_reference`. Use `verify_calculation_claims` to rebuild and verify selected fields. This checks structured calculation output, not the truth of psychological interpretations or human reports. New rule versions require new references.

`prepare_relationship_observation_note` accepts that reference, the person, an explicitly provided human statement and optional natal-point/question link. It returns a caller-owned, nonpersistent record with `HUMAN_REPORTED`, `statement_verification=not_verified` and `is_calculation_fact=false`. The server does not infer client statements or store consultation notes.
