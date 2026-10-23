"""Dignity arithmetic, missing facts and separation from focus selection."""
import copy
import json
import pytest
from services.classical_engine import compute_essential_dignities, DOROTHEAN_TRIPLICITY
from services.natal_resource_context import triplicity_context
from services.natal_condition_views import dignity_comparison, build_condition_views
from services.natal_salience import build_salience
from services.mcp_structure_graph import calculate_graph_data


def profile(planet, lon, day):
    condition = dict(essential=compute_essential_dignities(planet, lon, day))
    return dict(planet=planet, condition=condition, condition_availability='available',
                triplicity_context=triplicity_context(planet, int(lon//30), condition))


@pytest.fixture(scope='module')
def graph():
    return calculate_graph_data(year=2000, month=1, day=1, hour=12, minute=0,
                                location_id='coord:39.904200,116.407400')


@pytest.mark.parametrize('day', [True, False])
@pytest.mark.parametrize('sign', range(12))
def test_all_triplicity_roles_and_nonmembers(sign, day):
    rulers = DOROTHEAN_TRIPLICITY[sign]
    order = rulers if day else (rulers[1], rulers[0], rulers[2])
    for planet in ('sun','moon','mercury','venus','mars','jupiter','saturn'):
        p = profile(planet, sign*30+14.5, day)
        old = copy.deepcopy(p)
        comparison = dignity_comparison(p)
        a, b = (comparison['policies'][k] for k in ('active_sect_only','weighted_triplicity_321'))
        expected = 3-order.index(planet) if planet in order else 0
        assert b['contributions']['triplicity'] == expected
        assert a['total'] == p['condition']['essential']['essential_score']
        assert b['total']-a['total'] == expected-a['contributions']['triplicity']
        assert b['total'] == sum(b['contributions'].values())
        assert p == old


def test_nonprimary_member_changes_credit_not_identity():
    c = dignity_comparison(profile('jupiter', 19.0, True))
    assert c['policies']['active_sect_only']['total'] == 0
    assert c['policies']['active_sect_only']['peregrine'] is True
    assert c['policies']['weighted_triplicity_321']['total'] == 2
    assert c['policies']['weighted_triplicity_321']['peregrine'] is False
    assert c['score_delta'] == 2 and c['peregrine_changes'] is True


def test_multiple_dignities_and_debility_are_retained():
    mercury = dignity_comparison(profile('mercury', 155, True))['policies']['weighted_triplicity_321']
    assert mercury['contributions']['domicile'] == 5
    assert mercury['contributions']['exaltation'] == 4
    assert mercury['contributions']['term'] == 2
    assert mercury['total'] == 11
    saturn = dignity_comparison(profile('saturn', 19, True))['policies']['weighted_triplicity_321']
    assert saturn['contributions']['triplicity'] == 1
    assert saturn['contributions']['fall'] == -4
    assert saturn['total'] == -3


def test_unknown_sect_and_outer_planets_do_not_receive_zero_as_known_score():
    p = profile('jupiter', 19, True)
    p['triplicity_context'].update(order_status='unknown_sect', sect_priority=None)
    c = dignity_comparison(p)
    assert c['status'] == 'partial'
    assert c['policies']['weighted_triplicity_321']['total'] is None
    assert c['score_delta'] is None
    c = dignity_comparison(dict(planet='uranus', condition=None,
                               condition_availability='classical_conditions_not_defined_for_outer_planets'))
    assert c['status'] == 'not_applicable' and c['policies'] == {}


def test_condition_change_does_not_reselect_focus(graph):
    original = copy.deepcopy(graph)
    result = build_salience(graph)
    altered = copy.deepcopy(graph)
    for planet in altered['conditions']:
        altered['conditions'][planet]['essential'] = compute_essential_dignities(planet, 155, False)
        altered['conditions'][planet]['retrograde'] = not altered['conditions'][planet]['retrograde']
    changed = build_salience(altered)
    for key in ('core_structures','attention_layers','focus_selection'):
        assert result[key] == changed[key]
    assert result['planet_condition_assessments'] != changed['planet_condition_assessments']
    assert graph == original


def test_facts_are_complete_and_references_resolve(graph):
    result = build_salience(graph)
    layer = result['planet_condition_assessments']
    assert set(layer['planets']) == set(result['planet_profiles'])
    def resolve(ref):
        value = dict(result, source_graph=graph)
        for part in ref.strip('/').split('/'):
            value = value[int(part)] if isinstance(value,list) else value[part]
        return value
    def visit(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key == 'source_refs':
                    for ref in child: resolve(ref)
                elif key == 'dignity_comparison_ref': resolve(child)
                else: visit(child)
        elif isinstance(value, list):
            for child in value: visit(child)
    visit(layer)
    for planet, row in layer['planets'].items():
        assert row['relationship_context']['aspects'] == result['planet_profiles'][planet]['aspects']
        assert row['resource_verdict'] is None and row['importance_score'] is None
    assert layer['planets']['sun']['placement_and_motion']['solar_distance_test']['status'] == 'not_applicable'
    assert layer['method']['pna_replication'] is False
    json.dumps(layer, allow_nan=False)


def test_missing_axes_keeps_dignity_and_does_not_invent_houses(graph):
    partial = copy.deepcopy(graph)
    partial['axes'] = {}
    partial['houses'] = {'placidus': [], 'whole_sign': []}
    for node in partial['nodes']:
        node['house_p'] = node['house_w'] = None
    result = build_salience(partial)
    for planet, row in result['planet_condition_assessments']['planets'].items():
        assert row['angularity_and_triplicity']['axes_status'] == 'unavailable'
        assert row['angularity_and_triplicity']['axis_distances'] == []
        for house in row['placement_and_motion']['houses'].values():
            assert house['located_house'] is None and house['availability'] == 'unavailable'
        if planet in partial['conditions']:
            assert row['dignity_comparison']['status'] == 'available'


def test_solar_threshold_is_geometric_and_phase_not_supplied_is_explicit(graph):
    result = build_salience(graph)
    p = result['planet_profiles']
    for sep, expected in ((14.999999, False), (15, True), (15.000001, True)):
        p['mercury']['longitude'] = (p['sun']['longitude']+sep) % 360
        row = build_condition_views(result, graph)['planets']['mercury']
        assert row['placement_and_motion']['solar_distance_test']['at_least_15_degrees'] is expected
        assert row['relationship_context']['dynamics_status'] == 'not_supplied'
        assert row['relationship_context']['aspect_phases'] == []


def test_result_mutation_does_not_mutate_source_profile(graph):
    result = build_salience(graph)
    original = copy.deepcopy(result['planet_profiles'])
    row = result['planet_condition_assessments']['planets']['saturn']
    row['placement_and_motion']['essential']['domicile'] = 'changed'
    row['relationship_context']['aspects'].clear()
    assert result['planet_profiles'] == original
