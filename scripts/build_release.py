"""Build a source-only release without local Git history, databases or credentials."""
import hashlib
import json
from pathlib import Path
import tarfile

ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = {
    '.gitignore', '.dockerignore', 'Dockerfile', 'LICENSE', 'NOTICE.md', 'README.md',
    'CONTRIBUTING.md', 'SECURITY.md', 'requirements.txt', 'requirements.lock',
    'requirements-dev.txt', 'requirements-dev.lock',
}
SOURCE_DIRS = {'services', 'engine', 'assets', 'ephe', 'static_mcp', 'scripts', 'tests', 'docs', '.github'}
SUFFIXES = {'.py', '.js', '.md', '.txt', '.json', '.ttf', '.se1', '.png', '.sh', '.yml', '.yaml'}


def source_files():
    for path in sorted(ROOT.rglob('*')):
        rel = path.relative_to(ROOT)
        if path.is_symlink():
            continue
        if any(part in {'.git', '.venv', 'venv', '__pycache__', '.pytest_cache', 'dist', 'cache', 'logs'} for part in rel.parts):
            continue
        if not path.is_file():
            continue
        if rel.parts[0] == 'docs' and path.name.startswith('prelaunch-audit-'):
            continue
        if len(rel.parts) == 1:
            if path.name in ROOT_FILES or path.suffix == '.py':
                yield path, rel
        elif rel.parts[0] in SOURCE_DIRS and path.suffix in SUFFIXES:
            yield path, rel


def main():
    target = ROOT / 'dist' / 'hellenicstar-mcp-source.tar.gz'
    target.parent.mkdir(parents=True, exist_ok=True)
    files = list(source_files())
    checksums = {str(rel): hashlib.sha256(path.read_bytes()).hexdigest() for path, rel in files}
    with tarfile.open(target, 'w:gz') as archive:
        for path, rel in files:
            archive.add(path, arcname='hellenicstar-mcp/' + str(rel), recursive=False)
    manifest = {
        'archive': target.name, 'archive_sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
        'files': checksums,
        'excludes': ['Git history', 'credentials', 'local databases', 'runtime caches', 'audit work notes'],
    }
    target.with_name('source-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(f'{target}: {len(files)} files; SHA256 {manifest["archive_sha256"]}')


if __name__ == '__main__':
    main()
