"""App lifecycle contracts: real-mode decisions with a deterministic Docker adapter."""
import json
import sys
import tempfile
import unittest
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
from arise_server import apps, maintenance
from arise_server.util import run_stream


class AppSafety(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.cfg = SimpleNamespace(demo=False, state_dir=self.root / "state", apps=SimpleNamespace(root=str(self.root / "apps"), docker=True),
                                   templates_dir=self.root / "templates", system=SimpleNamespace(data_root=str(self.root)))
        self.patches = [patch.object(maintenance, "load", return_value=self.cfg), patch.object(apps, "load", return_value=self.cfg),
                        patch.object(apps, "available", return_value=True),
                        patch.object(apps, "APP_SECRETS_DIR", self.root / "secrets"),
                        patch.object(apps, "ram_total_mb", return_value=8192),
                        patch.object(apps, "_docker_allocations", return_value=[]),
                        patch.object(apps, "run", return_value={"ok": True, "out": "", "err": ""}),
                        patch.object(apps, "run_stream", return_value={"ok": True, "out": "pulled", "err": ""})]
        self.mocks = [p.start() for p in self.patches]
        self.addCleanup(self.temp.cleanup)
        for p in self.patches:
            self.addCleanup(p.stop)

    def installed(self, name="widget", limit="512m", autostart=False):
        p = Path(self.cfg.apps.root, name)
        p.mkdir(parents=True)
        (p / "compose.yaml").write_text(yaml.safe_dump({"services": {"web": {"image": "example/image", "mem_limit": limit, "restart": "unless-stopped" if autostart else "no"}}}))
        (p / "arise.json").write_text(json.dumps({"autostart": autostart}))
        return p

    def template(self):
        p = self.cfg.templates_dir / "widget"
        p.mkdir(parents=True)
        (p / "compose.yaml").write_text("services:\n  web:\n    image: example/image\n")
        (p / "template.yaml").write_text("name: widget\nautostart: false\nlimits: {mem_mb: 512, cpus: 1}\nenv:\n  DB_PASSWORD: CHANGE-ME\n")

    def test_aggregate_limits_budget_required_sync_before_optional(self):
        doc = apps.inject_limits({"services": {"a": {}, "b": {"mem_limit": "128m"}}}, {"mem_mb": 768})
        self.assertEqual(apps.compose_cap_mb(doc), 896)
        items = [{"id": "small", "autostart": True, "ram_mb": 1, "cap_mb": 512},
                 {"id": "nextcloud", "autostart": True, "ram_mb": 1, "cap_mb": 1800}]
        plan = apps.autostart_plan(items, 4096)
        self.assertEqual(plan["start"], ["nextcloud"])
        self.assertEqual(plan["used_mb"], 1800)

    def test_actual_templates_expose_and_plan_aggregate_caps(self):
        self.cfg.templates_dir = ROOT / "templates"
        rows = apps.templates()["templates"]
        nextcloud = next(t for t in rows if t["id"] == "nextcloud")
        self.assertEqual(nextcloud["cap_mb"], 2688)
        plan = apps.autostart_plan(rows, 8192)
        self.assertIn("nextcloud", plan["start"])
        self.assertLessEqual(sum(t["cap_mb"] for t in rows if t["id"] in plan["start"]), 6144)

    def test_manual_start_and_update_refuse_overbudget_before_action(self):
        self.installed(limit="2048m")
        allocations = [{"id": "other", "project": "other", "running": True, "restart": "no", "memory": 5 * 1024**3}]
        with patch.object(apps, "_docker_allocations", return_value=allocations):
            for action in ("start", "restart", "update"):
                result = apps.act("widget", action)
                self.assertFalse(result["ok"])
                self.assertIn("app budget", result["err"])
        self.mocks[-1].assert_not_called()
        self.mocks[-2].assert_not_called()

    def test_unbounded_or_unknown_existing_allocations_fail_closed(self):
        p = self.installed()
        doc = yaml.safe_load((p / "compose.yaml").read_text())
        with patch.object(apps, "_docker_allocations", return_value=[{"id": "other", "running": True, "memory": 0}]):
            self.assertFalse(apps._budget_guard("widget", doc)["ok"])
        with patch.object(apps, "_docker_allocations", side_effect=ValueError("inspection failed")):
            self.assertFalse(apps._budget_guard("widget", doc)["ok"])

    def test_backup_lock_defers_app_start_without_touching_docker(self):
        self.installed()
        ready, release = threading.Event(), threading.Event()

        def backup():
            with maintenance.exclusive("backup"):
                ready.set()
                release.wait(3)

        t = threading.Thread(target=backup)
        t.start()
        try:
            self.assertTrue(ready.wait(2))
            result = apps.act("widget", "start")
            self.assertFalse(result["ok"])
            self.assertIn("deferred", result["err"])
            self.mocks[-2].assert_not_called()
        finally:
            release.set()
            t.join()
    def test_autostart_off_updates_engine_policy_and_compose(self):
        p = self.installed(autostart=True)
        with patch.object(apps, "_docker_allocations", return_value=[{"id": "container", "project": "widget"}]):
            self.assertTrue(apps.set_autostart("widget", False)["ok"])
        self.mocks[-2].assert_called_once_with(["docker", "update", "--restart=no", "container"], timeout=30)
        self.assertEqual(yaml.safe_load((p / "compose.yaml").read_text())["services"]["web"]["restart"], "no")
        self.assertFalse(json.loads((p / "arise.json").read_text())["autostart"])

    def test_autostart_on_starts_stack_after_budget_check(self):
        p = self.installed()
        self.assertTrue(apps.set_autostart("widget", True)["ok"])
        self.assertEqual(self.mocks[-2].call_args.args[0][-2:], ["up", "-d"])
        self.assertTrue(json.loads((p / "arise.json").read_text())["autostart"])

    def test_failed_enable_does_not_persist_success(self):
        p = self.installed()
        original = (p / "compose.yaml").read_text()
        self.mocks[-2].return_value = {"ok": False, "err": "start failed", "out": ""}
        self.assertFalse(apps.set_autostart("widget", True)["ok"])
        self.assertEqual((p / "compose.yaml").read_text(), original)
        self.assertFalse(json.loads((p / "arise.json").read_text())["autostart"])

    def test_stats_group_by_compose_labels_not_container_names(self):
        with patch.object(apps, "_docker_allocations", return_value=[{"id": "abcdef123456789", "project": "nextcloud"}, {"id": "fedcba123456789", "project": "nextcloud"}]):
            self.mocks[-2].return_value = {"ok": True, "out": '\n'.join(json.dumps(row) for row in [
                {"id": "abcdef123456", "cpu": "5%", "memory": "100MiB / 1GiB"},
                {"id": "fedcba123456", "cpu": "10%", "memory": "200MiB / 1GiB"}])}
            self.assertEqual(apps._stats(), {"nextcloud": {"cpu": 15.0, "mem": 300 * 1024**2}})

    def test_restored_secret_copy_is_reused_and_data_kept(self):
        self.template()
        p = self.installed()
        (p / "db").mkdir()
        (p / "db" / "important").write_text("database")
        apps.APP_SECRETS_DIR.mkdir()
        (apps.APP_SECRETS_DIR / "widget.env").write_text("DB_PASSWORD=existing-test-credential\n")
        result = apps.deploy("widget", start=False)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["secrets_generated"], [])
        self.assertEqual(apps._read_env(str(p / ".env"))["DB_PASSWORD"], "existing-test-credential")
        self.assertEqual((p / "db" / "important").read_text(), "database")
        self.assertIn("--parallel", self.mocks[-1].call_args.args[0])

    def test_missing_restored_credentials_refuses_before_compose_mutation(self):
        self.template()
        p = self.installed()
        (p / "db").mkdir()
        (p / "db" / "important").write_text("database")
        previous = (p / "compose.yaml").read_text()
        result = apps.deploy("widget", start=False)
        self.assertFalse(result["ok"])
        self.assertIn("credentials are missing", result["err"])
        self.assertEqual((p / "compose.yaml").read_text(), previous)
        self.assertFalse((p / ".env").exists())
        self.mocks[-1].assert_not_called()

    def test_custom_name_refused_without_shared_data_or_containers(self):
        result = apps.deploy("trilium", name="private-notes")
        self.assertFalse(result["ok"])
        self.assertFalse(Path(self.cfg.apps.root, "private-notes").exists())
        self.mocks[-2].assert_not_called()

    def test_filebrowser_new_layout_does_not_lend_app_secrets_directory(self):
        p = self.installed("filebrowser")
        (p / ".env").write_text("PRIVATE=example\n")
        with patch.object(apps.os, "chown") as chown:
            self.assertTrue(apps._prepare_filebrowser(str(p))["ok"])
        self.assertEqual({call.args[0] for call in chown.call_args_list}, {p / "database", p / "config"})
        self.assertEqual((p / "database").stat().st_mode & 0o777, 0o700)
        self.assertEqual((p / ".env").read_text(), "PRIVATE=example\n")

    def test_filebrowser_migrates_only_after_stop_retains_original_and_newer_copy(self):
        p = self.installed("filebrowser")
        (p / "filebrowser.db").write_bytes(b"legacy database")
        with patch.object(apps.os, "chown"):
            self.assertTrue(apps._prepare_filebrowser(str(p))["ok"])
            self.assertEqual(self.mocks[-2].call_args.args[0][-1], "stop")
            self.assertEqual((p / "filebrowser.db").read_bytes(), b"legacy database")
            self.assertEqual((p / "database/filebrowser.db").read_bytes(), b"legacy database")
            (p / "database/filebrowser.db").write_bytes(b"newer data")
            self.assertTrue(apps._prepare_filebrowser(str(p))["ok"])
            self.assertEqual((p / "database/filebrowser.db").read_bytes(), b"newer data")
        self.assertEqual(self.mocks[-2].call_count, 1)

    def test_filebrowser_failed_stop_never_copies_live_database(self):
        p = self.installed("filebrowser")
        (p / "filebrowser.db").write_bytes(b"live database")
        self.mocks[-2].return_value = {"ok": False, "err": "stop failed", "out": ""}
        self.assertFalse(apps._prepare_filebrowser(str(p))["ok"])
        self.assertFalse((p / "database/filebrowser.db").exists())
        self.assertEqual((p / "filebrowser.db").read_bytes(), b"live database")


class StreamedCommands(unittest.TestCase):
    def test_streams_progress_and_preserves_exit_status(self):
        lines = []
        result = run_stream([sys.executable, "-c", "import sys; print('pull progress', flush=True); sys.exit(7)"], log=lines.append)
        self.assertFalse(result["ok"])
        self.assertEqual(result["code"], 7)
        self.assertIn("pull progress", lines)
        self.assertIn("pull progress", result["out"])

    def test_timeout_preserves_received_diagnostics(self):
        lines = []
        result = run_stream([sys.executable, "-c", "import time; print('pull started', flush=True); time.sleep(5)"], timeout=0.25, log=lines.append)
        self.assertEqual(result["code"], 124)
        self.assertIn("pull started", result["out"])


if __name__ == "__main__":
    unittest.main()
