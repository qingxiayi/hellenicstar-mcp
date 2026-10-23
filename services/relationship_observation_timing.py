"""Selected-time observations, using existing ephemeris/progression engines.

No event search, guessed meeting time, inherited synastry orbs, or predictions.
The book supplies observation actions; numerical policy is caller/engine owned.
"""
from copy import deepcopy
from calendar import monthrange
from datetime import datetime, timedelta, timezone
from itertools import combinations
import math
import re

ANGLES = {0, 30, 45, 60, 90, 120, 135, 150, 180}
FAST_TRANSITS = ('sun', 'moon', 'mercury', 'venus', 'mars')


def parse_instant(value, field):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d{1,6})?)?(Z|[+-]\d{2}:\d{2})', value):
        raise ValueError(f'{field} requires an ISO timestamp with an explicit UTC offset')
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone(timezone.utc)
    except OverflowError:
        raise ValueError(f'{field} is outside the supported calendar range') from None


def _orbs(value, field):
    if not isinstance(value, dict) or not value or set(value) - {str(a) for a in ANGLES}:
        raise ValueError(f'timing.{field} requires explicit aspect-angle keys and orb values')
    if any(type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 10 for v in value.values()):
        raise ValueError(f'timing.{field} orbs must be finite numbers in [0, 10]')
    windows = {}
    for angle, limit in value.items():
        for a in (int(angle), 180 - int(angle)):
            windows[a] = max(windows.get(a, 0), limit)
    if any(abs(a-b) <= windows[a]+windows[b] for a, b in combinations(windows, 2)):
        raise ValueError(f'timing.{field} windows overlap including axis complements')
    return {k: float(v) for k, v in sorted(value.items())}


def timing_settings(value, enabled, mode, relationship_context=None):
    if not enabled:
        if value is not None:
            raise ValueError('timing requires include_timing=true')
        return None
    if mode != 'synastry':
        raise ValueError('Timing observation requires mode=synastry and two complete births')
    allowed = {'at', 'date', 'month', 'month_part', 'event', 'transit_orbs_degrees', 'progression_orbs_degrees',
               'angle_progression_method', 'include_progressed_synastry', 'window_start', 'window_end'}
    if not isinstance(value, dict) or set(value) - allowed:
        raise ValueError('timing requires an explicit time and orb settings; unknown keys are rejected')
    if sum(k in value for k in ('at', 'date', 'month', 'event')) != 1:
        raise ValueError('timing requires exactly one of at, date, month, or event=childbirth')
    if 'month_part' in value and ('month' not in value or value['month_part'] not in ('early', 'middle', 'late')):
        raise ValueError('timing.month_part requires month and must be early, middle or late')
    calendar_window = None
    event = None
    if 'event' in value:
        roles = (relationship_context or {}).get('roles', {})
        if value['event'] != 'childbirth' or set(roles.values()) != {'parent', 'child'}:
            raise ValueError('timing.event=childbirth requires explicit parent/child roles in a family context')
        child = next(who for who, role in roles.items() if role == 'child')
        parent = next(who for who, role in roles.items() if role == 'parent')
        event = dict(event='childbirth', child_person=child, parent_person=parent,
                     birth_context_ref='/birth_context/'+child, role_origin='caller_supplied_not_inferred')
        moment = None  # Resolved only after the existing birth resolver has succeeded.
        precision = 'resolved_child_birth_instant'
    elif 'at' in value:
        moment = parse_instant(value['at'], 'timing.at')
        precision = 'supplied_instant'
    elif 'date' in value:
        day = value['date']
        if not isinstance(day, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', day):
            raise ValueError('timing.date must be YYYY-MM-DD; clock time is not assumed known')
        moment = datetime.fromisoformat(day + 'T12:00:00+00:00')
        precision = 'calendar_date_noon_illustration'
        calendar_window = dict(start_date=day, end_date_inclusive=day)
    else:
        month = value['month']
        if not isinstance(month, str) or not re.fullmatch(r'\d{4}-\d{2}', month):
            raise ValueError('timing.month must be YYYY-MM')
        part = value.get('month_part')
        sample_day = {'early': 5, 'middle': 15, 'late': 25, None: 15}[part]
        moment = datetime.fromisoformat(f'{month}-{sample_day:02d}T12:00:00+00:00')
        last = monthrange(moment.year, moment.month)[1]
        start, end = {'early': (1, 10), 'middle': (11, 20), 'late': (21, last), None: (1, last)}[part]
        calendar_window = dict(start_date=f'{month}-{start:02d}', end_date_inclusive=f'{month}-{end:02d}')
        precision = 'month_part_illustration' if part else 'month_midpoint_illustration'
    method = value.get('angle_progression_method', 'naibod')
    if method not in ('naibod', 'solar_arc_in_ra'):
        raise ValueError('timing.angle_progression_method must be naibod or solar_arc_in_ra')
    pp = value.get('include_progressed_synastry', True)
    if type(pp) is not bool:
        raise ValueError('timing.include_progressed_synastry must be boolean')
    from services.relationship_observation_windows import window_settings
    # Validate a requested window now; event containment is checked on resolution.
    window_anchor = moment
    if event and 'window_start' in value:
        window_anchor = parse_instant(value['window_start'], 'timing.window_start')
    return dict(at=moment.isoformat() if moment else None, event_context=event,
                node_type='mean' if event else 'true',
                requested_month=value.get('month'), requested_date=value.get('date'),
                window=window_settings(value, window_anchor),
                requested_month_part=value.get('month_part'), calendar_window=calendar_window, precision=precision,
                transit_orbs_degrees=_orbs(value.get('transit_orbs_degrees'), 'transit_orbs_degrees'),
                progression_orbs_degrees=_orbs(value.get('progression_orbs_degrees'), 'progression_orbs_degrees'),
                angle_progression_method=method, include_progressed_synastry=pp,
                excluded_transit_points=list(FAST_TRANSITS) if precision not in ('supplied_instant', 'resolved_child_birth_instant') else [],
                orb_provenance='ENGINE_DECISION_CALLER_SUPPLIED',
                approximate_date_policy='single_sample_not_interval_presence_or_absence',
                reference_clock_policy='UTC_reference_clock_not_claimed_actual_local_meeting_time',
                midpoint_policy_provenance='ENGINE_DECISION')


def resolve_event_settings(settings, contexts):
    """Resolve caller-declared child identity through authoritative birth context."""
    cfg = settings['timing']
    if cfg is None or cfg['event_context'] is None:
        return settings
    resolved = deepcopy(settings)
    cfg = resolved['timing']
    event = cfg['event_context']
    def birth_instant(who):
        ctx = contexts[who]
        return datetime.fromisoformat(ctx['civil_dt']).replace(
            tzinfo=timezone(timedelta(hours=ctx['utc_offset']))).astimezone(timezone.utc)
    moment = birth_instant(event['child_person'])
    if moment <= birth_instant(event['parent_person']):
        raise ValueError('The declared child must be born after the declared parent')
    cfg['at'] = moment.isoformat()
    if cfg['window']:
        from services.relationship_observation_windows import window_settings
        cfg['window'] = window_settings(dict(window_start=cfg['window']['start'], window_end=cfg['window']['end']), moment)
    cfg['reference_clock_policy'] = 'resolved_child_birth_UTC_from_supplied_civil_time_location_and_fold'
    cfg['approximate_date_policy'] = 'not_applicable_complete_birth_input'
    return resolved


def verify_natal_node_sources(geometries, contexts):
    """Verify the legacy positions; misleading upstream key names are not evidence."""
    import swisseph as swe
    from services.civil_time_resolver import _julian_day_ut
    from services.transit_utils import body_position
    from services.ephemeris_guard import EphemerisModeError
    for who, geometry in geometries.items():
        ctx = contexts[who]
        birth = datetime.fromisoformat(ctx['civil_dt']).replace(
            tzinfo=timezone(timedelta(hours=ctx['utc_offset']))).astimezone(timezone.utc)
        lon = body_position(swe.MEAN_NODE, _julian_day_ut(birth))[0]
        for point, expected in [('north_node', lon), ('south_node', (lon+180) % 360)]:
            if abs((geometry['points'][point]-expected+180) % 360-180) > 1e-7:
                raise EphemerisModeError('Natal node source does not match the declared mean-node convention')


def timing_provenance():
    return {
        'timing_observation': dict(concept_provenance='JG_EXPLICIT', operational_rule_provenance='ENGINE_DERIVED',
            chapter='Chapter Six – Transits and Progressions in Synastry',
            locator='Diana mid July 1980; Tom and Katie / same chart areas; two progressed charts',
            scope='selected-time geometry and bounded natal contexts, not psychological effects'),
        'timing_orbs': dict(concept_provenance='ENGINE_DECISION', operational_rule_provenance='ENGINE_DECISION',
            scope='caller supplies transit and progression aspect windows; no John Green numerical timing default'),
        'timing_midmonth': dict(concept_provenance='JG_EXPLICIT', operational_rule_provenance='ENGINE_DECISION',
            chapter='Chapter Six / Charles and Diana', locator='mid July 1980 / outer planets and progressions',
            scope='month/date/early-middle-late samples at 12:00 UTC are engineering illustrations; exclude fast transits, do not assert interval stability'),
        'timing_window': dict(concept_provenance='JG_EXPLICIT', operational_rule_provenance='ENGINE_DERIVED',
            chapter='Chapter Six / Tom and Katie; relationships over time',
            locator='throughout the process / major transits hit their cross-aspects',
            scope='numerical orb intervals and exact roots; mesh, derivative, tolerances and bounds are engineering, not author rules'),
        'childbirth_observation': dict(concept_provenance='JG_EXPLICIT', operational_rule_provenance='ENGINE_DERIVED',
            chapter='Chapter Seven / Synastry with family members; Carrie Fisher and Debbie Reynolds',
            quote='a child’s chart shows the transits a parent was undergoing at the time of birth',
            scope='resolve declared child birth; link parental transit contacts to identical child natal positions without adding independent evidence'),
        'progressed_synastry_comparison': dict(concept_provenance='JG_EXPLICIT', operational_rule_provenance='ENGINE_DERIVED',
            chapter='Chapter Six / concluding discussion of the two progressed charts',
            locator='Planets that were square in the natal synastry may not be any longer',
            scope='compare selected-time progressed synastry with natal geometry under identical explicit orbs; no first-appearance or internal-pattern requirement inferred'),
    }


def calculate_timing_sources(births, contexts, settings):
    """Reuse exact birth contexts, guarded positions and secondary progression engine."""
    import swisseph as swe
    from services.civil_time_resolver import _julian_day_ut
    from services.secondary_progressions import compute_secondary_progressions, PLANET_DEFS
    from services.solar_arc_engine import TROPICAL_YEAR_DAYS, MAX_SUPPORTED_AGE
    from services.transit_utils import body_position
    from services.relationship_observation import validate_geometry
    cfg = settings['timing']
    moment = datetime.fromisoformat(cfg['at'])
    event_jd = _julian_day_ut(moment)
    bodies = dict(PLANET_DEFS, chiron=swe.CHIRON,
                  north_node=swe.MEAN_NODE if cfg['node_type'] == 'mean' else swe.TRUE_NODE)
    transit = {p: body_position(body, event_jd)[0] for p, body in bodies.items()
               if p not in cfg['excluded_transit_points']}
    transit['south_node'] = (transit['north_node'] + 180) % 360
    progressed = {}
    for who, birth in births.items():
        ctx = contexts[who]
        local = datetime.fromisoformat(ctx['civil_dt']).replace(
            tzinfo=timezone(timedelta(hours=ctx['utc_offset'])))
        birth_jd = _julian_day_ut(local.astimezone(timezone.utc))
        age = (event_jd-birth_jd) / TROPICAL_YEAR_DAYS
        if not 0 <= age <= MAX_SUPPORTED_AGE:
            raise ValueError(f'timing date must be after person_{who} birth and within {MAX_SUPPORTED_AGE} years')
        prog = compute_secondary_progressions(
            birth['year'], birth['month'], birth['day'], birth['hour'], birth['minute'],
            ctx['lat'], ctx['lng'], age=age, house_system='P',
            angle_progression_method=cfg['angle_progression_method'],
            birth_location_id=birth['location_id'], birth_fold=birth.get('fold'))
        if abs(prog['progressed_jd'] - (birth_jd+age)) > 1e-8:
            raise ValueError('Progression birth instant disagrees with resolved natal context')
        chart = prog['progressed_chart']
        ps = {p: row['longitude'] for p, row in chart['planets'].items()}
        ps['chiron'] = chart['special_points']['chiron']['longitude']
        # Legacy progressions use mean nodes; explicit timing normally uses true
        # nodes, while childbirth matches the verified mean natal convention.
        # Reuse guarded ephemeris at the returned JD for the declared adapter;
        # also verify file-backed mode/positions for each engine planet.
        for p, body in bodies.items():
            lon = body_position(body, prog['progressed_jd'])[0]
            if p in ps and abs((ps[p]-lon+180) % 360-180) > 1e-8:
                raise ValueError('Progression source position disagrees with guarded ephemeris')
            ps[p] = lon
        ps['south_node'] = (ps['north_node']+180) % 360
        ps.update({p: row['longitude'] for p, row in chart['axes'].items()})
        geometry = dict(points=ps, cusps=chart['houses']['cusps'])
        validate_geometry(geometry)
        progressed[who] = dict(**geometry, age_years=age, birth_jd_ut=birth_jd,
                              progressed_jd_ut=prog['progressed_jd'],
                              angle_progression_method=prog['angle_progression_method'])
    return dict(event_jd_ut=event_jd, at_utc=cfg['at'], transit=dict(points=transit), progressed=progressed,
                node_type=cfg['node_type'], node_adapter='guarded_'+cfg['node_type']+'_node_at_progressed_jd',
                ephemeris_mode='swieph', progression_engine='secondary_progressions_day_for_a_year',
                progression_year_days=TROPICAL_YEAR_DAYS, transit_angles_computed=False)


def timing_pairs(cfg):
    pairs = [('transit', who+'_'+kind, 'transit_orbs_degrees')
             for who in ('a', 'b') for kind in ('natal', 'progressed')]
    pairs += [(p+'_progressed', n+'_natal', 'progression_orbs_degrees')
              for p in ('a', 'b') for n in ('a', 'b')]
    if cfg['include_progressed_synastry']:
        pairs.append(('a_progressed', 'b_progressed', 'progression_orbs_degrees'))
    return pairs


def build_timing_observations(observation, sources):
    from services.relationship_observation import contacts_between, CANONICAL, adjacent
    cfg = observation['settings']['timing']
    if cfg is None:
        return dict(status='not_computed', reason='not_requested',
                    window_scan=dict(status='not_computed', reason='not_requested'))
    if sources is None:
        raise ValueError('Timing sources required when include_timing=true')
    base = '/timing_observations'
    charts = {'transit': dict(points=sources['transit']['points'], person=None, kind='transit',
                              ref=base+'/sources/transit')}
    for who in ('a', 'b'):
        charts[who+'_natal'] = dict(points=observation['source_geometry'][who]['points'], person=who,
                                   kind='natal', ref='/source_geometry/'+who)
        charts[who+'_progressed'] = dict(points=sources['progressed'][who]['points'], person=who,
                                       kind='progressed', ref=base+'/sources/progressed/'+who)
    contacts = []
    for left, right, orb_key in timing_pairs(cfg):
        l, r = charts[left], charts[right]
        # Reuse axis equivalence and geometric deduplication. Timing has no
        # independently sourced tight threshold, so remove that display flag.
        policy = dict(orbs=cfg[orb_key], tight_orb_degrees=0)
        rows = contacts_between(l['points'], r['points'], left, right, policy,
                                first_points=tuple(p for p in CANONICAL if p in l['points']))
        for row in rows:
            row.pop('tight_contact'); row.pop('generational_contact')
            row.update(rule_id='timing_orbs', orb_settings_ref='/settings/timing/'+orb_key,
                       first_kind=l['kind'], second_kind=r['kind'],
                       first_owner=l['person'], second_owner=r['person'],
                       first_point_ref=l['ref']+'/points/'+row['first_point'],
                       second_point_ref=r['ref']+'/points/'+row['second_point'])
        contacts.extend(rows)
    contacts.sort(key=lambda r: r['id'])
    timing_index = {}
    transit_index = {}
    for i, row in enumerate(contacts):
        if row['second_kind'] != 'natal':
            continue
        key = (row['second_owner'], row['second_point'])
        ref = base+'/contacts/'+str(i)
        timing_index.setdefault(key, []).append(ref)
        if row['first_kind'] == 'transit':
            transit_index.setdefault(key, []).append(ref)
    static_index = {}
    for i, row in enumerate(observation['contacts']):
        for who, side in (('a', 'first'), ('b', 'second')):
            static_index.setdefault((who, row[side+'_point']), []).append('/contacts/'+str(i))
    point_entries, complex_entries, transit_cross = [], [], []
    for (who, point), refs in sorted(timing_index.items()):
        profile = observation['relationship_profiles'][who]
        edge_ids = {e['id'] for e in adjacent(profile['natal_aspects'], point)}
        partner = static_index.get((who, point), [])
        point_entries.append(dict(person=who, point=point, point_ref=f'/relationship_profiles/{who}/points/{point}',
            timing_contact_refs=refs, partner_contact_refs=partner, also_contacted_by_partner=bool(partner),
            natal_aspect_refs=[f'/relationship_profiles/{who}/natal_aspects/{i}'
                               for i, e in enumerate(profile['natal_aspects']) if e['id'] in edge_ids],
            context_depth=1, rule_id='timing_observation'))
    for who in ('a', 'b'):
        for i, comp in enumerate(observation['observation_complexes']['people'][who]):
            core, context = set(comp['core_members']), set(comp['members'])-set(comp['core_members'])
            def collect(index, members):
                return sorted({ref for p in members for ref in index.get((who, p), [])})
            core_t, ctx_t = collect(timing_index, core), collect(timing_index, context)
            if not core_t and not ctx_t:
                continue
            core_p, ctx_p = collect(static_index, core), collect(static_index, context)
            complex_entries.append(dict(person=who, complex_ref=f'/observation_complexes/people/{who}/{i}',
                core_timing_contact_refs=core_t, context_timing_contact_refs=ctx_t,
                core_partner_contact_refs=core_p, context_partner_contact_refs=ctx_p,
                time_and_partner_both_touch_core=bool(core_t and core_p),
                whole_complex_activation_inferred=False, rule_id='timing_observation'))
    for i, row in enumerate(observation['contacts']):
        a = transit_index.get(('a', row['first_point']), [])
        b = transit_index.get(('b', row['second_point']), [])
        if a or b:
            transit_cross.append(dict(contact_ref='/contacts/'+str(i), a_transit_contact_refs=a,
                b_transit_contact_refs=b, both_endpoints_contacted=bool(a and b),
                rule_id='timing_observation'))
    result = dict(status='computed', scope='one_selected_time_snapshot', sources=deepcopy(sources), contacts=contacts,
        node_conventions=dict(natal=observation['settings']['node_type'], transit=cfg['node_type'], progressed=cfg['node_type'],
                              same_convention=observation['settings']['node_type'] == cfg['node_type']),
        window_scan=dict(status='not_computed', reason='source_calculation_required' if cfg['window'] else 'not_requested'),
        natal_point_entries=point_entries, natal_complex_entries=complex_entries,
        transits_to_synastry_endpoints=transit_cross,
        counts=dict(unique_timing_contacts=len(contacts)),
        availability=dict(progressed_synastry='computed' if cfg['include_progressed_synastry'] else 'not_requested',
            monthly_presence_absence='not_computed', interval_presence_absence='not_computed', exact_pass_search='not_computed',
            symbolic_carrier_matching='not_computed', automatic_childbirth_date='not_computed'),
        policy=dict(rule_id='timing_observation', static_contact_counts_changed=False, counts_are_additive=False,
            whole_complex_activation_inferred=False, recursive_expansion=False,
            applying='not_computed', strength_or_priority_score=None, predictions_generated=False,
            time_precision=cfg['precision'], date_scope='single_sample_only',
            transits_have_no_person_owner=True, progressed_point_positions_are_not_natal_positions=True))
    from services.relationship_observation_childbirth import childbirth_view
    result['childbirth_observation'] = childbirth_view(observation, result)
    if result['childbirth_observation']['status'] == 'computed':
        result['availability']['automatic_childbirth_date'] = 'computed_from_declared_child_birth'
    from services.relationship_observation_progressed_comparison import progressed_synastry_comparison
    result['progressed_synastry_comparison'] = progressed_synastry_comparison(observation, result)
    result['availability']['progressed_synastry_comparison'] = result['progressed_synastry_comparison']['status']
    return result
