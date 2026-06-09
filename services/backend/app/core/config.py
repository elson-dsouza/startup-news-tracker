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
