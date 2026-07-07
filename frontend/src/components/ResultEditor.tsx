import { useState } from 'react';
import { useTranslation } from 'react-i18next';

/** Visual editor for a page's OCR markdown: tables stay editable grids and
 *  text lines stay plain lines, so users never see raw markdown syntax.
 *  The markdown our engine emits is flat (lines + GFM tables), which makes
 *  the parse/serialize round-trip lossless. */

type Block =
  | { type: 'text'; text: string }
  | { type: 'image'; markdown: string; src: string; alt: string }
  | { type: 'table'; rows: string[][] };

const TABLE_SEPARATOR = /^\|[\s\-:|]+\|$/;
const IMAGE_LINE = /^!\[([^\]]*)\]\((.+)\)$/;

export function parseBlocks(markdown: string): Block[] {
  const blocks: Block[] = [];
  let table: string[][] | null = null;
  for (const raw of markdown.split('\n')) {
    const line = raw.trimEnd();
    if (line.startsWith('|') && line.endsWith('|') && line.length > 1) {
      if (TABLE_SEPARATOR.test(line)) continue;
      const cells = line
        .slice(1, -1)
        .split(/(?<!\\)\|/)
        .map((cell) => cell.trim().replace(/\\\|/g, '|').replace(/<br>/g, '\n'));
      (table ??= []).push(cells);
      continue;
    }
    if (table) {
      blocks.push({ type: 'table', rows: table });
      table = null;
    }
    const image = line.trim().match(IMAGE_LINE);
    if (image) {
      blocks.push({ type: 'image', markdown: line.trim(), alt: image[1], src: image[2] });
    } else if (line.trim()) {
      blocks.push({ type: 'text', text: line.trim() });
    }
  }
  if (table) blocks.push({ type: 'table', rows: table });
  return blocks;
}

export function serializeBlocks(blocks: Block[]): string {
  const parts: string[] = [];
  for (const block of blocks) {
    if (block.type === 'text') {
      if (block.text.trim()) parts.push(block.text.trim());
      continue;
    }
    if (block.type === 'image') {
      parts.push(block.markdown);
      continue;
    }
    const rows = block.rows.filter((row) => row.some((cell) => cell.trim()));
    if (rows.length === 0) continue;
    const width = Math.max(...rows.map((row) => row.length));
    const render = (row: string[]) =>
      '| ' +
      Array.from({ length: width }, (_, i) =>
        (row[i] ?? '').trim().replace(/\|/g, '\\|').replace(/\n/g, '<br>'),
      ).join(' | ') +
      ' |';
    parts.push(
      [render(rows[0]), '| ' + Array(width).fill('---').join(' | ') + ' |', ...rows.slice(1).map(render)].join('\n'),
    );
  }
  return parts.join('\n\n');
}

export default function ResultEditor({
  initialValue,
  onChange,
}: {
  initialValue: string;
  onChange: (markdown: string) => void;
}) {
  const { t } = useTranslation();
  // Blocks are internal state (parsed once on mount — remount via key to
  // reset); every edit reports the serialized markdown upward. Keeping the
  // raw keystrokes local avoids trim/round-trip fights while typing.
  const [blocks, setBlocks] = useState<Block[]>(() => parseBlocks(initialValue));

  function commit(next: Block[]) {
    setBlocks(next);
    onChange(serializeBlocks(next));
  }

  function patchText(index: number, text: string) {
    const next = blocks.map((b, i) => (i === index ? { type: 'text' as const, text } : b));
    commit(next);
  }

  function patchCell(index: number, row: number, col: number, text: string) {
    const next = blocks.map((b, i) => {
      if (i !== index || b.type !== 'table') return b;
      const rows = b.rows.map((r, ri) => (ri === row ? r.map((c, ci) => (ci === col ? text : c)) : r));
      return { type: 'table' as const, rows };
    });
    commit(next);
  }

  function tableRowAction(index: number, row: number, action: 'add' | 'remove') {
    const next = blocks.map((b, i) => {
      if (i !== index || b.type !== 'table') return b;
      const rows = [...b.rows];
      if (action === 'add') {
        rows.splice(row + 1, 0, Array(rows[row]?.length ?? 1).fill(''));
      } else if (rows.length > 1) {
        rows.splice(row, 1);
      }
      return { type: 'table' as const, rows };
    });
    commit(next);
  }

  return (
    <div className="space-y-3">
      {blocks.map((block, index) =>
        block.type === 'text' ? (
          <input
            key={index}
            value={block.text}
            onChange={(event) => patchText(index, event.target.value)}
            className="w-full rounded border border-transparent px-2 py-1 text-sm text-slate-800 transition-colors hover:border-slate-200 focus:border-sky-400 focus:bg-sky-50/30 focus:outline-none"
          />
        ) : block.type === 'image' ? (
          <img
            key={index}
            src={block.src}
            alt={block.alt || 'code'}
            className="inline-block max-h-32 rounded border border-slate-200 bg-white p-1"
          />
        ) : (
          <div key={index} className="overflow-x-auto rounded border border-slate-200">
            <table className="w-full text-sm">
              <tbody>
                {block.rows.map((row, ri) => (
                  <tr key={ri} className={`group ${ri === 0 ? 'bg-slate-50 font-medium' : 'border-t border-slate-100'}`}>
                    {row.map((cell, ci) => (
                      <td key={ci} className="border-r border-slate-100 p-0 last:border-r-0">
                        <textarea
                          value={cell}
                          rows={1}
                          onChange={(event) => patchCell(index, ri, ci, event.target.value)}
                          className="block h-full w-full resize-none border border-transparent bg-transparent px-2 py-1.5 leading-5 focus:border-sky-400 focus:bg-sky-50/40 focus:outline-none"
                          style={{ minHeight: '2rem', height: cell.includes('\n') ? `${(cell.split('\n').length + 0.6) * 1.25}rem` : undefined }}
                        />
                      </td>
                    ))}
                    <td className="w-14 whitespace-nowrap px-1 text-right align-middle opacity-0 transition-opacity group-hover:opacity-100">
                      <button
                        type="button"
                        onClick={() => tableRowAction(index, ri, 'add')}
                        title={t('detail.addRow')}
                        className="cursor-pointer px-1 text-slate-400 hover:text-emerald-600"
                      >
                        ＋
                      </button>
                      <button
                        type="button"
                        onClick={() => tableRowAction(index, ri, 'remove')}
                        title={t('detail.removeRow')}
                        className="cursor-pointer px-1 text-slate-400 hover:text-red-600"
                      >
                        −
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ),
      )}
      {blocks.length === 0 && <p className="py-8 text-center text-sm text-slate-400">—</p>}
    </div>
  );
}
