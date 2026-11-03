"""Use the unchanged upstream single-completed-repetition diagnostic endpoint."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def prepare(batch_directory, name):
    """Write main-scoring/{artifacts,input,binding}.json for one completed instance and run `score-completed`."""
    batch = Path(batch_directory).resolve()
    folder = batch / 'premature-continuations' / name
    job = next((j for j in json.loads((batch / 'jobs.json').read_text()) if Path(j['folder']).name == name), None)
    require(job is not None, f'No job named {name} in {batch}/jobs.json')
    result = json.loads((folder / 'result.json').read_text())
    require((folder / 'run-finished.json').exists() and result['ownership_returned'], 'Instance did not finish and return ownership')
    require(sha256(result['final_report_path']) == result['final_report_sha256'], 'Final report does not match its recorded SHA-256')
    generation = result['generation']
    require(generation['exit_code'] == 0 and generation['result'].get('status') != 'failed' and generation['result']['files'],
            'Generation did not complete with files')
    dispatch = json.loads(Path(job['dispatch']).read_text())
    root = Path(dispatch['generations'][0]['workdir'])
    paths = [str(root / f['sourcePath']) for f in generation['result']['files']]
    require(all(Path(p).is_file() for p in paths), 'A generated artifact file is missing')
    work = folder / 'main-scoring'
    work.mkdir(exist_ok=False)
    artifacts = work / 'artifacts.json'
    artifacts.write_text(json.dumps({'artifacts': [{'reviewerId': 'commit-audit-reviewer', 'instances': [
        {'instanceId': job['instanceId'], 'artifactPaths': paths}]}]}, indent=2) + '\n')
    (work / 'input.json').write_text(json.dumps({
        'repositoryRoot': dispatch['repositoryRoot'], 'identity': dispatch['identity'], 'preparedPath': dispatch['preparedPath'],
        'artifactsPath': str(artifacts), 'options': {}}, indent=2) + '\n')
    effort = json.loads((folder / 'initial-preservation/results.json').read_text())[0]['selection']['effort']
    (work / 'binding.json').write_text(json.dumps({
        'instanceId': job['instanceId'], 'effort': effort, 'measurement_repeat': job['repetition'],
        'original_prepared_repeat': int(job['instanceId'].rsplit('-', 1)[1]), 'preparedPath': dispatch['preparedPath'],
        'prepared_sha256': sha256(dispatch['preparedPath']), 'initial_report_sha256': result['initial_report_sha256'],
        'continued_report_sha256': result['final_report_sha256'], 'artifact_sha256': {p: sha256(p) for p in paths},
        'only_actual_completed_repeat_selected': True, 'other_repeats_omitted_not_zeroed': True,
        'formal_status_failure_retained': result['terminal_kind']}, indent=2) + '\n')
    subprocess.run(['node', str(ROOT / 'tools/reviewer/arw_native.mjs'), 'score-completed', str(work / 'input.json'), str(work / 'pending.json')], check=True)
    pending = json.loads((work / 'pending.json').read_text())
    return {'status': pending.get('status'), 'candidates': len(pending.get('candidates', [])),
            'binding_requests': len(pending.get('bindingRequests', []))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch-directory', required=True)
    parser.add_argument('--name', required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.batch_directory, args.name)))


if __name__ == '__main__':
    main()
