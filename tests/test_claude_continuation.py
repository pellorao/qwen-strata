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

from tools.reviewer import claude_headless as ch
from tools.reviewer import claude_scenario as cs

FAKE = r'''
import json, os, sys, time
from pathlib import Path
if '--version' in sys.argv:
    print('2.1.303 (Claude Code)'); sys.exit(0)
script = json.loads(Path(os.environ['FAKE_SCRIPT']).read_text())
state = Path(os.environ['FAKE_STATE'])
n = int(state.read_text()) if state.exists() else 0
state.write_text(str(n + 1))
prompt = sys.stdin.read()
resume = sys.argv[sys.argv.index('--resume') + 1] if '--resume' in sys.argv else None
with open(os.environ['FAKE_LOG'], 'a') as log:
    log.write(json.dumps({'n': n, 'argv': sys.argv[1:], 'stdin': prompt, 'resume': resume}) + '\n')
if n and resume != 'sid-1':
    sys.exit(3)
step = script[min(n, len(script) - 1)]
print(json.dumps({'type': 'system', 'subtype': 'init', 'session_id': 'sid-1', 'model': 'm'}), flush=True)
if 'write' in step:
    target = Path(os.environ['FAKE_REPORT'])
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(bytes.fromhex(step['write']) if step.get('hex') else step['write'].encode())
time.sleep(step.get('sleep', 0))
print(json.dumps({'type': 'assistant', 'message': {'id': f'msg{n}', 'usage': {'service_tier': 'standard'}}}), flush=True)
print(json.dumps({'type': 'result', 'subtype': 'success', 'is_error': False, 'result': step['result'],
                  'session_id': 'sid-1', 'num_turns': 2, 'duration_ms': 10, 'duration_api_ms': 5,
                  'usage': {'input_tokens': 100, 'output_tokens': 7, 'cache_read_input_tokens': 1000,
                            'server_tool_use': {'web_search_requests': 0}, 'service_tier': 'standard'},
                  'total_cost_usd': 0.5 * (n + 1), 'modelUsage': {'m': {'inputTokens': 100 * (n + 1),
                                                                         'costUSD': 0.5 * (n + 1)}},
                  **step.get('fields', {})}), flush=True)
sys.exit(step.get('exit', 0))
'''
READY = '{"status":"ready"}'
INCOMPLETE = '{"status":"incomplete","reason":"Time limit reached."}'
REPORT = '.tmp/reports/review-result.md'


class ContinuationTest(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.base, True)
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

    def run_script(self, script, limit=60, clock=time.time):
        argv = [sys.executable, str(self.fake), '-p', '--settings', '{"same": true}']
        return ch.execute_continued(self.out, 'the handoff\n', argv, self.env(script), self.work, REPORT, limit,
                                    self.base / 'started-at.txt', clock=clock)

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

    def test_one_early_exit_gets_arw_instruction_in_the_same_session(self):
        result = self.run_script([{'result': INCOMPLETE}, {'write': '- finding\n', 'result': READY}])
        c = result['continuation']
        self.assertEqual((c['stop'], c['early_exit_count'], c['continue_count'], c['session_id']),
                         ('delivered', 1, 0, 'sid-1'))
        first, second = self.calls()
        self.assertEqual(second['argv'], first['argv'] + ['--resume', 'sid-1'])  # same argv and settings
        self.assertEqual(second['stdin'], 'The bound report is missing. ' + ch.ARW_CONTINUE_BODY)
        self.assertEqual((self.out / 'prompt-sent-1.md').read_text(), second['stdin'])
        self.assertEqual([s['report'] for s in c['segments'][:1]], ['missing'])
        summary = ch.stream_summary(ch.segment_streams(self.out))
        self.assertEqual((summary['usage']['input_tokens'], summary['usage']['output_tokens'], summary['num_turns']),
                         (200, 14, 4))  # per-result usage summed over both segments
        self.assertEqual((summary['total_cost_usd'], summary['modelUsage']['m']['costUSD'], summary['result_events']),
                         (1.0, 1.0, 2))  # cumulative fields from the last result
        self.assertEqual(summary['service_tiers'], {'standard': 2})
        from tools.reviewer.inspect_session import inspect_claude
        view = inspect_claude(self.out / 'stream.jsonl', str(self.work))  # the session check reads every segment
        self.assertEqual((view['result_events'], view['threadId'], view['work_seconds']), (2, 'sid-1', 0.02))
        harness = [m['text'] for m in view['messages'] if m['role'] == 'harness']
        self.assertEqual(harness, ['continuation (stream-1.jsonl): ' + second['stdin']])

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

    def test_hard_limit_stops_the_continued_segment(self):
        script = [{'result': INCOMPLETE}, {'sleep': 30, 'result': READY}]
        started = time.time()
        result = self.run_script(script, limit=3)
        c = result['continuation']
        self.assertEqual((c['stop'], result['hard_interrupt'], c['early_exit_count']), ('hard_limit', True, 1))
        self.assertLess(time.time() - started, 25)  # the limit counts from the first segment's start
        self.assertLess(result['wall_seconds'], 15)
        # F-B/F-C: the killed last segment has no result; accounting uses the one before, sums are lower bounds
        streams = ch.segment_streams(self.out)
        self.assertEqual(ch.accounting_stream(streams), self.out / 'stream.jsonl')
        summary = ch.stream_summary(streams)
        self.assertEqual((summary['segments'], summary['segments_without_result'], summary['usage_bound'],
                          summary['total_cost_usd']), (2, 1, 'lower', 0.5))
        self.assertTrue(cs.checks({'summary': {**summary, 'modelUsage': {'m': {}}}, 'exit': -9, 'hard_interrupt': True,
                                   'continuation': c}, 'm', False)['ended_normally'])

    def test_killed_segment_work_time_is_its_timestamp_span(self):
        from tools.reviewer.inspect_session import inspect_claude
        stamp = lambda s: f'2026-10-20T01:00:{s:02d}.000Z'
        event = lambda kind, s: json.dumps({'type': kind, 'timestamp': stamp(s), 'message': {
            'role': kind, 'content': [{'type': 'text', 'text': 'x'}]}})
        result = lambda ms: json.dumps({'type': 'result', 'duration_ms': ms, 'num_turns': 1, 'result': INCOMPLETE,
                                        'total_cost_usd': 0.25})
        (self.out / 'stream.jsonl').write_text('\n'.join([event('assistant', 0), event('assistant', 4), result(4000)]))
        (self.out / 'stream-1.jsonl').write_text('\n'.join([event('assistant', 10), event('assistant', 17)]))
        view = inspect_claude(self.out / 'stream.jsonl', str(self.work))
        self.assertEqual((view['work_seconds'], view['segments'], view['segments_without_result']), (11.0, 2, 1))
        self.assertEqual(view['work_time_source'], 'event timestamp span + result duration_ms')
        (self.out / 'stream-1.jsonl').write_text(json.dumps({'type': 'result', 'duration_ms': 1000, 'total_cost_usd': 0.1}))
        summary = ch.stream_summary(ch.segment_streams(self.out))
        self.assertEqual((round(summary['total_cost_usd'], 3), summary['usage_bound']), (0.35, 'complete'))

    def test_no_session_is_a_harness_fault(self):
        summary = {'result_event': True, 'modelUsage': {'m': {}}}
        check = lambda stop: cs.checks({'summary': summary, 'exit': 0, 'continuation': {'stop': stop}}, 'm', False)
        self.assertTrue(check('delivered')['ended_normally'])
        self.assertFalse(check('no_session')['ended_normally'])

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

        def segments(out, prompt_text, argv, env, work, limit, started_file, report):
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
        argv = [sys.executable, '-c', 'import sys; sys.stdin.read(); sys.exit(1)']
        result = ch.execute_continued(self.out, 'h', argv, env, self.work, REPORT, 30)
        self.assertEqual(result['continuation']['stop'], 'abnormal_end')

    def test_error_kinds(self):
        # F4: result fields as Claude Code 2.1.303 wrote them against a mock server (2026-10-20)
        toolong = {'is_error': True, 'terminal_reason': 'prompt_too_long', 'api_error_status': 400,
                   'result': 'Prompt is too long · the request is ~1200000 tokens (limit 1000000)'}
        maxtok = {'is_error': True, 'terminal_reason': 'api_error', 'api_error_status': None,
                  'result': "API Error: Claude's response exceeded the 128000 output token maximum. To configure"}
        badreq = {'is_error': True, 'terminal_reason': 'api_error', 'api_error_status': 400,
                  'result': 'API Error: 400 something malformed'}
        self.assertEqual([ch.error_kind(r) for r in (toolong, maxtok, badreq, {'is_error': False}, None)],
                         ['model', 'model', 'api', None, None])
        result = self.run_script([{'result': INCOMPLETE}, {'write': '- part\n', 'result': maxtok['result'],
                                                           'fields': maxtok, 'exit': 1}])
        c = result['continuation']
        self.assertEqual((c['stop'], c['early_exit_count'], len(self.calls())), ('model_error', 1, 2))
        summary = ch.stream_summary(ch.segment_streams(self.out))
        self.assertEqual((summary['is_error'], summary['error_kind']), (True, 'model'))
        valid = {'summary': {**summary, 'modelUsage': {'m': {}}}, 'exit': 1}
        self.assertTrue(cs.checks(valid, 'm', False)['ended_normally'])  # scored on the written report
        self.reset()
        result = self.run_script([{'result': badreq['result'], 'fields': badreq, 'exit': 1}])
        self.assertEqual(result['continuation']['stop'], 'abnormal_end')
        summary = ch.stream_summary(ch.segment_streams(self.out))
        self.assertEqual(summary['error_kind'], 'api')
        self.assertFalse(cs.checks({'summary': summary, 'exit': 1}, 'm', False)['ended_normally'])

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
        import subprocess
        from tools.reviewer.review_deadlines import REMINDER
        started = self.base / 'started'
        started.write_text(repr(time.time() - 300))  # T = 540 s: reminder at T/2 = 270 s, lead 270 s
        hook, flag = ch.reminder_hook(self.base, started, ch.reminder_time(540), hard=540)
        out = json.loads(subprocess.run(hook['command'].split(), capture_output=True, text=True).stdout)
        text = out['hookSpecificOutput']['additionalContext']
        self.assertTrue(text.startswith(REMINDER.replace('最多5分钟', '最多270秒') + ' 硬截止为'), text)
        remaining = int(text.split('当前剩余')[1].split('秒')[0])
        self.assertTrue(235 <= remaining <= 240, remaining)
        self.assertEqual(json.loads(flag.read_text())['text'], text)
        started.write_text(repr(time.time() - 3400))
        flag.unlink()
        hook, _ = ch.reminder_hook(self.base, started, 3300, hard=3600)  # a 5-minute lead keeps the original text
        text = json.loads(subprocess.run(hook['command'].split(), capture_output=True, text=True).stdout)[
            'hookSpecificOutput']['additionalContext']
        self.assertTrue(text.startswith(REMINDER + ' 硬截止为'))

    def test_scenario_record_carries_the_instance_pause_events(self):
        result = {'continuation': {'stop': 'delivered', 'delivered': True, 'early_exit_count': 10, 'continue_count': 1,
                                   'arw_pause_events': [{'early_exit_count': 10}], 'segments': [{}] * 11,
                                   'session_id': 's'}}
        records = [{'k': 0, 'continuation': cs.continuation_record(result)},
                   {'k': 1, 'continuation': cs.continuation_record({'continuation': {'early_exit_count': 2}})}]
        self.assertEqual(records[0]['continuation']['segments'], 11)
        self.assertEqual(cs.pause_summary(records), {'arw_pause_events': [{'early_exit_count': 10, 'handoff': 0}],
                                                     'continue_count': 1, 'early_exit_count': 12})


if __name__ == '__main__':
    unittest.main()
