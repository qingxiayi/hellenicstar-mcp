"""The standalone audit must use the same complete source as the shipped tool."""
import pytest
from scripts.verify_natal_structure import checked_salience


@pytest.mark.parametrize('location,completeness', [
    ('coord:39.904200,116.407400', 'full'),
    ('coord:78.223200,15.646900', 'partial'),
])
def test_standalone_audit_tracks_current_salience_adapter(location, completeness):
    result = checked_salience(dict(year=2000, month=1, day=1, hour=12,
                                   minute=0, location_id=location))
    assert result['schema_version'] == 'natal-priorities-v4'
    assert result['completeness'] == completeness
    assert result['interpretations'] == []
