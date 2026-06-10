import argparse
import asyncio
import logging

from app.db import async_session
from app.enrichment.service import EnrichmentService
from app.messaging.articles import ArticleQueue

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def run_once(batch_size: int | None = None) -> tuple[int, int]:
    async with async_session() as session:
        service = EnrichmentService(session)
        return await service.enrich_batch(batch_size=batch_size)


async def run_forever(idle_interval: float, batch_size: int | None = None) -> None:
    logger.info(
        "Starting queued article enrichment with %ss idle interval",
        idle_interval,
    )

    while True:
        try:
            enriched, total = await run_once(batch_size=batch_size)
            logger.info(
                "Enrichment complete: %s enriched from %s queued jobs",
                enriched,
                total,
            )
        except Exception:
            logger.exception("Error during enrichment")
            total = 0

        if total == 0:
            await asyncio.sleep(idle_interval)


async def consume_queue() -> None:
    queue = ArticleQueue()

    async def handle_article(article) -> bool:
        async with async_session() as session:
            service = EnrichmentService(session)
            return await service.enrich_raw_article(article)

    logger.info("Starting RabbitMQ article enrichment consumer")
    await queue.consume_forever(handle_article)


async def main() -> None:
    parser = argparse.ArgumentParser(description="Enrich startup funding articles.")
    parser.add_argument(
        "--interval",
        type=int,
        default=None,
        help="Deprecated alias for --idle-interval.",
    )
    parser.add_argument(
        "--idle-interval",
        type=float,
        default=None,
        help="Seconds to sleep when no queued enrichment jobs are available.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=None,
        help="Maximum articles to enrich per run.",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run enrichment once and exit.",
    )
    parser.add_argument(
        "--poll-db",
        action="store_true",
        help="Use the deprecated database-backed enrichment job loop.",
    )
    args = parser.parse_args()

    if args.once:
        enriched, total = await run_once(batch_size=args.batch_size)
        logger.info(
            "Enrichment complete: %s enriched from %s candidates",
            enriched,
            total,
        )
        return

    if args.poll_db:
        idle_interval = (
            args.idle_interval
            if args.idle_interval is not None
            else args.interval if args.interval is not None else 5.0
        )
        await run_forever(idle_interval, batch_size=args.batch_size)
        return

    await consume_queue()


if __name__ == "__main__":
    asyncio.run(main())
