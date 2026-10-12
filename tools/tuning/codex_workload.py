"""Run the sampling or window tuning workload through native Codex, one cold start per instance.

Each instance: (sampling) deploy the condition over the host default -> take the lease -> start the model with the
instance's context tier -> verify the loaded startup prompt and engine window -> run the Codex sessions -> stop the
model, capture the engine log -> score, analyse the sessions and check the condition took effect.  The staged
decision (tools.tuning.staged_decision) decides whether another round of +2 instances per condition is needed.

    python3 -m tools.tuning.codex_workload check --plan PLAN
    python3 -m tools.tuning.codex_workload run --plan PLAN --out DIR [--limit N]
    python3 -m tools.tuning.codex_workload decide --out DIR
"""
import argparse
from collections import Counter
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time

from tools.tuning import sampling_bank, staged_decision, window_bank

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / 'config/model-catalog.json'
CODEX = Path.home() / ('.local/lib/node_modules/@openai/codex/node_modules/@openai/codex-linux-x64/'
                       'vendor/x86_64-unknown-linux-musl/bin/codex')
STARTUP = ROOT / 'config/prompts/startup-instructions.txt'
TIERS = {156584: 100000, 206584: 150000}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def save(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def load_plan(path):
    """Plan with its frozen input and condition files; refuse anything that changed since it was frozen."""
    path = Path(path)
    plan = json.loads(path.read_text())
    if plan.get('schema') != 'codex-workload-v1' or plan['workload'] not in ('sampling', 'window'):
        raise ValueError('Not a Codex workload plan')
    raw = (ROOT / plan['input']['path']).read_bytes()
    if sha(raw) != plan['input']['sha256']:
        raise ValueError('Frozen workload input changed')
    names = set(plan['conditions'])
    if len(names) != 2 or set(plan['first_round']) != names or \
            any(plan['first_round'].count(n) != staged_decision.SIZES[0] for n in names):
        raise ValueError('First round must run each of the two conditions three times')
    conditions = {}
    for name, spec in plan['conditions'].items():
        window = spec['context_window']
        if window not in TIERS or spec['threshold'] != TIERS[window]:
            raise ValueError(name + ': context tier and threshold disagree')
        if plan['workload'] == 'window' and spec.get('deployment_condition'):
            raise ValueError('Window conditions change only the tier, never the deployment')
        if spec.get('deployment_condition'):
            from tools.ops.deployment_source import load_condition
            condition, digest = load_condition(path.parent / spec['deployment_condition'])
            if digest != spec['deployment_condition_sha256'] or condition.get('model') != plan['model']:
                raise ValueError(name + ': condition file differs from the frozen plan')
            conditions[name] = (condition, digest)
        else:
            conditions[name] = (None, None)
    return plan, json.loads(raw), conditions


def schedule(plan, rounds):
    """ABBA-style order: the frozen first round, then +2 per condition per round, alternating which goes first."""
    order = list(plan['first_round'])
    a, b = order[0], next(n for n in order if n != order[0])
    for r in range(1, rounds):
        order += [b, a, a, b] if r % 2 else [a, b, b, a]
    return order


def codex_overrides(plan, spec, folder, base_url):
    """`-c` overrides for one Codex session; the compaction prompt is the project base plus the native supplement."""
    from tools.metrics.prompt_policy import compaction_config
    from tools.reviewer.arw_measure import local_review_catalog
    slug = 'qwen3.8-flash-next-' + plan['model'].lower()
    catalog = local_review_catalog(CATALOG, folder / 'catalog.json', plan['model'], spec['context_window'])
    values = {'model': slug, 'model_provider': 'qwen_strata', 'model_catalog_json': str(catalog),
              'model_context_window': spec['context_window'],
              'model_auto_compact_token_limit': spec['threshold'], 'model_auto_compact_token_limit_scope': 'total',
              'model_reasoning_effort': plan['fixed_conditions']['effort'], 'web_search': 'disabled',
              'sandbox_mode': 'workspace-write' if plan['workload'] == 'sampling' else 'read-only',
              'approval_policy': 'never', 'agents.enabled': False, 'features.memories': False,
              'model_providers.qwen_strata.name': 'Local Strata tuning workload',
              'model_providers.qwen_strata.base_url': base_url,
              'model_providers.qwen_strata.wire_api': 'responses',
              'model_providers.qwen_strata.env_key': 'STRATA_API_KEY',
              'model_providers.qwen_strata.requires_openai_auth': False,
              'model_providers.qwen_strata.supports_websockets': False,
              'model_providers.qwen_strata.request_max_retries': 0,
              'model_providers.qwen_strata.stream_max_retries': 0}
    values = compaction_config(values, folder / 'prompt-policy')
    args = []
    for key, value in values.items():
        args += ['-c', key + '=' + json.dumps(value)]
    return args


def codex_exec(args, workspace, home, key, prompt, log, timeout, resume=None):
    """One `codex exec` turn; returns (exit code, thread id, seconds).  The prompt goes through stdin."""
    command = [str(CODEX), 'exec', *(['resume', resume] if resume else []), '--json', '--skip-git-repo-check',
               *args, '-']
    env = dict(os.environ, CODEX_HOME=str(home), STRATA_API_KEY=key)
    started = time.monotonic()
    with open(log, 'a') as out:
        try:
            done = subprocess.run(command, input=prompt, text=True, stdout=out, stderr=subprocess.STDOUT,
                                  cwd=workspace, env=env, timeout=timeout)
            code = done.returncode
        except subprocess.TimeoutExpired:
            code = 'timeout'
    thread = None
    for line in Path(log).read_text(errors='replace').splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get('type') == 'thread.started':
            thread = event.get('thread_id')
    return code, thread, time.monotonic() - started


def rollout(home):
    """The single session file under this isolated CODEX_HOME."""
    files = sorted(Path(home).glob('sessions/**/rollout-*.jsonl'))
    if len(files) != 1:
        raise RuntimeError(f'Expected one Codex session in {home}, found {len(files)}')
    return files[0]


def analyse_session(path):
    """Compactions (with the batch they follow), tool calls, repetition and the assistant's final reply per turn."""
    events = [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]
    calls, replies, compactions, last_user = [], [], [], None
    current = None
    for e in events:
        p = e.get('payload') or {}
        if e.get('type') == 'compacted':
            compactions.append({'after_user_turn': last_user})
        if e.get('type') != 'response_item':
            continue
        if p.get('type') == 'message' and p.get('role') == 'user':
            text = ''.join(c.get('text', '') for c in p.get('content', []))
            if text.startswith('<') or text.startswith('# AGENTS.md'):
                continue
            batch = re.match(r'Batch (\d+)/', text)
            last_user = ('opening' if text.startswith('This is a long-context') else f'batch {batch.group(1)}'
                         if batch else 'questions' if text.startswith('Questions about') else 'task')
            current = {'turn': last_user, 'text': None}
            replies.append(current)
        elif p.get('type') == 'message' and p.get('role') == 'assistant' and current is not None:
            current['text'] = ''.join(c.get('text', '') for c in p.get('content', []))
        elif p.get('type') in ('function_call', 'custom_tool_call', 'local_shell_call'):
            calls.append({'name': p.get('name') or p.get('type'),
                          'arguments': p.get('arguments') or p.get('input') or json.dumps(p.get('action'))})
    signature = [(c['name'], c['arguments']) for c in calls]
    longest, run = 0, 0
    for i, s in enumerate(signature):
        run = run + 1 if i and s == signature[i - 1] else 1
        longest = max(longest, run)
    repeated = Counter(signature)
    texts = [r['text'] for r in replies if r['text']]
    repeated_lines = max((max(Counter(l for l in t.splitlines() if l.strip()).values(), default=0) for t in texts),
                         default=0)
    return {'compactions': compactions, 'tool_calls': len(calls), 'calls': calls,
            'loop': {'longest_identical_call_run': longest,
                     'calls_repeated_3_or_more': sum(v for v in repeated.values() if v >= 3),
                     'duplicate_replies': len(texts) - len(set(texts)),
                     'max_repeated_line_in_a_reply': repeated_lines},
            'replies': replies}


def escapes(calls, workspace):
    """Tool calls naming an absolute path outside the workspace, a parent directory or Codex session material."""
    workspace, flagged = str(Path(workspace).resolve()), []
    for c in calls:
        text = str(c['arguments'])
        paths = re.findall(r'(?<![\w.])(/[\w.\-/]+|~[\w.\-/]*)', text)
        outside = [p for p in paths if not p.startswith(workspace) and p not in ('/dev/null', '/tmp')
                   and not p.startswith(('/usr/', '/bin/'))]
        if outside or '..' in text or 'sessions' in text or 'CODEX_HOME' in text:
            flagged.append({'call': c, 'outside': outside})
    return flagged


def session_effect(workload, spec, length, analysis):
    """Did compaction happen where this condition must make it happen (window) or not at all (sampling)?"""
    problems, count = [], len(analysis['compactions'])
    if workload == 'sampling' and count:
        problems.append(f'sampling session compacted {count} times; the workload must stay below the threshold')
    if workload == 'window':
        tier = spec['context_window']
        if length == 'L130' and tier == 156584 and count < 1:
            problems.append('L130 at 156584 did not compact')
        if length == 'L130' and tier == 206584 and count:
            problems.append(f'L130 at 206584 compacted {count} times')
        if length == 'L180' and count < 1:
            problems.append(f'L180 at {tier} did not compact')
        if analysis['tool_calls']:
            problems.append(f'{analysis["tool_calls"]} tool calls in a conversation-only recall session')
    return problems


def run_sampling(plan, data, spec, folder, args_for, key):
    """Problem set in chunks; each chunk is a fresh Codex session in its own workspace."""
    chunk, rows, sessions = plan['chunk'], [], []
    numbers = [x['number'] for x in data['items']]
    for start in range(0, len(numbers), chunk):
        part = numbers[start:start + chunk]
        here = folder / f'chunk-{start // chunk + 1:02d}'
        workspace, home = here / 'workspace', here / 'codex-home'
        home.mkdir(parents=True)
        sampling_bank.export(data, workspace, set(part))
        subprocess.run(['git', 'init', '-q'], cwd=workspace, check=True)
        prompt = (f'Solve the problems in this directory ({", ".join(part)}). Read README.md first and follow it. '
                  'Finish when every answer or solution file is written.')
        code, thread, seconds = codex_exec(args_for(here), workspace, home, key, prompt, here / 'codex.jsonl',
                                           plan['per_session_seconds_limit'])
        analysis = analyse_session(rollout(home))
        analysis['escapes'] = escapes(analysis['calls'], workspace)
        save(here / 'session-analysis.json', analysis)
        sessions.append({'escapes': len(analysis['escapes']), 'chunk': part, 'exit': code, 'thread': thread, 'seconds': seconds,
                         'compactions': len(analysis['compactions']), 'tool_calls': analysis['tool_calls'],
                         'loop': analysis['loop'], 'effect_problems': session_effect('sampling', spec, None, analysis)})
        rows += sampling_bank.score({**data, 'items': [x for x in data['items'] if x['number'] in part]},
                                    workspace)['rows']
    return {'score': sum(r['correct'] for r in rows) / len(rows), 'rows': rows, 'sessions': sessions}


def run_window(plan, data, spec, folder, args_for, key):
    """One conversation per length: opening, record batches, question turns, all in the same thread."""
    results = {}
    for name in plan['lengths']:
        length = data['lengths'][name]
        here = folder / name
        workspace, home = here / 'workspace', here / 'codex-home'
        workspace.mkdir(parents=True)
        home.mkdir()
        subprocess.run(['git', 'init', '-q'], cwd=workspace, check=True)
        log, thread, turns = here / 'codex.jsonl', None, []
        for prompt in [length['opening'], *length['turns'], *length['question_turns']]:
            code, started, seconds = codex_exec(args_for(here), workspace, home, key, prompt, log,
                                                plan['per_session_seconds_limit'], resume=thread)
            thread = thread or started
            turns.append({'exit': code, 'seconds': seconds})
            if code != 0:
                break
        analysis = analyse_session(rollout(home))
        save(here / 'session-analysis.json', analysis)
        answers = [r['text'] for r in analysis['replies'] if r['turn'] == 'questions']
        scored = window_bank.score(length, answers)
        results[name] = {'score': scored['score'], 'by_group': scored['by_group'], 'rows': scored['rows'],
                         'thread': thread, 'turns': turns, 'compactions': analysis['compactions'],
                         'tool_calls': analysis['tool_calls'], 'loop': analysis['loop'],
                         'effect_problems': session_effect('window', spec, name, analysis)}
    rows = [r for v in results.values() for r in v['rows']]
    return {'score': sum(r['correct'] for r in rows) / len(rows), 'lengths': results}


def engine_effect(log, health, spec, condition, configuration):
    """Engine window, startup prompt and (sampling) deployed request defaults as the engine actually ran them."""
    from tools.metrics.prompt_policy import verify_loaded_startup
    from tools.tuning.arw_dimension import verify_effect
    problems = []
    try:
        verify_loaded_startup(health.get('startup_instructions'), sha(STARTUP.read_bytes()))
    except ValueError as error:
        problems.append(str(error))
    if health.get('max_context') not in (None, spec['context_window']):
        problems.append(f'native health reports max_context {health.get("max_context")}')
    checks = {'context_window': spec['context_window'], **spec.get('checks', {})}
    effect = verify_effect(log, [], condition or {}, configuration, checks)
    return problems + effect['problems'], effect


def run_instance(plan, data, conditions, name, folder):
    from tools.ops.measurement_host import MeasurementHost
    from tools.reviewer.arw_measure import stop_and_capture_engine_log
    from tools.metrics.strata_tokens import engine_rates
    spec, (condition, digest) = plan['conditions'][name], conditions[name]
    folder.mkdir(parents=True)
    if condition is not None:
        from tools.ops.deploy import deploy
        save(folder / 'deploy.json', deploy(plan['host'], condition=(condition, digest)))
    host = MeasurementHost(plan['host'], condition=condition)
    save(folder / 'sources.json', host.verify_sources())
    owner = host.controller(folder / 'controller')
    record = {'condition': name, 'condition_sha256': digest, 'started': datetime.now().isoformat(timespec='seconds')}
    with owner:
        offset = host.log_offset(plan['model'])
        try:
            state, load = owner.start(model=plan['model'], context_window=spec['context_window'])
            health = state.get('native_health') or {}
            save(folder / 'start.json', {'status': state.get('status'), 'load_seconds': load, 'native_health': health})
            args_for = lambda here: codex_overrides(plan, spec, here, owner.model_base + '/v1')
            runner = run_sampling if plan['workload'] == 'sampling' else run_window
            began = time.monotonic()
            record.update(runner(plan, data, spec, folder, args_for, owner.key))
            record['session_seconds'] = time.monotonic() - began
        finally:
            stopped, requests, tokens = stop_and_capture_engine_log(owner, host.installation, plan['model'], offset,
                                                                    folder, host)
            record.update(stop=stopped.get('status'), tokens=tokens, **engine_rates(requests),
                          max_request_input=max((r['input'] for r in requests), default=None))
    log = (folder / 'engine-request-log.txt').read_text()
    problems, effect = engine_effect(log, health, spec, condition, host.configuration(plan['model']))
    sessions = record.get('sessions') or list(record.get('lengths', {}).values())
    problems += [p for s in sessions for p in s['effect_problems']]
    problems += [f'{s["escapes"]} tool calls leave the workspace' for s in sessions if s.get('escapes')]
    if plan['workload'] == 'window' and spec['context_window'] == 206584 and \
            (record['max_request_input'] or 0) > plan['verified_prompt_tokens']:
        problems.append(f'a request input of {record["max_request_input"]} exceeds the verified '
                        f'{plan["verified_prompt_tokens"]}')
    record['effect'] = {'ok': not problems, 'problems': problems, 'engine': effect}
    save(folder / 'result.json', record)
    return record


def run(plan_path, out, limit=None):
    """Run the next scheduled instances; stop after each round so the staged decision can be taken."""
    plan, data, conditions = load_plan(plan_path)
    if (plan.get('authorization') or {}).get('approved') is not True:
        raise ValueError('This plan is not approved for model runs')
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    progress_path = out / 'progress.json'
    progress = json.loads(progress_path.read_text()) if progress_path.exists() else {'rounds': 1, 'instances': []}
    order = schedule(plan, progress['rounds'])
    done = progress['instances']
    if [r['condition'] for r in done] != order[:len(done)]:
        raise ValueError('Recorded instances differ from the frozen schedule')
    if done and not done[-1]['effect_ok']:
        raise RuntimeError('The last instance failed its effect check; assess the impact before continuing')
    for slot in range(len(done), len(order))[:limit]:
        name = order[slot]
        record = run_instance(plan, data, conditions, name, out / f'{slot + 1:02d}-{name}')
        done.append({'slot': slot + 1, 'condition': name, 'score': record.get('score'),
                     'effect_ok': record['effect']['ok'], 'folder': f'{slot + 1:02d}-{name}'})
        save(progress_path, progress)
        if not record['effect']['ok']:
            raise RuntimeError(f'Instance {slot + 1} ({name}) failed its effect check: {record["effect"]["problems"]}')
    return progress


def decide(out, plan_path):
    """Staged decision on the closed instances; on 'continue' the next run adds one round (+2 per condition)."""
    plan, _, _ = load_plan(plan_path)
    progress_path = Path(out) / 'progress.json'
    progress = json.loads(progress_path.read_text())
    a, b = list(plan['conditions'])
    scores = {n: [r['score'] for r in progress['instances'] if r['condition'] == n] for n in (a, b)}
    if len(scores[a]) != len(scores[b]) or len(progress['instances']) != len(schedule(plan, progress['rounds'])):
        raise ValueError('The current round is not complete')
    result = staged_decision.judge(scores[a], scores[b])
    result.update(a=a, b=b, means={n: sum(v) / len(v) for n, v in scores.items()})
    progress.setdefault('decisions', []).append(result)
    if result['decision'] == 'continue':
        progress['rounds'] += 1
    save(progress_path, progress)
    return result


def check(plan_path):
    """No-model review of a plan: frozen input, conditions, schedule, Codex binary and per-workload self check."""
    plan, data, conditions = load_plan(plan_path)
    codex = CODEX.read_bytes()
    if sha(codex) != plan['fixed_conditions']['native_cli_sha256']:
        raise ValueError('Native Codex binary differs from the frozen plan')
    own = sampling_bank.self_check(data) if plan['workload'] == 'sampling' else window_bank.self_check(data)
    return {'workload': plan['workload'], 'input_sha256': plan['input']['sha256'], 'self_check': own,
            'first_round': schedule(plan, 1), 'second_round_adds': schedule(plan, 2)[6:],
            'conditions': {n: {'context_window': plan['conditions'][n]['context_window'],
                               'deployment_condition_sha256': conditions[n][1]} for n in plan['conditions']}}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)
    for command in ('check', 'run', 'decide'):
        p = sub.add_parser(command)
        p.add_argument('--plan', type=Path, required=True)
        if command != 'check':
            p.add_argument('--out', type=Path, required=True)
        if command == 'run':
            p.add_argument('--limit', type=int)
    args = parser.parse_args()
    if args.command == 'check':
        result = check(args.plan)
    elif args.command == 'run':
        result = run(args.plan, args.out, args.limit)
    else:
        result = decide(args.out, args.plan)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
