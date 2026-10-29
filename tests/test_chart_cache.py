"""Bounded internal PNG caching; runnable with unittest and pytest (stdlib only)."""

from contextlib import contextmanager
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

from services import chart_cache as cache


class ChartCacheTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for name, value in {"CACHE_DIR": self.root / "charts", "CACHE_MAX_BYTES": 12,
                            "CACHE_TTL_SECONDS": 7 * 86400, "_last_sweep": None}.items():
            p = patch.object(cache, name, value)
            p.start()
            self.addCleanup(p.stop)

    def key(self, value):
        return cache.cache_key({"fixture": value}, "placidus", 720)

    def seed(self, value, data=b"123456", age=0):
        path = cache._png_path(self.key(value))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        stamp = time.time() - age
        os.utime(path, (stamp, stamp))
        return path

    def pngs(self):
        return list(cache.CACHE_DIR.glob("*/*/*.png"))

    def render(self, value, fn):
        return cache.render_with_cache({"fixture": value}, "placidus", 720, fn)

    def test_repeat_hit_does_not_render_or_refresh_age(self):
        fn = Mock(return_value=b"123456")
        self.assertEqual(self.render("a", fn), b"123456")
        path = cache._png_path(self.key("a"))
        old = time.time() - 3600
        os.utime(path, (old, old))
        self.assertEqual(self.render("a", fn), b"123456")
        self.assertEqual(fn.call_count, 1)
        self.assertEqual(path.stat().st_mtime, old)

    def test_expired_hit_is_rejected_even_between_sweeps(self):
        path = self.seed("old", age=8 * 86400)
        cache._last_sweep = ((cache.CACHE_DIR, cache.CACHE_MAX_BYTES,
                              cache.CACHE_TTL_SECONDS), time.monotonic())
        fn = Mock(return_value=b"fresh")
        self.assertEqual(self.render("old", fn), b"fresh")
        self.assertEqual(fn.call_count, 1)
        self.assertEqual(path.read_bytes(), b"fresh")

    def test_first_read_reclaims_unrequested_expired_files(self):
        stale = self.seed("stale", age=8 * 86400)
        fresh = self.seed("fresh")
        self.assertEqual(cache.cache_get(self.key("fresh")), b"123456")
        self.assertFalse(stale.exists())
        self.assertTrue(fresh.exists())

    def test_exact_limit_is_allowed_and_oldest_write_evicted(self):
        old = self.seed("old", age=30)
        newer = self.seed("newer", age=10)
        cache.cache_put(self.key("latest"), b"abcdef")
        self.assertFalse(old.exists())
        self.assertTrue(newer.exists())
        self.assertEqual(sum(p.stat().st_size for p in self.pngs()), 12)

    def test_room_is_reserved_before_temporary_write(self):
        self.seed("old", age=30)
        self.seed("newer", age=10)
        replace = os.replace

        def observe(source, destination):
            total = sum(p.stat().st_size for p in self.pngs()) + Path(source).stat().st_size
            self.assertLessEqual(total, cache.CACHE_MAX_BYTES)
            replace(source, destination)

        with patch.object(cache.os, "replace", side_effect=observe):
            cache.cache_put(self.key("latest"), b"abcdef")
        self.assertEqual(cache.cache_get(self.key("latest")), b"abcdef")

    def test_oversized_image_is_returned_but_never_cached(self):
        fn = Mock(return_value=b"x" * 13)
        self.assertEqual(self.render("large", fn), b"x" * 13)
        self.assertEqual(self.render("large", fn), b"x" * 13)
        self.assertEqual(fn.call_count, 2)
        self.assertEqual(self.pngs(), [])
        self.assertEqual(list(cache.CACHE_DIR.glob("*/*/.tmp_*")), [])

    def test_existing_oversized_cache_converges_on_first_read(self):
        old = self.seed("old", data=b"x" * 12, age=60)
        newest = self.seed("newest", data=b"y" * 12)
        self.assertEqual(cache.cache_get(self.key("newest")), b"y" * 12)
        self.assertFalse(old.exists())
        self.assertEqual(self.pngs(), [newest])

    def test_periodic_sweep_runs_on_hits(self):
        self.render("hit", lambda: b"x")
        stale = self.seed("stale", age=8 * 86400)
        config, last = cache._last_sweep
        cache._last_sweep = (config, last - 61)
        self.assertEqual(cache.cache_get(self.key("hit")), b"x")
        self.assertFalse(stale.exists())

    def test_disabled_cache_never_creates_files(self):
        for setting in ("CACHE_MAX_BYTES", "CACHE_TTL_SECONDS"):
            with self.subTest(setting=setting), patch.object(cache, setting, 0):
                fn = Mock(return_value=b"image")
                self.render("a", fn)
                self.render("a", fn)
                self.assertEqual(fn.call_count, 2)
                self.assertIsNone(cache.cache_get(self.key("a")))
                cache.cache_put(self.key("a"), b"image")
                self.assertFalse(cache.CACHE_DIR.exists())

    def test_invalid_limits_use_bounded_defaults(self):
        for value in ("-1", "invalid", "", "inf", "1.5"):
            with self.subTest(value=value), patch.dict(os.environ, {"CACHE_TEST_LIMIT": value}):
                with self.assertLogs(cache.log, level="WARNING"):
                    self.assertEqual(cache._env_nonnegative_int("CACHE_TEST_LIMIT", 123), 123)
        with patch.dict(os.environ, {"CACHE_TEST_LIMIT": "0"}):
            self.assertEqual(cache._env_nonnegative_int("CACHE_TEST_LIMIT", 123), 0)

    def test_unwritable_cache_falls_back_without_rerendering(self):
        cache.CACHE_DIR.write_text("not a directory")
        fn = Mock(return_value=b"image")
        self.assertEqual(self.render("a", fn), b"image")
        self.assertEqual(fn.call_count, 1)

    def test_replace_failure_returns_image_and_removes_temp(self):
        fn = Mock(return_value=b"image")
        with patch.object(cache.os, "replace", side_effect=OSError("fixture replace failed")):
            with self.assertLogs(cache.log, level="WARNING"):
                self.assertEqual(self.render("a", fn), b"image")
        self.assertEqual(fn.call_count, 1)
        self.assertEqual(self.pngs(), [])
        self.assertEqual(list(cache.CACHE_DIR.glob("*/*/.tmp_*")), [])
        self.assertFalse(cache._png_path(self.key("a")).parent.exists())

    def test_partial_write_failure_removes_temp(self):
        fdopen = os.fdopen

        @contextmanager
        def fail_after_write(fd, mode):
            with fdopen(fd, mode) as real:
                class FailingWriter:
                    def write(self, data):
                        real.write(data[:2])
                        raise OSError("fixture partial write")
                yield FailingWriter()

        def open_for_write(fd, mode):
            return fail_after_write(fd, mode) if mode == "wb" else fdopen(fd, mode)

        with patch.object(cache.os, "fdopen", side_effect=open_for_write):
            with self.assertLogs(cache.log, level="WARNING"):
                self.assertEqual(self.render("a", lambda: b"image"), b"image")
        self.assertEqual(self.pngs(), [])
        self.assertEqual(list(cache.CACHE_DIR.glob("*/*/.tmp_*")), [])

    def test_delete_failure_prevents_new_disk_writes(self):
        old = self.seed("old", b"x" * 12, age=60)
        unlink = Path.unlink

        def deny(path, *args, **kwargs):
            if path == old:
                raise PermissionError("fixture unlink denied")
            return unlink(path, *args, **kwargs)

        fn = Mock(return_value=b"image")
        with patch.object(Path, "unlink", deny):
            self.assertEqual(self.render("new", fn), b"image")
        self.assertEqual(fn.call_count, 1)
        self.assertEqual(self.pngs(), [old])

    def test_orphan_temporary_files_are_removed_before_admission(self):
        path = cache._png_path(self.key("old"))
        path.parent.mkdir(parents=True)
        orphan = path.parent / (".tmp_" + self.key("old") + "_1234")
        orphan.write_bytes(b"orphan")
        cache.cache_put(self.key("new"), b"image")
        self.assertFalse(orphan.exists())
        self.assertFalse(path.parent.exists())
        self.assertEqual(cache.cache_get(self.key("new")), b"image")

    def test_unremovable_orphan_prevents_more_staging_files(self):
        path = cache._png_path(self.key("old"))
        path.parent.mkdir(parents=True)
        orphan = path.parent / (".tmp_" + self.key("old") + "_1234")
        orphan.write_bytes(b"orphan")
        unlink = Path.unlink

        def deny(path, *args, **kwargs):
            if path == orphan:
                raise PermissionError("fixture orphan denied")
            return unlink(path, *args, **kwargs)

        with patch.object(Path, "unlink", deny), self.assertLogs(cache.log, level="WARNING"):
            self.assertEqual(self.render("new", lambda: b"image"), b"image")
        self.assertEqual(self.pngs(), [])
        self.assertEqual(list(cache.CACHE_DIR.glob("*/*/.tmp_*")), [orphan])

    def test_unrelated_public_and_symlinked_files_are_not_evicted(self):
        cache.CACHE_DIR.mkdir()
        public = cache.CACHE_DIR / ("a" * 64 + ".png")
        public.write_bytes(b"public")
        outside = self.root / "outside"
        outside.mkdir()
        other = outside / "unrelated.png"
        other.write_bytes(b"keep")
        prefix = "00" if self.key("managed")[:2] != "00" else "ff"
        (cache.CACHE_DIR / prefix).symlink_to(outside, target_is_directory=True)
        self.render("managed", lambda: b"image")
        self.assertEqual(public.read_bytes(), b"public")
        self.assertEqual(other.read_bytes(), b"keep")

    def test_repeated_eviction_bounds_lock_files_and_removes_empty_dirs(self):
        cache.CACHE_MAX_BYTES = 1
        for i in range(100):
            self.assertEqual(self.render(i, lambda: b"x"), b"x")
        self.assertEqual(len(self.pngs()), 1)
        locks = list((cache.CACHE_DIR / ".locks").iterdir())
        self.assertLessEqual(len(locks), 65)
        hash_dirs = [p for p in cache.CACHE_DIR.glob("*/*") if p.is_dir()]
        self.assertEqual(len(hash_dirs), 1)
        self.assertEqual(len([p for p in cache.CACHE_DIR.iterdir() if p.is_dir()]), 2)

    def test_actual_hash_directory_symlink_cannot_bypass_accounting(self):
        for depth in (1, 2):
            with self.subTest(depth=depth):
                cache.CACHE_DIR = self.root / f"charts-{depth}"
                cache.CACHE_DIR.mkdir()
                path = cache._png_path(self.key("linked"))
                outside = self.root / f"outside-{depth}"
                outside.mkdir()
                link = path.parent.parent if depth == 1 else path.parent
                link.parent.mkdir(parents=True, exist_ok=True)
                link.symlink_to(outside, target_is_directory=True)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"outside")
                fn = Mock(return_value=b"fresh")
                self.assertEqual(self.render("linked", fn), b"fresh")
                self.assertEqual(fn.call_count, 1)
                self.assertEqual(path.read_bytes(), b"outside")
                self.assertEqual(list(outside.rglob(".tmp_*")), [])

    def test_linked_or_special_png_is_not_read_or_overwritten(self):
        for kind in ("symlink", "fifo"):
            with self.subTest(kind=kind):
                path = cache._png_path(self.key(kind))
                path.parent.mkdir(parents=True, exist_ok=True)
                if kind == "symlink":
                    outside = self.root / "outside.png"
                    outside.write_bytes(b"outside")
                    path.symlink_to(outside)
                else:
                    os.mkfifo(path)
                fn = Mock(return_value=b"fresh")
                self.assertEqual(self.render(kind, fn), b"fresh")
                self.assertEqual(fn.call_count, 1)
                self.assertFalse(path.is_file() and not path.is_symlink())
        self.assertEqual(outside.read_bytes(), b"outside")

    def test_empty_legacy_entry_is_rerendered(self):
        path = self.seed("empty", data=b"")
        self.assertEqual(self.render("empty", lambda: b"fresh"), b"fresh")
        self.assertEqual(path.read_bytes(), b"fresh")

    def test_lock_failure_falls_back_once(self):
        fn = Mock(return_value=b"fresh")
        with patch.object(cache.fcntl, "flock", side_effect=OSError("fixture lock failed")):
            self.assertEqual(self.render("a", fn), b"fresh")
        self.assertEqual(fn.call_count, 1)

    def test_renderer_oserror_propagates_without_retry(self):
        fn = Mock(side_effect=OSError("fixture renderer failed"))
        with self.assertRaisesRegex(OSError, "fixture renderer failed"):
            self.render("a", fn)
        self.assertEqual(fn.call_count, 1)
        # The stripe lock must also have been released by the exception.
        self.assertEqual(self.render("a", lambda: b"image"), b"image")

    def run_workers(self, values):
        # Pipes and files only: the concurrent test needs no sockets/shared memory.
        code = r'''
import json, os, pathlib, sys, time
sys.path.insert(0, sys.argv[1])
from services import chart_cache as c
root=pathlib.Path(sys.argv[2]); index=sys.argv[3]; value=json.loads(sys.argv[4])
c.CACHE_DIR=root/'charts'; c.CACHE_MAX_BYTES=12; c.CACHE_TTL_SECONDS=604800
(root/('ready-'+index)).write_text('ready')
deadline=time.monotonic()+5
while not (root/'go').exists():
    assert time.monotonic()<deadline, 'worker barrier timeout'
    time.sleep(.005)
def render():
    with (root/'renders').open('ab',buffering=0) as f:f.write(b'x')
    time.sleep(.03)
    return b'123456'
result=c.render_with_cache({'fixture':value},'placidus',720,render)
assert result==b'123456'
'''
        workers = []
        try:
            for i, value in enumerate(values):
                workers.append(subprocess.Popen(
                    [sys.executable, "-I", "-S", "-B", "-c", code,
                     str(Path(__file__).resolve().parents[1]), str(self.root), str(i), json.dumps(value)],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE))
            deadline = time.monotonic() + 5
            while len(list(self.root.glob("ready-*"))) != len(workers):
                self.assertLess(time.monotonic(), deadline, "worker readiness timeout")
                time.sleep(.005)
            (self.root / "go").write_text("go")
            for worker in workers:
                out, err = worker.communicate(timeout=5)
                self.assertEqual(worker.returncode, 0, (out, err))
        finally:
            for worker in workers:
                if worker.poll() is None:
                    worker.kill()
                worker.wait()

    def test_concurrent_processes_cannot_overcommit_budget(self):
        self.run_workers(["a", "b", "c"])
        self.assertEqual((self.root / "renders").read_bytes(), b"xxx")
        self.assertEqual(sum(p.stat().st_size for p in self.pngs()), 12)
        self.assertEqual(len(self.pngs()), 2)
        self.assertEqual(list(cache.CACHE_DIR.glob("*/*/.tmp_*")), [])

    def test_concurrent_same_key_renders_once(self):
        self.run_workers(["same", "same", "same"])
        self.assertEqual((self.root / "renders").read_bytes(), b"x")
        self.assertEqual(len(self.pngs()), 1)


if __name__ == "__main__":
    unittest.main()
