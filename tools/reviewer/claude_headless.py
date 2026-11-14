"""Headless Claude Code runs for references, blind adjudication and the Claude Code cross arm.

One runner, one parameter set, three backends (review 2026-10-19, D3/H3): `anthropic` runs the named Anthropic model
with the real configuration directory; `strata` takes the frontend lease, starts the served model with the
installation defaults and points the same Claude Code command at the frontend; `deepseek` points the same command at
DeepSeek's Anthropic-format endpoint with a fresh configuration directory and the key from DEEPSEEK_API_KEY
(multi-model benchmark, user 2026-10-19). The DeepSeek model is always named explicitly in every model variable,
because the endpoint maps Claude model names such as claude-opus-* to another model. The cross arm never goes through
qwen-approve or qwen-agent's own settings: only qwen-agent's model environment is reused.

Isolation (measurement rule "Claude Code 测试隔离"):
- a minimal environment instead of the caller's (the same effect as `env -i`): PATH, HOME, LANG, TERM and the backend's
  variables; the Strata arm also gets a fresh CLAUDE_CONFIG_DIR;
- `--setting-sources ""`, `--restricted` (file tools confined to the working directory), `--strict-mcp-config`,
  `--disable-slash-commands`, `--permission-mode dontAsk`, `--permission-prompts none`, `--no-session-persistence`;
- the working directory lives under WORK_BASE, outside the home directory, so no ancestor CLAUDE.md applies;
- the Bash sandbox reads only the working directory, writes only the granted paths and has no network; a new file at the
  top of the working directory stays writable (the sandbox always grants the working directory, see settings());
- web tools are off twice: `--tools` lists none and `--disallowedTools WebSearch,WebFetch` denies them (benchmark
  search rule, user 2026-10-19); tools.safety.claude_gate checks that no request offers a search tool;
- CLAUDE_CODE_SUBPROCESS_ENV_SCRUB=1 keeps the backend key out of command environments: without it the mock gate saw
  ANTHROPIC_AUTH_TOKEN in the shell (2026-10-19).
`--safe-mode` is not used: it also disables the PreCompact hook that carries the project compact prompt;
tools.safety.claude_gate checks that the real configuration's CLAUDE.md, hooks and skills still stay out.

Time limit as ARW (tools.reviewer.review_deadlines), delivered as high-priority messages (user 2026-10-20, as Codex):
Claude Code reads stream-json input (`--input-format stream-json --replay-user-messages`) and stdin stays open while a
turn runs. At the reminder time the harness writes the reminder as a user message with `priority: "now"` (no origin),
which aborts the generation in flight and starts the next request with it; when a tool is executing it first sends
`control_request interrupt` (the tool is cancelled), then the message (cc-priority-1022: 0.02-0.08 s during generation,
0.5 s during a long Bash, against the tool's remaining time without the interrupt). At the hard limit it sends the
interrupt and closes stdin, and stops the process group only after a grace period. Both are recorded in
`deadline-handoff.json` in ReviewDeadline's shape (attempted_at, status, receipt: the replayed message uuid or the
control response). The turn they cut short ends in an aborted result (`aborted_streaming` / `aborted_tools`, often
`error_during_execution`); tools.reviewer.reminder_interrupt.stream_exempt makes it ours, not an API fault.
At the end `~/.claude/statusline/estimate.sh --add-stream <stream> <label> --effort <level>` records the run.

Early-exit continuation as ARW's Reviewer runtime (`report=`, the scenario runs; user 2026-10-20, Codex parity): a
normally ended turn without full delivery (final message exactly {"status":"ready"} and a non-empty readable bound
report) gets ARW's own continuation instruction in the same session (`--resume <session id>`, the same argv and
settings, so session persistence stays on for these runs); at ARW's 10th early exit and every 5 after it the runtime
pauses and the harness answers 继续 as the user (one `arw_pause_events` entry each). The hard limit is the instance's
wall clock from the first segment's start. Each segment keeps its own stream (stream.jsonl, stream-1.jsonl, ...).

    python3 -m tools.reviewer.claude_headless --out .tmp/<work>/<run> --prompt prompt.md --backend anthropic \\
        --model opus --effort high --label <label> --copy <source>:<name> --write <name>/<report dir>
"""
import argparse
import contextlib
import fnmatch
import hashlib
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
import json
import os
import stat
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid

from tools.reviewer.review_deadlines import LIMITS, REMINDER, reminder_message, save as save_atomic
from tools.reviewer import reminder_interrupt
from tools.reviewer.harness_pins import CLAUDE as CLAUDE_COPY, CLAUDE_SHA256, CLAUDE_VERSION
from tools.reviewer.wsl_client import ROOT, save
from tools import guard_runs

sys.path.append(str(ROOT / 'src'))
from startup_instructions import startup_prompt_bytes

# Tunables
WORK_BASE = Path('/var/tmp/qwen-claude')  # isolated working directories, outside the home directory
TOOLS = 'Read,Write,Edit,Glob,Grep,Bash'  # no web tools: search stays a separate decision (D5)
DISALLOWED = 'WebSearch,WebFetch'  # denied as well, whatever --tools lists (benchmark: search off, user 2026-10-19)
REMINDER_AFTER, HARD_LIMIT = LIMITS['initial']  # 3300 s, 3600 s
ESTIMATE = Path.home() / '.claude/statusline/estimate.sh'
# The benchmark copy named in tools.reviewer.harness_pins; the CLIs refuse any other SHA or version (pinned_binary).
# Version notes below name the version an observation was made on. On 2.1.309 (2026-10-24) the mock gates
# (tools.safety.claude_gate, all backends, --pair) passed with the same deny lists and per-run TMPDIR, stream-json
# priority "now" and control_request interrupt behaved as on 2.1.303 (zero-model and Strata), and total_cost_usd still
# accumulates across --resume; the only new request content was the tool-search placeholder (ENABLE_TOOL_SEARCH below).
CLAUDE = str(CLAUDE_COPY)
AGENT = ROOT / 'scripts/wsl/qwen-agent'
# Named directories, not top-level ones: Claude Code 2.1.303 left /home readable to sandboxed commands with denyRead
# ["/home"], while the home directory itself (/home/pello on rtx3080ti) was denied (tools.safety.claude_gate, 2026-10-19). The working directory is re-opened
# by allowRead inside WORK_BASE.
# Claude Code's shared temporary directory (its default sandbox TMPDIR, also holding other sessions' task outputs and
# scratchpads): every run gets its own TMPDIR instead (run_tmp), and sandboxed commands can neither read nor write the
# shared one (2026-10-19: concurrent instances wrote and could read same-named drafts there).
SHARED_TMP = [f'/tmp/claude-{os.getuid()}']
# All of /tmp is shared between runs and sessions: sandboxed commands could create /tmp/<name> (mock 2026-10-19), so
# /tmp is denied for writes. A top-level denyRead of /tmp is not enforced by Claude Code 2.1.303 (as with /home), so
# shared_tmp_entries() denies reads of every entry present when the run starts.
SHARED_DENY = ['/tmp', *SHARED_TMP]
# The other world-writable directories: the sandbox let commands create files in /var/tmp and /run/lock that landed on
# the host, and read /var/tmp files (mock 2026-10-19). A denyWrite on /var/tmp would cover the runs' own directories
# beneath it (bwrap then fails); a denyRead of each directory works instead: the sandbox mounts an empty private
# directory there (each run re-allowed its own directories under WORK_BASE), so writes stay inside the sandbox.
WORLD_WRITABLE = [d for d in ('/var/tmp', '/run/lock', '/run/screen', '/dev/shm', '/dev/mqueue', '/var/crash', '/mnt/wsl',
                              '/mnt/wslg') if os.path.isdir(d)]
SETTINGS_ARGUMENT_LIMIT = 120000
# ARW early-exit pause points (frozen ARW 760007c: lib/arw-common/config.mjs earlyExitNotificationThreshold 10,
# lib/background-agent/manager.mjs noteEarlyExit nextEarlyExitNotificationCount = count + 5).
EARLY_EXIT_PAUSE_AT, EARLY_EXIT_PAUSE_STEP = 10, 5
CONTINUE_MESSAGE = '继续'  # the user's answer at a pause, as tools.reviewer.arw_measure.ARW_CONTINUE_MESSAGE
INTERRUPT_WAIT = 10  # seconds to wait for the interrupted turn's result before the reminder message is written
HARD_GRACE = 20  # seconds after the hard-limit interrupt before the process group is stopped
POLL = 0.1


# Each denied path costs bwrap about three arguments and bwrap takes at most 9000: with 2136 /tmp entries every Bash
# call of Claude Code 2.1.303 failed at sandbox setup (2026-10-20, test leftovers in /tmp). Refuse well before that.
SHARED_TMP_LIMIT = 1500
SHARED_TMP_ROOT = Path('/tmp')   # the directory whose entries are listed; tests point it at a temporary one


def shared_tmp_entries():
    """Entries at the top of /tmp (SHARED_TMP_ROOT) when a run starts, except Unix sockets (connecting to them is blocked anyway)."""
    entries = sorted(str(p) for p in SHARED_TMP_ROOT.iterdir() if not p.is_socket() and str(p) not in SHARED_DENY)
    if len(entries) > SHARED_TMP_LIMIT:
        raise RuntimeError(f'/tmp holds {len(entries)} top-level entries, over {SHARED_TMP_LIMIT}: each is denied '
                           'separately and the sandbox would exceed the bwrap argument limit; clear stale /tmp entries')
    return entries
DENY_READ = [str(Path.home()), '/root', '/mnt/c', '/mnt/wsl', '/mnt/wslg', str(WORK_BASE), '/etc/claude-code', *SHARED_DENY,
             *(d for d in WORLD_WRITABLE if d not in ('/mnt/wsl', '/mnt/wslg'))]
# Inputs that never belong in a working directory: credentials, private state and answer material.
FORBIDDEN = ['project.private.toml', 'installation.private.toml', '.credentials.json', '.claude.json', '.state',
             'key*.json', 'expected*.json', 'judgment']
STARTUP = ROOT / 'config/prompts/startup-instructions.txt'
COMPACT = ROOT / 'config/prompts/compact-prompt.txt'
BACKENDS = ('anthropic', 'strata', 'deepseek')
DEEPSEEK_BASE = 'https://api.deepseek.com/anthropic'
DEEPSEEK_KEY = 'DEEPSEEK_API_KEY'  # the name the user set in the WSL login environment (2026-10-19)
DEEPSEEK_MODEL = re.compile(r'deepseek-[a-z0-9][a-z0-9.-]*')
# Every variable that names a model for some request kind; all of them name the DeepSeek model.
DEEPSEEK_MODEL_VARIABLES = ('ANTHROPIC_MODEL', 'ANTHROPIC_SMALL_FAST_MODEL', 'ANTHROPIC_DEFAULT_OPUS_MODEL',
                            'ANTHROPIC_DEFAULT_SONNET_MODEL', 'ANTHROPIC_DEFAULT_HAIKU_MODEL', 'CLAUDE_CODE_SUBAGENT_MODEL')
# Strata arm: qwen-agent's model variables whose values go into the binding (never the lease key or the frontend URL).
MODEL_ENVIRONMENT_RECORDED = ('ANTHROPIC_MODEL', 'CLAUDE_CODE_MAX_CONTEXT_TOKENS', 'CLAUDE_CODE_MAX_OUTPUT_TOKENS',
                              'CLAUDE_CODE_EFFORT_LEVEL', 'CLAUDE_CODE_BLOCKING_LIMIT_OVERRIDE')


def workspace(run_id, base=WORK_BASE):
    """A fresh working directory outside the home directory; its parent holds only this run."""
    root = Path(base) / run_id
    work = root / 'work'
    if str(work.resolve()).startswith(('/home/', str(Path.home().resolve()) + '/')):
        raise ValueError('The isolated working directory must be outside /home and the home directory')
    work.mkdir(parents=True, exist_ok=False)
    return work


def copy_inputs(work, copies, forbidden=FORBIDDEN):
    """Copy each source into the working directory (dereferencing links), then refuse forbidden names."""
    for source, name in copies:
        source, target = Path(source), work / name
        if target.resolve().parent != work.resolve() and work.resolve() not in target.resolve().parents:
            raise ValueError('Input target leaves the working directory: ' + name)
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, target, symlinks=False)
        else:
            shutil.copyfile(source, target)
    found = sorted(str(p.relative_to(work)) for p in work.rglob('*')
                   if any(fnmatch.fnmatch(p.name, pattern) for pattern in forbidden))
    if found:
        raise ValueError('Forbidden inputs in the working directory: ' + ', '.join(found))


def file_hashes(work):
    return {str(p.relative_to(work)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(work.rglob('*')) if p.is_file() and not p.is_symlink()}


def run_tmp(work):
    """The run's own temporary directory, `<run root>/tmp` (0700) beside the working directory, given to Claude Code as
    TMPDIR and CLAUDE_CODE_TMPDIR. Claude Code 2.1.303 derives the sandboxed commands' TMPDIR from TMPDIR
    (`<tmp>/claude-<uid>`; CLAUDE_CODE_TMPDIR alone left it at the shared /tmp/claude-<uid>, mock 2026-10-19), and
    keeps its own temporary files under CLAUDE_CODE_TMPDIR; settings() grants the directory to this run only."""
    tmp = Path(work).resolve().parent / 'tmp'
    tmp.mkdir(mode=0o700, exist_ok=True)
    st = tmp.lstat()
    if not stat.S_ISDIR(st.st_mode) or st.st_mode & 0o777 != 0o700 or st.st_uid != os.getuid():
        raise ValueError(f'{tmp} is not this user\'s own 0700 directory')
    return tmp


def write_targets(work, writes):
    targets = [(work / w).resolve() for w in writes]
    for target in targets:
        if work.resolve() not in target.parents:
            raise ValueError('Write grants stay inside the working directory')
    return targets


def reminder_time(limit):
    """ARW's lead before the hard limit (300 s of 3600); half the limit when the limit is shorter than two leads."""
    lead = HARD_LIMIT - REMINDER_AFTER
    return limit - lead if limit >= 2 * lead else limit / 2


def session_hooks(compact=True):
    """The project compact prompt appended to Claude Code's own summary instructions, never replacing them (as
    qwen-agent does). compact=False leaves Claude Code's own compaction unchanged (multi-model benchmark: the project
    prompts go to Strata only, user 2026-10-19). The time reminder is no hook any more: Deadline delivers it."""
    return {'PreCompact': [{'hooks': [{'type': 'command', 'command': f'cat {COMPACT}'}]}]} if compact else {}


class Deadline:
    """One run's reminder and hard stop, in review_deadlines.ReviewDeadline's record shape (`out/deadline-handoff.json`).

    `reminder_after` None: no reminder (hard stop only). `scenario` True: the Codex API path's text
    (review_deadlines.reminder_message, wall-clock basis: the lead rewritten when it is not 5 minutes and the remaining
    seconds when it is sent; parity review F10, 2026-10-20); otherwise the fixed text. Times count from the first
    segment's start (begin()), so continuation segments keep the instance's clock."""

    def __init__(self, out, limit, reminder_after=None, scenario=False, run_id=None):
        self.path = Path(out) / 'deadline-handoff.json'
        self.limit, self.after, self.scenario = limit, reminder_after, scenario
        self.value = {'runId': run_id or Path(out).name, 'messageId': 'handoff', 'phase': 'initial', 'started_at': None,
                      'start_source': 'claude_headless first segment start', 'reminder_at': None,
                      'hard_deadline_at': None, 'reminder': None, 'interrupt': None,
                      'time_basis': 'wall clock from the first segment start', 'reminder_after_seconds': reminder_after,
                      'interrupt_after_seconds': limit, 'delivery': 'claude stream-json priority now'}

    def begin(self, started):
        if self.value['started_at'] is None:
            self.value.update(started_at=started, hard_deadline_at=started + self.limit,
                              reminder_at=None if self.after is None else started + self.after)
            self.save()

    def save(self):
        save_atomic(self.path, self.value)

    def reminder_due(self, now):
        return self.after is not None and self.value['reminder'] is None and now >= self.value['reminder_at']

    def hard_due(self, now):
        return now >= self.value['hard_deadline_at']

    def text(self, now):
        if not self.scenario:
            return REMINDER
        hard_at = self.value['hard_deadline_at']
        return reminder_message(self.after, self.limit, max(0, int(hard_at - now)), hard_at)


def user_message(text, priority=None):
    """One stream-json input line: a user message with its own uuid (replayed back as the delivery receipt)."""
    message = {'type': 'user', 'message': {'role': 'user', 'content': text}, 'parent_tool_use_id': None,
               'session_id': '', 'uuid': str(uuid.uuid4())}
    if priority:
        message['priority'] = priority
    return message


class Session:
    """A running `claude -p --input-format stream-json` process: stdout teed to the stream file and followed (tools
    in flight, results, replayed message uuids, control responses), stdin kept open until the last message's turn has
    ended."""

    def __init__(self, process, stream_file, clock=time.time):
        self.process, self.clock = process, clock
        self.lock, self.lines, self.tools, self.results = threading.Lock(), 0, set(), []
        self.replayed, self.responses, self.written, self.closed = {}, {}, [], False
        self.reader = threading.Thread(target=self.read, args=(stream_file,), daemon=True)
        self.reader.start()

    def read(self, stream_file):
        for raw in self.process.stdout:
            with self.lock:
                stream_file.write(raw)
                stream_file.flush()
                line = self.lines
                self.lines += 1
                try:
                    event = json.loads(raw)
                except ValueError:
                    continue
                if not isinstance(event, dict):
                    continue
                kind, message = event.get('type'), event.get('message')
                blocks = message.get('content') if isinstance(message, dict) else None
                blocks = blocks if isinstance(blocks, list) else []
                if kind == 'assistant' and not event.get('parent_tool_use_id'):
                    self.tools |= {b.get('id') for b in blocks if isinstance(b, dict) and b.get('type') == 'tool_use'}
                elif kind == 'user':
                    self.tools -= {b.get('tool_use_id') for b in blocks if isinstance(b, dict)
                                   and b.get('type') == 'tool_result'}
                    if event.get('isReplay') and event.get('uuid'):
                        self.replayed.setdefault(event['uuid'], (line, self.clock()))
                elif kind == 'result':
                    self.results.append((line, event))
                elif kind == 'control_response':
                    response = event.get('response') or {}
                    self.responses.setdefault(response.get('request_id'), (line, self.clock(), response))

    def send(self, value):
        """Write one input line; returns the stream line count at that moment (the in-flight position)."""
        with self.lock:
            at = self.lines
            self.process.stdin.write((json.dumps(value, ensure_ascii=False) + '\n').encode())
            self.process.stdin.flush()
        return at

    def say(self, text, priority=None):
        message = user_message(text, priority)
        at = self.send(message)
        self.written.append(message['uuid'])
        return message['uuid'], at

    def interrupt(self):
        request = 'req_' + uuid.uuid4().hex[:12]
        return request, self.send({'type': 'control_request', 'request_id': request, 'request': {'subtype': 'interrupt'}})

    def close(self):
        if not self.closed:
            self.closed = True
            try:
                self.process.stdin.close()
            except OSError:
                pass

    def turn_over(self):
        """The last written message replayed and a result after that replay: nothing more will run. Only the last
        one counts: a message that arrives before the one ahead of it was dequeued is merged into the same request, and
        the earlier message is then never replayed (mock gate 2026-10-23, reminder at 0 s)."""
        with self.lock:
            if not self.written or self.written[-1] not in self.replayed:
                return False
            last = self.replayed[self.written[-1]][0]
            return any(line > last for line, _ in self.results)

    def tool_running(self):
        with self.lock:
            return bool(self.tools)

    def wait_for(self, condition, seconds):
        end = time.time() + seconds
        while time.time() < end and self.process.poll() is None:
            with self.lock:
                if condition():
                    return True
            time.sleep(POLL / 2)
        with self.lock:
            return condition()


def deliver_reminder(session, deadline, stream_name):
    """priority "now"; with a tool executing, `control_request interrupt` first and the message after the cut turn's
    result (cc-priority-1022 scheme 1). Intent is recorded before sending, the receipt when the message is replayed."""
    now = session.clock()
    text = deadline.text(now)
    record = deadline.value['reminder'] = {'attempted_at': now, 'operation': 'send_message', 'status': 'unknown',
                                           'message': text, 'stream': stream_name}
    deadline.save()
    if session.tool_running():
        request, at = session.interrupt()
        record.update(method='interrupt+now', stream_line=at, interrupt_request={'request_id': request})
        deadline.save()
        got = session.wait_for(lambda: request in session.responses and any(
            line >= at for line, _ in session.results), INTERRUPT_WAIT)
        line, when, response = session.responses.get(request, (None, None, {}))
        record['interrupt_request'].update(response_subtype=response.get('subtype'), response_at=when,
                                           turn_result_seen=got)
        if response.get('subtype') == 'success':
            record['status'] = 'interrupt accepted'  # the cut turn is ours already; the message follows
        message, _ = session.say(text, 'now')
    else:
        message, at = session.say(text, 'now')
        record.update(method='now', stream_line=at)
    record['receipt'] = {'messageId': message, 'deliveryStatus': None}
    deadline.save()


def note_receipt(session, deadline):
    record = deadline.value['reminder']
    if record and record.get('receipt') and record['receipt']['deliveryStatus'] is None:
        with session.lock:
            replay = session.replayed.get(record['receipt']['messageId'])
        if replay:
            record['receipt'].update(deliveryStatus='accepted', replayed_at=replay[1])
            record['status'] = 'accepted'
            deadline.save()


def hard_stop(session, deadline, stream_name):
    """ARW's interrupt at the hard limit: control_request interrupt, stdin closed, the group stopped after HARD_GRACE."""
    now = session.clock()
    record = deadline.value['interrupt'] = {'attempted_at': now, 'operation': 'interrupt_agent', 'status': 'unknown',
                                            'stream': stream_name}
    deadline.save()
    try:
        request, at = session.interrupt()
        record.update(stream_line=at, receipt={'request_id': request})
    except OSError as error:
        record['error'] = str(error)
        request = None
    session.close()
    deadline.save()
    try:
        session.process.wait(timeout=HARD_GRACE)
    except subprocess.TimeoutExpired:
        record['group_stopped'] = True
    stop_group(session.process)  # also any leftover command of the session (a hard stop leaves nothing running)
    session.reader.join(timeout=5)
    line, when, response = session.responses.get(request, (None, None, {}))
    if response.get('subtype') == 'success':
        record.update(status='accepted')
        record['receipt'].update(accepted=True, response_at=when)
    deadline.save()


def drive(process, stream_file, stream_name, first_message, deadline, clock=time.time):
    """Write the segment's message and follow the session to its end: the reminder when due while a turn runs, stdin
    closed once the last message's turn is over, the hard stop at the limit. Returns (exit code, hard-stopped)."""
    session = Session(process, stream_file, clock)
    try:
        session.say(first_message)
    except OSError:
        session.close()
    while True:
        if process.poll() is not None:
            break
        now = clock()
        note_receipt(session, deadline)
        if deadline.hard_due(now):
            hard_stop(session, deadline, stream_name)
            break
        if not session.closed:
            if session.turn_over():
                session.close()
            elif deadline.reminder_due(now):
                try:
                    deliver_reminder(session, deadline, stream_name)
                except OSError as error:
                    deadline.value['reminder']['error'] = str(error)
                    deadline.save()
        time.sleep(POLL)
    session.reader.join(timeout=10)
    note_receipt(session, deadline)
    session.close()
    return process.wait(), deadline.value['interrupt'] is not None and deadline.value['interrupt'].get(
        'stream') == stream_name


def drive_turns(process, stream_file, stream_name, messages, deadline, clock=time.time):
    """Multi-turn conversation in one `claude -p` stream-json process: each message is written once the previous
    one's turn is over (its replay followed by a result); stdin closes after the last turn; the hard stop at the limit
    ends it (no further message is sent).  Returns (exit code, hard-stopped, per-turn send and end times)."""
    session = Session(process, stream_file, clock)
    turns, pending = [], list(messages)

    def send():
        text = pending.pop(0)
        session.say(text)
        turns.append({'sent_at': clock(), 'ended_at': None})

    try:
        send()
    except OSError:
        session.close()
    while True:
        if process.poll() is not None:
            break
        if deadline.hard_due(clock()):
            hard_stop(session, deadline, stream_name)
            break
        if not session.closed and session.turn_over():
            turns[-1]['ended_at'] = clock()
            if pending:
                try:
                    send()
                except OSError:
                    session.close()
            else:
                session.close()
        time.sleep(POLL)
    session.reader.join(timeout=10)
    session.close()
    hard = deadline.value['interrupt'] is not None
    return process.wait(), hard, turns


ANTHROPIC_START_CAP = (60, 3600)   # Anthropic-backend process starts (a segment, a turn run) per hour; a script that restarts the run over and over stops here


def start_process(argv, env, work, stdin, stderr, out):
    """Popen of one Claude Code process, plus its guard: Anthropic-backend starts are rate capped (a loop that keeps restarting the run
    spends the subscription), and the run is registered for the status page (local backends as claude-local, not a plan run).
    Returns (process, registration); leave the registration's `with` when the process has ended. A failed registration kills the process group and raises."""
    local = 'ANTHROPIC_BASE_URL' in env
    if not local:
        guard_runs.rate('qwen-strata:claude_headless', *ANTHROPIC_START_CAP)
    process = subprocess.Popen(argv, cwd=work, env=env, stdin=stdin, stdout=subprocess.PIPE, stderr=stderr, start_new_session=True)
    flag = lambda name: argv[argv.index(name) + 1] if name in argv and argv.index(name) + 1 < len(argv) else ''   # noqa: E731
    registration = contextlib.ExitStack()
    try:   # registered here, not left to the caller's `with`: a registry that fails must not leave the process running unattended
        registration.enter_context(guard_runs.registered(
            f'qwen-strata:{Path(out).parent.name}/{Path(out).name}', 'claude-local' if local else 'claude',
            model=flag('--model'), effort=flag('--effort'), source='' if local else 'claude-sub', pid=process.pid))
    except BaseException:
        os.killpg(process.pid, signal.SIGKILL)   # the process leads its own session and group (start_new_session)
        process.wait()
        raise
    return process, registration


def run_turns(out, messages, argv, env, work, deadline, clock=time.time):
    """One process, the messages one turn after another (window workload v2 on Claude Code); the clock starts with
    the first message."""
    stream, errors = out / 'stream.jsonl', out / 'stream.err'
    with stream.open('wb') as stdout, errors.open('wb') as stderr:
        begun = clock()
        deadline.begin(begun)
        process, registered = start_process(argv, env, work, subprocess.PIPE, stderr, out)
        with registered:
            code, timed_out, turns = drive_turns(process, stdout, stream.name, messages, deadline, clock)
        ended = clock()
    return {'exit': code, 'hard_interrupt': timed_out, 'started_at': begun, 'ended_at': ended,
            'wall_seconds': ended - begun, 'pid': process.pid, 'turns': turns, 'turns_planned': len(messages),
            'work_seconds': sum((t['ended_at'] or ended) - t['sent_at'] for t in turns)}


def conversation_analysis(stream, label=lambda text: text, in_text=None):
    """Per user turn of a run_turns stream: its label (`label(text)`, None to skip), the assistant's text, the
    context its last request carried (input + cache read + cache creation of the turn's result usage) and, for the
    window timeline, which turns were raw context when it was answered.  A compact_boundary drops everything before
    it except the turn in flight (Claude Code keeps no raw messages, only the summary)."""
    replies, compactions, raw, current, calls, texts = [], [], [], None, 0, {}

    def mark(point):
        point['raw'] = list(raw)
        if in_text:  # which facts are really in the raw text (`in_text(label, texts)`, window_bank.finder)
            point['in_text_ids'] = in_text(point['turn'], [texts[k] for k in raw if k in texts])
    for line in Path(stream).read_text(errors='replace').splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        kind, message = event.get('type'), event.get('message')
        if kind == 'system' and event.get('subtype') == 'compact_boundary':
            pending = current['turn'] if current is not None and current['result'] is None else None
            compactions.append({'after_user_turn': raw[-1] if raw else None, 'during_turn': pending,
                                'metadata': event.get('compact_metadata'), 'summary': None})
            raw = [pending] if pending else []
            texts = {k: v for k, v in texts.items() if k in raw}
            if current is not None:
                current['compactions_after'] = [c['after_user_turn'] for c in compactions]
        elif kind == 'user' and not event.get('isReplay') and isinstance(message, dict) and compactions \
                and compactions[-1].get('summary') is None:
            content = message.get('content')
            text = content if isinstance(content, str) else ''.join(
                b.get('text', '') for b in content or [] if isinstance(b, dict))
            if text.startswith('This session is being continued'):
                compactions[-1]['summary'] = text
        elif kind == 'user' and event.get('isReplay') and isinstance(message, dict):
            content = message.get('content')
            text = content if isinstance(content, str) else ''.join(
                b.get('text', '') for b in content or [] if isinstance(b, dict))
            name = label(text)
            if name is None:
                continue
            raw.append(name)
            texts[name] = text
            current = {'turn': name, 'text': '', 'result': None, 'context_tokens': None,
                       'compactions_after': [c['after_user_turn'] for c in compactions]}
            mark(current)
            replies.append(current)
        elif kind == 'assistant' and isinstance(message, dict) and current is not None \
                and not event.get('parent_tool_use_id'):
            for block in message.get('content') or []:
                if isinstance(block, dict) and block.get('type') == 'text':
                    current['text'] += block.get('text', '')
                elif isinstance(block, dict) and block.get('type') == 'tool_use':
                    calls += 1
        elif kind == 'result' and current is not None and current['result'] is None:
            usage = event.get('usage') or {}
            current['result'] = event.get('subtype')
            current['context_tokens'] = sum(usage.get(k) or 0 for k in (
                'input_tokens', 'cache_read_input_tokens', 'cache_creation_input_tokens')) or None
            mark(current)
    return {'replies': replies, 'compactions': compactions, 'tool_calls': calls}


def run_conversation(out, messages, model, effort, host, context_window, limit, label='window', run_id=None,
                     base=WORK_BASE, claude=CLAUDE, mock_base=None):
    """A multi-turn Strata conversation through Claude Code (window workload v2 mechanism check): the run() setup
    (isolated working directory, fresh configuration directory, minimal environment, project compact prompt hook)
    with `messages` sent one turn after another on the `context_window` tier.  `mock_base` (no-model precheck,
    tools.tuning.sandbox_probe): the same command and environment pointed at a loopback fake server, no lease."""
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    run_id = run_id or out.name + '-' + str(time.time_ns())
    work = workspace(run_id, base)
    session_settings = settings(work, [], session_hooks(True))
    argv = command('strata', model, effort, work, [], session_settings, TOOLS, True, claude)
    save(out / 'settings.json', session_settings)
    save(out / 'command.json', argv)
    binding = {'backend': 'strata', 'model': model, 'effort': effort, 'label': label, 'work': str(work),
               'limit_seconds': limit, 'tools': TOOLS, 'turns': len(messages),
               'messages_sha256': hashlib.sha256(json.dumps(messages).encode()).hexdigest(),
               'compact_prompt_sha256': hashlib.sha256(COMPACT.read_bytes()).hexdigest(), 'claude': binary(claude)}
    deadline = Deadline(out, limit, None, run_id=run_id)
    if mock_base:
        from tools.ops.deployment_source import published_tier, served_model
        tier = published_tier(host, served_model(host), context_window)
        home, config_dir = work.parent / 'home', work.parent / 'claude-config'
        home.mkdir()
        config_dir.mkdir()
        env = environment('strata', effort, home, config_dir, strata_environment(mock_base, 'fake-loopback', model,
                                                                                  effort, tier), tmp=run_tmp(work))
        save(out / 'binding.json', dict(binding, context_tier=tier, mock_base=mock_base))
        result = run_turns(out, messages, argv, env, work, deadline)
    else:
        result = strata_run(out, None, argv, model, effort, work, limit, None, binding, True, host, deadline=deadline,
                            context_window=context_window, messages=messages)
    result['summary'] = stream_summary([out / 'stream.jsonl'])
    result['session_files'] = keep_session_files(work, config_root('strata', work), out)
    result['run_tmp_removed'] = remove_run_tmp(work)
    shutil.rmtree(work.parent, ignore_errors=True)  # the run root: work, home, claude-config (history kept above)
    save(out / 'result.json', result)
    return result


def outside_grants(folder, targets):
    """Every existing entry under `folder` that is neither a grant nor inside one; an ancestor of a grant (such as the
    scenario root's `.tmp` above a nested report directory) is walked instead of left writable."""
    denied = []
    for p in sorted(folder.iterdir()):
        r = p.resolve()
        if any(r == t or t in r.parents for t in targets):
            continue
        if p.is_dir() and not p.is_symlink() and (p.name == '.git' or any(r in t.parents for t in targets)):
            # `.git` itself stays writable for new entries only: with CLAUDE_CODE_SUBPROCESS_ENV_SCRUB Claude Code
            # mounts empty stubs such as .git/config.lock, and bwrap cannot create them in a read-only .git (every
            # sandboxed command then fails, 2026-10-19). Its existing entries are denied one by one.
            denied += outside_grants(p, targets) if p.name != '.git' else [str(c) for c in sorted(p.iterdir())]
        else:
            denied.append(str(p))
    return denied


def settings(work, writes, hooks):
    """Session settings passed with --settings; no user, project or local settings file is read."""
    targets = write_targets(work, writes)
    # The sandbox always lets commands write in the working directory; denying the directory itself breaks bwrap
    # (it creates placeholders such as .git and scripts there), so every existing entry outside the grants is denied
    # and a new file at the top of the working directory stays possible (tools.safety.claude_gate records it).
    deny_write = outside_grants(work.resolve(), targets) + SHARED_DENY
    tmp = str(run_tmp(work))
    return {'autoMemoryEnabled': False, 'includeGitInstructions': False,
            'sandbox': {'enabled': True, 'autoAllowBashIfSandboxed': True, 'allowUnsandboxedCommands': False,
                        'filesystem': {'denyRead': list(DENY_READ) + shared_tmp_entries(), 'allowRead': [str(work), tmp],
                                       'denyWrite': deny_write, 'allowWrite': [str(t) for t in targets] + [tmp]},
                        'network': {'allowedDomains': []}},
            'hooks': hooks}


def allowed_tools(work, writes):
    """Reads anywhere in the working directory; Edit and Write only on the granted paths; sandboxed Bash."""
    grants = []
    for target in write_targets(work, writes):
        scope = f'/{target}/**' if target.is_dir() else f'/{target}'
        grants += [f'Edit({scope})', f'Write({scope})']
    return ','.join([f'Read(/{work}/**)', 'Glob', 'Grep', 'Bash', *grants])


def startup_text():
    raw = startup_prompt_bytes(STARTUP.read_bytes(), False)
    return raw.decode('utf-8').strip(), hashlib.sha256(raw).hexdigest()


def deepseek_model(model):
    """The DeepSeek model named verbatim; Claude names would be remapped by the endpoint to another model."""
    if not DEEPSEEK_MODEL.fullmatch(model or '') or re.search(r'claude|opus|sonnet|haiku', model):
        raise ValueError('The DeepSeek backend names a deepseek-* model explicitly, never a Claude model name')
    return model


def settings_argument(session_settings):
    """The settings as one argv string. Linux caps a single argument at 131072 bytes (MAX_ARG_STRLEN) and the denyRead
    list grows with /tmp (shared_tmp_entries); refuse before the kernel does, with the reason."""
    text = json.dumps(session_settings)
    if len(text.encode()) > SETTINGS_ARGUMENT_LIMIT:
        raise ValueError(f'Settings are {len(text.encode())} bytes, over {SETTINGS_ARGUMENT_LIMIT}: clear stale /tmp entries')
    return text


def command(backend, model, effort, work, writes, session_settings, tools=TOOLS, startup=True, claude=CLAUDE,
            persist=False, system_prompt=None):
    """The Claude Code command. All backends get the same flags; the startup prompt is appended here for API models
    and by the service for Strata, so each model sees it once (D4). The multi-model benchmark gives it only to Strata,
    so its API runs pass startup=False (--no-startup-prompt). persist=True drops --no-session-persistence so that an
    early exit can continue with --resume (scenario runs): the first request stays the same as without it (mock
    2026-10-20, only the run's own paths and ids differ), and the transcript lands in the configuration directory,
    which sandboxed commands and the restricted file tools cannot read (the home directory and WORK_BASE are denied).
    `system_prompt` (the scenario Role instructions, user 2026-10-20: Claude Code has no developer role, the system
    prompt is the matching place) goes into the same single --append-system-prompt, after the startup prompt."""
    if backend not in BACKENDS:
        raise ValueError('Unknown backend')
    if backend == 'deepseek':
        deepseek_model(model)
    argv = [claude, '-p', '--model', model, '--effort', effort, '--restricted', '--strict-mcp-config',
            '--disable-slash-commands', '--setting-sources', '', '--settings', settings_argument(session_settings),
            '--tools', tools, '--disallowedTools', DISALLOWED, '--permission-mode', 'dontAsk', '--permission-prompts', 'none',
            '--allowedTools', allowed_tools(work, writes),
            '--input-format', 'stream-json', '--replay-user-messages',
            '--output-format', 'stream-json', '--verbose', *([] if persist else ['--no-session-persistence'])]
    parts = [startup_text()[0]] if backend != 'strata' and startup else []
    if system_prompt:
        parts.append(system_prompt.strip())
    if parts:
        argv += ['--append-system-prompt', '\n\n'.join(parts)]
    return argv


def strata_environment(base, key, model, effort, tier):
    """qwen-agent's model variables for Claude Code (window, output, effort, compaction point), nothing else."""
    loader = SourceFileLoader('qwen_agent', str(AGENT))
    agent = module_from_spec(spec_from_loader('qwen_agent', loader))
    loader.exec_module(agent)
    frontend = type('Frontend', (), {'base': base, 'key': key})()
    return agent.claude(frontend, model, effort, tier, [])[1]


# Window, compaction point and output limit a scenario plan may fix for the DeepSeek arm (multi-model v2 §5.2: the same
# 1M window as its Codex arm); v1 plans fix none, so Claude Code keeps its defaults there.
DEEPSEEK_LIMIT_VARIABLES = ('CLAUDE_CODE_MAX_CONTEXT_TOKENS', 'CLAUDE_CODE_BLOCKING_LIMIT_OVERRIDE',
                            'CLAUDE_CODE_MAX_OUTPUT_TOKENS')


def deepseek_environment(model, key, base=DEEPSEEK_BASE, limits=None):
    """DeepSeek's Anthropic-format endpoint: the key as the bearer token, the model named in every model variable.
    `limits`: DEEPSEEK_LIMIT_VARIABLES values (positive integers) the plan fixes."""
    if not key:
        raise ValueError('The DeepSeek backend needs ' + DEEPSEEK_KEY)
    limits = dict(limits or {})
    if set(limits) - set(DEEPSEEK_LIMIT_VARIABLES) or any(
            not isinstance(v, int) or isinstance(v, bool) or v <= 0 for v in limits.values()):
        raise ValueError(f'DeepSeek limits must be positive integers of {DEEPSEEK_LIMIT_VARIABLES}: {limits}')
    return {'ANTHROPIC_BASE_URL': base, 'ANTHROPIC_AUTH_TOKEN': key, 'CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC': '1',
            **{name: deepseek_model(model) for name in DEEPSEEK_MODEL_VARIABLES},
            **{name: str(value) for name, value in limits.items()}}


def environment(backend, effort, home=None, config_dir=None, strata=None, tmp=None):
    """Minimal environment, the effect of `env -i`: no variable of the calling session reaches Claude Code.
    `strata` is the backend's model environment (Strata's from qwen-agent, or deepseek_environment()); `tmp` is the
    run's own TMPDIR (run_tmp), required so that no run falls back to the shared /tmp/claude-<uid>."""
    shared = [Path(p) for p in SHARED_TMP]
    if not tmp or Path(tmp).resolve() == Path('/tmp') or any(
            Path(tmp).resolve() == p or p in Path(tmp).resolve().parents for p in shared):
        raise ValueError('Every run has its own TMPDIR beside its working directory (run_tmp)')
    env = {'PATH': os.environ.get('PATH', '/usr/bin:/bin'), 'LANG': 'C.UTF-8', 'TERM': 'dumb',
           'DISABLE_AUTOUPDATER': '1', 'CLAUDE_CODE_EFFORT_LEVEL': effort, 'CLAUDE_CODE_SUBPROCESS_ENV_SCRUB': '1',
           'CLAUDE_CODE_TMPDIR': str(tmp), 'TMPDIR': str(tmp),
           # Claude Code 2.1.309 (not 2.1.303) adds a deferred `DeferredToolPlaceholder` tool ("never call this tool",
           # defer_loading) to every request for its tool search; turned off, the advertised tools are again exactly
           # --tools, as tools.safety.claude_gate requires (mock 2026-10-24: only the tool list changes).
           'ENABLE_TOOL_SEARCH': 'false'}
    if backend == 'anthropic':
        # A synthetic HOME (anthropic_home) whose only content links the real configuration directory, which supplies
        # the subscription login; --setting-sources "" keeps its settings, hooks and CLAUDE.md out (verified by
        # tools.safety.claude_gate). The real HOME is never the run's HOME: the Bash sandbox (bwrap) creates empty
        # mount points for protected dotfiles that do not exist, such as ~/.bash_profile (2026-10-19).
        if not home or Path(home).resolve() == Path.home().resolve():
            raise ValueError('The Anthropic backend runs with a synthetic HOME (anthropic_home), never the real one')
        env['HOME'] = str(home)
        if config_dir:
            env['CLAUDE_CONFIG_DIR'] = str(config_dir)
    else:
        if not (home and config_dir and strata):
            raise ValueError('This backend needs a fresh HOME, CLAUDE_CONFIG_DIR and its model environment')
        env.update(HOME=str(home), CLAUDE_CONFIG_DIR=str(config_dir), **strata)
    return env


def anthropic_home(run_root, real=None):
    """`<run_root>/home` holding only links to the real ~/.claude and ~/.claude.json (the login and Claude Code's own
    state, used as before); dotfiles the sandbox creates land here instead of in the real HOME. Nothing is opened."""
    real = Path(real or Path.home())
    home = Path(run_root) / 'home'
    if str(home.resolve()).startswith(str(real.resolve()) + '/'):
        raise ValueError('The synthetic HOME must be outside the real HOME')
    home.mkdir()
    (home / '.claude').symlink_to(real / '.claude')
    if (real / '.claude.json').exists():
        (home / '.claude.json').symlink_to(real / '.claude.json')
    return home


# A Bash call whose sandbox could not be built: Claude Code's own bwrap argument check, or bwrap failing before the
# command ran. Seen as the start of an error tool result (2026-10-20); the command never ran.
# F4 (2026-10-20): an is_error result caused by the model itself (its context or output exceeding the limits, mock
# 2026-10-20 with Claude Code 2.1.303: terminal_reason 'prompt_too_long'; "API Error: Claude's response exceeded the N
# output token maximum" with terminal_reason 'api_error') ends the run as ARW's incomplete on Codex would: scored on what
# was written, no continuation. Every other is_error (API status, transport, auth) stays a harness fault: invalid, rerun.
MODEL_ERROR_TEXT = re.compile(r'exceeded the \d+ output token maximum|^Prompt is too long')
MODEL_ERROR_SUBTYPES = {'error_max_turns'}


def error_kind(result):
    """None for a result without is_error, 'model' for a model-side failure, 'api' for any other."""
    if not isinstance(result, dict) or not result.get('is_error'):
        return None
    if (result.get('terminal_reason') == 'prompt_too_long' or result.get('subtype') in MODEL_ERROR_SUBTYPES
            or MODEL_ERROR_TEXT.search(str(result.get('result') or ''))):
        return 'model'
    return 'api'


SANDBOX_FAILURE = re.compile(r'(Error: )?(Sandbox profile has \d+ bwrap arguments|.*bwrap accepts at most|bwrap: )')


def tool_result_text(content):
    if isinstance(content, list):
        return '\n'.join(c.get('text', '') for c in content if isinstance(c, dict))
    return content if isinstance(content, str) else ''


def add_usage(total, usage):
    """Per-result usage summed field by field (numbers only; nested server_tool_use counts too)."""
    for key, value in (usage or {}).items():
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            total[key] = total.get(key, 0) + value
        elif isinstance(value, dict) and key in ('server_tool_use', 'output_tokens_details', 'cache_creation'):
            add_usage(total.setdefault(key, {}), value)
    return total


def stream_summary(stream):
    """All result events of one or more stream-json files (a continued run's segments, in order). Claude Code 2.1.303
    reports `usage`, `num_turns` and `duration_ms` per result, while `modelUsage`, `total_cost_usd` and
    `duration_api_ms` run on across the session, also over --resume (mock 2026-10-20; duration_api_ms in the benchmark
    streams, 2026-10-22): the former are summed, the latter taken from the last result.
    (Before 2026-10-20 only the last result was read, which undercounts any stream with more than one.)
    A segment without a result event (killed at the hard limit) leaves its usage and time out: the sums are then lower
    bounds (`segments_without_result`, `usage_bound`). A total_cost_usd that falls between segments is not cumulative,
    so it is summed instead. The result of a turn that a delivered reminder or interrupt cut short (user 2026-10-20 /
    2026-10-23, reminder_interrupt.stream_exempt) never counts as an error (`reminder_interrupts`); an aborted turn's
    streaming result carries no usage, so its tokens make the sums lower bounds too."""
    streams = [stream] if isinstance(stream, (str, Path)) else list(stream)
    lines, per_stream = [], [0] * len(streams)
    for index, one in enumerate(streams):
        try:
            lines += [(index, number, line) for number, line in enumerate(Path(one).read_text(errors='replace').splitlines())]
        except OSError:
            pass
    results, numbered = [], [[] for _ in streams]
    sandbox_failures = 0
    init = None
    tiers, seen = {}, set()
    for index, number, line in lines:
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        message = event.get('message') if event.get('type') == 'assistant' else None
        usage = message.get('usage') if isinstance(message, dict) else None
        if isinstance(usage, dict) and message.get('id') not in seen:
            # D14: the tier the API returned for each assistant message (stream-json repeats a message once per
            # content block, so it counts once by id); the absence is counted, not filled in.
            seen.add(message.get('id'))
            tier = usage.get('service_tier') or 'not-returned'
            tiers[tier] = tiers.get(tier, 0) + 1
        if event.get('type') == 'user' and isinstance(event.get('message'), dict):
            for block in event['message'].get('content') or []:
                if (isinstance(block, dict) and block.get('type') == 'tool_result' and block.get('is_error')
                        and SANDBOX_FAILURE.match(tool_result_text(block.get('content')))):
                    sandbox_failures += 1
        if event.get('type') == 'system' and event.get('subtype') == 'init' and init is None:
            init = {k: event.get(k) for k in ('model', 'tools', 'mcp_servers', 'permissionMode', 'claude_code_version')}
        if event.get('type') == 'result':
            results.append(event)
            numbered[index].append((number, event))
            per_stream[index] += 1
    without = sum(1 for n in per_stream if n == 0)
    # The turn a delivered reminder / interrupt cut short is ours, not a fault (reminder_interrupt.stream_exempt).
    cut = []
    for index, one in enumerate(streams):
        exempt = reminder_interrupt.stream_exempt(one, numbered[index]) if numbered[index] else {}
        cut += [event for line, event in numbered[index] if line in exempt]
    cut_ids = {id(e) for e in cut}
    if not results:
        return {'result_event': False, 'init': init, 'service_tiers': tiers, 'sandbox_failures': sandbox_failures,
                'segments': len(streams), 'segments_without_result': without}
    last = results[-1]
    costs = [r.get('total_cost_usd') for r in results]
    if any(c is None for c in costs):
        cost = last.get('total_cost_usd')
    elif all(b >= a for a, b in zip(costs, costs[1:])):
        cost = costs[-1]  # cumulative across --resume, as 2.1.303 reports it
    else:
        cost = sum(costs)
    usage = {}
    for one in results:
        add_usage(usage, one.get('usage'))
    for key in ('service_tier', 'speed', 'inference_geo'):  # descriptive fields as the last result gives them
        if key in (last.get('usage') or {}):
            usage[key] = last['usage'][key]

    def total(key):
        values = [r.get(key) for r in results]
        return None if any(v is None for v in values) else sum(values)

    def session_total(key):
        # duration_api_ms runs on across --resume like total_cost_usd (2.1.303: strata-1019 haiku-low-a7, 46
        # segments, each value the previous plus the segment's API time), so a non-decreasing series is cumulative
        values = [r.get(key) for r in results]
        if any(v is None for v in values):
            return None
        return values[-1] if all(b >= a for a, b in zip(values, values[1:])) else sum(values)
    server_tools = usage.get('server_tool_use') or {}
    searches = (server_tools.get('web_search_requests') or 0) + (server_tools.get('web_fetch_requests') or 0)
    judged = [r for r in results if id(r) not in cut_ids]
    # A turn whose stream was aborted reports zero usage (cc-priority-1022, mock and Strata d1): the tokens of its
    # requests are missing from the sums. aborted_tools keeps the usage of its completed requests (nothing in flight).
    aborted = sum(1 for r in results if r.get('terminal_reason') == 'aborted_streaming')
    return {'result_event': True, 'init': init, 'subtype': last.get('subtype'),
            'is_error': any(bool(r.get('is_error')) for r in judged),
            'error_kind': error_kind(last) if id(last) not in cut_ids else None,
            'reminder_interrupts': [{'subtype': r.get('subtype'), 'is_error': r.get('is_error'),
                                     'terminal_reason': r.get('terminal_reason')} for r in cut],
            'aborted_results': aborted,
            'duration_ms': total('duration_ms'),
            'duration_api_ms': session_total('duration_api_ms'), 'num_turns': total('num_turns'),
            'total_cost_usd': cost, 'usage': usage, 'modelUsage': last.get('modelUsage'),
            'result_events': len(results), 'segments': len(streams), 'segments_without_result': without,
            'usage_bound': 'lower' if without or aborted else 'complete', 'service_tiers': tiers,
            'server_web_requests': searches, 'sandbox_failures': sandbox_failures,
            'token_source': 'Claude Code stream-json result usage (API usage; engine log for the Strata arm)'}


def stop_group(process, grace=20):
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=grace)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait()


def run_segment(out, k, message, argv, env, work, deadline, on_start=None, clock=time.time):
    """One `claude -p` process (segment k: stream.jsonl and prompt-sent.md, else stream-k.jsonl and prompt-sent-k.md)
    driven to its end. `on_start(process, message)` may rewrite the message once the process exists."""
    suffix = '' if k == 0 else f'-{k}'
    stream, errors = out / f'stream{suffix}.jsonl', out / f'stream{suffix}.err'
    with stream.open('wb') as stdout, errors.open('wb') as stderr:
        begun = clock()
        deadline.begin(begun)
        process, registered = start_process(argv, env, work, subprocess.PIPE, stderr, out)
        with registered:
            if on_start:
                message = on_start(process, message)
            (out / f'prompt-sent{suffix}.md').write_text(message)
            code, timed_out = drive(process, stdout, stream.name, message, deadline, clock)
        ended = clock()
    return {'exit': code, 'hard_interrupt': timed_out, 'started_at': begun, 'ended_at': ended,
            'wall_seconds': ended - begun, 'pid': process.pid}


def execute(out, prompt_text, argv, env, work, limit=HARD_LIMIT, started_file=None, on_start=None, deadline=None,
            clock=time.time):
    """Run once with the prompt as the first stream-json message; the reminder and the hard stop as `deadline` says
    (hard stop only without one)."""
    deadline = deadline or Deadline(out, limit)
    before = file_hashes(work)
    save(out / 'files-before.json', before)
    started = clock()
    if started_file:
        Path(started_file).write_text(repr(started))
    deadline.begin(started)
    result = run_segment(out, 0, prompt_text, argv, env, work, deadline, on_start, clock)
    after = file_hashes(work)
    save(out / 'files-after.json', after)
    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    return {**result, 'started_at': started, 'wall_seconds': result['ended_at'] - started, 'changed_files': changed}


# ARW's continuation instructions, verbatim from the frozen snapshot 760007c, lib/reviewer-runtime/reviewer-runtime.mjs
# (the early-exit branch of the completion check): which one depends on the bound report's state.
ARW_REPORT_EXISTS = ('The bound report exists, but complete successful delivery of this task has not been confirmed. An '
                     'incomplete final status is legal and does not by itself establish that further work is impossible. '
                     'Verify the complete review and deliver the required ready status. Preserve the existing report and '
                     'evidence; do not create another Agent.')
ARW_CONTINUE_BODY = ('Complete successful delivery of this review task has not been confirmed. An incomplete final status is '
                     'legal and does not by itself establish that further work is impossible. Continue this same task using '
                     'the existing input and evidence, correct recoverable errors, complete the necessary checks, personally '
                     'deliver its original bound report and return the required ready status. Do not create another Agent '
                     'or replace this task.')
ARW_PAUSE_TEXT = ('The Reviewer runtime paused this same task after {count} normally completed turns without full report '
                  'delivery. Ask the user whether to continue. After approval, send this task an ordinary work message; to '
                  'end it, interrupt the original task.')  # lib/background-agent/manager.mjs noteEarlyExit
# JavaScript String.prototype.trim's set (WhiteSpace and LineTerminator), which ARW applies to the report text.
JS_SPACE = '\t\n\v\f\r                  　﻿'


def final_status(text):
    """ARW's reviewerFinalStatus: 'ready' only for exactly {"status":"ready"}, 'incomplete' for that status with one
    non-blank reason, otherwise None (not the status-only contract)."""
    try:
        value = json.loads(text) if isinstance(text, str) and not text.startswith('﻿') else None
    except ValueError:
        return None
    if not isinstance(value, dict):
        return None
    if value == {'status': 'ready'}:
        return 'ready'
    if (value.get('status') == 'incomplete' and len(value) == 2 and isinstance(value.get('reason'), str)
            and value['reason'].strip(JS_SPACE)):
        return 'incomplete'
    return None


def report_state(path):
    """The bound report as ARW reads it (strict UTF-8, no lossy decoding): (state, text or decoding error)."""
    path = Path(path)
    if not path.exists() and not path.is_symlink():
        return 'missing', None
    if path.is_symlink() or not path.is_file() or path.stat().st_nlink > 1:
        return 'unreadable', None  # ARW's scoped read refuses links and other kinds: no continuation
    try:
        data = path.read_bytes()
    except OSError:
        return 'unreadable', None
    try:
        return 'text', data.decode('utf-8')
    except UnicodeDecodeError:
        return 'undecodable', 'The encoded data was not valid for encoding utf-8'  # Node's TextDecoder message


def early_exit(final_text, report_path):
    """ARW's completion check after a normally ended turn: delivered, or the continuation it sends.
    `counted` says whether the turn counts towards the pause points (a recoverable read failure does not)."""
    state, text = report_state(report_path)
    delivered = final_status(final_text) == 'ready' and state == 'text' and bool(text.strip(JS_SPACE))
    if delivered:
        return {'delivered': True, 'report': state, 'continuable': False, 'counted': False, 'instruction': None}
    if state == 'unreadable':
        return {'delivered': False, 'report': state, 'continuable': False, 'counted': False, 'instruction': None}
    if state == 'text' and text.strip(JS_SPACE):
        instruction = ARW_REPORT_EXISTS
    elif state == 'undecodable':
        instruction = (f'The original bound report could not be read: filesystem-text-decoding-failed: {text}. Correct '
                       'this recoverable error and preserve the original report, judgments and evidence.\n\n'
                       + ARW_CONTINUE_BODY)
    else:
        instruction = ('The bound report is missing. ' if state == 'missing' else 'The bound report is empty. ') + ARW_CONTINUE_BODY
    return {'delivered': False, 'report': state, 'continuable': True, 'counted': state != 'undecodable',
            'instruction': instruction}


def segment_end(stream):
    """The session id and the last result event of one segment's stream."""
    session, result = None, None
    try:
        lines = Path(stream).read_text(errors='replace').splitlines()
    except OSError:
        lines = []
    for line in lines:
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get('type') == 'system' and event.get('subtype') == 'init':
            session = session or event.get('session_id')
        if event.get('type') == 'result':
            result = event
            session = event.get('session_id') or session
    return session, result


def execute_continued(out, prompt_text, argv, env, work, report, limit=HARD_LIMIT, started_file=None, on_start=None,
                      clock=time.time, deadline=None):
    """execute(), then ARW's continuation in the same session until full delivery, a run that cannot continue, or the
    hard limit counted from the first segment's start. Segment 0 is exactly execute(); segment i writes stream-i.jsonl,
    stream-i.err and prompt-sent-i.md. One `deadline` spans all segments: the reminder comes on the instance's elapsed
    time in whichever segment is running, the hard stop at the limit."""
    deadline = deadline or Deadline(out, limit)
    first = execute(out, prompt_text, argv, env, work, limit, started_file, on_start, deadline)
    started, before = first['started_at'], json.loads((out / 'files-before.json').read_text())
    segments = [{'index': 0, 'stream': 'stream.jsonl', 'message': 'handoff', **{k: first[k] for k in (
        'exit', 'hard_interrupt', 'started_at', 'ended_at', 'wall_seconds', 'pid')}}]
    early_exits, continue_count, next_pause, pauses = 0, 0, EARLY_EXIT_PAUSE_AT, []
    stop, last = None, first
    while stop is None:
        segment = segments[-1]
        session, result = segment_end(out / segment['stream'])
        if last['hard_interrupt']:
            stop = 'hard_limit'
            break
        if result is not None and error_kind(result) == 'model':
            stop = 'model_error'  # F4: scored on what was written, as ARW's incomplete; no continuation
            break
        if last['exit'] != 0 or result is None or result.get('is_error'):
            stop = 'abnormal_end'  # an API or transport error: the run is invalid as before, no continuation
            break
        check = early_exit(result.get('result'), Path(work) / report)
        segment.update(final_status=final_status(result.get('result')), report=check['report'],
                       delivered=check['delivered'])
        if check['delivered']:
            stop = 'delivered'
            break
        if not check['continuable']:
            stop = 'not_continuable'
            break
        if not session:
            stop = 'no_session'
            break
        message, kind = check['instruction'], 'arw_continuation'
        if check['counted']:
            early_exits += 1
            segment['early_exit_count'] = early_exits
            if early_exits >= next_pause:
                pauses.append({'at': clock(), 'segment': segment['index'], 'early_exit_count': early_exits,
                               'text': ARW_PAUSE_TEXT.format(count=early_exits), 'continue_count': continue_count})
                next_pause = early_exits + EARLY_EXIT_PAUSE_STEP
                message, kind = CONTINUE_MESSAGE, 'user_continue'
                pauses[-1]['continued'] = {'at': clock(), 'message': CONTINUE_MESSAGE}
                continue_count += 1
        remaining = limit - (clock() - started)
        if remaining <= 0:
            stop = 'deadline_between_segments'
            break
        k = len(segments)
        last = run_segment(out, k, message, [*argv, '--resume', session], env, work, deadline, clock=clock)
        segments.append({'index': k, 'stream': f'stream-{k}.jsonl', 'message': kind, 'session': session, **last})
    after = file_hashes(work)
    save(out / 'files-after.json', after)
    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    ended = segments[-1]['ended_at']
    return {'exit': last['exit'], 'hard_interrupt': last['hard_interrupt'], 'started_at': started, 'ended_at': ended,
            'wall_seconds': ended - started, 'pid': first['pid'], 'changed_files': changed,
            'continuation': {'stop': stop, 'delivered': stop == 'delivered', 'early_exit_count': early_exits,
                             'continue_count': continue_count, 'arw_pause_events': pauses, 'segments': segments,
                             'session_id': segment_end(out / 'stream.jsonl')[0]}}


def segment_streams(out):
    """A run's streams in segment order: stream.jsonl, then stream-1.jsonl, stream-2.jsonl, ..."""
    out = Path(out)
    more = sorted(out.glob('stream-*.jsonl'), key=lambda p: int(p.stem.split('-')[1]))
    return [out / 'stream.jsonl', *more]


def accounting_stream(streams):
    """The last stream with a result event: estimate.sh --add-stream reads one result per session id, and a last
    segment killed at the hard limit has none, so the one before it carries the cost so far (a lower bound then)."""
    with_result = [s for s in streams if segment_end(s)[1] is not None]
    return with_result[-1] if with_result else streams[-1]


def project_slug(work):
    """Claude Code's projects/<slug> name for a working directory (every character but a letter or digit is '-')."""
    return re.sub(r'[^A-Za-z0-9]', '-', str(work))


def config_root(backend, work):
    """The run's Claude Code configuration directory: the real ~/.claude for the Anthropic arm (anthropic_home links
    it), the run's fresh one otherwise."""
    return Path.home() / '.claude' if backend == 'anthropic' else Path(work).parent / 'claude-config'


def keep_session_files(work, config, out):
    """Move this run's projects/<slug> (the session transcript when persisted, and tool-results) into out/session-files,
    so the history stays with the run and no usage scan of ~/.claude/projects counts it as a main session. Nothing is
    read; only this run's own slug moves."""
    source = Path(config) / 'projects' / project_slug(work)
    if not source.is_dir() or source.is_symlink():
        return None
    target = Path(out) / 'session-files' / source.name
    target.parent.mkdir(exist_ok=True)
    shutil.move(str(source), str(target))
    return str(target.relative_to(out))


def remove_run_tmp(work):
    """Delete this run's own TMPDIR (`<run root>/tmp`, run_tmp) once the run is recorded (measurement rule: clean
    each instance's leftovers, user 2026-10-20). Only that directory, never through a link; the bytes freed or None."""
    tmp = Path(work).parent / 'tmp'
    if not tmp.is_dir() or tmp.is_symlink():
        return None
    size = sum(p.lstat().st_size for p in tmp.rglob('*') if not p.is_symlink() and p.is_file())

    def writable(function, path, _):
        os.chmod(os.path.dirname(path), 0o700)  # sandboxed commands may leave read-only directories
        function(path)
    shutil.rmtree(tmp, onexc=writable)
    return size


def account(stream, label, effort, out, estimate=ESTIMATE):
    """Add this run to the owner's optional quota ledger script (the script itself ignores models that are not
    Anthropic's). Never raises: the result says what happened, `estimate_exit` the script's exit code (None when it
    did not run) and `estimate_note` why it did not run or how it failed."""
    estimate = Path(estimate)
    if not estimate.is_file():
        return {'estimate_exit': None, 'estimate_note': 'skipped: the accounting script is absent on this machine'}
    try:
        done = subprocess.run([str(estimate), '--add-stream', str(stream), label, '--effort', effort],
                              capture_output=True, text=True)
        (out / 'add-stream.out').write_text(done.stdout + done.stderr)
    except OSError as error:
        return {'estimate_exit': None, 'estimate_note': f'failed: {error}'}
    return {'estimate_exit': done.returncode, 'estimate_note': None}


def binary(claude=CLAUDE):
    """Resolved path, SHA-256 and version of the Claude Code binary, recorded in every binding."""
    path = Path(shutil.which(claude) or claude).resolve()
    version = subprocess.run([str(path), '--version'], capture_output=True, text=True).stdout.strip()
    return {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'version': version}


def pinned_binary(claude=CLAUDE, expected=CLAUDE_VERSION, sha256=CLAUDE_SHA256):
    """The CLI entry points run only the pinned copy (SHA, then version); an auto-update would otherwise change the
    harness unseen."""
    found = binary(claude)
    if found['sha256'] != sha256 or found['version'].split()[0:1] != [expected]:
        raise SystemExit(f"Claude Code {found['version']!r} at {found['path']} (sha256 {found['sha256'][:12]}…) is not "
                         f"the pinned {expected} ({sha256[:12]}…; tools.reviewer.harness_pins)")
    return found


def run(out, prompt, backend, model, effort, label, copies=(), writes=(), limit=HARD_LIMIT, reminder_after=None,
        startup=True, tools=TOOLS, host=None, run_id=None, base=WORK_BASE, record=True, claude=CLAUDE, compact=True,
        report=None, system_prompt=None, deepseek_limits=None, deepseek_base=None):
    """One run. `system_prompt`: command(). `report` (the bound report, relative to the working directory) turns on ARW's early-exit
    continuation (execute_continued) and session persistence; without it the run is the single `claude -p` as before.
    `deepseek_limits`: deepseek_environment() limits of the DeepSeek backend (recorded in binding.json).
    `deepseek_base`: another endpoint for the DeepSeek backend (zero-model gates point it at a loopback mock)."""
    if deepseek_limits and backend != 'deepseek':
        raise ValueError('deepseek_limits apply to the DeepSeek backend only')
    if backend == 'strata' and not compact:
        raise ValueError('The Strata arm keeps the project compact prompt (hard constraint 3)')
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    control = out / 'control'
    control.mkdir()
    run_id = run_id or out.name + '-' + str(time.time_ns())
    work = workspace(run_id, base)
    copy_inputs(work, copies)
    for name in writes:
        (work / name).mkdir(parents=True, exist_ok=True)
    started_file = control / 'started-at.txt'
    reminder_after = reminder_time(limit) if reminder_after is None else reminder_after
    deadline = Deadline(out, limit, reminder_after, scenario=bool(report), run_id=run_id)
    session_settings = settings(work, writes, session_hooks(compact))
    prompt_text = Path(prompt).read_text()
    argv = command(backend, model, effort, work, writes, session_settings, tools, startup, claude, persist=bool(report),
                   system_prompt=system_prompt)
    save(out / 'settings.json', session_settings)
    save(out / 'command.json', [a if not a.startswith(startup_text()[0][:40]) else '<startup prompt>' for a in argv])
    binding = {'backend': backend, 'model': model, 'effort': effort, 'label': label, 'work': str(work),
               'writes': list(writes), 'limit_seconds': limit, 'reminder_after_seconds': reminder_after,
               'tools': tools, 'system_prompt_sha256': hashlib.sha256(system_prompt.encode()).hexdigest() if system_prompt else None,
               'prompt_sha256': hashlib.sha256(prompt_text.encode()).hexdigest(),
               'compact_prompt_sha256': hashlib.sha256(COMPACT.read_bytes()).hexdigest() if compact else None,
               'claude': binary(claude), 'continuation': {'report': report, 'pause_at': EARLY_EXIT_PAUSE_AT,
                                                          'pause_step': EARLY_EXIT_PAUSE_STEP} if report else None}
    if backend in ('anthropic', 'deepseek'):
        binding['startup_instructions'] = ({'enabled': True, 'placement': '--append-system-prompt',
                                            'sha256': startup_text()[1]} if startup else {'enabled': False})
        if backend == 'anthropic':
            env = environment('anthropic', effort, anthropic_home(work.parent), tmp=run_tmp(work))
        else:
            home, config_dir = work.parent / 'home', work.parent / 'claude-config'
            home.mkdir()
            config_dir.mkdir()
            env = environment('deepseek', effort, home, config_dir,
                              deepseek_environment(model, os.environ.get(DEEPSEEK_KEY), deepseek_base or DEEPSEEK_BASE,
                                                   limits=deepseek_limits),
                              tmp=run_tmp(work))
            binding['endpoint'] = deepseek_base or DEEPSEEK_BASE
            binding['deepseek_limits'] = dict(deepseek_limits or {})
        save(out / 'environment-names.json', sorted(env))
        save(out / 'binding.json', binding)
        result = run_segments(out, prompt_text, argv, env, work, limit, started_file, report, deadline)
    else:
        result = strata_run(out, prompt_text, argv, model, effort, work, limit, started_file, binding, startup, host,
                            report, deadline)
    result['reminder'] = deadline.value['reminder']
    result['interrupt'] = deadline.value['interrupt']
    streams = segment_streams(out)
    result['summary'] = stream_summary(streams)
    for name in writes:
        target = work / name
        if target.exists():
            shutil.copytree(target, out / 'outputs' / name, dirs_exist_ok=True)
    result['session_files'] = keep_session_files(work, config_root(backend, work), out)
    result['run_tmp_removed'] = remove_run_tmp(work)  # after the copies above; the stream holds every tool result
    save(out / 'result.json', result)  # the record first: accounting is optional and must never lose it
    if record:  # the last result carries the session's cumulative cost under the one session id
        try:
            result.update(account(accounting_stream(streams), label, effort, out))
        except Exception as error:  # noqa: BLE001 - recorded, the run result stands
            result.update(estimate_exit=None, estimate_note=f'failed: {error!r}')
        save(out / 'result.json', result)
    return result


def run_segments(out, prompt_text, argv, env, work, limit, started_file, report, deadline=None):
    if report:
        return execute_continued(out, prompt_text, argv, env, work, report, limit, started_file, deadline=deadline)
    return execute(out, prompt_text, argv, env, work, limit, started_file, deadline=deadline)


def strata_run(out, prompt_text, argv, model, effort, work, limit, started_file, binding, startup, host, report=None,
               deadline=None, context_window=None, messages=None):
    """Lease, cold start with installation defaults on the published tier (the default one, or `context_window`),
    the same command, engine-log tokens.  `messages` runs a multi-turn conversation instead of one prompt
    (run_turns)."""
    from tools.ops.measurement_host import MeasurementHost
    from tools.ops.deployment_source import published_tier, served_model
    from tools.metrics.prompt_policy import verify_loaded_startup
    from tools.reviewer.arw_measure import log_offset, stop_and_capture_engine_log
    if host is None:
        raise ValueError('The Strata backend needs a registered host')
    quantization = served_model(host)
    if model != 'qwen3.8-flash-next-' + quantization.lower():
        raise ValueError('The Strata arm names the served model, ' + 'qwen3.8-flash-next-' + quantization.lower())
    tier = published_tier(host, quantization, context_window)
    measurement_host = MeasurementHost(host)
    home, config_dir = work.parent / 'home', work.parent / 'claude-config'
    home.mkdir()
    config_dir.mkdir()
    with measurement_host.controller(out / 'controller') as owner:
        offset = log_offset(measurement_host.installation, quantization, measurement_host)
        service_offset = measurement_host.log_offset()
        try:
            options = {'model': quantization, 'context_window': tier['context_window']}
            if not startup:
                options['startup_instructions'] = False
            state, load = owner.start(**options)
            loaded = state['native_health'].get('startup_instructions')
            if startup:
                verify_loaded_startup(loaded, startup_text()[1])
            strata = strata_environment(owner.base, owner.key, model, effort, tier)
            binding.update(startup_instructions=loaded, context_tier=tier, load_seconds=load,
                           measurement_host=measurement_host.metadata(),
                           strata_release=measurement_host.installed_release(),
                           model_environment={k: v for k, v in strata.items() if k in MODEL_ENVIRONMENT_RECORDED})
            env = environment('strata', effort, home, config_dir, strata, tmp=run_tmp(work))
            save(out / 'environment-names.json', sorted(env))
            save(out / 'binding.json', binding)
            if messages is not None:
                result = run_turns(out, messages, argv, env, work, deadline or Deadline(out, limit))
            else:
                result = run_segments(out, prompt_text, argv, env, work, limit, started_file, report, deadline)
        finally:
            # The service log first, then the engine stop, each on its own; with the run's own exception in flight a
            # cleanup failure is written to cleanup-errors.txt instead of replacing it.
            failures, service = [], ''
            try:
                service = measurement_host.log_bytes_since(None, service_offset).decode(errors='replace')
                (out / 'service-log.txt').write_text(service)
            except Exception as error:  # noqa: BLE001
                failures.append(('service log', error))
            try:
                stopped, stages, tokens = stop_and_capture_engine_log(owner, measurement_host.installation, quantization,
                                                                      offset, out, measurement_host)
                save(out / 'engine-stop.json', stopped)
            except Exception as error:  # noqa: BLE001
                failures.append(('engine stop', error))
            if failures:
                if sys.exc_info()[1] is None:
                    raise failures[0][1]
                (out / 'cleanup-errors.txt').write_text(''.join(f'{step}: {error!r}\n' for step, error in failures))
    result.update(engine_requests=stages, engine_tokens=tokens, output_limits=output_limits(service),
                  token_consumption_source='engine log segment of this run (API usage in the stream is diagnostic only)')
    return result


def output_limits(service_log):
    """The thinking budgets and output limits the native service applied to this run's requests, from its progress
    lines ("thinking: n of budget B (max M) tokens", "... of max M tokens"): plan §14 checks them per instance."""
    return {'thinking_budgets': sorted({int(b) for b in re.findall(r'of budget (\d+) \(max \d+\)', service_log)}),
            'max_tokens': sorted({int(m) for m in re.findall(r'\(?max (\d+)\)? tokens', service_log)})}


def parse_copy(value):
    source, _, name = value.rpartition(':')
    if not source or not name:
        raise argparse.ArgumentTypeError('Use SOURCE:NAME')
    return source, name


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--out', type=Path, required=True, help='Run record directory (project .tmp/).')
    parser.add_argument('--prompt', type=Path, required=True, help='Final prompt text; placeholders already filled.')
    parser.add_argument('--backend', choices=BACKENDS, required=True)
    parser.add_argument('--model', required=True, help='Anthropic model (opus, sonnet, haiku or an ID), the served Strata model ID, or the DeepSeek model ID.')
    parser.add_argument('--effort', choices=('low', 'medium', 'high', 'xhigh', 'max'), required=True)
    parser.add_argument('--label', required=True, help='Quota ledger label (estimate.sh --add-stream).')
    parser.add_argument('--copy', type=parse_copy, action='append', default=[], help='SOURCE:NAME copied into the working directory.')
    parser.add_argument('--write', action='append', default=[], help='Working-directory path the run may write (repeatable).')
    parser.add_argument('--limit', type=int, default=HARD_LIMIT, help='Hard limit in seconds (default ARW 3600).')
    parser.add_argument('--reminder-after', type=float, help='Reminder time in seconds (default ARW: limit - 300).')
    parser.add_argument('--no-startup-prompt', action='store_true',
                        help='D4 no-prompt arm, and every API model run of the multi-model benchmark.')
    parser.add_argument('--no-compact-prompt', action='store_true',
                        help='API backends only: no project compact prompt (multi-model benchmark).')
    parser.add_argument('--tools', default=TOOLS)
    parser.add_argument('--host', help='Registered host for the Strata backend.')
    parser.add_argument('--claude', default=CLAUDE, help=f'Claude Code binary; must be the pinned copy ({CLAUDE_VERSION}).')
    args = parser.parse_args()
    pinned_binary(args.claude)
    print(json.dumps(run(args.out, args.prompt, args.backend, args.model, args.effort, args.label, args.copy, args.write,
                         args.limit, args.reminder_after, not args.no_startup_prompt, args.tools, args.host,
                         compact=not args.no_compact_prompt, claude=args.claude),
                     ensure_ascii=False))
