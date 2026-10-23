# Relationship observation v0.14 release candidate

2026-10-23. Adds `calculate_relationship_observation` and `prepare_relationship_observation_note` to the published natal v4 baseline, taking discovery from 46 to 48 tools.

Local candidate: 1198 tests passed, no skips, one existing dependency deprecation warning; dependency consistency passed. Existing MCP tool definitions, transport, CORS, authentication and endpoint settings are retained. The shared motif enumerator accepts an optional point set with its original ten-planet default unchanged. Natal mean lunar nodes remain the observation convention; explicit-date timing discloses its different node convention.

The archive contains implementation, documentation and synthetic tests. It excludes private birth data, consultation reports, runtime caches, local databases and source PDFs. Human observation notes are caller-owned and nonpersistent.

This record describes the local candidate only. Server verification, public HTTPS calls and Mini Program isolation will be recorded after the deployment completes; no deployment is claimed here.
