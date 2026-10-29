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
| MCP_CHART_DIR | Writable directory for publicly linked images (seven-day lifetime) |
| CHART_CACHE_DIR | Optional internal natal PNG cache; default `/var/cache/hellenicstar/charts` |
| CHART_CACHE_MAX_BYTES | Internal PNG content-byte budget; default `536870912` (512 MiB) |
| CHART_CACHE_TTL_SECONDS | Internal PNG lifetime since creation; default `604800` (seven days) |
| MCP_COMPUTE_MAX_ACTIVE | Active calculations per worker; default 2 |
| MCP_COMPUTE_MAX_WAITING | Waiting calculations per worker; default 4 |
| MCP_COMPUTE_WAIT_TIMEOUT_SECONDS | Queue wait timeout; default 15 seconds |
| AMAP_KEY | Optional operator-owned map key; not required for coordinates/offline data |

The concurrency defaults are configuration choices, not a measured capacity claim.
Use one worker until the intended server has been measured. Do not publish a capacity
number based on laptop tests.

The internal natal cache is separate from `MCP_CHART_DIR`. Provision a writable
`CHART_CACHE_DIR` for the service user if disk caching is wanted; an unavailable
cache falls back to rendering. The Dockerfile does not provision the default
internal path. Keep the two directories separate and give all workers sharing an
internal directory the same limits. Restart all workers together when upgrading
the cache implementation so older writers cannot bypass the new admission lock.
Keep this directory under the service account's exclusive control; do not let
other users replace its subdirectories. Linked hash paths and special PNG files
are refused rather than read or written outside the accounted layout.

Internal writes reserve space under a cross-process lock, first removing expired
PNGs and then evicting the oldest writes until the new image fits. Hits do not
extend lifetime. An image larger than the budget is returned without being cached;
cache write failures also leave the rendered response usable. Fixed lock stripes
bound newly created lock files (64 render locks and one maintenance lock).

Expired internal entries are refused on reads. Cleanup runs on the first cache
access per worker, on subsequent accesses at most once per minute, and before
every write; a requested expired entry is removed immediately. Idle or stopped
services do not perform background internal-cache deletion. This differs from the
HTTP public-image cleanup loop. Setting either internal limit to `0` disables
cache reads and writes, leaving existing files for operator removal. Invalid or
negative values use the bounded defaults and log a warning.

The budget covers managed internal PNG content bytes and reserves space before
staging a new file. It is not a filesystem quota: allow headroom for filesystem
metadata, existing legacy lock files, public images, databases and logs. If cleanup
cannot delete enough data, new cache writes are skipped. For a hard storage
boundary, place this directory on an appropriately sized filesystem or quota.

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
