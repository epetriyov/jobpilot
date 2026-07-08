"""Shared kernel (DOMAIN.md §2): единый язык, общие VO и события."""

from app.domain.shared.events import DomainEvent
from app.domain.shared.values import PromptVersion, Salary, Source, SourceRef

__all__ = ["DomainEvent", "PromptVersion", "Salary", "Source", "SourceRef"]
