from abc import ABC, abstractmethod
from typing import ClassVar, List, Type

from app.domain.raw_article import RawArticle


class SourcePlugin(ABC):
    _registry: ClassVar[List[Type["SourcePlugin"]]] = []

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        if cls.__name__ != "SourcePlugin":
            cls._registry.append(cls)

    @classmethod
    def get_plugins(cls) -> List[Type["SourcePlugin"]]:
        return list(cls._registry)

    @abstractmethod
    async def fetch(self) -> List[RawArticle]: ...
