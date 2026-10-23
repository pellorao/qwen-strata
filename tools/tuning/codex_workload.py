"""Run the sampling or window tuning workload through native Codex, one cold start per instance.

Each instance: (sampling) deploy the condition over the host default -> take the lease -> start the model with the
instance's context tier -> verify the loaded startup prompt and engine window -> run the Codex sessions -> stop the
model, capture the engine log -> score, analyse the sessions and check the condition took effect.  The staged
decision (tools.tuning.staged_decision) decides whether another round of +2 instances per condition is needed.

Every tool command runs in a native Codex permission profile that sees only the session's workspace (`isolation`,
verified without a model by tools.tuning.sandbox_probe, which `check` runs).  Sampling runs the set in mixed groups
(directions and tiers dealt across groups by the frozen set's order), one fresh Codex session and one hard limit per
group (`run_sampling`).  A sampling plan with `"pilot": true` runs one instance of one condition to measure Qwen's
per-item correctness, time and tokens.

    python3 -m tools.tuning.codex_workload check --plan PLAN
    python3 -m tools.tuning.codex_workload run --plan PLAN --out DIR [--limit N] [--groups 7-10]
    python3 -m tools.tuning.codex_workload decide --out DIR
    python3 -m tools.tuning.codex_workload claude-window --plan PLAN --out DIR --condition NAME

The window workload (v2, benchmarks/window-load-v1) runs in blocks instead: the consecutive instances of one condition
share one lease, one load and one unscored warm-up conversation (`run_window_block`); `claude-window` is the pilot's
Claude Code mechanism check.
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
from tools.reviewer.native_cli_binding import CODEX, CODEX_VENDOR
from tools.reviewer.providers import CREDENTIAL_PATTERNS, CREDENTIAL_VARIABLES

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / 'config/model-catalog.json'
STARTUP = ROOT / 'config/prompts/startup-instructions.txt'
TIERS = {156584: 100000, 206584: 150000}
KILL_GRACE_SECONDS = 5          # SIGTERM to the session's process group, then SIGKILL
ENGINE_IDLE_LIMIT_SECONDS = 120  # a cancelled request must leave Strata idle within this
GROUP_ATTEMPTS = 2              # a compacted sampling group is invalid and rerun once in a fresh session
MIN_FREE_COMMIT_GIB = 8         # default plan `min_free_commit_gib`: a group starts only with this much Windows commit
COMMIT_POLL_SECONDS = 30        # below it the group waits, rechecking this often
COMMIT_WAIT_LIMIT_SECONDS = 600  # and the instance fails after this long (exhausted commit crashed WSL, 2026-10-12)


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
        if plan['workload'] == 'window' and sorted(plan['first_round']) != sorted(names):
            raise ValueError('A window pilot runs each condition once')
        if plan['workload'] == 'sampling' and (len(names) != 1 or plan['first_round'] != list(names)):
            raise ValueError('A pilot runs one sampling condition once')
    elif len(names) not in staged_decision.FINAL_BOUNDS or set(plan['first_round']) != names or \
            any(plan['first_round'].count(n) != staged_decision.SIZES[0] for n in names):
        raise ValueError('First round must run each of the 2-6 conditions three times')
    if plan['workload'] == 'sampling' and not plan.get('pilot') and sampling_bank.points_of(data) is None:
        raise ValueError('A tuning sampling set must carry per-item points')
    if plan['workload'] == 'sampling':
        size, per_tier = plan.get('group_size'), plan.get('group_seconds_per_tier')
        if not isinstance(size, int) or size <= 0 or not isinstance(per_tier, (int, float)) or per_tier <= 0 or \
                {'instance_seconds_limit', 'item_seconds_limit', 'session_token_budget'} & set(plan):
            raise ValueError('A sampling plan sets group_size and group_seconds_per_tier (one limit per group)')
    elif any(not isinstance(plan.get(k), (int, float)) or plan[k] <= 0 for k in (
            'instance_seconds_limit', 'warmup_batches', 'warmup_seconds_limit', 'verified_prompt_tokens')):
        raise ValueError('A window plan sets instance_seconds_limit, warmup_batches, warmup_seconds_limit and '
                         'verified_prompt_tokens')
    if plan['workload'] == 'window' and data.get('schema') != window_bank.SCHEMA:
        raise ValueError('A window plan runs the window workload v2 (one conversation with five checkpoints)')
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


def next_round(sampled, round_number, conditions=None, grouped=False):
    """+2 instances for each candidate still sampled.  Sampling: mirrored (a b c c b a), direction alternating per
    round.  `grouped` (window, design v2 U13): the same condition back to back (one load per condition and round),
    the condition order reversed every round: round 1 a a a b b b, round 2 b b a a, round 3 a a b b.
    `round_number` is the number of decisions taken; `conditions` fixes the grouped base order (the plan's)."""
    if not grouped:
        order = list(sampled) if round_number % 2 else list(reversed(sampled))
        return order + order[::-1]
    base = [c for c in (conditions or sampled) if c in sampled]
    order = base if round_number % 2 == 0 else base[::-1]
    return [c for c in order for _ in range(2)]


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
            'shell_environment_policy.exclude': ['STRATA_*', 'CODEX_*', *CREDENTIAL_VARIABLES, *CREDENTIAL_PATTERNS],
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
              # Codex 0.162 otherwise clones the curated plugin marketplace (~105 MB git checkout) into every fresh
              # CODEX_HOME at startup; its instructions never reach the model (plugins_instructions stays false).
              'features.plugins': False,
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
            # /v1/status reports activity.in_flight = the running request plus those queued behind it.
            in_flight = (json.load(reply).get('activity') or {}).get('in_flight')
        if in_flight == 0:
            return time.monotonic() - started
        if time.monotonic() - started > limit:
            raise RuntimeError(f'Engine still has {in_flight} requests in flight {limit} s after the forced stop')
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


def turn_label(text):
    """The workload turn a user message is: opening, batch NN, questions N (window v2), else 'task'; None for
    harness context (environment, AGENTS.md) and compaction summaries."""
    if text.startswith('<') or text.startswith('# AGENTS.md'):
        return None
    batch = re.match(r'Batch (\d+)/', text)
    checkpoint = re.match(r'Checkpoint (\d+) of ', text)
    if text.startswith('This is a long-context'):
        return 'opening'
    return f'batch {batch.group(1)}' if batch else f'questions {checkpoint.group(1)}' if checkpoint else 'task'


def message_text(payload):
    return ''.join(c.get('text', '') for c in payload.get('content', []) if isinstance(c, dict))


def analyse_session(path, in_text=None):
    """Compactions (with the turn they follow and the turns kept raw), tool calls, repetition, the assistant's final
    reply per turn, and per question turn the window timeline: which turns were still raw context when it was
    answered, after which turns compactions happened, and the input of its last request (`window_bank.score`).
    A rollout cut by a forced stop may end in a partial line, which is skipped."""
    events = []
    for line in (Path(path).read_text().splitlines() if path else []):
        try:
            events.append(json.loads(line))
        except ValueError:
            continue
    calls, replies, compactions, last_user = [], [], [], None
    current, raw, timeline, summary_candidate, compacted_in_turn = None, [], [], False, False
    texts = {}  # raw label -> the text Codex still holds for it (the oldest kept message may be truncated)

    def mark_raw(point):
        point['raw'] = list(raw)
        point['compactions_after'] = [c['after_user_turn'] for c in compactions]
        if in_text:
            point['in_text_ids'] = in_text(point['label'], [texts[k] for k in raw if k in texts])
    for e in events:
        p = e.get('payload') or {}
        if e.get('type') == 'compacted':
            # Codex records the compaction's own summary as an assistant message just before this event (inside the
            # turn that was running); it is not that turn's reply.
            history = [message_text(x) for x in p.get('replacement_history') or [] if isinstance(x, dict)]
            last_text = current['texts'][-1] if current is not None and current['texts'] else None
            if summary_candidate and last_text and (last_text.strip() == (p.get('message') or '').strip()
                                                    or any(last_text.strip() in h for h in history)):
                current['texts'].pop()
                current['text'] = current['texts'][-1] if current['texts'] else None
            summary_candidate = False
            kept = [turn_label(message_text(x)) for x in p.get('replacement_history') or []
                    if isinstance(x, dict) and x.get('type') == 'message' and x.get('role') == 'user']
            raw = [k for k in kept if k and k != 'task']
            texts = {turn_label(t): t for t in (message_text(x) for x in p.get('replacement_history') or []
                                                 if isinstance(x, dict) and x.get('type') == 'message'
                                                 and x.get('role') == 'user') if turn_label(t) not in (None, 'task')}
            summary = p.get('message') or next((h for h in history if turn_label(h) == 'task'), None)
            compactions.append({'after_user_turn': last_user, 'kept_raw': list(raw), 'summary': summary})
            compacted_in_turn = True
        if e.get('type') == 'event_msg' and p.get('type') == 'token_count' and p.get('info') and current is not None \
                and not compacted_in_turn:  # the turn's own last request, not the compaction's reset count
            current['input_tokens'] = p['info']['last_token_usage'].get('input_tokens')
        if e.get('type') != 'response_item':
            continue
        if p.get('type') == 'message' and p.get('role') == 'user':
            label = turn_label(message_text(p))
            if label is None:
                continue
            last_user = label
            raw.append(label)
            texts[label] = message_text(p)
            current = {'turn': label, 'text': None, 'texts': [], 'input_tokens': None}
            summary_candidate = compacted_in_turn = False
            replies.append(current)
            if label.startswith('questions '):
                timeline.append({'label': label, 'point': current})
                mark_raw(timeline[-1])
        elif p.get('type') == 'message' and p.get('role') == 'assistant' and current is not None:
            current['text'] = message_text(p)
            current['texts'].append(current['text'])
            summary_candidate = True
            if current['turn'].startswith('questions ') and not compacted_in_turn:
                mark_raw(timeline[-1])
        elif p.get('type') in ('function_call', 'custom_tool_call', 'local_shell_call'):
            summary_candidate = False
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
    points = [{'label': t['label'], 'raw': t.get('raw', []), 'compactions_after': t.get('compactions_after', []),
               'context_tokens': t['point']['input_tokens'], 'answered': t['point']['text'] is not None,
               **({'in_text_ids': t['in_text_ids']} if 'in_text_ids' in t else {})}
              for t in timeline]
    return {'compactions': compactions, 'tool_calls': len(calls), 'calls': calls,
            'loop': {'longest_identical_call_run': longest,
                     'calls_repeated_3_or_more': sum(v for v in repeated.values() if v >= 3),
                     'duplicate_replies': len(texts) - len(set(texts)),
                     'max_repeated_line_in_a_reply': repeated_lines},
            'replies': replies, 'timeline': points}


ROOT_DIRECTORIES = {'bin', 'boot', 'dev', 'etc', 'home', 'lib', 'lib64', 'media', 'mnt', 'opt', 'proc', 'root',
                    'run', 'sbin', 'srv', 'sys', 'tmp', 'usr', 'var'}


def path_arguments(text):
    """Path-shaped words of a tool call: absolute paths under a real root directory, `~` paths and parent steps.
    Code and sed scripts in the same call (`a // b`, `/1000`, `s/x/y/g`) are not paths and are not returned."""
    words = re.findall(r'[^\s\'"`;|&<>(){}\[\],=:]+', text.replace('\\n', ' ').replace('\\t', ' '))
    found = []
    for word in words:
        if word.startswith('/') and word.split('/')[1] in ROOT_DIRECTORIES or word == '~' or word.startswith('~/'):
            found.append(word)
        elif word == '..' or word.startswith('../') or '/../' in word or word.endswith('/..'):
            found.append(word)
    return found


def escapes(calls, workspace):
    """Tool calls naming a path outside the workspace, a parent directory step, or Codex session material."""
    workspace, flagged = str(Path(workspace).resolve()), []
    for c in calls:
        text = str(c['arguments'])
        outside = [p for p in path_arguments(text)
                   if not (p.startswith('/') and (p == workspace or p.startswith(workspace + '/')))
                   and p not in ('/dev/null', '/tmp') and not p.startswith(('/usr/', '/bin/'))]
        if outside or 'CODEX_HOME' in text:
            flagged.append({'call': c, 'outside': outside})
    return flagged


def window_effect(spec, analysis, minimum_compactions=None):
    """Did compaction happen as this window condition must make it happen (design §2.3: 156584 at least twice,
    206584 at least once over the whole conversation), and no tool call at all (a recall session uses none)?"""
    problems, count, tier = [], len(analysis['compactions']), spec['context_window']
    needed = (minimum_compactions or {156584: 2, 206584: 1})[tier]
    if count < needed:
        problems.append(f'{tier} compacted {count} times, fewer than {needed}')
    if analysis['tool_calls']:
        problems.append(f'{analysis["tool_calls"]} tool calls in a conversation-only recall session')
    return problems


def ack_problems(analysis):
    """Batch turns whose reply is not exactly `ACK nn` for that batch (recorded, not an invalidity)."""
    bad = []
    for r in analysis['replies']:
        if r['turn'].startswith('batch ') or r['turn'] == 'opening':
            want = '00' if r['turn'] == 'opening' else r['turn'].split()[1]
            match = window_bank.ACK.match(r['text'] or '')
            if not match or match.group(1) != want:
                bad.append({'turn': r['turn'], 'reply': (r['text'] or '')[:200]})
    return bad


def context_tokens(path):
    """Context size after the last request of a rollout (input plus output of that request); 0 before any."""
    size = 0
    for line in (Path(path).read_text().splitlines() if path else []):
        try:
            e = json.loads(line)
        except ValueError:
            continue
        info = (e.get('payload') or {}).get('info') if e.get('type') == 'event_msg' else None
        if (e.get('payload') or {}).get('type') == 'token_count' and info:
            size = info['last_token_usage']['total_tokens']
    return size


def groups(items, size):
    """The set's fixed groups: consecutive runs in set order (`sampling_bank.chunks`).  A frozen set lists its items
    in mixed group order (`sampling_bank.grouped` with the same size), so every group mixes directions and tiers and
    cannot be solved by one generic program; the model may still work on a group's items in any order."""
    return sampling_bank.chunks(items, size)


def group_seconds_limit(group, per_tier):
    """Hard limit of a group: the sum of its items' tiers times `group_seconds_per_tier`."""
    return sum(x['tier'] for x in group) * per_tier


def group_prompt(group, limit):
    numbers = ', '.join(x['number'] for x in group)
    return (f'Read README.md first and follow it. Solve problems {numbers} (problems/<P>.md), in any order. Together '
            f'they have a hard limit of {round(limit / 60, 1):g} minutes: write each answer or solution as soon as it '
            'is done. End your turn when all of them are written.')


def approximate_seconds(part, workspace, started, seconds):
    """Per item: gap between consecutive result writes; the group time left after the last write is shared by the
    items with nothing written (the model may work on several items at once, so this is only approximate)."""
    gaps = sampling_bank.write_intervals(part, workspace, started)
    missing = [x['id'] for x in part['items'] if x['id'] not in gaps]
    left = max(0.0, seconds - sum(gaps.values()))
    return {**gaps, **{i: left / len(missing) for i in missing}}, set(missing)


def wait_for_free_commit(read, minimum_gib, log=print, sleep=time.sleep, clock=time.monotonic):
    """Block while Windows' free commit (`read()`, GiB) is below `minimum_gib`, logging each recheck; give up with an
    error after COMMIT_WAIT_LIMIT_SECONDS.  Returns the seconds waited, which a group's time leaves out."""
    began = clock()
    while (free := read()) < minimum_gib:
        waited = clock() - began
        if waited >= COMMIT_WAIT_LIMIT_SECONDS:
            raise RuntimeError(f'Windows free commit stayed below {minimum_gib} GiB for {waited:.0f} s '
                               f'(now {free:.1f} GiB)')
        log(f'{datetime.now():%H:%M:%S} Windows free commit {free:.1f} GiB < {minimum_gib} GiB; '
            f'waiting {waited:.0f} s so far')
        sleep(COMMIT_POLL_SECONDS)
    return clock() - began


def run_sampling(plan, data, spec, folder, args_for, key, mark, settle, gate=lambda: 0.0):
    """The set in mixed groups of at most `group_size` items (`groups`), each in a fresh Codex session whose
    workspace holds only that group; the model reads and answers them in any order, together if it likes.  A group's hard limit is the sum of its tiers times
    `group_seconds_per_tier`: at the limit the session is killed, `settle()` waits until Strata has cancelled the
    generation, and the group is scored on what it wrote.  Group time is exact and `mark()` around the session
    attributes its engine tokens; per-item time is approximate (write intervals).  A compacted group is invalid and
    rerun in a fresh session; if every attempt compacts the instance fails its effect check.  `gate()` runs before
    each attempt, outside its time (the free commit wait)."""
    rows, runs = [], []
    only = plan.get('only_groups')  # recovery: run just these group numbers (numbering of the full set kept)
    for g, group in enumerate(groups(data['items'], plan['group_size']), 1):
        if only and g not in only:
            continue
        part, limit = {**data, 'items': group}, group_seconds_limit(group, plan['group_seconds_per_tier'])
        for attempt in range(1, GROUP_ATTEMPTS + 1):
            here = folder / f'group-{g:02d}-{attempt}'
            workspace, home = here / 'workspace', here / 'codex-home'
            home.mkdir(parents=True)
            sampling_bank.export(part, workspace)
            subprocess.run(['git', 'init', '-q'], cwd=workspace, check=True)
            waited = gate()
            log_start, started = mark(), time.time()
            code, thread, seconds = codex_exec(args_for(here), workspace, home, key, group_prompt(group, limit),
                                               here / 'codex.jsonl', limit)
            timed_out = code == 'timeout'
            idle_seconds = settle() if timed_out else None
            log_end = mark()
            path = rollout(home, timed_out)
            analysis = analyse_session(path)
            analysis['escapes'] = escapes(analysis['calls'], workspace)
            save(here / 'session-analysis.json', analysis)
            run = {'group': g, 'attempt': attempt, 'items': [x['number'] for x in group], 'thread': thread,
                   'exit': code, 'seconds': seconds, 'commit_wait_seconds': waited, 'limit_seconds': limit, 'timed_out': timed_out,
                   'engine_idle_after_seconds': idle_seconds, 'log_bytes': [log_start, log_end],
                   'context_after': context_tokens(path), 'compactions': len(analysis['compactions']),
                   'valid': not analysis['compactions'], 'escapes': len(analysis['escapes']),
                   'tool_calls': analysis['tool_calls'], 'loop': analysis['loop'], 'effect_problems': []}
            runs.append(run)
            # On disk at once, so a run that dies (2026-10-12: WSL lost its memory) still attributes this group's tokens.
            save(here / 'group.json', run)
            if run['valid']:
                break
        if not run['valid']:
            run['valid'] = True  # the attempt that counts; its compaction fails the instance's effect check
            run['effect_problems'] = [f'group {g} compacted in all {GROUP_ATTEMPTS} attempts']
        result = sampling_bank.score(part, workspace)
        approx, unwritten = approximate_seconds(part, workspace, started, seconds)
        run.update(score=result['score'], correct=result['correct'])
        save(here / 'group.json', run)
        rows += [{**r, 'group': g, 'approx_seconds': approx[r['id']], 'approx_from_remainder': r['id'] in unwritten,
                  'group_timed_out': timed_out} for r in result['rows']]
    valid = [r for r in runs if r['valid']]
    return {**sampling_bank.weighted(rows), 'clustered': sampling_bank.cluster_se(rows), 'items': rows, 'groups': runs,
            'timed_out_groups': sum(r['timed_out'] for r in valid), 'answered': sum(r['answered'] for r in rows),
            'compacted_attempts': sum(not r['valid'] for r in runs)}


def run_conversation(plan, sequence, folder, args_for, key, settle, seconds_limit, mark=None, in_text=None):
    """One Codex thread over `sequence` (opening, batches, question turns), one `codex exec` (resume) per turn.
    The limit covers the whole conversation and each turn gets what is left; at the limit the turn is killed,
    `settle()` waits for Strata to go idle, and no further turn is sent (unanswered questions score zero)."""
    workspace, home = folder / 'workspace', folder / 'codex-home'
    workspace.mkdir(parents=True)
    home.mkdir()
    subprocess.run(['git', 'init', '-q'], cwd=workspace, check=True)
    log, thread, turns, timed_out = folder / 'codex.jsonl', None, [], False
    deadline = time.monotonic() + seconds_limit
    log_start = mark() if mark else None
    for item in sequence:
        left = deadline - time.monotonic()
        if left <= 0:
            timed_out = True
            break
        code, started, seconds = codex_exec(args_for(folder), workspace, home, key, item['text'], log, left,
                                            resume=thread)
        thread = thread or started
        turns.append({'turn': item['label'], 'exit': code, 'seconds': seconds})
        if code == 'timeout':
            timed_out = True
            turns[-1]['engine_idle_after_seconds'] = settle()
        if code != 0:
            break
    log_end = mark() if mark else None
    path = rollout(home, timed_out)
    analysis = analyse_session(path, in_text)
    save(folder / 'session-analysis.json', analysis)
    return {'thread': thread, 'turns': turns, 'turns_planned': len(sequence), 'timed_out': timed_out,
            'work_seconds': sum(t['seconds'] for t in turns), 'log_bytes': [log_start, log_end],
            'rollout': str(path) if path else None}, analysis


def run_window(plan, data, spec, folder, args_for, key, mark, settle):
    """One scored instance: the whole v2 conversation; scored with its own measured timeline (window_bank.score)."""
    session, analysis = run_conversation(plan, data['sequence'], folder, args_for, key, settle,
                                         plan['instance_seconds_limit'], mark, window_bank.finder(data))
    replies = [r['text'] for r in analysis['replies'] if r['turn'].startswith('questions ')]
    timeline = complete_timeline(analysis['timeline'], len(data['checkpoint_positions']))
    scored = window_bank.score(data, replies, timeline)
    acks = ack_problems(analysis)
    return {**session, 'score': scored['score'], 'raw_score': scored['raw_score'], 'scoring': scored,
            'compactions': analysis['compactions'], 'tool_calls': analysis['tool_calls'], 'loop': analysis['loop'],
            'ack_problems': len(acks), 'ack_examples': acks[:5],
            'summary_retention': retention(data, analysis['compactions']),
            'effect_problems': window_effect(spec, analysis) + (
                [] if session['timed_out'] or len(replies) == len(data['checkpoint_positions'])
                else [f'{len(replies)} question turns answered of {len(data["checkpoint_positions"])}'])}


def complete_timeline(points, checkpoints):
    """Checkpoints never reached (hard limit) still score zero; they count as not in raw text, context unknown."""
    points = list(points)
    for n in range(len(points) + 1, checkpoints + 1):
        points.append({'label': f'questions {n}', 'raw': [], 'compactions_after': [], 'context_tokens': None,
                       'answered': False, 'reached': False})
    return points


def loaded_startup_sha():
    """The engine loads the startup prompt without the deprecated loop prevention block."""
    import sys
    sys.path.append(str(Path(__file__).resolve().parents[2] / 'src'))
    from startup_instructions import startup_prompt_bytes
    return sha(startup_prompt_bytes(STARTUP.read_bytes(), False))


def engine_effect(log, health, spec, condition, configuration, service_log=''):
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
    effect = verify_effect(log, [], condition or {}, configuration, checks, service_log)
    return problems + effect['problems'], effect


def session_records(log, sessions, offset):
    """Engine token records per window (sampling group).  The log is parsed whole, then each record goes to the one whose byte
    window holds the start of its line: an offset taken while a line was being written must not split the record."""
    from tools.metrics.strata_tokens import parse_engine_log
    starts, position = [], 0
    for line in log.splitlines(keepends=True):  # the same line split as parse_engine_log, measured in bytes
        starts.append(position + offset)
        position += len(line.encode())
    windows = [s['log_bytes'] for s in sessions]
    grouped = [[] for _ in sessions]
    for r in parse_engine_log(log):
        byte = starts[r['log_line'] - 1]
        for i, (start, end) in enumerate(windows):
            if start <= byte < end:
                grouped[i].append(r)
                break
    return grouped


def run_instance(plan, data, conditions, name, folder):
    """One sampling instance, one cold start (the window workload runs in blocks: run_window_block)."""
    from tools.ops.measurement_host import MeasurementHost
    from tools.reviewer.arw_measure import stop_and_capture_engine_log
    from tools.metrics.strata_tokens import engine_rates, sum_engine_tokens
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
        offset, service_offset = host.log_offset(plan['model']), host.log_offset()
        # The windows in each group.json are byte offsets into these logs; kept for a run that never reaches its result.
        save(folder / 'log-offsets.json', {'engine_log': offset, 'service_log': service_offset})
        try:
            state, load = owner.start(model=plan['model'], context_window=spec['context_window'])
            health = state.get('native_health') or {}
            save(folder / 'start.json', {'status': state.get('status'), 'load_seconds': load, 'native_health': health})
            args_for = lambda here: codex_overrides(plan, spec, here, owner.model_base + '/v1')
            gate = lambda: wait_for_free_commit(host.free_commit_gib, plan.get('min_free_commit_gib',
                                                                               MIN_FREE_COMMIT_GIB))
            began = time.monotonic()
            record.update(run_sampling(plan, data, spec, folder, args_for, owner.key,
                                       lambda: host.log_offset(plan['model']),
                                       lambda: wait_engine_idle(owner.model_base, owner.key), gate))
            record['session_seconds'] = time.monotonic() - began
        finally:
            stopped, requests, tokens = stop_and_capture_engine_log(owner, host.installation, plan['model'], offset,
                                                                    folder, host)
            record.update(stop=stopped.get('status'), tokens=tokens, **engine_rates(requests),
                          max_request_input=max((r['input'] for r in requests), default=None))
    log = (folder / 'engine-request-log.txt').read_text()
    service_log = host.log_bytes_since(None, service_offset).decode(errors='replace')  # the sampling trace lives here
    (folder / 'service-log-since-start.txt').write_text(service_log)
    windows = record.get('groups', [])  # sampling: every group attempt has its own engine log window
    for window, records in zip(windows, session_records(log, windows, offset)):
        window.update(tokens=sum_engine_tokens(records), **engine_rates(records))
    problems, effect = engine_effect(log, health, spec, condition, host.configuration(plan['model']), service_log)
    sessions = [r for r in record.get('groups', []) if r['valid']]
    problems += [p for s in sessions for p in s['effect_problems']]
    # The sandbox already blocks every path outside the workspace (sandbox_probe); flagged calls are judged by
    # outcome in the session inspection: only a call that actually saw outside content invalidates the instance.
    record['escapes_for_review'] = sum(s.get('escapes', 0) for s in sessions)
    record['effect'] = {'ok': not problems, 'problems': problems, 'engine': effect}
    save(folder / 'result.json', record)
    return record


def run_window_block(plan, data, name, slots, out):
    """The window instances of one condition back to back under one lease and one load (measurement rule 预热与连跑):
    start the model on the condition's tier -> verify it -> an unscored warm-up conversation (the opening and the
    first `warmup_batches` batches of the same workload, its own thread) -> each scored instance in a fresh thread ->
    stop the model and capture the engine log, split into per-instance windows.  Returns the instance records."""
    from tools.ops.measurement_host import MeasurementHost
    from tools.reviewer.arw_measure import stop_and_capture_engine_log
    from tools.metrics.strata_tokens import engine_rates, sum_engine_tokens, task_rates
    spec = plan['conditions'][name]
    folder = out / ('block-' + '-'.join(f'{s:02d}' for s in slots) + '-' + name)
    folder.mkdir(parents=True)
    host = MeasurementHost(plan['host'])
    save(folder / 'sources.json', host.verify_sources())
    owner = host.controller(folder / 'controller')
    records, block = [], {'condition': name, 'slots': slots, 'started': datetime.now().isoformat(timespec='seconds')}
    with owner:
        offset, service_offset = host.log_offset(plan['model']), host.log_offset()
        save(folder / 'log-offsets.json', {'engine_log': offset, 'service_log': service_offset})
        try:
            state, load = owner.start(model=plan['model'], context_window=spec['context_window'])
            health = state.get('native_health') or {}
            block.update(status=state.get('status'), load_seconds=load, native_health=health)
            save(folder / 'start.json', block)
            args_for = lambda here: codex_overrides(plan, spec, here, owner.model_base + '/v1')
            mark = lambda: host.log_offset(plan['model'])
            settle = lambda: wait_engine_idle(owner.model_base, owner.key)
            warm = data['sequence'][:1 + plan['warmup_batches']]
            block['warmup'], _ = run_conversation(plan, warm, folder / 'warmup', args_for, owner.key, settle,
                                                  plan['warmup_seconds_limit'], mark)
            cleanup_instance(folder / 'warmup')
            save(folder / 'start.json', block)
            for slot in slots:
                here = folder / f'{slot:02d}-{name}'
                record = {'slot': slot, 'condition': name, 'block': folder.name,
                          'started': datetime.now().isoformat(timespec='seconds')}
                record.update(run_window(plan, data, spec, here, args_for, owner.key, mark, settle))
                save(here / 'instance.json', record)  # on disk at once; tokens are added after the block
                records.append(record)
                cleanup_instance(here)
        finally:
            stopped, requests, tokens = stop_and_capture_engine_log(owner, host.installation, plan['model'], offset,
                                                                    folder, host)
            block.update(stop=stopped.get('status'), tokens=tokens,
                         max_request_input=max((r['input'] for r in requests), default=None))
            save(folder / 'start.json', block)
    log = (folder / 'engine-request-log.txt').read_text()
    service_log = host.log_bytes_since(None, service_offset).decode(errors='replace')
    (folder / 'service-log-since-start.txt').write_text(service_log)
    sessions = [block['warmup'], *records]
    for session, own in zip(sessions, session_records(log, sessions, offset)):
        session.update(tokens=sum_engine_tokens(own), requests=len(own), **engine_rates(own),
                       max_request_input=max((r['input'] for r in own), default=None))
        if session is not block['warmup']:
            session.update(over_verified_record(own, plan['verified_prompt_tokens'], session['scoring']))
        if session is not block['warmup']:
            session.update(task_rates(session['tokens'], session['work_seconds']),
                           reused_share=(session['tokens']['cached_input'] / (session['tokens']['cached_input']
                                         + session['tokens']['uncached_input'])) if session['tokens'] else None)
    engine_problems, effect = engine_effect(log, block.get('native_health') or {}, spec, None,
                                            host.configuration(plan['model']), service_log)
    block['engine_effect'] = {'problems': engine_problems, 'engine': effect}
    save(folder / 'start.json', block)
    for record in records:
        problems = engine_problems + record['effect_problems']
        record['effect'] = {'ok': not problems, 'problems': problems}
        save(folder / f'{record["slot"]:02d}-{name}' / 'instance.json', record)
    return records


def run_claude_window(plan, data, name, out, seconds_limit=None, mock_base=None):
    """Claude Code mechanism check of the window workload (design §2.4: pilot only, one per tier, not judged):
    the same conversation through tools.reviewer.claude_headless.run_conversation on this condition's tier, then
    compaction positions, ACK compliance, parsed answers and the model-dependent split, as for Codex."""
    from tools.reviewer import claude_headless
    spec = plan['conditions'][name]
    folder = out / f'claude-{name}'
    result = claude_headless.run_conversation(
        folder, [s['text'] for s in data['sequence']], 'qwen3.8-flash-next-' + plan['model'].lower(),
        plan['fixed_conditions']['effort'], plan['host'], spec['context_window'],
        seconds_limit or plan['instance_seconds_limit'], label=f'window-{name}', mock_base=mock_base)
    analysis = claude_headless.conversation_analysis(folder / 'stream.jsonl', turn_label,
                                                     window_bank.finder(data))
    replies = [r['text'] for r in analysis['replies'] if r['turn'].startswith('questions ')]
    points = [{'label': r['turn'], 'raw': r['raw'], 'compactions_after': r['compactions_after'],
               'context_tokens': r['context_tokens'], 'answered': r['result'] is not None,
               'in_text_ids': r.get('in_text_ids')}
              for r in analysis['replies'] if r['turn'].startswith('questions ')]
    scored = window_bank.score(data, replies, complete_timeline(points, len(data['checkpoint_positions'])))
    acks = ack_problems(analysis)
    record = {'condition': name, 'harness': 'claude-code', 'score': scored['score'], 'raw_score': scored['raw_score'],
              'scoring': scored, 'compactions': analysis['compactions'], 'tool_calls': analysis['tool_calls'],
              'ack_problems': len(acks), 'ack_examples': acks[:5], 'work_seconds': result.get('work_seconds'),
              'summary_retention': retention(data, analysis['compactions']),
              'turns_done': len(result.get('turns', [])), 'turns_planned': len(data['sequence']),
              'hard_interrupt': result.get('hard_interrupt'), 'engine_tokens': result.get('engine_tokens'),
              'effect_problems': window_effect(spec, analysis)}
    log = folder / 'engine-request-log.txt'
    if log.exists():
        record.update(over_verified_requests(log.read_text(), plan.get('verified_prompt_tokens')))
    save(folder / 'window-result.json', record)
    return record


def request_kind(output_tokens):
    """Rough kind of a window-workload request by its output: an ACK (a few tokens), a checkpoint's answers
    (hundreds) or a compaction summary (thousands)."""
    return 'ack' if output_tokens < 200 else 'questions' if output_tokens < 2000 else 'compaction'


def retention(data, compactions):
    """summary_retention for every compaction with a summary.  A Claude Code compaction that ran before a turn's
    request (`during_turn`) summarised the turns before it; a Codex one, the turn it followed."""
    labels = [x['label'] for x in data['sequence']]
    rows = []
    for c in compactions:
        after = c['after_user_turn']
        if c.get('during_turn') and after in labels:
            after = labels[labels.index(after) - 1]
        if after in labels and c.get('summary'):
            row = window_bank.summary_retention(data, after, c['summary'])
            row.pop('rows')
            rows.append(row)
    return rows


def over_verified_record(records, verified, scoring):
    """Requests above the verified prompt length, recorded only (design §3, decision A 2026-10-24): the largest
    input, how many, of which kind, and which scored outputs depend on them: compaction summaries made from an
    over-length request, and answers given at >=150K."""
    over = [{'input': r['input'], 'output': r['output'], 'kind': request_kind(r['output'])}
            for r in records if r['input'] > verified]
    return {'over_verified': over, 'over_verified_count': len(over),
            'over_verified_summaries': sum(r['kind'] == 'compaction' for r in over),
            'answers_at_150k_or_more': sum(1 for r in scoring.get('rows', []) if r.get('bin') == '>=150K')}


def over_verified_requests(log, verified):
    """Largest request input of an engine log and the requests above the verified prompt length (recorded only;
    the Claude Code mechanism check never fails on it)."""
    from tools.metrics.strata_tokens import parse_engine_log
    requests = parse_engine_log(log)
    over = [{'input': r['input'], 'output': r['output'], 'kind': request_kind(r['output'])}
            for r in requests if verified and r['input'] > verified]
    return {'max_request_input': max((r['input'] for r in requests), default=None), 'requests': len(requests),
            'over_verified': over}


def cleanup_instance(here):
    """Measurement rule 存放: drop the empty recall workspace and the scratch CODEX_HOME material that is not the
    session record (the rollout and session analysis stay)."""
    import shutil
    shutil.rmtree(here / 'workspace', ignore_errors=True)
    for child in (here / 'codex-home').iterdir() if (here / 'codex-home').exists() else []:
        if child.name != 'sessions':
            shutil.rmtree(child, ignore_errors=True) if child.is_dir() else child.unlink(missing_ok=True)


def parse_groups(text):
    """'7-10' or '2,5,7-9' -> sorted group numbers."""
    numbers = set()
    for part in text.split(','):
        first, _, last = part.partition('-')
        numbers.update(range(int(first), int(last or first) + 1))
    return sorted(numbers)


def run(plan_path, out, limit=None, only_groups=None):
    """Run the scheduled instances not yet done; stop at the end of the round so the staged decision can be taken.
    `only_groups` (sampling, recovery after an interrupted instance): run just those groups, into a fresh `out`;
    the result covers those groups only and is merged with the interrupted instance's finished groups by hand."""
    plan, data, conditions = load_plan(plan_path)
    if only_groups:
        if plan['workload'] != 'sampling':
            raise ValueError('--groups applies to the sampling workload only')
        plan = {**plan, 'only_groups': only_groups}
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
    if plan['workload'] == 'window':
        return run_window_blocks(plan, data, out, progress, progress_path, limit)
    for slot in range(len(done), len(order))[:limit]:
        name = order[slot]
        record = run_instance(plan, data, conditions, name, out / f'{slot + 1:02d}-{name}')
        done.append({'slot': slot + 1, 'condition': name, 'score': record.get('score'),
                     'effect_ok': record['effect']['ok'], 'folder': f'{slot + 1:02d}-{name}'})
        save(progress_path, progress)
        if not record['effect']['ok']:
            raise RuntimeError(f'Instance {slot + 1} ({name}) failed its effect check: {record["effect"]["problems"]}')
    return progress


def run_window_blocks(plan, data, out, progress, progress_path, limit=None):
    """Pending window slots in blocks of consecutive same-condition slots (one lease and load per block)."""
    order, done = progress['order'], progress['instances']
    pending = list(range(len(done), len(order)))[:limit]
    while pending:
        name = order[pending[0]]
        slots = []
        while pending and order[pending[0]] == name:
            slots.append(pending.pop(0) + 1)
        records = run_window_block(plan, data, name, slots, out)
        for record in records:
            done.append({'slot': record['slot'], 'condition': name, 'score': record['score'],
                         'raw_score': record['raw_score'], 'work_seconds': record['work_seconds'],
                         'effect_ok': record['effect']['ok'],
                         'folder': f'{record["block"]}/{record["slot"]:02d}-{name}'})
        save(progress_path, progress)
        failed = [r for r in records if not r['effect']['ok']]
        if failed:
            raise RuntimeError(f'Instances {[r["slot"] for r in failed]} failed their effect check: '
                               f'{[r["effect"]["problems"] for r in failed]}')
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
        progress['order'] += next_round(result['sampled_next'], len(progress['decisions']), list(plan['conditions']),
                                        plan['workload'] == 'window')
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
            'second_round_if_all_open': next_round(list(plan['conditions']), 1, list(plan['conditions']),
                                                   plan['workload'] == 'window'),
            'conditions': {n: {'context_window': plan['conditions'][n]['context_window'],
                               'deployment_condition_sha256': conditions[n][1]} for n in plan['conditions']}}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)
    for command in ('check', 'run', 'decide', 'claude-window'):
        p = sub.add_parser(command)
        p.add_argument('--plan', type=Path, required=True)
        if command != 'check':
            p.add_argument('--out', type=Path, required=True)
        if command == 'claude-window':
            p.add_argument('--condition', required=True)
        if command == 'run':
            p.add_argument('--limit', type=int)
            p.add_argument('--groups', type=parse_groups, help="sampling recovery: run only these groups, e.g. 7-10")
    args = parser.parse_args()
    if args.command == 'check':
        result = check(args.plan)
    elif args.command == 'claude-window':
        plan, data, _ = load_plan(args.plan)
        if (plan.get('authorization') or {}).get('approved') is not True:
            raise ValueError('This plan is not approved for model runs')
        from tools.reviewer.claude_headless import pinned_binary
        pinned_binary()
        result = run_claude_window(plan, data, args.condition, Path(args.out).resolve())
        result = {k: v for k, v in result.items() if k != 'scoring'} | {
            'C1': result['scoring'].get('C1'), 'C2': result['scoring'].get('C2')}
    elif args.command == 'run':
        result = run(args.plan, args.out, args.limit, args.groups)
    else:
        result = decide(args.out, args.plan)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
