#!/bin/sh
# Run a fresh, read-only Codex review over the staged diff before committing.
# Correctness includes material drift between executable behavior and repository context.

set -eu

if [ "${SKIP_CODEX_REVIEW:-0}" = "1" ]; then
  echo "Codex staged review skipped (SKIP_CODEX_REVIEW=1)."
  exit 0
fi

if git diff --cached --quiet --; then
  exit 0
fi

if ! command -v codex >/dev/null 2>&1; then
  echo "Codex CLI is required for the staged review. Install it or use SKIP_CODEX_REVIEW=1 once." >&2
  exit 1
fi

if ! command -v bun >/dev/null 2>&1; then
  echo "Bun is required to validate the Codex review result. Install it or use SKIP_CODEX_REVIEW=1 once." >&2
  exit 1
fi

repository_root=$(git rev-parse --show-toplevel)
schema_path="$repository_root/.codex/review-output.schema.json"
review_output=$(mktemp "${TMPDIR:-/tmp}/evm-wallet-codex-review.XXXXXX")
review_log=$(mktemp "${TMPDIR:-/tmp}/evm-wallet-codex-review-log.XXXXXX")
trap 'rm -f "$review_output" "$review_log"' EXIT HUP INT TERM

echo "Running a fresh Codex review of staged changes..."
if ! codex exec \
  --ephemeral \
  --sandbox read-only \
  -c 'approval_policy="never"' \
  -c 'model_reasoning_effort="low"' \
  --color never \
  --output-schema "$schema_path" \
  --output-last-message "$review_output" \
  - >"$review_log" 2>&1 <<'PROMPT'
Review only the changes currently staged in this Git repository (`git diff --cached`).

Act as an independent code reviewer with no prior conversation context. You may inspect tracked repository files for context, but do not modify files and do not treat unstaged or untracked changes as part of the proposed commit. Apply the review priorities in `.github/copilot-instructions.md`.

Report only concrete correctness, security, data-integrity, regression, portability, materially missing-test, or material documentation-drift problems. Do not block on formatting, personal style, speculative improvements, or pre-existing problems outside the staged change. A finding must identify a specific failure mode and the smallest relevant staged file location.

Treat repository context as part of correctness. Use `AGENTS.md` for change routing and `ARCHITECTURE.md` for system boundaries, then inspect only the relevant detailed document. When staged code or configuration changes user-visible behavior, commands, system boundaries, dependency direction, data contracts, semantic policy, setup, or operations, verify that the owning documentation is updated in the staged change and does not contradict the implementation. Also compare staged documentation claims with the relevant repository implementation and tests even when implementation files are unchanged. Report an `error` when a material code shift is undocumented, when staged documentation introduces a materially false description of existing behavior, or when staged documentation contradicts the staged implementation. Do not require documentation changes for behavior-preserving refactors, tests-only changes, or implementation details that do not alter a documented contract.

Keep this pre-commit review focused and fast: start with the staged diff, open only files directly needed to validate it, avoid broad repository searches, and run only quick targeted read-only checks.

Set `approved` to false only when at least one `error` finding should block this commit. Use `warning` for useful non-blocking observations. Return only the JSON object required by the provided output schema.
PROMPT
then
  tail -n 40 "$review_log" >&2
  echo "Codex could not complete the staged review. Retry when connected, or use SKIP_CODEX_REVIEW=1 once." >&2
  exit 1
fi

bun -e '
  const outputPath = process.argv.at(-1);
  const review = await Bun.file(outputPath).json();
  console.log(`Codex review: ${review.summary}`);
  for (const finding of review.findings) {
    const location = finding.file
      ? `${finding.file}${finding.line ? `:${finding.line}` : ""}`
      : "repository";
    console.log(`  [${finding.severity}] ${location} — ${finding.message}`);
  }
  const blocked = !review.approved || review.findings.some((finding) => finding.severity === "error");
  if (blocked) {
    console.error("Commit blocked by Codex review. Fix the errors and stage the result.");
    console.error("Emergency bypass: SKIP_CODEX_REVIEW=1 git commit ...");
    process.exit(1);
  }
  console.log("Codex staged review passed.");
' "$review_output"
