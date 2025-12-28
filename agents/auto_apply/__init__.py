"""Auto-apply multi-agent system package."""

from .context import AutoApplyContext, FieldDescriptor, AnswerRecord, NavigatorResult
from .playwright_client import PlaywrightSession, PlaywrightClientError
from .knowledge_base import KnowledgeBase
from .application_navigator_agent import ApplicationNavigatorAgent
from .answer_validity_agent import AnswerValidityAgent
from .user_input_agent import UserInputRequiredAgent
from .application_submit_agent import ApplicationSubmitAgent
from .application_writer_agent import ApplicationWriterAgent
from .failure_writer_agent import FailureWriterAgent
from .orchestrator import AutoApplyOrchestrator

__all__ = [
    "AutoApplyContext",
    "FieldDescriptor",
    "AnswerRecord",
    "NavigatorResult",
    "PlaywrightSession",
    "PlaywrightClientError",
    "KnowledgeBase",
    "ApplicationNavigatorAgent",
    "AnswerValidityAgent",
    "UserInputRequiredAgent",
    "ApplicationSubmitAgent",
    "ApplicationWriterAgent",
    "FailureWriterAgent",
    "AutoApplyOrchestrator",
]
