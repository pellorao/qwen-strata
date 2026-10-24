"""Rebuild this local Strata installation from user-provided files, without downloads."""
import argparse
import json
import os
from pathlib import Path
import runpy
import socket
import sys

# Run with <installation>\runtime\Strata\.venv\Scripts\python.exe; the installation is wherever that venv lives.
INSTALL = Path(sys.prefix).resolve().parents[2]
RUNTIME = INSTALL / "runtime" / "Strata"


def deny_network(*args, **kwargs):
    raise OSError("Offline installation forbids network connections; provide missing files locally")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=["IQ2_XS", "Q2_0", "IQ3_XXS"], default="IQ3_XXS")
    args = parser.parse_args()
    if Path(sys.prefix).resolve() != (RUNTIME / ".venv").resolve() or not (INSTALL / "config/installed-release.json").is_file():
        parser.error("Run with the installation's .venv/Scripts/python.exe")
    os.environ["PIP_NO_INDEX"] = "1"
    os.environ["PIP_FIND_LINKS"] = str(INSTALL / "downloads" / "wheels")
    os.environ["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    os.environ["STRATA_GGUF_PY"] = str(RUNTIME / "third_party" / "llama.cpp" / "gguf-py")
    os.environ["CUDA_PATH"] = r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v13.0"
    os.environ["PATH"] = str(Path(sys.prefix) / "Scripts") + os.pathsep + os.environ["PATH"]
    socket.socket.connect = deny_network
    socket.socket.connect_ex = deny_network
    socket.create_connection = deny_network
    version=json.loads((INSTALL/"config/installed-release.json").read_text(encoding="utf-8"))["version"]
    sys.argv = [str(RUNTIME / "setup.py"), "--setup", "--family", "qwen", "--model", args.model,
                "--context", "250000", "--kv", "int8", "--vision", "no", "--draft-vocab", "cjk",
                "--experimental-speed-projection", "off", "--backend", "cuda", "--host", "127.0.0.1",
                "--port", "8100", "--data-dir", str(INSTALL / "data"),
                "--gguf-dir", str(INSTALL / "data" / "models" / args.model),
                "--prebuilt", str(INSTALL / "downloads" / ("engine-v"+version)), "--no-start", "--yes"]
    os.chdir(RUNTIME)
    runpy.run_path(str(RUNTIME / "setup.py"), run_name="__main__")


if __name__ == "__main__":
    main()
