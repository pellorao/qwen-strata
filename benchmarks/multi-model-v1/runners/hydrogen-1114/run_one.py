"""One Hydrogen instance of a v1 frozen scenario (plan.md §3): ARW zero-model prepare -> stage the scenario root(s) as
claude_scenario does -> one `agy -p` turn per handoff -> checks -> instance.json.

    python3 -I run_one.py <scenario-key: ca|cs|cstd|sr> <effort> <attempt> [--T seconds]

Instance directory: .tmp/hydrobench/<scenario-key>/hydrogen-<effort>-a<attempt> (bench_records DIR_NAME shape).
Work copies live in /tmp/hydrobench/work/<name>-h<k> (the only paths the model sees; no home directory in them).
"""
import argparse
import hashlib
import json
import re
import shutil
import sys
import time
from pathlib import Path

ROOT = Path('/home/pello/projects/qwen-strata')
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))
import agyrun  # noqa: E402
from tools.reviewer import claude_scenario as cs  # noqa: E402
from tools.reviewer.claude_headless import file_hashes  # noqa: E402
from tools.tuning.arw_dimension import load_plan, prepare  # noqa: E402

PLANS = HERE / 'plans'  # scenario plans with the Codex binding of 0.164.0 (plan.md §3); rest verbatim
OUT = ROOT / '.tmp/hydrobench'
WORK = Path('/tmp/hydrobench/work')
SCENARIOS = {'ca': ('commit-audit-v3', 1), 'cs': ('code-spec-v5', 1), 'cstd': ('code-standards-v5.1', 1),
             'sr': ('spec-readiness-v4.3', 2)}
HARD_LIMIT = 3600  # SR, CA: ARW original (reminder 55 min, interrupt 60 min; agy has the hard stop only)
SCAN = re.compile(r'pello|/home/|/Users/|[\w.+-]+@[\w-]+\.(?!example\b)[\w.]+|sk-[A-Za-z0-9]{16,}|Bearer\s+[A-Za-z0-9._-]{16,}|'
                  r'eyJ[A-Za-z0-9_-]{20,}\.|BEGIN [A-Z ]*PRIVATE KEY|private\.toml|\.credentials', re.I)
SKIP_SCAN = {'.git'}


def privacy_scan(root, prompt):
    hits = [f'prompt: {m.group(0)}' for m in SCAN.finditer(prompt)]
    for p in sorted(Path(root).rglob('*')):
        if p.is_file() and not p.is_symlink() and SKIP_SCAN.isdisjoint(p.relative_to(root).parts):
            text = p.read_bytes().decode('utf-8', 'replace')
            hits += [f'{p.relative_to(root)}: {m.group(0)}' for m in SCAN.finditer(text)][:3]
    return hits


def rewrite_active(work, handoff, staging):
    """SR's `spec-readiness/active-request.json` (harness state) names the host checkout path, which cs.stage leaves (the
    Claude arm read it unchanged); point it at the work copy like the request files, so no home path is sent."""
    for active in work.glob('.tmp/codex/*/*/spec-readiness/active-request.json'):
        text = active.read_text()
        if handoff['scenarioRoot'] in text:
            active.write_text(text.replace(handoff['scenarioRoot'], str(work)))
            staging.setdefault('rewritten_active_requests', []).append(str(active.relative_to(work)))


def run(key, effort, attempt, T=None):
    scenario, n_handoffs = SCENARIOS[key]
    name = f'hydrogen-{effort}-a{attempt}'
    out = OUT / key / name
    model = f'gemini-4-hydrogen-{effort}'
    plan_path = PLANS / f'{scenario}.json'
    plan = load_plan(plan_path)[0]
    if key in ('cs', 'cstd') and T is None:
        raise SystemExit('cs / cstd need --T (from the P4 probe)')
    out.mkdir(parents=True, exist_ok=False)
    prep = out / 'prep'
    prepare(plan, None, prep, time_limit_seconds=T if key in ('cs', 'cstd') else None)
    prepared = json.loads((prep / 'preparation.json').read_text())
    note = json.loads((prep / 'selection-source.json').read_text())['measurement_note']
    limit = T if key in ('cs', 'cstd') else HARD_LIMIT
    records = []
    for k, handoff in enumerate(prepared['handoffs'][:n_handoffs]):
        run_id = f'{name}-{key}-h{k}'
        work = WORK / run_id
        if work.exists():
            shutil.rmtree(work)
        work.parent.mkdir(parents=True, exist_ok=True)
        prompt, staging = cs.stage(handoff, cs.prompt_text(handoff, note, False), str(work), work)
        staging.pop('system', None)
        rewrite_active(work, handoff, staging)
        hits = privacy_scan(work, prompt)
        record = {'k': k, 'instanceId': handoff['instanceId'], 'run_id': run_id, 'staging': staging,
                  'prompt_sha256': hashlib.sha256(prompt.encode()).hexdigest(), 'measurement_note': note,
                  'role_as_system': False, 'privacy_hits': hits, 'hard_limit_seconds': limit}
        if hits:
            records.append(record)
            break  # nothing is sent
        h = out / f'h{k}'
        h.mkdir()
        before = file_hashes(work)
        (h / 'files-before.json').write_text(json.dumps(before, indent=1))
        result, cont = agyrun.execute(h, work, prompt, staging['report'], model, effort, limit)
        after = file_hashes(work)
        (h / 'files-after.json').write_text(json.dumps(after, indent=1))
        changed = sorted(f for f in set(before) | set(after) if before.get(f) != after.get(f))
        report_dir = str(Path(staging['report']).parent)
        report = work / staging['report']
        produced = report.exists() and report.stat().st_size > 0
        if produced:
            dest = h / 'outputs' / staging['report']
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(report, dest)
            target = Path(handoff['input']['reportPath'])
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(report, target)
        (h / 'result.json').write_text(json.dumps({'continuation': cont, **{k2: v for k2, v in result.items() if k2 != 'response_text'}}, indent=1))
        record.update(report_exists=produced, report_sha256=hashlib.sha256(report.read_bytes()).hexdigest() if produced else None,
                      wall_seconds=result['wall_seconds'], started_at=result['started_at'],
                      continuation=cont, checks=checks(result, cont, model, effort, changed, report_dir), tokens=result['usage_sum'],
                      tool_calls=len(result['tools']), api_seconds=sum(r['seconds'] or 0 for r in result['responses']),
                      final_response=(result['response_text'] or '')[:400])
        records.append(record)
        shutil.rmtree(work, ignore_errors=True)
        (out / 'instance.json').write_text(json.dumps({'plan': str(plan_path), 'model': model, 'effort': effort, 'scenario': scenario,
                                                       'attempt': attempt, 'T': T, 'handoffs': records}, indent=1))
    (out / 'instance.json').write_text(json.dumps({'plan': str(plan_path), 'model': model, 'effort': effort, 'scenario': scenario,
                                                   'attempt': attempt, 'T': T, 'handoffs': records}, indent=1))
    # scoring needs prep/arw/.tmp (upstream_score puts the kept answer data back); the rest of the ARW checkout goes
    arw = prep / 'arw'
    for child in list(arw.iterdir()) if arw.is_dir() else []:
        if child.name != '.tmp':
            shutil.rmtree(child) if child.is_dir() and not child.is_symlink() else child.unlink()
    return records


def checks(result, cont, model, effort, changed, report_dir):
    """Per-instance validity (plan.md §3). Valid: model echoed as asked, no forbidden tool, no denied action, every
    segment ended normally or by the hard stop / reminder, and the run either delivered or was stopped by the hard limit."""
    status, error = result['status'], result['error'] or ''
    quota = bool(re.search(r'429|RESOURCE_EXHAUSTED|quota|rate.?limit', json.dumps(error), re.I))
    stop = cont['stop']
    hard_stop = stop in ('hard_limit', 'deadline_between_segments')
    out = {'model_echo': result['model_echo'], 'model_match': result['model_echo'] == model, 'status': status,
           'error': error or None, 'stop': stop, 'hard_stop': hard_stop, 'quota_hit': quota,
           'forbidden_tools': result['forbidden_tools'], 'denied_actions': result['denied_actions'] or None,
           'driver_kill': result['killed_by_driver'], 'result_event': result['result_event'],
           'unexpected_changes': [f for f in changed if not f.startswith(report_dir + '/') and not cs.HARNESS_STUBS.fullmatch(f)]}
    out['ended_normally'] = stop in ('delivered', 'hard_limit', 'deadline_between_segments') and not result['killed_by_driver']
    out['valid'] = (out['model_match'] and not out['forbidden_tools'] and not out['denied_actions'] and out['ended_normally']
                    and not quota)
    return out


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('key', choices=SCENARIOS)
    ap.add_argument('effort', choices=('medium', 'high', 'xhigh'))
    ap.add_argument('attempt', type=int)
    ap.add_argument('--T', type=int)
    a = ap.parse_args()
    recs = run(a.key, a.effort, a.attempt, a.T)
    print(json.dumps([{'k': r['k'], 'valid': (r.get('checks') or {}).get('valid'), 'wall': r.get('wall_seconds'),
                       'privacy_hits': r['privacy_hits']} for r in recs]))
