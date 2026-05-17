from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from repo_rag_lab.training_samples import (
    batch_training_examples,
    load_family_state_payload,
    load_training_examples,
    materialize_combined_training_examples,
    materialize_training_candidates,
    resolve_prompt_family_support,
    resolve_prompt_family_support_from_payload,
    summarize_champion_index,
    summarize_family_state,
    summarize_training_examples,
    validate_training_examples,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
HUSHWHEEL_FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "hushwheel_lexiconarium"


def test_load_training_examples_reads_repository_samples() -> None:
    examples = load_training_examples(
        REPO_ROOT / "samples" / "training" / "repository_training_examples.yaml"
    )
    questions = {example.question for example in examples}
    assert len(examples) >= 8
    assert examples[0].question
    assert examples[0].expected_sources
    assert {
        "Which file explains the core workflow modules under src/repo_rag_lab?",
        "What should AZURE_INFERENCE_ENDPOINT contain for the Azure AI Inference SDK?",
        "Where can you read MCP discovery notes?",
        "How do you execute all tracked notebooks with monitored progress and report artifacts?",
        "How do you build the publication PDF locally?",
    }.issubset(questions)


def test_batch_training_examples_preserves_all_items() -> None:
    examples = load_training_examples(
        REPO_ROOT / "samples" / "training" / "repository_training_examples.yaml"
    )
    batches = batch_training_examples(examples, batch_size=2)
    assert sum(len(batch) for batch in batches) == len(examples)


def test_summarize_training_examples_lists_tags() -> None:
    examples = load_training_examples(
        REPO_ROOT / "samples" / "training" / "repository_training_examples.yaml"
    )
    summary = summarize_training_examples(examples)
    assert summary["example_count"] == len(examples)
    assert summary["benchmark_count"] == len(examples)
    assert "repo" in summary["unique_tags"]
    assert {"azure", "mcp", "notebooks", "publication"}.issubset(summary["unique_tags"])


def test_validate_training_examples_accepts_repository_samples() -> None:
    examples = load_training_examples(
        REPO_ROOT / "samples" / "training" / "repository_training_examples.yaml"
    )
    assert validate_training_examples(examples, root=REPO_ROOT) == []


def test_validate_training_examples_accepts_hushwheel_fixture_samples() -> None:
    examples = load_training_examples(
        REPO_ROOT / "samples" / "training" / "hushwheel_fixture_training_examples.yaml"
    )
    assert len(examples) == 6
    assert validate_training_examples(examples, root=HUSHWHEEL_FIXTURE_ROOT) == []


def test_materialize_training_candidates_and_combined_training_examples(tmp_path: Path) -> None:
    imported_dir = tmp_path / "artifacts" / "traces" / "imported"
    imported_dir.mkdir(parents=True, exist_ok=True)
    (tmp_path / "README.md").write_text("# Demo\n", encoding="utf-8")
    candidate_trace_path = imported_dir / "accepted.json"
    candidate_trace_path.write_text(
        """{
  "trace_record_kind": "repo-rag-trace-record",
  "trace_record_path": "artifacts/traces/imported/accepted.json",
  "question": "What does this repository research?",
  "answer": "It researches repository-grounded RAG.",
  "sources": ["README.md"],
  "context": [
    {
      "source": "README.md",
      "preview": "Repository-grounded RAG over repository files.",
      "text": "Repository-grounded RAG over repository files."
    }
  ],
  "trace": {
    "schema_version": 1,
    "trace_kind": "repo-rag-runtime",
    "recorded_at": "2026-04-29T00:00:00+00:00",
    "question": "What does this repository research?",
    "mode": "baseline",
    "retrieval_mode": "idf-rerank",
    "sources": ["README.md"],
    "source_count": 1,
    "context_count": 1,
    "context_field": "context",
    "mcp_candidate_count": 0,
    "answer_length": 20
  },
  "outcome": {
    "acceptance_status": "accepted",
    "accepted": true,
    "execution_status": "success",
    "method": "repo_rag_cli",
    "backend": "repo_rag_cli"
  }
}
""",
        encoding="utf-8",
    )

    candidates_summary = materialize_training_candidates(
        tmp_path,
        output_path=Path("artifacts/trainer/training-candidates.yaml"),
        summary_path=Path("artifacts/trainer/training-candidates-summary.json"),
    )
    assert candidates_summary["candidate_count"] == 1
    assert candidates_summary["replaced_count"] == 0
    materialized = load_training_examples(
        tmp_path / "artifacts" / "trainer" / "training-candidates.yaml"
    )
    assert len(materialized) == 1
    assert materialized[0].expected_sources == ()
    assert materialized[0].benchmark_context == ("Repository-grounded RAG over repository files.",)
    assert materialized[0].benchmark_context_sources == ("README.md",)

    base_training_path = tmp_path / "samples" / "training" / "base.yaml"
    base_training_path.parent.mkdir(parents=True, exist_ok=True)
    base_training_path.write_text(
        (
            '- question: "Where are logs stored?"\n'
            '  expected_answer: "samples/logs"\n'
            '  tags: ["logs"]\n'
        ),
        encoding="utf-8",
    )

    combined_summary = materialize_combined_training_examples(
        tmp_path,
        base_training_path=Path("samples/training/base.yaml"),
        candidates_path=Path("artifacts/trainer/training-candidates.yaml"),
        output_path=Path("artifacts/trainer/generated-training.yaml"),
        summary_path=Path("artifacts/trainer/generated-training-summary.json"),
    )
    assert combined_summary["base_example_count"] == 1
    assert combined_summary["candidate_example_count"] == 1
    assert combined_summary["combined_example_count"] == 2
    assert combined_summary["replaced_candidate_count"] == 0


def test_materialize_training_candidates_extracts_final_answer_from_codex_transcript(
    tmp_path: Path,
) -> None:
    imported_dir = tmp_path / "artifacts" / "traces" / "imported"
    imported_dir.mkdir(parents=True, exist_ok=True)
    transcript = """COMMAND: /usr/local/bin/codex exec -- demo
WORKING DIRECTORY: /tmp/demo
RETURN CODE: 0
STDOUT:
The plan is set.

STDERR:
OpenAI Codex v0.128.0
user
Add a demo GIF to README
codex
I am verifying the repo shape first.
exec
/bin/bash -lc "true"
 succeeded in 0ms:

codex
Added the demo GIF to README and verified npm run build.

tokens used
371,035
"""
    (imported_dir / "accepted.json").write_text(
        json.dumps(
            {
                "trace_record_kind": "repo-rag-trace-record",
                "trace_record_path": "artifacts/traces/imported/accepted.json",
                "question": "Add a demo GIF to README",
                "answer": transcript,
                "trace": {
                    "schema_version": 1,
                    "trace_kind": "repo-rag-runtime",
                    "recorded_at": "2026-05-06T16:55:06+00:00",
                    "question": "Add a demo GIF to README",
                    "mode": "codex-proxy",
                    "retrieval_mode": "lexical",
                    "sources": ["README.md"],
                    "source_count": 1,
                    "context_count": 1,
                    "context_field": "evidence_previews",
                    "mcp_candidate_count": 0,
                    "answer_length": len(transcript),
                },
                "outcome": {
                    "acceptance_status": "candidate",
                    "accepted": None,
                    "execution_status": "success",
                    "method": "codex_cli",
                    "backend": "codex_cli_repo_rag_proxy",
                },
            }
        ),
        encoding="utf-8",
    )

    summary = materialize_training_candidates(
        tmp_path,
        output_path=Path("artifacts/trainer/training-candidates.yaml"),
        summary_path=Path("artifacts/trainer/training-candidates-summary.json"),
    )

    assert summary["candidate_count"] == 1
    materialized = load_training_examples(
        tmp_path / "artifacts" / "trainer" / "training-candidates.yaml"
    )
    assert materialized[0].expected_answer == (
        "Added the demo GIF to README and verified npm run build."
    )
    payload = load_family_state_payload(tmp_path / "artifacts" / "trainer" / "family-state.json")
    provenance = payload["prompt_families"][0]["family_champion_record"]["provenance"]
    assert provenance["answer_normalization"]["normalization_method"] == "codex-final-block"
    assert provenance["answer_normalization"]["was_transcript"] is True


def test_materialize_training_candidates_sanitizes_existing_champion_index_transcript_answers(
    tmp_path: Path,
) -> None:
    trainer_dir = tmp_path / "artifacts" / "trainer"
    trainer_dir.mkdir(parents=True, exist_ok=True)
    transcript = """COMMAND: /usr/local/bin/codex exec -- demo
WORKING DIRECTORY: /tmp/demo
RETURN CODE: 0
STDOUT:
Done.

STDERR:
OpenAI Codex v0.128.0
user
Add a demo GIF to README
codex
Added the demo GIF to README and verified npm run build.

tokens used
203,413
"""
    champion_record = {
        "question": "Add a demo GIF to README",
        "expected_answer": transcript,
        "tags": ["trainer-candidate", "candidate"],
        "expected_sources": [],
        "candidate_status": "candidate",
        "prompt_family_id": "pf-demo",
        "context_group_id": "cg-demo",
        "exact_snapshot_id": "ts-demo",
        "quality_score": 0.8,
        "support_count": 1,
        "provenance": {},
    }
    champion_index = {
        "schema_version": 1,
        "record_kind": "repo-rag-trainer-champion-index",
        "generated_at": "2026-05-06T17:00:00+00:00",
        "prompt_families": [
            {
                "prompt_family_id": "pf-demo",
                "question": "Add a demo GIF to README",
                "normalized_question": "add a demo gif to readme",
                "family_champion_context_group_id": "cg-demo",
                "family_champion_score": 0.8,
                "family_champion_record": champion_record,
                "context_groups": [
                    {
                        "context_group_id": "cg-demo",
                        "sources": ["README.md"],
                        "evidence_fingerprints": [],
                        "evidence_count": 0,
                        "retrieval_mode": "lexical",
                        "mode": "codex-proxy",
                        "context_field": "evidence_previews",
                        "source_count": 1,
                        "context_count": 1,
                        "top_k": 4,
                        "trace_count": 1,
                        "support_by_record_key": {},
                        "champion_score": 0.8,
                        "champion_record": champion_record,
                    }
                ],
            }
        ],
    }
    (trainer_dir / "champion-index.json").write_text(
        json.dumps(champion_index, indent=2),
        encoding="utf-8",
    )

    summary = materialize_training_candidates(
        tmp_path,
        output_path=Path("artifacts/trainer/training-candidates.yaml"),
        summary_path=Path("artifacts/trainer/training-candidates-summary.json"),
        seed_existing_output=False,
    )

    assert summary["candidate_count"] == 1
    materialized = load_training_examples(trainer_dir / "training-candidates.yaml")
    assert materialized[0].expected_answer == (
        "Added the demo GIF to README and verified npm run build."
    )


def test_materialize_training_candidates_keeps_prompt_reformulation_and_command_trace(
    tmp_path: Path,
) -> None:
    imported_dir = tmp_path / "artifacts" / "traces" / "imported"
    imported_dir.mkdir(parents=True, exist_ok=True)
    (imported_dir / "unsupported.json").write_text(
        json.dumps(
            {
                "trace_record_kind": "repo-rag-trace-record",
                "trace_record_path": "artifacts/traces/imported/unsupported.json",
                "question": "Add a demo GIF to README",
                "original_prompt": "Add a demo GIF to README",
                "reformulated_prompt": "Inspect whether the README already embeds a demo GIF.",
                "answer": (
                    "The requested deliverable is already present in the repository. "
                    "Verification: the GIF is a valid 900x658 animated GIF at about 15 MB, "
                    "and the git worktree is clean."
                ),
                "command_trace": [
                    {"type": "message", "role": "assistant", "text": "inspect README"},
                    {"type": "message", "role": "assistant", "text": "check docs/assets"},
                ],
                "context": [
                    {
                        "source": "README.md",
                        "preview": (
                            "# national-debt-relief ## Demo "
                            "![Automated demo walkthrough]"
                            "(docs/assets/national-debt-relief-demo.gif)"
                        ),
                        "text": (
                            "# national-debt-relief ## Demo "
                            "![Automated demo walkthrough]"
                            "(docs/assets/national-debt-relief-demo.gif)"
                        ),
                    }
                ],
                "retrieved_context": [
                    {
                        "source": "package.json",
                        "preview": (
                            '{"name":"national-debt-relief","scripts":{"build":"vite build"}}'
                        ),
                        "text": (
                            '{"name":"national-debt-relief","scripts":{"build":"vite build"}}'
                        ),
                    }
                ],
                "trace": {
                    "schema_version": 1,
                    "trace_kind": "repo-rag-runtime",
                    "recorded_at": "2026-05-08T13:20:42+00:00",
                    "question": "Inspect whether the README already embeds a demo GIF.",
                    "original_prompt": "Add a demo GIF to README",
                    "reformulated_prompt": "Inspect whether the README already embeds a demo GIF.",
                    "mode": "codex-proxy",
                    "retrieval_mode": "lexical",
                    "sources": ["README.md", "package.json"],
                    "source_count": 2,
                    "context_count": 2,
                    "context_field": "evidence_previews",
                    "top_k": 4,
                    "program_loaded": True,
                    "mcp_candidate_count": 0,
                    "answer_length": 180,
                },
                "outcome": {
                    "acceptance_status": "candidate",
                    "accepted": None,
                    "execution_status": "success",
                    "method": "codex_cli",
                    "backend": "codex_cli_repo_rag_proxy",
                    "used_baseline_fallback": False,
                },
            }
        ),
        encoding="utf-8",
    )

    summary = materialize_training_candidates(
        tmp_path,
        output_path=Path("artifacts/trainer/training-candidates.yaml"),
        summary_path=Path("artifacts/trainer/training-candidates-summary.json"),
    )

    assert summary["candidate_count"] == 1
    assert summary["loaded_candidate_count"] == 1
    assert summary["dirty_family_count"] == 1
    materialized_path = tmp_path / "artifacts" / "trainer" / "training-candidates.yaml"
    materialized_payload = yaml.safe_load(materialized_path.read_text(encoding="utf-8"))
    assert materialized_payload[0]["question"] == "Add a demo GIF to README"
    assert materialized_payload[0]["original_prompt"] == "Add a demo GIF to README"
    assert materialized_payload[0]["reformulated_prompt"] == (
        "Inspect whether the README already embeds a demo GIF."
    )
    assert materialized_payload[0]["command_trace"] == [
        {"type": "message", "role": "assistant", "text": "inspect README"},
        {"type": "message", "role": "assistant", "text": "check docs/assets"},
    ]
    family_state = load_family_state_payload(
        tmp_path / "artifacts" / "trainer" / "family-state.json"
    )
    family_payload = family_state["prompt_families"][0]
    assert summary["dirty_family_ids"] == [family_payload["prompt_family_id"]]
    assert family_payload["family_needs_recompile"] is True
    assert family_payload["family_father_question"] == "Add a demo GIF to README"
    assert family_payload["family_runtime_record"]["reformulated_prompt"] == (
        "Inspect whether the README already embeds a demo GIF."
    )
    family_records = family_payload["family_records"]
    assert len(family_records) == 1
    assert family_records[0]["exact_snapshot_id"].startswith("ts-")
    assert family_records[0]["original_prompt"] == "Add a demo GIF to README"
    assert family_records[0]["reformulated_prompt"] == (
        "Inspect whether the README already embeds a demo GIF."
    )


def test_materialize_training_candidates_routes_feedback_trace_without_dirty_recompile(
    tmp_path: Path,
) -> None:
    imported_dir = tmp_path / "artifacts" / "traces" / "imported"
    imported_dir.mkdir(parents=True, exist_ok=True)
    trainer_dir = tmp_path / "artifacts" / "trainer"
    trainer_dir.mkdir(parents=True, exist_ok=True)
    family_state_path = trainer_dir / "family-state.json"
    family_state_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "record_kind": "repo-rag-trainer-champion-index",
                "family_state_kind": "repo-rag-trainer-family-state",
                "family_state_layout": "thin-index",
                "generated_at": "2026-05-15T12:00:00+00:00",
                "prompt_families": [
                    {
                        "prompt_family_id": "pf-docs",
                        "family_needs_recompile": False,
                        "question": "Inspect repository and update docs",
                        "normalized_question": "inspect repository and update docs",
                        "question_variants": ["Inspect repository and update docs"],
                        "question_variant_count": 1,
                        "family_father_question": "Inspect repository and update docs",
                        "family_runtime_score": 1.0,
                        "family_metric_1_mean": 1.0,
                        "family_runtime_artifact": {
                            "artifact_kind": "compiled-family-program",
                            "artifact_ready": True,
                            "program_path": "families/pf-docs/program.json",
                            "hit_rate": 1.0,
                        },
                        "family_record_count": 0,
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (imported_dir / "feedback-trace.json").write_text(
        json.dumps(
            {
                "trace_record_kind": "repo-rag-trace-record",
                "trace_record_path": "artifacts/traces/imported/feedback-trace.json",
                "question": "Inspect README.md and update repository docs",
                "original_prompt": "Inspect repository and update docs",
                "reformulated_prompt": "Inspect README.md and update repository docs",
                "answer": "Updated docs successfully.",
                "prompt_family_id": "pf-docs",
                "trainer_signal_kind": "feedback_trace",
                "trace": {
                    "schema_version": 1,
                    "trace_kind": "repo-rag-runtime",
                    "recorded_at": "2026-05-15T12:05:00+00:00",
                    "question": "Inspect README.md and update repository docs",
                    "mode": "codex-proxy",
                    "retrieval_mode": "idf-rerank",
                    "sources": ["README.md"],
                    "source_count": 1,
                    "context_count": 1,
                    "context_field": "context",
                    "program_loaded": True,
                    "program_path": "families/pf-docs/program.json",
                    "prompt_family_id": "pf-docs",
                    "prompt_family_similarity": 0.93,
                    "prompt_family_band": "match",
                    "family_runtime_hit_rate": 1.0,
                    "family_artifact_hit_rate": 1.0,
                    "family_artifact_selected": True,
                    "mediation_metric_hits": 1,
                    "mediation_metric_total": 1,
                    "trainer_signal_kind": "feedback_trace",
                },
                "outcome": {
                    "acceptance_status": "candidate",
                    "accepted": None,
                    "execution_status": "success",
                    "method": "codex_cli",
                    "backend": "codex_cli_repo_rag_proxy",
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    summary = materialize_training_candidates(
        tmp_path,
        output_path=trainer_dir / "training-candidates.yaml",
        summary_path=trainer_dir / "training-candidates-summary.json",
        family_state_path=family_state_path,
        upload_remote_state=False,
    )

    family_state = load_family_state_payload(family_state_path)
    family_payload = family_state["prompt_families"][0]

    assert summary["feedback_trace_count"] == 1
    assert summary["new_candidate_count"] == 0
    assert summary["dirty_family_count"] == 0
    assert family_payload["family_needs_recompile"] is False
    assert family_payload["family_feedback_count"] == 1
    assert family_payload["family_feedback_metric"]["metric_hits"] == 1
    assert family_payload["family_feedback_metric"]["metric_total"] == 1
    assert family_payload["family_success_metric"]["evidence_hits"] == 1
    assert family_payload["family_success_metric"]["evidence_total"] == 1
    assert family_payload["family_runtime_artifact"]["predicted_hit_rate"] == 0.666667
    assert family_payload["family_runtime_artifact"]["predicted_hit_rate_lower_bound"] == 0.364602
    assert family_payload["family_runtime_artifact"]["prediction_uncertainty"] == 0.235702
    assert family_payload.get("family_records", []) == []


def test_resolve_prompt_family_support_can_match_family_variant_not_only_father() -> None:
    payload = {
        "prompt_families": [
            {
                "prompt_family_id": "pf-variant",
                "question": "Investigate failing pytest target",
                "normalized_question": "investigate failing pytest target",
                "family_father_question": "Investigate failing pytest target",
                "question_variants": [
                    "Investigate failing pytest target",
                    "Run the failing pytest target and inspect stderr",
                ],
                "family_records": [
                    {
                        "question": "Run the failing pytest target and inspect stderr",
                        "original_prompt": "Fix the broken pytest target",
                        "reformulated_prompt": "Run the failing pytest target and inspect stderr",
                        "expected_answer": "Inspect stderr first.",
                        "metric_hits": 1,
                        "metric_total": 1,
                        "metric_ratio": 1.0,
                    }
                ],
            }
        ]
    }

    support_from_payload = resolve_prompt_family_support_from_payload(
        "Run the failing pytest target and inspect stderr",
        payload,
    )

    assert support_from_payload.prompt_family_id == "pf-variant"
    assert support_from_payload.supported is True
    assert support_from_payload.similarity >= 0.8


def test_resolve_prompt_family_support_can_use_family_profile_summaries() -> None:
    payload = {
        "prompt_families": [
            {
                "prompt_family_id": "pf-profile",
                "question": "Generate demo animation assets",
                "normalized_question": "generate demo animation assets",
                "family_father_question": "Generate demo animation assets",
                "question_variants": ["Generate demo animation assets"],
                "family_prompt_profile_terms": [
                    "record",
                    "demo",
                    "gif",
                    "readme",
                    "animation",
                    "assets",
                ],
                "family_command_pattern_summary": ["record", "gif", "readme"],
                "family_constraint_summary": ["readme.md", "demo.gif"],
                "family_success_metric": {
                    "posterior_mean": 0.95,
                    "lower_bound": 0.8,
                    "uncertainty": 0.05,
                },
                "family_records": [],
            }
        ]
    }

    support_from_payload = resolve_prompt_family_support_from_payload(
        "Update README.md with a demo GIF",
        payload,
    )

    assert support_from_payload.prompt_family_id == "pf-profile"
    assert support_from_payload.supported is True
    assert support_from_payload.similarity >= 0.8


def test_resolve_prompt_family_support_prefers_family_profile_over_surface_similarity() -> None:
    payload = {
        "prompt_families": [
            {
                "prompt_family_id": "pf-profile-first",
                "question": "Generate demo animation assets",
                "normalized_question": "generate demo animation assets",
                "family_father_question": "Generate demo animation assets",
                "question_variants": ["Generate demo animation assets"],
                "family_prompt_profile_terms": [
                    "demo",
                    "gif",
                    "readme",
                    "asset",
                    "record",
                    "wireframe",
                    "walkthrough",
                    "automation",
                ],
                "family_command_pattern_summary": [
                    "record",
                    "gif",
                    "asset",
                    "readme",
                ],
                "family_constraint_summary": [
                    "readme.md",
                    "demo.gif",
                    "wireframe",
                    "walkthrough",
                ],
                "family_success_metric": {
                    "posterior_mean": 0.8,
                    "lower_bound": 0.65,
                    "uncertainty": 0.05,
                },
                "family_records": [],
            }
        ]
    }

    support_from_payload = resolve_prompt_family_support_from_payload(
        "Refresh the tracked walkthrough asset and update the README embed.",
        payload,
    )

    assert support_from_payload.prompt_family_id == "pf-profile-first"
    assert support_from_payload.supported is True
    assert support_from_payload.similarity >= 0.8


def test_materialize_training_candidates_strips_execution_envelope_from_family_father(
    tmp_path: Path,
) -> None:
    imported_dir = tmp_path / "artifacts" / "traces" / "imported"
    imported_dir.mkdir(parents=True, exist_ok=True)
    dirty_original = (
        "Discord channel: prompts_debt_relief\n"
        "Repository checkout: realagiorganization/national-debt-relief -> "
        "/workspace/checked-out-repo\n"
        "Attachment mount: attachments_prompts_debt_relief\n\n"
        "Continue developing the national debt relief landing page"
    )
    dirty_reformulated = (
        "Discord channel: prompts_debt_relief\n"
        "Repository checkout: realagiorganization/national-debt-relief -> "
        "/workspace/checked-out-repo\n"
        "Attachment mount: attachments_prompts_debt_relief\n\n"
        "Inspect the existing landing page and continue development."
    )
    (imported_dir / "dirty-envelope.json").write_text(
        json.dumps(
            {
                "trace_record_kind": "repo-rag-trace-record",
                "trace_record_path": "artifacts/traces/imported/dirty-envelope.json",
                "question": dirty_reformulated,
                "original_prompt": dirty_original,
                "reformulated_prompt": dirty_reformulated,
                "answer": "The landing page already contains the requested baseline assets.",
                "command_trace": [
                    {
                        "type": "message",
                        "role": "user",
                        "text": dirty_original,
                    }
                ],
                "trace": {
                    "schema_version": 1,
                    "trace_kind": "repo-rag-runtime",
                    "recorded_at": "2026-05-10T19:42:26+00:00",
                    "question": dirty_reformulated,
                    "original_prompt": dirty_original,
                    "reformulated_prompt": dirty_reformulated,
                    "mode": "codex-proxy",
                    "retrieval_mode": "lexical",
                    "sources": ["README.md"],
                    "source_count": 1,
                    "context_count": 1,
                    "context_field": "evidence_previews",
                    "top_k": 4,
                    "program_loaded": False,
                    "mcp_candidate_count": 0,
                    "answer_length": 63,
                },
                "outcome": {
                    "acceptance_status": "candidate",
                    "accepted": None,
                    "execution_status": "success",
                    "method": "codex_cli",
                    "backend": "codex_cli_repo_rag_proxy",
                    "used_baseline_fallback": True,
                },
            }
        ),
        encoding="utf-8",
    )

    summary = materialize_training_candidates(
        tmp_path,
        output_path=Path("artifacts/trainer/training-candidates.yaml"),
        summary_path=Path("artifacts/trainer/training-candidates-summary.json"),
    )

    assert summary["candidate_count"] == 1
    materialized_payload = yaml.safe_load(
        (tmp_path / "artifacts" / "trainer" / "training-candidates.yaml").read_text(
            encoding="utf-8"
        )
    )
    assert materialized_payload[0]["question"] == (
        "Continue developing the national debt relief landing page"
    )
    assert materialized_payload[0]["original_prompt"] == (
        "Continue developing the national debt relief landing page"
    )
    assert materialized_payload[0]["reformulated_prompt"] == (
        "Inspect the existing landing page and continue development."
    )
    assert materialized_payload[0]["command_trace"] == [
        {
            "type": "message",
            "role": "user",
            "text": "Continue developing the national debt relief landing page",
        }
    ]

    family_state_path = tmp_path / "artifacts" / "trainer" / "family-state.json"
    family_state = json.loads(family_state_path.read_text(encoding="utf-8"))
    family_payload = family_state["prompt_families"][0]
    assert family_payload["family_father_question"] == (
        "Continue developing the national debt relief landing page"
    )
    assert str(family_payload["family_path"]).startswith("families/pf-")
    assert str(family_payload["family_path"]).endswith("/family.json")
    assert "family_records" not in family_payload
    assert "context_groups" not in family_payload
    assert "family_father_record" not in family_payload
    assert "family_runtime_artifact" not in family_payload
    assert "family_runtime_record" not in family_payload
    assert "family_champion_record" not in family_payload
    assert "Repository checkout:" not in family_payload["family_father_question"]
    support = resolve_prompt_family_support(
        "Continue developing the national debt relief landing page",
        family_state_path,
    )
    assert support.supported is True
    assert support.band == "match"
    assert support.family_father_question == (
        "Continue developing the national debt relief landing page"
    )


def test_materialize_training_candidates_dedupes_replayed_processed_trace_imports(
    tmp_path: Path,
) -> None:
    imported_dir = tmp_path / "artifacts" / "traces" / "imported"
    imported_dir.mkdir(parents=True, exist_ok=True)
    base_payload: dict[str, Any] = {
        "trace_record_kind": "repo-rag-trace-record",
        "question": "Add a demo GIF to README",
        "original_prompt": "Add a demo GIF to README",
        "reformulated_prompt": "Inspect whether the README already embeds a demo GIF.",
        "answer": "No father-backed prompt-family support was found for this turn.",
        "source_queue_item_path": (
            "queued/repo-rag-training/20260513T120200Z-worker-0-prompts_debt_relief.json"
        ),
        "source_trace_name": "worker-0-prompts_debt_relief",
        "trace": {
            "schema_version": 1,
            "trace_kind": "repo-rag-runtime",
            "question": "Add a demo GIF to README",
            "recorded_at": "2026-05-13T12:00:00+00:00",
            "mode": "codex-proxy-turn-mediation",
            "retrieval_mode": "lexical",
            "sources": [],
            "source_count": 0,
            "context_count": 0,
            "context_field": "evidence_previews",
            "mcp_candidate_count": 0,
            "answer_length": 63,
        },
        "outcome": {
            "acceptance_status": "candidate",
            "accepted": None,
            "execution_status": "success",
            "method": "codex_cli",
            "backend": "codex_cli_repo_rag_proxy",
        },
    }
    (imported_dir / "first.json").write_text(
        json.dumps(
            {
                **base_payload,
                "trace_record_path": "artifacts/traces/imported/20260513T120200Z-worker-0.json",
            }
        ),
        encoding="utf-8",
    )
    (imported_dir / "second.json").write_text(
        json.dumps(
            {
                **base_payload,
                "trace_record_path": (
                    "artifacts/traces/imported/20260513T121509Z-20260513T120200Z-worker-0.json"
                ),
                "trace": {
                    **base_payload["trace"],
                    "recorded_at": "2026-05-13T12:15:09+00:00",
                },
            }
        ),
        encoding="utf-8",
    )

    summary = materialize_training_candidates(
        tmp_path,
        trace_paths=[
            Path("artifacts/traces/imported/first.json"),
            Path("artifacts/traces/imported/second.json"),
        ],
        output_path=Path("artifacts/trainer/training-candidates.yaml"),
        summary_path=Path("artifacts/trainer/training-candidates-summary.json"),
    )

    assert summary["loaded_candidate_count"] == 2
    family_state = load_family_state_payload(
        tmp_path / "artifacts" / "trainer" / "family-state.json"
    )
    family_payload = family_state["prompt_families"][0]
    family_records = family_payload["family_records"]
    assert len(family_records) == 1
    assert (
        family_records[0]["provenance"]["source_queue_item_path"]
        == "queued/repo-rag-training/20260513T120200Z-worker-0-prompts_debt_relief.json"
    )


def test_materialize_training_candidates_dedupes_replayed_queue_item_prefixes(
    tmp_path: Path,
) -> None:
    imported_dir = tmp_path / "artifacts" / "traces" / "imported"
    imported_dir.mkdir(parents=True, exist_ok=True)
    base_payload: dict[str, Any] = {
        "trace_record_kind": "repo-rag-trace-record",
        "question": "Inspect the README demo GIF flow",
        "original_prompt": "Inspect the README demo GIF flow",
        "reformulated_prompt": "Check whether README already documents the GIF flow.",
        "answer": "No father-backed prompt-family support was found for this turn.",
        "source_trace_name": "worker-readme-5",
        "trace": {
            "schema_version": 1,
            "trace_kind": "repo-rag-runtime",
            "question": "Inspect the README demo GIF flow",
            "recorded_at": "2026-05-14T19:27:32+00:00",
            "mode": "codex-proxy-turn-mediation",
            "retrieval_mode": "lexical",
            "sources": [],
            "source_count": 0,
            "context_count": 0,
            "context_field": "evidence_previews",
            "mcp_candidate_count": 0,
            "answer_length": 63,
        },
        "outcome": {
            "acceptance_status": "candidate",
            "accepted": None,
            "execution_status": "success",
            "method": "codex_cli",
            "backend": "codex_cli_repo_rag_proxy",
        },
    }
    (imported_dir / "direct.json").write_text(
        json.dumps(
            {
                **base_payload,
                "source_queue_item_path": (
                    "queued/repo-rag-training/20260514T192732Z-worker-readme-5.json"
                ),
                "trace_record_path": (
                    "artifacts/traces/imported/20260514T192732Z-worker-readme-5.json"
                ),
            }
        ),
        encoding="utf-8",
    )
    (imported_dir / "replayed.json").write_text(
        json.dumps(
            {
                **base_payload,
                "source_queue_item_path": (
                    "queued/repo-rag-training/"
                    "20260514T192921Z-20260514T192732Z-worker-readme-5.json"
                ),
                "trace_record_path": (
                    "artifacts/traces/imported/"
                    "20260514T193012Z-20260514T192921Z-20260514T192732Z-worker-readme-5.json"
                ),
                "trace": {
                    **base_payload["trace"],
                    "recorded_at": "2026-05-14T19:30:12+00:00",
                },
            }
        ),
        encoding="utf-8",
    )

    summary = materialize_training_candidates(
        tmp_path,
        trace_paths=[
            Path("artifacts/traces/imported/direct.json"),
            Path("artifacts/traces/imported/replayed.json"),
        ],
        output_path=Path("artifacts/trainer/training-candidates.yaml"),
        summary_path=Path("artifacts/trainer/training-candidates-summary.json"),
    )

    assert summary["loaded_candidate_count"] == 2
    family_state = load_family_state_payload(
        tmp_path / "artifacts" / "trainer" / "family-state.json"
    )
    family_payload = family_state["prompt_families"][0]
    family_records = family_payload["family_records"]
    assert len(family_records) == 1
    assert family_records[0]["exact_snapshot_id"].startswith("ts-")


def test_resolve_prompt_family_support_matches_best_family_father(tmp_path: Path) -> None:
    trainer_dir = tmp_path / "artifacts" / "trainer"
    trainer_dir.mkdir(parents=True, exist_ok=True)
    family_state_path = trainer_dir / "champion-index.json"
    family_state_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "record_kind": "repo-rag-trainer-champion-index",
                "generated_at": "2026-05-09T18:00:00+00:00",
                "prompt_families": [
                    {
                        "prompt_family_id": "pf-readme",
                        "question": "Inspect whether the README already embeds a demo GIF.",
                        "normalized_question": (
                            "inspect whether the readme already embeds a demo gif."
                        ),
                        "family_father_question": (
                            "Inspect whether the README already embeds a demo GIF."
                        ),
                        "family_father_record": {
                            "question": "Inspect whether the README already embeds a demo GIF.",
                            "expected_answer": "README already embeds the GIF.",
                            "tags": ["trainer-candidate"],
                        },
                        "family_runtime_record": {
                            "question": "Inspect whether the README already embeds a demo GIF.",
                            "expected_answer": "README already embeds the GIF.",
                            "tags": ["trainer-candidate"],
                        },
                        "family_champion_context_group_id": "cg-readme",
                        "family_champion_score": 1.0,
                        "family_champion_record": {
                            "question": "Inspect whether the README already embeds a demo GIF.",
                            "expected_answer": "README already embeds the GIF.",
                            "tags": ["trainer-candidate"],
                        },
                        "context_groups": [],
                    },
                    {
                        "prompt_family_id": "pf-tests",
                        "question": "Run the failing pytest target and inspect stderr.",
                        "normalized_question": "run the failing pytest target and inspect stderr.",
                        "family_father_question": (
                            "Run the failing pytest target and inspect stderr."
                        ),
                        "family_father_record": {
                            "question": "Run the failing pytest target and inspect stderr.",
                            "expected_answer": "Inspect the failing pytest output.",
                            "tags": ["trainer-candidate"],
                        },
                        "family_runtime_record": {
                            "question": "Run the failing pytest target and inspect stderr.",
                            "expected_answer": "Inspect the failing pytest output.",
                            "tags": ["trainer-candidate"],
                        },
                        "family_champion_context_group_id": "cg-tests",
                        "family_champion_score": 1.0,
                        "family_champion_record": {
                            "question": "Run the failing pytest target and inspect stderr.",
                            "expected_answer": "Inspect the failing pytest output.",
                            "tags": ["trainer-candidate"],
                        },
                        "context_groups": [],
                    },
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    support = resolve_prompt_family_support(
        "Inspect whether the README already has a demo GIF embedded.",
        family_state_path,
    )

    assert support.supported is True
    assert support.band == "match"
    assert support.prompt_family_id == "pf-readme"
    assert support.family_father_question == (
        "Inspect whether the README already embeds a demo GIF."
    )
    assert support.family_runtime_record is not None


def test_resolve_prompt_family_support_normalizes_dirty_persisted_family_state(
    tmp_path: Path,
) -> None:
    trainer_dir = tmp_path / "artifacts" / "trainer"
    trainer_dir.mkdir(parents=True, exist_ok=True)
    family_state_path = trainer_dir / "family-state.json"
    dirty_question = (
        "Discord channel: prompts_debt_relief\n\n"
        "Messages with required reaction:\n"
        "[1] (2026-05-10T00:00:00+00:00 | drybox | id=1) "
        "Add a demo GIF to README\n"
        "Repository checkout: /tmp/repositories/demo\n"
        "Attachment mount: /tmp/attachments\n"
    )
    family_state_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "record_kind": "repo-rag-trainer-champion-index",
                "family_state_kind": "repo-rag-trainer-family-state",
                "generated_at": "2026-05-10T20:00:00+00:00",
                "prompt_families": [
                    {
                        "prompt_family_id": "pf-demo",
                        "question": dirty_question,
                        "normalized_question": dirty_question.casefold(),
                        "family_father_question": dirty_question,
                        "family_father_record": {
                            "question": dirty_question,
                            "expected_answer": "README already embeds the GIF.",
                            "tags": ["trainer-candidate"],
                            "original_prompt": dirty_question,
                            "reformulated_prompt": dirty_question,
                            "command_trace": [
                                {
                                    "type": "message",
                                    "role": "user",
                                    "text": dirty_question,
                                }
                            ],
                        },
                        "family_runtime_record": {
                            "question": dirty_question,
                            "expected_answer": "README already embeds the GIF.",
                            "tags": ["trainer-candidate"],
                            "original_prompt": dirty_question,
                            "reformulated_prompt": dirty_question,
                        },
                        "family_champion_context_group_id": "cg-demo",
                        "family_champion_score": 1.0,
                        "family_champion_record": {
                            "question": dirty_question,
                            "expected_answer": "README already embeds the GIF.",
                            "tags": ["trainer-candidate"],
                        },
                        "family_records": [
                            {
                                "question": dirty_question,
                                "expected_answer": "README already embeds the GIF.",
                                "tags": ["trainer-candidate"],
                                "original_prompt": dirty_question,
                                "reformulated_prompt": dirty_question,
                                "command_trace": [
                                    {
                                        "type": "message",
                                        "role": "user",
                                        "text": dirty_question,
                                    }
                                ],
                            }
                        ],
                        "context_groups": [],
                    }
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    support = resolve_prompt_family_support("Add a demo GIF to README", family_state_path)
    materialize_training_candidates(
        tmp_path,
        trace_paths=[],
        output_path=Path("artifacts/trainer/training-candidates.yaml"),
        summary_path=Path("artifacts/trainer/training-candidates-summary.json"),
        family_state_path=Path("artifacts/trainer/family-state.json"),
    )
    rewritten_state = load_family_state_payload(family_state_path)
    family_payload = rewritten_state["prompt_families"][0]

    assert support.supported is True
    assert support.band == "match"
    assert support.prompt_family_id == "pf-demo"
    assert support.family_father_question == "Add a demo GIF to README"
    assert family_payload["family_father_question"] == "Add a demo GIF to README"
    assert family_payload["question"] == "Add a demo GIF to README"
    assert family_payload["family_father_record"]["original_prompt"] == "Add a demo GIF to README"
    assert family_payload["family_records"][0]["reformulated_prompt"] == "Add a demo GIF to README"
    assert family_payload["family_records"][0]["command_trace"] == [
        {
            "type": "message",
            "role": "user",
            "text": "Add a demo GIF to README",
        }
    ]


def test_materialize_training_candidates_respects_explicit_empty_trace_paths(
    tmp_path: Path,
) -> None:
    imported_dir = tmp_path / "artifacts" / "traces" / "imported"
    imported_dir.mkdir(parents=True, exist_ok=True)
    (imported_dir / "accepted.json").write_text(
        json.dumps(
            {
                "trace_record_kind": "repo-rag-trace-record",
                "trace_record_path": "artifacts/traces/imported/accepted.json",
                "question": "Add a demo GIF to README",
                "answer": "README already embeds the GIF.",
                "trace": {
                    "schema_version": 1,
                    "trace_kind": "repo-rag-runtime",
                    "recorded_at": "2026-05-10T20:05:00+00:00",
                    "question": "Add a demo GIF to README",
                    "mode": "codex-proxy",
                    "sources": ["README.md"],
                    "source_count": 1,
                    "context_count": 0,
                    "program_loaded": False,
                    "mcp_candidate_count": 0,
                    "answer_length": 31,
                },
                "outcome": {
                    "acceptance_status": "accepted",
                    "accepted": True,
                    "execution_status": "success",
                    "method": "codex_cli",
                    "backend": "codex_cli_repo_rag_proxy",
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    summary = materialize_training_candidates(
        tmp_path,
        trace_paths=[],
        output_path=Path("artifacts/trainer/training-candidates.yaml"),
        summary_path=Path("artifacts/trainer/training-candidates-summary.json"),
        seed_existing_output=False,
    )

    assert summary["input_trace_count"] == 0
    assert summary["loaded_candidate_count"] == 0
    assert summary["candidate_count"] == 0
    assert summary["trace_paths"] == []
    materialized_payload = yaml.safe_load(
        (tmp_path / "artifacts" / "trainer" / "training-candidates.yaml").read_text(
            encoding="utf-8"
        )
    )
    assert materialized_payload == []


def test_resolve_prompt_family_support_creates_new_family_below_threshold(tmp_path: Path) -> None:
    trainer_dir = tmp_path / "artifacts" / "trainer"
    trainer_dir.mkdir(parents=True, exist_ok=True)
    family_state_path = trainer_dir / "champion-index.json"
    family_state_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "record_kind": "repo-rag-trainer-champion-index",
                "generated_at": "2026-05-09T18:05:00+00:00",
                "prompt_families": [
                    {
                        "prompt_family_id": "pf-readme",
                        "question": "Inspect whether the README already embeds a demo GIF.",
                        "normalized_question": (
                            "inspect whether the readme already embeds a demo gif."
                        ),
                        "family_father_question": (
                            "Inspect whether the README already embeds a demo GIF."
                        ),
                        "family_father_record": {
                            "question": "Inspect whether the README already embeds a demo GIF.",
                            "expected_answer": "README already embeds the GIF.",
                            "tags": ["trainer-candidate"],
                        },
                        "family_runtime_record": {
                            "question": "Inspect whether the README already embeds a demo GIF.",
                            "expected_answer": "README already embeds the GIF.",
                            "tags": ["trainer-candidate"],
                        },
                        "family_champion_context_group_id": "cg-readme",
                        "family_champion_score": 1.0,
                        "family_champion_record": {
                            "question": "Inspect whether the README already embeds a demo GIF.",
                            "expected_answer": "README already embeds the GIF.",
                            "tags": ["trainer-candidate"],
                        },
                        "context_groups": [],
                    }
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    support = resolve_prompt_family_support(
        "Provision a new AKS cluster and rotate deployment secrets.",
        family_state_path,
    )

    assert support.supported is False
    assert support.band == "new"
    assert support.prompt_family_id == "pf-readme"


def test_materialize_training_candidates_keeps_persisted_champions_without_benchmark_gate(
    tmp_path: Path,
) -> None:
    trainer_dir = tmp_path / "artifacts" / "trainer"
    trainer_dir.mkdir(parents=True, exist_ok=True)
    (trainer_dir / "training-candidates.yaml").write_text(
        (
            '- question: "Add a demo GIF to README"\n'
            '  expected_answer: "The GIF is already present and the git worktree is clean."\n'
            '  tags: ["trainer-candidate", "candidate"]\n'
            "  benchmark_context:\n"
            '    - "# national-debt-relief ## Demo '
            '![Automated demo walkthrough](docs/assets/national-debt-relief-demo.gif)"\n'
            "  benchmark_context_sources:\n"
            '    - "README.md"\n'
            "  provenance:\n"
            '    trace_record_path: "artifacts/trainer/'
            'recovered-imported-traces/unsupported.json"\n'
            '    recorded_at: "2026-05-08T13:20:42+00:00"\n'
        ),
        encoding="utf-8",
    )
    champion_index_path = trainer_dir / "champion-index.json"
    champion_index_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "record_kind": "repo-rag-trainer-champion-index",
                "generated_at": "2026-05-08T13:21:00+00:00",
                "prompt_families": [
                    {
                        "prompt_family_id": "pf-demo",
                        "question": "Add a demo GIF to README",
                        "family_champion_context_group_id": "cg-demo",
                        "family_champion_score": 0.91,
                        "family_champion_record": {
                            "question": "Add a demo GIF to README",
                            "expected_answer": (
                                "The GIF is already present and the git worktree is clean."
                            ),
                            "tags": ["trainer-candidate", "candidate"],
                            "expected_sources": [],
                            "benchmark_context": [
                                "# national-debt-relief ## Demo "
                                "![Automated demo walkthrough]"
                                "(docs/assets/national-debt-relief-demo.gif)"
                            ],
                            "benchmark_context_sources": ["README.md"],
                            "candidate_status": "candidate",
                            "prompt_family_id": "pf-demo",
                            "context_group_id": "cg-demo",
                            "exact_snapshot_id": "ts-demo",
                            "quality_score": 0.91,
                            "support_count": 1,
                            "provenance": {
                                "trace_record_path": (
                                    "artifacts/trainer/recovered-imported-traces/unsupported.json"
                                ),
                                "recorded_at": "2026-05-08T13:20:42+00:00",
                            },
                        },
                        "context_groups": [
                            {
                                "context_group_id": "cg-demo",
                                "sources": ["README.md"],
                                "evidence_fingerprints": ["ev-demo"],
                                "evidence_count": 1,
                                "retrieval_mode": "lexical",
                                "mode": "codex-proxy",
                                "context_field": "evidence_previews",
                                "source_count": 1,
                                "context_count": 1,
                                "top_k": 4,
                                "trace_count": 1,
                                "support_by_record_key": {"cr-demo": 1},
                                "champion_score": 0.91,
                                "champion_record": {
                                    "question": "Add a demo GIF to README",
                                    "expected_answer": (
                                        "The GIF is already present and the git worktree is clean."
                                    ),
                                    "tags": ["trainer-candidate", "candidate"],
                                    "expected_sources": [],
                                    "benchmark_context": [
                                        "# national-debt-relief ## Demo "
                                        "![Automated demo walkthrough]"
                                        "(docs/assets/national-debt-relief-demo.gif)"
                                    ],
                                    "benchmark_context_sources": ["README.md"],
                                    "candidate_status": "candidate",
                                    "prompt_family_id": "pf-demo",
                                    "context_group_id": "cg-demo",
                                    "exact_snapshot_id": "ts-demo",
                                    "quality_score": 0.91,
                                    "support_count": 1,
                                    "provenance": {
                                        "trace_record_path": (
                                            "artifacts/trainer/recovered-imported-traces/"
                                            "unsupported.json"
                                        ),
                                        "recorded_at": "2026-05-08T13:20:42+00:00",
                                    },
                                },
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    summary = materialize_training_candidates(
        tmp_path,
        output_path=Path("artifacts/trainer/training-candidates.yaml"),
        summary_path=Path("artifacts/trainer/training-candidates-summary.json"),
        champion_index_path=Path("artifacts/trainer/champion-index.json"),
    )

    assert summary["candidate_count"] == 1
    assert summary["family_state_path"] == "artifacts/trainer/family-state.json"
    family_state_path = tmp_path / str(summary["family_state_path"])
    assert family_state_path.exists()
    champion_index = load_family_state_payload(family_state_path)
    family = champion_index["prompt_families"][0]
    assert family["family_champion_record"] is not None
    assert len(family["context_groups"]) == 1


def test_summarize_champion_index_reports_family_trace_and_snapshot_ids(tmp_path: Path) -> None:
    trainer_dir = tmp_path / "artifacts" / "trainer"
    trainer_dir.mkdir(parents=True, exist_ok=True)
    champion_index = {
        "schema_version": 1,
        "record_kind": "repo-rag-trainer-champion-index",
        "generated_at": "2026-05-07T17:00:00+00:00",
        "prompt_families": [
            {
                "prompt_family_id": "pf-goat",
                "question": "Draft the Goat Labs scope split",
                "normalized_question": "draft the goat labs scope split",
                "family_champion_context_group_id": "cg-goat",
                "family_champion_score": 0.9,
                "family_champion_record": {
                    "question": "Draft the Goat Labs scope split",
                    "expected_answer": "Prepared the scope split.",
                    "tags": ["trainer-candidate", "candidate"],
                    "expected_sources": [],
                    "candidate_status": "candidate",
                    "prompt_family_id": "pf-goat",
                    "context_group_id": "cg-goat",
                    "exact_snapshot_id": "ts-goat",
                    "quality_score": 0.9,
                    "support_count": 1,
                    "provenance": {
                        "trace_record_path": (
                            "artifacts/trainer/recovered-imported-traces/"
                            "20260506T221908Z-worker-0-prompts_goat_labs-p00000-298625-"
                            "realagiorganization_goat_labs.json"
                        )
                    },
                },
                "context_groups": [
                    {
                        "context_group_id": "cg-goat",
                        "sources": ["README.md"],
                        "evidence_fingerprints": [],
                        "evidence_count": 0,
                        "retrieval_mode": "lexical",
                        "mode": "codex-proxy",
                        "context_field": "evidence_previews",
                        "source_count": 1,
                        "context_count": 1,
                        "top_k": 4,
                        "trace_count": 1,
                        "support_by_record_key": {},
                        "champion_score": 0.9,
                        "champion_record": {
                            "question": "Draft the Goat Labs scope split",
                            "expected_answer": "Prepared the scope split.",
                            "tags": ["trainer-candidate", "candidate"],
                            "expected_sources": [],
                            "candidate_status": "candidate",
                            "prompt_family_id": "pf-goat",
                            "context_group_id": "cg-goat",
                            "exact_snapshot_id": "ts-goat",
                            "quality_score": 0.9,
                            "support_count": 1,
                            "provenance": {
                                "trace_record_path": (
                                    "artifacts/trainer/recovered-imported-traces/"
                                    "20260506T221908Z-worker-0-prompts_goat_labs-p00000-298625-"
                                    "realagiorganization_goat_labs.json"
                                )
                            },
                        },
                    }
                ],
            }
        ],
    }
    champion_index_path = trainer_dir / "champion-index.json"
    champion_index_path.write_text(json.dumps(champion_index, indent=2), encoding="utf-8")

    summary = summarize_champion_index(champion_index_path)

    assert summary["candidate_count"] == 1
    assert summary["family_candidate_count"] == 1
    assert summary["prompt_family_ids"] == ["pf-goat"]
    assert summary["family_exact_snapshot_ids"] == ["ts-goat"]
    assert summary["champion_exact_snapshot_ids"] == ["ts-goat"]
    assert summary["family_trace_record_paths"] == [
        "artifacts/trainer/recovered-imported-traces/"
        "20260506T221908Z-worker-0-prompts_goat_labs-p00000-298625-"
        "realagiorganization_goat_labs.json"
    ]
    assert summary["champion_trace_record_paths"] == [
        "artifacts/trainer/recovered-imported-traces/"
        "20260506T221908Z-worker-0-prompts_goat_labs-p00000-298625-"
        "realagiorganization_goat_labs.json"
    ]
    assert summary["family_record_hashes"]
    assert summary["champion_record_hashes"]


def test_summarize_family_state_matches_champion_compat_summary(tmp_path: Path) -> None:
    trainer_dir = tmp_path / "artifacts" / "trainer"
    trainer_dir.mkdir(parents=True, exist_ok=True)
    family_state_path = trainer_dir / "champion-index.json"
    family_state_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "record_kind": "repo-rag-trainer-champion-index",
                "family_state_kind": "repo-rag-trainer-family-state",
                "generated_at": "2026-05-09T18:05:00+00:00",
                "prompt_families": [
                    {
                        "prompt_family_id": "pf-demo",
                        "family_runtime_record": {
                            "question": "Explain the repo",
                            "expected_answer": "It explains the repo.",
                            "tags": ["trainer-candidate"],
                            "prompt_family_id": "pf-demo",
                            "exact_snapshot_id": "ts-demo",
                            "provenance": {
                                "trace_record_path": "artifacts/traces/imported/demo.json"
                            },
                        },
                        "context_groups": [],
                    }
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    family_summary = summarize_family_state(family_state_path)
    compat_summary = summarize_champion_index(family_state_path)

    assert family_summary["family_trace_record_paths"] == ["artifacts/traces/imported/demo.json"]
    assert "champion_trace_record_paths" not in family_summary
    assert (
        compat_summary["family_trace_record_paths"] == (family_summary["family_trace_record_paths"])
    )
    assert (
        compat_summary["champion_trace_record_paths"]
        == (family_summary["family_trace_record_paths"])
    )
    assert (
        compat_summary["champion_exact_snapshot_ids"]
        == (family_summary["family_exact_snapshot_ids"])
    )
    assert compat_summary["champion_record_hashes"] == family_summary["family_record_hashes"]


def test_materialize_training_candidates_normalizes_legacy_worker_sources_and_duplicate_questions(
    tmp_path: Path,
) -> None:
    trainer_dir = tmp_path / "artifacts" / "trainer"
    trainer_dir.mkdir(parents=True, exist_ok=True)
    candidates_path = trainer_dir / "training-candidates.yaml"
    candidates_path.write_text(
        (
            '- question: "What does this repository research?"\n'
            '  expected_answer: "Legacy answer A."\n'
            '  tags: ["trainer-candidate", "candidate"]\n'
            "  expected_sources:\n"
            '    - "prompt_artifacts/prompts_shards_of_lokar_game-p00000-355cca.txt"\n'
            '- question: "What does this repository research?"\n'
            '  expected_answer: "Legacy answer B."\n'
            '  tags: ["trainer-candidate", "candidate"]\n'
            "  expected_sources:\n"
            '    - "docs/USAGE.md"\n'
        ),
        encoding="utf-8",
    )

    summary = materialize_training_candidates(
        tmp_path,
        output_path=Path("artifacts/trainer/training-candidates.yaml"),
        summary_path=Path("artifacts/trainer/training-candidates-summary.json"),
    )

    assert summary["candidate_count"] == 1
    assert summary["new_candidate_count"] == 0
    assert summary["replaced_count"] == 0
    materialized = load_training_examples(candidates_path)
    assert len(materialized) == 1
    assert materialized[0].question == "What does this repository research?"
    assert materialized[0].expected_sources == ()


def test_materialize_training_candidates_replaces_existing_candidate_with_new_trace(
    tmp_path: Path,
) -> None:
    imported_dir = tmp_path / "artifacts" / "traces" / "imported"
    imported_dir.mkdir(parents=True, exist_ok=True)
    trainer_dir = tmp_path / "artifacts" / "trainer"
    trainer_dir.mkdir(parents=True, exist_ok=True)
    candidates_path = trainer_dir / "training-candidates.yaml"
    candidates_path.write_text(
        (
            '- question: "What does this repository research?"\n'
            '  expected_answer: "Legacy answer."\n'
            '  tags: ["trainer-candidate", "candidate"]\n'
            "  expected_sources:\n"
            '    - "prompt_artifacts/prompts_shards_of_lokar_game-p00000-355cca.txt"\n'
        ),
        encoding="utf-8",
    )
    (imported_dir / "accepted.json").write_text(
        """{
  "trace_record_kind": "repo-rag-trace-record",
  "trace_record_path": "artifacts/traces/imported/accepted.json",
  "question": "What does this repository research?",
  "answer": "It researches repository-grounded RAG.",
  "sources": ["README.md"],
  "trace": {
    "schema_version": 1,
    "trace_kind": "repo-rag-runtime",
    "recorded_at": "2026-05-01T00:00:00+00:00",
    "question": "What does this repository research?",
    "mode": "codex-proxy",
    "retrieval_mode": "rag_heuristic_dspy",
    "sources": ["README.md"],
    "source_count": 1,
    "context_count": 1,
    "context_field": "context",
    "mcp_candidate_count": 0,
    "answer_length": 20
  },
  "outcome": {
    "acceptance_status": "candidate",
    "accepted": null,
    "execution_status": "success",
    "method": "codex_cli",
    "backend": "codex_cli_repo_rag_proxy"
  }
}
""",
        encoding="utf-8",
    )

    summary = materialize_training_candidates(
        tmp_path,
        output_path=Path("artifacts/trainer/training-candidates.yaml"),
        summary_path=Path("artifacts/trainer/training-candidates-summary.json"),
    )

    assert summary["candidate_count"] == 1
    assert summary["new_candidate_count"] == 1
    assert summary["replaced_count"] == 1
    materialized = load_training_examples(candidates_path)
    assert len(materialized) == 1
    assert materialized[0].expected_answer == "It researches repository-grounded RAG."
    assert materialized[0].expected_sources == ()


def test_materialize_training_candidates_reports_no_new_candidates_for_unchanged_full_ledger(
    tmp_path: Path,
) -> None:
    imported_dir = tmp_path / "artifacts" / "traces" / "imported"
    imported_dir.mkdir(parents=True, exist_ok=True)
    trainer_dir = tmp_path / "artifacts" / "trainer"
    trainer_dir.mkdir(parents=True, exist_ok=True)
    candidates_path = trainer_dir / "training-candidates.yaml"
    summary_path = trainer_dir / "training-candidates-summary.json"
    trace_path = imported_dir / "accepted.json"
    trace_path.write_text(
        """{
  "trace_record_kind": "repo-rag-trace-record",
  "trace_record_path": "artifacts/traces/imported/accepted.json",
  "question": "What does this repository research?",
  "answer": "It researches repository-grounded RAG.",
  "sources": ["README.md"],
  "trace": {
    "schema_version": 1,
    "trace_kind": "repo-rag-runtime",
    "recorded_at": "2026-05-01T00:00:00+00:00",
    "question": "What does this repository research?",
    "mode": "codex-proxy",
    "retrieval_mode": "rag_heuristic_dspy",
    "sources": ["README.md"],
    "source_count": 1,
    "context_count": 1,
    "context_field": "context",
    "mcp_candidate_count": 0,
    "answer_length": 20
  },
  "outcome": {
    "acceptance_status": "candidate",
    "accepted": null,
    "execution_status": "success",
    "method": "codex_cli",
    "backend": "codex_cli_repo_rag_proxy"
  }
}
""",
        encoding="utf-8",
    )

    first_summary = materialize_training_candidates(
        tmp_path,
        output_path=Path("artifacts/trainer/training-candidates.yaml"),
        summary_path=Path("artifacts/trainer/training-candidates-summary.json"),
    )
    second_summary = materialize_training_candidates(
        tmp_path,
        output_path=Path("artifacts/trainer/training-candidates.yaml"),
        summary_path=Path("artifacts/trainer/training-candidates-summary.json"),
    )

    assert first_summary["candidate_count"] == 1
    assert first_summary["new_candidate_count"] == 1


def test_materialize_training_candidates_preserves_all_imported_full_traces_in_family_records(
    tmp_path: Path,
) -> None:
    imported_dir = tmp_path / "artifacts" / "traces" / "imported"
    imported_dir.mkdir(parents=True, exist_ok=True)
    variants = [
        (
            "Outer prompt A",
            "Outer prompt A",
            "Outer prompt A",
            "No family support for prompt A.",
        ),
        (
            "Outer prompt B",
            "Outer prompt A",
            "Outer prompt B",
            "No family support for prompt B.",
        ),
        (
            "Envelope prompt",
            "<environment_context> cwd=/tmp/repo </environment_context>",
            "Envelope prompt",
            "No family support for envelope prompt.",
        ),
        (
            "Inspect repository structure",
            "Inspect repository structure",
            "Inspect repository structure",
            "No family support for structure inspection.",
        ),
        (
            "Verify README GIF asset",
            "Verify README GIF asset",
            "Verify README GIF asset",
            "No family support for asset verification.",
        ),
        (
            "Validate reproducibility",
            "Validate reproducibility",
            "Validate reproducibility",
            "No family support for reproducibility validation.",
        ),
        (
            "Final no-op sanity check",
            "Final no-op sanity check",
            "Final no-op sanity check",
            "No family support for final sanity check.",
        ),
    ]
    for index, (question, original_prompt, reformulated_prompt, answer) in enumerate(variants):
        trace_path = imported_dir / f"trace-{index}.json"
        trace_path.write_text(
            json.dumps(
                {
                    "trace_record_kind": "repo-rag-trace-record",
                    "trace_record_path": f"artifacts/traces/imported/trace-{index}.json",
                    "source_queue_item_path": (
                        "artifacts/traces/queued/repo-rag-training/"
                        f"20260517T0621{index:02d}Z-trace-{index}.json"
                    ),
                    "source_trace_name": f"trace-{index}",
                    "source_batch_name": "20260517T062138Z",
                    "question": question,
                    "original_prompt": original_prompt,
                    "reformulated_prompt": reformulated_prompt,
                    "answer": answer,
                    "sources": [],
                    "context": [],
                    "retrieved_context": [],
                    "command_trace": [],
                    "trace": {
                        "schema_version": 1,
                        "trace_kind": "repo-rag-runtime",
                        "recorded_at": f"2026-05-17T06:2{index}:00+00:00",
                        "question": question,
                        "original_prompt": original_prompt,
                        "reformulated_prompt": reformulated_prompt,
                        "mode": "codex-proxy-turn-mediation",
                        "retrieval_mode": "lexical",
                        "sources": [],
                        "source_count": 0,
                        "context_count": 0,
                        "context_field": "evidence_previews",
                        "mediation_metric_hits": 1,
                        "mediation_metric_total": 1,
                        "trainer_signal_kind": "full_trace",
                    },
                    "outcome": {
                        "acceptance_status": "candidate",
                        "accepted": None,
                        "execution_status": "success",
                        "method": "codex_cli",
                        "backend": "codex_cli_repo_rag_proxy",
                        "used_baseline_fallback": False,
                    },
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    summary = materialize_training_candidates(
        tmp_path,
        output_path=Path("artifacts/trainer/generated-training.yaml"),
        summary_path=Path("artifacts/trainer/generated-training-summary.json"),
        seed_existing_output=False,
        upload_remote_state=False,
    )

    assert summary["loaded_candidate_count"] == 7
    assert summary["family_candidate_count"] == 7
    family_state_path = tmp_path / "artifacts" / "trainer" / "family-state.json"
    family_state_payload = json.loads(family_state_path.read_text(encoding="utf-8"))
    prompt_families = family_state_payload["prompt_families"]
    assert sum(int(family["family_record_count"]) for family in prompt_families) == 7
    assert all("question_variants" not in family for family in prompt_families)
    family_files = sorted((tmp_path / "artifacts" / "trainer" / "families").rglob("family.json"))
    assert family_files
    for family_file in family_files:
        family_payload = json.loads(family_file.read_text(encoding="utf-8"))
        assert int(family_payload["family_record_count"]) >= 1
    record_files = sorted((tmp_path / "artifacts" / "trainer" / "families").rglob("records/*.json"))
    assert len(record_files) == 7


def test_materialize_training_candidates_tracks_context_groups_but_materializes_one_family_champion(
    tmp_path: Path,
) -> None:
    imported_dir = tmp_path / "artifacts" / "traces" / "imported"
    imported_dir.mkdir(parents=True, exist_ok=True)
    trainer_dir = tmp_path / "artifacts" / "trainer"
    trainer_dir.mkdir(parents=True, exist_ok=True)
    (tmp_path / "README.md").write_text("# Demo\n", encoding="utf-8")
    (tmp_path / "docs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "docs" / "USAGE.md").write_text("# Usage\n", encoding="utf-8")
    question = "Continue developing this game"

    (imported_dir / "accepted.json").write_text(
        f"""{{
  "trace_record_kind": "repo-rag-trace-record",
  "trace_record_path": "artifacts/traces/imported/accepted.json",
  "question": "{question}",
  "answer": "Focus first on the core gameplay loop and wire the save system after the combat pass.",
  "sources": ["README.md"],
  "trace": {{
    "schema_version": 1,
    "trace_kind": "repo-rag-runtime",
    "recorded_at": "2026-05-02T12:00:00+00:00",
    "question": "{question}",
    "mode": "codex-proxy",
    "retrieval_mode": "hybrid-vector",
    "sources": ["README.md"],
    "source_count": 1,
    "context_count": 1,
    "context_field": "evidence_previews",
    "top_k": 4,
    "program_loaded": true,
    "mcp_candidate_count": 0,
    "answer_length": 92
  }},
  "outcome": {{
    "acceptance_status": "accepted",
    "accepted": true,
    "execution_status": "success",
    "method": "codex_cli",
    "backend": "codex_cli_repo_rag_proxy",
    "used_baseline_fallback": false
  }}
}}
""",
        encoding="utf-8",
    )
    (imported_dir / "candidate.json").write_text(
        f"""{{
  "trace_record_kind": "repo-rag-trace-record",
  "trace_record_path": "artifacts/traces/imported/candidate.json",
  "question": "{question}",
  "answer": "Document the remaining gameplay systems after the current implementation pass.",
  "sources": ["docs/USAGE.md"],
  "trace": {{
    "schema_version": 1,
    "trace_kind": "repo-rag-runtime",
    "recorded_at": "2026-05-02T12:05:00+00:00",
    "question": "{question}",
    "mode": "codex-proxy",
    "retrieval_mode": "hybrid-vector",
    "sources": ["docs/USAGE.md"],
    "source_count": 1,
    "context_count": 1,
    "context_field": "evidence_previews",
    "top_k": 4,
    "program_loaded": false,
    "mcp_candidate_count": 0,
    "answer_length": 78
  }},
  "outcome": {{
    "acceptance_status": "candidate",
    "accepted": null,
    "execution_status": "success",
    "method": "codex_cli",
    "backend": "codex_cli_repo_rag_proxy",
    "used_baseline_fallback": false
  }}
}}
""",
        encoding="utf-8",
    )

    summary = materialize_training_candidates(
        tmp_path,
        output_path=Path("artifacts/trainer/training-candidates.yaml"),
        summary_path=Path("artifacts/trainer/training-candidates-summary.json"),
    )

    assert summary["candidate_count"] == 1
    assert summary["new_candidate_count"] == 1
    assert summary["prompt_family_count"] == 1
    assert summary["context_group_count"] == 1
    assert summary["new_context_group_count"] == 1

    materialized = load_training_examples(
        tmp_path / "artifacts" / "trainer" / "training-candidates.yaml"
    )
    assert len(materialized) == 1
    assert "core gameplay loop" in materialized[0].expected_answer

    champion_index = load_family_state_payload(
        tmp_path / "artifacts" / "trainer" / "family-state.json"
    )
    assert champion_index["record_kind"] == "repo-rag-trainer-champion-index"
    assert len(champion_index["prompt_families"]) == 1
    family = champion_index["prompt_families"][0]
    assert len(family["context_groups"]) == 1
    assert family["family_champion_record"]["candidate_status"] == "accepted"


def test_materialize_training_candidates_accumulates_support_for_repeated_answer_variant(
    tmp_path: Path,
) -> None:
    imported_dir = tmp_path / "artifacts" / "traces" / "imported"
    imported_dir.mkdir(parents=True, exist_ok=True)
    question = "Continue developing this game"
    answer = "Focus first on the core gameplay loop and wire the save system after the combat pass."
    for name, recorded_at in (
        ("accepted-a.json", "2026-05-02T12:00:00+00:00"),
        ("accepted-b.json", "2026-05-02T12:05:00+00:00"),
    ):
        (imported_dir / name).write_text(
            f"""{{
  "trace_record_kind": "repo-rag-trace-record",
  "trace_record_path": "artifacts/traces/imported/{name}",
  "question": "{question}",
  "answer": "{answer}",
  "sources": ["README.md"],
  "trace": {{
    "schema_version": 1,
    "trace_kind": "repo-rag-runtime",
    "recorded_at": "{recorded_at}",
    "question": "{question}",
    "mode": "codex-proxy",
    "retrieval_mode": "hybrid-vector",
    "sources": ["README.md"],
    "source_count": 1,
    "context_count": 1,
    "context_field": "evidence_previews",
    "top_k": 4,
    "program_loaded": true,
    "mcp_candidate_count": 0,
    "answer_length": 92
  }},
  "outcome": {{
    "acceptance_status": "accepted",
    "accepted": true,
    "execution_status": "success",
    "method": "codex_cli",
    "backend": "codex_cli_repo_rag_proxy",
    "used_baseline_fallback": false
  }}
}}
""",
            encoding="utf-8",
        )

    summary = materialize_training_candidates(
        tmp_path,
        output_path=Path("artifacts/trainer/training-candidates.yaml"),
        summary_path=Path("artifacts/trainer/training-candidates-summary.json"),
    )

    assert summary["candidate_count"] == 1
    assert summary["new_candidate_count"] == 1
    assert summary["context_group_count"] == 1

    champion_index = load_family_state_payload(
        tmp_path / "artifacts" / "trainer" / "family-state.json"
    )
    family = champion_index["prompt_families"][0]
    group = family["context_groups"][0]
    assert group["trace_count"] == 2
    champion_record = group["champion_record"]
    assert champion_record["support_count"] == 2
    assert family["family_champion_record"]["support_count"] == 2


def test_materialize_training_candidates_refreshes_same_key_champion_with_richer_benchmark_context(
    tmp_path: Path,
) -> None:
    imported_dir = tmp_path / "artifacts" / "traces" / "imported"
    imported_dir.mkdir(parents=True, exist_ok=True)
    trainer_dir = tmp_path / "artifacts" / "trainer"
    trainer_dir.mkdir(parents=True, exist_ok=True)
    question = "Continue developing this game"
    answer = "Focus first on the core gameplay loop and wire the save system after the combat pass."
    legacy_trace = imported_dir / "accepted-a.json"
    richer_trace = imported_dir / "accepted-b.json"
    legacy_trace.write_text(
        f"""{{
  "trace_record_kind": "repo-rag-trace-record",
  "trace_record_path": "artifacts/traces/imported/accepted-a.json",
  "question": "{question}",
  "answer": "{answer}",
  "sources": ["README.md"],
  "trace": {{
    "schema_version": 1,
    "trace_kind": "repo-rag-runtime",
    "recorded_at": "2026-05-02T12:00:00+00:00",
    "question": "{question}",
    "mode": "codex-proxy",
    "retrieval_mode": "hybrid-vector",
    "sources": ["README.md"],
    "source_count": 1,
    "context_count": 1,
    "context_field": "evidence_previews",
    "top_k": 4,
    "program_loaded": true,
    "mcp_candidate_count": 0,
    "answer_length": 92
  }},
  "outcome": {{
    "acceptance_status": "accepted",
    "accepted": true,
    "execution_status": "success",
    "method": "codex_cli",
    "backend": "codex_cli_repo_rag_proxy",
    "used_baseline_fallback": false
  }}
}}
""",
        encoding="utf-8",
    )
    first_summary = materialize_training_candidates(
        tmp_path,
        output_path=Path("artifacts/trainer/training-candidates.yaml"),
        summary_path=Path("artifacts/trainer/training-candidates-summary.json"),
    )

    richer_trace.write_text(
        f"""{{
  "trace_record_kind": "repo-rag-trace-record",
  "trace_record_path": "artifacts/traces/imported/accepted-b.json",
  "question": "{question}",
  "answer": "{answer}",
  "sources": ["README.md"],
  "context": [
    {{
      "source": "README.md",
      "preview": "Core gameplay loop summary.",
      "text": "Core gameplay loop summary."
    }}
  ],
  "retrieved_context": [
    {{
      "source": "docs/USAGE.md",
      "preview": "Save system follows the combat pass.",
      "text": "Save system follows the combat pass."
    }}
  ],
  "trace": {{
    "schema_version": 1,
    "trace_kind": "repo-rag-runtime",
    "recorded_at": "2026-05-02T12:05:00+00:00",
    "question": "{question}",
    "mode": "codex-proxy",
    "retrieval_mode": "hybrid-vector",
    "sources": ["README.md"],
    "source_count": 1,
    "context_count": 1,
    "context_field": "evidence_previews",
    "top_k": 4,
    "program_loaded": true,
    "mcp_candidate_count": 0,
    "answer_length": 92
  }},
  "outcome": {{
    "acceptance_status": "accepted",
    "accepted": true,
    "execution_status": "success",
    "method": "codex_cli",
    "backend": "codex_cli_repo_rag_proxy",
    "used_baseline_fallback": false
  }}
}}
""",
        encoding="utf-8",
    )
    second_summary = materialize_training_candidates(
        tmp_path,
        output_path=Path("artifacts/trainer/training-candidates.yaml"),
        summary_path=Path("artifacts/trainer/training-candidates-summary.json"),
    )

    assert first_summary["new_candidate_count"] == 1
    assert second_summary["candidate_count"] == 1
    assert second_summary["new_candidate_count"] == 1
    assert second_summary["replaced_count"] == 1

    materialized = load_training_examples(trainer_dir / "training-candidates.yaml")
    assert len(materialized) == 1
    assert materialized[0].benchmark_context == (
        "Save system follows the combat pass.",
        "Core gameplay loop summary.",
    )
    assert materialized[0].benchmark_context_sources == ("docs/USAGE.md", "README.md")

    champion_index = load_family_state_payload(trainer_dir / "family-state.json")
    family = champion_index["prompt_families"][0]
    assert family["family_champion_record"]["provenance"]["trace_record_path"].endswith(
        "accepted-b.json"
    )
    assert family["family_champion_record"]["provenance"]["benchmark_context_count"] == 2


def test_materialize_training_candidates_groups_similar_prompt_variants_into_one_family(
    tmp_path: Path,
) -> None:
    imported_dir = tmp_path / "artifacts" / "traces" / "imported"
    imported_dir.mkdir(parents=True, exist_ok=True)
    prompts = (
        (
            "accepted-a.json",
            "2026-05-02T12:00:00+00:00",
            "Continue developing this game",
            "Focus first on the core gameplay loop and wire the save system after the combat pass.",
            "accepted",
            True,
            True,
        ),
        (
            "accepted-b.json",
            "2026-05-02T12:05:00+00:00",
            "Continue developing this game further",
            "Document the remaining gameplay systems after the current implementation pass.",
            "candidate",
            False,
            None,
        ),
    )
    for name, recorded_at, question, answer, acceptance_status, program_loaded, accepted in prompts:
        (imported_dir / name).write_text(
            f"""{{
  "trace_record_kind": "repo-rag-trace-record",
  "trace_record_path": "artifacts/traces/imported/{name}",
  "question": "{question}",
  "answer": "{answer}",
  "sources": ["README.md"],
  "trace": {{
    "schema_version": 1,
    "trace_kind": "repo-rag-runtime",
    "recorded_at": "{recorded_at}",
    "question": "{question}",
    "mode": "codex-proxy",
    "retrieval_mode": "hybrid-vector",
    "sources": ["README.md"],
    "source_count": 1,
    "context_count": 1,
    "context_field": "evidence_previews",
    "top_k": 4,
    "program_loaded": {str(program_loaded).lower()},
    "mcp_candidate_count": 0,
    "answer_length": {len(answer)}
  }},
  "outcome": {{
    "acceptance_status": "{acceptance_status}",
    "accepted": {json.dumps(accepted)},
    "execution_status": "success",
    "method": "codex_cli",
    "backend": "codex_cli_repo_rag_proxy",
    "used_baseline_fallback": false
  }}
}}
""",
            encoding="utf-8",
        )

    summary = materialize_training_candidates(
        tmp_path,
        output_path=Path("artifacts/trainer/training-candidates.yaml"),
        summary_path=Path("artifacts/trainer/training-candidates-summary.json"),
    )

    assert summary["prompt_family_count"] == 1
    assert summary["new_prompt_family_count"] == 1
    champion_index = load_family_state_payload(
        tmp_path / "artifacts" / "trainer" / "family-state.json"
    )
    family = champion_index["prompt_families"][0]
    assert family["question_variant_count"] == 2
    assert sorted(family["question_variants"]) == [
        "Continue developing this game",
        "Continue developing this game further",
    ]
    assert "game" in family["family_prompt_profile_terms"]
    assert "continue" not in family["family_prompt_profile_terms"]


def test_materialize_training_candidates_splits_prompt_family_on_large_prompt_delta(
    tmp_path: Path,
) -> None:
    imported_dir = tmp_path / "artifacts" / "traces" / "imported"
    imported_dir.mkdir(parents=True, exist_ok=True)
    prompts = (
        (
            "accepted-a.json",
            "2026-05-02T12:00:00+00:00",
            "Continue developing this game",
            "Focus first on the core gameplay loop and wire the save system after the combat pass.",
        ),
        (
            "accepted-b.json",
            "2026-05-02T12:05:00+00:00",
            "Refactor the webhook dispatcher and Discord publish pipeline",
            "Separate webhook routing from batch publish orchestration and simplify retries.",
        ),
    )
    for name, recorded_at, question, answer in prompts:
        (imported_dir / name).write_text(
            f"""{{
  "trace_record_kind": "repo-rag-trace-record",
  "trace_record_path": "artifacts/traces/imported/{name}",
  "question": "{question}",
  "answer": "{answer}",
  "sources": ["README.md"],
  "trace": {{
    "schema_version": 1,
    "trace_kind": "repo-rag-runtime",
    "recorded_at": "{recorded_at}",
    "question": "{question}",
    "mode": "codex-proxy",
    "retrieval_mode": "hybrid-vector",
    "sources": ["README.md"],
    "source_count": 1,
    "context_count": 1,
    "context_field": "evidence_previews",
    "top_k": 4,
    "program_loaded": true,
    "mcp_candidate_count": 0,
    "answer_length": {len(answer)}
  }},
  "outcome": {{
    "acceptance_status": "accepted",
    "accepted": true,
    "execution_status": "success",
    "method": "codex_cli",
    "backend": "codex_cli_repo_rag_proxy",
    "used_baseline_fallback": false
  }}
}}
""",
            encoding="utf-8",
        )

    summary = materialize_training_candidates(
        tmp_path,
        output_path=Path("artifacts/trainer/training-candidates.yaml"),
        summary_path=Path("artifacts/trainer/training-candidates-summary.json"),
    )

    assert summary["prompt_family_count"] == 2
    assert summary["new_prompt_family_count"] == 2


def test_materialize_training_candidates_profile_terms_ignore_one_off_noise(
    tmp_path: Path,
) -> None:
    imported_dir = tmp_path / "artifacts" / "traces" / "imported"
    imported_dir.mkdir(parents=True, exist_ok=True)
    prompts = (
        (
            "accepted-a.json",
            "2026-05-15T12:00:00+00:00",
            (
                "Just update README with demo GIF walkthrough and describe whether it is "
                "really needed now"
            ),
            (
                "Chromium bootstrap detail for the README walkthrough GIF refresh and "
                "describe whether it is really needed now"
            ),
        ),
        (
            "accepted-b.json",
            "2026-05-15T12:05:00+00:00",
            (
                "Just refresh README demo GIF walkthrough and describe whether it is really "
                "needed now"
            ),
            (
                "Playwright dependency note for the README walkthrough GIF refresh and "
                "describe whether it is really needed now"
            ),
        ),
        (
            "accepted-c.json",
            "2026-05-15T12:10:00+00:00",
            (
                "Just adjust README walkthrough GIF in docs and describe whether it is "
                "really needed now"
            ),
            (
                "Timeout mitigation note for the README walkthrough GIF refresh and "
                "describe whether it is really needed now"
            ),
        ),
    )
    for name, recorded_at, question, reformulated_prompt in prompts:
        (imported_dir / name).write_text(
            f"""{{
  "trace_record_kind": "repo-rag-trace-record",
  "trace_record_path": "artifacts/traces/imported/{name}",
  "question": "{question}",
  "original_prompt": "{question}",
  "reformulated_prompt": "{reformulated_prompt}",
  "answer": "README walkthrough GIF updated.",
  "command_trace": [
    {{
      "type": "message",
      "role": "user",
      "text": "{reformulated_prompt}"
    }}
  ],
  "trace": {{
    "schema_version": 1,
    "trace_kind": "repo-rag-runtime",
    "recorded_at": "{recorded_at}",
    "question": "{question}",
    "original_prompt": "{question}",
    "reformulated_prompt": "{reformulated_prompt}",
    "mode": "codex-proxy",
    "retrieval_mode": "lexical",
    "sources": ["README.md"],
    "source_count": 1,
    "context_count": 1,
    "context_field": "evidence_previews",
    "mcp_candidate_count": 0,
    "answer_length": 29
  }},
  "outcome": {{
    "acceptance_status": "candidate",
    "accepted": null,
    "execution_status": "success",
    "method": "codex_cli",
    "backend": "codex_cli_repo_rag_proxy",
    "used_baseline_fallback": false
  }}
}}
""",
            encoding="utf-8",
        )

    summary = materialize_training_candidates(
        tmp_path,
        output_path=Path("artifacts/trainer/training-candidates.yaml"),
        summary_path=Path("artifacts/trainer/training-candidates-summary.json"),
    )

    assert summary["prompt_family_count"] == 1
    family_state = load_family_state_payload(
        tmp_path / "artifacts" / "trainer" / "family-state.json"
    )
    family = family_state["prompt_families"][0]
    assert family["family_prompt_profile_term_stats"]["readme"]["count"] >= 3
    assert family["family_prompt_profile_term_stats"]["gif"]["count"] >= 3
    assert family["family_prompt_profile_term_stats"]["walkthrough"]["count"] >= 3
    assert family["family_prompt_profile_term_stats"]["chromium"]["count"] >= 1
    assert family["family_prompt_profile_term_stats"]["playwright"]["count"] >= 1
    assert family["family_prompt_profile_term_stats"]["timeout"]["count"] >= 1
    assert 0.0 < family["family_prompt_profile_term_stats"]["readme"]["weight"] <= 1.0
    assert 0.0 < family["family_prompt_profile_term_stats"]["gif"]["weight"] <= 1.0
    assert len(family["family_prompt_profile_terms"]) <= 12
    assert "readme" in family["family_prompt_profile_terms"]
    assert "gif" in family["family_prompt_profile_terms"]
    assert "walkthrough" in family["family_prompt_profile_terms"]
    assert "just" not in family["family_prompt_profile_terms"]
    assert "describe" not in family["family_prompt_profile_terms"]
    assert "whether" not in family["family_prompt_profile_terms"]
    assert "really" not in family["family_prompt_profile_terms"]
    assert "needed" not in family["family_prompt_profile_terms"]
    assert "chromium" not in family["family_prompt_profile_terms"]
    assert "playwright" not in family["family_prompt_profile_terms"]
    assert "timeout" not in family["family_prompt_profile_terms"]


def test_materialize_training_candidates_prefers_technical_terms_in_active_summary(
    tmp_path: Path,
) -> None:
    imported_dir = tmp_path / "artifacts" / "traces" / "imported"
    imported_dir.mkdir(parents=True, exist_ok=True)
    prompts = (
        (
            "accepted-a.json",
            "2026-05-16T09:00:00+00:00",
            (
                "I reached the decision point: the repo already contains the requested GIF, "
                "README embed, and the recorder script, and the worktree is clean."
            ),
        ),
        (
            "accepted-b.json",
            "2026-05-16T09:05:00+00:00",
            (
                "The repo already contains the GIF and README embed, so I am checking the "
                "recorder script and current worktree before the final handoff."
            ),
        ),
        (
            "accepted-c.json",
            "2026-05-16T09:10:00+00:00",
            (
                "Before the final handoff I am confirming the existing README, GIF asset, "
                "recorder script, git state, and worktree contents."
            ),
        ),
    )
    for name, recorded_at, question in prompts:
        (imported_dir / name).write_text(
            f"""{{
  "trace_record_kind": "repo-rag-trace-record",
  "trace_record_path": "artifacts/traces/imported/{name}",
  "question": "{question}",
  "original_prompt": "{question}",
  "reformulated_prompt": "{question}",
  "answer": "Validation completed.",
  "command_trace": [
    {{
      "type": "message",
      "role": "user",
      "text": "{question}"
    }}
  ],
  "trace": {{
    "schema_version": 1,
    "trace_kind": "repo-rag-runtime",
    "recorded_at": "{recorded_at}",
    "question": "{question}",
    "original_prompt": "{question}",
    "reformulated_prompt": "{question}",
    "mode": "codex-proxy",
    "retrieval_mode": "lexical",
    "sources": ["README.md"],
    "source_count": 1,
    "context_count": 1,
    "context_field": "evidence_previews",
    "mcp_candidate_count": 0,
    "answer_length": 22
  }},
  "outcome": {{
    "acceptance_status": "candidate",
    "accepted": null,
    "execution_status": "success",
    "method": "codex_cli",
    "backend": "codex_cli_repo_rag_proxy",
    "used_baseline_fallback": false
  }}
}}
""",
            encoding="utf-8",
        )

    materialize_training_candidates(
        tmp_path,
        output_path=Path("artifacts/trainer/training-candidates.yaml"),
        summary_path=Path("artifacts/trainer/training-candidates-summary.json"),
    )

    family_state = load_family_state_payload(
        tmp_path / "artifacts" / "trainer" / "family-state.json"
    )
    family = family_state["prompt_families"][0]
    terms = family["family_prompt_profile_terms"]
    assert "gif" in terms
    assert "readme" in terms
    assert "recorder" in terms
    assert "script" in terms
    assert "repo" in terms
    assert "worktree" in terms
    assert len(terms) <= 12
    assert "already" not in terms
    assert "before" not in terms
    assert "contains" not in terms
    assert "decision" not in terms
    assert "does" not in terms
    assert "fields" not in terms
    assert "final" not in terms


def test_materialize_training_candidates_keeps_gradual_source_drift_in_one_context_group(
    tmp_path: Path,
) -> None:
    imported_dir = tmp_path / "artifacts" / "traces" / "imported"
    imported_dir.mkdir(parents=True, exist_ok=True)
    question = "Continue developing this game"
    answer = "Focus first on the core gameplay loop and wire the save system after the combat pass."
    traces = (
        ("accepted-a.json", "2026-05-02T12:00:00+00:00", ["README.md"], 1),
        ("accepted-b.json", "2026-05-02T12:05:00+00:00", ["README.md", "docs/USAGE.md"], 2),
        ("accepted-c.json", "2026-05-02T12:10:00+00:00", ["docs/USAGE.md"], 1),
    )
    for name, recorded_at, sources, context_count in traces:
        sources_json = json.dumps(sources)
        (imported_dir / name).write_text(
            f"""{{
  "trace_record_kind": "repo-rag-trace-record",
  "trace_record_path": "artifacts/traces/imported/{name}",
  "question": "{question}",
  "answer": "{answer}",
  "sources": {sources_json},
  "trace": {{
    "schema_version": 1,
    "trace_kind": "repo-rag-runtime",
    "recorded_at": "{recorded_at}",
    "question": "{question}",
    "mode": "codex-proxy",
    "retrieval_mode": "hybrid-vector",
    "sources": {sources_json},
    "source_count": {len(sources)},
    "context_count": {context_count},
    "context_field": "evidence_previews",
    "top_k": 4,
    "program_loaded": true,
    "mcp_candidate_count": 0,
    "answer_length": 92
  }},
  "outcome": {{
    "acceptance_status": "accepted",
    "accepted": true,
    "execution_status": "success",
    "method": "codex_cli",
    "backend": "codex_cli_repo_rag_proxy",
    "used_baseline_fallback": false
  }}
}}
""",
            encoding="utf-8",
        )

    summary = materialize_training_candidates(
        tmp_path,
        output_path=Path("artifacts/trainer/training-candidates.yaml"),
        summary_path=Path("artifacts/trainer/training-candidates-summary.json"),
    )

    assert summary["candidate_count"] == 1
    assert summary["context_group_count"] == 1

    champion_index = load_family_state_payload(
        tmp_path / "artifacts" / "trainer" / "family-state.json"
    )
    family = champion_index["prompt_families"][0]
    group = family["context_groups"][0]
    assert group["trace_count"] == 3
    assert group["sources"] == ["README.md", "docs/USAGE.md"]
    assert group["source_count"] == 2
    assert group["context_count"] == 2


def test_materialize_training_candidates_splits_same_sources_when_evidence_fingerprints_diverge(
    tmp_path: Path,
) -> None:
    imported_dir = tmp_path / "artifacts" / "traces" / "imported"
    imported_dir.mkdir(parents=True, exist_ok=True)
    question = "Continue developing this game"

    first_trace = {
        "trace_record_kind": "repo-rag-trace-record",
        "trace_record_path": "artifacts/traces/imported/accepted-a.json",
        "question": question,
        "answer": "Prioritize combat and progression balancing first.",
        "sources": ["README.md"],
        "context": [
            {
                "source": "README.md",
                "preview": "Combat loop, saving, and progression priorities.",
                "text": "Combat loop, saving, and progression priorities.",
            }
        ],
        "trace": {
            "schema_version": 1,
            "trace_kind": "repo-rag-runtime",
            "recorded_at": "2026-05-02T12:00:00+00:00",
            "question": question,
            "mode": "codex-proxy",
            "retrieval_mode": "hybrid-vector",
            "sources": ["README.md"],
            "source_count": 1,
            "context_count": 1,
            "context_field": "context",
            "top_k": 4,
            "program_loaded": True,
            "mcp_candidate_count": 0,
            "answer_length": 49,
        },
        "outcome": {
            "acceptance_status": "accepted",
            "accepted": True,
            "execution_status": "success",
            "method": "codex_cli",
            "backend": "codex_cli_repo_rag_proxy",
            "used_baseline_fallback": False,
        },
    }
    second_trace = {
        "trace_record_kind": "repo-rag-trace-record",
        "trace_record_path": "artifacts/traces/imported/accepted-b.json",
        "question": question,
        "answer": "Prioritize localization and UI documentation first.",
        "sources": ["README.md"],
        "context": [
            {
                "source": "README.md",
                "preview": "Localization checklist, UI docs, and menu polish.",
                "text": "Localization checklist, UI docs, and menu polish.",
            }
        ],
        "trace": {
            "schema_version": 1,
            "trace_kind": "repo-rag-runtime",
            "recorded_at": "2026-05-02T12:05:00+00:00",
            "question": question,
            "mode": "codex-proxy",
            "retrieval_mode": "hybrid-vector",
            "sources": ["README.md"],
            "source_count": 1,
            "context_count": 1,
            "context_field": "context",
            "top_k": 4,
            "program_loaded": True,
            "mcp_candidate_count": 0,
            "answer_length": 52,
        },
        "outcome": {
            "acceptance_status": "candidate",
            "accepted": None,
            "execution_status": "success",
            "method": "codex_cli",
            "backend": "codex_cli_repo_rag_proxy",
            "used_baseline_fallback": False,
        },
    }
    (imported_dir / "accepted-a.json").write_text(json.dumps(first_trace), encoding="utf-8")
    (imported_dir / "accepted-b.json").write_text(json.dumps(second_trace), encoding="utf-8")

    summary = materialize_training_candidates(
        tmp_path,
        output_path=Path("artifacts/trainer/training-candidates.yaml"),
        summary_path=Path("artifacts/trainer/training-candidates-summary.json"),
    )

    assert summary["candidate_count"] == 1
    assert summary["context_group_count"] == 1

    champion_index = load_family_state_payload(
        tmp_path / "artifacts" / "trainer" / "family-state.json"
    )
    family = champion_index["prompt_families"][0]
    assert len(family["context_groups"]) == 1


def test_materialize_training_candidates_keeps_family_champion_on_small_score_edge(
    tmp_path: Path,
) -> None:
    imported_dir = tmp_path / "artifacts" / "traces" / "imported"
    imported_dir.mkdir(parents=True, exist_ok=True)
    question = "Continue developing this game"
    supported_answer = "A" * 320
    slight_better_answer = "B" * 400

    for name, recorded_at in (
        ("supported-a.json", "2026-05-02T12:00:00+00:00"),
        ("supported-b.json", "2026-05-02T12:05:00+00:00"),
    ):
        (imported_dir / name).write_text(
            f"""{{
  "trace_record_kind": "repo-rag-trace-record",
  "trace_record_path": "artifacts/traces/imported/{name}",
  "question": "{question}",
  "answer": "{supported_answer}",
  "sources": ["README.md"],
  "trace": {{
    "schema_version": 1,
    "trace_kind": "repo-rag-runtime",
    "recorded_at": "{recorded_at}",
    "question": "{question}",
    "mode": "codex-proxy",
    "retrieval_mode": "hybrid-vector",
    "sources": ["README.md"],
    "source_count": 1,
    "context_count": 1,
    "context_field": "evidence_previews",
    "top_k": 4,
    "program_loaded": true,
    "mcp_candidate_count": 0,
    "answer_length": 320
  }},
  "outcome": {{
    "acceptance_status": "accepted",
    "accepted": true,
    "execution_status": "success",
    "method": "codex_cli",
    "backend": "codex_cli_repo_rag_proxy",
    "used_baseline_fallback": false
  }}
}}
""",
            encoding="utf-8",
        )

    (imported_dir / "challenger.json").write_text(
        f"""{{
  "trace_record_kind": "repo-rag-trace-record",
  "trace_record_path": "artifacts/traces/imported/challenger.json",
  "question": "{question}",
  "answer": "{slight_better_answer}",
  "sources": ["docs/USAGE.md"],
  "trace": {{
    "schema_version": 1,
    "trace_kind": "repo-rag-runtime",
    "recorded_at": "2026-05-02T12:10:00+00:00",
    "question": "{question}",
    "mode": "codex-proxy",
    "retrieval_mode": "hybrid-vector",
    "sources": ["docs/USAGE.md"],
    "source_count": 1,
    "context_count": 1,
    "context_field": "evidence_previews",
    "top_k": 4,
    "program_loaded": true,
    "mcp_candidate_count": 0,
    "answer_length": 400
  }},
  "outcome": {{
    "acceptance_status": "accepted",
    "accepted": true,
    "execution_status": "success",
    "method": "codex_cli",
    "backend": "codex_cli_repo_rag_proxy",
    "used_baseline_fallback": false
  }}
}}
""",
        encoding="utf-8",
    )

    summary = materialize_training_candidates(
        tmp_path,
        output_path=Path("artifacts/trainer/training-candidates.yaml"),
        summary_path=Path("artifacts/trainer/training-candidates-summary.json"),
    )

    assert summary["candidate_count"] == 1
    assert summary["context_group_count"] == 1

    champion_index = load_family_state_payload(
        tmp_path / "artifacts" / "trainer" / "family-state.json"
    )
    family = champion_index["prompt_families"][0]
    assert family["family_champion_record"]["expected_answer"] == supported_answer
    assert family["family_champion_record"]["support_count"] == 2


def test_materialize_combined_training_examples_dedupes_questions_and_strips_legacy_worker_sources(
    tmp_path: Path,
) -> None:
    (tmp_path / "README.md").write_text("# Demo\n", encoding="utf-8")
    base_training_path = tmp_path / "samples" / "training" / "base.yaml"
    base_training_path.parent.mkdir(parents=True, exist_ok=True)
    base_training_path.write_text(
        (
            '- question: "What does this repository research?"\n'
            '  expected_answer: "Base answer."\n'
            '  tags: ["repo"]\n'
            "  expected_sources:\n"
            '    - "README.md"\n'
            '- question: "Where are logs stored?"\n'
            '  expected_answer: "samples/logs"\n'
            '  tags: ["logs"]\n'
        ),
        encoding="utf-8",
    )

    candidates_path = tmp_path / "artifacts" / "trainer" / "training-candidates.yaml"
    candidates_path.parent.mkdir(parents=True, exist_ok=True)
    candidates_path.write_text(
        (
            '- question: "What does this repository research?"\n'
            '  expected_answer: "Legacy worker answer."\n'
            '  tags: ["trainer-candidate", "candidate"]\n'
            "  expected_sources:\n"
            '    - "prompt_artifacts/prompts_shards_of_lokar_game-p00000-355cca.txt"\n'
            '- question: "What does this repository research?"\n'
            '  expected_answer: "Fresh worker answer."\n'
            '  tags: ["trainer-candidate", "candidate"]\n'
            "  expected_sources:\n"
            '    - "docs/USAGE.md"\n'
        ),
        encoding="utf-8",
    )

    combined_summary = materialize_combined_training_examples(
        tmp_path,
        base_training_path=Path("samples/training/base.yaml"),
        candidates_path=Path("artifacts/trainer/training-candidates.yaml"),
        output_path=Path("artifacts/trainer/generated-training.yaml"),
        summary_path=Path("artifacts/trainer/generated-training-summary.json"),
    )

    assert combined_summary["base_example_count"] == 2
    assert combined_summary["candidate_example_count"] == 2
    assert combined_summary["combined_example_count"] == 2
    assert combined_summary["new_candidate_count"] == 0
    assert combined_summary["duplicate_candidate_count"] == 0
    assert combined_summary["replaced_candidate_count"] == 2

    combined_examples = load_training_examples(
        tmp_path / "artifacts" / "trainer" / "generated-training.yaml"
    )
    assert len(combined_examples) == 2
    first_example = combined_examples[0]
    assert first_example.question == "What does this repository research?"
    assert first_example.expected_answer == "Fresh worker answer."
    assert first_example.expected_sources == ()
    assert validate_training_examples(combined_examples, root=tmp_path) == []


def test_materialize_combined_training_examples_keeps_trainer_candidates_without_benchmark_gate(
    tmp_path: Path,
) -> None:
    base_training_path = tmp_path / "samples" / "training" / "base.yaml"
    base_training_path.parent.mkdir(parents=True, exist_ok=True)
    base_training_path.write_text(
        (
            '- question: "What does this repository research?"\n'
            '  expected_answer: "It researches repository-grounded RAG over repository files."\n'
            '  tags: ["repo", "rag"]\n'
            "  expected_sources:\n"
            '    - "README.md"\n'
        ),
        encoding="utf-8",
    )

    candidates_path = tmp_path / "artifacts" / "trainer" / "training-candidates.yaml"
    candidates_path.parent.mkdir(parents=True, exist_ok=True)
    candidates_path.write_text(
        (
            '- question: "Add a demo GIF to README"\n'
            '  expected_answer: "The GIF is already present and the git worktree is clean."\n'
            '  tags: ["trainer-candidate", "candidate"]\n'
            "  benchmark_context:\n"
            '    - "# national-debt-relief ## Demo '
            '![Automated demo walkthrough](docs/assets/national-debt-relief-demo.gif)"\n'
            "  benchmark_context_sources:\n"
            '    - "README.md"\n'
        ),
        encoding="utf-8",
    )

    combined_summary = materialize_combined_training_examples(
        tmp_path,
        base_training_path=Path("samples/training/base.yaml"),
        candidates_path=Path("artifacts/trainer/training-candidates.yaml"),
        output_path=Path("artifacts/trainer/generated-training.yaml"),
        summary_path=Path("artifacts/trainer/generated-training-summary.json"),
    )

    assert combined_summary["candidate_example_count"] == 1
    assert combined_summary["skipped_unsupported_candidate_count"] == 0
    assert combined_summary["combined_example_count"] == 2
