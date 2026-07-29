import { useId, useState, type CSSProperties } from "react";
import { CalendarDays } from "lucide-react";
import type { TimelineBucket, TimelineInterval } from "../data";
import {
  timelinePeriodLabel,
  timelineScaleLabel,
  timelineScaleTicks,
  timelineTickLabel,
  utcDate,
} from "./model";

export function ActivityTimeline({
  buckets,
  interval,
  selected,
  scopeYear,
  interactive,
  onSelect,
  onClear,
  onClearScope,
  partialThrough,
}: {
  buckets: TimelineBucket[];
  interval: TimelineInterval;
  selected: { start: string; end: string } | null;
  scopeYear: number | null;
  interactive: boolean;
  onSelect: (bucket: TimelineBucket) => void;
  onClear: () => void;
  onClearScope: () => void;
  partialThrough: string | null;
}) {
  const maximum = Math.max(0, ...buckets.map((bucket) => bucket.transfer_count));
  const scaleMaximum = Math.max(1, maximum);
  const scaleTicks = timelineScaleTicks(maximum);
  const partialDate = partialThrough ? new Date(partialThrough) : null;
  const tooltipId = useId();
  const [activeBucketStart, setActiveBucketStart] = useState<string | null>(null);
  const activeBucketIndex = buckets.findIndex((bucket) => bucket.bucket_start === activeBucketStart);
  const activeBucket = activeBucketIndex >= 0 ? buckets[activeBucketIndex] : null;
  return (
    <>
      <div className="timelineToolbar">
        <div className="timelineLegend" aria-label="Timeline legend">
          <span><i className="timelineInSwatch" />Inbound</span>
          <span><i className="timelineOutSwatch" />Outbound</span>
          <span><i className="timelineSelfSwatch" />Self</span>
        </div>
      </div>
      {selected && (
        <div className="timelineSelection">
          <span>
            <CalendarDays size={15} aria-hidden="true" />
            Filtering dashboard to {timelinePeriodLabel({
              bucket_start: selected.start,
              bucket_end: selected.end,
            }, interval)} UTC
          </span>
          <button type="button" onClick={onClear}>Clear month</button>
        </div>
      )}
      {!selected && scopeYear != null && (
        <div className="timelineSelection">
          <span>
            <CalendarDays size={15} aria-hidden="true" />
            {interactive
              ? `Filtering dashboard to ${scopeYear} UTC`
              : `Showing ${scopeYear} monthly activity`}
          </span>
          <button type="button" onClick={onClearScope}>All years</button>
        </div>
      )}
      {!interactive && (
        <p className="timelineDemoNote">Period cross-filtering is available in local live mode.</p>
      )}
      <div className="timelineScroll" role="region" aria-label="Captured event activity over time" tabIndex={0}>
        {buckets.length === 0 ? (
          <div className="timelineEmpty">No timeline activity matches</div>
        ) : (
          <div className="timelineChart">
            <div className="timelineYAxisTitle">Captured events</div>
            <div className={`timelineScale${maximum === 0 ? " empty" : ""}`} aria-label="Captured event count scale">
              {scaleTicks.map((tick, index) => (
                <span key={`${tick}-${index}`}>{timelineScaleLabel(tick, maximum)}</span>
              ))}
            </div>
            <div className="timelinePlot">
              {buckets.map((bucket) => {
                const selectedPeriod = selected?.start === bucket.bucket_start && selected.end === bucket.bucket_end;
                const bucketStartDate = utcDate(bucket.bucket_start);
                const bucketEndDate = utcDate(bucket.bucket_end);
                const isPartial = partialDate != null &&
                  bucketStartDate <= partialDate &&
                  partialDate < bucketEndDate;
                const height = bucket.transfer_count === 0
                  ? 0
                  : Math.max(1.5, bucket.transfer_count / scaleMaximum * 100);
                const inboundShare = bucket.transfer_count === 0
                  ? 0
                  : bucket.inbound_transfer_count / bucket.transfer_count * 100;
                const outboundShare = bucket.transfer_count === 0
                  ? 0
                  : bucket.outbound_transfer_count / bucket.transfer_count * 100;
                const selfShare = bucket.transfer_count === 0
                  ? 0
                  : bucket.self_transfer_count / bucket.transfer_count * 100;
                const style = {
                  "--timeline-height": `${height}%`,
                  "--timeline-in-share": `${inboundShare}%`,
                  "--timeline-out-share": `${outboundShare}%`,
                  "--timeline-self-share": `${selfShare}%`,
                } as CSSProperties;
                const period = timelinePeriodLabel(bucket, interval);
                const title = `${period} UTC: ${bucket.transfer_count.toLocaleString("en-US")} captured events (${bucket.inbound_transfer_count.toLocaleString("en-US")} inbound, ${bucket.outbound_transfer_count.toLocaleString("en-US")} outbound, ${bucket.self_transfer_count.toLocaleString("en-US")} self)${isPartial ? "; partial calendar period at data generation" : ""}`;
                return (
                  <button
                    key={bucket.bucket_start}
                    type="button"
                    className={`timelineBucket${selectedPeriod ? " selected" : ""}${isPartial ? " partial" : ""}`}
                    style={style}
                    aria-label={`${title}${interactive ? interval === "year" ? ". Open this year." : ". Select this month." : ""}`}
                    aria-describedby={activeBucketStart === bucket.bucket_start ? tooltipId : undefined}
                    aria-pressed={interactive ? selectedPeriod : undefined}
                    aria-disabled={!interactive}
                    onMouseEnter={() => setActiveBucketStart(bucket.bucket_start)}
                    onMouseLeave={() => setActiveBucketStart(null)}
                    onFocus={() => setActiveBucketStart(bucket.bucket_start)}
                    onBlur={() => setActiveBucketStart(null)}
                    onClick={() => interactive && onSelect(bucket)}
                  >
                    <span className="timelineBar" aria-hidden="true">
                      <i className="timelineInSegment" />
                      <i className="timelineOutSegment" />
                      <i className="timelineSelfSegment" />
                    </span>
                    <span className="timelineTick" aria-hidden="true">
                      {timelineTickLabel(bucket, interval)}{isPartial ? "*" : ""}
                    </span>
                  </button>
                );
              })}
              {activeBucket && (
                <div
                  className="timelineHoverTooltip"
                  id={tooltipId}
                  role="tooltip"
                  style={{
                    "--timeline-tooltip-position":
                      `${(activeBucketIndex + 0.5) / buckets.length * 100}%`,
                  } as CSSProperties}
                >
                  <strong>{timelinePeriodLabel(activeBucket, interval)} UTC</strong>
                  <span>{activeBucket.transfer_count.toLocaleString("en-US")} captured events</span>
                  <span>
                    {activeBucket.inbound_transfer_count.toLocaleString("en-US")} inbound
                    {" · "}
                    {activeBucket.outbound_transfer_count.toLocaleString("en-US")} outbound
                    {" · "}
                    {activeBucket.self_transfer_count.toLocaleString("en-US")} self
                  </span>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
      {partialDate && buckets.some((bucket) =>
        utcDate(bucket.bucket_start) <= partialDate && partialDate < utcDate(bucket.bucket_end)) && (
        <p className="timelinePartialNote">* Current calendar period is partial at data generation time.</p>
      )}
    </>
  );
}
