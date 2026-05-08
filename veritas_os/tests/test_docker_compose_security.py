"""Regression tests for Docker Compose credential hardening docs/config."""

from pathlib import Path


def test_docker_compose_exists() -> None:
    assert Path("docker-compose.yml").exists()


def test_docker_compose_has_no_unsafe_defaults() -> None:
    text = Path("docker-compose.yml").read_text(encoding="utf-8")
    blocked_patterns = [
        "${VERITAS_DB_PASSWORD:-",
        "${VERITAS_DATABASE_URL:-",
        "${VERITAS_BFF_SESSION_TOKEN:-",
        "${VERITAS_BFF_AUTH_TOKENS_JSON:-",
        "veritas-dev-session",
        "postgresql://veritas:veritas@",
        "VERITAS_DB_PASSWORD=veritas",
    ]
    for pattern in blocked_patterns:
        assert pattern not in text


def test_docker_compose_requires_explicit_secrets() -> None:
    text = Path("docker-compose.yml").read_text(encoding="utf-8")
    required = [
        "${VERITAS_DB_PASSWORD:?",
        "${VERITAS_DATABASE_URL:?",
        "${VERITAS_BFF_SESSION_TOKEN:?",
        "${VERITAS_BFF_AUTH_TOKENS_JSON:?",
    ]
    for item in required:
        assert item in text


def test_bff_auth_tokens_json_interpolation_is_quoted() -> None:
    text = Path("docker-compose.yml").read_text(encoding="utf-8")
    assert (
        "VERITAS_BFF_AUTH_TOKENS_JSON: "
        "'${VERITAS_BFF_AUTH_TOKENS_JSON:?"
    ) in text


def test_env_example_keeps_operator_template_tokens() -> None:
    text = Path(".env.example").read_text(encoding="utf-8")
    required = [
        "VERITAS_API_BASE_URL",
        "VERITAS_ENV=production",
        "VERITAS_ENCRYPTION_KEY",
        "VERITAS_DATABASE_URL=",
        "VERITAS_BFF_AUTH_TOKENS_JSON=",
        "CHANGE_ME",
    ]
    assert (
        "VERITAS_DB_PASSWORD=CHANGE_ME" in text
        or "VERITAS_DB_PASSWORD=CHANGE_ME_generate_a_strong_local_password" in text
    )
    assert (
        "VERITAS_BFF_SESSION_TOKEN=CHANGE_ME" in text
        or "VERITAS_BFF_SESSION_TOKEN=CHANGE_ME_generate_a_random_local_session_token" in text
    )
    for item in required:
        assert item in text


def test_env_example_has_no_legacy_insecure_values() -> None:
    text = Path(".env.example").read_text(encoding="utf-8")
    blocked = [
        "veritas-dev-session",
        "postgresql://veritas:veritas@postgres:5432/veritas",
        "postgresql://veritas:veritas@localhost:5432/veritas",
        "VERITAS_DB_PASSWORD=veritas",
    ]
    for item in blocked:
        assert item not in text


def test_docs_exist_and_include_boundaries() -> None:
    en_text = Path("docs/en/operations/docker-compose-security.md").read_text(
        encoding="utf-8"
    ).lower()
    ja_text = Path("docs/ja/operations/docker-compose-security.md").read_text(
        encoding="utf-8"
    )

    en_required = [
        "does not provide default database or admin bff credentials",
        "copy `.env.example` to `.env`",
        "replace every `change_me` value",
        "do not commit `.env`",
        "not production sla",
    ]
    for item in en_required:
        assert item in en_text

    ja_required = [".env.example", "CHANGE_ME", "本番SLA", "コミットしない"]
    for item in ja_required:
        assert item in ja_text


def test_docs_links_exist() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    index = Path("docs/INDEX.md").read_text(encoding="utf-8")
    documentation_map = Path("docs/DOCUMENTATION_MAP.md").read_text(encoding="utf-8")

    assert "docs/en/operations/docker-compose-security.md" in readme
    assert "docker-compose-security.md" in index
    assert "docker-compose-security.md" in documentation_map


def test_readme_has_no_known_compose_database_password_examples() -> None:
    text = Path("README.md").read_text(encoding="utf-8")
    blocked = [
        "postgresql://veritas:veritas@postgres",
        "postgresql://veritas:veritas@localhost",
        "veritas:veritas@",
    ]
    for item in blocked:
        assert item not in text
