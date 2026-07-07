import { useRef, useState, type WheelEvent, type MouseEvent } from 'react';
import AuthImage from './AuthImage';
import type { Region } from '../api/types';

interface Props {
  path: string; // API path of the page image (JWT-protected)
  pageWidth: number; // page size in pixels, from the Page record
  pageHeight: number;
  regions: Region[];
  hovered: number | null;
  onHover: (index: number | null) => void;
  onSelect?: (index: number) => void;
  showBoxes: boolean;
}

/** Confidence → border/fill classes. Color is backed up by the % label in the
 *  region list, so it is not the only indicator. */
export function confidenceTone(confidence: number): 'ok' | 'warn' | 'low' {
  if (confidence < 0.7) return 'low';
  if (confidence < 0.9) return 'warn';
  return 'ok';
}

const BOX_TONES: Record<ReturnType<typeof confidenceTone>, string> = {
  ok: 'border-sky-500/70 hover:bg-sky-400/20',
  warn: 'border-amber-500/80 hover:bg-amber-400/20',
  low: 'border-red-500/80 hover:bg-red-400/25',
};
const BOX_TONES_ACTIVE: Record<ReturnType<typeof confidenceTone>, string> = {
  ok: 'border-sky-500 bg-sky-400/25',
  warn: 'border-amber-500 bg-amber-400/25',
  low: 'border-red-500 bg-red-400/30',
};

/** Zoom/pan page viewer with OCR region bounding boxes overlaid on the scan.
 *  Boxes are positioned in % of the page size so they track the image at any
 *  zoom level. Hover/click syncs with the recognized-text panel. */
export default function RegionOverlayViewer({
  path,
  pageWidth,
  pageHeight,
  regions,
  hovered,
  onHover,
  onSelect,
  showBoxes,
}: Props) {
  const [scale, setScale] = useState(1);
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const dragging = useRef<{ x: number; y: number } | null>(null);
  // Survives past mouseup so the click handler can tell a drag from a click.
  const dragMoved = useRef(false);

  function onWheel(event: WheelEvent) {
    event.preventDefault();
    setScale((current) => Math.min(6, Math.max(0.3, current * (event.deltaY < 0 ? 1.1 : 0.9))));
  }
  function onMouseDown(event: MouseEvent) {
    dragging.current = { x: event.clientX - offset.x, y: event.clientY - offset.y };
    dragMoved.current = false;
  }
  function onMouseMove(event: MouseEvent) {
    if (!dragging.current) return;
    dragMoved.current = true;
    setOffset({ x: event.clientX - dragging.current.x, y: event.clientY - dragging.current.y });
  }
  function endDrag() {
    dragging.current = null;
  }

  return (
    <div
      className="h-full min-h-[60vh] cursor-grab overflow-hidden rounded bg-slate-100 active:cursor-grabbing"
      onWheel={onWheel}
      onMouseDown={onMouseDown}
      onMouseMove={onMouseMove}
      onMouseUp={endDrag}
      onMouseLeave={endDrag}
      onDoubleClick={() => {
        setScale(1);
        setOffset({ x: 0, y: 0 });
      }}
      title="scroll: zoom / drag: pan / double-click: reset"
    >
      <div
        className="flex h-full items-start justify-center"
        style={{ transform: `translate(${offset.x}px, ${offset.y}px) scale(${scale})` }}
      >
        <div className="relative max-h-full" style={{ aspectRatio: `${pageWidth} / ${pageHeight}` }}>
          <AuthImage
            path={path}
            draggable={false}
            className="max-h-full select-none"
            alt="scanned page"
          />
          {showBoxes &&
            regions.map((region, index) => {
              const [x0, y0, x1, y1] = region.bbox;
              const isCode = region.kind === 'code';
              const tone = confidenceTone(region.confidence);
              const active = hovered === index;
              const codeClass = active
                ? 'border-indigo-500 bg-indigo-400/25'
                : 'border-indigo-500/70 hover:bg-indigo-400/20';
              return (
                <div
                  key={index}
                  className={`absolute cursor-pointer rounded-[1px] border transition-colors duration-150 ${
                    isCode ? codeClass : active ? BOX_TONES_ACTIVE[tone] : BOX_TONES[tone]
                  }`}
                  style={{
                    left: `${(x0 / pageWidth) * 100}%`,
                    top: `${(y0 / pageHeight) * 100}%`,
                    width: `${((x1 - x0) / pageWidth) * 100}%`,
                    height: `${((y1 - y0) / pageHeight) * 100}%`,
                  }}
                  onMouseEnter={() => onHover(index)}
                  onMouseLeave={() => onHover(null)}
                  onClick={(event) => {
                    if (dragMoved.current) return;
                    event.stopPropagation();
                    onSelect?.(index);
                  }}
                  title={`${Math.round(region.confidence * 100)}% · ${region.markdown.slice(0, 80)}`}
                />
              );
            })}
        </div>
      </div>
    </div>
  );
}
