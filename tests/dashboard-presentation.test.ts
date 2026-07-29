import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

describe("dashboard presentation contract", () => {
  it("keeps table column headings in normal title case", () => {
    const styles = readFileSync(resolve(process.cwd(), "src/styles.css"), "utf8");

    expect(styles).toMatch(/th\s*\{[^}]*text-transform:\s*none;/s);
  });

  it("pairs the activity timeline with counterparties and keeps token activity full width", () => {
    const styles = readFileSync(resolve(process.cwd(), "src/styles.css"), "utf8");

    expect(styles).toMatch(
      /\.workspace\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1\.55fr\)\s*minmax\(450px,\s*1fr\);/s,
    );
    expect(styles).toMatch(/\.tokenActivityPanel\s*\{[^}]*grid-column:\s*1\s*\/\s*-1;/s);
  });

  it("fits every token-activity column on normal desktop widths", () => {
    const styles = readFileSync(resolve(process.cwd(), "src/styles.css"), "utf8");

    expect(styles).toMatch(/\.tokenActivityTable\s*\{[^}]*table-layout:\s*fixed;/s);
    expect(styles).toMatch(
      /@media \(max-width:\s*860px\)[\s\S]*?\.tokenActivityTable\s*\{[^}]*min-width:\s*820px;/s,
    );
  });
});
