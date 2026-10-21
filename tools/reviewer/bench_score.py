"""Final score of one multi-model benchmark instance (benchmarks/multi-model-v1/plan.md), the same for every arm.

Input: a normalized instance record (tools.reviewer.bench_records) and its frozen scenario plan. Steps:
  1. a fresh zero-model ARW preparation from the frozen plan with the instance's own T (arw_dimension.prepare),
     its answer-key contract checked against the instance's original prepared.json (when kept) and each fresh
     scenario repository against what the Reviewer saw (scenario-copies.json or h<k>/files-before.json; .git and
     .tmp left out, git object bytes do not reproduce);
  2. each bound report (sha256 checked) copied to the fresh handoff's reportPath, repaired on an independent copy
     (repair_reviewer_report, with every spill file kept for the handoff) and scored from the repaired copy as a format
     correction when anything changed. A handoff with a recorded report sha256 whose report is not found is an error;
     one that genuinely wrote no report (no file, no sha256) goes upstream as an explicit modelFailure;
  3. upstream score-completed (single_scenario_score.upstream_score, project scoring upgrade applied, the plan's
     Main identity) repeated until no candidate is pending, every pending candidate decided from the instance's
     decision store (<work>/decisions.json, written by tools.reviewer.blind_pool split/override). Decisions are keyed
     by a stable candidate id (the candidateId without the preparation uuid and instance number) so they survive
     fresh preparations, and carry the fingerprint of what the adjudicator saw (blind_pool.fingerprint of the pool
     item); a stored decision is used only while the live candidate has the same fingerprint, otherwise the candidate
     is pending again. Commit Audit candidates get their requirementSource (the requirement row of the finding) from
     the scored review.jsonl before both;
  4. format penalty f (format_penalty.score_repetitions; r also counts the record's final_status_format_errors, 1 for a
     B-class instance whose last final message is not ARW's status form, user 2026-10-20) and the overall merge (user 2026-10-20, reviewer-suite
     「整体罚分只扣一次」; plan §14.1 L445, L453-457):
        final = max(0, scoreBeforePenalty) x (1 - max(0.1 if paused, f, 0.1 if ARW cut))
     scoreBeforePenalty is the repetition score before ARW's 0.9 cut; the cut (a report diagnostic outside the
     project's REPORT_DIAGNOSTIC_TREATMENT, scoring-k.patch) joins the same max, so no overall penalty multiplies
     another. A paused instance loses 0.1 once, however many pauses it had (plan L457). The pause count is the
     record's (recorded or rebuilt per arm, bench_records pause_basis); a record without a basis (pause_known false)
     is refused.

Without decisions for every pending candidate the result is `needs-adjudication` with the pending candidates in
<work>/pending.json. --provisional lower|upper fills the missing ones (lower: not-matched / unsupported, upper: matched
/ supported) and marks the score provisional. --enumerate lists the candidate superset (every association decided
not-matched gives every finding candidate) in <work>/candidates.json for the blind pool; it scores nothing.

The last output line lists the instances whose preparation could be checked neither against an original
prepared.json nor against a manifest of the repository the Reviewer saw.

    python3 -m tools.reviewer.bench_score --id openai/code-spec-v5/sol-high-a1 [--root .tmp/bench-score]
        [--records records.jsonl] [--enumerate | --provisional lower|upper]
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from tools.reviewer import bench_records
from tools.reviewer.blind_pool import fingerprint

ROOT = bench_records.ROOT
DEFAULT_ROOT = ROOT / '.tmp/bench-score'
PAUSE_CUT = 0.1
ARW_CUT = 0.1
# scoring-k.patch REPORT_DIAGNOSTIC_TREATMENT: codes handled by the project (format penalty, record only, or inside a
# case). Any other report diagnostic keeps ARW's 0.9 cut of the repetition.
TREATED_DIAGNOSTICS = {
    'review-format-invalid', 'review-json-invalid', 'review-utf8-invalid', 'review-row-unattributed',
    'review-evidence-overrun', 'review-evidence-invalid', 'evidence-locator-invalid', 'review-row-invalid',
    'requirement-row-invalid', 'requirement-missing', 'requirement-coverage-invalid', 'requirement-duplicate',
    'requirement-conflicting', 'requirement-source-unexpected', 'requirement-source-invalid',
    'requirement-scope-continuation'}
CA_SCOPES = {'COMMIT-AUDIT-GATE-1': re.compile(r'/issues/[^/]+$'), 'COMMIT-AUDIT-GATE-2': re.compile(r'/spec\.md$')}
UUID_INSTANCE = re.compile(r'-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}-instance-\d+')
BOUNDS = {'lower': ('not-matched', 'unsupported'), 'upper': ('matched', 'supported')}


def stable_id(candidate_id):
    """candidateId without the preparation uuid and instance number: the same candidate of the same report under any
    fresh preparation of the same plan."""
    stable, count = UUID_INSTANCE.subn('', candidate_id)
    if count != 1:
        raise ValueError(f'candidate id without exactly one preparation instance: {candidate_id}')
    return stable


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=1) + '\n')


def work_dir(root, record_id):
    return Path(root) / record_id


def load_store(work):
    path = Path(work) / 'decisions.json'
    return json.loads(path.read_text()) if path.is_file() else {'decisions': {}, 'history': []}


def save_store(work, store):
    save(Path(work) / 'decisions.json', store)


# ---- record lookup ------------------------------------------------------------------------------------------------

def find_record(record_id, records=None):
    if records:
        for line in Path(records).read_text().splitlines():
            record = json.loads(line)
            if record['id'] == record_id:
                return record
        raise ValueError(f'{record_id}: not in {records}')
    arm, scenario, name = record_id.split('/')
    root, scenes = bench_records.LAYOUT[arm]
    scene = ROOT / root / scenes[scenario]
    # The whole scene, so the record carries its cell rank (first 5 valid by start time) besides the rejudged validity.
    for record in bench_records.scene_records(arm, scenario, scene):
        if record['id'] == record_id:
            return record
    raise ValueError(f'{record_id}: no such instance directory in {scene}')


# ---- preparation checks -------------------------------------------------------------------------------------------

def contract_binding(prepared_path):
    """Answer-key binding of every prepared instance, without instance ids."""
    out = []
    for contract in json.loads(Path(prepared_path).read_text())['contracts']:
        for instance in contract['instances']:
            expected = instance['expected']
            out.append({'reviewerId': contract.get('reviewerId'),
                        'judgmentBinding': expected['judgmentBinding'], 'problemCount': expected['problemCount'],
                        'cleanCount': expected['cleanCount'],
                        'scopes_sha256': hashlib.sha256(json.dumps(expected['scopes'], sort_keys=True).encode()).hexdigest()})
    return out


def file_tree(folder):
    out = {}
    for path in sorted(Path(folder).rglob('*')):
        rel = path.relative_to(folder)
        if rel.parts[0] in ('.git', '.tmp'):
            continue
        if path.is_symlink():
            out[str(rel)] = 'symlink:' + os.readlink(path)
        elif path.is_file():
            out[str(rel)] = sha256_file(path)
    return out


def run_suffix(scenario_root):
    """Scenario root below its ARW run (`csp/1`, `sr/runtime-migration/1`)."""
    parts = Path(scenario_root).parts
    return '/'.join(parts[parts.index('runs') + 2:])


def seen_tree(record, handoff, scenario_root):
    """Manifest of the scenario repository the Reviewer of this handoff saw, or None."""
    folder = ROOT / record['dir']
    if handoff.get('files_before'):
        return json.loads(Path(handoff['files_before']).read_text()), 'h<k>/files-before.json'
    copies = bench_records.load(folder / 'scenario-copies.json')
    if copies:
        suffix = run_suffix(scenario_root)
        keys = [k for k in copies if k.endswith('/' + suffix)]
        if len(keys) == 1:
            return copies[keys[0]], 'scenario-copies.json'
    return None, 'no manifest kept'


def prepare_fresh(record, work):
    from tools.tuning.arw_dimension import load_plan, prepare
    plan = load_plan(ROOT / record['plan'])[0]
    prep = Path(work) / 'prep'
    if not (prep / 'preparation.json').is_file():
        if prep.exists():
            shutil.rmtree(prep)
        prepare(plan, None, prep, time_limit_seconds=record['time_limit_seconds'])
    selection = json.loads((prep / 'selection-source.json').read_text())
    if selection.get('review_time_limit_seconds') != record['time_limit_seconds']:
        raise ValueError(f"{prep}: prepared with T {selection.get('review_time_limit_seconds')}, "
                         f"the instance ran with {record['time_limit_seconds']}")
    return plan, json.loads((prep / 'preparation.json').read_text())


def check_preparation(record, prepared):
    checks = {}
    fresh = contract_binding(prepared['preparedPath'])
    if record.get('original_prepared'):
        original = contract_binding(record['original_prepared'])
        checks['contract'] = 'same as the original prepared.json' if fresh == original else 'differs'
        if fresh != original:
            raise ValueError(f"{record['id']}: fresh answer-key contract differs from the original preparation")
    else:
        checks['contract'] = 'original prepared.json not kept (instance cleanup); fresh contract from the frozen plan'
    if len(prepared['handoffs']) < len(record['handoffs']):
        raise ValueError(f"{record['id']}: fresh preparation has fewer handoffs than the instance")
    trees = []
    for handoff, fresh_handoff in zip(record['handoffs'], prepared['handoffs']):
        if handoff['sub_scenario'] != bench_records.sub_scenario(fresh_handoff['instanceId']):
            raise ValueError(f"{record['id']} h{handoff['k']}: sub-scenario differs from the fresh handoff")
        seen, source = seen_tree(record, handoff, fresh_handoff['scenarioRoot'])
        if seen is None:
            trees.append({'k': handoff['k'], 'tree': source})
            continue
        differences = bench_records.tree_differences(seen, file_tree(fresh_handoff['scenarioRoot']))
        if differences:
            raise ValueError(f"{record['id']} h{handoff['k']}: fresh scenario repository differs from {source}: "
                             f"{differences[:10]}")
        trees.append({'k': handoff['k'], 'tree': f'same as {source}'})
    checks['trees'] = trees
    checks['unverified'] = not record.get('original_prepared') and any(t['tree'] == 'no manifest kept' for t in trees)
    return checks


# ---- reports ------------------------------------------------------------------------------------------------------

def place_reports(record, prepared, work):
    """Copy each bound report to its fresh reportPath, repair a copy; the upstream input and the repair records."""
    entries, repairs, rows = {}, {}, []
    for handoff, fresh in zip(record['handoffs'], prepared['handoffs']):
        row = {'k': handoff['k'], 'instanceId': fresh['instanceId'], 'original_instanceId': handoff['instanceId'],
               'report': handoff['report'], 'report_sha256': handoff['report_sha256']}
        rows.append(row)
        if not handoff['report']:
            if handoff.get('report_sha256'):
                raise ValueError(f"{record['id']} h{handoff['k']}: report sha256 recorded but no report file found")
            # Upstream needs an explicit model failure for a handoff without scorable content (zero bytes is not
            # "No findings"): the Reviewer wrote no report at all.
            reason = 'The Reviewer wrote no report (instance record: no report file and no report sha256).'
            entries.setdefault(fresh['reviewerId'], []).append(
                {'instanceId': fresh['instanceId'], 'artifactPaths': None, 'modelFailure': {'reason': reason}})
            repairs[fresh['instanceId']] = None
            row.update(scored='modelFailure: no report', repair={})
            continue
        if handoff.get('report_exists') is False:
            raise ValueError(f"{record['id']} h{handoff['k']}: a report was found although the record says none exists")
        if not handoff['report_ok'] or sha256_file(handoff['report']) != handoff['report_sha256']:
            raise ValueError(f"{record['id']} h{handoff['k']}: report differs from its recorded sha256")
        target = Path(fresh['input']['reportPath'])
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(handoff['report'], target)
        repaired = Path(work) / 'repair' / f"h{handoff['k']}" / target.name
        if repaired.parent.exists():
            shutil.rmtree(repaired.parent)
        repaired.parent.mkdir(parents=True)
        spills = [a for path in handoff.get('spill_files') or [] for a in ('--spill', path)]
        subprocess.run([sys.executable, '-m', 'tools.reviewer.repair_reviewer_report', '--report', str(target),
                        '--out', str(repaired), '--scenario-root', fresh['scenarioRoot'], *spills],
                       cwd=ROOT, check=True, capture_output=True)
        change_record = json.loads(repaired.with_name(repaired.name + '.changes.json').read_text())
        entry = {'instanceId': fresh['instanceId'], 'artifactPaths': [str(target)]}
        if change_record['changes']:
            corrected = target.with_name(target.stem + '.format-corrected' + target.suffix)
            shutil.copyfile(repaired, corrected)
            entry = {'instanceId': fresh['instanceId'], 'artifactPaths': None,
                     'formatCorrection': {'originalReportPath': str(target), 'correctedReportPath': str(corrected)}}
            if all(c['kind'] == 'requirement-line' for c in change_record['details']):
                # The ARW format-correction gate only accepts an original that fails in syntax; a row shift keeps the
                # report syntactically valid, so the corrected copy replaces the fresh copy at the prepared reportPath
                # and is scored as the report itself (the bound original is untouched; the repair record still counts
                # the moves in r; the diagnostics are all project-treated, so no residual cut changes).
                shutil.copyfile(repaired, target)
                corrected.unlink()
                entry = {'instanceId': fresh['instanceId'], 'artifactPaths': [str(target)]}
            repairs[fresh['instanceId']] = change_record
        else:
            repairs[fresh['instanceId']] = None
        spill_changes = [c for c in change_record['details'] if c['kind'] == 'spill-locator']
        row.update(scored='repaired copy' if change_record['changes'] else 'original', repair=change_record['changes'],
                   spill_files=len(handoff.get('spill_files') or []), spill_edits=len(spill_changes),
                   spill_fragments=sum(len(c['converted']) for c in spill_changes),
                   spill_in_range_readable=(change_record.get('diagnostics') or {}).get('inRangeSpillReadable'))
        entries.setdefault(fresh['reviewerId'], []).append(entry)
    upstream_input = {'artifacts': [{'reviewerId': r, 'instances': i} for r, i in entries.items()]}
    return upstream_input, repairs, rows


# ---- upstream loop ------------------------------------------------------------------------------------------------

def parse_reply(reply):
    for text in (reply.stdout, reply.stderr):
        text = text.strip()
        if text.startswith('{'):
            try:
                return json.loads(text)
            except ValueError:
                continue
    raise ValueError(f'score-completed gave no JSON (rc {reply.returncode}): {reply.stderr[-600:]}')


def bound_decision(candidate, bound):
    return next(v for v in BOUNDS[bound] if v in candidate['allowedDecisions'])


def adjudicate(prepared, input_path, work, decide, rounds=10, scorer=None):
    """Run upstream until it is no longer pending. decide(candidate) -> (decision, reason, source) or None.
    Returns (upstream output, candidates by stable id, decisions used, pending candidates)."""
    if scorer is None:
        from tools.reviewer.single_scenario_score import upstream_score as scorer
    seen, used = {}, {}
    for n in range(rounds):
        adjudication = None
        if used:
            adjudication = Path(work) / f'adjudication-{n}.json'
            save(adjudication, {'decisions': [{'candidateId': cid, 'decision': d['decision'], 'reason': d['reason']}
                                              for cid, d in used.items()]})
        up = parse_reply(scorer(prepared['repositoryRoot'], prepared['preparedPath'], input_path, adjudication))
        save(Path(work) / f'upstream-{n}.json', up)
        if up.get('status') != 'needs-adjudication':
            return up, seen, used, []
        pending = []
        for candidate in up.get('candidates', []):
            cid = candidate['candidateId']
            if cid in used:
                raise ValueError(f'{cid}: still pending after its decision was given')
            sid = stable_id(cid)
            if sid in seen and seen[sid]['candidateId'] != cid:
                raise ValueError(f'two candidates share the stable id {sid}')
            seen[sid] = candidate
            choice = decide(candidate)
            if choice is None:
                pending.append(candidate)
                continue
            decision, reason, source = choice
            if decision not in candidate['allowedDecisions']:
                raise ValueError(f'{sid}: decision {decision} not in {candidate["allowedDecisions"]}')
            used[cid] = {'stable_id': sid, 'decision': decision, 'reason': reason, 'source': source}
        if pending:
            return up, seen, used, pending
    raise ValueError(f'candidates still pending after {rounds} rounds')


def stored_choice(store, candidate, scenario):
    """The stored (decision, reason, source) of a live candidate; None when nothing is stored, 'stale' when the stored
    decision was made for other content (fingerprint differs), so the candidate is adjudicated again."""
    stored = store.get(stable_id(candidate['candidateId']))
    if stored is None:
        return None
    if stored.get('fingerprint') != fingerprint(candidate, scenario):
        return 'stale'
    return stored['decision'], stored['reason'], stored.get('source', 'store')


def merge(score_before_penalty, f, paused, arw_cut):
    """User 2026-10-20: one overall deduction, the largest of pause (0.1 once), format f and ARW's residual cut."""
    deduction = max(PAUSE_CUT if paused else 0.0, f, ARW_CUT if arw_cut else 0.0)
    return deduction, max(0.0, score_before_penalty) * (1 - deduction)


def repetition_score(up, repairs, registry=None, final_status_errors=0):
    from tools.reviewer.format_penalty import REGISTRY, score_repetitions
    rows = score_repetitions(up, repairs, registry or REGISTRY, extra_errors=final_status_errors)
    repetitions = [rep for result in up['results'] for rep in result.get('repetitions', [])]
    if len(rows) != 1 or len(repetitions) != 1:
        raise ValueError(f'expected one scored repetition, got {len(repetitions)}')
    row, rep = rows[0], repetitions[0]
    codes = [d.get('code') for d in rep.get('reportDiagnostics') or []]
    cut_codes = sorted({c for c in codes if c not in TREATED_DIAGNOSTICS})
    before = rep['scoreBeforePenalty']
    expected = before * 0.9 if cut_codes else before
    if abs(rep['score'] - expected) > 1e-9:
        raise ValueError(f"ARW score {rep['score']} does not match scoreBeforePenalty {before} with cut codes {cut_codes}")
    return {'scoreBeforePenalty': before, 'arw_score': rep['score'], 'rawScore': rep.get('rawScore'),
            'arw_cut': bool(cut_codes), 'arw_cut_codes': cut_codes, 'report_diagnostic_codes': sorted(set(codes)),
            'r': row['r'], 'rRepairable': row['rRepairable'], 'rUnrepairable': row['rUnrepairable'],
            'rOverrun': row['rOverrun'], 'rFinalStatus': row['rFinalStatus'], 'T_locators': row['T'], 'p': row['p'],
            'f': row['f'],
            'per_handoff': {i['instanceId']: {'score': i.get('score'), 'rawScore': i.get('rawScore'),
                                              'locatorCount': i.get('locatorCount')} for i in rep['instances']}}


def pause_state(record):
    if not record['pause_known']:
        raise ValueError(f"{record['id']}: pauses cannot be established (pause_known false: {record['pause_note']})")
    return {'paused': record['pause_count'] > 0, 'pause_count': record['pause_count'],
            'pause_basis': record.get('pause_basis') or 'record', 'harness_generation': record.get('harness_generation')}


# ---- Commit Audit requirementSource -------------------------------------------------------------------------------

def scored_report(upstream_input, instance_id):
    for artifact in upstream_input['artifacts']:
        for entry in artifact['instances']:
            if entry['instanceId'] == instance_id:
                if entry.get('formatCorrection'):
                    return entry['formatCorrection']['correctedReportPath']
                return (entry.get('artifactPaths') or [None])[0]
    return None


def review_rows(path):
    rows = []
    for line in Path(path).read_text(encoding='utf-8', errors='replace').splitlines():
        if line.strip():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict):
                rows.append(row)
    return rows


def requirement_source(candidate, rows):
    """The requirement row of a Commit Audit candidate's finding in the scored review.jsonl: the only finding row of the
    candidate's gate with the same finding text, or, when the text repeats, the findingIndex-th finding row of that gate
    (the scorer numbers findings per check) with that text. Anything else is an error, never a guess."""
    scope = CA_SCOPES[candidate['check']]
    same = [r for r in rows if r.get('result') != 'satisfied' and 'finding' in r and isinstance(r.get('source'), dict)
            and scope.search(str(r['source'].get('filePath', '')))]
    hits = [r for r in same if r['finding'] == candidate['finding']]
    index = candidate.get('findingIndex')
    if len(hits) == 1:
        row = hits[0]
    elif hits and isinstance(index, int) and index < len(same) and same[index]['finding'] == candidate['finding']:
        row = same[index]
    else:
        raise ValueError(f"{candidate['candidateId']}: no unique requirement row of its finding ({len(hits)} rows)")
    return {'filePath': row['source'].get('filePath'), 'line': row['source'].get('line'),
            'requirement': row.get('requirement')}


def annotate(candidate, scenario, upstream_input, cache):
    """Add requirementSource to a Commit Audit candidate (frozen brief field); others pass unchanged."""
    if not scenario.startswith('commit-audit') or candidate.get('requirementSource') is not None:
        return candidate
    path = scored_report(upstream_input, candidate['instanceId'])
    if path is None:
        raise ValueError(f"{candidate['candidateId']}: no scored report for its instance")
    if path not in cache:
        cache[path] = review_rows(path)
    return {**candidate, 'requirementSource': requirement_source(candidate, cache[path])}


def score_instance(record, work, provisional=None, enumerate_only=False, scorer=None):
    if 'validity_before_rejudge' not in record:
        raise ValueError(f"{record['id']}: record without the validity rejudge (rebuild it with bench_records)")
    if not record['valid']:
        raise ValueError(f"{record['id']}: not a valid instance ({record['validity']})")
    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)
    pause = None if enumerate_only else pause_state(record)
    plan, prepared = prepare_fresh(record, work)
    os.environ['CODEX_THREAD_ID'] = plan['codex_thread_id']
    checks = check_preparation(record, prepared)
    upstream_input, repairs, rows = place_reports(record, prepared, work)
    base = {'id': record['id'], 'arm': record['arm'], 'scenario': record['scenario'], 'config': record['config'],
            'time_limit_seconds': record['time_limit_seconds'], 'checks': checks, 'handoffs': rows,
            'validity_source': record['validity'].get('source'), 'valid_rank': record.get('valid_rank'),
            'main_statistic': record.get('main_statistic'), 'seconds': record.get('seconds'),
            'seconds_adjustment': record.get('seconds_adjustment')}
    if not upstream_input['artifacts']:
        result = {**base, 'status': 'no-report', 'final': 0.0}
        save(work / 'score.json', result)
        return result
    input_path = work / 'score-input.json'
    save(input_path, upstream_input)
    rows_cache = {}
    live = lambda c: annotate(c, record['scenario'], upstream_input, rows_cache)
    if enumerate_only:
        up, seen, used, pending = adjudicate(prepared, input_path, work / 'enumerate',
                                             lambda c: (bound_decision(c, 'lower'), 'enumeration only', 'enumerate'),
                                             scorer=scorer)
        candidates = [{'stable_id': sid, 'record': record['id'], **live(c)} for sid, c in sorted(seen.items())]
        save(work / 'candidates.json', candidates)
        return {**base, 'status': 'enumerated', 'candidates': len(candidates)}
    store = load_store(work)['decisions']
    stale = []

    def decide(candidate):
        choice = stored_choice(store, live(candidate), record['scenario'])
        if choice == 'stale':
            stale.append(stable_id(candidate['candidateId']))
        elif choice is not None:
            return choice
        if provisional:
            return bound_decision(candidate, provisional), f'provisional {provisional} bound: not adjudicated', 'provisional'
        return None

    up, seen, used, pending = adjudicate(prepared, input_path, work / 'upstream', decide, scorer=scorer)
    if pending:
        save(work / 'pending.json', [{'stable_id': stable_id(c['candidateId']), 'record': record['id'], **live(c)}
                                     for c in pending])
        result = {**base, 'status': 'needs-adjudication', 'pending': len(pending), 'decided': len(used),
                  'stale_decisions': sorted(set(stale))}
        save(work / 'score.json', result)
        return result
    if up.get('status') == 'failed':
        result = {**base, 'status': 'upstream-failed', 'diagnostics': up.get('diagnostics')}
        save(work / 'score.json', result)
        return result
    if 'final_status_format_errors' not in record:
        raise ValueError(f"{record['id']}: record without final_status_format_errors (rebuild it with bench_records)")
    scored = repetition_score(up, repairs, final_status_errors=record['final_status_format_errors'])
    deduction, final = merge(scored['scoreBeforePenalty'], scored['f'], pause['paused'], scored['arw_cut'])
    sources = {}
    for d in used.values():
        sources[d['source']] = sources.get(d['source'], 0) + 1
    result = {**base, 'status': 'provisional' if any(d['source'] == 'provisional' for d in used.values()) else 'final',
              'provisional_bound': provisional, **pause, **scored, 'overall_deduction': deduction, 'final': final,
              'decisions': len(used), 'decision_sources': sources, 'stale_decisions': sorted(set(stale)),
              'upstream_status': up.get('status'), 'final_status_basis': record.get('final_status_basis'),
              'template_findings': template_findings(seen.values(), {d['stable_id']: d for d in used.values()}),
              'rule': 'final = max(0, scoreBeforePenalty) x (1 - max(0.1 if paused, f, 0.1 if ARW cut))'}
    save(work / 'score.json', result)
    return result


# ---- template-style findings (ruling 2026-10-21) ------------------------------------------------------------------

TEMPLATE_ROWS = 3
TEMPLATE_RATIO = 0.9


def normalized_finding(text):
    text = re.sub(r'`[^`]*`', '`x`', str(text).lower())
    text = re.sub(r'[\w./-]+:\d+(?:[-,]\d+)*', 'loc', text)
    return re.sub(r'\s+', ' ', re.sub(r'\d+', '0', text)).strip()


def template_findings(candidates, decisions):
    """Clusters of the same or near-identical finding text on >= TEMPLATE_ROWS findings of one instance, with the
    candidates of each cluster that a decision credits (association matched, finding problem-N). Only a flag: the
    ruling (a generic template pasted on many rows is not matched, even where it happens to fit) needs Main's judgment
    of whether the text is generic, so the credited candidates of a generic cluster are corrected by blind_pool
    override, never here."""
    import difflib
    findings = {}
    for c in candidates:
        if c.get('finding') is not None:
            key = (c.get('check') or c.get('problemScope'), c.get('findingIndex'))
            findings.setdefault(c['instanceId'], {})[key] = c['finding']
    out = []
    for iid, texts in sorted(findings.items()):
        groups = []
        for key, text in texts.items():
            n = normalized_finding(text)
            group = next((g for g in groups if g['norm'] == n
                          or difflib.SequenceMatcher(None, g['norm'], n).ratio() >= TEMPLATE_RATIO), None)
            if group is None:
                groups.append({'norm': n, 'text': text, 'keys': [key]})
            else:
                group['keys'].append(key)
        for g in groups:
            if len(g['keys']) < TEMPLATE_ROWS:
                continue
            keys = set(g['keys'])
            credited = []
            for c in candidates:
                if c['instanceId'] != iid or (c.get('check') or c.get('problemScope'), c.get('findingIndex')) not in keys:
                    continue
                d = decisions.get(stable_id(c['candidateId']))
                if d and (d['decision'] == 'matched' or d['decision'].startswith('problem-')):
                    credited.append({'stable_id': d['stable_id'], 'decision': d['decision'], 'source': d['source']})
            out.append({'instanceId': iid, 'findings': len(keys), 'text': g['text'], 'credited': credited})
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--id', action='append', required=True, help='record id arm/scenario/dir; repeatable')
    parser.add_argument('--root', type=Path, default=DEFAULT_ROOT, help='score work root (<root>/<record id>/)')
    parser.add_argument('--records', type=Path, help='bench_records JSON Lines (default: read the instance directory)')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--enumerate', action='store_true', help='write the candidate superset only')
    mode.add_argument('--provisional', choices=sorted(BOUNDS), help='fill missing decisions with this bound')
    args = parser.parse_args()
    unverified = []
    for record_id in args.id:
        record = find_record(record_id, args.records)
        result = score_instance(record, work_dir(args.root, record_id), args.provisional, args.enumerate)
        if result['checks'].get('unverified'):
            unverified.append(record_id)
        print(json.dumps({k: result.get(k) for k in ('id', 'status', 'final', 'scoreBeforePenalty', 'f', 'paused',
                                                      'arw_cut', 'pending', 'candidates')}, ensure_ascii=False))
    print(json.dumps({'preparation_unverified': unverified,
                      'note': 'neither an original prepared.json nor a manifest of the repository the Reviewer saw'
                      }, ensure_ascii=False))


if __name__ == '__main__':
    main()
