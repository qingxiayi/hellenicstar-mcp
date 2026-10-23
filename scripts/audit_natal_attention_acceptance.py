"""Audit review-policy exclusions without changing rules or inferring rankings."""
import json
import sys
from collections import Counter
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.audit_natal_focus import held_out
from services.mcp_structure_graph import calculate_graph_data
from services.natal_salience import build_salience


def inspect(data):
    view=data['attention_layers']
    rows={r['planet']:r for r in view['planet_audit']}
    assert set(rows)==set(data['planet_profiles'])
    assert {t['id'] for t in view['primary_structures']['terminals']}=={t['id'] for t in data['core_structures']}
    for r in data['selection_audit']:
        roles=rows[r['planet']]['role_groups']
        for hit in r['focus_rules']:
            expected={'axis_conjunction':'axis_contact','identity_anchor':'identity',
                      'main_external_entry':'rulership','chart_ruler_dispositor':'rulership',
                      'maximal_configuration_focus':'aspect_network'}.get(hit['rule'])
            if expected:
                assert set(hit['evidence_ids'])<=set(roles[expected])
    maximal=set(data['focus_selection']['configuration_group_ids'])
    if view['version'] in ('natal-attention-v2', 'natal-attention-v3'):
        from services.natal_attention import NETWORK_ROLES
        for planet,row in rows.items():
            facets={f['evidence_id']:f for f in row['aspect_network_evidence']}
            for m in data['priority_configurations']:
                relevant=set(m['roles'].get(planet,[])) & NETWORK_ROLES
                if relevant:
                    assert relevant==set(facets[m['id']]['roles'])
                    assert m['id'] in row['role_groups']['aspect_network']
                    assert set(facets[m['id']]['represented_by'])<=maximal
            assert row['network_geometry_ids']==sorted({edge for f in facets.values() for edge in f['geometry_ids']})
    endpoints=[]
    for planet,row in rows.items():
        found=[]
        for m in data['priority_configurations']:
            if m['id'] in maximal and 'opposition_endpoint' in m['roles'].get(planet,[]):
                edges=[eid for eid in m['depends_on']
                       if data['evidence_index'][eid]['detail']['angle']==180 and
                       planet in (data['evidence_index'][eid]['detail']['from'],
                                  data['evidence_index'][eid]['detail']['to'])]
                assert edges
                found.append(dict(configuration=m['id'],opposition_edges=edges))
        if found and 'aspect_network' not in row['role_groups']:
            endpoints.append(dict(planet=planet,category=row['category'],roles=row['role_groups'],
                configuration_opposition_roles=found,
                chart_ruler=data['planet_profiles'][planet]['chart_ruler']))
    return endpoints


def main():
    stats=Counter(); examples=[]; shapes={}; failures=[]; demotions=[]
    for birth in held_out(2026102206,300):
        args={k:v for k,v in birth.items() if k not in ('id','group')}
        try:
            graph=calculate_graph_data(**args,include_supplementary=True)
            assert graph['status']=='ok'
            views={orb:build_salience(graph,dict(orb_view=orb)) for orb in (6,8,10)}
            missing={orb:inspect(data) for orb,data in views.items()}
            stats['charts']+=1;stats['views']+=3
            if missing[8]:
                stats['charts_with_maximal_opposition_role_not_in_attention_network']+=1
                stats['such_planets']+=len(missing[8])
                if any(r['chart_ruler'] for r in missing[8]):stats['charts_with_chart_ruler_in_this_category']+=1
                if len(examples)<4: examples.append(dict(birth=birth,excluded_roles=missing[8]))
            focus={orb:set(data['attention_layers']['cross_focus']) for orb,data in views.items()}
            if views[8]['attention_layers']['version'] in ('natal-attention-v2', 'natal-attention-v3'):
                assert not any(missing.values())
                assert focus[6]<=focus[8]<=focus[10]
            if focus[6]!=focus[8]:stats['cross_focus_changed_6_to_8']+=1
            if focus[8]!=focus[10]:stats['cross_focus_changed_8_to_10']+=1
            if focus[6]-focus[8]:
                stats['cross_focus_lost_when_view_widened_6_to_8']+=1
                if len(demotions)<3:
                    planets=sorted(focus[6]-focus[8])
                    demotions.append(dict(birth=birth,planets=planets,
                        views={str(orb):[r for r in views[orb]['attention_layers']['planet_audit'] if r['planet'] in planets]
                               for orb in (6,8)}))
            d=views[8]
            kinds={t['type'] for t in d['core_structures']}
            if len(d['core_structures'])>1:kinds.add('multiple_terminals')
            for kind in sorted(kinds):
                if kind not in shapes:
                    shapes[kind]=dict(birth=birth,terminals=[dict(members=t['members'],numerator=t['numerator']) for t in d['core_structures']],
                                     cross_focus=d['attention_layers']['cross_focus'],specific_focus=d['attention_layers']['specific_focus'])
        except Exception as exc:
            failures.append(dict(id=birth['id'],error=repr(exc)))
    print(json.dumps(dict(seed=2026102206,stats=dict(stats),examples=examples,view_demotions=demotions,structural_examples=shapes,
        invariant_failures=failures,
        interpretation='Endpoint-role exclusions and orb sensitivity are observations of the declared policy, not automatically astronomical errors or proof of psychological importance. No ranking oracle.',
        deployment='not_performed'),ensure_ascii=False,indent=2))
    assert not failures,failures

if __name__=='__main__':main()
