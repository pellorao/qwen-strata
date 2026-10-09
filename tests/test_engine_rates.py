import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.metrics.strata_tokens import engine_rates

class EngineRates(unittest.TestCase):
    def test_cache_is_excluded_and_all_execution_segments_are_included(self):
        stages=[{'uncached':1000,'cached':5000,'output':400,'prompt_ms':500,'decode_ms':2000},
                {'uncached':2000,'cached':7000,'output':200,'prompt_ms':1000,'decode_ms':1000}]
        rates=engine_rates(stages)
        self.assertEqual(rates['engine_input_tokens_per_second'],2000)
        self.assertEqual(rates['engine_output_tokens_per_second'],200)
        self.assertEqual(rates['engine_input_seconds'],1.5)
    def test_unavailable_or_zero_engine_duration_is_unknown(self):
        self.assertIsNone(engine_rates([])['engine_output_tokens_per_second'])
        rates=engine_rates([{'uncached':0,'cached':100,'output':0,'prompt_ms':0,'decode_ms':0}])
        self.assertIsNone(rates['engine_input_tokens_per_second'])
        self.assertIsNone(rates['engine_output_tokens_per_second'])


class TaskRates(unittest.TestCase):
    def test_tool_wait_and_recovery_reduce_task_rates_without_changing_engine_rates(self):
        from tools.metrics.strata_tokens import task_rates
        result=task_rates({'uncached_input':1000,'cached_input':9000,'output':500},20)
        self.assertEqual(result['task_input_tokens_per_second'],50)
        self.assertEqual(result['task_output_tokens_per_second'],25)
        self.assertEqual(result['task_review_seconds'],20)
    def test_task_rate_uses_supplied_model_alive_denominator(self):
        from tools.metrics.strata_tokens import task_rates
        started_ms, finished_ms = 100000, 160000
        result=task_rates({"uncached_input":6000,"cached_input":9000,"output":600},(finished_ms-started_ms)/1000)
        self.assertEqual(result["task_input_tokens_per_second"],100)
        self.assertEqual(result["task_output_tokens_per_second"],10)

    def test_unknown_total_review_time_stays_unknown(self):
        from tools.metrics.strata_tokens import task_rates
        result=task_rates({'uncached_input':1000,'cached_input':0,'output':500},None)
        self.assertIsNone(result['task_input_tokens_per_second'])
        self.assertIsNone(result['task_output_tokens_per_second'])

if __name__=='__main__':unittest.main()
