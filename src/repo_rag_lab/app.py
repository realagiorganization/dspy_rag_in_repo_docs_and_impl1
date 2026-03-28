from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .ui import render_answer_page
from .workflow import RAGAnswer, ask_repository

AnswerFn = Callable[[str, Path], RAGAnswer]


@dataclass
class RepositoryApp:
    answer_fn: AnswerFn = ask_repository

    def answer_question(self, question: str, root: Path) -> RAGAnswer:
        return self.answer_fn(question, root)

    def render_question_page(self, question: str, root: Path) -> str:
        answer = self.answer_question(question, root)
        return render_answer_page(answer)
