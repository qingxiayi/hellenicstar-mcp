"""System versioning and protocol metadata.

Sprint 1 新建立，无历史版本。
"""
from dataclasses import dataclass, asdict
from typing import Dict, Any

# 全局版本号（Sprint 1 新建立，无历史版本）
PROTOCOL_VERSION = "0.1.0"
ENGINE_VERSION = "0.1.0"
DATA_SCHEMA_VERSION = "0.1.0"

def get_plugin_manifest_version() -> str:
    """Legacy metadata field retained; standard MCP has no plugin manifest."""
    return "not_applicable"


@dataclass(frozen=True)
class VersionInfo:
    protocol_version: str
    engine_version: str
    data_schema_version: str
    plugin_manifest_version: str
    sub_modules: Dict[str, str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def get_sub_module_versions() -> Dict[str, str]:
    """延迟导入子模块版本常量，避免启动延迟和循环依赖。"""
    from services.calculator import CALC_VERSION
    from services.chart_cache import RENDERER_VERSION
    from services.jones_pattern import ENGINE_VERSION as JONES_ENGINE_VERSION
    from services.progressed_phase import ENGINE_VERSION as PROGRESSED_PHASE_ENGINE_VERSION
    from services.solar_arc_engine import ENGINE_VERSION as SOLAR_ARC_ENGINE_VERSION
    from services.time_lords import ENGINE_VERSION as TIME_LORDS_ENGINE_VERSION
    from services.transit_presentation import ENGINE_VERSION as TRANSIT_ENGINE_VERSION

    return {
        "calc": CALC_VERSION,
        "renderer": RENDERER_VERSION,
        "jones_pattern": JONES_ENGINE_VERSION,
        "progressed_phase": PROGRESSED_PHASE_ENGINE_VERSION,
        "solar_arc": SOLAR_ARC_ENGINE_VERSION,
        "time_lords": TIME_LORDS_ENGINE_VERSION,
        "transit": TRANSIT_ENGINE_VERSION,
    }


def get_version_info() -> Dict[str, Any]:
    return VersionInfo(
        protocol_version=PROTOCOL_VERSION,
        engine_version=ENGINE_VERSION,
        data_schema_version=DATA_SCHEMA_VERSION,
        plugin_manifest_version=get_plugin_manifest_version(),
        sub_modules=get_sub_module_versions(),
    ).to_dict()
