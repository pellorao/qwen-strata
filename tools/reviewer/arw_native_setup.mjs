// Bind public model metadata into an isolated Codex home before upstream startup.
import {existsSync,mkdirSync,readFileSync,writeFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';

export async function createIsolatedNativeSessions(info) {
 const upstream=async name=>import(pathToFileURL(resolve(info.repositoryRoot,'lib',name)));
 const {createCodexAppServerSessions}=await upstream('background-agent/codex-app-server.mjs');
 const {backgroundAgentRuntimeDirectory}=await upstream('background-agent/client.mjs');
 const codexHome=resolve(info.installationDirectory,'codex-home');
 mkdirSync(codexHome,{recursive:true,mode:0o700});
 const runtimeDirectory=backgroundAgentRuntimeDirectory(info.installationDirectory);
 mkdirSync(runtimeDirectory,{recursive:true,mode:0o700});
 if(info.catalog) {
  const raw=readFileSync(info.catalog);
  const catalog=JSON.parse(raw);
  if(!Array.isArray(catalog.models))throw Error('Bound catalog has no models array.');
  const cache=resolve(codexHome,'models_cache.json');
  if(existsSync(cache)) {
   if(!readFileSync(cache).equals(raw))throw Error('Isolated model cache differs from its bound source.');
  } else writeFileSync(cache,raw,{flag:'wx',mode:0o600});
  const custom=resolve(codexHome,'models.custom.json');
  if(!existsSync(custom))writeFileSync(custom,JSON.stringify({models:[],providers:{}})+'\n',{flag:'wx',mode:0o600});
 }
 const sessions=createCodexAppServerSessions({
  runtimeDirectory,
  ...(info.codexExecutable ? {codexExecutable:info.codexExecutable} : {}),
  environment:()=>{
   const env={...process.env};
   for(const key of Object.keys(env))if(key.startsWith('CODEX_')||key.startsWith('OPENAI_'))delete env[key];
   env.CODEX_HOME=codexHome;return env;
  },
 });
 return sessions;
}
