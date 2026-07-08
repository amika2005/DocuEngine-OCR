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

// --- Tabs ---
document.querySelectorAll('nav button').forEach((btn) => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('nav button').forEach((b) => b.classList.remove('active'));
    document.querySelectorAll('.tab').forEach((t) => t.classList.remove('active'));
    btn.classList.add('active');
    $(`tab-${btn.dataset.tab}`).classList.add('active');
  });
});

function renderQueue(queue) {
  const rows = queue
    .map((entry) => {
      const name = entry.path.split(/[\\/]/).pop();
      const label = STATE_LABELS[entry.state] ?? entry.state;
      const time = new Date(entry.updatedAt).toLocaleTimeString();
      const title = entry.error ? ` title="${entry.error.replace(/"/g, '&quot;')}"` : '';
      return `<tr><td>${name}</td><td class="state state-${entry.state}"${title}>${label}</td><td>${time}</td></tr>`;
    })
    .join('');
  $('queue').innerHTML = rows;
  $('queueEmpty').style.display = queue.length ? 'none' : 'block';

  const count = (state) => queue.filter((e) => e.state === state).length;
  $('cUp').textContent = `${count('uploading') + count('pending')} アップロード中`;
  $('cDone').textContent = `${count('done')} 完了`;
  $('cFail').textContent = `${count('failed')} 失敗`;
}

function renderStatus(status) {
  const on = status.connected;
  // Header pill
  $('conn').className = `conn ${on ? 'on' : 'off'}`;
  $('connText').textContent = on ? `接続済み${status.deviceName ? `: ${status.deviceName}` : ''}` : '未接続';
  // Home status card
  $('homeStatus').className = `big ${on ? 'on' : 'off'}`;
  $('homeStatus').textContent = on ? '接続済み・監視中' : '未接続';
  $('homeSub').textContent = on
    ? status.deviceName
      ? `端末: ${status.deviceName}`
      : '監視フォルダのファイルを自動アップロードします'
    : '設定タブでサーバーとトークンを登録してください';
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
  const msg = $('settingsMsg');
  const server = $('serverUrl').value.trim();
  const token = $('deviceToken').value.trim();
  const folder = $('watchFolder').value.trim();
  if (!server || !token || !folder) {
    msg.className = 'ng';
    msg.textContent = 'サーバー URL・トークン・監視フォルダをすべて入力してください';
    return;
  }
  msg.className = '';
  msg.textContent = '接続テスト中...';
  $('save').disabled = true;
  await watcherApi.setConfig({
    serverUrl: server,
    deviceToken: token,
    watchFolder: folder,
    moveUploaded: $('moveUploaded').checked,
  });
  const ok = await watcherApi.testConnection();
  $('save').disabled = false;
  msg.className = ok ? 'ok' : 'ng';
  msg.textContent = ok ? '✓ 接続に成功しました' : '✗ 接続できませんでした。URL とトークンを確認してください';
  renderStatus(await watcherApi.getStatus());
});

init();
