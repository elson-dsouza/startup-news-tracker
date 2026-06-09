from abc import ABC, abstractmethod
from typing import ClassVar, List, Type

from app.domain.raw_article import RawArticle


class SourcePlugin(ABC):
    _registry: ClassVar[List[Type["SourcePlugin"]]] = []
    source_id: ClassVar[str]
    display_name: ClassVar[str]

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        if getattr(cls, "source_id", None):
            cls._registry.append(cls)

    @classmethod
    def get_plugins(cls) -> List[Type["SourcePlugin"]]:
        return list(cls._registry)

    @classmethod
    def is_enabled(cls, enabled_sources: set[str]) -> bool:
        return not enabled_sources or cls.source_id in enabled_sources

    @abstractmethod
    async def fetch(self) -> List[RawArticle]: ...
