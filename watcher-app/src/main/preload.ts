import { contextBridge, ipcRenderer, webUtils } from 'electron';
import {
  IPC,
  type FolderValidation,
  type PickFolderResult,
  type StatusSnapshot,
  type WatcherConfig,
} from '../shared/ipc';

contextBridge.exposeInMainWorld('watcherApi', {
  // Electron 30+: File.path is deprecated/unreliable; this returns the real
  // on-disk path for a dropped file or folder.
  getDroppedPath: (file: File) => {
    try {
      return webUtils.getPathForFile(file);
    } catch {
      return '';
    }
  },
  getConfig: () => ipcRenderer.invoke(IPC.getConfig) as Promise<WatcherConfig>,
  setConfig: (config: WatcherConfig) => ipcRenderer.invoke(IPC.setConfig, config),
  getStatus: () => ipcRenderer.invoke(IPC.getStatus) as Promise<StatusSnapshot>,
  testConnection: () => ipcRenderer.invoke(IPC.testConnection) as Promise<boolean>,
  pickFolder: () => ipcRenderer.invoke(IPC.pickFolder) as Promise<PickFolderResult>,
  validateFolder: (folder: string) =>
    ipcRenderer.invoke(IPC.validateFolder, folder) as Promise<FolderValidation>,
  onStatusChanged: (callback: (status: StatusSnapshot) => void) => {
    ipcRenderer.on(IPC.statusChanged, (_event, status: StatusSnapshot) => callback(status));
  },
});
