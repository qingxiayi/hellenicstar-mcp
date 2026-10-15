# Deployment

The repository provides stdio and anonymous Streamable HTTP. A source release is
not a running public service. Configure the following before exposing HTTP:

| Variable | Purpose |
| --- | --- |
| MCP_PUBLIC_BASE | Public HTTPS origin used in image links |
| MCP_ALLOWED_HOSTS | Comma-separated actual hostnames, including ports if needed |
| MCP_SOURCE_URL | Corresponding source for the version deployed |
| MCP_SUPPORT_URL | Operator's support and data-handling contact page |
| MCP_LOCATION_DB_PATH | Optional offline SQLite database (default data/location.db) |
| MCP_GEO_CACHE_PATH | Writable optional geocoding cache |
| MCP_RATE_LIMIT_DB_PATH | Writable IP counter database |
| MCP_CHART_DIR | Writable chart cache directory |
| MCP_COMPUTE_MAX_ACTIVE | Active calculations per worker; default 2 |
| MCP_COMPUTE_MAX_WAITING | Waiting calculations per worker; default 4 |
| MCP_COMPUTE_WAIT_TIMEOUT_SECONDS | Queue wait timeout; default 15 seconds |
| AMAP_KEY | Optional operator-owned map key; not required for coordinates/offline data |

The concurrency defaults are configuration choices, not a measured capacity claim.
Use one worker until the intended server has been measured. Do not publish a capacity
number based on laptop tests.

Run behind an HTTPS reverse proxy:

```bash
.venv/bin/python -m uvicorn mcp_server:app --host 127.0.0.1 --port 5000 --workers 1
```

Expose `/mcp` and `/mcp/` subpaths. Disable proxy caching for these paths and overwrite
forwarded IP headers. Restrict access through a gateway when needed; the application
has no user accounts or built-in authorization. See SECURITY.md for retention.

A Dockerfile is included for Python 3.12/Linux. Its image build and the GitHub Actions
Linux job must be validated on a Docker/Linux host; the release preparation on macOS
does not prove those environments work. Example (after building an image):

```bash
docker run --rm -p 127.0.0.1:5000:5000 \
  -e MCP_PUBLIC_BASE=https://mcp.example.org \
  -e MCP_ALLOWED_HOSTS=mcp.example.org \
  -e MCP_SOURCE_URL=https://example.org/your-source-release \
  -e MCP_SUPPORT_URL=https://example.org/support \
  hellenicstar-mcp
```

Mount a writable state directory and the optional database as needed; container
recreation otherwise discards local caches. The standard MCP endpoint does not need
an app-specific plugin manifest. Test initialization, tool listing, a coordinate
calculation and an image URL through the actual HTTPS proxy before opening service
access. Inspect resulting image layout with the deployed fonts.

Swiss Ephemeris requires a short filesystem search path. If the installation path
is too long, set `SWEPH_PATH` to a shorter directory containing the checked files.
Do not set a conflicting `SE_EPHE_PATH`, which the upstream library gives priority.
