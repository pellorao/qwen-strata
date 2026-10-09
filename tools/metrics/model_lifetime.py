"""Model-alive duration, preserving interval estimates and their bounds."""
from pathlib import Path
import json


def alive_seconds(task_start_ms, task_end_ms, intervals):
    clipped=[]
    for interval in intervals:
        start=max(task_start_ms,interval['start_ms'])
        end=min(task_end_ms,interval['end_ms'])
        if end>start:clipped.append((start,end))
    merged=[]
    for start,end in sorted(clipped):
        if merged and start<=merged[-1][1]:merged[-1]=(merged[-1][0],max(end,merged[-1][1]))
        else:merged.append((start,end))
    return sum(end-start for start,end in merged)/1000


def historical_alive_time(batch,folder,original,task_start_ms,task_end_ms):
    """Estimate missing lifecycle timestamps from preserved capture receipts.

    File times are estimates, never called exact process events. Review intervals
    establish a lower bound; stop-confirmed result writes bound uncertain exits.
    """
    load=lambda path:json.loads(Path(path).read_text())
    intervals=[]
    end=original['measurement']['startedAt']+original['measurement']['wallClockMs']
    continued=batch/'premature-continuations'/folder.name
    # Prefer captured lifecycle transitions for new runs; keep historical estimates
    # only when an old part of the same task has no transition ledger.
    ledger_paths=[folder/'model-alive-events.json',continued/'model-alive-events.json']
    continued_closed=(continued/'run-finished.json').exists()
    if ledger_paths[0].exists() and (not continued_closed or ledger_paths[1].exists()):
        captured=[];estimated=False
        for path in ledger_paths:
            if not path.exists():continue
            opened=None
            for event in load(path):
                estimated=estimated or event.get('estimated',False)
                if event['alive']:opened=event['at']*1000
                elif opened is not None:
                    captured.append({'start_ms':opened,'end_ms':event['at']*1000});opened=None
            if opened is not None:captured.append({'start_ms':opened,'end_ms':task_end_ms})
        seconds=alive_seconds(task_start_ms,task_end_ms,captured)
        return {'seconds':seconds,'estimated':estimated,'lower_seconds':None,'upper_seconds':None,
            'basis':'Persisted model start/status/stop transitions; request/receipt uncertainty preserved in lifecycle ledgers','intervals':captured}

    if not (continued/'run-finished.json').exists():
        return {'seconds':(task_end_ms-task_start_ms)/1000,'estimated':False,
            'lower_seconds':(task_end_ms-task_start_ms)/1000,
            'upper_seconds':(task_end_ms-task_start_ms)/1000,
            'basis':'Single review remained under the same loaded model; no restart before task end',
            'intervals':[{'start_ms':task_start_ms,'end_ms':task_end_ms,'estimated':False}]}
    initial_result=folder/original['instanceId']/'result.json'
    closed=load(folder/'run-finished.json')['finished_at']*1000
    stop_estimate=min(closed,initial_result.stat().st_mtime*1000)
    stop_estimate=max(end,stop_estimate)
    intervals.append({'start_ms':task_start_ms,'end_ms':stop_estimate,
        'estimated':True,'lower_end_ms':end,'upper_end_ms':closed,
        'basis':'Initial result written after protected model stop; file timestamp estimates stop receipt'})
    segments=load(continued/'segments.json')
    receipts=[continued/'start-status.json']+sorted(continued.glob('http-observers/*/start-status.json'))
    boots=[]
    for path in receipts:
        if not path.exists():continue
        receipt=load(path)
        if receipt['load_s']<=0:continue
        confirmed=path.stat().st_mtime*1000
        boots.append({'start_ms':confirmed-receipt['load_s']*1000,
            'lower_start_ms':confirmed-receipt['load_s']*1000,'upper_start_ms':confirmed,
            'estimated':True,'basis':'Start-status write minus measured start-call duration; includes model startup estimate',
            'model_pid':receipt['status']['model_pid'],'receipt':str(path.relative_to(batch))})
    boots.sort(key=lambda x:x['start_ms'])
    blocked=continued/'blocked-with-clean-ownership.json'
    stop_before_boot=load(blocked)['finished_at']*1000 if blocked.exists() else None
    for index,boot in enumerate(boots):
        next_start=boots[index+1]['start_ms'] if index+1<len(boots) else task_end_ms+1
        group=[s for s in segments if boot['start_ms']<=s['started_at']*1000<next_start]
        if not group:continue
        last_end=max(s['finished_at']*1000 for s in group)
        final_boot=index==len(boots)-1
        stop=task_end_ms if final_boot else min(next_start,stop_before_boot or last_end)
        intervals.append({**boot,'end_ms':stop,'lower_end_ms':last_end,'upper_end_ms':stop,
            'basis':boot['basis']+'; model retained between rounds until task end or confirmed pre-restart release'})
    seconds=alive_seconds(task_start_ms,task_end_ms,intervals)
    lower=[{'start_ms':i.get('upper_start_ms',i['start_ms']),
            'end_ms':i.get('lower_end_ms',i['end_ms'])} for i in intervals]
    upper=[{'start_ms':i.get('lower_start_ms',i['start_ms']),
            'end_ms':i.get('upper_end_ms',i['end_ms'])} for i in intervals]
    return {'seconds':seconds,'estimated':True,'lower_seconds':alive_seconds(task_start_ms,task_end_ms,lower),
        'upper_seconds':alive_seconds(task_start_ms,task_end_ms,upper),
        'basis':'Historical start/stop transitions were not timestamped; receipt/file-time estimates, same-model gaps retained',
        'intervals':intervals}


class ModelAliveClock:
    """Persisted model transitions; waiting while alive continues to count."""
    def __init__(self,path):
        self.path=Path(path)
        self.events=json.loads(self.path.read_text()) if self.path.exists() else []

    def observe(self,alive,at,estimated=False,bounds=None):
        if self.events and at<self.events[-1]['at']:
            raise ValueError('Model lifetime event order changed')
        if self.events and self.events[-1]['alive']==alive:return
        self.events.append({'alive':bool(alive),'at':at,'estimated':estimated,'bounds':bounds})
        self.path.parent.mkdir(parents=True,exist_ok=True)
        stage=self.path.with_suffix('.json.stage')
        stage.write_text(json.dumps(self.events,indent=2)+'\n');stage.replace(self.path)

    def elapsed(self,start,end):
        intervals=[]
        opened=None
        for event in self.events:
            if event['alive']:opened=event['at']
            elif opened is not None:
                intervals.append({'start_ms':opened*1000,'end_ms':event['at']*1000});opened=None
        if opened is not None:intervals.append({'start_ms':opened*1000,'end_ms':end*1000})
        return alive_seconds(start*1000,end*1000,intervals)
