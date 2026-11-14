"""Normalized instance records (bench_records shape) of the Carbon supplement, for bench_score and the export.

    python3 -I carbon_records.py [--out records.jsonl]     every instance directory under .tmp/carbonbench/<ca|cs|cstd|sr>/

One record per instance directory, the fields bench_score reads (the claude_record shape): handoffs with report path,
sha, sub-scenario, `files_before`; validity from the instance checks (drive.classify's rule); pauses from the recorded continuation (execute in agyrun, plan §3); `validity_before_rejudge` present so bench_score accepts it. Ranking: every
valid instance of a Carbon cell is in the main statistic (phase-4 supplement, like phase 3).
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path('/home/pello/projects/qwen-strata')
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))
import drive  # noqa: E402
from tools.reviewer import bench_records as br  # noqa: E402
from tools.reviewer.claude_headless import final_status  # noqa: E402

OUT = ROOT / '.tmp/carbonbench'
SCEN = {'ca': 'commit-audit-v3', 'cs': 'code-spec-v5', 'cstd': 'code-standards-v5.1', 'sr': 'spec-readiness-v4.3'}
EFFORTS = ('low', 'medium', 'high')
FIRST_CONFIG = 33  # Hydrogen is 30-32
# Report-style family for synthetic controls: 'anthropic', the value of Hydrogen's records (bench_records.antigravity_record; same Gemini family, shared anchors).
STYLE_FAMILY = 'anthropic'


def record(key, folder):
    inst = json.loads((folder / 'instance.json').read_text())
    effort, attempt = inst['effort'], inst['attempt']
    verdict, reasons = drive.classify(folder)
    rec = {'id': f'antigravity/{SCEN[key]}/{folder.name}', 'arm': 'antigravity', 'harness': 'antigravity',
           'model_family': 'carbon', 'style_family': STYLE_FAMILY, 'effort': effort, 'requested_effort': effort,
           'effective_effort': effort, 'pooled': False, 'supplementary': False, 'supplementary_label': None,
           'config': FIRST_CONFIG + EFFORTS.index(effort), 'config_label': f'carbon-{effort}', 'scenario': SCEN[key],
           'plan': inst['plan'], 'plan_sha256_now': br.sha256_file(inst['plan']), 'attempt': attempt, 'dir': str(folder)}
    plan = json.loads(Path(inst['plan']).read_text())
    prep = br.load(folder / 'prep/preparation.json') or {}
    rec['identity'] = {'plan_codex_thread_id': plan['codex_thread_id'], 'prep_session_id': (prep.get('identity') or {}).get('sessionId')}
    originals = sorted(folder.glob(br.PREPARED))
    rec['original_prepared'] = str(originals[0]) if len(originals) == 1 else None
    handoffs = []
    for h in inst['handoffs']:
        k = h['k']
        staged = (h.get('staging') or {}).get('report')
        out = folder / f'h{k}'
        path, ok = br.report_location(h.get('report_sha256'), out / 'outputs' / staged if staged else None)
        result = br.load(out / 'result.json') or {}
        c = h.get('checks') or {}
        status = final_status(h.get('final_response')) or 'not-arw-form' if c.get('result_event') and c.get('status') == 'SUCCESS' else None
        handoffs.append({'k': k, 'instanceId': h['instanceId'], 'sub_scenario': br.sub_scenario(h['instanceId']), 'report': path,
                         'report_ok': ok, 'report_exists': h.get('report_exists'), 'report_sha256': h.get('report_sha256'),
                         'seconds': h.get('wall_seconds'),
                         'tokens': {'uncached_input': (h.get('tokens') or {}).get('input_tokens'),
                                    'cached_input': (h.get('tokens') or {}).get('cache_read_tokens'),
                                    'output': (h.get('tokens') or {}).get('output_tokens')},
                         'thinking_tokens': (h.get('tokens') or {}).get('thinking_tokens'), 'tokens_lower_bound': False,
                         'api_usage': result.get('usage_sum'), 'cost_usd': None, 'tool_calls': h.get('tool_calls'),
                         'api_seconds': h.get('api_seconds'), 'session': (h.get('continuation') or {}).get('conversation_id'),
                         'pause_events': (h.get('continuation') or {}).get('arw_pause_events', []),
                         'sandbox_failures': 0, 'continuation_stop': (h.get('continuation') or {}).get('stop'), 'models_returned': [c['model_echo']] if c.get('model_echo') else [],
                         'service_tiers': {}, 'files_before': str(out / 'files-before.json'), 'spill_files': [],
                         'compactions': None, 'compactions_source': 'not available in the agy stream',
                         'final_status': status, 'final_status_source': 'agy result response text',
                         'hard_stop': c.get('hard_stop'), 'unexpected_changes': c.get('unexpected_changes')})
    rec.update(br.validity(verdict, reasons, 'run_one checks (drive.classify)'))
    rec['validity_before_rejudge'] = {'valid': rec['valid'], 'status': verdict, 'source': 'run_one checks', 'reasons': reasons}
    rec['seconds_adjustment'] = None
    rec['started'] = min((h.get('started_at') for h in inst['handoffs'] if h.get('started_at')), default=None)
    rec['time_limit_seconds'], rec['time_limit_source'] = br.time_limit(folder, inst.get('T'))
    rec['harness_generation'] = None
    events = [e for h in inst['handoffs'] for e in (h.get('continuation') or {}).get('arw_pause_events', [])]
    rec.update(br.pause_fields(events, 0, None))
    rec['handoffs'] = handoffs
    rec['repository_manifest'] = {'kind': 'h<k>/files-before.json'}
    rec.update(br.SCORE_FIELDS)
    seconds = [h['seconds'] for h in handoffs]
    rec.update({'instance': attempt, 'seconds': sum(seconds) if None not in seconds else None})
    br.final_status_error(rec)
    return rec


def all_records():
    out = []
    for key in SCEN:
        for folder in sorted((OUT / key).glob('carbon-*-a*')) if (OUT / key).is_dir() else []:
            if (folder / 'instance.json').is_file():
                out.append(record(key, folder))
    # phase-4 supplement: every valid instance is in the main statistic, ranked by start time within its cell
    cells = {}
    for r in out:
        r['valid_rank'] = r['main_statistic'] = r['first_n'] = None
        if r['valid']:
            cells.setdefault((r['scenario'], r['config']), []).append(r)
    for group in cells.values():
        group.sort(key=lambda r: (r['started'] is None, r['started'] or 0, r['attempt']))
        for i, r in enumerate(group, 1):
            r.update(valid_rank=i, first_n=i <= 5, main_statistic=True, cell=f"antigravity/{r['scenario']}/{r['config']}", cell_pooled=False)
    return out


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', type=Path, default=OUT / 'records.jsonl')
    a = ap.parse_args()
    rows = all_records()
    a.out.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows))
    print(len(rows), 'records ->', a.out)
