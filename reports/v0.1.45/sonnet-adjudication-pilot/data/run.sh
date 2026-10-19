#!/bin/bash
# 临时：Sonnet 盲裁试点的一次无头运行。argv: 池名(s1|s2) 强度 额度标签
# 隔离同 Commit Audit v3 参考运行：--safe-mode --restricted --setting-sources ""，Bash 沙箱，工作目录在工程外，只读隔离目录。
set -u
ROOT=/home/pello/projects/qwen_strata; F=$ROOT/.tmp/score-leftover-1019
POOL=$1; E=$2; LABEL=$3; HARD=3600
ISO=/home/pello/arw-opus/sadj-$POOL-$E; OUTD=$F/runs/$POOL-$E
log() { echo "$(date +%FT%T%:z) $POOL-$E $*" >> $F/progress.md; }
[ -e $ISO ] || [ -e $OUTD ] && { log "目录已存在，停止"; exit 1; }
mkdir -p $ISO $OUTD
cp $F/pool-$POOL.json $ISO/
if [ $POOL = s1 ]; then
  cp -rL $ROOT/.tmp/commit-audit/v3formal/readj/view $ISO/view; [ -f $ISO/view/src/dispatch/retry.mjs ] || { log "view 复制失败"; exit 1; }
  TPL=$ROOT/benchmarks/reviewer-suite-v1/commit-audit-v3-brief.md
else
  TPL=$F/brief-cs51-template.md
fi
python3 - "$TPL" "$ISO" "$POOL" "$ISO/prompt.md" <<'PY'
import sys
from pathlib import Path
tpl, iso, name, out = sys.argv[1:]
t = Path(tpl).read_text()
assert '<ADJ>' in t and '<名>' in t
Path(out).write_text(t.replace('<ADJ>', iso).replace('<名>', name))
PY
echo '{}' > $ISO/decisions-$POOL.json
python3 - "$ISO" "$POOL" "$ISO/settings.json" <<'PY'
import json, sys
from pathlib import Path
iso, name, out = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
keep = {iso / f'decisions-{name}.json'}
deny = [str(p) for p in sorted(iso.iterdir()) if p not in keep] + [out]
s = {"autoMemoryEnabled": False, "includeGitInstructions": False,
     "sandbox": {"enabled": True, "autoAllowBashIfSandboxed": True, "allowUnsandboxedCommands": False,
                 "filesystem": {"denyRead": ["/home", "/mnt", "/tmp", "/etc/claude-code"], "allowRead": [str(iso)],
                                "denyWrite": deny, "allowWrite": [str(iso)]},
                 "network": {"allowedDomains": []}}}
Path(out).write_text(json.dumps(s, indent=1))
PY
BAD=$(find $ISO \( -name 'key*.json' -o -name 'decisions-p*' -o -name 'decisions-r*' -o -name 'expected*.json' -o -name judgment -o -name project.private.toml -o -name .credentials.json -o -name .state \) 2>/dev/null | head)
[ -n "$BAD" ] && { log "隔离违规：$BAD"; exit 1; }
(cd $ISO && find . -type f -print0 | sort -z | xargs -0 sha256sum) > $OUTD/files-before.txt
cp $ISO/prompt.md $ISO/settings.json $OUTD/
cd $ISO
date -u +%FT%TZ > $OUTD/started-utc.txt
log "开始（sonnet $E，池 $(python3 -c "import json;print(len(json.load(open('$ISO/pool-$POOL.json'))))") 项）"
timeout $HARD claude -p --model sonnet --effort $E --safe-mode --restricted --strict-mcp-config --disable-slash-commands \
  --setting-sources "" --settings "$(cat $ISO/settings.json)" \
  --tools Read,Write,Edit,Glob,Grep,Bash --permission-mode dontAsk --permission-prompts none \
  --allowedTools "Read(/$ISO/**),Glob,Grep,Bash,Edit(/$ISO/decisions-$POOL.json),Write(/$ISO/decisions-$POOL.json)" \
  --output-format stream-json --verbose --no-session-persistence < $ISO/prompt.md > $OUTD/stream.jsonl 2> $OUTD/stream.err
rc=$?
date -u +%FT%TZ > $OUTD/ended-utc.txt
cd $ROOT
(cd $ISO && find . -type f -print0 | sort -z | xargs -0 sha256sum) > $OUTD/files-after.txt
diff $OUTD/files-before.txt $OUTD/files-after.txt > $OUTD/files.diff
cp $ISO/decisions-$POOL.json $OUTD/
~/.claude/statusline/estimate.sh --add-stream $OUTD/stream.jsonl "$LABEL" >> $OUTD/add-stream.out 2>&1
log "结束 rc=$rc；files.diff $(grep -c '^[<>]' $OUTD/files.diff) 行"
