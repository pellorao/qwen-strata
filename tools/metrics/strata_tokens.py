"""Token consumption from native engine log records, independent of API usage."""
import re


PATTERN = re.compile(
    r'prompt (\d+) tokens = (\d+) reused \+ (\d+)(?: of (\d+))? read in '
    r'([\d.]+) ms.*?, (\d+) generated in ([\d.]+) ms')


def parse_engine_log(content):
    records = []
    for line_number, line in enumerate(content.splitlines(), 1):
        match = PATTERN.search(line)
        if match is None:
            # Startup can report "prompt chunk16384 ->8192". This is a
            # configuration diagnostic, not a partially written token row.
            chunk_notice = re.search(
                r'strata serve: prompt chunk \d+ -> \d+ tokens '
                r'so its buffers fit in every expert cache\s*$', line)
            if 'strata serve: prompt ' in line and chunk_notice is None:
                raise ValueError(f'Incomplete native token record at log line {line_number}')
            continue
        prompt, cached, read, read_total, prompt_ms, output, decode_ms = match.groups()
        prompt, cached, read, output = map(int, (prompt, cached, read, output))
        if cached + read > prompt or read_total is not None and read > int(read_total):
            raise ValueError(f'Inconsistent native token record at log line {line_number}')
        records.append({'input': prompt, 'cached': cached, 'uncached': read,
                        'prompt_ms': float(prompt_ms), 'output': output,
                        'decode_ms': float(decode_ms), 'log_line': line_number})
    return records


def sum_engine_tokens(records):
    if not records:
        return None
    return {name: sum(record[field] for record in records)
            for name, field in (('uncached_input', 'uncached'),
                                ('cached_input', 'cached'), ('output', 'output'))}


def engine_rates(records):
    """Physical engine rates for exactly these stages, never task wall time."""
    tokens = sum_engine_tokens(records)
    input_seconds = sum(r['prompt_ms'] for r in records) / 1000 if records else None
    decode_seconds = sum(r['decode_ms'] for r in records) / 1000 if records else None
    return {
        'engine_input_seconds': input_seconds,
        'engine_decode_seconds': decode_seconds,
        'engine_input_tokens_per_second': (
            tokens['uncached_input'] / input_seconds if tokens and input_seconds else None),
        'engine_output_tokens_per_second': (
            tokens['output'] / decode_seconds if tokens and decode_seconds else None),
        'unit': 'token/s',
        'source': 'Internal read/generated and prompt/decode durations; cache excluded from input numerator',
    }


def task_rates(tokens, review_seconds):
    """Review rates over work duration; tools/active recovery count, downtime and idle do not."""
    known = tokens is not None and review_seconds is not None and review_seconds > 0
    return {
        'task_review_seconds': review_seconds,
        'task_input_tokens_per_second': tokens['uncached_input'] / review_seconds if known else None,
        'task_output_tokens_per_second': tokens['output'] / review_seconds if known else None,
    }


def bounded_rates(records, missing_tokens, missing_seconds, review_seconds):
    """Propagate evidence-supplied bounds; never infer missing tokens from usage.

    Token intervals are marginal bounds: uncached/cached endpoints need not
    occur together. Their joint constraints belong in the evidence receipt.
    Returned observed values describe recorded stages, not a guessed full sum.
    """
    import math

    def interval(value):
        if (not isinstance(value, (list, tuple)) or len(value) != 2
                or any(type(v) not in (int, float) or not math.isfinite(v)
                       for v in value) or value[0] < 0 or value[1] < value[0]):
            raise ValueError('Bounds must be finite nonnegative ordered pairs.')
        return list(value)

    known = sum_engine_tokens(records)
    if known is None:
        raise ValueError('At least one recorded internal stage is required.')
    tokens = {k: [known[k] + v for v in interval(missing_tokens[k])]
              for k in ('uncached_input', 'cached_input', 'output')}
    work = interval(review_seconds)
    if work[0] == 0:
        raise ValueError('Review time must have a positive lower bound.')
    measured = engine_rates(records)
    times = {}
    for phase, field in [('input', 'engine_input_seconds'),
                         ('decode', 'engine_decode_seconds')]:
        times[phase] = [measured[field] + v
                        for v in interval(missing_seconds[phase])]
        if times[phase][0] == 0:
            raise ValueError('Recorded phase time must be positive.')
    ratio = lambda amount, duration: [amount[0] / duration[1],
                                      amount[1] / duration[0]]
    return {
        'recorded_complete_stage_tokens': known,
        'recorded_complete_stage_count': len(records),
        'tokens_interval': tokens,
        'engine_input_seconds_interval': times['input'],
        'engine_decode_seconds_interval': times['decode'],
        'review_work_seconds_interval': work,
        'engine_input_tokens_per_second_interval': ratio(tokens['uncached_input'], times['input']),
        'engine_output_tokens_per_second_interval': ratio(tokens['output'], times['decode']),
        'task_input_tokens_per_second_interval': ratio(tokens['uncached_input'], work),
        'task_output_tokens_per_second_interval': ratio(tokens['output'], work),
        'bound_type': 'evidence-bounded marginal envelope, not a confidence interval',
    }
