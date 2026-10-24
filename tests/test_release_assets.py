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


def test_source_archive_ships_installation_and_distribution_files(tmp_path, monkeypatch):
    import importlib.util
    import json
    import tarfile
    spec = importlib.util.spec_from_file_location('build_release', ROOT / 'scripts/build_release.py')
    release = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(release)
    expected = {'README.md', 'README_en.md', 'glama.json', 'docs/quickstart.md',
                'docs/glama-build-spec.json', 'docs/distribution.md', 'scripts/smoke_install.py'}
    for relative in expected:
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((ROOT / relative).read_bytes())
    for relative in ('.env', 'data/location.db', 'cache/private.json', '.venv/private.py'):
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text('must not ship')
    (tmp_path / 'linked.py').symlink_to(ROOT / 'mcp_server.py')
    monkeypatch.setattr(release, 'ROOT', tmp_path)
    release.main()
    manifest = json.loads((tmp_path / 'dist/source-manifest.json').read_text())
    archive_path = tmp_path / 'dist/hellenicstar-mcp-source.tar.gz'
    assert manifest['archive_sha256'] == hashlib.sha256(archive_path.read_bytes()).hexdigest()
    assert set(manifest['files']) == expected
    with tarfile.open(archive_path) as archive:
        assert set(archive.getnames()) == {'hellenicstar-mcp/' + p for p in expected}
        for relative, checksum in manifest['files'].items():
            assert hashlib.sha256(archive.extractfile('hellenicstar-mcp/' + relative).read()).hexdigest() == checksum


def test_installer_smoke_over_real_stdio(tmp_path):
    import json
    image = tmp_path / 'smoke.png'
    result = subprocess.run([sys.executable, str(ROOT / 'scripts/smoke_install.py'),
                             '--image', str(image)], capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert summary['status'] == 'ok'
    assert summary['claim_counts'] == {'supported': 1, 'contradicted': 1, 'unverified': 0}
    assert image.read_bytes().startswith(b'\x89PNG\r\n\x1a\n')
