import { contextBridge, ipcRenderer } from 'electron';
import { IPC, type FolderValidation, type StatusSnapshot, type WatcherConfig } from '../shared/ipc';

contextBridge.exposeInMainWorld('watcherApi', {
  getConfig: () => ipcRenderer.invoke(IPC.getConfig) as Promise<WatcherConfig>,
  setConfig: (config: WatcherConfig) => ipcRenderer.invoke(IPC.setConfig, config),
  getStatus: () => ipcRenderer.invoke(IPC.getStatus) as Promise<StatusSnapshot>,
  testConnection: () => ipcRenderer.invoke(IPC.testConnection) as Promise<boolean>,
  pickFolder: () => ipcRenderer.invoke(IPC.pickFolder) as Promise<string | null>,
  validateFolder: (folder: string) =>
    ipcRenderer.invoke(IPC.validateFolder, folder) as Promise<FolderValidation>,
  onStatusChanged: (callback: (status: StatusSnapshot) => void) => {
    ipcRenderer.on(IPC.statusChanged, (_event, status: StatusSnapshot) => callback(status));
  },
});
