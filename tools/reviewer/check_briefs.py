"""Pre-freeze mechanical check of the blind-adjudication briefs against frozen ARW copies and their answer keys.

Each brief is checked against a copy materialized from its frozen source manifest (made in --work when absent):
the ARW Adjudication section is quoted verbatim, the cited answer-key SHA is the materialized key's, only the caller
placeholders remain, the Role exists, the ARW decision block equals the frozen Commit Audit v3 brief's, and the
scenario-specific facts the brief states (decoy lines, file names, scopes, quoted sections) hold in the fixture.

  python3 -m tools.reviewer.check_briefs --work .tmp/<work>/arw
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
BRIEFS = {'code-spec-v5-brief.md': ('code-spec-v5', 'code-spec-reviewer'),
          'code-standards-v5.1-brief.md': ('code-standards-v5.1', 'code-standards-reviewer'),
          'spec-readiness-v4.3-brief.md': ('spec-readiness-v4.3', 'spec-readiness-reviewer')}


def materialized(work, version):
    target = Path(work) / ('arw-' + version)
    if not target.exists():
        subprocess.run([sys.executable, '-m', 'tools.reviewer.freeze_arw_source', '--manifest',
                        str(MANIFESTS / f'manifest-{version}.json'), '--out', str(target)],
                       cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
    return target


def line(path, number):
    lines = Path(path).read_text().splitlines()
    return lines[number - 1] if 0 < number <= len(lines) else ''


def check(work):
    results = []

    def chk(condition, message):
        results.append((bool(condition), message))

    frozen = (SUITE / 'commit-audit-v3-brief.md').read_text()
    block = re.search(r'^## 决定语义[^\n]*\n\n(.*?)^本工程补充（评分 r8\.1', frozen, re.S | re.M).group(1)
    for brief, (version, reviewer) in BRIEFS.items():
        text = (SUITE / brief).read_text()
        arw = materialized(work, version)
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
            design = (SUITE / 'spec-readiness-v4.md').read_text().splitlines(keepends=True)
            start = next(i for i, l in enumerate(design) if l.startswith('### 裁决 brief（新用例）'))
            end = next(i for i in range(start + 1, len(design)) if re.match(r'#{1,3} ', design[i]))
            body = ''.join(design[start + 1:end]).strip() + '\n'
            chk(body in text and hashlib.sha256(body.encode()).hexdigest() in text, 'SR: quoted v4 section verbatim with sha')
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
    return results


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--work', type=Path, required=True, help='directory holding (or receiving) the materialized copies')
    args = parser.parse_args()
    results = check(args.work)
    for ok, message in results:
        print(('OK  ' if ok else 'FAIL'), message)
    sys.exit(0 if all(ok for ok, _ in results) else 1)
