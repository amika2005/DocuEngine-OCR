import { app, BrowserWindow, dialog, ipcMain, Menu, nativeImage, safeStorage, Tray } from 'electron';
import Store from 'electron-store';
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

function setConfig(config: WatcherConfig): void {
  const { deviceToken, ...rest } = config;
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

function startWatching(): void {
  const config = getConfig();
  if (config.watchFolder && config.deviceToken && config.serverUrl) {
    folderWatcher.start(config.watchFolder);
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
    // parent it can appear behind the window and seem unclickable).
    const options: Electron.OpenDialogOptions = {
      properties: ['openDirectory', 'createDirectory'],
      title: 'Select watch folder',
    };
    const result = window
      ? await dialog.showOpenDialog(window, options)
      : await dialog.showOpenDialog(options);
    if (result.canceled || result.filePaths.length === 0) return null;
    return result.filePaths[0];
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
