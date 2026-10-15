from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from tests.fakes import FakeProvider
from tests.helpers import make_settings


def build_dist(root: Path) -> Path:
    dist = root / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>app</html>")
    (dist / "assets" / "app.js").write_text("console.log(1)")
    return dist


def test_serves_pages_and_assets_with_security_headers(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, static_dir=str(build_dist(tmp_path)))
    with TestClient(create_app(settings, provider=FakeProvider())) as c:
        home = c.get("/")
        assert home.status_code == 200 and "app" in home.text
        assert "frame-ancestors 'none'" in home.headers["content-security-policy"]
        assert home.headers["x-content-type-options"] == "nosniff"
        assert c.get("/staff").status_code == 200
        assert c.head("/").status_code == 200  # uptime monitors often send HEAD
        assert c.get("/assets/app.js").status_code == 200
        assert c.get("/does-not-exist").status_code == 404
        health = c.get("/api/health")
        assert health.headers["cache-control"] == "no-store"


def test_api_only_when_frontend_is_not_built(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, static_dir=str(tmp_path / "missing"))
    with TestClient(create_app(settings, provider=FakeProvider())) as c:
        assert c.get("/").status_code == 404
        assert c.get("/api/health").json() == {"status": "ok"}
