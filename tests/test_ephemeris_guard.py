# -*- coding: utf-8 -*-
"""星历完整性自检测试（第 0 步 commit 0c）。"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.ephemeris_guard import (
    EphemerisModeError,
    _mode_of,
    verify_ephemeris,
)
import swisseph as swe


def test_returned_flag_parsing():
    # 258 = FLG_SWIEPH(2)|FLG_SPEED(256)；260 = FLG_MOSEPH(4)|FLG_SPEED(256)。
    assert _mode_of(swe.FLG_SWIEPH | swe.FLG_SPEED) == "swieph"
    assert _mode_of(swe.FLG_MOSEPH | swe.FLG_SPEED) == "moshier"
    assert _mode_of(swe.FLG_MOSEPH) == "moshier"


def test_verify_passes_in_file_mode():
    info = verify_ephemeris(strict=True)
    assert info["ok"] is True
    # 五星体全部文件模式，凯龙不再报错。
    for body in ("sun", "moon", "saturn", "jupiter", "chiron"):
        assert info["per_body_mode"][body] == "swieph", info["per_body_mode"]
    # 三个文件 hash 全部匹配 provenance。
    for fname in ("sepl_18.se1", "semo_18.se1", "seas_18.se1"):
        assert info["files"][fname]["present"] is True
        assert info["files"][fname]["match"] is True


def test_chiron_now_computes():
    """凯龙此前在生产报错缺 seas_18.se1；纳入后应可算且为文件模式。"""
    info = verify_ephemeris(strict=False)
    assert info["per_body_mode"]["chiron"] == "swieph"


def test_silent_fallback_is_rejected(monkeypatch, tmp_path):
    """把星历路径指到空目录（模拟文件丢失/全新部署），strict 必须抛错。"""
    import services.ephemeris_guard as guard
    monkeypatch.setattr(guard, "EPHE_PATH", str(tmp_path))
    with pytest.raises(EphemerisModeError) as ei:
        guard.verify_ephemeris(strict=True)
    msg = str(ei.value)
    assert "自检失败" in msg
    # 非 strict 不抛，但 ok=False，便于 /health 观测。
    info = guard.verify_ephemeris(strict=False)
    assert info["ok"] is False


def test_non_strict_never_raises():
    info = verify_ephemeris(strict=False)
    assert "per_body_mode" in info and "files" in info


# ── CALC-001 回归：第三方库不得把星历路径改走 ──────────────────────────────

def test_real_natal_path_never_falls_back_to_moshier():
    """整条 compute() 链路里，十大主行星必须真的跑在 swieph 文件模式。

    这是 CALC-001 的回归守卫。Kerykeion 在 astrological_subject_factory.py 里把
    ephe_path 硬编码成它自带的 kerykeion/sweph（那一行没暴露成参数，传不进去），
    并在每次建盘时调 swe.set_ephe_path() 覆盖我们设好的路径。它那个目录只有
    seas_18.se1（小行星），缺 sepl_18.se1（行星）与 semo_18.se1（月亮），于是
    十大行星请求 FLG_SWIEPH 却静默回退 Moshier——只有读**返回**旗标才看得出来。

    发现时实测 1591 次主行星调用全是 moshier，而 /health/ephemeris 报 swieph：
    自检先 apply_ephe_path() 所以永远通过，真实路径却在更里层被改走。位置差异
    最大 0.403 角秒（月亮），在度分显示下完全看不出来，所以外部对拍也发现不了。

    这类降级无人可知，必须由测试守，不能靠隔几个月跑一次审计。
    """
    import inspect
    import swisseph as swe
    from services import calculator, ephemeris_guard as guard

    guard.apply_ephe_path()
    original = swe.calc_ut
    modes = []

    def spy(jd, body, flags=0, *args, **kwargs):
        result = original(jd, body, flags, *args, **kwargs)
        if body in range(10):
            modes.append(guard._mode_of(result[1]))
        return result

    swe.calc_ut = spy
    try:
        calculator._calc_cache._d.clear()
        calculator.compute("ephe-guard-regression", 1990, 4, 15, 18, 0, "",
                           lat=48.8566, lng=2.3522, tz="Europe/Paris")
    finally:
        swe.calc_ut = original

    assert modes, "应拦到主行星调用"
    bad = [m for m in modes if m != "swieph"]
    assert not bad, (
        f"{len(bad)}/{len(modes)} 次主行星调用回退到非 swieph 模式: "
        f"{sorted(set(bad))}"
    )


def test_third_party_set_ephe_path_cannot_displace_ours():
    """任何人调 swe.set_ephe_path，我们的目录都必须仍在查找列表里。"""
    import os
    import swisseph as swe
    from services import ephemeris_guard as guard

    guard.apply_ephe_path()
    # 模拟 Kerykeion：把路径指到一个只有小行星文件的目录
    import kerykeion
    their = os.path.join(os.path.dirname(kerykeion.__file__), "sweph")
    swe.set_ephe_path(their)

    jd = swe.julday(1990, 4, 15, 16)
    for name, body in (("sun", swe.SUN), ("moon", swe.MOON), ("jupiter", swe.JUPITER)):
        _res, rflag = swe.calc_ut(jd, body, swe.FLG_SWIEPH | swe.FLG_SPEED)
        assert guard._mode_of(rflag) == "swieph", f"{name} 被挤掉了"

    guard.apply_ephe_path()


def test_long_third_party_path_still_uses_checked_ephemeris_files():
    """Long site-packages paths must not reset Swiss Ephemeris to its defaults."""
    from services import ephemeris_guard as guard

    guard.apply_ephe_path()
    try:
        swe.set_ephe_path('/unrelated/' + 'long-installation-path/' * 20)
        jd = swe.julday(1990, 4, 15, 16)
        for body in (swe.SUN, swe.MOON, swe.CHIRON):
            _, flags = swe.calc_ut(jd, body, swe.FLG_SWIEPH | swe.FLG_SPEED)
            assert guard._mode_of(flags) == 'swieph'
    finally:
        guard.apply_ephe_path()


def test_pin_target_appends_once_and_keeps_order():
    import os
    from services import ephemeris_guard as guard

    assert guard._pin_target(None) == guard.EPHE_PATH
    assert guard._pin_target("") == guard.EPHE_PATH
    # 追加到请求路径之后，让请求方的目录优先被查
    assert guard._pin_target("/tmp/x") == os.pathsep.join(["/tmp/x", guard.EPHE_PATH])
    # 已包含则不重复追加
    assert guard._pin_target(guard.EPHE_PATH) == guard.EPHE_PATH
    two = os.pathsep.join(["/tmp/x", guard.EPHE_PATH])
    assert guard._pin_target(two) == two
    # 分号写法也认（Windows 习惯），规范化成本平台分隔符
    assert guard.EPHE_PATH in guard._pin_target("/tmp/x;/tmp/y")
