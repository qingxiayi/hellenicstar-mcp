"""Source-backed observation topics, never a planet whitelist or client claims.

The existing geometry and direction-specific paths are referenced, not mutated.
Topic text paraphrases author observation angles; applicability is not diagnosis.
"""
from copy import deepcopy

from services.relationship_observation_topics import projection_topics


SOURCES = {
    'descendant_topics': ('Chapter Two / The Descendant sign', 'Here are some common things we look for in our partner'),
    'seventh_topics': ('Chapter Two / Planets in the seventh house', 'we should also look to the aspects these planets make'),
    'seventh_venus_mars': ('Chapter Two / Planets in the seventh house / Venus-Mars question', 'What about a Venus–Mars conjunction in the seventh?'),
    'love_needs': ('Chapter Two / The Moon; Venus and Mars', 'what we need to make us feel safe'),
    'love_projection': ('Chapter Two / The Descendant sign; Planets in the seventh house', 'The Descendant sign'),
    'love_stages': ('Chapter Two / Other pointers', 'how we give love, how we have fun'),
    'parental': ('Chapter Two / The parental relationship', 'Start off with the parental significators'),
    'family': ('Chapter Seven / Synastry with family members', 'always bear in mind the nature of the relationship'),
    'friends': ('Chapter Seven / Synastry with friends', 'Otherwise, for just a friendship'),
    'friends_third': ('Chapter Seven / Synastry with friends / Third-house question', 'especially early friends'),
    'friends_home': ('Chapter Seven / Synastry with friends', 'If we are living with friends'),
    'work': ('Chapter Seven / Synastry with work colleagues and bosses', 'pay particular attention to the sixth house'),
    'work_creative': ('Chapter Seven / Synastry with work colleagues and bosses', 'The fifth may be useful for creative projects'),
    'work_friends': ('Chapter Seven / Synastry with work colleagues and bosses', 'friendships that develop with colleagues'),
    'work_authority': ('Chapter Seven / Synastry with work colleagues and bosses', 'With regards to those who supervise us'),
}


def lens_provenance():
    return {'lens_' + key: dict(concept_provenance='JG_EXPLICIT',
        operational_rule_provenance='ENGINE_DERIVED', chapter=chapter, quote=quote,
        scope='topic is an author-angle paraphrase, not a claim about a person; selection and status labels are engineering')
        for key, (chapter, quote) in SOURCES.items()}


def topic_specs(profile, settings, who):
    """Conditions distinguish emphasis, background and optional author pointers."""
    ctx = settings['relationship_context']
    role = ctx['roles'].get(who)
    rows = []

    def add(scenario, key, topic, source, ps=(), hs=(), tier='focus',
            status='applicable_by_context', condition='selected_relationship_type'):
        rows.append(dict(scenario=scenario, key=key, observation_topic=topic,
            points=list(ps), houses=list(hs), tier=tier,
            condition=dict(status=status, description=condition,
                context_ref='/settings/relationship_context'), rule_id='lens_' + source))

    def optional_status(key):
        value = ctx[key]
        return ('optional_unconfirmed' if value is None else
                'applicable_by_context' if value else 'not_applicable_by_context')

    def parents(scenario, source, status='applicable_by_context', condition='parental_background'):
        p = profile['parental_context']
        add(scenario, 'father_image', '父亲形象、权威及男性能量的观察背景', source,
            ps=p['father_points'], hs=[p['father_house']], tier='background', status=status, condition=condition)
        add(scenario, 'mother_image', '母亲形象、照料及女性能量的观察背景', source,
            ps=p['mother_points'], hs=[p['mother_house']], tier='background', status=status, condition=condition)

    for scenario in ctx['types']:
        if scenario == 'love':
            add(scenario, 'moon_needs', '情绪需要、照料与安全感', 'love_needs', ps=['moon'])
            add(scenario, 'venus_desires', '喜爱、欲望与价值', 'love_needs', ps=['venus'])
            add(scenario, 'mars_desires', '欲望、性表达与争取所需的方式', 'love_needs', ps=['mars'])
            add(scenario, 'partner_projection', '伴侣期待及投射的观察入口', 'love_projection', ps=['descendant'], hs=[7, 8])
            add(scenario, 'play_romance', '表达爱、玩乐与恋爱初期', 'love_stages', hs=[5])
            add(scenario, 'intimacy_sharing', '亲密与分享', 'love_stages', hs=[8])
            add(scenario, 'home', '共同生活中的家庭背景', 'love_stages', hs=[4], tier='conditional',
                status='applicable_by_context' if ctx['cohabiting'] else 'optional_unconfirmed',
                condition='cohabiting_supplied_true_or_discuss_shared_home')
            parents(scenario, 'parental')
            for item in projection_topics(profile):
                add(scenario, item['key'], item['topic'], item['source'], ps=item['points'],
                    tier='conditional', status='applicable_by_geometry', condition=item['condition'])
                rows[-1]['condition']['fact_refs'] = [
                    f'/relationship_profiles/{who}/points/{p}' for p in item['evidence_points']
                ] + [f'/relationship_profiles/{who}/natal_aspects/{i}' for i in item['aspect_indices']]
                rows[-1]['condition']['experience_status'] = 'requires_client_confirmation'

        elif scenario == 'friendship':
            for key, topic, point in (
                ('venus_pleasure', '共同喜好与愉悦', 'venus'),
                ('mars_action', '争取所需与表达主张的方式', 'mars'),
                ('mercury_exchange', '交流与理解', 'mercury'),
                ('jupiter_outlook', '人生观与理念', 'jupiter')):
                add(scenario, key, topic, 'friends', ps=[point])
            add(scenario, 'play', '玩乐与共同兴趣', 'friends', hs=[5])
            add(scenario, 'friendship', '友谊与共同理想', 'friends', hs=[11])
            add(scenario, 'early_sibling_like', '早期朋友或类似手足的关系', 'friends_third',
                hs=[3], tier='supplementary', status=optional_status('early_or_sibling_like_friendship'),
                condition='caller_supplied_early_or_sibling_like_friendship')
            if ctx['cohabiting']:
                add(scenario, 'shared_home', '同住朋友的家庭与分享背景', 'friends_home',
                    hs=[4, 8, 10, 12], tier='background', condition='cohabiting_supplied_true')
        elif scenario == 'work':
            add(scenario, 'routine', '日常工作、服务与安排', 'work', hs=[6])
            add(scenario, 'career', '事业与社会位置', 'work', hs=[10])
            add(scenario, 'sun_direction', '个人方向与人生追求', 'work', ps=['sun'])
            add(scenario, 'mars_assertion', '主张与行动方式', 'work', ps=['mars'])
            add(scenario, 'pluto_power', '权力与控制议题的观察入口', 'work', ps=['pluto'], tier='supplementary')
            add(scenario, 'creative_project', '共同创作', 'work_creative', hs=[5], tier='conditional',
                status=optional_status('creative_project'), condition='caller_supplied_creative_project')
            add(scenario, 'colleague_friendship', '工作中形成的友谊', 'work_friends', hs=[11], tier='conditional',
                status='applicable_by_context' if 'friendship' in ctx['types'] else 'optional_unconfirmed',
                condition='friendship_also_selected_or_confirm_colleague_friendship')
            if role in (None, 'employee'):
                state = 'applicable_by_context' if role == 'employee' else 'optional_unconfirmed'
                add(scenario, 'authority', '面对上级时的权威背景', 'work_authority', ps=['saturn'],
                    tier='role_specific', status=state, condition='this_person_is_employee')
                parents(scenario, 'work_authority', state, 'this_person_is_employee')
        elif scenario == 'family':
            parents(scenario, 'family')
            add(scenario, 'home_roots', '家庭与家族根源', 'family', hs=[4])
            add(scenario, 'family_secrets', '家庭隐秘议题的观察入口', 'family', hs=[8])
            add(scenario, 'ancestry', '家族与代际背景', 'family', hs=[12])
            if role in (None, 'parent'):
                add(scenario, 'children', '父母一侧对子女的态度', 'family', hs=[5], tier='role_specific',
                    status='applicable_by_context' if role == 'parent' else 'optional_unconfirmed',
                    condition='this_person_is_parent')
            if role in (None, 'sibling'):
                state = 'applicable_by_context' if role == 'sibling' else 'optional_unconfirmed'
                add(scenario, 'siblings', '兄弟姐妹关系', 'family', ps=['mercury'], hs=[3],
                    tier='role_specific', status=state, condition='both_people_are_siblings')
                add(scenario, 'gemini_cusps', '兄弟姐妹背景关联的双子座宫头', 'family',
                    hs=[h['house'] for h in profile['houses'] if h['cusp_sign'] == 'Gem'],
                    tier='role_specific', status=state, condition='both_people_are_siblings')
    return rows


def build_scenario_lenses(profiles, contacts, paths, overlays, settings):
    """Share point contexts among lenses; references never add geometric evidence."""
    people, contexts = {}, {}
    for who, profile in profiles.items():
        base = f'/relationship_profiles/{who}'
        side = 'first_point' if who == 'a' else 'second_point'
        contexts[who] = {}
        for point in profile['points']:
            contact_indices = [i for i, c in enumerate(contacts)
                if any(v[side] == point for v in c['endpoint_variants'])]
            ids = {contacts[i]['id'] for i in contact_indices}
            contexts[who][point] = dict(point_ref=f'{base}/points/{point}',
                natal_aspect_refs=[f'{base}/natal_aspects/{i}' for i, e in enumerate(profile['natal_aspects'])
                    if any(point in (v['first_point'], v['second_point']) for v in e['endpoint_variants'])],
                configuration_membership_ref=f'/configuration_memberships/{who}/{point}',
                contact_refs=[f'/contacts/{i}' for i in contact_indices],
                observation_path_refs=[f'/observation_paths/{i}' for i, p in enumerate(paths)
                    if p['target_person'] == who and p['contact_id'] in ids],
                contact_scope='direct_to_this_point_or_its_explicit_axis_equivalent_only')
        rows = []
        for spec in topic_specs(profile, settings, who):
            selected = set(spec['points'])
            objects = [dict(kind='point', point=p, fact_ref=f'{base}/points/{p}') for p in spec['points']]
            for h in spec['houses']:
                house = profile['houses'][h-1]
                selected.update([house['ruler'], *house['planets']])
                objects.append(dict(kind='house', house=h, fact_ref=f'{base}/houses/{h-1}',
                    ruler_ref=f'{base}/points/{house["ruler"]}',
                    occupant_refs=[f'{base}/points/{p}' for p in house['planets']],
                    parallel_ruler_ref=f'/house_ruler_comparisons/{who}/{h-1}'))
            # Seventh-house observation membership is not a change of actual house.
            # Apply this only to lenses that observe house 7; do not migrate other cusps.
            effective = [p for p, fact in profile['points'].items()
                         if 7 in spec['houses'] and fact['seventh_cusp_effect']]
            selected.update(effective)
            objects.extend(dict(kind='effective_seventh_house_point', point=p,
                fact_ref=f'{base}/points/{p}', rule_id='seventh_cusp',
                actual_house=profile['points'][p]['house'], observation_house=7) for p in effective)
            rows.append(dict(id=f'{who}:{spec["scenario"]}:{spec["key"]}', person=who,
                scenario=spec['scenario'], observation_topic=spec['observation_topic'],
                tier=spec['tier'], condition=deepcopy(spec['condition']), objects=objects,
                point_context_refs=[f'/scenario_observation_lenses/point_contexts/{who}/{p}' for p in sorted(selected)],
                overlay_refs=[f'/house_overlays/{i}' for i, o in enumerate(overlays)
                    if o['target_person'] == who and o['house'] in spec['houses']],
                rule_id=spec['rule_id'], topic_kind='source_paraphrase_for_observation',
                client_experience='not_inferred', creates_direct_contact=False))
        people[who] = rows
    return dict(status='computed', people=people, point_contexts=contexts,
        policy=dict(planet_whitelist=False, geometry_filtered=False, topics_are_client_facts=False,
            topic_coverage='four_scenarios_and_ch2_projection_conditions_not_all_interpretation_sentences', tiers_are_weights=False,
            optional_conditions_are_inferred=False, recursive_expansion=False,
            house_ruler_contacts_are_house_activations=False,
            legacy_scenario_lists='broad_background_union_not_exhaustive_author_focus'),
        context_intake=dict(owner='caller', reuse_explicit_conversation_context=True,
            ask_relationship_type_if_unknown=True, infer_from_chart=False,
            api_default='love_for_backward_compatibility_not_confirmation',
            supported_optional_contexts=['creative_project', 'early_or_sibling_like_friendship'],
            optional_context_values='true_applies_false_does_not_apply_null_unknown',
            unsupported_contexts=['consultant_client', 'person_country'],
            enforcement='caller_guidance_not_api_gate'))
