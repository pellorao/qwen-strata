"""Native Windows SSH transport; private host settings are loaded on Windows."""
import argparse
import json
import os
from pathlib import Path, PureWindowsPath
import sys
import subprocess

from tools.ops.remote_windows import authentication_environment, connection_environment, powershell


def python_command(host, code, arguments, timeout=120, *, executable=None):
    """Send long installer code through SSH stdin, never the Windows command line."""
    if os.name != 'nt':raise RuntimeError('Use Windows Python for native SSH')
    settings=connection_environment(host=host)
    python=str(executable or 'C:\\Python314\\python.exe')
    if not PureWindowsPath(python).is_absolute() or any(c in python for c in '\"\r\n'):
        raise ValueError('Remote Python must be an absolute Windows executable path')
    executable=Path(os.environ['SystemRoot'])/'System32/OpenSSH/ssh.exe'
    bootstrap="import sys,json;request=json.load(sys.stdin);sys.argv=['phase']+request['args'];exec(request['code'])"
    command=[str(executable),'-T','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=10',
             '-o','BatchMode=yes','-o','IdentitiesOnly=yes','-i',settings['STRATA_REMOTE_IDENTITY_FILE'],
             '-p',settings['STRATA_REMOTE_PORT'],'-l',settings['STRATA_REMOTE_USER'],
             settings['STRATA_REMOTE_HOST'],'"'+python+'"','-c','"'+bootstrap+'"']
    data=json.dumps({'code':code,'args':[str(x) for x in arguments]}).encode('utf-8')
    with authentication_environment(settings) as environment:
        try:reply=subprocess.run(command,input=data,capture_output=True,env=environment,timeout=timeout)
        except subprocess.TimeoutExpired:raise RuntimeError('Native remote Python phase timed out; private payload not echoed') from None
    if reply.returncode:raise RuntimeError('Native remote Python transport failed; private stderr not echoed')
    return reply.stdout.decode('utf-8-sig').strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', required=True)
    args = parser.parse_args()
    if os.name != 'nt':
        raise SystemExit('Use Windows Python for this transport worker')
    try:
        request = json.loads(sys.stdin.buffer.read().decode('utf-8'))
        if request.get('operation')=='python':
            if set(request)-{'operation','code','args','timeout','executable'} or not isinstance(request.get('code'),str):raise ValueError('Invalid Python request')
            result=python_command(args.host,request['code'],request.get('args',[]),request.get('timeout',120),executable=request.get('executable'))
        elif set(request) - {'script', 'timeout', 'known_hosts'} or not isinstance(request.get('script'), str):
            raise ValueError('Invalid native remote request')
        else:result = powershell(request['script'], connection_environment(host=args.host),
                            timeout=request.get('timeout', 60), known_hosts=request.get('known_hosts'))
        print(json.dumps({'ok': True, 'stdout': result}))
    except (OSError, ValueError, RuntimeError):
        # No traceback or original command/request may disclose configuration.
        print(json.dumps({'ok': False, 'error': 'Native Windows remote operation failed; private details not echoed'}))


if __name__ == '__main__':
    main()
