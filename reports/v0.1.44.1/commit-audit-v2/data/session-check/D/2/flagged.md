# 标记项全文

## #30 e175 exec_command：denied/permission in result

```
node - <<'EOF'
const {execSync} = require('child_process');
try { const s = execSync('git show ' + JSON.stringify(':.scratch/0001-dispatch-control/spec.md'), {encoding: 'utf8'}); console.log('ok', s.split('\n').length); }
catch (e) { console.log('ERR', e.message, '|', String(e.stderr || '').slice(0, 300)); }
console.log('cwd', process.cwd());
EOF
```

结果（320 字）：

```
Chunk ID: 76ad0f
Wall time: 0.0000 seconds
Process exited with code 0
Original token count: 55
Output:
ERR spawnSync /bin/sh EPERM | 
cwd /home/pello/projects/qwen_strata/.tmp/commit-audit/measure/q3/runs/D/arw/.tmp/codex/59773751-09d2-4c7d-8189-46ed8c9e2164/_reviewer-cap/runs/59851759-17ec-464b-bbd9-a68550c80f5d/ca/2

```

