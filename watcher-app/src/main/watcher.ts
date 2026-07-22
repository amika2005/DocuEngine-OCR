import chokidar, { type FSWatcher } from 'chokidar';
import path from 'node:path';
import type { Uploader } from './uploader';

const ALLOWED = new Set(['.pdf', '.png', '.jpg', '.jpeg', '.tif', '.tiff']);

export class FolderWatcher {
  private watcher: FSWatcher | null = null;

  constructor(private uploader: Uploader) {}

  start(folder: string): void {
    this.stop();
    // Events before 'ready' are the initial scan of files already in the folder;
    // events after it are genuine new arrivals (a fresh scan or a user drop).
    let ready = false;
    this.watcher = chokidar.watch(folder, {
      ignoreInitial: false, // pick up files scanned while the app was closed
      depth: 0,
      // Poll rather than rely on native OS file events. Scanner output can land
      // in network shares or driver-backed folders where native events are
      // unreliable or never fire — polling guarantees every new file is seen.
      usePolling: true,
      interval: 1000,
      binaryInterval: 1500,
      // Canon scanners write large PDFs slowly — wait until the file stops
      // growing before treating it as complete.
      awaitWriteFinish: { stabilityThreshold: 3000, pollInterval: 500 },
      ignored: (candidate) => {
        const base = path.basename(candidate);
        if (base.startsWith('.') || base.startsWith('~')) return true;
        const ext = path.extname(candidate).toLowerCase();
        return ext !== '' && !ALLOWED.has(ext);
      },
    });
    this.watcher.on('ready', () => {
      ready = true;
    });
    this.watcher.on('add', (filePath) => {
      if (ALLOWED.has(path.extname(filePath).toLowerCase())) {
        void this.uploader.enqueueFile(filePath, ready);
      }
    });
    this.watcher.on('error', (err) => {
      console.error('folder watch error', err);
    });
  }

  stop(): void {
    void this.watcher?.close();
    this.watcher = null;
  }
}
