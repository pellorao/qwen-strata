# 标记项全文

## #28 e167 exec_command：denied/permission in result

```
git show :src/dispatch/index.mjs | head -3; echo "exit=$?"
node --input-type=module -e '
const {execFileSync}=await import("node:child_process");
try{const t=execFileSync("git",["show",":src/dispatch/index.mjs"],{encoding:"utf8"});console.log("OK",t.split("\n").length);}catch(e){console.log("ERR",e.message.slice(0,300));}
' 2>&1 | tail -6
```

结果（228 字）：

```
Chunk ID: 0f0c5b
Wall time: 0.0000 seconds
Process exited with code 0
Original token count: 32
Output:
export * from './normalize.mjs';
export * from './queue.mjs';
export * from './capacity.mjs';
exit=0
ERR spawnSync git EPERM

```

