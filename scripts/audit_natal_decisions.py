"""Exercise v2 roles and separate dimensions on the fixed synthetic input set."""
from collections import Counter
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from services.mcp_structure_graph import calculate_graph_data
from services.natal_salience import build_salience


def resolve(data,path):
    for key in path.strip('/').split('/'):
        data=data[int(key)] if isinstance(data,list) else data[key]
    return data


def main():
    rows=json.loads((Path(__file__).resolve().parents[1]/'tests/fixtures/natal-structure-synthetic.json').read_text())
    status=Counter(); roles=Counter(); applicability=Counter(); state_coverage=Counter(); topics=Counter()
    failures=[]
    for row in rows:
        try:
            g=calculate_graph_data(**{k:v for k,v in row.items() if k not in ('id','group')})
            if g['status']!='ok':
                status['rejected_or_ambiguous']+=1; continue
            d=build_salience(g); status[g['completeness']]+=1
            assert len(d['priority_decisions']['rows'])==10
            for p in d['priority_decisions']['rows']:
                assert 'tier' not in p
                for r in p['roles']:
                    roles[r['kind']]+=1
                    assert resolve(d,r['source_ref']) is not None
            for topic in d['resource_decisions']['topics']:
                topics[topic['status']]+=1
                for c in topic['candidates']:
                    assert 'status' not in c and c['effective_remedy'] is None
                    assert c['relationship']['status']=='established'
                    applicability[c['applicability']['status']]+=1
                    state_coverage[c['counterpart_state']['availability']['essential']]+=1
                    assert c['applicability']['ability_to_resolve_issue']=='not_established'
                    for ref in c['counterpart_state']['source_refs']:
                        assert resolve(d,ref) is not None
        except Exception as exc: failures.append({'id':row['id'],'error':str(exc)})
    print(json.dumps(dict(version='v2',inputs=len(rows),counts=dict(status),role_instances=dict(roles),
        applicability=dict(applicability),essential_state_coverage=dict(state_coverage),topic_counts=dict(topics),failures=failures,
        limitation='Full and partial charts; relations repeat across topics. No importance or efficacy grades.'),ensure_ascii=False,indent=2))
    assert not failures


if __name__=='__main__': main()
