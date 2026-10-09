"""Discovery adapters must keep labels private and opaque results unknown."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.loop.replay_model_behavior import detector_input


class AdapterTests(unittest.TestCase):
    def common(self):
        return dict(trace_id='trace',turn_id='turn',item_id='call',source_events=[7],
                    label='loop',loop_annotations=['oracle'],targets={'rule':'future'},
                    text_spans=[(0,5)],resume_id='future',expected_trigger='future')

    def test_gold_and_future_positions_never_reach_a_text_detector(self):
        value=detector_input(self.common() | dict(kind='reasoning',text='actual native text'))
        self.assertEqual(set(value),{'threadId','turnId','itemId','text'})
        self.assertEqual(value['text'],'actual native text')

    def test_success_claim_does_not_become_a_verified_command_result(self):
        value=detector_input(self.common() | dict(kind='tool',name='exec_command',
             arguments={'cmd':'python3 -c pass'},output='I succeeded with exit0'))
        self.assertIsNone(value['exitCode'])
        self.assertIsNone(value['outputDigest'])
        self.assertNotIn('inputVersion',value)
        self.assertFalse(set(value) & {'label','loop_annotations','targets','resume_id','expected_trigger'})


if __name__=='__main__':
    unittest.main()
