from abc import ABC, abstractmethod
from app.models import SourceResult


class AbstractFetcher(ABC):
    @abstractmethod
    async def fetch(self) -> SourceResult:
        """Fetch items from the data source and return a SourceResult."""
        ...
