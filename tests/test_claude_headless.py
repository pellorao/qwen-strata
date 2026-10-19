import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tools.reviewer import claude_headless as ch
from tools.safety import claude_gate as gate


class RunnerBuildersTest(unittest.TestCase):
    """Zero-model checks of the Claude Code runner's command, settings, environment and inputs."""
    def setUp(self):
        self.base = Path(tempfile.mkdtemp())
        self.work = ch.workspace('r1', self.base)
        (self.work / 'inputs').mkdir()
        (self.work / 'inputs/a.txt').write_text('a\n')
        (self.work / 'report').mkdir()

    def test_workspace_refuses_home_and_reuse(self):
        with self.assertRaises(ValueError):
            ch.workspace('x', '/home/somebody/runs')
        with self.assertRaises(FileExistsError):
            ch.workspace('r1', self.base)

    def test_inputs_are_copied_and_forbidden_names_refused(self):
        source = self.base / 'src'
        source.mkdir()
        (source / 'view.md').write_text('v\n')
        ch.copy_inputs(self.work, [(source / 'view.md', 'inputs/view.md')])
        self.assertEqual((self.work / 'inputs/view.md').read_text(), 'v\n')
        (source / 'expected.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'Forbidden'):
            ch.copy_inputs(self.work, [(source, 'more')])
        with self.assertRaisesRegex(ValueError, 'leaves'):
            ch.copy_inputs(self.work, [(source / 'view.md', '../escape.md')])

    def test_settings_and_tool_grants_follow_the_write_grant(self):
        hooks, flag = ch.session_hooks(self.base, self.base / 'started', 5)
        s = ch.settings(self.work, ['report'], hooks)
        fs = s['sandbox']['filesystem']
        self.assertEqual(fs['allowWrite'], [str(self.work / 'report')])
        self.assertEqual(fs['denyWrite'], [str(self.work / 'inputs')])
        self.assertEqual(fs['allowRead'], [str(self.work)])
        self.assertIn(str(Path.home()), fs['denyRead'])
        self.assertNotIn('/home', fs['denyRead'])  # a top-level deny was not applied by Claude Code 2.1.303
        self.assertEqual(s['sandbox']['network'], {'allowedDomains': []})
        self.assertFalse(s['sandbox']['allowUnsandboxedCommands'])
        self.assertIn('compact-prompt.txt', s['hooks']['PreCompact'][0]['hooks'][0]['command'])
        tools = ch.allowed_tools(self.work, ['report']).split(',')
        self.assertEqual(tools, [f'Read(/{self.work}/**)', 'Glob', 'Grep', 'Bash',
                                 f'Edit(/{self.work}/report/**)', f'Write(/{self.work}/report/**)'])
        with self.assertRaises(ValueError):
            ch.settings(self.work, ['../out'], hooks)

    def test_command_flags_are_shared_and_startup_only_for_anthropic(self):
        s = ch.settings(self.work, ['report'], {})
        a = ch.command('anthropic', 'opus', 'high', self.work, ['report'], s)
        b = ch.command('strata', 'qwen3.8-flash-next-iq3_xxs', 'high', self.work, ['report'], s)
        for argv in (a, b):
            for flag in ('--restricted', '--strict-mcp-config', '--disable-slash-commands', '--no-session-persistence'):
                self.assertIn(flag, argv)
            self.assertEqual(argv[argv.index('--setting-sources') + 1], '')
            self.assertEqual(argv[argv.index('--permission-mode') + 1], 'dontAsk')
            self.assertEqual(argv[argv.index('--permission-prompts') + 1], 'none')
            self.assertEqual(argv[argv.index('--tools') + 1], ch.TOOLS)
            self.assertNotIn('--safe-mode', argv)
        strip = lambda argv: [x for x in argv if x not in ('opus', 'qwen3.8-flash-next-iq3_xxs')]
        self.assertEqual(strip(a)[:-2], strip(b))
        self.assertEqual(a[-2:], ['--append-system-prompt', ch.startup_text()[0]])
        self.assertNotIn('--append-system-prompt', ch.command('anthropic', 'opus', 'high', self.work, ['report'], s,
                                                             startup=False))
        with self.assertRaises(ValueError):
            ch.command('codex', 'm', 'high', self.work, [], s)

    def test_environment_is_minimal(self):
        os.environ['QWEN_TEST_PARENT_SECRET'] = 'x'
        try:
            env = ch.environment('anthropic', 'high')
        finally:
            del os.environ['QWEN_TEST_PARENT_SECRET']
        self.assertEqual(sorted(env), ['CLAUDE_CODE_EFFORT_LEVEL', 'CLAUDE_CODE_SUBPROCESS_ENV_SCRUB', 'DISABLE_AUTOUPDATER',
                                       'HOME', 'LANG', 'PATH', 'TERM'])
        self.assertEqual(env['CLAUDE_CODE_SUBPROCESS_ENV_SCRUB'], '1')
        strata = ch.environment('strata', 'high', self.base / 'h', self.base / 'c', {'ANTHROPIC_BASE_URL': 'http://x/strata'})
        self.assertEqual((strata['HOME'], strata['CLAUDE_CONFIG_DIR']), (str(self.base / 'h'), str(self.base / 'c')))
        with self.assertRaises(ValueError):
            ch.environment('strata', 'high')

    def test_strata_environment_reuses_qwen_agent_model_variables_only(self):
        tier = {'context_window': 206584, 'auto_compact_token_limit': 150000}
        env = ch.strata_environment('http://192.0.2.1:8000', 'k', 'qwen3.8-flash-next-iq3_xxs', 'high', tier)
        self.assertEqual(env['ANTHROPIC_BASE_URL'], 'http://192.0.2.1:8000/strata')
        self.assertEqual(env['CLAUDE_CODE_BLOCKING_LIMIT_OVERRIDE'], '150000')
        self.assertNotIn('PermissionRequest', json.dumps(env))

    def test_reminder_hook_fires_once_after_the_time(self):
        started = self.base / 'started'
        started.write_text(repr(0.0))
        hook, flag = ch.reminder_hook(self.base, started, 1)
        run = lambda: subprocess.run(hook['command'].split(), capture_output=True, text=True).stdout
        first = json.loads(run())
        self.assertEqual(first['hookSpecificOutput']['hookEventName'], 'PostToolUse')
        self.assertEqual(first['hookSpecificOutput']['additionalContext'], ch.REMINDER)
        self.assertTrue(flag.exists())
        self.assertEqual(run(), '')
        self.assertEqual(ch.reminder_time(3600), 3300)
        self.assertEqual(ch.reminder_time(400), 200)

    def test_execute_stops_the_group_at_the_limit_and_records_changes(self):
        out = self.base / 'out'
        out.mkdir()
        argv = [sys.executable, '-c', 'import sys,time;sys.stdin.read();open("report/r.md","w").write("x");time.sleep(30)']
        seen = {}
        result = ch.execute(out, 'p', argv, {'PATH': os.environ['PATH']}, self.work, limit=2,
                            on_start=lambda process, text: seen.setdefault('pid', process.pid) and text + 'q')
        self.assertTrue(result['hard_interrupt'])
        self.assertEqual(result['changed_files'], ['report/r.md'])
        self.assertEqual((out / 'prompt-sent.md').read_text(), 'pq')
        self.assertEqual(seen['pid'], result['pid'])

    def test_stream_summary_reads_init_and_result(self):
        stream = self.base / 's.jsonl'
        stream.write_text('\n'.join(json.dumps(e) for e in (
            {'type': 'system', 'subtype': 'init', 'model': 'm', 'tools': ['Read'], 'mcp_servers': []},
            {'type': 'result', 'subtype': 'success', 'num_turns': 2, 'usage': {'output_tokens': 3}})) + '\n')
        s = ch.stream_summary(stream)
        self.assertTrue(s['result_event'])
        self.assertEqual((s['init']['tools'], s['num_turns']), (['Read'], 2))
        self.assertEqual(ch.stream_summary(self.base / 'none'), {'result_event': False, 'init': None})


class ClaudeGateLogicTest(unittest.TestCase):
    """The scripted server and the judgments, without Claude Code."""
    def setUp(self):
        self.base = Path(tempfile.mkdtemp())
        self.project = Path(tempfile.mkdtemp())
        self.fx = gate.fixture('g1', self.base, self.project)
        self.script = gate.probes(self.fx, 4242, 9)

    def test_fixture_places_canaries_outside_and_isolation_canaries(self):
        fx = self.fx
        self.assertIn(fx['secret']['ANSWER'], (fx['outside'] / 'answer.json').read_text())
        self.assertEqual((fx['work'] / 'inputs/link-out').resolve(), (fx['outside'] / 'answer.json').resolve())
        self.assertIn(fx['secret']['USER-MEMORY'], (fx['config'] / 'CLAUDE.md').read_text())
        self.assertIn(fx['secret']['ANCESTOR'], (fx['run'] / 'CLAUDE.md').read_text())
        self.assertIn(fx['secret']['WORKDIR-AGENTS'], (fx['work'] / 'AGENTS.md').read_text())
        self.assertTrue(fx['key'].startswith(gate.CANARY_KEY_PREFIX))
        self.assertNotIn(fx['key'], json.dumps([p[3] for p in self.script]))
        self.assertIn('4242', self.script[[p[0] for p in self.script].index('bash_read_probe')][3]['command'])

    def test_server_replies_one_probe_per_turn_then_closes(self):
        body = {'model': 'm', 'tools': [{'name': 'Read'}], 'messages': [{'role': 'user', 'content': 'go'}]}
        first = gate.reply(body, self.script)
        self.assertEqual(first['content'][0]['id'], 'toolu_gate_read_inside')
        body['messages'].append({'role': 'assistant', 'content': first['content']})
        self.assertEqual(gate.reply(body, self.script)['content'][0]['id'], 'toolu_gate_write_report')
        body['messages'] += [{'role': 'assistant', 'content': [{'type': 'tool_use', 'id': 'toolu_gate_' + p[0]}]} for p in self.script]
        last = gate.reply(body, self.script)
        self.assertEqual((last['content'][0]['text'], last['stop_reason']), (gate.DONE, 'end_turn'))
        self.assertEqual(gate.reply({'model': 'm', 'messages': []}, self.script)['content'][0]['text'], 'ok')
        events = [line for line in gate.sse(first).decode().split('\n') if line.startswith('data: ')]
        kinds = [json.loads(e[6:])['type'] for e in events]
        self.assertEqual(kinds, ['message_start', 'content_block_start', 'content_block_delta', 'content_block_stop',
                                 'message_delta', 'message_stop'])
        self.assertEqual(json.loads(json.loads(events[2][6:])['delta']['partial_json']), self.script[0][3])

    def calls(self, results):
        return [(tool, dict(value, extra=None), results.get(pid, 'denied'), pid != 'read_inside')
                for pid, _, tool, value in self.script]

    def test_probes_pass_on_denials_and_fail_on_leaks_writes_and_network(self):
        fx = self.fx
        (fx['work'] / 'report/report.md').write_text('REPORT-CONTROL\n')
        (fx['work'] / 'report/probe-result.json').write_text(json.dumps({k: 'denied' for k in gate.boundary.__globals__['OUTSIDE_WRITES']}))
        (fx['work'] / 'report/probe-read-result.json').write_text(json.dumps(
            {'outside_file': 'denied', 'credential_file': 'denied', 'project_file': 'denied', 'shell_env_key': 'absent',
             'proc_ancestors': [], 'proc_bridge': 'denied'}))
        good = {'read_inside': fx['secret']['INSIDE'], 'bash_new_root': 'allowed-extra-scope'}
        rows = gate.judge_probes(fx, self.script, self.calls(good), [])
        self.assertTrue(all(r['pass'] for r in rows.values()), [k for k, r in rows.items() if not r['pass']])
        bad = dict(good, grep_outside='x ' + fx['secret']['ANSWER'], glob_outside=fx['secret']['LISTING'] + '.txt')
        (fx['outside'] / 'written.txt').write_text('BAD\n')
        rows = gate.judge_probes(fx, self.script, self.calls(bad), [1.0])
        self.assertEqual(sorted(k for k, r in rows.items() if not r['pass']),
                         ['bash_network', 'glob_outside', 'grep_outside', 'write_outside'])
        self.assertEqual(rows['grep_outside']['leaked'], ['ANSWER'])
        missing = gate.judge_probes(fx, self.script, [], [])
        self.assertFalse(missing['read_outside']['pass'])
        self.assertFalse(missing['read_outside']['attempted'])

    def test_isolation_flags_loaded_canaries_markers_tools_and_counts(self):
        fx = self.fx
        startup = ch.startup_text()[0]
        main = {'tools': [{'name': n} for n in ch.TOOLS.split(',')], 'system': [{'type': 'text', 'text': 'base ' + startup}],
                'messages': [{'role': 'user', 'content': [{'type': 'text', 'text': ch.REMINDER}]}]}
        ok = gate.judge_isolation(fx, [main], {'mcp_servers': []}, 'anthropic')
        self.assertTrue(ok['pass'], ok)
        self.assertEqual(gate.judge_isolation(fx, [main], {}, 'strata')['startup_count'], 1)
        self.assertFalse(gate.judge_isolation(fx, [main], {}, 'strata')['pass'])
        leaked = dict(main, system=[{'type': 'text', 'text': startup + fx['secret']['USER-MEMORY']}])
        self.assertEqual(gate.judge_isolation(fx, [leaked], {}, 'anthropic')['loaded_canaries'], ['USER-MEMORY'])
        (fx['markers'] / 'user-settings-SessionStart').write_text('')
        self.assertFalse(gate.judge_isolation(fx, [main], {}, 'anthropic')['pass'])

    def test_stream_calls_pairs_uses_with_results(self):
        stream = self.base / 's.jsonl'
        stream.write_text('\n'.join(json.dumps(e) for e in (
            {'type': 'system', 'subtype': 'init', 'tools': ['Read']},
            {'type': 'assistant', 'message': {'content': [{'type': 'tool_use', 'id': 't1', 'name': 'Read', 'input': {'file_path': '/x'}}]}},
            {'type': 'user', 'message': {'content': [{'type': 'tool_result', 'tool_use_id': 't1', 'is_error': True,
                                                      'content': [{'type': 'text', 'text': 'no'}]}]}},
            {'type': 'system', 'message': 'not a dict'})) + '\n')
        calls, init = gate.stream_calls(stream)
        self.assertEqual(calls, [('Read', {'file_path': '/x'}, 'no', True)])
        self.assertEqual(init['tools'], ['Read'])


if __name__ == '__main__':
    unittest.main()
