from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str = (
        "postgresql+asyncpg://startup_news:startup_news@localhost:5432/startup_news"
    )
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    enabled_sources: str = ""
    source_timeout_seconds: float = 30.0
    source_user_agent: str = "StartupNewsTracker/1.0 (+https://localhost)"
    google_news_queries_path: str = "app/ingestion/config/google_news.yaml"
    llama_cpp_base_url: str = "http://localhost:8080/v1"
    llama_cpp_model: str = "qwen3-1.7b"
    enrichment_enabled: bool = True
    enrichment_batch_size: int = 10
    enrichment_idle_interval_seconds: float = 5.0
    enrichment_job_max_attempts: int = 3
    enrichment_job_retry_delay_seconds: int = 300
    enrichment_job_stale_after_seconds: int = 1800
    rabbitmq_url: str = "amqp://startup_news:startup_news@localhost:5672/"
    article_queue_name: str = "article.enrichment"
    article_queue_max_priority: int = 255
    article_queue_prefetch_count: int = 1
    article_queue_retry_delay_seconds: int = 300
    article_queue_max_attempts: int = 3
    article_queue_dead_letter_name: str = "article.enrichment.failed"

    @property
    def allowed_cors_origins(self) -> list[str]:
        return [
            origin.strip() for origin in self.cors_origins.split(",") if origin.strip()
        ]

    @property
    def enabled_source_ids(self) -> set[str]:
        return {
            source.strip()
            for source in self.enabled_sources.split(",")
            if source.strip()
        }


settings = Settings()
