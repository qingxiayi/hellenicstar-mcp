"""Object-selection regression and holdout diagnostics, not an importance oracle."""
import copy
import json
import random
import sys
from collections import Counter
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.mcp_structure_graph import calculate_graph_data
from services.natal_salience import build_salience


def held_out():
    rng=random.Random(2026102202)
    return [dict(id=f'holdout-{i:03}',group='holdout',year=rng.randrange(1900,2100),
        month=rng.randrange(1,13),day=rng.randrange(1,29),hour=rng.randrange(24),minute=rng.randrange(60),
        location_id=f'coord:{rng.uniform(-65,65):.6f},{rng.uniform(-179,179):.6f}') for i in range(300)]


def main():
    root=Path(__file__).resolve().parents[1]
    fixtures=json.loads((root/'tests/fixtures/natal-structure-synthetic.json').read_text())
    failures=[]; stats={}; variants=0
    for label,rows in [('regression',fixtures),('holdout',held_out())]:
        status=Counter(); before=Counter(); after=Counter(); rules=Counter(); shapes=Counter(); rejected=[]
        for i,row in enumerate(rows):
            try:
                graph=calculate_graph_data(**{k:v for k,v in row.items() if k not in ('id','group')})
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
                status[graph['completeness']]+=1
                if graph['completeness']=='full':
                    before[sum(bool(p['selection_reasons']) for p in data['candidate_planets'])]+=1
                    after[len(data['priority_planets'])]+=1
                assert len(data['planet_profiles'])==10
                assert sum(t['numerator'] for t in data['core_structures'])==7
                assert data['focus_selection']['terminal_group_ids']==[t['id'] for t in data['core_structures']]
                assert {m['id'] for m in data['priority_configurations']}=={m['id'] for m in graph['aspects']['8']['motifs']}
                for t in data['core_structures']: shapes[t['type']]+=1
                if len(data['core_structures'])>1:shapes['multiple_terminals']+=1
                for p,profile in data['planet_profiles'].items():
                    assert {e['id'] for e in profile['aspects']}=={e['id'] for e in graph['aspects']['8']['edges'] if p in (e['from'],e['to'])}
                for audit in data['selection_audit']:
                    assert bool(audit['focus_rules'])==audit['selected']
                    assert {r['evidence_id'] for r in audit['rules_matched']}=={e for r in audit['focus_rules'] for e in r['evidence_ids']}
                    for rule in audit['focus_rules']:rules[rule['rule']]+=1
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
        stats[label]=dict(inputs=len(rows),status=dict(status),old_candidate_count_full=dict(sorted(before.items())),
            focal_planet_count_full=dict(sorted(after.items())),rule_occurrences=dict(rules),terminal_shapes=dict(shapes),rejected=rejected)
    print(json.dumps(dict(version='natal-focus-v2',samples=stats,configuration_variants=variants,failures=failures,
        limits=['No labelled professional importance truth; fewer selections alone is not evidence of accuracy.',
                'No planet-count target or fixed winner; broad outputs remain possible and disclosed.',
                'Holdout is deterministic synthetic data, not population representative.',
                'Rules use structural families, not statistical independence or psychological interpretation.']),ensure_ascii=False,indent=2))
    assert not failures,failures


if __name__=='__main__':main()
