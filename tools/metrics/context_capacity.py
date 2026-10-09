"""Capacity policy approved for future context comparisons (decimal tokens)."""

THRESHOLDS = (64000, 100000, 150000, 200000)
COMPACTION_OVERRUN_BUDGET = 32000
MAX_OUTPUT_BUDGET = 24576
CONTEXT_SLACK = 8


def context_capacity(threshold):
    if type(threshold) is not int or threshold not in THRESHOLDS:
        raise ValueError('Unsupported automatic compaction threshold')
    return threshold + COMPACTION_OVERRUN_BUDGET + MAX_OUTPUT_BUDGET + CONTEXT_SLACK


CONTEXT_WINDOWS = tuple(context_capacity(t) for t in THRESHOLDS)


def validate_context_pair(threshold, window):
    if type(window) is not int or window != context_capacity(threshold):
        raise ValueError('Context capacity must match the approved threshold formula')
