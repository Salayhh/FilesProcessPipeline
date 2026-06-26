"""Backward-compatible imports for the renamed LLM client."""

from files_pipeline.clients.llm import OpenAICompatibleClient


KimiClient = OpenAICompatibleClient

__all__ = ["KimiClient", "OpenAICompatibleClient"]
