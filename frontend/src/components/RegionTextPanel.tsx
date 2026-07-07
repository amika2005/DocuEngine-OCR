import { useEffect, useRef } from 'react';
import type { Region } from '../api/types';
import { confidenceTone } from './RegionOverlayViewer';

interface Props {
  regions: Region[];
  hovered: number | null;
  onHover: (index: number | null) => void;
  /** Region index to scroll into view (set when a box is clicked on the scan). */
  scrollTo: number | null;
}

const ROW_TONES: Record<ReturnType<typeof confidenceTone>, string> = {
  ok: 'border-slate-200 bg-white',
  warn: 'border-amber-300 bg-amber-50',
  low: 'border-red-300 bg-red-50',
};
const BADGE_TONES: Record<ReturnType<typeof confidenceTone>, string> = {
  ok: 'bg-slate-100 text-slate-600',
  warn: 'bg-amber-100 text-amber-800',
  low: 'bg-red-100 text-red-800',
};

/** Recognized text lines of one page, hover-synced with the bbox overlay.
 *  Low-confidence lines are tinted so correction targets stand out. */
export default function RegionTextPanel({ regions, hovered, onHover, scrollTo }: Props) {
  const rowRefs = useRef<(HTMLDivElement | null)[]>([]);

  useEffect(() => {
    if (scrollTo != null) {
      rowRefs.current[scrollTo]?.scrollIntoView({ block: 'center', behavior: 'smooth' });
    }
  }, [scrollTo]);

  if (regions.length === 0) {
    return <p className="py-12 text-center text-slate-400">—</p>;
  }

  return (
    <div className="space-y-1.5">
      {regions.map((region, index) => {
        const tone = confidenceTone(region.confidence);
        const active = hovered === index;
        return (
          <div
            key={index}
            ref={(el) => {
              rowRefs.current[index] = el;
            }}
            className={`cursor-pointer rounded border px-3 py-1.5 transition-colors duration-150 ${
              active ? 'border-sky-400 bg-sky-50' : ROW_TONES[tone]
            }`}
            onMouseEnter={() => onHover(index)}
            onMouseLeave={() => onHover(null)}
          >
            <div className="flex items-center gap-2">
              <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${BADGE_TONES[tone]}`}>
                {Math.round(region.confidence * 100)}%
              </span>
              {region.kind !== 'text' && (
                <span className="rounded bg-indigo-100 px-1.5 py-0.5 text-[10px] font-medium text-indigo-700">
                  {region.kind}
                </span>
              )}
            </div>
            {region.kind === 'table' ? (
              <pre className="mt-1 overflow-x-auto whitespace-pre text-xs leading-5 text-slate-800">
                {region.markdown}
              </pre>
            ) : (
              <p className="mt-0.5 break-all text-sm leading-5 text-slate-800">{region.markdown}</p>
            )}
          </div>
        );
      })}
    </div>
  );
}
