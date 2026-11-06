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

    def invoke_default(self, *args, home=None):
        def install_child(command, **kwargs):
            if command[1:3] == ["tool", "install"]:
                binary = Path(kwargs["env"]["UV_TOOL_BIN_DIR"]) / "willay"
                binary.parent.mkdir(parents=True)
                binary.write_text("fixture command")
            return self.child(command, **kwargs)

        with (
            patch.dict(INSTALLER, download=self.download),
            patch("shutil.which", return_value="/fixture/uv"),
            patch("subprocess.run", side_effect=install_child),
            patch.dict(
                os.environ,
                {"VERSION": "0.1.0", "PREFIX": "", "HOME": str(home or self.temporary.name)},
            ),
        ):
            INSTALLER["install"](list(args))

    def test_default_install_exposes_command_without_profile_changes(self):
        root = Path(self.temporary.name)
        real_home = root / "physical-home"
        real_home.mkdir()
        home = root / "aliased-home"
        home.symlink_to(real_home, target_is_directory=True)
        self.invoke_default(home=home)
        binary = home / ".local/bin/willay"
        self.assertTrue(binary.is_symlink())
        self.assertEqual(
            binary.resolve(), (home / ".local/share/willay/v0.1.0/bin/willay").resolve()
        )
        self.assertEqual(binary.read_text(), "fixture command")
        self.assertFalse((home / ".profile").exists())

    def test_default_install_preserves_existing_command(self):
        binary = Path(self.temporary.name) / ".local/bin/willay"
        binary.parent.mkdir(parents=True)
        binary.write_text("previous owner")
        with self.assertRaisesRegex(ValueError, "command already exists"):
            self.invoke_default()
        self.assertEqual(binary.read_text(), "previous owner")
        self.assertEqual(self.calls, [])
        self.assertFalse((Path(self.temporary.name) / ".local/share/willay/v0.1.0").exists())

    def test_default_install_preserves_dangling_command_symlink(self):
        binary = Path(self.temporary.name) / ".local/bin/willay"
        binary.parent.mkdir(parents=True)
        target = Path(self.temporary.name) / "other-owner"
        binary.symlink_to(target)
        with self.assertRaisesRegex(ValueError, "command already exists"):
            self.invoke_default()
        self.assertTrue(binary.is_symlink())
        self.assertEqual(binary.readlink(), target)
        self.assertEqual(self.calls, [])

    def test_default_dry_run_leaves_no_command_or_destination(self):
        self.invoke_default("--dry-run")
        self.assertFalse((Path(self.temporary.name) / ".local").exists())
        self.assertEqual(self.calls, [])

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
