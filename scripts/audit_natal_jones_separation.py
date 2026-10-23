"""Synthetic audit: Jones changes never alter the original natal layers."""
import copy
import json
from collections import Counter
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.audit_natal_focus import held_out
from services.mcp_structure_graph import calculate_graph_data
from services.natal_salience import build_salience


def main():
    root=Path(__file__).resolve().parents[1]
    cases=held_out(2026102311,40)
    cases += [r for r in json.loads((root/'tests/fixtures/natal-structure-synthetic.json').read_text())
              if r['group']=='latitude']
    totals, shapes, failures=Counter(), Counter(), []
    for i, case in enumerate(cases):
        try:
            graph=calculate_graph_data(**{k:v for k,v in case.items() if k not in ('id','group')})
            assert graph['status']=='ok'
            variants=[{}]
            if i<8:
                variants += [dict(orb_view=8),dict(orb_view=10),dict(rulership='modern',scope='ten')]
            for config in variants:
                data=build_salience(graph,config)
                missing=copy.deepcopy(graph);missing.pop('jones')
                other=build_salience(missing,config)
                for key in set(data)-{'jones_view','view_comparison'}:
                    assert data[key]==other[key], key
                layer=data['jones_view']
                assert layer['method']['selection_effect']=='none'
                assert all(c['aspect']['orb']<=layer['selected_orb_view'] for c in layer['direct_contacts'])
                assert len({c['aspect']['id'] for c in layer['direct_contacts']})==len(layer['direct_contacts'])
                assert len(data['view_comparison']['rows'])==10
                assert not any(e['family']=='chart_pattern' for e in data['evidence_index'].values())
                totals['configurations_checked']+=1
            totals['charts']+=1
            totals[graph['completeness']]+=1
            shapes[graph['jones']['pattern_en']]+=1
        except Exception as exc:
            failures.append(dict(id=case['id'],error=repr(exc)))
    report=dict(version='natal-jones-separation-audit-v1',seed=2026102311,
                totals=dict(totals),shapes=dict(shapes),failures=failures,
                limitation='Software isolation and geometry consistency, not a validation of author interpretations or efficacy.')
    (root/'docs/validation/natal-jones-parallel-audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False))
    if failures: raise SystemExit(1)


if __name__=='__main__':
    main()
