"""Build an offline database from the official GeoNames cities500.zip download.

Standard library only. Input: https://download.geonames.org/export/dump/cities500.zip
The original archive hash is recorded in metadata; no private aliases are merged.
"""
import argparse
import hashlib
import io
import os
from pathlib import Path
import sqlite3
import tempfile
import zipfile

SOURCE_URL = 'https://download.geonames.org/export/dump/cities500.zip'


def build(archive: Path, destination: Path):
    if destination.exists():
        raise ValueError('Destination exists; choose a new output path.')
    archive_hash = hashlib.sha256(archive.read_bytes()).hexdigest()
    version = 'geonames-cities500-' + archive_hash[:16]
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=destination.parent, suffix='.db')
    os.close(fd)
    temporary = Path(name)
    try:
        with sqlite3.connect(temporary) as conn:
            conn.executescript('''
                CREATE TABLE places (
                    location_id TEXT PRIMARY KEY, geoname_id INTEGER,
                    country_code TEXT, admin1 TEXT, lat_wgs84 REAL, lng_wgs84 REAL,
                    tz_iana TEXT, source TEXT, datum TEXT, version TEXT, population INTEGER
                );
                CREATE TABLE place_names (
                    location_id TEXT, name TEXT, name_lower TEXT, lang TEXT, is_preferred INTEGER
                );
                CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
            ''')
            count = 0
            with zipfile.ZipFile(archive) as zipped:
                with zipped.open('cities500.txt') as raw:
                    for line in io.TextIOWrapper(raw, encoding='utf-8'):
                        parts = line.rstrip('\n').split('\t')
                        if len(parts) != 19 or not parts[17]:
                            continue
                        gid, main, ascii_name, aliases = parts[:4]
                        lat, lng = float(parts[4]), float(parts[5])
                        if not -90 <= lat <= 90 or not -180 <= lng <= 180:
                            raise ValueError('Invalid WGS84 coordinates in archive')
                        loc = 'gn:' + str(int(gid))
                        conn.execute('INSERT INTO places VALUES (?,?,?,?,?,?,?,?,?,?,?)', (
                            loc, int(gid), parts[8], parts[10], lat, lng, parts[17],
                            'geonames', 'WGS84', version, int(parts[14] or 0),
                        ))
                        names = dict.fromkeys([main, ascii_name, *aliases.split(',')])
                        for label in names:
                            if not label:
                                continue
                            lang = ('main' if label == main else
                                    'zh' if any('\u4e00' <= ch <= '\u9fff' for ch in label) else 'alias')
                            conn.execute('INSERT INTO place_names VALUES (?,?,?,?,?)',
                                         (loc, label, label.lower(), lang, int(label == main)))
                        count += 1
            if not count:
                raise ValueError('No usable city records in archive')
            conn.executescript('''
                CREATE INDEX idx_names_lower ON place_names(name_lower);
                CREATE INDEX idx_names_locid ON place_names(location_id);
                CREATE INDEX idx_places_country ON places(country_code);
            ''')
            conn.executemany('INSERT INTO meta VALUES (?,?)', {
                'version': version, 'source': 'geonames', 'datum': 'WGS84',
                'source_url': SOURCE_URL, 'source_archive_sha256': archive_hash,
                'license': 'CC-BY-4.0', 'attribution': 'GeoNames, https://www.geonames.org/',
                'transformations': 'SQLite conversion; name deduplication and lowercasing; no private aliases',
                'record_count': str(count),
            }.items())
            conn.commit()
        os.link(temporary, destination)
        return count, archive_hash
    finally:
        temporary.unlink(missing_ok=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('--output', type=Path, default=Path('data/location.db'))
    args = parser.parse_args()
    count, sha = build(args.archive, args.output)
    print(f'Built {count} places; input SHA256 {sha}; output {args.output}')
