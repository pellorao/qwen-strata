import sys
from pathlib import Path
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from responses_bridge import apply_request_defaults, to_chat


class RequestDefaultsTests(unittest.TestCase):
    def test_omitted_chat_and_responses_effort_use_installed_high_defaults(self):
        defaults={'reasoning_effort':'high','reasoning_budget_tokens':8192,'max_tokens':24576}
        request={'input':'test'};chat,_=to_chat(request)
        apply_request_defaults(chat,request,defaults,True)
        self.assertEqual((chat['reasoning_effort'],chat['reasoning_budget_tokens'],chat['max_tokens']),('high',8192,24576))
        chat=apply_request_defaults({}, {}, defaults)
        self.assertEqual(chat['reasoning_effort'],'high')
        self.assertEqual(chat['max_tokens'],24576)

    def test_explicit_values_override_selected_defaults(self):
        request={'input':'test','reasoning':{'effort':'medium'},'temperature':.7,'max_output_tokens':2500}
        chat,_=to_chat(request)
        apply_request_defaults(chat,request,{'temperature':0,'top_p':.9,'max_tokens':8192,
            'reasoning_budget_tokens':4096,'reasoning_effort':'medium'},True)
        self.assertEqual(chat['temperature'],.7)
        self.assertEqual(chat['max_tokens'],2500)
        self.assertEqual(chat['reasoning_budget_tokens'],1250)

    def test_selected_budgets_do_not_change_other_efforts(self):
        request={'input':'test','reasoning':{'effort':'low'}}
        chat,_=to_chat(request)
        apply_request_defaults(chat,request,{'reasoning_effort':'medium','max_tokens':24576,'reasoning_budget_tokens':8192},True)
        self.assertEqual((chat['max_tokens'],chat['reasoning_budget_tokens']),(8192,2048))

    def test_chat_keeps_explicit_budget(self):
        request={'reasoning_effort':'medium','reasoning_budget_tokens':2000,'max_tokens':9000}
        chat=apply_request_defaults(dict(request),request,{'reasoning_effort':'medium','reasoning_budget_tokens':4096,'max_tokens':16384})
        self.assertEqual(chat,request)

    def test_new_model_defaults_replace_previous_model_for_both_api_formats(self):
        defaults = [
            {'reasoning_effort': 'high', 'reasoning_budget_tokens': 8192, 'max_tokens': 24576, 'temperature': 0.0},
            {'reasoning_effort': 'medium', 'reasoning_budget_tokens': 4096, 'max_tokens': 16384, 'temperature': 0.3},
            {'reasoning_effort': 'low', 'reasoning_budget_tokens': 2048, 'max_tokens': 8192, 'temperature': 0.7},
        ]
        for selected in (defaults[0], defaults[1], defaults[2], defaults[0], {}):
            original = {'input': 'synthetic request'}
            chat, _ = to_chat(original)
            apply_request_defaults(chat, original, selected, responses=True)
            expected = selected or {'reasoning_effort': 'low', 'reasoning_budget_tokens': 2048, 'max_tokens': 8192}
            for key, value in expected.items():
                self.assertEqual(chat[key], value)
            self.assertEqual(apply_request_defaults({}, {}, selected), selected)
