# Codex Exec Resume Plan

Goal: stop paying the full cold-start cost on every pipeline run by moving the worker path from
fresh `codex exec` sessions to persistent `codex exec resume` sessions backed by PVC-cached Codex
session files.

## Problem Statement

- The current worker path always starts a new `codex exec` session.
- A fresh session begins with no durable execution memory, so Codex re-reads large documentation
  and repository surfaces such as `docs/ENVS.md`, `docs/USAGE.md`, and `README.md`.
- Stateless repo-RAG helps with the initial mediation block, but it does not give Codex real
  continuity across pipeline runs.
- The repository already confirmed that `codex exec resume` exists, but the worker path does not
  use it yet.

## Non-Goals

- Do not replace the global DSPy bundle with per-repo mutable memory.
- Do not move worker execution to one infinitely growing session without reset rules.
- Do not rely on prompt-only memory tricks as the primary continuity mechanism.

## Invariants

- The global DSPy bundle remains global and immutable.
- Codex execution memory is local mutable state scoped to one repository workspace or prompt lane.
- Codex session files must survive pod turnover through PVC-backed caching and be restored into the
  exact path layout that `codex exec resume` expects.
- Codex credentials are still ephemeral runtime material: the worker must recreate `auth.json` and
  `config.toml` inside the active temp `CODEX_HOME` before both fresh `exec` and `exec resume`
  runs, because stale absolute paths from an earlier pod are not a valid auth strategy.
- Resume must be optional and revocable when the session becomes stale, too large, or mismatched to
  the current repository state.

## Phase 0: Recon and Contract

- [x] Confirm that the current worker implementation always starts `codex exec` rather than
      `codex exec resume`.
- [x] Confirm that the local Codex binary exposes `codex exec resume`.
- [x] Confirm that stateless repo-RAG mediation cannot by itself prevent Codex from re-reading
      repository files after a fresh session start.
- [x] Inspect the on-disk Codex session layout created by non-ephemeral `codex exec` runs.
- [x] Identify and implement a first minimal durable state set for resumed non-interactive
      sessions.
- [x] Identify whether session portability depends on `CODEX_HOME`, working directory, model, or
      auth profile consistency.

## Phase 1: Persistent Session State Surfaces

- [x] Define one PVC-backed Codex state root for workers.
- [x] Define one stable session namespace key, for example by repository identity plus prompt lane.
- [x] Persist a worker-visible `session-index.json` that maps lane keys to the latest observed
      Codex session hint plus restore metadata.
- [x] Persist worker-visible lane metadata beside each session:
      - working directory
      - last run timestamp
      - auth/config payload digests
      - latest observed session-file hint
      - last successful resume status
- [x] Enrich that lane metadata with repository fingerprint metadata and resolved model/profile
      summaries.
- [x] Enforce richer restore decisions from that metadata beyond working-directory plus auth/config
      digest checks.
- [x] Define a session-state artifact contract so worker logs can report whether a run used:
      - fresh exec
      - resumed exec
      - resumed-then-reset

## Phase 2: PVC Cache And Restore Path

- [x] Copy Codex session files and metadata out of the worker-local runtime directory after each
      successful run into the PVC-backed cache root.
- [x] Restore those files into the exact runtime path expected by Codex before the next worker run.
- [x] Keep the restore path deterministic so workers can prefer an explicit persisted
      `latest_session_id` and only fall back to `codex exec resume --last --all` when the
      snapshot lacks a usable session id.
- [x] Preserve only the current minimal durable Codex state needed for resume instead of copying
      unrelated temp files.
- [x] Add initial restore-compatibility guards for unreadable metadata and working-directory /
      auth-config mismatches before attempting resume.
- [x] Add a snapshot-manifest guard so partial-copy corruption falls back to reset instead of
      silently attempting resume.
- [x] Preserve `_codex_sessions` across guild-level artifact resets instead of letting the
      workflow root-wipe the entire artifacts PVC before the next worker run.
- [x] Add a deeper repo-state drift guard beyond repo-root / branch mismatch, so large repository
      drift can force a controlled reset without blocking ordinary same-branch development.
- [x] Add an explicitly parsed model/profile mismatch guard beyond config-digest checks.
- [x] Persist startup-debug continuity markers plus a dedicated restore-probe artifact so live
      runs can distinguish “worker never saw `_codex_sessions`” from “worker saw it but rejected
      it”.

## Phase 2.5: Guard, Auth, And Temp HOME Hydration

- [x] Inspect the current worker auth flow that writes ephemeral `auth.json` and `config.toml`
      into the active temp Codex home before launch.
- [x] Keep the persisted PVC session cache separate from the ephemeral temp `CODEX_HOME` used for
      the current pod.
- [x] On every fresh `exec` and every `exec resume`, restore session files first and then recreate
      the current pod's `auth.json` / `config.toml` in the active temp home.
- [x] Re-run guard preflight for resumed sessions, not only for fresh sessions, so missing
      credentials fail early instead of producing a broken Codex resume.
- [x] Ensure the resume path never depends on stale absolute file paths captured inside a previous
      pod's temporary home.
- [x] Record in worker artifacts whether the run used:
      - restored session state
      - regenerated auth/config files
      - successful guard preflight
- [x] Add a fallback rule: if session state restores but auth/config hydration or guard preflight
      fails, do not attempt resume with partial credentials.
- [x] Keep guard preflight out of the PVC-backed session lifecycle itself so `codex --version`
      verification cannot seed, reset, or overwrite a live resume lane accidentally.

## Phase 3: Worker Runner Pivot

- [x] Add a worker-side decision layer:
      - if a valid session exists, use `codex exec resume`
      - otherwise start fresh `codex exec`
- [x] Capture the latest observed session-file hint after a fresh run and write it into the
      PVC-backed session index.
- [x] Capture the latest observed session-file hint after resume and keep the index current.
- [x] Keep repo-RAG proxy mediation enabled for resumed sessions so retrieval and DSPy still supply
      fresh repository deltas instead of becoming the primary memory mechanism.
- [x] Persist enough metadata in worker artifacts to explain why a run resumed or reset.

## Phase 4: Reset, Fork, And Rotation Policy

- [x] Define a repository-drift threshold that forces reset only after sufficiently large
      repository change, not after ordinary same-branch iteration.
- [x] Reset automatically for broken or unreadable session files.
- [x] Reset on explicit operator request.
- [x] Reset after repeated resume failures hit the configured threshold.
- [x] Define one soft fork trigger for a divergent prompt lane and expose it through
      `DATASET_CODEX_SESSION_LANE` plus prompt metadata fields `codex_session_lane` /
      `session_lane`.
- [x] Define additional soft fork triggers:
      - automatic task-family lane derivation through
        `DATASET_CODEX_AUTO_SESSION_LANE_MODE` using stable prompt-family metadata such as
        `queue_label` and `prompt_slug`
      - broad-context prevention by splitting unrelated queue/prompt families into separate lanes
        before rollover-to-`reset` is required
- [x] Define rollover triggers for context growth:
      - token growth trend via `DATASET_CODEX_PROMPT_TOKEN_GROWTH_RESET_RATIO`
      - elapsed wall-clock age via `DATASET_CODEX_MAX_SESSION_AGE_SECONDS`
      - number of resumed runs via `DATASET_CODEX_MAX_RESUMED_RUNS`
- [x] Decide when to prefer `codex exec resume` versus starting a new lane with a fresh session id:
      - explicit `DATASET_CODEX_SESSION_LANE` or prompt lane hint prefers a distinct lane and can
        fork from the base lane when no snapshot exists yet
      - compatible existing lane below rollover thresholds resumes
      - incompatibility guards or rollover thresholds force `reset` on the lane instead of resume

## Phase 5: Telemetry, Cost, And Safety Gates

- [x] Report current session mode in worker artifacts:
      - `fresh`
      - `resumed`
      - `reset`
      - `resumed-then-reset`
- [x] Add `forked` mode to worker artifacts when lane forking exists.
- [x] Report cache-restore status in worker artifacts.
- [x] Report PVC sync-health in worker artifacts.
- [x] Report token deltas between fresh and resumed runs for the same task family through
      `codex_session_state.json` lane telemetry.
- [x] Report transcript-level path/read summaries plus deltas between fresh and resumed runs so
      later AKS validation can quantify repeated file-reading reduction without manually grepping
      `codex_response.txt`.
- [x] Add guards so resume is not silently used when the restored session does not match the
      current repository lane.
- [x] Keep trainer trace export compatible with resumed sessions so downstream DSPy training still
      sees normalized outcomes, including Codex session mode/state provenance in repo-RAG
      trace/outcome payloads.

## Phase 6: Validation

- [x] Add unit coverage for session-index writing, restore-path building, and resume/fresh
      fallback decisions.
- [x] Add local worker coverage proving that a first run creates a session snapshot.
- [x] Add local worker coverage proving that a second run on the same lane restores the snapshot
      and calls `codex exec resume`.
- [x] Add local worker coverage proving that corrupted cache / manifest state falls back to
      reset/fresh exec.
- [x] Add local worker coverage proving that repo drift can trigger reset.
- [ ] Run a live AKS experiment that proves:
      - first run starts fresh
      - second run resumes
      - documentation re-reading is materially reduced
      - prompt token usage drops relative to fresh-start runs

## Success Criteria

- A second run against the same repository lane uses `codex exec resume` instead of a fresh
  `codex exec`.
- The worker restores the right Codex session files from PVC automatically.
- The resumed run materially reduces repeated repository re-reading and input-token cost.
- Repo-RAG and DSPy remain freshness/delta layers, not fake substitutes for Codex session memory.

Latest local artifact status:

- [x] A second run against the same repository lane used `codex exec resume`.
- [x] The worker restored the expected persisted lane snapshot (`restored_files = 4`).
- [x] The resumed lane materially reduced prompt-token cost versus the recorded fresh baseline
  (`2568062 -> 103760`).
- [x] Persisted lane metadata now carries a stable `mcp_contract_signature`, so MCP launch-contract
  changes can force one clean reset instead of silently reusing a stale resumed lane.
- [ ] Live Codex-side MCP transport still needs one more validation pass with the new
  `repo_rag_mcp_debug.log` instrumentation, because worker-side preflight succeeds but the
  Codex-launched child still times out before the first recorded MCP request.
