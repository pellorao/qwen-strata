"""Scripted Responses streams name tools the way the client declared them."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.safety.scripted_responses import scripted_stream, tool_aliases


class ScriptedResponsesTests(unittest.TestCase):
    request = {'model': 'm', 'tools': [
        {'type': 'function', 'name': 'shell'}, {'type': 'tool_search'},
        {'type': 'namespace', 'name': 'mcp__files', 'tools': [{'type': 'function', 'name': 'read'}]}],
        'input': [{'type': 'additional_tools', 'tools': [{'type': 'custom', 'name': 'apply_patch'}]}]}

    def test_aliases_cover_namespaces_additional_tools_and_search(self):
        aliases = tool_aliases(self.request)
        self.assertEqual(set(aliases), {'shell', 'codex_tool_search', 'mcp__files__read', 'apply_patch'})
        self.assertEqual(aliases['mcp__files__read']['namespace'], 'mcp__files')

    def test_stream_emits_complete_items(self):
        events = []
        response = scripted_stream(events.append, self.request, tool_aliases(self.request),
                                   calls=[('mcp__files__read', {'path': 'a'}), ('apply_patch', {'input': 'p'})])
        self.assertEqual([e['type'] for e in events][0], 'response.created')
        self.assertEqual(events[-1]['type'], 'response.completed')
        self.assertEqual([e['sequence_number'] for e in events], list(range(len(events))))
        first, second = response['output']
        self.assertEqual((first['type'], first['name'], first['namespace']), ('function_call', 'read', 'mcp__files'))
        self.assertEqual((second['type'], second['input']), ('custom_tool_call', 'p'))
        text = scripted_stream(events.append, self.request, {}, 'done')['output'][0]
        self.assertEqual(text['content'][0]['text'], 'done')


if __name__ == '__main__':
    unittest.main()
