from datetime import UTC, datetime

import pytest

from willay import provider
from willay.spec import Refused
from willay.store import Store


def test_day_override_expires_without_resetting_charges(tmp_path, monkeypatch):
    s = Store(tmp_path)
    monkeypatch.setenv("WILLAY_DAILY_CHARACTER_CAP", "60000")
    monkeypatch.setenv("WILLAY_DAILY_REQUEST_CAP", "60")
    assert s.caps() == (20000, 20)
    monkeypatch.setenv("WILLAY_CAP_OVERRIDE_DATE", datetime.now(UTC).date().isoformat())
    assert s.caps() == (60000, 60)
    s.db.execute(
        "insert into takes(id,day,chars,seconds,status) values(?,?,?,?,?)",
        ("uncertain", s.usage()["day_utc"], 264, 0, "reserved"),
    )
    s.db.commit()
    monkeypatch.setenv("WILLAY_CAP_OVERRIDE_DATE", "2000-01-01")
    assert s.caps() == (20000, 20)
    assert s.usage()["reserved_characters"] == 264


def test_override_is_bounded_and_fail_closed(tmp_path, monkeypatch):
    monkeypatch.setenv("WILLAY_CAP_OVERRIDE_DATE", datetime.now(UTC).date().isoformat())
    monkeypatch.setenv("WILLAY_DAILY_REQUEST_CAP", "61")
    with pytest.raises(Refused):
        Store(tmp_path).usage()


def test_generation_timeout_diagnostics_without_secrets(monkeypatch):
    class Opener:
        def open(self, req, timeout):
            assert timeout == 300
            raise TimeoutError("synthetic_secret_must_not_appear")

    monkeypatch.setattr(provider.urllib.request, "build_opener", lambda *_: Opener())
    with pytest.raises(Refused) as caught:
        provider.call("dialogue", {"inputs": []}, "synthetic_key_must_not_appear")
    message = str(caught.value)
    assert "TimeoutError" in message and "charge reserved" in message
    assert "synthetic_" not in message


def test_override_admits_request_and_expiry_refuses_same_ledger(tmp_path, monkeypatch):
    from willay.spec import Piece

    s = Store(tmp_path)
    for i in range(20):
        s.db.execute(
            "insert into takes(id,day,chars,seconds,status) values(?,?,?,?,?)",
            (str(i), s.usage()["day_utc"], 1, 0, "reserved"),
        )
    s.db.commit()
    p = Piece("dialogue", {"inputs": [{"text": "new", "voice_id": "a"}]}, "test")
    with pytest.raises(Refused):
        s.preflight([p])
    monkeypatch.setenv("WILLAY_CAP_OVERRIDE_DATE", datetime.now(UTC).date().isoformat())
    monkeypatch.setenv("WILLAY_DAILY_REQUEST_CAP", "60")
    assert s.preflight([p]) == [p]
    monkeypatch.setenv("WILLAY_CAP_OVERRIDE_DATE", "2000-01-01")
    with pytest.raises(Refused):
        s.preflight([p])
    assert s.usage()["reserved_requests"] == 20
