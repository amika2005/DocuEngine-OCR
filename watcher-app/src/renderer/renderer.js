// Settings + status window. Plain JS on purpose — talks to main via the
// contextBridge API exposed in preload.ts.
/* global watcherApi */

const $ = (id) => document.getElementById(id);

// --- i18n (Japanese / English) ---
const STRINGS = {
  ja: {
    'nav.home': 'ホーム',
    'nav.settings': '設定',
    'conn.on': '接続済み',
    'conn.off': '未接続',
    'home.connected': '接続済み・監視中',
    'home.disconnected': '未接続',
    'home.promptSettings': '設定タブでサーバーとトークンを登録してください',
    'home.device': '端末: {name}',
    'home.watching': '監視フォルダのファイルを自動アップロードします',
    'counts.uploading': '{n} アップロード中',
    'counts.done': '{n} 完了',
    'counts.failed': '{n} 失敗',
    'table.file': 'ファイル',
    'table.state': '状態',
    'table.updated': '更新',
    'queue.empty': 'まだアップロードはありません。監視フォルダにファイルを入れてください。',
    'settings.serverUrl': 'サーバー URL',
    'settings.serverHint': 'DocuEngine サーバーのアドレス（例: http://localhost:8000）',
    'settings.token': 'デバイストークン',
    'settings.tokenHint': '管理画面「スキャナー端末」で発行したトークンを貼り付けてください',
    'settings.folder': '監視フォルダ（スキャナー出力先）',
    'settings.folderPh': 'C:\\Users\\...\\Scans',
    'settings.folderHint':
      '「選択」で選ぶ・フォルダをここにドラッグ＆ドロップ・パスを直接貼り付け のいずれかで指定できます',
    'settings.pick': '選択...',
    'settings.dropActive': 'フォルダをドロップ',
    'settings.folderMissing': '✗ フォルダが見つかりません。パスを確認してください',
    'settings.folderEmpty': '✗ 空のフォルダは選べません。ファイルのあるフォルダを選ぶか、パスを貼り付けてください',
    'settings.moveUploaded': 'アップロード後 uploaded/ フォルダへ移動',
    'settings.save': '保存して接続テスト',
    'settings.testing': '接続テスト中...',
    'settings.needAll': 'サーバー URL・トークン・監視フォルダをすべて入力してください',
    'settings.connOk': '✓ 接続に成功しました',
    'settings.connFail': '✗ 接続できませんでした。URL とトークンを確認してください',
    'state.pending': '待機中',
    'state.uploading': 'アップロード中',
    'state.done': '完了',
    'state.failed': '失敗',
    'state.duplicate': '重複',
  },
  en: {
    'nav.home': 'Home',
    'nav.settings': 'Settings',
    'conn.on': 'Connected',
    'conn.off': 'Not connected',
    'home.connected': 'Connected · watching',
    'home.disconnected': 'Not connected',
    'home.promptSettings': 'Add the server and token in the Settings tab',
    'home.device': 'Device: {name}',
    'home.watching': 'Files in the watch folder upload automatically',
    'counts.uploading': '{n} uploading',
    'counts.done': '{n} done',
    'counts.failed': '{n} failed',
    'table.file': 'File',
    'table.state': 'Status',
    'table.updated': 'Updated',
    'queue.empty': 'No uploads yet. Drop files into the watch folder.',
    'settings.serverUrl': 'Server URL',
    'settings.serverHint': 'Address of the DocuEngine server (e.g. http://localhost:8000)',
    'settings.token': 'Device token',
    'settings.tokenHint': 'Paste the token issued under "Scanner devices" in the admin UI',
    'settings.folder': 'Watch folder (scanner output)',
    'settings.folderPh': 'C:\\Users\\...\\Scans',
    'settings.folderHint':
      'Pick with the button, drag & drop a folder here, or paste the folder path directly',
    'settings.pick': 'Choose...',
    'settings.dropActive': 'Drop folder here',
    'settings.folderMissing': '✗ Folder not found. Check the path',
    'settings.folderEmpty': '✗ Empty folder can’t be picked. Choose a folder that has files, or paste the path',
    'settings.moveUploaded': 'Move to uploaded/ folder after upload',
    'settings.save': 'Save & test connection',
    'settings.testing': 'Testing connection...',
    'settings.needAll': 'Enter the server URL, token and watch folder',
    'settings.connOk': '✓ Connected successfully',
    'settings.connFail': '✗ Could not connect. Check the URL and token',
    'state.pending': 'Pending',
    'state.uploading': 'Uploading',
    'state.done': 'Done',
    'state.failed': 'Failed',
    'state.duplicate': 'Duplicate',
  },
};

let lang = localStorage.getItem('watcher-lang') || 'ja';
const t = (key, vars) => {
  let s = (STRINGS[lang] && STRINGS[lang][key]) || key;
  if (vars) for (const k in vars) s = s.replace(`{${k}}`, vars[k]);
  return s;
};

function applyStatic() {
  document.documentElement.lang = lang;
  document.querySelectorAll('[data-i18n]').forEach((el) => {
    el.textContent = t(el.getAttribute('data-i18n'));
  });
  document.querySelectorAll('[data-i18n-ph]').forEach((el) => {
    el.setAttribute('placeholder', t(el.getAttribute('data-i18n-ph')));
  });
  $('langToggle').textContent = lang === 'ja' ? 'EN' : '日本語';
}

// --- Tabs ---
document.querySelectorAll('nav button[data-tab]').forEach((btn) => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('nav button[data-tab]').forEach((b) => b.classList.remove('active'));
    document.querySelectorAll('.tab').forEach((tab) => tab.classList.remove('active'));
    btn.classList.add('active');
    $(`tab-${btn.dataset.tab}`).classList.add('active');
  });
});

$('langToggle').addEventListener('click', async () => {
  lang = lang === 'ja' ? 'en' : 'ja';
  localStorage.setItem('watcher-lang', lang);
  applyStatic();
  renderStatus(await watcherApi.getStatus());
});

let lastStatus = { connected: false, queue: [] };

function renderQueue(queue) {
  $('queue').innerHTML = queue
    .map((entry) => {
      const name = entry.path.split(/[\\/]/).pop();
      const label = t(`state.${entry.state}`);
      const time = new Date(entry.updatedAt).toLocaleTimeString();
      const title = entry.error ? ` title="${entry.error.replace(/"/g, '&quot;')}"` : '';
      return `<tr><td>${name}</td><td class="state state-${entry.state}"${title}>${label}</td><td>${time}</td></tr>`;
    })
    .join('');
  $('queueEmpty').style.display = queue.length ? 'none' : 'block';

  const count = (state) => queue.filter((e) => e.state === state).length;
  $('cUp').textContent = t('counts.uploading', { n: count('uploading') + count('pending') });
  $('cDone').textContent = t('counts.done', { n: count('done') });
  $('cFail').textContent = t('counts.failed', { n: count('failed') });
}

function renderStatus(status) {
  lastStatus = status;
  const on = status.connected;
  $('conn').className = `conn ${on ? 'on' : 'off'}`;
  $('connText').textContent = on
    ? `${t('conn.on')}${status.deviceName ? `: ${status.deviceName}` : ''}`
    : t('conn.off');
  $('homeStatus').className = `big ${on ? 'on' : 'off'}`;
  $('homeStatus').textContent = on ? t('home.connected') : t('home.disconnected');
  $('homeSub').textContent = on
    ? status.deviceName
      ? t('home.device', { name: status.deviceName })
      : t('home.watching')
    : t('home.promptSettings');
  renderQueue(status.queue);
}

async function init() {
  applyStatic();
  const config = await watcherApi.getConfig();
  $('serverUrl').value = config.serverUrl;
  $('deviceToken').value = config.deviceToken;
  $('watchFolder').value = config.watchFolder;
  $('moveUploaded').checked = config.moveUploaded;
  renderStatus(await watcherApi.getStatus());
  watcherApi.onStatusChanged(renderStatus);
}

async function setFolder(path) {
  const msg = $('settingsMsg');
  const res = await watcherApi.validateFolder(path);
  if (res.valid) {
    $('watchFolder').value = res.path;
    msg.className = 'ok';
    msg.textContent = res.path;
  } else {
    $('watchFolder').value = path;
    msg.className = 'ng';
    msg.textContent = t('settings.folderMissing');
  }
  return res.valid;
}

// Choose: try the native OS dialog first (it returns a plain string path — no
// File.path/webUtils involved). If it errors, show why and fall back to the
// in-page Chromium directory picker.
$('pickFolder').addEventListener('click', async () => {
  const msg = $('settingsMsg');
  let result = null;
  try {
    result = await watcherApi.pickFolder();
  } catch (err) {
    result = { path: null, error: String(err && err.message ? err.message : err) };
  }
  if (result && result.path) {
    await setFolder(result.path);
    return;
  }
  if (result && result.error) {
    // Native dialog failed to open — surface it, then use the in-page picker.
    msg.className = 'ng';
    msg.textContent = 'dialog: ' + result.error;
    $('folderInput').click();
    return;
  }
  // Plain cancel — leave the field as-is.
});

// Resolve a File object to its absolute on-disk path. File.path is deprecated
// (empty) in recent Electron; webUtils.getPathForFile (exposed as
// getDroppedPath) is the supported replacement.
let lastDiag = '';
function absPath(file) {
  if (!file) {
    lastDiag = 'no-file';
    return '';
  }
  let viaUtil = '';
  try {
    viaUtil = watcherApi.getDroppedPath ? watcherApi.getDroppedPath(file) : '(no-api)';
  } catch (err) {
    viaUtil = 'ERR:' + (err && err.message ? err.message : err);
  }
  const viaProp = file.path || '';
  lastDiag = `util=[${viaUtil}] path=[${viaProp}]`;
  const utilOk = viaUtil && viaUtil !== '(no-api)' && !viaUtil.startsWith('ERR:');
  return (utilOk ? viaUtil : '') || viaProp || '';
}

// Chromium directory picker. Derive the chosen folder from the first file's
// absolute path minus its in-folder relative path.
$('folderInput').addEventListener('change', async (e) => {
  const files = e.target.files;
  const msg = $('settingsMsg');
  if (!files || !files.length) {
    // Empty folder selected — nothing to derive a path from.
    msg.className = 'ng';
    msg.textContent = t('settings.folderEmpty');
    e.target.value = '';
    return;
  }
  const file = files[0];
  const abs = absPath(file);
  const rel = file.webkitRelativePath || '';
  let folder = abs;
  if (abs && rel) {
    // abs ends with rel (separators differ but char counts match); strip the
    // relative tail and re-append the top-level chosen folder name.
    const top = rel.split('/')[0];
    folder = abs.slice(0, abs.length - rel.length) + top;
  }
  e.target.value = ''; // allow re-picking the same folder
  if (folder) {
    await setFolder(folder);
  } else {
    // Couldn't read the on-disk path — show exactly what the platform returned
    // so the failing API is visible instead of a generic error.
    msg.className = 'ng';
    msg.textContent = `n=${files.length} rel=[${rel}] ${lastDiag}`;
  }
});

// --- Drag & drop a folder (reliable fallback when the native dialog misbehaves) ---
// Electron exposes an absolute `path` on dropped File objects; a dropped folder
// arrives as a File with an empty type. We hand it to the main process to
// normalize (a dropped file → its parent folder) and to confirm it exists.
function preventDefaults(e) {
  e.preventDefault();
  e.stopPropagation();
}
// Stop the whole window from navigating away if a file is dropped outside the zone.
['dragover', 'drop'].forEach((evt) => window.addEventListener(evt, (e) => e.preventDefault()));

const dropZone = $('folderDrop');
['dragenter', 'dragover'].forEach((evt) =>
  dropZone.addEventListener(evt, (e) => {
    preventDefaults(e);
    dropZone.classList.add('drag');
  }),
);
['dragleave', 'drop'].forEach((evt) =>
  dropZone.addEventListener(evt, (e) => {
    preventDefaults(e);
    dropZone.classList.remove('drag');
  }),
);
function pathFromDrop(dt) {
  if (dt.files && dt.files.length) {
    const p = absPath(dt.files[0]);
    if (p) return p;
  }
  if (dt.items && dt.items.length) {
    for (const item of dt.items) {
      if (item.kind === 'file') {
        const p = absPath(item.getAsFile && item.getAsFile());
        if (p) return p;
      }
    }
  }
  return '';
}

dropZone.addEventListener('drop', async (e) => {
  const dropped = pathFromDrop(e.dataTransfer);
  if (!dropped) {
    $('settingsMsg').className = 'ng';
    $('settingsMsg').textContent = t('settings.folderMissing');
    return;
  }
  await setFolder(dropped); // normalizes a dropped file → its parent folder
});

$('save').addEventListener('click', async () => {
  const msg = $('settingsMsg');
  const server = $('serverUrl').value.trim();
  const token = $('deviceToken').value.trim();
  const folderInput = $('watchFolder').value.trim();
  if (!server || !token || !folderInput) {
    msg.className = 'ng';
    msg.textContent = t('settings.needAll');
    return;
  }
  // Normalize (strip "Copy as path" quotes) and confirm the folder exists before
  // saving, so a bad path fails loudly here instead of silently not watching.
  const check = await watcherApi.validateFolder(folderInput);
  if (!check.valid) {
    msg.className = 'ng';
    msg.textContent = t('settings.folderMissing');
    return;
  }
  const folder = check.path;
  $('watchFolder').value = folder;
  msg.className = '';
  msg.textContent = t('settings.testing');
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
  msg.textContent = ok ? t('settings.connOk') : t('settings.connFail');
  renderStatus(await watcherApi.getStatus());
});

init();
