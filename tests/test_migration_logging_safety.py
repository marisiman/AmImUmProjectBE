from pathlib import Path


def test_alembic_migration_logging_never_emits_the_database_url():
    source = Path("migrations/env.py").read_text(encoding="utf-8")

    assert 'logger.info(f"Using database URL: {database_url}")' not in source
    assert 'logger.info("Database URL configured for Alembic.")' in source
