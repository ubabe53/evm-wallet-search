import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ActivityTimeline } from "../src/dashboard/ActivityTimeline";

afterEach(cleanup);

describe("ActivityTimeline", () => {
  it("selects an exact timeline bucket and exposes a clear action", () => {
    const onSelect = vi.fn();
    const onClear = vi.fn();
    const onClearScope = vi.fn();
    const bucket = {
      bucket_start: "2026-07-01",
      bucket_end: "2026-08-01",
      transfer_count: 6,
      inbound_transfer_count: 3,
      outbound_transfer_count: 2,
      self_transfer_count: 1,
    };

    const { rerender } = render(
      <ActivityTimeline
        buckets={[bucket]}
        interval="month"
        selected={null}
        scopeYear={2026}
        interactive
        onSelect={onSelect}
        onClear={onClear}
        onClearScope={onClearScope}
        partialThrough="2026-07-15T00:00:00Z"
      />,
    );
    expect(screen.getByText("Captured events")).toBeInTheDocument();
    expect(screen.getByLabelText("Captured event count scale")).toHaveTextContent("6");
    expect(screen.getByLabelText("Captured event count scale")).toHaveTextContent("4.5");
    fireEvent.mouseEnter(screen.getByRole("button", { name: /July 2026 UTC: 6 captured events/ }));
    expect(screen.getByRole("tooltip")).toHaveTextContent("6 captured events");
    expect(screen.getByRole("tooltip")).toHaveTextContent("3 inbound · 2 outbound · 1 self");
    fireEvent.mouseLeave(screen.getByRole("button", { name: /July 2026 UTC: 6 captured events/ }));
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /July 2026 UTC: 6 captured events/ }));
    expect(onSelect).toHaveBeenCalledWith(bucket);
    expect(screen.getByText(/Current calendar period is partial/)).toBeInTheDocument();

    rerender(
      <ActivityTimeline
        buckets={[bucket]}
        interval="month"
        selected={{ start: bucket.bucket_start, end: bucket.bucket_end }}
        scopeYear={2026}
        interactive
        onSelect={onSelect}
        onClear={onClear}
        onClearScope={onClearScope}
        partialThrough={null}
      />,
    );
    expect(screen.getByText(/Filtering dashboard to July 2026 UTC/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Clear month" }));
    expect(onClear).toHaveBeenCalled();

    rerender(
      <ActivityTimeline
        buckets={[]}
        interval="month"
        selected={{ start: bucket.bucket_start, end: bucket.bucket_end }}
        scopeYear={2026}
        interactive
        onSelect={onSelect}
        onClear={onClear}
        onClearScope={onClearScope}
        partialThrough={null}
      />,
    );
    expect(screen.getByText(/Filtering dashboard to July 2026 UTC/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Clear month" })).toBeInTheDocument();

    rerender(
      <ActivityTimeline
        buckets={[bucket]}
        interval="month"
        selected={null}
        scopeYear={2026}
        interactive={false}
        onSelect={onSelect}
        onClear={onClear}
        onClearScope={onClearScope}
        partialThrough={null}
      />,
    );
    expect(screen.getByRole("button", { name: /July 2026 UTC: 6 captured events/ }))
      .toHaveAttribute("aria-disabled", "true");
    expect(screen.getByText("Showing 2026 monthly activity")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "All years" }));
    expect(onClearScope).toHaveBeenCalled();
  });
});
