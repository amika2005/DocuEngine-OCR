import { useRef, useState, type WheelEvent, type MouseEvent } from 'react';

/** Zoom/pan viewer for scanned page images (mouse wheel to zoom, drag to pan). */
export default function PageViewer({ src }: { src: string }) {
  const [scale, setScale] = useState(1);
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const dragging = useRef<{ x: number; y: number } | null>(null);

  function onWheel(event: WheelEvent) {
    event.preventDefault();
    setScale((current) => Math.min(6, Math.max(0.3, current * (event.deltaY < 0 ? 1.1 : 0.9))));
  }
  function onMouseDown(event: MouseEvent) {
    dragging.current = { x: event.clientX - offset.x, y: event.clientY - offset.y };
  }
  function onMouseMove(event: MouseEvent) {
    if (!dragging.current) return;
    setOffset({ x: event.clientX - dragging.current.x, y: event.clientY - dragging.current.y });
  }
  function endDrag() {
    dragging.current = null;
  }

  return (
    <div
      className="h-[70vh] cursor-grab overflow-hidden rounded bg-slate-100 active:cursor-grabbing"
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
      <img
        src={src}
        draggable={false}
        className="mx-auto max-h-full select-none"
        style={{ transform: `translate(${offset.x}px, ${offset.y}px) scale(${scale})` }}
        alt="scanned page"
      />
    </div>
  );
}
