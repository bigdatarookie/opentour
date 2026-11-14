from __future__ import annotations

import io
import os
import plistlib
import sqlite3
import stat
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.local_board_release import (
    ReleaseError,
    backup_database,
    inspect_database,
    render_launch_agents,
    restore_schema3_backup,
    stage_release,
    validate_launch_agents,
)


def make_schema3(path: Path) -> None:
    db = sqlite3.connect(path)
    db.executescript("""
        CREATE TABLE tasks(id TEXT PRIMARY KEY, title TEXT NOT NULL);
        CREATE TABLE task_execution(task_id TEXT PRIMARY KEY REFERENCES tasks(id), native_ref TEXT NOT NULL);
        CREATE TABLE outbox(id TEXT PRIMARY KEY, message_id TEXT NOT NULL, destination TEXT NOT NULL,
          native_id TEXT NOT NULL, payload TEXT NOT NULL, digest TEXT NOT NULL, state TEXT NOT NULL,
          error TEXT, processing TEXT NOT NULL, updated_at TEXT NOT NULL, sender TEXT NOT NULL,
          native_body TEXT, delivered_at TEXT, received_at TEXT, accepted_at TEXT, continued_at TEXT,
          processing_reason TEXT, result_text TEXT, evidence_ref TEXT);
        INSERT INTO tasks VALUES('task_synthetic_01','synthetic fixture only');
        INSERT INTO task_execution VALUES('task_synthetic_01','qitem-synthetic-01');
        INSERT INTO outbox VALUES('delivery_synthetic_01','message_synthetic_01','operator-agent@kernel',
          'qitem-delivery-synthetic-01','synthetic payload','synthetic digest','delivered',NULL,
          'continued','2026-01-01T00:00:00Z','platform-developer@opentour-rig','synthetic body',
          '2026-01-01T00:00:01Z','2026-01-01T00:00:02Z','2026-01-01T00:00:03Z',
          '2026-01-01T00:00:04Z',NULL,'synthetic result','qitem-synthetic-01');
        PRAGMA user_version=3;
    """)
    db.commit()
    db.close()
    os.chmod(path, 0o600)


def migrate_legacy_schema4(path):
    # Exercise the retained schema3->4 rollback contract, not today's schema5 upgrade.
    with sqlite3.connect(path) as db:
        db.execute('ALTER TABLE task_execution ADD COLUMN destination TEXT')
        db.execute('ALTER TABLE outbox ADD COLUMN routing_ref TEXT')
        db.execute('PRAGMA user_version=4')


class LocalBoardReleaseTests(unittest.TestCase):
    def test_schema3_backup_migrates_and_pretraffic_restore_preserves_rows(self):
        with tempfile.TemporaryDirectory(prefix="opentour-release-test-") as raw:
            root = Path(raw)
            db_path = root / "board.sqlite3"
            backup_dir = root / "backups"
            make_schema3(db_path)

            backup, manifest, receipt = backup_database(db_path, backup_dir)
            self.assertEqual(receipt["user_version"], 3)
            self.assertEqual(receipt["table_counts"]["outbox"], 1)
            self.assertEqual(backup.stat().st_mode & 0o777, 0o600)
            self.assertEqual(manifest.stat().st_mode & 0o777, 0o600)

            migrate_legacy_schema4(db_path)
            migrated = inspect_database(db_path)
            self.assertEqual(migrated["user_version"], 4)
            self.assertEqual(migrated["integrity"], "ok")
            self.assertEqual(migrated["table_counts"]["tasks"], 1)
            self.assertEqual(migrated["table_counts"]["outbox"], 1)

            with self.assertRaisesRegex(ReleaseError, "services_must_be_stopped"):
                restore_schema3_backup(db_path, backup, services_stopped=False)
            restored = restore_schema3_backup(db_path, backup, services_stopped=True)
            self.assertEqual(restored["restored_schema"], 3)
            self.assertEqual(restored["integrity"], "ok")
            self.assertEqual(inspect_database(db_path)["user_version"], 3)
            db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            self.assertEqual(db.execute("SELECT title FROM tasks").fetchone()[0], "synthetic fixture only")
            self.assertEqual(db.execute("SELECT state,payload FROM outbox").fetchone(),
                             ("delivered", "synthetic payload"))
            db.close()

    def test_restore_refuses_to_discard_app_or_outbox_changes(self):
        with tempfile.TemporaryDirectory(prefix="opentour-release-test-") as raw:
            root = Path(raw)
            db_path = root / "board.sqlite3"
            make_schema3(db_path)
            backup, _, _ = backup_database(db_path, root / "backups")
            migrate_legacy_schema4(db_path)
            db = sqlite3.connect(db_path)
            db.execute("UPDATE outbox SET state='pending' WHERE id='delivery_synthetic_01'")
            db.commit()
            db.close()
            with self.assertRaisesRegex(ReleaseError, "changed_since_backup"):
                restore_schema3_backup(db_path, backup, services_stopped=True)
            self.assertEqual(inspect_database(db_path)["user_version"], 4)

    def test_restore_refuses_nonempty_pr20_routing_fields(self):
        with tempfile.TemporaryDirectory(prefix="opentour-release-test-") as raw:
            root = Path(raw)
            db_path = root / "board.sqlite3"
            make_schema3(db_path)
            backup, _, _ = backup_database(db_path, root / "backups")
            migrate_legacy_schema4(db_path)
            db = sqlite3.connect(db_path)
            db.execute("UPDATE outbox SET routing_ref='qitem-synthetic-02' WHERE id='delivery_synthetic_01'")
            db.commit()
            db.close()
            with self.assertRaisesRegex(ReleaseError, "new_schema_data"):
                restore_schema3_backup(db_path, backup, services_stopped=True)

    def test_old_release_opens_restored_synthetic_schema3_database_when_available(self):
        legacy = os.environ.get("OPENTOUR_LEGACY_RELEASE")
        if not legacy:
            self.skipTest("set OPENTOUR_LEGACY_RELEASE to an installed legacy source checkout")
        with tempfile.TemporaryDirectory(prefix="opentour-legacy-reader-") as raw:
            db_path = Path(raw) / "board.sqlite3"
            make_schema3(db_path)
            script = (
                "import sys; from backend.board_store import BoardStore; "
                "BoardStore(sys.argv[1]); print('legacy_opened_schema3')"
            )
            env = os.environ.copy()
            env["PYTHONDONTWRITEBYTECODE"] = "1"
            result = subprocess.run([sys.executable, "-c", script, str(db_path)], cwd=legacy,
                                    env=env, capture_output=True, text=True, check=True)
            self.assertEqual(result.stdout.strip(), "legacy_opened_schema3")
            self.assertNotIn("synthetic payload", result.stdout + result.stderr)
            self.assertEqual(inspect_database(db_path)["user_version"], 3)

    def test_rendered_agents_are_version_pinned_and_parse_without_loading(self):
        with tempfile.TemporaryDirectory(prefix="opentour-plist-fixture-") as raw:
            root = Path(raw)
            release = root / "releases" / "84be151"
            release.mkdir(parents=True)
            output = root / "candidate-agents"
            paths = render_launch_agents(release, root / "app", Path(sys.executable),
                                         root / "auth-reference.json", root / "state" / "board.sqlite3", output)
            result = validate_launch_agents(paths, release, root / "state" / "board.sqlite3",
                                            root / "auth-reference.json")
            self.assertTrue(result["valid"])
            self.assertFalse(result["loaded"])
            self.assertEqual({item["role"] for item in result["agents"]}, {"server", "worker"})
            for path in paths:
                data = plistlib.loads(path.read_bytes())
                self.assertTrue(data["KeepAlive"])
                self.assertEqual(data["WorkingDirectory"], str(release))

    def test_render_private_read_and_control_references_only_when_explicit(self):
        with tempfile.TemporaryDirectory(prefix='opentour-reference-plist-') as raw:
            root=Path(raw);release=root/'abcdef1';release.mkdir()
            crm=root/'crm.json';controls=root/'controls.json'
            for path in (crm,controls):path.write_text('synthetic-invalid-json-never-read');path.chmod(0o600)
            auth=root/'auth.json';db=root/'data'/'board.sqlite3'
            paths=render_launch_agents(release,root/'app',Path(sys.executable),auth,db,root/'plists',crm,controls)
            self.assertTrue(validate_launch_agents(paths,release,db,auth,crm,controls)['valid'])
            with self.assertRaisesRegex(ReleaseError,'must_not_add_crm_credentials'):
                validate_launch_agents(paths,release,db,auth)
            server=next(p for p in paths if '.server.' in p.name)
            worker=next(p for p in paths if '.worker.' in p.name)
            worker_args=plistlib.loads(worker.read_bytes())['ProgramArguments']
            self.assertNotIn('--crm-credential-file',worker_args);self.assertNotIn('--client-controls-file',worker_args)
            data=plistlib.loads(server.read_bytes());data['ProgramArguments'][data['ProgramArguments'].index('--client-controls-file')+1]=str(root/'wrong.json')
            server.write_bytes(plistlib.dumps(data))
            with self.assertRaisesRegex(ReleaseError,'private_reference_mismatch'):
                validate_launch_agents(paths,release,db,auth,crm,controls)

    def test_render_separate_control_capability_only_with_explicit_reference(self):
        with tempfile.TemporaryDirectory(prefix='opentour-write-reference-') as raw:
            root=Path(raw);release=root/'abcdef1';release.mkdir()
            capability=root/'control-capability.json';capability.write_text('synthetic-reference-never-read');capability.chmod(0o600)
            auth=root/'auth.json';db=root/'data'/'board.sqlite3'
            paths=render_launch_agents(release,root/'app',Path(sys.executable),auth,db,root/'plists',crm_control_credential_file=capability)
            self.assertTrue(validate_launch_agents(paths,release,db,auth,crm_control_credential_file=capability)['valid'])
            with self.assertRaises(ReleaseError):validate_launch_agents(paths,release,db,auth)
            worker=next(p for p in paths if '.worker.' in p.name)
            self.assertNotIn('--crm-control-credential-file',plistlib.loads(worker.read_bytes())['ProgramArguments'])

    def test_stage_extracts_exact_commit_without_checkout_metadata(self):
        with tempfile.TemporaryDirectory(prefix="opentour-stage-source-") as raw:
            root = Path(raw)
            source = root / "source"
            source.mkdir()
            revision = "0123456789abcdef0123456789abcdef01234567"
            expected_tree = "89abcdef0123456789abcdef0123456789abcdef"
            archive_stream = io.BytesIO()
            with tarfile.open(fileobj=archive_stream, mode="w") as archive:
                payload = b"synthetic fixture\n"
                directory = tarfile.TarInfo("bin")
                directory.type = tarfile.DIRTYPE
                directory.mode = 0o755
                archive.addfile(directory)
                member = tarfile.TarInfo("app.py")
                member.mode = 0o644
                member.size = len(payload)
                archive.addfile(member, io.BytesIO(payload))
                executable = tarfile.TarInfo("bin/run")
                executable.mode = 0o755
                executable_payload = b"#!/bin/sh\nexit 0\n"
                executable.size = len(executable_payload)
                archive.addfile(executable, io.BytesIO(executable_payload))
            archive_stream.seek(0)

            class ArchiveProcess:
                stdout = archive_stream
                stderr = io.BytesIO()

                def wait(self):
                    return 0

                def poll(self):
                    return 0

                def kill(self):
                    raise AssertionError("successful archive process must not be killed")

            def git_result(command, **kwargs):
                if command[-1] == f"{revision}^{{commit}}":
                    return subprocess.CompletedProcess(command, 0, revision, "")
                if command[-1] == f"{revision}^{{tree}}":
                    return subprocess.CompletedProcess(command, 0, expected_tree, "")
                raise AssertionError(f"unexpected git command: {command}")

            with mock.patch("tools.local_board_release.subprocess.run", side_effect=git_result) as run, \
                    mock.patch("tools.local_board_release.subprocess.Popen", return_value=ArchiveProcess()) as popen:
                release, receipt = stage_release(source, revision, root / "release-root")

            self.assertEqual(run.call_count, 2)
            self.assertEqual(popen.call_args.args[0][-1], revision)
            self.assertEqual(receipt["commit"], revision)
            self.assertEqual(receipt["tree"], expected_tree)
            self.assertEqual((release / "app.py").read_text(encoding="utf-8"), "synthetic fixture\n")
            self.assertEqual(stat.S_IMODE((release / "app.py").stat().st_mode), 0o444)
            self.assertEqual(stat.S_IMODE((release / "bin/run").stat().st_mode), 0o555)
            self.assertEqual(stat.S_IMODE((release / "bin").stat().st_mode), 0o555)
            self.assertEqual(stat.S_IMODE(release.stat().st_mode), 0o555)
            self.assertFalse((release / ".git").exists())


if __name__ == "__main__":
    unittest.main()
