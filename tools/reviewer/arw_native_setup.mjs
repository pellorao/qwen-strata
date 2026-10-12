// Bind public model metadata into an isolated Codex home before upstream startup.
import {existsSync,mkdirSync,readFileSync,writeFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';

export async function createIsolatedNativeSessions(info) {
 const upstream=async name=>import(pathToFileURL(resolve(info.repositoryRoot,'lib',name)));
 const {createCodexAppServerSessions}=await upstream('background-agent/codex-app-server.mjs');
 const {createSharedModelCatalog}=await upstream('background-agent/model-catalog.mjs');
 const {backgroundAgentRuntimeDirectory}=await upstream('background-agent/client.mjs');
 const codexHome=resolve(info.installationDirectory,'codex-home');
 mkdirSync(codexHome,{recursive:true,mode:0o700});
 // Codex 0.162 otherwise clones the curated plugin marketplace (~105 MB git checkout) into every fresh home;
 // its instructions never reach the model (plugins_instructions stays false), so only the download goes.
 const config=resolve(codexHome,'config.toml');const features='[features]\nplugins = false\n';
 if(existsSync(config)) {
  if(readFileSync(config,'utf8')!==features)throw Error('Isolated Codex config differs from the bound plugins-off setting.');
 } else writeFileSync(config,features,{flag:'wx',mode:0o600});
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
  // Upstream reads provider configurations only from the custom catalog.
  const custom=resolve(codexHome,'models.custom.json');
  const providers=Buffer.from(JSON.stringify({models:[],providers:catalog.providers??{}})+'\n');
  if(existsSync(custom)) {
   if(!readFileSync(custom).equals(providers))throw Error('Isolated provider catalog differs from its bound source.');
  } else writeFileSync(custom,providers,{flag:'wx',mode:0o600});
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
 return {sessions,modelCatalog};
}
