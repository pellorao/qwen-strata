"""Collect native Chat SSE text and timing; API usage is diagnostic only."""
import hashlib
import json
import time
import urllib.request


def collect(lines, now=time.monotonic, deadline=None):
    started=now();first=None;content=[];reasoning=[];finish=None;done=False;raw=[]
    for line in lines:
        if deadline is not None and now()>=deadline:raise TimeoutError('Logical streamed Chat deadline reached')
        raw.append(line)
        if not line.startswith(b'data:'):continue
        data=line[5:].strip()
        if data==b'[DONE]':done=True;break
        item=json.loads(data)
        if item.get('error'):raise RuntimeError('Native streamed Chat returned an error')
        for choice in item.get('choices',[]):
            if choice.get('index',0)!=0:continue
            delta=choice.get('delta',{})
            text=delta.get('content') or '';thought=delta.get('reasoning_content') or ''
            if text or thought:
                if first is None:first=now()-started
                content.append(text);reasoning.append(thought)
            if choice.get('finish_reason') is not None:finish=choice['finish_reason']
    if not done or finish is None:raise RuntimeError('Native streamed Chat terminal is incomplete')
    response={'choices':[{'index':0,'finish_reason':finish,'message':{
        'role':'assistant','content':''.join(content),'reasoning_content':''.join(reasoning)}}]}
    return response,{'first_model_text_delta_seconds':first,
        'first_delta_timing_basis':'Observed nonempty reasoning/content SSE delta; network delivery included, not exact engine first-token time.',
        'stream_done':done,'finish_reason':finish},b''.join(raw)


def request(owner, body, folder, number, timeout):
    started=time.monotonic()
    req=urllib.request.Request(owner.base+'/v1/chat/completions',json.dumps(body).encode(),
        {'Content-Type':'application/json','Authorization':'Bearer '+owner.key})
    with owner.opener.open(req,timeout=timeout) as reply:
        headers_at=time.monotonic()
        with (folder/f'response-{number}.sse').open('wb') as evidence:
            def observed_lines():
                for line in reply:
                    evidence.write(line);evidence.flush();yield line
            response,timing,raw=collect(observed_lines(),deadline=started+timeout)
    if timing['first_model_text_delta_seconds'] is not None:
        timing['first_model_text_delta_seconds']+=headers_at-started
    (folder/f'response-{number}.sse').write_bytes(raw)
    timing['sse_sha256']=hashlib.sha256(raw).hexdigest()
    (folder/f'response-{number}-timing.json').write_text(json.dumps(timing,indent=2)+'\n')
    return response,timing
