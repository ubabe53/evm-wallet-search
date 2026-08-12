#!/usr/bin/env bun

import {
  appPort,
  compose,
  readRuntimeEnvironment,
  readUserEnvironment,
  waitForLiveness,
} from "./local_stack";

export function requireExplicitRpc(environment: NodeJS.ProcessEnv): void {
  if (!environment.ETHEREUM_RPC_URL?.trim()) {
    throw new Error(
      "ETHEREUM_RPC_URL is required for app:enrich because counterparty evidence can require many RPC calls",
    );
  }
}

function shellEnvironment(): Record<string, string> {
  return Object.fromEntries(
    Object.entries(process.env).filter((entry): entry is [string, string] => entry[1] != null),
  );
}

async function main(): Promise<void> {
  const userEnvironment = await readUserEnvironment();
  const environment = { ...userEnvironment, ...shellEnvironment() };
  requireExplicitRpc(environment);
  const runtime = { ...environment, ...await readRuntimeEnvironment() };
  const baseUrl = `http://127.0.0.1:${appPort(environment)}`;

  console.log("Stopping the API while account evidence is refreshed...");
  await compose(["stop", "app"], runtime);
  try {
    await compose(
      ["run", "--rm", "--no-deps", "app", "python", "scripts/enrich_counterparty_types.py"],
      runtime,
    );
    await compose(
      ["run", "--rm", "--no-deps", "app", "python", "scripts/rebuild_live_enrichment.py"],
      runtime,
    );
  } finally {
    await compose(["up", "--detach", "--no-deps", "app"], runtime);
    await waitForLiveness(baseUrl);
  }
  console.log(`Account evidence published: ${baseUrl}`);
}

if (import.meta.main) {
  main().catch((error: unknown) => {
    console.error(error instanceof Error ? error.message : String(error));
    process.exitCode = 1;
  });
}
