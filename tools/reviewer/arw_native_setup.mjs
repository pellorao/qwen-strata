// Bind public model metadata into an isolated Codex home before upstream startup.
import {existsSync,linkSync,mkdirSync,readFileSync,unlinkSync,writeFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';

// Write a bound file once, or check the one already there. In a shared CODEX_HOME several runtimes start together:
// the bytes go to a private temporary file first and are hard-linked into place, so a reader never sees a partial file
// and only one writer wins; every other runtime compares.
export function bindFile(path,bytes,message){
 if(!existsSync(path)) {
  const temporary=`${path}.${process.pid}.${Date.now()}.tmp`;
  writeFileSync(temporary,bytes,{flag:'wx',mode:0o600});
  try {linkSync(temporary,path);} catch(error) {if(error.code!=='EEXIST')throw error;}
  finally {unlinkSync(temporary);}
 }
 if(!readFileSync(path).equals(bytes))throw Error(message);
}

export async function createIsolatedNativeSessions(info) {
 const upstream=async name=>import(pathToFileURL(resolve(info.repositoryRoot,'lib',name)));
 const {createCodexAppServerSessions}=await upstream('background-agent/codex-app-server.mjs');
 const {createSharedModelCatalog}=await upstream('background-agent/model-catalog.mjs');
 const {backgroundAgentRuntimeDirectory}=await upstream('background-agent/client.mjs');
 // A shared CODEX_HOME (info.codexHome, user 2026-10-20: parallel OpenAI runs let Codex coordinate its own login refresh)
 // holds only the common parts below; per-configuration settings reach each thread through its open settings.
 const codexHome=info.codexHome?resolve(info.codexHome):resolve(info.installationDirectory,'codex-home');
 mkdirSync(codexHome,{recursive:true,mode:0o700});
 // Codex 0.162 otherwise clones the curated plugin marketplace (~105 MB git checkout) into every fresh home;
 // its instructions never reach the model (plugins_instructions stays false), so only the download goes.
 const config=resolve(codexHome,'config.toml');const features='[features]\nplugins = false\n';
 bindFile(config,Buffer.from(features),'Isolated Codex config differs from the bound plugins-off setting.');
 const runtimeDirectory=backgroundAgentRuntimeDirectory(info.installationDirectory);
 mkdirSync(runtimeDirectory,{recursive:true,mode:0o700});
 if(info.catalog) {
  const raw=readFileSync(info.catalog);
  const catalog=JSON.parse(raw);
  if(!Array.isArray(catalog.models))throw Error('Bound catalog has no models array.');
  const cache=resolve(codexHome,'models_cache.json');
  bindFile(cache,raw,'Isolated model cache differs from its bound source.');
  // Upstream reads provider configurations only from the custom catalog.
  const custom=resolve(codexHome,'models.custom.json');
  const providers=Buffer.from(JSON.stringify({models:[],providers:catalog.providers??{}})+'\n');
  bindFile(custom,providers,'Isolated provider catalog differs from its bound source.');
 }
 // As in upstream's host, one catalog serves the App Server and the manager, which takes its providers from it.
 const modelCatalog=createSharedModelCatalog({runtimeDirectory,environment:()=>({CODEX_HOME:codexHome})});
 const sessions=createCodexAppServerSessions({
  runtimeDirectory,modelCatalog,
  ...(info.codexExecutable ? {codexExecutable:info.codexExecutable} : {}),
  environment:()=>{
   const env={...process.env};
   for(const key of Object.keys(env))if(key.startsWith('CODEX_')||key.startsWith('OPENAI_'))delete env[key];
   env.CODEX_HOME=codexHome;return env;
  },
 });
 if(info.denyRead!==undefined)sessions.open=denyReadOpen(sessions.open.bind(sessions),info.denyRead);
 return {sessions,modelCatalog};
}

// G7 (benchmark plan §3): upstream's Reviewer profile extends :read-only, which can read the user's logins and the
// project's private host file. Every root thread this runtime opens gets those paths as `none` in the profile it
// runs with; upstream code and its persisted settings stay unchanged, so a resumed thread is denied the same way.
export function denyReadSettings(settings,paths){
 if(!Array.isArray(paths)||!paths.length||paths.some(p=>typeof p!=='string'||!p.startsWith('/')))
  throw Error('Deny-read paths must be a non-empty list of absolute paths.');
 const profile=settings.config?.default_permissions;const key=`permissions.${profile}.filesystem`;
 const filesystem=settings.config?.[key];
 if(typeof profile!=='string'||filesystem===null||typeof filesystem!=='object')
  throw Error('Deny-read needs the Reviewer permission profile.');
 const denied={...filesystem};
 for(const path of paths){
  if(path in denied&&denied[path]!=='none')throw Error('A deny-read path is also granted: '+path);
  denied[path]='none';
 }
 return {...settings,config:{...settings.config,[key]:denied}};
}

function denyReadOpen(open,paths){
 denyReadSettings({config:{default_permissions:'check','permissions.check.filesystem':{}}},paths);
 return input=>open({...input,settings:denyReadSettings(input.settings,paths)});
}
