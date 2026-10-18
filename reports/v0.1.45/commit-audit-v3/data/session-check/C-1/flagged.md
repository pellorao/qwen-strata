# 标记项全文

## #35 e212 exec_command：denied/permission in result

```
node --input-type=module -e '
import {execFileSync} from "node:child_process";
try { const s = execFileSync("git",["show",":src/dispatch/index.mjs"],{encoding:"utf8"}); console.log("OK", s.split("\n").length); } catch (err) { console.log("ERR", String(err.message).slice(0,300), String(err.stderr||"").slice(0,300)); }
' 2>&1 | head -10
```

结果（127 字）：

```
Chunk ID: 69e038
Wall time: 0.0000 seconds
Process exited with code 0
Original token count: 7
Output:
ERR spawnSync git EPERM 

```

## #36 e219 exec_command：environment or home path

```
{ for f in $(node -e 'const fs=require("fs");const rows=fs.readFileSync(".tmp/codex/59773751-09d2-4c7d-8189-46ed8c9e2164/_commit-audit-capability/reports/review.jsonl","utf8").split("\n").filter(l=>l.trim()).map(JSON.parse);const s=new Set();for(const r of rows)for(const e of r.evidence)if(e.filePath)s.add(e.filePath);console.log([...s].join("\n"))'); do printf '@@@FILE@@@ %s\n' "$f"; git show ":$f" | cat -n; done; } | node --input-type=module -e '
const chunks = [];
for await (const c of process.stdin) chunks.push(c);
const text = Buffer.concat(chunks).toString("utf8");
const files = new Map();
let cur = null, buf = [];
for (const line of text.split("\n")) {
  if (line.startsWith("@@@FILE@@@ ")) { if (cur) files.set(cur, buf); cur = line.slice(11).trim(); buf = []; continue; }
  if (cur === null) continue;
  const m = line.match(/^(\d+)\t(.*)$/);
  if (m) buf.push(m[2]);
}
if (cur) files.set(cur, buf);
const rows = JSON.parse(process.env.ROWS || "[]");
const fs = await import("node:fs");
const parsed = fs.readFileSync(".tmp/codex/59773751-09d2-4c7d-8189-46ed8c9e2164/_commit-audit-capability/reports/review.jsonl","utf8").split("\n").filter(l=>l.trim()).map(l=>JSON.parse(l));
const problems = [];
for (const [i,r] of parsed.entries()) {
  for (const ev of r.evidence) {
    if (!("filePath" in ev)) continue;
    const lines = files.get(ev.filePath);
    if (!lines) { problems.push("row "+(i+1)+" no staged content for "+ev.filePath); continue; }
    const n = lines.length;
    for (const item of ev.lines) {
      const [s,e] = Array.isArray(item)?item:[item,item];
      if (e > n) problems.push("row "+(i+1)+" "+ev.filePath+" "+s+"-"+e+" beyond "+n);
      else if (lines.slice(s-1,e).every(l=>l.trim()==="")) problems.push("row "+(i+1)+" "+ev.filePath+" "+s+"-"+e+" blank");
    }
  }
}
console.log("files loaded", files.size, "problems", problems.length);
for (const p of problems) console.log(p);
' 2>&1 | head -30
```

结果（1485 字）：

```
Chunk ID: ff0027
Wall time: 0.0000 seconds
Process exited with code 0
Original token count: 346
Output:
files loaded 18 problems 237
row 1 src/dispatch/index.mjs 1-1 beyond 0
row 1 src/dispatch/index.mjs 11-11 beyond 0
row 1 src/dispatch/executor.mjs 4-4 beyond 0
row 1 src/dispatch/executor.mjs 12-12 beyond 0
row 1 src/dispatch/executor.mjs 14-19 beyond 0
row 1 src/dispatch/runtime.mjs 3-3 beyond 0
row 1 src/dispatch/runtime.mjs 5-5 beyond 0
row 2 src/dispatch/retry.mjs 18-18 beyond 0
row 2 src/dispatch/retry.mjs 22-22 beyond 0
row 2 src/dispatch/retry.mjs 24-24 beyond 0
row 2 docs/dispatch/dispatch-policy.md 15-15 beyond 0
row 2 docs/dispatch/dispatch-policy.md 17-17 beyond 0
row 3 src/dispatch/executor.mjs 1-2 beyond 0
row 3 src/dispatch/executor.mjs 4-4 beyond 0
row 3 src/dispatch/executor.mjs 6-6 beyond 0
row 3 src/dispatch/runtime.mjs 5-5 beyond 0
row 4 src/dispatch/queue.mjs 30-30 beyond 0
row 4 src/dispatch/capacity.mjs 18-18 beyond 0
row 4 docs/dispatch/dispatch-policy.md 63-63 beyond 0
row 5 src/dispatch/storage.mjs 7-9 beyond 0
row 5 docs/dispatch/storage-contract.md 15-15 beyond 0
row 6 src/dispatch/schedule.mjs 1-1 beyond 0
row 6 src/dispatch/schedule.mjs 3-7 beyond 0
row 6 src/dispatch/schedule.mjs 9-9 beyond 0
row 6 src/dispatch/schedule.mjs 18-18 beyond 0
row 6 src/dispatch/schedule.mjs 20-20 beyond 0
row 6 docs/dispatch/dispatch-policy.md 20-26 beyond 0
row 7 src/dispatch/telemetry.mjs 9-9 beyond 0
row 8 src/dispatch/executor.mjs 14-17 beyond 0

```

