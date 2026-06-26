"""Backward-compatible imports for the renamed organize stage."""

from files_pipeline.stages.organize import OrganizeStage, read_text_with_fallback


KimiStage = OrganizeStage

__all__ = ["KimiStage", "OrganizeStage", "read_text_with_fallback"]
