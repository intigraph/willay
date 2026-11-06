#!/bin/sh
# Install a published wheel with an existing uv and Python 3.12+.
set -eu
exec python3 - "$@" <<'PY'
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request


def download(url, limit):
    with urllib.request.urlopen(url, timeout=30) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError('download exceeds size limit')
    return data


def install(argv=None):
    parser = argparse.ArgumentParser(description='Install a checksummed Willay release wheel')
    parser.add_argument('--prefix', default=os.environ.get('PREFIX'))
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(argv)
    if sys.version_info < (3, 12):
        raise ValueError('Python 3.12+ is required; no interpreter will be downloaded')
    version = os.environ.get('VERSION', '')
    if version and not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise ValueError('VERSION must be a stable version such as 0.1.0')
    api = 'https://api.github.com/repos/intigraph/willay/releases/'
    release = json.loads(download(api + ('tags/v' + version if version else 'latest'), 2**20))
    tag = release['tag_name']
    if release.get('draft') or release.get('prerelease') or not re.fullmatch(
        r'v\d+\.\d+\.\d+', tag
    ) or (version and tag != 'v' + version):
        raise ValueError('release is not the requested stable version')
    version = tag[1:]
    wheel = f'willay-{version}-py3-none-any.whl'
    base = f'https://github.com/intigraph/willay/releases/download/{tag}/'
    assets = {asset['name']: asset['browser_download_url'] for asset in release['assets']}
    for name in ('SHA256SUMS', wheel):
        if assets.get(name) != base + name:
            raise ValueError('missing or noncanonical release asset: ' + name)
    prefix = Path(args.prefix).expanduser().absolute() if args.prefix else (
        Path.home() / '.local/share/willay' / tag
    )
    if prefix.exists() or prefix.is_symlink():
        raise ValueError('destination already exists; retained unchanged: ' + str(prefix))
    entrypoint = None if args.prefix else Path.home() / '.local/bin/willay'
    if entrypoint is not None and (entrypoint.exists() or entrypoint.is_symlink()):
        raise ValueError('command already exists; retained unchanged: ' + str(entrypoint))
    uv = shutil.which('uv')
    if not uv:
        raise ValueError('uv is required; install it from https://docs.astral.sh/uv/')
    if args.dry_run:
        print(f'Would install Willay {version} into {prefix}; metadata only, payload not verified')
        return
    sums = download(assets['SHA256SUMS'], 65536).decode('ascii')
    matches = [line.split()[0] for line in sums.splitlines()
               if len(line.split()) == 2 and line.split()[1].lstrip('*') == wheel]
    if len(matches) != 1 or not re.fullmatch(r'[a-fA-F0-9]{64}', matches[0]):
        raise ValueError('missing or ambiguous wheel checksum')
    data = download(assets[wheel], 16 * 2**20)
    if hashlib.sha256(data).hexdigest() != matches[0].lower():
        raise ValueError('wheel checksum mismatch; nothing installed')
    # uv environments contain absolute paths: create at the final private location.
    # Refuse existing destinations and remove only the new directory on failure.
    prefix.mkdir(parents=True, exist_ok=False)
    try:
        with tempfile.TemporaryDirectory(prefix='willay-wheel-') as directory:
            artifact = Path(directory) / wheel
            artifact.write_bytes(data)
            environment = {key: os.environ[key] for key in ('HOME', 'PATH', 'TMPDIR')
                           if key in os.environ}
            environment.update(UV_TOOL_DIR=str(prefix / 'tools'),
                               UV_TOOL_BIN_DIR=str(prefix / 'bin'),
                               UV_PYTHON_DOWNLOADS='never', UV_NO_CONFIG='1',
                               UV_NO_CACHE='1')
            subprocess.run([uv, 'tool', 'install', '--python', sys.executable,
                            '--no-managed-python', '--index-url', 'https://pypi.org/simple',
                            str(artifact)], env=environment, check=True, timeout=240)
            result = subprocess.run([str(prefix / 'bin/willay'), '--version'],
                                    env=environment, check=True, capture_output=True,
                                    text=True, timeout=30)
            if result.stdout.strip() != 'willay ' + version:
                raise ValueError('installed command version does not match the release')
        if entrypoint is not None:
            entrypoint.parent.mkdir(parents=True, exist_ok=True)
            entrypoint.symlink_to(prefix / 'bin/willay')
    except BaseException:
        shutil.rmtree(prefix)
        raise
    print(f'Installed Willay {version}: {prefix}/bin/willay')
    if entrypoint is not None:
        print(f'Command: {entrypoint}; add {entrypoint.parent} to PATH if needed.')
    else:
        print(f'Add {prefix}/bin to PATH.')
    print('No credentials, feed, service or shell profile were configured.')


if __name__ == '__main__':
    try:
        install()
    except Exception as error:
        print('Willay install refused: ' + str(error), file=sys.stderr)
        raise SystemExit(1)
PY
