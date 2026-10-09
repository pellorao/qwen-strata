"""No model requests: final counters can arrive during shutdown."""
import sys
from pathlib import Path
from unittest import TestCase, mock

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import tools.reviewer.arw_measure as arw_measure


class StopCaptureTests(TestCase):
    def test_final_snapshot_includes_counter_emitted_during_stop(self):
        state={'records':[{'output':10}]}
        class Controller:
            def stop(self):
                state['records'].append({'output':7})
                return {'status':'stopped'}
        def capture(*args):
            return list(state['records']),{'output':sum(r['output'] for r in state['records'])}
        with mock.patch.object(arw_measure,'capture_engine_log',side_effect=capture):
            stopped,records,tokens=arw_measure.stop_and_capture_engine_log(Controller(),None,'Q2_0',0,Path('/unused'))
        self.assertEqual(stopped['status'],'stopped')
        self.assertEqual(len(records),2)
        self.assertEqual(tokens,{'output':17})

    def test_unconfirmed_stop_cannot_publish_final_counters(self):
        controller=mock.Mock();controller.stop.return_value={'status':'partial'}
        with mock.patch.object(arw_measure,'capture_engine_log') as capture:
            with self.assertRaisesRegex(RuntimeError,'stop is unconfirmed'):
                arw_measure.stop_and_capture_engine_log(controller,None,'Q2_0',0,Path('/unused'))
        capture.assert_not_called()

    def test_failed_stop_cannot_publish_final_counters(self):
        controller=mock.Mock();controller.stop.side_effect=OSError('test stop failure')
        with mock.patch.object(arw_measure,'capture_engine_log') as capture:
            with self.assertRaises(OSError):
                arw_measure.stop_and_capture_engine_log(controller,None,'Q2_0',0,Path('/unused'))
        capture.assert_not_called()
