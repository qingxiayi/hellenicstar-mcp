"""Policy and extra-point comparisons cannot silently change natal defaults."""
import copy
import asyncio
import pytest
from services.natal_structure_graph import calculate_structure_graph, StructureInputError
from services.natal_salience import build_salience
from services.natal_policy_context import policy_context, validate_supplementary

BIRTH=dict(year=2000,month=1,day=1,hour=12,minute=0,lat=39.9042,lng=116.4074)

@pytest.mark.parametrize('birth',[BIRTH,dict(BIRTH,month=6,day=21,lat=78.2232,lng=15.6469)])
def test_node_axis_is_separate_and_legacy_geometry_stays_unchanged(birth):
    legacy=calculate_structure_graph(**birth)
    graph=calculate_structure_graph(**birth,include_supplementary=True)
    assert 'supplementary_source' not in legacy
    for field in ('nodes','axes','dispositor','aspects','conditions','houses','jones'):
        assert graph[field]==legacy[field],field
    a,b=build_salience(legacy),build_salience(graph)
    for field in ('focus_selection','core_structures','global_distribution','planet_profiles'):
        assert a[field]==b[field],field
    extra=b['supplementary_contacts']
    assert extra['status']=='available' and extra['node_model']=='true'
    assert set(extra['points'])=={'north_node','south_node'}
    assert extra['contacts']
    assert len({r['planet'] for r in extra['contacts']})==len(extra['contacts'])
    for contact in extra['contacts']:
        assert len(contact['expressions'])==2
        assert {e['node'] for e in contact['expressions']}=={'north_node','south_node'}
        assert all(e['orb']<=6 for e in contact['expressions'])
    if birth['lat']>70:
        assert all(all(v is None for v in p['houses'].values()) for p in extra['points'].values())


def test_supplementary_invalid_geometry_rejected_and_missing_not_fabricated():
    graph=calculate_structure_graph(**BIRTH,include_supplementary=True)
    for kind in ('longitude','orb','duplicate'):
        bad=copy.deepcopy(graph)
        if kind=='longitude':bad['supplementary_source']['points']['north_node']['longitude']+=1
        elif kind=='orb':bad['supplementary_source']['edges'][0]['orb']+=1
        else:bad['supplementary_source']['edges'].append(copy.deepcopy(bad['supplementary_source']['edges'][0]))
        with pytest.raises(StructureInputError):validate_supplementary(bad)
    graph.pop('supplementary_source')
    extra=build_salience(graph)['supplementary_contacts']
    assert extra['status']=='not_supplied' and extra['contacts']==[]


def test_triplicity_membership_sensitivity_all_signs_sects_and_seven_planets():
    from services.classical_engine import compute_essential_dignities,DOROTHEAN_TRIPLICITY,TRADITIONAL_PLANETS
    graph=dict(aspects={v:dict(edges=[],motifs=[]) for v in ('6','8','10')})
    for sign in range(12):
        for day in (True,False):
            for planet in TRADITIONAL_PLANETS:
                e=compute_essential_dignities(planet,sign*30+15,day)
                e['peregrine']=not any(e[k] for k in ('domicile','exaltation','triplicity','term','face'))
                profiles={planet:dict(condition=dict(essential=e),sign_idx=sign)}
                unchanged=copy.deepcopy(profiles)
                _,c=policy_context(graph,{'orb_view':8},profiles)
                row=c['dignity']['rows'][planet]
                assert row['active_sect']['triplicity']==(planet==DOROTHEAN_TRIPLICITY[sign][0 if day else 1])
                assert row['any_triplicity_member_sensitivity']['member']==(planet in DOROTHEAN_TRIPLICITY[sign])
                assert profiles==unchanged


def test_aspect_comparison_exposes_actual_views_without_tuning():
    graph=calculate_structure_graph(**BIRTH,include_supplementary=True)
    for orb in (6,8,10):
        data=build_salience(graph,{'orb_view':orb})
        context=data['policy_comparison']['aspects']
        assert context['selected_view']==orb
        assert context['upstream_orbs']=={str(a):10 for a in (0,60,90,120,180)}
        for view,row in context['views'].items():
            assert row['aspect_count']==len(graph['aspects'][view]['edges'])
            assert row['configuration_count']==len(graph['aspects'][view]['motifs'])


def test_real_tool_new_fact_verification_and_tamper_rejection():
    import mcp_server as m
    from services.mcp_result_facts import checked_result
    async def run():
        args={k:v for k,v in BIRTH.items() if k not in ('lat','lng')}
        args['location_id']='coord:39.904200,116.407400'
        data=await m.calculate_natal_salience(**args)
        assert data['status']=='ok'
        path='/supplementary_contacts/points/north_node/longitude'
        out=await m.verify_calculation_claims(reference=m.CalculationReference(**data['calculation_reference']),
            claims=[m.CalculationClaim(quote='true node',path=path,value=data['supplementary_contacts']['points']['north_node']['longitude'])])
        assert out['claims'][0]['verdict']=='supported'
        context=data['planet_profiles']['jupiter']['triplicity_context']
        identity=await m.verify_calculation_claims(reference=m.CalculationReference(**data['calculation_reference']),
            claims=[m.CalculationClaim(quote='triplicity ruler identity',
                path='/planet_profiles/jupiter/triplicity_context/is_triplicity_ruler',
                value=context['is_triplicity_ruler'])])
        assert identity['claims'][0]['verdict']=='supported'
        data['policy_comparison']['dignity']['rows']['jupiter']['active_sect']['triplicity']=not data['policy_comparison']['dignity']['rows']['jupiter']['active_sect']['triplicity']
        assert checked_result('calculate_natal_salience',data,args)['status']=='validation_failed'
    asyncio.run(run())
