from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker

from config import DATABASE_URL

# Создаем базовый класс для моделей
Base = declarative_base()

# Создаем асинхронный движок SQLAlchemy
engine = create_async_engine(DATABASE_URL, echo=False)

# Создаем фабрику сессий
async_session = sessionmaker(
    engine, expire_on_commit=False, class_=AsyncSession
) 