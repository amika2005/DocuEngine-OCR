/** Pairwise markdown diff that prefers table *cells* over whole GFM rows. */

export type CorrectionChange = {
  kind: 'cell' | 'text';
  oldText: string;
  newText: string;
  column?: string;
  row?: number;
};

function splitCells(line: string): string[] | null {
  const trimmed = line.trim();
  if (!trimmed.startsWith('|')) return null;
  const parts = trimmed.split('|');
  const inner = parts.slice(1, parts[parts.length - 1] === '' ? -1 : parts.length);
  if (inner.length === 0) return null;
  return inner.map((cell) => cell.trim());
}

function isSeparatorLine(line: string): boolean {
  const cells = splitCells(line);
  if (!cells) return false;
  return cells.every((cell) => /^:?-+:?$/.test(cell.replace(/\s/g, '')) || cell === '');
}

function decodeCell(value: string): string {
  return value.replace(/<br\s*\/?>/gi, '\n');
}

type LineOp = {
  op: 'eq' | 'del' | 'ins';
  a?: string;
  b?: string;
  ai?: number;
  bi?: number;
};

function lcsOps(oldLines: string[], newLines: string[]): LineOp[] {
  const n = oldLines.length;
  const m = newLines.length;
  const dp: number[][] = Array.from({ length: n + 1 }, () => Array(m + 1).fill(0));
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      dp[i][j] =
        oldLines[i] === newLines[j]
          ? dp[i + 1][j + 1] + 1
          : Math.max(dp[i + 1][j], dp[i][j + 1]);
    }
  }
  const ops: LineOp[] = [];
  let i = 0;
  let j = 0;
  while (i < n && j < m) {
    if (oldLines[i] === newLines[j]) {
      ops.push({ op: 'eq', a: oldLines[i], b: newLines[j], ai: i, bi: j });
      i += 1;
      j += 1;
    } else if (dp[i + 1][j] >= dp[i][j + 1]) {
      ops.push({ op: 'del', a: oldLines[i], ai: i });
      i += 1;
    } else {
      ops.push({ op: 'ins', b: newLines[j], bi: j });
      j += 1;
    }
  }
  while (i < n) {
    ops.push({ op: 'del', a: oldLines[i], ai: i });
    i += 1;
  }
  while (j < m) {
    ops.push({ op: 'ins', b: newLines[j], bi: j });
    j += 1;
  }
  return ops;
}

function firstTableHeader(lines: string[]): string[] | null {
  for (const line of lines) {
    if (isSeparatorLine(line)) continue;
    const cells = splitCells(line);
    if (cells) return cells;
  }
  return null;
}

/** 1-based data row (skips the header). Undefined for header / non-table. */
function dataRowNumber(lines: string[], lineIndex: number): number | undefined {
  let seenHeader = false;
  let dataRow = 0;
  for (let i = 0; i <= lineIndex && i < lines.length; i++) {
    const line = lines[i];
    if (!splitCells(line) || isSeparatorLine(line)) continue;
    if (!seenHeader) {
      seenHeader = true;
      continue;
    }
    dataRow += 1;
    if (i === lineIndex) return dataRow;
  }
  return undefined;
}

function pushCellDiffs(
  changes: CorrectionChange[],
  oldLine: string,
  newLine: string,
  header: string[] | null,
  row: number | undefined,
): boolean {
  const oldCells = splitCells(oldLine);
  const newCells = splitCells(newLine);
  if (!oldCells || !newCells || isSeparatorLine(oldLine) || isSeparatorLine(newLine)) {
    return false;
  }
  const n = Math.max(oldCells.length, newCells.length);
  for (let c = 0; c < n; c++) {
    const oldText = oldCells[c] ?? '';
    const newText = newCells[c] ?? '';
    if (oldText === newText) continue;
    const column = header?.[c];
    changes.push({
      kind: 'cell',
      oldText: decodeCell(oldText),
      newText: decodeCell(newText),
      column: column || undefined,
      row,
    });
  }
  return true;
}

export function diffCorrectionMarkdown(original: string, corrected: string): CorrectionChange[] {
  const oldLines = original.split('\n');
  const newLines = corrected.split('\n');
  const header = firstTableHeader(oldLines) ?? firstTableHeader(newLines);
  const ops = lcsOps(oldLines, newLines);
  const changes: CorrectionChange[] = [];

  let i = 0;
  while (i < ops.length) {
    const op = ops[i];
    if (op.op === 'eq') {
      i += 1;
      continue;
    }
    if (op.op === 'del' && ops[i + 1]?.op === 'ins') {
      const oldLine = op.a ?? '';
      const newLine = ops[i + 1].b ?? '';
      if (isSeparatorLine(oldLine) && isSeparatorLine(newLine)) {
        i += 2;
        continue;
      }
      const row = dataRowNumber(oldLines, op.ai ?? 0);
      if (!pushCellDiffs(changes, oldLine, newLine, header, row) && oldLine !== newLine) {
        changes.push({
          kind: 'text',
          oldText: decodeCell(oldLine),
          newText: decodeCell(newLine),
          row,
        });
      }
      i += 2;
      continue;
    }
    if (op.op === 'del') {
      const oldLine = op.a ?? '';
      if (!isSeparatorLine(oldLine) && oldLine.trim()) {
        const cells = splitCells(oldLine);
        changes.push({
          kind: 'text',
          oldText: decodeCell(cells ? cells.join(' | ') : oldLine),
          newText: '',
          row: dataRowNumber(oldLines, op.ai ?? 0),
        });
      }
      i += 1;
      continue;
    }
    const newLine = op.b ?? '';
    if (!isSeparatorLine(newLine) && newLine.trim()) {
      const cells = splitCells(newLine);
      changes.push({
        kind: 'text',
        oldText: '',
        newText: decodeCell(cells ? cells.join(' | ') : newLine),
        row: dataRowNumber(newLines, op.bi ?? 0),
      });
    }
    i += 1;
  }
  return changes;
}

export function commonAffix(
  a: string,
  b: string,
): { prefix: string; oldMid: string; newMid: string; suffix: string } {
  let start = 0;
  const min = Math.min(a.length, b.length);
  while (start < min && a[start] === b[start]) start += 1;
  let end = 0;
  while (end < min - start && a[a.length - 1 - end] === b[b.length - 1 - end]) end += 1;
  return {
    prefix: a.slice(0, start),
    oldMid: a.slice(start, a.length - end),
    newMid: b.slice(start, b.length - end),
    suffix: end ? a.slice(a.length - end) : '',
  };
}
