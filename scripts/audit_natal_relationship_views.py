"""Synthetic-only integration audit, using the original offline cohort."""
import argparse
import copy
import json
from collections import Counter
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.audit_natal_focus import held_out
from scripts.research_natal_candidate_routes import views as offline_views
from services.mcp_structure_graph import calculate_graph_data
from services.natal_salience import build_salience
from services.natal_relationship_views import build_relationship_views


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path,
        default=root/'docs/validation/natal-relationship-views-v1-audit.json')
    args = parser.parse_args()
    latitude = [r for r in json.loads((root/'tests/fixtures/natal-structure-synthetic.json').read_text())
                if r['group']=='latitude']
    assert len(latitude)==52
    cases = held_out(2026102307,100) + latitude
    totals, failures = Counter(), []
    for case in cases:
        try:
            graph = calculate_graph_data(**{k:v for k,v in case.items() if k not in ('id','group')})
            assert graph['status']=='ok'
            data = build_salience(graph)
            original_profiles = copy.deepcopy(data['planet_profiles'])
            layer = data['relationship_views']
            offline = offline_views(data)
            for target, row in layer['planets'].items():
                expected = offline[target]
                assert row['groups']==expected['groups']
                assert row['dependency_review']==expected['governance_review']
                assert row['direct_aspect_review']==expected['degree_contact_review']
                assert row['context_review']==expected['context_view']
                assert row['all_associations']==expected['all_candidates']
                assert set(row['relations'])==set(expected['all_candidates'])
                assert set(layer['states'][target])==set(original_profiles[target])-{'resource_review'} | {'condition_context'}
                selected = set(row['dependency_review']) | set(row['direct_aspect_review'])
                assert not selected.intersection(row['context_review'])
                assert selected | set(row['context_review'])==set(row['all_associations'])
                for other, relation in row['relations'].items():
                    assert relation['target_state_ref']==f'/relationship_views/states/{target}'
                    assert relation['counterpart_state_ref']==f'/relationship_views/states/{other}'
                totals['planet_views'] += 1
                totals['all_associations'] += len(row['all_associations'])
                totals['selected_union'] += len(selected)
                totals['background'] += len(row['context_review'])
            mutated = copy.deepcopy(data)
            for profile in mutated['planet_profiles'].values():
                for candidate in profile['resource_review']['candidates']:
                    candidate['routes'] = list(reversed(candidate['routes']*2))
                profile['resource_review']['candidates'].reverse()
            assert build_relationship_views(mutated)==layer
            assert data['planet_profiles']==original_profiles
            totals['charts'] += 1
            totals[graph['completeness']] += 1
        except Exception as exc:
            failures.append(dict(id=case['id'],error=repr(exc)))
    report=dict(version='natal-relationship-views-v1',seed=2026102307,orb_view=6,
                totals=dict(totals),failures=failures,
                limitation='Integration and classification checks only, not remedy efficacy or professional accuracy.')
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False))
    if failures: raise SystemExit(1)


if __name__=='__main__':
    main()
