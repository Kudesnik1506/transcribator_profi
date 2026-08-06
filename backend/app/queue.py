from arq import create_pool
from arq.connections import RedisSettings

from app.config import settings


async def get_queue():
    return await create_pool(RedisSettings.from_dsn(settings.redis_url))
