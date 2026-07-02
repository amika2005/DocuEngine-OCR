// Settings + status window. Plain JS on purpose — talks to main via the
// contextBridge API exposed in preload.ts.
/* global watcherApi */

const $ = (id) => document.getElementById(id);

const STATE_LABELS = {
  pending: '待機中',
  uploading: 'アップロード中',
  done: '完了',
  failed: '失敗',
  duplicate: '重複',
};

function renderQueue(queue) {
  $('queue').innerHTML = queue
    .map((entry) => {
      const name = entry.path.split(/[\\/]/).pop();
      const label = STATE_LABELS[entry.state] ?? entry.state;
      const time = new Date(entry.updatedAt).toLocaleTimeString();
      return `<tr><td>${name}</td><td class="state-${entry.state}" title="${entry.error ?? ''}">${label}</td><td>${time}</td></tr>`;
    })
    .join('');
}

function renderStatus(status) {
  $('status').innerHTML = status.connected
    ? `<span class="ok">接続済み${status.deviceName ? `: ${status.deviceName}` : ''}</span>`
    : '<span class="ng">未接続</span>';
  renderQueue(status.queue);
}

async function init() {
  const config = await watcherApi.getConfig();
  $('serverUrl').value = config.serverUrl;
  $('deviceToken').value = config.deviceToken;
  $('watchFolder').value = config.watchFolder;
  $('moveUploaded').checked = config.moveUploaded;
  renderStatus(await watcherApi.getStatus());
  watcherApi.onStatusChanged(renderStatus);
}

$('pickFolder').addEventListener('click', async () => {
  const folder = await watcherApi.pickFolder();
  if (folder) $('watchFolder').value = folder;
});

$('save').addEventListener('click', async () => {
  await watcherApi.setConfig({
    serverUrl: $('serverUrl').value.trim(),
    deviceToken: $('deviceToken').value.trim(),
    watchFolder: $('watchFolder').value.trim(),
    moveUploaded: $('moveUploaded').checked,
  });
  renderStatus(await watcherApi.getStatus());
});

init();
