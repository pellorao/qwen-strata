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
