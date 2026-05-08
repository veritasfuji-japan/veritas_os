"""Regression tests for Docker Compose credential hardening."""

from pathlib import Path


def test_docker_compose_exists() -> None:
    assert Path("docker-compose.yml").exists()


def test_docker_compose_has_no_unsafe_defaults() -> None:
    compose = Path("docker-compose.yml").read_text(encoding="utf-8")
    forbidden = [
        "POSTGRES_PASSWORD: ${VERITAS_DB_PASSWORD:-veritas}",
        "postgresql://veritas:veritas@postgres:5432/veritas",
        "VERITAS_BFF_SESSION_TOKEN: ${VERITAS_BFF_SESSION_TOKEN:-veritas-dev-session}",
        "VERITAS_BFF_AUTH_TOKENS_JSON: ${VERITAS_BFF_AUTH_TOKENS_JSON:-'{\"veritas-dev-session\":\"admin\"}'}",
        "veritas-dev-session",
    ]
    for token in forbidden:
        assert token not in compose


def test_docker_compose_requires_explicit_secrets() -> None:
    compose = Path("docker-compose.yml").read_text(encoding="utf-8")
    required_patterns = [
        "${VERITAS_DB_PASSWORD:?",
        "${VERITAS_DATABASE_URL:?",
        "${VERITAS_BFF_SESSION_TOKEN:?",
        "${VERITAS_BFF_AUTH_TOKENS_JSON:?",
    ]
    for pattern in required_patterns:
        assert pattern in compose


def test_env_example_exists_with_change_me_placeholders() -> None:
    env_example = Path(".env.example")
    assert env_example.exists()
    text = env_example.read_text(encoding="utf-8")
    assert "CHANGE_ME" in text
    assert "VERITAS_DB_PASSWORD=" in text
    assert "VERITAS_DATABASE_URL=" in text
    assert "VERITAS_BFF_SESSION_TOKEN=" in text
    assert "VERITAS_BFF_AUTH_TOKENS_JSON=" in text


def test_env_example_has_no_legacy_insecure_values() -> None:
    text = Path(".env.example").read_text(encoding="utf-8")
    forbidden = [
        "veritas-dev-session",
        "postgresql://veritas:veritas@postgres:5432/veritas",
        "VERITAS_DB_PASSWORD=veritas",
    ]
    for token in forbidden:
        assert token not in text


def test_docs_exist_and_include_security_boundaries() -> None:
    en_doc = Path("docs/en/operations/docker-compose-security.md")
    ja_doc = Path("docs/ja/operations/docker-compose-security.md")
    assert en_doc.exists()
    assert ja_doc.exists()

    en_text = en_doc.read_text(encoding="utf-8")
    assert "does not provide default database or admin BFF credentials" in en_text
    assert "Copy `.env.example` to `.env`" in en_text
    assert "replace every `CHANGE_ME` value" in en_text
    assert "Do not commit `.env`" in en_text
    assert "not production SLA" in en_text

    ja_text = ja_doc.read_text(encoding="utf-8")
    assert ".env.example" in ja_text
    assert "CHANGE_ME" in ja_text
    assert "本番SLAを意味しません" in ja_text


def test_docs_links_exist() -> None:
    assert "docs/en/operations/docker-compose-security.md" in Path("README.md").read_text(
        encoding="utf-8"
    )
    assert "docker-compose-security.md" in Path("docs/INDEX.md").read_text(
        encoding="utf-8"
    )
    assert "docker-compose-security.md" in Path(
        "docs/DOCUMENTATION_MAP.md"
    ).read_text(encoding="utf-8")
