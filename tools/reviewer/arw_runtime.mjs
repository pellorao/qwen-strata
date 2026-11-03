// Select an isolated location through upstream's dependency interfaces.
// Protocol, measurement and approval code remain upstream. An explicitly
// authorized report-directory permission adapter is applied at native.open.
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {spawnSync} from 'node:child_process';
import {createIsolatedNativeSessions} from './arw_native_setup.mjs';

const operation=process.argv[2];
const configuration=resolve(process.env.QWEN_ARW_RUNTIME_FILE??process.argv[3]);
const info=JSON.parse(readFileSync(configuration,'utf8'));
const upstream=async name=>import(pathToFileURL(resolve(info.repositoryRoot,'lib',name)));
const clientModule=await upstream('background-agent/client.mjs');
if(operation==='daemon') {
 mkdirSync(info.installationDirectory,{recursive:true,mode:0o700});
 const {createBackgroundAgentHost}=await upstream('arw-background-agent-host.mjs');
 const {createBackgroundAgentDaemon}=await upstream('background-agent/daemon.mjs');
 const {sessions:nativeSessions,modelCatalog}=await createIsolatedNativeSessions(info);
 const host=await createBackgroundAgentHost({installationDirectory:info.installationDirectory,
  programDirectory:info.programDirectory??info.repositoryRoot,nativeSessions,modelCatalog});
 const daemon=await createBackgroundAgentDaemon({runtimeDirectory:host.runtimeDirectory,
  dispatch:host.dispatch,list:host.manager.list,prepareMaintenance:host.manager.prepareMaintenance,
  port:0,maintenancePort:0});
 writeFileSync(configuration,JSON.stringify({...info,port:daemon.port,runtimeDirectory:host.runtimeDirectory},null,2)+'\n');
 // The providers upstream's manager actually reads, so the caller can check them before dispatch.
 console.log(JSON.stringify({ready:true,port:daemon.port,providers:await modelCatalog.getProviders()}));
 process.stdin.resume();
 process.stdin.on('end',async()=>{
  const result=await host.manager.prepareMaintenance({stopBackgroundAgents:false,allowIdleEviction:true});
  console.log(JSON.stringify({cleanup:result}));
  if(result.status!=='ready') {process.exitCode=1;return;}
  // Upstream batches state persistence. Its close() flushes the terminal rows;
  // exiting immediately would leave a completed thread persisted as running.
  await host.manager.close();
  await daemon.close();process.exit(0);
 });
} else if(operation==='client') {
 const args=process.argv.slice(3);
 if(args.length===1 && args[0]==='background-agent') {
  const runtime=clientModule.createBackgroundAgentClient({runtimeDirectory:info.runtimeDirectory,
   ownerId:process.env.CODEX_THREAD_ID,port:info.port,messageTimeoutMs:5000,
   caller:{repositoryRoot:process.cwd(),programDirectory:info.programDirectory??info.repositoryRoot}});
  const {runBackgroundAgent}=await upstream('background-agent/machine.mjs');
  process.exitCode=await runBackgroundAgent({runtime});
 } else {
  const result=spawnSync(process.execPath,[resolve(info.repositoryRoot,'arw.mjs'),...args],{stdio:'inherit'});
  if(result.error)throw result.error;
  process.exitCode=result.status??1;
 }
} else throw Error('Unknown upstream transport operation');
