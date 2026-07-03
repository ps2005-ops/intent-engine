"""The contract every pipeline stage implements, so stages stay swappable and testable in isolation."""

from abc import ABC, abstractmethod
from typing import Any


class Stage(ABC):
    name: str = "stage"

    @abstractmethod
    def run(self, *args, **kwargs) -> Any:
        ...
