import pytest
from pydantic import ValidationError

from app.core.config import Settings


@pytest.mark.parametrize("path", ["/", "/Index.html"])
def test_signup_and_login_page_is_served(client, path):
    response = client.get(path)
    assert response.status_code == 200
    assert 'id="signupForm"' in response.text
    assert 'id="loginForm"' in response.text
    assert 'src="/assets/js/auth.js"' in response.text
    assert "<<<<<<<" not in response.text


@pytest.mark.parametrize("path", ["/assets/css/styles.css", "/assets/js/auth.js"])
def test_frontend_assets_are_served(client, path):
    assert client.get(path).status_code == 200


@pytest.mark.parametrize("path", ["/.env", "/backend/.env", "/app/main.py", "/pyproject.toml"])
def test_backend_files_are_not_public(client, path):
    assert client.get(path).status_code == 404


def test_health_checks_the_database(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_security_headers_are_present(client):
    response = client.get("/api/me")
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]


def test_untrusted_host_is_rejected(client):
    assert client.get("/", headers={"Host": "attacker.example"}).status_code == 400


@pytest.mark.parametrize(
    "headers", [{"Origin": "https://attacker.example"}, {"Sec-Fetch-Site": "cross-site"}]
)
def test_cross_origin_authentication_requests_are_rejected(client, signup_payload, headers):
    response = client.post("/api/signup", json=signup_payload, headers=headers)
    assert response.status_code == 403


def test_same_origin_registration_is_allowed(client, signup_payload):
    response = client.post(
        "/api/signup", json=signup_payload, headers={"Origin": "http://testserver"}
    )
    assert response.status_code == 201


def test_non_json_signup_is_rejected(client):
    assert client.post("/api/signup", data={"name": "Jane Doe"}).status_code == 422


def test_production_requires_https():
    with pytest.raises(ValidationError, match="HTTPS"):
        Settings(_env_file=None, app_env="production", app_url="http://example.com")


def test_database_url_requires_postgresql_psycopg():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, database_url="sqlite:///accounts.db")


def test_wildcard_hosts_are_rejected():
    with pytest.raises(ValidationError, match="explicit hostnames"):
        Settings(_env_file=None, allowed_hosts=["*"])
