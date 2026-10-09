"""Deploy the WSL service entry points, without touching weights or runtime configuration."""
import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from tools.ops.deployment_source import load_host, source_bytes

ROOT = Path(__file__).resolve().parents[2]
FILES = {'scripts/wsl/Run-Strata-Controller.sh': 'Run-Strata-Controller.sh',
         'scripts/wsl/Setup-WSL-Network.sh': 'maintenance/Setup-WSL-Network.sh'}
FILES.update({f'src/{name}': f'src/{name}' for name in ('responses_bridge.py', 'brave_search.py', 'hosted_search.py', 'windows_host.py', 'wsl_launcher.py', 'setup_wsl_firewall.ps1', 'project_files_mcp.py', 'service_access.py', 'native_service.py', 'controller_backend.py', 'startup_instructions.py')})
FILES.update({'config/model-catalog.json':'config/model-catalog.json'})
FILES.update({'config/prompts/startup-instructions.txt':'config/prompts/startup-instructions.txt'})
FILES.update({'config/prompts/compact-prompt.txt':'config/prompts/compact-prompt.txt'})
FILES.update({'config/maintenance-baseline.json':'config/maintenance-baseline.json'})
# Install only the service and caller manual; maintenance reports, scenarios
# and agent documentation remain in the maintenance project.
FILES = {target: source for source, target in FILES.items()}
FILES.update({'README.md': 'docs/installation-directory-readme.md'})
FILES.update({f'config/{model.lower()}-prebuilt.json': f'config/templates/{model.lower()}-prebuilt.json'
              for model in ('Q2_0', 'IQ2_XS', 'IQ3_XXS')})
FILES['config/deployment.json'] = 'config/deployment.json'
FILES['config/service.json'] = 'config/service.json'
FILES['src/service_settings.py'] = 'src/service_settings.py'
FILES['Run-Strata-Controller.ps1'] = 'scripts/windows/Run-Strata-Controller.ps1'
FILES['maintenance/Setup-Native-Network.ps1'] = 'scripts/windows/Setup-Native-Network.ps1'
OBSOLETE = ('Run-Strata.cmd', 'Run-Codex.cmd', 'Stop-Strata.cmd', 'src/run_strata.ps1', 'src/run_codex.ps1', 'src/stop_strata.ps1',
            'Run-Strata.sh', 'Stop-Strata.sh', 'Status-Strata.sh', 'Setup-WSL-Network.sh',
            'docs/WSL-HANDOFF.md', 'docs/MIGRATION.md', 'docs/WORK-STATUS.md', 'docs/PENDING-DECISIONS.md',
            'docs/QUESTIONS.md', 'docs/WINDOWS-INSTALLATION-RECORD.md', 'docs/WINDOWS-CODEX-RECORD.md', 'docs/IQ3-DECISION.md')
OBSOLETE += ('docs/WSL-RUNNING.md', 'docs/VALIDATION.md', 'docs/INSTALLATION.md',
             'docs/PLAN.md', 'docs/installation.README.md', 'docs/DOWNLOADS.md',
             'docs/COMPACTION-OPTIONS.md', 'docs/CODEX.md', 'docs/TUNING.md',
             'reports/v0.1.38/code-review-EXECUTION-ADDENDUM.md',
             'reports/v0.1.38/code-review-PROTOCOL.md',
             'reports/v0.1.38/code-review-fixture/AGENTS.md',
             'benchmarks/code-standards-v1/PROTOCOL.md',
             'benchmarks/code-standards-v1/EXECUTION-ADDENDUM.md',
             'benchmarks/code-standards-v1/project/AGENTS.md')
OBSOLETE += ('docs/installation.readme.md','config/codex-default-compact-prompt.txt')
OBSOLETE += tuple('src/'+name for name in (
    'audit_compaction.py','benchmark.py','calibrate_200k.py','compare_candidates.py',
    'compare_compaction.py','compare_quant_final.py','confirm_defaults.py',
    'export_reports.py','install_offline.py','update_offline.py','verify_code_recall.py',
    'verify_codex.py','verify_compaction.py','verify_compaction_cycles.py',
    'verify_compaction_repeat.py','verify_console_stop.py','verify_launcher.py',
    'verify_lifecycle.py','verify_mcp_routes.py','verify_more_candidates.py',
    'verify_needle.py','verify_project_launcher.py','verify_recovery.py',
    'verify_release.py','verify_runtime.py','verify_threshold.py'))
RETIRED_TREES = ('reports','benchmarks','docs','tools','tests',
    'downloads/engine-v0.1.37','benchmarks/code-standards-v1',
    'reports/v0.1.36/quality', 'reports/v0.1.37/quality',
    'reports/v0.1.37/compaction', 'reports/v0.1.37/wsl-compaction',
    'reports/v0.1.38/code-review', 'reports/v0.1.38/code-review-fixture',
    'reports/v0.1.38/approval-cost',
    'reports/v0.1.38/safety-20261004/evidence',
    'reports/v0.1.38/safety-20261004/pathset-evidence',
    *(f'reports/v0.1.38/safety-20261004/{name}-evidence' for name in
      ('approval-mcp','approval-preflight','native-default','native-host','native-protocol')),
    'reports/v0.1.38/upgrade-cycle-20261003/profile-training-materials',
    'reports/v0.1.38/upgrade-cycle-20261003/profile-training-bounded-materials',
    'reports/v0.1.38/upgrade-cycle-20261003/profile-validation-evidence')
RETIRED_FILES = ('reports/v0.1.38/code-review-*',
    *(f'reports/v0.1.38/upgrade-cycle-20261003/{name}' for name in
      ('profile-validation-progress.json','profile-validation-progress.md',
       'profile-validation-active-observation.json','parameter-prompt.txt','parameter-startup-errors.json')))


def obsolete_entries(installation, docs_only=False):
    """Remove retired published inputs/details with the normal backup transaction."""
    entries=[p for p in OBSOLETE if not docs_only or p.startswith('docs/') or p.endswith('.md')]
    for relative in RETIRED_TREES:
        if docs_only and (relative == 'tests' or relative.startswith('downloads/')):
            continue
        entries.extend(p.relative_to(installation).as_posix()
            for p in (installation/relative).rglob('*') if p.is_file())
    for pattern in RETIRED_FILES:
        entries.extend(p.relative_to(installation).as_posix()
            for p in installation.glob(pattern) if p.is_file())
    return tuple(dict.fromkeys(entries))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def deploy(installation, docs_only=False, deployment='local'):
    if docs_only:return deploy_locked(installation,True,deployment)
    from tools.ops.upgrade_release import guard
    process=guard(installation.resolve(strict=True))
    try:return deploy_locked(installation,False,deployment)
    finally:
        process.stdin.close()
        process.wait(timeout=30)


def deploy_locked(installation, docs_only=False, deployment='local'):
    installation = installation.resolve(strict=True)
    if not (installation / 'runtime/Strata/.venv/Scripts/python.exe').is_file() or not (installation / 'config/installed-release.json').is_file():
        raise RuntimeError('Target must be the existing installed Strata runtime.')
    selected = {target: source for target, source in FILES.items()
                if not docs_only or source.endswith('.md') or source.startswith('reports/') or source.startswith('benchmarks/')}
    if not docs_only:
        host = load_host(deployment, ROOT)
        windows_target = subprocess.check_output(['wslpath', '-w', str(installation)], text=True).strip()
        from pathlib import PureWindowsPath
        if PureWindowsPath(windows_target) != PureWindowsPath(host['installation_root']):
            raise RuntimeError('Target differs from the selected project deployment')
        selected = {target: source for target, source in selected.items()
                    if not source.startswith('config/templates/') or
                    source.split('/')[-1].split('-prebuilt')[0].upper() in host['models']}
    obsolete = obsolete_entries(installation, docs_only)
    access = installation / '.state/ownership.json'
    if not docs_only:
        import sys
        sys.path.insert(0,str(ROOT/'src'))
        from service_access import authorize
        if not authorize(access,os.environ.get('STRATA_API_KEY')):
            raise RuntimeError('Runtime deployment requires the current maintenance ownership key.')
    payloads = {target: source_bytes(source, deployment, ROOT) for target, source in selected.items()}
    backup = ROOT / '.tmp/maintenance-backups' / ('wsl-deploy-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
    backup.mkdir(parents=True)
    before = {}
    for relative in set(selected) | set(obsolete):
        path = installation / relative
        if path.is_file():
            saved = backup / relative
            saved.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, saved)
            before[relative] = digest(path)
    try:
        for relative, source in selected.items():
            target = installation / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as temporary:
                stage = Path(temporary.name)
                temporary.write(payloads[relative])
            try:
                os.replace(stage, target)
            finally:
                stage.unlink(missing_ok=True)
            if digest(target) != hashlib.sha256(payloads[relative]).hexdigest():
                raise RuntimeError('Deployment hash mismatch: ' + relative)
        for relative in obsolete:
            old = installation / relative
            replacement = next((installation / target for target in selected
                                if target.casefold() == relative.casefold()), None)
            # On Windows a case-only old path may refer to the newly deployed
            # file. Remove separate obsolete files, never the replacement.
            if replacement is not None and old.exists() and replacement.exists() and old.samefile(replacement):
                continue
            old.unlink(missing_ok=True)
    except BaseException:
        for relative in set(selected) | set(obsolete):
            target = installation / relative
            if relative in before:
                shutil.copyfile(backup / relative, target)
            else:
                target.unlink(missing_ok=True)
        raise
    result = {'installation': str(installation), 'deployment': deployment, 'backup': str(backup), 'deployed_sha256': {target: digest(installation / target) for target in selected}, 'removed_entries': list(obsolete), 'runtime_configuration_modified': any(target.endswith('-prebuilt.json') for target in selected), 'client_catalog_modified': 'config/model-catalog.json' in selected, 'docs_only': docs_only}
    (backup / 'deployment.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    # Retired fixtures should not leave misleading empty scenario directories.
    for relative in RETIRED_TREES:
        tree = installation / relative
        for directory in sorted((p for p in tree.rglob('*') if p.is_dir()),
                                key=lambda p: len(p.parts), reverse=True):
            try: directory.rmdir()
            except OSError: pass
        try: tree.rmdir()
        except OSError: pass
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--install-root', type=Path, required=True)
    parser.add_argument('--deployment', default='local', help='Project-owned config/deployments identifier.')
    parser.add_argument('--docs-only', action='store_true', help='Sync documentation and completed summaries without replacing runtime files.')
    args = parser.parse_args()
    print(json.dumps(deploy(args.install_root, args.docs_only, args.deployment), indent=2))
