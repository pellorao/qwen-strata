"""Lossless manual reading view: full texts once, exact line changes thereafter.

The original JSONL remains authoritative. Every field is traversed and each
text is independently reconstructed and SHA checked. No inspection verdict.
"""
from pathlib import Path
import difflib
import hashlib
import json
import sys
from tools.reviewer.reading_text_deltas import exact_line_changes

import argparse
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--batch-directory', required=True)
parser.add_argument('--name')
parser.add_argument('--record',type=Path)
parser.add_argument('--codex-home',type=Path)
parser.add_argument('--allow-loaded-between-stages',action='store_true',help='Inspect a closed logical stage without unloading the merged instance model.')
parser.add_argument('--live-prefix',action='store_true',help='Render a SHA-bound current native prefix for reading; never establishes final session completeness.')
parser.add_argument('--baselines', nargs='*', default=[], help='Only fully Main-inspected closed native sessions')
parser.add_argument('--no-line-deltas',action='store_true',help='Render full unique texts without difflib or the optional hybrid view; preserves every structural field and text SHA.')
args=parser.parse_args()
BASE=Path(args.batch_directory).resolve()
folder=args.record.resolve().parent if args.record else BASE/args.name
assert folder.is_relative_to(BASE)
if args.record:
 assert args.codex_home
 record=json.loads(args.record.read_text())
 if args.live_prefix:
  assert not args.allow_loaded_between_stages
 elif args.allow_loaded_between_stages:
  assert record.get('finished_at')
  assert record['runtime_result']['taskState']=='ended'and record['runtime_result']['snapshot']['factsComplete']
 else:
  assert record.get('finished_at') and record.get('stop',{}).get('status')=='stopped'
else:
 record = json.loads((folder / 'results.json').read_text())[0]
 assert (folder / 'run-finished.json').exists()
if args.live_prefix:
 assert args.record and (args.no_line_deltas or args.baselines)
 recovery=json.loads(Path(record['accepted']['recoveryPath']).read_text())
 assert recovery['runId']==record['accepted']['runId']
 thread=recovery['threadId']
else:thread = record['runtime_result']['threadId']
home=args.codex_home if args.record else folder / 'arw-installation/codex-home'
source, = (home/'sessions').rglob('*' + thread + '.jsonl')
raw=source.read_bytes()
events = [json.loads(line) for line in raw.splitlines()]
assert events[0]['payload']['id'] == thread
out = folder / (f'main-exact-delta-prefix-{len(raw)}' if args.live_prefix else 'main-exact-delta-render')
if out.exists():
    previous=json.loads((out/'manifest.json').read_text())
    assert previous['session_sha256']==hashlib.sha256(raw).hexdigest()
    assert not previous['manual_inspection_complete']
    generated = [child for child in out.iterdir()
                 if child.name.startswith(('texts-','events-'))
                 or child.name in ('manifest.json','text-bindings.json')]
    # Validate before removing anything, and preserve Main's reading receipts
    # and additional views attached to this exact immutable session prefix.
    assert all(child.is_file() for child in generated)
    for child in generated:
        child.unlink()
else:
    out.mkdir()
values = []
known = {}
recent = {}
blocks = []
bindings = []

def text(value, category):
    if len(value) < 180:
        return value
    sha = hashlib.sha256(value.encode()).hexdigest()
    if sha in known:
        n = known[sha]
        assert values[n - 1] == value
        return {'exact_text_reference': n, 'sha256': sha}
    lines = value.splitlines(keepends=True)
    best = None
    best_size = len(value)
    for n in ([] if args.no_line_deltas else recent.get(category, [])[-18:]):
        prior = values[n - 1].splitlines(keepends=True)
        changes = exact_line_changes(values[n - 1], value)
        if changes is None:
            continue
        size = len(json.dumps(changes, ensure_ascii=False))
        if size < best_size * .75:
            best = (n, changes)
            best_size = size
    values.append(value)
    n = len(values)
    known[sha] = n
    recent.setdefault(category, []).append(n)
    header = f'TEXT {n} category={category} sha256={sha}\n'
    if best is None:
        body = value
        method = 'full'
    else:
        parent, changes = best
        body = f'Exact change from previously rendered TEXT {parent}; all other lines identical.\n'
        for change in changes:
            body += f"Replace old lines {change['old_lines']} with new lines {change['new_lines']}:\n{change['new_text']}\n"
        method = 'verified-line-delta'
    blocks.append(header + body + '\nEND TEXT\n\n')
    bindings.append({'text': n, 'category': category, 'sha256': sha,
                     'characters': len(value), 'render_method': method,
                     'parent': None if best is None else best[0]})
    return {'exact_text_reference': n, 'sha256': sha}

def walk(value, category):
    if isinstance(value, dict):
        answer = {}
        for key, item in value.items():
            if key == 'arguments' and isinstance(item, str):
                try:
                    parsed = json.loads(item)
                except ValueError:
                    answer[key] = text(item, 'arguments')
                else:
                    answer[key] = {'decoded_json': walk(parsed, 'arguments'),
                                   'original_sha256': hashlib.sha256(item.encode()).hexdigest()}
            elif key == 'output' and isinstance(item, str) and 'Output:\n' in item:
                metadata, body = item.split('Output:\n', 1)
                answer[key] = {'exact_metadata': metadata, 'body': text(body, 'tool-text')}
            else:
                child_category = 'tool-text' if key in ('stdout', 'stderr', 'aggregated_output', 'formatted_output') else category
                answer[key] = walk(item, child_category)
        return answer
    if isinstance(value, list):
        return [walk(item, category) for item in value]
    if isinstance(value, str):
        return text(value, category)
    return value

structures = []
for i, event in enumerate(events):
    p = event.get('payload', {})
    if event['type'] in ('token_usage_record',) or p.get('type') == 'token_count':
        structures.append(f'EVENT {i}: numeric diagnostic retained in original JSONL.\n')
        continue
    normalized = walk(event, 'reasoning' if p.get('type') == 'reasoning' else 'event-text')
    structures.append(f'EVENT {i}\n' + json.dumps(normalized, ensure_ascii=False, indent=2) + '\n\n')

def pages(label, parts):
    page = ''
    number = 1
    for part in parts:
        if page and len(page) + len(part) > 18000:
            (out / f'{label}-{number:03}.txt').write_text(page)
            number += 1
            page = ''
        page += part
    if page:
        (out / f'{label}-{number:03}.txt').write_text(page)
    return number

count = pages('texts', blocks)
structure_count = pages('events', structures)
(out / 'text-bindings.json').write_text(json.dumps(bindings, indent=2) + '\n')
(out / 'manifest.json').write_text(json.dumps({
    'status': 'lossless-render-only-main-inspection-pending',
    'instanceId': record['instanceId'], 'threadId': thread,
    'session_path': str(source), 'session_sha256': hashlib.sha256(raw).hexdigest(),
    'prefix_bytes':len(raw), 'live_prefix_only':args.live_prefix,
    'event_count': len(events), 'unique_long_texts': len(values),
    'text_page_count': count, 'event_page_count': structure_count,
    'exact_delta_reconstruction_verified': True,
    'manual_inspection_complete': False,
    **({'session_prefix_bytes':len(raw)} if args.live_prefix else {}),
}, indent=2) + '\n')
print(json.dumps({'text_pages': count, 'event_pages': structure_count,
                  'unique_texts': len(values),
                  'rendered_text_chars': sum(map(len, blocks))}))

if args.no_line_deltas:
    sys.exit(0)


"""Lossless reuse against fully Main-inspected high-2. No inspection verdict."""
from pathlib import Path
import json,hashlib,difflib,sys
B=BASE;F=folder
render_directory=out
for baseline_name in args.baselines:
 assert (B/baseline_name).resolve().is_relative_to(B)
 inspection=json.loads((B/baseline_name/'main-session-inspection/main-inspection.json').read_text())
 assert inspection['full_inspection_complete']
 assert hashlib.sha256(Path(inspection['session_path']).read_bytes()).hexdigest()==inspection['session_sha256']
def native_texts(folder,render_directory=None):
 render_directory=render_directory or folder/'main-exact-delta-render'
 m=json.loads((render_directory/'manifest.json').read_text());s=Path(m['session_path'])
 raw_session=s.read_bytes()
 if m.get('session_prefix_bytes') is not None:raw_session=raw_session[:m['session_prefix_bytes']]
 assert hashlib.sha256(raw_session).hexdigest()==m['session_sha256']
 found={}
 def walk(v):
  if isinstance(v,dict):
   for k,x in v.items():
    if k=='arguments' and isinstance(x,str):
     try:walk(json.loads(x))
     except ValueError:walk(x)
    elif k=='output' and isinstance(x,str) and 'Output:\n' in x:
     walk(x.split('Output:\n',1)[1])
    else:walk(x)
  elif isinstance(v,list):
   for x in v:walk(x)
  elif isinstance(v,str) and len(v)>=180:found[hashlib.sha256(v.encode()).hexdigest()]=v
 for e in [json.loads(l) for l in raw_session.splitlines()]:walk(e)
 binds=json.loads((render_directory/'text-bindings.json').read_text())
 return {r['text']:found[r['sha256']] for r in binds},binds
base_pool=[]
for baseline_name in args.baselines:
 prior, rows=native_texts(B/baseline_name)
 base_pool.extend((baseline_name,old,prior[old['text']]) for old in rows)
actual,ab=native_texts(F,render_directory);own_prior=[]
out=render_directory/'hybrid' if args.live_prefix else F/'main-hybrid-inspection-texts'
assert not out.exists(), 'Preserve an existing manual reading view'
out.mkdir();parts=[];binding=[]
for row in ab:
 n=row['text'];v=actual[n];lines=v.splitlines(keepends=True)
 best=None;bestlen=len(v);bestkind=None
 for baseline_name,old,prior_text in base_pool:
  if old['category']!=row['category']:continue
  exact=exact_line_changes(prior_text,v)
  if exact is None:continue
  try:
   changes=[(*ch['old_lines'],*ch['new_lines'],ch['new_text']) for ch in exact]
  except (KeyError,TypeError):
   continue  # No usable lossless delta: retain the full text.
  cost=sum(len(ch[4])+80 for ch in changes)
  if cost<bestlen*.75:best=(old['text'],changes);bestlen=cost;bestkind=baseline_name
 for old in own_prior:
  if old['category']!=row['category']:continue
  exact=exact_line_changes(actual[old['text']],v)
  if exact is None:continue
  try:
   changes=[(*ch['old_lines'],*ch['new_lines'],ch['new_text']) for ch in exact]
  except (KeyError,TypeError):
   continue  # No usable lossless delta: retain the full text.;cost=sum(len(ch[4])+80 for ch in changes)
  if cost<bestlen*.75:best=(old['text'],changes);bestlen=cost;bestkind='this-session-earlier'
 own_prior.append(row)
 if best is None:body=v;kind='full' 
 else:
  body=f'Base is {bestkind} TEXT {best[0]}; all omitted lines identical.\n'
  if not best[1]:body+='Identical full text; no changes.\n'
  for a,b,c,d,t in best[1]:body+=f'Replace old lines {a}..{b} with new lines {c}..{d}:\n{t}\n'
  kind='verified-cross-instance-line-delta'
 parts.append(f'TEXT {n} sha256={row["sha256"]}\n'+body+'\nEND TEXT\n\n')
 binding.append({'text':n,'sha256':row['sha256'],'kind':kind,'base_text':best[0] if best else None,'base_kind':bestkind})
page='';number=1
for part in parts:
 if page and len(page)+len(part)>14000:(out/f'page-{number:03}.txt').write_text(page);page='';number+=1
 page+=part
if page:(out/f'page-{number:03}.txt').write_text(page)
(out/'bindings.json').write_text(json.dumps(binding,indent=2)+'\n')
print(json.dumps({'status':'lossless-cross-render-only-no-inspection-verdict','pages':number,'characters':sum(map(len,parts))}))

# Preserve every event field in a compact structural view; long texts are bound by exact references.
for src in sorted(render_directory.glob('events-*.txt')):
 import re
 parts=re.split(r'(?m)^EVENT (\d+)(?:\n|:)',src.read_text());dst=[]
 for i in range(1,len(parts),2):
  number=parts[i];body=parts[i+1].strip()
  dst.append('EVENT '+number+' '+(json.dumps(json.loads(body),ensure_ascii=False,separators=(',',':')) if body.startswith('{') else body)+'\n')
 (out/src.name).write_text(''.join(dst))

# An exact field-delta view keeps every value while avoiding repeated event
# envelopes. Text references are interpreted against this render's bindings.
trees=[];chunks=[];latest={}
def field_changes(old,new,path=()):
 if old==new:return []
 if isinstance(old,dict)and isinstance(new,dict)and old.keys()==new.keys():
  return [change for key in new for change in field_changes(old[key],new[key],path+(key,))]
 return [{'path':list(path),'value':new}]
for src in sorted(render_directory.glob('events-*.txt')):
 parts=re.split(r'(?m)^EVENT (\d+)(?:\n|:)',src.read_text())
 for i in range(1,len(parts),2):
  number=int(parts[i]);body_text=parts[i+1].strip()
  if not body_text.startswith('{'):
   chunks.append('EVENT '+str(number)+' '+body_text+'\n');continue
  body=json.loads(body_text)
  kind=(body.get('type'),body.get('payload',{}).get('type'))
  reference=latest.get(kind);value=body
  if reference is not None:
   changes=field_changes(trees[reference][1],body)
   delta={'same_as_event':trees[reference][0],'except':changes}
   if len(json.dumps(delta))<len(json.dumps(body)):value=delta
  chunks.append('EVENT '+str(number)+' '+json.dumps(value,ensure_ascii=False,separators=(',',':'))+'\n')
  trees.append((number,body));latest[kind]=len(trees)-1
page='';number=1
for chunk in chunks:
 if page and len(page)+len(chunk)>14000:
  (out/f'fields-{number:03}.txt').write_text(page);page='';number+=1
 page+=chunk
if page:(out/f'fields-{number:03}.txt').write_text(page)
print(json.dumps({'lossless_field_delta_pages':number,'events':len(trees)}))
