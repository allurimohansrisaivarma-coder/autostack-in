"""Safe filesystem writes (S5): traversal/junction rejection, staged atomic replace, backups.

read_snapshot() in backend/file_diff.py already proves bounded *reading*; this module proves
bounded *writing* to a declared resource alias — the write half of S5 for the spike.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from pathlib import Path

from backend.spike_config import DATA_DIR

# Resource aliases -> directories (declared scope; a path string never grants access).
RESOURCE_DIRS: dict[str, Path] = {
    "sample-tracking-file": DATA_DIR / "resources" / "sample-tracking-file",
    "spike-scratch": DATA_DIR / "resources" / "spike-scratch",
    "invoice-register": DATA_DIR / "resources" / "invoice-register",
}


def _ensure_dirs() -> None:
    for d in RESOURCE_DIRS.values():
        d.mkdir(parents=True, exist_ok=True)


# Dated archive subfolders only: resolve_resource() accepts exactly this one nested
# shape ("archive-YYYY-MM-DD/<plain-name>") so file.archive can file snapshots into
# a dated folder without reopening the resolver to arbitrary nesting.
_DATED_ARCHIVE = "archive-"


def resolve_resource(alias: str, filename: str) -> Path:
    """Resolve alias+filename safely: reject traversal, absolute paths, symlinks/junctions.

    Raises PermissionError on any escape attempt (S5 fail-closed). The only nested
    form allowed is a first-level dated archive folder (see _DATED_ARCHIVE).
    """
    _ensure_dirs()
    if alias not in RESOURCE_DIRS:
        raise PermissionError(f"unknown resource alias: {alias}")
    base = RESOURCE_DIRS[alias].resolve()
    if not filename or filename in {".", ".."}:
        raise PermissionError(f"unsafe filename: {filename!r}")
    parts = [p for p in Path(filename).parts if p not in ("", ".")]
    if len(parts) == 2 and parts[0].startswith(_DATED_ARCHIVE) and Path(parts[1]).name == parts[1]:
        filename = str(Path(*parts))
    elif Path(filename).name != filename:
        raise PermissionError(f"unsafe filename: {filename!r}")
    candidate = (base / filename)
    # Reject symlink/junction components anywhere under the resource dir.
    for part in [base, *candidate.parents]:
        if part.exists() and (part.is_symlink() or part.resolve() != part):
            raise PermissionError(f"link in path: {part}")
    resolved = candidate.resolve()
    if base != resolved and base not in resolved.parents:
        raise PermissionError("path escapes resource directory")
    return resolved


def read_resource(alias: str, filename: str) -> bytes:
    path = resolve_resource(alias, filename)
    if not path.is_file():
        raise FileNotFoundError(f"resource not found: {alias}/{filename}")
    return path.read_bytes()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_resource(alias: str, filename: str, data: bytes, *, backup: bool = True) -> dict:
    """Staged write: temp file in same dir -> fsync -> atomic os.replace. Optional .bak.

    Returns {sha256, bytes, backup} so the caller can journal the effect with a digest.
    """
    path = resolve_resource(alias, filename)
    _ensure_dirs()
    # Dated archive subfolder may not exist yet — create it (resolver already
    # confined the path inside the resource directory).
    path.parent.mkdir(parents=True, exist_ok=True)
    existed = path.exists()
    if existed and backup:
        shutil.copy2(path, path.with_suffix(path.suffix + ".bak"))
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=".as-tmp-", suffix=".part")
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp_path, path)  # atomic on same volume
    finally:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
    return {"sha256": sha256_bytes(data), "bytes": len(data), "backup": existed and backup}
