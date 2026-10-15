# Swiss Ephemeris data

The bundled binary ephemerides originate from Swiss Ephemeris (Astrodienst).
Upstream: https://github.com/aloistr/swisseph and https://www.astro.com/ftp/swisseph/ephe/.
This distribution selects the AGPL option; see `LICENSE.txt` in this directory
and the repository `LICENSE`. Preserve these notices when redistributing.

| File | Bytes | SHA256 |
| --- | ---: | --- |
| sepl_18.se1 | 484061 | ca1393ceab3a44fbc895887cf789c68819ae6a1cbc9b22225872dbe4ccd99a66 |
| semo_18.se1 | 1304771 | 1ca07bd67c24374d77226180c20a4f9996cba013697894810518e7eb582ca4f7 |
| seas_18.se1 | 223002 | 5fd9c2aa1654e37c09a6aeb558076e795409b7dc4bd948ebc0faa7d4a7686b5b |

These bytes were carried over from the predecessor calculation project; the Chiron
file originated in its Kerykeion installation. The hashes above identify the exact
bundled assets, not a claim that a fresh upstream download was compared this run.

On 2026-10-14, with the standalone project's pinned ephemeris path, Saturn at noon
UT on January 1 in 1800, 1900, 2000 and 2399 returned the Swiss-file flag. This
corrects an inherited note claiming the planetary file could not serve 1800.
These samples do not validate every supported date or every body. Startup verifies
the expected file hashes and Sun/Moon/Jupiter/Saturn/Chiron file-mode samples.

After replacing files, update expected hashes in `services/ephemeris_guard.py` and
run `python -m pytest tests/test_ephemeris_guard.py`. `SWEPH_PATH` can override the
location, but the integrity gate still expects the documented assets.
