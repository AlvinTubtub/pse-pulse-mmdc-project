"""Regression checks for portable Boolean defaults in Alembic migrations."""

import ast
from pathlib import Path

import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.schema import CreateTable


REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION_DIR = REPO_ROOT / "backend" / "alembic" / "versions"


def _is_call(node, module_name: str, function_name: str) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == module_name
        and node.func.attr == function_name
    )


def test_migration_boolean_columns_do_not_use_integer_server_defaults():
    offenders = []
    for migration_path in sorted(MIGRATION_DIR.glob("*.py")):
        tree = ast.parse(migration_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not _is_call(node, "sa", "Column") or len(node.args) < 2:
                continue
            if not _is_call(node.args[1], "sa", "Boolean"):
                continue
            for keyword in node.keywords:
                if keyword.arg != "server_default" or not _is_call(keyword.value, "sa", "text"):
                    continue
                if keyword.value.args and isinstance(keyword.value.args[0], ast.Constant):
                    if keyword.value.args[0].value in {"0", "1"}:
                        offenders.append(f"{migration_path.name}:{node.lineno}")
    assert offenders == []


def test_boolean_default_expressions_compile_for_postgresql_and_sqlite():
    table = sa.Table(
        "boolean_defaults",
        sa.MetaData(),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("disabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    postgres_sql = str(CreateTable(table).compile(dialect=postgresql.dialect()))
    sqlite_sql = str(CreateTable(table).compile(dialect=sqlite.dialect()))

    assert "enabled BOOLEAN DEFAULT true NOT NULL" in postgres_sql
    assert "disabled BOOLEAN DEFAULT false NOT NULL" in postgres_sql
    assert "enabled BOOLEAN DEFAULT 1 NOT NULL" in sqlite_sql
    assert "disabled BOOLEAN DEFAULT 0 NOT NULL" in sqlite_sql


def test_fresh_sqlite_database_at_head_keeps_artifacts_inactive_by_default(tmp_path, monkeypatch):
    database = tmp_path / "boolean_defaults.sqlite"
    database_url = f"sqlite:///{database}"
    config = Config(str(REPO_ROOT / "backend" / "alembic.ini"))
    config.set_main_option("script_location", str(REPO_ROOT / "backend" / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    monkeypatch.setenv("DATABASE_URL", database_url)

    command.upgrade(config, "head")
    engine = sa.create_engine(database_url)
    try:
        with engine.connect() as connection:
            default_value = connection.exec_driver_sql("PRAGMA table_info(model_artifacts)").all()
        is_active = next(row for row in default_value if row["name"] == "is_active")
        assert is_active["dflt_value"] == "0"
    finally:
        engine.dispose()
