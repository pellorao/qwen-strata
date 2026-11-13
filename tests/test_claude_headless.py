import hashlib
import json
import os
import sys
import shutil
import tempfile
import unittest
from pathlib import Path

from tools.reviewer import claude_headless as ch
from tools.safety import claude_gate as gate


class RunnerBuildersTest(unittest.TestCase):
    """Zero-model checks of the Claude Code runner's command, settings, environment and inputs."""
    def setUp(self):
        self.base = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.base, True)
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
        hooks = ch.session_hooks()
        s = ch.settings(self.work, ['report'], hooks)
        fs = s['sandbox']['filesystem']
        tmp = self.work.resolve().parent / 'tmp'
        self.assertEqual(fs['allowWrite'], [str(self.work / 'report'), str(tmp)])
        self.assertEqual(fs['denyWrite'], [str(self.work / 'inputs'), *ch.SHARED_DENY])
        for place in ch.WORLD_WRITABLE:  # denied as a whole for reads: the sandbox mounts a private empty directory
            self.assertIn(place, fs['denyRead'])
        self.assertEqual(fs['allowRead'], [str(self.work), str(tmp)])
        self.assertEqual((tmp.stat().st_mode & 0o777, ch.SHARED_DENY), (0o700, ['/tmp', f'/tmp/claude-{os.getuid()}']))
        self.assertIn(str(Path.home()), fs['denyRead'])
        for shared in ch.SHARED_DENY:  # the shared temporary directory is neither readable nor writable
            self.assertIn(shared, fs['denyRead'])
        tmp.chmod(0o755)
        with self.assertRaisesRegex(ValueError, '0700'):  # a widened or foreign directory is never reused
            ch.run_tmp(self.work)
        tmp.chmod(0o700)
        with self.assertRaisesRegex(ValueError, 'over'):
            ch.settings_argument({'x': 'y' * ch.SETTINGS_ARGUMENT_LIMIT})
        self.assertNotIn('/home', fs['denyRead'])  # a top-level deny was not applied by Claude Code 2.1.303
        self.assertEqual(s['sandbox']['network'], {'allowedDomains': []})
        self.assertFalse(s['sandbox']['allowUnsandboxedCommands'])
        self.assertIn('compact-prompt.txt', s['hooks']['PreCompact'][0]['hooks'][0]['command'])
        tools = ch.allowed_tools(self.work, ['report']).split(',')
        self.assertEqual(tools, [f'Read(/{self.work}/**)', 'Glob', 'Grep', 'Bash',
                                 f'Edit(/{self.work}/report/**)', f'Write(/{self.work}/report/**)'])
        with self.assertRaises(ValueError):
            ch.settings(self.work, ['../out'], hooks)

    def test_nested_grant_denies_siblings_along_its_ancestors(self):
        (self.work / '.tmp/cap/reports').mkdir(parents=True)
        (self.work / '.tmp/cap/request.json').write_text('{}')
        (self.work / '.tmp/other').mkdir()
        fs = ch.settings(self.work, ['.tmp/cap/reports'], {})['sandbox']['filesystem']
        w = self.work.resolve()
        self.assertEqual(fs['denyWrite'], [str(w / '.tmp/cap/request.json'), str(w / '.tmp/other'),
                                           str(w / 'inputs'), str(w / 'report'), *ch.SHARED_DENY])

    def test_git_directory_stays_creatable_its_entries_denied(self):
        (self.work / '.git/info').mkdir(parents=True)
        (self.work / '.git/config').write_text('')
        fs = ch.settings(self.work, ['report'], {})['sandbox']['filesystem']
        w = self.work.resolve()
        self.assertIn(str(w / '.git/config'), fs['denyWrite'])
        self.assertIn(str(w / '.git/info'), fs['denyWrite'])
        self.assertNotIn(str(w / '.git'), fs['denyWrite'])  # the sandbox stubs .git/config.lock inside it

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
            self.assertEqual(argv[argv.index('--disallowedTools') + 1], 'WebSearch,WebFetch')
            self.assertNotIn('WebSearch', ch.TOOLS)
            self.assertNotIn('--safe-mode', argv)
        strip = lambda argv: [x for x in argv if x not in ('opus', 'qwen3.8-flash-next-iq3_xxs')]
        self.assertEqual(strip(a)[:-2], strip(b))
        self.assertEqual(a[-2:], ['--append-system-prompt', ch.startup_text()[0]])
        self.assertNotIn('--append-system-prompt', ch.command('anthropic', 'opus', 'high', self.work, ['report'], s,
                                                             startup=False))
        with self.assertRaises(ValueError):
            ch.command('codex', 'm', 'high', self.work, [], s)
        d = ch.command('deepseek', 'deepseek-flash', 'high', self.work, ['report'], s, startup=False)
        self.assertEqual([x for x in d if x != 'deepseek-flash'], strip(b))
        for bad in ('claude-opus-4-1', 'opus', 'deepseek-sonnet', 'gpt-6-luna', ''):
            with self.assertRaises(ValueError):
                ch.command('deepseek', bad, 'high', self.work, ['report'], s)

    def test_system_prompt_joins_the_one_append_flag(self):
        s = ch.settings(self.work, ['report'], {})
        only = ch.command('anthropic', 'opus', 'high', self.work, ['report'], s, startup=False, system_prompt='ROLE\n')
        self.assertEqual(only[-2:], ['--append-system-prompt', 'ROLE'])
        both = ch.command('anthropic', 'opus', 'high', self.work, ['report'], s, system_prompt='ROLE')
        self.assertEqual(both.count('--append-system-prompt'), 1)
        self.assertEqual(both[-1], ch.startup_text()[0] + '\n\nROLE')
        strata = ch.command('strata', 'qwen3.8-flash-next-iq3_xxs', 'high', self.work, ['report'], s, system_prompt='ROLE')
        self.assertEqual(strata[-2:], ['--append-system-prompt', 'ROLE'])

    def test_compact_prompt_hook_is_optional(self):
        hooks = ch.session_hooks()
        self.assertIn('PreCompact', hooks)
        hooks = ch.session_hooks(compact=False)
        self.assertEqual(hooks, {})
        with self.assertRaises(ValueError):
            ch.run(self.base / 'r', self.base / 'p.md', 'strata', 'qwen3.8-flash-next-iq3_xxs', 'high', 'x', compact=False,
                   base=self.base / 'w', record=False)

    def test_cli_runs_only_the_pinned_binary_and_records_its_hash(self):
        fake = self.base / 'claude'
        fake.write_text('#!/bin/sh\necho "9.9.9 (Claude Code)"\n')
        fake.chmod(0o755)
        digest = hashlib.sha256(fake.read_bytes()).hexdigest()
        found = ch.pinned_binary(str(fake), '9.9.9', digest)
        self.assertEqual((found['path'], found['version'], found['sha256']),
                         (str(fake.resolve()), '9.9.9 (Claude Code)', digest))
        for expected, sha in (('9.9.8', digest), ('9.9.9', '0' * 64)):  # another version, or the same one rebuilt
            with self.assertRaises(SystemExit):
                ch.pinned_binary(str(fake), expected, sha)
        self.assertIn(f'/.local/share/qwen-bench/claude-code-{ch.CLAUDE_VERSION}/', ch.CLAUDE)

    def test_deepseek_environment_names_the_model_everywhere(self):
        env = ch.environment('deepseek', 'medium', self.base / 'h', self.base / 'c',
                             ch.deepseek_environment('deepseek-flash', 'synthetic'), tmp=ch.run_tmp(self.work))
        self.assertEqual((env['ANTHROPIC_BASE_URL'], env['ANTHROPIC_AUTH_TOKEN']), (ch.DEEPSEEK_BASE, 'synthetic'))
        self.assertEqual({env[n] for n in ch.DEEPSEEK_MODEL_VARIABLES}, {'deepseek-flash'})
        self.assertEqual((env['CLAUDE_CODE_EFFORT_LEVEL'], env['CLAUDE_CODE_SUBPROCESS_ENV_SCRUB']), ('medium', '1'))
        self.assertNotIn('ANTHROPIC_API_KEY', env)
        with self.assertRaises(ValueError):
            ch.deepseek_environment('deepseek-flash', None)
        self.assertFalse(set(ch.DEEPSEEK_LIMIT_VARIABLES) & set(env))
        # Plan-fixed limits (multi-model v2 §5.2) become the Claude Code variables; anything else is refused.
        limited = ch.deepseek_environment('deepseek-flash', 'synthetic', limits={'CLAUDE_CODE_MAX_CONTEXT_TOKENS': 1048576})
        self.assertEqual(limited['CLAUDE_CODE_MAX_CONTEXT_TOKENS'], '1048576')
        for bad in ({'CLAUDE_CODE_MAX_CONTEXT_TOKENS': None}, {'CLAUDE_CODE_MAX_CONTEXT_TOKENS': '1048576'},
                    {'ANTHROPIC_BASE_URL': 1}, {'CLAUDE_CODE_MAX_OUTPUT_TOKENS': 0}):
            with self.assertRaises(ValueError):
                ch.deepseek_environment('deepseek-flash', 'synthetic', limits=bad)
        with self.assertRaises(ValueError):
            ch.environment('deepseek', 'high', tmp=ch.run_tmp(self.work))

    def test_environment_is_minimal(self):
        os.environ['QWEN_TEST_PARENT_SECRET'] = 'x'
        try:
            tmp = ch.run_tmp(self.work)
            env = ch.environment('anthropic', 'high', self.base / 'h', tmp=tmp)
        finally:
            del os.environ['QWEN_TEST_PARENT_SECRET']
        self.assertEqual(sorted(env), ['CLAUDE_CODE_EFFORT_LEVEL', 'CLAUDE_CODE_SUBPROCESS_ENV_SCRUB', 'CLAUDE_CODE_TMPDIR',
                                       'DISABLE_AUTOUPDATER', 'ENABLE_TOOL_SEARCH', 'HOME', 'LANG', 'PATH', 'TERM',
                                       'TMPDIR'])
        self.assertEqual(env['CLAUDE_CODE_SUBPROCESS_ENV_SCRUB'], '1')
        self.assertEqual(env['ENABLE_TOOL_SEARCH'], 'false')  # no DeferredToolPlaceholder (2.1.309)
        self.assertEqual((env['TMPDIR'], env['CLAUDE_CODE_TMPDIR']), (str(tmp), str(tmp)))
        for shared in (None, '/tmp', f'/tmp/claude-{os.getuid()}', f'/tmp/claude-{os.getuid()}/x'):
            with self.assertRaisesRegex(ValueError, 'TMPDIR'):  # no run falls back to the shared temporary directory
                ch.environment('anthropic', 'high', self.base / 'h', tmp=shared)
        with self.assertRaises(ValueError):
            ch.environment('anthropic', 'high', tmp=tmp)
        with self.assertRaises(ValueError):
            ch.environment('anthropic', 'high', Path.home(), tmp=tmp)
        real = self.base / 'real'
        (real / '.claude').mkdir(parents=True)
        (self.base / 'run').mkdir()
        home = ch.anthropic_home(self.base / 'run', real)
        self.assertEqual(sorted(p.name for p in home.iterdir()), ['.claude'])
        self.assertEqual((home / '.claude').resolve(), (real / '.claude').resolve())
        strata = ch.environment('strata', 'high', self.base / 'h', self.base / 'c', {'ANTHROPIC_BASE_URL': 'http://x/strata'},
                                tmp=tmp)
        self.assertEqual((strata['HOME'], strata['CLAUDE_CONFIG_DIR']), (str(self.base / 'h'), str(self.base / 'c')))
        with self.assertRaises(ValueError):
            ch.environment('strata', 'high', tmp=tmp)

    def test_strata_environment_reuses_qwen_agent_model_variables_only(self):
        tier = {'context_window': 206584, 'auto_compact_token_limit': 150000}
        env = ch.strata_environment('http://192.0.2.1:8000', 'k', 'qwen3.8-flash-next-iq3_xxs', 'high', tier)
        self.assertEqual(env['ANTHROPIC_BASE_URL'], 'http://192.0.2.1:8000/strata')
        self.assertEqual(env['CLAUDE_CODE_BLOCKING_LIMIT_OVERRIDE'], '150000')
        self.assertNotIn('PermissionRequest', json.dumps(env))

    def test_reminder_time_follows_arw_lead(self):
        self.assertEqual(ch.reminder_time(3600), 3300)
        self.assertEqual(ch.reminder_time(400), 200)
        self.assertNotIn('PostToolUse', json.dumps(ch.session_hooks()))  # the reminder is a priority message now

    def test_execute_stops_the_group_at_the_limit_and_records_changes(self):
        out = self.base / 'out'
        out.mkdir()
        # a process that ignores the hard-limit interrupt: stdin closes, the group is stopped after the grace
        argv = [sys.executable, '-c', 'import sys,time;sys.stdin.read();open("report/r.md","w").write("x");time.sleep(30)']
        seen = {}
        grace, ch.HARD_GRACE = ch.HARD_GRACE, 1
        try:
            result = ch.execute(out, 'p', argv, {'PATH': os.environ['PATH']}, self.work, limit=2,
                                on_start=lambda process, text: seen.setdefault('pid', process.pid) and text + 'q')
        finally:
            ch.HARD_GRACE = grace
        self.assertTrue(result['hard_interrupt'])
        self.assertLess(result['wall_seconds'], 10)
        self.assertEqual(result['changed_files'], ['report/r.md'])
        self.assertEqual((out / 'prompt-sent.md').read_text(), 'pq')
        self.assertEqual(seen['pid'], result['pid'])
        stop = json.loads((out / 'deadline-handoff.json').read_text())['interrupt']
        self.assertEqual((stop['status'], stop.get('group_stopped')), ('unknown', True))  # never answered

    def test_turns_are_sent_one_after_another_and_analysed(self):
        out = self.base / 'turns'
        out.mkdir()
        # a fake `claude -p` stream: replay each message, compact before the third turn, reply, then a result
        fake = (
            'import json,sys\n'
            'n=0\n'
            'for line in sys.stdin:\n'
            '    m=json.loads(line); n+=1; text=m["message"]["content"]\n'
            '    if n==3: print(json.dumps({"type":"system","subtype":"compact_boundary"}),flush=True)\n'
            '    print(json.dumps({"type":"user","isReplay":True,"uuid":m["uuid"],"message":m["message"]}),flush=True)\n'
            '    print(json.dumps({"type":"assistant","message":{"content":[{"type":"text","text":"R:"+text}]}}),flush=True)\n'
            '    print(json.dumps({"type":"result","subtype":"success","usage":{"input_tokens":n*10,'
            '"cache_read_input_tokens":5}}),flush=True)\n')
        argv = [sys.executable, '-c', fake]
        messages = ['Batch 01/03. x', 'Batch 02/03. y', 'Checkpoint 1 of 1. q']
        result = ch.run_turns(out, messages, argv, {'PATH': os.environ['PATH']}, self.work, ch.Deadline(out, 60))
        self.assertEqual((result['exit'], result['hard_interrupt'], len(result['turns'])), (0, False, 3))
        self.assertTrue(all(t['ended_at'] for t in result['turns']))
        from tools.tuning.codex_workload import turn_label
        analysis = ch.conversation_analysis(out / 'stream.jsonl', turn_label,
                                            lambda label, texts: [t[:5] for t in texts if label == 'questions 1'])
        self.assertEqual([r['turn'] for r in analysis['replies']], ['batch 01', 'batch 02', 'questions 1'])
        self.assertEqual(analysis['replies'][2]['text'], 'R:Checkpoint 1 of 1. q')
        self.assertEqual(analysis['replies'][2]['context_tokens'], 35)
        self.assertEqual(analysis['compactions'][0]['after_user_turn'], 'batch 02')
        self.assertEqual(analysis['replies'][2]['raw'], ['questions 1'])
        self.assertEqual(analysis['replies'][2]['in_text_ids'], ['Check'])  # only the turn kept after compaction
        self.assertEqual(analysis['replies'][2]['compactions_after'], ['batch 02'])
        self.assertEqual(analysis['tool_calls'], 0)

    def test_command_reads_stream_json_input_and_replays_it(self):
        argv = ch.command('anthropic', 'opus', 'high', self.work, ['report'], {'s': 1})
        i = argv.index('--input-format')
        self.assertEqual(argv[i:i + 3], ['--input-format', 'stream-json', '--replay-user-messages'])
        message = ch.user_message('hello', 'now')
        self.assertEqual((message['message'], message['priority'], 'origin' in message),
                         ({'role': 'user', 'content': 'hello'}, 'now', False))

    def test_stream_summary_reads_init_and_result(self):
        stream = self.base / 's.jsonl'
        stream.write_text('\n'.join(json.dumps(e) for e in (
            {'type': 'system', 'subtype': 'init', 'model': 'm', 'tools': ['Read'], 'mcp_servers': []},
            {'type': 'assistant', 'message': {'id': 'm1', 'usage': {'service_tier': 'standard'}}},
            {'type': 'assistant', 'message': {'id': 'm1', 'usage': {'service_tier': 'standard'}}},
            {'type': 'assistant', 'message': {'id': 'm2', 'usage': {'output_tokens': 1}}},
            {'type': 'result', 'subtype': 'success', 'num_turns': 2,
             'usage': {'output_tokens': 3, 'server_tool_use': {'web_search_requests': 1}}})) + '\n')
        s = ch.stream_summary(stream)
        self.assertTrue(s['result_event'])
        self.assertEqual((s['init']['tools'], s['num_turns']), (['Read'], 2))
        self.assertEqual((s['service_tiers'], s['server_web_requests']), ({'standard': 1, 'not-returned': 1}, 1))
        self.assertEqual(ch.stream_summary(self.base / 'none'),
                         {'result_event': False, 'init': None, 'service_tiers': {}, 'sandbox_failures': 0,
                          'segments': 1, 'segments_without_result': 1})
        self.assertEqual(s['sandbox_failures'], 0)

    def test_stream_summary_sums_every_result_of_one_stream(self):
        # bench-strata-1019 ca-r2 strata-medium-a2/h0 (2026-10-20): one stream with several results; the summary
        # read only the last one (5.2 s, 1 turn of 1097.6 s, 58 turns). Per-result fields add up, cost runs on.
        stream = self.base / 'multi.jsonl'
        stream.write_text('\n'.join(json.dumps(e) for e in (
            {'type': 'result', 'subtype': 'success', 'num_turns': 57, 'duration_ms': 1092400, 'duration_api_ms': 900,
             'total_cost_usd': 3.0, 'usage': {'output_tokens': 85167, 'input_tokens': 53346}},
            {'type': 'result', 'subtype': 'success', 'num_turns': 1, 'duration_ms': 5200, 'duration_api_ms': 100,
             'total_cost_usd': 3.5645, 'usage': {'output_tokens': 335, 'input_tokens': 401}})) + '\n')
        s = ch.stream_summary(stream)
        self.assertEqual((s['result_events'], s['num_turns'], s['duration_ms'], s['duration_api_ms']), (2, 58, 1097600, 1000))
        self.assertEqual((s['usage']['output_tokens'], s['usage']['input_tokens']), (85502, 53747))
        self.assertEqual((s['total_cost_usd'], s['usage_bound']), (3.5645, 'complete'))

    def test_stream_summary_api_time_runs_on_across_resume(self):
        # bench-anthropic-1019 cs-r1 haiku-low-a7/h0 (2.1.303): each resumed segment's duration_api_ms is the session
        # total so far, so the last one is the API time; a series that falls back is per result and summed.
        streams = []
        for i, (api, wall) in enumerate(((54060, 56375), (91527, 39471), (185543, 97557))):
            streams.append(self.base / f'seg-{i}.jsonl')
            streams[-1].write_text(json.dumps({'type': 'result', 'subtype': 'success', 'num_turns': 1, 'duration_ms': wall,
                                               'duration_api_ms': api, 'usage': {'output_tokens': 1}}) + '\n')
        s = ch.stream_summary(streams)
        self.assertEqual((s['duration_api_ms'], s['duration_ms']), (185543, 193403))

    def test_stream_summary_counts_sandbox_setup_failures(self):
        # 2026-10-20: every Bash call failed at sandbox setup (bwrap argument limit); a command's own error does not count.
        limit = ('Sandbox profile has 9672 bwrap arguments and bwrap accepts at most 9000 (about 3000 mounts); '
                 'reduce what the configuration expands to')
        results = [{'type': 'tool_result', 'tool_use_id': 'a', 'is_error': True, 'content': limit},
                   {'type': 'tool_result', 'tool_use_id': 'b', 'is_error': True,
                    'content': [{'type': 'text', 'text': 'bwrap: Can\'t mount proc on /newroot/proc'}]},
                   {'type': 'tool_result', 'tool_use_id': 'c', 'is_error': True, 'content': 'Exit code 1\ngrep: x: No such file'},
                   {'type': 'tool_result', 'tool_use_id': 'd', 'is_error': False, 'content': 'docs say bwrap accepts at most 9000'}]
        stream = self.base / 'sandbox.jsonl'
        stream.write_text('\n'.join(json.dumps({'type': 'user', 'message': {'role': 'user', 'content': [r]}}) for r in results)
                          + '\n' + json.dumps({'type': 'result', 'subtype': 'success'}) + '\n')
        self.assertEqual(ch.stream_summary(stream)['sandbox_failures'], 2)

    def test_shared_tmp_entries_refuse_over_limit(self):
        expected = sorted(str(p) for p in Path('/tmp').iterdir() if not p.is_socket() and str(p) not in ch.SHARED_DENY)
        self.assertEqual(ch.shared_tmp_entries(), expected)  # under the limit: the same list as before the check
        self.assertEqual(ch.SHARED_TMP_LIMIT, 1500)
        (self.base / 'probe').mkdir(exist_ok=True)
        original = ch.SHARED_TMP_LIMIT
        ch.SHARED_TMP_LIMIT = -1
        try:
            with self.assertRaisesRegex(RuntimeError, 'over -1'):
                ch.shared_tmp_entries()
        finally:
            ch.SHARED_TMP_LIMIT = original


class ClaudeGateLogicTest(unittest.TestCase):
    """The scripted server and the judgments, without Claude Code."""
    def setUp(self):
        self.base = Path(tempfile.mkdtemp())
        self.project = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.base, True)
        self.addCleanup(shutil.rmtree, self.project, True)
        self.fx = gate.fixture('g1', self.base, self.project)
        self.script = gate.probes(self.fx, 4242, 9)

    def tearDown(self):
        gate.release(self.fx)
        self.assertFalse(self.fx['shared_tmp'].exists() or self.fx['top_tmp'].exists() or self.fx['tmp_socket']['path'].exists())

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
        good = {'read_inside': fx['secret']['INSIDE'], 'bash_new_root': 'allowed-extra-scope',
                'tmpdir_own': f"TMPDIR={fx['tmp']}/claude-{os.getuid()}\n{fx['secret']['TMP']}\nOWN-WRITE-OK",
                'bash_large_command': f'LARGE-OK {gate.LARGE}'}
        rows = gate.judge_probes(fx, self.script, self.calls(good), [])
        self.assertTrue(all(r['pass'] for r in rows.values()), [k for k, r in rows.items() if not r['pass']])
        bad = dict(good, grep_outside='x ' + fx['secret']['ANSWER'], glob_outside=fx['secret']['LISTING'] + '.txt')
        (fx['outside'] / 'written.txt').write_text('BAD\n')
        rows = gate.judge_probes(fx, self.script, self.calls(bad), [1.0])
        self.assertEqual(sorted(k for k, r in rows.items() if not r['pass']),
                         ['bash_network', 'glob_outside', 'grep_outside', 'write_outside'])
        self.assertEqual(rows['grep_outside']['leaked'], ['ANSWER'])
        cross = dict(good, read_peer_tmp=fx['secret']['PEER'], read_shared_tmp=fx['secret']['SHARED'],
                     tmp_socket='CONNECTED', read_shared_places=fx['peer_tmp'].parent.name + '\nother')
        written = gate.shared_write_targets(fx)[-3]  # the peer run's working directory
        written.write_text('BAD\n')
        fx['tmp_socket']['hits'].append(1.0)  # judged by the listener's accepted connections, not by the text
        (fx['outside'] / 'written.txt').unlink()
        (fx['peer_tmp'] / 'written.txt').write_text('BAD\n')
        (fx['shared_tmp'] / 'written.txt').write_text('BAD\n')
        rows = gate.judge_probes(fx, self.script, self.calls(cross), [])
        self.assertEqual(sorted(k for k, r in rows.items() if not r['pass']),
                         ['read_peer_tmp', 'read_shared_places', 'read_shared_tmp', 'tmp_socket', 'write_peer_tmp',
                          'write_shared_places', 'write_shared_tmp'])
        self.assertEqual((rows['read_shared_places']['leaked'], rows['write_shared_places']['written']),
                         (['PEER_RUN'], [str(written)]))
        gate.remove_written(fx)
        self.assertFalse(written.exists())
        (fx['shared_tmp'] / 'written.txt').unlink()
        missing = gate.judge_probes(fx, self.script, [], [])
        self.assertFalse(missing['read_outside']['pass'])
        self.assertFalse(missing['read_outside']['attempted'])

    def test_failed_session_still_removes_its_canaries_and_writes(self):
        fx = self.fx
        written = gate.shared_write_targets(fx)[-3]  # the peer run's working directory

        def fails(*args, **kwargs):
            written.write_text('BAD\n')  # a write probe got through, then the session broke before judging
            raise RuntimeError('Claude Code broke')
        original = ch.execute
        ch.execute = fails
        try:
            with self.assertRaisesRegex(RuntimeError, 'broke'):
                gate.session(self.base / 'out', 'anthropic', 'haiku', 'high', 1, self.base, None, fx=fx)
        finally:
            ch.execute = original
        self.assertFalse(any(p.exists() for p in (fx['top_tmp'], fx['tmp_socket']['path'], *fx['place_canaries'])))
        self.assertFalse(written.exists())
        self.assertEqual(json.loads((self.base / 'out/unjudged-writes.json').read_text()), [str(written)])
        # a failure before Claude Code starts (here the scripted server) releases them as well
        other = gate.fixture('g2', self.base, Path(tempfile.mkdtemp(dir=self.project)))
        original = gate.serve
        gate.serve = lambda out=None: (_ for _ in ()).throw(OSError('no port'))
        try:
            with self.assertRaisesRegex(OSError, 'no port'):
                gate.session(self.base / 'out2', 'anthropic', 'haiku', 'high', 2, self.base, None, fx=other)
        finally:
            gate.serve = original
        self.assertFalse(any(p.exists() for p in (other['top_tmp'], other['tmp_socket']['path'], *other['place_canaries'])))
        self.assertFalse((self.base / 'out2/unjudged-writes.json').exists())

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
        self.assertEqual(gate.judge_isolation(fx, [main], {}, 'deepseek')['expected_startup_count'], 1)
        self.assertEqual(gate.judge_isolation(fx, [main], {}, 'deepseek', startup=False)['expected_startup_count'], 0)
        searching = dict(main, tools=main['tools'] + [{'type': 'web_search_20250305', 'name': 'web_search'}])
        self.assertEqual(gate.judge_isolation(fx, [searching], {}, 'anthropic')['web_tools'], ['web_search'])
        self.assertFalse(gate.judge_isolation(fx, [searching], {}, 'anthropic')['pass'])
        self.assertFalse(gate.judge_isolation(fx, [main], {'tools': ['Read', 'WebFetch']}, 'anthropic')['pass'])
        (fx['markers'] / 'user-settings-SessionStart').write_text('')
        self.assertFalse(gate.judge_isolation(fx, [main], {}, 'anthropic')['pass'])
        self.assertEqual([p[0] for p in gate.probes(fx, 1, 2, 'smoke')], list(gate.SMOKE))

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
