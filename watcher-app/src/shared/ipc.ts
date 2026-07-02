export interface WatcherConfig {
  serverUrl: string;
  deviceToken: string;
  watchFolder: string;
  moveUploaded: boolean; // move files into uploaded/ after successful upload
}

export interface JournalEntry {
  path: string;
  sha256: string;
  state: 'pending' | 'uploading' | 'done' | 'failed' | 'duplicate';
  documentId?: string;
  error?: string;
  updatedAt: string;
}

export interface StatusSnapshot {
  connected: boolean;
  deviceName?: string;
  queue: JournalEntry[];
}

export const IPC = {
  getConfig: 'config:get',
  setConfig: 'config:set',
  getStatus: 'status:get',
  testConnection: 'connection:test',
  statusChanged: 'status:changed',
  pickFolder: 'folder:pick',
} as const;
