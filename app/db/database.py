
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine, async_sessionmaker, AsyncSession
from logger import setup_db_logger
from config import settings

#Инициализируем файловый логгер для базы данных
setup_db_logger("sqlalchemy.log")


async_engine = create_async_engine(
    url= settings.DATABASE_URL_asyncpg,
    echo=False,
)

async_session_factory = async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)



async def get_db():
    """
    Генератор изолированных сессий базы данных для эндпоинтов FastAPI.
    """
    async with async_session_factory() as session:
        yield session