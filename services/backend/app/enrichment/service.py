import logging
import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from uuid import UUID, uuid4

from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.domain.raw_article import RawArticle
from app.enrichment.extraction import ArticleExtractor, ExtractionResult
from app.enrichment.llama_cpp import LlamaCppClient, LlamaCppResult
from app.models.article import (
    Article,
    ArticleEnrichment,
    ArticleEnrichmentJob,
    ArticleEntity,
)

logger = logging.getLogger(__name__)


RETRYABLE_STATUSES = {"pending", "failed"}


class EnrichmentService:
    def __init__(
        self,
        session: AsyncSession,
        extractor: ArticleExtractor | None = None,
        llm_client: LlamaCppClient | None = None,
    ) -> None:
        self.session = session
        self.extractor = extractor or ArticleExtractor()
        self.llm_client = llm_client or LlamaCppClient()

    async def enrich_batch(self, batch_size: int | None = None) -> tuple[int, int]:
        if not settings.enrichment_enabled:
            logger.info("Article enrichment is disabled")
            return 0, 0

        await self.enqueue_missing_jobs(batch_size=batch_size)
        jobs = await self._claim_jobs(batch_size or settings.enrichment_batch_size)
        enriched_count = 0
        processed_count = 0
        for job in jobs:
            article = await self._fetch_article(job.article_id)
            if article is None:
                await self._mark_job_done(job)
                processed_count += 1
                continue

            try:
                is_enriched = await self._enrich_article(article)
            except Exception as exc:
                logger.exception("Article enrichment job %s failed", job.id)
                await self._mark_job_retryable(job, str(exc))
                processed_count += 1
                continue

            processed_count += 1
            if is_enriched:
                enriched_count += 1

            enrichment_status = (
                article.enrichment.enrichment_status if article.enrichment else None
            )
            if is_enriched or enrichment_status == "skipped":
                await self._mark_job_done(job)
            else:
                error = (
                    article.enrichment.enrichment_error
                    if article.enrichment
                    else "AI enrichment failed."
                )
                await self._mark_job_retryable(job, error)

        return enriched_count, processed_count

    async def enqueue_missing_jobs(self, batch_size: int | None = None) -> int:
        candidates = await self._fetch_candidates(
            batch_size or settings.enrichment_batch_size
        )
        if not candidates:
            return 0

        existing_result = await self.session.execute(
            select(ArticleEnrichmentJob.article_id).where(
                ArticleEnrichmentJob.article_id.in_(
                    [article.id for article in candidates]
                )
            )
        )
        existing_article_ids = {row[0] for row in existing_result.fetchall()}
        jobs = [
            ArticleEnrichmentJob(
                article_id=article.id,
                max_attempts=settings.enrichment_job_max_attempts,
            )
            for article in candidates
            if article.id not in existing_article_ids
        ]
        if not jobs:
            return 0

        self.session.add_all(jobs)
        await self.session.commit()
        return len(jobs)

    async def _fetch_candidates(self, batch_size: int) -> list[Article]:
        statement = (
            select(Article)
            .outerjoin(ArticleEnrichment)
            .options(selectinload(Article.enrichment), selectinload(Article.entities))
            .where(
                or_(
                    ArticleEnrichment.article_id.is_(None),
                    ArticleEnrichment.enrichment_status.in_(RETRYABLE_STATUSES),
                    ArticleEnrichment.extraction_status.in_(RETRYABLE_STATUSES),
                )
            )
            .order_by(Article.published_at.desc(), Article.created_at.desc())
            .limit(batch_size)
        )
        result = await self.session.execute(statement)
        return list(result.scalars().unique().all())

    async def _claim_jobs(self, batch_size: int) -> list[ArticleEnrichmentJob]:
        now = datetime.now(UTC)
        stale_before = now - timedelta(
            seconds=settings.enrichment_job_stale_after_seconds
        )
        statement = (
            select(ArticleEnrichmentJob)
            .where(
                or_(
                    and_(
                        ArticleEnrichmentJob.status == "queued",
                        ArticleEnrichmentJob.next_attempt_at <= now,
                    ),
                    and_(
                        ArticleEnrichmentJob.status == "failed",
                        ArticleEnrichmentJob.attempts
                        < ArticleEnrichmentJob.max_attempts,
                        ArticleEnrichmentJob.next_attempt_at <= now,
                    ),
                    and_(
                        ArticleEnrichmentJob.status == "processing",
                        ArticleEnrichmentJob.locked_at < stale_before,
                    ),
                )
            )
            .order_by(
                ArticleEnrichmentJob.priority.desc(),
                ArticleEnrichmentJob.created_at.asc(),
            )
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        )
        result = await self.session.execute(statement)
        jobs = list(result.scalars().all())
        for job in jobs:
            job.status = "processing"
            job.attempts += 1
            job.locked_at = now
            job.last_error = None

        if jobs:
            await self.session.commit()
        return jobs

    async def _fetch_article(self, article_id: UUID) -> Article | None:
        result = await self.session.execute(
            select(Article)
            .options(selectinload(Article.enrichment), selectinload(Article.entities))
            .where(Article.id == article_id)
        )
        return result.scalars().unique().one_or_none()

    async def _mark_job_done(self, job: ArticleEnrichmentJob) -> None:
        job.status = "done"
        job.locked_at = None
        job.last_error = None
        await self.session.commit()

    async def _mark_job_retryable(
        self, job: ArticleEnrichmentJob, error: str | None
    ) -> None:
        job.locked_at = None
        job.last_error = (error or "Article enrichment failed.")[:1000]
        if job.attempts >= job.max_attempts:
            job.status = "failed"
        else:
            job.status = "queued"
            job.next_attempt_at = datetime.now(UTC) + timedelta(
                seconds=settings.enrichment_job_retry_delay_seconds
            )
        await self.session.commit()

    async def enrich_raw_article(self, raw_article: RawArticle) -> bool:
        if not settings.enrichment_enabled:
            logger.info("Article enrichment is disabled")
            return False

        existing_result = await self.session.execute(
            select(Article.id).where(Article.url == raw_article.url)
        )
        if existing_result.scalar_one_or_none() is not None:
            return True

        article = Article(
            id=uuid4(),
            source=raw_article.source,
            title=raw_article.title,
            url=raw_article.url,
            external_id=raw_article.external_id,
            source_url=raw_article.source_url,
            published_at=raw_article.published_at,
            content=raw_article.content,
        )
        enrichment = ArticleEnrichment(article_id=article.id)
        article.enrichment = enrichment

        if not await self._populate_enrichment(article):
            await self.session.rollback()
            return False

        self.session.add(article)
        try:
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            return True

        return True

    async def _enrich_article(self, article: Article) -> bool:
        enrichment = article.enrichment or ArticleEnrichment(article_id=article.id)
        article.enrichment = enrichment
        is_enriched = await self._populate_enrichment(article)
        await self.session.commit()
        return is_enriched

    async def _populate_enrichment(self, article: Article) -> bool:
        enrichment = article.enrichment
        if enrichment is None:
            enrichment = ArticleEnrichment(article_id=article.id)
            article.enrichment = enrichment

        extraction = await self._extract_article_text(article)
        enrichment_text = extraction.text
        extraction_status = extraction.status
        extraction_error = extraction.error
        if extraction.status != "extracted" or not extraction.text:
            enrichment_text = clean_feed_content(article.content)
            if enrichment_text:
                extraction_status = "feed_fallback"
                extraction_error = None

        enrichment.extraction_status = extraction_status
        enrichment.full_text = enrichment_text
        enrichment.extraction_error = extraction_error

        if not enrichment_text:
            enrichment.enrichment_status = "skipped"
            enrichment.enrichment_error = (
                extraction_error or "No article text or feed content available."
            )
            return False

        ai_result = await self.llm_client.enrich_article(
            title=article.title,
            source=article.source,
            url=extraction.final_url or article.url,
            published_at=(
                article.published_at.isoformat() if article.published_at else None
            ),
            rss_content=article.content,
            full_text=enrichment_text,
        )
        self._apply_ai_result(article, enrichment, ai_result)
        return ai_result.status == "enriched"

    async def _extract_article_text(self, article: Article) -> ExtractionResult:
        urls_to_try: list[str] = []
        if article.source_url:
            urls_to_try.append(article.source_url)
        if article.url not in urls_to_try:
            urls_to_try.append(article.url)

        last_result: ExtractionResult | None = None
        for url in urls_to_try:
            result = await self.extractor.extract(url)
            last_result = result
            if result.status == "extracted" and result.text:
                return result

        if last_result is not None:
            return last_result

        return ExtractionResult(
            status="failed",
            final_url=article.url,
            error="No article URL available for extraction.",
        )

    def _apply_ai_result(
        self,
        article: Article,
        enrichment: ArticleEnrichment,
        ai_result: LlamaCppResult,
    ) -> None:
        enrichment.model_name = ai_result.model_name
        if ai_result.status != "enriched" or ai_result.payload is None:
            enrichment.enrichment_status = "failed"
            enrichment.enrichment_error = ai_result.error or "AI enrichment failed."
            return

        payload = ai_result.payload
        enrichment.enrichment_status = "enriched"
        enrichment.enrichment_error = None
        enrichment.summary = payload.summary
        enrichment.startup_country = payload.startup_country
        enrichment.publisher_country = payload.publisher_country
        enrichment.mentioned_countries = payload.mentioned_countries
        enrichment.funding_amount_original = payload.funding_amount_original
        enrichment.funding_currency_original = payload.funding_currency_original
        enrichment.funding_amount_usd = self._decimal_or_none(
            payload.funding_amount_usd
        )
        enrichment.funding_round = payload.funding_round
        enrichment.generated_at = datetime.now(UTC)

        article.entities.clear()
        seen: set[tuple[str, str]] = set()
        for entity in payload.entities:
            normalized_name = normalize_entity_name(entity.name)
            key = (entity.entity_type, normalized_name)
            if not normalized_name or key in seen:
                continue
            seen.add(key)
            article.entities.append(
                ArticleEntity(
                    article_id=article.id,
                    entity_type=entity.entity_type,
                    name=entity.name.strip(),
                    normalized_name=normalized_name,
                )
            )

    @staticmethod
    def _decimal_or_none(value: str | None) -> Decimal | None:
        if value is None:
            return None
        cleaned = re.sub(r"[^0-9.\-]", "", value)
        if not cleaned:
            return None
        try:
            return Decimal(cleaned)
        except InvalidOperation:
            return None


def normalize_entity_name(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def clean_feed_content(value: str | None) -> str | None:
    if not value:
        return None
    text = re.sub(r"<[^>]+>", " ", value)
    text = re.sub(r"\s+", " ", text).strip()
    return text or None
