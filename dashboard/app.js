/* ============================================================================
 * FreshMart Pipeline Control Center — dashboard logic
 *
 * Responsibilities
 * ----------------
 *  1. Role tab switching (Cashier / Manager / Vendor / Customer / HR / Ops / Kafka)
 *  2. Form submission → POST to /api/* endpoints (proxied to pos-simulator)
 *  3. Live-poll /api/stats and /api/recent/* every 4 seconds
 *  4. Health check the three core services (Kafka / Postgres / NiFi)
 *  5. Toast notifications for every action
 * ============================================================================ */

const API = '/api';                  // proxied through nginx → pos-simulator:9090
const POLL_MS = 4000;                // refresh cadence

// ─────────────────────────────────────────────────────────────────────────────
// Toast helper — IBM Carbon-style notification slide-in (bottom-right).
// ─────────────────────────────────────────────────────────────────────────────
function toast(msg, kind = 'success') {
  const colours = {
    success: 'border-ibm-green bg-ibm-green-light text-ibm-black',
    error:   'border-ibm-red bg-ibm-red-light text-ibm-black',
    info:    'border-ibm-blue bg-ibm-blue-light text-ibm-black',
  };
  const el = document.createElement('div');
  el.className = `border-l-4 ${colours[kind]} px-4 py-3 shadow-md mono text-xs flex items-start gap-3 animate-toast-in`;
  el.innerHTML = `<span class="font-bold uppercase">${kind}</span> <span class="flex-1">${msg}</span>`;
  document.getElementById('toast-stack').appendChild(el);
  setTimeout(() => el.remove(), 4500);
}

// ─────────────────────────────────────────────────────────────────────────────
// Generic JSON helpers
// ─────────────────────────────────────────────────────────────────────────────
async function postJSON(url, body) {
  const r = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  let data;
  try { data = await r.json(); } catch { data = null; }
  if (!r.ok) {
    // Surface structured validation errors from the backend
    const detail = data && data.errors ? data.errors.join('; ')
                 : data && data.error  ? data.error
                 : `HTTP ${r.status}`;
    const err = new Error(detail);
    err.status = r.status;
    err.detail = data;
    throw err;
  }
  return data;
}
async function getJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

// Convert <form> elements to a plain JSON object (numbers stay numbers).
function formToJson(form) {
  const data = {};
  new FormData(form).forEach((v, k) => {
    // coerce numeric fields
    if (!isNaN(v) && v !== '' && form.elements[k].type === 'number') data[k] = Number(v);
    else data[k] = v;
  });
  return data;
}

// ─────────────────────────────────────────────────────────────────────────────
// Role tab switching
// ─────────────────────────────────────────────────────────────────────────────
function switchRole(role) {
  document.querySelectorAll('.tab-btn').forEach(b =>
    b.classList.toggle('tab-active', b.dataset.role === role));
  document.querySelectorAll('.role-panel').forEach(p =>
    p.classList.toggle('hidden', p.dataset.panel !== role));
  // remember choice across reloads
  localStorage.setItem('fm-role', role);
}

document.getElementById('role-tabs').addEventListener('click', e => {
  const btn = e.target.closest('.tab-btn');
  if (btn) switchRole(btn.dataset.role);
});

// ─────────────────────────────────────────────────────────────────────────────
// Form handlers — one per workflow
// ─────────────────────────────────────────────────────────────────────────────

// Workflow 1 — single POS sale
document.getElementById('form-sale').addEventListener('submit', async e => {
  e.preventDefault();
  try {
    const r = await postJSON(`${API}/pos/sale`, formToJson(e.target));
    toast(`POS sale published to kafka.${r.kafka_topic}`, 'success');
    refreshAll();
  } catch (err) { toast(`Sale failed: ${err}`, 'error'); }
});

// Workflow 1 — bulk burst of random sales
document.getElementById('btn-bulk-sale').addEventListener('click', async () => {
  try {
    const r = await postJSON(`${API}/pos/sale/bulk`, { count: 25, store_id: 'FM-042' });
    toast(`Fired ${r.fired} random sales to pos-sales`, 'success');
    refreshAll();
  } catch (err) { toast(`Bulk failed: ${err}`, 'error'); }
});

// Workflow 2 — manager inventory sweep
document.getElementById('btn-inventory-check').addEventListener('click', async () => {
  try {
    const r = await postJSON(`${API}/inventory/check`, {});
    toast(`Inventory swept — ${r.triggered.length} reorders triggered`, 'info');
    refreshAll();
  } catch (err) { toast(`Sweep failed: ${err}`, 'error'); }
});

// Workflow 3 — vendor delivery
document.getElementById('form-delivery').addEventListener('submit', async e => {
  e.preventDefault();
  try {
    const r = await postJSON(`${API}/vendor/delivery`, formToJson(e.target));
    toast(`Vendor delivery → kafka.${r.topic}`, 'success');
    refreshAll();
  } catch (err) { toast(`Delivery failed: ${err}`, 'error'); }
});

// Workflow 6 — customer feedback
document.getElementById('form-feedback').addEventListener('submit', async e => {
  e.preventDefault();
  try {
    const r = await postJSON(`${API}/feedback`, formToJson(e.target));
    const kind = r.category === 'SAFETY' ? 'error' : 'info';
    toast(`Feedback classified as ${r.category}${r.payload.recall_triggered ? ' — RECALL TRIGGERED' : ''}`, kind);
    refreshAll();
  } catch (err) { toast(`Feedback failed: ${err}`, 'error'); }
});

// Workflow 6 — automated recall test (5 SAFETY feedbacks for one SKU)
document.getElementById('btn-recall-test').addEventListener('click', async () => {
  toast('Firing 5 SAFETY complaints to trigger recall...', 'info');
  for (let i = 0; i < 5; i++) {
    await postJSON(`${API}/feedback`, {
      store_id: 'FM-042',
      sku: 'MILK-WHOLE-1G',
      feedback_text: `Customer #${i+1} reports the milk was spoiled and made them sick.`,
    });
  }
  toast('Recall sequence complete — check product-recalls topic', 'error');
  refreshAll();
});

// Workflow 5 — HR weekly schedule notify
const hrForm = document.getElementById('form-hr');
hrForm.elements.week_start.value = new Date().toISOString().slice(0, 10);
hrForm.addEventListener('submit', async e => {
  e.preventDefault();
  try {
    const r = await postJSON(`${API}/schedule/notify`, formToJson(e.target));
    toast(`HR pushed ${r.notified} shift notifications`, 'success');
    refreshAll();
  } catch (err) { toast(`HR sync failed: ${err}`, 'error'); }
});

// Workflow 4 — planogram broadcast
document.getElementById('form-planogram').addEventListener('submit', async e => {
  e.preventDefault();
  try {
    const r = await postJSON(`${API}/planogram/sync`, formToJson(e.target));
    toast(`Planogram broadcast → kafka.${r.topic}`, 'success');
    refreshAll();
  } catch (err) { toast(`Broadcast failed: ${err}`, 'error'); }
});

// One-click full demo — sequentially fires every workflow
document.getElementById('btn-demo-all').addEventListener('click', async () => {
  toast('Demo: firing all 6 workflows in sequence...', 'info');
  try {
    await postJSON(`${API}/pos/sale/bulk`, { count: 20, store_id: 'FM-042' });
    await postJSON(`${API}/vendor/delivery`, { vendor_id: 'DOLE', sku: 'BAN-CAVENDISH-1LB', cases: 240, unit_cost: 0.28 });
    await postJSON(`${API}/inventory/check`, {});
    await postJSON(`${API}/planogram/sync`, { store_id: 'FM-042', sku: 'BAN-CAVENDISH-1LB', aisle: 'A07', section: 'PRODUCE-1', shelf_level: 2 });
    await postJSON(`${API}/schedule/notify`, { week_start: new Date().toISOString().slice(0,10) });
    await postJSON(`${API}/feedback`, { store_id: 'FM-042', sku: 'CHEESE-CHED-8OZ', feedback_text: 'Cheese was moldy and expired!' });
    toast('Demo complete — inspect Kafka topics and tables', 'success');
    refreshAll();
  } catch (err) { toast(`Demo failed: ${err}`, 'error'); }
});

// ─────────────────────────────────────────────────────────────────────────────
// Kafka inspector
// ─────────────────────────────────────────────────────────────────────────────
async function loadTopics() {
  try {
    const r = await getJSON(`${API}/topics`);
    const sel = document.getElementById('topic-select');
    sel.innerHTML = r.topics.length
      ? r.topics.map(t => `<option value="${t}">${t}</option>`).join('')
      : '<option>No topics yet — fire some events</option>';
  } catch (err) { console.error(err); }
}
document.getElementById('btn-refresh-topics').addEventListener('click', loadTopics);
document.getElementById('btn-peek').addEventListener('click', async () => {
  const topic = document.getElementById('topic-select').value;
  if (!topic) return;
  document.getElementById('topic-peek').textContent = `Peeking ${topic}...`;
  try {
    const r = await getJSON(`${API}/topics/${encodeURIComponent(topic)}/peek`);
    document.getElementById('topic-peek').textContent =
      r.messages?.length
        ? r.messages.map(m => `[p${m.partition} off:${m.offset}] ${m.value}`).join('\n\n')
        : `No recent messages on ${topic}.`;
  } catch (err) {
    document.getElementById('topic-peek').textContent = `Error: ${err}`;
  }
});

// ─────────────────────────────────────────────────────────────────────────────
// Live polling — stats, recent tables, health
// ─────────────────────────────────────────────────────────────────────────────
async function refreshStats() {
  try {
    const s = await getJSON(`${API}/stats`);
    ['sales','feedback','reorders','deliveries','recalls','events','low_stock'].forEach(k => {
      const el = document.getElementById(`stat-${k}`);
      if (el && s[k] !== undefined) el.textContent = s[k];
    });
  } catch { /* shown by health */ }
}

function renderRows(rows, mapFn) {
  if (!Array.isArray(rows) || rows.length === 0) {
    return '<div class="text-ibm-gray60">No events yet.</div>';
  }
  return rows.map(mapFn).join('');
}

async function refreshRecent() {
  try {
    const sales = await getJSON(`${API}/recent/sales`);
    document.getElementById('recent-sales').innerHTML = renderRows(sales, r =>
      `<div class="border-l-2 border-ibm-blue pl-2 py-1">
         <div class="text-ibm-black">${r.sku} × ${r.qty}</div>
         <div class="text-ibm-gray60 text-[10px]">${r.store_id} · ${r.emp_id ?? '—'} · $${Number(r.unit_price).toFixed(2)} · ${new Date(r.sale_ts).toLocaleTimeString()}</div>
       </div>`);
  } catch {}

  try {
    const reorders = await getJSON(`${API}/recent/reorders`);
    document.getElementById('recent-reorders').innerHTML = renderRows(reorders, r =>
      `<div class="border-l-2 border-ibm-yellow pl-2 py-1">
         <div class="text-ibm-black">${r.sku} — ${r.qty_ordered} cases</div>
         <div class="text-ibm-gray60 text-[10px]">${r.store_id} · vendor ${r.vendor_id ?? '—'} · ${new Date(r.ordered_at).toLocaleTimeString()}</div>
       </div>`);
  } catch {}

  try {
    const deliveries = await getJSON(`${API}/recent/deliveries`);
    document.getElementById('recent-deliveries').innerHTML = renderRows(deliveries, r =>
      `<div class="border-l-2 border-ibm-green pl-2 py-1">
         <div class="text-ibm-black">${r.sku} × ${r.cases}</div>
         <div class="text-ibm-gray60 text-[10px]">${r.vendor_id} · $${Number(r.unit_cost).toFixed(2)} · ${r.delivery_date}</div>
       </div>`);
  } catch {}

  try {
    const feedback = await getJSON(`${API}/recent/feedback`);
    document.getElementById('recent-feedback').innerHTML = renderRows(feedback, r => {
      const bar = r.recall_triggered ? 'border-ibm-red' : (r.category === 'SAFETY' ? 'border-ibm-yellow' : 'border-ibm-gray60');
      return `<div class="border-l-2 ${bar} pl-2 py-1">
         <div class="text-ibm-black">${r.sku} · <span class="text-ibm-gray60">[${r.category}]</span> ${r.recall_triggered ? '<span class="text-ibm-red font-bold">⚠ RECALL</span>' : ''}</div>
         <div class="text-ibm-gray60 text-[10px]">${r.store_id} · ${new Date(r.received_at).toLocaleTimeString()}</div>
         <div class="text-ibm-gray70 text-[11px] mt-1">${r.feedback_text}</div>
       </div>`;
    });
  } catch {}

  try {
    const events = await getJSON(`${API}/recent/events`);
    const html = renderRows(events, r =>
      `<div class="border-l-2 border-ibm-blue pl-2 py-1">
         <div class="text-ibm-black">${r.event_type} <span class="text-ibm-gray60 text-[10px]">via ${r.source ?? '—'}</span></div>
         <div class="text-ibm-gray60 text-[10px]">${new Date(r.created_at).toLocaleTimeString()}</div>
       </div>`);
    document.getElementById('recent-events').innerHTML = html;
    document.getElementById('recent-events-hr').innerHTML = html;
  } catch {}

  // Inventory table
  try {
    const inv = await getJSON(`${API}/recent/inventory`);
    const head = `<div class="grid grid-cols-5 gap-2 text-[10px] uppercase text-ibm-gray60 mb-2 pb-2 border-b border-ibm-gray20">
        <div>SKU</div><div>Store</div><div>Qty</div><div>Threshold</div><div>Status</div></div>`;
    const rows = inv.map(r => {
      const low = r.qty < r.reorder_threshold;
      return `<div class="grid grid-cols-5 gap-2 py-1 ${low ? 'bg-ibm-red-light' : ''}">
        <div class="truncate">${r.sku}</div>
        <div>${r.store_id}</div>
        <div>${r.qty}</div>
        <div>${r.reorder_threshold}</div>
        <div class="${low ? 'text-ibm-red font-bold' : 'text-ibm-green'}">${low ? 'LOW' : 'OK'}</div>
      </div>`;
    }).join('');
    document.getElementById('inventory-table').innerHTML = head + rows;
  } catch {}

  // Employee table (HR panel)
  try {
    const emps = await getJSON(`${API}/recent/employees`);
    const head = `<div class="grid grid-cols-4 gap-2 text-[10px] uppercase text-ibm-gray60 mb-2 pb-2 border-b border-ibm-gray20">
        <div>ID</div><div>Name</div><div>Role</div><div>Store</div></div>`;
    const rows = emps.map(r =>
      `<div class="grid grid-cols-4 gap-2 py-1">
         <div>${r.emp_id}</div>
         <div>${r.emp_name ?? ''}</div>
         <div class="text-ibm-blue">${r.role}</div>
         <div>${r.store_id ?? '—'}</div>
       </div>`).join('');
    document.getElementById('employee-table').innerHTML = head + rows;
  } catch {}
}

async function refreshHealth() {
  try {
    const h = await getJSON(`${API}/health`);
    document.getElementById('status-dot-kafka').className =
      'w-2 h-2 rounded-full live-dot ' + (h.kafka === 'up' ? 'bg-ibm-green' : 'bg-ibm-red');
    document.getElementById('status-dot-pg').className =
      'w-2 h-2 rounded-full live-dot ' + (h.postgres === 'up' ? 'bg-ibm-green' : 'bg-ibm-red');
  } catch {
    document.getElementById('status-dot-kafka').className = 'w-2 h-2 rounded-full live-dot bg-ibm-red';
    document.getElementById('status-dot-pg').className   = 'w-2 h-2 rounded-full live-dot bg-ibm-red';
  }
  // NiFi health — direct check (it's https + self-signed; we just try and let it tell us)
  try {
    await fetch('https://localhost:8443/nifi/', { mode: 'no-cors' });
    document.getElementById('status-dot-nifi').className = 'w-2 h-2 rounded-full live-dot bg-ibm-green';
  } catch {
    document.getElementById('status-dot-nifi').className = 'w-2 h-2 rounded-full live-dot bg-ibm-yellow';
  }
}

function refreshAll() { refreshStats(); refreshRecent(); }

// ─────────────────────────────────────────────────────────────────────────────
// Boot
// ─────────────────────────────────────────────────────────────────────────────
switchRole(localStorage.getItem('fm-role') || 'cashier');
refreshAll();
refreshHealth();
loadTopics();
setInterval(refreshAll, POLL_MS);
setInterval(refreshHealth, 10000);
