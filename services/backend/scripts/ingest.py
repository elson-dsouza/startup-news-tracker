import argparse
import asyncio
import logging

from app.db import async_session
from app.ingestion.services.ingestion_service import IngestionService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def run_once() -> tuple[int, int]:
    async with async_session() as session:
        service = IngestionService(session)
        return await service.ingest()


async def run_forever(interval: int) -> None:
    logger.info("Starting news ingestion with %ss interval", interval)

    while True:
        try:
            created, total = await run_once()
            logger.info(
                "Ingestion complete: %s new articles from %s total fetched",
                created,
                total,
            )
        except Exception:
            logger.exception("Error during ingestion")

        await asyncio.sleep(interval)


async def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest startup funding articles.")
    parser.add_argument(
        "--interval",
        type=int,
        default=3600,
        help="Interval in seconds between ingestion runs.",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run ingestion once and exit.",
    )
    args = parser.parse_args()

    if args.once:
        created, total = await run_once()
        logger.info(
            "Ingestion complete: %s new articles from %s total fetched", created, total
        )
        return

    await run_forever(args.interval)


if __name__ == "__main__":
    asyncio.run(main())
