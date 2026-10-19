import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.reviewer.arw_measure import api_review_catalog, execute_review, review_settings, run, run_api
from tools.reviewer.providers import api_provider, validate_api_selection
from tools.reviewer.wsl_client import ROOT
sys.path.append(str(ROOT/'src'))
from startup_instructions import startup_prompt_bytes

OPENAI={'id':'openai','base_url':'https://api.openai.com/v1'}
API={'provider':OPENAI,'model':'gpt-6.1-sol','effort':'high'}
STRATA={'model':'IQ3_XXS','effort':'high','context_window':206584,'auto_compact_token_limit':150000}


class Fixture:
    def __init__(self,root):
        self.root=root;self.report=root/'reports/result.jsonl';self.report.parent.mkdir()
        self.runtime=root/'runtime.json';self.runtime.write_text('{}')
        (root/'bin').mkdir();(root/'bin/arw').write_text('#!/bin/sh\nexit 0\n')
        self.native={'role':'r','identity':{'kind':'isolated','instanceId':'native'},'instructions':'Exact Role.\n',
            'handoff':'Exact handoff.','cwd':str(root),'writePaths':[str(self.report)],'reportPath':str(self.report),
            'stateDirectory':str(root/'state')}
    def execute(self,selection,name):
        class Machine:
            def call(self,operation,bound):
                self.bound=bound;return {'runId':'run'}
        machine=Machine()
        handoff={'input':self.native,'instanceId':'native','reviewerId':'r','scenarioId':'s','scenarioRoot':str(self.root)}
        prep={'preparedPath':str(self.root/'p.json'),'identity':{'sessionId':'o'},'generations':[]}
        with patch.dict('os.environ',{'QWEN_ARW_RUNTIME_FILE':str(self.runtime),'QWEN_ARW_MODEL_BASE':'http://local/v1'}),\
                patch('tools.reviewer.arw_measure.observe_review',lambda m,r,f:r):
            record=execute_review(machine,self.root,prep,handoff,self.root/name,selection,self.root/'catalog.json')
        return machine.bound,record


class ApiProviderTests(unittest.TestCase):
    def test_strata_path_has_no_provider_and_defaults_unchanged(self):
        self.assertIsNone(api_provider(STRATA))
        with tempfile.TemporaryDirectory() as tmp:
            fixture=Fixture(Path(tmp));bound,record=fixture.execute(STRATA,'strata')
        settings=bound['settings']
        self.assertEqual((settings['modelProvider'],settings['serviceTier'],settings['model']),
                         ('qwen_strata','default','qwen3.8-flash-next-iq3_xxs'))
        self.assertNotIn('web_search',settings['config'])
        self.assertEqual(settings['config']['shell_environment_policy']['exclude'],['STRATA_API_KEY'])
        self.assertEqual(bound['instructions'],'Exact Role.\n')
        self.assertNotIn('provider',record);self.assertNotIn('startup_instructions',record)

    def test_switches_apply_on_both_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'bin').mkdir();(root/'bin/arw').write_text('#!/bin/sh\n')
            with patch.dict('os.environ',{'QWEN_ARW_MODEL_BASE':'http://local/v1'}):
                for selection in (STRATA,API):
                    settings=review_settings({**selection,'service_tier':'flex','web_search':'disabled'},root/'runtime.json',root/'x')
                    self.assertEqual(settings['serviceTier'],'flex');self.assertEqual(settings['config']['web_search'],'disabled')
                    for bad in ({'service_tier':'fast'},{'web_search':'on'}):
                        with self.assertRaises(ValueError):review_settings({**selection,**bad},root/'runtime.json',root/'y')

    def test_api_settings_bind_provider_key_and_native_window(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture=Fixture(Path(tmp));bound,record=fixture.execute(API,'api')
        settings=bound['settings'];config=settings['config']
        self.assertEqual((settings['model'],settings['modelProvider'],settings['serviceTier']),('gpt-6.1-sol','benchmark_openai','default'))
        self.assertEqual(config['model_providers'],{'benchmark_openai':{'name':'OpenAI','base_url':'https://api.openai.com/v1',
            'wire_api':'responses','env_key':'BENCHMARK_OPENAI_API_KEY','requires_openai_auth':False,'supports_websockets':False}})
        self.assertEqual(config['shell_environment_policy']['exclude'],['BENCHMARK_OPENAI_API_KEY','STRATA_API_KEY'])
        self.assertNotIn('model_context_window',config);self.assertIn('experimental_compact_prompt_file',config)
        self.assertEqual(record['provider']['codex_id'],'benchmark_openai')

    def test_api_startup_prompt_is_appended_once_with_loaded_sha(self):
        raw=startup_prompt_bytes((ROOT/'config/prompts/startup-instructions.txt').read_bytes(),False)
        with tempfile.TemporaryDirectory() as tmp:
            fixture=Fixture(Path(tmp));bound,record=fixture.execute(API,'on')
            off,record_off=fixture.execute({**API,'startup_instructions':False},'off')
        self.assertTrue(bound['instructions'].startswith('Exact Role.\n\n'))
        self.assertTrue(bound['instructions'].endswith(raw.decode().strip()))
        self.assertEqual(bound['instructions'].count(raw.decode().strip()),1)
        self.assertEqual(record['startup_instructions']['sha256'],hashlib.sha256(raw).hexdigest())
        self.assertFalse(record['startup_instructions']['loop_prevention_enabled'])
        self.assertEqual(record['instructions_sha256'],hashlib.sha256(bound['instructions'].encode()).hexdigest())
        self.assertEqual(bound['handoff'],'Exact handoff.')
        self.assertEqual(off['instructions'],'Exact Role.\n');self.assertEqual(record_off['startup_instructions'],{'enabled':False})

    def test_selection_validation(self):
        self.assertEqual(validate_api_selection({**API,'provider':{'id':'deepseek','base_url':'https://api.example/v1'}})['env_key'],
                         'BENCHMARK_DEEPSEEK_API_KEY')
        for bad in ({'provider':{'id':'anthropic','base_url':'https://x'}},{'provider':{'id':'openai'}},
                    {'provider':{**OPENAI,'base_url':'http://api.openai.com/v1'}},
                    {'provider':{**OPENAI,'env_key':'OPENAI_API_KEY'}},{'provider':{**OPENAI,'env_key':'STRATA_API_KEY'}},
                    {'provider':{**OPENAI,'key':'literal'}},{'model_owner':'arw'},{'engine_overrides':{}},
                    {'loop_reminder':'on'},{'model':'bad model'},{'effort':None}):
            with self.subTest(bad=bad),self.assertRaises(ValueError):validate_api_selection({**API,**bad})

    def test_api_catalog_keeps_native_guardian_unless_selected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'source.json'
            original={'models':[{'slug':'gpt-6.1-sol','auto_review_model_override':'codex-auto-review','web_search_tool_type':'text_and_image'},
                                {'slug':'other'}],'providers':{'qwen_strata':{'driver':'strata'}}}
            source.write_text(json.dumps(original))
            effective=json.loads(api_review_catalog(source,root/'a.json',API).read_text())
            self.assertEqual(effective['models'],original['models']);self.assertNotIn('providers',effective)
            chosen=json.loads(api_review_catalog(source,root/'b.json',{**API,'guardian_model':'gpt-6-luna'}).read_text())
            self.assertEqual(chosen['models'][0]['auto_review_model_override'],'gpt-6-luna')
            with self.assertRaises(ValueError):api_review_catalog(source,root/'c.json',{**API,'model':'absent'})

    def test_entry_points_keep_paths_apart(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            with patch('tools.reviewer.native_cli_binding.verify_native_cli',lambda value:None):
                with self.assertRaises(ValueError):run(None,root/'strata',API,[],root/'c.json',host='rtx3080ti')
                with patch.dict('os.environ',{},clear=True),self.assertRaises(ValueError):
                    run_api(root/'api',API,[],root/'c.json')
                with patch.dict('os.environ',{'BENCHMARK_OPENAI_API_KEY':'synthetic','STRATA_API_KEY':'synthetic'},clear=True),\
                        self.assertRaises(ValueError):
                    run_api(root/'api',API,[],root/'c.json')
            self.assertFalse((root/'api').exists())


if __name__=='__main__':unittest.main()
