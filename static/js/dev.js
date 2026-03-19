/**
 * Observer Console — Single consolidated JS file
 * Handles all API calls, WebSocket, polling, and DOM updates.
 * No dependencies. No frameworks. Just fetch() and getElementById().
 */

// ── Helpers ──────────────────────────────────────────────────────────
const API = '/api/v1';
const $ = id => document.getElementById(id);
function setText(id, v) { const el = $(id); if (el) el.textContent = v ?? '--'; }
function setDot(id, color) { const el = $(id); if (el) el.className = 'dot ' + color; }
function setBtn(id, on) {
    const el = $(id);
    if (!el) return;
    el.className = on ? 'on' : 'off';
    el.textContent = on ? 'ON' : 'OFF';
}
function shortTime(iso) {
    if (!iso) return '--';
    try { return new Date(iso).toISOString().replace('T', ' ').slice(0, 19) + ' UTC'; }
    catch { return iso; }
}

async function api(method, path, body) {
    try {
        const opts = { method, headers: { 'Content-Type': 'application/json' } };
        if (body !== undefined) opts.body = JSON.stringify(body);
        const r = await fetch(API + path, opts);
        if (!r.ok) return null;
        const text = await r.text();
        return text ? JSON.parse(text) : {};
    } catch (e) { console.warn('API error:', path, e); return null; }
}
const GET = path => api('GET', path);
const POST = (path, body) => api('POST', path, body);

let ws = null;
const sessionStart = Date.now();

// ── WebSocket ────────────────────────────────────────────────────────
function connectWS() {
    const wsProto = (location.protocol === 'https:') ? 'wss:' : 'ws:';
    ws = new WebSocket(`${wsProto}//${location.host}/ws`);
    ws.onopen = () => { setText('ws-status', 'ONLINE'); setDot('ws-dot', 'green'); };
    ws.onclose = () => { setText('ws-status', 'OFFLINE'); setDot('ws-dot', 'red'); setTimeout(connectWS, 3000); };
    ws.onerror = () => { setText('ws-status', 'ERROR'); setDot('ws-dot', 'red'); };
    ws.onmessage = (e) => {
        try {
            const msg = JSON.parse(e.data);
            if (msg.type === 'new_signals') fetchSignals();
        } catch {}
    };
}

// ── Clock / Session Timer ────────────────────────────────────────────
function updateClock() {
    const now = new Date();
    setText('clock', now.toISOString().slice(11, 19) + ' UTC');
    const elapsed = Math.floor((Date.now() - sessionStart) / 1000);
    const h = String(Math.floor(elapsed / 3600)).padStart(2, '0');
    const m = String(Math.floor((elapsed % 3600) / 60)).padStart(2, '0');
    const s = String(elapsed % 60).padStart(2, '0');
    setText('session-timer', `${h}:${m}:${s}`);
}

// ══════════════════════════════════════════════════════════════════════
// POLLING — runs every 30s
// ══════════════════════════════════════════════════════════════════════

async function pollAll() {
    await Promise.allSettled([
        pollSystem(),
        pollDB(),
        pollCollectors(),
        pollFeeds(),
        pollFeedSites(),
        pollScreening(),
        pollNLLB(),
    ]);
}

// ── System ───────────────────────────────────────────────────────────
async function pollSystem() {
    const [health, intel, metrics] = await Promise.allSettled([
        GET('/health'),
        GET('/intelligence?limit=1&offset=0'),
        GET('/metrics/ai'),
    ]);

    const h = health.value;
    if (h) {
        setText('sys-active-feeds', h.feeds?.enabled_groups ?? '--');
    }

    const i = intel.value;
    if (i) {
        const proc = i.articles_processed || 0;
        const rej = i.articles_rejected || 0;
        const total = proc + rej;
        setText('sys-total-feeds', i.pagination?.total_count ?? '--');
        setText('sys-accept-rate', total > 0 ? Math.round(proc / total * 100) + '%' : '--');
        setText('sys-errors', '0');
    }

    const m = metrics.value;
    if (m) {
        const rate = m.calls_per_minute ?? m.translations_per_minute ?? 0;
        setText('sys-translator', rate > 0 ? rate.toFixed(1) + '/min' : 'idle');
    }
}

// ── Database ─────────────────────────────────────────────────────────
async function pollDB() {
    const [details, cfg] = await Promise.allSettled([
        GET('/database/details'),
        GET('/database/config'),
    ]);
    const d = details.value;
    if (d) {
        setText('db-size', d.database?.size_pretty ?? '--');
        setText('db-signals', d.signals?.total ?? '--');
        setText('db-pool', d.pool ? `idle:${d.pool.idle} active:${d.pool.current - d.pool.idle} max:${d.pool.max}` : '--');
        setText('db-processed', d.signals?.processed ?? '--');
        setText('db-pending', d.signals?.unprocessed ?? '--');
        setText('db-oldest', shortTime(d.signals?.oldest));
        setText('db-newest', shortTime(d.signals?.newest));
    }
    const c = cfg.value;
    if (c && c.max_signals_limit) {
        $('db-max-input').value = c.max_signals_limit;
    }
}

// ── Collectors ───────────────────────────────────────────────────────
async function pollCollectors() {
    const d = await GET('/collectors');
    if (!d || !d.collectors) return;

    for (const c of d.collectors) {
        const name = c.name;
        const prefix = `coll-${name}`;
        const running = c.enabled && c.available;
        setDot(`${prefix}-dot`, running ? 'green' : c.enabled ? 'yellow' : 'gray');
        setText(`${prefix}-status`, running ? 'RUNNING' : c.enabled ? 'STARTING' : 'OFF');
        setText(`${prefix}-24h`, c.articles_24h ?? '--');
        setText(`${prefix}-errors`, c.errors_24h ?? c.errors ?? '0');
        setText(`${prefix}-last`, shortTime(c.last_collection ?? c.last_run));
        setBtn(`${prefix}-toggle`, c.enabled);
    }
}

// ── Feed Groups ─────────────────────────────────────────────────────
async function pollFeeds() {
    const [status, groups] = await Promise.allSettled([
        GET('/feeds/status'),
        GET('/feeds/groups'),
    ]);

    const s = status.value;
    if (s) {
        setText('fg-total', s.total_feeds ?? '--');
        setText('fg-enabled', s.total_enabled_feeds ?? '--');
        setText('fg-errors', s.feed_errors ?? '0');
        setText('fg-healthy', s.health_summary?.healthy_feeds ?? '--');
        setText('fg-processed', s.articles_processed ?? '--');
        setText('fg-rejected', s.articles_rejected ?? '--');
        const proc = s.articles_processed || 0;
        const rej = s.articles_rejected || 0;
        const total = proc + rej;
        setText('fg-accept', total > 0 ? Math.round(proc / total * 100) + '%' : '--');
    }

    const g = groups.value;
    if (g && g.groups) {
        const tbody = $('fg-body');
        tbody.innerHTML = '';
        for (const grp of g.groups) {
            const tr = document.createElement('tr');
            const isTier1 = grp.tier === 1;
            tr.innerHTML =
                `<td style="color:${isTier1 ? '#fa0' : '#888'}">${grp.tier}</td>` +
                `<td>${esc(grp.name)}${grp.description ? ' <span class="mute">(' + esc(grp.description) + ')</span>' : ''}</td>` +
                `<td>${grp.feed_count}</td>` +
                `<td>${isTier1 ? '<span class="mute">LOCKED</span>' : ''}</td>`;
            if (!isTier1) {
                const btn = document.createElement('button');
                btn.className = grp.currently_enabled ? 'on' : 'off';
                btn.textContent = grp.currently_enabled ? 'ON' : 'OFF';
                btn.onclick = async function() {
                    const isOn = this.classList.contains('on');
                    if (isOn) {
                        await POST('/feeds/groups/disable', { groups: [grp.name] });
                    } else {
                        await POST('/feeds/groups/enable', { groups: [grp.name] });
                    }
                    pollFeeds();
                };
                tr.lastChild.innerHTML = '';
                tr.lastChild.appendChild(btn);
            }
            tbody.appendChild(tr);
        }
        feedGroupCache = g.groups;
    }
}
let feedGroupCache = [];

// ── Feed Sites (unified RSS + Scraper) ──────────────────────────────
let feedSitesCache = [];

async function pollFeedSites() {
    const d = await GET('/feed-sites');
    if (!d) return;
    const stats = d.stats || {};
    setText('fs-total', stats.total ?? '--');
    setText('fs-rss', stats.rss ?? '--');
    setText('fs-scraper', stats.scraper ?? '--');
    setText('fs-enabled', stats.enabled ?? '--');

    feedSitesCache = d.sites || [];
    renderFeedSites();
}

function renderFeedSites() {
    const tbody = $('fs-body');
    tbody.innerHTML = '';
    const search = ($('fs-search')?.value || '').toLowerCase();
    const typeFilter = $('fs-type-filter')?.value || 'all';

    for (const site of feedSitesCache) {
        if (typeFilter !== 'all' && site.type !== typeFilter) continue;
        if (search) {
            const haystack = `${site.name} ${site.url} ${site.group} ${site.language}`.toLowerCase();
            if (!haystack.includes(search)) continue;
        }
        const tr = document.createElement('tr');
        const typeColor = site.type === 'rss' ? '#6af' : '#ca0';
        const typeLabel = site.type === 'rss' ? 'RSS' : 'Scrape';

        tr.innerHTML =
            `<td>${esc(site.name || '--')}</td>` +
            `<td style="max-width:280px;overflow:hidden;text-overflow:ellipsis">${esc(site.url || '--')}</td>` +
            `<td>${esc(site.group || '--')}</td>` +
            `<td style="color:${typeColor}">${typeLabel}</td>` +
            `<td>${esc(site.language || '--')}</td>` +
            `<td></td>` +
            `<td></td>`;

        // Toggle button
        const toggleBtn = document.createElement('button');
        toggleBtn.className = site.enabled ? 'on' : 'off';
        toggleBtn.textContent = site.enabled ? 'ON' : 'OFF';
        const siteGroup = site.group;
        const siteUrl = site.url;
        const siteType = site.type;
        toggleBtn.onclick = async function() {
            await POST('/feed-sites/toggle', { group: siteGroup, url: siteUrl, site_type: siteType });
            pollFeedSites();
        };
        tr.children[5].appendChild(toggleBtn);

        // Delete button
        const delBtn = document.createElement('button');
        delBtn.className = 'danger';
        delBtn.textContent = 'X';
        delBtn.onclick = async function() {
            if (!confirm(`Delete "${site.name}" from ${site.group}?`)) return;
            await POST('/feed-sites/delete', { group: siteGroup, url: siteUrl, site_type: siteType });
            pollFeedSites();
        };
        tr.children[6].appendChild(delBtn);

        tbody.appendChild(tr);
    }
}

// ── Screening ────────────────────────────────────────────────────────
async function pollScreening() {
    const d = await GET('/admin/screening/status');
    if (!d) return;
    const available = d.available;
    const sources = ['fbi', 'interpol', 'sanctions', 'opensanctions'];
    for (const s of sources) {
        setDot(`scr-${s}-dot`, available ? 'green' : 'gray');
        setText(`scr-${s}-status`, available ? 'Connected' : 'Off');
    }
    if (d.log_stats) {
        for (const [key, count] of Object.entries(d.log_stats)) {
            const el = $(`scr-${key}-hits`);
            if (el) el.textContent = count;
        }
    }
}

// ── NLLB ─────────────────────────────────────────────────────────────
async function pollNLLB() {
    const d = await GET('/admin/nllb/params');
    if (!d) return;
    if (d.device) $('nllb-device').value = d.device;
    if (d.compute_type) $('nllb-compute').value = d.compute_type;
    const p = d.params;
    if (p) {
        if (p.inter_threads != null) $('nllb-workers').value = p.inter_threads;
        if (p.intra_threads != null) $('nllb-cores').value = p.intra_threads;
        if (p.beam_size != null) $('nllb-beam').value = p.beam_size;
        if (p.length_penalty != null) $('nllb-lenpen').value = p.length_penalty;
        if (p.repetition_penalty != null) $('nllb-reppen').value = p.repetition_penalty;
        if (p.sampling_temperature != null) $('nllb-temp').value = p.sampling_temperature;
        if (p.sampling_topk != null) $('nllb-topk').value = p.sampling_topk;
        if (p.max_batch_size != null) $('nllb-batch').value = p.max_batch_size;
    }
}

// ══════════════════════════════════════════════════════════════════════
// ACTIONS — button/input event handlers
// ══════════════════════════════════════════════════════════════════════

// ── System ───────────────────────────────────────────────────────────
function initSystemActions() {
    $('restart-pipeline-btn').onclick = async () => {
        if (!confirm('Restart article pipeline?')) return;
        await POST('/admin/restart/pipeline');
    };
    $('restart-app-btn').onclick = async () => {
        if (!confirm('Restart entire app?')) return;
        await POST('/admin/restart/app');
    };
}

// ── Database ─────────────────────────────────────────────────────────
function initDBActions() {
    $('db-max-btn').onclick = async () => {
        const val = parseInt($('db-max-input').value);
        if (isNaN(val) || val < 100) return;
        await POST('/database/config', { max_signals_limit: val });
        pollDB();
    };
    $('db-backup-btn').onclick = async () => {
        $('db-backup-btn').textContent = 'Creating...';
        await POST('/database/backup');
        $('db-backup-btn').textContent = 'Backup';
        loadBackups();
    };
    $('db-restore-btn').onclick = async () => {
        const sel = $('db-restore-select');
        if (sel.style.display === 'none') {
            await loadBackups();
            sel.style.display = 'inline-block';
        } else if (sel.value) {
            if (!confirm(`Restore from ${sel.value}?`)) return;
            await POST('/database/restore', { filename: sel.value });
            sel.style.display = 'none';
            pollDB();
        }
    };
}

async function loadBackups() {
    const d = await GET('/database/backups');
    const sel = $('db-restore-select');
    sel.innerHTML = '<option value="">Select backup...</option>';
    if (d && d.backups) {
        for (const b of d.backups) {
            const opt = document.createElement('option');
            opt.value = b.filename;
            opt.textContent = `${b.filename} (${b.size_pretty})`;
            sel.appendChild(opt);
        }
    }
}

// ── Collectors ───────────────────────────────────────────────────────
function initCollectorActions() {
    for (const name of ['rss', 'np4k']) {
        $(`coll-${name}-toggle`).onclick = async function() {
            const isOn = this.classList.contains('on');
            await POST(`/collectors/${name}/${isOn ? 'disable' : 'enable'}`);
            pollCollectors();
        };
        $(`coll-${name}-collect`).onclick = async function() {
            this.textContent = '...';
            await POST(`/collectors/${name}/collect`);
            this.textContent = 'Collect';
            setTimeout(pollCollectors, 2000);
        };
    }
}

// ── Feed Groups ─────────────────────────────────────────────────────
const REGION_MAP = {
    ukraine: ['ukraine'],
    middle_east: ['middle_east'],
    asia: ['east_asia', 'south_asia', 'southeast_asia'],
    africa: ['africa'],
    americas: ['americas', 'latin_america'],
    caucasus_central_asia: ['caucasus_central_asia'],
};

function initFeedActions() {
    for (const btn of document.querySelectorAll('.region-btn')) {
        btn.onclick = async function() {
            const region = this.dataset.region;
            const groups = REGION_MAP[region] || [region];
            await POST('/feeds/groups/enable', { groups });
            pollFeeds();
        };
    }

    $('fg-reset-btn').onclick = async () => {
        if (!confirm('Reset feed groups to defaults?')) return;
        await POST('/feeds/reset');
        pollFeeds();
    };
}

// ── Feed Sites ──────────────────────────────────────────────────────
function initFeedSiteActions() {
    $('fs-search').oninput = renderFeedSites;
    $('fs-type-filter').onchange = renderFeedSites;
}

// ── Filters ──────────────────────────────────────────────────────────
function initFilterActions() {
    loadFilterStatus();

    $('filter-mode').onchange = async () => {
        await POST('/feeds/content-filter/mode', { mode: $('filter-mode').value });
    };

    $('filter-blacklist').onchange = async () => {
        await POST('/feeds/content-filter/select', { bl_file: $('filter-blacklist').value });
    };
    $('filter-whitelist').onchange = async () => {
        await POST('/feeds/content-filter/select', { wl_file: $('filter-whitelist').value });
    };

    $('filter-edit-btn').onclick = async () => {
        const file = $('filter-edit-file').value;
        if (!file) return;
        const d = await GET(`/admin/filter/content?filename=${encodeURIComponent(file)}`);
        if (d) {
            $('filter-editor').value = d.content || '';
            $('filter-editor-row').style.display = 'block';
        }
    };

    $('filter-save-btn').onclick = async () => {
        const file = $('filter-edit-file').value;
        const content = $('filter-editor').value;
        if (!file) return;
        const r = await POST('/admin/filter/content', { filename: file, content: content });
        setText('filter-save-status', r ? 'Saved!' : 'Error');
        setTimeout(() => setText('filter-save-status', ''), 3000);
    };
}

async function loadFilterStatus() {
    const d = await GET('/feeds/content-filter/status');
    if (!d) return;

    if (d.mode) $('filter-mode').value = d.mode;

    const blFiles = d.available_bl || [];
    populateSelect('filter-blacklist', blFiles, d.active_bl);

    const wlFiles = d.available_wl || [];
    populateSelect('filter-whitelist', wlFiles, d.active_wl);

    populateSelect('filter-edit-file', [...blFiles, ...wlFiles]);
}

function populateSelect(selId, items, activeValue) {
    const sel = $(selId);
    if (!sel) return;
    sel.innerHTML = '';
    for (const name of items) {
        const opt = document.createElement('option');
        opt.value = name; opt.textContent = name;
        if (name === activeValue) opt.selected = true;
        sel.appendChild(opt);
    }
}

// ── NLLB ─────────────────────────────────────────────────────────────
function initNLLBActions() {
    $('nllb-apply-btn').onclick = async () => {
        const body = buildNLLBParams();
        const r = await POST('/admin/nllb/params', body);
        setText('nllb-status', r ? 'Applied!' : 'Error');
        setTimeout(() => setText('nllb-status', ''), 3000);
    };
    $('nllb-save-btn').onclick = async () => {
        const body = buildNLLBParams();
        const r = await POST('/admin/nllb/model-params', body);
        setText('nllb-status', r ? 'Saved & restarting...' : 'Error');
        setTimeout(() => setText('nllb-status', ''), 5000);
    };
}

function buildNLLBParams() {
    return {
        device: $('nllb-device').value,
        compute_type: $('nllb-compute').value,
        inter_threads: parseInt($('nllb-workers').value),
        intra_threads: parseInt($('nllb-cores').value),
        beam_size: parseInt($('nllb-beam').value),
        length_penalty: parseFloat($('nllb-lenpen').value),
        repetition_penalty: parseFloat($('nllb-reppen').value),
        sampling_temperature: parseFloat($('nllb-temp').value),
        sampling_topk: parseInt($('nllb-topk').value),
        max_batch_size: parseInt($('nllb-batch').value),
    };
}

// ── Signals ──────────────────────────────────────────────────────────
let signalCache = [];

function initSignalActions() {
    $('sig-refresh-btn').onclick = fetchSignals;
    $('sig-time').onchange = fetchSignals;
    $('sig-search').oninput = renderSignals;
    fetchSignals();
}

async function fetchSignals() {
    const tw = $('sig-time').value;
    let params = 'limit=200&offset=0';
    if (tw !== 'all') params += `&time_window=${tw}`;
    const d = await GET(`/intelligence?${params}`);
    if (d && d.intel) {
        signalCache = d.intel;
        renderSignals();
    }
}

function renderSignals() {
    const tbody = $('sig-body');
    const search = ($('sig-search').value || '').toLowerCase();
    tbody.innerHTML = '';

    let shown = 0;
    const MAX_SIGNALS = 10;
    for (const s of signalCache) {
        if (shown >= MAX_SIGNALS) break;
        if (search) {
            const haystack = `${s.title || ''} ${s.source_name || ''} ${s.description || ''} ${s.geo_location || ''}`.toLowerCase();
            if (!haystack.includes(search)) continue;
        }
        const tr = document.createElement('tr');
        tr.innerHTML = `<td>${shortTime(s.created_at)}</td>` +
            `<td style="color:${scoreColor(s.analyst_score)}">${s.analyst_score ?? '--'}</td>` +
            `<td>${esc(s.source_name || '--')}</td>` +
            `<td>${esc(truncate(s.title || s.description || '--', 80))}</td>` +
            `<td>${esc(s.geo_location || '--')}</td>`;
        tbody.appendChild(tr);
        shown++;
    }
    setText('sig-count', shown);
}

function scoreColor(score) {
    if (score == null) return '#666';
    if (score >= 80) return '#f44';
    if (score >= 60) return '#fa0';
    if (score >= 40) return '#cc0';
    return '#4c4';
}

function truncate(s, n) { return s.length > n ? s.slice(0, n) + '...' : s; }
function esc(s) { const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }

// ══════════════════════════════════════════════════════════════════════
// INIT
// ══════════════════════════════════════════════════════════════════════
document.addEventListener('DOMContentLoaded', () => {
    connectWS();
    updateClock();
    setInterval(updateClock, 1000);

    // Wire up all action handlers
    initSystemActions();
    initDBActions();
    initCollectorActions();
    initFeedActions();
    initFeedSiteActions();
    initFilterActions();
    initNLLBActions();
    initSignalActions();

    // Initial poll + periodic refresh
    pollAll();
    setInterval(pollAll, 30000);
});
