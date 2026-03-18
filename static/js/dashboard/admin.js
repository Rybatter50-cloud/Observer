/**
 * RYBAT Dashboard - Admin Control Panel
 * Collector config expand, filter editor, AI control mock, app controls
 */

// ==================== COLLECTOR CONFIG EXPAND ====================

var _collectorConfigs = {};

async function fetchCollectorConfigs() {
    try {
        var res = await fetch('/api/v1/admin/collectors/config');
        if (!res.ok) return;
        var data = await res.json();
        var collectors = data.collectors || [];
        for (var i = 0; i < collectors.length; i++) {
            _collectorConfigs[collectors[i].name] = collectors[i];
        }
        // Render config panels for each collector that has one
        renderCollectorConfigPanel('rss', 'rssConfigPanel');
        renderCollectorConfigPanel('np4k', 'np4kConfigPanel');
        renderCollectorConfigPanel('newsapi', 'newsapiConfigPanel');
        // Render inline stats from collector stats data
        renderCollectorSubStats('rss');
        renderCollectorSubStats('np4k');
        renderCollectorSubStats('newsapi');
    } catch (e) {
        console.error('[Admin] Error fetching collector configs:', e);
    }
}

function renderCollectorSubStats(name) {
    var el = document.getElementById(name + 'SubStats');
    if (!el) return;

    var cfg = _collectorConfigs[name];
    if (!cfg) { el.innerHTML = ''; return; }

    var stats = cfg.stats || {};
    var html = '';

    var articles = stats.articles_24h || 0;
    var errors = stats.errors_24h || 0;
    var lastRun = stats.last_collection;

    html += '<span class="collector-sub-stat-item">';
    html += '<span class="collector-sub-stat-label">24h:</span>';
    html += '<span class="collector-sub-stat-value' + (articles > 0 ? ' green' : '') + '">' + articles + '</span>';
    html += '</span>';

    if (errors > 0) {
        html += '<span class="collector-sub-stat-item">';
        html += '<span class="collector-sub-stat-label">err:</span>';
        html += '<span class="collector-sub-stat-value red">' + errors + '</span>';
        html += '</span>';
    }

    if (lastRun) {
        var ago = _formatAgo(lastRun);
        html += '<span class="collector-sub-stat-item">';
        html += '<span class="collector-sub-stat-label">last:</span>';
        html += '<span class="collector-sub-stat-value">' + ago + '</span>';
        html += '</span>';
    }

    el.innerHTML = html;
}

function _formatAgo(isoStr) {
    try {
        var diff = Date.now() - new Date(isoStr).getTime();
        var sec = Math.floor(diff / 1000);
        if (sec < 60) return sec + 's';
        var min = Math.floor(sec / 60);
        if (min < 60) return min + 'm';
        var hr = Math.floor(min / 60);
        return hr + 'h';
    } catch (e) {
        return '--';
    }
}

function toggleCollectorConfig(name, btnEl) {
    var panel = document.getElementById(name + 'ConfigPanel');
    if (!panel) return;

    var isVisible = panel.classList.contains('visible');
    panel.classList.toggle('visible');
    if (btnEl) {
        btnEl.classList.toggle('expanded');
        // Update arrow text
        btnEl.innerHTML = isVisible ? '&#9654; Config' : '&#9660; Config';
    }

    // Fetch config on first expand
    if (!isVisible && !_collectorConfigs[name]) {
        fetchCollectorConfigs();
    }
}

async function forceCollect(name) {
    var btn = event.target;
    if (btn) { btn.disabled = true; btn.textContent = '...'; }

    try {
        var res = await fetch('/api/v1/collectors/' + name + '/collect', { method: 'POST' });
        if (res.ok) {
            if (btn) { btn.textContent = 'OK'; }
            setTimeout(function() { if (btn) { btn.textContent = 'Collect'; btn.disabled = false; } }, 2000);
            // Refresh stats after a delay for the collection to produce results
            setTimeout(fetchCollectorConfigs, 5000);
        } else {
            var data = await res.json().catch(function() { return {}; });
            console.error('[Collector] Force collect failed:', data.detail || res.status);
            if (btn) { btn.textContent = 'Err'; }
            setTimeout(function() { if (btn) { btn.textContent = 'Collect'; btn.disabled = false; } }, 3000);
        }
    } catch (e) {
        console.error('[Collector] Force collect error:', e);
        if (btn) { btn.textContent = 'Err'; }
        setTimeout(function() { if (btn) { btn.textContent = 'Collect'; btn.disabled = false; } }, 3000);
    }
}

var _collectorEditorFields = {}; // { collectorName: [ {key, value, ...} ] }

function renderCollectorConfigPanel(name, panelId) {
    var panel = document.getElementById(panelId);
    if (!panel) return;

    // If we already have editable fields loaded, render them
    if (_collectorEditorFields[name]) {
        _renderInlineEditor(name, panel);
        return;
    }

    // Otherwise fetch from the env endpoint
    panel.innerHTML = '<span style="font-size:9px;color:var(--text-muted)">Loading settings...</span>';
    fetch('/api/v1/admin/collectors/env?collector=' + encodeURIComponent(name))
        .then(function(res) { return res.json(); })
        .then(function(data) {
            _collectorEditorFields[name] = data.fields || [];
            _renderInlineEditor(name, panel);
        })
        .catch(function(e) {
            panel.innerHTML = '<span style="font-size:9px;color:var(--warn-red)">Error loading</span>';
        });
}

function _renderInlineEditor(name, panel) {
    var fields = _collectorEditorFields[name] || [];
    if (fields.length === 0) {
        panel.innerHTML = '<span style="font-size:9px;color:var(--text-muted)">No settings</span>';
        return;
    }

    var html = '<div class="collector-inline-fields" data-collector="' + name + '">';
    for (var i = 0; i < fields.length; i++) {
        var f = fields[i];
        var fieldId = 'cif_' + name + '_' + f.key;
        html += '<div class="collector-inline-field">';
        html += '<label class="collector-inline-label" for="' + fieldId + '" title="' + _escHtml(f.key) + '">' + _escHtml(f.description) + '</label>';

        if (f.type === 'bool') {
            html += '<label class="toggle-switch collector-inline-toggle">';
            html += '<input type="checkbox" id="' + fieldId + '" data-key="' + _escHtml(f.key) + '"';
            html += (f.value === 'true' || f.value === 'True') ? ' checked' : '';
            html += '>';
            html += '<span class="toggle-slider"></span>';
            html += '</label>';
        } else if (f.type === 'select' && f.options) {
            html += '<select class="collector-inline-input" id="' + fieldId + '" data-key="' + _escHtml(f.key) + '">';
            for (var j = 0; j < f.options.length; j++) {
                html += '<option value="' + _escHtml(f.options[j]) + '"';
                html += f.value === f.options[j] ? ' selected' : '';
                html += '>' + _escHtml(f.options[j]) + '</option>';
            }
            html += '</select>';
        } else {
            html += '<input type="text" class="collector-inline-input" id="' + fieldId + '" data-key="' + _escHtml(f.key) + '" value="' + _escHtml(f.value) + '">';
        }

        html += '</div>';
    }
    html += '</div>';

    // Registry stats (from the config endpoint, if available)
    var cfg = _collectorConfigs[name];
    if (cfg) {
        var reg = cfg.registry || {};
        var regKeys = Object.keys(reg);
        if (regKeys.length > 0 && !reg.error) {
            html += '<div class="collector-registry-stats">';
            for (var k = 0; k < regKeys.length; k++) {
                var rk = regKeys[k];
                var label = rk.replace(/_/g, ' ').replace(/\btotal\b/i, '').trim();
                label = label.charAt(0).toUpperCase() + label.slice(1);
                html += '<div class="collector-registry-stat">';
                html += '<span class="collector-registry-stat-label">' + label + '</span>';
                html += '<span class="collector-registry-stat-value">' + reg[rk] + '</span>';
                html += '</div>';
            }
            html += '</div>';
        }
    }

    html += '<div class="collector-inline-actions">';
    html += '<button class="collector-inline-apply" onclick="applyCollectorSettings(\'' + name + '\')">Apply</button>';
    html += '<span class="collector-inline-status" id="cif_status_' + name + '"></span>';
    html += '</div>';

    panel.innerHTML = html;
}

async function applyCollectorSettings(name) {
    var statusEl = document.getElementById('cif_status_' + name);
    if (statusEl) { statusEl.textContent = 'Saving...'; statusEl.className = 'collector-inline-status'; }

    var container = document.querySelector('.collector-inline-fields[data-collector="' + name + '"]');
    if (!container) return;

    var values = {};
    var inputs = container.querySelectorAll('[data-key]');
    for (var i = 0; i < inputs.length; i++) {
        var el = inputs[i];
        var key = el.getAttribute('data-key');
        if (el.type === 'checkbox') {
            values[key] = el.checked ? 'true' : 'false';
        } else {
            values[key] = el.value;
        }
    }

    try {
        var res = await fetch('/api/v1/admin/collectors/env', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ collector: name, values: values }),
        });
        var data = await res.json();

        if (data.success) {
            // Update cached field values
            _collectorEditorFields[name] = null;
            // Refresh config display
            _collectorConfigs = {};
            fetchCollectorConfigs();
            if (statusEl) { statusEl.textContent = 'Saved'; statusEl.className = 'collector-inline-status success'; }
            setTimeout(function() { if (statusEl) statusEl.textContent = ''; }, 3000);
        } else {
            var errMsg = data.detail || (data.errors ? data.errors.join('; ') : 'Save failed');
            if (statusEl) { statusEl.textContent = errMsg; statusEl.className = 'collector-inline-status error'; }
        }
    } catch (e) {
        if (statusEl) { statusEl.textContent = 'Error: ' + e.message; statusEl.className = 'collector-inline-status error'; }
    }
}


// ==================== FILTER EDITOR ====================

var _filterEditorMode = 'text'; // 'text' or 'patterns'
var _filterEditorFile = '';
var _filterEditorType = ''; // 'bl' or 'wl'
var _filterEditorDirty = false;

function openFilterEditor() {
    var overlay = document.getElementById('filterEditorOverlay');
    if (!overlay) return;

    // Default to the currently active BL file
    _filterEditorType = 'bl';
    _filterEditorMode = 'text';
    _filterEditorDirty = false;

    // Populate file selector
    _populateFilterEditorFileSelect();

    // Set mode toggle state
    _setFilterEditorModeUI('text');

    overlay.classList.add('visible');

    // Load default file
    var select = document.getElementById('filterEditorFileSelect');
    if (select && select.value) {
        _filterEditorFile = select.value;
        loadFilterEditorContent(_filterEditorFile);
    }
}

function closeFilterEditor() {
    if (_filterEditorDirty) {
        if (!confirm('Discard unsaved changes?')) return;
    }
    var overlay = document.getElementById('filterEditorOverlay');
    if (overlay) overlay.classList.remove('visible');
    _filterEditorDirty = false;
}

function _populateFilterEditorFileSelect() {
    var select = document.getElementById('filterEditorFileSelect');
    if (!select) return;

    // Fetch current filter status to get available files
    fetch('/api/v1/feeds/content-filter/status')
        .then(function(res) { return res.json(); })
        .then(function(data) {
            select.innerHTML = '';

            // BL files
            var blFiles = data.available_bl || [];
            if (blFiles.length > 0) {
                var blGroup = document.createElement('optgroup');
                blGroup.label = 'Blacklist';
                for (var i = 0; i < blFiles.length; i++) {
                    var opt = document.createElement('option');
                    opt.value = blFiles[i];
                    opt.textContent = blFiles[i];
                    opt.setAttribute('data-type', 'bl');
                    if (blFiles[i] === data.active_bl) opt.selected = true;
                    blGroup.appendChild(opt);
                }
                select.appendChild(blGroup);
            }

            // WL files
            var wlFiles = data.available_wl || [];
            if (wlFiles.length > 0) {
                var wlGroup = document.createElement('optgroup');
                wlGroup.label = 'Whitelist';
                for (var j = 0; j < wlFiles.length; j++) {
                    var opt2 = document.createElement('option');
                    opt2.value = wlFiles[j];
                    opt2.textContent = wlFiles[j];
                    opt2.setAttribute('data-type', 'wl');
                    wlGroup.appendChild(opt2);
                }
                select.appendChild(wlGroup);
            }

            // Load the first selected file
            if (select.value) {
                _filterEditorFile = select.value;
                var selectedOpt = select.options[select.selectedIndex];
                _filterEditorType = selectedOpt.getAttribute('data-type') || 'bl';
                loadFilterEditorContent(select.value);
            }
        })
        .catch(function(e) {
            console.error('[Filter Editor] Error loading files:', e);
        });
}

function onFilterEditorFileChange() {
    var select = document.getElementById('filterEditorFileSelect');
    if (!select) return;

    if (_filterEditorDirty) {
        if (!confirm('Discard unsaved changes to current file?')) {
            select.value = _filterEditorFile;
            return;
        }
    }

    _filterEditorFile = select.value;
    var selectedOpt = select.options[select.selectedIndex];
    _filterEditorType = selectedOpt.getAttribute('data-type') || 'bl';
    _filterEditorDirty = false;
    loadFilterEditorContent(select.value);
}

function setFilterEditorMode(mode) {
    if (_filterEditorDirty) {
        // Save current content before switching modes
        _syncFilterEditorContent();
    }
    _filterEditorMode = mode;
    _setFilterEditorModeUI(mode);
    loadFilterEditorContent(_filterEditorFile);
}

function _setFilterEditorModeUI(mode) {
    var textBtn = document.getElementById('filterEditorModeText');
    var patternsBtn = document.getElementById('filterEditorModePatterns');
    var textArea = document.getElementById('filterEditorTextarea');
    var patternList = document.getElementById('filterPatternList');

    if (textBtn) textBtn.classList.toggle('active', mode === 'text');
    if (patternsBtn) patternsBtn.classList.toggle('active', mode === 'patterns');

    if (textArea) textArea.style.display = mode === 'text' ? 'block' : 'none';
    if (patternList) patternList.style.display = mode === 'patterns' ? 'block' : 'none';
}

async function loadFilterEditorContent(filename) {
    if (!filename) return;

    var statusEl = document.getElementById('filterEditorStatus');
    var countEl = document.getElementById('filterEditorCount');
    if (statusEl) statusEl.textContent = 'Loading...';

    try {
        if (_filterEditorMode === 'text') {
            var res = await fetch('/api/v1/admin/filter/content?filename=' + encodeURIComponent(filename));
            if (!res.ok) throw new Error('Failed to load filter');
            var data = await res.json();

            var textarea = document.getElementById('filterEditorTextarea');
            if (textarea) textarea.value = data.content;
            if (countEl) countEl.textContent = data.line_count + ' patterns';
            if (statusEl) statusEl.textContent = '';
        } else {
            var res2 = await fetch('/api/v1/admin/filter/patterns?filename=' + encodeURIComponent(filename));
            if (!res2.ok) throw new Error('Failed to load patterns');
            var data2 = await res2.json();

            renderPatternList(data2.patterns || []);
            if (countEl) countEl.textContent = data2.total + ' patterns';
            if (statusEl) statusEl.textContent = '';
        }
        _filterEditorDirty = false;
    } catch (e) {
        if (statusEl) {
            statusEl.textContent = 'Error: ' + e.message;
            statusEl.className = 'filter-editor-status error';
        }
    }
}

function renderPatternList(patterns) {
    var container = document.getElementById('filterPatternList');
    if (!container) return;

    var html = '';
    for (var i = 0; i < patterns.length; i++) {
        var p = patterns[i];
        var inputClass = 'filter-pattern-input' + (p.valid === false ? ' invalid' : '');
        html += '<div class="filter-pattern-item">';
        html += '<input type="text" class="' + inputClass + '" value="' + _escHtml(p.pattern) + '" onchange="markFilterEditorDirty()">';
        html += '<button class="filter-pattern-remove" onclick="removeFilterPattern(this)" title="Remove">&times;</button>';
        html += '</div>';
    }

    html += '<div class="filter-pattern-add-row">';
    html += '<button class="filter-pattern-add-btn" onclick="addFilterPattern()">+ Add Pattern</button>';
    html += '</div>';

    container.innerHTML = html;
}

function addFilterPattern() {
    var container = document.getElementById('filterPatternList');
    if (!container) return;

    var addRow = container.querySelector('.filter-pattern-add-row');
    var item = document.createElement('div');
    item.className = 'filter-pattern-item';
    item.innerHTML = '<input type="text" class="filter-pattern-input" value="" placeholder="\\bkeyword\\b" onchange="markFilterEditorDirty()">' +
        '<button class="filter-pattern-remove" onclick="removeFilterPattern(this)" title="Remove">&times;</button>';

    container.insertBefore(item, addRow);
    item.querySelector('input').focus();
    markFilterEditorDirty();
}

function removeFilterPattern(btn) {
    var item = btn.parentElement;
    if (item) item.remove();
    markFilterEditorDirty();
}

function markFilterEditorDirty() {
    _filterEditorDirty = true;
    var statusEl = document.getElementById('filterEditorStatus');
    if (statusEl) {
        statusEl.textContent = 'Unsaved changes';
        statusEl.className = 'filter-editor-status';
    }
}

function _syncFilterEditorContent() {
    // Placeholder - syncing between modes not needed since we re-fetch on mode switch
}

async function saveFilterEditor() {
    var statusEl = document.getElementById('filterEditorStatus');
    if (statusEl) {
        statusEl.textContent = 'Saving...';
        statusEl.className = 'filter-editor-status';
    }

    try {
        var body;
        var url;

        if (_filterEditorMode === 'text') {
            var textarea = document.getElementById('filterEditorTextarea');
            if (!textarea) return;
            url = '/api/v1/admin/filter/content';
            body = JSON.stringify({
                filename: _filterEditorFile,
                content: textarea.value,
            });
        } else {
            var inputs = document.querySelectorAll('#filterPatternList .filter-pattern-input');
            var patterns = [];
            for (var i = 0; i < inputs.length; i++) {
                var val = inputs[i].value.trim();
                if (val) patterns.push(val);
            }
            url = '/api/v1/admin/filter/patterns';
            body = JSON.stringify({
                filename: _filterEditorFile,
                patterns: patterns,
            });
        }

        var res = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: body,
        });

        var data = await res.json();

        if (data.success) {
            _filterEditorDirty = false;
            var countEl = document.getElementById('filterEditorCount');
            if (countEl) countEl.textContent = data.valid_patterns + ' patterns';

            var errMsg = '';
            if (data.errors && data.errors.length > 0) {
                errMsg = ' (' + data.errors.length + ' warnings)';
            }

            if (statusEl) {
                statusEl.textContent = 'Saved! ' + data.valid_patterns + ' patterns' + errMsg;
                statusEl.className = 'filter-editor-status success';
            }

            // Refresh the content filter status in the sidebar
            if (typeof fetchContentFilterStatus === 'function') {
                fetchContentFilterStatus();
            }
        } else {
            if (statusEl) {
                statusEl.textContent = data.detail || 'Save failed';
                statusEl.className = 'filter-editor-status error';
            }
        }
    } catch (e) {
        if (statusEl) {
            statusEl.textContent = 'Error: ' + e.message;
            statusEl.className = 'filter-editor-status error';
        }
    }
}


// ==================== AI CONTROL (OLLAMA) ====================

var _ollamaStatus = null;

// All config param keys (must match id="ollamaCfg_{key}" in HTML)
var _ollamaParamKeys = [
    'temperature', 'top_p', 'top_k', 'num_ctx', 'num_predict',
    'repeat_penalty', 'repeat_last_n', 'tfs_z',
    'mirostat', 'mirostat_tau', 'mirostat_eta',
    'seed', 'stop', 'num_thread', 'num_gpu',
];

async function fetchOllamaConfig() {
    try {
        var res = await fetch('/api/v1/admin/ollama/status');
        if (!res.ok) return;
        _ollamaStatus = await res.json();
        renderOllamaConfig();
    } catch (e) {
        console.error('[Admin] Error fetching Ollama status:', e);
    }
}

function renderOllamaConfig() {
    if (!_ollamaStatus) return;

    // Connection badge
    var badge = document.getElementById('ollamaConnBadge');
    if (badge) {
        if (_ollamaStatus.available) {
            badge.textContent = 'Connected';
            badge.className = 'ollama-conn-badge connected';
        } else {
            badge.textContent = 'Offline';
            badge.className = 'ollama-conn-badge offline';
        }
    }

    // Populate model selector: installed models + profile fallbacks
    var modelSelect = document.getElementById('ollamaModelSelect');
    if (modelSelect) {
        modelSelect.innerHTML = '';
        var installed = _ollamaStatus.installed_models || [];
        var profiles = _ollamaStatus.model_profiles || [];

        // Merge: installed first, then profile names not in installed
        var allModels = installed.slice();
        for (var i = 0; i < profiles.length; i++) {
            if (allModels.indexOf(profiles[i].name) === -1) allModels.push(profiles[i].name);
        }

        for (var j = 0; j < allModels.length; j++) {
            var mName = allModels[j];
            var opt = document.createElement('option');
            opt.value = mName;
            // Find profile metadata if available
            var profile = null;
            for (var k = 0; k < profiles.length; k++) {
                if (profiles[k].name === mName) { profile = profiles[k]; break; }
            }
            opt.textContent = profile
                ? profile.label + '  (' + profile.parameters + ' · ' + profile.vram + ')'
                : mName;
            if (mName === _ollamaStatus.configured_model) opt.selected = true;
            modelSelect.appendChild(opt);
        }
    }

    // Populate all config fields
    var cfg = _ollamaStatus.config || {};
    for (var p = 0; p < _ollamaParamKeys.length; p++) {
        var key = _ollamaParamKeys[p];
        var el = document.getElementById('ollamaCfg_' + key);
        if (el && cfg[key] !== undefined) {
            if (el.tagName === 'SELECT') {
                el.value = String(cfg[key]);
            } else {
                el.value = cfg[key];
            }
        }
    }
}

async function applyOllamaConfig() {
    var statusEl = document.getElementById('ollamaConfigStatus');
    if (statusEl) { statusEl.textContent = 'Saving...'; statusEl.className = 'collector-inline-status'; }

    var configObj = {};
    var modelSelect = document.getElementById('ollamaModelSelect');
    if (modelSelect) configObj.model = modelSelect.value;

    for (var i = 0; i < _ollamaParamKeys.length; i++) {
        var key = _ollamaParamKeys[i];
        var el = document.getElementById('ollamaCfg_' + key);
        if (el) configObj[key] = el.value;
    }

    try {
        var res = await fetch('/api/v1/admin/ollama/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ config: configObj }),
        });
        var data = await res.json();

        if (data.success) {
            if (statusEl) { statusEl.textContent = 'Saved'; statusEl.className = 'collector-inline-status success'; }
            setTimeout(function() { if (statusEl) statusEl.textContent = ''; }, 3000);
        } else {
            var errMsg = data.detail || 'Save failed';
            if (statusEl) { statusEl.textContent = errMsg; statusEl.className = 'collector-inline-status error'; }
        }
    } catch (e) {
        if (statusEl) { statusEl.textContent = 'Error: ' + e.message; statusEl.className = 'collector-inline-status error'; }
    }
}


// ==================== APP CONTROLS ====================

async function restartPipeline() {
    var btn = document.getElementById('restartPipelineBtn');
    var statusEl = document.getElementById('appControlStatus');

    if (btn) { btn.disabled = true; btn.textContent = 'Restarting...'; }
    if (statusEl) { statusEl.textContent = 'Restarting pipeline...'; statusEl.className = 'app-control-status'; }

    try {
        var res = await fetch('/api/v1/admin/restart/pipeline', { method: 'POST' });
        var data = await res.json();

        if (data.success) {
            if (statusEl) {
                statusEl.textContent = 'Pipeline restarted';
                statusEl.className = 'app-control-status success';
            }
        } else {
            if (statusEl) {
                statusEl.textContent = data.detail || 'Restart failed';
                statusEl.className = 'app-control-status error';
            }
        }
    } catch (e) {
        if (statusEl) {
            statusEl.textContent = 'Error: ' + e.message;
            statusEl.className = 'app-control-status error';
        }
    } finally {
        if (btn) { btn.disabled = false; btn.textContent = 'Pipeline'; }
    }
}

async function restartApp() {
    if (!confirm('Restart the entire RYBAT application?\n\nThe page will reload automatically.')) return;

    var btn = document.getElementById('restartAppBtn');
    var statusEl = document.getElementById('appControlStatus');

    if (btn) { btn.disabled = true; btn.textContent = 'Restarting...'; }
    if (statusEl) { statusEl.textContent = 'Restarting app...'; statusEl.className = 'app-control-status'; }

    try {
        await fetch('/api/v1/admin/restart/app', { method: 'POST' });
        if (statusEl) {
            statusEl.textContent = 'Restart initiated, reloading...';
            statusEl.className = 'app-control-status success';
        }
        // Auto-reload after a short delay
        setTimeout(function() { location.reload(); }, 3000);
    } catch (e) {
        // Connection may drop during restart - that's expected
        if (statusEl) {
            statusEl.textContent = 'Restarting, reloading...';
            statusEl.className = 'app-control-status success';
        }
        setTimeout(function() { location.reload(); }, 3000);
    }
}


// ==================== SCREENING ====================

async function fetchScreeningStatus() {
    try {
        var res = await fetch('/api/v1/admin/screening/status');
        if (!res.ok) return;
        var data = await res.json();
        renderScreeningSourceDots(data);
        renderScreeningStats(data);
    } catch (e) {
        console.error('[Admin] Error fetching screening status:', e);
    }
}

function _setScreeningDot(dotId, statusId, available, label) {
    var dot = document.getElementById(dotId);
    var status = document.getElementById(statusId);
    if (dot) {
        if (available === 'loading') {
            dot.className = 'screening-source-dot loading';
        } else if (available) {
            dot.className = 'screening-source-dot green';
        } else {
            dot.className = 'screening-source-dot red';
        }
    }
    if (status) {
        status.textContent = label;
    }
}

function renderScreeningSourceDots(data) {
    var sources = data.sources || {};

    // FBI — echo the API
    var fbi = sources.fbi || {};
    _setScreeningDot('screenFbiDot', 'screenFbiStatus',
        fbi.available !== false, fbi.available !== false ? 'Connected' : 'Error');

    // Interpol — gray if disabled, red/green if enabled
    var interpol = sources.interpol || {};
    if (interpol.enabled === false) {
        _setScreeningDot('screenInterpolDot', 'screenInterpolStatus', false, 'Disabled');
        var dot = document.getElementById('screenInterpolDot');
        if (dot) dot.className = 'screening-source-dot gray';
    } else {
        _setScreeningDot('screenInterpolDot', 'screenInterpolStatus',
            interpol.available !== false, interpol.available !== false ? 'Connected' : 'Error');
    }

    // Sanctions Network — echo the API
    var sn = sources.sanctions_network || {};
    _setScreeningDot('screenSanctionsNetDot', 'screenSanctionsNetStatus',
        sn.available !== false, sn.available !== false ? 'Connected' : 'Error');

    // OpenSanctions — CSV/DB, show loading state
    var os = sources.opensanctions || {};
    if (os.entities_in_db > 0) {
        _setScreeningDot('screenOpenSancDot', 'screenOpenSancStatus',
            true, os.entities_in_db.toLocaleString() + ' entities');
    } else if (os.enabled !== false) {
        _setScreeningDot('screenOpenSancDot', 'screenOpenSancStatus',
            'loading', 'Loading CSV...');
    } else {
        _setScreeningDot('screenOpenSancDot', 'screenOpenSancStatus',
            false, 'Not loaded');
    }
}

function renderScreeningStats(data) {
    var el = document.getElementById('screeningStatsContent');
    if (!el) return;

    var html = '';
    var logStats = data.log_stats || {};
    var total = logStats.total || data.total_screens || 0;

    html += _screeningRow('Total Checks', total.toLocaleString());

    el.innerHTML = html;
}

function _screeningRow(label, value) {
    return '<div class="screening-stat-row">' +
        '<span class="screening-stat-label">' + label + '</span>' +
        '<span class="screening-stat-value">' + value + '</span>' +
        '</div>';
}


// ==================== SCREENING REPORT DIALOG ====================

var _lastReportParams = null;

function openReportDialog() {
    var overlay = document.getElementById('reportOverlay');
    if (!overlay) return;

    // Default date range: last 7 days
    var end = new Date();
    var start = new Date();
    start.setDate(start.getDate() - 7);
    document.getElementById('reportDateStart').value = start.toISOString().split('T')[0];
    document.getElementById('reportDateEnd').value = end.toISOString().split('T')[0];

    document.getElementById('reportResults').innerHTML = '';
    document.getElementById('reportExportBtn').style.display = 'none';
    var statusEl = document.getElementById('reportStatus');
    if (statusEl) statusEl.textContent = '';

    overlay.classList.add('visible');
}

function closeReportDialog() {
    var overlay = document.getElementById('reportOverlay');
    if (overlay) overlay.classList.remove('visible');
}

async function generateReport() {
    var statusEl = document.getElementById('reportStatus');
    var resultsEl = document.getElementById('reportResults');
    var exportBtn = document.getElementById('reportExportBtn');
    if (statusEl) { statusEl.textContent = 'Generating...'; statusEl.className = 'report-status'; }
    if (resultsEl) resultsEl.innerHTML = '';
    if (exportBtn) exportBtn.style.display = 'none';

    var sources = [];
    var checkboxes = document.querySelectorAll('.report-checkbox input:checked');
    for (var i = 0; i < checkboxes.length; i++) sources.push(checkboxes[i].value);

    var format = 'summary';
    var radios = document.querySelectorAll('input[name="reportFormat"]');
    for (var j = 0; j < radios.length; j++) { if (radios[j].checked) format = radios[j].value; }

    _lastReportParams = {
        date_start: document.getElementById('reportDateStart').value,
        date_end: document.getElementById('reportDateEnd').value,
        sources: sources,
        format: format,
    };

    try {
        var res = await fetch('/api/v1/screening/report', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(_lastReportParams),
        });
        var data = await res.json();

        if (!res.ok) {
            if (statusEl) { statusEl.textContent = data.detail || 'Error'; statusEl.className = 'report-status error'; }
            return;
        }

        _renderReportResults(data, format, resultsEl);
        if (statusEl) { statusEl.textContent = ''; }
        if (exportBtn) exportBtn.style.display = 'inline-block';
    } catch (e) {
        if (statusEl) { statusEl.textContent = 'Error: ' + e.message; statusEl.className = 'report-status error'; }
    }
}

function _renderReportResults(data, format, container) {
    if (!container) return;
    var html = '';

    // Summary stats
    html += '<div class="report-summary-grid">';
    html += '<div class="report-summary-stat"><span class="report-stat-val">' + (data.total_checks || 0) + '</span><span class="report-stat-label">Total Checks</span></div>';
    html += '<div class="report-summary-stat"><span class="report-stat-val">' + (data.total_hits || 0) + '</span><span class="report-stat-label">Total Hits</span></div>';
    html += '<div class="report-summary-stat"><span class="report-stat-val">' + (data.unique_names || 0) + '</span><span class="report-stat-label">Unique Names</span></div>';
    html += '<div class="report-summary-stat"><span class="report-stat-val">' + (data.unique_ips || 0) + '</span><span class="report-stat-label">Unique IPs</span></div>';
    html += '</div>';

    // Source breakdown
    var bySource = data.by_source || {};
    var srcKeys = Object.keys(bySource);
    if (srcKeys.length > 0) {
        html += '<div class="report-section-label">By Source</div>';
        html += '<div class="report-source-grid">';
        for (var i = 0; i < srcKeys.length; i++) {
            html += '<div class="report-source-item"><span class="report-source-name">' + _escHtml(srcKeys[i]) + '</span>';
            html += '<span class="report-source-val">' + bySource[srcKeys[i]] + '</span></div>';
        }
        html += '</div>';
    }

    // Detailed entries table
    if (format === 'detailed' && data.entries && data.entries.length > 0) {
        html += '<div class="report-section-label">Entries (' + data.entries.length + ')</div>';
        html += '<div class="report-entries-wrap"><table class="report-entries-table">';
        html += '<thead><tr><th>Time</th><th>Name</th><th>Hits</th><th>Sources</th><th>IP</th></tr></thead><tbody>';
        for (var j = 0; j < data.entries.length; j++) {
            var e = data.entries[j];
            var hitCls = e.hit_count > 0 ? 'report-hit-pos' : '';
            html += '<tr>';
            html += '<td>' + _escHtml(e.created_at || '') + '</td>';
            html += '<td>' + _escHtml(e.queried_name || '') + '</td>';
            html += '<td class="' + hitCls + '">' + e.hit_count + '</td>';
            html += '<td>' + _escHtml(e.sources_checked || '') + '</td>';
            html += '<td>' + _escHtml(e.client_ip || '') + '</td>';
            html += '</tr>';
        }
        html += '</tbody></table></div>';
    }

    container.innerHTML = html;
}

async function exportReportCSV() {
    if (!_lastReportParams) return;
    var params = new URLSearchParams({
        date_start: _lastReportParams.date_start,
        date_end: _lastReportParams.date_end,
        sources: _lastReportParams.sources.join(','),
    });
    window.open('/api/v1/screening/report/export?' + params.toString(), '_blank');
}


// ==================== BROADCAST CONTROL (MOCK) ====================

function sendBroadcast() {
    // Mock — not connected
    var statusEl = document.getElementById('bcastUplinkStatus');
    if (statusEl) {
        statusEl.innerHTML = '<span class="bcast-uplink-icon pulse">&#9678;</span><span>TRANSMITTING... <span class="bcast-fail">FAILED</span> — No uplink configured</span>';
        setTimeout(function() {
            statusEl.innerHTML = '<span class="bcast-uplink-icon">&#9678;</span><span>UPLINK STANDBY &mdash; No satellite link established</span>';
        }, 3000);
    }
}

function openReportScheduler() {
    var panel = document.getElementById('bcastSchedulerPanel');
    if (panel) {
        panel.style.display = panel.style.display === 'none' ? 'block' : 'block';
        // Auto-expand if collapsed
        var body = document.getElementById('bcastSchedulerBody');
        if (body && body.style.maxHeight === '0px') {
            toggleSchedulerPanel();
        }
    }
}

var _schedulerOpen = false;

function toggleSchedulerPanel() {
    _schedulerOpen = !_schedulerOpen;
    var body = document.getElementById('bcastSchedulerBody');
    var arrow = document.getElementById('bcastSchedulerArrow');
    if (body) {
        if (_schedulerOpen) {
            body.style.maxHeight = body.scrollHeight + 'px';
            if (arrow) arrow.classList.add('open');
        } else {
            body.style.maxHeight = '0';
            if (arrow) arrow.classList.remove('open');
        }
    }
}


// ==================== EMBEDDINGS / SENTENCE-TRANSFORMER CONTROLS ====================

var _embConfig = null;
var _embTrainingRunning = false;

async function fetchEmbeddingsConfig() {
    try {
        var res = await fetch('/api/v1/admin/embeddings/config');
        if (!res.ok) return;
        _embConfig = await res.json();
        renderEmbeddingsPanel(_embConfig);
    } catch (e) {
        console.error('[Admin] Error fetching embeddings config:', e);
    }
}

function renderEmbeddingsPanel(cfg) {
    var el = document.getElementById('embeddingsContent');
    if (!el) return;

    // Update header badge — show Loading when enabled but model still warming up
    var badge = document.getElementById('embStatusBadge');
    if (badge) {
        if (cfg.enabled && cfg.ready) {
            badge.textContent = 'Active';
            badge.className = 'transformer-status-badge active';
        } else if (cfg.load_error) {
            badge.textContent = 'Error';
            badge.className = 'transformer-status-badge inactive';
        } else if (cfg.enabled && !cfg.ready) {
            badge.textContent = 'Loading';
            badge.className = 'transformer-status-badge loading';
        } else {
            badge.textContent = 'Off';
            badge.className = 'transformer-status-badge inactive';
        }
    }

    var stats = cfg.stats || {};
    var html = '';

    // Row 1: Enable toggle + Model
    html += '<div class="emb-row">';
    html += '<div class="emb-field">';
    html += '<span class="emb-label">Enabled</span>';
    html += '<label class="toggle-switch"><input type="checkbox" id="embEnabledToggle" ' + (cfg.enabled ? 'checked' : '') + '><span class="toggle-slider"></span></label>';
    html += '</div>';
    html += '<div class="emb-field">';
    html += '<span class="emb-label">Model</span>';
    html += '<span class="emb-value-mono">' + (cfg.model || 'all-MiniLM-L6-v2') + '</span>';
    html += '</div>';
    html += '<div class="emb-field">';
    html += '<span class="emb-label">Load Time</span>';
    html += '<span class="emb-value-mono">' + (cfg.load_time_ms || 0) + ' ms</span>';
    html += '</div>';
    html += '</div>';

    // Row 2: Dedup threshold + Buffer
    html += '<div class="emb-row">';
    html += '<div class="emb-field">';
    html += '<span class="emb-label">Dedup Threshold</span>';
    html += '<input type="text" class="emb-input" id="embDedupThreshold" value="' + (cfg.dedup_threshold || 0.88) + '" inputmode="decimal" pattern="[0-9.]*">';
    html += '</div>';
    html += '<div class="emb-field">';
    html += '<span class="emb-label">Dedup Buffer</span>';
    html += '<span class="emb-value-mono">' + (cfg.buffer_count || 0) + ' / ' + (cfg.buffer_max || 500) + '</span>';
    html += '<button class="emb-btn-sm" onclick="clearEmbeddingsBuffer()" title="Clear ring buffer">Clear</button>';
    html += '</div>';
    html += '</div>';

    // Row 3: Classifier + Stats
    html += '<div class="emb-row">';
    html += '<div class="emb-field">';
    html += '<span class="emb-label">Classifier</span>';
    if (cfg.classifier_loaded) {
        html += '<span class="emb-value-mono emb-clf-ok">' + (cfg.classifier_labels || []).length + ' labels: ' + (cfg.classifier_labels || []).join(', ') + '</span>';
    } else {
        html += '<span class="emb-value-mono emb-clf-none">Not loaded</span>';
    }
    html += '<button class="emb-btn-sm" onclick="reloadEmbeddingsClassifier()">Reload</button>';
    html += '</div>';
    html += '<div class="emb-field">';
    html += '<span class="emb-label">Stats</span>';
    html += '<span class="emb-value-mono">' + (stats.encode_count || 0).toLocaleString() + ' encodes &middot; ' + (stats.dedup_caught || 0) + ' dupes &middot; ' + (stats.classify_count || 0) + ' classified</span>';
    html += '</div>';
    html += '</div>';

    // Actions row: Apply + Train
    html += '<div class="emb-actions">';
    html += '<button class="emb-apply-btn" onclick="applyEmbeddingsConfig()">Apply</button>';
    html += '<button class="emb-train-btn" onclick="openTrainClassifierModal()">Train Classifier</button>';
    html += '<span class="emb-apply-status" id="embApplyStatus"></span>';
    html += '</div>';

    if (cfg.load_error) {
        html += '<div class="emb-error">' + cfg.load_error + '</div>';
    }

    el.innerHTML = html;
}

async function applyEmbeddingsConfig() {
    var statusEl = document.getElementById('embApplyStatus');
    var enabled = document.getElementById('embEnabledToggle');
    var threshold = document.getElementById('embDedupThreshold');

    var payload = {};
    if (enabled) payload.enabled = enabled.checked;
    if (threshold) payload.dedup_threshold = parseFloat(threshold.value);

    try {
        if (statusEl) { statusEl.textContent = 'Saving...'; statusEl.className = 'emb-apply-status'; }
        var res = await fetch('/api/v1/admin/embeddings/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        var data = await res.json();
        if (data.success) {
            if (statusEl) { statusEl.textContent = 'Saved'; statusEl.className = 'emb-apply-status ok'; }
            setTimeout(fetchEmbeddingsConfig, 500);
        } else {
            if (statusEl) { statusEl.textContent = data.message || 'Error'; statusEl.className = 'emb-apply-status err'; }
        }
    } catch (e) {
        if (statusEl) { statusEl.textContent = 'Failed'; statusEl.className = 'emb-apply-status err'; }
    }
    setTimeout(function() { if (statusEl) statusEl.textContent = ''; }, 3000);
}

async function reloadEmbeddingsClassifier() {
    try {
        var res = await fetch('/api/v1/admin/embeddings/reload-classifier', { method: 'POST' });
        var data = await res.json();
        if (data.success) {
            fetchEmbeddingsConfig();
        } else {
            alert('Classifier reload failed: ' + (data.message || 'unknown'));
        }
    } catch (e) {
        alert('Classifier reload error: ' + e.message);
    }
}

async function clearEmbeddingsBuffer() {
    try {
        var res = await fetch('/api/v1/admin/embeddings/clear-buffer', { method: 'POST' });
        var data = await res.json();
        if (data.success) {
            fetchEmbeddingsConfig();
        }
    } catch (e) {
        console.error('[Admin] Error clearing buffer:', e);
    }
}


// ==================== CLASSIFIER TRAINING MODAL ====================

function openTrainClassifierModal() {
    var overlay = document.getElementById('trainClassifierOverlay');
    if (!overlay) return;

    // Pre-populate from current config
    var model = (_embConfig && _embConfig.model) ? _embConfig.model : 'all-MiniLM-L6-v2';
    var output = (_embConfig && _embConfig.classifier_path) ? _embConfig.classifier_path : 'models/classifier.pkl';

    var modelInput = document.getElementById('trainModel');
    var outputInput = document.getElementById('trainOutput');
    var minSamplesInput = document.getElementById('trainMinSamples');
    var previewInput = document.getElementById('trainPreview');
    var statsCheck = document.getElementById('trainStats');
    var backfillCheck = document.getElementById('trainBackfill');
    var minConfInput = document.getElementById('trainMinConfidence');
    var confRow = document.getElementById('trainConfRow');
    var logEl = document.getElementById('trainLog');
    var runBtn = document.getElementById('trainRunBtn');

    if (modelInput) modelInput.value = model;
    if (outputInput) outputInput.value = output;
    if (minSamplesInput) minSamplesInput.value = '20';
    if (previewInput) previewInput.value = '20';
    if (statsCheck) statsCheck.checked = false;
    if (backfillCheck) backfillCheck.checked = false;
    if (minConfInput) minConfInput.value = '0.75';
    if (confRow) confRow.style.display = 'none';
    if (logEl) { logEl.textContent = ''; logEl.style.display = 'none'; }
    if (runBtn) { runBtn.disabled = false; runBtn.textContent = 'Run Training'; }

    overlay.classList.add('visible');
}

function closeTrainClassifierModal() {
    if (_embTrainingRunning) {
        if (!confirm('Training is still running. Close anyway? (it will continue in the background)')) return;
    }
    var overlay = document.getElementById('trainClassifierOverlay');
    if (overlay) overlay.classList.remove('visible');
}

function onBackfillToggle() {
    var backfillCheck = document.getElementById('trainBackfill');
    var confRow = document.getElementById('trainConfRow');
    if (confRow) {
        confRow.style.display = (backfillCheck && backfillCheck.checked) ? 'flex' : 'none';
    }
}

async function runTrainClassifier() {
    var modelInput = document.getElementById('trainModel');
    var outputInput = document.getElementById('trainOutput');
    var minSamplesInput = document.getElementById('trainMinSamples');
    var previewInput = document.getElementById('trainPreview');
    var statsCheck = document.getElementById('trainStats');
    var backfillCheck = document.getElementById('trainBackfill');
    var minConfInput = document.getElementById('trainMinConfidence');
    var logEl = document.getElementById('trainLog');
    var runBtn = document.getElementById('trainRunBtn');

    // Build payload
    var payload = {
        model: modelInput ? modelInput.value.trim() : 'all-MiniLM-L6-v2',
        output: outputInput ? outputInput.value.trim() : 'models/classifier.pkl',
        min_samples: minSamplesInput ? parseInt(minSamplesInput.value) || 20 : 20,
        preview: previewInput ? parseInt(previewInput.value) || 20 : 20,
        stats: statsCheck ? statsCheck.checked : false,
        backfill: backfillCheck ? backfillCheck.checked : false,
    };

    // Enforce min-confidence >= 0.75 when backfill is on
    if (payload.backfill) {
        var conf = minConfInput ? parseFloat(minConfInput.value) : 0.75;
        if (isNaN(conf) || conf < 0.75) {
            alert('Minimum confidence for backfill must be at least 0.75');
            return;
        }
        payload.min_confidence = conf;
    }

    // Validate min_samples
    if (payload.min_samples < 1) { payload.min_samples = 1; }
    if (payload.preview < 0) { payload.preview = 0; }

    // Show log area, disable button
    if (logEl) { logEl.textContent = 'Starting training...\n'; logEl.style.display = 'block'; }
    if (runBtn) { runBtn.disabled = true; runBtn.textContent = 'Running...'; }
    _embTrainingRunning = true;

    try {
        var res = await fetch('/api/v1/admin/embeddings/train-classifier', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        var data = await res.json();
        if (logEl) {
            logEl.textContent = data.output || '';
            if (data.error) {
                logEl.textContent += '\n\nERROR: ' + data.error;
            }
            if (data.success) {
                logEl.textContent += '\n\nTraining completed successfully.';
            }
            logEl.scrollTop = logEl.scrollHeight;
        }
        // Auto-reload classifier after successful training
        if (data.success) {
            reloadEmbeddingsClassifier();
        }
    } catch (e) {
        if (logEl) {
            logEl.textContent += '\n\nFetch error: ' + e.message;
        }
    }

    _embTrainingRunning = false;
    if (runBtn) { runBtn.disabled = false; runBtn.textContent = 'Run Training'; }
}


// ==================== NLLB / CT2 TUNING PANEL ====================

var _nllbAccordionOpen = false;

function toggleNllbAccordion() {
    _nllbAccordionOpen = !_nllbAccordionOpen;
    var body = document.getElementById('nllbAccordionBody');
    var arrow = document.getElementById('nllbAccordionArrow');
    if (body) {
        if (_nllbAccordionOpen) {
            body.style.maxHeight = body.scrollHeight + 'px';
            if (arrow) arrow.classList.add('open');
        } else {
            body.style.maxHeight = '0';
            if (arrow) arrow.classList.remove('open');
        }
    }
}

var _nllbParamsLoaded = false;

async function fetchNllbParams() {
    try {
        var res = await fetch('/api/v1/admin/nllb/params');
        if (!res.ok) return;
        var data = await res.json();
        populateNllbPanel(data);
    } catch (e) {
        console.error('[Admin] Error fetching NLLB params:', e);
    }
}

function populateNllbPanel(data) {
    var badge = document.getElementById('nllbStatusBadge');
    if (badge) {
        if (data.loaded) {
            badge.textContent = 'Active';
            badge.classList.add('active');
        } else {
            badge.textContent = 'Off';
            badge.classList.remove('active');
        }
    }

    // Model load params (selects + inputs)
    var deviceSel = document.getElementById('nllbDevice');
    if (deviceSel && data.device) deviceSel.value = data.device;
    var computeSel = document.getElementById('nllbComputeType');
    if (computeSel && data.compute_type) computeSel.value = data.compute_type;
    setNllbInput('nllbInterThreads', data.inter_threads);
    setNllbInput('nllbIntraThreads', data.intra_threads);

    var p = data.params || {};
    setNllbInput('nllbBeamSize', p.beam_size);
    setNllbInput('nllbLengthPenalty', p.length_penalty);
    setNllbInput('nllbRepetitionPenalty', p.repetition_penalty);
    setNllbInput('nllbNoRepeatNgram', p.no_repeat_ngram_size);
    setNllbInput('nllbSamplingTemp', p.sampling_temperature);
    setNllbInput('nllbSamplingTopK', p.sampling_topk);
    setNllbInput('nllbSamplingTopP', p.sampling_topp);
    setNllbInput('nllbMaxBatchSize', p.max_batch_size);
    setNllbInput('nllbMaxDecodeLen', p.max_decoding_length);
    setNllbInput('nllbMaxInputLen', p.max_input_length);

    var batchTypeEl = document.getElementById('nllbBatchType');
    if (batchTypeEl && p.batch_type) batchTypeEl.value = p.batch_type;

    updateSamplingVisibility();
    _nllbParamsLoaded = true;
}

function setNllbInput(id, value) {
    var el = document.getElementById(id);
    if (el && value !== undefined) el.value = value;
}

function updateSamplingVisibility() {
    var beamEl = document.getElementById('nllbBeamSize');
    var section = document.getElementById('nllbSamplingSection');
    if (beamEl && section) {
        var beam = parseInt(beamEl.value) || 1;
        section.style.opacity = beam === 1 ? '1' : '0.4';
        var inputs = section.querySelectorAll('input');
        for (var i = 0; i < inputs.length; i++) {
            inputs[i].disabled = beam !== 1;
        }
    }
}

// Toggle sampling section when beam size changes
document.addEventListener('change', function(e) {
    if (e.target && e.target.id === 'nllbBeamSize') {
        updateSamplingVisibility();
    }
});

async function applyNllbParams() {
    var btn = document.getElementById('nllbApplyBtn');
    var status = document.getElementById('nllbApplyStatus');
    if (btn) btn.disabled = true;
    if (status) { status.textContent = 'Applying...'; status.className = 'nllb-apply-status'; }

    var params = {
        beam_size:            parseInt(document.getElementById('nllbBeamSize').value) || 1,
        length_penalty:       parseFloat(document.getElementById('nllbLengthPenalty').value) || 1.0,
        repetition_penalty:   parseFloat(document.getElementById('nllbRepetitionPenalty').value) || 1.0,
        no_repeat_ngram_size: parseInt(document.getElementById('nllbNoRepeatNgram').value) || 0,
        sampling_temperature: parseFloat(document.getElementById('nllbSamplingTemp').value) || 1.0,
        sampling_topk:        parseInt(document.getElementById('nllbSamplingTopK').value) || 1,
        sampling_topp:        parseFloat(document.getElementById('nllbSamplingTopP').value) || 1.0,
        max_batch_size:       parseInt(document.getElementById('nllbMaxBatchSize').value) || 16,
        batch_type:           document.getElementById('nllbBatchType').value,
        max_decoding_length:  parseInt(document.getElementById('nllbMaxDecodeLen').value) || 512,
        max_input_length:     parseInt(document.getElementById('nllbMaxInputLen').value) || 512,
    };

    try {
        var res = await fetch('/api/v1/admin/nllb/params', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(params),
        });
        if (!res.ok) throw new Error('HTTP ' + res.status);
        var data = await res.json();
        // Refresh with server-clamped values
        if (data.params) populateNllbPanel({params: data.params, loaded: true, device: null, compute_type: null});
        if (status) { status.textContent = 'Applied'; status.className = 'nllb-apply-status success'; }
    } catch (e) {
        console.error('[Admin] Error applying NLLB params:', e);
        if (status) { status.textContent = 'Error: ' + e.message; status.className = 'nllb-apply-status error'; }
    }
    if (btn) btn.disabled = false;
    if (status) setTimeout(function() { status.textContent = ''; }, 4000);
}


async function saveNllbModelParams() {
    var btn = document.getElementById('nllbRestartBtn');
    var status = document.getElementById('nllbApplyStatus');
    if (btn) btn.disabled = true;
    if (status) { status.textContent = 'Saving...'; status.className = 'nllb-apply-status'; }

    var params = {
        device:        document.getElementById('nllbDevice').value,
        compute_type:  document.getElementById('nllbComputeType').value,
        inter_threads: parseInt(document.getElementById('nllbInterThreads').value) || 1,
        intra_threads: parseInt(document.getElementById('nllbIntraThreads').value) || 4,
    };

    try {
        var res = await fetch('/api/v1/admin/nllb/model-params', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(params),
        });
        if (!res.ok) throw new Error('HTTP ' + res.status);
        if (status) { status.textContent = 'Saved — restarting...'; status.className = 'nllb-apply-status success'; }
        // Page will reload when the server comes back
        setTimeout(function() { location.reload(); }, 3000);
    } catch (e) {
        console.error('[Admin] Error saving NLLB model params:', e);
        if (status) { status.textContent = 'Error: ' + e.message; status.className = 'nllb-apply-status error'; }
        if (btn) btn.disabled = false;
    }
}


// ==================== METRICS TEXT (stats bar) ====================

async function fetchMetricsText() {
    try {
        var res = await fetch('/api/v1/metrics/ai');
        if (!res.ok) return;
        var data = await res.json();

        var queueEl = document.getElementById('metricsQueue');
        var analystEl = document.getElementById('metricsAnalyst');

        if (queueEl) queueEl.textContent = data.queue_size || 0;
        if (analystEl) analystEl.textContent = (data.analyst_calls_per_min || 0).toFixed(1) + '/m';
    } catch (e) {
        // Silently fail - metrics are non-critical
    }
}


// ==================== API KEY STATUS DOTS ====================

function updateApiKeyDots() {
    var keys = [
        { env: 'GEMINI_API_KEY', dotId: 'geminiKeyDot' },
        { env: 'NEWSAPI_KEY', dotId: 'newsapiKeyDot' },
        { env: 'INTERPOL_API_KEY', dotId: 'interpolKeyDot' },
        { env: 'VIRUSTOTAL_API_KEY', dotId: 'vtKeyDot' },
        { env: 'URLSCAN_API_KEY', dotId: 'usKeyDot' }
    ];
    keys.forEach(function(k) {
        fetch('/api/v1/collectors/apikey/' + k.env)
            .then(function(res) { return res.json(); })
            .then(function(data) {
                var dot = document.getElementById(k.dotId);
                if (dot) dot.className = 'api-key-status-dot ' + (data.is_set ? 'set' : 'unset');
            })
            .catch(function() {});
    });
}


// ==================== HELPERS ====================

function _escHtml(str) {
    var d = document.createElement('div');
    d.textContent = str;
    return d.innerHTML;
}


// ==================== FEED STATS (replaces feeds.js on admin panel) ====================

async function fetchFeedStats() {
    try {
        var res = await fetch('/api/v1/feeds/status');
        if (!res.ok) return;
        var data = await res.json();

        perfMetrics.totalFeeds = data.total_feeds || 0;
        perfMetrics.activeFeeds = data.total_enabled_feeds || 0;
        perfMetrics.feedErrors = data.feed_errors || 0;
        perfMetrics.articlesProcessed = data.articles_processed || 0;
        perfMetrics.articlesRejected = data.articles_rejected || 0;

        updateStats();
    } catch (e) {
        // Silently fail
    }
}


// ==================== INIT ====================

function initAdminPanel() {
    // Fetch feed stats for the stats bar (replaces feeds.js)
    fetchFeedStats();
    setInterval(fetchFeedStats, 15000);
    // Fetch collector configs (refresh every 60s for 24h metrics)
    setTimeout(fetchCollectorConfigs, 2000);
    setInterval(fetchCollectorConfigs, 60000);
    // Fetch Ollama config
    setTimeout(fetchOllamaConfig, 2200);
    // Fetch screening status (poll every 30s to keep dots and counts fresh)
    setTimeout(fetchScreeningStatus, 2400);
    setInterval(fetchScreeningStatus, 30000);
    // Fetch embeddings config (poll every 60s for badge + stats)
    setTimeout(fetchEmbeddingsConfig, 2600);
    setInterval(fetchEmbeddingsConfig, 60000);
    // Fetch NLLB tuning parameters
    setTimeout(fetchNllbParams, 2800);
    // Fetch metrics text for stats bar
    fetchMetricsText();
    setInterval(fetchMetricsText, 15000);
    // Update API key status dots
    setTimeout(updateApiKeyDots, 1500);
}
