"""Diagnostic study of synthetic births, not a ranking-quality benchmark.

No personal records, fixed planet winner or expected interpretation is used.
Run: .venv/bin/python scripts/audit_natal_priorities.py > audit.json
"""
import json
from collections import Counter
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.mcp_structure_graph import calculate_graph_data
from services.natal_salience import build_salience, CATEGORIES


def main():
    source = Path(__file__).resolve().parents[1] / 'tests/fixtures/natal-structure-synthetic.json'
    rows = json.loads(source.read_text())
    counts = Counter()
    selection = Counter()
    categories = Counter()
    exclusive = Counter()
    without = {category: Counter() for category in CATEGORIES}
    shapes = Counter()
    resources = Counter()
    sensitivity = {str(n): Counter() for n in (0, 1, 3)}
    examples = {}
    failures = []
    for row in rows:
        args = {k: v for k, v in row.items() if k not in ('id', 'group')}
        try:
            graph = calculate_graph_data(**args)
            if graph['status'] != 'ok':
                counts['rejected_or_ambiguous'] += 1
                continue
            result = build_salience(graph)
            counts[graph['completeness']] += 1
            # Compare equivalent full inputs; partial coverage is counted separately.
            if graph['completeness'] != 'full':
                continue
            planets = result['priority_planets']
            selection[len(planets)] += 1
            for category in CATEGORIES:
                categories[category] += sum(category in p['categories'] for p in planets)
                exclusive[category] += sum(p['categories'] == [category] for p in planets)
                without[category][sum(bool(set(p['categories']) - {category}) for p in planets)] += 1
            for threshold in (0, 1, 3):
                variant = result if threshold == 3 else build_salience(graph, {'tight_orb': threshold})
                sensitivity[str(threshold)][len(variant['priority_planets'])] += 1
                assert variant['core_structures'] == result['core_structures']

            terminals = result['core_structures']
            labels = {t['type'] for t in terminals}
            if len(terminals) > 1:
                labels.add('multiple_terminals')
            if len(planets) == 10:
                labels.add('all_ten_selected')
            if len(planets) <= 6:
                labels.add('six_or_fewer_selected')
            for label in sorted(labels):
                shapes[label] += 1
                if label not in examples:
                    examples[label] = dict(input=row, selected={p['planet']: p['categories'] for p in planets},
                        terminals=[{k: t[k] for k in ('members','numerator','denominator','main_entries','feeders')} for t in terminals])

            all_nodes = {n['id'] for n in graph['nodes']}
            for p in planets:
                profile = p['profile']
                review = profile['resource_review']
                assert review['verdict'] is None
                resources['reviewed_planets'] += 1
                resources['no_external_candidate'] += not review['candidates']
                for candidate in review['candidates']:
                    assert candidate['planet'] in all_nodes and candidate['planet'] != p['planet']
                    assert candidate['assessment'] == 'not_evaluated'
                    state = candidate['counterpart_state']
                    resources['candidate_pairs'] += 1
                    resources['multiple_routes_same_pair'] += len(candidate['routes']) > 1
                    condition = state['condition']
                    resources['classical_condition_unavailable'] += condition is None
                    if condition:
                        essential = condition['essential']
                        resources['detriment_or_fall'] += essential['detriment'] or essential['fall']
                        resources['retrograde'] += state['retrograde']
                    resources['has_square_or_opposition'] += any(e['angle'] in (90,180) for e in state['aspects'])
                    for route in candidate['routes']:
                        if route['kind'] == 'mutual_reception':
                            resources['mutual_without_current_aspect'] += not route['detail']['current_view']['has_aspect']
        except Exception as exc:
            failures.append(dict(id=row['id'], error=f'{type(exc).__name__}: {exc}'))

    output = dict(input_count=len(rows), counts=dict(counts), failures=failures,
        selected_count_full=dict(sorted(selection.items())), category_planet_hits=dict(categories),
        exclusive_category_hits=dict(exclusive),
        selected_count_if_one_category_removed={k:dict(sorted(v.items())) for k,v in without.items()},
        tight_orb_sensitivity={k:dict(sorted(v.items())) for k,v in sensitivity.items()},
        chart_shape_counts=dict(shapes), resources=dict(resources), examples=examples,
        limitations=['Synthetic sample is not population representative.',
            'No independently labelled important-planet or remedy answers: recall and precision are unknown.',
            'Category ablation diagnoses coverage; it does not justify deleting a category.',
            'Resource counters overlap; counts describe facts, not efficacy or harm.'])
    print(json.dumps(output, ensure_ascii=False, indent=2))
    assert not failures


if __name__ == '__main__':
    main()
