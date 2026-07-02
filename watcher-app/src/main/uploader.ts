/**
 * Upload queue: concurrency 2, exponential backoff on network errors, 429-aware
 * (server backpressure), automatic batching — files that appear within a 60s
 * window share one server batch so the web UI shows scanner-run progress.
 */
import { readFile, mkdir, rename } from 'node:fs/promises';
import path from 'node:path';
import type { WatcherConfig } from '../shared/ipc';
import { Journal, sha256File } from './journal';

const CONCURRENCY = 2;
const MAX_BACKOFF_MS = 5 * 60_000;
const BATCH_WINDOW_MS = 60_000;

export class Uploader {
  private active = 0;
  private queue: string[] = []; // sha256 keys awaiting upload
  private currentBatch: { id: string; lastAdd: number } | null = null;
  private backoffMs = 1000;

  constructor(
    private journal: Journal,
    private getConfig: () => WatcherConfig,
    private onChange: () => void,
  ) {}

  /** Called by the watcher for every stable new file. */
  async enqueueFile(filePath: string): Promise<void> {
    const sha256 = await sha256File(filePath);
    const existing = this.journal.get(sha256);
    if (existing && (existing.state === 'done' || existing.state === 'duplicate')) return;
    await this.journal.upsert({ path: filePath, sha256, state: 'pending' });
    this.queue.push(sha256);
    this.onChange();
    void this.pump();
  }

  /** Re-queue failures/pending from a previous run. */
  resume(): void {
    for (const entry of this.journal.pending()) this.queue.push(entry.sha256);
    void this.pump();
  }

  private async pump(): Promise<void> {
    while (this.active < CONCURRENCY && this.queue.length > 0) {
      const key = this.queue.shift()!;
      this.active += 1;
      void this.upload(key).finally(() => {
        this.active -= 1;
        void this.pump();
      });
    }
  }

  private async ensureBatch(): Promise<string | null> {
    const now = Date.now();
    if (this.currentBatch && now - this.currentBatch.lastAdd < BATCH_WINDOW_MS) {
      this.currentBatch.lastAdd = now;
      return this.currentBatch.id;
    }
    if (this.currentBatch) void this.closeBatch(this.currentBatch.id);
    try {
      const response = await this.request('POST', '/api/v1/ingest/batches');
      const batch = (await response.json()) as { id: string };
      this.currentBatch = { id: batch.id, lastAdd: now };
      return batch.id;
    } catch {
      return null; // batchless upload is fine
    }
  }

  private async closeBatch(batchId: string): Promise<void> {
    try {
      await this.request('POST', `/api/v1/ingest/batches/${batchId}/close`);
    } catch {
      /* non-fatal */
    }
  }

  private async upload(sha256: string): Promise<void> {
    const entry = this.journal.get(sha256);
    if (!entry || entry.state === 'done' || entry.state === 'duplicate') return;
    await this.journal.upsert({ ...entry, state: 'uploading' });
    this.onChange();

    try {
      const batchId = await this.ensureBatch();
      const content = await readFile(entry.path);
      const form = new FormData();
      form.append(
        'file',
        new Blob([new Uint8Array(content)]),
        path.basename(entry.path),
      );
      const url = `/api/v1/ingest/documents${batchId ? `?batch_id=${batchId}` : ''}`;
      const response = await this.request('POST', url, form, sha256);

      if (response.status === 201) {
        const doc = (await response.json()) as { id: string };
        await this.journal.upsert({ ...entry, state: 'done', documentId: doc.id });
        await this.moveUploaded(entry.path);
        this.backoffMs = 1000;
      } else if (response.status === 409) {
        await this.journal.upsert({ ...entry, state: 'duplicate' });
        await this.moveUploaded(entry.path);
      } else if (response.status === 429) {
        // Server backpressure — retry the whole entry later.
        await this.retryLater(sha256, entry, 'server busy');
      } else {
        const body = await response.text();
        await this.journal.upsert({ ...entry, state: 'failed', error: `${response.status}: ${body.slice(0, 200)}` });
      }
    } catch (error) {
      await this.retryLater(sha256, entry, String(error));
    }
    this.onChange();
  }

  private async retryLater(sha256: string, entry: { path: string }, reason: string): Promise<void> {
    await this.journal.upsert({ path: entry.path, sha256, state: 'pending', error: reason });
    const delay = this.backoffMs;
    this.backoffMs = Math.min(this.backoffMs * 2, MAX_BACKOFF_MS);
    setTimeout(() => {
      this.queue.push(sha256);
      void this.pump();
    }, delay);
  }

  private async moveUploaded(filePath: string): Promise<void> {
    if (!this.getConfig().moveUploaded) return;
    try {
      const dir = path.join(path.dirname(filePath), 'uploaded');
      await mkdir(dir, { recursive: true });
      await rename(filePath, path.join(dir, path.basename(filePath)));
    } catch {
      /* file may be locked by the scanner — harmless, dedupe protects us */
    }
  }

  async request(
    method: string,
    apiPath: string,
    body?: FormData,
    idempotencyKey?: string,
  ): Promise<Response> {
    const config = this.getConfig();
    const headers: Record<string, string> = { 'X-Device-Token': config.deviceToken };
    if (idempotencyKey) headers['Idempotency-Key'] = idempotencyKey;
    return fetch(new URL(apiPath, config.serverUrl), { method, headers, body });
  }
}
