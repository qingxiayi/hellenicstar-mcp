# -*- coding: utf-8 -*-
"""services/ephemeris_guard.py —— 星历完整性地基（实施第 0 步）。

单一职责：
  1. 确定性解析 Swiss Ephemeris 文件路径（仓库 `ephe/`，可用 SWEPH_PATH 覆盖）。
  2. 启动/健康检查时断言土/木/日/月/凯龙真的跑在 swieph 文件模式，
     杜绝「请求 FLG_SWIEPH 却静默回退 Moshier」这类无人可知的降级。

文件来源与校验值见 ephe/PROVENANCE.md。
"""
import hashlib
import os

import swisseph as swe

# 仓库根 = 本文件所在 services/ 的上一级。
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resolve_ephe_path(environ=None):
    """确定性解析星历路径：SWEPH_PATH 环境变量优先，否则仓库内 ephe/。

    抽成纯函数便于测试（传 environ 字典即可，无需改进程环境或 reload 模块）。
    """
    environ = os.environ if environ is None else environ
    return environ.get("SWEPH_PATH") or os.path.join(REPO_ROOT, "ephe")


# 确定性星历路径。不再传 None 靠默认路径碰运气。
EPHE_PATH = resolve_ephe_path()

# 自检星体：名字 -> swe 常量。凯龙纳入是因为它此前在生产上报错缺文件。
_GUARD_BODIES = [
    ("sun", swe.SUN),
    ("moon", swe.MOON),
    ("saturn", swe.SATURN),
    ("jupiter", swe.JUPITER),
    ("chiron", swe.CHIRON),
]

# provenance：随仓库提供的文件 -> 期望 SHA-256。
EXPECTED_SHA256 = {
    "sepl_18.se1": "ca1393ceab3a44fbc895887cf789c68819ae6a1cbc9b22225872dbe4ccd99a66",
    "semo_18.se1": "1ca07bd67c24374d77226180c20a4f9996cba013697894810518e7eb582ca4f7",
    "seas_18.se1": "5fd9c2aa1654e37c09a6aeb558076e795409b7dc4bd948ebc0faa7d4a7686b5b",
}

# 自检探测年份位于随附文件覆盖范围内；不是覆盖下界。
GUARD_PROBE_YEAR = 1900


class EphemerisModeError(RuntimeError):
    """要求 swieph 文件模式却检测到 Moshier / 缺文件 / hash 不符时抛出。"""


def apply_ephe_path():
    """把 swe 的星历路径设成确定性 EPHE_PATH。引擎与自检共用同一入口。"""
    _ensure_path_pin()
    swe.set_ephe_path(EPHE_PATH)
    return EPHE_PATH


# ── 路径钉死：防第三方库把星历路径改走 ───────────────────────────────────
#
# Kerykeion 在 astrological_subject_factory.py 里把 ephe_path 硬编码成它自己的
# `kerykeion/sweph`（那一行没有暴露成参数，传不进去），并在每次建盘时调
# swe.set_ephe_path() 覆盖我们设好的路径。而它自带的目录里只有 seas_18.se1
# （小行星），没有 sepl_18.se1（行星）和 semo_18.se1（月亮）——于是十大主行星
# 请求 FLG_SWIEPH 却静默回退 Moshier，返回旗标里才看得出来。
#
# 不跟它抢最后一次调用，而是把我们的目录**追加**进它设的路径。Swiss Ephemeris
# 接受多目录列表并按序查找（实测 ';' 与 ':' 都可），所以小行星仍从它的目录取，
# 行星与月亮落到我们这份校验过 hash 的文件上，两边都满足。
#
# 只在 os.pathsep 存在时用它，Windows 上是 ';'，Unix 上是 ':'，两者 swe 都认。
_PATH_PINNED = False


# sweph.c swe_set_ephe_path accepts AS_MAXCH - 1 - 13 bytes (256 - 14).
# Longer paths silently select the library default instead of the supplied path.
_MAX_EPHE_PATH_BYTES = 242


def _pin_target(requested):
    """Include checked files without overflowing Swiss Ephemeris' path buffer."""
    if len(os.fsencode(EPHE_PATH)) > _MAX_EPHE_PATH_BYTES:
        raise EphemerisModeError("星历目录路径过长；请用 SWEPH_PATH 指向较短的星历目录")
    if not requested:
        return EPHE_PATH
    parts = [p for p in str(requested).replace(";", os.pathsep).split(os.pathsep) if p]
    if any(os.path.abspath(p) == os.path.abspath(EPHE_PATH) for p in parts):
        target = str(requested)
    else:
        target = os.pathsep.join(parts + [EPHE_PATH])
    return target if len(os.fsencode(target)) <= _MAX_EPHE_PATH_BYTES else EPHE_PATH


def _ensure_path_pin():
    """装一次性包装：之后任何 swe.set_ephe_path 调用都会带上 EPHE_PATH。"""
    global _PATH_PINNED
    if _PATH_PINNED:
        return
    original = swe.set_ephe_path

    def set_ephe_path_pinned(path=None):
        return original(_pin_target(path))

    set_ephe_path_pinned._ephemeris_guard_original = original
    swe.set_ephe_path = set_ephe_path_pinned
    _PATH_PINNED = True


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _mode_of(rflag):
    if rflag & swe.FLG_SWIEPH:
        return "swieph"
    if rflag & swe.FLG_MOSEPH:
        return "moshier"
    if rflag & swe.FLG_JPLEPH:
        return "jpl"
    return "unknown(%d)" % rflag


def verify_ephemeris(strict=True, probe_year=GUARD_PROBE_YEAR):
    """对关键星体断言 swieph 文件模式，并校验文件 hash。

    读的是 swe.calc_ut 的**返回**旗标（不是输入旗标），这是唯一能发现
    静默回退的地方。strict=True 且任一异常则抛 EphemerisModeError。

    返回 provenance dict，供 /health/ephemeris 与启动日志使用。
    """
    apply_ephe_path()
    jd = swe.julday(probe_year, 1, 1, 0.0)
    per_body = {}
    bad = []
    for name, pl in _GUARD_BODIES:
        try:
            _res, rflag = swe.calc_ut(jd, pl, swe.FLG_SWIEPH | swe.FLG_SPEED)
            mode = _mode_of(rflag)
            per_body[name] = mode
            if mode != "swieph":
                bad.append("%s=%s" % (name, mode))
        except Exception as e:  # 缺文件时 swe 抛异常
            per_body[name] = "error:%s" % type(e).__name__
            bad.append("%s=error(%s)" % (name, str(e)[:80]))

    files = {}
    for fname, expected in EXPECTED_SHA256.items():
        fpath = os.path.join(EPHE_PATH, fname)
        if not os.path.exists(fpath):
            files[fname] = {"present": False}
            bad.append("%s=missing" % fname)
            continue
        actual = _sha256(fpath)
        files[fname] = {"present": True, "sha256": actual, "match": actual == expected}
        if actual != expected:
            bad.append("%s=sha256_mismatch" % fname)

    info = {
        "pyswisseph_version": getattr(swe, "version", "?"),
        "ephe_path": EPHE_PATH,
        "probe_year": probe_year,
        "per_body_mode": per_body,
        "files": files,
        "ok": not bad,
    }
    if strict and bad:
        raise EphemerisModeError(
            "星历完整性自检失败（要求 swieph 文件模式）: "
            + "; ".join(bad)
            + " | ephe_path=" + EPHE_PATH
            + " | 修复: 确认该目录下有 sepl_18/semo_18/seas_18.se1 且 hash 匹配"
            + "（见 ephe/PROVENANCE.md）"
        )
    return info
