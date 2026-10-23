"""Every exposed data family exercises real output checks and wrong-value rejection.

These are delivery/invariant regressions, not independent astronomical or
historical validation. Algorithm regression suites are included in tests/ and run by scripts/verify.sh.
"""
import asyncio
from copy import deepcopy
import inspect
import json

import pytest

from services.mcp_validation import CONTRACTS, META_CONTRACTS, RENDER_SOURCES, validate_output
from services.mcp_result_facts import checked_result, verify_calculation_claims_data, normalize_arguments, lookup

BIRTH=dict(year=1990,month=4,day=15,hour=18,minute=0,location_id='gn:2988507')
PARTNER=dict(year=1988,month=8,day=1,hour=9,minute=30,location_id='gn:2988507')
MOMENT='2026-10-08T12:00:00+08:00'
EXTRAS={
 'calculate_natal_salience':{},
 'calculate_relationship_observation':dict(person_a=BIRTH,person_b=PARTNER),
 'calculate_natal_structure_graph':{},
 "scan_planetary_aspects":dict(planet_a="Jupiter",planet_b="Saturn",start_date="2020-01-01",end_date="2020-12-31",aspects=[0]),
 'search_birthplace':dict(query='Paris'), 'resolve_birth_coordinates':dict(latitude=48.8566,longitude=2.3522),
 'calculate_natal_chart':dict(house_system='placidus'), 'calculate_classical_factors':dict(house_system='placidus'),
 'calculate_zodiacal_releasing':dict(as_of='2026-10-08'), 'calculate_time_lords':dict(as_of='2026-10-08',house_system='placidus'),
 'calculate_solar_arc':dict(as_of='2026-10-08'), 'calculate_transits_to_natal':dict(from_date='2026-01-01',to_date='2026-12-31'),
 'calculate_timeline_synthesis':dict(target_year=2026),
 'get_transit_snapshot':dict(moment=MOMENT), 'calculate_saturn_jupiter_cycles':dict(as_of='2026-10-08'),
 'calculate_house_ingresses':dict(from_date='2026-01-01',to_date='2026-12-31'), 'calculate_progressed_lunation':dict(as_of='2026-10-08'),
 'calculate_solar_return':dict(target_year=2026,residence_location_id=BIRTH['location_id'],house_system='placidus'),
 'calculate_lunar_return':dict(target_year=2026,target_month=4,residence_location_id=BIRTH['location_id'],house_system='placidus'),
 'calculate_secondary_progressions':dict(as_of='2026-04-15',house_system='placidus'),
 'calculate_relationship_charts':dict(person_a=BIRTH,person_b=PARTNER), 'get_current_sky':dict(moment=MOMENT),
 'calculate_house_rulers':dict(house_system='placidus'),
 'calculate_zodiacal_releasing_l4':dict(lot='fortune',parent_start='2026-08-24',parent_sign='GEMINI',as_of='2026-10-08'),
 'calculate_lifetime_transit_summary':{}, 'calculate_aspect_windows':dict(moment=MOMENT,location_id=BIRTH['location_id']),
 'calculate_sky_chart':dict(moment=MOMENT,location_id=BIRTH['location_id']),
 'calculate_davison_chart':dict(person_a=BIRTH,person_b=PARTNER,house_system='placidus'),
 'calculate_relocation_chart':dict(year=1990,month=4,day=15,hour=18,minute=0,location_id=BIRTH['location_id'],relocation_location_id='gn:5128581',house_system='placidus'),
 'calculate_lots':dict(house_system='whole_sign',lots=['fortune','spirit','eros']),
}
PATHS={
 'calculate_natal_salience':'/core_structures/0/denominator',
 'calculate_relationship_observation':'/counts/unique_contacts',
 'calculate_natal_structure_graph':'/dispositor/traditional/paths/sun/terminal',
 "scan_planetary_aspects":"/events/0/exact_datetime_utc",
 'search_birthplace':'/options/0/location_id', 'resolve_birth_coordinates':'/timezone',
 'calculate_natal_chart':'/planets/0/house', 'calculate_classical_factors':'/jones_pattern/high_focus_planet',
 'calculate_zodiacal_releasing':'/lots/fortune/level1/0/sign', 'calculate_time_lords':'/firdaria/major_periods/0/lord',
 'calculate_solar_arc':'/aspect_matrix/0/angle','calculate_transits_to_natal':'/events/0/exact_utc',
 'calculate_timeline_synthesis':'/events/0/date',
 'get_transit_snapshot':'/transit_positions/太阳/sign','calculate_saturn_jupiter_cycles':'/stats/saturn_count',
 'calculate_house_ingresses':'/events/0/entered_house','calculate_progressed_lunation':'/phase/phase_name',
 'calculate_solar_return':'/chart/planets/sun/house',
 'calculate_lunar_return':'/chart/planets/moon/house',
 'calculate_secondary_progressions':'/settings/method',
 'calculate_relationship_charts':'/a_planets_in_b_houses/太阳',
 'get_current_sky':'/moon_phase/phase_name','calculate_house_rulers':'/houses/0/tracks/0/house_ruler',
 'calculate_zodiacal_releasing_l4':'/level4/0/sign','calculate_lifetime_transit_summary':'/total_events',
 'calculate_aspect_windows':'/aspects/0/angle','calculate_sky_chart':'/planets/0/house',
 'calculate_davison_chart':'/chart/planets/sun/house','calculate_relocation_chart':'/axes/ascendant/sign',
 'calculate_lots':'/lots/0/name_zh',
}
# Each mutation is a realistic corrupted output, not merely a missing top key.
MUTATIONS={
 'calculate_natal_salience':('/core_structures/0/denominator',-1),
 'calculate_relationship_observation':('/counts/unique_contacts',-1),
 'calculate_natal_structure_graph':('/dispositor/traditional/paths/sun/terminal',['invalid']),
 "scan_planetary_aspects":("/events/0/angular_difference",12.0),
 'search_birthplace':('/options/0/location_id',''), 'resolve_birth_coordinates':('/lat',91),
 'calculate_natal_chart':('/planets/0/house',1), 'calculate_classical_factors':('/jones_pattern/high_focus_planet','不存在的星体'),
 'calculate_zodiacal_releasing':('/lots/fortune/level1/0/level',4), 'calculate_time_lords':('/annual_profections/years/0/house',13),
 'calculate_solar_arc':('/aspect_matrix/0/age',100), 'calculate_transits_to_natal':('/event_count',-1),
 'calculate_timeline_synthesis':('/event_count',-1),
 'get_transit_snapshot':('/transit_positions/太阳/sign','双鱼座'), 'calculate_saturn_jupiter_cycles':('/stats/saturn_count',-1),
 'calculate_house_ingresses':('/events/0/entered_house',0), 'calculate_progressed_lunation':('/phase/phase_num',1),
 'calculate_solar_return':('/solar_return/house_system','whole_sign'),
 'calculate_lunar_return':('/lunar_return/house_system','whole_sign'),
 'calculate_secondary_progressions':('/settings/house_system','whole_sign'),
 'calculate_relationship_charts':('/synastry_aspects/0/first','B:金星'),
 'get_current_sky':('/moon_phase/phase_num',1), 'calculate_house_rulers':('/houses/0/tracks/0/house_ruler','不存在的星体'),
 'calculate_zodiacal_releasing_l4':('/level4/0/level',1), 'calculate_lifetime_transit_summary':('/chapters/0/total',-1),
 'calculate_aspect_windows':('/aspects/0/remaining_days',-1), 'calculate_sky_chart':('/planets/0/house',13),
 'calculate_davison_chart':('/chart/house_cusps',[0]*12), 'calculate_relocation_chart':('/house_cusps',[0]*12),
 'calculate_lots':('/lots/0/longitude', -1.0),
}

@pytest.fixture(scope='module')
def samples():
 import mcp_server as m
 out={}
 for name,extra in EXTRAS.items():
  sig=inspect.signature(getattr(m,name)); args={**{k:v for k,v in BIRTH.items() if k in sig.parameters},**extra}
  for k in ('person_a','person_b'):
   if k in args: args[k]=m.BirthInput(**args[k])
  b=sig.bind_partial(**args); b.apply_defaults(); args=normalize_arguments(b.arguments)
  raw=getattr(m,name).__wrapped__(**args)
  out[name]=(raw,args)
 return out

@pytest.mark.parametrize('name',sorted(CONTRACTS))
def test_every_data_tool_checks_real_results_and_rejects_corruption(name,samples):
 raw,args=samples[name]; json_args={k:v.model_dump() if hasattr(v,'model_dump') else v for k,v in args.items()}
 assert raw['status']=='ok'
 assert validate_output(name,raw,json_args)==[]
 corrupt=deepcopy(raw); path,bad=MUTATIONS[name]; keys=path[1:].split('/'); parent=corrupt
 for key in keys[:-1]: parent=parent[int(key)] if isinstance(parent,list) else parent[key]
 key=int(keys[-1]) if isinstance(parent,list) else keys[-1]; parent[key]=bad
 rejected=checked_result(name,corrupt,args)
 assert rejected['status']=='validation_failed', (name,rejected)
 assert 'calculation_reference' not in rejected and 'birth_context' not in rejected

@pytest.mark.parametrize('name',sorted(CONTRACTS))
def test_every_family_can_verify_true_false_and_absent_source_claims(name,samples):
 raw,args=samples[name]; checked=checked_result(name,raw,args)
 assert checked['status']=='ok',checked
 path=PATHS[name]; actual=lookup(raw,path)
 claims=[dict(quote='测试事实',path=path,value=actual),dict(quote='错误事实',path=path,value='故意错误'),dict(quote='未提供',path='/missing_value',value=1)]
 out=verify_calculation_claims_data(checked['calculation_reference'],claims)
 assert out.get('counts')==dict(supported=1,contradicted=1,unverified=1),out
 assert out['coverage']['independent_algorithm_verification'] is False


def test_no_new_tool_can_skip_contract_registration():
 import mcp_server as m
 listed=asyncio.run(m.mcp.list_tools())
 assert {t.name for t in listed}==set(CONTRACTS)|set(META_CONTRACTS)|set(RENDER_SOURCES)|{'verify_natal_claims','verify_calculation_claims'}
 with pytest.raises(RuntimeError):
  @m.tool()
  def unregistered_algorithm(): return {'status':'ok'}


def test_reference_rejects_tampering_wrong_tool_and_moving_clock(samples):
 raw,args=samples['calculate_natal_chart']; ref=checked_result('calculate_natal_chart',raw,args)['calculation_reference']
 c=[dict(quote='太阳宫位',path='/planets/0/house',value=8)]
 altered=deepcopy(ref);altered['input']['house_system']='whole_sign'
 assert verify_calculation_claims_data(altered,c)['status']=='reference_mismatch'
 altered=deepcopy(ref);altered['tool']='verify_calculation_claims'
 assert verify_calculation_claims_data(altered,c)['status']=='invalid_reference'
 altered=deepcopy(ref);altered['input']['minute']=True
 assert verify_calculation_claims_data(altered,c)['status']=='invalid_reference'
 raw,args=samples['get_current_sky']; ref=checked_result('get_current_sky',raw,args)['calculation_reference'];ref['input']['moment']=None
 assert verify_calculation_claims_data(ref,c)['status']=='invalid_reference'


def test_finite_values_and_boolean_are_not_house_numbers(samples):
 raw,args=samples['calculate_natal_chart']
 for bad in (True,float('nan'),float('inf')):
  corrupt=deepcopy(raw);corrupt['planets'][0]['house']=bad
  assert checked_result('calculate_natal_chart',corrupt,args)['status']=='validation_failed'
 from services.mcp_result_facts import exact_equal
 assert not exact_equal(True,1)


def test_render_blocks_before_rendering_bad_source(monkeypatch,samples):
 import mcp_server as m
 from services.mcp_result_facts import REGISTRY
 original=REGISTRY['calculate_natal_chart']
 def bad_source(**args):
  raw=deepcopy(samples['calculate_natal_chart'][0]); raw['planets'][0]['house']=13; return raw
 bad_source.__signature__=inspect.signature(original)
 monkeypatch.setitem(REGISTRY,'calculate_natal_chart',bad_source)
 def never(**args): pytest.fail('invalid calculation must not be rendered')
 monkeypatch.setattr(m,'render_natal_chart_png',never)
 out=asyncio.run(m.render_natal_chart(**BIRTH,house_system='placidus'))
 assert out.structuredContent['status']=='validation_failed'
 assert len(out.content)==1

@pytest.mark.parametrize('name',sorted(RENDER_SOURCES))
def test_every_image_has_checked_numeric_source(name):
 import mcp_server as m
 sig=inspect.signature(getattr(m,name)); args={k:v for k,v in BIRTH.items() if k in sig.parameters}
 extra={
  'render_natal_chart':dict(house_system='whole_sign'), 'render_jones_pattern':{},
  'render_solar_return_chart':dict(target_year=2026,residence_location_id=BIRTH['location_id'],house_system='placidus'),
  'render_lunar_return_chart':dict(target_year=2026,target_month=4,residence_location_id=BIRTH['location_id'],house_system='placidus'),
  'render_secondary_progressions_chart':dict(as_of='2026-04-15',house_system='placidus'),
  'render_composite_chart':dict(person_a=m.BirthInput(**BIRTH),person_b=m.BirthInput(**PARTNER)),
  'render_sky_chart':dict(moment=MOMENT,location_id=BIRTH['location_id']),
  'render_transit_biwheel':dict(moment=MOMENT),
  'render_solar_arc_biwheel':dict(age=30,as_of='2026-10-08'),
  'render_davison_chart':dict(person_a=m.BirthInput(**BIRTH),person_b=m.BirthInput(**PARTNER),house_system='placidus'),
  'render_relocation_chart':dict(relocation_location_id='gn:5128581',house_system='placidus'),
  'render_saturn_jupiter_cycles':dict(as_of='2026-10-08',max_age=80),
 }[name]
 out=asyncio.run(getattr(m,name)(**{**args,**extra}))
 assert out.structuredContent['status']=='ok',out.structuredContent
 assert out.structuredContent['quality']['image_semantics_checked'] is False
 source=out.structuredContent['calculation_source']
 assert source['quality']['status']=='passed'
 assert source['calculation_reference']['tool']==RENDER_SOURCES[name]
 assert out.content[1].type=='image'
 if name=='render_solar_arc_biwheel': assert source['settings']['wheel_age']==30


def test_invalid_result_status_and_absent_required_sections_are_blocked(samples):
 for name,(raw,args) in samples.items():
  no_status=dict(raw); no_status.pop('status')
  assert checked_result(name,no_status,args)['status']=='validation_failed'
  for key in CONTRACTS[name][1]:
   broken=dict(raw);broken.pop(key)
   assert checked_result(name,broken,args)['status']=='validation_failed',(name,key)


def test_sky_chart_disambiguates_dst_from_requested_instant():
 import mcp_server as m
 # Both UTC instants map to 01:30 in New York; the offset selects the fold.
 for stamp,fold in [('2024-11-03T05:30:00+00:00',0),('2024-11-03T06:30:00+00:00',1)]:
  data=asyncio.run(m.calculate_sky_chart(moment=stamp,location_id='gn:5128581'))
  assert data['status']=='ok',data
  assert data['settings']['chart_moment'].endswith('-04:00' if fold==0 else '-05:00')


def test_reversed_transit_dates_are_input_errors():
 import mcp_server as m
 for name in ('calculate_transits_to_natal','calculate_house_ingresses'):
  data=asyncio.run(getattr(m,name)(**BIRTH,from_date='2026-02-02',to_date='2026-02-01'))
  assert data['status']=='invalid_input'


def test_fresh_worker_initializes_ephemeris_even_when_natal_is_cached():
 import concurrent.futures
 import swisseph as swe
 import mcp_server as m
 from services.ephemeris_guard import apply_ephe_path
 def fresh_worker():
  swe.set_ephe_path('/tmp/hellenicstar-intentionally-missing-ephemeris')
  try:
   _,flags=m._invoke_calculation(lambda: swe.calc_ut(swe.julday(2026,1,1),swe.CHIRON,swe.FLG_SWIEPH),{})
   return flags & swe.FLG_SWIEPH
  finally: apply_ephe_path()
 with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
  assert executor.submit(fresh_worker).result() == swe.FLG_SWIEPH
