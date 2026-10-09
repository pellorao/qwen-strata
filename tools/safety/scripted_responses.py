"""Scripted Responses SSE for loopback mocks: a fixed answer or tool calls, never a model."""
import json
import time
import uuid


def tool_aliases(request):
    """Map each declared client tool to {name, namespace, type}, keyed as the model would call it."""
    aliases = {}
    declared = list(request.get('tools') or [])
    for item in request.get('input') or []:
        if isinstance(item, dict) and item.get('type') in ('additional_tools', 'tool_search_output'):
            declared += item.get('tools') or []

    def add(tool, namespace=None):
        alias = namespace + '__' + tool['name'] if namespace else tool['name']
        aliases[alias] = {'name': tool['name'], 'namespace': namespace, 'type': tool.get('type', 'function')}

    for tool in declared:
        kind = tool.get('type')
        if kind == 'namespace':
            for nested in tool.get('tools') or []:
                add(nested, tool['name'])
        elif kind in ('function', 'custom'):
            add(tool)
        elif kind == 'tool_search':
            aliases['codex_tool_search'] = {'name': 'tool_search', 'namespace': None, 'type': 'tool_search'}
    return aliases


def scripted_stream(emit, request, aliases, text=None, calls=()):
    """Emit one complete response: `text`, or `calls` as [(alias, arguments)]."""
    sequence = iter(range(1 << 30))
    response = {'id': 'resp_' + uuid.uuid4().hex, 'object': 'response', 'created_at': int(time.time()),
                'status': 'in_progress', 'model': request.get('model'), 'output': [], 'usage': None}

    def event(kind, **data):
        emit(dict(type=kind, sequence_number=next(sequence), **data))

    event('response.created', response=dict(response))
    items = []
    if not calls:
        items.append({'id': 'msg_' + uuid.uuid4().hex, 'type': 'message', 'role': 'assistant', 'status': 'completed',
                      'content': [{'type': 'output_text', 'text': text or '', 'annotations': []}]})
    for index, (alias, arguments) in enumerate(calls):
        meta = aliases[alias]
        call_id = f'call_{uuid.uuid4().hex}'
        if meta['type'] == 'tool_search':
            item = {'type': 'tool_search_call', 'execution': 'client', 'arguments': arguments}
        elif meta['type'] == 'custom':
            item = {'type': 'custom_tool_call', 'name': meta['name'], 'input': arguments['input']}
        else:
            item = {'type': 'function_call', 'name': meta['name'], 'arguments': json.dumps(arguments)}
        if meta['namespace']:
            item['namespace'] = meta['namespace']
        items.append(dict(item, id=f'fc_{index}_{uuid.uuid4().hex}', call_id=call_id, status='completed'))
    for index, item in enumerate(items):
        event('response.output_item.added', output_index=index, item=item)
        event('response.output_item.done', output_index=index, item=item)
    response.update(status='completed', output=items, usage={
        'input_tokens': 0, 'output_tokens': 0, 'total_tokens': 0,
        'input_tokens_details': {'cached_tokens': 0}, 'output_tokens_details': {'reasoning_tokens': 0}})
    event('response.completed', response=response)
    return response
