"""Synthetic-only regression for the default inclusive six-degree natal policy."""
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
    cases = held_out(20261023, 100)
    cases += [r for r in json.loads((root/'tests/fixtures/natal-structure-synthetic.json').read_text())
              if r['group'] == 'latitude']
    stats = Counter(); failures = []
    for case in cases:
        try:
            graph = calculate_graph_data(**{k: v for k, v in case.items() if k not in ('id', 'group')},
                                         include_supplementary=True)
            assert graph['status'] == 'ok'
            narrow, wide = build_salience(graph), build_salience(graph, dict(orb_view=8))
            assert narrow['method']['config']['orb_view'] == graph['settings']['primary_aspect_view'] == 6
            assert narrow['core_structures'] == wide['core_structures']
            assert narrow['house_ruler_links'] == wide['house_ruler_links']
            selected = {e['id'] for e in graph['aspects']['6']['edges']}
            for p, profile in narrow['planet_profiles'].items():
                assert {e['id'] for e in profile['aspects']} == {
                    e['id'] for e in graph['aspects']['6']['edges'] if p in (e['from'], e['to'])}
                assert all(e['orb'] <= 6 for e in profile['aspects'])
            assert {m['id'] for m in narrow['priority_configurations']} == {
                m['id'] for m in graph['aspects']['6']['motifs']}
            for m in narrow['priority_configurations']:
                assert set(m['depends_on']) <= selected
            for relation in narrow['reception_facts']['rows']:
                view = relation['current_view']
                assert view['orb_view'] == 6
                assert view['has_aspect'] == (view['aspect_id'] in selected)
            for contact in narrow['supplementary_contacts']['contacts']:
                assert all(e['orb'] <= 6 for e in contact['expressions'])
            stats['charts'] += 1
            stats[graph['completeness']] += 1
            stats['aspects_removed_vs_8'] += len(graph['aspects']['8']['edges']) - len(selected)
            stats['motifs_removed_vs_8'] += len(wide['priority_configurations']) - len(narrow['priority_configurations'])
        except Exception as exc:
            failures.append(dict(id=case['id'], error=repr(exc)))
    report = dict(policy='uniform_major_aspects_orb_lte_6', seed=20261023,
                  stats=dict(stats), failures=failures,
                  limitation='Software consistency only; no psychological efficacy or target ranking.')
    (root/'docs/validation/natal-orb-6-audit.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(report, ensure_ascii=False))
    if failures:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
