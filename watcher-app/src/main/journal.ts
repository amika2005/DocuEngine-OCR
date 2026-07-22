/**
 * Upload journal — survives restarts so every scanned file is uploaded exactly
 * once (dedupe by content sha256; the server enforces it too via 409).
 * Stored as an atomically-replaced JSON file in userData; at scanner volumes
 * (hundreds of files/day) this is simpler and just as safe as a SQLite journal.
 */
import { createHash } from 'node:crypto';
import { createReadStream } from 'node:fs';
import { mkdir, readFile, rename, writeFile } from 'node:fs/promises';
import path from 'node:path';
import type { JournalEntry } from '../shared/ipc';

export class Journal {
  private entries = new Map<string, JournalEntry>(); // key: sha256
  private file: string;
  private saving = Promise.resolve();

  constructor(dir: string) {
    this.file = path.join(dir, 'upload-journal.json');
  }

  async load(): Promise<void> {
    try {
      const raw = await readFile(this.file, 'utf-8');
      for (const entry of JSON.parse(raw) as JournalEntry[]) {
        this.entries.set(entry.sha256, entry);
        // Anything mid-flight when we died goes back to pending.
        if (entry.state === 'uploading') entry.state = 'pending';
      }
    } catch {
      /* first run */
    }
  }

  get(sha256: string): JournalEntry | undefined {
    return this.entries.get(sha256);
  }

  all(): JournalEntry[] {
    return [...this.entries.values()].sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
  }

  pending(): JournalEntry[] {
    return this.all().filter((entry) => entry.state === 'pending' || entry.state === 'failed');
  }

  async upsert(entry: Omit<JournalEntry, 'updatedAt'>): Promise<JournalEntry> {
    const full: JournalEntry = { ...entry, updatedAt: new Date().toISOString() };
    this.entries.set(full.sha256, full);
    await this.persist();
    return full;
  }

  /** Forget an entry entirely, so re-adding the same file uploads it again. */
  async delete(sha256: string): Promise<void> {
    if (this.entries.delete(sha256)) await this.persist();
  }

  private async persist(): Promise<void> {
    // Serialize writes; atomic replace so a crash never corrupts the journal.
    this.saving = this.saving.then(async () => {
      await mkdir(path.dirname(this.file), { recursive: true });
      const tmp = `${this.file}.tmp`;
      await writeFile(tmp, JSON.stringify(this.all(), null, 1));
      await rename(tmp, this.file);
    });
    await this.saving;
  }
}

export function sha256File(filePath: string): Promise<string> {
  return new Promise((resolve, reject) => {
    const hash = createHash('sha256');
    createReadStream(filePath)
      .on('data', (chunk) => hash.update(chunk))
      .on('end', () => resolve(hash.digest('hex')))
      .on('error', reject);
  });
}
