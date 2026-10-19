"""Headless Claude Code runs for references, blind adjudication and the Claude Code cross arm.

One runner, one parameter set, three backends (review 2026-10-19, D3/H3): `anthropic` runs the named Anthropic model
with the real configuration directory; `strata` takes the frontend lease, starts the served model with the
installation defaults and points the same Claude Code command at the frontend; `deepseek` points the same command at
DeepSeek's Anthropic-format endpoint with a fresh configuration directory and the key from BENCHMARK_DEEPSEEK_API_KEY
(multi-model benchmark, user 2026-10-19). The DeepSeek model is always named explicitly in every model variable,
because the endpoint maps Claude model names such as claude-opus-* to another model. The cross arm never goes through
qwen-approve or qwen-agent's own settings: only qwen-agent's model environment is reused.

Isolation (measurement rule "Claude Code 测试隔离"):
- a minimal environment instead of the caller's (the same effect as `env -i`): PATH, HOME, LANG, TERM and the backend's
  variables; the Strata arm also gets a fresh CLAUDE_CONFIG_DIR;
- `--setting-sources ""`, `--restricted` (file tools confined to the working directory), `--strict-mcp-config`,
  `--disable-slash-commands`, `--permission-mode dontAsk`, `--permission-prompts none`, `--no-session-persistence`;
- the working directory lives under WORK_BASE, outside /home/pello, so no ancestor CLAUDE.md applies;
- the Bash sandbox reads only the working directory, writes only the granted paths and has no network; a new file at the
  top of the working directory stays writable (the sandbox always grants the working directory, see settings());
- web tools are off twice: `--tools` lists none and `--disallowedTools WebSearch,WebFetch` denies them (benchmark
  search rule, user 2026-10-19); tools.safety.claude_gate checks that no request offers a search tool;
- CLAUDE_CODE_SUBPROCESS_ENV_SCRUB=1 keeps the backend key out of command environments: without it the mock gate saw
  ANTHROPIC_AUTH_TOKEN in the shell (2026-10-19).
`--safe-mode` is not used: it also disables the hooks that carry the time reminder and the project compact prompt;
tools.safety.claude_gate checks that the real configuration's CLAUDE.md, hooks and skills still stay out.

Time limit as ARW (tools.reviewer.review_deadlines): a PostToolUse hook adds the original reminder once the run has
worked REMINDER seconds, and the process group is stopped at the hard limit. The reminder can only arrive after a
tool call. At the end `~/.claude/statusline/estimate.sh --add-stream <stream> <label> --effort <level>` records the run.

    python3 -m tools.reviewer.claude_headless --out .tmp/<work>/<run> --prompt prompt.md --backend anthropic \\
        --model opus --effort high --label <label> --copy <source>:<name> --write <name>/<report dir>
"""
import argparse
import fnmatch
import hashlib
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time

from tools.reviewer.review_deadlines import LIMITS, REMINDER
from tools.reviewer.wsl_client import ROOT, save

sys.path.append(str(ROOT / 'src'))
from startup_instructions import startup_prompt_bytes

# Tunables
WORK_BASE = Path('/var/tmp/qwen-claude')  # isolated working directories, outside /home/pello
TOOLS = 'Read,Write,Edit,Glob,Grep,Bash'  # no web tools: search stays a separate decision (D5)
DISALLOWED = 'WebSearch,WebFetch'  # denied as well, whatever --tools lists (benchmark: search off, user 2026-10-19)
REMINDER_AFTER, HARD_LIMIT = LIMITS['initial']  # 3300 s, 3600 s
ESTIMATE = Path.home() / '.claude/statusline/estimate.sh'
CLAUDE = 'claude'
AGENT = ROOT / 'scripts/wsl/qwen-agent'
# Named directories, not top-level ones: Claude Code 2.1.303 left /home readable to sandboxed commands with denyRead
# ["/home"], while /home/pello was denied (tools.safety.claude_gate, 2026-10-19). The working directory is re-opened
# by allowRead inside WORK_BASE.
DENY_READ = [str(Path.home()), '/root', '/mnt/c', '/mnt/wsl', '/mnt/wslg', str(WORK_BASE), '/etc/claude-code']
# Inputs that never belong in a working directory: credentials, private state and answer material.
FORBIDDEN = ['project.private.toml', 'installation.private.toml', '.credentials.json', '.claude.json', '.state',
             'key*.json', 'expected*.json', 'judgment']
STARTUP = ROOT / 'config/prompts/startup-instructions.txt'
COMPACT = ROOT / 'config/prompts/compact-prompt.txt'
BACKENDS = ('anthropic', 'strata', 'deepseek')
DEEPSEEK_BASE = 'https://api.deepseek.com/anthropic'
DEEPSEEK_KEY = 'BENCHMARK_DEEPSEEK_API_KEY'
DEEPSEEK_MODEL = re.compile(r'deepseek-[a-z0-9][a-z0-9.-]*')
# Every variable that names a model for some request kind; all of them name the DeepSeek model.
DEEPSEEK_MODEL_VARIABLES = ('ANTHROPIC_MODEL', 'ANTHROPIC_SMALL_FAST_MODEL', 'ANTHROPIC_DEFAULT_OPUS_MODEL',
                            'ANTHROPIC_DEFAULT_SONNET_MODEL', 'ANTHROPIC_DEFAULT_HAIKU_MODEL', 'CLAUDE_CODE_SUBAGENT_MODEL')


def workspace(run_id, base=WORK_BASE):
    """A fresh working directory outside /home/pello; its parent holds only this run."""
    root = Path(base) / run_id
    work = root / 'work'
    if str(work.resolve()).startswith('/home/'):
        raise ValueError('The isolated working directory must be outside /home')
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


def write_targets(work, writes):
    targets = [(work / w).resolve() for w in writes]
    for target in targets:
        if work.resolve() not in target.parents:
            raise ValueError('Write grants stay inside the working directory')
    return targets


def reminder_hook(control, started_file, after=REMINDER_AFTER, text=REMINDER):
    """PostToolUse hook: once the run has worked `after` seconds, add the ARW reminder to the model context, once."""
    script = control / 'deadline-reminder.py'
    flag = control / 'reminder-sent.json'
    script.write_text(
        'import json,sys,time\nfrom pathlib import Path\n'
        f'started=float(Path({str(started_file)!r}).read_text());flag=Path({str(flag)!r})\n'
        f'if time.time()-started>={after!r} and not flag.exists():\n'
        ' flag.write_text(json.dumps({"sent_at":time.time(),"elapsed":time.time()-started}))\n'
        f' print(json.dumps({{"hookSpecificOutput":{{"hookEventName":"PostToolUse","additionalContext":{text!r}}}}},ensure_ascii=False))\n')
    return {'type': 'command', 'command': f'{sys.executable} {script}'}, flag


def reminder_time(limit):
    """ARW's lead before the hard limit (300 s of 3600); half the limit when the limit is shorter than two leads."""
    lead = HARD_LIMIT - REMINDER_AFTER
    return limit - lead if limit >= 2 * lead else limit / 2


def session_hooks(control, started_file, reminder_after):
    """The time reminder after tool calls, and the project compact prompt appended to Claude Code's own summary
    instructions, never replacing them (as qwen-agent does)."""
    hook, flag = reminder_hook(control, started_file, reminder_after)
    return {'PostToolUse': [{'matcher': '*', 'hooks': [hook]}],
            'PreCompact': [{'hooks': [{'type': 'command', 'command': f'cat {COMPACT}'}]}]}, flag


def settings(work, writes, hooks):
    """Session settings passed with --settings; no user, project or local settings file is read."""
    targets = write_targets(work, writes)
    # The sandbox always lets commands write in the working directory; denying the directory itself breaks bwrap
    # (it creates placeholders such as .git and scripts there), so every existing entry outside the grants is denied
    # and a new file at the top of the working directory stays possible (tools.safety.claude_gate records it).
    deny_write = [str(p) for p in sorted(work.iterdir())
                  if not any(p.resolve() == t or p.resolve() in t.parents for t in targets)]
    return {'autoMemoryEnabled': False, 'includeGitInstructions': False,
            'sandbox': {'enabled': True, 'autoAllowBashIfSandboxed': True, 'allowUnsandboxedCommands': False,
                        'filesystem': {'denyRead': list(DENY_READ), 'allowRead': [str(work)],
                                       'denyWrite': deny_write, 'allowWrite': [str(t) for t in targets]},
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


def command(backend, model, effort, work, writes, session_settings, tools=TOOLS, startup=True, claude=CLAUDE):
    """The Claude Code command. All backends get the same flags; the startup prompt is appended here for API models
    and by the service for Strata, so each model sees it once (D4). The multi-model benchmark gives it only to Strata,
    so its API runs pass startup=False (--no-startup-prompt)."""
    if backend not in BACKENDS:
        raise ValueError('Unknown backend')
    if backend == 'deepseek':
        deepseek_model(model)
    argv = [claude, '-p', '--model', model, '--effort', effort, '--restricted', '--strict-mcp-config',
            '--disable-slash-commands', '--setting-sources', '', '--settings', json.dumps(session_settings),
            '--tools', tools, '--disallowedTools', DISALLOWED, '--permission-mode', 'dontAsk', '--permission-prompts', 'none',
            '--allowedTools', allowed_tools(work, writes),
            '--output-format', 'stream-json', '--verbose', '--no-session-persistence']
    if backend != 'strata' and startup:
        argv += ['--append-system-prompt', startup_text()[0]]
    return argv


def strata_environment(base, key, model, effort, tier):
    """qwen-agent's model variables for Claude Code (window, output, effort, compaction point), nothing else."""
    loader = SourceFileLoader('qwen_agent', str(AGENT))
    agent = module_from_spec(spec_from_loader('qwen_agent', loader))
    loader.exec_module(agent)
    frontend = type('Frontend', (), {'base': base, 'key': key})()
    return agent.claude(frontend, model, effort, tier, [])[1]


def deepseek_environment(model, key, base=DEEPSEEK_BASE):
    """DeepSeek's Anthropic-format endpoint: the key as the bearer token, the model named in every model variable."""
    if not key:
        raise ValueError('The DeepSeek backend needs ' + DEEPSEEK_KEY)
    return {'ANTHROPIC_BASE_URL': base, 'ANTHROPIC_AUTH_TOKEN': key, 'CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC': '1',
            **{name: deepseek_model(model) for name in DEEPSEEK_MODEL_VARIABLES}}


def environment(backend, effort, home=None, config_dir=None, strata=None):
    """Minimal environment, the effect of `env -i`: no variable of the calling session reaches Claude Code.
    `strata` is the backend's model environment (Strata's from qwen-agent, or deepseek_environment())."""
    env = {'PATH': os.environ.get('PATH', '/usr/bin:/bin'), 'LANG': 'C.UTF-8', 'TERM': 'dumb',
           'DISABLE_AUTOUPDATER': '1', 'CLAUDE_CODE_EFFORT_LEVEL': effort, 'CLAUDE_CODE_SUBPROCESS_ENV_SCRUB': '1'}
    if backend == 'anthropic':
        # The real configuration directory supplies only the subscription login; --setting-sources "" keeps its
        # settings, hooks and CLAUDE.md out (verified by tools.safety.claude_gate).
        env['HOME'] = str(home or Path.home())
        if config_dir:
            env['CLAUDE_CONFIG_DIR'] = str(config_dir)
    else:
        if not (home and config_dir and strata):
            raise ValueError('This backend needs a fresh HOME, CLAUDE_CONFIG_DIR and its model environment')
        env.update(HOME=str(home), CLAUDE_CONFIG_DIR=str(config_dir), **strata)
    return env


def stream_summary(stream):
    """The result event of a stream-json run: usage, cost, turns and durations as Claude Code reports them."""
    result = None
    try:
        lines = Path(stream).read_text(errors='replace').splitlines()
    except OSError:
        lines = []
    init = None
    tiers, seen = {}, set()
    for line in lines:
        try:
            event = json.loads(line)
        except ValueError:
            continue
        message = event.get('message') if event.get('type') == 'assistant' else None
        usage = message.get('usage') if isinstance(message, dict) else None
        if isinstance(usage, dict) and message.get('id') not in seen:
            # D14: the tier the API returned for each assistant message (stream-json repeats a message once per
            # content block, so it counts once by id); the absence is counted, not filled in.
            seen.add(message.get('id'))
            tier = usage.get('service_tier') or 'not-returned'
            tiers[tier] = tiers.get(tier, 0) + 1
        if event.get('type') == 'system' and event.get('subtype') == 'init' and init is None:
            init = {k: event.get(k) for k in ('model', 'tools', 'mcp_servers', 'permissionMode', 'claude_code_version')}
        if event.get('type') == 'result':
            result = event
    if result is None:
        return {'result_event': False, 'init': init, 'service_tiers': tiers}
    keep = ('subtype', 'is_error', 'duration_ms', 'duration_api_ms', 'num_turns', 'total_cost_usd', 'usage', 'modelUsage')
    server_tools = (result.get('usage') or {}).get('server_tool_use') or {}
    searches = (server_tools.get('web_search_requests') or 0) + (server_tools.get('web_fetch_requests') or 0)
    return {'result_event': True, 'init': init, **{k: result.get(k) for k in keep}, 'service_tiers': tiers,
            'server_web_requests': searches,
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


def execute(out, prompt_text, argv, env, work, limit=HARD_LIMIT, started_file=None, on_start=None):
    """Run once with the prompt on stdin; stop the whole process group at the hard limit."""
    stream, errors = out / 'stream.jsonl', out / 'stream.err'
    before = file_hashes(work)
    save(out / 'files-before.json', before)
    with stream.open('wb') as stdout, errors.open('wb') as stderr:
        started = time.time()
        if started_file:
            Path(started_file).write_text(repr(started))
        process = subprocess.Popen(argv, cwd=work, env=env, stdin=subprocess.PIPE, stdout=stdout, stderr=stderr,
                                   start_new_session=True)
        if on_start:
            prompt_text = on_start(process, prompt_text)
        (out / 'prompt-sent.md').write_text(prompt_text)
        process.stdin.write(prompt_text.encode())
        process.stdin.close()
        timed_out = False
        try:
            code = process.wait(timeout=limit)
        except subprocess.TimeoutExpired:
            timed_out = True
            stop_group(process)
            code = process.returncode
        ended = time.time()
    after = file_hashes(work)
    save(out / 'files-after.json', after)
    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    return {'exit': code, 'hard_interrupt': timed_out, 'started_at': started, 'ended_at': ended,
            'wall_seconds': ended - started, 'pid': process.pid, 'changed_files': changed}


def account(stream, label, effort, out, estimate=ESTIMATE):
    """Add this run to the quota ledger; the script itself ignores models that are not Anthropic's."""
    done = subprocess.run([str(estimate), '--add-stream', str(stream), label, '--effort', effort],
                          capture_output=True, text=True)
    (out / 'add-stream.out').write_text(done.stdout + done.stderr)
    return done.returncode


def run(out, prompt, backend, model, effort, label, copies=(), writes=(), limit=HARD_LIMIT, reminder_after=None,
        startup=True, tools=TOOLS, host=None, run_id=None, base=WORK_BASE, record=True, claude=CLAUDE):
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
    hooks, flag = session_hooks(control, started_file, reminder_after)
    session_settings = settings(work, writes, hooks)
    prompt_text = Path(prompt).read_text()
    argv = command(backend, model, effort, work, writes, session_settings, tools, startup, claude)
    save(out / 'settings.json', session_settings)
    save(out / 'command.json', [a if not a.startswith(startup_text()[0][:40]) else '<startup prompt>' for a in argv])
    binding = {'backend': backend, 'model': model, 'effort': effort, 'label': label, 'work': str(work),
               'writes': list(writes), 'limit_seconds': limit, 'reminder_after_seconds': reminder_after,
               'tools': tools, 'prompt_sha256': hashlib.sha256(prompt_text.encode()).hexdigest(),
               'compact_prompt_sha256': hashlib.sha256(COMPACT.read_bytes()).hexdigest(),
               'claude_version': subprocess.run([claude, '--version'], capture_output=True, text=True).stdout.strip()}
    if backend in ('anthropic', 'deepseek'):
        binding['startup_instructions'] = ({'enabled': True, 'placement': '--append-system-prompt',
                                            'sha256': startup_text()[1]} if startup else {'enabled': False})
        if backend == 'anthropic':
            env = environment('anthropic', effort)
        else:
            home, config_dir = work.parent / 'home', work.parent / 'claude-config'
            home.mkdir()
            config_dir.mkdir()
            env = environment('deepseek', effort, home, config_dir,
                              deepseek_environment(model, os.environ.get(DEEPSEEK_KEY)))
            binding['endpoint'] = DEEPSEEK_BASE
        save(out / 'environment-names.json', sorted(env))
        save(out / 'binding.json', binding)
        result = execute(out, prompt_text, argv, env, work, limit, started_file)
    else:
        result = strata_run(out, prompt_text, argv, model, effort, work, limit, started_file, binding, startup, host)
    result['reminder'] = json.loads(flag.read_text()) if flag.exists() else None
    result['summary'] = stream_summary(out / 'stream.jsonl')
    for name in writes:
        target = work / name
        if target.exists():
            shutil.copytree(target, out / 'outputs' / name, dirs_exist_ok=True)
    if record:
        result['estimate_exit'] = account(out / 'stream.jsonl', label, effort, out)
    save(out / 'result.json', result)
    return result


def strata_run(out, prompt_text, argv, model, effort, work, limit, started_file, binding, startup, host):
    """Lease, cold start with installation defaults on the published tier, the same command, engine-log tokens."""
    from tools.ops.measurement_host import MeasurementHost
    from tools.ops.deployment_source import published_tier, served_model
    from tools.metrics.prompt_policy import verify_loaded_startup
    from tools.reviewer.arw_measure import log_offset, stop_and_capture_engine_log
    if host is None:
        raise ValueError('The Strata backend needs a registered host')
    quantization = served_model(host)
    if model != 'qwen3.8-flash-next-' + quantization.lower():
        raise ValueError('The Strata arm names the served model, ' + 'qwen3.8-flash-next-' + quantization.lower())
    tier = published_tier(host, quantization)
    measurement_host = MeasurementHost(host)
    home, config_dir = work.parent / 'home', work.parent / 'claude-config'
    home.mkdir()
    config_dir.mkdir()
    with measurement_host.controller(out / 'controller') as owner:
        offset = log_offset(measurement_host.installation, quantization, measurement_host)
        try:
            options = {'model': quantization, 'context_window': tier['context_window']}
            if not startup:
                options['startup_instructions'] = False
            state, load = owner.start(**options)
            loaded = state['native_health'].get('startup_instructions')
            if startup:
                verify_loaded_startup(loaded, startup_text()[1])
            binding.update(startup_instructions=loaded, context_tier=tier, load_seconds=load,
                           measurement_host=measurement_host.metadata())
            strata = strata_environment(owner.base, owner.key, model, effort, tier)
            env = environment('strata', effort, home, config_dir, strata)
            save(out / 'environment-names.json', sorted(env))
            save(out / 'binding.json', binding)
            result = execute(out, prompt_text, argv, env, work, limit, started_file)
        finally:
            stopped, stages, tokens = stop_and_capture_engine_log(owner, measurement_host.installation, quantization,
                                                                  offset, out, measurement_host)
            save(out / 'engine-stop.json', stopped)
    result.update(engine_requests=stages, engine_tokens=tokens,
                  token_consumption_source='engine log segment of this run (API usage in the stream is diagnostic only)')
    return result


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
    parser.add_argument('--tools', default=TOOLS)
    parser.add_argument('--host', help='Registered host for the Strata backend.')
    args = parser.parse_args()
    print(json.dumps(run(args.out, args.prompt, args.backend, args.model, args.effort, args.label, args.copy, args.write,
                         args.limit, args.reminder_after, not args.no_startup_prompt, args.tools, args.host),
                     ensure_ascii=False))
