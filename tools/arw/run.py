"""Run ARW Reviewer instances on Strata with the pinned ARW (config/arw-pin.json).

One ARW `reviewer-capability run` is one instance: setup, spawn the Reviewer on the Strata provider, wait, inspect,
repair, score.  ARW owns the model lease and start (the installation's defaults), the 60 minute model work limit and
the scoring.  This module only prepares an isolated HOME (own ARW install and background-agent daemon, so the real
HOME's daemon is never touched), runs instances, and checks that the installation's startup prompt is the project's.

    python3 -m tools.arw.run init   --work DIR
    python3 -m tools.arw.run run    --work DIR --scenario spec-readiness --out OUT --name a1
    python3 -m tools.arw.run check  --work DIR     # /health: lease, loaded startup prompt SHA against the project's
    python3 -m tools.arw.run stop   --work DIR     # stop the isolated daemon by its exact pid
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import time
import urllib.request

from tools.arw import pin as arw_pin
from tools.ops.deployment_source import current_host, frontend_base, served_model, wsl_gateway
from tools.ops.model_catalog import MODELS
from tools.ops.measurement_host import MeasurementHost
from src.startup_instructions import startup_prompt_bytes

ROOT = arw_pin.ROOT
# --- tunables ---
SCENARIOS = {'code-spec': 'requirements-reviewer', 'commit-audit': 'requirements-reviewer',
             'code-standards': 'code-standards-reviewer', 'spec-readiness': 'spec-readiness-reviewer'}
PROVIDER = 'qwen_strata'
EFFORT = 'high'
INSTANCE_WALL = 4500  # s; outer kill of one `run` (ARW's own limit is 3600 s of model work)
STOP_WAIT = 60  # s; daemon exit after SIGTERM
HOME_LINKS = ('.cache', '.config', '.local', '.npm', '.gitconfig')  # read-mostly; no daemon state, no credentials
CODEX_CONFIG = '''[model_providers.qwen_strata]
name = "Qwen Strata"
wire_api = "responses"
requires_openai_auth = false
'''
# --- end tunables ---


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def home_ports(home, user=None):
    """The daemon's control and maintenance ports, the same function ARW derives from user and HOME."""
    user = user or os.environ.get('USER') or Path('~').expanduser().name
    h = int.from_bytes(hashlib.sha256(f'{user}\0{home}'.encode()).digest()[:4], 'big')
    m = int.from_bytes(hashlib.sha256(f'maintenance\0{user}\0{home}'.encode()).digest()[:4], 'big')
    return 30000 + h % 2768, 20000 + m % 10000


def paths(work):
    work = Path(work).resolve()
    return {'work': work, 'home': work / 'home', 'tmp': work / 'tmp', 'install_view': work / 'strata-install',
            'codex_home': work / 'codex-home'}


def strata_install_view(installation, view, gateway):
    """What ARW reads of the installation (config/frontend.json, config/deployment.json, the compact prompt), as a
    directory of its own.  The installation's frontend.json names the adapter (`listen_interface`) and the project's
    callers take the WSL default gateway; the pinned ARW wants `listen_address`, so the view adds it when missing.
    Every other file is a link to the installation's own, byte for byte."""
    installation, view = Path(installation), Path(view)
    if view.exists():
        shutil.rmtree(view)
    (view / 'config/prompts').mkdir(parents=True)
    frontend = json.loads((installation / 'config/frontend.json').read_text())
    if not frontend.get('listen_address'):
        if not gateway:
            raise ValueError('No WSL default gateway to use as the frontend address')
        frontend['listen_address'] = gateway
    (view / 'config/frontend.json').write_text(json.dumps(frontend, indent=2) + '\n')
    for relative in ('config/deployment.json', 'config/prompts/compact-prompt.txt'):
        (view / relative).symlink_to(installation / relative)
    return frontend


def expected_startup_sha(prompt_file=None):
    """SHA-256 of the startup prompt as the frontend loads it (default: without the deprecated loop-prevention block)."""
    raw = Path(prompt_file or ROOT / 'config/prompts/startup-instructions.txt').read_bytes()
    return sha(startup_prompt_bytes(raw, False))


def health(base=None, urlopen=urllib.request.urlopen):
    base = base or frontend_base(MeasurementHost(current_host()).deployment)
    with urlopen(base + '/health', timeout=15) as response:
        return json.load(response)


def startup_binding(health_reply, expected):
    """{ok, reason, loaded, expected} for the loaded startup prompt; only a loaded model can be checked."""
    loaded = (health_reply.get('startup_instructions') or {}).get('sha256')
    if health_reply.get('model') is None or loaded is None:
        return {'ok': None, 'reason': 'no model loaded', 'loaded': loaded, 'expected': expected}
    return {'ok': loaded == expected, 'reason': None if loaded == expected else 'loaded startup prompt differs',
            'loaded': loaded, 'expected': expected}


def environment(work, session):
    p = paths(work)
    env = {k: v for k, v in os.environ.items() if not k.startswith(('CLAUDECODE', 'CLAUDE_CODE', 'CODEX_THREAD'))}
    env.update(HOME=str(p['home']), CODEX_HOME=str(p['codex_home']), CODEX_THREAD_ID=session, TMPDIR=str(p['tmp']))
    for key in ('USAGE_GUARD', 'RUN_RECORD'):
        env.pop(key, None)
    return env


def init(work, host=None, context_window=None):
    """Pinned checkout, isolated HOME with its own ARW install, provider config pointing at the installation view.
    context_window: a published tier the provider selects (ARW `contextWindow`); None keeps the installation's default tier."""
    p = paths(work)
    checkout = arw_pin.ensure()
    for directory in ('home', 'tmp', 'codex_home'):
        p[directory].mkdir(parents=True, exist_ok=True)
    real = Path('~').expanduser()
    for name in HOME_LINKS:
        if (real / name).exists() and not os.path.lexists(p['home'] / name):
            (p['home'] / name).symlink_to(real / name)
    installation = MeasurementHost(host or current_host()).installation
    # The static part of the provider entry belongs to Codex's config.toml (ARW only overrides base_url and the token).
    (p['codex_home'] / 'config.toml').write_text(CODEX_CONFIG)
    # ARW builds the Codex model catalog from `models_cache.json` in the Codex home; the Strata model's entry is the
    # installation's own catalog.  The Codex home holds no login: Strata needs none.
    shutil.copyfile(installation / 'config/model-catalog.json', p['codex_home'] / 'models_cache.json')
    frontend = strata_install_view(installation, p['install_view'], wsl_gateway())
    installed = p['home'] / '.agent-repository-workflow'
    if not (installed / 'manifest.json').exists():
        subprocess.run(['node', str(checkout / 'install.mjs'), '--non-interactive', '--register-path', 'false'],
                       check=True, env=environment(work, 'init'), stdin=subprocess.DEVNULL, timeout=300)
    config = json.loads((installed / 'config.json').read_text())
    provider = {'driver': 'strata', 'maxInstances': 1, 'installationDirectory': str(p['install_view'])}
    if context_window is not None:
        provider['contextWindow'] = context_window
    config['backgroundAgent']['providers'] = {PROVIDER: provider}
    (installed / 'config.json').write_text(json.dumps(config, indent=2) + '\n')
    return {'checkout': str(checkout), 'home': str(p['home']), 'ports': home_ports(str(p['home'])),
            'installation': str(installation), 'frontend': frontend}


def model_id(host=None):
    """ARW model id (catalog slug) of the one model the current host serves."""
    return 'qwen3.8-flash-next-' + MODELS[served_model(host or current_host())]


def settings(model=None, effort=EFFORT):
    model = model or model_id()
    return {'model': model, 'modelProvider': PROVIDER, 'reasoningEffort': effort, 'serviceTier': 'default'}


def scenario_directory(checkout, scenario):
    return Path(checkout) / arw_pin.FIXTURES / SCENARIOS[scenario] / scenario


def run_command(checkout, scenario, instance, settings_value):
    return ['timeout', '-k', '10', str(INSTANCE_WALL), 'node', str(Path(checkout) / 'scripts/reviewer-capability.mjs'),
            'run', str(scenario_directory(checkout, scenario)), str(instance), '--settings', json.dumps(settings_value)]


def parse_result(stdout):
    """ARW prints one JSON object as its last line; anything else is a failed run."""
    try:
        value = json.loads(stdout.strip().splitlines()[-1])
        if isinstance(value, dict):
            return value
    except (ValueError, IndexError):
        pass
    return {'status': 'failed', 'stage': 'parse', 'stdout': stdout[-300:]}


def run_instance(work, scenario, name, session='qs-arw', effort=EFFORT, popen=subprocess.Popen):
    """One ARW instance; its directory is `<checkout>/.tmp/codex/<session>/<name>` (the Skill's layout: the recovery
    records must stay inside the session's temporary directory).  Returns (ARW result, instance directory, seconds)."""
    checkout = arw_pin.ensure()
    instance = checkout / '.tmp/codex' / session / name
    if instance.exists():
        raise ValueError(f'{instance} exists; instance directories are new paths')
    instance.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    process = popen(run_command(checkout, scenario, instance, settings(effort=effort)), cwd=checkout,
                    env=environment(work, session), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, text=True, start_new_session=True)
    out, err = process.communicate()
    result = parse_result(out)
    if process.returncode in (124, 137):
        result = {'status': 'outer-timeout'}
    result.update(_rc=process.returncode, _stderr=err[-500:])
    return result, instance, time.monotonic() - started


def daemon_pid(work):
    """The isolated daemon: pid listening on its control port, checked to run with the isolated HOME."""
    home = str(paths(work)['home'])
    out = subprocess.run(['ss', '-ltnpH', f'sport = :{home_ports(home)[0]}'], capture_output=True, text=True,
                         stdin=subprocess.DEVNULL, timeout=10).stdout
    found = re.search(r'pid=(\d+)', out)
    if not found:
        return None
    try:
        variables = Path(f'/proc/{found.group(1)}/environ').read_bytes().split(b'\0')
    except OSError:
        return None
    return int(found.group(1)) if f'HOME={home}'.encode() in variables else None


def stop(work):
    pid = daemon_pid(work)
    if pid is None:
        return None
    os.kill(pid, signal.SIGTERM)
    deadline = time.monotonic() + STOP_WAIT
    while Path(f'/proc/{pid}').exists() and time.monotonic() < deadline:
        time.sleep(1)
    return pid


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('init', 'run', 'check', 'stop'))
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--scenario', choices=sorted(SCENARIOS))
    parser.add_argument('--name')
    parser.add_argument('--effort', default=EFFORT)
    args = parser.parse_args()
    if args.command == 'init':
        result = init(args.work)
    elif args.command == 'check':
        reply = health()
        result = {'health': reply, 'startup': startup_binding(reply, expected_startup_sha())}
    elif args.command == 'stop':
        result = {'stopped_pid': stop(args.work)}
    else:
        result, instance, seconds = run_instance(args.work, args.scenario, args.name, effort=args.effort)
        result.update(instance=str(instance), seconds=round(seconds))
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == '__main__':
    main()
