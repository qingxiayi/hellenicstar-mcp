"""Separate, versioned priority extraction contract; graph v1 stays unchanged."""
from services.natal_salience import build_salience, normalize_config, DEFAULT_ASPECT_VIEW
from services.mcp_structure_graph import calculate_graph_data, validate_graph_output
from services.natal_aspect_dynamics import calculate_dynamics

CONFIG_KEYS=('scope','rulership','orb_view','tight_orb','axis_orb','include_mc_ruler','distribution_points','reception_policy','dynamics_days')


def calculate_salience_data(*, scope='classical7', rulership='traditional', orb_view=DEFAULT_ASPECT_VIEW,
                            tight_orb=3.0, axis_orb=5.0, include_mc_ruler=False,
                            distribution_points='ten_plus_asc_mc', reception_policy='dignity_only', dynamics_days=30, **birth):
    try:
        config=normalize_config(dict(scope=scope,rulership=rulership,orb_view=orb_view,
            tight_orb=tight_orb,axis_orb=axis_orb,include_mc_ruler=include_mc_ruler,
            distribution_points=distribution_points,reception_policy=reception_policy,dynamics_days=dynamics_days))
    except ValueError as exc:
        return {'status':'invalid_input','error':str(exc)}
    if 'interpretation_policy' in birth:
        return {'status':'invalid_input','error':'interpretation_policy has been withdrawn; calculation-only endpoint'}
    graph=calculate_graph_data(**birth,include_supplementary=True)
    if graph['status']!='ok': return graph
    dynamics=calculate_dynamics(graph,dynamics_days,orb_view)
    return dict(build_salience(graph,config,dynamics),status='ok',completeness=graph['completeness'],
                birth_context=graph['birth_context'],settings=config,source_graph=graph,
                layer_availability=graph['layer_availability'],interpretations=[])


def validate_salience_output(data,args):
    from services.mcp_validation import require,context
    context(data['birth_context'],args)
    config=normalize_config({k:args[k] for k in CONFIG_KEYS if k in args})
    graph=data['source_graph']
    validate_graph_output(graph)
    require(data['settings']==config,'/settings','policy_matches_request')
    require(data['completeness']==graph['completeness'] and data['layer_availability']==graph['layer_availability'],'/completeness','source_availability_matches')
    require(data['birth_context']==graph['birth_context'],'/birth_context','source_context_matches')
    require(data['interpretations']==[],'/interpretations','no_psychological_inferences')
    dynamics=calculate_dynamics(graph,config['dynamics_days'],config['orb_view'])
    for key,value in build_salience(graph,config,dynamics).items():
        require(data[key]==value,'/'+key,'priorities_match_source_and_policy')
