"""A read-only MCP fixture for comparing server-owned and Codex-owned tool execution."""
import json, sys
from pathlib import Path
DATA=Path(sys.argv[1]); LOG=Path(sys.argv[2])
for line in sys.stdin:
    try:
        request=json.loads(line); method=request.get('method'); params=request.get('params',{})
        if 'id' not in request: continue
        if method=='initialize': result={'protocolVersion':'2025-03-26','capabilities':{'tools':{}},'serverInfo':{'name':'strata-fixture','version':'1'}}
        elif method=='tools/list': result={'tools':[{'name':'read_record','description':'Read the exact value of a named record from the local fixture.','annotations':{'readOnlyHint':True,'destructiveHint':False,'idempotentHint':True,'openWorldHint':False},'inputSchema':{'type':'object','properties':{'name':{'type':'string','enum':['ALPHA','BETA','GAMMA']}},'required':['name'],'additionalProperties':False}}]}
        elif method=='tools/call':
            name=params.get('arguments',{}).get('name'); value=json.loads(DATA.read_text(encoding='utf-8'))[name]
            with LOG.open('a',encoding='utf-8') as f: f.write(json.dumps({'method':method,'name':name,'value':value})+'\n')
            result={'content':[{'type':'text','text':str(value)}]}
        else: result={}
        print(json.dumps({'jsonrpc':'2.0','id':request['id'],'result':result}),flush=True)
    except Exception as error:
        print(json.dumps({'jsonrpc':'2.0','id':request.get('id'),'error':{'code':-32603,'message':str(error)}}),flush=True)
