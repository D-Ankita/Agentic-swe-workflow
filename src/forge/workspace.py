from __future__ import annotations

import hashlib
import os
import tempfile
from dataclasses import asdict
from pathlib import Path

from .models import ChangeSet, FileEdit


class EditRejected(RuntimeError):
    pass


class WorkspaceEditor:
    """Validates then atomically applies bounded, root-confined file edits."""

    def __init__(self, root: Path, *, max_files: int = 20, max_bytes: int = 500_000):
        self.root = root.resolve()
        self.max_files, self.max_bytes = max_files, max_bytes

    def _target(self, relative: str) -> Path:
        path = Path(relative)
        if path.is_absolute() or ".." in path.parts or not path.parts:
            raise EditRejected(f"Unsafe path: {relative}")
        cursor = self.root
        for part in path.parts:
            cursor = cursor / part
            if cursor.is_symlink():
                raise EditRejected(f"Symlink paths are not editable: {relative}")
        return self.root.joinpath(path)

    @staticmethod
    def digest(content: bytes) -> str:
        return hashlib.sha256(content).hexdigest()

    def validate(self, changes: ChangeSet) -> list[tuple[FileEdit, Path]]:
        if len(changes.edits) > self.max_files:
            raise EditRejected(f"Change set exceeds {self.max_files} files")
        if len({edit.path for edit in changes.edits}) != len(changes.edits):
            raise EditRejected("Change set contains duplicate paths")
        if sum(len((edit.content or "").encode()) for edit in changes.edits) > self.max_bytes:
            raise EditRejected(f"Change set exceeds {self.max_bytes} bytes")
        validated = []
        for edit in changes.edits:
            target = self._target(edit.path)
            exists = target.is_file()
            if edit.action == "create" and exists:
                raise EditRejected(f"Create target already exists: {edit.path}")
            if edit.action in {"update", "delete"} and not exists:
                raise EditRejected(f"Target does not exist: {edit.path}")
            if edit.action in {"update", "delete"} and not edit.expected_sha256:
                raise EditRejected(f"Update/delete requires expected_sha256: {edit.path}")
            if edit.expected_sha256 and self.digest(target.read_bytes()) != edit.expected_sha256:
                raise EditRejected(f"Precondition failed: {edit.path}")
            validated.append((edit, target))
        return validated

    def apply(self, changes: ChangeSet) -> list[dict[str, object]]:
        validated = self.validate(changes)
        results = []
        for edit, target in validated:
            if edit.action == "delete":
                target.unlink()
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                fd, temporary = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.")
                try:
                    with os.fdopen(fd, "w", encoding="utf-8") as stream:
                        stream.write(edit.content or "")
                    os.replace(temporary, target)
                finally:
                    if os.path.exists(temporary):
                        os.unlink(temporary)
            results.append(asdict(edit) | {"applied": True})
        return results
