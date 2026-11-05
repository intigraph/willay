"""Actual embedded installer controls; no package installs or network calls."""

import hashlib
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SOURCE = Path(__file__).parents[1] / "install.sh"
PAYLOAD = SOURCE.read_text().split("<<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]
INSTALLER = {"__name__": "installer_fixture"}
exec(compile(PAYLOAD, str(SOURCE), "exec"), INSTALLER)


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="willay-installer-control-")
        self.addCleanup(self.temporary.cleanup)
        self.prefix = Path(self.temporary.name) / "release"
        self.wheel = "willay-0.1.0-py3-none-any.whl"
        self.data = b"fixture wheel; never executed"
        base = "https://github.com/intigraph/willay/releases/download/v0.1.0/"
        self.release = {
            "tag_name": "v0.1.0",
            "assets": [
                {"name": name, "browser_download_url": base + name}
                for name in ("SHA256SUMS", self.wheel)
            ],
        }
        self.calls = []

    def download(self, url, _limit):
        if "api.github.com" in url:
            return json.dumps(self.release).encode()
        if url.endswith("SHA256SUMS"):
            return (hashlib.sha256(self.data).hexdigest() + "  " + self.wheel).encode()
        return self.data

    def child(self, command, **kwargs):
        self.calls.append((command, kwargs))
        if command[-1] == "--version":
            return subprocess.CompletedProcess(command, 0, "willay 0.1.0\n", "")
        return subprocess.CompletedProcess(command, 0)

    def invoke(self, *args, child=None):
        with (
            patch.dict(INSTALLER, download=self.download),
            patch("shutil.which", return_value="/fixture/uv"),
            patch("subprocess.run", side_effect=child or self.child),
            patch.dict(os.environ, {"VERSION": "0.1.0", "SECRET_CONTROL": "not-forwarded"}),
        ):
            INSTALLER["install"](["--prefix", str(self.prefix), *args])

    def test_install_and_refuse_overwrite(self):
        self.invoke()
        self.assertTrue(self.prefix.is_dir())
        self.assertEqual(len(self.calls), 2)
        self.assertNotIn("SECRET_CONTROL", self.calls[0][1]["env"])
        self.assertEqual(self.calls[0][1]["env"]["UV_PYTHON_DOWNLOADS"], "never")
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.invoke()
        self.assertTrue(self.prefix.is_dir())

    def test_dry_run_writes_nothing(self):
        self.invoke("--dry-run")
        self.assertFalse(self.prefix.exists())
        self.assertEqual(self.calls, [])

    def test_corrupt_payload_refuses_before_destination(self):
        original = self.download
        self.download = lambda url, limit: (
            b"corrupt" if url.endswith(".whl") else original(url, limit)
        )
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            self.invoke()
        self.assertFalse(self.prefix.exists())

    def test_foreign_asset_refused(self):
        self.release["assets"][1]["browser_download_url"] = "https://example.test/wheel"
        with self.assertRaisesRegex(ValueError, "noncanonical"):
            self.invoke()
        self.assertFalse(self.prefix.exists())

    def test_wrong_version_and_prerelease_refused(self):
        self.release["tag_name"] = "v0.2.0"
        with self.assertRaisesRegex(ValueError, "requested stable"):
            self.invoke()
        self.release["tag_name"] = "v0.1.0"
        self.release["prerelease"] = True
        with self.assertRaisesRegex(ValueError, "requested stable"):
            self.invoke()

    def test_failed_child_cleanup(self):
        def failed(command, **_kwargs):
            raise subprocess.CalledProcessError(2, command)

        with self.assertRaises(subprocess.CalledProcessError):
            self.invoke(child=failed)
        self.assertFalse(self.prefix.exists())

    def test_wrong_installed_version_cleanup(self):
        def wrong(command, **kwargs):
            if command[-1] == "--version":
                return subprocess.CompletedProcess(command, 0, "willay 9.9.9\n", "")
            return self.child(command, **kwargs)

        with self.assertRaisesRegex(ValueError, "does not match"):
            self.invoke(child=wrong)
        self.assertFalse(self.prefix.exists())


if __name__ == "__main__":
    unittest.main()
