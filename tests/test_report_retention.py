"""Permanent reports survive deletion or partial recreation of raw measurements."""
import json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import tools.ops.export_reports as reports
class ReportRetentionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.original=(reports.ROOT,reports.RAW,reports.PUBLIC)
        reports.ROOT=Path(self.temp.name);reports.RAW=reports.ROOT/'.tmp/reports';reports.PUBLIC=reports.ROOT/'reports'
        self.path=reports.PUBLIC/'v0.1.37/integration.json';self.path.parent.mkdir(parents=True)
        self.path.write_text(json.dumps({'version':'0.1.37','type':'integration','results':{'historical':{'statistics':{'pass':True}}}}),encoding='utf-8')
    def tearDown(self):
        reports.ROOT,reports.RAW,reports.PUBLIC=self.original;self.temp.cleanup()
    def test_missing_raw_preserves_permanent_report(self):
        before=self.path.read_bytes();reports.export();self.assertEqual(self.path.read_bytes(),before)
    def test_hotfix_report_directory_is_not_treated_as_a_legacy_tree_to_move(self):
        current=reports.PUBLIC/'v0.1.40.1/summary.json';current.parent.mkdir()
        current.write_text('{"version":"0.1.40.1","pass":true}')
        before=current.read_bytes();reports.RAW.mkdir(parents=True)
        reports.export()
        self.assertEqual(current.read_bytes(),before)
        self.assertFalse((reports.ROOT/'.tmp/report-export-before-summary').exists())
    def test_new_partial_raw_merges_and_has_no_temporary_references(self):
        reports.RAW.mkdir(parents=True);(reports.RAW/'new.json').write_text('{"pass":true}',encoding='utf-8')
        reports.publish('0.1.37','integration',[('new','new.json',reports.identity)])
        text=self.path.read_text(encoding='utf-8');data=json.loads(text)
        self.assertIn('historical',data['results']);self.assertIn('new',data['results']);self.assertNotIn('.tmp',text)
    def test_new_wsl_version_keeps_all_existing_version_reports(self):
        before=self.path.read_bytes();future=self.path.parent.parent/'v0.1.38/wsl-workflow.json'
        future.parent.mkdir();future.write_text(json.dumps({'version':'0.1.38','type':'wsl-workflow','results':{'earlier':{'statistics':{'pass':False}}}}))
        reports.RAW.mkdir(parents=True)
        (reports.RAW/'wsl-workflow-summary.json').write_text('{"version":"0.1.38","pass":true}')
        reports.export();self.assertEqual(self.path.read_bytes(),before)
        results=json.loads(future.read_text())['results'];self.assertIn('earlier',results);self.assertTrue(results['linux_acceptance']['statistics']['pass'])
        self.assertFalse((reports.ROOT/'.tmp/report-export-before-summary').exists())
    def test_legacy_summary_cannot_republish_raw_answers_or_detail_references(self):
        reports.RAW.mkdir(parents=True)
        (reports.RAW/'new.json').write_text(json.dumps({'pass':False,'retained_details':['wsl-compaction/selected-summaries.json'],'bad_summary_continuation':'raw model answer','summary':{'pass':True,'retained_details':['other.json']}}))
        reports.publish('0.1.37','integration',[('new','new.json',reports.identity)])
        statistics=json.loads(self.path.read_text())['results']['new']['statistics']
        self.assertEqual(statistics,{'pass':False,'summary':{'pass':True}})
if __name__=='__main__':unittest.main()
