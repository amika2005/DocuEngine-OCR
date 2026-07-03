import { useState } from 'react';
import { useTranslation } from 'react-i18next';

export interface DailyPoint {
  date: string; // YYYY-MM-DD
  count: number;
}

/** 7-day document volume — single-series bar chart.
 *  Dataviz rules: thin bars with rounded tops anchored to the baseline, one
 *  sequential hue (#2563eb, validated), no legend (title names the series),
 *  recessive baseline, per-bar hover tooltip, labels in text tokens. */
export default function VolumeChart({ title, data }: { title: string; data: DailyPoint[] }) {
  const { i18n } = useTranslation();
  const [hover, setHover] = useState<number | null>(null);
  const max = Math.max(1, ...data.map((point) => point.count));

  function dayLabel(date: string): string {
    return new Date(`${date}T00:00:00`).toLocaleDateString(
      i18n.language === 'ja' ? 'ja-JP' : 'en-US',
      { weekday: 'short' },
    );
  }

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4">
      <div className="mb-3 flex items-baseline justify-between">
        <h2 className="text-sm font-medium text-slate-700">{title}</h2>
        <span className="text-xs tabular-nums text-slate-400">
          {hover != null
            ? `${data[hover].date} — ${data[hover].count}`
            : `max ${max === 1 && data.every((p) => p.count === 0) ? 0 : max}`}
        </span>
      </div>
      <div className="flex h-36 items-end gap-2" onMouseLeave={() => setHover(null)}>
        {data.map((point, index) => {
          const heightPct = (point.count / max) * 100;
          return (
            <div
              key={point.date}
              className="group flex h-full flex-1 cursor-default flex-col justify-end"
              onMouseEnter={() => setHover(index)}
              title={`${point.date}: ${point.count}`}
            >
              <div
                className={`mx-auto w-full max-w-8 rounded-t transition-colors ${
                  hover === index ? 'bg-blue-700' : 'bg-blue-600'
                }`}
                style={{
                  height: point.count === 0 ? '2px' : `${Math.max(heightPct, 3)}%`,
                  backgroundColor: point.count === 0 ? '#e2e8f0' : undefined,
                }}
              />
            </div>
          );
        })}
      </div>
      <div className="mt-1 flex gap-2 border-t border-slate-100 pt-1">
        {data.map((point) => (
          <span key={point.date} className="flex-1 text-center text-[10px] text-slate-400">
            {dayLabel(point.date)}
          </span>
        ))}
      </div>
    </div>
  );
}
