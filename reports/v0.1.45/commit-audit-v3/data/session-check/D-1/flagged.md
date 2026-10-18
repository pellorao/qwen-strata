# 标记项全文

## #35 e202 exec_command：denied/permission in result

```
node -e "
const cp=require('child_process');
try{ const s=cp.execSync('git show :.scratch/0001-dispatch-control/spec.md',{encoding:'utf8'}); console.log('ok',s.split('\n').length); }catch(e){ console.log('ERR',e.message, e.stderr && e.stderr.toString()); }
" 2>&1
```

结果（131 字）：

```
Chunk ID: 5515e5
Wall time: 0.0000 seconds
Process exited with code 0
Original token count: 8
Output:
ERR spawnSync /bin/sh EPERM 

```

