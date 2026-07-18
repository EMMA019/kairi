"""
image.py エンドポイントの単体テスト
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_generate_image_redirect_default():
    response = client.get("/api/image/generate?prompt=1girl, anime style, kairi", follow_redirects=False)
    assert response.status_code == 307
    assert "pollinations.ai" in response.headers["location"]
    assert "1girl" in response.headers["location"]

def test_generate_image_cf_fallback(monkeypatch):
    from app.routers.settings import app_settings
    monkeypatch.setattr(app_settings, "get", lambda: {"image_engine": "cf-flux", "cf_api_token": ""})
    response = client.get("/api/image/generate?prompt=1girl, anime style, kairi", follow_redirects=False)
    assert response.status_code == 307  # トークンなしの時は自動でPollinationsへフォールバックすること
    assert "pollinations.ai" in response.headers["location"]
