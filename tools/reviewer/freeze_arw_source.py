"""Freeze current upstream source bytes; extract only verified source members.

This never imports Git history or copies runtime state. Materialization and
original ARW preparation happen in a separate temporary copy. Project-owned
compatibility patches listed in the manifest are applied after extraction and
their results verified; a fresh freeze starts without them. The project's ARW scoring
upgrade (evidence F2 instead of F3 and the k-weighted score, user 2026-10-14/16) is applied to every
materialized copy after the manifest patches, and to an already materialized copy before it scores.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import tarfile

ROOTS = {'lib', 'scripts', 'docs', '.agents', 'tests'}
FILES = {'arw.mjs', 'package.json', 'arw.config.json', 'release-manifest.json', 'release-validation.json',
         '.gitignore', 'AGENTS.md', 'README.md'}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def freeze(source, destination):
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=source, text=True).strip()
    names = subprocess.check_output(['git', 'ls-files', '--cached', '--others',
        '--exclude-standard', '-z'], cwd=source).decode().split('\0')
    selected = sorted({n for n in names if n and (n.split('/')[0] in ROOTS or n in FILES)
                       and (source / n).exists()})
    payload = {}
    modes = {}
    for name in selected:
        path = source / name
        if path.is_symlink() or not path.is_file():
            raise ValueError('Source must be an ordinary file: ' + name)
        payload[name] = path.read_bytes()
        modes[name] = 0o755 if path.stat().st_mode & 0o111 else 0o644
    hashes = {name: sha(raw) for name, raw in payload.items()}
    destination.mkdir(parents=True, exist_ok=True)
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode='w:gz') as archive:
        for name, raw in payload.items():
            member = tarfile.TarInfo(name)
            member.size, member.mode, member.mtime = len(raw), modes[name], 0
            archive.addfile(member, io.BytesIO(raw))
    # A moving worktree cannot silently become an inconsistent frozen source.
    if any(sha((source / name).read_bytes()) != expected for name, expected in hashes.items()):
        raise ValueError('Upstream changed during snapshot; preserve the prior freeze')
    raw = buffer.getvalue()
    filename = f'arw-{head[:12]}-{sha(raw)[:12]}.tar.gz'
    target = destination / filename
    if target.exists() and target.read_bytes() != raw:
        raise ValueError('Snapshot name collision')
    target.write_bytes(raw)
    manifest = {'schema': 2, 'source_head': head,
        'current_files_include_uncommitted_changes': bool(subprocess.check_output(
            ['git', 'status', '--porcelain', '--', *sorted(ROOTS), *sorted(FILES)], cwd=source)),
        'framework': 'Unmodified current upstream prepare/generate/verify/score-completed and Reviewer runtime',
        'snapshot': {'file': filename, 'sha256': sha(raw), 'bytes': len(raw)},
        'sha256': hashes, 'modes': modes,
        'scope': 'Repository source/configuration/skills/tests only; no Git history, scratch plans, '
                 'sessions, private credentials, installation or model state.'}
    return manifest


PATCHES = Path(__file__).resolve().parents[2] / 'benchmarks/reviewer-suite-v1/arw-patches'
JUDGMENT = Path(__file__).resolve().parents[2] / 'benchmarks/reviewer-suite-v1/judgment'
# Answer keys allowed to repeat a question (check_repeats); not copied into ARW.
REPEATS = JUDGMENT / 'repeats.json'
FIXTURES = 'tests/fixtures/reviewer-capability'
SCORING_UPGRADE = {
    'file': 'scoring-k.patch',
    'sha256': '21574f23f9e8174414d9edf39b0c4725d5b1f0fce8b7010d8e0a9b0c70bed6ce',
    # Members no scenario patch touches: (ARW original, upgraded).
    'members': {
        'lib/release/reviewer-capability-scoring.mjs': (
            '89a4e6bdc0a47756c28abce013ce6940ebf224e8609ebf809a499c57b85d60c4',
            'd61b20928c628e771f1c272b4f4446d7c1f65ea9d6a3fd851af43f0a68e61a50'),
        'lib/release/reviewer-capability-verification.mjs': (
            'a5e5a5f32fe87d2b84f55e259ea39db0ba1f7e56a681b96af93710ca7b01d9a1',
            '5abdae4334e65a6093abad9882e9bec8a0924e0db3b09f4b22e2860e183d4074'),
        'docs/agents/reviewer-capability-scoring.md': (
            '8dac785a4dc2eee70949fd02a212b65959039c256fa87f6a3e86c105ec011769',
            '7517f410b3f27bf526b68a4400730dd040158a301ce0deadb3e4e73846e66113'),
        'docs/agents/reviewer-capability-scenarios.md': (
            '5fe9b4e5511416a4af636baa67b812bf46f627710b75b1285e6c49758fdb909b',
            '3f444bc68cb9ed8cf3f2e004da5b14a328d0fef2469cd1158c6ed04932b2b859'),
        'docs/agents/reviewer-capability-verification.md': (
            '400cbc050ef9683074ac0483c5803819459fc2ba81f3e4c0b59eef7ab2cc9a9c',
            '00cab0d057e25ce34ad1fe62d971072e118d8925bb23012d48c633b57b7ac1cf')},
    # Scenario patches also change this member, so its upgrade is checked by reverse application.
    'patched_member': 'lib/release/reviewer-capability-conformance.mjs',
    # Earlier drafts, recognized by the scoring and verification modules they leave behind; a copy still
    # carrying one is reverted before the current upgrade. r1 and r2 carried paired cases (withdrawn
    # 2026-10-15); r3 had evidence F2 only, before the two-part score (user 2026-10-15); r4 bound overlays
    # without a registry; r5 had no in-key registration and rejected results without two-part counts;
    # r6 judged clean cases mechanically, matched multi-word terms as word bags, required evidence score
    # >= 0.5 for judgment problem cases and cut every format error by 0.9 (r7, user 2026-10-15). r7 cut a
    # continuation past the requirement-scope stop by 0.9 (one wrong answer, user 2026-10-15); it left the same
    # modules as r7.1, so both are recognized by their scoring document as well. r7.1 scored judgment cases (A) and
    # the rest (B, F2) apart; r8 weights every case by k (user 2026-10-16). r8 nominated the clean case of a satisfied
    # Commit Audit row only by evidence and terms, so a false gap there also failed no-other (r8.1, user 2026-10-17). r8.1
    # had no merged cases and still gave a Spec Readiness case scored in both scenarios a 0.5 share (r8.2, user 2026-10-17).
    # r8.2 offered a Commit Audit finding the problem cases of other requirement rows in its finding decision (r8.3).
    'superseded': {
        ('bd274533d5c134c53ed80d6d015bf13402b52ddc5dcde85d658e0463cc9dc69d',
         '5abdae4334e65a6093abad9882e9bec8a0924e0db3b09f4b22e2860e183d4074'): (
            'superseded/scoring-k-r8.2.patch', 'cda3153729fb808199ad7b5ceaa71355e07926d65231d06d68e8924af43fb93b'),
        ('cc4a6538c6a7190a25c013ba2f40a25c364c57f1ca8aaf904ea911a08a7e76fd',
         '6d990d13f03cc34618a425fa979871c9df2ce8415886c511234f8d6efe2839c9'): (
            'superseded/scoring-k-r8.1.patch', '81f0eb4c5b9d084ebc97bffdbd5b5f55be3872c90562c619c99183b0351a551c'),
        ('009ea8579c8237cd29a736fb691b843ba37105231975b26fe083a8ada3c8ea72',
         '6d990d13f03cc34618a425fa979871c9df2ce8415886c511234f8d6efe2839c9'): (
            'superseded/scoring-k-r8.patch', '8106f958de2fef888c04c0c1726c67e61290e7f1c4796583e627983bd7676fc1'),
        ('555a20834fcea541bc785a61d9b6cd5c4e97b9d96709ef95598e1c405d5bc9c7',
         'b6afd551621a3496702cb7abafc1e6ab82c15e1ece5d13e9434db9057731f1b0',
         '217908536a38ba83e1936392dcdb368823435adc1e1514cd0ee22592c0a5795b'): (
            'superseded/scoring-f2-r7.1.patch', 'ebc4ad013b225cca8fc5a2d7b8542dba5bc6a459c6dec44e5e42716266b05666'),
        ('555a20834fcea541bc785a61d9b6cd5c4e97b9d96709ef95598e1c405d5bc9c7',
         'b6afd551621a3496702cb7abafc1e6ab82c15e1ece5d13e9434db9057731f1b0',
         'a9e35b62a8726b9d8375ea3c9bcc43db0b8b34ce047ffc4abb24c1660289b93d'): (
            'superseded/scoring-f2-r7.patch', '053870f3478170662e47b780c1c709911f14df86cb59477be62d8c4d586a13c6'),
        ('6d317e629d35bd732d0adf50427e2b9ec79f67df4370d636ba73bc8be383c230',
         'a5e5a5f32fe87d2b84f55e259ea39db0ba1f7e56a681b96af93710ca7b01d9a1'): (
            'superseded/scoring-f2-r1-pairs.patch', 'eca2b547d73091244592aa7adf2fa7efbc1f38476f4847f58fc9a2a2477fd8e7'),
        ('dfffb39933527ad30d40ea0ccd83d47be4654fe6a751bf21dc2a7c47eade775b',
         'a5e5a5f32fe87d2b84f55e259ea39db0ba1f7e56a681b96af93710ca7b01d9a1'): (
            'superseded/scoring-f2-r2-pairs.patch', 'df85dcad195d5193dd71b833e5dc380b1899fb71b88d618d136c5d88f53cc3fe'),
        ('4a618270a9ae49d63b2b64714fc7c5dd42aef35c94f68ac60bf87f606740a8b1',
         'a5e5a5f32fe87d2b84f55e259ea39db0ba1f7e56a681b96af93710ca7b01d9a1'): (
            'superseded/scoring-f2-r3.patch', '0f31a0370ac1628b6230ad92c75286c524d6ff06e610780f82b3759d1b0614e0'),
        ('134b9e00bdf72a9cf7596900a54d6c0e22615c53e6a8a9c9a17d788c81a1869f',
         'f06d74b68a803ab66589eb9e2158c7356447e39485242933e4c93f6a41b2c41f'): (
            'superseded/scoring-f2-r4.patch', '855004abacbff41880bd26a93efb10620bd1e4a92b0ff4af625d6201db4985b9'),
        ('67c1a38e459c7143a92c641be11422c0e47bf22db3e3c60317c3121c6ecd160b',
         '48e3d051c8d8c94160c2ee81e1f0c533991ba65d5771fdff6e78735da111c164'): (
            'superseded/scoring-f2-r5.patch', '4e0f732b214e81686b565be2d030b4391dd41be4df819c6d87a885b305467913'),
        ('67c1a38e459c7143a92c641be11422c0e47bf22db3e3c60317c3121c6ecd160b',
         'ae591793e30144cda24a4f28321b6b84d9a24990de30ae46c56afc55eb041056'): (
            'superseded/scoring-f2-r6.patch', '25573a2edb6b4a23cf2ea00e0d9a3541e0b655bac163ad98d825147dd1969056')}}


def git_apply(patch, destination, *options, check=True):
    # Stop repository discovery: inside an enclosing repository git apply resolves paths
    # against that repository and silently skips patches with git headers.
    return subprocess.run(['git', 'apply', '-p1', *options, str(patch.resolve())], cwd=destination, check=check,
                          capture_output=not check,
                          env=dict(os.environ, GIT_CEILING_DIRECTORIES=str(Path(destination).resolve().parent))).returncode == 0


# Harness compatibility patches a caller opts into at prepare time (not in the frozen manifests, whose sha the scenario
# plans bind). codex-0.163-synthetic-mount-targets: Codex 0.163 bubblewrap leaves empty .git/.codex/.agents/.aws mount
# targets in the writable report directory (stubtest2, 2026-10-20); the binding check sets exactly those aside and logs
# each one. Recorded in docs/arw-upstream-issues.md.
HARNESS_PATCHES = {
    'codex-0.163-synthetic-mount-targets': {
        'file': 'codex-0.163-synthetic-mount-targets.patch',
        'sha256': 'c1347209125ebb3682b5b3a69eb0fc192ea70469822596d433383ce10f63a476',
        'base': {'lib/reviewer-runtime/reviewer-runtime.mjs':
                 '7ac16d500831a4912718e1a2823cc7dc72c58fb7d5aaa5460944c628b687f020'},
        'result': {'lib/reviewer-runtime/reviewer-runtime.mjs':
                   '7fae6d7233111b312775e692673fa4551ab98b44e46c4b7baeacf686eff93354',
                   'lib/reviewer-runtime/codex-mount-targets.mjs':
                   '0060fdcbf8ca5b61dd5100f2a134e98c46b2689d5aa19497090b5fda42126922',
                   'tests/reviewer-runtime/codex-mount-targets.test.mjs':
                   '61ddfae128067afcac8aed470dfcb2ab78cf3e66288c337ded97e2aa6ba5991d'}},
    # strata-measurement-time-limit: ARW's Strata work policy hard-codes a 55-minute reminder and 60-minute stop and never
    # reads the measurement time limit T (independent review F1, 2026-10-20). With a provider reviewTimeLimitSeconds the
    # reminder comes 300 s before T (T/2 when T < 600 s, reminder_message wording) and the stop at T; without it nothing changes.
    'strata-measurement-time-limit': {
        'file': 'strata-measurement-time-limit.patch',
        'sha256': '8b285e30868bfb803255b7e62333a8351875b736f1e8bc230cce990f3d8648b9',
        'base': {'lib/background-agent/strata-work-policy.mjs':
                 '4a9bff8c488a09ad3a98baf9ab6c8a50ac2febd64c1c1c7beebcf282b1101785',
                 'lib/background-agent/strata-driver.mjs':
                 '6ce2a8d093911042ca8c4d94af90e4717c3da83962166aa4bf27e87a604103a4',
                 'lib/background-agent/model-catalog.mjs':
                 'ec2e2fc2db43752c87744855fa6aa5019a0f0eeb2d5c9948b0eebb9ab80bcd4e'},
        'result': {'lib/background-agent/strata-work-policy.mjs':
                   'd57b1c3ab4836b12589332e13cd917efd3b0195395e4c9aa24df8b53abc7fc60',
                   'lib/background-agent/strata-driver.mjs':
                   '5d1b4586b61c5dc6e3d3264c205291e91017d821b23430d3a40eae890b99c8dc',
                   'lib/background-agent/model-catalog.mjs':
                   '7b45b8b0367afa9f7c4bc4bebbd1c0ca259ec948c8dc230c091405627f535f21',
                   'tests/background-agent/strata-time-limit.test.mjs':
                   'c882c3625c2d3da298d6b6c8393c2d14bd605d7aa05d98f1e37c020f2f921e07'}},
    # reviewer-private-scratch: a Codex Reviewer gets a private writable scratch outside the scenario root and the report
    # directory, also its commands' TMPDIR, as the Claude Code arms have (F2, user 2026-10-20: a Reviewer must be able to
    # write scripts); the common scratch root is denied, so no Reviewer reaches another one's. tools.reviewer.reviewer_scratch
    # computes the same path and removes it after the instance. Default for later Codex Reviewer measurements; the
    # multi-model benchmark v1 never selects it (user 2026-10-20, no rerun, same condition for every Codex arm).
    'reviewer-private-scratch': {
        'file': 'reviewer-private-scratch.patch',
        'sha256': '12b35b5b297f81344c785a201970fda4384692bdf8f1774c4bda2c677752f1ca',
        'base': {'lib/reviewer-runtime/reviewer-native-policy.mjs':
                 'bad1b30494faf504b542bcddbc50fb1b2379ea40c47727dd6e93af570ab2b280'},
        'result': {'lib/reviewer-runtime/reviewer-native-policy.mjs':
                   'e8469645d95352d1b0f7ab59fbf8d4315835f5b5306251942680770deba9046c',
                   'lib/reviewer-runtime/reviewer-scratch.mjs':
                   'b851ef995a7d822cd37369dca80c5556bf577cbcc04c8c9d41cd6a4a893ee827',
                   'tests/reviewer-runtime/reviewer-scratch.test.mjs':
                   '88573f9a91bfcb83b5b1caba850e15945020fb118ccd1b3079d8d66b312239ba'}}}


def apply_harness_patch(name, destination):
    """Apply one pinned harness patch to a materialized copy, checking the members before and after."""
    entry = HARNESS_PATCHES[name]
    destination = Path(destination)
    for member, expected in entry['base'].items():
        if sha((destination / member).read_bytes()) != expected:
            raise ValueError(f'{name}: base member differs: {member}')
    git_apply(pinned_patch(entry['file'], entry['sha256']), destination)
    for member, expected in entry['result'].items():
        if sha((destination / member).read_bytes()) != expected:
            raise ValueError(f'{name}: patched member differs: {member}')
    return {'name': name, 'file': entry['file'], 'sha256': entry['sha256'], 'result': entry['result']}


def pinned_patch(name, digest):
    patch = PATCHES / name
    if sha(patch.read_bytes()) != digest:
        raise ValueError('Scoring upgrade patch differs: ' + name)
    return patch


# A k 4 false positive costs as much as four missed problem cases, so it must be adjudicated twice; until
# that procedure exists, k 4 marks are refused.
DUAL_ADJUDICATION_MISSING = '{} marks k 4 cases, which need dual adjudication that is not implemented yet'
# A merged case counts once in its k tier, but the tier balance below counts every case; until the balance counts
# merged cases once, a merged case marked k >= 1 (in the key or by an overlay) is refused.
MERGED_K_MISSING = ('{} marks merged case {} at k >= 1; the k tier balance does not count merged cases once yet, so merged '
                    'cases must stay at the default k 0.25')


def k_balanced(tiers):
    """Each marked tier holds k problem cases per clean case, so reporting everything or nothing scores 0 on it."""
    return bool(tiers) and all(counts['problem'] == float(k) * counts['clean'] for k, counts in tiers.items())


def evidence_sets(case):
    """The evidence sets a case accepts: a problem case's placement evidence, or a clean case's evidence and
    its alternatives, each as a sorted tuple of (file, line)."""
    sets = [placement['evidence'] for placement in case['placements']] if 'placements' in case else [
        case.get('evidence', [])] + case.get('evidenceAlternatives', [])
    return frozenset(tuple(sorted({(item['filePath'], item['line']) for item in items})) for items in sets)


def merged_cases(fixture):
    """Merged cases the answer key declares (`merge`, r8.2, user 2026-10-17): a question kept on purpose in two places
    (e.g. a Commit Audit requirement repeated by an issue and the spec) and scored once. Each name must hold exactly two
    cases of one kind, k and result in two different scopes, and both cases expect the same evidence: the measurement
    note lets the reviewer copy the reviewed row's conclusion and evidence, which must not cost points. Returns
    {name: [case names]}."""
    members = {}
    for scope in fixture['scopes']:
        for kind in ('problem', 'clean'):
            for index, case in enumerate(scope.get(kind + 'Cases', [])):
                if 'merge' in case:
                    members.setdefault(case['merge'], []).append((scope['scope'], kind, index, case))
    for name, items in members.items():
        if (len(items) != 2 or items[0][0] == items[1][0] or items[0][1] != items[1][1]
                or not isinstance(name, str) or not name
                or any(case.get('noOtherSupportedFinding') for *_, case in items)
                or len({(case.get('k'), case.get('judgment'), case.get('result')) for *_, case in items}) != 1):
            raise ValueError(f'Merged case {name!r} must hold two cases of one kind, k and result in two scopes')
        if len({evidence_sets(case) for *_, case in items}) != 1:
            raise ValueError(f'Merged case {name!r} must expect the same evidence in both cases')
    return {name: [f'{scope}/{kind}/{index}' for scope, kind, index, _ in items] for name, items in members.items()}


def repeated_cases(fixture):
    """Groups of cases in one answer key that ask the same question twice (user 2026-10-16/17): the same
    expectation, or the same evidence (a clean case's evidence or one of its alternatives, a problem case's
    placement evidence). Cases are named scope/kind/index (0-based); noOther cases are left out. The two cases of
    a declared merged case are one question: a group made only of them is no repeat."""
    by_expectation, by_evidence = {}, {}
    for scope in fixture['scopes']:
        for kind in ('problem', 'clean'):
            for index, case in enumerate(scope.get(kind + 'Cases', [])):
                if case.get('noOtherSupportedFinding'):
                    continue
                name = f"{scope['scope']}/{kind}/{index}"
                by_expectation.setdefault(case.get('expectation'), []).append(name)
                for evidence in evidence_sets(case):
                    if evidence:
                        by_evidence.setdefault(evidence, []).append(name)
    question = {case: name for name, cases in merged_cases(fixture).items() for case in cases}
    repeats = lambda names: len({question.get(name, name) for name in names}) > 1
    groups = [('expectation', names) for names in by_expectation.values() if repeats(names)]
    shared = {tuple(sorted(set(names))) for names in by_evidence.values() if repeats(names)}
    return groups + [('evidence', list(names)) for names in sorted(shared)]


def check_repeats(reviewer, digest, fixture):
    """Refuse an answer key with a repeated question unless judgment/repeats.json lists the key as a legacy
    version kept only to rescore old reports, or lists each group of cases that share evidence as reviewed
    distinct questions. A shared expectation is never allowed outside a legacy key or a declared merged case
    (user 2026-10-17: accidental repeats are rewritten, repeats kept on purpose are declared in the key)."""
    allowed = json.loads(REPEATS.read_text()).get(reviewer, {}).get(digest, {})
    if allowed.get('legacy'):
        return
    reviewed = {tuple(sorted(item['cases'])) for item in allowed.get('sharedEvidence', [])}
    for kind, names in repeated_cases(fixture):
        if kind == 'expectation' or tuple(names) not in reviewed:
            raise ValueError(f"Answer key {digest} of {reviewer} repeats a question ({kind}): {' '.join(names)}")


def judgment_binding(destination):
    """Bind every answer key in this copy through judgment/registry.json, which maps each known
    reviewer and expected.json sha256 to its k overlay, to in-key (k marks written in the key) or to
    all-B (every case at the default k 0.25). A case marks k 1 or 4 with `k`; a two-part judgment mark
    (`judgment: true`, r7) and an overlay case without `k` count as k 1. An unregistered key, marks in a key
    not registered as in-key, an overlay that does not match its key case by case, or a marked tier without
    k problem cases per clean case stops the upgrade, and so does any k 4 mark until dual adjudication of
    k 4 false positives exists, and any k >= 1 mark on a merged case (`merge`) until the tier balance counts merged
    cases once. Returns the files to copy into the ARW copy and the
    binding of each reviewer."""
    registry_raw = (JUDGMENT / 'registry.json').read_bytes()
    registry = json.loads(registry_raw)
    files, bound = {'registry.json': registry_raw}, {}
    for expected_path in sorted((destination / FIXTURES).glob('*/expected.json')):
        reviewer, digest = expected_path.parent.name, sha(expected_path.read_bytes())
        entry = registry.get(reviewer, {}).get(digest)
        if entry is None:
            raise ValueError(f'Answer key {digest} of {reviewer} is not registered in judgment/registry.json')
        fixture = json.loads(expected_path.read_text())
        check_repeats(reviewer, digest, fixture)
        merged = {(scope['scope'], kind, index): case['merge'] for scope in fixture['scopes'] for kind in ('problem', 'clean')
                  for index, case in enumerate(scope.get(kind + 'Cases', [])) if 'merge' in case}
        scopes = {scope['scope']: scope for scope in fixture['scopes']}
        marked = {}
        for scope in scopes.values():
            for kind in ('problem', 'clean'):
                for case in scope.get(kind + 'Cases', []):
                    if case.get('judgment') is True or 'k' in case:
                        if 'merge' in case and (case.get('judgment') is True or float(case['k']) >= 1):
                            raise ValueError(MERGED_K_MISSING.format(f'Answer key {digest} of {reviewer}', case['merge']))
                        tier = marked.setdefault(str(1 if case.get('judgment') is True else case['k']), {'problem': 0, 'clean': 0})
                        tier[kind] += 1
        if '4' in marked:
            raise ValueError(DUAL_ADJUDICATION_MISSING.format(f'Answer key {digest} of {reviewer}'))
        if entry['judgment'] == 'in-key':
            if not k_balanced(marked):
                raise ValueError(f'Answer key {digest} of {reviewer} must hold k problem cases per clean case in each marked tier')
            bound[reviewer] = {'judgment': 'in-key', 'expectedSha256': digest}
            continue
        if marked:
            raise ValueError(f"Answer key {digest} of {reviewer} marks k cases but is registered as {entry['judgment']}")
        if entry['judgment'] == 'all-B':
            bound[reviewer] = {'judgment': 'all-B', 'expectedSha256': digest}
            continue
        path = JUDGMENT / entry['judgment']
        raw = path.read_bytes()
        overlay = json.loads(raw)
        if overlay['reviewerId'] != reviewer or overlay['expectedSha256'] != digest:
            raise ValueError(f'Judgment overlay {path.name} is not bound to answer key {digest} of {reviewer}')
        seen, counts, tiers = set(), {'problem': 0, 'clean': 0}, {}
        for item in overlay['cases']:
            cases = scopes[item['scope']][item['kind'] + 'Cases'] if item['scope'] in scopes else []
            case = cases[item['index']] if 0 <= item['index'] < len(cases) else {}
            key = (item['scope'], item['kind'], item['index'])
            if (case.get('expectation') != item['expectation'] or case.get('noOtherSupportedFinding') or key in seen
                    or item.get('k', 1) not in (1, 4)):
                raise ValueError(f"Judgment overlay {path.name} does not match its fixture: {' '.join(map(str, key))}")
            if item.get('k', 1) == 4:
                raise ValueError(DUAL_ADJUDICATION_MISSING.format(f'Judgment overlay {path.name}'))
            if key in merged:
                raise ValueError(MERGED_K_MISSING.format(f'Judgment overlay {path.name}', merged[key]))
            seen.add(key)
            counts[item['kind']] += 1
            tiers.setdefault(str(item.get('k', 1)), {'problem': 0, 'clean': 0})[item['kind']] += 1
        # Each case counts once per scoring unit (the two Spec Readiness scenarios never score the same case,
        # v4.3), so a balanced unit needs k problem cases per clean case in each tier.
        if not k_balanced(tiers) or overlay.get('counts') != counts:
            raise ValueError(f'Judgment overlay {path.name} must hold k problem cases per clean case in each tier, correctly counted')
        files[path.name] = raw
        bound[reviewer] = {'judgment': path.name, 'overlaySha256': sha(raw), 'expectedSha256': digest}
    return files, bound


def bind_judgment(destination):
    """Copy the registry and the overlays bound to this copy to <arw>/reviewer-judgment/, which ARW
    reads when it loads an answer key; an unchanged directory is left alone, a changed one is replaced
    through a staged copy."""
    wanted, bound = judgment_binding(destination)
    target = destination / 'reviewer-judgment'
    present = {path.name: path.read_bytes() for path in target.glob('*')} if target.is_dir() else {}
    if present != wanted:
        staged, old = target.with_name('reviewer-judgment.staged'), target.with_name('reviewer-judgment.old')
        shutil.rmtree(staged, ignore_errors=True)
        staged.mkdir()
        for name, raw in wanted.items():
            (staged / name).write_bytes(raw)
        if target.exists():
            target.rename(old)
        staged.rename(target)
        shutil.rmtree(old, ignore_errors=True)
    return bound


def upgrade_scoring(destination):
    """Bring a materialized copy to the project's scoring rule (evidence F2, the r7 adjudicated clean cases
    and the r8 k-weighted score, user 2026-10-14/16). Applies the upgrade once; a copy left by a superseded
    draft is reverted first."""
    destination = Path(destination)
    members = SCORING_UPGRADE['members']
    scoring_module = 'lib/release/reviewer-capability-scoring.mjs'
    migrated = None
    modules = tuple(sha((destination / name).read_bytes()) for name in (
        scoring_module, 'lib/release/reviewer-capability-verification.mjs'))
    draft = SCORING_UPGRADE['superseded'].get(modules) or SCORING_UPGRADE['superseded'].get(
        modules + (sha((destination / 'docs/agents/reviewer-capability-scoring.md').read_bytes()),))
    if draft:
        git_apply(pinned_patch(*draft), destination, '--reverse')
        shutil.rmtree(destination / 'reviewer-pairs', ignore_errors=True)
        migrated = draft[0]
    patch = pinned_patch(SCORING_UPGRADE['file'], SCORING_UPGRADE['sha256'])
    current = {name: sha((destination / name).read_bytes()) for name in members}
    applied = False
    if all(current[name] == new for name, (_, new) in members.items()):
        if not git_apply(patch, destination, '--reverse', '--check', check=False):
            raise ValueError('ARW scoring upgrade is incomplete in ' + SCORING_UPGRADE['patched_member'])
    elif all(current[name] == old for name, (old, _) in members.items()):
        git_apply(patch, destination)
        applied = True
    else:
        raise ValueError('ARW scoring members differ from both the original and the upgrade; re-materialize the copy')
    return {'applied': applied, 'migrated_from': migrated, 'judgment': bind_judgment(destination)}


def materialize(manifest, archive_path, destination, patch_directory=None):
    raw = archive_path.read_bytes()
    if sha(raw) != manifest['snapshot']['sha256']:
        raise ValueError('Frozen source archive differs')
    destination.mkdir(parents=True, exist_ok=False)
    seen = set()
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:gz') as archive:
        for member in archive:
            path = PurePosixPath(member.name)
            if (not member.isfile() or path.is_absolute() or '..' in path.parts
                    or member.name in seen or member.name not in manifest['sha256']):
                raise ValueError('Unexpected archive member: ' + member.name)
            stream = archive.extractfile(member)
            data = stream.read()
            if sha(data) != manifest['sha256'][member.name]:
                raise ValueError('Frozen member differs: ' + member.name)
            target = destination / member.name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            target.chmod(manifest['modes'][member.name])
            seen.add(member.name)
    if seen != set(manifest['sha256']):
        raise ValueError('Frozen source members are missing')
    for entry in manifest.get('patches', []):
        patch = (patch_directory or archive_path.parent) / entry['file']
        if sha(patch.read_bytes()) != entry['sha256']:
            raise ValueError('Compatibility patch differs: ' + entry['file'])
        git_apply(patch, destination)
        for name, expected in entry['result'].items():
            if sha((destination / name).read_bytes()) != expected:
                raise ValueError('Patched member differs: ' + name)
    upgrade_scoring(destination)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--source', type=Path)
    mode.add_argument('--manifest', type=Path)
    mode.add_argument('--upgrade-scoring', type=Path, metavar='ARW', help='upgrade an already materialized copy')
    parser.add_argument('--out', type=Path)
    parser.add_argument('--archive-directory', type=Path)
    args = parser.parse_args()
    if args.upgrade_scoring:
        print(json.dumps({'scoring_upgrade': SCORING_UPGRADE['file'], **upgrade_scoring(args.upgrade_scoring)}))
    elif args.out is None:
        parser.error('--out is required with --source or --manifest')
    elif args.source:
        result = freeze(args.source, args.out)
        (args.out / 'manifest.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps({'files': len(result['sha256']), 'snapshot': result['snapshot']}))
    else:
        result = json.loads(args.manifest.read_text())
        archive = (args.archive_directory or args.manifest.parent) / result['snapshot']['file']
        materialize(result, archive, args.out)
        print(json.dumps({'materialized_files': len(result['sha256']),
                          'patches': [entry['file'] for entry in result.get('patches', [])] + [SCORING_UPGRADE['file']]}))
