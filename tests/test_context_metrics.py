import json
from pathlib import Path
import sys,tempfile,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.metrics.context_metrics import engine_token_speeds, inspect_compactions

class EngineSpeedTests(unittest.TestCase):
    def test_phase_totals_include_generation_and_exclude_cache_reuse(self):
        rates = engine_token_speeds({'uncached_input': 200, 'cached_input': 10000, 'output': 30}, .2, .3)
        self.assertEqual(rates, {'input_tokens_per_second': 1000, 'output_tokens_per_second': 100})

    def test_unknown_and_zero_duration_cannot_be_reported_as_zero_speed(self):
        rates = engine_token_speeds({'uncached_input': None, 'output': 30}, 1, 0)
        self.assertEqual(rates, {'input_tokens_per_second': None, 'output_tokens_per_second': None})

    def test_invalid_counter_is_not_a_rate(self):
        with self.assertRaises(ValueError):
            engine_token_speeds({'uncached_input': -1, 'output': 30}, 1, 1)

class CompactionEvidenceTests(unittest.TestCase):
    def test_replayed_replacement_counts_once_and_failure_stays_separate(self):
        compact={'type':'compacted','payload':{'window_id':'w1','compaction_response_id':'r1','replacement_history':[]}}
        events=[compact,compact,{'type':'response_item','payload':{'type':'function_call'}},
                {'type':'event_msg','payload':{'type':'error','message':'compaction failed'}}]
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'history.jsonl';p.write_text('\n'.join(map(json.dumps,events)))
            r=inspect_compactions(p)
            self.assertEqual(r['successful_compaction_count'],1)
            self.assertEqual(r['observed_failed_compaction_count'],1)
            self.assertTrue(r['continued_after_every_success'])
    def test_incomplete_evidence_cannot_be_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'history.jsonl';p.write_text(json.dumps({'type':'compacted','payload':{}}))
            with self.assertRaises(ValueError):inspect_compactions(p)
if __name__=='__main__':unittest.main()
