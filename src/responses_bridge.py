"""Responses bridge. Only hosted web search runs here; other tools stay client-owned."""
import argparse, hashlib, ipaddress, json, re, select, socket, sys, threading, time, urllib.error, urllib.request, uuid
from service_access import AccessError
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

class UpstreamFailure(RuntimeError):
    """An accepted backend request failed while generating its response."""

def uid(prefix): return prefix + uuid.uuid4().hex

def tools_to_chat(items, hosted_search=False, additional_items=()):
    tools, aliases, definitions = [], {}, {}
    def add(tool, namespace=None, repeated=False):
        kind = tool.get('type')
        if kind not in ('function', 'custom'):
            raise ValueError('Unsupported tool type: '+str(kind))
        name = tool['name']
        alias = name if namespace is None else namespace+'__'+name
        if len(alias)>64: alias = 'tool_'+hashlib.sha256(alias.encode()).hexdigest()[:40]
        if alias in aliases:
            if repeated and definitions[alias] == (namespace, tool): return
            raise ValueError('Duplicate or conflicting tool alias: '+alias)
        definitions[alias] = (namespace, tool)
        aliases[alias] = dict(name=name, namespace=namespace, type=kind)
        parameters = tool.get('parameters', {'type':'object','properties':{}})
        description = tool.get('description','')
        if kind=='custom':
            parameters = {'type':'object','properties':{'input':{'type':'string','description':'Complete raw input for this tool.'}},'required':['input'],'additionalProperties':False}
            description += '\nProvide the complete free-form tool input in the input string. '+json.dumps(tool.get('format',{}),ensure_ascii=False)
        tools.append({'type':'function','function':{'name':alias,'description':description,'parameters':parameters}})
    def visit(tool, repeated=False):
        if not isinstance(tool,dict): raise ValueError('Tool declarations must be objects.')
        if tool.get('type') in ('web_search', 'web_search_preview'):
            if not hosted_search: raise ValueError('Hosted search requires the installation search service.')
            from brave_search import search_tool
            if 'strata_web_search' in aliases:
                if repeated and aliases['strata_web_search'].get('tool') == tool: return
                raise ValueError('Only one hosted search declaration is supported.')
            add(search_tool(tool))
            aliases['strata_web_search'].update(type='web_search', tool=tool)
        elif tool.get('type')=='tool_search':
            if tool.get('execution')!='client': raise ValueError('Only client-executed tool discovery is supported.')
            add({'type':'function','name':'codex_tool_search','description':tool.get('description',''),
                 'parameters':tool.get('parameters',{'type':'object','properties':{}})},repeated=repeated)
            aliases['codex_tool_search'].update(type='tool_search',name='tool_search')
        elif tool.get('type')=='namespace':
            for nested in tool.get('tools',[]): add(nested,tool['name'],repeated)
        else: add(tool,repeated=repeated)
    for tool in items or []: visit(tool)
    for tool in additional_items: visit(tool,repeated=True)
    return tools, aliases

def to_chat(req, search=None, owner=None):
    def cipher(obj):
        if isinstance(obj,dict): return bool(obj.get('encrypted_content') or obj.get('encrypted_function_args')) or any(cipher(v) for v in obj.values())
        return isinstance(obj,list) and any(cipher(v) for v in obj)
    if cipher(req): raise ValueError('Encrypted input cannot be interpreted by this local provider.')
    if req.get('previous_response_id'): raise ValueError('Send full Responses input history; previous_response_id is unsupported.')
    messages = []
    if req.get('instructions'): messages.append({'role':'system','content':req['instructions']})
    items = req.get('input',[])
    if isinstance(items,str): items=[{'role':'user','content':items}]
    additional = []
    for item in items:
        if item.get('type') in ('additional_tools','tool_search_output'):
            if item.get('type')=='tool_search_output' and item.get('execution')!='client':
                raise ValueError('Only client-executed tool discovery history is supported.')
            declared = item.get('tools')
            if not isinstance(declared,list): raise ValueError(item['type']+' must contain a tools array.')
            additional.extend(declared)
    tools, aliases = tools_to_chat(req.get('tools'), hosted_search=search is not None,
                                  additional_items=additional)
    pending_reasoning = ''
    for item in items:
        kind = item.get('type','message')
        if kind=='additional_tools': continue
        if kind=='reasoning':
            pending_reasoning += ''.join(x.get('text','') for x in item.get('summary',[]))
            continue
        if kind=='message':
            role = item.get('role','user')
            content = item.get('content','')
            if isinstance(content,list):
                if any(x.get('type') not in ('input_text','output_text','text') for x in content):
                    raise ValueError('Only text input is supported by this deployment.')
                content = ''.join(x.get('text','') for x in content)
            msg = {'role':'system' if role=='developer' else role,'content':content}
            if role=='assistant' and pending_reasoning: msg['reasoning_content']=pending_reasoning; pending_reasoning=''
            messages.append(msg)
        elif kind=='web_search_call':
            if search is None: raise ValueError('Search history requires the installation search service.')
            record=search.replay(owner,item['id'])
            call={'id':item['id'],'type':'function','function':{'name':'strata_web_search','arguments':json.dumps(record['arguments'],ensure_ascii=False)}}
            msg={'role':'assistant','content':None,'tool_calls':[call]}
            if pending_reasoning: msg['reasoning_content']=pending_reasoning; pending_reasoning=''
            messages.extend([msg,{'role':'tool','tool_call_id':item['id'],'content':json.dumps(record['result'],ensure_ascii=False)}])
        elif kind in ('function_call','custom_tool_call','tool_search_call'):
            if kind=='tool_search_call':
                if item.get('execution')!='client' or not isinstance(item.get('arguments'),dict) or not item.get('call_id'):
                    raise ValueError('Invalid client tool discovery call.')
                name,namespace='tool_search',None
            else: name, namespace = item['name'], item.get('namespace')
            alias = next((a for a,v in aliases.items() if v['name']==name and v['namespace']==namespace), None)
            if alias is None: alias = 'codex_tool_search' if kind=='tool_search_call' else namespace+'__'+name if namespace else name
            arguments = json.dumps(item['arguments'],ensure_ascii=False) if kind=='tool_search_call' else item.get('arguments','{}') if kind=='function_call' else json.dumps({'input':item['input']},ensure_ascii=False)
            call = {'id':item['call_id'],'type':'function','function':{'name':alias,'arguments':arguments}}
            if messages and messages[-1]['role']=='assistant' and messages[-1].get('tool_calls'):
                messages[-1]['tool_calls'].append(call)
            else:
                msg={'role':'assistant','content':None,'tool_calls':[call]}
                if pending_reasoning: msg['reasoning_content']=pending_reasoning; pending_reasoning=''
                messages.append(msg)
        elif kind in ('function_call_output','custom_tool_call_output','tool_search_output'):
            if kind=='tool_search_output' and not item.get('call_id'): raise ValueError('Tool discovery result requires a call_id.')
            output={'status':item.get('status'),'tools':item['tools']} if kind=='tool_search_output' else item.get('output','')
            if not isinstance(output,str): output=json.dumps(output,ensure_ascii=False)
            messages.append({'role':'tool','tool_call_id':item['call_id'],'content':output})
        else: raise ValueError('Unsupported input item: '+kind)
    systems=[m['content'] for m in messages if m['role']=='system']
    messages=[m for m in messages if m['role']!='system']
    # Hosted results and client-owned results can be interleaved in Responses
    # history. Chat requires one assistant batch followed by all its results.
    normalized=[]; batch=None; results=[]
    for message in messages:
        if message['role']=='assistant' and message.get('tool_calls'):
            if batch is None: batch=dict(message,tool_calls=list(message['tool_calls']))
            else:
                batch['tool_calls'].extend(message['tool_calls'])
                if message.get('reasoning_content'):
                    batch['reasoning_content']=batch.get('reasoning_content','')+message['reasoning_content']
        elif message['role']=='tool' and batch is not None: results.append(message)
        else:
            if batch is not None: normalized.extend([batch,*results]); batch=None; results=[]
            normalized.append(message)
    if batch is not None: normalized.extend([batch,*results])
    messages=normalized
    if systems: messages.insert(0,{'role':'system','content':'\n\n'.join(systems)})
    chat={'model':req.get('model','qwen3.8-flash-next-q2_0'),'messages':messages,'stream':True,
          'stream_options':{'include_usage':True},'max_tokens':req.get('max_output_tokens',8192),
          'reasoning_effort':(req.get('reasoning') or {}).get('effort','low'),'reasoning_budget_tokens':2048}
    effort=chat['reasoning_effort']
    defaults={'none':(0,8192),'low':(2048,8192),'medium':(4096,16384),'high':(8192,24576),'xhigh':(8192,24576),'max':(8192,24576)}
    budget,output=defaults.get(effort,(2048,8192))
    if not req.get('max_output_tokens'):chat['max_tokens']=output
    if budget:chat['reasoning_budget_tokens']=min(budget,max(1,chat['max_tokens']//2))
    else:chat.pop('reasoning_budget_tokens',None)
    if tools: chat['tools']=tools
    if req.get('tool_choice') in ('auto','none','required'): chat['tool_choice']=req['tool_choice']
    elif isinstance(req.get('tool_choice'),dict) and req['tool_choice'].get('type') in ('web_search','web_search_preview'):
        if 'strata_web_search' not in aliases: raise ValueError('No hosted search tool was declared.')
        chat['tool_choice']={'type':'function','function':{'name':'strata_web_search'}}
    for key in ('temperature','top_p'):
        if key in req: chat[key]=req[key]
    return chat, aliases


def apply_request_defaults(chat, original, defaults, responses=False):
    """Owner-selected defaults; explicit request values and other efforts win."""
    explicit_effort=('effort'in(original.get('reasoning')or{}))if responses else 'reasoning_effort'in original
    if not explicit_effort and 'reasoning_effort'in defaults:
        chat['reasoning_effort']=defaults['reasoning_effort']
    sampling = ('temperature','top_p','top_k','min_p','presence_penalty',
                'frequency_penalty','repetition_penalty','penalty_last_n')
    for key in sampling:
        if key not in original and key in defaults:
            chat[key] = defaults[key]
    effort = chat.get('reasoning_effort','low')
    if effort == defaults.get('reasoning_effort'):
        explicit_output = 'max_output_tokens' in original if responses else 'max_tokens' in original
        if not explicit_output and 'max_tokens' in defaults:
            chat['max_tokens'] = defaults['max_tokens']
        if 'reasoning_budget_tokens' not in original and 'reasoning_budget_tokens' in defaults:
            chat['reasoning_budget_tokens'] = min(defaults['reasoning_budget_tokens'],chat.get('max_tokens',8192)//2)
    return chat

class ModelSelectionError(ValueError):
    def __init__(self, message, *, status, code):
        super().__init__(message)
        self.status, self.code = status, code


def bind_loaded_model(request, ownership, key):
    """Resolve an omitted model and reject a mismatch before any inference."""
    if not isinstance(request, dict):
        raise ModelSelectionError('Generation request must be an object.', status=400, code='invalid_request')
    from service_access import AccessError
    try:
        state = ownership.status(key)
    except AccessError:
        raise
    except Exception as error:
        raise ModelSelectionError('Unable to verify the loaded model.', status=503, code='model_not_ready') from error
    if not isinstance(state, dict):
        raise ModelSelectionError('Unable to verify the loaded model.', status=503, code='model_not_ready')
    loaded = state.get('model')
    if state.get('status') != 'running' or not isinstance(loaded, str) or not loaded:
        raise ModelSelectionError('No loaded model is ready. Start a model through /ownership/start.',
                                  status=503, code='model_not_ready')
    requested = request.get('model', loaded)
    if not isinstance(requested, str) or not requested:
        raise ModelSelectionError('model must be a non-empty string.', status=400, code='invalid_model')
    if requested != loaded:
        raise ModelSelectionError('Requested model does not match the loaded model. Stop the current model '
                                  'through /ownership/stop, then select the target through /ownership/start.',
                                  status=409, code='model_mismatch')
    return dict(request, model=loaded)


class Translator:
    def __init__(self, emit, req, aliases):
        self.emit_raw, self.req, self.aliases=emit,req,aliases
        self.sequence=0; self.items=[]; self.calls={}; self.text_item=None; self.reason_item=None
        self.closed=set(); self.sources={}
        self.response={'id':uid('resp_'),'object':'response','created_at':int(time.time()),'status':'in_progress','model':req.get('model','qwen3.8-flash-next-q2_0'),'output':[],'usage':None,'error':None,'incomplete_details':None}
    def emit(self, kind, **data):
        self.emit_raw(dict(type=kind,sequence_number=self.sequence,**data)); self.sequence+=1
    def begin(self):
        self.emit('response.created',response=self.response.copy()); self.emit('response.in_progress',response=self.response.copy())
    def add(self,item):
        index=len(self.items); self.items.append(item)
        self.emit('response.output_item.added',output_index=index,item=json.loads(json.dumps(item)))
        return index
    def accept(self,event):
        for choice in event.get('choices',[]):
            delta=choice.get('delta',{})
            reason=delta.get('reasoning_content')
            if reason:
                if self.reason_item is None:
                    item={'id':uid('rs_'),'type':'reasoning','summary':[{'type':'summary_text','text':''}]}
                    self.reason_item=self.add(item)
                    self.emit('response.reasoning_summary_part.added',item_id=item['id'],output_index=self.reason_item,summary_index=0,part=item['summary'][0].copy())
                item=self.items[self.reason_item]; item['summary'][0]['text']+=reason
                self.emit('response.reasoning_summary_text.delta',item_id=item['id'],output_index=self.reason_item,summary_index=0,delta=reason)
            text=delta.get('content')
            if text:
                if self.text_item is None:
                    item={'id':uid('msg_'),'type':'message','role':'assistant','status':'in_progress','content':[{'type':'output_text','text':'','annotations':[]}]}
                    self.text_item=self.add(item)
                    self.emit('response.content_part.added',item_id=item['id'],output_index=self.text_item,content_index=0,part=item['content'][0].copy())
                item=self.items[self.text_item]; item['content'][0]['text']+=text
                self.emit('response.output_text.delta',item_id=item['id'],output_index=self.text_item,content_index=0,delta=text)
            for call in delta.get('tool_calls',[]):
                key=call.get('index',0); fn=call.get('function',{})
                record=self.calls.setdefault(key,{'id':None,'name':'','args':''})
                if call.get('id'): record['id']=call['id']
                if fn.get('name'): record['name']+=fn['name']
                record['args']+=fn.get('arguments','')
        if event.get('usage'): self.usage=event['usage']
        for choice in event.get('choices',[]):
            if choice.get('finish_reason'): self.finish_reason=choice['finish_reason']
    def finish(self, final=True, skip_tools=()):
        for index,item in enumerate(self.items):
            if index in self.closed or item['type']=='web_search_call': continue
            if item['type']=='message':
                part=item['content'][0]; item['status']='completed'
                for match in re.finditer(r'\[[^\]\n]+\]\((https?://[^\s)]+)\)',part['text']):
                    url=match.group(1)
                    if url in self.sources:
                        annotation={'type':'url_citation','url':url,'title':self.sources[url],
                                    'start_index':match.start(),'end_index':match.end()}
                        part['annotations'].append(annotation)
                        self.emit('response.output_text.annotation.added',item_id=item['id'],output_index=index,
                                  content_index=0,annotation_index=len(part['annotations'])-1,annotation=annotation)
                self.emit('response.output_text.done',item_id=item['id'],output_index=index,content_index=0,text=part['text'])
                self.emit('response.content_part.done',item_id=item['id'],output_index=index,content_index=0,part=part)
            else:
                part=item['summary'][0]
                self.emit('response.reasoning_summary_text.done',item_id=item['id'],output_index=index,summary_index=0,text=part['text'])
                self.emit('response.reasoning_summary_part.done',item_id=item['id'],output_index=index,summary_index=0,part=part)
            self.emit('response.output_item.done',output_index=index,item=item)
            self.closed.add(index)
        for record in self.calls.values():
            if record['name'] in skip_tools: continue
            meta=self.aliases.get(record['name'])
            if meta is None: raise ValueError('Model returned unknown tool: '+record['name'])
            if meta['type']=='tool_search':
                value=json.loads(record['args'])
                if not isinstance(value,dict): raise ValueError('Tool discovery arguments must be an object.')
                item={'id':uid('tsc_'),'type':'tool_search_call','execution':'client','status':'completed',
                      'call_id':record['id'] or uid('call_'),'arguments':value}
                index=self.add(item)
                self.emit('response.output_item.done',output_index=index,item=item)
                self.closed.add(index)
                continue
            item={'id':uid('fc_'),'type':'function_call' if meta['type']=='function' else 'custom_tool_call','call_id':record['id'] or uid('call_'),'name':meta['name'],'status':'in_progress'}
            if meta['namespace']: item['namespace']=meta['namespace']
            field='arguments' if meta['type']=='function' else 'input'
            value=record['args'] if field=='arguments' else json.loads(record['args'])['input']
            if field=='arguments': json.loads(value)
            item[field]=''; index=self.add(item)
            event='response.function_call_arguments' if field=='arguments' else 'response.custom_tool_call_input'
            self.emit(event+'.delta',item_id=item['id'],output_index=index,delta=value)
            item[field]=value; item['status']='completed'
            self.emit(event+'.done',item_id=item['id'],output_index=index,**{field:value})
            self.emit('response.output_item.done',output_index=index,item=item)
            self.closed.add(index)
        if not final: return
        return self.complete()
    def complete(self, usage=None):
        raw=getattr(self,'usage',{})
        self.response['usage']=usage if usage is not None else {'input_tokens':raw.get('prompt_tokens',0),'output_tokens':raw.get('completion_tokens',0),'total_tokens':raw.get('total_tokens',0),'input_tokens_details':{'cached_tokens':raw.get('prompt_tokens_details',{}).get('cached_tokens',0)},'output_tokens_details':{'reasoning_tokens':raw.get('completion_tokens_details',{}).get('reasoning_tokens',0)}}
        incomplete=getattr(self,'finish_reason',None)=='length'
        self.response.update(output=self.items,status='incomplete' if incomplete else 'completed',incomplete_details={'reason':'max_output_tokens'} if incomplete else None)
        self.emit('response.incomplete' if incomplete else 'response.completed',response=self.response)
        return self.response

    def fail(self, code, message):
        # Codex recognizes a failed Response terminal, rather than a flat SSE
        # error followed by EOF. Retain partial items without completing them.
        self.response.update(status='failed', output=self.items,
                             error={'code':'server_error', 'message':f'[{code}] {message}'})
        self.emit('response.failed', response=self.response)
        return self.response

class Handler(BaseHTTPRequestHandler):
    protocol_version='HTTP/1.1'
    def authorized(self):
        clients=getattr(self.server,'allowed_clients',None)
        if clients is not None and self.client_address[0] not in clients:
            self.close_connection=True
            self.send_json(403,{'error':{'message':'Client address is not allowed.'}})
            return False
        ownership=getattr(self.server,'ownership',None)
        if ownership is not None:
            from service_access import bearer, AccessError
            try:
                ownership.require(bearer(self.headers))
            except AccessError as error:
                self.close_connection=True
                self.send_json(error.status,{'error':{'message':str(error)}})
                return False
        return True
    def log_message(self,*args): pass
    def send_json(self,status,value):
        raw=json.dumps(value,ensure_ascii=False).encode(); self.send_response(status)
        self.send_header('Content-Type','application/json'); self.send_header('Content-Length',str(len(raw))); self.end_headers(); self.wfile.write(raw)
    def do_GET(self):
        ownership=getattr(self.server,'ownership',None)
        if self.path=='/health' and ownership is not None:
            clients=getattr(self.server,'allowed_clients',None)
            if clients is not None and self.client_address[0] not in clients:
                return self.send_json(403,{'error':{'message':'Client address is not allowed.'}})
            try:
                self.send_json(200,{'status':'ok','service':'strata-responses-bridge','backend':self.server.backend,
                                   'controller':True,**ownership.available()})
            except Exception:
                self.send_json(503,{'error':{'message':'Controller state inspection failed.'}})
            return
        if not self.authorized(): return
        if self.path=='/ownership/status' and ownership is not None:
            from service_access import bearer
            try: self.send_json(200,ownership.status(bearer(self.headers)))
            except Exception: self.send_json(503,{'error':{'message':'Model status inspection failed.'}})
            return
        if self.path=='/health': self.send_json(200,{'status':'ok','service':'strata-responses-bridge','backend':self.server.backend})
        else: self.send_json(404,{'error':{'message':'Unknown endpoint'}})
    def do_POST(self):
        ownership=getattr(self.server,'ownership',None)
        if ownership is not None and self.path in ('/ownership/acquire','/ownership/start','/ownership/stop','/ownership/release'):
            clients=getattr(self.server,'allowed_clients',None)
            if clients is not None and self.client_address[0] not in clients:
                return self.send_json(403,{'error':{'message':'Client address is not allowed.'}})
            from service_access import bearer, AccessError
            try:
                size=int(self.headers.get('Content-Length',0))
                if size<0 or size>65536: raise ValueError('Invalid control request size.')
                body=json.loads(self.rfile.read(size) or b'{}')
                if not isinstance(body,dict): raise ValueError('Control request must be an object.')
                action=self.path.rsplit('/',1)[1]
                if action=='acquire': result=ownership.acquire()
                elif action=='start': result=ownership.start(bearer(self.headers),body)
                elif action=='stop': result=ownership.stop(bearer(self.headers))
                else: result=ownership.release(bearer(self.headers))
                self.send_json(200,result)
            except AccessError as error: self.send_json(error.status,{'error':{'message':str(error)}})
            except (ValueError,TypeError,KeyError) as error: self.send_json(400,{'error':{'message':str(error)}})
            except Exception as error: self.send_json(503,{'error':{'message':str(error)}})
            return
        if not self.authorized(): return
        if self.path=='/v1/chat/completions' and ownership is not None:
            from service_access import bearer, AccessError
            upstream=None
            try:
                size=int(self.headers.get('Content-Length',0))
                if size<0 or size>32*1024*1024: raise ValueError('Invalid request size.')
                original=bind_loaded_model(json.loads(self.rfile.read(size)),ownership,bearer(self.headers))
                if hasattr(ownership.backend,'request_defaults'):
                    original=apply_request_defaults(dict(original),original,ownership.backend.request_defaults())
                raw=json.dumps(original).encode()
                headers={'Content-Type':'application/json','Authorization':'Bearer '+bearer(self.headers)}
                opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
                upstream=opener.open(urllib.request.Request(self.server.backend+'/v1/chat/completions',raw,headers),
                                     timeout=getattr(self.server,'upstream_timeout',900))
                self.send_response(upstream.status)
                self.send_header('Content-Type',upstream.headers.get('Content-Type','application/json'))
                self.send_header('Connection','close');self.end_headers();self.close_connection=True
                while chunk:=upstream.read1(65536):
                    self.wfile.write(chunk);self.wfile.flush()
            except ModelSelectionError as error:
                self.send_json(error.status,{'error':{'message':str(error),'type':'invalid_request_error','code':error.code}})
            except AccessError as error:
                self.send_json(error.status,{'error':{'message':str(error)}})
            except urllib.error.HTTPError as error:
                self.send_json(error.code,{'error':{'message':error.read().decode('utf-8','replace')}});error.close()
            except (OSError,ValueError) as error:
                if upstream is None: self.send_json(503,{'error':{'message':str(error)}})
                self.close_connection=True
            finally:
                if upstream: upstream.close()
            return
        if self.path not in ('/responses','/v1/responses'): return self.send_json(404,{'error':{'message':'Unknown endpoint'}})
        upstream=None; streamed=False; trace=uid('request_'); translator=None
        def failure(code, message, error):
            # Always log attribution, including when full tracing is disabled.
            # Deliberately exclude arbitrary exception text and tool arguments.
            diagnostic={'request_id':trace, 'code':code, 'error_type':type(error).__name__,
                        'tool_calls':{str(k):{'name':re.sub(r'[^A-Za-z0-9_.-]', '?', v['name'])[:128]}
                                      for k,v in getattr(translator,'calls',{}).items()}}
            try:
                print(json.dumps(diagnostic),file=sys.stderr,flush=True)
                if getattr(self.server,'trace',None):
                    (self.server.trace/(trace+'-error.json')).write_text(
                        json.dumps(diagnostic,indent=2),encoding='utf-8')
            except OSError: pass
            if streamed and translator is not None:
                try: translator.fail(code,message)
                except OSError: pass
        try:
            size=int(self.headers.get('Content-Length',0))
            if size>32*1024*1024: raise ValueError('Request exceeds 32 MiB.')
            if size<0: raise ValueError('Invalid request size.')
            req=json.loads(self.rfile.read(size))
            from service_access import bearer, AccessError
            owner=bearer(self.headers)
            if ownership is not None:
                req=bind_loaded_model(req,ownership,owner)
            search=getattr(self.server,'search',None)
            chat,aliases=to_chat(req,search,owner)
            if ownership is not None and hasattr(ownership.backend,'request_defaults'):
                apply_request_defaults(chat,req,ownership.backend.request_defaults(),responses=True)
            if self.server.trace: (self.server.trace/(trace+'-input.json')).write_text(json.dumps(req,ensure_ascii=False,indent=2),encoding='utf-8')
            if self.server.trace: (self.server.trace/(trace+'-forwarded.json')).write_text(json.dumps(chat,ensure_ascii=False,indent=2),encoding='utf-8')
            headers={'Content-Type':'application/json'}
            if ownership is not None:
                from service_access import bearer
                headers['Authorization']='Bearer '+bearer(self.headers)
            opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
            upstream=opener.open(urllib.request.Request(self.server.backend+'/v1/chat/completions',json.dumps(chat,ensure_ascii=False).encode(),headers),timeout=getattr(self.server,'upstream_timeout',900))
            streamed=req.get('stream',False); events=[]
            if streamed:
                self.send_response(200); self.send_header('Content-Type','text/event-stream'); self.send_header('Cache-Control','no-cache'); self.send_header('Connection','close'); self.end_headers(); self.close_connection=True
            def emit(event):
                events.append(event)
                if streamed:
                    self.wfile.write(('event: '+event['type']+'\ndata: '+json.dumps(event,ensure_ascii=False)+'\n\n').encode()); self.wfile.flush()
            translator=Translator(emit,req,aliases); translator.begin(); done=False
            def check():
                if ownership is not None: ownership.require(owner)
                if streamed and select.select([self.connection],[],[],0)[0]:
                    if not self.connection.recv(1,socket.MSG_PEEK):
                        raise BrokenPipeError('Caller disconnected; hosted work was cancelled.')
            first=[upstream]
            def generate(current):
                check()
                if first: connection=first.pop()
                else:
                    connection=opener.open(urllib.request.Request(self.server.backend+'/v1/chat/completions',json.dumps(current,ensure_ascii=False).encode(),headers),timeout=getattr(self.server,'upstream_timeout',900))
                ended=False
                try:
                    for raw in connection:
                        check()
                        line=raw.decode('utf-8').strip()
                        if line.startswith(':') and streamed: self.wfile.write(b': heartbeat\n\n'); self.wfile.flush()
                        if not line.startswith('data: '): continue
                        if line=='data: [DONE]': ended=True; break
                        event=json.loads(line[6:])
                        if event.get('error'): raise UpstreamFailure(str(event['error']))
                        yield event
                    if not ended: raise UpstreamFailure('Upstream stream ended without [DONE].')
                finally: connection.close()
            if any(meta['type']=='web_search' for meta in aliases.values()):
                if ownership is None: raise ValueError('Hosted search requires the exclusive controller.')
                from hosted_search import run_hosted
                response=run_hosted(translator,chat,aliases,search,owner,check,generate)
            else:
                for event in generate(chat): translator.accept(event)
                response=translator.finish()
            if self.server.trace:
                (self.server.trace/(trace+'-output.json')).write_text(json.dumps(response,ensure_ascii=False,indent=2),encoding='utf-8')
            if not streamed: self.send_json(200,response)
        except BrokenPipeError: pass
        except ModelSelectionError as error:
            failure(error.code,str(error),error)
            if not streamed: self.send_json(error.status,{'error':{'message':str(error),'type':'invalid_request_error','code':error.code}})
        except AccessError as error:
            failure('access_denied',str(error),error)
            if not streamed: self.send_json(error.status,{'error':{'message':str(error)}})
        except urllib.error.HTTPError as error:
            detail=error.read().decode('utf-8','replace');error.close()
            failure('upstream_error','Local model returned HTTP '+str(error.code),error)
            if not streamed: self.send_json(error.code,{'error':{'message':detail,'type':'upstream_error'}})
        except (urllib.error.URLError,TimeoutError,ConnectionResetError) as error:
            timeout=isinstance(error,TimeoutError) or isinstance(getattr(error,'reason',None),TimeoutError)
            code=504 if timeout else 503
            message='Upstream timeout' if timeout else 'Upstream connection failed: '+str(error)
            failure('upstream_timeout' if timeout else 'upstream_error',message,error)
            if not streamed: self.send_json(code,{'error':{'message':message,'type':'upstream_timeout' if timeout else 'upstream_error'}})
        except UpstreamFailure as error:
            failure('upstream_error',str(error),error)
            if not streamed: self.send_json(503,{'error':{'message':str(error),'type':'upstream_error'}})
        except Exception as error:
            failure('invalid_response',str(error),error)
            if not streamed: self.send_json(400,{'error':{'message':str(error),'type':'invalid_request_error'}})
        finally:
            if upstream: upstream.close()

def bind_policy(host,clients):
    address=ipaddress.IPv4Address(host)
    if not address.is_loopback and not any(address in network for network in (
        ipaddress.IPv4Network('10.0.0.0/8'),ipaddress.IPv4Network('172.16.0.0/12'),ipaddress.IPv4Network('192.168.0.0/16'))):
        raise ValueError('Bind to localhost or a specific private IPv4 address.')
    allowed={str(ipaddress.IPv4Address(value)) for value in clients}
    if not address.is_loopback and not allowed:
        raise ValueError('A non-loopback listener requires explicit --allow-client addresses.')
    return str(address),allowed or None

if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--port',type=int,default=8101); parser.add_argument('--backend',default='http://127.0.0.1:8100'); parser.add_argument('--trace',type=Path); parser.add_argument('--upstream-timeout',type=float,default=900)
    parser.add_argument('--host',default='127.0.0.1'); parser.add_argument('--allow-client',action='append',default=[])
    parser.add_argument('--access-file',type=Path)
    parser.add_argument('--model-port',type=int,default=8100)
    parser.add_argument('--api-base-url')
    args=parser.parse_args()
    try: host,clients=bind_policy(args.host,args.allow_client)
    except ValueError as error: parser.error(str(error))
    if not 1<=args.port<=65535 or not 1<=args.model_port<=65535 or args.port==args.model_port: raise SystemExit('Controller/model ports must be valid and distinct.')
    if args.backend not in (f'http://127.0.0.1:{args.model_port}',f'http://{host}:{args.model_port}'): raise SystemExit('Backend must be the local Strata service on the selected model port.')
    if args.api_base_url:
        from urllib.parse import urlsplit
        advertised=urlsplit(args.api_base_url)
        if advertised.scheme not in ('http','https') or not advertised.hostname or not advertised.port or advertised.username or advertised.password or advertised.path or advertised.query or advertised.fragment: raise SystemExit('Invalid advertised API base URL.')
    if args.upstream_timeout<=0: raise SystemExit('Upstream timeout must be positive.')
    if args.trace: args.trace.mkdir(parents=True,exist_ok=True)
    server=ThreadingHTTPServer((host,args.port),Handler); server.backend=args.backend; server.trace=args.trace; server.upstream_timeout=args.upstream_timeout; server.allowed_clients=clients
    if args.access_file:
        from service_access import Ownership
        from controller_backend import Backend
        from urllib.parse import urlsplit
        server.ownership=Ownership(args.access_file,Backend(host,args.access_file,
            model_host=urlsplit(args.backend).hostname,model_port=args.model_port,
            api_port=args.port,api_base_url=args.api_base_url))
        from brave_search import BraveSearch
        server.search=BraveSearch(args.access_file.parent)
    print('Responses bridge ready: http://'+host+':'+str(args.port)+'/v1',flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()
