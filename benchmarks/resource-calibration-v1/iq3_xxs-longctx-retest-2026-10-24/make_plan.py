"""One-off: build workload v3 prompts and a conditions-v2 plan for the long-context memory retest.

usage: make_plan.py TAG OUTDIR --lengths 150 [..] --order "150:1,100:2,.." --questions N --knobs JSON [--created ISO] [--scope TEXT]
Writes OUTDIR/plan-TAG.json and .tmp/longctx-retest-1024/prep/workload-TAG.json.
"""
import argparse,hashlib,json,sys
from pathlib import Path
sys.path.insert(0,'benchmarks/resource-calibration-v1');import workload as W
from tools.tuning.window_bank import tokenizer_counter
d=lambda b:hashlib.sha256(b).hexdigest()
canon=lambda v:json.dumps(v,sort_keys=True,separators=(',',':')).encode()
ap=argparse.ArgumentParser();ap.add_argument('tag');ap.add_argument('outdir');ap.add_argument('--order',required=True)
ap.add_argument('--questions',type=int,required=True);ap.add_argument('--batch',type=int,default=8);ap.add_argument('--knobs',default='{}')
ap.add_argument('--created',default='2026-10-24T06:00:00+0900');ap.add_argument('--scope',required=True);ap.add_argument('--seed-base',type=int,default=0)
a=ap.parse_args()
knobs=json.loads(a.knobs);order=[tuple(map(int,x.split(':')))for x in a.order.split(',')]  # (length in K, repetition)
count=tokenizer_counter('rtx3080ti');prep=Path('.tmp/longctx-retest-1024/prep');prep.mkdir(parents=True,exist_ok=True)
def build(length,rep):
    seed=a.seed_base+length*10+rep;n=int(length*1000/45);target=length*1000
    mk=lambda m:W.build(m,3,seed=seed,questions=a.questions,batch=a.batch,**knobs)
    for _ in range(8):  # scale to the neighbourhood
        w=mk(n);tok=count([w['shared_prefix']+w['cases'][0]['question']])[0]
        if abs(tok-target)<=target*0.03:break
        n=max(200,round(n*target/tok))
    best=(abs(tok-target),n,w,tok)
    for m in range(n-24,n+25,2):  # each record count is a different prompt; keep the one closest to the target
        w=mk(m);tok=count([w['shared_prefix']+w['cases'][0]['question']])[0]
        if abs(tok-target)<best[0]:best=(abs(tok-target),m,w,tok)
    return best[2],best[3],seed
workload={'schema_version':3,'repetitions':{}};bindings={};tokens={}
conds=sorted({l for l,_ in order})
for length,rep in order:
    w,tok,seed=build(length,rep);key=f'len{length}k-r{rep}'
    workload['repetitions'][key]={'shared_prefix':w['shared_prefix'],'cases':w['cases'],'record_count':w['record_count'],'seed':seed,'knobs':w['knobs']}
    bindings[key]=[{'id':c['id'],'user_text_sha256':d((w['shared_prefix']+c['question']).encode()),'expected_sha256':d(canon(c['expected'])),
                    'alternatives_sha256':d(canon(c['alternatives']))}for c in w['cases']]
    tokens[key]=[tok,w['record_count'],seed];print(key,tok,w['record_count'],seed,flush=True)
wpath=prep/f'workload-{a.tag}.json';wpath.write_text(json.dumps(workload))
req={"temperature":0.0,"top_p":1.0,"top_k":20,"max_tokens":24576,"reasoning_budget_tokens":8192,"min_p":0.0,
     "presence_penalty":0.0,"frequency_penalty":0.0,"repetition_penalty":1.0,"penalty_last_n":64,"reasoning_effort":"high"}
sources=["tools/tuning/resource_calibration.py","tools/metrics/streamed_chat.py","tools/metrics/host_telemetry.py",
 "tools/metrics/windows_resource_sampler.py","tools/ops/measurement_host.py","tools/metrics/strata_tokens.py",
 "benchmarks/resource-calibration-v1/workload.py","config/prompts/startup-instructions.txt","config/prompts/compact-prompt.txt",
 "config/deployments/rtx3080ti.json","config/templates/iq3_xxs-prebuilt.json","src/model_process.py"]
cond=lambda l:f'len{l}k'
plan={"schema":"conditions-v2","status":"frozen-approved","created_at":a.created,"host":"rtx3080ti","candidate_dimension":"context-length",
 "authorization":{"approved":True,"approved_on":"2026-10-24","scope":a.scope},
 "conditions":[{"id":cond(l),"overrides":{"max-context":206584}}for l in conds],
 "schedule":[{"condition":cond(l),"repetition":r}for l,r in order],
 "model_instances":len(order),"logical_requests":sum(len(v['cases'])for v in workload['repetitions'].values()),
 "repetitions_per_condition":max(r for _,r in order),
 "fixed_conditions":{"strata_version":"0.2.2","strata_commit":"011c9e600a93bbc9fd451c563501b5831c32bbca","engine_version":"0.1.47","model":"IQ3_XXS",
   "base":"部署默认参数（rtx3080ti IQ3_XXS 默认档 206584，kv-resident 20480，--kv int8）；override 只写与默认相同的 max-context 以核对实际窗口",
   "max_context":206584,"user_text_tokens_tokenizer":{k:v[0] for k,v in tokens.items()},"record_counts_and_seeds":{k:v[1:] for k,v in tokens.items()},
   "request":req,"loop_reminder":"off","conversation_cache":"installed default (8192 MiB, 4 slots)",
   "workload_knobs":workload['repetitions'][next(iter(workload['repetitions']))]['knobs']},
 "baseline":{"start_options":{"model":"IQ3_XXS","engine_overrides":{"max-context":206584}},"request_options":{"chat":req}},
 "workload":{"source":"benchmarks/resource-calibration-v1/workload.py","version":3,"questions_per_instance":a.questions,"batch":a.batch,
   "file_sha256":d(wpath.read_bytes()),
   "build":"tools/ 下一次性脚本 make_plan.py（.tmp/longctx-retest-1024/make_plan.py，已随本计划目录提交为 make_plan.py）按 record_count 与 seed 调 workload.build(n,3,seed=...,questions=...,batch=...,**knobs)",
   "case_bindings":bindings},
 "prompt_binding":{"startup_sha256":"1cae169a1b1ebcafbd6b0562992d377c84a550f4cd8bea7184340cf033cd17f6","compact_sha256":"3856cb62b26a0ab3a3b58c4e77d51a68119a0e11c3c44ec6d61d7e5dc59f42af"},
 "telemetry":{"interval_seconds":1},"stream_chat":True,"capture_each_request":True,"record_kv_facts":True,
 "per_logical_request_work_seconds_limit":600,
 "source_sha256":{p:d(Path(p).read_bytes())for p in sources},
 "default_profile_sha256_verified":"8f59b4aa8873209dff11c11e37bcda9529a1335b724a1afeea37bf6388975baf"}
out=Path(a.outdir);out.mkdir(parents=True,exist_ok=True);(out/f'plan-{a.tag}.json').write_text(json.dumps(plan,ensure_ascii=False,indent=1)+'\n')
print('plan',out/f'plan-{a.tag}.json',plan['logical_requests'],'requests')
