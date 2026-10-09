import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.metrics.prompt_policy import compaction_config, NATIVE_COMPACT_VERSION


class PromptPolicyTests(unittest.TestCase):
    def test_explicit_diagnostic_keeps_native_compaction_without_project_appendix(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'config/prompts').mkdir(parents=True)
            base=root/'config/prompts/compact-prompt.txt';base.write_text('Project custom instructions')
            native=root/'tools/resources/codex'/NATIVE_COMPACT_VERSION;native.mkdir(parents=True)
            (native/'compact-prompt.txt').write_text('Native default')
            result=compaction_config({},root/'out',root,include_project_base=False)
            self.assertEqual(Path(result['experimental_compact_prompt_file']).read_text(),'Native default\n')
            self.assertEqual(base.read_text(),'Project custom instructions')
            self.assertEqual(json.loads((root/'out/compact-prompt-policy.json').read_text())['policy'],'native-only-diagnostic')

    def test_preserves_file_and_inline_supplements_and_input_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'config/prompts').mkdir(parents=True)
            (root/'config/prompts/compact-prompt.txt').write_text('基础摘要指令\n')
            supplement=root/'scene.txt';supplement.write_text('场景补充')
            original={'compact_prompt':'额外约束','experimental_compact_prompt_file':str(supplement),'other':123}
            result=compaction_config(original,root/'out',root)
            text=Path(result['experimental_compact_prompt_file']).read_text()
            self.assertEqual(text,'基础摘要指令\n\n场景补充\n\n额外约束\n')
            self.assertEqual(original['compact_prompt'],'额外约束')
            self.assertNotIn('compact_prompt',result)
            self.assertEqual(result['other'],123)
            receipt=json.loads((root/'out/compact-prompt-policy.json').read_text())
            self.assertEqual(len(receipt['sources']),3)
            self.assertEqual(len(receipt['rendered_sha256']),64)

    def test_missing_or_empty_base_fails_before_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'config/prompts').mkdir(parents=True)
            with self.assertRaises(FileNotFoundError):compaction_config({},root/'out',root)
            (root/'config/prompts/compact-prompt.txt').write_text(' \n')
            with self.assertRaises(ValueError):compaction_config({},root/'out',root)
            self.assertFalse((root/'out').exists())

    def test_native_default_is_retained_and_identical_base_is_not_duplicated(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'config/prompts').mkdir(parents=True)
            base=root/'config/prompts/compact-prompt.txt';base.write_text('base')
            native=root/'tools/resources/codex'/NATIVE_COMPACT_VERSION
            native.mkdir(parents=True)
            (native/'compact-prompt.txt').write_text('native default')
            result=compaction_config({},root/'out',root)
            self.assertEqual(Path(result['experimental_compact_prompt_file']).read_text(),'base\n\nnative default\n')
            result=compaction_config({'experimental_compact_prompt_file':str(base)},root/'out2',root)
            self.assertEqual(Path(result['experimental_compact_prompt_file']).read_text(),'base\n')


if __name__=='__main__':unittest.main()
