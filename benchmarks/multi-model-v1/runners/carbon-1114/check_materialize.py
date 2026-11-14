"""Zero-model check (plan.md §9 step 2): materialize each frozen scenario with the derived plan, stage it as run_one does,
privacy-scan the staged root and prompt, and print the material byte totals (CS 152919, CStd 142529 as v1)."""
import json
import shutil
import sys
from pathlib import Path
sys.path.insert(0, '/home/pello/projects/qwen-strata')
sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_one as r  # noqa: E402
from tools.reviewer import claude_scenario as cs  # noqa: E402
from tools.tuning.arw_dimension import load_plan, prepare  # noqa: E402

BASE = Path('/tmp/carbonbench/check')
shutil.rmtree(BASE, ignore_errors=True)
for key, (scenario, n) in r.SCENARIOS.items():
    plan = load_plan(r.PLANS / f'{scenario}.json')[0]
    prep = BASE / key / 'prep'
    T = 600 if key in ('cs', 'cstd') else None
    prepare(plan, None, prep, time_limit_seconds=T)
    prepared = json.loads((prep / 'preparation.json').read_text())
    note = json.loads((prep / 'selection-source.json').read_text())['measurement_note']
    for k, h in enumerate(prepared['handoffs'][:n]):
        work = BASE / key / f'work-h{k}'
        prompt, st = cs.stage(h, cs.prompt_text(h, note, False), str(work), work)
        r.rewrite_active(work, h, st)
        hits = r.privacy_scan(work, prompt)
        size = lambda parts: sum(f.stat().st_size for p in parts for f in ([work / p] if (work / p).is_file() else sorted((work / p).rglob('*'))) if f.is_file())
        print(key, k, 'prompt bytes', len(prompt.encode()), 'files', sum(1 for _ in work.rglob('*') if _.is_file()),
              'CS material', size(['governing-spec.md', 'src']) if (work / 'src').exists() else '-', 'src', size(['src']) if (work / 'src').exists() else '-',
              'privacy hits', hits[:5], 'report', st['report'], flush=True)
