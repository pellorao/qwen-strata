# 标记项全文

## #28 e163 exec_command：denied/permission in result

```
node - <<'NODE_EOF'
const fs = require('fs');
const {execSync} = require('child_process');
const out = '.tmp/codex/59773751-09d2-4c7d-8189-46ed8c9e2164/_commit-audit-capability/reports/review.jsonl';
const req = JSON.parse(fs.readFileSync('.tmp/codex/59773751-09d2-4c7d-8189-46ed8c9e2164/_commit-audit-capability/request.json', 'utf8'));
const lines = fs.readFileSync(out, 'utf8').split('\n');
if (lines.pop() !== '') throw new Error('file must end with LF');
const rows = lines.map(l => JSON.parse(l));
const problems = [];
const cache = new Map();
const staged = (p) => { if (!cache.has(p)) cache.set(p, execSync('git show ":'+p.replace(/"/g,'\\"'), {encoding:'utf8'}).split('\n')); return cache.get(p); };
const seen = new Map();
rows.forEach((r, i) => {
  const keys = Object.keys(r);
  for (const k of ['source','requirement','result','evidence']) if (!keys.includes(k)) problems.push(`row ${i+1} missing ${k}`);
  for (const k of keys) if (!['source','requirement','result','finding','evidence'].includes(k)) problems.push(`row ${i+1} bad key ${k}`);
  if (!['satisfied','gap','uncertain'].includes(r.result)) problems.push(`row ${i+1} bad result`);
  if (typeof r.requirement !== 'string' || !r.requirement.trim()) problems.push(`row ${i+1} empty requirement`);
  if (!r.source || typeof r.source.filePath !== 'string' || !Number.isInteger(r.source.line) || r.source.line < 1) problems.push(`row ${i+1} bad source`);
  if ((r.result === 'gap' || r.result === 'uncertain') && (typeof r.finding !== 'string' || !r.finding.trim())) problems.push(`row ${i+1} missing finding`);
  if (r.result === 'satisfied' && r.finding !== undefined) problems.push(`row ${i+1} satisfied has finding`);
  if (!Array.isArray(r.evidence) || r.evidence.length === 0) problems.push(`row ${i+1} empty evidence`);
  const filesSeen = new Set();
  r.evidence.forEach((e, j) => {
    const ek = Object.keys(e);
    if (ek.length === 1 && ek[0] === 'command') { if (typeof e.command !== 'string' || !e.command.trim() || !Number.isInteger(e.exitCode)) problems.push(`row ${i+1} bad command evidence`); return; }
    if (ek.length !== 2 || ek[0] !== 'filePath' || ek[1] !== 'lines') problems.push(`row ${i+1} bad evidence keys ${ek}`);
    if (filesSeen.has(e.filePath)) problems.push(`row ${i+1} duplicate file ${e.filePath}`);
    filesSeen.add(e.filePath);
    if (typeof e.filePath !== 'string' || !Array.isArray(e.lines) || e.lines.length === 0) { problems.push(`row ${i+1} bad lines shape`); return; }
    const norm = [];
    e.lines.forEach(item => {
      if (Number.isInteger(item) && item >= 1) norm.push([item, item]);
      else if (Array.isArray(item) && item.length === 2 && item.every(n => Number.isInteger(n) && n >= 1) && item[0] <= item[1]) norm.push(item);
      else problems.push(`row ${i+1} bad line item ${JSON.stringify(item)}`);
    });
    for (let k = 1; k < norm.length; k++) {
      if (norm[k][0] < norm[k-1][0]) problems.push(`row ${i+1} unsorted lines`);
      if (norm[k][0] <= norm[k-1][1] + 1) problems.push(`row ${i+1} overlapping/adjacent ranges not merged`);
    }
    const src = staged(e.filePath);
    norm.forEach(([a,b]) => { if (b > src.length) problems.push(`row ${i+1} ${e.filePath}:${a}-${b} beyond ${src.length} lines`); });
  });
  const key = r.source.filePath + ':' + r.source.line;
  if (seen.has(key)) problems.push(`duplicate source ${key} (rows ${seen.get(key)+1} and ${i+1})`);
  seen.set(key, i);
});
// Gate 1 coverage
let g1expected = 0;
req.gate1.forEach(g => g.requirements.forEach(q => {
  g1expected++;
  const k = q.filePath + ':' + q.line;
  if (!seen.has(k)) problems.push(`missing Gate 1 requirement ${k}`);
}));
// Gate 2 coverage + minimum distinct source lines
const g2 = req.gate2[0];
const g2rows = rows.filter(r => r.source.filePath === g2.documents[0]);
const distinct = new Set(g2rows.map(r => r.source.line));
const body = staged(g2.documents[0]);
let bodyCount = 0, inFence = false;
body.forEach(l => {
  const t = l.trim();
  if (t.startsWith('```')) { inFence = !inFence; return; }
  if (inFence) return;
  if (!t) return;
  if (/^#{1,6}\s/.test(t)) return;
  bodyCount++;
});
const min = Math.ceil(bodyCount / 3);
console.log('total rows', rows.length, 'gate1 expected', g1expected, 'gate1 actual', rows.filter(r=>r.source.filePath.includes('/issues/')).length);
console.log('gate2 rows', g2rows.length, 'distinct source lines', distinct.size, 'body lines', bodyCount, 'minimum', min, distinct.size >= min ? 'OK' : 'FAIL');
const counts = {};
rows.forEach(r => counts[r.result] = (counts[r.result]||0)+1);
console.log('results', JSON.stringify(counts));
console.log('problems:', problems.length ? problems : 'none');
NODE_EOF
```

结果（1017 字）：

```
Chunk ID: 79b79b
Wall time: 0.0000 seconds
Process exited with code 1
Original token count: 229
Output:
/bin/sh: 1: Syntax error: Unterminated quoted string
<ref *1> node:child_process:1017
    throw err;
    ^

Error: spawnSync /bin/sh EPERM
    at Object.spawnSync (node:internal/child_process:1160:20)
    at spawnSync (node:child_process:928:24)
    at execSync (node:child_process:1009:15)
    at staged ([stdin]:10:57)
    at [stdin]:40:17
    at Array.forEach (<anonymous>)
    at [stdin]:23:14
    at Array.forEach (<anonymous>)
    at [stdin]:12:6
    at runScriptInThisContext (node:internal/vm:219:10) {
  errno: -1,
  code: 'EPERM',
  syscall: 'spawnSync /bin/sh',
  path: '/bin/sh',
  spawnargs: [ '-c', 'git show ":src/dispatch/index.mjs' ],
  error: [Circular *1],
  status: 2,
  signal: null,
  output: [
    null,
    '',
    '/bin/sh: 1: Syntax error: Unterminated quoted string\n'
  ],
  pid: 10,
  stdout: '',
  stderr: '/bin/sh: 1: Syntax error: Unterminated quoted string\n'
}

Node.js v24.21.0

```

