"""Reading hierarchy, linked evidence and non-prescriptive resource checks."""
import copy
import pytest
from services.natal_salience import build_salience
from services.natal_structure_graph import calculate_structure_graph
from services.natal_reading_plan import _resource_checks


def pointer(data, path):
    for key in path.strip('/').split('/'):
        data=data[int(key)] if isinstance(data,list) else data[key]
    return data


@pytest.fixture(scope='module')
def result():
    return build_salience(calculate_structure_graph(year=2000,month=1,day=1,hour=12,minute=0,lat=39.9042,lng=116.4074))


def test_every_terminal_survives_and_containment_is_expansion(result):
    plan=result['reading_plan']; backbone=plan['structural_backbone']
    assert [pointer(result,p) for p in backbone['terminal_refs']]==result['core_structures']
    maximal=backbone['maximal_configuration_ids']
    for m in backbone['configuration_expansion']:
        assert (m['id'] in maximal)==(not m['parent_ids'])
        assert m['id'] not in m['contained_ids']
    assert plan['score'] is None
    assert plan['candidate_coverage']['selected']==len(result['priority_planets'])
    assert len(plan['complete_profiles'])==len(result['priority_planets'])


def test_matrix_keeps_context_separate_and_all_refs_resolve(result):
    evidence=result['evidence_index']; audit={r['planet']:r for r in result['selection_audit']}
    assert len(result['evidence_matrix']['rows'])==10
    for row in result['evidence_matrix']['rows']:
        selection=[]
        for family,cells in row['cells'].items():
            for cell in cells:
                assert evidence[cell['evidence_id']]['family']==family
                if cell['usage']=='selection': selection.append(cell['evidence_id'])
        assert set(selection)=={r['evidence_id'] for r in audit[row['planet']]['rules_matched']}
        if row['profile_ref']: assert pointer(result,row['profile_ref'])['planet']==row['planet']
    for topic in result['resource_checks']['topics']:
        assert topic['verdict'] is None
        assert all(pointer(result,ref) is not None for ref in topic['source_refs'])
        for candidate in topic['candidate_connections']:
            assert candidate['planet'] not in topic['affected_planets']
            for connection in candidate['connections']:
                linked=pointer(result,connection['candidate_ref'])
                assert linked['planet']==candidate['planet']
                assert linked['assessment']=='not_evaluated'


def test_specific_aspect_shared_connection_does_not_become_remedy():
    edge=dict(id='a:moon:sun:90',angle=90,orb=4.8,**{'from':'moon','to':'sun'})
    def profile(candidates):
        return dict(condition=None,condition_availability='unknown',retrograde=False,
            houses={'placidus':None,'whole_sign':None},house_ruler_links={'placidus':[],'whole_sign':[]},
            aspects=[edge],resource_review={'candidates':[{'planet':p} for p in candidates]})
    ps={'sun':(0,{'profile':profile(['moon','venus','mars'])}),
        'moon':(1,{'profile':profile(['sun','venus'])})}
    original=copy.deepcopy(ps)
    result=_resource_checks(ps)
    assert ps==original
    assert len(result['topics'])==1
    t=result['topics'][0]
    assert t['fact']['orb']==4.8 and t['verdict'] is None
    assert {c['planet']:c['coverage'] for c in t['candidate_connections']}=={'mars':'some_affected','venus':'all_affected'}
    assert all('not_evaluated' in c['relevance'] for c in t['candidate_connections'])
    del ps['moon']
    partial=_resource_checks(ps)['topics'][0]
    assert partial['unavailable_endpoint_profiles']==['moon']
    assert all(c['coverage']=='some_affected' for c in partial['candidate_connections'])


def test_missing_houses_do_not_generate_house_topics():
    graph=calculate_structure_graph(year=2000,month=6,day=21,hour=12,minute=0,lat=78.2232,lng=15.6469)
    data=build_salience(graph)
    assert data['reading_plan']['structural_backbone']['terminal_refs']
    assert not data['reading_plan']['identity_and_local']['axis_contact_ids']
    assert not any(t['kind']=='house_association' for t in data['resource_checks']['topics'])


def test_zero_tight_gate_does_not_hide_non_tight_hard_aspect_topics():
    graph=calculate_structure_graph(year=2000,month=1,day=1,hour=12,minute=0,lat=39.9042,lng=116.4074)
    data=build_salience(graph,{'tight_orb':0})
    assert not data['reading_plan']['identity_and_local']['tight_aspect_ids']
    assert any(t['kind']=='square_or_opposition' and t['fact']['orb']>0 for t in data['resource_checks']['topics'])
