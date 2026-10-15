"""Timezone normalization helpers shared by geocoding entrypoints."""

from typing import Optional


_PRESERVE_CHINA_REGION_ZONES = {"Asia/Taipei", "Asia/Hong_Kong", "Asia/Macau"}


def normalize_search_timezone(country: Optional[str], tz: Optional[str]) -> Optional[str]:
    """Use China's official civil timezone for mainland China results."""
    if tz in _PRESERVE_CHINA_REGION_ZONES:
        return tz
    if country == "CN":
        return "Asia/Shanghai"
    return tz


def normalize_timezone_for_coords(lat: Optional[float], lng: Optional[float], tz: Optional[str],
                                   country: Optional[str] = None) -> Optional[str]:
    """Normalize timezone for mainland China coordinates when country is unavailable."""
    if tz in _PRESERVE_CHINA_REGION_ZONES:
        return tz
    # country 守卫：只在确认中国境内才归一（避免误伤蒙古/朝鲜/日本/越南等边框内邻国）
    if country and country != "CN":
        return tz
    if lat is not None and lng is not None and 18 <= float(lat) <= 54 and 73 <= float(lng) <= 135:
        return "Asia/Shanghai"
    return tz
