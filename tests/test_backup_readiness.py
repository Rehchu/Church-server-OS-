"""Recovery regressions: real temporary files, mocked external programs only."""
import errno
import json
import sys
import tempfile
import threading
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
from arise_server import audit, backups, config, maintenance, offboard, sharing


class BackupReadiness(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.cfg = config.Config(path=str(self.root / "arise.toml"), found=True, demo=False, raw={
            "paths": {"state_dir": str(self.root / "state")},
            "apps": {"root": str(self.root / "apps")},
            "directory": {"homes_path": str(self.root / "homes")},
            "nas": {"mount": str(self.root / "nas")},
            "people": {"leavers_archive": str(self.root / "leavers")},
        })
        for mod in (backups, sharing, offboard, audit, maintenance):
            self.enterContext(patch.object(mod, "load", return_value=self.cfg))

    def test_jobs_follow_storage_configuration_and_preserve_custom_paths(self):
        self.assertEqual(backups.resolve_job({"id": "homes", "paths": ["/srv/arise/homes"]})["paths"], [str(self.root / "homes")])
        self.assertEqual(backups.resolve_job({"id": "homes", "paths": ["/custom"]})["paths"], ["/custom"])
        for source, expected in (("state", "state"), ("leavers", "leavers"), ("apps", "apps")):
            self.assertEqual(backups.resolve_job({"id": source, "source": source})["paths"], [str(self.root / expected)])
        self.assertTrue(backups.resolve_job({"id": "apps", "paths": ["/srv/arise/apps"]})["quiesce_apps"])

    def test_sftp_account_probe_never_requests_a_shell(self):
        with patch.object(sharing, "which", return_value="/usr/bin/sftp"), patch.object(sharing, "run", return_value={"ok": True}) as run:
            self.assertTrue(sharing._home_ready("sftp:backup@arise-home:/backups"))
        self.assertEqual(run.call_args.args[0][0], "sftp")
        self.assertEqual(run.call_args.kwargs["input_text"], "pwd\nquit\n")
        self.assertIn("StrictHostKeyChecking=yes", run.call_args.args[0])

    def _app(self):
        app = self.root / "apps" / "testapp"
        app.mkdir(parents=True)
        (app / "compose.yaml").write_text("services: {}\n")
        return "a" * 64

    def _docker(self, cid, calls, stop_ok=True, exitcode=0, start_ok=True):
        def run(cmd, **kw):
            calls.append(cmd)
            result = {"ok": True, "out": "", "err": ""}
            if cmd[1] == "ps": result["out"] = cid + "\n" if cid else ""
            if cmd[1] == "stop": result["ok"] = stop_ok
            if cmd[1] == "inspect": result["out"] = json.dumps({"Running": False, "ExitCode": exitcode})
            if cmd[1] == "start": result["ok"] = start_ok
            return result
        return run

    def test_failed_backup_still_restarts_only_previously_running_containers(self):
        cid = self._app(); calls = []
        with patch.object(backups, "run", side_effect=self._docker(cid, calls)):
            with self.assertRaisesRegex(RuntimeError, "restic failed"):
                with backups.quiesced_apps():
                    self.assertTrue((self.cfg.state_dir / "backup-apps-stopped.json").exists())
                    raise RuntimeError("restic failed")
        self.assertEqual([c for c in calls if c[1] == "start"], [["docker", "start", cid]])
        self.assertFalse((self.cfg.state_dir / "backup-apps-stopped.json").exists())

    def test_failed_stop_and_forced_kill_refuse_backup_but_restart(self):
        cid = self._app()
        for opts in ({"stop_ok": False}, {"exitcode": 137}):
            calls = []
            with self.subTest(opts=opts), patch.object(backups, "run", side_effect=self._docker(cid, calls, **opts)):
                with self.assertRaises(RuntimeError):
                    with backups.quiesced_apps():
                        self.fail("must not copy a live/forcibly killed database")
                self.assertIn(["docker", "start", cid], calls)

    def test_no_running_containers_are_not_started(self):
        self._app(); calls = []
        with patch.object(backups, "run", side_effect=self._docker("", calls)):
            with backups.quiesced_apps():
                pass
        self.assertFalse(any(c[1] in ("start", "stop") for c in calls))

    def test_restart_failure_retains_record_for_execstoppost_or_boot_recovery(self):
        cid = self._app(); calls = []
        with patch.object(backups, "run", side_effect=self._docker(cid, calls, start_ok=False)):
            with self.assertRaisesRegex(RuntimeError, "restart"):
                with backups.quiesced_apps(): pass
        self.assertTrue((self.cfg.state_dir / "backup-apps-stopped.json").exists())
        with patch.object(backups, "run", return_value={"ok": True}) as run:
            self.assertTrue(backups.resume_apps()["ok"])
        run.assert_called_once_with(["docker", "start", cid], timeout=300)
        self.assertFalse((self.cfg.state_dir / "backup-apps-stopped.json").exists())

    def test_failed_samba_backup_prevents_system_snapshot(self):
        with patch.object(backups, "available", return_value=True), patch.object(backups, "live_repo", return_value="repo"), \
             patch.object(sharing, "backup_targets", return_value={"live": "synology"}), \
             patch.object(backups, "samba_offline_backup", return_value={"ok": False, "err": "locked"}), \
             patch.object(backups, "_restic") as restic:
            r = backups._execute({"id": "config", "paths": [str(self.root)], "samba_offline": True})
        self.assertFalse(r["ok"])
        self.assertIn("fresh Samba", r["error"])
        restic.assert_not_called()

    def test_success_without_new_samba_tarball_is_a_failure(self):
        d = self.root / "domain"; d.mkdir()
        (d / "samba-backup-old.tar.bz2").write_bytes(b"old")
        with patch.object(backups, "SAMBA_BACKUP_DIR", str(d)), patch.object(backups, "which", return_value="samba-tool"), \
             patch.object(backups, "run", return_value={"ok": True}):
            self.assertFalse(backups.samba_offline_backup()["ok"])

    def test_new_samba_tarball_is_required_and_accepted(self):
        d = self.root / "domain"
        def create(*a, **kw):
            (d / "samba-backup-new.tar.bz2").write_bytes(b"fresh")
            return {"ok": True}
        with patch.object(backups, "SAMBA_BACKUP_DIR", str(d)), patch.object(backups, "which", return_value="samba-tool"), \
             patch.object(backups, "run", side_effect=create):
            self.assertTrue(backups.samba_offline_backup()["ok"])

    def test_system_drill_rejects_missing_tarball_and_failed_listing(self):
        for listing in ({"ok": True, "out": "/etc/arise/arise.toml"},
                        {"ok": False, "out": "/etc/arise/arise.toml samba-backup-old.tar.bz2"}):
            with patch.object(backups, "_restic", side_effect=[{"ok": True, "out": '[{"id":"12345678"}]'}, listing]):
                self.assertFalse(backups._drill_system_check()["ok"])

    def test_full_drill_does_not_pass_when_file_restores_but_domain_check_fails(self):
        def restic(args, timeout):
            if args[0] == "snapshots":
                return {"ok": True, "out": '[{"short_id":"12345678"}]'}
            if args[0] == "ls":
                return {"ok": True, "out": json.dumps({"struct_type": "node", "type": "file", "size": 3, "path": "/document"})}
            if args[0] == "restore":
                (Path(args[args.index("--target") + 1]) / "document").write_bytes(b"abc")
                return {"ok": True, "out": ""}
            self.fail(args)
        with patch.object(backups, "available", return_value=True), patch.object(backups, "_restic", side_effect=restic), \
             patch.object(backups, "_drill_system_check", return_value={"ok": False, "note": "domain backup missing"}):
            result = backups.drill()
        self.assertFalse(result["ok"])
        self.assertIn("domain backup missing", result["note"])
        self.assertFalse((self.cfg.state_dir / "drill").exists())

    def test_missing_restic_never_reports_demo_drill_success_on_real_host(self):
        with patch.object(backups, "available", return_value=False):
            self.assertFalse(backups.drill()["ok"])
            self.assertFalse(backups.repo()["ok"])
            self.assertEqual(backups.snapshots()["snapshots"], [])
            self.assertFalse(backups.restore_version("/example", "12345678")["ok"])

    def test_verify_and_optional_skips_do_not_mask_a_missed_backup_night(self):
        rows = [{"job": "verify", "ok": True, "started": "2026-11-03T01:00:00"},
                {"job": "leavers", "ok": True, "skipped": True, "started": "2026-11-03T01:00:00"}]
        self.assertIsNotNone(backups.missed_night(rows, datetime(2026, 11, 3, 4)))

    def test_offboard_retries_failed_move_before_mac_removal(self):
        entry = {"name": "a.b", "move_to": "c.d", "disable_on": "2026-10-01", "done": None}
        offboard._write([entry])
        with patch.object(offboard.directory, "enable_user", return_value={"ok": True}), \
             patch.object(offboard, "copy_to_archive", return_value={"ok": True}), \
             patch("arise_server.accounts.switched"), \
             patch("arise_server.profiles.mailbox_export", return_value={"ok": True}), \
             patch("arise_server.macs.queue_removals", return_value={"ok": True}) as removals:
            with patch.object(offboard, "_move_home", return_value={"ok": False, "err": "disk full"}):
                self.assertFalse(offboard.sweep(datetime(2026, 11, 1))["ok"])
            self.assertIsNone(offboard._read()[0]["done"])
            removals.assert_not_called()
            with patch.object(offboard, "_move_home", return_value={"ok": True, "to": "/safe"}) as move:
                self.assertTrue(offboard.sweep(datetime(2026, 11, 2))["ok"])
            self.assertEqual(move.call_args.args[2], datetime(2026, 11, 1))
            removals.assert_called_once()
            self.assertIsNotNone(offboard._read()[0]["done"])

    def test_leavers_archive_rejects_same_size_corrupt_copy(self):
        when = datetime(2026, 11, 1)
        src = self.root / "homes" / "a.b"; src.mkdir(parents=True)
        (src / "file.txt").write_bytes(b"abc")
        dst = Path(offboard.archive_dir(str(self.root / "leavers"), "a.b", when))
        dst.mkdir(parents=True); (dst / "file.txt").write_bytes(b"xyz")
        with patch("arise_server.util.which", return_value="rsync"), patch("arise_server.util.run", return_value={"ok": True}):
            result = offboard.copy_to_archive("a.b", when)
        self.assertFalse(result["ok"])
        self.assertIn("content verification", result["err"])

    def test_audit_failure_is_logged_and_exposed_without_event_contents(self):
        with patch.object(audit.os, "open", side_effect=OSError(errno.ENOSPC, "full")), self.assertLogs(audit.__name__, level="ERROR") as logs:
            row = audit.record("private-person", "sensitive-action", detail="private-detail")
        self.assertFalse(row["recorded"])
        self.assertFalse(audit.write_health()["ok"])
        self.assertNotIn("private-person", " ".join(logs.output))
        self.assertNotIn("private-detail", " ".join(logs.output))

    def test_maintenance_lock_reentrant_but_excludes_another_thread(self):
        errors = []
        def update():
            try:
                with maintenance.exclusive("update"):
                    errors.append("entered")
            except maintenance.MaintenanceBusy:
                errors.append("deferred")
        with maintenance.exclusive("backup"):
            with maintenance.exclusive("nested app stop"):
                worker = threading.Thread(target=update)
                worker.start(); worker.join(timeout=5)
                self.assertFalse(worker.is_alive())
        self.assertEqual(errors, ["deferred"])
        with maintenance.exclusive("update after backup"):
            pass

    def test_backup_budget_leaves_cleanup_time_and_refuses_short_window(self):
        with patch("arise_server.church.in_service_now", return_value=None), \
             patch("arise_server.church.next_service", return_value={"at": "2026-11-01T10:00"}), \
             patch("arise_server.calendar.events", return_value=[]):
            self.assertEqual(maintenance.backup_budget(now=datetime(2026, 11, 1, 9)), 3000)
            with self.assertRaises(maintenance.MaintenanceBusy):
                maintenance.backup_budget(now=datetime(2026, 11, 1, 9, 30))

    def test_backup_budget_includes_special_calendar_services(self):
        with patch("arise_server.church.in_service_now", return_value=None), \
             patch("arise_server.church.next_service", return_value=None), \
             patch("arise_server.calendar.events", return_value=[{"start": "2026-11-02T12:00", "is_service": True}]):
            self.assertEqual(maintenance.backup_budget(now=datetime(2026, 11, 2, 11)), 3000)

    def test_unattended_wrapper_never_runs_command_during_service(self):
        with patch("arise_server.church.in_service_now", return_value={"name": "service"}), \
             patch.object(maintenance.subprocess, "run") as run:
            self.assertEqual(maintenance.main(["/usr/lib/apt/apt.systemd.daily", "install"]), 1)
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
