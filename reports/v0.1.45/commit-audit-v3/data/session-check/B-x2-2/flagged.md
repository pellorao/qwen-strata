# 标记项全文

## #17 e119 exec_command：denied/permission in result

```
cat <<'ARWEOF' | node --input-type=module -
import {readFileSync} from 'node:fs';
import {execFileSync} from 'node:child_process';

const req = JSON.parse(readFileSync('.tmp/codex/59773751-09d2-4c7d-8189-46ed8c9e2164/_commit-audit-capability/request.json', 'utf8'));
const draftPath = '.tmp/codex/59773751-09d2-4c7d-8189-46ed8c9e2164/_commit-audit-capability/reports/review.jsonl';
const lines = readFileSync(draftPath, 'utf8').split('\n');
if (lines.at(-1) !== '') throw new Error('no trailing newline');
const rows = lines.slice(0, -1).map((l, i) => { if (l.trim() === '') throw new Error(`blank line ${i+1}`); return JSON.parse(l); });
const problems = [];

const key = (s) => `${s.filePath}:${s.line}`;
const counts = new Map();
for (const r of rows) counts.set(key(r.source), (counts.get(key(r.source)) ?? 0) + 1);

// Gate 1 coverage
let g1 = 0;
for (const group of req.gate1) for (const r of group.requirements) {
  g1 += 1;
  const k = `${r.filePath}:${r.line}`;
  if (counts.get(k) !== 1) problems.push(`gate1 missing or duplicated: ${k} -> ${counts.get(k)}`);
}
// Gate 2 coverage: every non-empty, non-heading, non-fence body line of each gate2 doc
let g2expected = 0;
for (const g2 of req.gate2) {
  const text = readFileSync(g2.documents[0], 'utf8').split('\n');
  let fence = false;
  const body = [];
  text.forEach((l, i) => {
    const t = l.trim();
    if (t.startsWith('```')) { fence = !fence; return; }
    if (fence) return;
    if (t === '') return;
    if (t.startsWith('#')) return;
    body.push(i + 1);
  });
  g2expected = body.length;
  if (g2expected !== g2.minimumSourceLines[0].count) problems.push(`minimumSourceLines mismatch: doc body ${g2expected} vs request ${g2.minimumSourceLines[0].count}`);
  for (const ln of body) { const k = `${g2.documents[0]}:${ln}`; if (counts.get(k) !== 1) problems.push(`gate2 missing or duplicated: ${k} -> ${counts.get(k)}`); }
  const distinct = new Set(rows.filter(r => r.source.filePath === g2.documents[0]).map(r => r.source.line));
  if (distinct.size < g2.minimumSourceLines[0].count) problems.push(`gate2 distinct source lines ${distinct.size} < ${g2.minimumSourceLines[0].count}`);
  else console.log(`gate2 distinct source lines: ${distinct.size} (min ${g2.minimumSourceLines[0].count})`);
}
if (rows.length !== g1 + g2expected) problems.push(`row count ${rows.length} != gate1 ${g1} + gate2 ${g2expected}`);

// Evidence validation against staged bytes
const staged = new Map();
const stagedText = (p) => {
  if (!staged.has(p)) staged.set(p, execFileSync('git', ['show', `:0:${p}`], {encoding: 'utf8'}).split('\n'));
  return staged.get(p);
};
const tracked = new Set(execFileSync('git', ['diff', '--cached', '--name-only'], {encoding: 'utf8'}).split('\n').filter(Boolean));
for (const [i, r] of rows.entries()) {
  for (const ev of r.evidence) {
    if (!tracked.has(ev.filePath)) problems.push(`row ${i}: evidence file not staged: ${ev.filePath}`);
    const text = stagedText(ev.filePath);
    const n = text.length - (text.at(-1) === '' ? 1 : 0);
    for (const l of ev.lines) {
      const range = Array.isArray(l) ? [l[0], l[1]] : [l, l];
      if (range[1] > n) problems.push(`row ${i}: line ${range[1]} beyond ${ev.filePath} (${n} lines)`);
      for (let x = range[0]; x <= range[1]; x += 1) if ((text[x - 1] ?? '').trim() === '') problems.push(`row ${i}: blank line ${x} in ${ev.filePath}`);
    }
  }
  if (!tracked.has(r.source.filePath) && !readFileSync(r.source.filePath, 'utf8')) problems.push(`row ${i}: source unreadable`);
}

// source line must match staged/worktree content of the requirement line
for (const [i, r] of rows.entries()) {
  const text = readFileSync(r.source.filePath, 'utf8').split('\n');
  const line = text[r.source.line - 1];
  if (!line || line.trim() === '') problems.push(`row ${i}: source line ${r.source.line} empty in ${r.source.filePath}`);
}

const tally = rows.reduce((a, r) => (a[r.result] = (a[r.result] ?? 0) + 1, a), {});
console.log(JSON.stringify({rows: rows.length, tally, gate1: g1, gate2expected}));
console.log(problems.length ? 'PROBLEMS:\n' + problems.join('\n') : 'OK');
ARWEOF
```

结果（2898 字）：

```
Chunk ID: 166c07
Wall time: 0.0000 seconds
Process exited with code 1
Original token count: 699
Output:
gate2 distinct source lines: 57 (min 19)
node:internal/child_process:1160
    result.error = new ErrnoException(result.error, 'spawnSync ' + options.file);
                   ^

<ref *1> Error: spawnSync git EPERM
    at Object.spawnSync (node:internal/child_process:1160:20)
    at spawnSync (node:child_process:928:24)
    at execFileSync (node:child_process:971:15)
    at file:///home/pello/projects/qwen_strata/.tmp/commit-audit/v3formal/q3/runs/B/arw/.tmp/codex/59773751-09d2-4c7d-8189-46ed8c9e2164/_reviewer-cap/runs/a58b90f2-d23f-4948-835d-d96df2a011e6/ca/2/[eval1]:51:25
    at ModuleJob.run (node:internal/modules/esm/module_job:561:25)
    at process.processTicksAndRejections (node:internal/process/task_queues:104:5)
    at async node:internal/modules/esm/loader:223:26
    at async ModuleLoader.executeModuleJob (node:internal/modules/esm/loader:220:20)
    at async asyncRunEntryPointWithESMLoader (node:internal/modules/run_main:101:5) {
  errno: -1,
  code: 'EPERM',
  syscall: 'spawnSync git',
  path: 'git',
  spawnargs: [ 'diff', '--cached', '--name-only' ],
  error: [Circular *1],
  status: 0,
  signal: null,
  output: [
    null,
    '.scratch/0001-dispatch-control/issues/01-assemble-dispatch-plan.md\n' +
      '.scratch/0001-dispatch-control/issues/02-publish-dispatch-manifest.md\n' +
      'src/dispatch/access.mjs\n' +
      'src/dispatch/capacity.mjs\n' +
      'src/dispatch/executor.mjs\n' +
      'src/dispatch/index.mjs\n' +
      'src/dispatch/manifest.mjs\n' +
      'src/dispatch/normalize.mjs\n' +
      'src/dispatch/publisher.mjs\n' +
      'src/dispatch/queue.mjs\n' +
      'src/dispatch/retry.mjs\n' +
      'src/dispatch/runtime.mjs\n' +
      'src/dispatch/schedule.mjs\n' +
      'src/dispatch/serialize.mjs\n' +
      'src/dispatch/storage.mjs\n' +
      'src/dispatch/telemetry.mjs\n' +
      'tests/dispatch/plan.test.mjs\n' +
      'tests/dispatch/publish.test.mjs\n' +
      'tests/dispatch/scenarios.mjs\n',
    ''
  ],
  pid: 11,
  stdout: '.scratch/0001-dispatch-control/issues/01-assemble-dispatch-plan.md\n' +
    '.scratch/0001-dispatch-control/issues/02-publish-dispatch-manifest.md\n' +
    'src/dispatch/access.mjs\n' +
    'src/dispatch/capacity.mjs\n' +
    'src/dispatch/executor.mjs\n' +
    'src/dispatch/index.mjs\n' +
    'src/dispatch/manifest.mjs\n' +
    'src/dispatch/normalize.mjs\n' +
    'src/dispatch/publisher.mjs\n' +
    'src/dispatch/queue.mjs\n' +
    'src/dispatch/retry.mjs\n' +
    'src/dispatch/runtime.mjs\n' +
    'src/dispatch/schedule.mjs\n' +
    'src/dispatch/serialize.mjs\n' +
    'src/dispatch/storage.mjs\n' +
    'src/dispatch/telemetry.mjs\n' +
    'tests/dispatch/plan.test.mjs\n' +
    'tests/dispatch/publish.test.mjs\n' +
    'tests/dispatch/scenarios.mjs\n',
  stderr: ''
}

Node.js v24.21.0

```

