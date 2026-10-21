"""Synthetic birthdays: real MCP calculation, projection and recomputation."""
import asyncio
import copy
import json
from pathlib import Path
import sys

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

BIRTH = dict(year=2000,month=1,day=1,hour=12,minute=0,location_id='coord:39.904200,116.407400')
POLAR = {**BIRTH,'month':6,'day':21,'location_id':'coord:78.223200,15.646900'}

@pytest.mark.parametrize('args,completeness', [(BIRTH,'full'),(POLAR,'partial')])
def test_checked_graph_can_be_recomputed_and_verified(args,completeness):
    import mcp_server as m
    async def run():
        out=await m.calculate_natal_structure_graph(**args)
        assert out['status']=='ok',out
        assert out['completeness']==completeness
        assert out['quality']['status']=='passed'
        path='/dispositor/traditional/paths/sun/terminal'
        value=out['dispositor']['traditional']['paths']['sun']['terminal']
        ref=m.CalculationReference(**out['calculation_reference'])
        result=await m.verify_calculation_claims(reference=ref,claims=[m.CalculationClaim(quote='Synthetic test',path=path,value=value),m.CalculationClaim(quote='False claim',path=path,value=['invalid'])])
        assert result['status']=='ok',result
        assert [c['verdict'] for c in result['claims']]==['supported','contradicted']
        projected=await m.calculate_natal_structure_graph(**args,include=['dispositor'],detail_level='summary')
        assert projected['completeness']==completeness
        assert projected['layer_availability']==out['layer_availability']
        assert projected['calculation_reference']==out['calculation_reference']
    asyncio.run(run())

@pytest.mark.parametrize('path,bad', [('nodes.0.lon',400),('nodes.0.house_p',0),('facts.lon:sun.value',999),('aspects.10.edges.0.orb',99),('dispositor.traditional.terminals.0.basin',[]),('interpretations',['psychology']),('completeness','partial')])
def test_corrupted_graph_is_withheld(path,bad):
    from services.mcp_structure_graph import calculate_graph_data
    from services.mcp_result_facts import checked_result
    g=calculate_graph_data(**BIRTH)
    parts=path.split('.');node=g
    for p in parts[:-1]:node=node[int(p)] if isinstance(node,list) else node[p]
    node[int(parts[-1]) if isinstance(node,list) else parts[-1]]=bad
    out=checked_result('calculate_natal_structure_graph',g,BIRTH)
    assert out['status']=='validation_failed'
    assert 'nodes' not in out


def test_real_stdio_graph_full_partial_missing_invalid_and_verification():
    async def run():
        params=StdioServerParameters(command=sys.executable,args=[str(Path(__file__).resolve().parents[1]/'mcp_server.py')])
        async with stdio_client(params) as (read,write):
            async with ClientSession(read,write) as s:
                await s.initialize()
                assert 'calculate_natal_structure_graph' in {t.name for t in (await s.list_tools()).tools}
                async def call(args):
                    r=await s.call_tool('calculate_natal_structure_graph',args)
                    assert not r.isError,r
                    return json.loads(r.content[0].text)
                for args,kind in [(BIRTH,'full'),(POLAR,'partial')]:
                    d=await call(args)
                    assert d['status']=='ok' and d['completeness']==kind,d
                    r=await s.call_tool('verify_calculation_claims',{'reference':d['calculation_reference'],'claims':[dict(quote='Synthetic graph',path='/completeness',value=kind)]})
                    checked=json.loads(r.content[0].text)
                    assert checked['claims'][0]['verdict']=='supported',checked
                missing=await call({})
                assert missing['status']=='needs_clarification'
                invalid=await s.call_tool('calculate_natal_structure_graph',{**BIRTH,'hour':9.5})
                assert invalid.isError
                assert (await call({**BIRTH,'day':32}))['status']=='invalid_input'
                dst=await call(dict(year=2020,month=11,day=1,hour=1,minute=30,location_id='coord:40.712800,-74.006000'))
                assert dst['status']=='ambiguous' and len(dst['candidates'])==2
    asyncio.run(run())
