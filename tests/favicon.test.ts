import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

describe("dashboard favicon contract", () => {
  it("declares the local SVG favicon in the Vite HTML shell", () => {
    const html = readFileSync(resolve(process.cwd(), "index.html"), "utf8");

    expect(html).toMatch(/<link\s+rel="icon"\s+href="%BASE_URL%favicon\.svg"\s+type="image\/svg\+xml"\s*\/>/);
    expect(html).not.toMatch(/https?:\/\//);
  });

  it("keeps the mark square, compact, and high contrast", () => {
    const svg = readFileSync(resolve(process.cwd(), "public/favicon.svg"), "utf8");

    expect(svg).toMatch(/viewBox="0 0 64 64"/);
    expect(svg).toContain('fill="#101722"');
    expect(svg).toContain('stroke="#f0f6fc"');
    expect(svg).toContain('fill="#4ade80"');
    expect(svg).not.toMatch(/<image\b|(?:href|xlink:href)="https?:\/\//);
  });
});
