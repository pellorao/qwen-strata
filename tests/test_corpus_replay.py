"""The frozen development / validation split partitions the loop corpus without sharing a task."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.loop.corpus_replay import CORPUS, load


class SplitTests(unittest.TestCase):
    def test_split_partitions_traces_and_groups(self):
        development, validation, whole = load('development'), load('validation'), load(None)
        traces = lambda part: {o.trace_id for o in part[0]}
        self.assertFalse(traces(development) & traces(validation))
        self.assertEqual(traces(development) | traces(validation), traces(whole))
        self.assertEqual(len(development[1]) + len(validation[1]), len(whole[1]))

    def test_no_initial_task_text_is_on_both_sides(self):
        manifest = json.loads((CORPUS / 'behavior-manifest.json').read_text())
        split = json.loads((CORPUS / 'split.json').read_text())
        side = {t: name for name in ('development', 'validation') for t in split[name]}
        seen = {}
        for trace in manifest['traces']:
            for task in trace['initial_task_inputs']:
                self.assertEqual(seen.setdefault(task['source_text_sha256'], side[trace['trace_id']]),
                                 side[trace['trace_id']])

    def test_companions_are_reviewed_on_development_only_and_join_their_occurrence(self):
        review = json.loads((CORPUS / 'occurrence-companions.json').read_text())
        split = json.loads((CORPUS / 'split.json').read_text())
        self.assertTrue({d['trace_id'] for d in review['decisions']} <= set(split['development']))
        groups = {g.id: g for g in load('development')[1]}
        for d in review['decisions']:
            record = d['trace_id'] + ':' + ','.join(map(str, d['events']))
            self.assertEqual(record in groups[d['case_id']].records()[d['occurrence']], d['decision'] == 'companion')


if __name__ == '__main__':
    unittest.main()
