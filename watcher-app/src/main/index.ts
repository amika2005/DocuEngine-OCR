import { app, BrowserWindow, dialog, ipcMain, Menu, nativeImage, safeStorage, Tray } from 'electron';
import Store from 'electron-store';
import fs from 'node:fs';
import path from 'node:path';
import { IPC, type StatusSnapshot, type WatcherConfig } from '../shared/ipc';
import { Journal } from './journal';
import { Uploader } from './uploader';
import { FolderWatcher } from './watcher';

const store = new Store<{ config: Omit<WatcherConfig, 'deviceToken'>; tokenEncrypted?: string }>({
  defaults: {
    config: { serverUrl: '', watchFolder: '', moveUploaded: true },
  },
});

let window: BrowserWindow | null = null;
let tray: Tray | null = null;
let connected = false;
let deviceName: string | undefined;

const journal = new Journal(app.getPath('userData'));

function getConfig(): WatcherConfig {
  const base = store.get('config');
  let deviceToken = '';
  const encrypted = store.get('tokenEncrypted');
  if (encrypted) {
    try {
      deviceToken = safeStorage.isEncryptionAvailable()
        ? safeStorage.decryptString(Buffer.from(encrypted, 'base64'))
        : Buffer.from(encrypted, 'base64').toString('utf-8');
    } catch {
      deviceToken = '';
    }
  }
  return { ...base, deviceToken };
}

/**
 * Clean up a folder path typed or pasted by the user. Windows Explorer's
 * "Copy as path" wraps the path in double quotes ("C:\...\Scans"), which
 * breaks the watcher silently — strip those and trailing whitespace. If the
 * path points at a file (e.g. a file was dropped), fall back to its folder.
 */
function normalizeFolder(input: string): string {
  let p = (input ?? '').trim();
  if (p.length >= 2 && p.startsWith('"') && p.endsWith('"')) p = p.slice(1, -1).trim();
  try {
    if (p && fs.statSync(p).isFile()) p = path.dirname(p);
  } catch {
    // Path may not exist yet; validation happens separately.
  }
  return p;
}

function setConfig(config: WatcherConfig): void {
  const { deviceToken, ...rest } = config;
  rest.watchFolder = normalizeFolder(rest.watchFolder);
  store.set('config', rest);
  if (deviceToken) {
    const encrypted = safeStorage.isEncryptionAvailable()
      ? safeStorage.encryptString(deviceToken).toString('base64')
      : Buffer.from(deviceToken, 'utf-8').toString('base64');
    store.set('tokenEncrypted', encrypted);
  }
}

const uploader = new Uploader(journal, getConfig, notifyStatus);
const folderWatcher = new FolderWatcher(uploader);

function snapshot(): StatusSnapshot {
  return { connected, deviceName, queue: journal.all().slice(0, 100) };
}

function notifyStatus(): void {
  window?.webContents.send(IPC.statusChanged, snapshot());
  updateTray();
}

async function testConnection(): Promise<boolean> {
  try {
    const response = await uploader.request('POST', '/api/v1/ingest/handshake');
    if (response.ok) {
      const data = (await response.json()) as { device_name: string };
      deviceName = data.device_name;
      connected = true;
    } else {
      connected = false;
    }
  } catch {
    connected = false;
  }
  notifyStatus();
  return connected;
}

function createWindow(): void {
  if (window) {
    window.show();
    return;
  }
  window = new BrowserWindow({
    width: 720,
    height: 560,
    title: 'DocuEngine Watcher',
    webPreferences: { preload: path.join(__dirname, 'preload.js') },
  });
  void window.loadFile(path.join(__dirname, '..', '..', 'src', 'renderer', 'index.html'));
  window.on('closed', () => {
    window = null;
  });
}

function updateTray(): void {
  if (!tray) return;
  const uploading = journal.all().some((entry) => entry.state === 'uploading');
  const failed = journal.all().some((entry) => entry.state === 'failed');
  tray.setToolTip(
    `DocuEngine Watcher — ${uploading ? 'アップロード中' : failed ? 'エラーあり' : connected ? '待機中' : '未接続'}`,
  );
}

function createTray(): void {
  // 1x1 transparent placeholder; real icons ship with the installer assets.
  tray = new Tray(nativeImage.createEmpty());
  tray.setContextMenu(
    Menu.buildFromTemplate([
      { label: '設定 / Status', click: createWindow },
      { type: 'separator' },
      { label: '終了', click: () => app.quit() },
    ]),
  );
  tray.on('double-click', createWindow);
  updateTray();
}

function folderExists(folder: string): boolean {
  try {
    return !!folder && fs.statSync(folder).isDirectory();
  } catch {
    return false;
  }
}

function startWatching(): void {
  const config = getConfig();
  if (config.deviceToken && config.serverUrl && folderExists(config.watchFolder)) {
    folderWatcher.start(config.watchFolder);
  } else {
    folderWatcher.stop();
  }
}

app.whenReady().then(async () => {
  await journal.load();

  ipcMain.handle(IPC.getConfig, () => getConfig());
  ipcMain.handle(IPC.setConfig, (_event, config: WatcherConfig) => {
    setConfig(config);
    startWatching();
    void testConnection();
  });
  ipcMain.handle(IPC.getStatus, () => snapshot());
  ipcMain.handle(IPC.testConnection, () => testConnection());
  ipcMain.handle(IPC.pickFolder, async () => {
    // Parent the dialog to the window so it opens modal and in front (without a
    // parent it can appear behind the window and seem unclickable). Returns
    // {path, failed} so the renderer can fall back to the in-page picker only
    // on a real failure (not when the user simply cancels).
    try {
      const current = getConfig().watchFolder;
      const options: Electron.OpenDialogOptions = {
        properties: ['openDirectory', 'createDirectory'],
        title: '監視フォルダを選択 / Select watch folder',
        defaultPath: folderExists(current) ? current : app.getPath('documents'),
      };
      const result = window
        ? await dialog.showOpenDialog(window, options)
        : await dialog.showOpenDialog(options);
      if (result.canceled || result.filePaths.length === 0) {
        return { path: null, failed: false };
      }
      return { path: result.filePaths[0], failed: false };
    } catch (err) {
      // Native dialog can be unreliable on some Windows setups; the renderer
      // falls back to an in-page directory picker / drag-and-drop.
      console.error('pickFolder failed', err);
      return { path: null, failed: true };
    }
  });
  ipcMain.handle(IPC.validateFolder, (_event, folder: string) => {
    const p = normalizeFolder(folder);
    return { path: p, valid: folderExists(p) };
  });

  createTray();
  const config = getConfig();
  if (!config.serverUrl || !config.deviceToken || !config.watchFolder) {
    createWindow(); // first run — show settings
  }
  startWatching();
  uploader.resume();
  void testConnection();
  app.setLoginItemSettings({ openAtLogin: true });
});

// Tray app: keep running when the settings window closes.
app.on('window-all-closed', () => {});
