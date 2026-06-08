from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings


def get_engine() -> AsyncEngine:
    return create_async_engine(settings.database_url, future=True, echo=False)


engine = get_engine()
async_session = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    future=True,
)
