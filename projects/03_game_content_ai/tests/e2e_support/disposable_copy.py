"""
T7: Disposable Project Copy構築ヘルパー。

docs/design/mvp_end_to_end_hardening_validation.md 7.5.3節が確定した
exact whitelist（「その他」の余地を残さないclosed-world whitelist）に
基づき、シナリオA・B・C・F1が実subprocessを起動するための使い捨てコピーを
新規構築するtest-only helper。既存実装の再利用ではなく新規構築である
（7.5.3節・用語集）。

コピー対象（exact whitelist、これ以外は一切コピーしない）：
  1. src/ 配下の全ての *.py（再帰的、__pycache__以下は除く）
  2. scripts/ 配下の全ての *.py（フラット構成）
  3. main.py
  4. .env.example
  5. requirements.txt
  6. prompts/ 配下の全ての *.md

venvはコピーしない（既存プロジェクトのvenvを絶対パスで参照する）。
"""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from pathlib import Path
from typing import Optional


def _copy_py_tree(src_dir: Path, dest_dir: Path) -> None:
    for path in src_dir.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        rel = path.relative_to(src_dir)
        dest = dest_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dest)


def _copy_flat_py(src_dir: Path, dest_dir: Path) -> None:
    dest_dir.mkdir(parents=True, exist_ok=True)
    for path in src_dir.glob("*.py"):
        shutil.copy2(path, dest_dir / path.name)


class DisposableProjectCopy:
    """7.5.3節のexact whitelistに基づく使い捨てプロジェクトコピー。

    使用例::

        with DisposableProjectCopy(PROJECT_ROOT) as copy:
            subprocess.run([str(copy.venv_python), str(copy.main_py)], cwd=copy.root, ...)
    """

    def __init__(self, project_root: Path, keep: Optional[bool] = None):
        self.project_root = Path(project_root).resolve()
        self._tmp_parent: Optional[str] = None
        self.root: Optional[Path] = None
        # 既定は削除、保持は明示的opt-inのみ（DISPOSABLE_COPY_KEEP=1、7.5.3節）
        if keep is None:
            keep = os.environ.get("DISPOSABLE_COPY_KEEP") == "1"
        self._keep = keep

    def build(self) -> "DisposableProjectCopy":
        self._tmp_parent = tempfile.mkdtemp(prefix="disposable_copy_")
        root = Path(self._tmp_parent) / "copy"
        root.mkdir(parents=True, exist_ok=False)

        _copy_py_tree(self.project_root / "src", root / "src")
        _copy_flat_py(self.project_root / "scripts", root / "scripts")
        shutil.copy2(self.project_root / "main.py", root / "main.py")
        shutil.copy2(self.project_root / ".env.example", root / ".env.example")
        shutil.copy2(self.project_root / "requirements.txt", root / "requirements.txt")

        prompts_src = self.project_root / "prompts"
        prompts_dest = root / "prompts"
        prompts_dest.mkdir(parents=True, exist_ok=True)
        for path in prompts_src.glob("*.md"):
            shutil.copy2(path, prompts_dest / path.name)

        self.root = root
        return self

    def teardown(self) -> None:
        if self._keep:
            return
        if self._tmp_parent is not None and Path(self._tmp_parent).exists():
            shutil.rmtree(self._tmp_parent, ignore_errors=True)

    def __enter__(self) -> "DisposableProjectCopy":
        return self.build()

    def __exit__(self, exc_type, exc, tb) -> None:
        self.teardown()

    # ── 参照用パス ─────────────────────────────────────────────
    @property
    def main_py(self) -> Path:
        assert self.root is not None
        return self.root / "main.py"

    @property
    def src_dir(self) -> Path:
        assert self.root is not None
        return self.root / "src"

    @property
    def venv_python(self) -> Path:
        """venvはコピーしない。既存プロジェクトのvenvを絶対パスで参照する。"""
        return self.project_root / "venv" / "Scripts" / "python.exe"


# ── Zero-Diff証拠契約（7.5.3節）────────────────────────────────
# Original Project側（実リポジトリのプロジェクトルート）が、シナリオ実行の
# 前後で1バイトも変化していないことを確認するためのbefore/after manifest。
_ZERO_DIFF_EXCLUDED_DIR_NAMES = {".git", "venv"}


def capture_manifest(project_root: Path) -> dict[str, str]:
    """project_root配下（.git/・venv/を除く）の相対パス→SHA-256ハッシュを
    再帰的に収集する。"""
    project_root = Path(project_root).resolve()
    manifest: dict[str, str] = {}
    for dirpath, dirnames, filenames in os.walk(project_root):
        dirnames[:] = [d for d in dirnames if d not in _ZERO_DIFF_EXCLUDED_DIR_NAMES]
        for filename in filenames:
            file_path = Path(dirpath) / filename
            rel = file_path.relative_to(project_root).as_posix()
            manifest[rel] = _sha256_of(file_path)
    return manifest


def _sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def diff_manifests(before: dict[str, str], after: dict[str, str]) -> list[str]:
    """2つのmanifestを比較し、差分を人間可読な説明のリストとして返す
    （空リスト＝完全一致＝Zero-Diff）。"""
    issues: list[str] = []
    before_paths = set(before)
    after_paths = set(after)
    for added in sorted(after_paths - before_paths):
        issues.append(f"unexpected new file: {added}")
    for removed in sorted(before_paths - after_paths):
        issues.append(f"unexpectedly removed file: {removed}")
    for common in sorted(before_paths & after_paths):
        if before[common] != after[common]:
            issues.append(f"unexpected content change: {common}")
    return issues
