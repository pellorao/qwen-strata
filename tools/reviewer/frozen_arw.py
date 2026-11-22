"""The frozen-ARW (760007c, benchmark v1) preparation: a zero-model ARW batch from a frozen manifest, with the plan's
measurement note and Codex binding.  Only the v1 scoring pipeline (bench_score, claude_scenario, adjudication_view)
still reads it; new measurements go through the pinned ARW (tools.arw), and this module goes with the v1 suite."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from tools.ops.deployment_source import source_bytes
from tools.reviewer.harness_pins import codex_binary
from tools.tuning.arw_dimension import ROOT, save, sha

CATALOG = 'config/model-catalog.json'
MEASUREMENT_NOTE = 'benchmarks/reviewer-suite-v1/measurement-note.txt'
# Scenario versions whose handoff needs its own measurement note: (reviewer, source manifest file) -> (plain note,
# time-limit template). Commit Audit v2, v3 and v3.1 (multi-model benchmark v2 draft) declare merged issue/spec
# requirements, which the note explains (user 2026-10-17).
COMMIT_AUDIT_NOTES = ('benchmarks/reviewer-suite-v1/measurement-note-commit-audit.txt',
                      'benchmarks/reviewer-suite-v1/measurement-note-time-limit-commit-audit.txt')
SCENARIO_NOTES = {
    ('commit-audit-reviewer', 'manifest-commit-audit-v2.json'): COMMIT_AUDIT_NOTES,
    ('commit-audit-reviewer', 'manifest-commit-audit-v3.json'): COMMIT_AUDIT_NOTES,
    ('commit-audit-reviewer', 'manifest-commit-audit-v3.1.json'): COMMIT_AUDIT_NOTES,
}


def extract_agent_config(manual):
    """The Codex config block of ARW's agent-cli manual, as prepare.sh took it."""
    section = re.search(r'如果使用 Codex(.*?)如果使用 Claude Code', manual, re.S)
    block = section and re.search(r'^```json\n(.*?)^```$', section.group(1), re.S | re.M)
    if not block:
        raise ValueError('agent-cli manual has no Codex config block')
    json.loads(block.group(1))
    return block.group(1)


def time_limited_note(fixed, folder, time_limit_seconds):
    """Render the plan's note template with this batch's review time limit into the batch folder."""
    template = fixed['measurement_note_template']
    raw = (ROOT / template['path']).read_bytes()
    if sha(raw) != template['sha256']:
        raise ValueError('Measurement note template differs from the frozen plan')
    if type(time_limit_seconds) is not int or time_limit_seconds <= 0:
        raise ValueError('A time-limited plan needs a positive whole number of seconds')
    text = raw.decode().replace('{{time_limit_minutes}}', f'{time_limit_seconds / 60:.1f}'.removesuffix('.0'))
    if '{{' in text:
        raise ValueError('Measurement note template has an unrendered placeholder')
    rendered = folder / 'measurement-note.txt'
    rendered.write_text(text)
    # A prep outside the project (OpenAI arm, /tmp) keeps the absolute path; readers join it onto ROOT.
    path = rendered.relative_to(ROOT) if rendered.is_relative_to(ROOT) else rendered
    return ({'path': str(path), 'sha256': sha(text.encode())},
            {'measurement_note_template': template, 'review_time_limit_seconds': time_limit_seconds})


def plain_note(fixed):
    """The plan's frozen measurement note: the common note, or the scenario note the plan names (e.g. Commit Audit
    adds how repeated issue and spec requirements are scored, user 2026-10-17)."""
    path = fixed.get('measurement_note_path', MEASUREMENT_NOTE)
    raw = (ROOT / path).read_bytes()
    if sha(raw) != fixed['measurement_note_sha256']:
        raise ValueError('Measurement note differs from the frozen plan')
    return {'path': path, 'sha256': sha(raw)}


def required_scenario_note(fixed, reviewer):
    """Refuse a plan that would hand a scenario needing its own note (SCENARIO_NOTES) the common note or another one,
    instead of falling back silently."""
    wanted = SCENARIO_NOTES.get((reviewer, Path(fixed['arw_source_manifest']).name))
    if wanted is None:
        return
    limited = 'measurement_note_template' in fixed
    named = fixed['measurement_note_template']['path'] if limited else fixed.get('measurement_note_path')
    if named is None or Path(named) != Path(wanted[limited]):
        raise ValueError(f"{reviewer} on {Path(fixed['arw_source_manifest']).name} needs the measurement note "
                         f"{'template ' if limited else ''}{wanted[limited]}, not {named or 'the common note'}")


def selection(plan, condition, context_window=None, folder=None, time_limit_seconds=None, reviewer=None):
    """The plan binds its own Codex version (`codex`, `native_cli_sha256`): the benchmark copy of that version, so a
    frozen plan keeps the harness it was frozen with after harness_pins moves on (measurement rule "harness 版本")."""
    fixed = plan['fixed_conditions']
    executable = codex_binary(fixed['codex'])
    if not executable.is_file():
        raise ValueError(f"The plan's Codex {fixed['codex']} benchmark copy is missing: {executable}")
    codex = executable.read_bytes()
    required_scenario_note(fixed, reviewer or plan.get('reviewer'))
    if 'measurement_note_template' in fixed:
        note, limit = time_limited_note(fixed, folder, time_limit_seconds)
    else:
        if time_limit_seconds is not None:
            raise ValueError('The plan has no time-limited measurement note')
        note, limit = plain_note(fixed), {}
    if sha(codex) != fixed['native_cli_sha256']:
        raise ValueError('Native CLI differs from the frozen plan')
    return {'model': plan['model'], 'effort': fixed['effort'], 'model_owner': 'arw', 'engine_overrides': {},
            'startup_instructions': True, 'project_compaction_instructions': True,
            'generation_policy': 'first-delivery-only', 'loop_prevention_instructions': False,
            'archive_http': True, 'automatic_continuation': False,
            'native_cli': {'executable': str(executable), 'version': fixed['codex'], 'sha256': sha(codex)},
            'loop_reminder': 'off', 'measurement_note': note, **limit,
            # the multi-model benchmark disables Codex web search on every arm (D5); a plan may bind the same
            **({'web_search': fixed['web_search']} if 'web_search' in fixed else {}),
            'deployment_condition': condition,
            # a published context tier the caller selects; omitted, ARW starts the installation default tier
            **({} if context_window is None else {'context_window': context_window})}


def prepare(plan, condition, folder, reviewer=None, context_window=None, time_limit_seconds=None, harness_patches=(),
            preparations=1):
    """Fresh ARW batch for one slot; only its first handoff(s) run, the others stay deferred. harness_patches: names
    from freeze_arw_source.HARNESS_PATCHES applied to the materialized copy (recorded in harness-patches.json).
    preparations > 1: further ARW preparations in the same checkout (preparation-2.json, ...; one ARW preparation holds
    three handoffs), so a block of more than three instances runs in one arw_measure batch. The copy scores with the
    plan's fixed_conditions.scoring (v1 plans have none: r8.4). A Codex batch of a plan that declares
    codex_harness_patches must apply at least those (codex_harness_patches(plan)); a Claude Code batch applies none."""
    declared = codex_harness_patches(plan)
    if harness_patches and not set(declared) <= set(harness_patches):
        raise ValueError(f'harness patches {list(harness_patches)} leave out the plan\'s {declared}')
    folder.mkdir(parents=True)
    arw = folder / 'arw'
    scoring = plan['fixed_conditions'].get('scoring')
    subprocess.run([sys.executable, '-m', 'tools.reviewer.freeze_arw_source', '--manifest',
                    plan['fixed_conditions']['arw_source_manifest'], '--out', str(arw)]
                   + (['--scoring', scoring] if scoring else []),
                   cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
    if harness_patches:
        from tools.reviewer.freeze_arw_source import apply_harness_patch
        save(folder / 'harness-patches.json', [apply_harness_patch(name, arw) for name in harness_patches])
    (arw / 'config.json').write_text(extract_agent_config((arw / 'docs/manuals/agent-cli.md').read_text()))
    save(folder / 'selection-source.json', selection(plan, condition, context_window, folder, time_limit_seconds, reviewer))
    subprocess.run(['git', 'init', '-q'], cwd=arw, check=True)
    env = dict(os.environ, CODEX_THREAD_ID=plan['codex_thread_id'])
    ids = []
    for number in range(1, preparations + 1):
        suffix = '' if number == 1 else f'-{number}'
        with (folder / f'prepare{suffix}.json').open('w') as out, (folder / f'prepare{suffix}.err').open('w') as err:
            subprocess.run(['node', 'scripts/reviewer-capability-conformance.mjs', 'prepare', '--reviewer', reviewer or plan['reviewer']],
                           cwd=arw, env=env, stdout=out, stderr=err, check=True)
        prepared = json.loads((folder / f'prepare{suffix}.json').read_text())
        prepared.update(repositoryRoot=str(arw.resolve()), programDirectory=str(arw.resolve()),
                        identity={'platform': 'codex', 'sessionId': plan['codex_thread_id']})
        save(folder / f'preparation{suffix}.json', prepared)
        ids += [h['instanceId'] for h in prepared['handoffs']]
    return ids


def codex_harness_patches(plan):
    """Harness patches the plan fixes for its Codex arms (multi-model v2: reviewer-private-scratch and the mount-target
    patch); v1 plans fix none, their callers choose."""
    return list(plan['fixed_conditions'].get('codex_harness_patches', []))


def preflight(plan, folder):
    subprocess.run([sys.executable, '-m', 'tools.ops.measurement_host', '--host', plan['host'],
                    '--selection', str(folder / 'selection-source.json'), '--out', str(folder / 'preflight')],
                   cwd=ROOT, check=True)


def host_catalog(host, folder, condition=None):
    """The model catalog as this host's installation holds it (only the served model, its default tier); the
    project catalog lists every quantization, which the host no longer publishes."""
    raw = source_bytes(CATALOG, host, condition=condition)
    path = folder / 'host-model-catalog.json'
    path.write_bytes(raw)
    return path, sha(raw)
