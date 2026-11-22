"""The one place that names the harness versions the tools run (measurement rule "harness 版本", user 2026-10-23).

Each piece of work starts on the then-latest Codex and Claude Code and keeps them until it ends: to change versions,
install a read-only benchmark copy (off PATH; Codex from the npm registry tarballs, integrity checked, no install
scripts; Claude Code copied from the daily install, checksum checked against the official release manifest), update
the four values below, then rerun the harness's zero-model mock gates (Claude Code also tools.ops.claude_compact_probe).
The CLIs and gates refuse a binary whose SHA or version differs. Finished work keeps the versions it recorded
(the multi-model benchmark v1: Codex 0.163.0, Claude Code 2.1.303; archived benchmark_export)."""
from pathlib import Path

BENCH = Path.home() / '.local/share/qwen-bench'

CODEX_VERSION = '0.164.0'
CODEX_SHA256 = 'b93f6811d3f653f0fb83be4050d857fb9abbb111dfa2ce160563327daff7f306'
CLAUDE_VERSION = '2.1.310'
CLAUDE_SHA256 = 'b73676430af12f97316a798b8371f81d640f90a58bdcb8f3ce56a835bb47df56'


def codex_vendor(version):
    """Vendor directory of the Codex benchmark copy of `version` (layout: multi-model benchmark plan §3). Frozen plans
    bind their own version (arw_dimension.selection), so keep a copy while finished work may still be re-prepared."""
    return (BENCH / f'codex-{version}'
            / 'node_modules/@openai/codex/node_modules/@openai/codex-linux-x64/vendor')


def codex_binary(version):
    return codex_vendor(version) / 'x86_64-unknown-linux-musl/bin/codex'


CODEX_VENDOR = codex_vendor(CODEX_VERSION)
CODEX = codex_binary(CODEX_VERSION)
CLAUDE = BENCH / f'claude-code-{CLAUDE_VERSION}' / 'claude'
