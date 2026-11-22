import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.strata.providers import api_provider, credential_deny_paths, validate_api_selection

OPENAI={'id':'openai','auth':'env_key','base_url':'https://api.openai.com/v1'}
API={'provider':OPENAI,'model':'gpt-6.1-sol','effort':'high'}


class ApiProviderTests(unittest.TestCase):
    def test_selection_validation(self):
        self.assertEqual(validate_api_selection({**API,'provider':{'id':'deepseek','base_url':'https://api.example/v1'}})['env_key'],
                         'DEEPSEEK_API_KEY')
        for bad in ({'provider':{'id':'anthropic','base_url':'https://x'}},{'provider':{'id':'openai'}},
                    {'provider':{**OPENAI,'base_url':'http://api.openai.com/v1'}},
                    {'provider':{**OPENAI,'env_key':'OPENAI_API_KEY'}},{'provider':{**OPENAI,'env_key':'STRATA_API_KEY'}},
                    {'provider':{**OPENAI,'key':'literal'}},{'model_owner':'arw'},{'engine_overrides':{}},
                    {'loop_reminder':'on'},{'model':'bad model'},{'effort':None}):
            with self.subTest(bad=bad),self.assertRaises(ValueError):validate_api_selection({**API,**bad})

    def test_shared_codex_home_is_denied_only_when_given(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);shared=root/'shared'
            provider=validate_api_selection({**API,'provider':{'id':'openai','auth_home':str(root/'login')}})
            paths=credential_deny_paths(provider,root/'home',root/'project',codex_home=shared)
            self.assertEqual(paths[-1],str(shared))
            self.assertNotIn(str(shared),credential_deny_paths(provider,root/'home',root/'project'))


if __name__=='__main__':unittest.main()
