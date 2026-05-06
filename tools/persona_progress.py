"""Backup and restore local PersonaPet progress outside git.

Default backup contents are intentionally limited to long-term progress:
- outputs/memory
- outputs/life

API keys in persona_llm_config.json are private and are only included when
--include-config is passed explicitly.
"""

import argparse
import json
import os
import shutil
import sys
import time
import zipfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BACKUP_ROOT = REPO_ROOT / "user_data_backups"
DEFAULT_PROGRESS_DIRS = (
    Path("outputs") / "memory",
    Path("outputs") / "life",
)
ALL_OUTPUT_DIR = Path("outputs")
CONFIG_FILE = Path("persona_llm_config.json")


def iter_files(base_path):
    if not base_path.exists():
        return
    if base_path.is_file():
        yield base_path
        return
    for path in base_path.rglob("*"):
        if path.is_file():
            yield path


def safe_rel(path):
    rel = path.resolve().relative_to(REPO_ROOT.resolve())
    return rel.as_posix()


def default_backup_name():
    return f"persona_progress_{time.strftime('%Y%m%d_%H%M%S')}.zip"


def backup(args):
    backup_root = Path(args.backup_root).expanduser().resolve()
    backup_root.mkdir(parents=True, exist_ok=True)
    backup_path = backup_root / default_backup_name()
    roots = [ALL_OUTPUT_DIR] if args.all_outputs else list(DEFAULT_PROGRESS_DIRS)
    files = []
    for rel_root in roots:
        files.extend(iter_files(REPO_ROOT / rel_root) or [])
    if args.include_config and (REPO_ROOT / CONFIG_FILE).exists():
        files.append(REPO_ROOT / CONFIG_FILE)
    files = sorted(set(files))
    manifest = {
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "repo": str(REPO_ROOT),
        "default_progress_only": not args.all_outputs,
        "include_config": bool(args.include_config),
        "files": [safe_rel(path) for path in files],
    }
    with zipfile.ZipFile(backup_path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("persona_progress_manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        for path in files:
            archive.write(path, safe_rel(path))
    print(f"BACKUP_CREATED {backup_path}")
    print(f"FILES {len(files)}")
    if not args.include_config:
        print("CONFIG_SKIPPED persona_llm_config.json")
    return 0


def list_backups(args):
    backup_root = Path(args.backup_root).expanduser().resolve()
    if not backup_root.exists():
        print(f"NO_BACKUP_DIR {backup_root}")
        return 0
    backups = sorted(backup_root.glob("persona_progress_*.zip"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not backups:
        print(f"NO_BACKUPS {backup_root}")
        return 0
    for path in backups:
        size_mb = path.stat().st_size / (1024 * 1024)
        print(f"{path.name}\t{size_mb:.2f} MB\t{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(path.stat().st_mtime))}")
    return 0


def ensure_safe_member(member_name):
    normalized = Path(member_name)
    if normalized.is_absolute() or ".." in normalized.parts:
        raise RuntimeError(f"Unsafe archive member: {member_name}")
    return normalized


def restore(args):
    archive_path = Path(args.archive).expanduser().resolve()
    if not archive_path.exists():
        print(f"BACKUP_NOT_FOUND {archive_path}", file=sys.stderr)
        return 2
    restored = 0
    skipped = 0
    with zipfile.ZipFile(archive_path, "r") as archive:
        for info in archive.infolist():
            if info.is_dir() or info.filename == "persona_progress_manifest.json":
                continue
            rel = ensure_safe_member(info.filename)
            if rel == CONFIG_FILE and not args.include_config:
                skipped += 1
                continue
            if not args.all_outputs:
                allowed = any(rel == root or root in rel.parents for root in DEFAULT_PROGRESS_DIRS)
                allowed = allowed or (args.include_config and rel == CONFIG_FILE)
                if not allowed:
                    skipped += 1
                    continue
            target = (REPO_ROOT / rel).resolve()
            if REPO_ROOT.resolve() not in target.parents and target != REPO_ROOT.resolve():
                raise RuntimeError(f"Restore target escaped repo: {target}")
            if target.exists() and not args.force:
                skipped += 1
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info, "r") as source, open(target, "wb") as dest:
                shutil.copyfileobj(source, dest)
            restored += 1
    print(f"RESTORED {restored}")
    print(f"SKIPPED {skipped}")
    if not args.force:
        print("NOTE existing files are skipped; pass --force to overwrite local progress")
    if not args.include_config:
        print("CONFIG_SKIPPED pass --include-config to restore persona_llm_config.json")
    return 0


def build_parser():
    parser = argparse.ArgumentParser(description="Backup/restore PersonaPet local progress without committing private data.")
    parser.add_argument("--backup-root", default=str(DEFAULT_BACKUP_ROOT), help="Backup folder outside the repo.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    backup_parser = subparsers.add_parser("backup", help="Create a progress backup zip.")
    backup_parser.add_argument("--include-config", action="store_true", help="Also include persona_llm_config.json with API keys.")
    backup_parser.add_argument("--all-outputs", action="store_true", help="Backup the whole outputs directory, including voice/screenshots.")
    backup_parser.set_defaults(func=backup)

    list_parser = subparsers.add_parser("list", help="List existing progress backups.")
    list_parser.set_defaults(func=list_backups)

    restore_parser = subparsers.add_parser("restore", help="Restore a progress backup zip.")
    restore_parser.add_argument("archive", help="Path to persona_progress_*.zip.")
    restore_parser.add_argument("--include-config", action="store_true", help="Restore persona_llm_config.json from the backup.")
    restore_parser.add_argument("--all-outputs", action="store_true", help="Restore every outputs/* file in the backup.")
    restore_parser.add_argument("--force", action="store_true", help="Overwrite existing local progress files.")
    restore_parser.set_defaults(func=restore)
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
