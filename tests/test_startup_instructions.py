import copy
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from startup_instructions import load_startup_instructions, install_startup_instructions


class StartupInstructionsTests(unittest.TestCase):
    def test_loop_only_diagnostic_preserves_completion_checks_and_caller_rules(self):
        project=Path(__file__).resolve().parents[1]
        raw=(project/'config/prompts/startup-instructions.txt').read_bytes()
        normal,normal_meta=load_startup_instructions(project)
        partial,meta=load_startup_instructions(project,include_loop_prevention=False)
        self.assertNotIn('Progress and loop prevention:',partial)
        self.assertNotIn('If several consecutive steps repeat',partial)
        self.assertEqual(partial,normal[normal.index('Complete the assigned task:'):])
        self.assertIn('Do not end an assigned task',partial)
        self.assertIn('Completion check before ending:',partial)
        self.assertIn('Obey explicit stop instructions and time limits.',partial)
        self.assertTrue(meta['enabled'])
        self.assertFalse(meta['loop_prevention_enabled'])
        self.assertEqual(meta['source_sha256'],normal_meta['sha256'])
        self.assertEqual((project/'config/prompts/startup-instructions.txt').read_bytes(),raw)
        class Service:
            def prepare(self,messages): return messages
        install_startup_instructions(Service,partial)
        result=Service().prepare([{'role':'system','content':'Original role and task rules.'}])
        self.assertTrue(result[0]['content'].startswith('Original role and task rules.\n\n'))
        self.assertIn('Completion check before ending:',result[0]['content'])

    def test_loop_only_diagnostic_rejects_ambiguous_blocks_and_non_boolean_selection(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'config/prompts').mkdir(parents=True)
            p=root/'config/prompts/startup-instructions.txt';p.write_text('Unrecognized prompt layout.\n')
            with self.assertRaises(ValueError):load_startup_instructions(root,include_loop_prevention=False)
            for invalid in (0,1,None,'false'):
                with self.assertRaises(ValueError):load_startup_instructions(root,include_loop_prevention=invalid)

    def test_explicit_diagnostic_can_omit_project_prompt_without_deleting_it(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'config/prompts').mkdir(parents=True)
            p=root/'config/prompts/startup-instructions.txt';p.write_text('Original added instructions.\n')
            before=p.read_bytes()
            text,metadata=load_startup_instructions(root,False)
            self.assertIsNone(text)
            self.assertFalse(metadata['enabled'])
            self.assertEqual(p.read_bytes(),before)
            self.assertEqual(load_startup_instructions(root)[0],'Original added instructions.')
            for invalid in (0,1,None,'false'):
                with self.assertRaises(ValueError):load_startup_instructions(root,invalid)

    def test_process_snapshot_preserves_caller_and_tool_history_across_requests(self):
        class Service:
            def prepare(self, messages, tools, kwargs, max_new=None):
                return messages, tools, kwargs, max_new

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'config/prompts').mkdir(parents=True)
            path = root / 'config/prompts/startup-instructions.txt'
            path.write_text('Inspect actual results.\n')
            text, first = load_startup_instructions(root)
            install_startup_instructions(Service, text)
            service = Service()
            history = [{'role': 'system', 'content': 'Caller instructions.'},
                       {'role': 'assistant', 'tool_calls': [{'id': 'one'}]},
                       {'role': 'tool', 'tool_call_id': 'one', 'content': 'error'}]
            before = copy.deepcopy(history)
            path.write_text('Changed for the next process.\n')
            for _ in range(2):
                messages, tools, kwargs, budget = service.prepare(history, ['tool'], {'enable_thinking': True}, 100)
                self.assertEqual(messages[0]['content'], 'Caller instructions.\n\nInspect actual results.')
                self.assertEqual(messages[1:], history[1:])
                self.assertEqual((tools, kwargs, budget), (['tool'], {'enable_thinking': True}, 100))
            self.assertEqual(history, before)
            self.assertNotEqual(first['sha256'], load_startup_instructions(root)[1]['sha256'])

    def test_chat_without_system_and_content_blocks_receive_instructions(self):
        class Service:
            def prepare(self, messages, **kwargs):
                return messages

        install_startup_instructions(Service, 'Check progress.')
        service = Service()
        caller = [{'role': 'user', 'content': 'Task'}]
        self.assertEqual(service.prepare(caller)[0], {'role': 'system', 'content': 'Check progress.'})
        blocks = [{'role': 'system', 'content': [{'type': 'text', 'text': 'Caller'}]}]
        original = copy.deepcopy(blocks)
        self.assertEqual(service.prepare(blocks)[0]['content'],
                         [{'type': 'text', 'text': 'Caller'}, {'type': 'text', 'text': 'Check progress.'}])
        self.assertEqual(blocks, original)


if __name__ == '__main__':
    unittest.main()
