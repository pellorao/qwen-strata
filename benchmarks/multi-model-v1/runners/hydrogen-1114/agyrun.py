"""One Hydrogen (Antigravity `agy -p`) turn in a work directory, stream-json, scoped permissions as ~/.claude/bin/agy-run.py.

Shared by run_one.py (scenario instances) and p4probe.py (T probes). The stream is kept; `summarize` turns it into the
facts the plan (§3 per-instance checks) needs: per-response usage, tool names, web/subagent tools, final status.
"""
import json
import re
import os
import signal
import subprocess
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))   # the repository root: tools.guard_runs (a runner started by path has only its own directory)
from tools import guard_runs  # noqa: E402

# --- tunables ---
AGY = os.path.expanduser('~/.local/bin/agy')
LIMITS = Path(os.path.expanduser('~/.claude/statusline/limits/antigravity-gemini.json'))
LIMITS_PY = os.path.expanduser('~/.claude/statusline/limits.py')
ALLOW_CMDS = ['ls', 'cat', 'echo', 'wc', 'head', 'tail', 'grep', 'find', 'sort', 'diff', 'nl', 'sed', 'awk', 'tr', 'cut',
              'uniq', 'stat', 'tree', 'git status', 'git diff', 'git log', 'git show', 'git cat-file', 'git ls-tree',
              'git ls-files', 'git grep', 'git rev-parse', 'git blame', 'git rev-list', 'git diff-tree',
              'git merge-base', 'git branch', 'git tag', 'git show-ref', 'git for-each-ref', 'node', 'python3', 'jq', 'date',
              'pwd', 'basename', 'dirname', 'realpath', 'file', 'du', 'xargs', 'printf', 'test', 'comm', 'paste', 'column',
              'od', 'md5sum', 'sha256sum', 'which', 'rg', 'expand', 'fold', 'rev', 'tac', 'seq']
DENY = ['command(sudo)', 'command(rm -rf)', 'command(curl)', 'command(wget)', 'command(git push)', 'command(git reset)',
        'command(git checkout)', 'command(git stash)']
# Tools plan §3 forbids (search, web, browser, sub-agents, anything leaving the repository); agy cannot disable them,
# so a call makes the instance invalid.
FORBIDDEN = ('search_web', 'read_url_content', 'open_browser_url', 'invoke_subagent', 'define_subagent', 'manage_subagents',
             'browser_subagent', 'run_workflow', 'generate_image', 'call_mcp_tool', 'schedule', 'manage_inbox', 'send_message')
HOME = os.path.expanduser('~')
GEMINI = f'{HOME}/.gemini/antigravity-cli'
STARTUP = 7  # seconds agy needs to start and stop around its --print-timeout (measured 6.5-7); taken off every segment's budget
START_CAP = (60, 3600)  # agy turn starts per hour (a continuation or a reminder is a start too); a loop restarting turns stops here (usage_guard rate net)
GRACE = 90  # seconds past --print-timeout before the process group is killed
# --- end tunables ---


def remaining():
    """Gemini group remaining percent per window, from the status-line limits file (refreshed after every run)."""
    d = json.loads(LIMITS.read_text())
    return {w['name']: round(100 - w['used_pct'], 2) for w in d['windows']}


def refresh_limits():
    subprocess.run(['python3', '-I', LIMITS_PY, '--refresh', 'agy'], timeout=120, stdin=subprocess.DEVNULL,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)


def settings(work):
    allow = [f'read_file({work})', f'write_file({work})'] + [f'command({c})' for c in ALLOW_CMDS]
    return {'agentMode': 'auto', 'permissions': {'allow': allow, 'deny': DENY + [f'write_file({work}/.git)']}}


def prepare_state(state):
    """A per-instance private copy of agy's small state (token file is bound live, not copied: a refresh must reach the real one)."""
    state.mkdir(parents=True, exist_ok=True)
    for f in ('installation_id', 'jetski_state.pbtxt', 'agentapi'):
        if not (state / f).exists():
            shutil.copy(f'{GEMINI}/bin/agentapi' if f == 'agentapi' else f'{GEMINI}/{f}', state / f)
    if not (state / 'config').exists():
        shutil.copytree(f'{HOME}/.gemini/config', state / 'config')


def bwrap(state, work):
    g = GEMINI
    return ['bwrap', '--ro-bind', '/usr', '/usr', '--symlink', 'usr/bin', '/bin', '--symlink', 'usr/lib', '/lib',
            '--symlink', 'usr/lib64', '/lib64', '--symlink', 'usr/sbin', '/sbin', '--ro-bind', '/etc', '/etc',
            '--ro-bind', '/mnt/wsl', '/mnt/wsl', '--proc', '/proc', '--dev', '/dev', '--tmpfs', '/tmp', '--tmpfs', HOME,
            '--ro-bind', AGY, AGY, '--bind', str(state), g, '--ro-bind', f'{g}/bin', f'{g}/bin',
            '--bind', str(state / 'agentapi'), f'{g}/bin/agentapi', '--ro-bind', f'{g}/builtin', f'{g}/builtin',
            '--bind', f'{g}/antigravity-oauth-token', f'{g}/antigravity-oauth-token',
            '--bind', str(state / 'config'), f'{HOME}/.gemini/config', '--bind', str(work), str(work),
            '--chdir', str(work), '--unshare-pid', '--die-with-parent', '--setenv', 'HOME', HOME]


def turn(out, work, prompt, model, effort, timeout_seconds, conversation=None, name='stream', state_dir=None):
    """Run one agy turn with `prompt` in `work`; returns the facts. Files: out/stream.jsonl, stream.err, prompt-sent.md."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    (out / ('prompt-sent.md' if name == 'stream' else f'prompt-sent-{name}.md')).write_text(prompt)
    state = Path(state_dir or out / 'agy-state')
    prepare_state(state)
    (state / 'settings.json').write_text(json.dumps(settings(work)))
    # agy's own --sandbox cannot confine reads (tested: cat of files outside the work dir worked) and fails nested in
    # bwrap, so the confinement is bwrap: the user's home, /tmp, /mnt are not visible; the work dir is the only writable
    # project path; agy's state dir is a per-instance private copy (no other run's conversations, no cross-run memory).
    inner = [AGY, '-p', '', '--input-format', 'stream-json', '--model', model, '--effort', effort, '--output-format',
             'stream-json', '--print-timeout', f'{int(timeout_seconds)}s', '--settings', f'{GEMINI}/settings.json',
             '--add-dir', str(work), '--disable-slash-commands']
    if conversation:
        inner += ['--conversation', conversation]
    cmd = bwrap(state, work) + inner
    message = json.dumps({'event': 'user', 'message': {'content': prompt}}) + '\n'
    started = time.time()
    with (out / f'{name}.jsonl').open('wb') as so, (out / f'{name}.err').open('wb') as se:
        guard_runs.rate('qwen-strata:hydrogen-agy', *START_CAP)
        p = subprocess.Popen(cmd, cwd=work, stdin=subprocess.PIPE, stdout=so, stderr=se, start_new_session=True)
        killed = False
        with guard_runs.agy('qwen-strata:hydrogen-agy', model, effort, pid=p.pid):   # the status page's run list; removed when the turn ends
            try:
                p.stdin.write(message.encode())
                p.stdin.close()
                code = p.wait(timeout=timeout_seconds + GRACE)
            except subprocess.TimeoutExpired:
                os.killpg(p.pid, signal.SIGKILL)
                p.wait()
                code, killed = p.returncode, True
    ended = time.time()
    try:
        refresh_limits()
    except Exception:
        pass
    return {'exit': code, 'killed_by_driver': killed, 'started_at': started, 'ended_at': ended,
            'wall_seconds': ended - started, **summarize(out / f'{name}.jsonl')}


def summarize(stream):
    init, result, responses, tools, kinds = None, None, [], [], {}
    seen = set()
    for line in Path(stream).read_text(errors='replace').splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            kinds['non-json'] = kinds.get('non-json', 0) + 1
            continue
        kind = e.get('event')
        kinds[kind] = kinds.get(kind, 0) + 1
        if kind == 'init':
            init = e['init']
        elif kind == 'result':
            result = e['result']
        elif kind == 'step_update':
            s = e['step_update']
            if s.get('step_type') == 'agent_response' and s.get('state') == 'DONE' and s.get('usage'):
                responses.append({'step': s['step_index'], 'seconds': s.get('duration_seconds'), 'usage': s['usage']})
            if s.get('step_type') == 'tool' and s.get('tool_name') and s['step_index'] not in seen:
                seen.add(s['step_index'])
                tools.append(s['tool_name'])
    usage = {k: sum(r['usage'].get(k) or 0 for r in responses)
             for k in ('input_tokens', 'cache_read_tokens', 'output_tokens', 'thinking_tokens')}
    res = result or {}
    return {'model_echo': (init or {}).get('model'), 'permission_mode': (init or {}).get('permission_mode'),
            'conversation_id': res.get('conversation_id'), 'finished_reason': res.get('finished_reason'), 'status': res.get('status'), 'error': res.get('error'), 'denied_actions': res.get('denied_actions'),
            'result_usage': res.get('usage'), 'result_seconds': res.get('duration_seconds'), 'num_turns': res.get('num_turns'),
            'response_text': res.get('response'), 'responses': responses, 'usage_sum': usage, 'tools': tools,
            'forbidden_tools': [t for t in tools if t in FORBIDDEN or t.startswith('browser_')], 'event_kinds': kinds,
            'result_event': result is not None, 'result_keys': sorted(res)}


def timed_out(res):
    """--print-timeout ends a turn with status SUCCESS, an empty response and finished_reason print_timeout (tested); an
    ERROR / DEADLINE_EXCEEDED form was seen earlier, so both count."""
    text = json.dumps(res.get('error') or '') + (res.get('response_text') or '')
    return res.get('finished_reason') == 'print_timeout' or (
        res.get('status') == 'ERROR' and bool(re.search(r'print_timeout|DEADLINE_EXCEEDED', text, re.I)))


def merge(parts):
    """One result in turn()'s shape for a run of segments: usage, tools, responses and denials summed over all of them."""
    first, last = parts[0], parts[-1]
    merged = dict(last)
    merged['model_echo'] = first['model_echo']
    merged['responses'] = [r for p in parts for r in p['responses']]
    merged['tools'] = [t for p in parts for t in p['tools']]
    merged['forbidden_tools'] = [t for p in parts for t in p['forbidden_tools']]
    merged['denied_actions'] = [d for p in parts for d in (p['denied_actions'] or [])] or None
    merged['usage_sum'] = {k: sum(p['usage_sum'][k] for p in parts) for k in first['usage_sum']}
    merged['killed_by_driver'] = any(p['killed_by_driver'] for p in parts)
    merged['started_at'], merged['wall_seconds'] = first['started_at'], last['ended_at'] - first['started_at']
    merged['num_turns'] = sum(p['num_turns'] or 0 for p in parts)
    return merged


def execute(out, work, prompt, report_path, model, effort, limit, clock=time.time):
    """ARW's whole-instance behaviour on Hydrogen, as claude_headless.execute_continued does on the Claude arm: segment 0
    is the handoff; a turn that ends normally without full delivery (final message exactly {"status":"ready"} and a
    non-empty report) gets ARW's continuation in the same conversation (`--conversation`), with the pause after the 10th
    counted early exit and every 5th after; the reminder arrives at reminder_time(limit) by ending the running turn
    (`--print-timeout`) and sending review_deadlines.reminder_message as the next turn; the hard stop is `limit` seconds
    from the first segment's start for the whole instance. Returns (merged result, continuation record)."""
    from tools.reviewer import claude_headless as ch
    from tools.reviewer.review_deadlines import reminder_message
    out = Path(out)
    started = clock()
    after, hard_at = ch.reminder_time(limit), started + limit
    reminder_sent, conv, message, kind = False, None, prompt, 'handoff'
    parts, segments, early, next_pause, pauses, continues, stop = [], [], 0, ch.EARLY_EXIT_PAUSE_AT, [], 0, None
    while stop is None:
        now = clock()
        if hard_at - now <= 3:
            stop = 'deadline_between_segments'
            break
        reminder_pending = not reminder_sent and started + after > now
        budget = ((started + after - now) if reminder_pending else (hard_at - now)) - STARTUP
        k = len(segments)
        res = turn(out, work, message, model, effort, max(1, int(budget)), conversation=conv,
                   name='stream' if k == 0 else f'stream-{k}', state_dir=out / 'agy-state')
        parts.append(res)
        conv = conv or res['conversation_id'] or session_of(out / ('stream.jsonl' if k == 0 else f'stream-{k}.jsonl'))
        seg = {'index': k, 'message': kind, 'status': res['status'], 'wall_seconds': res['wall_seconds'], 'budget': int(budget)}
        segments.append(seg)
        if timed_out(res):
            if reminder_pending:
                reminder_sent = True
                left = max(0, int(hard_at - clock()))
                message, kind = reminder_message(after, limit, left, hard_at), 'reminder'
                seg['ended_by'] = 'reminder_due'
                if not conv:
                    stop = 'no_conversation'
                continue
            stop = 'hard_limit'
            seg['ended_by'] = 'hard_limit'
            break
        if res['status'] != 'SUCCESS' or res['killed_by_driver']:
            stop = 'abnormal_end'
            break
        check = ch.early_exit(res['response_text'], Path(work) / report_path)
        seg.update(report=check['report'], delivered=check['delivered'])
        if check['delivered']:
            stop = 'delivered'
        elif not check['continuable']:
            stop = 'not_continuable'
        elif not conv:
            stop = 'no_conversation'
        if stop:
            break
        message, kind = check['instruction'], 'arw_continuation'
        if check['counted']:
            early += 1
            seg['early_exit_count'] = early
            if early >= next_pause:
                pauses.append({'segment': k, 'early_exit_count': early, 'text': ch.ARW_PAUSE_TEXT.format(count=early),
                               'continued': {'message': ch.CONTINUE_MESSAGE}})
                next_pause = early + ch.EARLY_EXIT_PAUSE_STEP
                message, kind = ch.CONTINUE_MESSAGE, 'user_continue'
    return merge(parts), {'stop': stop, 'delivered': stop == 'delivered', 'early_exit_count': early, 'arw_pause_events': pauses,
                          'segments': segments, 'conversation_id': conv, 'reminder_after': after, 'reminder_sent': reminder_sent,
                          'hard_limit': limit}


def session_of(stream):
    for line in Path(stream).read_text(errors='replace').splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get('conversation_id'):
            return e['conversation_id']
    return None
