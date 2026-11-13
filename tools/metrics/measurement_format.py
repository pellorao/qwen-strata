"""Shared measurement presentation; round only after aggregation."""
from decimal import Decimal


def minutes(seconds):
    return '未知' if seconds is None else format(seconds / 60, '.1f')


def equivalent_cost_usd(tokens):
    """User-defined USD equivalent from raw token counts, not rounded K cells."""
    values = [tokens.get(k) for k in ('uncached_input', 'cached_input', 'output')]
    if any(v is None for v in values):
        return None
    uncached, cached, output = map(lambda v: Decimal(str(v)), values)
    return (uncached * Decimal('0.15') + cached * Decimal('0.016')
            + output * Decimal('0.47')) / 1_000_000
