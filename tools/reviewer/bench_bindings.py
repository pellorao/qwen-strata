"""SHA bindings of a multi-model benchmark suite: record them (--write) or recompute them all and compare (--check).

The bindings (benchmarks/multi-model-<suite>/bindings.json, plan.md "绑定" section) are:
- files: every input file by repo-relative path and sha256 - the scenario plans, their source manifests and the archives,
  compatibility patches, scoring and harness patches those name, measurement notes, briefs, anchor registries, the
  judgment registry, the format-baseline registries, the base prompts, the API-arm catalogs, the Strata arm's host deployment JSON;
- harness: the Codex and Claude Code benchmark copies of tools/reviewer/harness_pins.py, hashed on disk, plus --version;
- prompts: startup prompt source and as loaded (loop-prevention block off, the only-Strata rule), compact prompt;
- roles: per plan and handoff the Role / system-prompt sha256 (tools.safety.claude_role_gate, zero model, ~3 minutes);
- code: every file of CODE_FILES (the run, gate, record and scoring code that sets a condition or a score at run time)
  by repo-relative path and sha256. The freeze commit is the code binding; this section lets --check name each file
  changed after it, so every such change is recorded as a deviation (v1 plan section 14.1).
Besides equality with the record, --check verifies that what each plan states about itself (manifest, note, Codex sha)
and what each manifest states about its archive and patches matches the files, and that the format-baseline archives
verify (an `inheritsFrom` entry against the archive of the suite it inherits from). The plan.md of the suite is not bound here (it holds the record); it is bound by the freeze commit.

    python3 -m tools.reviewer.bench_bindings --suite v2 --check [--no-roles]
    python3 -m tools.reviewer.bench_bindings --suite v2 --write     (after any change to a bound file)
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

from tools.reviewer import bench_suite, freeze_arw_source as freeze, harness_pins as pins

ROOT = Path(__file__).resolve().parents[2]
V1_SUITE = ROOT / 'benchmarks/reviewer-suite-v1'
SUITE_DIRS = {'v2': ROOT / 'benchmarks/multi-model-v2'}
CATALOGS = ROOT / 'benchmarks/multi-model-v1/catalogs'
PROMPTS = ROOT / 'config/prompts'
BASE_NOTE = V1_SUITE / 'measurement-note.txt'
# Code that sets a run condition or a score at run time (F15 M1). Left out: wsl_client (paths and file writes), the
# reporting tools benchmark_summary / benchmark_export (no condition, no score), src/startup_instructions.py (its output
# is bound as prompts.startup_loaded_sha256), src/output_limit.py and src/frontend.py (bound as deployed, plan F14).
CODE_FILES = (
    # Claude Code arms: runner, deadlines and high-priority reminders, harness pins
    'tools/reviewer/claude_scenario.py', 'tools/reviewer/claude_headless.py', 'tools/reviewer/review_deadlines.py',
    'tools/reviewer/reminder_interrupt.py', 'tools/reviewer/harness_pins.py',
    # Codex arms: plan prepare, ARW runtime and its setup (deny-read, shell exclude), API relay, scenario freeze
    'tools/tuning/arw_dimension.py', 'tools/reviewer/arw_measure.py', 'tools/reviewer/arw_runtime.mjs',
    'tools/reviewer/arw_native_setup.mjs', 'tools/reviewer/providers.py', 'tools/reviewer/api_relay.py',
    'tools/reviewer/freeze_arw_source.py',
    # safety gates and session inspection
    'tools/safety/claude_gate.py', 'tools/safety/safety_gate.py', 'tools/reviewer/inspect_session.py',
    # records, validity and scoring
    'tools/reviewer/bench_suite.py', 'tools/reviewer/bench_records.py', 'tools/reviewer/bench_validity.py',
    'tools/reviewer/bench_score.py', 'tools/reviewer/single_scenario_score.py', 'tools/reviewer/arw_native.mjs',
    'tools/reviewer/format_penalty.py', 'tools/reviewer/repair_reviewer_report.py', 'tools/reviewer/blind_pool.py',
)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def rel(path):
    path = Path(path).resolve()
    return str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)


def plan_files(plan_path, problems):
    """Files one scenario plan pulls in; consistency findings (what the plan or manifest says against the file) go to problems."""
    plan = json.loads(Path(plan_path).read_text())
    fixed = plan['fixed_conditions']
    files = [plan_path]

    def agrees(path, claimed, what):
        if claimed is not None and sha(path) != claimed:
            problems.append(f'{rel(plan_path)}: {what} sha256 {claimed[:8]} but {rel(path)} is {sha(path)[:8]}')

    manifest_path = ROOT / fixed['arw_source_manifest']
    agrees(manifest_path, fixed.get('arw_source_manifest_sha256'), 'manifest')
    files.append(manifest_path)
    manifest = json.loads(manifest_path.read_text())
    archive = (manifest_path.parent / manifest['snapshot']['file']).resolve()
    agrees(archive, manifest['snapshot']['sha256'], 'snapshot')
    files.append(archive)
    for entry in manifest.get('patches', []):
        patch = (archive.parent / entry['file']).resolve()
        agrees(patch, entry['sha256'], f"manifest patch {entry['file']}")
        files.append(patch)
    note = ROOT / fixed['measurement_note_path'] if fixed.get('measurement_note_path') else BASE_NOTE
    agrees(note, fixed.get('measurement_note_sha256'), 'measurement note')
    files.append(note)
    template = fixed.get('measurement_note_template')
    if template:
        agrees(ROOT / template['path'], template['sha256'], 'measurement note template')
        files.append(ROOT / template['path'])
    for name in fixed.get('codex_harness_patches', []):
        entry = freeze.HARNESS_PATCHES[name]
        agrees(freeze.PATCHES / entry['file'], entry['sha256'], f'harness patch {name}')
        files.append(freeze.PATCHES / entry['file'])
    if fixed['codex'] != pins.CODEX_VERSION or fixed['native_cli_sha256'] != pins.CODEX_SHA256:
        problems.append(f'{rel(plan_path)}: codex {fixed["codex"]} {fixed["native_cli_sha256"][:8]} differs from harness_pins')
    return files


def collect_files(suite, problems):
    spec = bench_suite.suite(suite)
    files = []
    for scenario in spec['scenarios']:
        files += plan_files(bench_suite.plan_path(suite, scenario), problems)
        files += [bench_suite.brief_path(suite, scenario), spec['anchors'] / f'{scenario}.json']
    scoring = [(freeze.SCORING_UPGRADE, freeze.PATCHES), (freeze.SCORING_OVERLAY, freeze.V2_PATCHES)]
    for entry, directory in scoring:
        files.append(directory / entry['file'])
        if sha(directory / entry['file']) != entry['sha256']:
            problems.append(f"scoring patch {entry['file']} is {sha(directory / entry['file'])[:8]}, freeze_arw_source says {entry['sha256'][:8]}")
    files += sorted((V1_SUITE / 'judgment').glob('*'))
    files += [V1_SUITE / 'format-baseline.json', SUITE_DIRS[suite] / 'format-baseline.json']
    files += [PROMPTS / 'startup-instructions.txt', PROMPTS / 'compact-prompt.txt']
    files += sorted(CATALOGS.glob('*.json'))
    files.append(ROOT / 'config/deployments/rtx3080ti.json')  # the Strata arm's host (the one host that is online)
    return {rel(f): sha(f) for f in sorted(set(Path(f).resolve() for f in files))}


def code_files(problems, names=CODE_FILES):
    out = {}
    for name in names:
        if (ROOT / name).is_file():
            out[name] = sha(ROOT / name)
        else:
            problems.append(f'code file {name} is missing')
    return out


def version(binary):
    out = subprocess.run([str(binary), '--version'], capture_output=True, text=True, timeout=60)
    return (out.stdout or out.stderr).strip()


def harness():
    return {'codex': {'version': pins.CODEX_VERSION, 'path': str(pins.CODEX), 'sha256': sha(pins.CODEX),
                      'reports': version(pins.CODEX), 'pinned_sha256': pins.CODEX_SHA256},
            'claude': {'version': pins.CLAUDE_VERSION, 'path': str(pins.CLAUDE), 'sha256': sha(pins.CLAUDE),
                       'reports': version(pins.CLAUDE), 'pinned_sha256': pins.CLAUDE_SHA256}}


def prompts():
    from tools.reviewer import claude_headless as ch
    return {'startup_source_sha256': sha(PROMPTS / 'startup-instructions.txt'), 'startup_loaded_sha256': ch.startup_text()[1],
            'compact_sha256': sha(PROMPTS / 'compact-prompt.txt')}


def roles(suite, work):
    """Role / system-prompt sha256 per plan and handoff, from the Role gate (judged on the requests a mock received)."""
    from tools.safety import claude_role_gate
    out = {}
    for scenario in bench_suite.suite(suite)['scenarios']:
        summary = claude_role_gate.check_plan(Path(work) / scenario, scenario, claude_role_gate.PLANS[scenario])
        if not summary['pass']:
            raise ValueError(f'Role gate failed for {scenario}')
        out[scenario] = [{'handoff': h['handoff'], 'role_bytes': h['role_bytes'], 'system_sha256': h['system_sha256']}
                         for h in summary['handoffs']]
    return out


def baseline_problems(suite):
    from tools.reviewer import format_penalty
    problems = []
    registry = format_penalty.suite_registry(suite)
    for reviewer, keys in json.loads(registry.read_text()).items():
        for key, entry in keys.items():
            source = registry
            try:
                if entry.get('inheritsFrom'):
                    source = format_penalty.suite_registry(entry['inheritsFrom'])
                    entry = json.loads(source.read_text()).get(reviewer, {}).get(key)
                    if not isinstance(entry, dict):
                        raise ValueError(f'not registered in {rel(source)}')
                format_penalty.verify_archive(entry, source.parent / 'format-baseline')
                format_penalty.registered_baseline(reviewer, key, registry)
            except (ValueError, OSError) as error:
                problems.append(f'format baseline {reviewer} {key[:8]}: {error}')
    return problems


def collect(suite, with_roles=True, work=None):
    problems = []
    data = {'suite': suite, 'files': collect_files(suite, problems), 'code': code_files(problems), 'harness': harness(),
            'prompts': prompts()}
    for name, item in data['harness'].items():
        if item['sha256'] != item['pinned_sha256'] or item['version'] not in item['reports']:
            problems.append(f'{name} copy differs from harness_pins: {item}')
    problems += baseline_problems(suite)
    if with_roles:
        work = Path(work or ROOT / '.tmp/bench-bindings-roles')
        shutil.rmtree(work, ignore_errors=True)
        try:
            data['roles'] = roles(suite, work)
        finally:
            shutil.rmtree(work, ignore_errors=True)
    return data, problems


def differences(recorded, actual):
    """Lines naming every binding whose recomputed value differs from the record (sections absent from actual are skipped)."""
    out = []
    for section, value in actual.items():
        if section in ('files', 'code'):
            names = set(value) | set(recorded.get(section, {}))
            for name in sorted(names):
                old, new = recorded.get(section, {}).get(name), value.get(name)
                if old != new:
                    out.append(f'{section} {name}: recorded {str(old)[:12]}, now {str(new)[:12]}')
        elif recorded.get(section) != value:
            out.append(f'{section}: recorded {json.dumps(recorded.get(section))}, now {json.dumps(value)}')
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--suite', choices=sorted(SUITE_DIRS), required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check', action='store_true')
    mode.add_argument('--write', action='store_true')
    parser.add_argument('--no-roles', action='store_true', help='skip the Role gate (~3 minutes); roles are then not compared')
    args = parser.parse_args(argv)
    path = SUITE_DIRS[args.suite] / 'bindings.json'
    data, problems = collect(args.suite, not args.no_roles)
    if args.write:
        if problems:
            print('\n'.join('FAIL ' + p for p in problems))
            return 1
        path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + '\n')
        print(f'wrote {rel(path)}: {len(data["files"])} files, {len(data["code"])} code files')
        return 0
    found = problems + differences(json.loads(path.read_text()), data)
    print('\n'.join('FAIL ' + p for p in found) if found else f'OK  {len(data["files"])} files, {len(data["code"])} code files, 2 harness copies, prompts'
          + ('' if args.no_roles else ', roles') + ' match ' + rel(path))
    return 1 if found else 0


if __name__ == '__main__':
    sys.exit(main())
