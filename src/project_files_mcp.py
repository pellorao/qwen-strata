"""Read-only, bounded project-file MCP. No subprocess, network or file mutation tools."""
import json
import os
import sys
from pathlib import Path

EXCLUDED={'.git','.venv','__pycache__','node_modules'}
ANNOTATIONS={'readOnlyHint':True,'destructiveHint':False,'idempotentHint':True,'openWorldHint':False}

def scoped(root,relative):
    path=(root/relative).resolve(strict=True)
    if not path.is_relative_to(root):raise ValueError('Path is outside the selected workspace')
    if any(part.casefold() in EXCLUDED for part in path.relative_to(root).parts):raise ValueError('Excluded directory')
    return path

def call(root,name,args):
    if not isinstance(args,dict):raise ValueError('Arguments must be an object')
    if name=='list_files':
        if set(args)-{'path','offset','limit'}:raise ValueError('Unknown arguments')
        path=scoped(root,args.get('path','.'))
        if not path.is_dir():raise ValueError('Expected directory')
        offset=args.get('offset',0);limit=args.get('limit',100)
        if type(offset)!=int or offset<0 or type(limit)!=int or not 1<=limit<=200:raise ValueError('Invalid page')
        entries=[]
        for item in sorted(path.iterdir(),key=lambda p:p.name.casefold()):
            if item.name.casefold() in EXCLUDED:continue
            try:resolved=scoped(root,str(item.relative_to(root)))
            except (ValueError,OSError):continue
            entries.append({'path':str(item.relative_to(root)),'directory':resolved.is_dir()})
        return {'entries':entries[offset:offset+limit],'total':len(entries),'next_offset':offset+limit if offset+limit<len(entries) else None}
    if name=='read_file':
        if set(args)-{'path','start_line','line_count'}:raise ValueError('Unknown arguments')
        path=scoped(root,args['path'])
        if not path.is_file() or path.stat().st_size>16*1024*1024:raise ValueError('Expected UTF-8 file of at most 16 MiB')
        start=args.get('start_line',1);count=args.get('line_count',200)
        if type(start)!=int or start<1 or type(count)!=int or not 1<=count<=400:raise ValueError('Invalid line range')
        text=path.read_text(encoding='utf-8-sig')
        if '\x00' in text:raise ValueError('Binary content is not supported')
        lines=text.splitlines();selected=[];used=0;char_limit=False
        for line in lines[start-1:start-1+count]:
            if used+len(line)+1>24000:char_limit=True;break
            selected.append(line);used+=len(line)+1
        last=start+len(selected)-1
        return {'path':str(path.relative_to(root)),'start_line':start,'end_line':last,'total_lines':len(lines),'text':'\n'.join(selected),'truncated':char_limit or last<len(lines),'next_line':last+1 if last<len(lines) and selected else None,'overlong_line':char_limit and not selected}
    raise ValueError('Unknown tool')

TOOLS=[
 {'name':'list_files','description':'List one workspace directory, with pagination. Excludes .git, .venv, node_modules and paths outside workspace.','annotations':ANNOTATIONS,'inputSchema':{'type':'object','properties':{'path':{'type':'string'},'offset':{'type':'integer','minimum':0},'limit':{'type':'integer','minimum':1,'maximum':200}},'additionalProperties':False}},
 {'name':'read_file','description':'Read a UTF-8 workspace text file by line range. Output explicitly reports truncation and next_line; no writes or commands.','annotations':ANNOTATIONS,'inputSchema':{'type':'object','properties':{'path':{'type':'string'},'start_line':{'type':'integer','minimum':1},'line_count':{'type':'integer','minimum':1,'maximum':400}},'required':['path'],'additionalProperties':False}}
]

def main():
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    raw=os.environ.get('QWEN_PROJECT_WORKSPACE')
    if not raw:raise SystemExit('QWEN_PROJECT_WORKSPACE is required; configure it in the calling project')
    root=Path(raw).resolve(strict=True)
    if not root.is_dir():raise SystemExit('Workspace must be a directory')
    audit=os.environ.get('QWEN_PROJECT_AUDIT')
    for line in sys.stdin:
        request={}
        try:
            request=json.loads(line)
            if not isinstance(request,dict):
                request={}
                raise ValueError('Invalid Request')
            if 'id' not in request:continue
            method=request.get('method');params=request.get('params',{})
            if method=='initialize':result={'protocolVersion':params.get('protocolVersion','2025-03-26'),'capabilities':{'tools':{}},'serverInfo':{'name':'local-project-readonly','version':'1'}}
            elif method=='tools/list':result={'tools':TOOLS}
            elif method=='ping':result={}
            elif method=='resources/list':result={'resources':[]}
            elif method=='resources/templates/list':result={'resourceTemplates':[]}
            elif method=='tools/call':
                try:
                    value=call(root,params.get('name'),params.get('arguments',{}));result={'content':[{'type':'text','text':json.dumps(value,ensure_ascii=False)}]};ok=True
                except (ValueError,OSError,KeyError,UnicodeError) as error:
                    result={'isError':True,'content':[{'type':'text','text':str(error)}]};ok=False
                if audit:
                    with Path(audit).open('a',encoding='utf-8') as f:f.write(json.dumps({'tool':params.get('name'),'arguments':params.get('arguments'),'ok':ok},ensure_ascii=True)+'\n')
            else:raise ValueError('Unsupported MCP method')
            response={'jsonrpc':'2.0','id':request['id'],'result':result}
        except Exception as error:response={'jsonrpc':'2.0','id':request.get('id'),'error':{'code':-32603,'message':str(error)}}
        print(json.dumps(response,ensure_ascii=True),flush=True)

if __name__=='__main__':main()
