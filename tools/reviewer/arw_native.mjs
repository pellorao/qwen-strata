// Orchestration only: all preparation, generation and scoring remain upstream.
import {readFileSync,writeFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';

const [operation,inputPath,outputPath]=process.argv.slice(2);
const input=JSON.parse(readFileSync(inputPath,'utf8'));
const root=resolve(input.repositoryRoot);
const capability=await import(pathToFileURL(resolve(root,'lib/release/reviewer-capability-conformance.mjs')));
let result;
if(operation==='prepare') {
 result=await capability.prepareReviewerCapabilityConformance({repositoryRoot:root,
  agentIdentity:input.identity,...(input.preparedPath!==undefined
   ? {preparedPath:input.preparedPath,selection:input.selection}
   : {reviewerId:input.reviewerId})});
} else if(operation==='verify' || operation==='verify-diagnostic' || operation==='score-completed') {
 const request={repositoryRoot:root,agentIdentity:input.identity,preparedPath:input.preparedPath,
  input:JSON.parse(readFileSync(input.artifactsPath,'utf8'))};
 for (const [field,path] of Object.entries(input.options??{})) request[field]=JSON.parse(readFileSync(path,'utf8'));
 result=await (operation==='verify'?capability.verifyReviewerCapabilityConformance(request):
  operation==='verify-diagnostic'?capability.verifyReviewerCapabilityConformanceDiagnostic(request):
  capability.scoreReviewerCapabilityCompletedRepetitions(request));
} else if(operation==='commit-audit-generate') {
 const audit=await import(pathToFileURL(resolve(root,'lib/commit-audit/commit-audit.mjs')));
 result=await audit.generateCommitAudit({repositoryRoot:input.scenarioRoot,requestPath:input.requestPath});
} else throw Error('Unknown upstream operation');
writeFileSync(outputPath,JSON.stringify(result,null,2)+'\n');
console.log(JSON.stringify({operation,status:result.status??result.diagnosticResult?.status??'prepared',
 originalFormalStatus:result.originalFormalResult?.status,handoffs:result.handoffs?.length}));
