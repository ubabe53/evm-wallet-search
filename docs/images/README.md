# Dashboard images

This directory is the documentation-owned home for dashboard captures.

## Current screenshot slot

The intended overview image is `dashboard-overview.png`. It is deliberately absent today:
no checked-in screenshot currently matches the timeline, analysis-context, provenance,
recognition, account-evidence, and table contracts.

When refreshing it:

1. Run `bun run analytics:build:fixture` and `bun run export:dashboard`.
2. Start `bun run dashboard:dev:fixture`.
3. Capture the complete desktop overview with the visible fixture badge and provenance strip.
4. Verify the controls and panels against
   [dashboard behavior](../architecture.md#dashboard-behavior) and the frontend tests.
5. Add `dashboard-overview.png` here and embed it from the root README in the same commit.

This procedure makes the empty slot intentional without publishing a broken image link.
