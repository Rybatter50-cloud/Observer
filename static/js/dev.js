/**
 * RYBAT Dev Console — Single consolidated JS file
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
            if (msg.type === 'vt_scan_result') pollVT();
            if (msg.type === 'urlscan_result') pollUrlscan();
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
        pollAPIKeys(),
        pollVT(),
        pollUrlscan(),
        pollScreening(),
        pollOllama(),
        pollNLLB(),
        pollEmbeddings(),
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

// ── API Keys & Toggles (registry-driven) ────────────────────────────
async function pollAPIKeys() {
    const d = await GET('/apis');
    if (!d || !d.apis) return;
    renderAPIs(d.apis);
}

function renderAPIs(apis) {
    const keyed = apis.filter(a => a.category === 'keyed');
    const pub = apis.filter(a => a.category === 'public');

    // ── Keyed APIs ──
    const keyedBody = $('api-keyed-body');
    keyedBody.innerHTML = '';
    for (const api of keyed) {
        const color = api.enabled ? (api.has_key ? 'green' : 'yellow') : 'gray';
        const status = api.enabled ? (api.has_key ? 'Active' : 'No Key') : 'Off';
        const tr = document.createElement('tr');

        // Service + Status cells
        tr.innerHTML =
            `<td>${esc(api.display_name)}</td>` +
            `<td><span class="dot ${color}"></span>${status}</td>` +
            `<td><input type="password" placeholder="API key" style="width:180px" data-api="${api.name}"> ` +
            `<button class="api-key-save" data-api="${api.name}">Save</button></td>` +
            `<td></td>`;

        // Toggle button
        const btn = document.createElement('button');
        btn.className = api.enabled ? 'on' : 'off';
        btn.textContent = api.enabled ? 'ON' : 'OFF';
        const apiName = api.name;
        const wasOn = api.enabled;
        btn.onclick = async () => {
            await POST(`/apis/${apiName}/toggle`, { enabled: !wasOn });
            pollAPIKeys();
        };
        tr.lastChild.appendChild(btn);
        keyedBody.appendChild(tr);
    }

    // Wire key-save buttons (keyed table only)
    for (const btn of keyedBody.querySelectorAll('.api-key-save')) {
        btn.onclick = async function() {
            const name = this.dataset.api;
            const input = keyedBody.querySelector(`input[data-api="${name}"]`);
            if (!input || !input.value.trim()) return;
            await POST(`/apis/${name}/key`, { key: input.value.trim() });
            input.value = '';
            pollAPIKeys();
        };
    }

    // ── Public APIs ──
    const pubBody = $('api-public-body');
    pubBody.innerHTML = '';
    for (const api of pub) {
        const color = api.enabled ? 'green' : 'gray';
        const status = api.enabled ? 'Active' : 'Off';
        const tr = document.createElement('tr');
        tr.innerHTML =
            `<td>${esc(api.display_name)}</td>` +
            `<td><span class="dot ${color}"></span>${status}</td>` +
            `<td></td>`;

        const btn = document.createElement('button');
        btn.className = api.enabled ? 'on' : 'off';
        btn.textContent = api.enabled ? 'ON' : 'OFF';
        const apiName = api.name;
        const wasOn = api.enabled;
        btn.onclick = async () => {
            await POST(`/apis/${apiName}/toggle`, { enabled: !wasOn });
            pollAPIKeys();
        };
        tr.lastChild.appendChild(btn);
        pubBody.appendChild(tr);
    }
}

// ── VirusTotal ───────────────────────────────────────────────────────
async function pollVT() {
    const d = await GET('/virustotal/status');
    if (!d) return;
    const connected = d.connected && d.enabled;
    const running = d.scheduler_running && !d.scheduler_paused;
    setDot('vt-dot', connected ? (running ? 'green' : 'yellow') : 'gray');
    setText('vt-status', connected ? (running ? 'RUNNING' : (d.scheduler_paused ? 'PAUSED' : 'IDLE')) : 'DISCONNECTED');
    setText('vt-quota', `${d.quota_remaining ?? '--'} / ${d.quota_daily_limit ?? '--'} remaining (${d.quota_used_today ?? 0} used)`);
    setText('vt-progress', `${d.feeds_scanned ?? 0} / ${d.total_feeds ?? '--'} feeds`);
    setText('vt-current', d.current_feed ?? 'idle');
    setText('vt-last-scan', shortTime(d.last_scan_time));
    setText('vt-total-scans', d.total_scans ?? '--');
    setText('vt-threats', d.threats_found ?? '0');
    setBtn('vt-sched-toggle', running);
    if (d.warning_threshold) $('vt-warn-thresh').value = d.warning_threshold;
    if (d.auto_disable_threshold) $('vt-disable-thresh').value = d.auto_disable_threshold;
}

// ── urlscan.io ───────────────────────────────────────────────────────
async function pollUrlscan() {
    const d = await GET('/urlscan/status');
    if (!d) return;
    const connected = d.connected && d.enabled;
    const running = d.scheduler_running && !d.scheduler_paused;
    setDot('us-dot', connected ? (running ? 'green' : 'yellow') : 'gray');
    setText('us-status', connected ? (running ? 'RUNNING' : (d.scheduler_paused ? 'PAUSED' : 'IDLE')) : 'DISCONNECTED');
    setText('us-quota', `${d.quota_remaining ?? '--'} / ${d.quota_daily_limit ?? '--'} remaining (${d.quota_used_today ?? 0} used)`);
    setText('us-progress', `${d.feeds_scanned ?? 0} / ${d.total_feeds ?? '--'} feeds`);
    setText('us-current', d.current_feed ?? 'idle');
    setText('us-last-scan', shortTime(d.last_scan_time));
    setText('us-total-scans', d.total_scans ?? '--');
    setText('us-threats', d.threats_found ?? '0');
    setBtn('us-sched-toggle', running);
    if (d.warning_threshold) $('us-warn-thresh').value = d.warning_threshold;
    if (d.auto_disable_threshold) $('us-disable-thresh').value = d.auto_disable_threshold;
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
    // Stats from log_stats if available
    if (d.log_stats) {
        for (const [key, count] of Object.entries(d.log_stats)) {
            const el = $(`scr-${key}-hits`);
            if (el) el.textContent = count;
        }
    }
}

// ── Ollama ───────────────────────────────────────────────────────────
async function pollOllama() {
    const d = await GET('/admin/ollama/status');
    if (!d) return;
    setDot('ollama-dot', d.available ? 'green' : 'gray');
    setText('ollama-status', d.available ? `Connected (${d.configured_model})` : 'Disconnected');

    // Populate model dropdown: installed models + known profiles
    const select = $('ollama-model');
    if (select && d.installed_models && select.options.length <= 1) {
        select.innerHTML = '';
        const installed = d.installed_models || [];
        const profiles = d.model_profiles || [];
        // Merge: installed first, then profile names not yet listed
        const allModels = installed.slice();
        for (const p of profiles) {
            if (!allModels.includes(p.name)) allModels.push(p.name);
        }
        for (const m of allModels) {
            const opt = document.createElement('option');
            opt.value = m;
            const profile = profiles.find(p => p.name === m);
            const isInstalled = installed.includes(m);
            opt.textContent = profile
                ? `${profile.label} (${profile.parameters} · ${profile.vram})${isInstalled ? '' : ' [not installed]'}`
                : m;
            if (m === d.configured_model) opt.selected = true;
            select.appendChild(opt);
        }
    }

    // Populate config values
    if (d.config) {
        const c = d.config;
        $('ollama-temp').value = c.temperature ?? 0.7;
        $('ollama-topp').value = c.top_p ?? 0.9;
        $('ollama-topk').value = c.top_k ?? 40;
        $('ollama-ctx').value = c.num_ctx ?? 4096;
        $('ollama-maxtok').value = c.num_predict ?? 2048;
        $('ollama-repeat').value = c.repeat_penalty ?? 1.1;
        $('ollama-seed').value = c.seed ?? 0;
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

// ── Embeddings / Sentence Transformer ────────────────────────────────
async function pollEmbeddings() {
    const d = await GET('/admin/embeddings/config');
    if (!d) return;
    setDot('emb-dot', d.ready ? 'green' : d.enabled ? 'yellow' : 'gray');
    setText('emb-status', d.ready ? 'READY' : d.enabled ? (d.load_error ? 'ERROR' : 'LOADING') : 'OFF');
    setText('emb-model', d.model ?? '--');
    setText('emb-classifier', d.classifier_loaded ? 'Loaded' : 'Not loaded');
    setText('emb-labels', d.classifier_labels?.length ?? 0);
    const stats = d.stats || {};
    setText('emb-encodes', stats.encode_count ?? 0);
    setText('emb-dedup', stats.dedup_caught ?? 0);
    setText('emb-buffer', `${d.buffer_count ?? 0} / ${d.buffer_max ?? 500}`);
    setBtn('emb-toggle', d.enabled);
    if (d.dedup_threshold != null) $('emb-threshold').value = d.dedup_threshold;
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
    for (const name of ['rss', 'np4k', 'newsapi', 'wikirumours']) {
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
    // Region preset buttons
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

// ── API Keys (dynamic — no static init needed) ─────────────────────
function initAPIKeyActions() {
    // All wiring happens dynamically in renderAPIs() via pollAPIKeys()
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

    // Set current mode
    if (d.mode) $('filter-mode').value = d.mode;

    // Populate blacklist dropdown
    const blFiles = d.available_bl || [];
    populateSelect('filter-blacklist', blFiles, d.active_bl);

    // Populate whitelist dropdown
    const wlFiles = d.available_wl || [];
    populateSelect('filter-whitelist', wlFiles, d.active_wl);

    // Populate edit dropdown with all files
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

// ── VirusTotal ───────────────────────────────────────────────────────
function initVTActions() {
    $('vt-sched-toggle').onclick = async function() {
        const isOn = this.classList.contains('on');
        await POST(`/virustotal/scheduler/${isOn ? 'stop' : 'start'}`);
        setTimeout(pollVT, 1000);
    };

    $('vt-config-btn').onclick = async () => {
        await POST('/virustotal/config', {
            warning_threshold: parseInt($('vt-warn-thresh').value),
            auto_disable_threshold: parseInt($('vt-disable-thresh').value),
        });
    };

    $('vt-scan-btn').onclick = async () => {
        const url = $('vt-url-input').value.trim();
        if (!url) return;
        setText('vt-scan-result', 'Scanning...');
        const d = await POST('/virustotal/scan', { url });
        if (d) {
            const risk = d.risk_score ?? 0;
            const mal = d.malicious_count ?? 0;
            setText('vt-scan-result', `risk=${risk} malicious=${mal}/${d.total_engines ?? 0} ${d.error_msg || ''}`);
        } else {
            setText('vt-scan-result', 'Error');
        }
    };
}

// ── urlscan.io ───────────────────────────────────────────────────────
function initUrlscanActions() {
    $('us-sched-toggle').onclick = async function() {
        const isOn = this.classList.contains('on');
        await POST(`/urlscan/scheduler/${isOn ? 'stop' : 'start'}`);
        setTimeout(pollUrlscan, 1000);
    };

    $('us-config-btn').onclick = async () => {
        await POST('/urlscan/config', {
            warning_threshold: parseInt($('us-warn-thresh').value),
            auto_disable_threshold: parseInt($('us-disable-thresh').value),
        });
    };

    $('us-scan-btn').onclick = async () => {
        const url = $('us-url-input').value.trim();
        if (!url) return;
        setText('us-scan-result', 'Scanning...');
        const d = await POST('/urlscan/scan', { url });
        if (d) {
            const risk = d.risk_score ?? 0;
            setText('us-scan-result', `risk=${risk} malicious=${d.verdict_malicious ?? false} ${d.error_msg || ''}`);
        } else {
            setText('us-scan-result', 'Error');
        }
    };
}

// ── Ollama ───────────────────────────────────────────────────────────
function initOllamaActions() {
    $('ollama-apply-btn').onclick = async () => {
        const body = { config: {
            model: $('ollama-model').value,
            temperature: parseFloat($('ollama-temp').value),
            top_p: parseFloat($('ollama-topp').value),
            top_k: parseInt($('ollama-topk').value),
            num_ctx: parseInt($('ollama-ctx').value),
            num_predict: parseInt($('ollama-maxtok').value),
            repeat_penalty: parseFloat($('ollama-repeat').value),
            seed: parseInt($('ollama-seed').value),
            num_gpu: parseInt($('ollama-gpu').value),
            num_thread: parseInt($('ollama-threads').value),
        }};
        const r = await POST('/admin/ollama/config', body);
        setText('ollama-apply-status', r ? 'Applied!' : 'Error');
        setTimeout(() => setText('ollama-apply-status', ''), 3000);
    };
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

// ── Embeddings / Sentence Transformer ────────────────────────────────
function initEmbeddingsActions() {
    $('emb-toggle').onclick = async function() {
        const isOn = this.classList.contains('on');
        await POST('/admin/embeddings/config', { enabled: !isOn });
        pollEmbeddings();
    };

    $('emb-apply-btn').onclick = async () => {
        const thresh = parseFloat($('emb-threshold').value);
        if (isNaN(thresh) || thresh < 0 || thresh > 1) return;
        const r = await POST('/admin/embeddings/config', { dedup_threshold: thresh });
        setText('emb-action-status', r?.success ? 'Applied!' : 'Error');
        setTimeout(() => setText('emb-action-status', ''), 3000);
        pollEmbeddings();
    };

    $('emb-reload-btn').onclick = async () => {
        setText('emb-action-status', 'Reloading...');
        const r = await POST('/admin/embeddings/reload-classifier');
        setText('emb-action-status', r?.success ? 'Reloaded!' : 'Failed');
        setTimeout(() => setText('emb-action-status', ''), 3000);
        pollEmbeddings();
    };

    $('emb-clear-btn').onclick = async () => {
        const r = await POST('/admin/embeddings/clear-buffer');
        setText('emb-action-status', r?.success ? 'Buffer cleared' : 'Error');
        setTimeout(() => setText('emb-action-status', ''), 3000);
        pollEmbeddings();
    };
}

// ── Chat ─────────────────────────────────────────────────────────────
function initChatActions() {
    const input = $('chat-input');
    const log = $('chat-log');

    $('chat-send-btn').onclick = sendChat;
    input.onkeydown = (e) => { if (e.key === 'Enter') sendChat(); };

    $('chat-clear-btn').onclick = async () => {
        await POST('/chat/clear');
        log.innerHTML = '<span class="mute">Cleared.</span>';
    };

    function chatClearPlaceholder() {
        // Clear the initial placeholder if it's the only content
        if (log.children.length === 1 && log.children[0].classList.contains('mute')) {
            log.innerHTML = '';
        }
    }

    function chatAppend(cls, text) {
        chatClearPlaceholder();
        var el = document.createElement('div');
        el.className = cls;
        el.textContent = text;
        log.appendChild(el);
        log.scrollTop = log.scrollHeight;
        return el;
    }

    function chatAppendHtml(cls, html) {
        chatClearPlaceholder();
        var el = document.createElement('div');
        el.className = cls;
        el.innerHTML = html;
        log.appendChild(el);
        log.scrollTop = log.scrollHeight;
        return el;
    }

    function parseCmd(text) {
        const t = text.toLowerCase().trim();
        if (t === '/clear' || t === 'clear chat') return { type: 'clear' };
        if (t === '/status') return { type: 'status' };
        if (t === '/reset') return { type: 'reset' };
        if (t === '/feeds reset') return { type: 'feeds-reset' };
        if (t === '/feeds all') return { type: 'feeds-all' };
        if (t.startsWith('/discover ')) return { type: 'discover', arg: text.slice(10).trim() };
        if (t.startsWith('/filter append ')) {
            const rest = text.slice(15).trim();
            const m = rest.match(/^(\S+)\s+(.*)/);
            if (m) {
                const pats = [];
                const re = /"([^"]+)"|'([^']+)'|(\S+)/g;
                let mx;
                while ((mx = re.exec(m[2])) !== null) pats.push(mx[1] || mx[2] || mx[3]);
                return { type: 'append-filter', file: m[1], patterns: pats };
            }
        }
        if (t.startsWith('/filter ')) return { type: 'build-filter', arg: text.slice(8).trim() };
        if (t.startsWith('/feeds ')) return { type: 'manage-feeds', arg: text.slice(7).trim() };
        if (t.startsWith('/lang ')) return { type: 'filter-lang', arg: text.slice(6).trim() };
        if (t === '/units') return { type: 'units-list' };
        if (t.startsWith('/units search ')) return { type: 'units-search', arg: text.slice(14).trim() };
        if (t.startsWith('/units add ')) return { type: 'units-add', arg: text.slice(11).trim() };
        if (t.startsWith('/units remove ')) return { type: 'units-remove', arg: text.slice(14).trim() };
        if (t.startsWith('/units toggle ')) return { type: 'units-toggle', arg: text.slice(14).trim() };
        if (t.startsWith('/units group ')) return { type: 'units-group', arg: text.slice(13).trim() };
        const fm = t.match(/^(?:build|create|make|generate)\s+(?:a\s+)?filter\s+(?:for|about|on)\s+(.+)/);
        if (fm) return { type: 'build-filter', arg: fm[1].trim() };
        return null;
    }

    async function sendChat() {
        const msg = input.value.trim();
        if (!msg) return;
        input.value = '';
        chatAppend('chat-user', '> ' + msg);

        const cmd = parseCmd(msg);

        try {
            if (cmd) {
                switch (cmd.type) {
                    case 'clear':
                        await POST('/chat/clear');
                        await POST('/analyst/reset');
                        log.innerHTML = '<span class="mute">Cleared.</span>';
                        return;
                    case 'reset':
                        await POST('/analyst/reset');
                        chatAppend('chat-assistant', 'Analyst session reset.');
                        return;
                    case 'status': {
                        const d = await GET('/analyst/status');
                        if (d) {
                            let t = 'Analyst: ' + (d.available ? 'ONLINE' : 'OFFLINE');
                            if (d.model) t += '\nModel: ' + d.model;
                            if (d.model_loaded !== undefined) t += '\nLoaded: ' + (d.model_loaded ? 'yes' : 'no');
                            if (d.tools) t += '\nTools: ' + d.tools;
                            if (d.max_steps) t += '\nMax steps: ' + d.max_steps;
                            if (d.reason) t += '\nReason: ' + d.reason;
                            chatAppend('chat-assistant', t);
                        } else {
                            chatAppend('chat-error', 'Could not reach analyst status endpoint.');
                        }
                        return;
                    }
                    case 'discover':      await chatDiscover(cmd.arg); return;
                    case 'build-filter':   await chatBuildFilter(cmd.arg); return;
                    case 'append-filter':  await chatAppendFilter(cmd.file, cmd.patterns); return;
                    case 'manage-feeds':   await chatManageFeeds(cmd.arg); return;
                    case 'feeds-all':      await chatFeedsAll(); return;
                    case 'feeds-reset':    await chatFeedsReset(); return;
                    case 'filter-lang':    await chatFilterLang(cmd.arg); return;
                    case 'units-list':     await chatUnitsList(); return;
                    case 'units-search':   await chatUnitsSearch(cmd.arg); return;
                    case 'units-add':      await chatUnitsAdd(cmd.arg); return;
                    case 'units-remove':   await chatUnitsRemove(cmd.arg); return;
                    case 'units-toggle':   await chatUnitsToggle(cmd.arg); return;
                    case 'units-group':    await chatUnitsGroup(cmd.arg); return;
                }
            }

            // Send to analyst agent (ReAct loop with tool calls)
            setText('chat-status', 'analyzing...');
            const d = await POST('/analyst/query', { query: msg });
            setText('chat-status', '');

            if (d && d.report) {
                chatAppend('chat-assistant', d.report);
                // Show analysis metadata
                var meta = '[' + (d.tool_calls_made || 0) + ' tool calls';
                if (d.total_duration_ms) meta += ' | ' + Math.round(d.total_duration_ms / 1000) + 's';
                if (d.model) meta += ' | ' + d.model;
                meta += ']';
                chatAppend('chat-mute', meta);
                if (d.error) chatAppend('chat-error', d.error);
            } else {
                chatAppend('chat-error', (d && d.error) || (d && d.detail) || 'No response from analyst.');
            }
        } catch (err) {
            setText('chat-status', '');
            chatAppend('chat-error', 'Error: ' + err.message);
        }
    }

    // ── /discover <country> ─────────────────────────────────────────
    async function chatDiscover(country) {
        chatAppend('chat-assistant', 'Discovering feeds for: ' + country + '...\nThis may take 30-60 seconds (Gemini + RSS probing).');
        setText('chat-status', 'discovering...');

        var d;
        try {
            d = await POST('/chat/discover-feeds', { country: country });
        } catch (err) {
            setText('chat-status', '');
            chatAppend('chat-error', 'Network error: ' + err.message);
            return;
        }
        setText('chat-status', '');

        if (!d || !d.success) {
            chatAppend('chat-error', 'Discovery failed: ' + ((d && d.error) || 'no response from server'));
            return;
        }

        var rss = d.discovered || [];
        var scraper = d.scraper_sites || [];
        var skipped = d.skipped || [];
        var failed = d.failed || [];

        if (rss.length === 0 && scraper.length === 0) {
            chatAppend('chat-assistant', 'No feeds found for ' + country + '. ' + failed.length + ' outlets checked.');
            return;
        }

        // Build result with checkboxes
        var html = 'Found <b>' + rss.length + '</b> RSS + <b>' + scraper.length + '</b> Scraper sources in <b>' + esc(country) + '</b>';
        html += '<div style="margin:4px 0;max-height:180px;overflow-y:auto;white-space:normal">';

        if (rss.length > 0) {
            html += '<div style="color:#6af;margin:2px 0">RSS Feeds:</div>';
            for (var i = 0; i < rss.length; i++) {
                var f = rss[i];
                html += '<label style="display:block;color:#ccc"><input type="checkbox" checked data-idx="' + i + '" class="dcb-rss"> ' + esc(f.name) + ' <span class="mute">' + esc(f.domain) + ' [' + (f.rss_urls ? f.rss_urls.length : 0) + ' RSS]</span></label>';
            }
        }
        if (scraper.length > 0) {
            html += '<div style="color:#ca0;margin:2px 0">Scraper Sites (no RSS):</div>';
            for (var j = 0; j < scraper.length; j++) {
                var s = scraper[j];
                html += '<label style="display:block;color:#ccc"><input type="checkbox" checked data-idx="' + j + '" class="dcb-sc"> ' + esc(s.name) + ' <span class="mute">' + esc(s.domain) + '</span></label>';
            }
        }
        html += '</div>';

        if (skipped.length > 0) html += '<div class="mute">Skipped (already in registry): ' + esc(skipped.map(function(x) { return x.name; }).join(', ')) + '</div>';
        if (failed.length > 0) html += '<div class="mute">Failed: ' + esc(failed.map(function(x) { return x.name; }).join(', ')) + '</div>';

        var usage = d.gemini_usage;
        if (usage && typeof usage.remaining !== 'undefined') {
            html += '<div class="mute" style="margin-top:2px">' + usage.remaining + ' Gemini uses remaining today</div>';
        }

        html += '<div style="margin-top:4px"><button class="dc-add">Add Selected</button> <button class="dc-skip">Skip</button></div>';

        var el = chatAppendHtml('chat-assistant', html);

        el.querySelector('.dc-add').onclick = async function() {
            var cbs = el.querySelectorAll('.dcb-rss:checked');
            var selRss = [];
            for (var a = 0; a < cbs.length; a++) selRss.push(parseInt(cbs[a].getAttribute('data-idx')));
            var scCbs = el.querySelectorAll('.dcb-sc:checked');
            var selSc = [];
            for (var b = 0; b < scCbs.length; b++) selSc.push(parseInt(scCbs[b].getAttribute('data-idx')));
            if (selRss.length === 0 && selSc.length === 0) { chatAppend('chat-error', 'No sources selected.'); return; }
            var btns = el.querySelectorAll('button');
            for (var c = 0; c < btns.length; c++) btns[c].disabled = true;
            chatAppend('chat-assistant', 'Adding ' + (selRss.length + selSc.length) + ' sources...');
            setText('chat-status', 'saving...');
            var r = await POST('/chat/confirm-feeds', { selected: selRss, selected_scrapers: selSc });
            setText('chat-status', '');
            if (r && r.success) {
                var result = 'Added to "' + r.group + '":';
                if (r.added_count > 0) result += ' ' + r.added_count + ' RSS (' + r.added.join(', ') + ')';
                if (r.added_scraper_count > 0) result += ' ' + r.added_scraper_count + ' Scraper (' + r.added_scrapers.join(', ') + ')';
                chatAppend('chat-assistant', result);
                pollFeeds(); pollFeedSites();
            } else {
                chatAppend('chat-error', 'Confirm failed: ' + ((r && r.error) || 'unknown'));
            }
        };

        el.querySelector('.dc-skip').onclick = function() {
            var btns = el.querySelectorAll('button');
            for (var c = 0; c < btns.length; c++) btns[c].disabled = true;
            chatAppend('chat-assistant', 'Discovery results discarded.');
        };
    }

    // ── /filter <topic> ─────────────────────────────────────────────
    async function chatBuildFilter(topic) {
        chatAppend('chat-assistant', 'Generating filter for: ' + topic + '...');
        setText('chat-status', 'generating...');
        var name = topic.toLowerCase().replace(/[^a-z0-9]/g, '_').replace(/_+/g, '_').slice(0, 30).replace(/_$/, '');
        var d = await POST('/chat/build-filter', { topic: topic, name: name });
        setText('chat-status', '');
        if (d && d.success) {
            chatAppend('chat-assistant', 'Filter "' + d.filename + '" created with ' + d.valid + ' patterns. Available in Content Filter dropdown.');
        } else {
            chatAppend('chat-error', 'Filter failed: ' + ((d && d.error) || 'unknown'));
        }
    }

    // ── /filter append <file> "patterns..." ─────────────────────────
    async function chatAppendFilter(file, patterns) {
        chatAppend('chat-assistant', 'Appending ' + patterns.length + ' pattern(s) to ' + file + '...');
        var d = await POST('/chat/append-filter', { filename: file, patterns: patterns });
        if (d && d.success) {
            var msg = 'Appended ' + d.added + ' pattern(s) to ' + d.filename + '. Total: ' + d.total;
            if (d.duplicates > 0) msg += ' (' + d.duplicates + ' dupes skipped)';
            chatAppend('chat-assistant', msg);
        } else {
            chatAppend('chat-error', 'Append failed: ' + ((d && d.error) || 'unknown'));
        }
    }

    // ── /feeds <region> ─────────────────────────────────────────────
    async function chatManageFeeds(region) {
        chatAppend('chat-assistant', 'Matching feeds for: ' + region + '...');
        setText('chat-status', 'thinking...');
        var d = await POST('/chat/manage-feeds', { region: region });
        setText('chat-status', '');
        if (d && d.success) {
            var groups = (d.enabled || []).map(function(g) { return g.replace(/_/g, ' '); }).join(', ');
            chatAppend('chat-assistant', 'Feeds updated for "' + d.region + '": ' + d.enabled.length + ' groups enabled (' + d.enabled_feed_count + ' feeds), ' + d.disabled_count + ' disabled.\nGroups: ' + groups + '\nType /filter ' + region.toLowerCase() + ' to build a matching content filter, or /feeds reset to undo.');
            pollFeeds();
        } else {
            chatAppend('chat-error', 'Feed matching failed: ' + ((d && d.error) || 'unknown'));
        }
    }

    // ── /feeds all ──────────────────────────────────────────────────
    async function chatFeedsAll() {
        var d = await POST('/chat/enable-all-feeds');
        if (d && d.success) {
            chatAppend('chat-assistant', 'All feeds enabled: ' + d.enabled_count + ' feeds across ' + d.group_count + ' groups.');
            pollFeeds();
        } else {
            chatAppend('chat-error', 'Failed: ' + ((d && d.error) || 'unknown'));
        }
    }

    // ── /feeds reset ────────────────────────────────────────────────
    async function chatFeedsReset() {
        var d = await POST('/chat/reset-feeds');
        if (d && d.success) {
            chatAppend('chat-assistant', 'Feeds restored: ' + d.restored_feeds + ' feed states reset.');
            pollFeeds();
        } else {
            chatAppend('chat-error', 'Reset failed: ' + ((d && d.error) || 'unknown'));
        }
    }

    // ── /lang <code> ────────────────────────────────────────────────
    async function chatFilterLang(lang) {
        chatAppend('chat-assistant', 'Filtering feeds to language: ' + lang.toUpperCase() + '...');
        var d = await POST('/chat/filter-lang', { lang: lang });
        if (d && d.success) {
            var groups = (d.groups || []).map(function(g) { return g.replace(/_/g, ' '); }).join(', ');
            chatAppend('chat-assistant', 'Language: ' + d.lang.toUpperCase() + ' \u2014 ' + d.enabled_count + ' feeds enabled, ' + d.disabled_count + ' disabled.\nGroups: ' + groups + '\nType /feeds reset to undo.');
            pollFeeds();
        } else {
            chatAppend('chat-error', 'Language filter: ' + ((d && d.error) || 'unknown'));
        }
    }

    // ── /units ─────────────────────────────────────────────────────
    // DVIDS unit management commands

    async function chatUnitsList() {
        chatAppend('chat-assistant', 'Fetching DVIDS unit registry...');
        var d = await GET('/dvids/units');
        if (!d || !d.groups) {
            chatAppend('chat-error', 'Could not fetch DVIDS units.');
            return;
        }
        var lines = ['DVIDS Units: ' + d.total_units + ' tracked (' + d.total_enabled + ' enabled)', ''];
        var groups = d.groups;
        for (var gk in groups) {
            var g = groups[gk];
            var status = g.enabled ? 'ON' : 'OFF';
            lines.push('[' + status + '] ' + g.label + ' (' + gk + ') \u2014 ' + g.enabled_unit_count + '/' + g.unit_count + ' units enabled');
            for (var i = 0; i < g.units.length; i++) {
                var u = g.units[i];
                var uStatus = u.enabled ? '\u2713' : '\u2717';
                lines.push('  ' + uStatus + ' ' + u.unit_id + ': ' + u.unit_name + ' [' + u.branch + ']');
            }
            lines.push('');
        }
        lines.push('Commands: /units search <name>, /units add <group> <id>, /units remove <group> <id>');
        lines.push('/units toggle <group> <id>, /units group <group> on|off');
        chatAppend('chat-assistant', lines.join('\n'));
    }

    async function chatUnitsSearch(query) {
        // Parse optional branch filter: /units search branch:Army special forces
        var branch = '';
        var searchName = query;
        var branchMatch = query.match(/^branch:(\S+)\s*(.*)/i);
        if (branchMatch) {
            branch = branchMatch[1];
            searchName = branchMatch[2].trim();
        }

        chatAppend('chat-assistant', 'Searching DVIDS for: ' + (searchName || '(all)') + (branch ? ' [branch: ' + branch + ']' : '') + '...');
        var params = '?max_results=25';
        if (searchName) params += '&unit_name=' + encodeURIComponent(searchName);
        if (branch) params += '&branch=' + encodeURIComponent(branch);

        var d = await GET('/dvids/units/search' + params);
        if (!d || !d.results) {
            chatAppend('chat-error', 'DVIDS search failed. Is DVIDS_API_KEY configured?');
            return;
        }

        if (d.results.length === 0) {
            chatAppend('chat-assistant', 'No DVIDS units found for "' + query + '".');
            return;
        }

        var lines = ['Found ' + d.total_results + ' units' + (d.total_results > 25 ? ' (showing first 25)' : '') + ':', ''];
        for (var i = 0; i < d.results.length; i++) {
            var r = d.results[i];
            var tracked = r.tracked ? ' \u2605' : '';
            lines.push('  ' + r.id + ': ' + r.unit_name + ' [' + r.branch + '] (' + (r.unit_abbrev || '') + ')' + tracked);
        }
        lines.push('');
        lines.push('\u2605 = already tracked. Use /units add <group> <id> to add a unit.');
        chatAppend('chat-assistant', lines.join('\n'));
    }

    async function chatUnitsAdd(arg) {
        // /units add <group_key> <unit_id>
        var parts = arg.split(/\s+/);
        if (parts.length < 2) {
            chatAppend('chat-error', 'Usage: /units add <group_key> <unit_id>\nExample: /units add centcom 72');
            return;
        }
        var groupKey = parts[0];
        var unitId = parseInt(parts[1], 10);
        if (isNaN(unitId)) {
            chatAppend('chat-error', 'Invalid unit ID. Use /units search to find IDs.');
            return;
        }

        // First look up the unit name from DVIDS
        chatAppend('chat-assistant', 'Looking up unit ' + unitId + '...');
        var search = await GET('/dvids/units/search?unit_id=' + unitId);
        var unitName = 'Unit ' + unitId;
        var unitAbbrev = '';
        var branch = '';
        if (search && search.results && search.results.length > 0) {
            var found = search.results[0];
            unitName = found.unit_name || unitName;
            unitAbbrev = found.unit_abbrev || '';
            branch = found.branch || '';
        }

        var d = await POST('/dvids/units/add', {
            group_key: groupKey,
            unit_id: unitId,
            unit_name: unitName,
            unit_abbrev: unitAbbrev,
            branch: branch,
            enabled: true
        });

        if (d && d.success) {
            chatAppend('chat-assistant', 'Added: ' + unitName + ' [' + branch + '] to group "' + groupKey + '".');
        } else {
            chatAppend('chat-error', 'Add failed: ' + ((d && d.error) || 'unknown'));
        }
    }

    async function chatUnitsRemove(arg) {
        // /units remove <group_key> <unit_id>
        var parts = arg.split(/\s+/);
        if (parts.length < 2) {
            chatAppend('chat-error', 'Usage: /units remove <group_key> <unit_id>');
            return;
        }
        var d = await POST('/dvids/units/remove', {
            group_key: parts[0],
            unit_id: parseInt(parts[1], 10)
        });
        if (d && d.success) {
            chatAppend('chat-assistant', 'Removed unit ' + parts[1] + ' from "' + parts[0] + '".');
        } else {
            chatAppend('chat-error', 'Remove failed: ' + ((d && d.error) || 'unknown'));
        }
    }

    async function chatUnitsToggle(arg) {
        // /units toggle <group_key> <unit_id>
        var parts = arg.split(/\s+/);
        if (parts.length < 2) {
            chatAppend('chat-error', 'Usage: /units toggle <group_key> <unit_id>');
            return;
        }
        // Fetch current state to invert it
        var reg = await GET('/dvids/units');
        var currentEnabled = true;
        if (reg && reg.groups && reg.groups[parts[0]]) {
            var units = reg.groups[parts[0]].units || [];
            for (var i = 0; i < units.length; i++) {
                if (units[i].unit_id === parseInt(parts[1], 10)) {
                    currentEnabled = units[i].enabled;
                    break;
                }
            }
        }

        var d = await POST('/dvids/units/toggle', {
            group_key: parts[0],
            unit_id: parseInt(parts[1], 10),
            enabled: !currentEnabled
        });
        if (d && d.success) {
            chatAppend('chat-assistant', 'Unit ' + d.unit_id + ' in "' + parts[0] + '": ' + (d.enabled ? 'ENABLED' : 'DISABLED'));
        } else {
            chatAppend('chat-error', 'Toggle failed: ' + ((d && d.error) || 'unknown'));
        }
    }

    async function chatUnitsGroup(arg) {
        // /units group <group_key> on|off
        var parts = arg.split(/\s+/);
        if (parts.length < 2 || (parts[1] !== 'on' && parts[1] !== 'off')) {
            chatAppend('chat-error', 'Usage: /units group <group_key> on|off');
            return;
        }
        var enabled = parts[1] === 'on';
        var d = await POST('/dvids/groups/toggle', {
            group_key: parts[0],
            enabled: enabled
        });
        if (d && d.success) {
            chatAppend('chat-assistant', 'DVIDS group "' + d.group + '": ' + (d.enabled ? 'ENABLED' : 'DISABLED'));
        } else {
            chatAppend('chat-error', 'Group toggle failed: ' + ((d && d.error) || 'unknown'));
        }
    }
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
    initAPIKeyActions();
    initFilterActions();
    initVTActions();
    initUrlscanActions();
    initOllamaActions();
    initNLLBActions();
    initEmbeddingsActions();
    initChatActions();
    initSignalActions();

    // Initial poll + periodic refresh
    pollAll();
    setInterval(pollAll, 30000);
});
