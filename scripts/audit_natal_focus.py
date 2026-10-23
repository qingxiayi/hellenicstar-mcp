"""Object-selection regression and holdout diagnostics, not an importance oracle."""
import copy
import argparse
import importlib.util
import json
import random
import sys
from collections import Counter
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.mcp_structure_graph import calculate_graph_data
from services.natal_salience import build_salience


def held_out(seed=2026102203, count=300):
    rng=random.Random(seed)
    return [dict(id=f'holdout-{i:03}',group='holdout',year=rng.randrange(1900,2100),
        month=rng.randrange(1,13),day=rng.randrange(1,29),hour=rng.randrange(24),minute=rng.randrange(60),
        location_id=f'coord:{rng.uniform(-65,65):.6f},{rng.uniform(-179,179):.6f}') for i in range(count)]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--baseline-dir',type=Path,help='Optional immutable prior natal_focus.py and natal_salience.py snapshot')
    parser.add_argument('--holdout-seed',type=int,default=2026102203)
    parser.add_argument('--holdout-count',type=int,default=300)
    args=parser.parse_args()
    if args.holdout_count < 1:
        parser.error('--holdout-count must be positive')
    baseline=None
    if args.baseline_dir:
        modules={}
        for name in ('natal_focus','natal_salience'):
            spec=importlib.util.spec_from_file_location('baseline_'+name,args.baseline_dir/(name+'.py'))
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);modules[name]=module
        modules['natal_salience'].select_focus=modules['natal_focus'].select_focus
        baseline=modules['natal_salience'].build_salience
    root=Path(__file__).resolve().parents[1]
    fixtures=json.loads((root/'tests/fixtures/natal-structure-synthetic.json').read_text())
    failures=[]; stats={}; variants=0
    for label,rows in [('regression',fixtures),('holdout',held_out(args.holdout_seed,args.holdout_count))]:
        status=Counter(); before=Counter(); after=Counter(); rules=Counter(); shapes=Counter(); rejected=[]
        changes=Counter(); examples=[]; attention_counts=Counter()
        for i,row in enumerate(rows):
            try:
                graph=calculate_graph_data(**{k:v for k,v in row.items() if k not in ('id','group')},include_supplementary=True)
                status[graph['status']]+=1
                if graph['status']!='ok':
                    if label=='regression':
                        assert row['group'] in ('invalid_probe','boundary')
                        expected={'dst-gap':'nonexistent','dst-repeat-unset':'ambiguous','china-dst-gap':'nonexistent','apia-skipped-date':'nonexistent'}.get(row['id'],'invalid_input')
                        assert graph['status']==expected
                    else:
                        assert graph['status'] in ('nonexistent','ambiguous')
                    rejected.append(dict(id=row['id'],status=graph['status']));continue
                data=build_salience(graph)
                old=baseline(graph) if baseline else None
                status[graph['completeness']]+=1
                if graph['completeness']=='full':
                    if old: before[len(old['priority_planets'])]+=1
                    after[len(data['priority_planets'])]+=1
                if old:
                    old_ids=set(old['focus_selection']['planet_ids']);new_ids=set(data['focus_selection']['planet_ids'])
                    changes['changed' if old_ids!=new_ids else 'unchanged']+=1
                    assert old['core_structures']==data['core_structures']
                    assert old['planet_profiles']==data['planet_profiles']
                    if old_ids!=new_ids and len(examples)<8:
                        examples.append(dict(id=row['id'],added=sorted(new_ids-old_ids),removed=sorted(old_ids-new_ids)))
                assert len(data['planet_profiles'])==10
                attention=data['attention_layers']
                attention_counts[len(attention['cross_focus'])]+=1
                partition=sum((attention[k] for k in ('cross_focus','specific_focus','associated_context')),[])
                assert len(partition)==len(set(partition))==10
                assert set(partition)==set(data['planet_profiles'])
                assert [t['id'] for t in attention['primary_structures']['terminals']]==[t['id'] for t in data['core_structures']]
                for item in attention['planet_audit']:
                    assert (item['category']=='cross_focus')==(len(item['role_groups'])>=2)
                    assert set(item['evidence_ids'])<=set(data['evidence_index'])
                assert data['supplementary_contacts']['status']=='available'
                assert len(data['supplementary_contacts']['points'])==2
                assert data['policy_comparison']['aspects']['views']['8']['aspect_count']==len(graph['aspects']['8']['edges'])
                assert sum(t['numerator'] for t in data['core_structures'])==7
                assert data['focus_selection']['terminal_group_ids']==[t['id'] for t in data['core_structures']]
                assert {m['id'] for m in data['priority_configurations']}=={m['id'] for m in graph['aspects'][str(data['method']['config']['orb_view'])]['motifs']}
                for t in data['core_structures']: shapes[t['type']]+=1
                if len(data['core_structures'])>1:shapes['multiple_terminals']+=1
                for p,profile in data['planet_profiles'].items():
                    assert {e['id'] for e in profile['aspects']}=={e['id'] for e in graph['aspects'][str(data['method']['config']['orb_view'])]['edges'] if p in (e['from'],e['to'])}
                    context=profile['triplicity_context']
                    if context['status']=='available':
                        assert context['counted_by_engine']==profile['condition']['essential']['triplicity']
                        assert context['is_triplicity_ruler']==(p in context['rulers'].values())
                        order=context['sect_order']
                        assert context['sect_priority']==(order.index(p)+1 if order and p in order else None)
                        assert profile['resource_review']['intrinsic']['condition_context']['triplicity_context']==context
                for audit in data['selection_audit']:
                    assert bool(audit['focus_rules'])==audit['selected']
                    assert {r['evidence_id'] for r in audit['rules_matched']}=={e for r in audit['focus_rules'] for e in r['evidence_ids']}
                    for rule in audit['focus_rules']:rules[rule['rule']]+=1
                    for ev in audit['candidate_evaluations']:
                        if ev['disposition']=='synonymous_relation':
                            assert ev['evidence_id'] not in {x for ids in audit['structural_families'].values() for x in ids}
                for identity,e in data['evidence_index'].items():
                    if e['family']=='reception':
                        for p in (e['detail']['planet1'],e['detail']['planet2']):
                            audit=next(a for a in data['selection_audit'] if a['planet']==p)
                            assert identity in {r['evidence_id'] for r in audit['candidate_rules_matched']}
                assert all(not t['unavailable_endpoint_profiles'] for t in data['resource_checks']['topics'])
                if i%25==0:
                    altered=copy.deepcopy(graph)
                    altered['nodes']=list(reversed(altered['nodes']))*2
                    for view in altered['aspects'].values():
                        view['edges']=list(reversed(view['edges']))*2;view['motifs']=list(reversed(view['motifs']))*2
                    assert build_salience(altered)==data
                    for scope in ('classical7','ten'):
                        for rulership in ('traditional','modern'):
                            for orb in (6,8,10):
                                v=build_salience(graph,dict(scope=scope,rulership=rulership,orb_view=orb))
                                assert sum(t['numerator'] for t in v['core_structures'])==(7 if scope=='classical7' else 10)
                                assert len(v['planet_profiles'])==10
                                variants+=1
            except Exception as exc:
                failures.append(dict(id=row['id'],error=repr(exc)))
        stats[label]=dict(inputs=len(rows),status=dict(status),baseline_focal_count_full=dict(sorted(before.items())),
            focal_planet_count_full=dict(sorted(after.items())),changes=dict(changes),examples=examples,
            rule_occurrences=dict(rules),terminal_shapes=dict(shapes),rejected=rejected,
            cross_focus_counts=dict(sorted(attention_counts.items())))
    print(json.dumps(dict(version='natal-focus-v4',holdout_seed=args.holdout_seed,samples=stats,configuration_variants=variants,failures=failures,
        limits=['No labelled professional importance truth; fewer selections alone is not evidence of accuracy.',
                'No planet-count target or fixed winner; broad outputs remain possible and disclosed.',
                'Holdout is deterministic synthetic data, not population representative.',
                'Rules use structural families, not statistical independence or psychological interpretation.']),ensure_ascii=False,indent=2))
    assert not failures,failures


if __name__=='__main__':main()
