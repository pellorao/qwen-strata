"""Distinct trusted feedback for cross-call and completed-response repetition."""


def reminder_text(kind):
    if kind == 'single_response':
        return ('The completed reasoning or output contains repeated passages or repeated reconsideration. '
                'Keep the conclusions already established from authorized evidence. In the next response, '
                'continue from the first unresolved step instead of reproducing that passage or restarting '
                'the same deliberation. This message concerns a completed response, not an interruption '
                'of its generation. Keep the original task, permissions and cumulative deadline.')
    if kind == 'cross_call':
        return ('Repeated operations or retries have produced no new relevant evidence or progress. '
                'Use the available results, address the specific unresolved cause with a focused step, '
                'and advance the original deliverable. Do not repeat the same ineffective operation or '
                'replay a tool with unknown side effects. Keep the original task, permissions and cumulative deadline.')
    raise ValueError('Unknown repetition reminder kind')
