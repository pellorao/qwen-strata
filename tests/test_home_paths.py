"""Isolation and deny paths follow Path.home(); on rtx3080ti (HOME=/home/pello) they expand exactly as the literal
/home/pello paths they replaced, so the sandbox, HOME isolation and credential deny lists are unchanged there."""
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
RTX3080TI_HOME = '/home/pello'

# Runs in a fresh interpreter whose HOME is rtx3080ti's, since several of these are module-level constants.
PROBE = r'''
import json, tempfile
from pathlib import Path
from tools.strata import claude_headless as ch, harness_pins, providers
from tools.tuning import sandbox_probe
result = {
    'deny_read_home': ch.DENY_READ[0],
    'estimate': str(ch.ESTIMATE),
    'anthropic_config': str(ch.config_root('anthropic', '/var/tmp/qwen-claude/r/work')),
    'bench': str(harness_pins.BENCH),
    'credential_deny': providers.credential_deny_paths(project_root='/p'),
    'user_codex': [str(p) for n, p, k in sandbox_probe.targets(Path('/s')) if n == 'user-codex'],
}
try:
    ch.workspace('x', '/home/pello/runs')
    result['workspace_under_home'] = 'allowed'
except ValueError:
    result['workspace_under_home'] = 'refused'
print(json.dumps(result))
'''


class Rtx3080tiHomePathsTest(unittest.TestCase):
    def test_expansions_match_the_literal_paths(self):
        env = {'PATH': '/usr/bin:/bin', 'HOME': RTX3080TI_HOME, 'LANG': 'C.UTF-8'}
        reply = subprocess.run([sys.executable, '-c', PROBE], cwd=ROOT, env=env, capture_output=True, text=True,
                               timeout=120)
        self.assertEqual(reply.returncode, 0, reply.stderr)
        result = json.loads(reply.stdout)
        self.assertEqual(result, {
            'deny_read_home': '/home/pello',
            'estimate': '/home/pello/.claude/statusline/estimate.sh',
            'anthropic_config': '/home/pello/.claude',
            'bench': '/home/pello/.local/share/qwen-bench',
            'credential_deny': ['/home/pello/.claude/.credentials.json', '/home/pello/.codex', '/p/project.private.toml'],
            'user_codex': ['/home/pello/.codex'],
            'workspace_under_home': 'refused',
        })


if __name__ == '__main__':
    unittest.main()
