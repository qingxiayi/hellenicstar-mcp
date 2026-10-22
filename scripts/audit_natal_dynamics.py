"""Cross-chart bounded-motion audit, with numerical residual and mesh checks."""
from collections import Counter
from datetime import datetime, timezone
from functools import lru_cache
import json
from pathlib import Path
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from services.mcp_salience import calculate_salience_data
from services.natal_aspect_dynamics import trace_pair, STEP, residual
from services.transit_utils import body_position
from services.planetary_aspect_scan import BODIES
from services.natal_relation_facts import reception_facts, POLICIES


def main():
    rows=json.loads((Path(__file__).resolve().parents[1]/'tests/fixtures/natal-structure-synthetic.json').read_text())
    counts=Counter(); phases=Counter(); searches=Counter(); policies=Counter(); failures=[]; rejects=[]
    max_residual=0.; finer=0; start_time=time.monotonic()
    for index,case in enumerate(rows):
        try:
            d=calculate_salience_data(**{k:v for k,v in case.items() if k not in ('id','group')})
            if d['status']!='ok':
                expected={'dst-gap':'nonexistent','dst-repeat-unset':'ambiguous',
                    'china-dst-gap':'nonexistent','apia-skipped-date':'nonexistent'}.get(case['id'],'invalid_input')
                assert case['group'] in ('boundary','invalid_probe') and d['status']==expected
                rejects.append({'id':case['id'],'status':d['status']});continue
            counts[d['completeness']]+=1
            motion=d['aspect_dynamics']; counts['dynamics_'+motion['status']]+=1
            utc=datetime.fromisoformat(motion['epoch_utc'])
            epoch=2451545.+(utc-datetime(2000,1,1,12,tzinfo=timezone.utc)).total_seconds()/86400
            @lru_cache(maxsize=10000)
            def pos(body,t): return body_position(BODIES[body],t)
            for r in motion['rows']:
                phases[r['phase']['status']]+=1; searches[r['search']['status']]+=1
                a,b=r['planet_a'],r['planet_b']
                if r['phase']['status'] in ('applying','separating'):
                    target=r['phase']['directed_target']
                    before=abs(residual(pos(a,epoch-1/86400)[0],pos(b,epoch-1/86400)[0],target))
                    after=abs(residual(pos(a,epoch+1/86400)[0],pos(b,epoch+1/86400)[0],target))
                    if abs(after-before)>1e-8:
                        assert (after<before)==(r['phase']['status']=='applying')
                hit=r['search']['first_exact_jd_ut']
                if hit is not None:
                    error=abs(abs((pos(b,hit)[0]-pos(a,hit)[0]+180)%360-180)-r['angle'])
                    max_residual=max(max_residual,error)
                    assert error<1e-5,error
                    assert epoch<=hit<=epoch+30
                if index%120==0 and r['status']=='available':
                    fine=trace_pair(a,b,r['angle'],epoch,30,pos,step=STEP/2)
                    assert fine['search']['status']==r['search']['status']
                    other=fine['search']['first_exact_jd_ut']
                    assert (hit is None and other is None) or abs(hit-other)<2/86400
                    assert [(e['kind'],e.get('body')) for e in fine['search']['events_before_exact_or_end']]==[(e['kind'],e.get('body')) for e in r['search']['events_before_exact_or_end']]
                    finer+=1
            graph=d['source_graph']; nodes={n['id']:n for n in graph['nodes']}
            for policy in POLICIES:
                facts=reception_facts(nodes,graph['aspects']['8']['edges'],graph['facts']['sect']['value'],8,motion,policy)
                for r in facts['rows']:
                    e=r['policy_evaluation'];policies[policy+':'+str(e['meets'])]+=1
                    if e['meets'] is True: assert not e['failed'] and not e['unknown']
        except Exception as e: failures.append(dict(id=case['id'],error=repr(e)))
        if (index+1)%100==0: print(f'{index+1}/{len(rows)} checked; failures={len(failures)}',file=sys.stderr,flush=True)
    print(json.dumps(dict(version='natal-dynamics-audit-v1',inputs=len(rows),counts=dict(counts),
        phase_counts=dict(phases),search_counts=dict(searches),policy_counts=dict(policies),
        max_exact_residual_deg=max_residual,finer_mesh_pair_checks=finer,rejected=rejects,failures=failures,
        elapsed_seconds=round(time.monotonic()-start_time,2),
        limitations=['30-day bounded first-hit search, not unlimited perfection proof.',
                    'Same ephemeris checked by finite differences and finer mesh, not independent astronomy data.',
                    'No claim of psychological importance or reception efficacy.']),ensure_ascii=False,indent=2))
    assert not failures,failures


if __name__=='__main__':main()
