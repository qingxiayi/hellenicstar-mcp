"""Stateless, cross-module source-field verification against checked recomputation.

References are reproducibility checks, not signatures or authorization tokens.
Only registered read-only data tools can be recomputed. No snapshots persisted.
"""
from datetime import datetime, timezone
import hashlib
import inspect
import json
from typing import Dict, List, Union

from pydantic import BaseModel, ConfigDict, Field, StrictStr, ValidationError, create_model
from services.mcp_validation import CONTRACTS, VERSION, blocked, validate_output

SCHEMA = 'calculation-reference-v2'
LEGACY_SCHEMA = 'calculation-reference-v1'
REGISTRY = {}
MODELS = {}

Scalar = Union[str, int, float, bool, None]
ScalarDict = Dict[str, Scalar]
ScalarList = List[Scalar]
DictList = List[ScalarDict]
NestedDict = Dict[str, Union[Scalar, ScalarDict]]

ClaimValueType = Union[
    str, int, float, bool,
    ScalarList,
    ScalarDict,
    DictList,
    NestedDict,
    None
]

# Bounded nested input for explicit relationship contexts: role dictionaries and
# additional-type lists. Tool-specific models still validate keys and semantics.
ReferenceInputType = Union[Scalar, ScalarDict, ScalarList, Dict[str, Union[Scalar, ScalarDict, ScalarList]]]


class CalculationReference(BaseModel):
    model_config = ConfigDict(extra='forbid')
    schema_version: StrictStr
    tool: StrictStr = Field(max_length=80)
    input: dict[str, ReferenceInputType]
    fingerprint: StrictStr = Field(min_length=64,max_length=64)


class CalculationClaim(BaseModel):
    model_config = ConfigDict(extra='forbid')
    quote: StrictStr = Field(min_length=1,max_length=1000,description='Exact draft quote; echoed, not semantically parsed.')
    path: StrictStr = Field(min_length=1,max_length=500,description='Exact JSON Pointer to the source result field, e.g. /jones_pattern/high_focus_planet. Include adjacent role/time/planet fields in a separate claim to retain context.')
    value: ClaimValueType = Field(description='Exact claimed source value, including row objects for events/roles. No fuzzy rounding or semantic interpretation.')


def register(fn):
    name=fn.__name__
    REGISTRY[name]=fn
    spec={k:(p.annotation,p.default if p.default is not inspect.Parameter.empty else ...)
          for k,p in inspect.signature(fn).parameters.items()}
    MODELS[name]=create_model(name+'ReferenceInput',__config__=ConfigDict(extra='forbid'),**spec)


def normalize_arguments(args, *, tool=None):
    """Freeze moving defaults ONCE so a later verification uses the same instant."""
    now=datetime.now(timezone.utc)
    args=dict(args)
    if 'moment' in args and args['moment'] in (None,''):
        args['moment']=now.isoformat(timespec='seconds')
    age_only_secondary = (tool in {'calculate_secondary_progressions',
                                   'render_secondary_progressions_chart'}
                          and args.get('age') is not None)
    if 'as_of' in args and args['as_of'] in (None,'') and not age_only_secondary:
        args['as_of']=now.date().isoformat()
    return args


def json_args(args):
    return {k:v.model_dump(mode='json') if isinstance(v,BaseModel) else v for k,v in args.items()}


def data_payload(data):
    metadata = ('fact_reference', 'calculation_reference', 'quality',
                'interpretation_workflow', 'calculation_envelope')
    return {k: v for k, v in data.items() if k not in metadata}


def canonical_numbers(value):
    """Ignore JSON number spelling, without rounding or coercing bool/string.

    JavaScript JSON.parse/stringify turns 3.0 into 3 and -0.0 into 0. These
    denote the same numeric fact. Nonintegral floats retain every stored digit;
    large integers are never converted to floats (which could lose precision).
    """
    if isinstance(value, dict):
        return {key: canonical_numbers(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [canonical_numbers(item) for item in value]
    if type(value) is float and value.is_integer():
        return int(value)
    return value


def fingerprint(data, *, schema_version=SCHEMA):
    payload = data_payload(data)
    if schema_version == SCHEMA:
        payload = canonical_numbers(payload)
    elif schema_version != LEGACY_SCHEMA:
        raise ValueError('Unsupported calculation reference schema')
    return hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False,
                                    allow_nan=False,separators=(',',':')).encode()).hexdigest()


def checked_result(tool,data,args):
    if isinstance(data,dict) and isinstance(data.get('status'),str) and data['status']!='ok':
        return data
    args=json_args(args)
    issues=validate_output(tool,data,args)
    if issues: return blocked(tool,issues)
    ref={'schema_version':SCHEMA,'tool':tool,'input':args,'fingerprint':fingerprint(data)}
    out={**data,'calculation_reference':ref,
         'quality':{'status':'passed','contract_version':VERSION,
                    'scope':'required_fields_and_registered_domain_invariants',
                    'algorithm_independently_verified_this_call':False,
                    'regression_test':CONTRACTS[tool][2],
                    'limitations':'结构和一致性检查通过，不等于独立证明算法正确，也不验证解释。'}}
    if tool not in ('search_birthplace','resolve_birth_coordinates','calculate_natal_chart'):
        out['interpretation_workflow']={
            'next_tool':'verify_calculation_claims',
            'before_final_answer':'Submit all source facts used in the draft with unchanged calculation_reference and exact JSON Pointer paths. Include full event/role objects when context matters. Correct contradicted facts and verify the corrected draft; identify unverified facts.',
            'scope':'Submitted source fields only; quote semantics, omitted facts and psychological interpretations are not checked.'}
    return out


def lookup(data,path):
    if not path.startswith('/') or len(path.split('/'))>30: raise KeyError(path)
    value=data_payload(data)
    for part in path[1:].split('/'):
        # RFC 6901 decoding; reject invalid escape sequences.
        if '~' in part.replace('~1','').replace('~0',''): raise KeyError(path)
        part=part.replace('~1','/').replace('~0','~')
        if isinstance(value,list):
            if not part.isdigit() or str(int(part))!=part: raise KeyError(path)
            value=value[int(part)]
        elif isinstance(value,dict): value=value[part]
        else: raise KeyError(path)
    return value


def exact_equal(a,b):
    # JSON bool and number must remain distinct (True != house 1).
    return json.dumps(canonical_numbers(a),sort_keys=True,ensure_ascii=False,allow_nan=False)==json.dumps(canonical_numbers(b),sort_keys=True,ensure_ascii=False,allow_nan=False)


def verify_calculation_claims_data(reference,claims):
    ref=CalculationReference.model_validate(reference)
    if ref.schema_version not in (SCHEMA, LEGACY_SCHEMA) or ref.tool not in REGISTRY:
        return {'status':'invalid_reference','next_action':'recalculate_source','error':'引用版本或数据工具不受支持。'}
    if not 1<=len(claims)<=100 or len(json.dumps([reference,claims],ensure_ascii=False))>100_000:
        return {'status':'invalid_input','error':'每次核对 1–100 项，输入总量不可超过 100000 字符。'}
    # Do not allow a reference with un-frozen time defaults to drift silently.
    for key in ('moment','as_of'):
        if key in inspect.signature(REGISTRY[ref.tool]).parameters and not ref.input.get(key):
            if (key == 'as_of' and ref.tool == 'calculate_secondary_progressions'
                    and ref.input.get('age') is not None):
                continue
            return {'status':'invalid_reference','next_action':'recalculate_source','error':'引用缺少固定的计算时刻或参考日期。'}
    try:
        args=MODELS[ref.tool].model_validate(ref.input).model_dump()
        # Keep nested BirthInput objects for the original callable.
        parsed=MODELS[ref.tool].model_validate(ref.input)
        native={k:getattr(parsed,k) for k in type(parsed).model_fields}
        from services.mcp_contract import tool_clarification
        gate=tool_clarification(ref.tool,native,inspect.signature(REGISTRY[ref.tool]).parameters)
        if gate: return {'status':'invalid_reference','next_action':'recalculate_source','error':'引用缺少原工具所需参数。'}
        out=checked_result(ref.tool,REGISTRY[ref.tool](**native),args)
    except (ValidationError,TypeError,ValueError):
        return {'status':'invalid_reference','next_action':'recalculate_source','error':'引用输入不符合原工具契约。'}
    if out.get('status')!='ok': return out
    if fingerprint(out, schema_version=ref.schema_version)!=ref.fingerprint:
        return {'status':'reference_mismatch','next_action':'recalculate_source','error':'原结果已变化或引用被改动，请重新计算后提交。'}
    rows=[]
    for raw in claims:
        c=CalculationClaim.model_validate(raw)
        row={'quote':c.quote,'path':c.path,'claimed_value':c.value}
        try:
            actual=lookup(out,c.path)
            # null is an explicitly unavailable/undefined result, not support.
            if actual is None:
                row.update(verdict='unverified',reason='原结果未提供确定值。')
            else:
                row.update(verdict='supported' if exact_equal(actual,c.value) else 'contradicted',
                           evidence={'tool':ref.tool,'path':c.path,'value':actual})
        except (KeyError,IndexError,TypeError,ValueError):
            row.update(verdict='unverified',reason='无法定位可核对的原结果字段。')
        rows.append(row)
    counts={k:sum(r['verdict']==k for r in rows) for k in ('supported','contradicted','unverified')}
    return {'status':'ok','calculation_reference':ref.model_dump(),'claims':rows,'counts':counts,
            'assessment':('contains_conflicts' if counts['contradicted'] else 'no_verifiable_claims' if not counts['supported'] else 'partially_verified' if counts['unverified'] else 'submitted_claims_supported'),
            'coverage':{'submitted_claims':len(rows),'checked_claims':counts['supported']+counts['contradicted'],
                        'quote_semantics_checked':False,'full_report_checked':False,
                        'independent_algorithm_verification':False},
            'next_action':'correct_and_reverify' if counts['contradicted'] else 'review_unverified_claims' if counts['unverified'] else 'use_verified_facts'}
