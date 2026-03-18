# GitHub Actions Summary

- Recorded at: `2026-03-18T09:41:20Z`
- Repository head after repair push: `9e2e49f56541a3cf7e67de875bc0a2884adc183e`
- Branch: `master`

## Relevant Runs

### Feature push: DSPy artifact reuse and live Azure proof

- Commit: `9cf65a23831da40a059ba7ca2cbe94c5e16f4274`
- `CI` run `23237682794`: `failure`
- `Publication PDF` run `23237682668`: `success`

`CI` job results for `23237682794`:

- `Python Quality, Tests, And Build` job `67545675437`: `success`
- `Rust Wrapper` job `67545675483`: `failure`

Failure cause from the `Rust Wrapper` log:

- `cargo fmt --manifest-path rust-cli/Cargo.toml --check` reported formatting drift in
  `rust-cli/src/main.rs`

`Publication PDF` results for `23237682668`:

- `Build Publication PDF` job `67545675022`: `success`

### Repair push: Rust wrapper format and lint fix

- Commit: `9e2e49f56541a3cf7e67de875bc0a2884adc183e`
- `CI` run `23238335051`: `success`

`CI` job results for `23238335051`:

- `Rust Wrapper` job `67547949172`: `success`
- `Python Quality, Tests, And Build` job `67547949215`: `success`

## Notes

- No new `Publication PDF` run was triggered for the repair push, which is expected because the
  follow-up commit only touched `rust-cli/src/main.rs` plus regenerated file summaries.
- Both the failed and successful CI runs emitted GitHub-hosted runner warnings about Node.js 20
  action deprecation for some marketplace actions. Those warnings did not block the repaired run.
