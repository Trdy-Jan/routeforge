import pytest

from routeforge import __main__ as entry


def test_exits_with_message_when_admin_password_missing(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ROUTEFORGE_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("ROUTEFORGE_ADMIN_PASSWORD", raising=False)
    with pytest.raises(SystemExit) as exc:
        entry.main()
    assert exc.value.code == 1
    assert "ROUTEFORGE_ADMIN_PASSWORD" in capsys.readouterr().err


def test_runs_uvicorn_with_proxy_headers(tmp_path, monkeypatch):
    monkeypatch.setenv("ROUTEFORGE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ROUTEFORGE_ADMIN_PASSWORD", "pw")
    monkeypatch.setenv("ROUTEFORGE_PORT", "9000")
    calls: dict = {}
    monkeypatch.setattr(entry.uvicorn, "run", lambda app, **kw: calls.update(kw, app=app))
    entry.main()
    assert calls["port"] == 9000 and calls["host"] == "0.0.0.0"
    assert calls["proxy_headers"] is True and calls["forwarded_allow_ips"] == "127.0.0.1"
    assert (tmp_path / "routeforge.db").exists()
