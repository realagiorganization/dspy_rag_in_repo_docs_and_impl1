# GitHub Actions Run Log

- Logged at: `2026-03-17T09:22:51Z`
- Branch: `master`
- HEAD: `a9f0cee9f57ca1f7faefa9a619b5d3351a3aff24`

## Latest Runs

- Workflow: `CI`
  - Run ID: `23187167912`
  - Title: `Store publication assets directly for "develop a subfolder that is la...`
  - Status: `completed`
  - Conclusion: `success`
  - URL: <https://github.com/realagiorganization/dspy_rag_in_repo_docs_and_impl1/actions/runs/23187167912>
- Workflow: `Publication PDF`
  - Run ID: `23187167908`
  - Title: `Store publication assets directly for "develop a subfolder that is la...`
  - Status: `completed`
  - Conclusion: `success`
  - URL: <https://github.com/realagiorganization/dspy_rag_in_repo_docs_and_impl1/actions/runs/23187167908>

## Jobs

- `Python Quality, Tests, And Build`: success in `59s`, job URL <https://github.com/realagiorganization/dspy_rag_in_repo_docs_and_impl1/actions/runs/23187167912/job/67373500940>
- `Rust Wrapper`: success in `34s`, job URL <https://github.com/realagiorganization/dspy_rag_in_repo_docs_and_impl1/actions/runs/23187167912/job/67373500895>
- `Build Publication PDF`: success in `1m29s`, job URL <https://github.com/realagiorganization/dspy_rag_in_repo_docs_and_impl1/actions/runs/23187167908/job/67373500905>

## Notes

- The earlier `Publication PDF` run `23186781134` failed during `actions/checkout` because the first publication commit stored the PDF and banner as Git LFS pointers that were not fetchable in GitHub Actions.
- Follow-up commit `a9f0cee` removed the LFS tracking for those two publication assets, kept the stable README PDF link, and allowed the corrected publication workflow to pass.
- The main `CI` workflow still emits Node.js 20 deprecation warnings for `actions/checkout@v4`, `actions/upload-artifact@v4`, and `astral-sh/setup-uv@v6`.
