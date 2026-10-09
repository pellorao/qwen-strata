import sys, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from responses_bridge import to_chat, Translator, bind_policy
class BridgeTests(unittest.TestCase):
    def test_non_loopback_binding_requires_explicit_client(self):
        self.assertEqual(bind_policy('127.0.0.1',[]),('127.0.0.1',None))
        self.assertEqual(bind_policy('172.27.48.1',['172.27.63.165']),('172.27.48.1',{'172.27.63.165'}))
        for host,clients in [('0.0.0.0',['172.27.63.165']),('8.8.8.8',['172.27.63.165']),('172.27.48.1',[])]:
            with self.assertRaises(ValueError):bind_policy(host,clients)
    def test_custom_namespace_and_usage(self):
        req={'tools':[{'type':'namespace','name':'functions','tools':[{'type':'custom','name':'apply_patch'}]}], 'input':[{'type':'reasoning','summary':[{'text':'plan'}]},{'type':'custom_tool_call','namespace':'functions','name':'apply_patch','call_id':'c','input':'patch'},{'type':'custom_tool_call_output','call_id':'c','output':'ok'}]}
        chat,aliases=to_chat(req)
        self.assertEqual(chat['messages'][0]['reasoning_content'],'plan')
        self.assertEqual(chat['messages'][1]['tool_call_id'],'c')
        events=[]; trans=Translator(events.append,req,aliases); trans.begin()
        trans.accept({'choices':[{'delta':{'tool_calls':[{'index':0,'id':'new','function':{'name':'functions__apply_patch','arguments':'{"input":"patch"}'}}]},'finish_reason':'tool_calls'}],'usage':{'prompt_tokens':200000,'completion_tokens':10,'total_tokens':200010,'prompt_tokens_details':{'cached_tokens':199000}}})
        result=trans.finish(); self.assertEqual(result['output'][0]['input'],'patch'); self.assertEqual(result['output'][0]['namespace'],'functions')
        self.assertEqual(result['usage']['input_tokens_details']['cached_tokens'],199000)
        self.assertEqual([e['sequence_number'] for e in events],list(range(len(events))))
    def test_incomplete_and_reasoning(self):
        events=[]; trans=Translator(events.append,{},{}); trans.begin()
        trans.accept({'choices':[{'delta':{'reasoning_content':'think'}}]}); trans.accept({'choices':[{'delta':{'content':'answer'},'finish_reason':'length'}]})
        result=trans.finish(); self.assertEqual(result['status'],'incomplete'); self.assertEqual(result['output'][0]['summary'][0]['text'],'think')
    def test_duplicate_long_tool_alias_is_rejected(self):
        tool={'type':'function','name':'long_'+'x'*80}
        with self.assertRaises(ValueError):to_chat({'tools':[tool,tool],'input':[]})
    def test_native_additional_tools_preserves_declarations_and_history(self):
        tool={'type':'namespace','name':'functions','tools':[{'type':'function','name':'exec_command',
            'description':'Run a command','parameters':{'type':'object','properties':{'cmd':{'type':'string'}}}}]}
        req={'input':[{'type':'additional_tools','role':'developer','tools':[tool]},
            {'type':'function_call','namespace':'functions','name':'exec_command','call_id':'a','arguments':'{"cmd":"/usr/bin/true"}'},
            {'type':'function_call_output','call_id':'a','output':'exit 0'}]}
        chat,aliases=to_chat(req)
        self.assertEqual(chat['tools'][0]['function']['name'],'functions__exec_command')
        self.assertEqual(chat['messages'][0]['tool_calls'][0]['function']['name'],'functions__exec_command')
        self.assertEqual(chat['messages'][1]['tool_call_id'],'a')
        self.assertEqual(aliases['functions__exec_command']['namespace'],'functions')
        self.assertFalse(any(m['role']=='system' for m in chat['messages']))
    def test_additional_tools_repeated_inventory_deduplicates_but_conflicts_fail(self):
        tool={'type':'function','name':'f','description':'original'}
        chat,_=to_chat({'tools':[tool],'input':[{'type':'additional_tools','role':'developer','tools':[tool,tool]}]})
        self.assertEqual(len(chat['tools']),1)
        for declared in ([dict(tool,description='changed')],None,{},[None]):
            with self.subTest(declared=declared),self.assertRaises(ValueError):
                to_chat({'tools':[tool],'input':[{'type':'additional_tools','role':'developer','tools':declared}]})
    def test_history_and_rejections(self):
        chat,_=to_chat({'input':[{'type':'function_call','call_id':'a','name':'f','arguments':'{}'},{'type':'function_call','call_id':'b','name':'g','arguments':'{}'},{'type':'function_call_output','call_id':'a','output':'A'}]})
        self.assertEqual(len(chat['messages'][0]['tool_calls']),2)
        for req in ({'previous_response_id':'x'},{'tools':[{'type':'web_search'}]},{'input':[{'type':'message','content':[{'type':'input_image'}]}]}):
            with self.assertRaises(ValueError): to_chat(req)
        trans=Translator(lambda e:None,{},{}); trans.accept({'choices':[{'delta':{'tool_calls':[{'function':{'name':'missing','arguments':'{}'}}]}}]})
        with self.assertRaises(ValueError): trans.finish()
    def test_client_tool_discovery_returns_native_call_without_execution(self):
        req={'tools':[{'type':'tool_search','execution':'client','description':'Discover deferred MCP tools',
                       'parameters':{'type':'object','properties':{'query':{'type':'string'}}}}]}
        chat,aliases=to_chat(req)
        self.assertEqual(chat['tools'][0]['function']['name'],'codex_tool_search')
        events=[];trans=Translator(events.append,req,aliases);trans.begin()
        trans.accept({'choices':[{'delta':{'tool_calls':[{'index':0,'id':'find-1','function':{
            'name':'codex_tool_search','arguments':'{"query":"deployment status","limit":3}'}}]},'finish_reason':'tool_calls'}]})
        item=trans.finish()['output'][0]
        self.assertEqual(item['type'],'tool_search_call')
        self.assertEqual(item['execution'],'client')
        self.assertEqual(item['call_id'],'find-1')
        self.assertEqual(item['arguments'],{'query':'deployment status','limit':3})
        self.assertEqual(events[-2]['type'],'response.output_item.done')
    def test_discovered_tools_and_native_search_history_replay(self):
        tool={'type':'namespace','name':'mcp__deployment','tools':[{'type':'function','name':'status',
              'description':'Read status','parameters':{'type':'object','properties':{}}}]}
        req={'tools':[{'type':'tool_search','execution':'client'}],'input':[
            {'type':'tool_search_call','execution':'client','call_id':'discover','arguments':{'query':'status'}},
            {'type':'tool_search_output','execution':'client','status':'completed','call_id':'discover','tools':[tool]},
            {'type':'additional_tools','role':'developer','tools':[tool]},
            {'type':'function_call','namespace':'mcp__deployment','name':'status','call_id':'status','arguments':'{}'},
            {'type':'function_call_output','call_id':'status','output':'healthy'}]}
        chat,aliases=to_chat(req)
        self.assertIn('mcp__deployment__status',aliases)
        self.assertEqual(chat['messages'][0]['tool_calls'][0]['function']['name'],'codex_tool_search')
        self.assertEqual(chat['messages'][1]['tool_call_id'],'discover')
        self.assertEqual(chat['messages'][0]['tool_calls'][1]['function']['name'],'mcp__deployment__status')
        self.assertFalse(any(m['role']=='system' for m in chat['messages']))
        self.assertEqual(len(chat['tools']),2)
    def test_invalid_discovery_modes_and_history_fail_closed(self):
        for req in ({'tools':[{'type':'tool_search','execution':'server'}]},
                    {'input':[{'type':'tool_search_call','execution':'client','call_id':'a','arguments':'bad'}]},
                    {'input':[{'type':'tool_search_output','execution':'client','call_id':'a','tools':None}]},
                    {'input':[{'type':'tool_search_output','execution':'server','call_id':'a','tools':[]}]},
                    {'input':[{'type':'tool_search_output','execution':'client','tools':[]}]}):
            with self.subTest(req=req),self.assertRaises(ValueError):to_chat(req)
if __name__=='__main__': unittest.main()
