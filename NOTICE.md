# Notice and third-party attributions

Project source is distributed under GNU AGPL-3.0 (see LICENSE). Data and fonts
retain their respective licenses below; this notice does not relicense them.

## Swiss Ephemeris / pyswisseph

Copyright Astrodienst AG. This project selects the AGPL option of Swiss Ephemeris's
AGPL / professional dual-license model. The ephemeris files in `ephe/` are included
under that option. The upstream notice is preserved in `ephe/LICENSE.txt`.
Sources: https://github.com/aloistr/swisseph and https://github.com/astrorigin/pyswisseph.
File hashes and local runtime checks are documented in `ephe/PROVENANCE.md`.

## Kerykeion

Kerykeion is used for planetary chart calculations under its AGPL license.
Source: https://github.com/g-battaglia/kerykeion. Python dependencies are installed
from the lockfiles; their original package licenses remain applicable.

## Optional geographic data

GeoNames: https://www.geonames.org/ — Creative Commons Attribution 4.0,
https://creativecommons.org/licenses/by/4.0/.
Official download: https://download.geonames.org/export/dump/cities500.zip.

`scripts/build_location_db.py` converts that public archive to SQLite, lowercases
search keys, deduplicates names and identifies Chinese aliases. It preserves the
input coordinates and timezone identifiers. The resolver separately applies this
project's documented mainland-China civil-time convention. The input SHA256,
source URL, transformations and record count are stored in the database metadata
and compressed-asset manifest. No private place aliases or predecessor curated
records are merged into the public release asset. The data is provided as-is.

## HellenicStar Astro Symbols font

`assets/fonts/astro-symbols.ttf` is a modified subset derived from STIX Two Math.
The internal family / full / PostScript names have been changed to HellenicStar
Astro Symbols. Glyph outlines have not been changed by this release cleanup.
Copyright 2001–2021 The STIX Fonts Project Authors.
Source: https://github.com/stipub/stixfonts.
The font remains under SIL Open Font License 1.1; the original copyright and full
license are preserved in `assets/fonts/OFL.txt` and embedded font metadata.
The upstream font authors do not endorse this project.
