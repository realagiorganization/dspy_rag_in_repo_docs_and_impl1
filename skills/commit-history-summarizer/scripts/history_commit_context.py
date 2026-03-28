from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9._/-]{1,}")
STOP_WORDS = {
    "md",
    "py",
    "json",
    "yaml",
    "yml",
    "toml",
    "txt",
    "the",
    "and",
    "for",
    "with",
    "that",
    "this",
    "from",
    "into",
    "repo",
    "repository",
    "file",
    "files",
}
EXPANSIONS = {
    "agents.md": ["agents", "instructions"],
    "todo.md": ["todo", "cleanup"],
    "ci.yml": ["ci", "workflow", "github actions"],
    "workflows": ["workflow", "github actions", "ci"],
    "feature": ["bdd", "gherkin"],
    "gherkin": ["bdd", "feature"],
    "markdownlint": ["markdown", "lint"],
    "taplo": ["toml", "format"],
}


@dataclass(frozen=True)
class HistoryEntry:
    line_no: int
    session_id: str
    ts: int
    text: str


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+")
    parser.add_argument("--history", default="~/.codex/history.jsonl")
    parser.add_argument("--extra-term", action="append", default=[])
    parser.add_argument("--limit", type=int, default=6)
    args = parser.parse_args()

    history_path = Path(args.history).expanduser()
    entries = load_history(history_path)
    search_terms = build_search_terms(args.paths, args.extra_term)
    matches = score_entries(entries, search_terms)[: args.limit]

    print("Search terms:")
    for term in search_terms:
        print(f"- {term}")

    if not matches:
        print("\nNo relevant history entries found.")
        return 0

    print("\nSuggested rationale:")
    for summary in summarize_matches(matches):
        print(f"- {summary}")

    print("\nVerbatim excerpts:")
    for score, entry in matches:
        quote = (
            f'[history.jsonl:{entry.line_no}] session={entry.session_id} '
            f'ts={entry.ts} "{entry.text}"'
        )
        print(
            f"- {quote}"
        )
        print(f"  score={score}")
    return 0


def load_history(path: Path) -> list[HistoryEntry]:
    entries: list[HistoryEntry] = []
    for line_no, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw_line.strip():
            continue
        payload = json.loads(raw_line)
        text = str(payload.get("text", "")).strip()
        if not text:
            continue
        entries.append(
            HistoryEntry(
                line_no=line_no,
                session_id=str(payload.get("session_id", "")),
                ts=int(payload.get("ts", 0)),
                text=text,
            )
        )
    return entries


def build_search_terms(paths: list[str], extra_terms: list[str]) -> list[str]:
    counter: Counter[str] = Counter()
    for raw_path in paths:
        path = Path(raw_path)
        candidates = {
            raw_path.lower(),
            path.name.lower(),
            path.stem.lower(),
            *[part.lower() for part in path.parts],
        }
        for candidate in list(candidates):
            candidates.update(EXPANSIONS.get(candidate, []))
        for term in candidates:
            for token in TOKEN_RE.findall(term):
                if token in STOP_WORDS or len(token) < 3:
                    continue
                counter[token] += 1
    for term in extra_terms:
        for token in TOKEN_RE.findall(term.lower()):
            if token in STOP_WORDS or len(token) < 3:
                continue
            counter[token] += 2
    return [term for term, _ in counter.most_common()]


def score_entries(
    entries: list[HistoryEntry], search_terms: list[str]
) -> list[tuple[int, HistoryEntry]]:
    scored: list[tuple[int, HistoryEntry]] = []
    for entry in entries:
        lowered = entry.text.lower()
        overlap = sum(1 for term in search_terms if term in lowered)
        if overlap == 0:
            continue
        score = overlap
        if "commit" in lowered:
            score += 2
        if "push" in lowered:
            score += 1
        scored.append((score, entry))
    scored.sort(key=lambda item: (item[0], item[1].ts), reverse=True)
    return scored


def summarize_matches(matches: list[tuple[int, HistoryEntry]]) -> list[str]:
    summaries: list[str] = []
    seen: set[str] = set()
    for _, entry in matches:
        sentence = entry.text.replace("\n", " ").strip()
        if sentence in seen:
            continue
        seen.add(sentence)
        summaries.append(sentence)
        if len(summaries) == 3:
            break
    return summaries


if __name__ == "__main__":
    raise SystemExit(main())
