"""Transfer registered model files directly, then verify pinned remote SHA256."""
import argparse
import json
import os
from pathlib import Path, PureWindowsPath
import subprocess
import time
import uuid

from tools.ops.remote_windows import connection_environment, host_configuration, powershell
from tools.ops.ssh_files import copy_file, powershell_literal

ROOT = Path(__file__).resolve().parents[2]


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    stage = path.with_suffix(path.suffix + '.stage')
    stage.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')
    stage.replace(path)


def model_manifests(models):
    if not models or len(set(models)) != len(models) or any(m not in ('Q2_0', 'IQ2_XS', 'IQ3_XXS') for m in models):
        raise ValueError('Choose unique registered model quantizations')
    return [json.loads((ROOT / 'config/artifacts' / (model.lower() + '.json')).read_text(encoding='utf-8')) for model in models]


def plan(host='rtx3080ti', models=('Q2_0',)):
    settings = connection_environment(host=host)
    manifests = model_manifests(models)
    files = [{**item, 'model': manifest['model'], 'target_directory': manifest['target_directory']}
             for manifest in manifests for item in manifest['files']]
    unique = {item['sha256']: item for item in files}
    return {'host': host, 'models': list(models), 'files': files,
            'total_bytes': sum(x['bytes'] for x in files),
            'unique_transfer_bytes': sum(x['bytes'] for x in unique.values()),
            'unique_file_count': len(unique), 'source': 'registered existing local model files',
            'access_endpoint': settings['api_base_url'],
            'verification': 'Direct upload; compare remote size and complete SHA256 against project pinned manifests before publishing.',
            'model_requests': 0, 'starts_inference': False, 'needs_user_transfer_approval': True}


def run(out, host='rtx3080ti', known_hosts=None, models=('Q2_0',)):
    if os.name != 'nt':
        raise RuntimeError('Execute the approved transfer with Windows Python and native Windows SCP/SSH')
    settings = connection_environment(host=host)
    if not settings.get('STRATA_REMOTE_IDENTITY_FILE'):
        raise RuntimeError('Complete existing-key authentication and native file validation first')
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    specification = plan(host, models)
    save(out / 'plan.json', specification)
    known_hosts = Path(known_hosts or Path(os.environ['USERPROFILE']) / '.ssh/known_hosts')
    local = host_configuration(host='local')
    installed = Path(local['installation_path'])
    progress = out / 'progress.json'
    records = []
    began = time.time()
    transferred = {}
    for item in specification['files']:
        target = PureWindowsPath(settings['installation_path']) / item['target_directory']
        script = "$ErrorActionPreference='Stop';New-Item -ItemType Directory -Path " + powershell_literal(str(target)) + " -Force | Out-Null;[Console]::WriteLine('ready')"
        if powershell(script, settings, known_hosts=known_hosts).strip() != 'ready':
            raise RuntimeError('Remote target directory not confirmed')
        source = installed / item['target_directory'] / item['name']
        if not source.is_file() or source.stat().st_size != item['bytes']:
            raise RuntimeError('Registered local model file is missing or has an unexpected size')
        final = target / item['name']
        if item['sha256'] in transferred:
            canonical = transferred[item['sha256']]
            script = ("$ErrorActionPreference='Stop';[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false);"
                      "$target=" + powershell_literal(str(final)) + ";$source=" + powershell_literal(str(canonical)) + ";"
                      "if(Test-Path -LiteralPath $target){throw 'Shared shard destination already exists'};"
                      "New-Item -ItemType HardLink -Path $target -Target $source|Out-Null;"
                      "[ordered]@{bytes=(Get-Item -LiteralPath $target).Length;hardlink_created=$true}|ConvertTo-Json -Compress")
            actual = json.loads(powershell(script, settings, known_hosts=known_hosts))
            if actual['bytes'] != item['bytes'] or not actual['hardlink_created']:
                raise RuntimeError('Shared shard link was not confirmed')
            record = {**item, 'upload_seconds': 0, 'transferred_bytes': 0, 'source_remote_sha_verified': True,
                      'hardlinked_to': str(canonical), 'remote_verified': actual}
            records.append(record)
            save(out / 'completed-files.json', records)
            print(json.dumps({'stage': 'shared-shard-linked', 'model': item['model'], 'file': item['name']}), flush=True)
            continue
        partial = target / (item['name'] + '.part-' + uuid.uuid4().hex)
        status = {'stage': 'upload', 'file': item['name'], 'bytes': item['bytes'], 'at': time.time()}
        save(progress, status)
        print(json.dumps(status), flush=True)
        seconds = copy_file(source, partial, settings, known_hosts, timeout=12 * 3600)
        script = ("$ErrorActionPreference='Stop';[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false);"
                  "$partial=" + powershell_literal(str(partial)) + ";$final=" + powershell_literal(str(final)) + ";"
                  "$hash=(Get-FileHash -LiteralPath $partial -Algorithm SHA256).Hash.ToLower();"
                  "$bytes=(Get-Item -LiteralPath $partial).Length;"
                  "if($hash -ne '" + item['sha256'] + "' -or $bytes -ne " + str(item['bytes']) + "){throw 'Transferred model SHA or size mismatch'};"
                  "if(Test-Path -LiteralPath $final){throw 'Final model already exists; preserve both files'};"
                  "[System.IO.File]::Move($partial,$final);"
                  "[ordered]@{sha256=$hash;bytes=$bytes;committed=$true}|ConvertTo-Json -Compress")
        actual = json.loads(powershell(script, settings, timeout=1800, known_hosts=known_hosts))
        assert actual['sha256'] == item['sha256'] and actual['bytes'] == item['bytes'] and actual['committed']
        transferred[item['sha256']] = final
        record = {**item, 'upload_seconds': seconds, 'transferred_bytes': item['bytes'], 'remote_verified': actual}
        records.append(record)
        save(out / 'completed-files.json', records)
        print(json.dumps({'stage': 'verified', 'file': item['name'], 'upload_seconds': seconds}), flush=True)
    result = {'status': 'completed', 'host': host, 'files': records, 'started_at': began,
              'finished_at': time.time(), 'total_bytes': specification['total_bytes'],
              'unique_transfer_bytes': specification['unique_transfer_bytes'],
              'source': specification['source'], 'model_requests': 0,
              'password_echoed': False, 'manifest_source': 'maintenance project',
              'integrity_verified_after_upload': True}
    save(out / 'result.json', result)
    save(progress, {'stage': 'completed', 'total_bytes': specification['total_bytes'], 'at': time.time()})
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='rtx3080ti')
    parser.add_argument('--models', nargs='+', choices=('Q2_0', 'IQ2_XS', 'IQ3_XXS'), default=['Q2_0'])
    parser.add_argument('--known-hosts', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--approved', action='store_true', help='Execute only after the user approves this transfer.')
    args = parser.parse_args()
    if args.approved:
        result = run(args.out, args.host, args.known_hosts, args.models)
    else:
        result = plan(args.host, args.models)
        save(args.out / 'plan.json', result)
    print(json.dumps(result, indent=2))
