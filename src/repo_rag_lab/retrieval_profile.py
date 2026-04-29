"""Profile-driven retrieval weighting, exclusions, and repo-local overrides."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Any

DEFAULT_RETRIEVAL_PROFILE_PATH = Path("config/retrieval-profile.json")
SUPPORTED_RETRIEVAL_MODES = frozenset({"lexical", "idf-rerank"})


@dataclass(frozen=True)
class SubpathAdjustment:
    """One additive source-score adjustment keyed by a contiguous source subpath."""

    path: tuple[str, ...]
    value: float


@dataclass(frozen=True)
class ContextualPathRule:
    """One additive source-score adjustment gated by path and question-term conditions."""

    value: float
    path_name: str | None = None
    subpath: tuple[str, ...] | None = None
    required_terms: frozenset[str] = frozenset()
    required_term_prefix: str | None = None


@dataclass(frozen=True)
class RetrievalProfile:
    """Configurable retrieval weighting and exclusion rules."""

    name: str = "generic-default"
    retrieval_mode: str = "lexical"
    rerank_candidate_pool_size: int = 24
    source_adjustments_by_name: dict[str, float] = field(default_factory=dict)
    source_adjustments_by_part: dict[str, float] = field(default_factory=dict)
    subpath_adjustments: tuple[SubpathAdjustment, ...] = ()
    contextual_rules: tuple[ContextualPathRule, ...] = ()
    excluded_names: frozenset[str] = frozenset()
    excluded_parts: frozenset[str] = frozenset()
    excluded_subpaths: tuple[tuple[str, ...], ...] = ()
    path_term_overlap_bonus: float = 0.45
    definition_pattern_bonus: float = 2.0
    question_echo_penalty: float = 4.2
    document_seeking_markdown_bonus: float = 0.8
    document_seeking_documentation_bonus: float = 0.9
    document_seeking_readme_bonus: float = 0.4
    code_seeking_source_bonus: float = 1.4

    def merged_with(self, overlay: RetrievalProfile) -> RetrievalProfile:
        """Return a profile that overlays ``overlay`` on top of ``self``."""

        return RetrievalProfile(
            name=overlay.name or self.name,
            retrieval_mode=overlay.retrieval_mode or self.retrieval_mode,
            rerank_candidate_pool_size=overlay.rerank_candidate_pool_size,
            source_adjustments_by_name={
                **self.source_adjustments_by_name,
                **overlay.source_adjustments_by_name,
            },
            source_adjustments_by_part={
                **self.source_adjustments_by_part,
                **overlay.source_adjustments_by_part,
            },
            subpath_adjustments=(*self.subpath_adjustments, *overlay.subpath_adjustments),
            contextual_rules=(*self.contextual_rules, *overlay.contextual_rules),
            excluded_names=frozenset((*self.excluded_names, *overlay.excluded_names)),
            excluded_parts=frozenset((*self.excluded_parts, *overlay.excluded_parts)),
            excluded_subpaths=(*self.excluded_subpaths, *overlay.excluded_subpaths),
            path_term_overlap_bonus=overlay.path_term_overlap_bonus,
            definition_pattern_bonus=overlay.definition_pattern_bonus,
            question_echo_penalty=overlay.question_echo_penalty,
            document_seeking_markdown_bonus=overlay.document_seeking_markdown_bonus,
            document_seeking_documentation_bonus=overlay.document_seeking_documentation_bonus,
            document_seeking_readme_bonus=overlay.document_seeking_readme_bonus,
            code_seeking_source_bonus=overlay.code_seeking_source_bonus,
        )

    def excludes(self, source: Path) -> bool:
        """Return ``True`` when ``source`` should be excluded before scoring."""

        if source.name in self.excluded_names:
            return True
        if any(part in self.excluded_parts for part in source.parts):
            return True
        return any(_contains_path_parts(source, subpath) for subpath in self.excluded_subpaths)

    @classmethod
    def from_mapping(cls, payload: dict[str, Any]) -> RetrievalProfile:
        """Build a retrieval profile from a JSON object."""

        subpath_adjustments = tuple(
            SubpathAdjustment(
                path=tuple(str(part) for part in record["path"]),
                value=float(record["value"]),
            )
            for record in payload.get("subpath_adjustments", [])
        )
        contextual_rules = tuple(
            ContextualPathRule(
                value=float(record["value"]),
                path_name=_string_or_none(record.get("path_name")),
                subpath=_tuple_or_none(record.get("subpath")),
                required_terms=frozenset(
                    str(term) for term in record.get("required_terms", []) if str(term).strip()
                ),
                required_term_prefix=_string_or_none(record.get("required_term_prefix")),
            )
            for record in payload.get("contextual_rules", [])
        )
        return cls(
            name=str(payload.get("name") or "custom-profile"),
            retrieval_mode=_retrieval_mode_or_default(
                payload.get("retrieval_mode"),
                default=cls.retrieval_mode,
            ),
            rerank_candidate_pool_size=int(
                payload.get("rerank_candidate_pool_size", cls.rerank_candidate_pool_size)
            ),
            source_adjustments_by_name=_float_mapping(payload.get("source_adjustments_by_name")),
            source_adjustments_by_part=_float_mapping(payload.get("source_adjustments_by_part")),
            subpath_adjustments=subpath_adjustments,
            contextual_rules=contextual_rules,
            excluded_names=frozenset(str(name) for name in payload.get("excluded_names", [])),
            excluded_parts=frozenset(str(part) for part in payload.get("excluded_parts", [])),
            excluded_subpaths=tuple(
                tuple(str(part) for part in record)
                for record in payload.get("excluded_subpaths", [])
            ),
            path_term_overlap_bonus=float(
                payload.get("path_term_overlap_bonus", cls.path_term_overlap_bonus)
            ),
            definition_pattern_bonus=float(
                payload.get("definition_pattern_bonus", cls.definition_pattern_bonus)
            ),
            question_echo_penalty=float(
                payload.get("question_echo_penalty", cls.question_echo_penalty)
            ),
            document_seeking_markdown_bonus=float(
                payload.get(
                    "document_seeking_markdown_bonus",
                    cls.document_seeking_markdown_bonus,
                )
            ),
            document_seeking_documentation_bonus=float(
                payload.get(
                    "document_seeking_documentation_bonus",
                    cls.document_seeking_documentation_bonus,
                )
            ),
            document_seeking_readme_bonus=float(
                payload.get("document_seeking_readme_bonus", cls.document_seeking_readme_bonus)
            ),
            code_seeking_source_bonus=float(
                payload.get("code_seeking_source_bonus", cls.code_seeking_source_bonus)
            ),
        )


DEFAULT_RETRIEVAL_PROFILE = RetrievalProfile(
    source_adjustments_by_name={
        "README.md": 1.2,
        "AGENTS.md": 1.0,
    },
    source_adjustments_by_part={
        ".codex": -2.5,
        ".github": -1.5,
        "data": -6.0,
        "docs": 0.6,
        "generated": -2.0,
        "include": 0.5,
        "src": 0.4,
        "tests": -5.0,
    },
)


def _contains_path_parts(path: Path, needle: tuple[str, ...]) -> bool:
    parts = path.parts
    for index in range(len(parts) - len(needle) + 1):
        if parts[index : index + len(needle)] == needle:
            return True
    return False


def _float_mapping(raw_value: object) -> dict[str, float]:
    if not isinstance(raw_value, dict):
        return {}
    return {str(key): float(value) for key, value in raw_value.items()}


def _string_or_none(raw_value: object) -> str | None:
    if raw_value is None:
        return None
    text = str(raw_value).strip()
    return text or None


def _tuple_or_none(raw_value: object) -> tuple[str, ...] | None:
    if raw_value is None:
        return None
    if not isinstance(raw_value, list):
        raise ValueError(f"Expected a list of path parts, got: {raw_value!r}")
    parts = tuple(str(part).strip() for part in raw_value if str(part).strip())
    return parts or None


def _retrieval_mode_or_default(raw_value: object, *, default: str) -> str:
    if raw_value is None:
        return default
    mode = str(raw_value).strip().casefold()
    if mode not in SUPPORTED_RETRIEVAL_MODES:
        supported = ", ".join(sorted(SUPPORTED_RETRIEVAL_MODES))
        raise ValueError(f"Unsupported retrieval mode `{raw_value}`. Expected one of: {supported}")
    return mode


@cache
def load_retrieval_profile(root: Path) -> RetrievalProfile:
    """Load the repo-local retrieval profile, falling back to generic defaults."""

    resolved_root = root.resolve()
    profile_path = resolved_root / DEFAULT_RETRIEVAL_PROFILE_PATH
    if not profile_path.is_file():
        return DEFAULT_RETRIEVAL_PROFILE
    payload = json.loads(profile_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Retrieval profile must be a JSON object: {profile_path}")
    return DEFAULT_RETRIEVAL_PROFILE.merged_with(RetrievalProfile.from_mapping(payload))
