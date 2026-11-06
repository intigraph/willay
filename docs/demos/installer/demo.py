"""Exercise the actual installer through the retained HTTP/uv fixture controls."""
import contextlib
import importlib.util
import io
from pathlib import Path

root = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('installer_controls', root / 'tests/test_installer.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
for method, caption in [
    ('test_install_and_refuse_overwrite', 'Private install succeeds; existing destination refuses overwrite.'),
    ('test_corrupt_payload_refuses_before_destination', 'Corrupt wheel refuses before creating the destination.'),
    ('test_wrong_installed_version_cleanup', 'Wrong installed version refuses and cleans the new directory.'),
]:
    control = module.InstallerTests(method)
    control.setUp()
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            getattr(control, method)()
        print('PASS:', caption)
    finally:
        control.doCleanups()
print('HTTP and uv are mocked; installer code is real. No real release or platform acceptance claimed.')
