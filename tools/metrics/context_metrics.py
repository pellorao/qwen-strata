"""Compaction evidence from one native Reviewer history, independent of scoring."""
import hashlib
import json
import math
from pathlib import Path


def engine_token_speeds(tokens, prompt_seconds, decode_seconds):
    """Engine rates for one scope; cache reuse is not a prefill numerator."""
    def rate(key, seconds):
        count = tokens.get(key)
        if count is None or seconds is None:
            return None
        if (isinstance(count, bool) or not isinstance(count, int) or count < 0
                or isinstance(seconds, bool) or not isinstance(seconds, (int, float))
                or not math.isfinite(seconds) or seconds < 0):
            raise ValueError('Invalid raw engine counter or phase duration')
        return count / seconds if seconds else None
    return {'input_tokens_per_second': rate('uncached_input', prompt_seconds),
            'output_tokens_per_second': rate('output', decode_seconds)}


def inspect_compactions(path):
    path=Path(path);raw=path.read_bytes()
    events=[json.loads(line) for line in raw.splitlines() if line.strip()]
    seen={};failures=[];continued=[]
    for index,event in enumerate(events):
        payload=event.get('payload',{})
        if event.get('type')=='compacted':
            response=payload.get('compaction_response_id');window=payload.get('window_id')
            if not response or not window or not isinstance(payload.get('replacement_history'),list):
                raise ValueError('Compaction lacks response/window identity or completed replacement history')
            key=(response,window)
            if key in seen:
                continue
            future=[e for e in events[index+1:] if e.get('type')=='response_item'
                    and e.get('payload',{}).get('type') in ('function_call','custom_tool_call','message','web_search_call')]
            row={'response_id':response,'window_id':window,'window_number':payload.get('window_number'),
                 'timestamp':event.get('timestamp'),'ordinal':event.get('ordinal'),
                 'replacement_history_items':len(payload['replacement_history']),
                 'continued_after':bool(future)}
            seen[key]=row;continued.append(bool(future))
        if event.get('type')=='event_msg' and payload.get('type')=='error':
            text=json.dumps(payload,ensure_ascii=False)
            if 'compact' in text.lower():
                failures.append({'timestamp':event.get('timestamp'),'ordinal':event.get('ordinal'),'payload':payload})
    return {'source_path':str(path),'source_sha256':hashlib.sha256(raw).hexdigest(),
            'successful_compaction_count':len(seen),'successful_compactions':list(seen.values()),
            'observed_failed_compaction_count':len(failures),'observed_failed_compactions':failures,
            'continued_after_every_success':bool(continued) and all(continued),
            'scope':'Native completed history replacement events, deduplicated by response and window; failure count covers recorded compaction error events only.'}
