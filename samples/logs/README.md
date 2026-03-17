# GitHub Run Logs

Store post-push GitHub Actions inspection logs in this directory.

## Required Flow

1. Push the commit.
2. Inspect recent runs with `gh run list --limit 10`.
3. Save the relevant `gh run view` output in a timestamped file here.
4. Record whether the `CI` and `Publish` workflows passed for the pushed revision.
