"""Freeze an ordinary Hokum target and external driver for a disposable VM."""

import argparse
import hashlib
import json
import mmap
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path


def command(*args):
    return subprocess.check_output(args, text=True).strip()


def duration(value):
    if not re.fullmatch(r"[1-9][0-9]*[smh]", value):
        raise argparse.ArgumentTypeError("expected a positive duration: 10s, 5m, 1h")
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument(
        "--backend",
        choices=("mock", "pipewire"),
        default=os.environ.get("HOKUM_BACKEND", "mock"),
        help="guest service backend (default: HOKUM_BACKEND or mock)",
    )
    parser.add_argument("--time-limit-fuzz", type=duration, default="30s")
    parser.add_argument("--time-limit-run", type=duration, default="15s")
    parser.add_argument("--replay", type=Path)
    parser.add_argument("--build-only", action="store_true")
    args = parser.parse_args()
    if args.backend not in {"mock", "pipewire"}:
        parser.error("HOKUM_BACKEND must be mock or pipewire")
    root = Path(command("git", "rev-parse", "--show-toplevel"))
    source = args.bundle.resolve(strict=True)
    for name in (
        "hokum",
        "bombadil",
        "rune-driver",
        "spec.ts",
    ):
        if not (source / name).is_file():
            parser.error(f"bundle missing {name}")
    # No links or special files: do not accidentally freeze an entire source tree
    # or let a guest-visible bundle reach back into the host filesystem.
    files = list(source.rglob("*"))
    if any(p.is_symlink() or not (p.is_file() or p.is_dir()) for p in files):
        parser.error(
            "bundle must contain only regular files and directories (no symlinks)"
        )
    state = root / ".state/hokum"
    state.mkdir(parents=True, exist_ok=True)
    run = Path(tempfile.mkdtemp(prefix=time.strftime("run-%Y%m%d-%H%M%S-"), dir=state))
    run.chmod(0o700)
    frozen = run / "bundle"
    shutil.copytree(source, frozen)
    for name in ("hokum", "bombadil", "rune-driver"):
        (frozen / name).chmod(0o755)
    hashes = {
        str(p.relative_to(frozen)): hashlib.file_digest(
            p.open("rb"), "sha256"
        ).hexdigest()
        for p in sorted(frozen.rglob("*"))
        if p.is_file()
    }
    (run / "hashes.json").write_text(json.dumps(hashes, indent=2) + "\n")
    # nix-store --add does NOT register references. Scan embedded store paths
    # explicitly, including ELF interpreter/RPATH, without executing host code.
    references = set()
    for path in frozen.rglob("*"):
        if path.is_file() and path.stat().st_size:
            with (
                path.open("rb") as stream,
                mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as data,
            ):
                for match in re.finditer(
                    rb"/nix/store/[a-z0-9]{32}-[A-Za-z0-9+._?=-]+", data
                ):
                    reference = os.fsdecode(match[0])
                    if Path(reference).exists():
                        references.add(reference)
    store_bundle = command("nix-store", "--add", str(frozen))
    (run / "closure.txt").write_text(
        command("nix-store", "-qR", store_bundle, *sorted(references)) + "\n"
    )
    nixpkgs = command(
        "nix",
        "eval",
        "--impure",
        "--raw",
        "--expr",
        f"(builtins.getFlake {json.dumps(str(root))}).inputs.nixpkgs.outPath",
    )
    expr = (
        f"(import {Path(__file__).with_name('vm.nix')} {{ "
        f"pkgs = import {nixpkgs} {{}}; bundle = {store_bundle}; "
        f"backend = {json.dumps(args.backend)}; "
        f"dependencies = [ {' '.join(sorted(references))} ]; }}).driver"
    )
    (run / "build-expression.nix").write_text(expr + "\n")
    driver_root = command(
        "nix",
        "build",
        "--impure",
        "--expr",
        expr,
        "--out-link",
        str(run / "driver-build"),
        "--print-out-paths",
    )
    driver = str(Path(driver_root) / "bin/nixos-test-driver")
    request = {
        "bundle": str(frozen),
        "backend": args.backend,
        "time_limit_fuzz": args.time_limit_fuzz,
        "time_limit_run": args.time_limit_run,
        "driver": driver,
        "store_bundle": store_bundle,
    }
    if args.replay:
        shutil.copyfile(args.replay.resolve(strict=True), run / "input.bin")
        request["replay"] = str(run / "input.bin")
    (run / "request.json").write_text(json.dumps(request, indent=2) + "\n")
    print(f"run: {run}\ndriver: {driver}", flush=True)
    if args.build_only:
        return 0
    with tempfile.TemporaryDirectory(prefix="hokum-") as runtime:
        env = {
            **os.environ,
            "XDG_RUNTIME_DIR": runtime,
            "HOKUM_REQUEST": str(run / "request.json"),
        }
        # Ignore host VM overrides that could expose directories or devices.
        for key in list(env):
            if key.startswith("QEMU_") or key in {
                "SHARED_DIR",
                "NIX_DISK_IMAGE",
                "USE_TMPDIR",
            }:
                del env[key]
        with (run / "driver.log").open("w") as log:
            result = subprocess.run(
                [driver, "-o", str(run)],
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                check=False,
            )
    if result.returncode:
        return result.returncode
    return int((run / "artifacts/status").read_text())


if __name__ == "__main__":
    raise SystemExit(main())
