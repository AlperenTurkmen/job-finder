"""Unified agents package for job-finder.

Subpackages:
- discovery: Find careers pages and extract job URLs
- scoring: Evaluate roles for fit (for-me and for-them scores)
- cover_letter: Generate and refine cover letters
- common: Shared utilities (Gemini client, profile, orchestration)
- auto_apply: Playwright-based form filling and submission
"""

from agents.discovery import (
    GeminiClient,
    choose_careers_page,
    extract_all_job_urls,
    run_normaliser,
    ConversionResult,
)
from agents.scoring import (
    ForMeScoreAgent,
    ForThemScoreAgent,
    RoleEvaluationEngine,
    RoleValidationAgent,
)
from agents.cover_letter import (
    CoverLetterGeneratorAgent,
    HRSimulationAgent,
    StyleExtractorAgent,
)
from agents.common import (
    GeminiConfig,
    ProfileAgent,
    OrchestratorAgent,
    InsightGeneratorAgent,
    RoleAnalysisAgent,
    CSVWriterAgent,
)
from agents.auto_apply import AutoApplyOrchestrator, PlaywrightSession

__all__ = [
    # Discovery
    "GeminiClient",
    "choose_careers_page",
    "extract_all_job_urls",
    "run_normaliser",
    "ConversionResult",
    # Scoring
    "ForMeScoreAgent",
    "ForThemScoreAgent",
    "RoleEvaluationEngine",
    "RoleValidationAgent",
    # Cover Letter
    "CoverLetterGeneratorAgent",
    "HRSimulationAgent",
    "StyleExtractorAgent",
    # Common
    "GeminiConfig",
    "ProfileAgent",
    "OrchestratorAgent",
    "InsightGeneratorAgent",
    "RoleAnalysisAgent",
    "CSVWriterAgent",
    # Auto-Apply
    "AutoApplyOrchestrator",
    "PlaywrightSession",
]
