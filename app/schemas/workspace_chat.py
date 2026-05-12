"""Shared workspace chat enums (collaborative + student session)."""

from enum import Enum
from typing import Literal

WorkspaceActionLiteral = Literal["chat", "suggest", "improve", "modify"]


class WorkspaceAction(str, Enum):
    """Frontend workspace chat actions. Only ``modify`` triggers document edit proposals."""

    chat = "chat"
    suggest = "suggest"
    improve = "improve"
    modify = "modify"
