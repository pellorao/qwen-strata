"""Execute hosted search between local model rounds, retaining Responses events."""
import json
import uuid

from brave_search import SearchError


def combined_usage(rounds):
    def total(key, detail=None):
        values = [((row.get(detail) or {}).get(key) if detail else row.get(key)) for row in rounds]
        return sum(values) if all(type(v) is int and v >= 0 for v in values) else None
    usage={'input_tokens': total('prompt_tokens'), 'output_tokens': total('completion_tokens'),
            'total_tokens': total('total_tokens'),
            'input_tokens_details': {'cached_tokens': total('cached_tokens', 'prompt_tokens_details')},
            'output_tokens_details': {'reasoning_tokens': total('reasoning_tokens', 'completion_tokens_details')}}
    # Codex's wire decoder rejects null integer detail fields. Omit unknown
    # optional details; never invent a zero. Raw round telemetry remains saved.
    for field in ('input_tokens_details','output_tokens_details'):
        if next(iter(usage[field].values())) is None: usage.pop(field)
    if any(usage[k] is None for k in ('input_tokens','output_tokens','total_tokens')):
        raise RuntimeError('Hosted response token totals are unknown; a valid completion usage cannot be emitted.')
    return usage


def run_hosted(translator, chat, aliases, search, owner, check, generate):
    """Other tool calls are returned to the harness, never executed on the server.

    generate receives the Chat request and yields validated upstream events.
    The original output budget covers *all* internal model rounds.
    """
    hosted = {name: meta['tool'] for name, meta in aliases.items() if meta['type'] == 'web_search'}
    allow_search = chat.get('tool_choice') != 'none'
    remaining = chat['max_tokens']
    rounds, failures = [], []
    requests = 0
    search_calls = 0
    for item in translator.req.get('input',[]) if isinstance(translator.req.get('input'),list) else []:
        if item.get('type')=='web_search_call':
            record=search.replay(owner,item['id'])
            for source in record['result'].get('results',[]):
                translator.sources[source['url']]=source['title']
    for _ in range(8):
        check()
        current = dict(chat, max_tokens=remaining)
        if 'reasoning_budget_tokens' in current:
            current['reasoning_budget_tokens'] = min(current['reasoning_budget_tokens'], max(0, remaining // 2))
        translator.calls = {}; translator.text_item = None; translator.reason_item = None
        translator.finish_reason = None
        translator.usage = {}
        for event in generate(current):
            check(); translator.accept(event)
        usage = translator.usage
        rounds.append(usage)
        consumed = usage.get('completion_tokens')
        if type(consumed) is not int or consumed < 0:
            raise RuntimeError('Hosted search cannot enforce the shared output budget: upstream output usage is unknown.')
        remaining -= consumed
        internal = [r for r in translator.calls.values() if r['name'] in hosted]
        external = [r for r in translator.calls.values() if r['name'] not in hosted]
        if internal and not allow_search:
            raise RuntimeError('Model requested search despite tool_choice=none; no search was executed.')
        # Close this round's text/reasoning and return any client-owned calls.
        translator.finish(final=False, skip_tools=hosted)
        if translator.finish_reason == 'length' or remaining <= 0:
            translator.finish_reason = 'length'
            break
        if not internal: break
        assistant = {'role': 'assistant', 'content': None, 'tool_calls': []}
        if translator.text_item is not None:
            assistant['content'] = translator.items[translator.text_item]['content'][0]['text']
        if translator.reason_item is not None:
            assistant['reasoning_content'] = translator.items[translator.reason_item]['summary'][0]['text']
        results = []
        for record in internal:
            check()
            search_calls += 1
            if search_calls > 8:
                raise RuntimeError('Hosted search call limit reached; no additional search was executed.')
            item = {'id': 'wc_' + uuid.uuid4().hex, 'type': 'web_search_call', 'status': 'in_progress',
                    'action': {'type': 'search', 'queries': []}}
            index = translator.add(item)
            translator.emit('response.web_search_call.in_progress', output_index=index, item_id=item['id'])
            args = {}
            try:
                args = json.loads(record['args'])
                translator.emit('response.web_search_call.searching', output_index=index, item_id=item['id'])
                result = search.execute(owner, args, hosted[record['name']], check)
                requests += result['brave_requests']
                item['action'] = result['action']; item['status'] = 'completed'
                for source in result['results']:
                    translator.sources[source['url']] = source['title']
                translator.emit('response.web_search_call.completed', output_index=index, item_id=item['id'])
            except (SearchError, json.JSONDecodeError) as error:
                code = getattr(error, 'code', 'invalid_arguments')
                failures.append(code)
                result = {'error': {'code': code, 'message': str(error) if isinstance(error, SearchError) else 'Invalid search JSON arguments.'}}
                item['status'] = 'failed'
            check()
            search.remember(owner, item['id'], {'arguments': args, 'result': result})
            translator.emit('response.output_item.done', output_index=index, item=item.copy())
            translator.closed.add(index)
            # Use the public item ID internally too, so replay reconstructs the same call.
            assistant['tool_calls'].append({'id': item['id'], 'type': 'function',
                'function': {'name': record['name'], 'arguments': record['args']}})
            results.append({'role': 'tool', 'tool_call_id': item['id'], 'content': json.dumps(result, ensure_ascii=False)})
        if external:
            # Resume only after the caller has supplied its own tool results.
            break
        chat['messages'].extend([assistant, *results])
        # Forced/required choice is satisfied by this round; allow a final answer.
        chat['tool_choice'] = 'auto'
    else:
        raise RuntimeError('Hosted search model-round limit reached; response was not completed.')
    check()
    translator.response['strata_search'] = {'provider': 'brave', 'model_rounds': len(rounds),
        'search_calls': search_calls, 'successful_brave_requests': requests,
        'tool_failures': failures, 'round_usage': rounds}
    search.remember_response(owner,translator.response)
    return translator.complete(combined_usage(rounds))
