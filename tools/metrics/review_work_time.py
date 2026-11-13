"""Review work intervals, excluding shutdown and idle between completed turns."""
import json
from tools.metrics.model_lifetime import alive_seconds, ModelAliveClock


def recorded_work_time(batch, folder, original, final_end_ms):
    start=original['measurement']['startedAt']
    original_end=original['measurement'].get('finishedAt')
    estimated=original_end is None
    if original_end is None:
        original_end=start+original['measurement']['wallClockMs']
    intervals=[{'start_ms':start,'end_ms':original_end,
                'estimated':estimated,'basis':'Original ARW start/end; last observed wall duration if end absent'}]
    continued=batch/'premature-continuations'/folder.name
    if (continued/'run-finished.json').exists():
        for segment in json.loads((continued/'segments.json').read_text()):
            measurement=segment.get('measurement') or {}
            if measurement.get('startedAt') is None or measurement.get('finishedAt') is None:
                raise ValueError(f'continuation segment of {folder.name} lacks measurement startedAt/finishedAt')
            intervals.append({'start_ms':measurement['startedAt'],
                              'end_ms':measurement['finishedAt'],
                              'estimated':False,'basis':'Bound continuation measurement/native terminal'})
        cutoff=continued/'hard-budget-native-facts-failure.json'
        if cutoff.exists():
            receipt=json.loads(cutoff.read_text())
            if receipt.get('protected_stop'):
                # Old stop receipts lack a completed-at timestamp. Use the known
                # stop intent as an explicit estimate, never an exact exit event.
                stop_s=receipt.get('protected_stop_completed_at')
                if stop_s is None:stop_s=receipt.get('at')
                if stop_s is None:
                    raise ValueError(f'{cutoff} has neither protected_stop_completed_at nor at')
                stop_ms=stop_s*1000
                # Later authorized continuations must not move the historical
                # stop boundary onto a new segment or erase the old idle gap.
                for interval in intervals:
                    if interval['start_ms']<stop_ms<interval['end_ms']:
                        interval['uncut_end_ms']=interval['end_ms'];interval['end_ms']=stop_ms
                        interval['estimated']='protected_stop_completed_at' not in receipt
                        interval['basis']='Protected stop receipt or estimated stop intent; post-stop retry excluded'
    seconds=alive_seconds(start,final_end_ms,intervals)
    estimated=any(i['estimated'] for i in intervals)
    return {'seconds':seconds,'estimated':estimated,'intervals':intervals,
            'basis':'Reviewer work intervals, including tools and in-turn recovery; shutdown and completed-turn sleep excluded'}


class ReviewWorkClock(ModelAliveClock):
    """Same interval clock, with states meaning working/idle rather than loaded."""
    def set_working(self,working,at,estimated=False):
        self.observe(working,at,estimated=estimated)
