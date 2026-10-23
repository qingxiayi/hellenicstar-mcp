"""Replay synthetic civil births and independently check graph reachability.
Run from source with: python scripts/verify_natal_structure.py
No personal birth records or interpretation reports are included.
"""
import json
from pathlib import Path
import random
import signal
import sys
import time
from collections import Counter
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.mcp_structure_graph import calculate_graph_data
from services.mcp_validation import validate_output
from services.natal_structure_graph import TEN, SIGN_KEYS, TRADITIONAL_RULERS, MODERN_RULERS, topology


def oracle(planets, rules):
    nxt={k:rules[SIGN_KEYS[int(v['longitude']//30)]] for k,v in planets.items()}
    reach={k:{k,nxt[k]} for k in planets}
    for _ in planets:
        reach={k:set().union(*(reach[j] for j in reach[k])) for k in planets}
    components={tuple(sorted(j for j in planets if j in reach[k] and k in reach[j])) for k in planets}
    return {c:sorted(k for k in planets if set(c)<=reach[k]) for c in components if all(nxt[k] in c for k in c)}


def check_graph(planets, got, rules):
    assert {tuple(t['members']):sorted(t['basin']) for t in got['terminals']}==oracle(planets,rules)


def main():
    rows=json.loads((Path(__file__).resolve().parents[1]/'tests/fixtures/natal-structure-synthetic.json').read_text())
    counts=Counter();failures=[];elapsed=[]; candidate_sets=Counter(); terminal_shapes=Counter()
    def timeout(*_): raise TimeoutError('8 seconds per input')
    signal.signal(signal.SIGALRM,timeout)
    expected_rejections={'dst-gap','dst-repeat-unset','china-dst-gap','invalid-leap','invalid-hour','apia-skipped-date','lat-over','lng-over','negative-minute','minute-60','month-13','fold-2','fractional-hour'}
    for row in rows:
        args={k:v for k,v in row.items() if k not in ('id','group')};start=time.perf_counter()
        try:
            signal.alarm(8)
            d=calculate_graph_data(**args)
            if row['id'] in expected_rejections:
                assert d['status'] in ('invalid_input','ambiguous','nonexistent'),d['status']
                counts['rejected']+=1
            else:
                assert d['status']=='ok',d.get('error',d['status'])
                assert not validate_output('calculate_natal_structure_graph',d,args)
                ps={n['id']:{'longitude':n['lon']} for n in d['nodes']}
                for policy,rules in [('traditional',TRADITIONAL_RULERS),('modern',MODERN_RULERS)]:check_graph(ps,d['dispositor'][policy],rules)
                counts[d['completeness']]+=1
                from services.natal_salience import build_salience
                salience=build_salience(d)
                selected={k:v for k,v in ps.items() if k in salience['scope_comparison']['classical7']['origins']}
                check_graph(selected,{'terminals':[{'members':t['members'],'basin':t['origins']} for t in salience['core_structures']]},TRADITIONAL_RULERS)
                checked=dict(salience,status='ok',settings=salience['method']['config'],source_graph=d,completeness=d['completeness'],birth_context=d['birth_context'],layer_availability=d['layer_availability'],interpretations=[])
                assert not validate_output('calculate_natal_salience',checked,args)
                if d['completeness']=='full':
                    candidate_sets[str(len(salience['priority_planets']))]+=1
                    terminal_shapes.update(t['type'] for t in salience['core_structures'])
        except Exception as e:failures.append({'id':row['id'],'error':type(e).__name__+': '+str(e)})
        finally:signal.alarm(0)
        elapsed.append(time.perf_counter()-start)
    rng=random.Random(20261022)
    for _ in range(10000):
        ps={k:{'longitude':rng.randrange(12)*30+rng.uniform(.001,29.999)} for k in TEN}
        for rules in (TRADITIONAL_RULERS,MODERN_RULERS):check_graph(ps,topology(ps,rules),rules)
    summary={'synthetic_birth_inputs':len(rows),'counts':dict(counts),'failures':failures,'independent_topology_checks':20000,'max_input_seconds':round(max(elapsed),4),'priority_candidate_counts_full':dict(candidate_sets),'salience_terminal_shapes_full':dict(terminal_shapes)}
    print(json.dumps(summary,ensure_ascii=False,indent=2))
    assert not failures,summary

if __name__=='__main__':main()
