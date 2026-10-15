# Security and data handling

Do not publish real birth details or credentials in issues. Contact the operator of
the affected deployment through its configured support page for private reports.
The open-source repository does not operate every deployment.

The HTTP service is anonymous by default. Use a trusted HTTPS reverse proxy or an
access gateway when network access must be restricted. Bind the application to
loopback on a host; container ports should also be published to loopback. Configure
`MCP_ALLOWED_HOSTS` for the actual public host. Forwarded client-IP headers must be
overwritten by the proxy, not accepted directly from untrusted clients.

Calculation concurrency and a finite queue are controlled by `MCP_COMPUTE_*` variables.
They apply per worker and are not measured user-capacity guarantees. Keep one worker
until you have measured the intended deployment's CPU and memory requirements.

Chart URLs grant access to anyone holding the link. They expire after seven days.
The HTTP process sweeps expired files every minute and refuses expired reads;
stopped processes cannot delete files until restarted. Do not cache `/mcp/` in the
reverse proxy. The application sets `Cache-Control: no-store`.

The application caches calculation results in memory and does not create user accounts.
IP rate-limit counters and optional geocoding caches are local SQLite files. Platform,
proxy and client logs must be configured by each operator. When serving modified
versions, make the corresponding source available and set `MCP_SOURCE_URL` to it.
