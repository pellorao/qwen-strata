"""Run the sampling or window tuning workload through native Codex, one cold start per instance.

Each instance: (sampling) deploy the condition over the host default -> take the lease -> start the model with the
instance's context tier -> verify the loaded startup prompt and engine window -> run the Codex sessions -> stop the
model, capture the engine log -> score, analyse the sessions and check the condition took effect.  The staged
decision (tools.tuning.staged_decision) decides whether another round of +2 instances per condition is needed.

Every tool command runs in a native Codex permission profile that sees only the session's workspace (`isolation`,
verified without a model by tools.tuning.sandbox_probe, which `check` runs).  A sampling plan with `"pilot": true`
runs one instance of one condition, one item per session, to measure Qwen's per-item time and tokens.

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
import signal
import subprocess
import time

from tools.tuning import sampling_bank, staged_decision, window_bank

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / 'config/model-catalog.json'
CODEX_VENDOR = Path.home() / '.local/lib/node_modules/@openai/codex/node_modules/@openai/codex-linux-x64/vendor'
CODEX = CODEX_VENDOR / 'x86_64-unknown-linux-musl/bin/codex'
STARTUP = ROOT / 'config/prompts/startup-instructions.txt'
TIERS = {156584: 100000, 206584: 150000}
KILL_GRACE_SECONDS = 5          # SIGTERM to the session's process group, then SIGKILL
ENGINE_IDLE_LIMIT_SECONDS = 120  # a cancelled request must leave Strata idle within this


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
    data = json.loads(raw)
    if plan.get('pilot'):
        if plan['workload'] != 'sampling' or len(names) != 1 or plan['first_round'] != list(names) or plan['chunk'] != 1:
            raise ValueError('A pilot runs one sampling condition once, one item per session')
    elif len(names) not in staged_decision.FINAL_BOUNDS or set(plan['first_round']) != names or \
            any(plan['first_round'].count(n) != staged_decision.SIZES[0] for n in names):
        raise ValueError('First round must run each of the 2-6 conditions three times')
    if plan['workload'] == 'sampling' and not plan.get('pilot') and sampling_bank.points_of(data) is None:
        raise ValueError('A tuning sampling set must carry per-item points')
    limit, other = ('per_session_seconds_limit', 'instance_seconds_limit')[::1 if plan.get('pilot') else -1]
    if not isinstance(plan.get(limit), (int, float)) or plan[limit] <= 0 or other in plan:
        raise ValueError('A pilot sets per_session_seconds_limit; every other plan sets instance_seconds_limit only')
    if plan['workload'] == 'window' and plan['length'] not in data['lengths']:
        raise ValueError('A window plan runs exactly one frozen length per instance')
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
    return plan, data, conditions


def next_round(sampled, round_number):
    """+2 instances for each candidate still sampled, mirrored (a b c c b a), direction alternating per round."""
    order = list(sampled) if round_number % 2 else list(reversed(sampled))
    return order + order[::-1]


def isolation(workload, folder):
    """Native Codex permission profile: tool commands see only the system minimum, the Codex binary (the sandbox
    helper re-executes it) and this session's workspace, never the bank, the project, CODEX_HOME or /tmp.  Sampling
    may write its workspace; window recall only reads.  The provider key is kept out of the shell environment.
    Codex would otherwise add its own CODEX_HOME (the live rollout we analyse) as readable, so it is denied.
    Verified without a model by tools.tuning.sandbox_probe."""
    workspace = str((Path(folder) / 'workspace').resolve())
    return {'default_permissions': 'tuning_workspace',
            'permissions.tuning_workspace.filesystem': {
                ':minimal': 'read', str(CODEX_VENDOR): 'read',
                workspace: 'write' if workload == 'sampling' else 'read',
                str((Path(folder) / 'codex-home').resolve()): 'none'},
            'shell_environment_policy.exclude': ['STRATA_*', 'CODEX_*'],
            'shell_environment_policy.set': {'TMPDIR': workspace}}


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
              'approval_policy': 'never', 'agents.enabled': False, 'features.memories': False,
              'model_providers.qwen_strata.name': 'Local Strata tuning workload',
              'model_providers.qwen_strata.base_url': base_url,
              'model_providers.qwen_strata.wire_api': 'responses',
              'model_providers.qwen_strata.env_key': 'STRATA_API_KEY',
              'model_providers.qwen_strata.requires_openai_auth': False,
              'model_providers.qwen_strata.supports_websockets': False,
              'model_providers.qwen_strata.request_max_retries': 0,
              'model_providers.qwen_strata.stream_max_retries': 0,
              **isolation(plan['workload'], folder)}
    values = compaction_config(values, folder / 'prompt-policy')
    args = []
    for key, value in values.items():
        args += ['-c', key + '=' + toml_value(value)]
    return args


def toml_value(value):
    """JSON already is TOML for strings, numbers, booleans and arrays; tables need TOML's inline form."""
    if isinstance(value, dict):
        return '{' + ', '.join(json.dumps(k) + ' = ' + toml_value(v) for k, v in value.items()) + '}'
    return json.dumps(value)


def run_limited(command, prompt, out, cwd, env, timeout):
    """Run in its own process group; at the hard limit kill the whole group (Codex and every shell it started).
    Returns the exit code, or 'timeout'.  Killing Codex drops its HTTP stream, which makes the frontend and then
    Strata cancel the generation (`wait_engine_idle` confirms it)."""
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=out, stderr=subprocess.STDOUT, text=True,
                               cwd=cwd, env=env, start_new_session=True)
    try:
        process.communicate(prompt, timeout=max(timeout, 0.1))
        return process.returncode
    except subprocess.TimeoutExpired:
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.killpg(process.pid, sig)
            except ProcessLookupError:
                break
            try:
                process.wait(timeout=KILL_GRACE_SECONDS)
                break
            except subprocess.TimeoutExpired:
                continue
        process.wait()
        return 'timeout'


def wait_engine_idle(model_base, key, limit=ENGINE_IDLE_LIMIT_SECONDS):
    """After a forced stop: poll Strata's /v1/status (through the frontend) until no request runs or waits.
    Returns the seconds waited; raises if the engine is still busy at the limit."""
    import urllib.request
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    started = time.monotonic()
    while True:
        request = urllib.request.Request(model_base + '/v1/status', headers={'Authorization': 'Bearer ' + key})
        with opener.open(request, timeout=30) as reply:
            live = json.load(reply).get('live') or {}
        if live.get('state') == 'idle' and not live.get('queued') and not live.get('running'):
            return time.monotonic() - started
        if time.monotonic() - started > limit:
            raise RuntimeError(f'Engine still {live.get("state")} {limit} s after the forced stop')
        time.sleep(2)


def codex_exec(args, workspace, home, key, prompt, log, timeout, resume=None):
    """One `codex exec` turn under a hard limit; returns (exit code or 'timeout', thread id, seconds)."""
    command = [str(CODEX), 'exec', *(['resume', resume] if resume else []), '--json', '--skip-git-repo-check',
               *args, '-']
    # Codex runs inside the workspace, so a relative CODEX_HOME would not resolve there.
    env = dict(os.environ, CODEX_HOME=str(Path(home).resolve()), STRATA_API_KEY=key)
    started = time.monotonic()
    with open(log, 'a') as out:
        code = run_limited(command, prompt, out, workspace, env, timeout)
    thread = None
    for line in Path(log).read_text(errors='replace').splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get('type') == 'thread.started':
            thread = event.get('thread_id')
    return code, thread, time.monotonic() - started


def rollout(home, timed_out=False):
    """The single session file under this isolated CODEX_HOME (None if a forced stop came before Codex wrote it)."""
    files = sorted(Path(home).glob('sessions/**/rollout-*.jsonl'))
    if not files and timed_out:
        return None
    if len(files) != 1:
        raise RuntimeError(f'Expected one Codex session in {home}, found {len(files)}')
    return files[0]


def analyse_session(path):
    """Compactions (with the batch they follow), tool calls, repetition and the assistant's final reply per turn.
    A rollout cut by a forced stop may end in a partial line, which is skipped."""
    events = []
    for line in (Path(path).read_text().splitlines() if path else []):
        try:
            events.append(json.loads(line))
        except ValueError:
            continue
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


def session_limit(plan, data):
    """Hard seconds per sampling session: a pilot sets it directly; a tuning plan splits its instance limit evenly
    over the sessions, so every chunk gets the same chance whatever happened in the chunks before it."""
    if plan.get('pilot'):
        return plan['per_session_seconds_limit']
    sessions = -(-len(data['items']) // plan['chunk'])
    return plan['instance_seconds_limit'] / sessions


def run_sampling(plan, data, spec, folder, args_for, key, mark, settle):
    """Problem set in chunks; each chunk is a fresh Codex session in its own workspace.  `mark()` is the engine log
    offset, taken around each session so its tokens can be attributed after the final capture.  A session that hits
    its hard limit is killed, `settle()` waits until Strata has cancelled the generation, and the session is scored
    on the files it had written; the timeout itself does not invalidate the instance."""
    chunk, rows, sessions = plan['chunk'], [], []
    numbers = [x['number'] for x in data['items']]
    limit = session_limit(plan, data)
    for start in range(0, len(numbers), chunk):
        part = numbers[start:start + chunk]
        here = folder / f'chunk-{start // chunk + 1:02d}'
        workspace, home = here / 'workspace', here / 'codex-home'
        home.mkdir(parents=True)
        sampling_bank.export(data, workspace, set(part))
        subprocess.run(['git', 'init', '-q'], cwd=workspace, check=True)
        prompt = (f'Solve the problems in this directory ({", ".join(part)}). Read README.md first and follow it. '
                  f'This session has a hard limit of {round(limit / 60, 1):g} minutes: write each answer or solution '
                  'file as soon as its problem is done. Finish when every answer or solution file is written.')
        log_start = mark()
        code, thread, seconds = codex_exec(args_for(here), workspace, home, key, prompt, here / 'codex.jsonl',
                                           limit)
        timed_out = code == 'timeout'
        idle_seconds = settle() if timed_out else None
        log_end = mark()
        analysis = analyse_session(rollout(home, timed_out))
        analysis['escapes'] = escapes(analysis['calls'], workspace)
        save(here / 'session-analysis.json', analysis)
        scored = sampling_bank.score({**data, 'items': [x for x in data['items'] if x['number'] in part]},
                                     workspace)['rows']
        sessions.append({'escapes': len(analysis['escapes']), 'chunk': part, 'exit': code, 'thread': thread,
                         'seconds': seconds, 'limit_seconds': limit, 'timed_out': timed_out,
                         'engine_idle_after_seconds': idle_seconds,
                         'answered': sum(r['answered'] for r in scored), 'log_bytes': [log_start, log_end],
                         'compactions': len(analysis['compactions']), 'tool_calls': analysis['tool_calls'],
                         'loop': analysis['loop'], 'effect_problems': session_effect('sampling', spec, None, analysis)})
        rows += scored
    return {**sampling_bank.weighted(rows), 'sessions': sessions,
            'timed_out_sessions': sum(x['timed_out'] for x in sessions),
            'answered': sum(r['answered'] for r in rows)}


def run_window(plan, data, spec, folder, args_for, key, mark, settle):
    """One conversation of the plan's single length: opening, record batches, question turns, in one thread.
    The instance limit covers the whole conversation; each turn gets what is left.  At the limit the turn is killed,
    `settle()` waits for Strata to go idle, no further turn is sent and unanswered questions score zero."""
    results = {}
    deadline = time.monotonic() + plan['instance_seconds_limit']
    for name in [plan['length']]:
        length = data['lengths'][name]
        here = folder / name
        workspace, home = here / 'workspace', here / 'codex-home'
        workspace.mkdir(parents=True)
        home.mkdir()
        subprocess.run(['git', 'init', '-q'], cwd=workspace, check=True)
        log, thread, turns, timed_out = here / 'codex.jsonl', None, [], False
        prompts = [length['opening'], *length['turns'], *length['question_turns']]
        for prompt in prompts:
            left = deadline - time.monotonic()
            if left <= 0:
                timed_out = True
                break
            code, started, seconds = codex_exec(args_for(here), workspace, home, key, prompt, log, left,
                                                resume=thread)
            thread = thread or started
            turns.append({'exit': code, 'seconds': seconds})
            if code == 'timeout':
                timed_out = True
                turns[-1]['engine_idle_after_seconds'] = settle()
            if code != 0:
                break
        analysis = analyse_session(rollout(home, timed_out))
        save(here / 'session-analysis.json', analysis)
        answers = [r['text'] for r in analysis['replies'] if r['turn'] == 'questions']
        scored = window_bank.score(length, answers)
        results[name] = {'score': scored['score'], 'by_group': scored['by_group'], 'rows': scored['rows'],
                         'thread': thread, 'turns': turns, 'turns_planned': len(prompts), 'timed_out': timed_out,
                         'compactions': analysis['compactions'],
                         'tool_calls': analysis['tool_calls'], 'loop': analysis['loop'],
                         'effect_problems': session_effect('window', spec, name, analysis)}
    rows = [r for v in results.values() for r in v['rows']]
    return {'score': sum(r['correct'] for r in rows) / len(rows), 'lengths': results}


def loaded_startup_sha():
    """The engine loads the startup prompt without the deprecated loop prevention block."""
    import sys
    sys.path.append(str(Path(__file__).resolve().parents[2] / 'src'))
    from startup_instructions import startup_prompt_bytes
    return sha(startup_prompt_bytes(STARTUP.read_bytes(), False))


def engine_effect(log, health, spec, condition, configuration):
    """Engine window, startup prompt and (sampling) deployed request defaults as the engine actually ran them."""
    from tools.metrics.prompt_policy import verify_loaded_startup
    from tools.tuning.arw_dimension import verify_effect
    problems = []
    try:
        verify_loaded_startup(health.get('startup_instructions'), loaded_startup_sha())
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
    from tools.metrics.strata_tokens import engine_rates, parse_engine_log, sum_engine_tokens
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
            record.update(runner(plan, data, spec, folder, args_for, owner.key, lambda: host.log_offset(plan['model']),
                                 lambda: wait_engine_idle(owner.model_base, owner.key)))
            record['session_seconds'] = time.monotonic() - began
        finally:
            stopped, requests, tokens = stop_and_capture_engine_log(owner, host.installation, plan['model'], offset,
                                                                    folder, host)
            record.update(stop=stopped.get('status'), tokens=tokens, **engine_rates(requests),
                          max_request_input=max((r['input'] for r in requests), default=None))
    log = (folder / 'engine-request-log.txt').read_text()
    for session in record.get('sessions', []):
        start, end = (b - offset for b in session['log_bytes'])
        records = parse_engine_log(log.encode()[start:end].decode(errors='replace'))
        session.update(tokens=sum_engine_tokens(records), **engine_rates(records))
    problems, effect = engine_effect(log, health, spec, condition, host.configuration(plan['model']))
    sessions = record.get('sessions') or list(record.get('lengths', {}).values())
    problems += [p for s in sessions for p in s['effect_problems']]
    # The sandbox already blocks every path outside the workspace (sandbox_probe); flagged calls are judged by
    # outcome in the session inspection: only a call that actually saw outside content invalidates the instance.
    record['escapes_for_review'] = sum(s.get('escapes', 0) for s in sessions)
    if plan['workload'] == 'window' and spec['context_window'] == 206584 and \
            (record['max_request_input'] or 0) > plan['verified_prompt_tokens']:
        problems.append(f'a request input of {record["max_request_input"]} exceeds the verified '
                        f'{plan["verified_prompt_tokens"]}')
    record['effect'] = {'ok': not problems, 'problems': problems, 'engine': effect}
    save(folder / 'result.json', record)
    return record


def run(plan_path, out, limit=None):
    """Run the scheduled instances not yet done; stop at the end of the round so the staged decision can be taken."""
    plan, data, conditions = load_plan(plan_path)
    if (plan.get('authorization') or {}).get('approved') is not True:
        raise ValueError('This plan is not approved for model runs')
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    progress_path = out / 'progress.json'
    progress = json.loads(progress_path.read_text()) if progress_path.exists() else \
        {'order': list(plan['first_round']), 'instances': [], 'decisions': [], 'tied': []}
    order, done = progress['order'], progress['instances']
    if [r['condition'] for r in done] != order[:len(done)]:
        raise ValueError('Recorded instances differ from the recorded schedule')
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
    """Staged decision over the candidates still sampled; on 'continue' the next round (+2 each) is scheduled."""
    plan, _, _ = load_plan(plan_path)
    if plan.get('pilot'):
        raise ValueError('A pilot is a measurement of item cost, not a decision')
    progress_path = Path(out) / 'progress.json'
    progress = json.loads(progress_path.read_text())
    if len(progress['instances']) != len(progress['order']):
        raise ValueError('The current round is not complete')
    sampled = progress['decisions'][-1]['sampled_next'] if progress['decisions'] else list(plan['conditions'])
    scores = {n: [r['score'] for r in progress['instances'] if r['condition'] == n] for n in sampled}
    result = staged_decision.judge_many(scores, len(plan['conditions']))
    progress['tied'] += result['tied']
    result['tie_group'] = [result['leader'], *progress['tied']] if result['decision'] == 'equivalent' else None
    progress['decisions'].append(result)
    if result['decision'] == 'continue':
        progress['order'] += next_round(result['sampled_next'], len(progress['decisions']))
    save(progress_path, progress)
    return result


def check(plan_path):
    """No-model review of a plan: frozen input, conditions, schedule, Codex binary and per-workload self check."""
    plan, data, conditions = load_plan(plan_path)
    codex = CODEX.read_bytes()
    if sha(codex) != plan['fixed_conditions']['native_cli_sha256']:
        raise ValueError('Native Codex binary differs from the frozen plan')
    own = sampling_bank.self_check(data) if plan['workload'] == 'sampling' else window_bank.self_check(data)
    from tools.tuning.sandbox_probe import probe
    folder = ROOT / '.tmp/sandbox-probe' / datetime.now().strftime('%Y%m%d-%H%M%S')
    isolated = probe(folder, plan['workload'])
    return {'workload': plan['workload'], 'input_sha256': plan['input']['sha256'], 'self_check': own,
            'sandbox_probe': {'ok': isolated['ok'], 'problems': isolated['problems'], 'folder': str(folder)},
            'first_round': plan['first_round'],
            'second_round_if_all_open': next_round(list(plan['conditions']), 1),
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
