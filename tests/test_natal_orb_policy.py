"""The default six-degree view must be inclusive and consistent across layers."""
import itertools

from services.natal_structure_graph import _aspect_layers
from services.mcp_salience import calculate_salience_data, validate_salience_output


def test_six_degree_boundary_includes_exact_limit_but_not_just_outside():
    edges = [dict(id='at-limit', **{'from': 'sun', 'to': 'moon'}, angle=60,
                  orb=6.0, depends_on=['lon:sun', 'lon:moon']),
             dict(id='outside', **{'from': 'sun', 'to': 'mercury'}, angle=60,
                  orb=6.000001, depends_on=['lon:sun', 'lon:mercury'])]
    views = _aspect_layers(edges)
    assert [e['id'] for e in views['6']['edges']] == ['at-limit']
    assert {e['id'] for e in views['8']['edges']} == {'at-limit', 'outside'}


def test_default_policy_propagates_without_changing_dispositor_core():
    birth = dict(year=2000, month=1, day=1, hour=12, minute=0,
                 location_id='coord:39.904200,116.407400')
    data = calculate_salience_data(**birth)
    validate_salience_output(data, birth)
    graph = data['source_graph']
    assert data['settings']['orb_view'] == graph['settings']['primary_aspect_view'] == 6
    selected = {e['id'] for e in graph['aspects']['6']['edges']}
    assert selected < {e['id'] for e in graph['aspects']['8']['edges']}
    assert {r['aspect_id'] for r in data['aspect_dynamics']['rows']} == selected
    for p, profile in data['planet_profiles'].items():
        assert {e['id'] for e in profile['aspects']} == {
            e['id'] for e in graph['aspects']['6']['edges'] if p in (e['from'], e['to'])}
    for relation in data['reception_facts']['rows']:
        view = relation['current_view']
        assert view['orb_view'] == 6
        assert view['has_aspect'] == (view['aspect_id'] in selected)
    expected_shared = []
    for a, b in itertools.combinations(graph['aspects']['6']['motifs'], 2):
        shared = sorted(set(a['depends_on']) & set(b['depends_on']))
        if shared:
            expected_shared.append(dict(structures=[a['id'], b['id']], shared_aspect_edges=shared))
    assert graph['dependencies']['motif_shared_edges'] == expected_shared
    wide = calculate_salience_data(**birth, orb_view=8)
    assert wide['settings']['orb_view'] == 8
    assert data['core_structures'] == wide['core_structures']
    assert data['house_ruler_links'] == wide['house_ruler_links']
    assert data['source_graph']['conditions'] == wide['source_graph']['conditions']
