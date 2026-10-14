"""Per-batch speed probe for the reading-volume time limit: P, G and beta on the real material.

T seconds = B * (1/P + k/G) / beta (.claude/rules/reviewer-suite.md). One cold load, two requests:
a wrapper-only baseline, then the same wrapper after the concatenated material. beta is the
material bytes over the input-token difference; P and G come from the material request's own
engine record (read / prompt time, generated / decode time). API usage is never used.
"""
import argparse
from pathlib import Path

from tools.reviewer.wsl_client import save

MODEL = 'IQ3_XXS'
STARTUP_SHA256 = '1cae169a1b1ebcafbd6b0562992d377c84a550f4cd8bea7184340cf033cd17f6'
MAX_TOKENS = 512
INSTRUCTION = ('Write a plain-text walkthrough of the material above, one module at a time. '
               'Keep writing until you are stopped.')


def material(paths):
    """Files in the given order with a path header each; B counts only the file bytes."""
    parts, size = [], 0
    for path in paths:
        raw = Path(path).read_bytes()
        size += len(raw)
        parts.append(f'=== {path} ===\n' + raw.decode())
    return '\n\n'.join(parts), size


def bodies(text, max_tokens=MAX_TOKENS):
    request = lambda content, limit: {'messages': [{'role': 'user', 'content': content}],
        'max_tokens': limit, 'temperature': 0.0, 'reasoning_effort': 'low', 'stream': False}
    return request(INSTRUCTION, 16), request(text + '\n\n' + INSTRUCTION, max_tokens)


def rates(records, material_bytes):
    """The first engine record is the baseline; every later one is a segment of the material request.

    Strata splits a long reply into segments that each log a record (the later ones reuse the cached prompt),
    so P and G sum over all material segments."""
    if len(records) < 2:
        raise ValueError('Probe needs the baseline and the material engine records')
    baseline, segments = records[0], records[1:]
    material_tokens = segments[0]['input'] - baseline['input']
    read, prompt_ms = sum(r['uncached'] for r in segments), sum(r['prompt_ms'] for r in segments)
    output, decode_ms = sum(r['output'] for r in segments), sum(r['decode_ms'] for r in segments)
    if material_tokens <= 0 or prompt_ms <= 0 or decode_ms <= 0 or output <= 0:
        raise ValueError('Probe engine record cannot give rates')
    return {'material_bytes': material_bytes, 'material_tokens': material_tokens,
            'beta_bytes_per_token': material_bytes / material_tokens,
            'P_tokens_per_second': read / (prompt_ms / 1000),
            'G_tokens_per_second': output / (decode_ms / 1000),
            'material_records': segments, 'baseline_record': baseline,
            'source': 'engine log records; P uses uncached read over prompt time, both summed over the material segments'}


def time_limit_seconds(material_bytes, beta, P, G, k):
    return material_bytes * (1 / P + k / G) / beta


def run(host, paths, out, max_tokens=MAX_TOKENS):
    from tools.metrics.prompt_policy import verify_loaded_startup
    from tools.reviewer.arw_measure import stop_and_capture_engine_log
    out = Path(out); out.mkdir(parents=True, exist_ok=False)
    text, size = material(paths)
    baseline, probe = bodies(text, max_tokens)
    owner = host.controller(out / 'controller')
    with owner:
        if owner.call('/model/status')['status'] != 'stopped':
            raise RuntimeError('Model was not stopped')
        offset = host.log_offset(MODEL)
        status, load_seconds = owner.start(model=MODEL, engine_overrides={})
        startup = status['native_health']['startup_instructions']
        verify_loaded_startup(startup, STARTUP_SHA256)
        responses = []
        for number, body in enumerate((baseline, probe), 1):
            responses.append(owner.call('/strata/v1/chat/completions', body, timeout=900))
            save(out / f'response-{number}.json', responses[-1])
        stopped, records, _ = stop_and_capture_engine_log(owner, host.installation, MODEL, offset, out, host)
    # API usage only reconciles which records belong to which request; the counts come from the engine log.
    usage = [r.get('usage', {}).get('prompt_tokens') for r in responses]
    if None not in usage and records and (records[0]['input'] != usage[0] or len(records) < 2 or records[1]['input'] != usage[1]):
        raise RuntimeError('Engine records do not line up with the two probe requests')
    result = dict(rates(records, size), files=[str(p) for p in paths], load_seconds=load_seconds,
                  max_context=status['native_health'].get('max_context'), startup_instructions=startup,
                  stop=stopped.get('status'))
    save(out / 'speed-probe.json', result)
    return result


def main():
    from tools.ops.measurement_host import MeasurementHost
    parser = argparse.ArgumentParser(description='Measure P, G and beta on the material before a batch.')
    parser.add_argument('--host', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--max-tokens', type=int, default=MAX_TOKENS)
    parser.add_argument('files', nargs='+')
    args = parser.parse_args()
    result = run(MeasurementHost(args.host), args.files, args.out, args.max_tokens)
    print({k: result[k] for k in ('material_bytes', 'material_tokens', 'beta_bytes_per_token',
                                  'P_tokens_per_second', 'G_tokens_per_second')})


if __name__ == '__main__':
    main()
