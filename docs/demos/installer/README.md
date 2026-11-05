The recording runs the actual embedded installer through the retained fixture
controls. It demonstrates successful private installation, retained-destination
refusal, checksum refusal before destination creation, and wrong-version cleanup.
HTTP and uv are mocked. It does not prove a real wheel installs on any OS.

Reproduce with `python3 docs/demos/installer/demo.py`. Replay the recorded terminal
with `scriptreplay --log-timing docs/demos/installer/timing.log --log-out
docs/demos/installer/output.log`. The hosted installer workflow separately tests
the real published v0.1.0 wheel; those results remain pending.
