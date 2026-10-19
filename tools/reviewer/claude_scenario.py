"""One ARW reviewer scenario instance on Claude Code headless (multi-model benchmark, Claude Code arms).

ARW's own zero-model preparation (tools.tuning.arw_dimension.prepare, the frozen manifest and measurement note of the
scenario plan) gives the handoffs; each of the first `--handoffs` handoffs (Spec Readiness: 2, RM then AP, each a fresh
session as ARW's one-root-thread-per-instance rule) runs once through tools.reviewer.claude_headless.run:
- the prompt is the bound Role instructions, the handoff and the measurement note, as the 2026-10-18 reference runs;
- the working directory is a copy of the scenario root (ARW's handoff `cwd`), outside /home; the scenario root path and
  the request files' absolute draft path are rewritten to the copy, Spec Readiness' host-relative draft path to the
  root-relative one;
- only the report's directory is writable; the report is copied back to the prepared `reportPath` for scoring.
Each handoff's record gets `checks`: the returned model IDs against the bound ID (plan §2 match rule), service tiers
(S5), server web requests, startup prompt off, completion.

    python3 -m tools.reviewer.claude_scenario --plan <plan.json> --out .tmp/<work>/<run> --model claude-opus-5-5 \\
        --effort high --label <label> --claude <binary> --no-startup-prompt --no-compact-prompt [--handoffs 2]
        [--time-limit-seconds T] [--limit S] [--dry-run]
"""
import argparse
import hashlib
import json
import re
import shutil
import time
from pathlib import Path

from tools.reviewer import claude_headless as ch
from tools.reviewer.wsl_client import ROOT, save

TIERS_OK = {'default', 'standard', 'not-returned'}


def prompt_text(handoff, note):
    """Role instructions, handoff, then the frozen measurement note (appended only)."""
    raw = (ROOT / note['path']).read_bytes()
    if hashlib.sha256(raw).hexdigest() != note['sha256']:
        raise ValueError('Measurement note differs from its binding')
    body = handoff['input']['handoff'].rstrip('\n') + '\n\n' + raw.decode().strip()
    return ('# Bound Role instructions (system-level for this task)\n\n' + handoff['input']['instructions'].strip()
            + '\n\n# Handoff (the task)\n\n' + body + '\n')


def host_relative(report, root):
    """The draft path relative to the ARW checkout (the host workspace), as Spec Readiness handoffs also name it."""
    parts = Path(root).parts
    return str(Path(report).relative_to(Path(*parts[:parts.index('arw') + 1])))


def stage(handoff, prompt, work, stage_dir):
    """A copy of the scenario root with the absolute paths pointed at the working directory; the rewritten prompt."""
    root, report = handoff['scenarioRoot'], handoff['input']['reportPath']
    shutil.copytree(root, stage_dir, symlinks=True)
    rewritten = []
    for request in [*stage_dir.glob('.tmp/codex/*/*/spec-readiness/requests/request-*.json'),
                    *stage_dir.glob('.tmp/codex/*/_commit-audit-capability/request.json')]:
        text = request.read_text()
        if root in text:
            request.write_text(text.replace(root, str(work)))
            rewritten.append(str(request.relative_to(stage_dir)))
    if prompt.count(root) < 1:
        raise ValueError('The prompt does not name the scenario root')
    relative = str(Path(report).relative_to(root))
    host = host_relative(report, root)
    hosts = prompt.count(host)
    prompt = prompt.replace(host, relative).replace(root, str(work))
    if root in prompt or re.search(r'/home/pello', prompt):
        raise ValueError('The prompt still names a path under /home')
    return prompt, {'rewritten_requests': rewritten, 'host_relative_replaced': hosts, 'report': relative}


def checks(result, model, startup):
    """Per-run validity: plan §2 model match (exact or a date suffix), §3 tiers, search and startup prompt."""
    summary = result.get('summary') or {}
    returned = sorted({*(summary.get('modelUsage') or {}), *([summary['init']['model']] if summary.get('init') else [])})
    pattern = re.compile(re.escape(model) + r'(-\d{4}-\d{2}-\d{2}|-\d{8})?')
    tiers = summary.get('service_tiers') or {}
    out = {'models_returned': returned, 'model_match': bool(returned) and all(pattern.fullmatch(m) for m in returned),
           'service_tiers': tiers, 'tier_ok': set(tiers) <= TIERS_OK,
           'server_web_requests': summary.get('server_web_requests'),
           'completed': result.get('exit') == 0 and not result.get('hard_interrupt') and summary.get('result_event') is True
           and not summary.get('is_error'),
           'startup_prompt_off': not startup}
    out['valid'] = (out['model_match'] and out['tier_ok'] and out['server_web_requests'] == 0 and out['startup_prompt_off'])
    return out


def run(plan_path, out, model, effort, label, claude, handoffs=1, limit=ch.HARD_LIMIT, time_limit=None,
        startup=False, compact=False, dry_run=False, backend='anthropic'):
    from tools.tuning.arw_dimension import load_plan, prepare
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    plan = load_plan(Path(plan_path))[0]
    prep = out / 'prep'
    prepare(plan, None, prep, time_limit_seconds=time_limit)
    prepared = json.loads((prep / 'preparation.json').read_text())
    note = json.loads((prep / 'selection-source.json').read_text())['measurement_note']
    records = []
    for k, handoff in enumerate(prepared['handoffs'][:handoffs]):
        run_id = f'{out.name}-h{k}-{time.time_ns()}'
        work = ch.WORK_BASE / run_id / 'work'
        stage_dir = out / f'stage-h{k}'
        prompt, staging = stage(handoff, prompt_text(handoff, note), str(work), stage_dir)
        (out / f'prompt-h{k}.md').write_text(prompt)
        report_dir = str(Path(staging['report']).parent)
        copies = [(p, p.name) for p in sorted(stage_dir.iterdir())]
        record = {'k': k, 'instanceId': handoff['instanceId'], 'run_id': run_id, 'staging': staging,
                  'prompt_sha256': hashlib.sha256(prompt.encode()).hexdigest(), 'measurement_note': note}
        if dry_run:
            records.append(record)
            continue
        result = ch.run(out / f'h{k}', out / f'prompt-h{k}.md', backend, model, effort, f'{label} h{k}', copies,
                        [report_dir], limit, startup=startup, run_id=run_id, claude=claude, compact=compact)
        produced = out / f'h{k}' / 'outputs' / report_dir / Path(staging['report']).name
        if produced.exists():
            target = Path(handoff['input']['reportPath'])
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(produced, target)
        record.update(report_exists=produced.exists(),
                      report_sha256=hashlib.sha256(produced.read_bytes()).hexdigest() if produced.exists() else None,
                      wall_seconds=result.get('wall_seconds'), checks=checks(result, model, startup))
        records.append(record)
        save(out / 'instance.json', {'plan': str(plan_path), 'model': model, 'effort': effort, 'label': label,
                                     'handoffs': records})
    save(out / 'instance.json', {'plan': str(plan_path), 'model': model, 'effort': effort, 'label': label,
                                 'handoffs': records, 'dry_run': dry_run})
    return records


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--plan', type=Path, required=True, help='Scenario plan (arw-dimension-v1) naming the frozen manifest and note.')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--model', required=True, help='Concrete model ID (plan §2: aliases resolved before the run).')
    parser.add_argument('--effort', choices=('low', 'medium', 'high'), required=True)
    parser.add_argument('--label', required=True)
    parser.add_argument('--claude', required=True, help=f'The benchmark Claude Code binary ({ch.CLAUDE_VERSION}).')
    parser.add_argument('--handoffs', type=int, default=1)
    parser.add_argument('--limit', type=int, default=ch.HARD_LIMIT, help='Hard limit per handoff in seconds (ARW 3600).')
    parser.add_argument('--time-limit-seconds', type=int, help='Review time limit rendered into a time-limited note.')
    parser.add_argument('--no-startup-prompt', action='store_true')
    parser.add_argument('--no-compact-prompt', action='store_true')
    parser.add_argument('--dry-run', action='store_true', help='Prepare and stage only; no model run.')
    args = parser.parse_args()
    ch.pinned_binary(args.claude)
    print(json.dumps(run(args.plan, args.out, args.model, args.effort, args.label, args.claude, args.handoffs, args.limit,
                         args.time_limit_seconds, not args.no_startup_prompt, not args.no_compact_prompt, args.dry_run),
                     ensure_ascii=False))
