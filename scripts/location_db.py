"""Package or install the optional location database (Python standard library only)."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def validate(path):
    conn = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)
    try:
        if conn.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
            raise ValueError('Database integrity check failed')
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if tables != {'places', 'place_names', 'meta'}:
            raise ValueError(f'Unexpected tables: {tables}')
        meta = dict(conn.execute('SELECT key, value FROM meta'))
        if meta.get('datum') != 'WGS84':
            raise ValueError('Expected WGS84 database')
        conn.execute('SELECT location_id, lat_wgs84, lng_wgs84, tz_iana FROM places LIMIT 1')
        return meta
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    pack = sub.add_parser('pack')
    pack.add_argument('--source', type=Path, default=ROOT / 'data/location.db')
    pack.add_argument('--output', type=Path, default=ROOT / 'dist/location.db.gz')
    install = sub.add_parser('install')
    install.add_argument('archive', type=Path)
    install.add_argument('--sha256', required=True, help='SHA256 of the compressed release asset')
    install.add_argument('--destination', type=Path, default=ROOT / 'data/location.db')
    args = parser.parse_args()
    if args.action == 'pack':
        meta = validate(args.source)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.source.open('rb') as src, args.output.open('wb') as dst:
            with gzip.GzipFile(filename='', mode='wb', fileobj=dst, mtime=0) as zipped:
                shutil.copyfileobj(src, zipped)
        manifest = dict(database=meta, archive=args.output.name,
                        archive_sha256=digest(args.output), database_sha256=digest(args.source))
        args.output.with_suffix('.manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
        print(json.dumps(manifest, indent=2))
    else:
        if args.destination.exists():
            raise SystemExit('Destination exists; choose a new path or back up and move it first.')
        if digest(args.archive) != args.sha256.lower():
            raise SystemExit('Archive SHA256 mismatch')
        args.destination.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(dir=args.destination.parent, suffix='.tmp')
        temp = Path(name)
        try:
            with os.fdopen(fd, 'wb') as dst, gzip.open(args.archive, 'rb') as src:
                shutil.copyfileobj(src, dst)
            validate(temp)
            # Atomic publication without overwriting an existing destination.
            os.link(temp, args.destination)
            print(f'Installed: {args.destination}')
        finally:
            temp.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
