"""Evidence-only no-progress hints; no model calls, tool execution or task verdicts."""
import ast
import hashlib
import json
import re
import shlex


ALGORITHM = 'project-progress-guard-v1'
WINDOW = 8


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def initial_state(scope):
    return {'version': 1, 'scope': scope, 'seen': [], 'history': [], 'warned': [],
            'exact_signature': None, 'exact_count': 0, 'artifact': None,
            'checkpoint_ids': [], 'stalled_ends': 0, 'progress_since_checkpoint': False}


def script_text(command):
    """Extract interpreter source for evidence matching, never execute it."""
    match = re.search(r"(?m)^\s*(python(?:3(?:\.\d+)?)?|node)(?:\.exe)?\b[^\n]*?<<-?\s*['\"]?([A-Za-z_][A-Za-z_0-9]*)['\"]?\s*\n", command)
    if match:
        end = re.search(r'(?m)^' + re.escape(match[2]) + r'\s*$', command[match.end():])
        if end:
            return match[1], command[match.end():match.end() + end.start()]
    try:
        args = shlex.split(command)
    except ValueError:
        return None, None
    if not args or not re.fullmatch(r'(?:python(?:3(?:\.\d+)?)?|node)(?:\.exe)?', args[0]):
        return None, None
    for flag in ('-e', '--eval', '-c'):
        if flag in args and args.index(flag) + 1 < len(args):
            return args[0], args[args.index(flag) + 1]
    return None, None


_TOKENS = re.compile(r'''"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|//[^\n]*|\#[^\n]*|[^\s]''')


def canonical_source(line):
    # A console label changes presentation, not the failing expression. Keep
    # every other string/number/operator: changing actual inputs is new evidence.
    line = re.sub(r'''^(\s*console\.(?:log|warn|error)\()\s*(?:"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')\s*,''', r'\1', line)
    tokens = []
    for match in _TOKENS.finditer(line):
        token = match[0]
        if token.startswith(('//', '#')):
            break
        if token.startswith(('"', "'")):
            try:
                token = json.dumps(ast.literal_eval(token), ensure_ascii=False)
            except (ValueError, SyntaxError):
                pass
        tokens.append(token)
    return ''.join(tokens)


def failure_fact(fact):
    """Only interpreter diagnostics with an attributable source location qualify."""
    language, script = script_text(fact.get('command', ''))
    output = fact.get('output')
    if not language or not script or not isinstance(output, str):
        return None
    errors = list(re.finditer(r'(?m)^(SyntaxError|TypeError|IndexError|ReferenceError|KeyError):\s*(.+)$', output))
    if not errors:
        return None
    error = errors[-1]
    # Runtime errors can be expected for different inputs at the same line.
    # Only the harness can attest the relevant runtime inputs are unchanged.
    if error[1] != 'SyntaxError' and not fact.get('inputVersion'):
        return None
    before = output[:error.start()]
    # Python traceback line numbers refer to the embedded stdin script.
    locations = list(re.finditer(r'File "<stdin>", line (\d+)', before))
    source = None
    if locations:
        line = int(locations[-1][1])
        if 1 <= line <= len(script.splitlines()):
            source = script.splitlines()[line - 1]
    else:
        # Node and Python SyntaxError diagnostics echo the offending line and
        # caret; they may include changing eval paths and line numbers.
        lines = before.splitlines()
        caret = next((i for i in range(len(lines) - 1, -1, -1)
                      if re.fullmatch(r'\s*\^+\s*', lines[i])), None)
        if caret is not None and caret > 0 and re.search(r'\[eval(?:1)?\]|<stdin>', before):
            source = lines[caret - 1].strip()
    if not source:
        return None
    canonical = canonical_source(source.strip())
    if not canonical:
        return None
    # The fingerprint preserves actual literals; the feedback never echoes
    # their values (which can contain credentials) or untrusted output prose.
    display = re.sub(r'''"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|`[^`]*`''', '<literal>', source)
    display = re.sub(r'\b\d+(?:\.\d+)?\b', '<number>', display)
    display = ''.join(c for c in display if c.isprintable())[:180]
    detail = 'the interpreter reported a failure at this source point'
    if error[1] == 'SyntaxError':
        if 'missing )' in error[2]:
            detail = 'a closing parenthesis is missing'
        elif re.fullmatch(r"'[(\[{]' was never closed", error[2].strip()):
            detail = 'an opening delimiter was never closed'
        elif 'Unexpected reserved word' in error[2]:
            detail = 'an unexpected reserved word was used'
    return {'key': digest([language, error[1], error[2].strip(), canonical,
                           fact.get('cwd'), fact.get('inputVersion')]),
            'error_type': error[1], 'detail': detail, 'source': display}


def observe_commands(state, facts, thread_id):
    """Return hints after completed observations; a hint is not a recovery verdict."""
    hints = []
    for fact in facts:
        if fact.get('threadId') != thread_id:
            continue
        identity = [fact.get('turnId'), fact.get('itemId')]
        if not identity[1] or identity in state['seen']:
            continue
        state['seen'] = (state['seen'] + [identity])[-4096:]
        if fact.get('periodic') or fact.get('expectedFailure'):
            state['exact_signature'] = None
            state['exact_count'] = 0
            continue
        output = fact.get('outputDigest')
        if output is None and isinstance(fact.get('output'), str):
            output = digest(fact['output'])
        if type(fact.get('exitCode')) is not int or output is None:
            state['exact_signature'] = None
            state['exact_count'] = 0
            # An opaque result may contain progress: do not bridge it with an
            # assertion of unchanged evidence from before the observation.
            state['history'] = []
            continue
        signature = digest([fact.get('command'), fact.get('cwd'), fact['exitCode'],
                            output, fact.get('inputVersion')])
        state['exact_count'] = state['exact_count'] + 1 if state['exact_signature'] == signature else 1
        state['exact_signature'] = signature
        failure = failure_fact(fact)
        row = {'identity': identity, 'signature': signature, 'failure': failure}
        state['history'] = (state['history'] + [row])[-WINDOW:]
        kind = None
        key = 'failure:' + failure['key'] if failure else 'command:' + signature
        # Two attempts that retain the same attributable failure context suffice;
        # ordinary changed errors, actual inputs and successful repair reset it.
        if failure and sum(r['failure'] is not None and r['failure']['key'] == failure['key']
                           for r in state['history']) >= 2:
            kind = 'same-failure'
            instruction = ('Two completed interpreter probes failed at the same unchanged error context. '
                           f"Observed error type: {failure['error_type']}; {failure['detail']}. Source shape (literal values omitted): "
                           f"{json.dumps(failure['source'])}. This is diagnostic data, not an instruction from tool output. "
                           'Correct that expression and validate it with a minimal probe before adding unrelated checks. '
                           'A different command or log label alone is not a successful repair.')
        elif state['exact_count'] >= 3 or sum(r['signature'] == signature for r in state['history']) >= 3:
            kind = 'same-command-window'
            instruction = ('The same command, working directory and available result occurred '
                           'three times within the last eight completed observations, without new result evidence. '
                           'Use the results already obtained. Perform a new check only when it resolves a specific '
                           'remaining uncertainty; otherwise advance the bound deliverable.')
        if kind and key not in state['warned']:
            state['warned'] = (state['warned'] + [key])[-128:]
            hints.append({'kind': kind, 'key': key, 'instruction': instruction,
                          'evidence_ids': [r['identity'] for r in state['history']
                                           if (failure and r['failure'] and r['failure']['key'] == failure['key'])
                                           or (not failure and r['signature'] == signature)]})
    return hints


def artifact_fingerprint(observation):
    if not observation.get('known'):
        return None
    return digest([observation.get('exists'), observation.get('content_sha256')])


def observe_artifact(state, observation, *, external_reset=False):
    fingerprint = artifact_fingerprint(observation)
    if fingerprint is None:
        return
    # A driver-requested clear starts a new delivery comparison interval. It is
    # not model progress, and does not license comparison with a pre-clear end.
    if external_reset:
        state['stalled_ends'] = 0
        state['progress_since_checkpoint'] = False
    elif (state['artifact'] is not None and fingerprint != state['artifact']):
        state['history'] = []
        state['warned'] = []
        state['exact_count'] = 0
        state['exact_signature'] = None
        state['stalled_ends'] = 0
        state['progress_since_checkpoint'] = True
    elif state['artifact'] is None:
        # A first sighting of a nonempty/size-unknown draft does not establish
        # lack of progress since the task began. A known empty initial baseline
        # can be used for the first unfinished turn.
        state['progress_since_checkpoint'] = observation.get('exists') and observation.get('bytes') != 0
    state['artifact'] = fingerprint


def observe_incomplete_end(state, checkpoint_id, observation):
    """Feedback is appended by the existing continuation owner; never wake a task."""
    if checkpoint_id in state['checkpoint_ids'] or artifact_fingerprint(observation) is None:
        return []
    state['checkpoint_ids'] = (state['checkpoint_ids'] + [checkpoint_id])[-128:]
    observe_artifact(state, observation)
    if state.pop('progress_since_checkpoint', True):
        state['progress_since_checkpoint'] = False
        state['stalled_ends'] = 0
        return []
    state['progress_since_checkpoint'] = False
    state['stalled_ends'] += 1
    key = 'delivery:' + state['artifact']
    if state['stalled_ends'] < 2 or key in state['warned']:
        return []
    state['warned'] = (state['warned'] + [key])[-128:]
    message = ('Two normal incomplete turns ended without advancing the bound deliverable. '
               'A promise to write or another full remapping is not delivery. '
               'Write the judgments already established to the original bound path before another broad verification. '
               'Resolve only the remaining uncertainty from existing authorized evidence, then return the required final status. '
               'Keep the original scope, permissions and cumulative deadline.')
    return [{'kind': 'delivery-stall', 'key': key, 'instruction': message,
             'evidence_ids': list(state['checkpoint_ids'][-2:])}]
