"""Timing boundaries, independently checked geometry, and source verification."""
from copy import deepcopy
from datetime import datetime, timezone

import pytest

from services.relationship_observation import build_observation, settings_for, calculate_observation_data
from tests.test_relationship_observation import geometry, BIRTH, PARTNER
from tests.test_relationship_observation_v010 import lookup


def config(**changes):
    return dict(at='2020-06-01T15:30:00+08:00',
                transit_orbs_degrees={'0': 1, '90': 1, '180': 1},
                progression_orbs_degrees={'0': 1, '90': 1, '180': 1}, **changes)


def sources():
    return dict(transit=dict(points={p: v for p, v in geometry(17)['points'].items()
                                    if p not in ('ascendant', 'descendant', 'midheaven', 'imum_coeli')}),
                progressed={'a': geometry(30), 'b': geometry(55)})


def synthetic(cfg=None, source=None, a=None, b=None):
    return build_observation({'a': a or geometry(), 'b': b or geometry(11)}, {'a': {}, 'b': {}},
        settings_for(include_timing=True, timing=cfg or config()), timing_sources=source or sources())


@pytest.mark.parametrize('changes', [
    {'at': '2020-06-01'}, {'at': '2020-06-01T12:00:00'}, {'at': True},
    {'at': '2020-02-30T12:00:00Z'}, {'at': '2020-01-01T12:00:00+24:00'},
    {'month': '2020-06'}, {'unexpected': True}, {'include_progressed_synastry': 1},
    {'angle_progression_method': 'unknown'}, {'transit_orbs_degrees': {}},
    {'progression_orbs_degrees': None}, {'transit_orbs_degrees': {'0': True}},
    {'transit_orbs_degrees': {'0': float('nan')}}, {'transit_orbs_degrees': {'0': -1}},
    {'transit_orbs_degrees': {'0': 11}}, {'transit_orbs_degrees': {'25': 1}},
    {'transit_orbs_degrees': {'30': 10, '45': 10}},
])
def test_invalid_timing_settings_fail(changes):
    c = config(); c.update(changes)
    with pytest.raises(ValueError): settings_for(include_timing=True, timing=c)


def test_no_implicit_date_or_orbs_and_mode_boundary():
    for opts in [dict(include_timing=True), dict(timing=config()),
                 dict(include_timing=True, timing=config(), mode='natal')]:
        with pytest.raises(ValueError): settings_for(**opts)
    c = config(); c.pop('at')
    with pytest.raises(ValueError): settings_for(include_timing=True, timing=c)
    c['month'] = '2020-13'
    with pytest.raises(ValueError): settings_for(include_timing=True, timing=c)


def test_static_contact_and_network_results_unchanged_by_timing():
    r = synthetic()
    old = build_observation(r['source_geometry'], r['birth_context'], settings_for())
    for key in ('contacts', 'counts', 'observation_paths', 'activation_clusters',
                'house_overlays', 'observation_complexes', 'observation_complex_links'):
        assert r[key] == old[key]
    assert old['timing_observations']['status'] == 'not_computed'
    t = r['timing_observations']
    assert len(t['contacts']) == len({c['id'] for c in t['contacts']}) == t['counts']['unique_timing_contacts']
    assert t['policy']['counts_are_additive'] is False
    assert all(c['first_owner'] is None for c in t['contacts'] if c['first_kind'] == 'transit')


def test_contact_geometry_and_references_against_endpoints():
    r = synthetic()
    def walk(x):
        if isinstance(x, dict):
            for k, v in x.items():
                if k.endswith('_ref'):
                    assert lookup(r, v) is not None
                if k.endswith('_refs'):
                    for ref in v: assert lookup(r, ref) is not None
                walk(v)
        elif isinstance(x, list):
            for v in x: walk(v)
    walk(r['timing_observations'])
    for c in r['timing_observations']['contacts']:
        left, right = lookup(r, c['first_point_ref']), lookup(r, c['second_point_ref'])
        sep = abs((left-right+180) % 360-180)
        assert c['separation_degrees'] == pytest.approx(sep)
        assert c['orb_degrees'] == pytest.approx(abs(sep-c['angle']))
        orbs = lookup(r, c['orb_settings_ref'])
        assert any(c['orb_degrees'] <= orbs[str(a)] for a in c['evaluated_angles'])
        assert 'tight_contact' not in c and c['applying'] is None


def test_axis_equivalents_once_and_complete_point_pair_coverage():
    src = sources(); src['transit']['points']['sun'] = 30
    r = synthetic(source=src)
    hits = [c for c in r['timing_observations']['contacts']
            if c['first_person']=='transit' and c['first_point']=='sun' and c['second_person']=='a_natal']
    node = [c for c in hits if c['second_point']=='north_node']
    assert len(node)==1
    assert {(v['second_point'], v['angle']) for v in node[0]['endpoint_variants']} == {('north_node',0),('south_node',180)}
    # Independent all-endpoint enumeration, then collapse axis-equivalent identities.
    aliases={'south_node':'north_node','descendant':'ascendant','imum_coeli':'midheaven'}
    expected=set()
    for p, left in src['transit']['points'].items():
        for q, right in r['source_geometry']['a']['points'].items():
            sep=abs((left-right+180)%360-180)
            if any(abs(sep-a)<=1 for a in (0,90,180)):
                expected.add((aliases.get(p,p),aliases.get(q,q)))
    actual={(c['first_point'],c['second_point']) for c in r['timing_observations']['contacts']
            if c['first_person']=='transit' and c['second_person']=='a_natal'}
    assert actual==expected


def test_partner_and_time_overlap_reference_real_endpoints_only():
    r=synthetic(); t=r['timing_observations']
    for row in t['natal_point_entries']:
        for ref in row['timing_contact_refs']:
            c=lookup(r,ref)
            assert (c['second_owner'],c['second_point'])==(row['person'],row['point'])
        for ref in row['partner_contact_refs']:
            c=lookup(r,ref);side='first' if row['person']=='a' else 'second'
            assert c[side+'_point']==row['point']
    for row in t['natal_complex_entries']:
        comp=lookup(r,row['complex_ref'])
        for ref in row['core_timing_contact_refs']:
            assert lookup(r,ref)['second_point'] in comp['core_members']
        for ref in row['context_timing_contact_refs']:
            assert lookup(r,ref)['second_point'] in set(comp['members'])-set(comp['core_members'])
        assert row['whole_complex_activation_inferred'] is False
        assert row['time_and_partner_both_touch_core']==bool(row['core_timing_contact_refs'] and row['core_partner_contact_refs'])
    for row in t['transits_to_synastry_endpoints']:
        static=lookup(r,row['contact_ref'])
        for who,side in [('a','first'),('b','second')]:
            for ref in row[who+'_transit_contact_refs']:
                c=lookup(r,ref)
                assert c['first_kind']=='transit'
                assert (c['second_owner'],c['second_point'])==(who,static[side+'_point'])


def test_progressed_pair_is_one_geometry_with_both_owners_and_can_be_disabled():
    r=synthetic(); rows=r['timing_observations']['contacts']
    pp=[c for c in rows if c['first_kind']==c['second_kind']=='progressed']
    assert pp and all((c['first_owner'],c['second_owner'])==('a','b') for c in pp)
    cfg=config(include_progressed_synastry=False)
    off=synthetic(cfg=cfg)['timing_observations']
    assert off['availability']['progressed_synastry']=='not_requested'
    assert off['contacts']==[c for c in rows if c not in pp]


def test_real_timestamp_not_replaced_by_noon_and_true_nodes_not_renamed_mean():
    import swisseph as swe
    from services.civil_time_resolver import _julian_day_ut
    from services.solar_arc_engine import TROPICAL_YEAR_DAYS
    from services.transit_utils import body_position
    r=calculate_observation_data(person_a=BIRTH,person_b=PARTNER,include_timing=True,timing=config())
    assert r['status']=='ok'
    src=r['timing_observations']['sources']
    event=_julian_day_ut(datetime(2020,6,1,7,30,tzinfo=timezone.utc))
    assert src['event_jd_ut']==event
    assert src['transit']['points']['moon']==body_position(swe.MOON,event)[0]
    for who in ('a','b'):
        p=src['progressed'][who]
        assert p['progressed_jd_ut']==pytest.approx(p['birth_jd_ut']+(event-p['birth_jd_ut'])/TROPICAL_YEAR_DAYS)
        assert p['points']['north_node']==body_position(swe.TRUE_NODE,p['progressed_jd_ut'])[0]
        assert abs(p['points']['north_node']-body_position(swe.MEAN_NODE,p['progressed_jd_ut'])[0])>0.01


def test_month_input_drops_fast_transits_and_never_claims_entire_month():
    cfg=config();cfg.pop('at');cfg['month']='2020-06'
    r=calculate_observation_data(person_a=BIRTH,person_b=PARTNER,include_timing=True,timing=cfg)
    assert r['status']=='ok'
    t=r['timing_observations']
    assert t['sources']['at_utc']=='2020-06-15T12:00:00+00:00'
    assert not set(('sun','moon','mercury','venus','mars')) & t['sources']['transit']['points'].keys()
    assert t['availability']['monthly_presence_absence']=='not_computed'
    assert t['policy']['time_precision']=='month_midpoint_illustration'
    assert all(c['first_point'] not in ('sun','moon','mercury','venus','mars')
               for c in t['contacts'] if c['first_kind']=='transit')


@pytest.mark.parametrize('at',['1999-01-01T12:00:00Z','2200-01-01T12:00:00Z'])
def test_before_birth_or_unsupported_age_rejected(at):
    cfg=config();cfg['at']=at
    r=calculate_observation_data(person_a=BIRTH,person_b=PARTNER,include_timing=True,timing=cfg)
    assert r['status']=='invalid_input'


def test_source_failure_is_unavailable_not_fallback(monkeypatch):
    from services.ephemeris_guard import EphemerisModeError
    import services.relationship_observation_timing as timing
    def fail(*args):raise EphemerisModeError('test missing ephemeris')
    monkeypatch.setattr(timing,'calculate_timing_sources',fail)
    r=calculate_observation_data(person_a=BIRTH,person_b=PARTNER,include_timing=True,timing=config())
    assert r['status']=='unavailable' and 'contacts' not in r


def test_verified_reference_recomputes_timing_and_rejects_forged_geometry():
    import mcp_server  # Register calculation reference models.
    from services.mcp_result_facts import checked_result,verify_calculation_claims_data
    args=dict(person_a=BIRTH,person_b=PARTNER,include_timing=True,timing=config())
    raw=calculate_observation_data(**args)
    checked=checked_result('calculate_relationship_observation',raw,args)
    assert checked['status']=='ok'
    result=verify_calculation_claims_data(checked['calculation_reference'],[
        dict(quote='Time computed',path='/timing_observations/status',value='computed'),
        dict(quote='UTC instant',path='/timing_observations/sources/at_utc',value='2020-06-01T07:30:00+00:00'),
        dict(quote='No predictions',path='/timing_observations/policy/predictions_generated',value=False)])
    assert result['counts']['supported']==3, result
    for field in ('sources','contacts','natal_point_entries','natal_complex_entries','transits_to_synastry_endpoints'):
        corrupt=deepcopy(raw)
        if field=='sources':corrupt['timing_observations'][field]['transit']['points']['sun']+=0.1
        else:
            assert corrupt['timing_observations'][field]
            corrupt['timing_observations'][field].pop()
        assert checked_result('calculate_relationship_observation',corrupt,args)['status']=='validation_failed'


def test_equivalent_offsets_and_numeric_orbs_have_same_calculation_fingerprint():
    from services.mcp_result_facts import fingerprint
    args=dict(person_a=BIRTH,person_b=PARTNER,include_timing=True)
    a=calculate_observation_data(**args,timing=config())
    cfg=config();cfg['at']='2020-06-01T07:30:00Z'
    cfg['transit_orbs_degrees']={k:float(v) for k,v in cfg['transit_orbs_degrees'].items()}
    b=calculate_observation_data(**args,timing=cfg)
    assert fingerprint(a)==fingerprint(b)


def test_swapping_births_swaps_natal_and_progressed_ownership():
    args=dict(include_timing=True,timing=config())
    ab=calculate_observation_data(person_a=BIRTH,person_b=PARTNER,**args)['timing_observations']
    ba=calculate_observation_data(person_a=PARTNER,person_b=BIRTH,**args)['timing_observations']
    assert ab['sources']['progressed']['a']==ba['sources']['progressed']['b']
    assert ab['sources']['progressed']['b']==ba['sources']['progressed']['a']
    assert ab['sources']['transit']==ba['sources']['transit']
    def signature(rows,swap=False):
        result={}
        def owner(v):return {'a':'b','b':'a',None:None}[v] if swap else v
        for c in rows:
            ends=tuple(sorted((
                (c['first_kind'],owner(c['first_owner']) or '',c['first_point']),
                (c['second_kind'],owner(c['second_owner']) or '',c['second_point']))))
            result[ends+(c['angle'],)]=c['orb_degrees']
        return result
    assert signature(ab['contacts'])==pytest.approx(signature(ba['contacts'],swap=True))


def test_disabled_timing_never_calls_time_engines(monkeypatch):
    import services.relationship_observation_timing as timing
    monkeypatch.setattr(timing,'calculate_timing_sources',lambda *a:pytest.fail('timing must be opt-in'))
    r=calculate_observation_data(person_a=BIRTH,person_b=PARTNER)
    assert r['status']=='ok' and r['timing_observations']['status']=='not_computed'


@pytest.mark.parametrize('part,sample,end', [('early','05','10'),('middle','15','20'),('late','25','29')])
def test_month_parts_preserve_calendar_range_and_label_engineering_sample(part,sample,end):
    cfg=config();cfg.pop('at');cfg.update(month='2024-02',month_part=part)
    s=settings_for(include_timing=True,timing=cfg)['timing']
    assert s['at']==f'2024-02-{sample}T12:00:00+00:00'
    assert s['calendar_window']['end_date_inclusive']==f'2024-02-{end}'
    assert s['precision']=='month_part_illustration'
    assert s['midpoint_policy_provenance']=='ENGINE_DECISION'
    assert s['excluded_transit_points']==['sun','moon','mercury','venus','mars']


def test_date_without_clock_is_not_promoted_to_exact_instant():
    cfg=config();cfg.pop('at');cfg['date']='2022-09-17'
    s=settings_for(include_timing=True,timing=cfg)['timing']
    assert s['at']=='2022-09-17T12:00:00+00:00'
    assert s['requested_date']=='2022-09-17'
    assert s['precision']=='calendar_date_noon_illustration'
    assert 'moon' in s['excluded_transit_points']


@pytest.mark.parametrize('change',[{'month_part':'early'}, {'date':'2022-09-17'},
    {'month_part':None}, {'month_part':'first'}, {'month_part':True}])
def test_ambiguous_or_inapplicable_period_input_rejected(change):
    cfg=config();cfg.update(change)
    with pytest.raises(ValueError): settings_for(include_timing=True,timing=cfg)
