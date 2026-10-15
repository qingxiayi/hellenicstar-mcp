"""Source archives and optional geographic assets can be used independently."""
import hashlib
import sqlite3
import subprocess
import sys
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def test_location_archive_build_pack_install_and_no_overwrite(tmp_path):
    source = tmp_path / 'cities500.zip'
    with zipfile.ZipFile(source, 'w') as archive:
        archive.writestr('cities500.txt', '\t'.join([
            '2988507', 'Paris', 'Paris', '巴黎,Paris', '48.85341', '2.3488',
            'P', 'PPLC', 'FR', '', '11', '', '', '', '2138551', '', '42',
            'Europe/Paris', '2026-01-01',
        ]) + '\n')
    database = tmp_path / 'built.db'

    def run(script, *args):
        return subprocess.run([sys.executable, str(ROOT / 'scripts' / script), *map(str, args)],
                              capture_output=True, text=True)

    built = run('build_location_db.py', source, '--output', database)
    assert built.returncode == 0, built.stderr
    with sqlite3.connect(database) as conn:
        assert conn.execute('SELECT tz_iana FROM places').fetchone() == ('Europe/Paris',)
        assert conn.execute("SELECT name FROM place_names WHERE lang='zh'").fetchone() == ('巴黎',)
        assert dict(conn.execute('SELECT key,value FROM meta'))['source_archive_sha256'] == hashlib.sha256(source.read_bytes()).hexdigest()
    packed = tmp_path / 'location.db.gz'
    assert run('location_db.py', 'pack', '--source', database, '--output', packed).returncode == 0
    installed = tmp_path / 'installed.db'
    sha = hashlib.sha256(packed.read_bytes()).hexdigest()
    assert run('location_db.py', 'install', packed, '--sha256', sha, '--destination', installed).returncode == 0
    assert installed.read_bytes() == database.read_bytes()
    assert run('location_db.py', 'install', packed, '--sha256', sha, '--destination', installed).returncode != 0
    assert run('location_db.py', 'install', packed, '--sha256', '0' * 64, '--destination', tmp_path / 'bad.db').returncode != 0
    assert not (tmp_path / 'bad.db').exists()


def test_calculation_quality_references_shipped_regressions():
    from services.mcp_validation import CONTRACTS
    for _, _, regression in CONTRACTS.values():
        assert (ROOT / regression).is_file(), regression
