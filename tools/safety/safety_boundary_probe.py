"""Execute inside the native sandbox against synthetic canaries only."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys


def check(workspace,report,outside):
    workspace=Path(workspace).resolve();report=Path(report).resolve();outside=Path(outside).resolve()
    source=workspace/'input.txt';results={}
    assert source.read_text()=='SYNTHETIC-READ-OK\n' and outside.read_text()=='OUTSIDE-READ-OK\n'
    results['source_read']='allowed';results['outside_read']='allowed'
    def denied(name,operation):
        try:operation();results[name]='UNEXPECTED-WRITE'
        except OSError:results[name]='denied'
    denied('source_write',lambda:source.write_text('BAD'))
    denied('outside_write',lambda:outside.write_text('BAD'))
    denied('traversal_write',lambda:(report.parent/os.path.relpath(outside,report.parent)).write_text('BAD'))
    link=report.parent/'symlink-probe'
    try:
        link.symlink_to(outside);denied('symlink_write',lambda:link.write_text('BAD'))
    finally:link.unlink(missing_ok=True)
    hard=report.parent/'hardlink-probe'
    try:
        try:os.link(outside,hard)
        except OSError:results['hardlink_write']='denied'
        else:denied('hardlink_write',lambda:hard.write_text('BAD'))
    finally:hard.unlink(missing_ok=True)
    code='from pathlib import Path; Path('+repr(str(outside))+').write_text("BAD")'
    child=subprocess.run([sys.executable,'-c',code],capture_output=True)
    results['child_write']='denied'if child.returncode else'UNEXPECTED-WRITE'
    fd=os.open(outside,os.O_RDONLY)
    try:denied('proc_fd_write',lambda:Path('/proc/self/fd/'+str(fd)).write_text('BAD'))
    finally:os.close(fd)
    denied('proc_root_write',lambda:(Path('/proc/self/root')/str(outside).lstrip('/')).write_text('BAD'))
    sibling=report.parent/'sibling-probe.txt'
    try:sibling.write_text('APPROVED-DIRECTORY-SCOPE');results['report_sibling_write']='allowed'
    finally:sibling.unlink(missing_ok=True)
    results['canaries_unchanged']=source.read_text()=='SYNTHETIC-READ-OK\n'and outside.read_text()=='OUTSIDE-READ-OK\n'
    results['pass']=results['canaries_unchanged']and all(results[k]=='denied'for k in ['source_write','outside_write','traversal_write','symlink_write','hardlink_write','child_write','proc_fd_write','proc_root_write'])
    return results


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--workspace',type=Path,required=True);parser.add_argument('--report',type=Path,required=True);parser.add_argument('--outside',type=Path,required=True);args=parser.parse_args()
    result=check(args.workspace,args.report,args.outside)
    print(json.dumps(result));(args.report.parent/'boundary-results.json').write_text(json.dumps(result)+'\n')
    raise SystemExit(0 if result['pass'] else 1)
