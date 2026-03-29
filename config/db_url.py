"""Normalize database URLs for SQLAlchemy async drivers (Railway uses postgresql://)."""


def normalize_database_url_for_async(url: str) -> str:
    """Railway / Heroku often expose postgres as postgresql:// or postgres:// — async needs asyncpg."""
    if not url:
        return url
    if url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + url[len("postgresql://") :]
    if url.startswith("postgres://"):
        return "postgresql+asyncpg://" + url[len("postgres://") :]
    return url
