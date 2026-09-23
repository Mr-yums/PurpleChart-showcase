"""Package only committed sources and the separately verified market archives."""

import hashlib
import json
import subprocess
import tarfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
version = json.loads((root / "frontend/package.json").read_text())["version"]
files = subprocess.check_output(["git", "ls-files"], cwd=root, text=True).splitlines()
assert len(set(p.casefold() for p in files)) == len(files)
manifest = json.loads((root / "data/manifest.json").read_text())
for name, entry in manifest["files"].items():
    assert name in {
        "replay_archive.sqlite",
        "purplechart_v2_archive.sqlite",
        "gex_qqq.db",
    }
    path = root / "data" / name
    assert hashlib.file_digest(path.open("rb"), "sha256").hexdigest() == entry["sha256"]
    files.append("data/" + name)
for name in files:
    assert not any(
        p in {".git", ".venv", "node_modules", "__pycache__", "dist", "releases"}
        for p in Path(name).parts
    )
    assert not (root / name).is_symlink()
    assert Path(name).name not in {".env", "compose.override.yaml"}
out = root / "releases"
out.mkdir(exist_ok=True)
archive = out / f"purple-replay-{version}.tar.gz"
temporary = archive.with_suffix(".tmp")
with tarfile.open(temporary, "w:gz", compresslevel=1) as tar:
    directories = {"purple-replay"}
    for name in files:
        directories.update(
            "purple-replay/" + str(parent)
            for parent in Path(name).parents
            if str(parent) != "."
        )
    for name in sorted(directories):
        info = tarfile.TarInfo(name)
        info.type = tarfile.DIRTYPE
        info.mode = 0o755
        tar.addfile(info)
    for name in sorted(files):
        path = root / name
        info = tar.gettarinfo(path, arcname="purple-replay/" + name)
        info.uid = info.gid = 0
        info.uname = info.gname = ""
        info.mode = 0o755 if name == "scripts/check" else 0o644
        with path.open("rb") as stream:
            tar.addfile(info, stream)
temporary.replace(archive)
sha = hashlib.file_digest(archive.open("rb"), "sha256").hexdigest()
(out / "SHA256SUMS").write_text(sha + "  " + archive.name + "\n")
print(
    json.dumps({"files": len(files), "bytes": archive.stat().st_size, "sha256": sha}),
    flush=True,
)
