"""Rebuild this local Strata installation from user-provided files, without downloads.

Run with <installation>\\runtime\\Strata\\.venv\\Scripts\\python.exe; the installation is wherever that venv lives.
The engine is the one already installed in runtime\\Strata\\engine (tools.ops.upgrade_release unpacks the release's
engine package there), checked against config\\installed-release.json. Since 0.2.0 the release and engine versions
differ (0.2.4 ships engine 0.1.48), so the engine folder is not derived from the release version.
"""
import argparse
import json
import os
from pathlib import Path
import runpy
import socket
import sys


def installation(prefix=None):
    """The installation holding the running venv (<installation>/runtime/Strata/.venv)."""
    venv = Path(prefix or sys.prefix).resolve()
    if venv.name != '.venv' or venv.parent.name != 'Strata' or venv.parent.parent.name != 'runtime':
        raise ValueError("Run with the installation's runtime/Strata/.venv python")
    root = venv.parents[2]
    if not (root / 'config/installed-release.json').is_file():
        raise ValueError('The installation has no config/installed-release.json')
    return root


def installed_engine(root):
    """runtime/Strata/engine, when it holds the engine version installed-release.json names (files before 0.2.0
    carry no engine_version: the release version is the engine version then)."""
    release = json.loads((root / 'config/installed-release.json').read_text(encoding='utf-8'))
    expected = release.get('engine_version', release['version'])
    engine = root / 'runtime/Strata/engine'
    try:
        build = json.loads((engine / 'BUILD.json').read_text(encoding='utf-8'))
    except FileNotFoundError:
        build = None
    if not build or not (engine / 'strata.exe').is_file():
        raise ValueError('No installed engine in runtime/Strata/engine; install the release with tools.ops.upgrade_release')
    if build.get('version') != expected:
        raise ValueError(f'Installed engine {build.get("version")} is not the release engine {expected}; '
                         'reinstall the release with tools.ops.upgrade_release')
    return engine


def deny_network(*args, **kwargs):
    raise OSError("Offline installation forbids network connections; provide missing files locally")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=["IQ2_XS", "Q2_0", "IQ3_XXS"], default="IQ3_XXS")
    args = parser.parse_args()
    try:
        root = installation()
        engine = installed_engine(root)
    except ValueError as error:
        parser.error(str(error))
    runtime = root / "runtime" / "Strata"
    os.environ["PIP_NO_INDEX"] = "1"
    os.environ["PIP_FIND_LINKS"] = str(root / "downloads" / "wheels")
    os.environ["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    os.environ["STRATA_GGUF_PY"] = str(runtime / "third_party" / "llama.cpp" / "gguf-py")
    # No CUDA_PATH override: the ready-made engine needs no toolkit (setup.py reads CUDA_PATH only to find nvcc for
    # a local build), and the machine's own toolkit, if any, stays visible.
    os.environ["PATH"] = str(Path(sys.prefix) / "Scripts") + os.pathsep + os.environ["PATH"]
    socket.socket.connect = deny_network
    socket.socket.connect_ex = deny_network
    socket.create_connection = deny_network
    # setup.py keeps an installed engine that covers this GPU; --prebuilt names the same folder, so a refused engine
    # is looked up locally only (no download, the network is denied above).
    sys.argv = [str(runtime / "setup.py"), "--setup", "--family", "qwen", "--model", args.model,
                "--context", "250000", "--kv", "int8", "--vision", "no", "--draft-vocab", "cjk",
                "--experimental-speed-projection", "off", "--backend", "cuda", "--host", "127.0.0.1",
                "--port", "8100", "--data-dir", str(root / "data"),
                "--gguf-dir", str(root / "data" / "models" / args.model),
                "--prebuilt", str(engine), "--no-start", "--yes"]
    os.chdir(runtime)
    runpy.run_path(str(runtime / "setup.py"), run_name="__main__")


if __name__ == "__main__":
    main()
