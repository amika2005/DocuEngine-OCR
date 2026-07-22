/**
 * Upload queue: concurrency 2, exponential backoff on network errors, 429-aware
 * (server backpressure), automatic batching — files that appear within a 60s
 * window share one server batch so the web UI shows scanner-run progress.
 */
import { readFile, mkdir, rename, unlink } from 'node:fs/promises';
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

  /**
   * Called by the watcher for every stable file. `isUserAdded` is true for files
   * that arrive after the initial folder scan (a fresh scan or a manual drop).
   */
  async enqueueFile(filePath: string, isUserAdded = false): Promise<void> {
    const sha256 = await sha256File(filePath);
    const existing = this.journal.get(sha256);
    if (existing && (existing.state === 'done' || existing.state === 'duplicate')) {
      // Same content was already uploaded. Don't re-OCR identical bytes — but if
      // the user just dropped it in, surface it as a duplicate (with a fresh
      // timestamp so it's visibly detected) and apply the after-upload action so
      // the redundant copy is cleaned up per the user's setting.
      if (isUserAdded) {
        await this.journal.upsert({ ...existing, path: filePath, state: 'duplicate' });
        this.onChange();
        await this.afterUpload(filePath);
      }
      return;
    }
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
        await this.afterUpload(entry.path);
        this.backoffMs = 1000;
      } else if (response.status === 409) {
        await this.journal.upsert({ ...entry, state: 'duplicate' });
        await this.afterUpload(entry.path);
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

  /**
   * Act on the original file once it has uploaded: keep it in place, delete it,
   * or move it into an `uploaded/` sub-folder. All failures are swallowed —
   * a file locked by the scanner is harmless because the sha256 dedupe (and the
   * journal `done` state) already prevents a re-upload.
   */
  private async afterUpload(filePath: string): Promise<void> {
    const action = this.getConfig().afterUpload;
    try {
      if (action === 'delete') {
        await unlink(filePath);
      } else if (action === 'move') {
        const dir = path.join(path.dirname(filePath), 'uploaded');
        await mkdir(dir, { recursive: true });
        await rename(filePath, path.join(dir, path.basename(filePath)));
      }
      // 'keep' (or anything else): leave the original untouched.
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
    // `localhost` can resolve to IPv6 (::1) where a 127.0.0.1-only server isn't
    // listening, which hangs the request — normalize to IPv4 for local URLs.
    const base = config.serverUrl.replace('://localhost', '://127.0.0.1');
    // Always time out so a bad address surfaces as a failure, never a hang.
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 15_000);
    try {
      return await fetch(new URL(apiPath, base), { method, headers, body, signal: controller.signal });
    } finally {
      clearTimeout(timer);
    }
  }
}
