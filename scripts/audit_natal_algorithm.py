"""Execute synthetic inputs and audit factual routes; no interpretation oracle."""
from collections import Counter
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.mcp_structure_graph import calculate_graph_data
from services.natal_salience import build_salience


def resolve(data, path):
    for key in path.strip('/').split('/'):
        data = data[int(key)] if isinstance(data, list) else data[key]
    return data


def audit():
    root = Path(__file__).resolve().parents[1]
    inputs = json.loads((root/'tests/fixtures/natal-structure-synthetic.json').read_text())
    counts = Counter(); routes = Counter(); shapes = Counter(); failures = []; rejected = []
    for row in inputs:
        try:
            graph = calculate_graph_data(**{k:v for k,v in row.items() if k not in ('id','group')})
            if graph['status'] != 'ok':
                assert row['group'] in ('invalid_probe','boundary'), row['id']
                expected = {'dst-gap':'nonexistent','dst-repeat-unset':'ambiguous',
                    'china-dst-gap':'nonexistent','apia-skipped-date':'nonexistent'}.get(row['id'],'invalid_input')
                assert graph['status'] == expected, graph['status']
                rejected.append(dict(id=row['id'],status=graph['status']))
                continue
            data = dict(build_salience(graph),source_graph=graph)
            counts[graph['completeness']] += 1
            assert 'interpretation_hypotheses' not in data
            assert sum(t['numerator'] for t in data['core_structures']) == 7
            for terminal in data['core_structures']: shapes[terminal['type']] += 1
            if len(data['core_structures']) > 1: counts['multiple_terminal_charts'] += 1
            facts = data['reception_facts']['rows']
            assert len({r['id'] for r in facts}) == len(facts)
            for fact in facts:
                assert fact['phase']['status'] in ('unknown','not_applicable')
                for ref in fact['source_refs']: assert resolve(data,ref) is not None
            for p in data['priority_planets']:
                profile = p['profile']; review = profile['resource_review']
                assert review['intrinsic']['planet'] == p['planet'] and review['verdict'] is None
                represented = set()
                for candidate in review['candidates']:
                    assert candidate['planet'] != p['planet'] and candidate['assessment'] == 'not_evaluated'
                    for route in candidate['routes']:
                        routes[route['kind']] += 1
                        for ref in route['source_refs']: assert resolve(data,ref) is not None
                        if route['kind'] in ('conjunction','square_or_opposition','sextile_or_trine'):
                            represented.add(route['detail']['id'])
                assert represented == {e['id'] for e in profile['aspects']}
            for topic in data['resource_decisions']['topics']:
                for candidate in topic['candidates']:
                    assert candidate['effective_remedy'] is None
                    for c in candidate['relationship']['connections']:
                        assert any(c[k] for k in ('governance','aspects','dignity_relations','shared_configurations'))
                        assert resolve(data,c['source_ref'])['planet'] == candidate['planet']
        except Exception as exc:
            failures.append(dict(id=row['id'],error=repr(exc)))
    print(json.dumps(dict(version='algorithm-only-v1',inputs=len(inputs),counts=dict(counts),
        terminal_shapes=dict(shapes),route_instances=dict(routes),rejected=rejected,failures=failures,
        limits=['Synthetic inputs are not a population sample or proof of importance accuracy.',
                'Candidate routes overlap; counts are neither independent evidence nor efficacy.',
                'Applying/separating and perfection are unknown; no psychological conclusions.']),
        ensure_ascii=False,indent=2))
    assert not failures, failures


if __name__ == '__main__': audit()
