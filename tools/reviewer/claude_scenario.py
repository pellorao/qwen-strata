"""One ARW reviewer scenario instance on Claude Code headless (multi-model benchmark, Claude Code arms).

ARW's own zero-model preparation (tools.tuning.arw_dimension.prepare, the frozen manifest and measurement note of the
scenario plan) gives the handoffs; each of the first `--handoffs` handoffs (Spec Readiness: 2, RM then AP, each a fresh
session as ARW's one-root-thread-per-instance rule) runs once through tools.reviewer.claude_headless.run:
- the prompt is the bound Role instructions, the handoff and the measurement note, as the 2026-10-18 reference runs;
  with `--role-as-system` (new plans; user 2026-10-20: Claude Code has no developer role, the system prompt is the
  matching place, as Codex's developer instructions) the Role instructions go through `--append-system-prompt`
  instead and the user message holds the handoff and the measurement note only. The scenario plan's
  fixed_conditions.claude_role_as_system decides it (multi-model v2: true, plan §5.4); plans without it (v1) keep the
  old shape unless the flag is given, and a flag that contradicts the plan is refused;
- the working directory is a copy of the scenario root (ARW's handoff `cwd`), outside /home; the scenario root path and
  the request files' absolute draft path are rewritten to the copy, Spec Readiness' host-relative draft path to the
  root-relative one;
- only the report's directory is writable; the report is copied back to the prepared `reportPath` for scoring.
Each handoff runs with ARW's early-exit continuation (claude_headless.execute_continued, user 2026-10-20): its record
gets `continuation` and instance.json the Codex path's `arw_pause_events`, `continue_count` (plus `early_exit_count`).
Each handoff's record gets `checks`: the returned model IDs against the bound ID (plan §2 match rule; a safeguards
refusal fallback to another model fails it), service tiers (S5), server web requests, startup prompt off, and a normal
end (a stop at the hard limit stays valid; an API or transport error does not; the turn a delivered reminder or
interrupt cut short is ours, not an error: `reminder_interrupts`). With `--time-limit-seconds T` the
hard stop is T and the reminder comes at ARW's lead before it.
`--backend strata --host <id>` runs the served model through claude_headless's Strata arm (lease, cold start with the
installation defaults, engine-log tokens; the startup prompt by the service, the compact prompt by PreCompact): its
checks replace "startup prompt off" with the two prompt SHA-256 the run actually loaded (plan §14) and the thinking
budget and output limit the native service applied to every request (plan §2.1).
`--backend deepseek` takes the window, compaction point and output limit from the plan's
fixed_conditions.deepseek_claude_environment when it has one (multi-model v2 §5.2); a value still null there (not yet
measured at freeze) refuses the run.

    python3 -m tools.reviewer.claude_scenario --plan <plan.json> --out .tmp/<work>/<run> --model claude-opus-5-5 \\
        --effort high --label <label> --claude <binary> --no-startup-prompt --no-compact-prompt [--handoffs 2]
        [--time-limit-seconds T] [--limit S] [--dry-run] [--backend strata --host <id> | --backend deepseek]
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
# Empty stubs Claude Code itself creates in the working directory with CLAUDE_CODE_SUBPROCESS_ENV_SCRUB (listed in
# .git/info/exclude by the harness, which also adds .git/commondir and .git/config.worktree); recorded, not the model's.
HARNESS_STUBS = re.compile(r'(\.env(\.[a-z]+)*|\.gitmodules|\.npmrc|\.yarnrc(\.yml)?|bunfig\.toml|package(-lock)?\.json|'
                           r'pnpm-lock\.yaml|yarn\.lock|\.git/(commondir|config\.worktree|info/exclude))')


def prompt_text(handoff, note, role_as_system=False):
    """Role instructions, handoff, then the frozen measurement note (appended only). With `role_as_system` the prompt
    is the handoff and the note only, the Role instructions being `role_text`."""
    raw = (ROOT / note['path']).read_bytes()
    if hashlib.sha256(raw).hexdigest() != note['sha256']:
        raise ValueError('Measurement note differs from its binding')
    body = handoff['input']['handoff'].rstrip('\n') + '\n\n' + raw.decode().strip()
    if role_as_system:
        return body + '\n'
    return ('# Bound Role instructions (system-level for this task)\n\n' + handoff['input']['instructions'].strip()
            + '\n\n# Handoff (the task)\n\n' + body + '\n')


def role_text(handoff):
    """The bound Role instructions as the system-prompt text (`--role-as-system`)."""
    return '# Bound Role instructions\n\n' + handoff['input']['instructions'].strip()


def host_relative(report, root):
    """The draft path relative to the ARW checkout (the host workspace), as Spec Readiness handoffs also name it."""
    parts = Path(root).parts
    return str(Path(report).relative_to(Path(*parts[:parts.index('arw') + 1])))


def stage(handoff, prompt, work, stage_dir, system=None):
    """A copy of the scenario root with the absolute paths pointed at the working directory; the rewritten prompt.
    A `system` text (the Role instructions) is rewritten the same way and returned as the info's `system`."""
    root, report = handoff['scenarioRoot'], handoff['input']['reportPath']
    shutil.copytree(root, stage_dir, symlinks=True)
    rewritten = []
    for request in [*stage_dir.glob('.tmp/codex/*/*/spec-readiness/requests/request-*.json'),
                    *stage_dir.glob('.tmp/codex/*/_commit-audit-capability/request.json')]:
        text = request.read_text()
        if root in text:
            request.write_text(text.replace(root, str(work)))
            rewritten.append(str(request.relative_to(stage_dir)))
    if (prompt + (system or '')).count(root) < 1:
        raise ValueError('The prompt does not name the scenario root')
    relative = str(Path(report).relative_to(root))
    host = host_relative(report, root)
    def rewrite(text):
        text = text.replace(root, str(work))  # absolute paths first: the host-relative path is a suffix of them
        count = text.count(host)
        text = text.replace(host, relative)
        if root in text or re.search(r'/home/pello', text):
            raise ValueError('The prompt still names a path under /home')
        return text, count
    prompt, hosts = rewrite(prompt)
    info = {'rewritten_requests': rewritten, 'host_relative_replaced': hosts, 'report': relative}
    if system is not None:
        info['system'], more = rewrite(system)
        info['host_relative_replaced'] += more
    return prompt, info


def strata_expected(effort):
    """Strata arm: the prompt SHA-256 the service and the PreCompact hook must load, and §2.1's effort limits."""
    from frontend import EFFORT_BUDGETS  # src/ is on the path (claude_headless)
    budget, total = EFFORT_BUDGETS[effort]
    return {'startup_sha256': ch.startup_text()[1], 'compact_sha256': hashlib.sha256(ch.COMPACT.read_bytes()).hexdigest(),
            'thinking_budget': min(budget, total // 2), 'max_tokens': total}


def checks(result, model, startup, report_dir=None, strata=None, binding=None):
    """Per-run validity: plan §2 model match (exact or a date suffix), §3 tiers, search and startup prompt.
    `strata` (strata_expected) checks the Strata arm's loaded prompts (from the run's `binding`) and output limits."""
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
    # A run stopped at the hard limit or by a model-side error (F4: its context or output over the limits, as ARW's
    # incomplete on Codex) stays valid, scored on what it wrote; any other abnormal end (API or transport error,
    # non-zero exit) is invalid and rerun.
    # Files changed outside the report directory other than the harness stubs: recorded for the session check (the
    # sandbox lets commands create new files in the report's ancestor directories, never change existing ones).
    out['unexpected_changes'] = [f for f in result.get('changed_files') or []
                                 if not (report_dir and f.startswith(report_dir + '/')) and not HARNESS_STUBS.fullmatch(f)]
    out['error_kind'] = summary.get('error_kind')
    # A turn our reminder or hard-stop interrupt cut short is never an API fault (user 2026-10-20 / 2026-10-23, rulings
    # 「提醒和中断打断生成」): stream_summary already leaves it out of is_error and error_kind; listed for the record.
    out['reminder_interrupts'] = len(summary.get('reminder_interrupts') or [])
    # A run left undelivered without a session id to resume is a harness fault (no continuation possible): invalid.
    out['continuation_stop'] = (result.get('continuation') or {}).get('stop')
    out['ended_normally'] = (out['continuation_stop'] != 'no_session'
                             and (out['completed'] or bool(result.get('hard_interrupt'))
                                  or (summary.get('result_event') is True and summary.get('error_kind') == 'model')))
    # Harness fault: a Bash call whose sandbox could not be built never ran (bwrap argument limit, 2026-10-20).
    out['sandbox_failures'] = summary.get('sandbox_failures') or 0
    prompts_ok = out['startup_prompt_off']
    if strata:
        loaded = {'startup_sha256': ((binding or {}).get('startup_instructions') or {}).get('sha256'),
                  'compact_sha256': (binding or {}).get('compact_prompt_sha256')}
        limits = result.get('output_limits') or {}
        del out['startup_prompt_off']
        out.update(prompts=loaded, prompts_ok=all(loaded[k] == strata[k] for k in loaded), output_limits=limits,
                   output_limits_ok=limits.get('max_tokens') == [strata['max_tokens']]
                   and limits.get('thinking_budgets') in ([], [strata['thinking_budget']]))
        prompts_ok = out['prompts_ok'] and out['output_limits_ok']
    out['valid'] = (out['model_match'] and out['tier_ok'] and out['server_web_requests'] == 0 and prompts_ok
                    and out['ended_normally'] and out['sandbox_failures'] == 0)
    return out


def run(plan_path, out, model, effort, label, claude, handoffs=1, limit=ch.HARD_LIMIT, time_limit=None,
        startup=False, compact=False, dry_run=False, backend='anthropic', host=None, role_as_system=None):
    from tools.tuning.arw_dimension import load_plan, prepare
    if time_limit is not None:
        limit = time_limit  # the note's limit is the hard stop; the reminder follows ARW's lead (reminder_time)
    plan = load_plan(Path(plan_path))[0]
    role_as_system = plan_role_as_system(plan, role_as_system)
    limits = plan_deepseek_limits(plan, backend)
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    prep = out / 'prep'
    prepare(plan, None, prep, time_limit_seconds=time_limit)
    prepared = json.loads((prep / 'preparation.json').read_text())
    note = json.loads((prep / 'selection-source.json').read_text())['measurement_note']
    records = []
    for k, handoff in enumerate(prepared['handoffs'][:handoffs]):
        run_id = f'{out.name}-h{k}-{time.time_ns()}'
        work = ch.WORK_BASE / run_id / 'work'
        stage_dir = out / f'stage-h{k}'
        prompt, staging = stage(handoff, prompt_text(handoff, note, role_as_system), str(work), stage_dir,
                                role_text(handoff) if role_as_system else None)
        system = staging.pop('system', None)
        (out / f'prompt-h{k}.md').write_text(prompt)
        if system is not None:
            (out / f'system-h{k}.md').write_text(system)
        report_dir = str(Path(staging['report']).parent)
        copies = [(p, p.name) for p in sorted(stage_dir.iterdir())]
        record = {'k': k, 'instanceId': handoff['instanceId'], 'run_id': run_id, 'staging': staging,
                  'prompt_sha256': hashlib.sha256(prompt.encode()).hexdigest(), 'measurement_note': note,
                  'role_as_system': role_as_system,
                  'system_sha256': hashlib.sha256(system.encode()).hexdigest() if system else None}
        if dry_run:
            records.append(record)
            continue
        result = ch.run(out / f'h{k}', out / f'prompt-h{k}.md', backend, model, effort, f'{label} h{k}', copies,
                        [report_dir], limit, startup=startup, run_id=run_id, claude=claude, compact=compact, host=host,
                        report=staging['report'], system_prompt=system, deepseek_limits=limits)
        produced = out / f'h{k}' / 'outputs' / report_dir / Path(staging['report']).name
        if produced.exists():
            target = Path(handoff['input']['reportPath'])
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(produced, target)
        record.update(report_exists=produced.exists(),
                      report_sha256=hashlib.sha256(produced.read_bytes()).hexdigest() if produced.exists() else None,
                      wall_seconds=result.get('wall_seconds'), continuation=continuation_record(result))
        if backend == 'strata':
            binding = json.loads((out / f'h{k}' / 'binding.json').read_text())
            record.update(checks=checks(result, model, startup, report_dir, strata_expected(effort), binding),
                          engine_tokens=result.get('engine_tokens'), strata_release=binding.get('strata_release'),
                          load_seconds=binding.get('load_seconds'), model_environment=binding.get('model_environment'))
        else:
            record['checks'] = checks(result, model, startup, report_dir)
        records.append(record)
        save(out / 'instance.json', {'plan': str(plan_path), 'model': model, 'effort': effort, 'label': label,
                                     'handoffs': records, **pause_summary(records)})
    save(out / 'instance.json', {'plan': str(plan_path), 'model': model, 'effort': effort, 'label': label,
                                 'handoffs': records, 'dry_run': dry_run, **pause_summary(records)})
    return records


def plan_role_as_system(plan, requested=None):
    """Role placement: the plan's claude_role_as_system when it has one (a contradicting request is refused), else the
    request (default False, the v1 shape)."""
    fixed = plan['fixed_conditions']
    if 'claude_role_as_system' not in fixed:
        return bool(requested)
    if requested is not None and requested != fixed['claude_role_as_system']:
        raise ValueError(f"the plan fixes claude_role_as_system {fixed['claude_role_as_system']}")
    return fixed['claude_role_as_system']


def plan_deepseek_limits(plan, backend):
    """The DeepSeek arm's Claude Code limits the plan fixes (None without them); a null value refuses the run."""
    limits = plan['fixed_conditions'].get('deepseek_claude_environment')
    if backend != 'deepseek' or limits is None:
        return None
    unset = sorted(name for name, value in limits.items() if value is None)
    if unset:
        raise ValueError(f'deepseek_claude_environment is not frozen yet: {unset} still null')
    return limits


def continuation_record(result):
    """The handoff's early-exit continuation as ARW would have run it (claude_headless.execute_continued)."""
    c = result.get('continuation') or {}
    return {'stop': c.get('stop'), 'delivered': c.get('delivered'), 'early_exit_count': c.get('early_exit_count'),
            'continue_count': c.get('continue_count'), 'arw_pause_events': c.get('arw_pause_events') or [],
            'segments': len(c.get('segments') or []), 'session_id': c.get('session_id')}


def pause_summary(records):
    """Instance-level fields as the Codex path's instance.json: every pause of every handoff is one violation entry;
    scoring multiplies the instance by 0.9 once when any exists (user 2026-10-20)."""
    events = [dict(e, handoff=r['k']) for r in records for e in (r.get('continuation') or {}).get('arw_pause_events') or []]
    return {'arw_pause_events': events,
            'continue_count': sum((r.get('continuation') or {}).get('continue_count') or 0 for r in records),
            'early_exit_count': sum((r.get('continuation') or {}).get('early_exit_count') or 0 for r in records)}


def arguments(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--plan', type=Path, required=True, help='Scenario plan (arw-dimension-v1) naming the frozen manifest and note.')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--model', required=True, help='Concrete model ID (plan §2: aliases resolved before the run).')
    parser.add_argument('--effort', choices=('low', 'medium', 'high'), required=True)
    parser.add_argument('--label', required=True)
    parser.add_argument('--claude', default=ch.CLAUDE,
                        help=f'The pinned Claude Code benchmark copy ({ch.CLAUDE_VERSION}; tools.reviewer.harness_pins).')
    parser.add_argument('--handoffs', type=int, default=1)
    parser.add_argument('--limit', type=int, default=ch.HARD_LIMIT, help='Hard limit per handoff in seconds (ARW 3600).')
    parser.add_argument('--time-limit-seconds', type=int,
                        help='Review time limit rendered into a time-limited note; also the hard stop (overrides --limit).')
    parser.add_argument('--no-startup-prompt', action='store_true')
    parser.add_argument('--no-compact-prompt', action='store_true')
    parser.add_argument('--dry-run', action='store_true', help='Prepare and stage only; no model run.')
    parser.add_argument('--backend', choices=ch.BACKENDS, default='anthropic',
                        help='deepseek: the DeepSeek Anthropic-format endpoint, key from DEEPSEEK_API_KEY.')
    parser.add_argument('--host', help='Registered host for the Strata backend.')
    parser.add_argument('--role-as-system', action='store_const', const=True, default=None,
                        help="Role instructions through --append-system-prompt; default: the plan's claude_role_as_system, "
                             'else in the user message.')
    args = parser.parse_args(argv)
    if args.backend == 'strata' and not args.host:
        parser.error('--backend strata needs --host')
    return args


if __name__ == '__main__':
    args = arguments()
    ch.pinned_binary(args.claude)
    print(json.dumps(run(args.plan, args.out, args.model, args.effort, args.label, args.claude, args.handoffs, args.limit,
                         args.time_limit_seconds, not args.no_startup_prompt, not args.no_compact_prompt, args.dry_run,
                         args.backend, args.host, args.role_as_system),
                     ensure_ascii=False))
