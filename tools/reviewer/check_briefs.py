"""Pre-freeze mechanical check of the blind-adjudication briefs against frozen ARW copies and their answer keys.

Each brief is checked against a copy materialized from its frozen source manifest (made in --work when absent):
the ARW Adjudication section is quoted verbatim, the cited answer-key SHA is the materialized key's, only the caller
placeholders remain, the Role exists, the ARW decision block equals the frozen Commit Audit v3 brief's, and the
scenario-specific facts the brief states (decoy lines, file names, scopes, quoted sections) hold in the fixture.
--suite v2 checks the multi-model benchmark v2 draft briefs the same way against their own manifests, and also that
the v2 common paragraph is word for word the same in all four briefs and carries the required rulings, and that the
Role sentences the briefs quote are on the cited lines.

  python3 -m tools.reviewer.check_briefs --work .tmp/<work>/arw [--suite v2]
"""
import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SUITE = ROOT / 'benchmarks/reviewer-suite-v1'
MANIFESTS = SUITE / 'source-snapshots/current'
FIXTURES = 'tests/fixtures/reviewer-capability'
V2 = ROOT / 'benchmarks/multi-model-v2'
# suite -> brief path -> (source manifest, reviewer)
SUITES = {
    'v1': {SUITE / 'code-spec-v5-brief.md': (MANIFESTS / 'manifest-code-spec-v5.json', 'code-spec-reviewer'),
           SUITE / 'code-standards-v5.1-brief.md': (MANIFESTS / 'manifest-code-standards-v5.1.json', 'code-standards-reviewer'),
           SUITE / 'spec-readiness-v4.3-brief.md': (MANIFESTS / 'manifest-spec-readiness-v4.3.json', 'spec-readiness-reviewer')},
    'v2': {V2 / 'briefs/code-spec-v5.1-brief.md': (V2 / 'scenarios/manifest-code-spec-v5.1.json', 'code-spec-reviewer'),
           V2 / 'briefs/code-standards-v5.1-brief.md': (MANIFESTS / 'manifest-code-standards-v5.1.json', 'code-standards-reviewer'),
           V2 / 'briefs/spec-readiness-v4.4-brief.md': (V2 / 'scenarios/manifest-spec-readiness-v4.4.json', 'spec-readiness-reviewer'),
           V2 / 'briefs/commit-audit-v3.1-brief.md': (V2 / 'scenarios/manifest-commit-audit-v3.1.json', 'commit-audit-reviewer')}}
V2_COMMON = re.compile(r'^本工程补充（multi-model-v2 统一口径.*?\n\n', re.S | re.M)
# Rulings the v2 common paragraph must carry (plan.md section 9, items 8 and 12): rulings.md "一条 finding 讲了两个缺陷"
# and the four clauses of "finding 的机制写对了，但结论或例子与代码相反".
V2_COMMON_RULINGS = ('其中一个与期望句是同一问题即 matched，其余缺陷不影响该关联', '与被审材料的实际行为相反',
                     '只是个别措辞写反', '复现的情形实测属实', '错误意图当成正确要求')
# A Role sentence a v2 brief quotes as `docs/agents/roles/<file>`:<line> 原文"…"、"…": each quote must be on that line.
V2_ROLE_QUOTE = re.compile(r'`(docs/agents/roles/[^`]+)`:(\d+) 原文((?:"[^"]+"、?)+)')


def materialized(work, manifest):
    target = Path(work) / ('arw-' + manifest.stem.removeprefix('manifest-'))
    if not target.exists():
        subprocess.run([sys.executable, '-m', 'tools.reviewer.freeze_arw_source', '--manifest', str(manifest),
                        '--out', str(target)], cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
    return target


def quoted_section(document, heading, text):
    """The body of a design note's section (below its heading, up to the next heading of level 1–3, trimmed, one
    final LF) and whether the brief quotes it verbatim together with its sha256."""
    lines = document.read_text().splitlines(keepends=True)
    start = next(i for i, l in enumerate(lines) if l.startswith(heading))
    end = next(i for i in range(start + 1, len(lines)) if re.match(r'#{1,3} ', lines[i]))
    body = ''.join(lines[start + 1:end]).strip() + '\n'
    return body in text and hashlib.sha256(body.encode()).hexdigest() in text


def line(path, number):
    lines = Path(path).read_text().splitlines()
    return lines[number - 1] if 0 < number <= len(lines) else ''


def check(work, suite='v1'):
    results = []

    def chk(condition, message):
        results.append((bool(condition), message))

    frozen = (SUITE / 'commit-audit-v3-brief.md').read_text()
    block = re.search(r'^## 决定语义[^\n]*\n\n(.*?)^本工程补充（评分 r8\.1', frozen, re.S | re.M).group(1)
    briefs = SUITES[suite]
    if suite == 'v2':
        commons = {path.name: V2_COMMON.search(path.read_text()) for path in briefs}
        chk(all(commons.values()) and len({m.group(0) for m in commons.values()}) == 1,
            'v2: common paragraph identical in all briefs')
        common = next(iter(commons.values()))
        for ruling in V2_COMMON_RULINGS:
            chk(common and ruling in common.group(0), f'v2: common paragraph states {ruling}')
    for path, (manifest, reviewer) in briefs.items():
        brief, text = path.name, path.read_text()
        arw = materialized(work, manifest)
        fixture = arw / FIXTURES / reviewer
        verification = (arw / 'docs/agents/reviewer-capability-verification.md').read_text().splitlines(keepends=True)
        start = verification.index('## Adjudication\n')
        end = next(i for i in range(start + 1, len(verification)) if verification[i].startswith('## '))
        chk(''.join(verification[start:end]).rstrip('\n') + '\n\n' in text, f'{brief}: ARW Adjudication section verbatim')
        key_bytes = (fixture / 'expected.json').read_bytes()
        digest = hashlib.sha256(key_bytes).hexdigest()
        chk(digest in text, f'{brief}: cites materialized key sha {digest[:8]}')
        chk(set(re.findall(r'<(?:[A-Z]+|名|裁决者)>', text)) == {'<ADJ>', '<名>'}, f'{brief}: placeholders only <ADJ>/<名>')
        chk('"adjudicator": "blind Opus high"' in text and 'unsure' not in text, f'{brief}: single blind Opus output contract')
        chk(frozen[frozen.index('## 输出'):] == text[text.index('## 输出'):], f'{brief}: output section equals the frozen brief')
        chk((arw / 'docs/agents/roles' / (reviewer + '.md')).exists(), f'{brief}: role file exists')
        chk(block in text, f'{brief}: ARW decision block identical to frozen Commit Audit brief')
        if suite == 'v2':
            quotes = V2_ROLE_QUOTE.findall(text)
            chk(quotes or reviewer == 'commit-audit-reviewer', f'{brief}: quotes the Role on vague findings')
            for role_path, number, quoted in quotes:
                for sentence in re.findall(r'"([^"]+)"', quoted):
                    chk(sentence in line(arw / role_path, int(number)), f'{brief}: {role_path}:{number} holds "{sentence}"')
        key = json.loads(key_bytes)
        scenario = fixture / 'scenario'
        if reviewer == 'code-spec-reviewer':
            source = scenario / 'candidate/src/reservations'
            chk(any('endAt <= startAt' in p.read_text() for p in source.glob('*.mjs')), 'CS: decoy endAt <= startAt in reservations')
            chk([s['scope'] for s in key['scopes']] == ['CODE-SPEC-FINDINGS'], 'CS: single scope CODE-SPEC-FINDINGS')
            chk((scenario / 'base/governing-spec.md').exists(), 'CS: governing-spec.md in base')
            modules = [p.name for p in (scenario / 'candidate/src').iterdir() if p.is_dir() and p.name != 'platform']
            chk(len(modules) == 13, f'CS: 13 feature modules ({len(modules)})')
        if reviewer == 'code-standards-reviewer':
            modified = sorted(str(p.relative_to(scenario / 'candidate')) for p in (scenario / 'candidate').rglob('*')
                              if p.is_file() and 'catering' not in p.parts)
            chk(len(modified) == 3 and all(m in text and (scenario / 'base' / m).exists() for m in modified),
                f'CStd: 3 modified existing files named {modified}')
            chk('normalizeMemberId' in (scenario / 'base/src/members/profile.mjs').read_text(), 'CStd: normalizeMemberId in base')
            chk((scenario / 'base/src/AGENTS.md').exists(), 'CStd: src/AGENTS.md exists')
            scope = key['scopes'][0]
            chk(sum(1 for c in scope['problemCases'] if c.get('judgment')) == 10
                and sum(1 for c in scope['cleanCases'] if c.get('judgment')) == 10, 'CStd: A-class 10:10 in key')
            role = (arw / 'docs/agents/roles/code-standards-reviewer.md').read_text()
            chk('不把其中独立存在的历史问题扩展为本次 finding' in role and '不得判断变更是否实现相应的产品或 issue 要求' in role,
                'CStd: cited role sentences exist')
            # S3 decoys: the brief's lines are the placements of clean cases C22 and C29 and hold the named code.
            cleans = scope['cleanCases']
            c22, c29 = cleans[21], cleans[28]
            placements = lambda case: [[(e['filePath'], e['line']) for e in group]
                                       for group in [case['evidence']] + case.get('evidenceAlternatives', [])]
            chk('extraCharges' in c22['expectation'] and placements(c22) == [[('src/billing/line-items.mjs', 26)]],
                'CStd: C22 is the buildLineItems extraCharges clean case at line-items.mjs:26')
            chk('extraCharges' in c29['expectation'] and placements(c29) == [
                [('src/billing/invoice-service.mjs', 22)], [('src/billing/invoice-service.mjs', 32)],
                [('src/catering/catering-pricing.mjs', 30)], [('src/catering/catering-service.mjs', 148)]],
                'CStd: C29 placements are invoice-service :22/:32, catering-pricing :30, catering-service :148')
            source = scenario / 'candidate'
            facts = [('src/billing/line-items.mjs', 26, 'buildLineItems', 'extraCharges'),
                     ('src/billing/line-items.mjs', 32, 'memberId', 'extraCharges'),
                     ('src/billing/invoice-service.mjs', 22, 'previewInvoice', 'extraCharges'),
                     ('src/billing/invoice-service.mjs', 32, 'issueInvoice', 'extraCharges'),
                     ('src/catering/catering-pricing.mjs', 30, 'invoiceCharges', 'orders'),
                     ('src/catering/catering-service.mjs', 148, 'memberInvoiceCharges', 'invoiceCharges')]
            for path, number, *words in facts:
                chk(f'`{path}:{number}`' in text and all(w in line(source / path, number) for w in words),
                    f'CStd: brief cites {path}:{number} holding {words}')
            draft_for = (source / 'src/billing/invoice-service.mjs').read_text()
            chk('buildLineItems(reservations, prepared, extraCharges)' in draft_for, 'CStd: draftFor passes extraCharges')
            item = (source / 'src/billing/line-items.mjs').read_text()
            chk('export const lineItemFor = ({buildingId, endAt, reservationId, roomId, startAt}, charge)' in item,
                'CStd: lineItemFor builds reservation items without memberId')
        if reviewer == 'spec-readiness-reviewer':
            chk(quoted_section(SUITE / 'spec-readiness-v4.md', '### 裁决 brief（新用例）', text),
                'SR: quoted v4 section verbatim with sha')
            override = json.loads((SUITE / 'judgment/spec-readiness-v4.2.json').read_text())
            chk(override['expectedSha256'] == digest, 'SR: k override binds the same key sha')
            role = (arw / 'docs/agents/roles/spec-readiness-reviewer.md').read_text()
            chk(re.search(r'Role 原文"([^"]+)"', text).group(1) in role, 'SR: quoted role sentence verbatim')
            refs = sorted(set(re.findall(r'`((?:promotion-runtime|promotion-recovery|access-review|validation-report|'
                                         r'runtime-migration)\.md):\d+', text))) + ['architecture/02-commit.md']
            for ref in refs:
                name = Path(ref).name
                chk(any(scenario.glob("**/" + name)), f'SR: referenced file {ref} exists in scenario')
            scopes = [s['scope'] for s in key['scopes']]
            for scope in ('SPEC-READINESS-INPUTS', 'SPEC-READINESS-REQUIREMENTS'):
                chk(scope in scopes and scope in text, f'SR: scope {scope} in key and brief')
            chk(len(scopes) - 2 == 9, 'SR: AP-only checks = 9')
        if reviewer == 'commit-audit-reviewer':
            chk(quoted_section(SUITE / 'commit-audit-v3.md', '## 裁决口径', text), 'CA: quoted v3 verdict section verbatim with sha')
            chk([s['scope'] for s in key['scopes']] == ['COMMIT-AUDIT-GATE-1', 'COMMIT-AUDIT-GATE-2'], 'CA: two gates')
            issue = scenario / 'candidate/.scratch/0001-dispatch-control/issues/02-publish-dispatch-manifest.md'
            chk('`orderManifestGroups`' in line(issue, 30) and '`orderManifestGroups`' in line(
                scenario / 'base/.scratch/0001-dispatch-control/spec.md', 45), 'CA: twin clean lines 02:30 and spec:45')
    return results


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--work', type=Path, required=True, help='directory holding (or receiving) the materialized copies')
    parser.add_argument('--suite', choices=sorted(SUITES), default='v1')
    args = parser.parse_args()
    results = check(args.work, args.suite)
    for ok, message in results:
        print(('OK  ' if ok else 'FAIL'), message)
    sys.exit(0 if all(ok for ok, _ in results) else 1)
