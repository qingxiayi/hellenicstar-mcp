"""Condition facts and explicit dignity-policy comparisons, not salience scores.

This is a project view of existing graph facts, not a PNA implementation.
No second ephemeris, new dignity table, or inferred resource efficacy is used.
"""
import copy
from services.classical_engine import ESSENTIAL_WEIGHTS
from services.natal_resource_context import condition_context


VERSION = 'natal-condition-views-v1'
POLICIES = ('active_sect_only', 'weighted_triplicity_321')


def dignity_comparison(profile):
    condition = profile['condition']
    ref = '/planet_profiles/' + profile['planet']
    if not condition:
        return dict(status='not_applicable', reason=profile['condition_availability'],
                    policies={}, source_refs=[ref + '/condition_availability'])
    essential = condition['essential']
    triplicity = profile['triplicity_context']
    order_known = triplicity.get('order_status') == 'available'
    priority = triplicity.get('sect_priority')
    policies = {}
    for policy in POLICIES:
        if policy == 'weighted_triplicity_321' and not order_known:
            policies[policy] = dict(status='unavailable', reason='unknown_sect',
                                    total=None, contributions=None, peregrine=None)
            continue
        contributions = {key: weight if essential[key] else 0
                         for key, weight in ESSENTIAL_WEIGHTS.items()}
        if policy == 'weighted_triplicity_321':
            contributions['triplicity'] = {1: 3, 2: 2, 3: 1}.get(priority, 0)
        policies[policy] = dict(status='available', total=sum(contributions.values()),
            contributions=contributions,
            peregrine=not any(contributions[k] > 0 for k in
                             ('domicile', 'exaltation', 'triplicity', 'term', 'face')))
    baseline = policies['active_sect_only']
    alternate = policies['weighted_triplicity_321']
    available = alternate['status'] == 'available'
    return dict(status='available' if available else 'partial', policies=policies,
        score_delta=alternate['total']-baseline['total'] if available else None,
        peregrine_changes=alternate['peregrine'] != baseline['peregrine'] if available else None,
        source_refs=[ref+'/condition/essential', ref+'/triplicity_context'])


def build_condition_views(result, graph):
    profiles = result['planet_profiles']
    dynamics = result['aspect_dynamics']
    comparisons = {p: dignity_comparison(v) for p, v in sorted(profiles.items())}
    rows = {}
    for planet, profile in sorted(profiles.items()):
        ref = '/planet_profiles/' + planet
        context = condition_context(profile)
        condition = profile['condition']
        essential = condition['essential'] if condition else None
        sep = abs((profile['longitude'] - profiles['sun']['longitude'] + 180) % 360 - 180)
        solar = (dict(status='not_applicable', reason='sun_is_reference', separation_deg=0.0,
                      at_least_15_degrees=None) if planet == 'sun' else
                 dict(status='available', separation_deg=sep, at_least_15_degrees=sep >= 15.0))
        solar.update(rule='geometric_elongation_only; not a physical visibility or heliacal-rise calculation',
                     source_refs=[ref+'/longitude', '/planet_profiles/sun/longitude'])
        contacts = []
        for axis, data in sorted(graph['axes'].items()):
            contacts.append(dict(axis=axis,
                separation_deg=abs((profile['longitude']-data['lon']+180) % 360-180),
                source_refs=[ref+'/longitude', '/source_graph/axes/'+axis+'/lon']))
        phases = [dict(aspect_id=r['aspect_id'], phase=copy.deepcopy(r['phase']),
                       search=copy.deepcopy(r['search']), source_refs=[f'/aspect_dynamics/rows/{i}'])
                  for i, r in enumerate(dynamics.get('rows', []))
                  if planet in (r['planet_a'], r['planet_b'])]
        host = profile['dispositor']['planet']
        host_profile = profiles[host]
        rows[planet] = dict(
            dignity_comparison=comparisons[planet],
            placement_and_motion=dict(
                houses=context['houses'], retrograde=profile['retrograde'],
                essential=copy.deepcopy(essential),
                own_place_flags={k: essential[k] for k in ('domicile','exaltation','term')} if essential else None,
                classical_solar_state=copy.deepcopy(context['solar']), solar_distance_test=solar,
                orientality=copy.deepcopy(condition['orientality']) if condition else None,
                source_refs=[ref+'/condition', ref+'/houses', ref+'/house_ruler_links', ref+'/retrograde']),
            angularity_and_triplicity=dict(
                axes_status='available' if contacts else 'unavailable',
                axis_distances=contacts, selected_axis_contacts=copy.deepcopy(profile['axis_contacts']),
                triplicity=copy.deepcopy(profile['triplicity_context']),
                source_refs=[ref+'/axis_contacts', ref+'/triplicity_context']),
            relationship_context=dict(
                dispositor=dict(planet=host, self_ruled=host==planet,
                    state=condition_context(host_profile),
                    dignity_comparison_ref='/planet_condition_assessments/planets/'+host+'/dignity_comparison',
                    source_refs=[ref+'/dispositor', '/planet_profiles/'+host]),
                aspects=copy.deepcopy(profile['aspects']), aspect_phases=phases,
                dynamics_status=dynamics['status'],
                mutual_receptions=copy.deepcopy(profile['receptions']),
                one_way_receptions=copy.deepcopy(profile['one_way_receptions']),
                source_refs=[ref+'/aspects', ref+'/receptions', ref+'/one_way_receptions', '/aspect_dynamics']),
            resource_verdict=None, importance_score=None)
    return dict(version=VERSION, planets=rows,
        method=dict(
            default_dignity_policy='active_sect_only', comparison_policy='weighted_triplicity_321',
            comparison_source='https://zizaiastro.com/tools/chart.html',
            comparison_source_checked='2026-10-22',
            comparison_scope='Dignity arithmetic only, using our existing bounds/faces and ephemeris; not whole-site equivalence.',
            triplicity_weights=dict(primary=3, secondary=2, participating=1),
            other_weights={k: v for k,v in ESSENTIAL_WEIGHTS.items() if k!='triplicity'},
            peregrine_rule='no positive own dignity under the named policy; no peregrine penalty',
            aggregation='dignity terms only; houses, motion, aspects and axes are not added to this score',
            selection_effect='none', reception_effect='none',
            provenance='project_policy_comparison; not an ancient or report-author scoring formula',
            pna_replication=False,
            outside_scope=['PNA composite score', 'heliacal rise/set events', 'PNA completion verdict',
                           'resource efficacy', 'psychological interpretation']),
        sources=[dict(url='https://www.astrology-x-files.com/hellenistic/preliminary-natal-analysis.html',
                      use='conceptual distinction between capacity and activation; not a numeric formula')])
