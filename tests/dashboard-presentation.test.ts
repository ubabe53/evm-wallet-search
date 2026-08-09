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

  it("keeps token and counterparty rankings free of horizontal scrolling", () => {
    const styles = readFileSync(resolve(process.cwd(), "src/styles.css"), "utf8");

    expect(styles).toMatch(/\.tokenActivityTable\s*\{[^}]*table-layout:\s*fixed;/s);
    expect(styles).toMatch(
      /\.tokenTableScroll\s*\{[^}]*overflow-x:\s*hidden;[^}]*overflow-y:\s*auto;/s,
    );
    expect(styles).toMatch(
      /\.counterpartyTableScroll\s*\{[^}]*overflow-x:\s*hidden;[^}]*overflow-y:\s*auto;/s,
    );
    expect(styles).not.toMatch(/\.tokenActivityTable\s*\{[^}]*min-width:/s);
    expect(styles).not.toMatch(/\.counterpartyTable\s*\{[^}]*min-width:/s);
  });

  it("uses responsive ranking cards and themed vertical scrollbars", () => {
    const styles = readFileSync(resolve(process.cwd(), "src/styles.css"), "utf8");

    expect(styles).toMatch(
      /@media \(max-width:\s*860px\)[\s\S]*?\.tokenActivityTable tr,[\s\S]*?\.counterpartyTable tr\s*\{[^}]*display:\s*grid;/s,
    );
    expect(styles).toMatch(
      /\.tokenTableScroll::-webkit-scrollbar-thumb,[\s\S]*?\.counterpartyTableScroll::-webkit-scrollbar-thumb\s*\{[^}]*border-radius:\s*999px;/s,
    );
  });
});
