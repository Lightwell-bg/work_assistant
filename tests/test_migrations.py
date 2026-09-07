"""Проверка первой миграции: применяется и создаёт ожидаемую схему."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

REPO_ROOT = Path(__file__).resolve().parent.parent


def _alembic_config(db_url: str) -> Config:
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "migrations"))
    # env.py читает URL из -x db_url, если он задан — так тест не зависит
    # от настроек .env приложения (get_x_argument смотрит на cmd_opts.x).
    cfg.cmd_opts = SimpleNamespace(x=[f"db_url={db_url}"])  # type: ignore[assignment]
    return cfg


def test_upgrade_head_creates_all_tables(tmp_path: Path) -> None:
    db_path = tmp_path / "migrations_test.db"
    db_url = f"sqlite+aiosqlite:///{db_path}"
    cfg = _alembic_config(db_url)

    command.upgrade(cfg, "head")

    sync_engine = create_engine(f"sqlite:///{db_path}")
    inspector = inspect(sync_engine)
    tables = set(inspector.get_table_names())
    assert {
        "job_postings",
        "filter_sets",
        "filter_rules",
        "drafts",
        "llm_usage",
        "upwork_job_facts",
        "search_queries",
    } <= tables

    job_columns = {col["name"] for col in inspector.get_columns("job_postings")}
    assert {"id", "external_id", "title", "status", "score_value"} <= job_columns

    filter_rule_columns = {col["name"] for col in inspector.get_columns("filter_rules")}
    assert {"filter_set_id", "position", "field", "operator", "value"} <= filter_rule_columns

    draft_columns = {col["name"] for col in inspector.get_columns("drafts")}
    assert {"job_posting_id", "content", "status"} <= draft_columns

    llm_usage_columns = {col["name"] for col in inspector.get_columns("llm_usage")}
    expected_llm_usage_columns = {
        "purpose",
        "job_external_id",
        "model",
        "prompt_tokens",
        "completion_tokens",
        "cost_usd",
    }
    assert expected_llm_usage_columns <= llm_usage_columns

    upwork_job_facts_columns = {
        col["name"] for col in inspector.get_columns("upwork_job_facts")
    }
    assert {
        "id",
        "job_external_id",
        "raw_payload",
        "created_at",
        "updated_at",
    } <= upwork_job_facts_columns

    sync_engine.dispose()


def test_upgrade_head_creates_search_queries_columns(tmp_path: Path) -> None:
    db_path = tmp_path / "search_queries_test.db"
    cfg = _alembic_config(f"sqlite+aiosqlite:///{db_path}")

    command.upgrade(cfg, "head")

    inspector = inspect(create_engine(f"sqlite:///{db_path}"))
    columns = {col["name"] for col in inspector.get_columns("search_queries")}
    assert columns == {
        "id",
        "source",
        "name",
        "query",
        "is_active",
        "created_at",
        "updated_at",
    }
