"""Deterministic natal priorities and relation facts, without interpretation.

Lineage, synonymous facts, containment and correlated evidence are distinct.
"""
import copy
import json
import math
from collections import Counter
from services.natal_structure_graph import TEN, SEVEN, topology, DEFAULT_ASPECT_VIEW
from services.natal_house_rulers import SIGN_KEYS, TRADITIONAL_RULERS, MODERN_RULERS, PLANET_ZH
from services.natal_resource_context import triplicity_context, resource_review
from services.natal_reading_plan import build_reading_layers
from services.natal_decision_policy import build_decisions
from services.natal_relation_facts import reception_facts, POLICIES
from services.natal_focus import select_focus

DEFAULTS = dict(scope='classical7', rulership='traditional', orb_view=DEFAULT_ASPECT_VIEW,
                tight_orb=3.0, axis_orb=5.0, include_mc_ruler=False,
                distribution_points='ten_plus_asc_mc', reception_policy='dignity_only', dynamics_days=30)
CATEGORIES = ('terminal', 'identity', 'dispositor_bridge', 'axis', 'tight_aspect', 'configuration', 'house_ruler', 'angular_concentration', 'reception')


def normalize_config(config=None):
    if config is not None and not isinstance(config,dict):
        raise ValueError('config must be an object')
    c={**DEFAULTS,**(config or {})}
    if set(c)!=set(DEFAULTS): raise ValueError('Unknown priority configuration key')
    if c['scope'] not in ('classical7','ten') or c['rulership'] not in ('traditional','modern'):
        raise ValueError('Unknown origin scope or rulership')
    if type(c['orb_view']) is not int or c['orb_view'] not in (6,8,10):
        raise ValueError('orb_view must be 6, 8 or 10')
    for key in ('tight_orb','axis_orb'):
        v=c[key]
        if type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=10:
            raise ValueError(key+' must be finite and between 0 and 10')
    if c['tight_orb']>c['orb_view']: raise ValueError('tight_orb cannot exceed orb_view')
    if type(c['include_mc_ruler']) is not bool: raise ValueError('include_mc_ruler must be boolean')
    if c['distribution_points'] not in ('ten','ten_plus_asc_mc'):
        raise ValueError('Unknown distribution point set')
    if c['reception_policy'] not in POLICIES:
        raise ValueError('Unknown reception policy')
    if type(c['dynamics_days']) is not int or not 1 <= c['dynamics_days'] <= 90:
        raise ValueError('dynamics_days must be an integer between 1 and 90')
    return c


def tightness(orb):
    return 'exact' if orb<=1 else 'tight' if orb<=3 else 'moderate' if orb<=5 else 'wide'


def _clean(value):
    if isinstance(value,dict):
        return {k:_clean(v) for k,v in value.items() if k not in ('source_pointer','source_facts')}
    if isinstance(value,list): return [_clean(v) for v in value]
    return value


def _unique(rows, identity):
    result={}
    for row in rows:
        item=_clean(row); key=identity(item)
        if key in result and result[key]!=item:
            raise ValueError('Contradictory duplicate: '+str(key))
        result[key]=item
    return [result[k] for k in sorted(result)]


def terminal_metrics(nodes, rules, origins):
    """Origin scope is separate from the available transit nodes and rulers."""
    full=topology({k:{'longitude':v['lon']} for k,v in sorted(nodes.items())},rules)
    result=[]
    for t in full['terminals']:
        members=sorted(t['members']); basin=sorted(set(t['basin']) & set(origins))
        if not basin: continue
        external=[k for k in basin if k not in members]
        paths={k:full['paths'][k] for k in basin}
        entry={k:[] for k in members}
        for k in external:
            entry[paths[k]['path'][paths[k]['steps_to_terminal']]].append(k)
        maximum=max(map(len,entry.values()),default=0)
        direct=[k for k in external if paths[k]['steps_to_terminal']==1]
        result.append(dict(id='terminal:'+':'.join(members),
            type='self' if len(members)==1 else 'two_node_cycle' if len(members)==2 else 'multi_node_cycle',
            members=members, origins=basin, numerator=len(basin), denominator=len(origins),
            coverage=len(basin)/len(origins), external_origins=external,
            feeders=dict(direct=direct,indirect=[k for k in external if k not in direct]),
            first_entry={k:dict(origins=v,count=len(v)) for k,v in entry.items()},
            main_entries=[k for k,v in entry.items() if maximum and len(v)==maximum],
            internal_edges=[e for e in full['edges'] if e['from'] in members], paths=paths))
    return sorted(result,key=lambda t:(-t['numerator'],t['id'])),full


def _axis_contacts(nodes,axes,limit):
    contacts=[]
    for pair in (('asc','dsc'),('mc','ic')):
        anchor=next((a for a in pair if a in axes),None)
        if anchor is None: continue
        for k,n in sorted(nodes.items()):
            sep=abs((n['lon']-axes[anchor]['lon']+180)%360-180)
            angle=min((0,60,90,120,180),key=lambda a:abs(sep-a)); orb=abs(sep-angle)
            if orb>limit: continue
            expressions=[]
            for a in pair:
                if a not in axes: continue
                d=abs((n['lon']-axes[a]['lon']+180)%360-180)
                target=min((0,60,90,120,180),key=lambda v:abs(d-v))
                expressions.append(dict(axis=a,angle=target,orb=round(abs(d-target),6)))
            contacts.append(dict(id=f'axis:{k}:{pair[0]}:{angle}',planet=k,
                axis_pair=list(pair),canonical_axis=anchor,angle=angle,orb=round(orb,6),
                tightness=tightness(orb),expressions=expressions))
    return sorted(contacts,key=lambda a:(a['orb'],a['id']))


def build_salience(graph, config=None, dynamics=None):
    c=normalize_config(config)
    nodes={n['id']:n for n in _unique(graph['nodes'],lambda n:n['id'])}
    if set(nodes)!=set(TEN): raise ValueError('The complete ten-planet graph is required')
    for n in nodes.values():
        if type(n['lon']) not in (int,float) or not math.isfinite(n['lon']) or not 0<=n['lon']<360:
            raise ValueError('Invalid longitude')
        if n['sign_idx']!=int(n['lon']//30): raise ValueError('Sign contradicts longitude')
    rules=TRADITIONAL_RULERS if c['rulership']=='traditional' else MODERN_RULERS
    comparisons={}; full=None
    for scope,origins in (('classical7',SEVEN),('ten',TEN)):
        metrics,full=terminal_metrics(nodes,rules,origins)
        comparisons[scope]=dict(origins=list(origins),terminals=metrics)
    cores=comparisons[c['scope']]['terminals']
    aspects=[]
    for original in graph['aspects'][str(c['orb_view'])]['edges']:
        e=_clean(original); a,b=sorted((e['from'],e['to']))
        e.update(id=f'a:{a}:{b}:{int(e["angle"])}', **{'from':a,'to':b})
        e['depends_on']=sorted(set(e['depends_on']))
        aspects.append(e)
    aspects=_unique(aspects,lambda e:e['id'])
    for e in aspects: e['tightness']=tightness(e['orb'])
    motifs=[]
    for original in graph['aspects'][str(c['orb_view'])]['motifs']:
        m=_clean(original); m['members']=sorted(m['members']);m['depends_on']=sorted(set(m['depends_on']))
        m['id']=m['kind']+':'+':'.join(m['members']); motifs.append(m)
    motifs=_unique(motifs,lambda m:m['id'])
    axes=graph['axes']; axis_contacts=_axis_contacts(nodes,axes,c['axis_orb'])
    evidence={}; reasons={k:[] for k in sorted(nodes)}

    def record(identity,family,detail,depends,refs,planets=(),category=None,synonym=None):
        item=dict(id=identity,family=family,detail=detail,depends_on=sorted(set(depends)),
                  source_refs=refs,synonym_group=synonym or identity)
        if identity in evidence and evidence[identity]!=item: raise ValueError('Conflicting evidence ID')
        evidence[identity]=item
        if category:
            for k in planets:
                reason=dict(category=category,evidence_id=identity)
                if reason not in reasons[k]: reasons[k].append(reason)
        return identity

    for core in cores:
        record(core['id'],'dispositor',core,[f'lon:{k}' for k in core['origins']+core['members']],
               ['/source_graph/dispositor'],core['members'],'terminal')
        for k in core['main_entries']:
            record('entry:'+core['id']+':'+k,'dispositor',core['first_entry'][k],[core['id']],
                   ['/core_structures'],[k],'terminal')
    for k in ('sun','moon'):
        record('identity:'+k,'identity',dict(role='luminary',planet=k),[],['/source_graph/nodes'],[k],'identity')
    chart_ruler=rules[SIGN_KEYS[int(axes['asc']['lon']//30)]] if 'asc' in axes else None
    if chart_ruler:
        record('identity:chart_ruler','identity',dict(planet=chart_ruler),['axis:asc'],['/source_graph/axes/asc'],[chart_ruler],'identity')
        host=rules[SIGN_KEYS[nodes[chart_ruler]['sign_idx']]]
        if host != chart_ruler:
            record('bridge:chart_ruler','dispositor',dict(planet=host,guest=chart_ruler,
                role='chart_ruler_dispositor',rulership=c['rulership'],depth=1),
                ['axis:asc',f'lon:{chart_ruler}'],['/source_graph/axes/asc','/source_graph/nodes'],
                [host],'dispositor_bridge')
    if c['include_mc_ruler'] and 'mc' in axes:
        k=rules[SIGN_KEYS[int(axes['mc']['lon']//30)]]
        record('identity:mc_ruler','identity',dict(planet=k),['axis:mc'],['/source_graph/axes/mc'],[k],'identity')
    for contact in axis_contacts:
        k=contact['planet']
        record(contact['id'],'angularity',contact,[f'lon:{k}']+['axis:'+a for a in contact['axis_pair'] if a in axes],
               ['/source_graph/nodes','/source_graph/axes'],[k],'axis')
    priority_aspects=[]
    for e in aspects:
        selected=e['orb']<=c['tight_orb']
        record(e['id'],'aspect',e,e['depends_on'],['/source_graph/aspects/'+str(c['orb_view'])+'/edges'],
               [e['from'],e['to']], 'tight_aspect' if selected else None)
        if selected: priority_aspects.append(dict(e,selection_rule='orb_lte_tight_orb'))
    configurations=[]
    for m in motifs:
        roles={}
        for k in m['members']:
            incident=[e['angle'] for e in aspects if e['id'] in m['depends_on'] and k in (e['from'],e['to'])]
            roles[k]=['opposition_endpoint'] if 180 in incident else ['member']
            if m['kind']=='wedge' and 180 not in incident: roles[k]=['mediator']
            if m['kind']=='minor_grand_trine' and sorted(incident)==[60,60]: roles[k]=['sextile_vertex']
            if m['kind']=='t_square' and sorted(incident)==[90,90]: roles[k]=['apex']
            if m['kind']=='kite' and sorted(incident)==[60,60,180]: roles[k].append('sextile_apex')
        contained=[n['id'] for n in motifs if set(n['depends_on'])<set(m['depends_on'])]
        overlaps=[dict(id=n['id'],shared_edges=sorted(set(n['depends_on']) & set(m['depends_on'])))
                  for n in motifs if n['id']!=m['id'] and set(n['depends_on']) & set(m['depends_on'])]
        item=dict(m,roles=roles,contains=sorted(contained),shared_with=overlaps)
        configurations.append(item)
        record(m['id'],'configuration',item,m['depends_on'],['/source_graph/aspects/'+str(c['orb_view'])+'/motifs'],m['members'],'configuration')
    houses={}; links=[]
    for system,field in (('placidus','house_p'),('whole_sign','house_w')):
        houses[system]=_unique(graph['houses'][system],lambda h:h['house'])
        for h in houses[system]:
            k=h['rulers'][c['rulership']]['planet']
            link=dict(system=system,house=h['house'],ruler=k,located_house=h['rulers'][c['rulership']]['located_house'],path=full['paths'][k])
            links.append(link)
            lights=sorted(set(h['occupants']) & {'sun','moon'})
            record(f'ruler:{system}:{h["house"]}','house_ruler',dict(link,luminaries=lights),
                   [f'cusp:{system}:{h["house"]}',f'lon:{k}'],['/source_graph/houses/'+system],
                   [k], 'house_ruler' if lights else None)
            if h['category']=='angular' and len(h['occupants'])>=2:
                record(f'concentration:{system}:{h["house"]}','angularity',dict(system=system,house=h['house'],members=sorted(h['occupants'])),
                       [f'house:{system}:{p}' for p in h['occupants']],['/source_graph/houses/'+system],h['occupants'],'angular_concentration')
    receptions=[]
    for r in _unique(graph['receptions']['mutual_receptions'],lambda r:tuple(sorted((r['planet1'],r['planet2'])))):
        a,b=sorted((r['planet1'],r['planet2']))
        edge=next((e for e in aspects if {e['from'],e['to']}=={a,b}),None)
        angles={'合相':0,'六分相':60,'四分相':90,'三分相':120,'对分相':180}
        upstream_orb=abs(abs((nodes[a]['lon']-nodes[b]['lon']+180)%360-180)-angles[r['aspect']]) if r['has_aspect'] else None
        item=dict(r,upstream=dict(has_aspect=r['has_aspect'],aspect=r['aspect'],orb=upstream_orb),
                  current_view=dict(orb_view=c['orb_view'],has_aspect=edge is not None,
                                    aspect_id=edge['id'] if edge else None,orb=edge['orb'] if edge else None))
        receptions.append(item)
        terminal_id='terminal:'+':'.join((a,b))
        synonym=terminal_id if r['domicile_cycle'] and terminal_id in evidence else None
        record('reception:'+a+':'+b,'reception',item,r['depends_on'],
               ['/source_graph/receptions/mutual_receptions'],[a,b],'reception',synonym=synonym)
    one_way=[]
    for r in _unique(graph['receptions']['receptions'],lambda r:(r['received_planet'],r['dignitor_planet'])):
        a,b=r['received_planet'],r['dignitor_planet']
        edge=next((e for e in aspects if {e['from'],e['to']}=={a,b}),None)
        one_way.append(dict(r,upstream=dict(has_aspect=True,aspect=r['aspect'],orb=r['orb']),
            current_view=dict(orb_view=c['orb_view'],has_aspect=edge is not None,
                              aspect_id=edge['id'] if edge else None,orb=edge['orb'] if edge else None)))
    profiles={}
    for k,n in sorted(nodes.items()):
        ruler=rules[SIGN_KEYS[n['sign_idx']]]
        condition=copy.deepcopy(graph['conditions'].get(k))
        if condition:
            condition['essential']['peregrine']=not any(condition['essential'][key] for key in ('domicile','exaltation','triplicity','term','face'))
        located={}; ruled={}
        for system,field in (('placidus','house_p'),('whole_sign','house_w')):
            located[system]=n[field]; ruled[system]=[h for h in links if h['system']==system and h['ruler']==k]
            if n[field] in (1,4,7,10):
                record(f'angular:{system}:{k}','angularity',dict(planet=k,system=system,house=n[field]),
                       [f'house:{system}:{k}'],['/source_graph/nodes'])
        profiles[k]=dict(planet=k,longitude=n['lon'],sign=n['sign'],sign_idx=n['sign_idx'],retrograde=n['retrograde'],
            condition=condition,condition_availability='available' if condition else 'classical_conditions_not_defined_for_outer_planets',
            triplicity_context=triplicity_context(k,n['sign_idx'],condition),
            houses=located,house_ruler_links=ruled,aspects=[e for e in aspects if k in (e['from'],e['to'])],
            dispositor=dict(planet=ruler,condition=graph['conditions'].get(ruler)),path=full['paths'][k],
            terminal_ids=[t['id'] for t in cores if k in t['origins'] or k in t['members']],
            receptions=[r for r in receptions if k in (r['planet1'],r['planet2'])],
            one_way_receptions=[r for r in one_way if k in (r['received_planet'],r['dignitor_planet'])],
            configurations=[dict(id=m['id'],roles=m['roles'][k]) for m in configurations if k in m['members']],
            axis_contacts=[a for a in axis_contacts if a['planet']==k],chart_ruler=(k==chart_ruler) if chart_ruler else None,
            source_refs=['/source_graph/nodes','/source_graph/houses','/source_graph/aspects/'+str(c['orb_view'])]+(['/source_graph/conditions/'+k] if condition else []))
    relation_facts = reception_facts(nodes, aspects, graph['facts']['sect']['value'], c['orb_view'], dynamics, c['reception_policy'])
    for k in profiles:
        profiles[k]['resource_review']=resource_review(k,profiles,relation_facts['rows'])
    # Correlation groups retain house angularity and axis contact as distinct facts.
    for k in nodes:
        related=[e['id'] for e in evidence.values() if e['family']=='angularity' and
                 (e['detail'].get('planet')==k or k in e['detail'].get('members',[]))]
        for identity in related: evidence[identity]['correlation_group']='angularity:'+k if 'members' not in evidence[identity]['detail'] else 'angular_concentration'
    points={k:n['lon'] for k,n in sorted(nodes.items())}
    requested=list(sorted(nodes))
    if c['distribution_points']=='ten_plus_asc_mc':
        requested+=['asc','mc']; points.update({a:axes[a]['lon'] for a in ('asc','mc') if a in axes})
    distribution=dict(requested_points=requested,available_points=sorted(points),missing_points=sorted(set(requested)-set(points)),
                      point_count=len(points),status='full' if len(points)==len(requested) else 'partial',houses={})
    for label,names in (('elements',['fire','earth','air','water']),('modalities',['cardinal','fixed','mutable'])):
        counts=Counter(names[int(lon//30)%len(names)] for lon in points.values())
        distribution[label]={name:counts[name] for name in names}
    for system,field in (('placidus','house_p'),('whole_sign','house_w')):
        available=all(nodes[k][field] is not None for k in TEN)
        hs=[nodes[k][field] for k in TEN] if available else []
        distribution['houses'][system]=dict(status='available' if available else 'unavailable',points=list(TEN),
            method='house-number groups; whole-sign groups are not physical horizon geometry',
            quadrants={str(q+1):sum((h-1)//3==q for h in hs) for q in range(4)} if available else None,
            hemispheres=dict(above=sum(h>=7 for h in hs),below=sum(h<=6 for h in hs),
                eastern=sum(h in (10,11,12,1,2,3) for h in hs),western=sum(h in (4,5,6,7,8,9) for h in hs)) if available else None)
    focus, focus_policy = select_focus(reasons, evidence, configurations)
    priority=[]; audit=[]; candidates=[]
    for k in sorted(nodes):
        original=reasons[k]
        candidates.append(dict(planet=k,selection_reasons=original))
        selected=focus[k]['selection_reasons']
        selected.sort(key=lambda r:(CATEGORIES.index(r['category']),r['evidence_id']))
        categories=[category for category in CATEGORIES if any(r['category']==category for r in selected)]
        if selected: priority.append(dict(planet=k,categories=categories,selection_reasons=selected,profile=profiles[k]))
        audit.append(dict(planet=k,selected=bool(selected),rules_matched=selected,
                          reason=focus[k]['reason'], candidate_rules_matched=original,
                          focus_rules=focus[k]['rules'], structural_families=focus[k]['structural_families'],
                          candidate_evaluations=focus[k]['candidate_evaluations'],
                          unknowns=['axis:'+a for a in ('asc','mc','dsc','ic') if a not in axes]))
    priority.sort(key=lambda r:(CATEGORIES.index(r['categories'][0]),r['planet']))
    result = dict(schema_version='natal-priorities-v4',core_structures=cores,scope_comparison=comparisons,
        priority_planets=priority,planet_profiles=profiles,candidate_planets=candidates,
        focus_selection=dict(policy=focus_policy,planet_ids=[p["planet"] for p in priority],
            terminal_group_ids=[t["id"] for t in cores],
            configuration_group_ids=sorted(m["id"] for m in configurations if not any(m["id"] in n["contains"] for n in configurations)),
            broad_selection=len(priority)>=8,
            coverage_note="No forced cap; broad selections must be displayed as such, not a unique core."),priority_aspects=sorted(priority_aspects,key=lambda e:(e['orb'],e['id'])),
        priority_configurations=sorted(configurations,key=lambda m:(-len(m['members']),m['id'])),
        house_ruler_links=links,global_distribution=distribution,reception_facts=relation_facts,
        aspect_dynamics=copy.deepcopy(dynamics) if dynamics else dict(status='not_supplied',rows=[]),
        evidence_index=dict(sorted(evidence.items())),selection_audit=audit,
        availability=dict(source=graph['layer_availability'],axes={a:'available' if a in axes else 'unavailable' for a in ('asc','mc','dsc','ic')},
            chart_pattern_focus=dict(status='moved_to_parallel_view',source_ref='/jones_view/upstream_focus',selection_effect='none'),
            configurations=dict(supported=['grand_trine','minor_grand_trine','wedge','t_square','kite','mystic_rectangle','grand_cross'],unsupported=['yod'])),
        method=dict(version='natal-priorities-v4',config=c,score=None,category_order=list(CATEGORIES),
            within_category='stable identifier; aspects by orb; configurations by member count then identifier',
            deduplication='stable semantic IDs; synonyms linked, contained configurations retained; correlated evidence not discarded',
            interpretation='Calculation and selection rules only; no psychological hypotheses, advice, efficacy, global importance grade or independent-evidence count inferred',
            aspect_source='existing engine list filtered by selected orb view; cannot restore omitted upstream aspects'))
    result.update(build_reading_layers(result))
    result.update(build_decisions(result))
    from services.natal_policy_context import policy_context
    result['supplementary_contacts'], result['policy_comparison'] = policy_context(graph,c,profiles)
    result['availability']['supplementary_contacts']=result['supplementary_contacts']['status']
    result['reading_plan']['identity_and_local']['supplementary_contacts_ref']='/supplementary_contacts'
    from services.natal_attention import build_attention_layers
    result['attention_layers'] = build_attention_layers(result)
    from services.natal_condition_views import build_condition_views
    result['planet_condition_assessments'] = build_condition_views(result, graph)
    from services.natal_relationship_views import build_relationship_views
    result['relationship_views'] = build_relationship_views(result)
    from services.natal_jones_view import build_jones_view
    result['jones_view'], result['view_comparison'] = build_jones_view(graph, result)
    return result
