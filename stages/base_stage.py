"""Base class for all pipeline stages."""
from abc import ABC, abstractmethod
from typing import Any, Dict

from config import Config


class BaseStage(ABC):
    """Abstract base class for pipeline stages."""

    def __init__(self, config: Config = None):
        self.config = config or Config()
        self.stats = {"success": 0, "failed": 0}

    @abstractmethod
    def run(self, *args, **kwargs) -> Dict[str, Any]:
        """Execute the stage."""
        pass

    def get_stats(self) -> Dict[str, int]:
        """Get stage statistics."""
        return self.stats.copy()
