import base64
import hashlib
import io
from pathlib import Path
import ssl
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "08-provider-node/05-desktop-app-shell"))
import provider_update as updater


class SecureUpdateTests(unittest.TestCase):
    def setUp(self):
        self.key = Ed25519PrivateKey.generate()
        self.payload = b"inert installer fixture"
        self.current = "2026.11.01-update2"
        now = int(time.time())
        self.release = dict(schema=1, channel="stable", platform="windows-x64",
                            filename=updater.SETUP, version="2026.11.01-update10",
                            minimum_version=self.current, sequence=10, issued=now-1,
                            expires=now+300, size=len(self.payload),
                            sha256=hashlib.sha256(self.payload).hexdigest())
        self.addCleanup(patch.stopall)
        patch.multiple(updater, RELEASE_BASE="https://release.example.invalid/updates",
                       RELEASE_PUBLIC_KEY=self.key.public_key().public_bytes_raw().hex()).start()
        patch.object(updater.platform, "machine", return_value="AMD64").start()

    def signed(self, **changes):
        metadata = dict(self.release, **changes)
        signature = self.key.sign(updater._signed_bytes(metadata))
        return {"release": metadata, "signature": base64.b64encode(signature).decode()}

    def stage(self, root, envelope, payload=None, base=None):
        with patch.object(updater, "_open", return_value=io.BytesIO(self.payload if payload is None else payload)):
            return updater.stage_update(base or updater._feed(), {"signed_envelope": envelope},
                                        root, current_build=self.current)

    def test_unsigned_forged_and_modified_metadata(self):
        with self.assertRaises(ValueError):
            updater._verify(self.release, self.current)
        altered = self.signed()
        altered["release"]["version"] = "2026.11.02-update11"
        with self.assertRaises(InvalidSignature):
            updater._verify(altered, self.current)
        forged = self.signed()
        forged["signature"] = base64.b64encode(bytes(64)).decode()
        with self.assertRaises(InvalidSignature):
            updater._verify(forged, self.current)

    def test_expiry_platform_channel_and_version(self):
        for changes in (dict(expires=int(time.time())-1), dict(platform="linux-x64"),
                        dict(channel="testing"), dict(minimum_version="2026.11.02-update1"),
                        dict(version="arbitrary")):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                updater._verify(self.signed(**changes), self.current)
        self.assertTrue(updater._verify(self.signed(), self.current)[1])
        self.assertFalse(updater._verify(self.signed(version=self.current), self.current)[1])

    def test_unconfigured_http_and_foreign_feed(self):
        with patch.object(updater, "RELEASE_PUBLIC_KEY", ""), self.assertRaises(ValueError):
            updater._feed()
        with patch.object(updater, "RELEASE_BASE", "http://release.example.invalid"), self.assertRaises(ValueError):
            updater._feed()
        with tempfile.TemporaryDirectory() as root, self.assertRaises(ValueError):
            self.stage(root, self.signed(), base="https://foreign.example.invalid")

    def test_tls_verification_and_no_redirect(self):
        context = ssl.create_default_context()
        with patch.object(updater.ssl, "create_default_context", return_value=context),              patch.object(updater.urllib.request, "build_opener") as build:
            build.return_value.open.side_effect = ssl.SSLCertVerificationError("invalid certificate")
            with self.assertRaises(ssl.SSLCertVerificationError):
                updater._open(updater._feed())
            redirect, https = build.call_args.args
            self.assertIsNone(redirect.redirect_request())
            self.assertTrue(https._context.check_hostname)
            self.assertEqual(https._context.verify_mode, ssl.CERT_REQUIRED)

    def test_modified_truncated_and_interrupted_download(self):
        with tempfile.TemporaryDirectory() as root:
            for payload in (self.payload[:-1] + b"X", self.payload[:-1]):
                with self.assertRaises(ValueError):
                    self.stage(root, self.signed(), payload)
            with patch.object(updater, "_open", side_effect=ConnectionResetError), self.assertRaises(ConnectionResetError):
                updater.stage_update(updater._feed(), {"signed_envelope": self.signed()}, root,
                                     current_build=self.current)
            self.assertFalse([p for p in Path(root).glob("update-*") if p.is_dir()])

    def test_replay_lower_sequence_and_conflicting_sequence(self):
        with tempfile.TemporaryDirectory() as root:
            self.stage(root, self.signed())
            for envelope in (self.signed(sequence=9), self.signed(version="2026.11.02-update10")):
                with self.assertRaisesRegex(ValueError, "Replayed"):
                    self.stage(root, envelope)

    def test_verified_launch_boundary_and_settings(self):
        with tempfile.TemporaryDirectory() as root:
            settings = Path(root) / "seeder-settings.json"
            settings.write_bytes(b'{"fixture":true}')
            staged = self.stage(root, self.signed())
            with patch.object(updater.sys, "frozen", True, create=True),                  patch.object(updater.subprocess, "Popen") as launch:
                updater.restart_with_update(staged, root, current_build=self.current)
                launch.assert_called_once_with([str(staged[0].resolve())], close_fds=True)
                staged[0].write_bytes(b"X" * len(self.payload))
                with self.assertRaises(ValueError):
                    updater.restart_with_update(staged, root, current_build=self.current)
                self.assertEqual(launch.call_count, 1)
            self.assertEqual(settings.read_bytes(), b'{"fixture":true}')


if __name__ == "__main__":
    unittest.main()
