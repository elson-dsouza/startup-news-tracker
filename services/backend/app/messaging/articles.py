import asyncio
import json
import logging
from datetime import UTC, datetime
from typing import Awaitable, Callable

import aio_pika
from aio_pika.abc import AbstractIncomingMessage, AbstractRobustConnection

from app.core.config import settings
from app.domain.raw_article import RawArticle

logger = logging.getLogger(__name__)


ArticleHandler = Callable[[RawArticle], Awaitable[bool]]


class ArticleQueue:
    def __init__(
        self,
        *,
        url: str | None = None,
        queue_name: str | None = None,
        dead_letter_queue_name: str | None = None,
        max_priority: int | None = None,
        prefetch_count: int | None = None,
        max_attempts: int | None = None,
    ) -> None:
        self.url = url or settings.rabbitmq_url
        self.queue_name = queue_name or settings.article_queue_name
        self.dead_letter_queue_name = (
            dead_letter_queue_name or settings.article_queue_dead_letter_name
        )
        self.max_priority = max_priority or settings.article_queue_max_priority
        self.prefetch_count = prefetch_count or settings.article_queue_prefetch_count
        self.max_attempts = max_attempts or settings.article_queue_max_attempts
        self._connection: AbstractRobustConnection | None = None

    async def connect(self) -> None:
        if self._connection and not self._connection.is_closed:
            return
        self._connection = await aio_pika.connect_robust(self.url)

    async def close(self) -> None:
        if self._connection and not self._connection.is_closed:
            await self._connection.close()

    async def publish_articles(self, articles: list[RawArticle]) -> int:
        if not articles:
            return 0

        await self.connect()
        assert self._connection is not None
        channel = await self._connection.channel()
        await self._declare_queue(channel)

        published_count = 0
        try:
            sorted_articles = sorted(
                articles,
                key=lambda article: article.published_at or datetime.min,
                reverse=True,
            )
            for index, article in enumerate(sorted_articles):
                priority = max(self.max_priority - index, 0)
                message = aio_pika.Message(
                    body=json.dumps(raw_article_to_message(article)).encode("utf-8"),
                    content_type="application/json",
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                    priority=priority,
                    timestamp=datetime.now(UTC),
                    headers={"attempts": 0},
                )
                await channel.default_exchange.publish(
                    message,
                    routing_key=self.queue_name,
                )
                published_count += 1
        finally:
            await channel.close()

        return published_count

    async def consume_forever(self, handler: ArticleHandler) -> None:
        await self.connect()
        assert self._connection is not None
        channel = await self._connection.channel()
        await channel.set_qos(prefetch_count=self.prefetch_count)
        queue = await self._declare_queue(channel)

        async with queue.iterator() as queue_iter:
            async for message in queue_iter:
                await self._handle_message(message, handler)

    async def _handle_message(
        self,
        message: AbstractIncomingMessage,
        handler: ArticleHandler,
    ) -> None:
        try:
            article = raw_article_from_message(json.loads(message.body.decode("utf-8")))
        except (TypeError, ValueError, json.JSONDecodeError):
            logger.exception("Dropping malformed article queue message")
            await message.ack()
            return

        try:
            is_enriched = await handler(article)
        except Exception:
            logger.exception("Article queue handler failed")
            await message.nack(requeue=True)
            await asyncio.sleep(settings.article_queue_retry_delay_seconds)
            return

        if is_enriched:
            await message.ack()
            return

        await self._retry_or_dead_letter(message)

    async def _declare_queue(self, channel):
        return await channel.declare_queue(
            self.queue_name,
            durable=True,
            arguments={"x-max-priority": self.max_priority},
        )

    async def _retry_or_dead_letter(self, message: AbstractIncomingMessage) -> None:
        attempts = _message_attempts(message) + 1
        if attempts >= self.max_attempts:
            await self._publish_dead_letter(message, attempts)
            await message.ack()
            logger.warning(
                "Moved article message to %s after %s failed attempts",
                self.dead_letter_queue_name,
                attempts,
            )
            return

        await self._republish_retry(message, attempts)
        await message.ack()
        await asyncio.sleep(settings.article_queue_retry_delay_seconds)

    async def _republish_retry(
        self, message: AbstractIncomingMessage, attempts: int
    ) -> None:
        assert self._connection is not None
        channel = await self._connection.channel()
        await self._declare_queue(channel)
        try:
            await channel.default_exchange.publish(
                self._copy_message(message, attempts),
                routing_key=self.queue_name,
            )
        finally:
            await channel.close()

    async def _publish_dead_letter(
        self, message: AbstractIncomingMessage, attempts: int
    ) -> None:
        assert self._connection is not None
        channel = await self._connection.channel()
        await channel.declare_queue(
            self.dead_letter_queue_name,
            durable=True,
            arguments={"x-max-priority": self.max_priority},
        )
        try:
            await channel.default_exchange.publish(
                self._copy_message(message, attempts),
                routing_key=self.dead_letter_queue_name,
            )
        finally:
            await channel.close()

    @staticmethod
    def _copy_message(
        message: AbstractIncomingMessage,
        attempts: int,
    ) -> aio_pika.Message:
        headers = dict(message.headers or {})
        headers["attempts"] = attempts
        return aio_pika.Message(
            body=bytes(message.body),
            content_type=message.content_type,
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            priority=message.priority,
            timestamp=datetime.now(UTC),
            headers=headers,
        )


def _message_attempts(message: AbstractIncomingMessage) -> int:
    headers = message.headers or {}
    try:
        return int(headers.get("attempts") or 0)
    except (TypeError, ValueError):
        return 0


def raw_article_to_message(article: RawArticle) -> dict[str, str | None]:
    return {
        "source": article.source,
        "title": article.title,
        "url": article.url,
        "published_at": (
            article.published_at.isoformat() if article.published_at else None
        ),
        "content": article.content,
        "external_id": article.external_id,
        "source_url": article.source_url,
    }


def raw_article_from_message(payload: dict[str, object]) -> RawArticle:
    published_at = payload.get("published_at")
    if isinstance(published_at, str) and published_at:
        parsed_published_at = datetime.fromisoformat(published_at)
    else:
        parsed_published_at = None

    return RawArticle(
        source=str(payload["source"]),
        title=str(payload["title"]),
        url=str(payload["url"]),
        published_at=parsed_published_at,
        content=_optional_string(payload.get("content")),
        external_id=_optional_string(payload.get("external_id")),
        source_url=_optional_string(payload.get("source_url")),
    )


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
