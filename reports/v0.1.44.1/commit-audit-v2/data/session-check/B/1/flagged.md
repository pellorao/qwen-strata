# 标记项全文

## #27 e168 exec_command：denied/permission in result

```
node --input-type=module -e "
import {execFileSync} from 'node:child_process';
try { const s=execFileSync('git',['show',':.scratch/0001-dispatch-control/spec.md'],{encoding:'utf8'}); console.log('ok', s.split('\n').length); } catch(e){ console.log('fail', e.message.slice(0,300)); }
" 2>&1 | tail -5
```

结果（127 字）：

```
Chunk ID: ebf1e5
Wall time: 0.0000 seconds
Process exited with code 0
Original token count: 7
Output:
fail spawnSync git EPERM

```

