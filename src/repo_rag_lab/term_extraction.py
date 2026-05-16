"""Technical-term extraction utilities for prompt-family routing profiles."""

from __future__ import annotations

import re
from collections.abc import Mapping
from collections.abc import Iterable, Sequence

_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")

PROFILE_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "accessible",
        "all",
        "and",
        "are",
        "behavior",
        "can",
        "claim",
        "clean",
        "confirm",
        "describe",
        "exact",
        "found",
        "for",
        "from",
        "generated",
        "inspect",
        "instead",
        "into",
        "its",
        "just",
        "matches",
        "needed",
        "now",
        "once",
        "otherwise",
        "reading",
        "really",
        "relevant",
        "report",
        "should",
        "state",
        "states",
        "static",
        "still",
        "switch",
        "them",
        "the",
        "then",
        "this",
        "that",
        "through",
        "verify",
        "walks",
        "whether",
        "with",
        "you",
        "your",
    }
)

PROFILE_SUMMARY_NARRATIVE_STOPWORDS = frozenset(
    {
        "actually",
        "adhere",
        "adheres",
        "already",
        "against",
        "any",
        "anything",
        "appears",
        "approach",
        "appropriate",
        "available",
        "based",
        "before",
        "both",
        "but",
        "change",
        "changes",
        "checked",
        "checking",
        "cleanly",
        "close",
        "code",
        "coding",
        "commands",
        "complete",
        "completion",
        "compact",
        "conceptually",
        "conclusions",
        "contains",
        "contents",
        "context",
        "create",
        "current",
        "decision",
        "described",
        "does",
        "doesn",
        "driven",
        "edit",
        "ensure",
        "execute",
        "existing",
        "fields",
        "final",
        "findings",
        "grabbing",
        "grounded",
        "handoff",
        "identify",
        "line",
        "mediation",
        "only",
        "output",
        "point",
        "precise",
        "provide",
        "ranges",
        "reached",
        "references",
        "rely",
        "requested",
        "required",
        "use",
        "where",
    }
)

PROFILE_SUMMARY_LOW_SIGNAL_TERMS = frozenset(
    {
        "command",
        "commands",
        "directory",
        "directories",
        "file",
        "files",
        "https",
        "mounted",
        "package",
        "packages",
        "path",
        "paths",
        "prompt",
        "prompts",
        "query",
        "queries",
        "shell",
    }
)

TECHNICAL_TERM_CATEGORIES: dict[str, frozenset[str]] = {
    "repo": frozenset(
        {
            "repo",
            "repository",
            "readme",
            "docs",
            "doc",
            "artifact",
            "artifacts",
            "asset",
            "assets",
            "bundle",
            "bundles",
            "trace",
            "traces",
            "queue",
            "queued",
            "processed",
            "script",
            "scripts",
            "family",
            "families",
            "submodule",
            "submodules",
            "worktree",
            "workflow",
            "workflows",
            "program",
            "programs",
            "runtime",
            "overlay",
            "payload",
            "wrapper",
            "metadata",
            "manifest",
            "index",
            "summary",
            "channel",
            "version",
            "versions",
            "registry",
        }
    ),
    "git": frozenset(
        {
            "git",
            "github",
            "commit",
            "commits",
            "branch",
            "branches",
            "merge",
            "rebase",
            "checkout",
            "clone",
            "fetch",
            "pull",
            "push",
            "diff",
            "patch",
            "stash",
            "pointer",
            "sha",
            "origin",
            "develop",
            "main",
            "master",
            "tag",
            "tags",
            "worktree",
        }
    ),
    "build_ci": frozenset(
        {
            "build",
            "compile",
            "compiled",
            "ci",
            "lint",
            "typecheck",
            "coverage",
            "pytest",
            "test",
            "tests",
            "quality",
            "hook",
            "hooks",
            "smoke",
            "verification",
            "audit",
            "release",
            "publish",
            "promotion",
            "rollback",
            "deploy",
            "deployment",
            "runner",
            "pipeline",
            "pipelines",
            "check",
            "checks",
        }
    ),
    "cloud_ops": frozenset(
        {
            "azure",
            "aks",
            "blob",
            "storage",
            "container",
            "containers",
            "worker",
            "workers",
            "pod",
            "pods",
            "pvc",
            "mcp",
            "proxy",
            "codex",
            "exec",
            "resume",
            "session",
            "sessions",
            "token",
            "tokens",
            "latency",
            "throughput",
            "telemetry",
            "handoff",
            "enqueue",
            "drain",
            "cache",
            "cached",
            "cluster",
            "clusters",
            "deployment",
            "containerapp",
        }
    ),
    "frontend_media": frozenset(
        {
            "gif",
            "png",
            "svg",
            "image",
            "images",
            "banner",
            "animation",
            "walkthrough",
            "wireframe",
            "frame",
            "frames",
            "render",
            "rendered",
            "recorder",
            "record",
            "screenshot",
            "ui",
            "ux",
            "frontend",
            "css",
            "html",
            "react",
            "component",
            "components",
            "embed",
        }
    ),
    "browser_automation": frozenset(
        {
            "playwright",
            "chromium",
            "browser",
            "headless",
            "page",
            "pages",
            "selector",
            "selectors",
            "click",
            "input",
            "hover",
            "scroll",
            "navigation",
            "dialog",
            "fixture",
            "fixtures",
            "viewport",
            "locator",
        }
    ),
    "python_ml": frozenset(
        {
            "python",
            "uv",
            "venv",
            "pip",
            "package",
            "packages",
            "module",
            "modules",
            "notebook",
            "notebooks",
            "dspy",
            "rag",
            "raglab",
            "trainer",
            "training",
            "retrieval",
            "embedding",
            "embeddings",
            "metric",
            "metrics",
            "similarity",
            "profile",
            "profiles",
            "term",
            "terms",
            "stats",
            "weight",
            "weights",
            "uncertainty",
            "posterior",
            "feedback",
            "baseline",
            "router",
            "routing",
        }
    ),
    "programming_languages": frozenset(
        {
            "python",
            "javascript",
            "typescript",
            "rust",
            "go",
            "golang",
            "java",
            "kotlin",
            "scala",
            "swift",
            "objectivec",
            "c",
            "cpp",
            "cxx",
            "csharp",
            "dotnet",
            "php",
            "ruby",
            "perl",
            "lua",
            "haskell",
            "ocaml",
            "elixir",
            "erlang",
            "clojure",
            "julia",
            "racket",
            "matlab",
            "fortran",
            "solidity",
        }
    ),
    "databases_storage": frozenset(
        {
            "sql",
            "sqlite",
            "postgres",
            "postgresql",
            "mysql",
            "mariadb",
            "redis",
            "mongodb",
            "elastic",
            "elasticsearch",
            "opensearch",
            "duckdb",
            "parquet",
            "delta",
            "warehouse",
            "lakehouse",
            "vector",
            "vectors",
            "vectorstore",
            "indexing",
            "shard",
            "shards",
            "replica",
            "replicas",
            "schema",
            "schemas",
            "migration",
            "migrations",
            "query",
            "queries",
            "dataset",
            "datasets",
        }
    ),
    "api_web_backend": frozenset(
        {
            "api",
            "apis",
            "rest",
            "graphql",
            "grpc",
            "webhook",
            "webhooks",
            "http",
            "https",
            "request",
            "requests",
            "response",
            "responses",
            "endpoint",
            "endpoints",
            "route",
            "routes",
            "handler",
            "handlers",
            "middleware",
            "server",
            "servers",
            "client",
            "clients",
            "auth",
            "oauth",
            "jwt",
            "cookie",
            "cookies",
            "cors",
            "csrf",
            "json",
        }
    ),
    "data_science_analytics": frozenset(
        {
            "pandas",
            "numpy",
            "scipy",
            "sklearn",
            "scikitlearn",
            "matplotlib",
            "seaborn",
            "plotly",
            "analysis",
            "analytics",
            "statistic",
            "statistics",
            "hypothesis",
            "distribution",
            "regression",
            "classification",
            "clustering",
            "sampling",
            "evaluation",
            "benchmark",
            "benchmarks",
            "experiment",
            "experiments",
            "ablation",
            "feature",
            "features",
            "signal",
            "signals",
            "corpus",
            "corpora",
        }
    ),
    "neural_networks_ai": frozenset(
        {
            "neural",
            "network",
            "networks",
            "transformer",
            "transformers",
            "attention",
            "embedding",
            "embeddings",
            "tokenizer",
            "tokenizers",
            "llm",
            "llms",
            "model",
            "models",
            "checkpoint",
            "checkpoints",
            "finetune",
            "finetuning",
            "inference",
            "training",
            "pretrain",
            "pretraining",
            "prompt",
            "prompts",
            "completion",
            "completions",
            "generation",
            "decoder",
            "encoder",
            "multimodal",
            "diffusion",
            "quantization",
            "rag",
        }
    ),
    "research_science": frozenset(
        {
            "research",
            "paper",
            "papers",
            "publication",
            "publications",
            "bibliography",
            "citation",
            "citations",
            "theory",
            "method",
            "methods",
            "methodology",
            "experiment",
            "experiments",
            "finding",
            "findings",
            "result",
            "results",
            "reproducibility",
            "replication",
            "survey",
            "surveys",
            "baseline",
            "baselines",
            "evidence",
            "hypothesis",
            "novelty",
            "peerreview",
            "appendix",
            "manuscript",
        }
    ),
    "infrastructure_devops": frozenset(
        {
            "terraform",
            "ansible",
            "helm",
            "kubernetes",
            "kubectl",
            "ingress",
            "service",
            "services",
            "namespace",
            "namespaces",
            "secret",
            "secrets",
            "configmap",
            "daemonset",
            "statefulset",
            "cronjob",
            "autoscaling",
            "cdn",
            "dns",
            "loadbalancer",
            "loadbalancing",
            "firewall",
            "iam",
            "policy",
            "policies",
            "observability",
            "logging",
            "monitoring",
            "metrics",
            "tracing",
            "prometheus",
            "grafana",
        }
    ),
    "linux_commands": frozenset(
        {
            "ls",
            "pwd",
            "cd",
            "cp",
            "mv",
            "rm",
            "mkdir",
            "rmdir",
            "touch",
            "cat",
            "less",
            "head",
            "tail",
            "grep",
            "rg",
            "find",
            "sed",
            "awk",
            "xargs",
            "sort",
            "uniq",
            "cut",
            "tee",
            "chmod",
            "chown",
            "ln",
            "tar",
            "gzip",
            "gunzip",
            "zip",
            "unzip",
            "curl",
            "wget",
            "ssh",
            "scp",
            "rsync",
            "systemctl",
            "journalctl",
            "ps",
            "top",
            "kill",
            "killall",
            "nohup",
            "env",
            "export",
            "make",
        }
    ),
    "windows_commands": frozenset(
        {
            "powershell",
            "cmd",
            "dir",
            "copy",
            "move",
            "del",
            "erase",
            "ren",
            "type",
            "findstr",
            "where",
            "tasklist",
            "taskkill",
            "setx",
            "set",
            "start",
            "cls",
            "robocopy",
            "xcopy",
            "icacls",
            "reg",
            "schtasks",
            "winget",
            "choco",
            "msbuild",
            "wsl",
            "notepad",
            "explorer",
            "powershellise",
        }
    ),
    "macos_commands": frozenset(
        {
            "brew",
            "defaults",
            "diskutil",
            "hdiutil",
            "launchctl",
            "mdfind",
            "mdutil",
            "open",
            "osascript",
            "pbcopy",
            "pbpaste",
            "pkgutil",
            "plutil",
            "screencapture",
            "security",
            "softwareupdate",
            "spctl",
            "swvers",
            "xattr",
            "xcodebuild",
            "xcrun",
        }
    ),
    "gamedev": frozenset(
        {
            "unity",
            "unreal",
            "godot",
            "gamedev",
            "gameplay",
            "game",
            "games",
            "player",
            "players",
            "npc",
            "enemy",
            "enemies",
            "sprite",
            "sprites",
            "shader",
            "shaders",
            "mesh",
            "meshes",
            "texture",
            "textures",
            "material",
            "materials",
            "animation",
            "animations",
            "physics",
            "collision",
            "collider",
            "hitbox",
            "level",
            "levels",
            "quest",
            "quests",
            "inventory",
            "savegame",
            "savestate",
            "multiplayer",
            "singleplayer",
            "scene",
            "scenes",
            "camera",
            "cameras",
            "hud",
            "ui",
            "vfx",
            "sfx",
        }
    ),
    "mobile_dev": frozenset(
        {
            "adb",
            "android",
            "androidstudio",
            "apk",
            "appbundle",
            "cocoapods",
            "emulator",
            "emulators",
            "fastlane",
            "gradle",
            "ios",
            "ipa",
            "podfile",
            "provisioning",
            "simulator",
            "simulators",
            "swiftui",
            "xcode",
        }
    ),
    "package_managers": frozenset(
        {
            "apt",
            "brew",
            "bun",
            "cargo",
            "composer",
            "conda",
            "gem",
            "gradle",
            "homebrew",
            "mamba",
            "maven",
            "npm",
            "nuget",
            "pip",
            "pnpm",
            "poetry",
            "uv",
            "winget",
            "yarn",
        }
    ),
    "kubernetes": frozenset(
        {
            "kubernetes",
            "kubectl",
            "kubeconfig",
            "kubelet",
            "kubeproxy",
            "ingress",
            "service",
            "services",
            "namespace",
            "namespaces",
            "deployment",
            "deployments",
            "replicaset",
            "replicasets",
            "daemonset",
            "statefulset",
            "job",
            "jobs",
            "cronjob",
            "autoscaler",
            "autoscaling",
            "configmap",
            "secret",
            "secrets",
            "persistentvolume",
            "persistentvolumeclaim",
            "node",
            "nodes",
            "clusterip",
            "loadbalancer",
            "helm",
            "chart",
            "charts",
        }
    ),
    "security_infosec": frozenset(
        {
            "authn",
            "authz",
            "certificate",
            "certificates",
            "checksum",
            "checksums",
            "cve",
            "decrypt",
            "encryption",
            "firewall",
            "hash",
            "hashes",
            "hmac",
            "jwt",
            "mfa",
            "oauth",
            "oidc",
            "pentest",
            "saml",
            "sandbox",
            "sandboxing",
            "secret",
            "secrets",
            "signature",
            "signatures",
            "sso",
            "ssh",
            "ssl",
            "tls",
            "token",
            "tokens",
            "vulnerability",
            "vulnerabilities",
        }
    ),
    "cloud_services": frozenset(
        {
            "azure",
            "aws",
            "gcp",
            "openai",
            "s3",
            "ec2",
            "eks",
            "ecs",
            "lambda",
            "cloudfront",
            "cloudwatch",
            "iam",
            "rds",
            "dynamodb",
            "sqs",
            "sns",
            "pubsub",
            "bigquery",
            "gcs",
            "cloudrun",
            "cloudbuild",
            "artifactregistry",
            "appservice",
            "containerapps",
            "cosmosdb",
            "servicebus",
            "keyvault",
            "aks",
            "acr",
            "azureopenai",
            "blob",
            "storage",
        }
    ),
    "systems": frozenset(
        {
            "docker",
            "linux",
            "shell",
            "bash",
            "zsh",
            "tmux",
            "pty",
            "stdout",
            "stderr",
            "timeout",
            "process",
            "processes",
            "command",
            "commands",
            "path",
            "paths",
            "file",
            "files",
            "directory",
            "directories",
            "mount",
            "mounted",
            "fd",
            "stdin",
            "stdout",
            "stderr",
        }
    ),
}

TECHNICAL_TERM_LOOKUP = frozenset().union(*TECHNICAL_TERM_CATEGORIES.values())
_CATEGORY_PRIORITY = {
    "browser_automation": 0,
    "frontend_media": 0,
    "git": 1,
    "repo": 1,
    "kubernetes": 1,
    "cloud_services": 1,
    "linux_commands": 1,
    "windows_commands": 1,
    "macos_commands": 1,
    "gamedev": 1,
    "mobile_dev": 1,
    "programming_languages": 2,
    "databases_storage": 2,
    "api_web_backend": 2,
    "data_science_analytics": 2,
    "neural_networks_ai": 2,
    "package_managers": 2,
    "security_infosec": 2,
    "cloud_ops": 3,
    "build_ci": 3,
    "python_ml": 3,
    "infrastructure_devops": 3,
    "research_science": 4,
    "systems": 5,
}
_TERM_CATEGORY_PRIORITY: dict[str, int] = {}
for _category_name, _terms in TECHNICAL_TERM_CATEGORIES.items():
    _priority = _CATEGORY_PRIORITY.get(_category_name, 4)
    for _term in _terms:
        existing = _TERM_CATEGORY_PRIORITY.get(_term)
        if existing is None or _priority < existing:
            _TERM_CATEGORY_PRIORITY[_term] = _priority


def extract_tokens(value: object) -> list[str]:
    """Return lowercase alphanumeric tokens from one prompt-like value."""

    cleaned = str(value or "").strip().casefold()
    if not cleaned:
        return []
    return [token for token in _TOKEN_PATTERN.findall(cleaned) if token]


def extract_profile_terms(values: Sequence[object], *, limit: int = 12) -> list[str]:
    """Return one prioritized prompt-term summary from prompt-like values.

    Technical terms are matched first through hashed set membership. Remaining capacity
    is then filled with non-stopword fallback terms in first-seen order.
    """

    prioritized_terms: list[str] = []
    fallback_terms: list[str] = []
    prioritized_seen: set[str] = set()
    fallback_seen: set[str] = set()
    for value in values:
        for token in extract_tokens(value):
            if len(token) < 3 or token in PROFILE_STOPWORDS:
                continue
            if token in TECHNICAL_TERM_LOOKUP:
                if token in prioritized_seen:
                    continue
                prioritized_seen.add(token)
                prioritized_terms.append(token)
                if len(prioritized_terms) >= limit:
                    return prioritized_terms
                continue
            if token in fallback_seen:
                continue
            fallback_seen.add(token)
            fallback_terms.append(token)
    if len(prioritized_terms) >= limit:
        return prioritized_terms[:limit]
    return [*prioritized_terms, *fallback_terms][:limit]


def is_technical_term(term: object) -> bool:
    """Return whether one term belongs to the technical lookup surface."""

    cleaned = str(term or "").strip().casefold()
    return bool(cleaned) and cleaned in TECHNICAL_TERM_LOOKUP


def is_summary_narrative_term(term: object) -> bool:
    """Return whether one term should be aggressively down-weighted in active summaries."""

    cleaned = str(term or "").strip().casefold()
    return bool(cleaned) and cleaned in PROFILE_SUMMARY_NARRATIVE_STOPWORDS


def is_low_signal_summary_term(term: object) -> bool:
    """Return whether one term should be excluded from active routing summaries."""

    cleaned = str(term or "").strip().casefold()
    return bool(cleaned) and (
        cleaned.isdigit()
        or cleaned in PROFILE_SUMMARY_NARRATIVE_STOPWORDS
        or cleaned in PROFILE_SUMMARY_LOW_SIGNAL_TERMS
    )


def select_profile_summary_terms(
    counts: Mapping[str, object],
    *,
    limit: int,
    min_count: int = 1,
) -> list[str]:
    """Return one selective active routing summary from one term-frequency mapping.

    The selector keeps full term statistics elsewhere, but the active summary prefers
    technical terms, penalizes broad narrative words, and uses raw counts only after
    those stronger routing signals have been applied.
    """

    normalized: list[tuple[str, int]] = []
    for key, value in counts.items():
        term = str(key or "").strip().casefold()
        if not term:
            continue
        try:
            count = int(value)
        except (TypeError, ValueError):
            continue
        if count <= 0:
            continue
        normalized.append((term, count))
    if not normalized:
        return []
    eligible = [(term, count) for term, count in normalized if count >= min_count] or normalized

    def _sort_key(item: tuple[str, int]) -> tuple[int, int, int, str]:
        term, count = item
        category_priority = _TERM_CATEGORY_PRIORITY.get(term, 9)
        return (
            category_priority,
            -count,
            len(term),
            term,
        )

    technical_preferred = [
        item
        for item in eligible
        if item[0] in TECHNICAL_TERM_LOOKUP and not is_low_signal_summary_term(item[0])
    ]
    fallback_preferred = [
        item
        for item in eligible
        if item[0] not in TECHNICAL_TERM_LOOKUP and not is_low_signal_summary_term(item[0])
    ]
    if technical_preferred:
        ranked = technical_preferred
    elif fallback_preferred:
        ranked = fallback_preferred
    else:
        ranked = [item for item in eligible if item[0] not in PROFILE_SUMMARY_NARRATIVE_STOPWORDS]
        if not ranked:
            ranked = eligible

    selected: list[str] = []
    seen: set[str] = set()
    for term, _count in sorted(ranked, key=_sort_key):
        if term in seen:
            continue
        seen.add(term)
        selected.append(term)
        if len(selected) >= limit:
            break
    return selected


def technical_terms_for_category(category: str) -> frozenset[str]:
    """Return one category-scoped technical-term set."""

    return TECHNICAL_TERM_CATEGORIES.get(category, frozenset())


def iter_all_technical_terms() -> Iterable[str]:
    """Yield all known technical terms in sorted order."""

    return iter(sorted(TECHNICAL_TERM_LOOKUP))
