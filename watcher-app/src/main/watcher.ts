import chokidar, { type FSWatcher } from 'chokidar';
import path from 'node:path';
import type { Uploader } from './uploader';

const ALLOWED = new Set(['.pdf', '.png', '.jpg', '.jpeg', '.tif', '.tiff']);

export class FolderWatcher {
  private watcher: FSWatcher | null = null;

  constructor(private uploader: Uploader) {}

  start(folder: string): void {
    this.stop();
    this.watcher = chokidar.watch(folder, {
      ignoreInitial: false, // pick up files scanned while the app was closed
      depth: 0,
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
    this.watcher.on('add', (filePath) => {
      if (ALLOWED.has(path.extname(filePath).toLowerCase())) {
        void this.uploader.enqueueFile(filePath);
      }
    });
  }

  stop(): void {
    void this.watcher?.close();
    this.watcher = null;
  }
}
