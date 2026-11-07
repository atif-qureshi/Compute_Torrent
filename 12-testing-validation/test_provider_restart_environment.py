import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class RestartTests(unittest.TestCase):
    def modules(self):
        for root in ("08-provider-node", "desktop"):
            path = ROOT / root / "05-desktop-app-shell/provider_update.py"
            spec = importlib.util.spec_from_file_location(root + "_updater", path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            yield module

    def test_restart_environment_resets_child_only(self):
        for module in self.modules():
            inherited = {"_PYI_ARCHIVE_FILE": "old.exe", "_PYI_PARENT_PROCESS_LEVEL": "1",
                         "_PYI_PARENT_PID": "123", "_MEIPASS2": "temp", "PYI_TEST": "old",
                         "PATH": "fixture-path", "USERPROFILE": "fixture-user"}
            with patch.dict(module.os.environ, inherited, clear=True):
                cleaned = module.restart_environment()
                self.assertEqual(cleaned, {"PATH": "fixture-path", "USERPROFILE": "fixture-user",
                                           "PYINSTALLER_RESET_ENVIRONMENT": "1"})
                self.assertEqual(dict(module.os.environ), inherited)

    def test_check_update_parses_manifest(self):
        import io
        fake_sha = "a" * 64
        for module in self.modules():
            fake_manifest = f'{{"version": "2026.11.07-hybrid4", "filename": "ComputeTorrent_Seeder.exe", "sha256": "{fake_sha}", "size": 123}}'.encode()
            with patch.object(module, "_open_url", return_value=io.BytesIO(fake_manifest)) as network:
                manifest, base, is_newer = module.check_update("http://coordinator.example:8001", "2026.11.07-hybrid3")
                self.assertEqual(manifest["version"], "2026.11.07-hybrid4")
                self.assertTrue(is_newer)
                network.assert_called_once()


if __name__ == "__main__":
    unittest.main()
