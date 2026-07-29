import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "../src/App";
import {
  INDIRECT_TRANSFER_EXPLANATION,
  SELF_TRANSFER_EXPLANATION,
} from "../src/dashboard/model";
import { dashboardEvents, metadata, summaries, timeline } from "./dashboard-fixtures";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("App", () => {
  it("renders exported dashboard data", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((path: string) => {
        const payload = path.endsWith("summaries.json")
            ? summaries
            : path.endsWith("timeline.json")
              ? timeline
              : path.endsWith("meta.json")
                ? metadata
                : dashboardEvents;

        return Promise.resolve({ ok: true, json: () => Promise.resolve(payload) });
      }),
    );

    render(<App />);

    await waitFor(() => expect(screen.getByText(
      "Transfer Event Analytics based on emitted Transfer(address,address,uint256) events.",
    )).toBeInTheDocument());
    expect(screen.getByRole("region", { name: "Analysis context" })).toHaveTextContent(
      "Analyzing0x1vitalik.ethEthereum mainnetExample wallet",
    );
    expect(screen.getByRole("link", { name: "0x1" })).toHaveAttribute(
      "href",
      "https://etherscan.io/address/0x1",
    );
    expect(screen.getByText("vitalik.eth")).toHaveAttribute(
      "title",
      "Configured project label; not a live ENS resolution.",
    );
    expect(screen.getByText("Current selection")).toBeInTheDocument();
    expect(screen.getAllByText("USDC").length).toBeGreaterThan(0);
    expect(screen.getAllByRole("link", { name: "USDC" })[0]).toHaveAttribute(
      "href",
      "https://etherscan.io/token/0x2",
    );
    expect(screen.getAllByRole("link", { name: "0x1111...1111" })[0]).toHaveAttribute(
      "href",
      "https://etherscan.io/address/0x1111111111111111111111111111111111111111",
    );
    expect(screen.getAllByText("Contract").find((element) => element.hasAttribute("title"))).toHaveAttribute(
      "title",
      "Contract bytecode observed at pinned block 22500000",
    );
    expect(screen.getAllByRole("link", { name: "View transaction on Etherscan" })[0]).toHaveAttribute(
      "href",
      "https://etherscan.io/tx/0xaaa",
    );
    expect(screen.getByText("Recent Events")).toBeInTheDocument();
    expect(screen.getByText("Top Counterparties")).toBeInTheDocument();
    expect(screen.getByText(
      "Addresses opposite the tracked wallet in Transfer events; mint/burn, self, and token contracts excluded.",
    )).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "0x111...111" })).toHaveAttribute(
      "href",
      "https://etherscan.io/address/0x1111111111111111111111111111111111111111",
    );
    const timelineHeading = screen.getByText("Activity Timeline");
    const tokenActivityHeading = screen.getByText("Token Activity");
    const counterpartyHeading = screen.getByText("Top Counterparties");
    expect(timelineHeading.compareDocumentPosition(counterpartyHeading) & Node.DOCUMENT_POSITION_FOLLOWING)
      .toBeTruthy();
    expect(counterpartyHeading.compareDocumentPosition(tokenActivityHeading) & Node.DOCUMENT_POSITION_FOLLOWING)
      .toBeTruthy();
    expect(screen.queryByText("Token Flow")).not.toBeInTheDocument();
    expect(screen.getByText(
      "One row per emitting contract across captured Transfer-signature events.",
    )).toBeInTheDocument();
    const tokenActivityPanel = tokenActivityHeading.closest(".panel") as HTMLElement;
    const tokenActivity = within(tokenActivityPanel);
    expect(tokenActivity.getByRole("columnheader", { name: "Activity" })).toBeInTheDocument();
    expect(tokenActivity.getByRole("columnheader", { name: "Direction" })).toBeInTheDocument();
    expect(tokenActivity.getByRole("columnheader", { name: "Counterparties" })).toBeInTheDocument();
    expect(tokenActivity.getByRole("columnheader", { name: "Recognition" })).toBeInTheDocument();
    expect(tokenActivity.queryByRole("columnheader", { name: "Senders | Recipients" })).not.toBeInTheDocument();
    expect(tokenActivity.queryByRole("columnheader", { name: "Indirect In / Out" })).not.toBeInTheDocument();
    expect(tokenActivity.getByText("USD Coin")).toBeInTheDocument();
    expect(tokenActivity.getByRole("link", { name: "0x2" })).toHaveAttribute(
      "href",
      "https://etherscan.io/token/0x2",
    );
    expect(tokenActivityPanel.querySelectorAll(".rankCell")[0]).toHaveTextContent("1");
    expect(tokenActivityPanel.querySelector(".tokenActivityBar span")).toHaveStyle({ width: "100%" });
    expect(tokenActivity.getAllByText("In 1").length).toBeGreaterThan(0);
    expect(tokenActivity.getByText("Indirect 1 in · 0 out")).toHaveAttribute(
      "title",
      INDIRECT_TRANSFER_EXPLANATION,
    );
    expect(tokenActivity.getAllByText("1 senders · 0 recipients").length).toBeGreaterThan(0);
    expect(screen.getAllByTitle(INDIRECT_TRANSFER_EXPLANATION).length).toBeGreaterThanOrEqual(2);
    expect(screen.getAllByText("in*").length).toBeGreaterThan(0);
    expect(screen.getByText("self")).toHaveAttribute("title", SELF_TRANSFER_EXPLANATION);
    expect(screen.getByText("same wallet")).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Inbound / Outbound Events" })).toBeInTheDocument();
    expect(screen.queryByRole("columnheader", { name: "Amount" })).not.toBeInTheDocument();
    expect(screen.queryByText("raw only")).not.toBeInTheDocument();
    expect(screen.getByText("Fixture data")).toBeInTheDocument();
    expect(screen.getByText("Coverage not recorded")).toBeInTheDocument();
    expect(screen.getByText(/Generated Nov 14, 2023, 10:15 PM UTC/)).toBeInTheDocument();
    expect(screen.getByText("Activity Timeline")).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Timeline year" })).toHaveValue("");
    expect(screen.getByRole("option", { name: "2023" })).toBeInTheDocument();
    expect(screen.getByText("Period cross-filtering is available in local live mode.")).toBeInTheDocument();
    fireEvent.change(screen.getByRole("combobox", { name: "Timeline year" }), {
      target: { value: "2023" },
    });
    expect(screen.getByRole("combobox", { name: "Timeline year" })).toHaveValue("2023");
    expect(screen.getByText("Showing 2023 monthly activity")).toBeInTheDocument();
    fireEvent.change(screen.getByRole("combobox", { name: "Timeline year" }), {
      target: { value: "" },
    });
    expect(screen.getByText("10 of 12 events")).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "All" })).toBeChecked();
    expect(screen.getByRole("radio", { name: "Recognized" })).not.toBeChecked();
    expect(screen.getByRole("radio", { name: "Other" })).not.toBeChecked();
    expect(screen.queryByText("Status (2)")).not.toBeInTheDocument();
    expect(screen.queryByText("Quality (1)")).not.toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Recognition" })).toBeInTheDocument();
    expect(screen.queryByText(/^reputation$/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/^high confidence$/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Show less" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Show more" }));
    expect(screen.getByText("12 of 12 events")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Show less" }));
    expect(screen.getByText("10 of 12 events")).toBeInTheDocument();
    expect(screen.getAllByText("OTHER").length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("radio", { name: "Recognized" }));
    expect(screen.queryByText("OTHER")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("radio", { name: "Other" }));
    expect(screen.getAllByText("OTHER").length).toBeGreaterThan(0);
    expect(screen.queryByText("USDC")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("radio", { name: "All" }));
    expect(screen.getAllByText("USDC").length).toBeGreaterThan(0);

    fireEvent.mouseEnter(screen.getByLabelText("What recognized means"));
    expect(screen.getByText(/exact Ethereum contract address appears in Uniswap/)).toBeInTheDocument();
    expect(screen.getByRole("tooltip", { name: /Recognized tokens/ })).toBeInTheDocument();
    expect(screen.getByLabelText("How token recognition works")).toBeInTheDocument();
    fireEvent.mouseEnter(screen.getByLabelText("How token recognition works"));
    expect(screen.getByRole("tooltip", { name: /Recognition controls/ }))
      .toHaveTextContent("Recognition controls");
    expect(screen.getAllByRole("combobox", { name: /Recognition for/ }).every((control) => control.hasAttribute("disabled"))).toBe(true);

    fireEvent.mouseEnter(screen.getByLabelText("How address type works"));
    expect(screen.getByRole("tooltip", { name: /Address type/ })).toBeInTheDocument();
    const addressTypeSummary = screen.getByText("Address type (2)");
    const addressTypeMenu = addressTypeSummary.closest("details");
    fireEvent.click(addressTypeSummary);
    expect(addressTypeMenu).toHaveAttribute("open");
    const contractAccount = screen.getByRole("checkbox", { name: "Contract" });
    const eoaCandidate = screen.getByRole("checkbox", { name: "EOA" });
    expect(contractAccount).toBeChecked();
    expect(eoaCandidate).toBeChecked();
    fireEvent.click(contractAccount);
    expect(screen.queryByRole("link", { name: "0x111...111" })).not.toBeInTheDocument();
    fireEvent.click(contractAccount);
    fireEvent.mouseLeave(addressTypeMenu!);
    expect(addressTypeMenu).not.toHaveAttribute("open");

    const recognizedStatus = screen.getAllByText("Recognized")
      .find((element) => element.classList.contains("recognitionStatus"));
    expect(recognizedStatus).toHaveTextContent(/^Recognized$/);

    fireEvent.change(screen.getByLabelText("Filter dashboard"), { target: { value: "contract" } });
    expect(screen.getAllByRole("link", { name: "0x1111...1111" }).length).toBeGreaterThan(0);

    fireEvent.change(screen.getByLabelText("Filter dashboard"), { target: { value: "0x1111" } });
    expect(screen.getAllByText("0x1111...1111").length).toBeGreaterThan(0);

    fireEvent.click(screen.getByLabelText("Switch to dark theme"));
    expect(document.documentElement.dataset.theme).toBe("dark");

    fireEvent.click(screen.getByLabelText("Switch to light theme"));
    expect(document.documentElement.dataset.theme).toBe("light");
  });

  it("shows an actionable error when generated data is unavailable", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve({ ok: false, status: 404 })),
    );

    render(<App />);

    expect(await screen.findByText(/Could not load data\/summaries\.json \(HTTP 404\)/)).toBeInTheDocument();
    expect(screen.getByText(/analytics:build/)).toBeInTheDocument();
  });
});
