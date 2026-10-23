"""Explicit relationship context and parallel factual views; no inferred roles."""
from copy import deepcopy

from services.natal_house_rulers import TRADITIONAL_RULERS, MODERN_RULERS
from services.relationship_charts import PLANETS


def context_settings(value, primary, scenarios):
    value = {} if value is None else value
    if not isinstance(value, dict) or set(value) - {'additional_types', 'roles', 'cohabiting', 'creative_project', 'early_or_sibling_like_friendship'}:
        raise ValueError('relationship_context supports additional_types, roles, cohabiting, creative_project and early_or_sibling_like_friendship only')
    additional = value.get('additional_types', [])
    if not isinstance(additional, list) or any(not isinstance(t, str) or t not in scenarios for t in additional):
        raise ValueError('additional_types must be a list of supported relationship types')
    types = sorted(set([primary] + additional))
    roles = value.get('roles', {})
    if not isinstance(roles, dict):
        raise ValueError('roles must be an object with a and b')
    if roles:
        if set(roles) != {'a', 'b'} or any(not isinstance(r, str) for r in roles.values()):
            raise ValueError('roles must specify both a and b')
        pair = (roles['a'], roles['b'])
        family = {('parent', 'child'), ('child', 'parent'), ('sibling', 'sibling')}
        work = {('supervisor', 'employee'), ('employee', 'supervisor'), ('colleague', 'colleague')}
        if pair not in family | work:
            raise ValueError('supported role pairs: parent/child, siblings, supervisor/employee, colleagues')
        if ('family' if pair in family else 'work') not in types:
            raise ValueError('role pair requires family or work in the selected relationship types')
    cohabiting = value.get('cohabiting', False)
    if type(cohabiting) is not bool:
        raise ValueError('cohabiting must be boolean')
    optional = {}
    for key, scenario in [('creative_project', 'work'), ('early_or_sibling_like_friendship', 'friendship')]:
        supplied = value.get(key)
        if supplied is not None and type(supplied) is not bool:
            raise ValueError(f'{key} must be boolean or null')
        if supplied is not None and scenario not in types:
            raise ValueError(f'{key} requires {scenario} in the selected relationship types')
        optional[key] = supplied  # null/omitted is unknown, distinct from explicit false
    return dict(types=types, roles=dict(sorted(roles.items())), cohabiting=cohabiting, **optional,
                supplied=bool(value), role_origin='caller_supplied_not_inferred')


def combined_scenario(primary, context, scenarios):
    result = deepcopy(scenarios[primary])
    for t in context['types']:
        for key in ('points', 'houses'):
            result[key].extend(v for v in scenarios[t][key] if v not in result[key])
    result['element_focus_by_type'] = {t: scenarios[t]['element_focus'] for t in context['types']}
    return result


def context_provenance():
    return {
        'relationship_context': dict(concept_provenance='JG_EXPLICIT', operational_rule_provenance='ENGINE_DERIVED',
            chapter='Chapter Seven / Family; Friends; Work colleagues',
            scope='roles and cohabitation supplied by caller; role-specific focal entries coexist with general natal background'),
        'parallel_ruler_context': dict(concept_provenance='JG_DERIVED', operational_rule_provenance='ENGINE_DERIVED',
            chapter='Chapter Seven / Simon and Garfunkel',
            quote='Saturn is the old ruler of Aquarius too',
            scope='generalize the example into separately labelled traditional and modern house-ruler backgrounds; no propagation'),
        'special_contact_views': dict(concept_provenance='JG_EXPLICIT', operational_rule_provenance='ENGINE_DERIVED',
            chapter='Chapter Three / Inner planets; Nodes; Saturn and Chiron; Chapter Seven / Friends',
            scope='parallel contact lists, not weights; tight ASC uses the separately declared engineering display threshold'),
        'hemisphere_background': dict(concept_provenance='JG_EXPLICIT', operational_rule_provenance='ENGINE_DECISION',
            chapter='Chapter Three / Cross-aspects', quote='How important is the hemisphere emphasis?',
            scope='Sun through Pluto, actual houses 1-6 below and 7-12 above; cusp assigned by existing house calculation; no personality inferred'),
        'minor_orbs': dict(concept_provenance='JG_EXPLICIT', operational_rule_provenance='ENGINE_DECISION',
            chapter='Chapter Three / Cross-aspects', quote='particularly if they are very close aspects by orb',
            scope='explicit caller orbs only; no author numerical minor threshold; reject overlapping windows including axis complements'),
        'yod_context': dict(concept_provenance='JG_EXPLICIT', operational_rule_provenance='ENGINE_DERIVED',
            chapter='Chapter Six / Tom and Katie; Chapter Seven / Simon and Garfunkel',
            scope='two enabled quincunxes and an enabled sextile; all three original edges required; no destiny or psychological interpretation'),
    }


def focus_entries(who, profile, settings):
    """Role focal objects are explicit; no inference from age, gender or charts."""
    ctx, rows = settings['relationship_context'], []
    role = ctx['roles'].get(who)
    base = f'/relationship_profiles/{who}'

    def add(reason, ps=(), hs=()):
        rows.append(dict(id=f'{who}:{reason}', person=who, reason=reason,
            points=list(ps), houses=sorted(set(hs)),
            fact_refs=[f'{base}/points/{p}' for p in ps] + [f'{base}/houses/{h-1}' for h in sorted(set(hs))],
            context_ref='/settings/relationship_context', rule_id='relationship_context'))

    if role == 'parent':
        add('parent_children_house', hs=[5])
    elif role == 'child':
        add('child_parental_indicators', ps=['sun', 'moon', 'saturn', 'mars', 'venus'], hs=[4, 10])
    elif role == 'sibling':
        add('sibling_communication', ps=['mercury'], hs=[3])
        add('sibling_gemini_cusps', hs=[h['house'] for h in profile['houses'] if h['cusp_sign'] == 'Gem'])
    elif role == 'employee':
        add('employee_authority_indicators', ps=['saturn', 'sun', 'moon', 'mars', 'venus'], hs=[4, 10])
    # Supervisor/colleague labels do not themselves justify invented extra rules.
    if ctx['cohabiting']:
        add('shared_home_family_background', hs=[4, 8, 10, 12])
    return rows


def context_candidate_reasons(who, point, profile, settings):
    reasons = []
    for entry in focus_entries(who, profile, settings):
        if point in entry['points']:
            reasons.append(dict(id='context_' + entry['reason'], role='context_' + entry['reason'],
                rule_id='relationship_context', fact_refs=entry['fact_refs'] + [entry['context_ref']]))
        for house in profile['houses']:
            if house['house'] not in entry['houses']:
                continue
            for relation, match in (('ruler', house['ruler'] == point), ('occupant', point in house['planets'])):
                if match:
                    role = f'context_{entry["reason"]}_house_{house["house"]}_{relation}'
                    reasons.append(dict(id=role, role=role, rule_id='relationship_context',
                        fact_refs=[f'/relationship_profiles/{who}/houses/{house["house"]-1}', entry['context_ref']]))
    return reasons


def build_context_views(profiles, contacts, settings):
    role_entries, rulers, hemispheres = {}, {}, {}
    for who, profile in profiles.items():
        role_entries[who] = focus_entries(who, profile, settings)
        rulers[who] = []
        for h in profile['houses']:
            policies = {}
            for name, table in (('traditional', TRADITIONAL_RULERS), ('modern', MODERN_RULERS)):
                policies.setdefault(table[h['cusp_sign']], []).append(name)
            rulers[who].append(dict(house=h['house'], house_ref=f'/relationship_profiles/{who}/houses/{h["house"]-1}',
                selected_ruler=h['ruler'], routes=[dict(point=p, policies=names,
                    selected=p == h['ruler'], point_ref=f'/relationship_profiles/{who}/points/{p}',
                    natal_aspect_refs=[f'/relationship_profiles/{who}/natal_aspects/{i}'
                        for i, e in enumerate(profile['natal_aspects']) if p in (e['first_point'], e['second_point'])])
                    for p, names in sorted(policies.items())], rule_id='parallel_ruler_context'))
        below = [p for p in PLANETS[:10] if profile['points'][p]['house'] <= 6]
        above = [p for p in PLANETS[:10] if profile['points'][p]['house'] >= 7]
        hemispheres[who] = dict(below_horizon=below, above_horizon=above,
            fact_refs=[f'/relationship_profiles/{who}/points/{p}' for p in PLANETS[:10]],
            rule_id='hemisphere_background')

    lists = {key: [] for key in ('friendship_supportive_contact_ids', 'nodal_primary_contact_ids',
             'nodal_background_contact_ids', 'personal_asc_contact_ids', 'personal_asc_tight_contact_ids',
             'minor_contact_ids')}
    slow = []
    for i, c in enumerate(contacts):
        p, q = c['first_point'], c['second_point']
        if ('friendship' in settings['relationship_context']['types'] and p in PLANETS and q in PLANETS
                and c['angle'] in (60, 120)):
            lists['friendship_supportive_contact_ids'].append(c['id'])
        if 'north_node' in (p, q):
            key = 'nodal_primary_contact_ids' if c['angle'] in (0, 90, 180) else 'nodal_background_contact_ids'
            lists[key].append(c['id'])
        personal_asc = ((p == 'ascendant' and q in ('sun', 'moon', 'venus', 'mars'))
                        or (q == 'ascendant' and p in ('sun', 'moon', 'venus', 'mars')))
        if personal_asc:
            lists['personal_asc_contact_ids'].append(c['id'])
            if c['tight_contact']:
                lists['personal_asc_tight_contact_ids'].append(c['id'])
        if c['angle'] in (30, 45, 135, 150):
            lists['minor_contact_ids'].append(c['id'])
        outer = {'uranus', 'neptune', 'pluto'}
        if (p in outer and q in outer) or ({p, q} <= {'saturn', 'chiron'}):
            contexts = {}
            for who, point in (('a', p), ('b', q)):
                contexts[who] = dict(point_ref=f'/relationship_profiles/{who}/points/{point}',
                    personal_natal_aspect_refs=[f'/relationship_profiles/{who}/natal_aspects/{j}'
                        for j, e in enumerate(profiles[who]['natal_aspects'])
                        if point in (e['first_point'], e['second_point'])
                        and {e['first_point'], e['second_point']} & set(PLANETS[:5])])
            slow.append(dict(contact_id=c['id'], contact_ref=f'/contacts/{i}', contexts=contexts,
                cohort_membership='not_inferred'))
    computed = settings['mode'] == 'synastry'
    return dict(relationship_context_observations=dict(status='computed',
        context=deepcopy(settings['relationship_context']), people=role_entries,
        role_scope='specific_focal_entries_plus_retained_general_background', rule_id='relationship_context'),
        house_ruler_comparisons=rulers, hemisphere_backgrounds=hemispheres,
        special_contact_observations=dict(status='computed' if computed else 'not_computed',
            **lists, slow_planet_contexts=slow,
            friendship_status=('computed' if computed else 'not_computed') if 'friendship' in settings['relationship_context']['types'] else 'not_applicable',
            rule_id='special_contact_views', ordering='existing_orb_order', weights=None,
            contacts_omitted=False, interpretation='not_computed'))
