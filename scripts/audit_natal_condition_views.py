"""Reproducible synthetic-only audit of condition policy comparisons."""
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
    root = Path(__file__).resolve().parents[1]
    latitude_cases = [r for r in json.loads((root/'tests/fixtures/natal-structure-synthetic.json').read_text())
                      if r['group'] == 'latitude']
    assert latitude_cases, 'Latitude boundary fixtures must not silently disappear'
    samples = held_out(2026102212, 100) + latitude_cases
    stats = Counter(); failures = []
    for sample in samples:
        try:
            graph = calculate_graph_data(**{k:v for k,v in sample.items() if k not in ('id','group')})
            assert graph['status'] == 'ok', graph['status']
            data = build_salience(graph)
            layer = data['planet_condition_assessments']
            stats['charts'] += 1
            stats[graph['completeness']] += 1
            stats[graph['facts']['sect']['value']] += 1
            for planet, row in layer['planets'].items():
                p = data['planet_profiles'][planet]
                c = row['dignity_comparison']
                assert row['relationship_context']['aspects'] == p['aspects']
                assert row['resource_verdict'] is None and row['importance_score'] is None
                if p['condition']:
                    stats['classical_planets'] += 1
                    a = c['policies']['active_sect_only']; b = c['policies']['weighted_triplicity_321']
                    assert a['total'] == p['condition']['essential']['essential_score']
                    assert b['total'] == sum(b['contributions'].values())
                    assert c['score_delta'] in (0,1,2)
                    if c['score_delta']: stats['planets_with_changed_dignity_credit'] += 1
                    if c['peregrine_changes']: stats['planets_with_changed_peregrine_flag'] += 1
                else:
                    assert c['status'] == 'not_applicable'
                if graph['completeness'] == 'partial':
                    assert row['angularity_and_triplicity']['axes_status'] == 'unavailable'
            # Reverse inputs: identifiers and calculations must be order-stable.
            reverse = copy.deepcopy(graph)
            reverse['nodes'].reverse()
            assert build_salience(reverse) == data
            # Alternate dignity states cannot change structural focus or terminals.
            altered = copy.deepcopy(graph)
            for p in altered['conditions']:
                e = altered['conditions'][p]['essential']
                e['triplicity'] = not e['triplicity']
                e['essential_score'] += 3 if e['triplicity'] else -3
            other = build_salience(altered)
            assert data['attention_layers'] == other['attention_layers']
            assert data['core_structures'] == other['core_structures']
            stats['invariant_variants'] += 2
        except Exception as exc:
            failures.append(dict(id=sample['id'], error=str(exc)))
    report = dict(version='natal-condition-views-v1', seed=2026102212,
                  stats=dict(stats), failures=failures,
                  limitation='Rule arithmetic and software invariants, not professional validity or predictive efficacy.')
    output = root/'docs/validation/natal-condition-views-v1-audit.json'
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(report, ensure_ascii=False))
    if failures: raise SystemExit(1)


if __name__ == '__main__':
    main()
