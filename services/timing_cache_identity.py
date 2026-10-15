"""Identity only for timing response caches. No astronomical/rule calculations.

Canonicalize JSON without rounding coordinates or dropping fields. Extra inputs
may cause harmless misses; they never select an owner or change calculation rules.
Process-local caches die on restart. This internal namespace is not a claim that
the engine actually used Swiss (CALC-001 has a separate unresolved execution gate).
"""
import hashlib
import json
from importlib import metadata

CACHE_SCHEMA_VERSION = "timing-response-cache-2"
# Internal cache namespace for the unchanged 360-day / Capricorn-27 defaults.
# Bump this if a future approved rule implementation changes; not a public field.
ZR_RULES_VERSION = "zr-lb-once-completion-age100-spiritshift-3"


def _dependency_versions():
    versions = {}
    for name in ("kerykeion", "pyswisseph", "tzdata", "timezonefinder"):
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = "unavailable"
    return versions


DEPENDENCY_VERSIONS = _dependency_versions()


def response_key(owner, calculation, body, *, context=None, options=None, versions=None):
    """owner must come from _require_member, never the request body."""
    payload = dict(schema=CACHE_SCHEMA_VERSION, owner=owner, calculation=calculation,
                   input=body, context=context, options=options, versions=versions,
                   dependencies=DEPENDENCY_VERSIONS)
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
