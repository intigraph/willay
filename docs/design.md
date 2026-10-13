# Implementation and release design

Willay uses Python 3.12+ rather than a Rust skeleton. This keeps the existing
cc-speaks credential client reusable and retains the tested HTTP, SQLite and
ffmpeg pipeline in one implementation. TOML uses the standard library;
ffmpeg performs the audio work as a bounded subprocess. The only runtime
dependency supplies a packaged ffmpeg when the host has none. Python/uv are
required; this is not a static native binary.

The repository follows the Yupana template for justfile quality/build/docs
entry points, MIT licensing, mdBook/Pages and same-workflow release artifacts
with checksums. Python uses release-please as the language-appropriate
release-PR equivalent; release-plz supports Rust packages. The release PR
updates pyproject.toml, changelog and the marked root package version in uv.lock.
The version exposed by the CLI comes from installed package metadata.

Artifacts are built from the actual version tag, checked against its independent
version, and uploaded in the same workflow that creates the release, avoiding
reliance on token-generated tag events. A manual existing-tag repair lane stays
available. No automatic PyPI publication or registry-name claim is configured.
Release PRs still need complete CI and an independent review before merging.

The agent authors scripts; Willay never calls a language model. Dialogue and
effects reserve a conservative local budget before sending, retain ambiguous
charges and skip content-identical successful takes. State is shared on one
rendering host, not an account-global usage meter across unrelated products.
A separate bounded authenticated feed reader serves only completed artifacts.
Host installation, private TLS routing and phone playback remain separate from
source controls.

References: [release-plz scope](https://release-plz.dev/docs),
[release-please Python strategy](https://github.com/googleapis/release-please/blob/main/src/strategies/python.ts),
and [release customization](https://github.com/googleapis/release-please/blob/main/docs/customizing.md).
