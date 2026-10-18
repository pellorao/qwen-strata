# 标记项全文

## #4 e31 exec_command：workdir outside root: /home/pello/projects/qwen_strata/.tmp/commit-audit/measure/q3/runs/C/arw/.tmp/codex/59773751-09d2-4c7d-8189-46ed8c9e2164/_reviewer-cap/runs/8dbda33a-8189-46ed8c9e2164/_reviewer-cap/runs/8dbda33a-8057-45a2-92be-0111fad3990d/ca/2; denied/permission in result

```
cat docs/agents/roles/commit-audit-reviewer/gate-2.md
```

结果（141 字）：

```
exec_command failed: CreateProcess { message: "Rejected(\"Failed to create unified exec process: No such file or directory (os error 2)\")" }
```

## #11 e80 exec_command：workdir outside root: /home/pello/projects/qwen_strata/.tmp/commit-audit/measure/q3/runs/C/arw/.tmp/codex/59773751-09d2-4c7d-8189-46ed8c9e2164/_reviewer-cap/runs/8dbda33a-8189-46ed8c9e2164/_reviewer-cap/runs/8dbda33a-8057-45a2-92be-0111fad3990d/ca/2; denied/permission in result

```
git diff --cached -- .scratch/0001-dispatch-control/issues/ | cat
```

结果（141 字）：

```
exec_command failed: CreateProcess { message: "Rejected(\"Failed to create unified exec process: No such file or directory (os error 2)\")" }
```

## #23 e164 exec_command：workdir outside root: /home/pello/projects/qwen_strata/.tmp/commit-audit/measure/q3/runs/C/arw/.tmp/codex/59773751-09d2-4c7d-8189-46ed8c9e2164/_reviewer-cap/runs/8dbda33a-8189-46ed8c9e2164/_reviewer-cap/runs/8dbda33a-8057-45a2-92be-0111fad3990d/ca/2; denied/permission in result

```
node --input-type=module <<'SCRIPT'
import {writeFileSync} from 'node:fs';
const out = "/home/pello/projects/qwen_strata/.tmp/commit-audit/measure/q3/runs/C/arw/.tmp/codex/59773751-09d2-4c7d-8189-46ed8c9e2164/_reviewer-cap/runs/8dbda33a-8057-45a2-92be-0111fad3990d/ca/2/.tmp/codex/59773751-09d2-4c7d-8189-46ed8c9e2164/_commit-audit-capability/reports/review.jsonl";
const I1 = ".scratch/0001-dispatch-control/issues/01-assemble-dispatch-plan.md";
const I2 = ".scratch/0001-dispatch-control/issues/02-publish-dispatch-manifest.md";
const SP = ".scratch/0001-dispatch-control/spec.md";
const mergePairs = (pairs) => {
  const ps = pairs.map(([start, end]) => [start, end]).sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  const merged = [];
  for (const part of ps) {
    const last = merged.at(-1);
    if (last && part[0] <= last[1] + 1) last[1] = Math.max(last[1], part[1]);
    else merged.push(part);
  }
  return merged.map(([start, end]) => (start === end ? start : [start, end]));
};
const F = (filePath, ...pairs) => ({filePath, lines: mergePairs(pairs)});
const C = (command, exitCode) => ({command, exitCode});
const rows = [];
const add = (filePath, line, requirement, result, evidence, finding) => {
  const row = {source: {filePath, line}, requirement, result, evidence};
  if (finding !== undefined) row.finding = finding;
  rows.push(row);
};
const TESTCMD = "node --test tests/dispatch/plan.test.mjs tests/dispatch/publish.test.mjs";

add(I1, 7, "Connect dispatch planning and execution through the public dispatch entry.", "gap",
  [F("src/dispatch/index.mjs", [1, 11]), F("src/dispatch/executor.mjs", [4, 19])],
  "src/dispatch/index.mjs re-exports eleven dispatch modules but not src/dispatch/executor.mjs and not src/dispatch/policy.mjs, so the execution operations named in this issue (executeAuthorizedPlan, executeDryRun, runEligibleStops, emitPlanCreated, planFailure) and the policy operations (loadAllowedRegions, isAllowedRegion, policyVersion, selectRegionPolicy) are unreachable from the public dispatch entry. Importing src/dispatch/index.mjs yields 75 bindings and none of them is an executor or policy operation, so planning and execution are not connected through that entry. Add export * from './executor.mjs' and export * from './policy.mjs' to src/dispatch/index.mjs.");
add(I1, 19, "The capacity boundary test exercises a total exactly equal to the configured limit.", "gap",
  [F("tests/dispatch/scenarios.mjs", [3, 8]), F("tests/dispatch/plan.test.mjs", [5, 7]), C(TESTCMD, 0)],
  "The only capacity test uses packageWeights [4, 5] against vehicleCapacity 10, so the exercised total is 9, one unit below the configured limit; no staged test exercises a total exactly equal to the limit. The boundary case is also the case that src/dispatch/capacity.mjs:3 currently rejects, so exercising the stated boundary would fail as the code stands.");
add(I1, 20, "executeAuthorizedPlan checks authorization before invoking dispatch.", "gap",
  [F("src/dispatch/executor.mjs", [4, 8])],
  "executeAuthorizedPlan calls dispatchRoute(dispatch, route) on line 5 and only then evaluates canPlanRoute on line 6, so dispatch runs for every caller and the forbidden result is returned after dispatch already executed. Running it with an actor whose depotId does not match the route recorded a dispatch call and still returned {ok: false, error: 'forbidden'}. Evaluate canPlanRoute and return before calling dispatchRoute.");
add(I1, 21, "planFailure returns a structured non-throwing failure result.", "satisfied", [F("src/dispatch/executor.mjs", [19, 19])]);
add(I1, 22, "totalPackageWeight sums every package weight without changing the package list.", "satisfied", [F("src/dispatch/capacity.mjs", [1, 1])]);
add(I1, 23, "chooseDeparture evaluates the inclusive dispatch window in UTC.", "gap",
  [F("src/dispatch/schedule.mjs", [1, 6])],
  "departureWindow.hourOf is date.getHours(), which reports the hour in the process local time zone, while the window declares zone 'UTC'. chooseDeparture applies the inclusive startHour..endHour test to that local hour, so the same instant is accepted or rejected depending on the machine time zone instead of UTC. Use date.getUTCHours() for the window test.");
add(I1, 24, "redactNestedDriverToken removes a nested driver token from telemetry.", "satisfied", [F("src/dispatch/telemetry.mjs", [9, 9])]);
add(I1, 28, "emitPlanCreated emits plan.created only after storage succeeds.", "gap",
  [F("src/dispatch/executor.mjs", [14, 17]), F("src/dispatch/storage.mjs", [1, 5])],
  "emitPlanCreated passes an onValidated callback that emits plan.created, and savePlan invokes onValidated?.() on line 4 before await store.write(plan) on the same line, so the event is emitted before the write is attempted and is emitted even when the write later fails. Running emitPlanCreated recorded the order emit:plan.created then write. Emit after store.write resolves.");
add(I1, 29, "hasDuplicateRouteKeys rejects duplicates after route-key normalization.", "gap",
  [F("src/dispatch/queue.mjs", [12, 12]), F("src/dispatch/normalize.mjs", [3, 3])],
  "hasDuplicateRouteKeys builds its set from String(stop.routeKey).trim(), while route-key normalization in this candidate is normalizeRouteKey, which applies NFKC before trimming and uppercasing. Route keys that differ only in letter case or Unicode form are counted as distinct, so duplicates survive the check: stops with routeKey 'a' and 'A' return false. Build the set from normalizeRouteKey(stop.routeKey).");
add(I1, 30, "parseRetryCount accepts only integer counts from 0 through 3 and otherwise returns an error result.", "gap",
  [F("src/dispatch/retry.mjs", [1, 6])],
  "The accepted values are Array.from({length: dispatchRetryBudget}) with dispatchRetryBudget = 3, which is [0, 1, 2], so a count of 3 is rejected although the criterion accepts 0 through 3; parseRetryCount(3) returns {ok: false, value: 3}. The failure shape is {ok: false, value} with no error field, so a rejected value does not produce an error result. Accept 0 through 3 inclusive and return an error field when ok is false.");
add(I1, 31, "remainingVehicleCapacity never returns a negative value.", "satisfied", [F("src/dispatch/capacity.mjs", [12, 12])]);
add(I1, 32, "createDispatchPlan returns an ordered plan without mutating the supplied stop list.", "gap",
  [F("src/dispatch/queue.mjs", [7, 10])],
  "createDispatchPlan copies input.stops by reference into plan.stops on line 8 and then calls plan.stops.sort(compareStops) on line 9, and Array.prototype.sort reorders in place, so the caller's array is reordered. Calling it with [{priority:1,sequence:2},{priority:5,sequence:1}] left the supplied array in the new order. Sort a copy, as orderStops already does.");
add(I1, 33, "previewPlan returns a dry-run result without invoking storage.", "satisfied", [F("src/dispatch/storage.mjs", [15, 15])]);
add(I1, 34, "redactAccessLog removes token and secret fields while preserving other fields.", "satisfied", [F("src/dispatch/access.mjs", [12, 12])]);
add(I1, 38, "loadAllowedRegions obtains the allowed-region list from the configured policy provider.", "satisfied", [F("src/dispatch/policy.mjs", [1, 1])]);
add(I1, 39, "The invalid-storage test asserts that validation failure performs zero writes.", "satisfied",
  [F("tests/dispatch/plan.test.mjs", [9, 14]), F("src/dispatch/storage.mjs", [1, 3]), C(TESTCMD, 0)]);
add(I1, 40, "savePlan validates a plan before the first persistent write.", "satisfied", [F("src/dispatch/storage.mjs", [1, 5])]);
add(I1, 41, "computeBackoff doubles from 250 milliseconds and caps the result at 2000 milliseconds.", "satisfied", [F("src/dispatch/retry.mjs", [8, 8])]);
add(I1, 42, "retryTransient permits retries only for errors explicitly marked transient.", "satisfied", [F("src/dispatch/retry.mjs", [10, 10])]);
add(I1, 43, "restorePlan confirms that a partial-write restore completed successfully.", "uncertain",
  [F("src/dispatch/storage.mjs", [13, 13]), F("docs/dispatch/storage-contract.md", [1, 5])],
  "restorePlan returns adapter.restore(snapshot) unchanged and contains no check of the returned value, so whether the caller receives a confirmation that a partial-write restore completed depends entirely on the storage adapter's restore contract, which the candidate does not define; docs/dispatch/storage-contract.md specifies only store.put semantics. With an adapter whose restore returns undefined, restorePlan returns undefined and no confirmation is available. The adapter contract is needed to decide this criterion.");
add(I1, 47, "retainScheduleOffset preserves the supplied offset exactly.", "satisfied", [F("src/dispatch/schedule.mjs", [10, 10])]);
add(I1, 48, "runEligibleStops skips cancelled stops while retaining the other stop order.", "satisfied", [F("src/dispatch/executor.mjs", [12, 12])]);
add(I1, 49, "withinVehicleCapacity accepts a total equal to the configured limit.", "gap",
  [F("src/dispatch/capacity.mjs", [3, 3])],
  "withinVehicleCapacity returns weight < limit, so a total exactly equal to the limit is rejected; withinVehicleCapacity(10, 10) evaluates to false. Use weight <= limit so a total at the limit is accepted.");
add(I1, 50, "canPlanRoute requires both the routes:plan scope and matching depot ownership.", "gap",
  [F("src/dispatch/access.mjs", [3, 3])],
  "canPlanRoute returns actor.scopes.includes('routes:plan') || actor.depotId === route.depotId, so either condition alone authorizes the route: an actor with the routes:plan scope and a different depot is accepted, and an actor with matching depot and no scope is accepted. The criterion requires both. Combine the scope test and requireDepotOwner(actor, route) with &&.");
add(I1, 51, "serializePlan sorts keys lexically, uses two-space JSON, and ends with one LF.", "gap",
  [F("src/dispatch/serialize.mjs", [2, 3])],
  "serializePlan passes format 'plan' to finishJsonDocument, which appends the newline only when format === 'document', so serializePlan output ends with the closing brace and has no terminal LF; the last characters for a nested plan are '}' 'LF' '}'. Two-space indentation and lexical top-level key order are present. Serialize the plan with the document format so one LF terminates the document.");
add(I1, 52, "selectActiveClaims excludes claims before their start and at or after expiry.", "satisfied", [F("src/dispatch/access.mjs", [1, 1])]);
add(I1, 53, "checksumPlan hashes the bytes returned by the plan serializer.", "satisfied", [F("src/dispatch/serialize.mjs", [7, 7])]);

add(I2, 7, "Connect dispatch manifest publication through the public dispatch entry.", "satisfied", [F("src/dispatch/index.mjs", [9, 11])]);
add(I2, 19, "safeAnnouncement omits a top-level credential from the announcement payload.", "satisfied", [F("src/dispatch/publisher.mjs", [27, 27])]);
add(I2, 20, "encodeUtf8 encodes publication bytes as UTF-8.", "satisfied", [F("src/dispatch/serialize.mjs", [11, 11])]);
add(I2, 21, "manifestEntryIsValid rejects blank package IDs.", "satisfied", [F("src/dispatch/manifest.mjs", [22, 22])]);
add(I2, 22, "publishWithAnnouncement removes the stored manifest when announcement delivery fails.", "gap",
  [F("src/dispatch/publisher.mjs", [10, 15]), F("src/dispatch/manifest.mjs", [30, 30])],
  "publishWithAnnouncement writes the manifest with store.put(manifest, {announce: true}) on line 11 and, when announcer.send throws, calls handleAnnouncementFailure, which destructures only {error, manifest} and returns a failure object; it never uses the store and never removes or compensates the stored manifest. Running it against a store that records put and remove showed only a put, so the manifest stays published after a failed announcement. Remove the stored manifest before returning the failure result.");
add(I2, 23, "redactManifestEvent removes credentials nested below an auth field.", "satisfied", [F("src/dispatch/telemetry.mjs", [7, 9])]);
add(I2, 27, "Given a positive integer maximum, chunkManifest limits every non-empty chunk to that configured maximum.", "satisfied", [F("src/dispatch/manifest.mjs", [15, 20])]);
add(I2, 28, "Under docs/dispatch/storage-contract.md, publishWithAnnouncement waits for the exact manifest to be durably stored before sending its announcement.", "satisfied",
  [F("src/dispatch/publisher.mjs", [10, 13]), F("docs/dispatch/storage-contract.md", [3, 4])]);
add(I2, 29, "serializeManifestRecords emits NDJSON with one LF after every record, including the last.", "gap",
  [F("src/dispatch/serialize.mjs", [9, 9])],
  "serializeManifestRecords joins the per-record JSON strings with a newline, which places a separator between records only, so the final record has no trailing LF; two records produce '{\"a\":1}\\n{\"b\":2}'. Terminate each record, for example records.map(record => JSON.stringify(record) + '\\n').join('').");
add(I2, 30, "orderManifestGroups orders destination groups in ascending lexical order.", "gap",
  [F("src/dispatch/manifest.mjs", [11, 11])],
  "The comparator is right.destination.localeCompare(left.destination), which is the descending direction; groups with destination 'B', 'A', 'C' are returned as C, B, A. Compare left.destination with right.destination to obtain ascending order.");
add(I2, 31, "auditFieldsPresent requires action, actor, and timestamp fields.", "satisfied", [F("src/dispatch/telemetry.mjs", [11, 11])]);
add(I2, 35, "publicationResult returns structured success and failure variants.", "satisfied", [F("src/dispatch/publisher.mjs", [19, 19])]);
add(I2, 36, "normalizedPlanKey trims and uppercases the route-key storage segment.", "satisfied", [F("src/dispatch/storage.mjs", [21, 21])]);
add(I2, 37, "buildManifest copies record objects instead of mutating supplied records.", "satisfied", [F("src/dispatch/manifest.mjs", [26, 26])]);
add(I2, 38, "publicationRetryBudget is two attempts.", "satisfied", [F("src/dispatch/retry.mjs", [20, 20])]);
add(I2, 39, "publishManifest validates every entry before storing the manifest.", "gap",
  [F("src/dispatch/publisher.mjs", [4, 8]), F("src/dispatch/manifest.mjs", [30, 30])],
  "publishManifest awaits stageManifest on line 5, which performs store.put, and only then evaluates manifest.entries.every(manifestEntryIsValid) on line 6, so an invalid manifest is already stored when it is rejected. Publishing a manifest whose only entry has packageId '  ' recorded one store.put and returned {ok: false, error: 'invalid-manifest'}. Validate every entry before staging the manifest.");
add(I2, 43, "successTelemetry records the success event, manifest ID, and timestamp.", "satisfied", [F("src/dispatch/telemetry.mjs", [3, 3])]);
add(I2, 44, "groupByDestination groups records using normalized destination keys.", "satisfied", [F("src/dispatch/manifest.mjs", [3, 9])]);
add(I2, 45, "failureTelemetry records the failure event, error, manifest ID, and timestamp.", "satisfied", [F("src/dispatch/telemetry.mjs", [5, 5])]);
add(I2, 46, "publishWithRetry retries only failures explicitly marked transient.", "gap",
  [F("src/dispatch/publisher.mjs", [17, 17]), F("src/dispatch/retry.mjs", [12, 16])],
  "publishWithRetry delegates to retryPublication, which re-runs the operation for any thrown error and never consults retryTransient, so permanent failures are retried. A store that always threw a plain Error was attempted twice before the error propagated. Retry only when retryTransient(error) is true and rethrow immediately otherwise.");
add(I2, 47, "preserveManifestDriver trims driver labels without changing letter case.", "satisfied",
  [F("src/dispatch/manifest.mjs", [24, 24]), F("src/dispatch/normalize.mjs", [5, 5])]);
add(I2, 48, "coalescePackages removes duplicate package IDs across the complete manifest.", "gap",
  [F("src/dispatch/manifest.mjs", [13, 13]), F("src/dispatch/normalize.mjs", [11, 11])],
  "coalescePackages maps each group independently through normalizePackageIds, so duplicates are removed only inside a single group and an ID that appears in two destination groups is kept in both. Groups [{packageIds: ['P1','P1','P2']}, {packageIds: ['P1','P3']}] keep P1 in both groups. Track already seen package IDs across all groups and drop them from later groups.");

add(SP, 7, "Stop ordering uses descending priority followed by ascending sequence.", "satisfied", [F("src/dispatch/queue.mjs", [3, 3])]);
add(SP, 8, "Publication audit records include action, actor, and timestamp.", "satisfied", [F("src/dispatch/publisher.mjs", [21, 25])]);
add(SP, 9, "Window membership includes both the declared start and end hour.", "satisfied", [F("src/dispatch/schedule.mjs", [8, 8])]);
add(SP, 10, "Schedule offsets pass through without coercion.", "satisfied", [F("src/dispatch/schedule.mjs", [10, 10])]);
add(SP, 11, "Stable JSON sorts keys recursively at every object depth.", "gap",
  [F("src/dispatch/serialize.mjs", [1, 5])],
  "stableTopLevel sorts ownKeys only for the object it wraps, and JSON.stringify applies that proxy only at the top level; nested plain objects are serialized in their own insertion order, so keys are not sorted at every object depth. toStableJson({b: {z: 1, a: 2}, a: 1}) keeps the nested order z then a. Rebuild nested objects with sorted keys before stringifying.");
add(SP, 12, "Manifest-event redaction removes credentials nested inside authentication data.", "satisfied", [F("src/dispatch/telemetry.mjs", [7, 9])]);
add(SP, 13, "Empty manifests use an empty entries array and a generated marker.", "satisfied", [F("src/dispatch/manifest.mjs", [28, 28])]);
add(SP, 14, "Publication failure telemetry includes the manifest ID, error, and timestamp.", "satisfied", [F("src/dispatch/telemetry.mjs", [5, 5])]);
add(SP, 15, "Driver labels are trimmed without changing their letter case.", "satisfied", [F("src/dispatch/normalize.mjs", [5, 5])]);
add(SP, 16, "savePlan completes validation before its first write.", "satisfied", [F("src/dispatch/storage.mjs", [1, 5])]);
add(SP, 17, "Announcement failure rolls back the manifest written earlier in the same operation.", "gap",
  [F("src/dispatch/publisher.mjs", [10, 15]), F("src/dispatch/manifest.mjs", [30, 30])],
  "Same requirement as the reviewed row for .scratch/0001-dispatch-control/issues/02-publish-dispatch-manifest.md:22. publishWithAnnouncement writes the manifest with store.put(manifest, {announce: true}) on line 11 and, when announcer.send throws, calls handleAnnouncementFailure, which destructures only {error, manifest} and returns a failure object; it never uses the store and never removes or compensates the stored manifest. Running it against a store that records put and remove showed only a put, so the manifest stays published after a failed announcement. Remove the stored manifest before returning the failure result.");
add(SP, 21, "Package IDs are trimmed, deduplicated, and sorted lexically.", "satisfied", [F("src/dispatch/normalize.mjs", [11, 11])]);
add(SP, 22, "Package coalescing removes duplicate IDs across destination groups.", "gap",
  [F("src/dispatch/manifest.mjs", [13, 13]), F("src/dispatch/normalize.mjs", [11, 11])],
  "Same requirement as the reviewed row for .scratch/0001-dispatch-control/issues/02-publish-dispatch-manifest.md:48. coalescePackages maps each group independently through normalizePackageIds, so duplicates are removed only inside a single group and an ID that appears in two destination groups is kept in both. Groups [{packageIds: ['P1','P1','P2']}, {packageIds: ['P1','P3']}] keep P1 in both groups. Track already seen package IDs across all groups and drop them from later groups.");
add(SP, 23, "Atomic plan writes remove temporary bytes when the rename operation fails.", "gap",
  [F("src/dispatch/storage.mjs", [7, 11])],
  "writePlanAtomically awaits store.writeTemporary(bytes) and then awaits store.renameTemporary() with no try/catch and no cleanup call, so when the rename rejects the temporary bytes stay in the store and the failure propagates without removing them. Wrap the rename in try/catch and remove the temporary file (for example store.removeTemporary()) before rethrowing.");
add(SP, 24, "Under docs/dispatch/storage-contract.md, publishManifest returns the exact manifest object durably stored by store.put in a success result.", "satisfied",
  [F("src/dispatch/publisher.mjs", [4, 8]), F("src/dispatch/manifest.mjs", [30, 30]), F("docs/dispatch/storage-contract.md", [3, 4])]);
add(SP, 25, "Eligible-stop execution excludes cancelled stops.", "satisfied", [F("src/dispatch/executor.mjs", [12, 12])]);
add(SP, 26, "Assigning all packages accepts a total equal to the vehicle limit.", "gap",
  [F("src/dispatch/capacity.mjs", [3, 3], [14, 14])],
  "Same requirement as the reviewed row for .scratch/0001-dispatch-control/issues/01-assemble-dispatch-plan.md:49. canAssignAllPackages delegates to withinVehicleCapacity, which returns weight < limit, so a total exactly equal to the vehicle limit is rejected; canAssignAllPackages([{weight:5},{weight:5}], 10) evaluates to false. Use weight <= limit.");
add(SP, 27, "The public dispatch entry exports the execution operations used by callers.", "gap",
  [F("src/dispatch/index.mjs", [1, 11]), F("src/dispatch/executor.mjs", [4, 19])],
  "Same requirement as the reviewed row for .scratch/0001-dispatch-control/issues/01-assemble-dispatch-plan.md:7. src/dispatch/index.mjs re-exports eleven dispatch modules but not src/dispatch/executor.mjs and not src/dispatch/policy.mjs, so the execution operations (executeAuthorizedPlan, executeDryRun, runEligibleStops, emitPlanCreated, planFailure) and the policy operations (loadAllowedRegions, isAllowedRegion, policyVersion, selectRegionPolicy) are unreachable from the public dispatch entry. Importing src/dispatch/index.mjs yields 75 bindings and none of them is an executor or policy operation. Add export * from './executor.mjs' and export * from './policy.mjs'.");
add(SP, 28, "Publication success telemetry includes the manifest ID and timestamp.", "satisfied", [F("src/dispatch/telemetry.mjs", [3, 3])]);
add(SP, 29, "Plan previews return without touching persistent storage.", "satisfied", [F("src/dispatch/storage.mjs", [15, 15])]);
add(SP, 30, "Appending a stable stop returns a new list.", "satisfied", [F("src/dispatch/queue.mjs", [27, 27])]);
add(SP, 31, "Dispatch backoff is capped at 2000 milliseconds.", "satisfied", [F("src/dispatch/retry.mjs", [8, 8])]);
add(SP, 35, "Frozen dispatch plans also freeze a copied stop list.", "satisfied", [F("src/dispatch/queue.mjs", [25, 25])]);
add(SP, 36, "Transient retry classification requires an explicit true marker.", "satisfied", [F("src/dispatch/retry.mjs", [10, 10])]);
add(SP, 37, "Depot ownership requires equal actor and route depot identifiers.", "satisfied", [F("src/dispatch/access.mjs", [14, 14])]);
add(SP, 38, "Urgent-stop partitioning leaves the supplied stop list unchanged.", "gap",
  [F("src/dispatch/queue.mjs", [14, 23])],
  "partitionUrgentStops builds remaining with filter and then calls updateStopBuffer(stops, remaining), whose target.splice(0, target.length, ...values) rewrites the caller's array in place, so the supplied stop list is changed. Calling it with two stops left the supplied array with one element. Return the filtered remaining list without rewriting the input array.");
add(SP, 39, "Destination keys are normalized with NFKC, trimmed, and uppercased.", "satisfied", [F("src/dispatch/normalize.mjs", [9, 9])]);
add(SP, 40, "The next dispatch time is not earlier than either supplied bound.", "satisfied", [F("src/dispatch/schedule.mjs", [12, 12])]);
add(SP, 41, "Plan-created telemetry is emitted only after plan storage succeeds.", "gap",
  [F("src/dispatch/executor.mjs", [14, 17]), F("src/dispatch/storage.mjs", [1, 5])],
  "Same requirement as the reviewed row for .scratch/0001-dispatch-control/issues/01-assemble-dispatch-plan.md:28. emitPlanCreated passes an onValidated callback that emits plan.created, and savePlan invokes onValidated?.() on line 4 before await store.write(plan) on the same line, so the event is emitted before the write is attempted and is emitted even when the write later fails. Running emitPlanCreated recorded the order emit:plan.created then write. Emit after store.write resolves.");
add(SP, 42, "Access-log redaction removes both token and secret fields.", "satisfied", [F("src/dispatch/access.mjs", [12, 12])]);
add(SP, 43, "Package weight totals include every supplied package.", "satisfied", [F("src/dispatch/capacity.mjs", [1, 1])]);
add(SP, 44, "toStableJson uses two-space indentation and one terminal LF.", "satisfied", [F("src/dispatch/serialize.mjs", [2, 5])]);
add(SP, 45, "Manifest destination groups are ordered in ascending lexical order.", "gap",
  [F("src/dispatch/manifest.mjs", [11, 11])],
  "Same requirement as the reviewed row for .scratch/0001-dispatch-control/issues/02-publish-dispatch-manifest.md:30. The comparator is right.destination.localeCompare(left.destination), which is the descending direction; groups with destination 'B', 'A', 'C' are returned as C, B, A. Compare left.destination with right.destination to obtain ascending order.");
add(SP, 46, "Manifest NDJSON ends every record, including the final record, with LF.", "gap",
  [F("src/dispatch/serialize.mjs", [9, 9])],
  "Same requirement as the reviewed row for .scratch/0001-dispatch-control/issues/02-publish-dispatch-manifest.md:29. serializeManifestRecords joins the per-record JSON strings with a newline, which places a separator between records only, so the final record has no trailing LF; two records produce '{\"a\":1}\\n{\"b\":2}'. Terminate each record with its own LF.");
add(SP, 50, "The publication integration test invokes publishManifest through the binding imported from the public dispatch entry.", "gap",
  [F("tests/dispatch/publish.test.mjs", [3, 9]), C(TESTCMD, 0)],
  "publish.test.mjs imports publishManifest from src/dispatch/index.mjs as publicPublishManifest on line 3 and never uses it; line 8 rebinds the local publishManifest to the publishManifest imported from src/dispatch/publisher.mjs on line 4, and line 9 invokes that internal binding, so the integration test exercises the module path rather than the binding imported from the public dispatch entry. Invoke publicPublishManifest in the test.");
add(SP, 51, "Destination grouping uses normalized keys and copied records.", "satisfied", [F("src/dispatch/manifest.mjs", [3, 9])]);
add(SP, 52, "Batch authorization checks depot ownership for every route in the batch.", "gap",
  [F("src/dispatch/access.mjs", [7, 10])],
  "authorizeRouteBatch maps requireDepotOwner over all routes but then returns ownership.length === 0 || ownership[0], which inspects only the first result, so a batch whose first route is owned and a later route is not owned is accepted. authorizeRouteBatch with actor depotId 'D1' and routes [{depotId:'D1'},{depotId:'D2'}] returned true. Return ownership.every(Boolean).");
add(SP, 53, "Plan restoration reports whether the storage adapter restored the requested snapshot.", "uncertain",
  [F("src/dispatch/storage.mjs", [13, 13]), F("docs/dispatch/storage-contract.md", [1, 5])],
  "Same requirement as the reviewed row for .scratch/0001-dispatch-control/issues/01-assemble-dispatch-plan.md:43. restorePlan returns adapter.restore(snapshot) unchanged and contains no check of the returned value, so whether the caller receives a report about the requested snapshot depends entirely on the storage adapter's restore contract, which the candidate does not define; docs/dispatch/storage-contract.md specifies only store.put semantics. With an adapter whose restore returns undefined, restorePlan returns undefined and no report is available. The adapter contract is needed to decide this requirement.");
add(SP, 54, "Blackout intervals include the start and exclude the end.", "satisfied", [F("src/dispatch/schedule.mjs", [14, 14])]);
add(SP, 55, "Authorized execution rejects a caller before invoking dispatch.", "gap",
  [F("src/dispatch/executor.mjs", [4, 8])],
  "Same requirement as the reviewed row for .scratch/0001-dispatch-control/issues/01-assemble-dispatch-plan.md:20. executeAuthorizedPlan calls dispatchRoute(dispatch, route) on line 5 and only then evaluates canPlanRoute on line 6, so dispatch runs for every caller and the forbidden result is returned after dispatch already executed. Running it with an actor whose depotId does not match the route recorded a dispatch call and still returned {ok: false, error: 'forbidden'}. Evaluate canPlanRoute and return before calling dispatchRoute.");
add(SP, 56, "Successful publication results and failed publication results use distinct structured variants.", "satisfied", [F("src/dispatch/publisher.mjs", [19, 19])]);
add(SP, 57, "Blank package IDs make a manifest entry invalid.", "satisfied", [F("src/dispatch/manifest.mjs", [22, 22])]);
add(SP, 58, "An explicit vehicle capacity of zero is preserved instead of replaced by a default.", "satisfied", [F("src/dispatch/capacity.mjs", [5, 5])]);
add(SP, 59, "Retry-count parsing accepts integers from 0 through 3 and rejects fractions and integers outside that range.", "gap",
  [F("src/dispatch/retry.mjs", [1, 6])],
  "Same requirement as the reviewed row for .scratch/0001-dispatch-control/issues/01-assemble-dispatch-plan.md:30. The accepted values are Array.from({length: dispatchRetryBudget}) with dispatchRetryBudget = 3, which is [0, 1, 2], so a count of 3 is rejected although the range is 0 through 3; parseRetryCount(3) returns {ok: false, value: 3}. Fractions and out-of-range integers are rejected as required. Accept 0 through 3 inclusive.");
add(SP, 60, "Serialized plan parsing returns structured success or failure.", "satisfied", [F("src/dispatch/serialize.mjs", [13, 15])]);
add(SP, 61, "Depot aliases are trimmed and lowercased.", "satisfied", [F("src/dispatch/normalize.mjs", [7, 7])]);
add(SP, 65, "The ordinary stop-ordering operation sorts a copy of its input.", "satisfied", [F("src/dispatch/queue.mjs", [5, 5])]);
add(SP, 66, "Stops at the vehicle weight limit remain in the accepted partition.", "satisfied", [F("src/dispatch/capacity.mjs", [7, 10])]);
add(SP, 67, "Given a positive integer maximum, manifest chunks never exceed that configured size.", "satisfied", [F("src/dispatch/manifest.mjs", [15, 20])]);
add(SP, 68, "normalizeRouteKey applies NFKC before trimming and uppercasing.", "satisfied", [F("src/dispatch/normalize.mjs", [3, 3])]);
add(SP, 69, "Normalized plan storage keys trim and uppercase route keys.", "satisfied", [F("src/dispatch/storage.mjs", [21, 21])]);
add(SP, 70, "The declared departure window records UTC as its time zone.", "satisfied", [F("src/dispatch/schedule.mjs", [1, 1])]);
add(SP, 71, "Publication retries stop immediately for errors not marked transient.", "gap",
  [F("src/dispatch/publisher.mjs", [17, 17]), F("src/dispatch/retry.mjs", [12, 16])],
  "Same requirement as the reviewed row for .scratch/0001-dispatch-control/issues/02-publish-dispatch-manifest.md:46. publishWithRetry delegates to retryPublication, which re-runs the operation for any thrown error and never consults retryTransient, so a failure with no transient marker is retried. A store that always threw a plain Error was attempted twice before the error propagated. Retry only when retryTransient(error) is true and rethrow immediately otherwise.");
add(SP, 72, "UTF-8 encoding uses the explicit utf8 encoding name.", "satisfied", [F("src/dispatch/serialize.mjs", [11, 11])]);
add(SP, 73, "Planning scope matching accepts only the exact routes:plan scope.", "gap",
  [F("src/dispatch/access.mjs", [5, 5])],
  "scopeAllowsPlan returns scope.startsWith('routes:plan'), so any scope that begins with the planning scope is accepted; scopeAllowsPlan('routes:planning') returned true. Compare with the exact value, scope === 'routes:plan'.");
add(SP, 74, "Route tokens combine the normalized destination and the normalized route key.", "gap",
  [F("src/dispatch/normalize.mjs", [3, 3], [13, 13])],
  "formatRouteToken normalizes the destination with normalizeDestination but builds the route-key part with asText(routeKey).trim().toUpperCase() instead of normalizeRouteKey(routeKey), so the NFKC step of route-key normalization is skipped and the two parts of the token are normalized by different rules. A route key whose composed form differs from its decomposed form produces a token that does not match the normalized route key. Use normalizeRouteKey(routeKey) for the second part.");
add(SP, 75, "Server-provided retry delays are capped at 2000 milliseconds.", "gap",
  [F("src/dispatch/retry.mjs", [18, 18])],
  "retryAfterDelay returns Math.max(serverDelay, 2000), which raises any smaller delay to 2000 and lets a larger server-provided delay pass through unchanged, so the delay is floored rather than capped; retryAfterDelay(5000) returns 5000 while computeBackoff on line 8 caps with Math.min(2000, ...). Use Math.min(2000, serverDelay).");

writeFileSync(out, rows.map(r => JSON.stringify(r)).join('\n') + '\n');
console.log('rows', rows.length);
SCRIPT
```

结果（141 字）：

```
exec_command failed: CreateProcess { message: "Rejected(\"Failed to create unified exec process: No such file or directory (os error 2)\")" }
```

## #25 e178 exec_command：.. escapes root: ..; denied/permission in result

```
node --input-type=module <<'SCRIPT'
import {readFileSync, writeFileSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
const root = "/home/pello/projects/qwen_strata/.tmp/commit-audit/measure/q3/runs/C/arw/.tmp/codex/59773751-09d2-4c7d-8189-46ed8c9e2164/_reviewer-cap/runs/8dbda33a-8057-45a2-92be-0111fad3990d/ca/2";
const out = root + "/.tmp/codex/59773751-09d2-4c7d-8189-46ed8c9e2164/_commit-audit-capability/reports/review.jsonl";
const req = JSON.parse(readFileSync(root + "/.tmp/codex/59773751-09d2-4c7d-8189-46ed8c9e2164/_commit-audit-capability/request.json", 'utf8'));
const rows = readFileSync(out, 'utf8').split('\n').filter(l => l !== '').map(l => JSON.parse(l));
const problems = [];
const staged = new Map();
const stagedLines = (p) => {
  if (!staged.has(p)) staged.set(p, execFileSync('git', ['show', ':' + p], {cwd: root}).toString('utf8').split('\n'));
  return staged.get(p);
};
const want = [];
for (const g of req.gate1) for (const r of g.requirements) want.push(r.filePath + ':' + r.line);
for (const g of req.gate2) for (const d of g.documents) { /* whole-document scope handled below */ }
const have = rows.map(r => r.source.filePath + ':' + r.source.line);
const missing = want.filter(k => !have.includes(k));
const extraGate1 = have.filter(k => want.includes(k) === false && !k.startsWith(req.gate2[0].documents[0] + ':'));
if (missing.length) problems.push('missing gate1 rows: ' + missing.join(','));
const dup = have.filter((k, i) => have.indexOf(k) !== i);
if (dup.length) problems.push('duplicate rows: ' + dup.join(','));
const gate2Doc = req.gate2[0].documents[0];
const gate2Rows = rows.filter(r => r.source.filePath === gate2Doc);
const specLines = stagedLines(gate2Doc);
const bodyLines = [];
let inFence = false;
specLines.forEach((text, i) => {
  const t = text.trim();
  if (t.startsWith('```')) { inFence = !inFence; return; }
  if (inFence) return;
  if (t === '') return;
  if (t.startsWith('#')) return;
  bodyLines.push(i + 1);
});
const minNeeded = req.gate2[0].minimumSourceLines.find(m => m.filePath === gate2Doc).count;
const distinct = new Set(gate2Rows.map(r => r.source.line));
if (distinct.size < minNeeded) problems.push('gate2 distinct source lines ' + distinct.size + ' < ' + minNeeded);
for (const line of distinct) if (!bodyLines.includes(line)) problems.push('gate2 source line not a body line: ' + line);
console.log('spec body lines', bodyLines.length, 'gate2 rows', gate2Rows.length, 'distinct', distinct.size, 'min', minNeeded);
for (const row of rows) {
  const keys = Object.keys(row);
  for (const k of keys) if (!['source', 'requirement', 'result', 'evidence', 'finding'].includes(k)) problems.push('bad key ' + k);
  if (keys.filter(k => k === 'finding').length !== (row.result === 'satisfied' ? 0 : 1)) problems.push('finding shape ' + row.source.filePath + ':' + row.source.line);
  if (!['satisfied', 'gap', 'uncertain'].includes(row.result)) problems.push('bad result');
  if (typeof row.requirement !== 'string' || row.requirement.length === 0) problems.push('bad requirement');
  if (!Number.isInteger(row.source.line) || row.source.line < 1) problems.push('bad source line');
  if (row.source.filePath.startsWith('/') || row.source.filePath.startsWith('..')) problems.push('source not repo-relative');
  if (!Array.isArray(row.evidence) || row.evidence.length === 0) problems.push('empty evidence');
  const files = new Map();
  for (const item of row.evidence) {
    if ('command' in item) {
      if (typeof item.command !== 'string' || item.command.length === 0) problems.push('bad command');
      if (!Number.isInteger(item.exitCode)) problems.push('bad exitCode');
      continue;
    }
    if ('lines' in item) {
      if (typeof item.filePath !== 'string' || item.filePath.startsWith('/')) problems.push('bad filePath ' + item.filePath);
      files.set(item.filePath, (files.get(item.filePath) ?? 0) + 1);
      if (!Array.isArray(item.lines) || item.lines.length === 0) { problems.push('bad lines ' + item.filePath); continue; }
      let prevEnd = 0;
      const text = stagedLines(item.filePath);
      for (const entry of item.lines) {
        const pair = Array.isArray(entry) ? entry : [entry, entry];
        if (pair.length !== 2 || !pair.every(v => Number.isInteger(v) && v >= 1)) problems.push('bad line entry ' + item.filePath);
        else {
          if (pair[1] < pair[0]) problems.push('reversed range ' + item.filePath + ' ' + pair.join('-'));
          if (pair[0] <= prevEnd + 1) problems.push('unmerged/unordered ' + item.filePath + ' ' + pair.join('-'));
          prevEnd = pair[1];
          const total = text.length && text.at(-1) === '' ? text.length - 1 : text.length;
          if (pair[1] > total) problems.push('range beyond file ' + item.filePath + ' ' + pair[1] + '>' + total);
          for (let ln = pair[0]; ln <= pair[1]; ln += 1) if ((text[ln - 1] ?? '').trim() === '') problems.push('empty cited line ' + item.filePath + ':' + ln);
        }
      }
    } else problems.push('unknown evidence shape');
  }
  for (const [f, count] of files) if (count > 1) problems.push('duplicate file object ' + f + ' @' + row.source.filePath + ':' + row.source.line);
}
console.log('rows', rows.length, 'gate1 rows', rows.length - gate2Rows.length);
console.log('results', rows.reduce((a, r) => (a[r.result] = (a[r.result] ?? 0) + 1, a), {}));
console.log('problems', problems.length ? problems : 'none');
SCRIPT
```

结果（2780 字）：

```
Chunk ID: 9f6d4e
Wall time: 0.0000 seconds
Process exited with code 1
Original token count: 669
Output:
node:internal/child_process:1160
    result.error = new ErrnoException(result.error, 'spawnSync ' + options.file);
                   ^

<ref *1> Error: spawnSync git EPERM
    at Object.spawnSync (node:internal/child_process:1160:20)
    at spawnSync (node:child_process:928:24)
    at execFileSync (node:child_process:971:15)
    at stagedLines (file:///home/pello/projects/qwen_strata/.tmp/commit-audit/measure/q3/runs/C/arw/.tmp/codex/59773751-09d2-4c7d-8189-46ed8c9e2164/_reviewer-cap/runs/8dbda33a-8057-45a2-92be-0111fad3990d/ca/2/[eval1]:10:37)
    at file:///home/pello/projects/qwen_strata/.tmp/commit-audit/measure/q3/runs/C/arw/.tmp/codex/59773751-09d2-4c7d-8189-46ed8c9e2164/_reviewer-cap/runs/8dbda33a-8057-45a2-92be-0111fad3990d/ca/2/[eval1]:24:19
    at ModuleJob.run (node:internal/modules/esm/module_job:561:25)
    at process.processTicksAndRejections (node:internal/process/task_queues:104:5)
    at async node:internal/modules/esm/loader:223:26
    at async ModuleLoader.executeModuleJob (node:internal/modules/esm/loader:220:20)
    at async asyncRunEntryPointWithESMLoader (node:internal/modules/run_main:101:5) {
  errno: -1,
  code: 'EPERM',
  syscall: 'spawnSync git',
  path: 'git',
  spawnargs: [ 'show', ':.scratch/0001-dispatch-control/spec.md' ],
  error: [Circular *1],
  status: 0,
  signal: null,
  output: [
    null,
    Buffer(4185) [Uint8Array] [
       35,  32,  68, 105, 115, 112,  97, 116,  99, 104,  32,  67,
      111, 110, 116, 114, 111, 108,  32,  82, 117, 108, 101, 115,
       10,  10,  35,  35,  32,  82, 101, 113, 117, 105, 114, 101,
      109, 101, 110, 116, 115,  10,  10,  35,  35,  35,  32,  73,
      100, 101, 110, 116, 105, 116, 121,  32,  97, 110, 100,  32,
      111, 114, 100, 101, 114, 105, 110, 103,  10,  10,  45,  32,
       83, 116, 111, 112,  32, 111, 114, 100, 101, 114, 105, 110,
      103,  32, 117, 115, 101, 115,  32, 100, 101, 115,  99, 101,
      110, 100, 105, 110,
      ... 4085 more items
    ],
    Buffer(0) [Uint8Array] []
  ],
  pid: 10,
  stdout: Buffer(4185) [Uint8Array] [
     35,  32,  68, 105, 115, 112,  97, 116,  99, 104,  32,  67,
    111, 110, 116, 114, 111, 108,  32,  82, 117, 108, 101, 115,
     10,  10,  35,  35,  32,  82, 101, 113, 117, 105, 114, 101,
    109, 101, 110, 116, 115,  10,  10,  35,  35,  35,  32,  73,
    100, 101, 110, 116, 105, 116, 121,  32,  97, 110, 100,  32,
    111, 114, 100, 101, 114, 105, 110, 103,  10,  10,  45,  32,
     83, 116, 111, 112,  32, 111, 114, 100, 101, 114, 105, 110,
    103,  32, 117, 115, 101, 115,  32, 100, 101, 115,  99, 101,
    110, 100, 105, 110,
    ... 4085 more items
  ],
  stderr: Buffer(0) [Uint8Array] []
}

Node.js v24.21.0

```

## #26 e185 exec_command：.. escapes root: ..

```
git status --porcelain && node --input-type=module <<'SCRIPT'
import {readFileSync} from 'node:fs';
const root = "/home/pello/projects/qwen_strata/.tmp/commit-audit/measure/q3/runs/C/arw/.tmp/codex/59773751-09d2-4c7d-8189-46ed8c9e2164/_reviewer-cap/runs/8dbda33a-8057-45a2-92be-0111fad3990d/ca/2";
const out = root + "/.tmp/codex/59773751-09d2-4c7d-8189-46ed8c9e2164/_commit-audit-capability/reports/review.jsonl";
const req = JSON.parse(readFileSync(root + "/.tmp/codex/59773751-09d2-4c7d-8189-46ed8c9e2164/_commit-audit-capability/request.json", 'utf8'));
const rows = readFileSync(out, 'utf8').split('\n').filter(l => l !== '').map(l => JSON.parse(l));
const problems = [];
const cache = new Map();
const fileLines = (p) => {
  if (!cache.has(p)) cache.set(p, readFileSync(root + '/' + p, 'utf8').split('\n'));
  return cache.get(p);
};
const want = [];
for (const g of req.gate1) for (const r of g.requirements) want.push(r.filePath + ':' + r.line);
const have = rows.map(r => r.source.filePath + ':' + r.source.line);
const missing = want.filter(k => !have.includes(k));
const dup = have.filter((k, i) => have.indexOf(k) !== i);
if (missing.length) problems.push('missing gate1 rows: ' + missing.join(','));
if (dup.length) problems.push('duplicate rows: ' + dup.join(','));
const gate2Doc = req.gate2[0].documents[0];
const gate2Rows = rows.filter(r => r.source.filePath === gate2Doc);
const spec = fileLines(gate2Doc);
const bodyLines = [];
let inFence = false;
spec.forEach((text, i) => {
  const t = text.trim();
  if (t.startsWith('```')) { inFence = !inFence; return; }
  if (inFence || t === '' || t.startsWith('#')) return;
  bodyLines.push(i + 1);
});
const minNeeded = req.gate2[0].minimumSourceLines.find(m => m.filePath === gate2Doc).count;
const distinct = new Set(gate2Rows.map(r => r.source.line));
if (distinct.size < minNeeded) problems.push('gate2 distinct ' + distinct.size + ' < ' + minNeeded);
for (const line of distinct) if (!bodyLines.includes(line)) problems.push('gate2 line not body: ' + line);
const uncovered = bodyLines.filter(l => !distinct.has(l));
console.log('spec body lines', bodyLines.length, 'gate2 rows', gate2Rows.length, 'distinct', distinct.size, 'min', minNeeded, 'uncovered body lines', uncovered.join(',') || 'none');
for (const row of rows) {
  for (const k of Object.keys(row)) if (!['source', 'requirement', 'result', 'evidence', 'finding'].includes(k)) problems.push('bad key ' + k);
  const hasFinding = Object.prototype.hasOwnProperty.call(row, 'finding');
  if (hasFinding !== (row.result !== 'satisfied')) problems.push('finding shape @' + row.source.filePath + ':' + row.source.line);
  if (hasFinding && typeof row.finding !== 'string') problems.push('bad finding type');
  if (!['satisfied', 'gap', 'uncertain'].includes(row.result)) problems.push('bad result');
  if (typeof row.requirement !== 'string' || row.requirement.length === 0) problems.push('bad requirement');
  if (!Number.isInteger(row.source.line) || row.source.line < 1) problems.push('bad source line');
  if (!Array.isArray(row.evidence) || row.evidence.length === 0) problems.push('empty evidence');
  const files = new Map();
  for (const item of row.evidence) {
    if ('command' in item) {
      if (typeof item.command !== 'string' || item.command.length === 0) problems.push('bad command');
      if (!Number.isInteger(item.exitCode)) problems.push('bad exitCode');
      continue;
    }
    if (!('lines' in item) || typeof item.filePath !== 'string' || item.filePath.startsWith('/') || item.filePath.startsWith('..')) { problems.push('bad evidence shape'); continue; }
    files.set(item.filePath, (files.get(item.filePath) ?? 0) + 1);
    if (!Array.isArray(item.lines) || item.lines.length === 0) { problems.push('bad lines ' + item.filePath); continue; }
    let prevEnd = 0;
    const text = fileLines(item.filePath);
    const total = text.at(-1) === '' ? text.length - 1 : text.length;
    for (const entry of item.lines) {
      const pair = Array.isArray(entry) ? entry : [entry, entry];
      if (pair.length !== 2 || !pair.every(v => Number.isInteger(v) && v >= 1)) { problems.push('bad entry ' + item.filePath); continue; }
      if (pair[1] < pair[0]) problems.push('reversed ' + item.filePath + ' ' + pair.join('-'));
      if (pair[0] <= prevEnd + 1) problems.push('unmerged ' + item.filePath + ' ' + pair.join('-'));
      prevEnd = pair[1];
      if (pair[1] > total) problems.push('beyond file ' + item.filePath + ' ' + pair[1] + '>' + total);
      for (let ln = pair[0]; ln <= pair[1]; ln += 1) if ((text[ln - 1] ?? '').trim() === '') problems.push('empty cited line ' + item.filePath + ':' + ln);
    }
  }
  for (const [f, c] of files) if (c > 1) problems.push('duplicate file object ' + f + ' @' + row.source.filePath + ':' + row.source.line);
}
console.log('rows', rows.length, 'gate1 rows', rows.length - gate2Rows.length);
console.log('results', rows.reduce((a, r) => (a[r.result] = (a[r.result] ?? 0) + 1, a), {}));
console.log('problems', problems.length ? problems : 'none');
SCRIPT
```

结果（2749 字）：

```
Chunk ID: 6e481e
Wall time: 0.0000 seconds
Process exited with code 0
Original token count: 662
Output:
M  .scratch/0001-dispatch-control/issues/01-assemble-dispatch-plan.md
M  .scratch/0001-dispatch-control/issues/02-publish-dispatch-manifest.md
A  src/dispatch/access.mjs
A  src/dispatch/capacity.mjs
A  src/dispatch/executor.mjs
A  src/dispatch/index.mjs
A  src/dispatch/manifest.mjs
A  src/dispatch/normalize.mjs
A  src/dispatch/policy.mjs
A  src/dispatch/publisher.mjs
A  src/dispatch/queue.mjs
A  src/dispatch/retry.mjs
A  src/dispatch/runtime.mjs
A  src/dispatch/schedule.mjs
A  src/dispatch/serialize.mjs
A  src/dispatch/storage.mjs
A  src/dispatch/telemetry.mjs
A  tests/dispatch/plan.test.mjs
A  tests/dispatch/publish.test.mjs
A  tests/dispatch/scenarios.mjs
spec body lines 57 gate2 rows 57 distinct 57 min 19 uncovered body lines none
rows 106 gate1 rows 49
results { gap: 35, satisfied: 69, uncertain: 2 }
problems [
  'unmerged src/dispatch/index.mjs 1-11',
  'empty cited line src/dispatch/executor.mjs:9',
  'empty cited line src/dispatch/executor.mjs:11',
  'empty cited line src/dispatch/executor.mjs:13',
  'empty cited line src/dispatch/executor.mjs:18',
  'empty cited line tests/dispatch/scenarios.mjs:4',
  'unmerged src/dispatch/capacity.mjs 1-1',
  'unmerged src/dispatch/schedule.mjs 1-6',
  'empty cited line src/dispatch/schedule.mjs:2',
  'unmerged src/dispatch/storage.mjs 1-5',
  'unmerged src/dispatch/retry.mjs 1-6',
  'empty cited line src/dispatch/retry.mjs:2',
  'unmerged src/dispatch/policy.mjs 1-1',
  'unmerged src/dispatch/storage.mjs 1-3',
  'unmerged src/dispatch/storage.mjs 1-5',
  'unmerged docs/dispatch/storage-contract.md 1-5',
  'empty cited line docs/dispatch/storage-contract.md:2',
  'unmerged src/dispatch/access.mjs 1-1',
  'empty cited line src/dispatch/telemetry.mjs:8',
  'unmerged src/dispatch/serialize.mjs 1-5',
  'empty cited line src/dispatch/serialize.mjs:4',
  'empty cited line src/dispatch/telemetry.mjs:8',
  'unmerged src/dispatch/storage.mjs 1-5',
  'unmerged src/dispatch/index.mjs 1-11',
  'empty cited line src/dispatch/executor.mjs:9',
  'empty cited line src/dispatch/executor.mjs:11',
  'empty cited line src/dispatch/executor.mjs:13',
  'empty cited line src/dispatch/executor.mjs:18',
  'empty cited line src/dispatch/queue.mjs:18',
  'unmerged src/dispatch/storage.mjs 1-5',
  'unmerged src/dispatch/capacity.mjs 1-1',
  'empty cited line src/dispatch/serialize.mjs:4',
  'empty cited line tests/dispatch/publish.test.mjs:5',
  'unmerged docs/dispatch/storage-contract.md 1-5',
  'empty cited line docs/dispatch/storage-contract.md:2',
  'unmerged src/dispatch/retry.mjs 1-6',
  'empty cited line src/dispatch/retry.mjs:2',
  'unmerged src/dispatch/schedule.mjs 1-1'
]

```

## #27 e192 exec_command：workdir outside root: /home/pello/projects/qwen_strata/.tmp/commit-audit/measure/q3/runs/C/arw/.tmp/codex/59773751-09d2-4c7d-8189-46ed8c9e2164/_reviewer-cap/runs/8dbda33a-8189-46ed8c9e2164/_reviewer-cap/runs/8dbda33a-8057-45a2-92be-0111fad3990d/ca/2; denied/permission in result

```
node --input-type=module <<'SCRIPT'
import {readFileSync, writeFileSync} from 'node:fs';
const root = "/home/pello/projects/qwen_strata/.tmp/commit-audit/measure/q3/runs/C/arw/.tmp/codex/59773751-09d2-4c7d-8189-46ed8c9e2164/_reviewer-cap/runs/8dbda33a-8057-45a2-92be-0111fad3990d/ca/2";
const out = root + "/.tmp/codex/59773751-09d2-4c7d-8189-46ed8c9e2164/_commit-audit-capability/reports/review.jsonl";
const rows = readFileSync(out, 'utf8').split('\n').filter(l => l !== '').map(l => JSON.parse(l));
const cache = new Map();
const fileLines = (p) => {
  if (!cache.has(p)) cache.set(p, readFileSync(root + '/' + p, 'utf8').split('\n'));
  return cache.get(p);
};
for (const row of rows) {
  for (const item of row.evidence) {
    if ('command' in item) continue;
    const text = fileLines(item.filePath);
    const wanted = new Set();
    for (const entry of item.lines) {
      const pair = Array.isArray(entry) ? entry : [entry, entry];
      for (let ln = pair[0]; ln <= pair[1]; ln += 1) if ((text[ln - 1] ?? '').trim() !== '') wanted.add(ln);
    }
    const sorted = [...wanted].sort((a, b) => a - b);
    const merged = [];
    for (const ln of sorted) {
      const last = merged.at(-1);
      if (last && ln === last[1] + 1) last[1] = ln;
      else merged.push([ln, ln]);
    }
    item.lines = merged.map(([s, e]) => (s === e ? s : [s, e]));
  }
}
writeFileSync(out, rows.map(r => JSON.stringify(r)).join('\n') + '\n');
console.log('rewritten rows', rows.length);
SCRIPT
```

结果（141 字）：

```
exec_command failed: CreateProcess { message: "Rejected(\"Failed to create unified exec process: No such file or directory (os error 2)\")" }
```

## #29 e206 exec_command：.. escapes root: ..

```
node --input-type=module <<'SCRIPT'
import {readFileSync} from 'node:fs';
const root = "/home/pello/projects/qwen_strata/.tmp/commit-audit/measure/q3/runs/C/arw/.tmp/codex/59773751-09d2-4c7d-8189-46ed8c9e2164/_reviewer-cap/runs/8dbda33a-8057-45a2-92be-0111fad3990d/ca/2";
const out = root + "/.tmp/codex/59773751-09d2-4c7d-8189-46ed8c9e2164/_commit-audit-capability/reports/review.jsonl";
const req = JSON.parse(readFileSync(root + "/.tmp/codex/59773751-09d2-4c7d-8189-46ed8c9e2164/_commit-audit-capability/request.json", 'utf8'));
const rows = readFileSync(out, 'utf8').split('\n').filter(l => l !== '').map(l => JSON.parse(l));
const problems = [];
const cache = new Map();
const fileLines = (p) => {
  if (!cache.has(p)) cache.set(p, readFileSync(root + '/' + p, 'utf8').split('\n'));
  return cache.get(p);
};
const want = [];
for (const g of req.gate1) for (const r of g.requirements) want.push(r.filePath + ':' + r.line);
const have = rows.map(r => r.source.filePath + ':' + r.source.line);
if (want.filter(k => !have.includes(k)).length) problems.push('missing gate1 rows');
if (have.filter((k, i) => have.indexOf(k) !== i).length) problems.push('duplicate rows');
const gate2Doc = req.gate2[0].documents[0];
const gate2Rows = rows.filter(r => r.source.filePath === gate2Doc);
const spec = fileLines(gate2Doc);
const bodyLines = [];
let inFence = false;
spec.forEach((text, i) => {
  const t = text.trim();
  if (t.startsWith('```')) { inFence = !inFence; return; }
  if (inFence || t === '' || t.startsWith('#')) return;
  bodyLines.push(i + 1);
});
const minNeeded = req.gate2[0].minimumSourceLines.find(m => m.filePath === gate2Doc).count;
const distinct = new Set(gate2Rows.map(r => r.source.line));
if (distinct.size < minNeeded) problems.push('gate2 distinct ' + distinct.size + ' < ' + minNeeded);
for (const line of distinct) if (!bodyLines.includes(line)) problems.push('gate2 line not body: ' + line);
console.log('spec body lines', bodyLines.length, 'gate2 rows', gate2Rows.length, 'distinct', distinct.size, 'min', minNeeded, 'uncovered', bodyLines.filter(l => !distinct.has(l)).join(',') || 'none');
for (const row of rows) {
  for (const k of Object.keys(row)) if (!['source', 'requirement', 'result', 'evidence', 'finding'].includes(k)) problems.push('bad key ' + k);
  const hasFinding = Object.prototype.hasOwnProperty.call(row, 'finding');
  if (hasFinding !== (row.result !== 'satisfied')) problems.push('finding shape @' + row.source.filePath + ':' + row.source.line);
  if (!['satisfied', 'gap', 'uncertain'].includes(row.result)) problems.push('bad result');
  if (typeof row.requirement !== 'string' || row.requirement.length === 0) problems.push('bad requirement');
  if (!Number.isInteger(row.source.line) || row.source.line < 1) problems.push('bad source line');
  if (!Array.isArray(row.evidence) || row.evidence.length === 0) problems.push('empty evidence');
  const files = new Map();
  for (const item of row.evidence) {
    if ('command' in item) {
      if (typeof item.command !== 'string' || item.command.length === 0) problems.push('bad command');
      if (!Number.isInteger(item.exitCode)) problems.push('bad exitCode');
      continue;
    }
    if (!('lines' in item) || typeof item.filePath !== 'string' || item.filePath.startsWith('/') || item.filePath.startsWith('..')) { problems.push('bad evidence shape'); continue; }
    files.set(item.filePath, (files.get(item.filePath) ?? 0) + 1);
    if (!Array.isArray(item.lines) || item.lines.length === 0) { problems.push('bad lines ' + item.filePath); continue; }
    const text = fileLines(item.filePath);
    const total = text.at(-1) === '' ? text.length - 1 : text.length;
    let prev = null;
    for (const entry of item.lines) {
      const pair = Array.isArray(entry) ? entry : [entry, entry];
      if (pair.length !== 2 || !pair.every(v => Number.isInteger(v) && v >= 1)) { problems.push('bad entry ' + item.filePath); continue; }
      if (pair[1] < pair[0]) problems.push('reversed ' + item.filePath + ' ' + pair.join('-'));
      if (prev !== null && pair[0] <= prev[1] + 1) problems.push('unmerged ' + item.filePath + ' ' + pair.join('-'));
      prev = pair;
      if (pair[1] > total) problems.push('beyond file ' + item.filePath + ' ' + pair[1] + '>' + total);
      for (let ln = pair[0]; ln <= pair[1]; ln += 1) if ((text[ln - 1] ?? '').trim() === '') problems.push('blank cited line ' + item.filePath + ':' + ln);
    }
  }
  for (const [f, c] of files) if (c > 1) problems.push('duplicate file object ' + f + ' @' + row.source.filePath + ':' + row.source.line);
}
console.log('rows', rows.length, 'gate1 rows', rows.length - gate2Rows.length);
console.log('results', rows.reduce((a, r) => (a[r.result] = (a[r.result] ?? 0) + 1, a), {}));
console.log('problems', problems.length ? problems : 'none');
SCRIPT
```

结果（256 字）：

```
Chunk ID: 1c7dce
Wall time: 0.0000 seconds
Process exited with code 0
Original token count: 39
Output:
spec body lines 57 gate2 rows 57 distinct 57 min 19 uncovered none
rows 106 gate1 rows 49
results { gap: 35, satisfied: 69, uncertain: 2 }
problems none

```

