const apiBase = '';

const fileInput = document.getElementById('fileInput');
const useLLM = document.getElementById('useLLM');
const uploadForm = document.getElementById('uploadForm');
const historyList = document.getElementById('historyList');
const refreshHistory = document.getElementById('refreshHistory');
const viewLatestBtn = document.getElementById('viewLatestBtn');
const resultJson = document.getElementById('resultJson');
const downloadLink = document.getElementById('downloadLink');
const copyJsonBtn = document.getElementById('copyJsonBtn');
const clearResultBtn = document.getElementById('clearResultBtn');
const toggleFormatBtn = document.getElementById('toggleFormatBtn');
const pageFilter = document.getElementById('pageFilter');
const tableFilter = document.getElementById('tableFilter');
const searchInput = document.getElementById('searchInput');
const exportCsvBtn = document.getElementById('exportCsvBtn');
const exportAllZipBtn = document.getElementById('exportAllZipBtn');

let pretty = true;
let lastResult = null;
let currentResultId = null;
let searchDebounce = null;

function renderResult(obj) {
  lastResult = obj;
  if (!obj) {
    resultJson.textContent = '';
    return;
  }
  const filtered = buildFilteredView(obj);
  resultJson.textContent = pretty ? JSON.stringify(filtered, null, 2) : JSON.stringify(filtered);
}

function buildFilteredView(obj) {
  if (!obj || !obj.tables) return obj;
  const selectedPage = parseInt(pageFilter.value || '0', 10);
  const selectedTableIndex = parseInt(tableFilter.value || '-1', 10);
  const q = (searchInput.value || '').toLowerCase().trim();

  let tables = obj.tables;
  if (selectedPage) {
    tables = tables.filter(t => t.page === selectedPage);
  }
  if (selectedTableIndex >= 0) {
    tables = tables.filter(t => t.table_index === selectedTableIndex);
  }
  if (q) {
    tables = tables.filter(t => JSON.stringify(t).toLowerCase().includes(q));
  }
  return { ...obj, tables };
}

function populateFiltersFromResult(obj) {
  if (!obj || !obj.tables) {
    pageFilter.innerHTML = '';
    tableFilter.innerHTML = '';
    return;
  }
  const pages = Array.from(new Set(obj.tables.map(t => t.page))).sort((a,b)=>a-b);
  pageFilter.innerHTML = '<option value="0">All Pages</option>' + pages.map(p => `<option value="${p}">Page ${p}</option>`).join('');
  // default table list shows all for selected page or empty
  updateTableFilterOptions(obj);
}

function updateTableFilterOptions(obj) {
  if (!obj || !obj.tables) { tableFilter.innerHTML = ''; return; }
  const selectedPage = parseInt(pageFilter.value || '0', 10);
  let tables = obj.tables;
  if (selectedPage) tables = tables.filter(t => t.page === selectedPage);
  const indices = Array.from(new Set(tables.map(t => t.table_index))).sort((a,b)=>a-b);
  tableFilter.innerHTML = '<option value="-1">All Tables</option>' + indices.map(i => `<option value="${i}">Table ${i}</option>`).join('');
}

async function fetchHistory() {
  const res = await fetch(`${apiBase}/api/history`);
  const data = await res.json();
  historyList.innerHTML = '';
  data.forEach(item => {
    const li = document.createElement('li');
    li.className = 'py-3 flex items-center justify-between gap-4';
    li.innerHTML = `
      <div>
        <div class="font-medium text-slate-800">${item.filename}</div>
        <div class="muted">${new Date(item.created_at).toLocaleString()} • Tables: ${item.table_count} • LLM: ${item.use_llm ? 'Yes' : 'No'}</div>
      </div>
      <div class="flex items-center gap-2">
        <button class="btn btn-secondary viewBtn" data-id="${item.id}">View</button>
        <a class="btn btn-primary" href="${apiBase}/api/download/${item.id}.json">Download</a>
      </div>
    `;
    historyList.appendChild(li);
  });
  historyList.querySelectorAll('.viewBtn').forEach(btn => {
    btn.addEventListener('click', async (e) => {
      const id = e.currentTarget.getAttribute('data-id');
      const data = await fetchResult(id);
      renderResult(data);
      downloadLink.classList.remove('hidden');
      downloadLink.href = `${apiBase}/api/download/${id}.json`;
    });
  });
  return data;
}

async function fetchResult(id) {
  const res = await fetch(`${apiBase}/api/result/${id}`);
  const data = await res.json();
  currentResultId = id;
  populateFiltersFromResult(data);
  return data;
}

uploadForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  const file = fileInput.files[0];
  if (!file) return;

  const params = new URLSearchParams();
  params.set('use_llm', useLLM.checked ? 'true' : 'false');

  const form = new FormData();
  form.append('file', file);

  renderResult({ message: 'Uploading and extracting...' });

  try {
    const res = await fetch(`${apiBase}/api/upload?${params.toString()}`, {
      method: 'POST',
      body: form,
    });
    if (!res.ok) throw new Error('Upload failed');
    const info = await res.json();
    // Immediately fetch full result to populate filters and JSON view
    const data = await fetchResult(info.id);
    renderResult(data);
    downloadLink.classList.remove('hidden');
    downloadLink.href = `${apiBase}/api/download/${info.id}.json`;
    await fetchHistory();
  } catch (err) {
    renderResult({ error: err.message });
  }
});

refreshHistory.addEventListener('click', fetchHistory);

viewLatestBtn.addEventListener('click', async () => {
  const hist = await fetchHistory();
  if (hist && hist.length > 0) {
    const latest = hist[0];
    const data = await fetchResult(latest.id);
    renderResult(data);
    downloadLink.classList.remove('hidden');
    downloadLink.href = `${apiBase}/api/download/${latest.id}.json`;
  } else {
    renderResult({ info: 'No history yet. Upload a PDF to get started.' });
  }
});

copyJsonBtn.addEventListener('click', async () => {
  try {
    const text = resultJson.textContent || '';
    if (!text.trim()) return;
    await navigator.clipboard.writeText(text);
    copyJsonBtn.textContent = 'Copied';
    setTimeout(() => { copyJsonBtn.textContent = 'Copy JSON'; }, 1200);
  } catch {}
});

clearResultBtn.addEventListener('click', () => {
  renderResult(null);
  downloadLink.classList.add('hidden');
  downloadLink.href = '#';
});

toggleFormatBtn.addEventListener('click', () => {
  pretty = !pretty;
  toggleFormatBtn.textContent = pretty ? 'Pretty' : 'Compact';
  // re-render current
  renderResult(lastResult);
});

pageFilter.addEventListener('change', () => {
  updateTableFilterOptions(lastResult);
  renderResult(lastResult);
});

tableFilter.addEventListener('change', () => {
  renderResult(lastResult);
});

searchInput.addEventListener('input', () => {
  if (searchDebounce) clearTimeout(searchDebounce);
  searchDebounce = setTimeout(() => renderResult(lastResult), 200);
});

exportCsvBtn.addEventListener('click', () => {
  if (!currentResultId || !lastResult || !lastResult.tables) return;
  const page = parseInt(pageFilter.value || '0', 10);
  const ti = parseInt(tableFilter.value || '-1', 10);
  if (!page || ti < 0) {
    // require explicit page and table selection
    exportCsvBtn.textContent = 'Select Page & Table';
    setTimeout(() => { exportCsvBtn.textContent = 'Export CSV (Selected)'; }, 1200);
    return;
  }
  const url = `${apiBase}/api/export/${currentResultId}/table.csv?page=${page}&table_index=${ti}`;
  window.location.href = url;
});

exportAllZipBtn.addEventListener('click', () => {
  if (!currentResultId) return;
  const url = `${apiBase}/api/export/${currentResultId}/all.zip`;
  window.location.href = url;
});

// initial
fetchHistory();
