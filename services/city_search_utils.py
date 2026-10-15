"""Helpers for city search result formatting."""


def builtin_coordinate_keys(query, row_name, cn_to_en):
    """Return built-in coordinate keys that are safe for one search result row."""
    keys = []
    query_matches_row = (
        row_name.lower() == query.lower()
        or cn_to_en.get(query) == row_name
    )
    if query_matches_row:
        keys.append(query)
    keys.append(row_name)
    return keys
