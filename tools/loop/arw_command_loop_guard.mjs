// Reuse only upstream's duplicate-command policy. Ownership and deadlines stay
// with the measurement driver; there is no new detector or verdict here.
import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
const input=JSON.parse(readFileSync(0,'utf8'));
const {createStrataWorkPolicy,initialStrataWorkState}=await import(pathToFileURL(resolve(input.repositoryRoot,'lib/background-agent/strata-work-policy.mjs')));
let state=input.state??initialStrataWorkState(false);
if(state.isolated!==false)throw Error('Measurement guard must not introduce another work budget');
const hints=[];
const policy=createStrataWorkPolicy({readState:()=>state,saveState:value=>{state=value;},
 send:async({kind,instruction})=>{if(kind!=='repeat')throw Error('Unexpected non-loop intervention');hints.push({kind,instruction});},
 continueTask:async()=>{throw Error('Existing driver owns task continuation');},
 stop:async()=>{throw Error('Existing driver owns interruption');},workDuration:()=>null});
await policy.observeCommands(input.facts,input.threadId);policy.close();
// onAccepted is deliberately not simulated. The Python caller persists the
// real send_message receipt and its id after admission, separately from hints.
process.stdout.write(JSON.stringify({state,hints})+'\n');
