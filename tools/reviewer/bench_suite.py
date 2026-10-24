"""The multi-model benchmark suites: per suite its scenario names, frozen scenario plans, blind adjudication briefs,
anchor registry, bench_score work root and scoring version (benchmarks/multi-model-v2/plan.md §9.2: decisions, anchors
and scoring are kept apart per suite, so nothing of v1 is reused for v2 without notice).

code-standards-v5.1 is a scenario of both suites with different briefs, so a scenario name alone never selects a suite;
tools take --suite (default v1, whose values are those every v1 result was produced with)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

SUITES = {
    'v1': {'scenarios': ('commit-audit-v3', 'code-spec-v5', 'code-standards-v5.1', 'spec-readiness-v4.3'),
           'plans': ROOT / 'benchmarks/multi-model-v1/scenarios',
           'briefs': ROOT / 'benchmarks/reviewer-suite-v1',
           'anchors': ROOT / 'benchmarks/multi-model-v1/anchors',
           'score_root': ROOT / '.tmp/bench-score',
           'model_failures': ROOT / 'benchmarks/multi-model-v1/model-failures.json',
           'scoring': 'r8.4'},
    'v2': {'scenarios': ('commit-audit-v3.1', 'code-spec-v5.1', 'code-standards-v5.1', 'spec-readiness-v4.4'),
           'plans': ROOT / 'benchmarks/multi-model-v2/scenarios',
           'briefs': ROOT / 'benchmarks/multi-model-v2/briefs',
           'anchors': ROOT / 'benchmarks/multi-model-v2/anchors',
           'score_root': ROOT / '.tmp/bench-score-v2',
           'model_failures': ROOT / 'benchmarks/multi-model-v2/model-failures.json',
           'scoring': 'r8.5'},
}
DEFAULT = 'v1'


def suite(name):
    if name not in SUITES:
        raise ValueError(f'unknown benchmark suite {name!r}')
    return SUITES[name]


def check_scenario(name, scenario):
    if scenario not in suite(name)['scenarios']:
        raise ValueError(f'{scenario} is not a scenario of suite {name}')
    return scenario


def plan_path(name, scenario):
    return suite(name)['plans'] / f'{check_scenario(name, scenario)}.json'


def brief_path(name, scenario):
    return suite(name)['briefs'] / f'{check_scenario(name, scenario)}-brief.md'


def all_scenarios():
    return sorted({s for value in SUITES.values() for s in value['scenarios']})
