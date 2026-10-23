"""Server-side MCP output contracts; passing is NOT proof of algorithm correctness.

Every data tool is explicitly registered. Invalid results are withheld, not
returned alongside an error. No reports, birth inputs or snapshots are stored.
"""
from datetime import date, datetime, timezone
import math
from zoneinfo import ZoneInfo

VERSION = 'mcp-output-contracts-v1'
SIGNS = ('白羊座','金牛座','双子座','巨蟹座','狮子座','处女座','天秤座','天蝎座','射手座','摩羯座','水瓶座','双鱼座')
PHASES = ('新月','娥眉月','上弦月','盈凸月','满月','亏凸月','下弦月','残月')
ASPECT_NAMES = {0: {'合','合相'},60:{'六分','六分相','六合相'},90:{'刑','刑相','四分','四分相'},
                120:{'拱','拱相','三分','三分相'},150:{'梅花','梅花相','梅花相位'},180:{'冲','冲相','对分','对分相'}}
# Explicit registry: a newly exposed calculation cannot silently bypass checks.
CONTRACTS = {
    'calculate_natal_salience': ('natal_salience', {'schema_version':str, 'completeness':str, 'birth_context':dict, 'settings':dict, 'source_graph':dict, 'core_structures':list, 'priority_planets':list, 'planet_profiles':dict, 'candidate_planets':list, 'focus_selection':dict, 'attention_layers':dict, 'planet_condition_assessments':dict, 'relationship_views':dict, 'jones_view':dict, 'view_comparison':dict, 'priority_aspects':list, 'priority_configurations':list, 'house_ruler_links':list, 'global_distribution':dict, 'evidence_index':dict, 'reading_plan':dict, 'evidence_matrix':dict, 'resource_checks':dict, 'priority_decisions':dict, 'resource_decisions':dict, 'reception_facts':dict, 'aspect_dynamics':dict, 'supplementary_contacts':dict, 'policy_comparison':dict, 'selection_audit':list, 'availability':dict, 'method':dict, 'layer_availability':dict, 'interpretations':list}, 'tests/test_natal_salience.py'),
    'calculate_natal_structure_graph': ('natal_structure', {'schema_version': str, 'completeness': str, 'birth_context': dict, 'settings': dict, 'nodes': list, 'facts': dict, 'dispositor': dict, 'aspects': dict, 'houses': dict, 'conditions': dict, 'receptions': dict, 'layer_availability': dict, 'interpretations': list}, 'tests/test_mcp_structure_graph.py'),
    "scan_planetary_aspects": ("planetary_scan", {"settings": dict, "event_count": int, "events": list, "windows": list, "year_summary": list}, "tests/test_planetary_aspect_scan.py"),
    'search_birthplace': ('location', {'options': list}, 'tests/test_mcp_natal.py'),
    'resolve_birth_coordinates': ('location', {'location_id': str, 'lat': float, 'lng': float, 'timezone': str}, 'tests/test_mcp_guardrails.py'),
    'calculate_natal_chart': ('natal', {'birth_context': dict, 'settings': dict, 'planets': list, 'axes': dict, 'house_cusps': list, 'aspects': list}, 'tests/test_mcp_natal.py'),
    'calculate_classical_factors': ('classical_jones', {'birth_context': dict, 'settings': dict, 'sect': str, 'sect_light': str, 'planet_condition': dict, 'lots': list, 'jones_pattern': dict, 'moon_phase': dict, 'sect_light_triplicity': dict}, 'tests/test_jones_pattern.py'),
    'calculate_zodiacal_releasing': ('releasing', {'birth_context': dict, 'settings': dict, 'as_of': str, 'lots': dict}, 'tests/test_zodiacal_releasing.py'),
    'calculate_time_lords': ('time_lords', {'birth_context': dict, 'as_of': str, 'firdaria': dict, 'annual_profections': dict}, 'tests/test_time_lords.py'),
    'calculate_solar_arc': ('solar_arc', {'birth_context': dict, 'settings': dict, 'aspect_matrix': list, 'axis_contacts_by_directed_points': list, 'directed_axes_to_natal_points': list, 'directed_positions_at_wheel_age': dict, 'cross_aspects_at_wheel_age': list}, 'tests/test_solar_arc_matrix.py'),
    'calculate_transits_to_natal': ('transit_events', {'birth_context': dict, 'settings': dict, 'event_count': int, 'events': list}, 'tests/test_transit_lifetime.py'),
    'calculate_timeline_synthesis': ('timeline_synthesis', {'birth_context': dict, 'engine_version': str, 'settings': dict, 'event_count': int, 'events': list, 'resonances': list}, 'tests/test_timeline_synthesis.py'),
    'get_transit_snapshot': ('transit_snapshot', {'birth_context': dict, 'moment': str, 'transit_positions': dict, 'active_aspects_to_natal': list}, 'tests/test_transit_natal.py'),
    'calculate_saturn_jupiter_cycles': ('cycles', {'birth_context': dict, 'as_of': str, 'natal': dict, 'range': dict, 'saturn_events': list, 'jupiter_events': list, 'aspects': list, 'saturn_phases': list, 'jupiter_phases': list, 'stats': dict, 'current': dict}, 'tests/test_transit_golden_cases.py'),
    'calculate_house_ingresses': ('ingresses', {'birth_context': dict, 'settings': dict, 'events': list, 'event_count': int}, 'tests/test_transit_lifetime.py'),
    'calculate_progressed_lunation': ('progressed', {'birth_context': dict, 'as_of': str, 'phase': dict, 'timeline': list, 'settings': dict}, 'tests/test_progressed_phase.py'),
    'calculate_solar_return': ('return', {'birth_context': dict, 'solar_return': dict, 'chart': dict, 'overlay_with_natal': dict, 'focus': dict, 'monthly_moon_progressions': dict}, 'tests/test_solar_return.py'),
    'calculate_lunar_return': ('lunar_return', {'birth_context': dict, 'lunar_return': dict, 'chart': dict, 'overlay_with_natal': dict, 'focus': dict}, 'tests/test_lunar_return.py'),
    'calculate_secondary_progressions': ('secondary_progressions', {'birth_context': dict, 'settings': dict, 'progressed_chart': dict, 'progressed_to_natal_aspects': list, 'progressed_ephemeris_date': str}, 'tests/test_secondary_progressions.py'),
    'calculate_relationship_charts': ('relationship', {'birth_context': dict, 'settings': dict, 'synastry_aspects': list, 'a_planets_in_b_houses': dict, 'b_planets_in_a_houses': dict, 'composite_chart': dict, 'composite_to_natal_aspects': dict}, 'tests/test_relationship_charts.py'),
    'get_current_sky': ('sky', {'timestamp': str, 'moon_phase': dict, 'moon': dict, 'sun': dict, 'voc': dict, 'retrograde_planets': list, 'planet_aspects_active': list}, 'tests/test_sky_now.py'),
    'calculate_house_rulers': ('rulers', {'birth_context': dict, 'settings': dict, 'houses': list}, 'tests/test_natal_house_rulers.py'),
    'calculate_zodiacal_releasing_l4': ('releasing_l4', {'birth_context': dict, 'as_of': str, 'lot': str, 'parent_period': dict, 'level4': list}, 'tests/test_zodiacal_releasing.py'),
    'calculate_lifetime_transit_summary': ('lifetime', {'birth_context': dict, 'settings': dict, 'total_events': int, 'chapters': list, 'totals_by_group': dict, 'totals_by_target': dict, 'totals_by_aspect': list}, 'tests/test_transit_lifetime.py'),
    'calculate_aspect_windows': ('windows', {'moment': str, 'location_id': str, 'aspect_count': int, 'aspects': list}, 'tests/test_aspect_windows.py'),
    'calculate_sky_chart': ('sky_chart', {'moment': str, 'location': dict, 'settings': dict, 'planets': list, 'house_cusps': list, 'axes': dict, 'aspects': list, 'moon_phase': dict, 'planet_motion': list}, 'tests/test_mcp_natal.py'),
    'calculate_davison_chart': ('davison', {'birth_context': dict, 'settings': dict, 'midpoint_space_time': dict, 'chart': dict, 'aspects': list}, 'tests/test_davison_chart.py'),
    'calculate_relocation_chart': ('relocation', {'birth_context': dict, 'settings': dict, 'relocation_location': dict, 'angular_shifts': dict, 'axes': dict, 'house_cusps': list, 'planets': list, 'aspects': list}, 'tests/test_relocation_chart.py'),
    'calculate_lots': ('lots', {'birth_context': dict, 'settings': dict, 'sect': str, 'lots': list}, 'tests/test_classical_engine.py'),
}
# Images get a checked numerical companion BEFORE rendering. Pixel/label layout
# still requires visual tests; image presence never proves chart correctness.
RENDER_SOURCES = {
    'render_natal_chart': 'calculate_natal_chart',
    'render_jones_pattern': 'calculate_classical_factors',
    'render_solar_return_chart': 'calculate_solar_return',
    'render_lunar_return_chart': 'calculate_lunar_return',
    'render_secondary_progressions_chart': 'calculate_secondary_progressions',
    'render_composite_chart': 'calculate_relationship_charts',
    'render_sky_chart': 'calculate_sky_chart',
    'render_transit_biwheel': 'get_transit_snapshot',
    'render_solar_arc_biwheel': 'calculate_solar_arc',
    'render_davison_chart': 'calculate_davison_chart',
    'render_relocation_chart': 'calculate_relocation_chart',
    'render_saturn_jupiter_cycles': 'calculate_saturn_jupiter_cycles',
}

# Metadata tools are audited separately from calculation tools: they do not
# produce calculation_reference values or enter the claim-recomputation registry.
META_CONTRACTS = {
    'calculate_natal_structure_graph': ('natal_structure', {'schema_version': str, 'completeness': str, 'birth_context': dict, 'settings': dict, 'nodes': list, 'facts': dict, 'dispositor': dict, 'aspects': dict, 'houses': dict, 'conditions': dict, 'receptions': dict, 'layer_availability': dict, 'interpretations': list}, 'tests/test_mcp_structure_graph.py'),
    'get_capabilities': {'schema_version': str, 'versions': dict,
                         'tool_count': int, 'tools': list, 'algorithm_registry': dict},
    'get_agent_protocol': {'schema_version': str, 'uri': str, 'content': str},
    'recommend_workflow': {'goal': str, 'label': str,
                           'required_information': list, 'steps': list,
                           'first_calculation_tool': str, 'boundary': str},
}


def number(v):
    return type(v) in (int, float) and math.isfinite(v)


def pointer(parts):
    return '/' + '/'.join(str(p).replace('~','~0').replace('/','~1') for p in parts)


class InvalidOutput(ValueError):
    def __init__(self, path, rule):
        self.path, self.rule = path, rule
        super().__init__(rule)


def require(ok, path, rule):
    if not ok:
        raise InvalidOutput(path, rule)


def fields(obj, spec, path=''):
    require(isinstance(obj, dict), path, 'expected_object')
    for key, typ in spec.items():
        v = obj.get(key)
        good = number(v) if typ is float else type(v) is typ
        require(good, path + '/' + key, 'missing_or_invalid_field')


def instant(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def longitude(v, path):
    require(number(v) and 0 <= v < 360, path, 'longitude_0_to_360')


def house(v, path):
    require(type(v) is int and 1 <= v <= 12, path, 'house_1_to_12')


def walk(value, parts=()):
    """Finite values, typed houses/motion, geometric sign consistency everywhere."""
    path = pointer(parts)
    if isinstance(value, float):
        require(math.isfinite(value), path, 'finite_number')
    elif isinstance(value, list):
        for i, v in enumerate(value): walk(v, (*parts, i))
    elif isinstance(value, dict):
        for k, v in value.items():
            p = pointer((*parts,k))
            if v is not None:
                if k in ('longitude','lon','cusp_longitude','sun_lon','moon_lon'):
                    longitude(v,p)
                elif k in ('house','natal_house','entered_house','left_house'):
                    house(v,p)
                elif k in ('retrograde','is_current','applying'):
                    require(type(v) is bool,p,'boolean_flag')
                elif k in ('orb','orb_limit'):
                    require(number(v) and v >= 0,p,'nonnegative_orb')
            walk(v,(*parts,k))
        lon = value.get('longitude',value.get('lon'))
        sign = value.get('sign',value.get('sign_zh',value.get('sign_cn')))
        if number(lon) and isinstance(sign,str):
            # Values may be rounded to 4 decimals at a boundary; accept either
            # adjacent sign only within that rounding precision.
            candidates = {SIGNS[int(((lon+d)%360)//30)] for d in (-0.000051,0,0.000051)}
            normalized = sign if sign.endswith('座') else sign+'座'
            require(normalized in candidates,path,'sign_matches_longitude')
        if number(value.get('orb')) and number(value.get('orb_limit')):
            require(value['orb'] <= value['orb_limit'] + .001,path,'orb_within_limit')
        if 'angle' in value and isinstance(value.get('aspect'),str):
            angle=value['angle']
            require(number(angle) and angle in ASPECT_NAMES and value['aspect'] in ASPECT_NAMES[angle],path,'aspect_name_matches_angle')


def context(ctx, args, path='/birth_context'):
    fields(ctx, {'lat':float,'lng':float,'tz_iana':str,'civil_dt':str,'fold':int},path)
    require(-90 <= ctx['lat'] <= 90 and -180 <= ctx['lng'] <= 180,path,'coordinates_in_range')
    require(ctx['fold'] in (0,1),path+'/fold','dst_fold')
    ZoneInfo(ctx['tz_iana'])
    local = instant(ctx['civil_dt'])
    for key in ('year','month','day','hour','minute'):
        if args.get(key) is not None:
            require(getattr(local,key)==args[key],path+'/civil_dt','birth_input_matches_output')
    if args.get('fold') is not None:
        require(ctx['fold']==args['fold'],path+'/fold','resolved_fold_matches_input')


def phase(p, path):
    fields(p, {'phase_num':int,'phase_name':str,'angle_diff':float},path)
    a = p['angle_diff']; longitude(a,path+'/angle_diff')
    i = p['phase_num'] - 1
    require(0 <= i < 8 and p['phase_name']==PHASES[i],path,'rudhyar_phase_name')
    # Compact sky data round angle_diff to 2 decimals.
    choices = {int(((a+d)%360)//45) for d in (-.0051,0,.0051)}
    require(i in choices,path,'rudhyar_45_degree_boundary')
    if number(p.get('sun_lon')) and number(p.get('moon_lon')):
        require(abs(((p['moon_lon']-p['sun_lon']-a+180)%360)-180)<.002,path,'phase_elongation')


def cusp_list(cusps,path):
    require(type(cusps) is list and len(cusps)==12,path,'twelve_cusps')
    vals = [c['longitude'] if isinstance(c,dict) else c for c in cusps]
    for i,v in enumerate(vals): longitude(v,path+'/'+str(i))
    widths=[(vals[(i+1)%12]-v)%360 for i,v in enumerate(vals)]
    require(all(0 < w < 180 for w in widths) and abs(sum(widths)-360)<.01,path,'ordered_cusps_one_circle')
    return vals


def chart(data,path=''):
    fields(data,{'planets':list,'axes':dict,'house_cusps':list,'aspects':list},path)
    require(len(data['planets'])>=10,path+'/planets','planet_table_incomplete')
    names=[p.get('key',p.get('name')) for p in data['planets']]
    require(None not in names and len(set(names))==len(names),path+'/planets','unique_planets')
    cusps=cusp_list(data['house_cusps'],path+'/house_cusps')
    for i,p in enumerate(data['planets']):
        fields(p,{'longitude':float,'sign':str,'house':int,'retrograde':bool},path+'/planets/'+str(i))
        h=p['house']-1; width=(cusps[(h+1)%12]-cusps[h])%360
        delta=(p['longitude']-cusps[h])%360
        # Allow endpoint rounding, but do not silently shift house systems.
        require(delta <= width+.002 or delta >= 359.998,path+'/planets/'+str(i)+'/house','house_matches_cusps')
    axes=data['axes']
    require({'asc','dsc','mc','ic'} <= axes.keys(),path+'/axes','four_axes')
    for a,b in [('asc','dsc'),('mc','ic')]:
        x=axes[a].get('longitude',axes[a].get('lon')); y=axes[b].get('longitude',axes[b].get('lon'))
        longitude(x,path+'/axes/'+a); longitude(y,path+'/axes/'+b)
        require(abs((y-x)%360-180)<.002,path+'/axes','opposite_axes')
    positions={p.get('key',p.get('name')):p['longitude'] for p in data['planets']}
    positions.update({k:v.get('longitude',v.get('lon')) for k,v in axes.items()})
    for alias,key in {'ascendant':'asc','descendant':'dsc','midheaven':'mc','imum_coeli':'ic',
                      'part_of_fortune':'pars_fortuna','part_of_spirit':'pars_spiritus',
                      'true_north_lunar_node':'north_node','true_south_lunar_node':'south_node'}.items():
        if key in positions: positions[alias]=positions[key]
    aspect_geometry(data['aspects'],positions,path+'/aspects')


def aspect_geometry(rows,positions,path):
    for i,a in enumerate(rows):
        first=a.get('point1',a.get('first','').split(':')[-1])
        second=a.get('point2',a.get('second','').split(':')[-1])
        # Sky-chart projection names planets in Chinese, while aspects use keys.
        from services.mcp_facts import _POINTS
        names={**_POINTS,'part_of_fortune':'福点','part_of_spirit':'精神点',
               'midheaven':'中天','imum_coeli':'天底','ascendant':'上升点','descendant':'下降点',
               'true_north_lunar_node':'北交点','true_south_lunar_node':'南交点'}
        x=positions.get(first,positions.get(names.get(first)))
        y=positions.get(second,positions.get(names.get(second)))
        require(number(x) and number(y),path+'/'+str(i),'aspect_points_present')
        separation=abs((x-y+180)%360-180)
        require(number(a.get('angle')) and number(a.get('orb')) and
                abs(abs(separation-a['angle'])-a['orb'])<.003,path+'/'+str(i),'aspect_orb_matches_positions')


def periods(rows,path,level=None):
    require(type(rows) is list,path,'period_list')
    prev=None
    for i,p in enumerate(rows):
        q=path+'/'+str(i)
        fields(p,{'start':str,'end':str,'is_current':bool},q)
        start,end=instant(p['start']),instant(p['end'])
        # L4 may expose two instants rounded to the same civil date.
        require(start<=end,q,'period_start_before_end')
        if prev is not None: require(prev<=start,q,'periods_nonoverlapping')
        prev=end
        if level is not None: require(p.get('level')==level,q,'release_level_matches')
        if 'age_start' in p:
            require(number(p['age_start']) and number(p.get('age_end')) and p['age_start']<=p['age_end'],q,'period_age_order')
    require(sum(p['is_current'] for p in rows)<=1,path,'at_most_one_current_period')


def sorted_dates(rows,key,path):
    vals=[instant(r[key]) for r in rows]
    require(vals==sorted(vals),path,'chronological_order')


def domain_checks(tool,d,args):
    family=CONTRACTS[tool][0]
    if 'birth_context' in d:
        if family in ('relationship', 'davison'):
            for who in ('a','b'): context(d['birth_context'][who],args.get('person_'+who) or {},'/birth_context/'+who)
        else: context(d['birth_context'],args)
    if args.get('house_system') and 'settings' in d and 'house_system' in d['settings']:
        require(d['settings']['house_system']==args['house_system'],'/settings/house_system','house_system_matches_input')
    if args.get('as_of') and 'as_of' in d:
        require(d['as_of']==args['as_of'],'/as_of','reference_date_matches_input')
    if args.get('moment'):
        stamp=d.get('moment',d.get('timestamp'))
        if stamp: require(instant(stamp)==instant(args['moment']),'/moment','instant_matches_input')
    if family=='planetary_scan':
        require(d['event_count'] >= 0, '/event_count', 'nonnegative_count')
        if d['settings']['output_precision'] != 'year_summary':
            require(d['event_count']==len(d['events']), '/events', 'count_matches')
        for i, row in enumerate(d['events']):
            path='/events/'+str(i)
            fields(row, {'planet_a':str,'planet_b':str,'aspect_degree':float,
                         'longitude_a':float,'longitude_b':float,'angular_difference':float,
                         'hit_index':int,'cycle_group_id':str,'retrograde_a':bool,'retrograde_b':bool}, path)
            require(row['planet_a']==d['planet_a'] and row['planet_b']==d['planet_b'],path,'pair_matches')
            require(row['hit_index']>=1,path,'positive_hit_index')
            require(0<=row['longitude_a']<360 and 0<=row['longitude_b']<360,path,'longitude_range')
            require(abs(row['angular_difference']-row['aspect_degree'])<0.00002,path,'exact_residual')
    elif family=='location':
        rows=d.get('options',[d])
        require(bool(rows),'/options','nonempty_location_result')
        for row in rows:
            require(bool(row.get('location_id')),'/location_id','canonical_location_required')
        if 'lat' in d:
            require(-90<=d['lat']<=90 and -180<=d['lng']<=180,'/lat','coordinates_in_range'); ZoneInfo(d['timezone'])
    elif family in ('natal','sky_chart'):
        chart(d)
        if family=='sky_chart': phase(d['moon_phase'],'/moon_phase')
    elif family=='classical_jones':
        require(d['sect'] in ('日生人','夜生人'),'/sect','known_sect')
        require(d['sect_light']==('太阳' if d['sect']=='日生人' else '月亮'),'/sect_light','sect_light_matches')
        require(len(d['lots'])==2 and {v['name'] for v in d['lots']}=={'福点','精神点'},'/lots','two_named_lots')
        phase(d['moon_phase'],'/moon_phase')
        j=d['jones_pattern']; fields(j,{'pattern_en':str,'pattern_zh':str,'key_roles':list,'max_gap_deg':float,'span_deg':float,'sorted_gaps_deg':list},'/jones_pattern')
        require(len(j['sorted_gaps_deg'])==10 and abs(sum(j['sorted_gaps_deg'])-360)<.01,'/jones_pattern/sorted_gaps_deg','ten_gaps_one_circle')
        require(abs(j['span_deg']+j['max_gap_deg']-360)<.03,'/jones_pattern','span_plus_gap_360')
        require(abs(max(j['sorted_gaps_deg'])-j['max_gap_deg'])<.02,'/jones_pattern/max_gap_deg','maximum_gap_matches')
        for r in j['key_roles']: fields(r,{'planet_name':str,'role_type':str,'role_label':str,'longitude':float},'/jones_pattern/key_roles')
        if j.get('high_focus_planet'):
            require(any(r['planet_name']==j['high_focus_planet'] for r in j['key_roles']),'/jones_pattern/high_focus_planet','focus_has_explicit_role')
    elif family=='releasing':
        require(set(d['lots'])=={'fortune','spirit'},'/lots','both_release_lots')
        for key,lot in d['lots'].items():
            for level,field in enumerate(('level1','level2_in_current_level1','level3_in_current_level2'),1): periods(lot[field],'/lots/'+key+'/'+field,level)
    elif family=='releasing_l4': periods(d['level4'],'/level4',4)
    elif family=='time_lords':
        periods(d['firdaria']['major_periods'],'/firdaria/major_periods')
        periods(d['firdaria']['sub_periods_in_current_major'],'/firdaria/sub_periods_in_current_major')
        rows=d['annual_profections']['years']; periods(rows,'/annual_profections/years')
        for r in rows: require(r['house']==r['age']%12+1,'/annual_profections/years','annual_house_from_age')
    elif family=='solar_arc':
        s=d['settings']; require(0<=s['age_from']<s['age_to']<=80,'/settings','solar_arc_age_bounds')
        require(s['wheel_date']==args['as_of'],'/settings/wheel_date','reference_date_matches_input')
        require(bool(d['directed_positions_at_wheel_age']['planets']),'/directed_positions_at_wheel_age','directed_positions_present')
        for r in d['aspect_matrix']:
            require(s['age_from']-.02<=r['age']<=s['age_to']+.02,'/aspect_matrix','event_inside_age_range')
            require(r['angle'] in (0,90,180),'/aspect_matrix','hard_aspect_angle')
    elif family in ('transit_events','ingresses'):
        require(d['event_count']==len(d['events']),'/event_count','count_matches_rows')
        for r in d['events']:
            t=instant(r['exact_utc'])
            if args.get('from_date'): require(t.date()>=date.fromisoformat(args['from_date']),'/events','event_after_range_start')
            if args.get('to_date'): require(t.date()<=date.fromisoformat(args['to_date']),'/events','event_before_range_end')
            if family=='ingresses': require(r['entered_house']!=r['left_house'],'/events','ingress_changes_house')
    elif family=='timeline_synthesis':
        from services.timeline_synthesis import NATURES, TECHNIQUE_PRIORITY, WEIGHTS, _sort_key
        s=d['settings']
        require(s['target_year']==args['target_year'] and s['span_years']==args['span_years'],
                '/settings','timeline_window_matches_input')
        require(1<=s['span_years']<=3 and s['timezone']==d['birth_context']['tz_iana'],
                '/settings','timeline_window_and_timezone')
        require(d['event_count']==len(d['events']),'/event_count','count_matches_rows')
        require(d['events']==sorted(d['events'],key=_sort_key),'/events','stable_event_order')
        zone=ZoneInfo(s['timezone'])
        for i,row in enumerate(d['events']):
            path=f'/events/{i}'
            fields(row,{'index':int,'technique':str,'nature':str,'weight':str,
                        'date':str,'exact_utc':str,'local_at':str,'time_precision':str,
                        'focus':str,
                        'source':dict},path)
            require(row['index']==i and row['technique'] in TECHNIQUE_PRIORITY
                    and row['nature'] in NATURES and row['weight'] in WEIGHTS
                    and row['time_precision'] in ('minute','second'),
                    path,'timeline_event_enums_and_index')
            utc=instant(row['exact_utc'])
            local=instant(row['local_at'])
            require(utc.tzinfo is not None and utc.utcoffset().total_seconds()==0
                    and local.tzinfo is not None and local==utc.astimezone(zone)
                    and local.utcoffset()==utc.astimezone(zone).utcoffset()
                    and row['date']==local.date().isoformat()
                    and s['target_year']<=local.year<s['target_year']+s['span_years'],
                    path,'timeline_event_instant_and_calendar')
            source=row['source']
            if row['weight']!='exact':
                opened=instant(source['start_utc']); closed=instant(source['end_utc'])
                require(opened.tzinfo is not None and closed.tzinfo is not None
                        and opened<=utc<closed,path+'/source','timeline_period_covers_event')
        for i,row in enumerate(d['resonances']):
            path=f'/resonances/{i}'
            fields(row,{'focus':str,'start_utc':str,'end_utc':str,
                        'techniques':list,'technique_count':int,
                        'event_indices':list,'event_count':int},path)
            indices=row['event_indices']
            require(bool(indices) and len(set(indices))==len(indices)
                    and all(type(j) is int and 0<=j<len(d['events']) for j in indices),
                    path+'/event_indices','resonance_valid_unique_sources')
            sources=[d['events'][j] for j in indices]
            techniques=sorted({e['technique'] for e in sources},key=TECHNIQUE_PRIORITY.__getitem__)
            require(all(e['focus']==row['focus'] for e in sources)
                    and row['techniques']==techniques and len(techniques)>=2
                    and row['technique_count']==len(techniques)
                    and row['event_count']==len(sources)
                    and instant(row['start_utc'])<=instant(row['end_utc']),
                    path,'resonance_matches_source_events')
    elif family=='transit_snapshot':
        require(len(d['transit_positions'])>=10,'/transit_positions','transit_planets_present')
    elif family=='cycles':
        for key,field in [('saturn_count','saturn_events'),('jupiter_count','jupiter_events'),('aspect_count','aspects')]:
            require(d['stats'][key]==len(d[field]),'/stats/'+key,'count_matches_rows')
            sorted_dates(d[field],'utc_datetime','/'+field)
        for field in ('saturn_phases','jupiter_phases'):
            for r in d[field]: require(r['start_age']<=r['end_age'],'/'+field,'cycle_age_order')
    elif family=='progressed':
        phase(d['phase'],'/phase'); sorted_dates(d['timeline'],'date','/timeline')
        for r in d['timeline']:
            require(1<=r['phase_num']<=8 and r['phase_name']==PHASES[r['phase_num']-1],'/timeline','phase_label_matches_number')
    elif family=='lunar_return':
        lr=d['lunar_return']; require(lr['house_system']==args.get('house_system','placidus'),'/lunar_return/house_system','house_system_matches_input')
        require(lr['residence_location_id']==args['residence_location_id'],'/lunar_return/residence_location_id','return_location_matches_input')
        local_return = instant(lr['local'])
        require(local_return.year==args['target_year'],'/lunar_return/local','return_year_matches_input')
        require(local_return.month==args['target_month'],'/lunar_return/local','return_month_matches_input')
        c=d['chart']; cusp_list(c['house_cusps'],'/chart/house_cusps')
        require(len(c['planets'])>=10,'/chart/planets','return_planets_present')
        require(abs((c['planets']['moon']['longitude']-lr['natal_moon_longitude']+180)%360-180)<.0002,
                '/chart/planets/moon/longitude','moon_return_matches_natal_longitude')
        lunation=c['lunation_phase']
        require(1<=lunation['phase_num']<=8 and lunation['phase_name']==PHASES[lunation['phase_num']-1],
                '/chart/lunation_phase','rudhyar_phase_name')
        require(abs((c['planets']['moon']['longitude']-c['planets']['sun']['longitude']-lunation['elongation']+180)%360-180)<.0002,
                '/chart/lunation_phase/elongation','phase_matches_planets')
        positions={k:v['longitude'] for k,v in c['planets'].items()}
        positions.update({k:v['longitude'] for k,v in c['angles'].items()})
        positions.update({short:positions[long] for short,long in
                          [('asc','ascendant'),('dsc','descendant'),('mc','midheaven'),('ic','imum_coeli')] if long in positions})
        aspect_geometry(c['aspects'],positions,'/chart/aspects')
    elif family=='secondary_progressions':
        s=d['settings']; require(s['house_system']==args.get('house_system','placidus'),'/settings/house_system','house_system_matches_input')
        require(s['angle_progression_method']==args.get('angle_progression_method','naibod'),'/settings/angle_progression_method','progression_method_matches_input')
        require(0<=s['age']<=120,'/settings/age','age_in_range')
        if args.get('age') is not None:
            require(abs(s['age']-args['age'])<.0001,'/settings/age','age_matches_input')
        if args.get('as_of') is not None:
            require(s['as_of']==args['as_of'],'/settings/as_of','date_matches_input')
        c=d['progressed_chart']
        cusp_list(c['house_cusps'],'/progressed_chart/house_cusps')
        require(len(c['planets'])>=10,'/progressed_chart/planets','progressed_planets_present')
        require({'ascendant','midheaven','descendant','imum_coeli'}<=c['axes'].keys(),'/progressed_chart/axes','progressed_axes_present')
        lunation=c['lunation_phase']
        require(1<=lunation['phase_num']<=8 and lunation['phase_name']==PHASES[lunation['phase_num']-1],
                '/progressed_chart/lunation_phase','rudhyar_phase_name')
        # Elongation is serialized to four decimals; permit only the adjacent
        # sector within half a last decimal at a 45-degree boundary.
        a = lunation['elongation']
        choices = {int(((a+delta)%360)//45) for delta in (-.00005, 0, .00005)}
        require(lunation['phase_num']-1 in choices,
                '/progressed_chart/lunation_phase','rudhyar_45_degree_boundary')
        require(abs((c['planets']['moon']['longitude']-c['planets']['sun']['longitude']-lunation['elongation']+180)%360-180)<.0002,
                '/progressed_chart/lunation_phase/elongation','phase_matches_planets')
    elif family=='return':
        sr=d['solar_return']; require(sr['house_system']==args['house_system'],'/solar_return/house_system','house_system_matches_input')
        require(sr['residence_location_id']==args['residence_location_id'],'/solar_return/residence_location_id','return_location_matches_input')
        require(instant(sr['utc']).year==args['target_year'],'/solar_return/utc','return_year_matches_input')
        c=d['chart']; cusp_list(c['house_cusps'],'/chart/house_cusps')
        require(len(c['planets'])>=10,'/chart/planets','return_planets_present')
        positions={k:v['longitude'] for k,v in c['planets'].items()}
        positions.update({k:v['longitude'] for k,v in c['angles'].items()})
        positions.update({short:positions[long] for short,long in
                          [('asc','ascendant'),('dsc','descendant'),('mc','midheaven'),('ic','imum_coeli')] if long in positions})
        aspect_geometry(c['aspects'],positions,'/chart/aspects')
    elif family=='relationship':
        require(d['settings']['orb_profile']==args.get('orb_profile','greene'),'/settings/orb_profile','orb_profile_matches_input')
        cusp_list(d['composite_chart']['house_cusps'],'/composite_chart/house_cusps')
        comp=d['composite_chart']
        positions={k:v['longitude'] for k,v in {**comp['planets'],**comp['axes']}.items()}
        aspect_geometry(comp['aspects'],positions,'/composite_chart/aspects')
        for field in ('a_planets_in_b_houses','b_planets_in_a_houses'):
            require(len(d[field])>=10,'/'+field,'both_overlay_tables_present')
            for k,v in d[field].items(): house(v,'/'+field+'/'+k)
        for a in d['synastry_aspects']:
            require(a['first'].startswith('A:') and a['second'].startswith('B:'),'/synastry_aspects','synastry_sides_explicit')
    elif family=='sky': phase(d['moon_phase'],'/moon_phase')
    elif family=='rulers':
        require([h['house'] for h in d['houses']]==list(range(1,13)),'/houses','twelve_house_chains')
        for h in d['houses']:
            require(bool(h['tracks']),'/houses/tracks','ruler_tracks_present')
            for t in h['tracks']:
                require(bool(t['chain']) and t['chain'][0]['planet']==t['house_ruler'],'/houses/tracks/chain','chain_starts_with_ruler')
    elif family=='lifetime':
        require(len(d['chapters'])==12,'/chapters','twelve_seven_year_chapters')
        require(sum(c['total'] for c in d['chapters'])==d['total_events'],'/total_events','chapter_total_matches')
        for c in d['chapters']:
            require(c['slow']+c['fast']==c['total']==c['axes']+c['points']==sum(c['planets'].values()),'/chapters','count_partitions_match')
    elif family=='windows':
        require(d['aspect_count']==len(d['aspects']),'/aspect_count','count_matches_rows')
        for r in d['aspects']:
            if all(number(r.get(k)) for k in ('total_days','elapsed_days','remaining_days')):
                require(min(r['total_days'],r['elapsed_days'],r['remaining_days'])>=0 and abs(r['elapsed_days']+r['remaining_days']-r['total_days'])<=.031,'/aspects','window_durations_add_up')
    elif family=='davison':
        st=d['midpoint_space_time']
        require('jd' in st and 'utc' in st and 'lat' in st and 'lng' in st, '/midpoint_space_time', 'midpoint_fields_present')
        require(-90 <= st['lat'] <= 90, '/midpoint_space_time/lat', 'latitude_in_range')
        require(-180 <= st['lng'] <= 180, '/midpoint_space_time/lng', 'longitude_in_range')
        c=d['chart']
        cusp_list(c['house_cusps'], '/chart/house_cusps')
        require(len(c['planets'])>=10, '/chart/planets', 'davison_planets_present')
        require({'ascendant', 'midheaven', 'descendant', 'imum_coeli'} <= c['axes'].keys(), '/chart/axes', 'davison_axes_present')
        if d['settings']['house_system']=='whole_sign':
            asc_sign=int(c['axes']['ascendant']['longitude']//30)
            require(int(c['house_cusps'][0])==asc_sign*30, '/chart/house_cusps/0', 'whole_sign_first_cusp')
            for key,p in c['planets'].items():
                expected=(int(p['longitude']//30)-asc_sign)%12+1
                require(p['house']==expected, '/chart/planets/'+key+'/house', 'whole_sign_house_matches_sign')
    elif family=='lots':
        require(d['sect'] in ('日生人', '夜生人'), '/sect', 'known_sect')
        require(isinstance(d['lots'], list) and len(d['lots']) > 0, '/lots', 'non_empty_lots')
        for lot in d['lots']:
            fields(lot, {'key': str, 'name_zh': str, 'longitude': float, 'sign': str, 'formula': str, 'reversed_at_night': bool}, '/lots')
    elif family=='relocation':
        rl=d['relocation_location']
        require(rl['location_id']==args['relocation_location_id'], '/relocation_location/location_id', 'relocation_location_matches_input')
        require(-90 <= rl['lat'] <= 90, '/relocation_location/lat', 'latitude_in_range')
        require(-180 <= rl['lng'] <= 180, '/relocation_location/lng', 'longitude_in_range')
        require('delta_asc_deg' in d['angular_shifts'] and 'delta_mc_deg' in d['angular_shifts'], '/angular_shifts', 'angular_shifts_present')
        require({'ascendant', 'midheaven', 'descendant', 'imum_coeli'} <= d['axes'].keys(), '/axes', 'relocation_axes_present')
        cusp_list(d['house_cusps'], '/house_cusps')
        require(len(d['planets'])>=10, '/planets', 'relocation_planets_present')
        if d['settings']['house_system']=='whole_sign':
            asc_sign=int(d['axes']['ascendant']['longitude']//30)
            require(int(d['house_cusps'][0])==asc_sign*30, '/house_cusps/0', 'whole_sign_first_cusp')
            for i,p in enumerate(d['planets']):
                expected=(int(p['longitude']//30)-asc_sign)%12+1
                require(p['relocated_house']==expected, f'/planets/{i}/relocated_house', 'whole_sign_house_matches_sign')
                require(isinstance(p['natal_house'],int) and 1<=p['natal_house']<=12,
                        f'/planets/{i}/natal_house', 'natal_house_present')
                require(p['house_changed']==(p['natal_house']!=p['relocated_house']),
                        f'/planets/{i}/house_changed', 'house_change_matches_houses')


def validate_output(tool, data, args):
    """Return bounded diagnostics only; never include invalid values or payloads."""
    try:
        require(tool in CONTRACTS,'/','tool_has_contract')
        require(isinstance(data,dict) and data.get('status')=='ok','/status','successful_result_required')
        fields(data,CONTRACTS[tool][1])
        if tool == 'calculate_natal_salience':
            from services.mcp_salience import validate_salience_output
            validate_salience_output(data,args)
        elif tool == 'calculate_natal_structure_graph':
            from services.mcp_structure_graph import validate_graph_output
            context(data['birth_context'], args)
            validate_graph_output(data)
        else:
            walk(data); domain_checks(tool,data,args)
    except InvalidOutput as exc:
        return [{'path':exc.path,'rule':exc.rule}]
    except (KeyError,TypeError,ValueError,IndexError,OverflowError):
        return [{'path':'/','rule':'incomplete_or_invalid_domain_structure'}]
    return []


def validate_meta_output(tool, data):
    """Check discovery/protocol results without treating input schemas as chart data."""
    try:
        require(tool in META_CONTRACTS, '/', 'meta_tool_has_contract')
        require(isinstance(data, dict) and data.get('status') == 'ok',
                '/status', 'successful_result_required')
        fields(data, META_CONTRACTS[tool])
        if tool == 'recommend_workflow':
            from services.mcp_envelope import registered_tools
            from services.mcp_workflow import WORKFLOWS
            require(data['goal'] in WORKFLOWS, '/goal', 'known_workflow_goal')
            require(bool(data['steps']), '/steps', 'nonempty_workflow')
            require(data['first_calculation_tool'] in registered_tools(),
                    '/first_calculation_tool', 'registered_calculation_tool')
            for row in data['steps']:
                fields(row, {'tool': str, 'when': str, 'purpose': str}, '/steps')
                require(row['tool'] in registered_tools(), '/steps/tool', 'registered_tool')
        if tool == 'get_capabilities':
            rows = data['tools']
            require(data['schema_version'] == 'mcp-capabilities-v1',
                    '/schema_version', 'known_capability_schema')
            require(data['tool_count'] == len(rows), '/tool_count', 'count_matches_tools')
            names = []
            for row in rows:
                fields(row, {'name': str, 'description': str, 'input_schema': dict,
                             'registered_algorithm_keys': list, 'provenance_coverage': str},
                       '/tools')
                names.append(row['name'])
            require(len(set(names)) == len(names), '/tools', 'unique_tool_names')
            from algorithm_registry import list_algorithms
            registry = list_algorithms()
            require(data['algorithm_registry'] == registry,
                    '/algorithm_registry', 'registry_matches_source')
            for row in rows:
                require(set(row['registered_algorithm_keys']) <= set(registry),
                        '/tools', 'registered_algorithm_keys_exist')
        elif tool == 'get_agent_protocol':
            require(data['schema_version'] == 'mcp-agent-protocol-v1',
                    '/schema_version', 'known_agent_protocol_schema')
            require(data['uri'] == 'hellenicstar://agent-protocol',
                    '/uri', 'known_agent_protocol_uri')
            require(bool(data['content'].strip()), '/content', 'nonempty_protocol')
    except InvalidOutput as exc:
        return [{'path': exc.path, 'rule': exc.rule}]
    except (KeyError, TypeError, ValueError):
        return [{'path': '/', 'rule': 'incomplete_or_invalid_meta_structure'}]
    return []


def blocked(tool, issues):
    return {'status':'validation_failed','tool':tool,'error':'计算结果未通过服务器检查，已阻止作为正常数据返回。',
            'issues':issues,'next_action':'report_calculation_error','retryable':False}
