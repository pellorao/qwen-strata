// Controlled safety diagnostics use upstream native sessions and permission policy.
import {readFileSync,mkdirSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {pathToFileURL} from 'node:url';
import {createInterface} from 'node:readline';
import {createIsolatedNativeSessions} from '../reviewer/arw_native_setup.mjs';
const info=JSON.parse(readFileSync(process.argv[2],'utf8'));
const {reviewerNativeSettings,declineReviewerInteractions}=await import(pathToFileURL(resolve(info.repositoryRoot,'lib/reviewer-runtime/reviewer-native-policy.mjs')));
let native=(await createIsolatedNativeSessions(info)).sessions;let session=null;let root=null;let current=null;
const lines=createInterface({input:process.stdin,crlfDelay:Infinity});
// Approved policy (user 2026-10-07): the report's own dedicated parent directory; without it the exact report file (known bwrap failure).
function writes(c){if(c.reportDirectory===undefined)return [c.report];if(resolve(c.reportDirectory)!==dirname(resolve(c.report)))throw Error('The write grant is the report\'s own parent directory');return [c.reportDirectory];}
// Without a provider the gate runs the served Strata model; an API provider gate names its provider, model and effort.
const provider=info.modelProvider??'qwen_strata';
if(provider==='qwen_strata'?!/^qwen3\.8-flash-next-[a-z0-9_]+$/.test(info.model??''):!/^(benchmark_[a-z]+|openai)$/.test(provider)||!/^[A-Za-z0-9][A-Za-z0-9._:-]*$/.test(info.model??''))throw Error('The gate names the served model');
function settings(c){return reviewerNativeSettings({model:info.model,modelProvider:provider,reasoningEffort:info.reasoningEffort??'high',serviceTier:info.serviceTier??'default',config:c.config},{cwd:c.cwd,readPaths:[],writePaths:writes(c)});}
for await(const line of lines){
 const request=JSON.parse(line);let result;
 try{
  if(request.operation==='start'){
   if(session){await session.stop();session=null;}
   current=request.input;mkdirSync(current.cwd,{recursive:true});
   session=await native.open({settings:settings(current),cwd:current.cwd,readPaths:[],writePaths:writes(current),onNotification:()=>{}});
   root=await session.start({instructions:current.instructions});
   const turn=await session.startTurn({threadId:root.threadId,handoff:current.handoff});result={...root,...turn};
  }else if(request.operation==='snapshot'){
   result=await session.snapshot({rootThreadId:root.threadId});
   if(result.clientRequests.length){await declineReviewerInteractions(session,result.clientRequests);result=await session.snapshot({rootThreadId:root.threadId});}
  }else if(request.operation==='restart'){
   // The new manager is built before the session is stopped and the old one swapped out: a failed build leaves both usable.
   const next=(await createIsolatedNativeSessions(info)).sessions;try{await session.stop();await native.close();}catch(error){await next.close().catch(()=>{});throw error;}native=next;
   session=await native.open({settings:settings(current),cwd:current.cwd,readPaths:[],writePaths:writes(current),onNotification:()=>{}});
   const resumed=await session.resume({threadId:root.threadId,expectedSessionPath:root.sessionPath,instructions:current.instructions});
   if(resumed.threadId!==root.threadId)throw Error('Restart changed original thread');
   const turn=await session.startTurn({threadId:root.threadId,handoff:request.input.handoff});result={...resumed,...turn};
  }else if(request.operation==='interrupt'){
   const snap=await session.snapshot({rootThreadId:root.threadId});const member=snap.members.find(x=>x.threadId===root.threadId);
   result=member?.turnId?await session.interruptGroup({rootThreadId:root.threadId,turnId:member.turnId}):{alreadyIdle:true};
  }else if(request.operation==='close'){
   if(session){await session.stop();session=null;}result=await native.close();
  }else throw Error('Unknown controlled operation');
  console.log(JSON.stringify({id:request.id,ok:true,result}));
 }catch(error){let message=String(error.message);for(const name of ['STRATA_API_KEY',info.envKey]){const secret=name&&process.env[name];if(secret)message=message.replaceAll(secret,'<redacted>');}console.log(JSON.stringify({id:request.id,ok:false,errorType:error.constructor.name,message}));}
}
try{if(session)await session.stop();await native.close();}catch{process.exitCode=1;}
