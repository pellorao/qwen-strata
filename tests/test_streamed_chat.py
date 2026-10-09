import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.metrics.streamed_chat import collect


def event(delta=None, finish=None):
    return ('data: '+json.dumps({'choices':[{'index':0,'delta':delta or {},'finish_reason':finish}]})+'\n').encode()


class StreamedChatTests(unittest.TestCase):
    def test_reasoning_then_fragmented_json_and_terminal_are_preserved(self):
        lines=[event({'role':'assistant'}),event({'reasoning_content':'calculate'}),
               event({'content':'[{"id":'}),event({'content':'"a"}]'}),event(finish='stop'),b'data: [DONE]\n']
        response,timing,raw=collect(lines,now=lambda:10)
        self.assertEqual(response['choices'][0]['message']['content'],'[{"id":"a"}]')
        self.assertEqual(response['choices'][0]['message']['reasoning_content'],'calculate')
        self.assertEqual(timing['first_model_text_delta_seconds'],0)
        self.assertEqual(raw,b''.join(lines))

    def test_connection_end_without_done_is_not_success(self):
        with self.assertRaises(RuntimeError):collect([event({'content':'[]'},finish='stop')])

    def test_work_deadline_does_not_reset_with_each_delta(self):
        with self.assertRaises(TimeoutError):collect([event({'content':'[]'})],now=lambda:20,deadline=19)


if __name__=='__main__':unittest.main()
