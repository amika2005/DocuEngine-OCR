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
    config: { serverUrl: '', watchFolder: '', afterUpload: 'keep' },
  },
});

let window: BrowserWindow | null = null;
let tray: Tray | null = null;
let connected = false;
let deviceName: string | undefined;

const journal = new Journal(app.getPath('userData'));

function getConfig(): WatcherConfig {
  const base = store.get('config') as Omit<WatcherConfig, 'deviceToken'> & { moveUploaded?: boolean };
  // Migrate the old boolean `moveUploaded` field to the `afterUpload` action.
  if (base.afterUpload === undefined) {
    base.afterUpload = base.moveUploaded ? 'move' : 'keep';
  }
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
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      // The preload requires a local module (../shared/ipc). Electron's default
      // sandbox only lets a preload require Electron built-ins, so the require
      // throws and contextBridge never exposes `watcherApi` — breaking the whole
      // settings UI. Disable the sandbox (contextIsolation stays on, so the
      // renderer is still isolated) so the preload can load its dependencies.
      sandbox: false,
      contextIsolation: true,
      nodeIntegration: false,
    },
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

// 16x16 teal "D" badge, inlined so the tray always has a visible, clickable
// icon (an empty image renders nothing, leaving the user no way to reopen the
// window). Kept as a data URL to avoid shipping a separate asset file.
const TRAY_ICON_PNG =
  'iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAN0lEQVR4nGPgL8tjgOL/JGKwPnI1ww2hRDMYYxiACwyMAdj4owbQ2wBCmmljADlJmeLMRFF2BgBvimCD0niQPAAAAABJRU5ErkJggg==';

function createTray(): void {
  const icon = nativeImage.createFromDataURL(`data:image/png;base64,${TRAY_ICON_PNG}`);
  tray = new Tray(icon.isEmpty() ? nativeImage.createEmpty() : icon);
  tray.setContextMenu(
    Menu.buildFromTemplate([
      { label: '設定 / Status', click: createWindow },
      { type: 'separator' },
      { label: '終了', click: () => app.quit() },
    ]),
  );
  tray.setToolTip('DocuEngine Watcher');
  tray.on('click', createWindow); // single click also opens (Windows expectation)
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

// Only one watcher instance may run. This tray app has no visible window most of
// the time, so a user who double-clicks the exe again (the natural way to "open"
// it) would otherwise just spawn a dead duplicate. Instead, the second launch is
// caught here and told to surface the existing instance's settings window.
const gotSingleInstanceLock = app.requestSingleInstanceLock();
if (!gotSingleInstanceLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    createWindow();
    window?.show();
    window?.focus();
  });
}

if (gotSingleInstanceLock) app.whenReady().then(async () => {
  await journal.load();

  ipcMain.handle(IPC.getConfig, () => getConfig());
  ipcMain.handle(IPC.setConfig, (_event, config: WatcherConfig) => {
    setConfig(config);
    startWatching();
    void testConnection();
  });
  ipcMain.handle(IPC.getStatus, () => snapshot());
  ipcMain.handle(IPC.testConnection, () => testConnection());
  ipcMain.handle(IPC.pickFolder, () => {
    // Synchronous native dialog: returns the chosen path as a plain string, so
    // there is no File / File.path / webUtils involvement. Sync (not the
    // promise API) so it can never hang as an unresolved promise. Returns
    // {path, error}; the renderer shows `error` and falls back to the in-page
    // picker if the native dialog itself fails to open.
    try {
      const current = getConfig().watchFolder;
      const options: Electron.OpenDialogSyncOptions = {
        properties: ['openDirectory'],
        title: '監視フォルダを選択 / Select watch folder',
        defaultPath: folderExists(current) ? current : app.getPath('documents'),
      };
      const paths = window
        ? dialog.showOpenDialogSync(window, options)
        : dialog.showOpenDialogSync(options);
      if (!paths || paths.length === 0) return { path: null, error: '' };
      return { path: paths[0], error: '' };
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      console.error('pickFolder failed', err);
      return { path: null, error: message };
    }
  });
  ipcMain.handle(IPC.validateFolder, (_event, folder: string) => {
    const p = normalizeFolder(folder);
    return { path: p, valid: folderExists(p) };
  });

  createTray();
  const config = getConfig();
  // Show the window on a manual launch (double-clicking the exe). Only the login
  // auto-start launches with `--hidden`, so that one stays silent in the tray.
  // A first run with incomplete config always shows the settings window.
  const startHidden = process.argv.includes('--hidden');
  const configComplete = config.serverUrl && config.deviceToken && config.watchFolder;
  if (!startHidden || !configComplete) {
    createWindow();
  }
  startWatching();
  uploader.resume();
  void testConnection();
  // Auto-start at login, but silently (tray only) via the --hidden flag.
  app.setLoginItemSettings({ openAtLogin: true, args: ['--hidden'] });
});

// Tray app: keep running when the settings window closes.
app.on('window-all-closed', () => {});
