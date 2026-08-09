#!/usr/bin/env bun

import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const RUNTIME_ENV_PATH = resolve(ROOT, ".runtime", "docker.env");
const ADDRESS_PATTERN = /^0x[0-9a-fA-F]{40}$/;
const ENS_PATTERN = /^(?=.{3,255}$)(?![.-])[a-z0-9-]+(?:\.[a-z0-9-]+)*\.eth$/i;
const DEFAULT_PORT = 5173;
const USER_ENV_PATH = resolve(ROOT, ".env");

export type ScanJobPayload = {
  job_id: string;
  wallet_address: string;
  wallet_label: string;
  status: "queued" | "running" | "completed" | "failed";
  progress: number;
  error: string | null;
};

export function normalizeInitialWallet(value: string | undefined): string {
  const normalized = value?.trim() ?? "";
  if (ADDRESS_PATTERN.test(normalized)) return normalized.toLowerCase();
  if (ENS_PATTERN.test(normalized)) return normalized.toLowerCase();
  throw new Error("Provide one Ethereum address or ENS name: bun run app:up -- <wallet>");
}

export function appPort(environment: NodeJS.ProcessEnv = process.env): number {
  const value = environment.EVM_WALLET_APP_PORT?.trim();
  if (!value) return DEFAULT_PORT;
  const port = Number(value);
  if (!Number.isInteger(port) || port < 1024 || port > 65535) {
    throw new Error("EVM_WALLET_APP_PORT must be an integer between 1024 and 65535");
  }
  return port;
}

export function parseEnvironmentFile(content: string): Record<string, string> {
  return Object.fromEntries(content.split(/\r?\n/).flatMap((line) => {
    const normalized = line.trim();
    if (!normalized || normalized.startsWith("#")) return [];
    const assignment = normalized.startsWith("export ")
      ? normalized.slice("export ".length)
      : normalized;
    const separator = assignment.indexOf("=");
    if (separator < 1) return [];
    const key = assignment.slice(0, separator).trim();
    let value = assignment.slice(separator + 1).trim();
    if (
      value.length >= 2 &&
      ((value.startsWith('"') && value.endsWith('"')) ||
        (value.startsWith("'") && value.endsWith("'")))
    ) {
      value = value.slice(1, -1);
    }
    return [[key, value]];
  }));
}

export async function readUserEnvironment(): Promise<Record<string, string>> {
  try {
    return parseEnvironmentFile(await readFile(USER_ENV_PATH, "utf8"));
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return {};
    throw error;
  }
}

function shellEnvironment(): Record<string, string> {
  return Object.fromEntries(
    Object.entries(process.env).filter((entry): entry is [string, string] => entry[1] != null),
  );
}

export function scanStage(job: Pick<ScanJobPayload, "status" | "progress">): string {
  if (job.status === "completed") return "Complete";
  if (job.status === "failed") return "Failed";
  if (job.status === "queued") return "Queued";
  if (job.progress < 5) return "Preparing scan";
  if (job.progress < 95) return "Indexing and building analytics";
  return "Validating and publishing";
}

function requireEnvioToken(environment: NodeJS.ProcessEnv = process.env): void {
  const token = environment.ENVIO_API_TOKEN?.trim();
  if (!token) {
    throw new Error(
      "ENVIO_API_TOKEN is required. Copy .env.example to .env and add a token from https://envio.dev/app/api-tokens",
    );
  }
}

export async function readRuntimeEnvironment(): Promise<Record<string, string>> {
  try {
    const content = await readFile(RUNTIME_ENV_PATH, "utf8");
    return Object.fromEntries(content.split(/\r?\n/).flatMap((line) => {
      const separator = line.indexOf("=");
      return separator > 0 ? [[line.slice(0, separator), line.slice(separator + 1)]] : [];
    }));
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return {};
    throw error;
  }
}

async function persistDefaultWallet(walletAddress: string): Promise<void> {
  await mkdir(dirname(RUNTIME_ENV_PATH), { recursive: true });
  await writeFile(RUNTIME_ENV_PATH, `EVM_WALLET_SCAN_ADDRESS=${walletAddress}\n`, { mode: 0o600 });
}

async function compose(
  arguments_: string[],
  runtime: Record<string, string>,
  options: { quiet?: boolean } = {},
): Promise<void> {
  const processHandle = Bun.spawn(["docker", "compose", ...arguments_], {
    cwd: ROOT,
    env: { ...process.env, ...runtime },
    stdout: options.quiet ? "ignore" : "inherit",
    stderr: "inherit",
  });
  const exitCode = await processHandle.exited;
  if (exitCode !== 0) throw new Error(`docker compose ${arguments_.join(" ")} failed`);
}

async function fetchJson<T>(url: string, init?: RequestInit): Promise<{ response: Response; payload: T | null }> {
  const response = await fetch(url, init);
  const payload = await response.json().catch(() => null) as T | null;
  return { response, payload };
}

async function waitForLiveness(baseUrl: string, timeoutMs = 180_000): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(`${baseUrl}/api/v1/health/live`);
      if (response.ok) return;
    } catch {
      // The web proxy is still starting.
    }
    await Bun.sleep(1_000);
  }
  throw new Error("The container stack did not become live within three minutes");
}

async function createInitialScan(baseUrl: string, wallet: string): Promise<ScanJobPayload> {
  const { response, payload } = await fetchJson<ScanJobPayload & { detail?: string }>(
    `${baseUrl}/api/v1/scan-jobs`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ wallet }),
    },
  );
  if (!response.ok || !payload) {
    const detail = payload?.detail ?? `HTTP ${response.status}`;
    const current = detail.match(/Wallet (0x[0-9a-f]{40}) is already scanned/);
    if (current) {
      return {
        job_id: "already-current",
        wallet_address: current[1],
        wallet_label: wallet,
        status: "completed",
        progress: 100,
        error: null,
      };
    }
    throw new Error(`Could not start the initial wallet scan: ${detail}`);
  }
  return payload;
}

async function waitForScan(baseUrl: string, initial: ScanJobPayload): Promise<ScanJobPayload> {
  if (initial.status === "completed") return initial;
  let previousStage = "";
  let current = initial;
  while (current.status === "queued" || current.status === "running") {
    const stage = scanStage(current);
    if (stage !== previousStage) {
      console.log(`  ${stage}`);
      previousStage = stage;
    }
    await Bun.sleep(1_500);
    const result = await fetchJson<ScanJobPayload>(
      `${baseUrl}/api/v1/scan-jobs/${encodeURIComponent(current.job_id)}`,
    );
    if (!result.response.ok || !result.payload) {
      throw new Error("Could not monitor the initial wallet scan");
    }
    current = result.payload;
  }
  if (current.status === "failed") {
    throw new Error(`Initial wallet scan failed: ${current.error ?? "unknown worker error"}`);
  }
  console.log("  Complete");
  return current;
}

async function up(walletInput: string): Promise<void> {
  const userEnvironment = await readUserEnvironment();
  const environment = { ...userEnvironment, ...shellEnvironment() };
  requireEnvioToken(environment);
  const wallet = normalizeInitialWallet(walletInput);
  const port = appPort(environment);
  const baseUrl = `http://127.0.0.1:${port}`;
  const saved = await readRuntimeEnvironment();
  const runtime = {
    ...userEnvironment,
    ...shellEnvironment(),
    ...saved,
    ...(ADDRESS_PATTERN.test(wallet) ? { EVM_WALLET_SCAN_ADDRESS: wallet } : {}),
  };

  console.log("Building and starting the live application...");
  await compose(["up", "--build", "--detach", "postgres", "app", "web"], runtime);
  await waitForLiveness(baseUrl);
  console.log(`Scanning ${wallet} through the Ethereum finalized head...`);
  const completed = await waitForScan(baseUrl, await createInitialScan(baseUrl, wallet));
  await persistDefaultWallet(completed.wallet_address);

  if (runtime.EVM_WALLET_SCAN_ADDRESS !== completed.wallet_address) {
    await compose(
      ["up", "--detach", "--no-deps", "--force-recreate", "app"],
      { ...runtime, EVM_WALLET_SCAN_ADDRESS: completed.wallet_address },
      { quiet: true },
    );
    await waitForLiveness(baseUrl);
  }
  console.log(`\nLive dashboard ready: ${baseUrl}`);
}

async function main(): Promise<void> {
  const [command = "", argument] = process.argv.slice(2);
  const runtime = await readRuntimeEnvironment();
  switch (command) {
    case "up":
      await up(argument);
      return;
    case "down":
      await compose(["down"], runtime);
      return;
    case "status":
      await compose(["ps"], runtime);
      return;
    case "logs":
      await compose(["logs", "--follow", "app", "web", "postgres"], runtime);
      return;
    case "check":
      {
        const userEnvironment = await readUserEnvironment();
        const environment = { ...userEnvironment, ...shellEnvironment() };
        requireEnvioToken(environment);
        await compose(["config", "--quiet"], { ...environment, ...runtime });
      }
      return;
    default:
      throw new Error("Use one of: app:up, app:down, app:status, app:logs, app:check");
  }
}

if (import.meta.main) {
  main().catch((error: unknown) => {
    console.error(error instanceof Error ? error.message : String(error));
    process.exitCode = 1;
  });
}
