import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const readProjectFile = (path: string) => readFileSync(resolve(process.cwd(), path), "utf8");

describe("GitHub Pages fixture deployment contract", () => {
  it("keeps publication gated and rebuilds only the static fixture path", () => {
    const workflow = readProjectFile(".github/workflows/deploy.yml");
    const fixtureBuild = workflow.indexOf("run: bun run analytics:build:fixture");
    const exportStep = workflow.indexOf("run: bun run export:dashboard");
    const dashboardBuild = workflow.indexOf("run: bun run dashboard:build");

    expect(workflow).toContain("vars.ENABLE_GITHUB_PAGES == 'true'");
    expect(workflow).toContain("github.event.workflow_run.conclusion == 'success'");
    expect(workflow).toContain("github.event.workflow_run.head_branch == 'main'");
    expect(workflow).toContain("github.ref == 'refs/heads/main'");
    expect(workflow).toContain('ref: ${{ github.event_name == \'workflow_run\' && github.event.workflow_run.head_sha || github.sha }}');
    expect(fixtureBuild).toBeGreaterThan(0);
    expect(exportStep).toBeGreaterThan(fixtureBuild);
    expect(dashboardBuild).toBeGreaterThan(exportStep);
    expect(workflow).toContain('--base "/${{ github.event.repository.name }}/"');
    expect(workflow).not.toMatch(/analytics:build:hyperindex|api:dev|ENVIO_API_TOKEN|ETHEREUM_RPC_URL/);
  });

  it("uses base-relative fixture assets and a compile-time static adapter", () => {
    const html = readProjectFile("index.html");
    const dataSource = readProjectFile("src/data.ts");
    const packageJson = JSON.parse(readProjectFile("package.json")) as {
      scripts: Record<string, string>;
    };

    expect(packageJson.scripts["dashboard:build"]).toContain("VITE_DATA_MODE=static");
    expect(html).toContain('href="%BASE_URL%favicon.svg"');
    for (const file of ["summaries", "timeline", "events", "meta"]) {
      expect(dataSource).toContain(`fetchJson<`);
      expect(dataSource).toContain(`"data/${file}.json"`);
    }
  });
});
