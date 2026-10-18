# 标记项全文

## #17 e122 exec_command：workdir outside root: /home/pello/projects/qwen_strata/.tmp/commit-audit/measure/q3/runs/C/arw/.tmp/codex/59773751-09d2-4c7d-8189-46ed8c9e2164/_reviewer-cap/runs/8dbda33a-8189-46ed8c9e2164/_reviewer-cap/runs/8dbda33a-8057-45a2-92be-0111fad3990d/ca/3; denied/permission in result

```
rg -n "dispatch-policy|allowedRegions|policy\.mjs|runtime\.mjs|executor\.mjs" --glob '!.git' . ; echo "--- exit $? ---"; rg -n "provider" src tests docs config
```

结果（141 字）：

```
exec_command failed: CreateProcess { message: "Rejected(\"Failed to create unified exec process: No such file or directory (os error 2)\")" }
```

