"""Measurement-only Codex profile: project read, fixed scratch write, command network denied."""
from pathlib import Path
from tools.reviewer.native_cli_binding import CODEX_VENDOR


def restricted_profile(workspace, scratch):
    workspace = Path(workspace).resolve(strict=True)
    scratch = Path(scratch).resolve(strict=True)
    if workspace == scratch or workspace.is_relative_to(scratch):
        raise ValueError('Scratch must not contain the read-only project')
    # The sandbox helper re-executes the native binary, not the npm wrapper that `codex` resolves to.
    vendor = CODEX_VENDOR.resolve(strict=True)
    return {
        'default_permissions': 'review', 'approval_policy': 'never',
        'permissions.review.description': 'Project read; fixed scratch write; no command network',
        'permissions.review.filesystem': {':minimal': 'read', str(vendor): 'read',
                                         str(workspace): 'read', str(scratch): 'write'},
        'permissions.review.network.enabled': False,
        'mcp_servers.project.enabled': False,
    }
