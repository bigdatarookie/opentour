#!/usr/bin/env python3
"""Stage and recover a versioned local OpenTour board release.

This helper never calls launchctl. It stages exact Git commits, makes SQLite
online backups, renders temporary LaunchAgent definitions, and offers a guarded
pre-traffic schema-3 rollback path.
"""
from __future__ import annotations

import argparse
import base64
import datetime as dt
import hashlib
import json
import os
import plistlib
import re
import shutil
import sqlite3
import stat
import subprocess
import sys
import tarfile
import tempfile
import uuid
from pathlib import Path, PurePosixPath


REPO = Path(__file__).resolve().parents[1]
LEGACY_SCHEMA = 3
UPGRADED_SCHEMA = 4
SERVICE_PREFIX = "com.opentour.board"
DEFAULT_PATH = "/Users/garry/Library/Application Support/OpenTour"
DEFAULT_PATH_ENV = "/Users/garry/.local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"


class ReleaseError(ValueError):
    """A release precondition failed; no activation is attempted."""


def _is_inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _outside_checkout(path: Path) -> Path:
    resolved = path.expanduser().absolute()
    if _is_inside(resolved, REPO) or ".artifacts" in resolved.parts:
        raise ReleaseError("path_must_be_outside_checkout_and_artifacts")
    return resolved


def _private_dir(path: Path, create: bool = False) -> Path:
    path = _outside_checkout(path)
    if create:
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        info = path.lstat()
    except OSError as exc:
        raise ReleaseError("private_directory_unavailable") from exc
    if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise ReleaseError("private_directory_invalid")
    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
        raise ReleaseError("private_directory_permissions_invalid")
    return path


def _private_file(path: Path) -> Path:
    path = _outside_checkout(path)
    try:
        info = path.lstat()
    except OSError as exc:
        raise ReleaseError("private_file_unavailable") from exc
    if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise ReleaseError("private_file_invalid")
    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
        raise ReleaseError("private_file_permissions_invalid")
    return path


def _connect_readonly(path: Path) -> sqlite3.Connection:
    path = _private_file(path)
    try:
        return sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=10)
    except sqlite3.Error as exc:
        raise ReleaseError("database_open_failed") from exc


def _schema_version(db: sqlite3.Connection) -> int:
    try:
        return int(db.execute("PRAGMA user_version").fetchone()[0])
    except sqlite3.Error as exc:
        raise ReleaseError("database_schema_unavailable") from exc


def _integrity(db: sqlite3.Connection) -> str:
    try:
        rows = db.execute("PRAGMA integrity_check").fetchall()
    except sqlite3.Error as exc:
        raise ReleaseError("database_integrity_check_failed") from exc
    if rows != [("ok",)]:
        raise ReleaseError("database_integrity_check_failed")
    return "ok"


def _tables(db: sqlite3.Connection) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for (name,) in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND (name NOT LIKE 'sqlite_%' OR name='sqlite_sequence') ORDER BY name"):
        escaped = name.replace('"', '""')
        result[name] = [row[1] for row in db.execute(f'PRAGMA table_info("{escaped}")')]
    return result


def _json_value(value):
    if isinstance(value, bytes):
        return {"bytes_b64": base64.b64encode(value).decode("ascii")}
    return {"type": type(value).__name__, "value": value}


def _logical_digest(db: sqlite3.Connection, schema: dict[str, list[str]], allowed_extra_tables=()) -> str:
    """Fingerprint table rows privately; return only a digest, never row values."""
    current = _tables(db)
    if set(current) - set(allowed_extra_tables) != set(schema):
        raise ReleaseError("database_table_set_changed_since_backup")
    digest = hashlib.sha256()
    for table in sorted(schema):
        columns = schema[table]
        if not columns or any(column not in current[table] for column in columns):
            raise ReleaseError("database_columns_changed_since_backup")
        table_sql = '"' + table.replace('"', '""') + '"'
        column_sql = ",".join('"' + c.replace('"', '""') + '"' for c in columns)
        try:
            rows = db.execute(f"SELECT {column_sql} FROM {table_sql} ORDER BY rowid")
            digest.update(table.encode("utf-8") + b"\0")
            for row in rows:
                raw = json.dumps([_json_value(value) for value in row], sort_keys=True,
                                 ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                digest.update(len(raw).to_bytes(8, "big") + raw)
        except sqlite3.Error as exc:
            raise ReleaseError("database_row_fingerprint_failed") from exc
    return digest.hexdigest()


def _assert_only_empty_pr20_columns(db: sqlite3.Connection, schema3: dict[str, list[str]]) -> None:
    """Reject any schema-4 fields/data beyond the exact nullable PR20 migration."""
    current = _tables(db)
    if set(current) != set(schema3):
        raise ReleaseError("database_schema_changed_beyond_pr20")
    additions = {"task_execution": {"destination"}, "outbox": {"routing_ref"}}
    for table, old_columns in schema3.items():
        extra = set(current[table]) - set(old_columns)
        expected = additions.get(table, set())
        if extra != expected:
            raise ReleaseError("database_schema_changed_beyond_pr20")
        for column in extra:
            table_sql = '"' + table.replace('"', '""') + '"'
            column_sql = '"' + column.replace('"', '""') + '"'
            if db.execute(f"SELECT 1 FROM {table_sql} WHERE {column_sql} IS NOT NULL LIMIT 1").fetchone():
                raise ReleaseError("rollback_refused_new_schema_data")


def _table_counts(db: sqlite3.Connection) -> dict[str, int]:
    counts = {}
    for table in _tables(db):
        escaped = table.replace('"', '""')
        counts[table] = int(db.execute(f'SELECT count(*) FROM "{escaped}"').fetchone()[0])
    return counts


def _fsync_file(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _make_release_readonly(root: Path, seal_root: bool = True) -> None:
    """Remove write bits from staged files/directories while preserving execution."""
    entries = sorted(root.rglob("*"), key=lambda path: len(path.parts), reverse=True)
    for path in entries:
        info = path.lstat()
        mode = stat.S_IMODE(info.st_mode)
        if stat.S_ISDIR(info.st_mode):
            os.chmod(path, 0o555)
        elif stat.S_ISREG(info.st_mode):
            os.chmod(path, mode & ~0o222)
        else:
            raise ReleaseError("staged_release_contains_unsupported_file")
    if seal_root:
        os.chmod(root, 0o555)


def _remove_staging_tree(root: Path) -> None:
    """Make a partially sealed staging tree removable, then discard it."""
    if not root.exists():
        return
    entries = list(root.rglob("*"))
    for path in entries:
        try:
            if path.is_dir() and not path.is_symlink():
                os.chmod(path, 0o700)
            else:
                os.chmod(path, 0o600)
        except OSError:
            pass
    try:
        os.chmod(root, 0o700)
    except OSError:
        pass
    shutil.rmtree(root, ignore_errors=True)


def backup_database(database: Path, backup_dir: Path) -> tuple[Path, Path, dict]:
    """Make a consistent, mode-0600 SQLite snapshot and private metadata sidecar."""
    database = _private_file(database.expanduser().absolute())
    backup_dir = _private_dir(backup_dir, create=True)
    src = _connect_readonly(database)
    try:
        version = _schema_version(src)
        _integrity(src)
        columns = _tables(src)
        digest = _logical_digest(src, columns)
        counts = _table_counts(src)
        stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        stem = f"board-schema{version}-{stamp}-{uuid.uuid4().hex[:8]}"
        target = backup_dir / f"{stem}.sqlite3"
        manifest = backup_dir / f"{stem}.json"
        fd, temp_name = tempfile.mkstemp(prefix=".board-backup-", suffix=".sqlite3", dir=backup_dir)
        os.close(fd)
        temp = Path(temp_name)
        try:
            dst = sqlite3.connect(temp)
            try:
                src.backup(dst)
                dst.commit()
                _integrity(dst)
                if _schema_version(dst) != version or _logical_digest(dst, columns) != digest:
                    raise ReleaseError("backup_snapshot_verification_failed")
            finally:
                dst.close()
            os.chmod(temp, 0o600)
            _fsync_file(temp)
            payload = {
                "format": 1,
                "database": target.name,
                "user_version": version,
                "table_columns": columns,
                "table_counts": counts,
                "logical_sha256": digest,
                "database_sha256": _file_sha256(temp),
                "created_at": stamp,
            }
            manifest_temp = backup_dir / f".{stem}.{uuid.uuid4().hex}.json.tmp"
            fd = os.open(manifest_temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(payload, stream, sort_keys=True, separators=(",", ":"))
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp, target)
            os.replace(manifest_temp, manifest)
            _fsync_dir(backup_dir)
        except BaseException:
            temp.unlink(missing_ok=True)
            raise
        return target, manifest, payload
    finally:
        src.close()


def _read_manifest(backup: Path) -> tuple[Path, dict]:
    backup = _private_file(backup.expanduser().absolute())
    manifest_path = backup.with_suffix(".json")
    manifest_path = _private_file(manifest_path)
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ReleaseError("backup_manifest_invalid") from exc
    if (manifest.get("format") != 1 or manifest.get("database") != backup.name
            or not isinstance(manifest.get("table_columns"), dict)):
        raise ReleaseError("backup_manifest_invalid")
    actual_hash = _file_sha256(backup)
    if actual_hash != manifest.get("database_sha256"):
        raise ReleaseError("backup_integrity_mismatch")
    return backup, manifest


def _restore_backup(database: Path, backup: Path, services_stopped: bool, old_schema, new_schema, guard, extra_tables=()) -> dict:
    """Restore a verified pre-migration snapshot only before any application effect."""
    if not services_stopped:
        raise ReleaseError("services_must_be_stopped_before_restore")
    database = _private_file(database.expanduser().absolute())
    backup, manifest = _read_manifest(backup)
    if manifest.get("user_version") != old_schema:
        raise ReleaseError("rollback_backup_must_be_schema3" if old_schema==3 else "rollback_backup_must_be_schema4")
    for suffix in ("-wal", "-shm"):
        if Path(str(database) + suffix).exists():
            raise ReleaseError("database_sidecar_present")
    src = _connect_readonly(backup)
    current = _connect_readonly(database)
    try:
        if _schema_version(src) != old_schema or _schema_version(current) != new_schema:
            raise ReleaseError("rollback_schema_versions_mismatch")
        _integrity(src)
        _integrity(current)
        columns = manifest["table_columns"]
        guard(current, columns)
        if _logical_digest(src, columns) != manifest.get("logical_sha256"):
            raise ReleaseError("backup_logical_fingerprint_mismatch")
        # The guard verifies the exact migration-only additions, all still empty.
        if _logical_digest(current, columns, extra_tables) != manifest.get("logical_sha256"):
            raise ReleaseError("rollback_refused_database_changed_since_backup")
        fd, temp_name = tempfile.mkstemp(prefix=f".{database.name}.restore-", suffix=".sqlite3", dir=database.parent)
        os.close(fd)
        temp = Path(temp_name)
        try:
            dst = sqlite3.connect(temp)
            try:
                src.backup(dst)
                dst.commit()
                _integrity(dst)
                if _schema_version(dst) != old_schema or _logical_digest(dst, columns) != manifest["logical_sha256"]:
                    raise ReleaseError("rollback_staging_verification_failed")
            finally:
                dst.close()
            os.chmod(temp, 0o600)
            _fsync_file(temp)
            os.replace(temp, database)
            _fsync_dir(database.parent)
        except BaseException:
            temp.unlink(missing_ok=True)
            raise
        return {"restored_schema": old_schema, "integrity": "ok", "table_counts": manifest["table_counts"]}
    finally:
        current.close()
        src.close()


def restore_schema3_backup(database: Path, backup: Path, services_stopped: bool) -> dict:
    return _restore_backup(database,backup,services_stopped,3,4,_assert_only_empty_pr20_columns)


def _assert_only_empty_v016_tables(db, schema4):
    current=_tables(db)
    extra={'client_conversations':['task_id'],
           'proposal_revisions':['task_id','revision','base_revision','title','body','author','author_role','source_message','created_at']}
    if current != {**schema4,**extra}:
        raise ReleaseError('database_schema_changed_beyond_v016')
    for table in extra:
        if db.execute('SELECT 1 FROM '+table+' LIMIT 1').fetchone():
            raise ReleaseError('rollback_refused_new_schema_data')


def restore_schema4_backup(database: Path, backup: Path, services_stopped: bool) -> dict:
    """Pre-traffic schema5->4 only; any saved message/receipt/edit/heartbeat refuses."""
    return _restore_backup(database,backup,services_stopped,4,5,_assert_only_empty_v016_tables,
                           ('client_conversations','proposal_revisions'))


def assert_local_services_stopped() -> None:
    """Fail closed unless the versioned LaunchAgents, listener and modules are absent."""
    if sys.platform != "darwin":
        raise ReleaseError("launchd_stop_verification_unsupported")
    try:
        jobs = subprocess.run(["launchctl", "list"], check=True, capture_output=True, text=True).stdout
        if any(line.split() and line.split()[-1].startswith(SERVICE_PREFIX + ".") for line in jobs.splitlines()):
            raise ReleaseError("opentour_launch_agent_still_loaded")
        listener = subprocess.run(["lsof", "-nP", "-iTCP:18083", "-sTCP:LISTEN"],
                                  capture_output=True, text=True)
        if listener.returncode == 0 and listener.stdout.strip():
            raise ReleaseError("opentour_backend_listener_still_running")
        if listener.returncode not in (0, 1):
            raise ReleaseError("listener_stop_check_unavailable")
        for module in ("backend.server", "backend.context_delivery"):
            result = subprocess.run(["pgrep", "-f", module], capture_output=True, text=True)
            if result.returncode == 0 and result.stdout.strip():
                raise ReleaseError("opentour_module_process_still_running")
            if result.returncode not in (0, 1):
                raise ReleaseError("process_stop_check_unavailable")
    except OSError as exc:
        raise ReleaseError("launchd_stop_check_unavailable") from exc


def stage_release(repo: Path, revision: str, release_root: Path) -> tuple[Path, dict]:
    """Extract an exact Git archive into a new versioned directory atomically."""
    repo = repo.expanduser().resolve()
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ReleaseError("revision_must_be_full_commit_sha")
    release_root = _outside_checkout(release_root.expanduser().absolute())
    release_root.mkdir(mode=0o755, parents=True, exist_ok=True)
    info = release_root.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o022:
        raise ReleaseError("release_root_permissions_invalid")
    commit = subprocess.run(["git", "-C", str(repo), "rev-parse", "--verify", f"{revision}^{{commit}}"],
                            check=True, capture_output=True, text=True).stdout.strip()
    if commit != revision:
        raise ReleaseError("revision_resolution_mismatch")
    tree = subprocess.run(["git", "-C", str(repo), "rev-parse", f"{revision}^{{tree}}"],
                          check=True, capture_output=True, text=True).stdout.strip()
    destination = release_root / revision[:7]
    if destination.exists():
        raise ReleaseError("release_destination_already_exists")
    temp = release_root / f".{revision[:7]}.staging-{uuid.uuid4().hex}"
    temp.mkdir(mode=0o755)
    proc = subprocess.Popen(["git", "-C", str(repo), "archive", "--format=tar", revision],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        with tarfile.open(fileobj=proc.stdout, mode="r|") as archive:
            for member in archive:
                rel = PurePosixPath(member.name)
                if rel.is_absolute() or any(part in ("", ".", "..") for part in rel.parts):
                    raise ReleaseError("unsafe_archive_path")
                target = temp.joinpath(*rel.parts)
                if member.isdir():
                    target.mkdir(mode=0o755, parents=True, exist_ok=True)
                    continue
                if not member.isfile():
                    raise ReleaseError("archive_links_and_special_files_are_refused")
                target.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
                source = archive.extractfile(member)
                if source is None:
                    raise ReleaseError("archive_member_unavailable")
                fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
                with source, os.fdopen(fd, "wb") as output:
                    shutil.copyfileobj(source, output)
                    output.flush()
                    os.fsync(output.fileno())
                os.chmod(target, (member.mode & 0o755) or 0o644)
        if proc.stdout:
            proc.stdout.close()
        stderr = proc.stderr.read() if proc.stderr else b""
        if proc.stderr:
            proc.stderr.close()
        status = proc.wait()
        if status:
            raise ReleaseError("git_archive_failed")
        # Keep the staging root writable until the atomic directory rename; on
        # macOS rename requires write access to the source directory itself.
        _make_release_readonly(temp, seal_root=False)
        os.replace(temp, destination)
        temp = destination
        os.chmod(temp, 0o555)
        _fsync_dir(release_root)
    except BaseException:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
        _remove_staging_tree(temp)
        raise
    return destination, {"commit": commit, "tree": tree, "archive_stderr_bytes": len(stderr)}


def render_launch_agents(release_dir: Path, app_root: Path, python: Path,
                         auth_file: Path, database: Path, output_dir: Path,
                         crm_credential_file: Path | None = None, client_controls_file: Path | None = None,
                         crm_control_credential_file: Path | None = None) -> list[Path]:
    """Render and parse two plist fixtures; deliberately never loads them."""
    release_dir = release_dir.expanduser().absolute()
    app_root = _outside_checkout(app_root)
    output_dir = _private_dir(output_dir, create=True)
    python = python.expanduser().absolute()
    if not release_dir.is_dir() or not python.is_absolute():
        raise ReleaseError("release_runtime_paths_invalid")
    revision = release_dir.name
    if not re.fullmatch(r"[0-9a-f]{7,40}", revision):
        raise ReleaseError("release_directory_must_be_versioned")
    auth_file = auth_file.expanduser().absolute()
    database = database.expanduser().absolute()
    logs = app_root / "logs"
    home = str(Path.home())
    prefix = revision[:7]
    base = ["/usr/bin/env", "-i", f"PATH={DEFAULT_PATH_ENV}", f"HOME={home}", "LANG=en_US.UTF-8", str(python), "-m"]
    specs = {
        "server": ("backend.server", ["--port", "18083", "--auth-file", str(auth_file), "--board-db", str(database)]),
        "worker": ("backend.context_delivery", ["--board-db", str(database), "--serve", "--service", "--interval", "2", "--limit", "20"]),
    }
    references={"--crm-credential-file":crm_credential_file,"--client-controls-file":client_controls_file,"--crm-control-credential-file":crm_control_credential_file}
    for flag, reference in references.items():
        if reference is not None:specs['server'][1].extend([flag,str(_private_file(reference.expanduser().absolute()))])
    paths = []
    for role, (module, args) in specs.items():
        label = f"{SERVICE_PREFIX}.{role}.{prefix}"
        data = {
            "Label": label,
            "ProgramArguments": base + [module] + args,
            "WorkingDirectory": str(release_dir),
            "RunAtLoad": True,
            "KeepAlive": True,
            "StandardOutPath": str(logs / f"{label}.stdout.log"),
            "StandardErrorPath": str(logs / f"{label}.stderr.log"),
        }
        path = output_dir / f"{label}.plist"
        raw = plistlib.dumps(data, fmt=plistlib.FMT_XML, sort_keys=True)
        parsed = plistlib.loads(raw)
        if parsed != data:
            raise ReleaseError("launch_agent_roundtrip_failed")
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        paths.append(path)
    validate_launch_agents(paths, release_dir, database, auth_file,crm_credential_file,client_controls_file,crm_control_credential_file)
    _fsync_dir(output_dir)
    return paths


def validate_launch_agents(paths: list[Path], release_dir: Path, database: Path, auth_file: Path,
                          crm_credential_file: Path | None = None, client_controls_file: Path | None = None,
                         crm_control_credential_file: Path | None = None) -> dict:
    if len(paths) != 2:
        raise ReleaseError("exactly_two_launch_agents_required")
    records = []
    for path in paths:
        _private_file(path)
        try:
            data = plistlib.loads(path.read_bytes())
        except Exception as exc:
            raise ReleaseError("launch_agent_plist_invalid") from exc
        if sys.platform == "darwin":
            try:
                subprocess.run(["plutil", "-lint", str(path)], check=True,
                               capture_output=True, text=True)
            except (OSError, subprocess.SubprocessError) as exc:
                raise ReleaseError("launch_agent_plutil_validation_failed") from exc
        args = data.get("ProgramArguments")
        if not isinstance(args, list) or "-m" not in args:
            raise ReleaseError("launch_agent_arguments_invalid")
        module = args[args.index("-m") + 1]
        role = "server" if module == "backend.server" else "worker" if module == "backend.context_delivery" else "unknown"
        if role == "unknown" or data.get("WorkingDirectory") != str(release_dir):
            raise ReleaseError("launch_agent_release_mismatch")
        if data.get("RunAtLoad") is not True or data.get("KeepAlive") is not True:
            raise ReleaseError("launch_agent_lifecycle_policy_invalid")
        if "--board-db" not in args or args[args.index("--board-db") + 1] != str(database):
            raise ReleaseError("launch_agent_database_mismatch")
        if role == "server":
            if "--auth-file" not in args or args[args.index("--auth-file") + 1] != str(auth_file):
                raise ReleaseError("launch_agent_auth_reference_mismatch")
            for flag,reference in {"--crm-credential-file":crm_credential_file,"--client-controls-file":client_controls_file,"--crm-control-credential-file":crm_control_credential_file}.items():
                if reference is None:
                    if flag in args:raise ReleaseError("release_profile_must_not_add_crm_credentials" if flag=="--crm-credential-file" else "release_profile_unexpected_client_controls")
                elif (args.count(flag)!=1 or args.index(flag)+1>=len(args)
                      or args[args.index(flag)+1]!=str(_private_file(reference.expanduser().absolute()))):
                    raise ReleaseError("launch_agent_private_reference_mismatch")
        else:
            if not {"--serve", "--service"}.issubset(args):
                raise ReleaseError("launch_agent_worker_mode_invalid")
            if any(name in " ".join(args) for name in ("OPENRIG_SESSION_NAME", "OPENRIG_NODE_ID")):
                raise ReleaseError("worker_must_not_claim_seat_identity")
        records.append({"role": role, "label": data.get("Label"), "module": module})
    if {record["role"] for record in records} != {"server", "worker"}:
        raise ReleaseError("server_worker_pair_incomplete")
    if len({record["label"] for record in records}) != 2:
        raise ReleaseError("launch_agent_labels_not_unique")
    return {"valid": True, "agents": records, "loaded": False}


def inspect_database(path: Path) -> dict:
    db = _connect_readonly(path.expanduser().absolute())
    try:
        return {"user_version": _schema_version(db), "integrity": _integrity(db), "table_counts": _table_counts(db)}
    finally:
        db.close()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    stage = sub.add_parser("stage", help="extract an exact Git commit to a new versioned release directory")
    stage.add_argument("--repo", type=Path, required=True)
    stage.add_argument("--revision", required=True)
    stage.add_argument("--release-root", type=Path, required=True)
    backup = sub.add_parser("backup", help="make a private SQLite online backup and metadata sidecar")
    backup.add_argument("--database", type=Path, required=True)
    backup.add_argument("--backup-dir", type=Path, required=True)
    restore = sub.add_parser("restore", help="restore an unchanged schema-3 backup before PR20 traffic")
    restore.add_argument("--database", type=Path, required=True)
    restore.add_argument("--backup", type=Path, required=True)
    restore.add_argument("--assert-services-stopped", action="store_true", required=True,
                         help="operator confirms both LaunchAgents are unloaded and processes exited")
    restore4 = sub.add_parser("restore-v4", help="restore unchanged schema-4 snapshot before any v016 traffic")
    restore4.add_argument("--database", type=Path, required=True)
    restore4.add_argument("--backup", type=Path, required=True)
    restore4.add_argument("--assert-services-stopped", action="store_true", required=True)
    agents = sub.add_parser("render-agents", help="write and validate candidate plists without loading them")
    agents.add_argument("--release-dir", type=Path, required=True)
    agents.add_argument("--app-root", type=Path, required=True)
    agents.add_argument("--python", type=Path, required=True)
    agents.add_argument("--auth-file", type=Path, required=True)
    agents.add_argument("--database", type=Path, required=True)
    agents.add_argument("--output-dir", type=Path, required=True)
    agents.add_argument("--crm-credential-file", type=Path, help="Explicit existing private GET-only CRM reference; contents never read by renderer")
    agents.add_argument("--client-controls-file", type=Path, help="Explicit private exact client/obligation bindings; contents never read by renderer")
    agents.add_argument("--crm-control-credential-file", type=Path, help="Separate exact Contact.title capability reference; never the GET API key/admin credential")
    inspect = sub.add_parser("inspect", help="read schema, integrity and aggregate table counts")
    inspect.add_argument("--database", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "stage":
            path, receipt = stage_release(args.repo, args.revision, args.release_root)
            result = {"release_dir": str(path), **receipt}
        elif args.command == "backup":
            path, manifest, info = backup_database(args.database, args.backup_dir)
            result = {"backup": str(path), "manifest": str(manifest), "user_version": info["user_version"],
                      "integrity": "ok", "table_counts": info["table_counts"]}
        elif args.command in ("restore","restore-v4"):
            assert_local_services_stopped()
            restore_fn=restore_schema4_backup if args.command=="restore-v4" else restore_schema3_backup
            result = restore_fn(args.database, args.backup, args.assert_services_stopped)
        elif args.command == "render-agents":
            paths = render_launch_agents(args.release_dir, args.app_root, args.python,
                                         args.auth_file, args.database, args.output_dir,args.crm_credential_file,args.client_controls_file,args.crm_control_credential_file)
            result = {"plists": [str(path) for path in paths],
                      **validate_launch_agents(paths, args.release_dir.absolute(), args.database.absolute(), args.auth_file.absolute(),args.crm_credential_file,args.client_controls_file,args.crm_control_credential_file)}
        else:
            result = inspect_database(args.database)
    except (ReleaseError, OSError, sqlite3.Error, subprocess.SubprocessError) as exc:
        print(json.dumps({"ok": False, "error": str(exc) if isinstance(exc, ReleaseError) else "operation_failed"}, sort_keys=True))
        return 2
    print(json.dumps({"ok": True, **result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
