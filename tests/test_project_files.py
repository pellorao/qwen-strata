import sys,tempfile,unittest,json,subprocess,os
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from project_files_mcp import call

class ProjectFileTests(unittest.TestCase):
    def test_scope_and_pages(self):
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder);root=base/'root';root.mkdir();(base/'outside.txt').write_text('private',encoding='utf-8')
            (root/'中文.txt').write_text('第一行\n第二行\n第三行',encoding='utf-8');(root/'.git').mkdir()
            result=call(root,'read_file',{'path':'中文.txt','start_line':2,'line_count':1})
            self.assertEqual(result['text'],'第二行');self.assertTrue(result['truncated']);self.assertEqual(result['next_line'],3)
            self.assertEqual(call(root,'list_files',{})['entries'],[{'path':'中文.txt','directory':False}])
            for name,args in [('read_file',{'path':'../outside.txt'}),('read_file',{'path':str(base/'outside.txt')}),('list_files',{'path':'.git'}),('read_file',{'path':'中文.txt','line_count':401}),('write_file',{'path':'中文.txt'})]:
                with self.assertRaises(ValueError):call(root,name,args)
            self.assertEqual((root/'中文.txt').read_text(encoding='utf-8'),'第一行\n第二行\n第三行')
    def test_stdio_chinese(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'中文.txt').write_text('UTF8中文正文',encoding='utf-8')
            request={'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':'read_file','arguments':{'path':'中文.txt'}}}
            proc=subprocess.run([sys.executable,str(Path(__file__).resolve().parents[1]/'src/project_files_mcp.py')],input=(json.dumps(request,ensure_ascii=False)+'\n').encode('utf-8'),capture_output=True,env=dict(os.environ,QWEN_PROJECT_WORKSPACE=str(root),QWEN_PROJECT_AUDIT=''),timeout=10)
            self.assertEqual(proc.returncode,0)
            result=json.loads(proc.stdout.decode('utf-8'))['result']
            self.assertNotIn('isError',result)
            self.assertEqual(json.loads(result['content'][0]['text'])['text'],'UTF8中文正文')
    def test_non_object_json_lines_get_an_error_and_the_server_keeps_running(self):
        with tempfile.TemporaryDirectory() as folder:
            request={'jsonrpc':'2.0','id':7,'method':'ping'}
            data=('null\n5\n[]\n'+json.dumps(request)+'\n').encode('utf-8')
            proc=subprocess.run([sys.executable,str(Path(__file__).resolve().parents[1]/'src/project_files_mcp.py')],input=data,capture_output=True,env=dict(os.environ,QWEN_PROJECT_WORKSPACE=folder,QWEN_PROJECT_AUDIT=''),timeout=10)
            self.assertEqual(proc.returncode,0)
            replies=[json.loads(line) for line in proc.stdout.decode('utf-8').splitlines()]
            self.assertEqual(len(replies),4)
            self.assertTrue(all('error' in r and r['id'] is None for r in replies[:3]))
            self.assertEqual(replies[3],{'jsonrpc':'2.0','id':7,'result':{}})
    def test_long_line_is_explicit(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'a.txt').write_text('x'*24001,encoding='utf-8')
            result=call(root,'read_file',{'path':'a.txt'})
            self.assertTrue(result['truncated']);self.assertTrue(result['overlong_line']);self.assertIsNone(result['next_line'])

if __name__=='__main__':unittest.main()
