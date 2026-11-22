"""Zero-model tests of the Claude Code path's ARW early-exit continuation (claude_headless.execute_continued).

A scripted fake `claude` stands in for Claude Code: each invocation plays the next step of a script (write the bound
report or not, return a final message, sleep), prints stream-json events and logs its argv and stdin."""
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from tools.strata import claude_headless as ch
from tools.strata.review_deadlines import REMINDER

FAKE = r'''
import json, os, queue, sys, threading, time
from pathlib import Path
if '--version' in sys.argv:
    print('2.1.303 (Claude Code)'); sys.exit(0)
# stream-json input as Claude Code reads it: one JSON line per user message or control request, stdin open meanwhile.
script = json.loads(Path(os.environ['FAKE_SCRIPT']).read_text())
state = Path(os.environ['FAKE_STATE'])
n = int(state.read_text()) if state.exists() else 0
state.write_text(str(n + 1))
lines = queue.Queue()
def feed():
    for raw in sys.stdin:
        lines.put(json.loads(raw))
    lines.put(None)
threading.Thread(target=feed, daemon=True).start()
emit = lambda e: print(json.dumps(e), flush=True)
first = lines.get()
prompt = first['message']['content']
resume = sys.argv[sys.argv.index('--resume') + 1] if '--resume' in sys.argv else None
log = lambda **kw: open(os.environ['FAKE_LOG'], 'a').write(json.dumps(kw) + '\n')
log(n=n, argv=sys.argv[1:], stdin=prompt, resume=resume)
if n and resume != 'sid-1':
    sys.exit(3)
step = script[min(n, len(script) - 1)]
def result(text, **fields):
    emit({'type': 'result', 'subtype': 'success', 'is_error': False, 'result': text, 'terminal_reason': 'completed',
          'session_id': 'sid-1', 'num_turns': 2, 'duration_ms': 10, 'duration_api_ms': 5,
          'usage': {'input_tokens': 100, 'output_tokens': 7, 'cache_read_input_tokens': 1000,
                    'server_tool_use': {'web_search_requests': 0}, 'service_tier': 'standard'},
          'total_cost_usd': 0.5 * (n + 1), 'modelUsage': {'m': {'inputTokens': 100 * (n + 1), 'costUSD': 0.5 * (n + 1)}},
          **fields})
replay = lambda m: emit({'type': 'user', 'isReplay': True, 'uuid': m['uuid'], 'message': m['message']})
emit({'type': 'system', 'subtype': 'init', 'session_id': 'sid-1', 'model': 'm'})
replay(first)
if 'write' in step:
    target = Path(os.environ['FAKE_REPORT'])
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(bytes.fromhex(step['write']) if step.get('hex') else step['write'].encode())
if step.get('tool'):
    emit({'type': 'assistant', 'message': {'id': f'tu{n}', 'content': [{'type': 'tool_use', 'id': 'toolu_1', 'name': 'Bash'}]}})
pending, aborted, closed = [], None, False
end = time.time() + step.get('sleep', 0)
while time.time() < end:
    try:
        m = lines.get(timeout=0.02)
    except queue.Empty:
        continue
    if m is None:
        closed = True
        continue
    log(n=n, input=m)
    if m['type'] == 'control_request':
        emit({'type': 'control_response', 'response': {'subtype': 'success', 'request_id': m['request_id']}})
        if step.get('ignore_interrupt'):
            continue
        aborted = 'aborted_tools' if step.get('tool') else 'aborted_streaming'
        break
    pending.append(m)
    if m.get('priority') == 'now' and not step.get('tool'):
        aborted = 'aborted_streaming'  # generation is cut at once; a running tool is waited for
        break
if aborted:
    if step.get('tool'):
        emit({'type': 'user', 'message': {'content': [{'type': 'tool_result', 'tool_use_id': 'toolu_1', 'is_error': True,
                                                       'content': 'rejected'}]}})
    emit({'type': 'result', 'subtype': 'error_during_execution', 'is_error': True, 'terminal_reason': aborted,
          'session_id': 'sid-1', 'num_turns': 1, 'duration_ms': 5, 'duration_api_ms': 5,
          'usage': {'input_tokens': 0, 'output_tokens': 0}, 'total_cost_usd': 0.5 * (n + 1) - 0.25})
else:
    if step.get('tool'):
        emit({'type': 'user', 'message': {'content': [{'type': 'tool_result', 'tool_use_id': 'toolu_1', 'content': 'ok'}]}})
    if not pending:
        emit({'type': 'assistant', 'message': {'id': f'msg{n}', 'usage': {'service_tier': 'standard'}}})
        result(step['result'], **step.get('fields', {}))
for m in pending:  # each queued message starts the next turn
    replay(m)
    emit({'type': 'assistant', 'message': {'id': f'msg{n}', 'usage': {'service_tier': 'standard'}}})
    result(step['result'], **step.get('fields', {}))
while not closed:
    m = lines.get()
    if m is None:
        break
    log(n=n, input=m)
    if m['type'] == 'user':
        replay(m)
        result(step['result'])
sys.exit(step.get('exit', 0))
'''
READY = '{"status":"ready"}'
INCOMPLETE = '{"status":"incomplete","reason":"Time limit reached."}'
REPORT = '.tmp/reports/review-result.md'


class ContinuationTest(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.base, True)
        (self.base / 'fake-tmp-root').mkdir()   # not the real /tmp: its entry count must not decide the result (SHARED_TMP_LIMIT)
        patcher = mock.patch.object(ch, 'SHARED_TMP_ROOT', self.base / 'fake-tmp-root')
        patcher.start()
        self.addCleanup(patcher.stop)
        poll = mock.patch.object(ch, 'POLL', 0.005)  # the polling interval only paces the loop, not what it decides
        poll.start()
        self.addCleanup(poll.stop)
        self.work = self.base / 'work'
        self.work.mkdir()
        (self.work / 'src.txt').write_text('input\n')
        self.out = self.base / 'out'
        self.out.mkdir()
        self.fake = self.base / 'fake.py'
        self.fake.write_text(FAKE)
        self.log = self.base / 'log.jsonl'

    def env(self, script):
        (self.base / 'script.json').write_text(json.dumps(script))
        return {'PATH': os.environ['PATH'], 'FAKE_SCRIPT': str(self.base / 'script.json'),
                'FAKE_STATE': str(self.base / 'state'), 'FAKE_LOG': str(self.log),
                'FAKE_REPORT': str(self.work / REPORT)}

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def run_script(self, script, limit=60, clock=time.time, reminder_after=None):
        argv = [sys.executable, str(self.fake), '-p', '--settings', '{"same": true}']
        self.deadline = ch.Deadline(self.out, limit, reminder_after, scenario=True)
        return ch.execute_continued(self.out, 'the handoff\n', argv, self.env(script), self.work, REPORT, limit,
                                    self.base / 'started-at.txt', clock=clock, deadline=self.deadline)

    def inputs(self):
        return [call['input'] for call in self.calls() if 'input' in call]

    def test_first_delivery_runs_once_as_before(self):
        result = self.run_script([{'write': '- finding\n', 'result': READY}])
        c = result['continuation']
        self.assertEqual((c['stop'], c['early_exit_count'], c['continue_count'], c['arw_pause_events']),
                         ('delivered', 0, 0, []))
        self.assertEqual(len(self.calls()), 1)
        self.assertNotIn('--resume', self.calls()[0]['argv'])
        self.assertEqual((self.out / 'prompt-sent.md').read_text(), 'the handoff\n')
        self.assertEqual(sorted(p.name for p in self.out.glob('stream*')), ['stream.err', 'stream.jsonl'])
        self.assertEqual(result['changed_files'], [REPORT])
        for key in ('exit', 'hard_interrupt', 'started_at', 'ended_at', 'wall_seconds', 'pid'):
            self.assertIn(key, result)  # the keys of a single execute() stay


    def test_tenth_early_exit_pauses_and_the_user_continues(self):
        script = [{'write': '- partial\n', 'result': INCOMPLETE}] * 10 + [{'result': READY}]
        result = self.run_script(script)
        c = result['continuation']
        self.assertEqual((c['stop'], c['early_exit_count'], c['continue_count']), ('delivered', 10, 1))
        stdin = [call['stdin'] for call in self.calls()]
        self.assertEqual(stdin[1:10], [ch.ARW_REPORT_EXISTS] * 9)
        self.assertEqual(stdin[10], '继续')
        self.assertEqual(ch.CONTINUE_MESSAGE, '继续')
        [event] = c['arw_pause_events']
        self.assertEqual((event['early_exit_count'], event['continue_count'], event['segment']), (10, 0, 9))
        self.assertTrue(event['text'].startswith('The Reviewer runtime paused this same task after 10 normally'))
        self.assertEqual(event['continued']['message'], '继续')
        self.assertEqual(len(ch.segment_streams(self.out)), 11)

    def test_pauses_repeat_every_five_after_the_tenth(self):
        script = [{'write': '- partial\n', 'result': INCOMPLETE}] * 15 + [{'result': READY}]
        c = self.run_script(script)['continuation']
        self.assertEqual([e['early_exit_count'] for e in c['arw_pause_events']], [10, 15])
        self.assertEqual([e['continue_count'] for e in c['arw_pause_events']], [0, 1])
        stdin = [call['stdin'] for call in self.calls()]
        self.assertEqual([i for i, s in enumerate(stdin) if s == '继续'], [10, 15])



    def test_reminder_during_a_tool_interrupts_first(self):
        started = time.time()
        result = self.run_script([{'tool': True, 'sleep': 20, 'write': '- f\n', 'result': READY}], reminder_after=0.3)
        self.assertLess(time.time() - started, 10)  # not after the tool's remaining time
        self.assertEqual(result['continuation']['stop'], 'delivered')
        interrupt, message = self.inputs()
        self.assertEqual((interrupt['type'], interrupt['request']['subtype']), ('control_request', 'interrupt'))
        self.assertEqual((message['type'], message['priority']), ('user', 'now'))
        reminder = json.loads((self.out / 'deadline-handoff.json').read_text())['reminder']
        self.assertEqual((reminder['method'], reminder['status'], reminder['interrupt_request']['response_subtype'],
                          reminder['interrupt_request']['turn_result_seen']), ('interrupt+now', 'accepted', 'success', True))
        summary = ch.stream_summary(ch.segment_streams(self.out))
        self.assertEqual((summary['is_error'], [r['terminal_reason'] for r in summary['reminder_interrupts']],
                          summary['usage_bound']), (False, ['aborted_tools'], 'complete'))

    def test_reminder_in_a_continued_segment_names_that_segment(self):
        result = self.run_script([{'result': INCOMPLETE}, {'sleep': 20, 'write': '- f\n', 'result': READY}],
                                 reminder_after=0.3)
        self.assertEqual((result['continuation']['stop'], len(result['continuation']['segments'])), ('delivered', 2))
        reminder = json.loads((self.out / 'deadline-handoff.json').read_text())['reminder']
        self.assertEqual((reminder['stream'], reminder['status']), ('stream-1.jsonl', 'accepted'))
        summary = ch.stream_summary(ch.segment_streams(self.out))
        self.assertEqual((summary['is_error'], len(summary['reminder_interrupts'])), (False, 1))

    def test_turn_is_over_after_the_last_message_is_answered(self):
        import threading
        session = object.__new__(ch.Session)
        session.lock, session.written, session.replayed, session.results = threading.Lock(), ['a', 'b'], {}, []
        self.assertFalse(session.turn_over())
        session.results.append((3, {}))  # the turn 'b' cut short
        session.replayed['b'] = (5, 0.0)  # 'a' arrived merged with 'b' and is never replayed (mock gate, reminder at 0)
        self.assertFalse(session.turn_over())
        session.results.append((9, {}))
        self.assertTrue(session.turn_over())

    def test_only_the_turn_in_flight_at_delivery_is_exempt(self):
        from tools.strata import reminder_interrupt as ri
        events = [{'type': 'result', 'subtype': 'error_during_execution', 'is_error': True, 'terminal_reason': 'api_error',
                   'result': 'API Error: 500'},
                  {'type': 'user', 'isReplay': True, 'uuid': 'u'},
                  {'type': 'result', 'subtype': 'error_during_execution', 'is_error': True,
                   'terminal_reason': 'aborted_streaming'},
                  {'type': 'result', 'subtype': 'success', 'is_error': False, 'terminal_reason': 'completed', 'result': READY}]
        stream = self.out / 'stream.jsonl'
        stream.write_text('\n'.join(json.dumps(e) for e in events) + '\n')
        record = lambda **kw: (self.out / 'deadline-handoff.json').write_text(json.dumps(
            {'reminder': {'attempted_at': 1, 'stream': 'stream.jsonl', 'stream_line': 1, **kw}, 'interrupt': None}))
        results = [(i, e) for i, e in enumerate(events) if e['type'] == 'result']
        record(status='accepted')
        self.assertEqual(ri.stream_exempt(stream, results), {2: 'reminder'})  # the earlier error stays an error
        summary = ch.stream_summary(stream)
        self.assertEqual((summary['is_error'], summary['error_kind'], len(summary['reminder_interrupts'])), (True, None, 1))
        record(status='unknown')  # never delivered: nothing is ours
        self.assertEqual(ri.stream_exempt(stream, results), {})
        record(status='unknown', interrupt_request={'response_subtype': 'success'})  # the interrupt itself landed
        self.assertEqual(ri.stream_exempt(stream, results), {2: 'reminder'})
        (self.out / 'deadline-handoff.json').write_text(json.dumps({'reminder': {
            'stream': 'stream-1.jsonl', 'stream_line': 1, 'status': 'accepted'}}))
        self.assertEqual(ri.stream_exempt(stream, results), {})  # another segment's event
        self.assertEqual(ch.stream_summary(stream)['error_kind'], None)  # the last result is a success either way



    def test_run_tmp_is_removed_at_closeout(self):
        root = self.base / 'run'
        work = root / 'work'
        work.mkdir(parents=True)
        tmp = ch.run_tmp(work)
        (tmp / 'claude-1000/locked').mkdir(parents=True)
        (tmp / 'claude-1000/locked/out.txt').write_text('12345')
        os.chmod(tmp / 'claude-1000/locked', 0o500)  # a read-only directory a sandboxed command left
        (root / 'answer.md').write_text('kept\n')
        self.assertEqual(ch.remove_run_tmp(work), 5)
        self.assertFalse(tmp.exists())
        self.assertTrue(work.is_dir() and (root / 'answer.md').exists())  # nothing else in the run root
        self.assertIsNone(ch.remove_run_tmp(work))

    def test_run_closeout_moves_session_files_then_removes_the_run_tmp(self):
        from unittest import mock
        seen = {}

        def segments(out, prompt_text, argv, env, work, limit, started_file, report, deadline=None):
            config = self.base / 'cfg'
            (config / 'projects' / ch.project_slug(work)).mkdir(parents=True)
            (Path(work).parent / 'tmp/leftover.txt').write_text('x')
            (Path(work) / 'r').mkdir(exist_ok=True)
            (Path(work) / 'r/report.md').write_text('- f\n')
            (out / 'stream.jsonl').write_text(json.dumps({'type': 'result', 'is_error': False, 'result': READY}) + '\n')
            seen.update(work=Path(work), config=config)
            return {'exit': 0, 'hard_interrupt': False}
        prompt = self.base / 'p.md'
        prompt.write_text('h\n')
        with mock.patch.object(ch, 'run_segments', segments), \
                mock.patch.object(ch, 'config_root', lambda backend, work: seen['config']):
            result = ch.run(self.base / 'run', prompt, 'anthropic', 'm', 'high', 'x', writes=['r'], startup=False,
                            base=self.base / 'runs', record=False, claude=sys.executable, report='r/report.md')
        self.assertEqual(result['run_tmp_removed'], 1)
        self.assertFalse((seen['work'].parent / 'tmp').exists())
        self.assertTrue((self.base / 'run/session-files' / ch.project_slug(seen['work'])).is_dir())
        self.assertTrue((self.base / 'run/outputs/r/report.md').exists())  # the answer is kept

    def test_session_files_move_into_the_run_record(self):
        work = Path('/var/tmp/qwen-claude/x-1/work')
        self.assertEqual(ch.project_slug(work), '-var-tmp-qwen-claude-x-1-work')
        config = self.base / 'claude-config'
        own = config / 'projects' / ch.project_slug(work)
        (own / 'tool-results').mkdir(parents=True)
        (own / 'sid.jsonl').write_text('{}\n')
        (config / 'projects/-other').mkdir()
        self.assertEqual(ch.keep_session_files(work, config, self.out), 'session-files/' + own.name)
        self.assertTrue((self.out / 'session-files' / own.name / 'sid.jsonl').exists())
        self.assertFalse(own.exists())
        self.assertTrue((config / 'projects/-other').is_dir())  # only this run's slug moves
        self.assertIsNone(ch.keep_session_files(work, config, self.out))

    def test_no_new_segment_once_the_limit_has_passed(self):
        result = self.run_script([{'result': INCOMPLETE}], limit=50, clock=lambda: time.time() + 100)
        self.assertEqual(result['continuation']['stop'], 'deadline_between_segments')
        self.assertEqual(len(self.calls()), 1)

    def test_abnormal_end_does_not_continue(self):
        script = [{'result': INCOMPLETE}]
        env = self.env(script)
        argv = [sys.executable, '-c', 'import sys; sys.stdin.readline(); sys.exit(1)']
        result = ch.execute_continued(self.out, 'h', argv, env, self.work, REPORT, 30)
        self.assertEqual(result['continuation']['stop'], 'abnormal_end')


    def reset(self):
        for p in (self.base / 'state', self.log):
            p.unlink(missing_ok=True)
        shutil.rmtree(self.out)
        self.out.mkdir()

    def test_delivery_rules_follow_arw(self):
        report = self.work / 'r.md'
        self.assertEqual(ch.early_exit(READY, report)['report'], 'missing')
        report.write_text(' \n﻿')
        check = ch.early_exit(READY, report)  # whitespace only (JavaScript trim) is empty
        self.assertEqual((check['delivered'], check['counted']), (False, True))
        self.assertTrue(check['instruction'].startswith('The bound report is empty. Complete successful delivery'))
        report.write_text('No findings.')
        self.assertTrue(ch.early_exit(' {"status": "ready"}\n', report)['delivered'])
        for final in ('{"status":"ready","note":1}', 'Done. {"status":"ready"}', '', None, INCOMPLETE):
            check = ch.early_exit(final, report)
            self.assertEqual((check['delivered'], check['instruction']), (False, ch.ARW_REPORT_EXISTS), final)
        self.assertEqual(ch.final_status('{"status":"incomplete","reason":" "}'), None)
        self.assertEqual(ch.final_status(INCOMPLETE), 'incomplete')
        report.write_bytes(b'\xff- x\n')
        check = ch.early_exit(READY, report)  # a recoverable read: continued, not counted
        self.assertEqual((check['continuable'], check['counted']), (True, False))
        self.assertTrue(check['instruction'].startswith(
            'The original bound report could not be read: filesystem-text-decoding-failed: The encoded data was not '
            'valid for encoding utf-8. Correct this recoverable error'))
        report.unlink()
        report.symlink_to(self.work / 'src.txt')
        self.assertEqual(ch.early_exit(READY, report)['continuable'], False)

    def test_undecodable_report_continues_without_counting(self):
        script = [{'write': 'ff2d', 'hex': True, 'result': READY}, {'write': '- fixed\n', 'result': READY}]
        c = self.run_script(script)['continuation']
        self.assertEqual((c['stop'], c['early_exit_count']), ('delivered', 0))

    def test_run_persists_the_session_only_for_continued_runs(self):
        common = ('anthropic', 'm', 'high', self.work, ['r'], {'s': 1})
        self.assertIn('--no-session-persistence', ch.command(*common, startup=False))
        self.assertNotIn('--no-session-persistence', ch.command(*common, startup=False, persist=True))

    def test_scenario_reminder_rewrites_the_lead_and_gives_the_remaining_seconds(self):
        deadline = ch.Deadline(self.out, 540, ch.reminder_time(540), scenario=True)  # reminder at T/2, lead 270 s
        now = time.time()
        deadline.begin(now - 300)
        text = deadline.text(now)
        self.assertTrue(text.startswith(REMINDER.replace('最多5分钟', '最多270秒') + ' 硬截止为'), text)
        self.assertEqual(int(text.split('当前剩余')[1].split('秒')[0]), 240)
        self.assertTrue(deadline.reminder_due(now) and not deadline.hard_due(now))
        deadline = ch.Deadline(self.out, 3600, 3300, scenario=True)  # a 5-minute lead keeps the original text
        deadline.begin(now - 3400)
        self.assertTrue(deadline.text(now).startswith(REMINDER + ' 硬截止为'))
        self.assertEqual(ch.Deadline(self.out, 3600, 3300).text(now), REMINDER)  # not a scenario run: the fixed text
        self.assertFalse(ch.Deadline(self.out, 10).reminder_due(now))  # no reminder without a time


    def run_recorded(self, **patches):
        from unittest import mock
        def segments(out, prompt_text, argv, env, work, limit, started_file, report, deadline=None):
            (out / 'stream.jsonl').write_text(json.dumps({'type': 'result', 'is_error': False, 'result': READY}) + '\n')
            return {'exit': 0, 'hard_interrupt': False}
        prompt = self.base / 'p.md'
        prompt.write_text('h\n')
        with mock.patch.object(ch, 'run_segments', segments), \
                mock.patch.object(ch, 'config_root', lambda backend, work: self.base / 'cfg'):
            return ch.run(self.base / 'run', prompt, 'anthropic', 'm', 'high', 'x', startup=False, base=self.base / 'runs',
                          claude=sys.executable, **patches)

    def test_result_is_saved_before_accounting_and_an_absent_script_is_recorded(self):
        from unittest import mock
        seen = {}

        def account(stream, label, effort, out, estimate=None):
            seen['saved_first'] = (out / 'result.json').exists()
            return {'estimate_exit': 0, 'estimate_note': None}
        with mock.patch.object(ch, 'account', account):
            self.run_recorded()
        self.assertTrue(seen['saved_first'])
        missing = self.base / 'no-such-estimate.sh'
        self.assertEqual(ch.account(self.base / 's.jsonl', 'x', 'high', self.base, estimate=missing)['estimate_exit'], None)
        self.assertIn('absent', ch.account(self.base / 's.jsonl', 'x', 'high', self.base, estimate=missing)['estimate_note'])

    def test_failing_accounting_never_loses_the_result(self):
        from unittest import mock
        with mock.patch.object(ch, 'account', side_effect=OSError('boom')):
            result = self.run_recorded()
        saved = json.loads((self.base / 'run/result.json').read_text())
        self.assertIsNone(saved['estimate_exit'])
        self.assertIn('boom', saved['estimate_note'])
        self.assertEqual(saved['exit'], result['exit'])

    def test_account_records_a_script_that_cannot_start(self):
        script = self.base / 'estimate.sh'
        script.write_text('#!/nonexistent/interpreter\n')
        script.chmod(0o755)
        done = ch.account(self.base / 's.jsonl', 'x', 'high', self.base, estimate=script)
        self.assertIsNone(done['estimate_exit'])
        self.assertTrue(done['estimate_note'].startswith('failed:'))
        ok = self.base / 'ok.sh'
        ok.write_text('#!/bin/sh\necho added\nexit 3\n')
        ok.chmod(0o755)
        self.assertEqual(ch.account(self.base / 's.jsonl', 'x', 'high', self.base, estimate=ok), {'estimate_exit': 3, 'estimate_note': None})


class StrataRunCleanupTest(unittest.TestCase):
    """strata_run's finally: the service log is saved first and a cleanup failure never masks the run's exception."""
    def setUp(self):
        self.base = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.base, True)
        self.out = self.base / 'out'
        self.out.mkdir()
        self.work = self.base / 'case/work'
        self.work.mkdir(parents=True)

    def call(self, run_error, stop_error):
        from contextlib import contextmanager
        from unittest import mock
        host = mock.MagicMock()
        host.installation = self.base
        host.log_bytes_since.return_value = b'service text'
        host.metadata.return_value = {}
        host.installed_release.return_value = {}
        owner = mock.MagicMock()
        owner.start.return_value = ({'native_health': {}}, 1.0)

        @contextmanager
        def controller(folder):
            yield owner
        host.controller = controller

        def stop(*args):
            if stop_error:
                raise stop_error
            return {'status': 'stopped'}, [], {}

        def segments(*args, **kwargs):
            if run_error:
                raise run_error
            return {'exit': 0}
        with mock.patch('tools.ops.measurement_host.MeasurementHost', return_value=host), \
                mock.patch('tools.ops.deployment_source.served_model', return_value='IQ3_XXS'), \
                mock.patch('tools.ops.deployment_source.published_tier', return_value={'context_window': 1, 'auto_compact_token_limit': 1}), \
                mock.patch('tools.strata.engine_log.log_offset', return_value=0), \
                mock.patch('tools.strata.engine_log.stop_and_capture_engine_log', stop), \
                mock.patch.object(ch, 'strata_environment', return_value={}), \
                mock.patch.object(ch, 'environment', return_value={}), \
                mock.patch.object(ch, 'run_tmp', return_value=self.base / 'tmp'), \
                mock.patch.object(ch, 'run_segments', segments):
            return ch.strata_run(self.out, 'p', [], 'qwen3.8-flash-next-iq3_xxs', 'high', self.work, 60, None, {}, False,
                                 'h')

    def test_run_exception_survives_a_failing_stop_and_the_log_is_kept(self):
        with self.assertRaisesRegex(RuntimeError, 'run failed'):
            self.call(RuntimeError('run failed'), OSError('stop failed'))
        self.assertEqual((self.out / 'service-log.txt').read_text(), 'service text')
        self.assertIn('stop failed', (self.out / 'cleanup-errors.txt').read_text())

    def test_failing_stop_after_a_good_run_still_raises(self):
        with self.assertRaisesRegex(OSError, 'stop failed'):
            self.call(None, OSError('stop failed'))
        self.assertEqual((self.out / 'service-log.txt').read_text(), 'service text')

    def test_clean_run_returns_the_engine_record(self):
        result = self.call(None, None)
        self.assertEqual(result['engine_requests'], [])
        self.assertFalse((self.out / 'cleanup-errors.txt').exists())


if __name__ == '__main__':
    unittest.main()
