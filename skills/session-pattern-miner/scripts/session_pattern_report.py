from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9'/-]{2,}")
STOP_WORDS = {
    "carry",
    "ahead",
    "again",
    "this",
    "that",
    "with",
    "from",
    "into",
    "just",
    "yourself",
    "codex",
    "session",
    "sessions",
}


@dataclass(frozen=True)
class HistoryEntry:
    session_id: str
    ts: int
    text: str


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--history", default="~/.codex/history.jsonl")
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--top", type=int, default=12)
    args = parser.parse_args()

    entries = load_history(Path(args.history).expanduser())
    window = entries[-args.limit :]
    keyword_counts = Counter()
    normalized_counts = Counter()
    normalized_to_entry: dict[str, str] = {}

    for entry in window:
        normalized = normalize_text(entry.text)
        normalized_counts[normalized] += 1
        normalized_to_entry.setdefault(normalized, entry.text)
        keyword_counts.update(tokenize(entry.text))

    print(f"Analyzed entries: {len(window)}")

    print("\nTop keywords:")
    for keyword, count in keyword_counts.most_common(args.top):
        print(f"- {keyword}: {count}")

    print("\nRepeated prompts:")
    repeated = [(text, count) for text, count in normalized_counts.items() if count > 1]
    if not repeated:
        print("- None")
    else:
        top_repeated = sorted(repeated, key=lambda item: item[1], reverse=True)[: args.top]
        for normalized, count in top_repeated:
            print(f"- {count}x {normalized_to_entry[normalized]}")

    print("\nRecent entries:")
    for entry in window[-10:]:
        print(f"- [{entry.session_id}] {entry.ts}: {entry.text}")
    return 0


def load_history(path: Path) -> list[HistoryEntry]:
    entries: list[HistoryEntry] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        if not raw_line.strip():
            continue
        payload = json.loads(raw_line)
        text = str(payload.get("text", "")).strip()
        if not text:
            continue
        entries.append(
            HistoryEntry(
                session_id=str(payload.get("session_id", "")),
                ts=int(payload.get("ts", 0)),
                text=text,
            )
        )
    return entries


def tokenize(text: str) -> list[str]:
    tokens = []
    for token in TOKEN_RE.findall(text.lower()):
        if token in STOP_WORDS:
            continue
        tokens.append(token)
    return tokens


def normalize_text(text: str) -> str:
    return " ".join(tokenize(text))


if __name__ == "__main__":
    raise SystemExit(main())
