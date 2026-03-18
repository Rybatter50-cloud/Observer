/**
 * RYBAT Dashboard - Collector Controls & Content Filter
 * Toggle switches for RSS, NewsAPI, Scraper (trafilatura) collectors
 * Content filter mode and file selection
 */

// ==================== RSS COLLECTOR CONTROL ====================

/**
 * Toggle RSS collector on/off
 * @param {boolean} enabled - Whether to enable or disable
 */
async function toggleRSS(enabled) {
    var toggle = document.getElementById('rssToggle');
    var statusText = document.getElementById('rssStatusText');

    if (toggle) toggle.disabled = true;
    if (statusText) statusText.textContent = enabled ? 'Enabling...' : 'Disabling...';

    try {
        var endpoint = enabled ? '/api/v1/collectors/rss/enable' : '/api/v1/collectors/rss/disable';
        var response = await fetch(endpoint, { method: 'POST' });

        if (response.ok) {
            _updateRSSStatus(enabled, true);
            console.log('[Collector] RSS ' + (enabled ? 'enabled' : 'disabled'));
        } else {
            if (toggle) toggle.checked = !enabled;
            _updateRSSStatus(!enabled, true);
            console.error('[Collector] Failed to toggle RSS');
        }
    } catch (error) {
        console.error('[Collector] Error toggling RSS:', error);
        if (toggle) toggle.checked = !enabled;
        _updateRSSStatus(!enabled, true);
    } finally {
        if (toggle) toggle.disabled = false;
    }
}

function _updateRSSStatus(enabled, available) {
    var statusText = document.getElementById('rssStatusText');
    var subCard = document.getElementById('rssSubCard');
    if (!statusText) return;

    if (!available) {
        statusText.textContent = 'N/A';
        statusText.className = 'collector-status-badge unavailable';
        if (subCard) subCard.setAttribute('data-state', 'disabled');
    } else if (enabled) {
        statusText.textContent = 'Active';
        statusText.className = 'collector-status-badge enabled';
        if (subCard) subCard.setAttribute('data-state', 'active');
    } else {
        statusText.textContent = 'Off';
        statusText.className = 'collector-status-badge disabled';
        if (subCard) subCard.setAttribute('data-state', 'disabled');
    }
}

async function fetchRSSStatus() {
    try {
        var response = await fetch('/api/v1/collectors/rss/status');
        if (response.ok) {
            var data = await response.json();
            var toggle = document.getElementById('rssToggle');
            if (toggle) {
                toggle.checked = data.enabled !== false;
            }
            _updateRSSStatus(data.enabled !== false, true);
        }
    } catch (error) {
        // RSS is always available in this architecture, default to enabled
        _updateRSSStatus(true, true);
    }
}

// ==================== NEWSAPI COLLECTOR CONTROL ====================

/**
 * Toggle NewsAPI collector on/off
 * @param {boolean} enabled - Whether to enable or disable
 */
async function toggleNewsAPI(enabled) {
    var toggle = document.getElementById('newsapiToggle');
    var statusText = document.getElementById('newsapiStatusText');

    if (toggle) toggle.disabled = true;
    if (statusText) statusText.textContent = enabled ? 'Enabling...' : 'Disabling...';

    try {
        var endpoint = enabled ? '/api/v1/collectors/newsapi/enable' : '/api/v1/collectors/newsapi/disable';
        var response = await fetch(endpoint, { method: 'POST' });

        if (response.ok) {
            _updateNewsAPIStatus(enabled, true);
            console.log('[Collector] NewsAPI ' + (enabled ? 'enabled' : 'disabled'));
        } else {
            if (toggle) toggle.checked = !enabled;
            _updateNewsAPIStatus(!enabled, true);
            console.error('[Collector] Failed to toggle NewsAPI');
        }
    } catch (error) {
        console.error('[Collector] Error toggling NewsAPI:', error);
        if (toggle) toggle.checked = !enabled;
        _updateNewsAPIStatus(!enabled, true);
    } finally {
        if (toggle) toggle.disabled = false;
    }
}

function _updateNewsAPIStatus(enabled, available) {
    var statusText = document.getElementById('newsapiStatusText');
    var subCard = document.getElementById('newsapiSubCard');
    if (!statusText) return;

    if (!available) {
        statusText.textContent = 'N/A';
        statusText.className = 'collector-status-badge unavailable';
        if (subCard) subCard.setAttribute('data-state', 'disabled');
    } else if (enabled) {
        statusText.textContent = 'Active';
        statusText.className = 'collector-status-badge enabled';
        if (subCard) subCard.setAttribute('data-state', 'active');
    } else {
        statusText.textContent = 'Off';
        statusText.className = 'collector-status-badge disabled';
        if (subCard) subCard.setAttribute('data-state', 'disabled');
    }
}

async function fetchNewsAPIStatus() {
    try {
        var response = await fetch('/api/v1/collectors/newsapi/status');
        if (response.ok) {
            var data = await response.json();
            var toggle = document.getElementById('newsapiToggle');

            if (toggle) {
                toggle.checked = data.enabled || false;
                toggle.disabled = !data.available;
            }

            _updateNewsAPIStatus(data.enabled || false, data.available || false);
        } else {
            _updateNewsAPIStatus(false, false);
        }
    } catch (error) {
        console.error('[Collector] Error fetching NewsAPI status:', error);
        _updateNewsAPIStatus(false, false);
    }
}

// ==================== NP4K COLLECTOR CONTROL ====================

/**
 * Toggle NP4K collector on/off
 * @param {boolean} enabled - Whether to enable or disable
 */
async function toggleNP4K(enabled) {
    var toggle = document.getElementById('np4kToggle');
    var statusText = document.getElementById('np4kStatusText');

    if (toggle) toggle.disabled = true;
    if (statusText) statusText.textContent = enabled ? 'Enabling...' : 'Disabling...';

    try {
        var endpoint = enabled ? '/api/v1/collectors/np4k/enable' : '/api/v1/collectors/np4k/disable';
        var response = await fetch(endpoint, { method: 'POST' });

        if (response.ok) {
            _updateNP4KStatus(enabled, true);
            console.log('[Collector] NP4K ' + (enabled ? 'enabled' : 'disabled'));
        } else {
            if (toggle) toggle.checked = !enabled;
            _updateNP4KStatus(!enabled, true);
            console.error('[Collector] Failed to toggle NP4K');
        }
    } catch (error) {
        console.error('[Collector] Error toggling NP4K:', error);
        if (toggle) toggle.checked = !enabled;
        _updateNP4KStatus(!enabled, true);
    } finally {
        if (toggle) toggle.disabled = false;
    }
}

function _updateNP4KStatus(enabled, available) {
    var statusText = document.getElementById('np4kStatusText');
    var subCard = document.getElementById('np4kSubCard');
    if (!statusText) return;

    if (!available) {
        statusText.textContent = 'N/A';
        statusText.className = 'collector-status-badge unavailable';
        if (subCard) subCard.setAttribute('data-state', 'disabled');
    } else if (enabled) {
        statusText.textContent = 'Active';
        statusText.className = 'collector-status-badge enabled';
        if (subCard) subCard.setAttribute('data-state', 'active');
    } else {
        statusText.textContent = 'Off';
        statusText.className = 'collector-status-badge disabled';
        if (subCard) subCard.setAttribute('data-state', 'disabled');
    }
}

async function fetchNP4KStatus() {
    try {
        var response = await fetch('/api/v1/collectors/np4k/status');
        if (response.ok) {
            var data = await response.json();
            var toggle = document.getElementById('np4kToggle');

            if (toggle) {
                toggle.checked = data.enabled || false;
                toggle.disabled = !data.available;
            }

            _updateNP4KStatus(data.enabled || false, data.available || false);
        } else {
            _updateNP4KStatus(false, false);
        }
    } catch (error) {
        console.error('[Collector] Error fetching NP4K status:', error);
        _updateNP4KStatus(false, false);
    }
}


// ==================== CONTENT FILTER CONTROLS ====================

async function fetchContentFilterStatus() {
    try {
        var response = await fetch('/api/v1/feeds/content-filter/status');
        if (!response.ok) return;
        var data = await response.json();

        var modeSelect = document.getElementById('contentFilterMode');
        if (modeSelect && modeSelect.value !== data.mode) {
            modeSelect.value = data.mode;
        }

        var blSelect = document.getElementById('contentFilterBL');
        if (blSelect && data.available_bl) {
            _populateFilterDropdown(blSelect, data.available_bl, data.active_bl);
        }

        if (data.available_wl) {
            _populateWlDropdown(data.available_wl, data.active_wl);
        }

        _updateContentFilterStatus(data);
    } catch (error) {
        console.error('[Content Filter] Error fetching status:', error);
    }
}

function _populateFilterDropdown(selectEl, files, activeFile) {
    var needsRebuild = (selectEl.options.length !== files.length);
    if (!needsRebuild) {
        for (var i = 0; i < files.length; i++) {
            if (selectEl.options[i].value !== files[i]) {
                needsRebuild = true;
                break;
            }
        }
    }

    if (needsRebuild) {
        selectEl.innerHTML = '';
        for (var j = 0; j < files.length; j++) {
            var opt = document.createElement('option');
            opt.value = files[j];
            var label = files[j].replace(/^[BW]L_/, '').replace(/^ollama_/, '').replace(/_/g, ' ');
            label = label.charAt(0).toUpperCase() + label.slice(1);
            opt.textContent = label;
            selectEl.appendChild(opt);
        }
    }

    if (selectEl.value !== activeFile) {
        selectEl.value = activeFile;
    }
}

// ==================== WL CUSTOM DROPDOWN ====================

var _wlDropdownOpen = false;
var _wlActiveFile = '';

function _populateWlDropdown(files, activeFile) {
    _wlActiveFile = activeFile;
    var menu = document.getElementById('wlDropdownMenu');
    var label = document.getElementById('wlDropdownLabel');
    if (!menu || !label) return;

    // Update button label
    var displayName = activeFile.replace(/^WL_/, '').replace(/^ollama_/, '').replace(/_/g, ' ');
    displayName = displayName.charAt(0).toUpperCase() + displayName.slice(1);
    label.textContent = displayName;

    // Build menu items
    menu.innerHTML = '';
    for (var i = 0; i < files.length; i++) {
        var f = files[i];
        var isAI = f.indexOf('WL_ollama_') === 0;
        var isActive = f === activeFile;

        var item = document.createElement('div');
        item.className = 'filter-dropdown-item' + (isActive ? ' active' : '');
        item.setAttribute('data-value', f);

        var nameSpan = document.createElement('span');
        nameSpan.className = 'filter-item-name';
        var itemLabel = f.replace(/^WL_/, '').replace(/^ollama_/, '').replace(/_/g, ' ');
        itemLabel = itemLabel.charAt(0).toUpperCase() + itemLabel.slice(1);
        nameSpan.textContent = itemLabel;
        nameSpan.onclick = (function(val) {
            return function() { selectWlFilter(val); };
        })(f);

        item.appendChild(nameSpan);

        if (isAI) {
            var badge = document.createElement('span');
            badge.className = 'filter-badge-ai-sm';
            badge.textContent = 'AI';
            item.appendChild(badge);

            var del = document.createElement('button');
            del.className = 'filter-delete-btn';
            del.title = 'Delete this AI filter';
            del.innerHTML = '\u2715';
            del.onclick = (function(val) {
                return function(e) { e.stopPropagation(); deleteWlFilter(val); };
            })(f);
            item.appendChild(del);
        }

        menu.appendChild(item);
    }
}

function toggleWlDropdown() {
    var menu = document.getElementById('wlDropdownMenu');
    if (!menu) return;
    _wlDropdownOpen = !_wlDropdownOpen;
    menu.style.display = _wlDropdownOpen ? 'block' : 'none';
}

// Close dropdown when clicking outside
document.addEventListener('click', function(e) {
    var wrap = document.getElementById('wlDropdownWrap');
    if (wrap && !wrap.contains(e.target)) {
        var menu = document.getElementById('wlDropdownMenu');
        if (menu) menu.style.display = 'none';
        _wlDropdownOpen = false;
    }
});

function selectWlFilter(filename) {
    // Close dropdown
    var menu = document.getElementById('wlDropdownMenu');
    if (menu) menu.style.display = 'none';
    _wlDropdownOpen = false;

    changeContentFilterFile('wl', filename);
}

async function deleteWlFilter(filename) {
    if (!filename.startsWith('WL_ollama_')) return;

    var displayName = filename.replace(/^WL_ollama_/, '').replace(/_/g, ' ');
    if (!confirm('Delete AI filter "' + displayName + '"?')) return;

    try {
        var response = await fetch('/api/v1/feeds/content-filter/file', {
            method: 'DELETE',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ filename: filename })
        });

        if (response.ok) {
            fetchContentFilterStatus();
        } else {
            var data = await response.json();
            alert('Delete failed: ' + (data.detail || 'unknown error'));
        }
    } catch (error) {
        alert('Delete error: ' + error.message);
    }
}

function _updateContentFilterStatus(data) {
    var statusEl = document.getElementById('contentFilterStatus');
    if (!statusEl) return;

    var mode = data.mode || 'both';
    var text = mode.charAt(0).toUpperCase() + mode.slice(1) +
        ' — BL:' + (data.bl_count || 0) + ' WL:' + (data.wl_count || 0);
    statusEl.textContent = text;
    statusEl.className = 'collector-api-status-text enabled';
}

async function changeContentFilterMode(mode) {
    var statusEl = document.getElementById('contentFilterStatus');
    if (statusEl) statusEl.textContent = 'Switching...';

    try {
        var response = await fetch('/api/v1/feeds/content-filter/mode', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ mode: mode })
        });

        if (response.ok) {
            var data = await response.json();
            _updateContentFilterStatus(data);
        } else {
            setTimeout(fetchContentFilterStatus, 500);
        }
    } catch (error) {
        console.error('[Content Filter] Error changing mode:', error);
        setTimeout(fetchContentFilterStatus, 500);
    }
}

async function changeContentFilterFile(type, filename) {
    var statusEl = document.getElementById('contentFilterStatus');
    if (statusEl) statusEl.textContent = 'Loading filter...';

    var body = {};
    if (type === 'bl') body.bl_file = filename;
    else body.wl_file = filename;

    try {
        var response = await fetch('/api/v1/feeds/content-filter/select', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });

        if (response.ok) {
            var data = await response.json();
            _updateContentFilterStatus(data);
            // Full refresh to update the custom WL dropdown label + active state
            fetchContentFilterStatus();
        } else {
            setTimeout(fetchContentFilterStatus, 500);
        }
    } catch (error) {
        console.error('[Content Filter] Error changing filter file:', error);
        setTimeout(fetchContentFilterStatus, 500);
    }
}


// ==================== API KEY DIALOG ====================

var _apikeyCurrentName = '';

async function openApiKeyDialog(keyName, displayName) {
    _apikeyCurrentName = keyName;
    var overlay = document.getElementById('apikeyDialogOverlay');
    var title = document.getElementById('apikeyDialogTitle');
    var masked = document.getElementById('apikeyMasked');
    var input = document.getElementById('apikeyInput');
    var status = document.getElementById('apikeyDialogStatus');

    title.textContent = displayName + ' API Key';
    masked.textContent = 'Loading...';
    input.value = '';
    input.type = 'password';
    status.textContent = '';
    overlay.classList.add('visible');

    try {
        var response = await fetch('/api/v1/collectors/apikey/' + keyName);
        if (response.ok) {
            var data = await response.json();
            masked.textContent = data.is_set ? data.masked : 'Not set';
        } else {
            masked.textContent = 'Error loading';
        }
    } catch (e) {
        masked.textContent = 'Connection error';
    }
}

function closeApiKeyDialog() {
    document.getElementById('apikeyDialogOverlay').classList.remove('visible');
    _apikeyCurrentName = '';
}

function toggleApiKeyVisibility() {
    var input = document.getElementById('apikeyInput');
    input.type = input.type === 'password' ? 'text' : 'password';
}

async function saveApiKey() {
    var input = document.getElementById('apikeyInput');
    var status = document.getElementById('apikeyDialogStatus');
    var value = input.value.trim();

    if (!value) {
        status.textContent = 'Please enter an API key.';
        status.className = 'apikey-dialog-status error';
        return;
    }

    status.textContent = 'Saving...';
    status.className = 'apikey-dialog-status';

    try {
        var response = await fetch('/api/v1/collectors/apikey', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ key_name: _apikeyCurrentName, value: value })
        });

        if (response.ok) {
            var data = await response.json();
            document.getElementById('apikeyMasked').textContent = data.masked;
            status.textContent = 'Saved successfully!';
            status.className = 'apikey-dialog-status success';
            input.value = '';

            // Refresh relevant status
            if (_apikeyCurrentName === 'NEWSAPI_KEY') fetchNewsAPIStatus();
            if (_apikeyCurrentName === 'GEMINI_API_KEY') fetchGeminiKeyStatus();
            if (_apikeyCurrentName === 'INTERPOL_API_KEY') fetchInterpolKeyStatus();
            if (_apikeyCurrentName === 'VIRUSTOTAL_API_KEY') fetchVTKeyStatus();
            updateApiKeyDots();
        } else {
            var err = await response.json().catch(function() { return {}; });
            status.textContent = 'Error: ' + (err.detail || 'Save failed');
            status.className = 'apikey-dialog-status error';
        }
    } catch (e) {
        status.textContent = 'Connection error: ' + e.message;
        status.className = 'apikey-dialog-status error';
    }
}

// ==================== API KEY STATUS (inline) ====================

function _updateKeyStatusInline(elementId, data) {
    var el = document.getElementById(elementId);
    if (!el) return;
    if (data.is_set) {
        el.textContent = 'Key configured';
        el.className = 'api-key-configured set';
    } else {
        el.textContent = 'No key';
        el.className = 'api-key-configured unset';
    }
}

async function fetchGeminiKeyStatus() {
    try {
        var response = await fetch('/api/v1/collectors/apikey/GEMINI_API_KEY');
        if (response.ok) {
            _updateKeyStatusInline('geminiKeyStatus', await response.json());
        }
    } catch (e) {
        var el = document.getElementById('geminiKeyStatus');
        if (el) { el.textContent = 'Error'; el.className = 'api-key-configured unset'; }
    }
}

async function fetchNewsAPIKeyStatus() {
    try {
        var response = await fetch('/api/v1/collectors/apikey/NEWSAPI_KEY');
        if (response.ok) {
            _updateKeyStatusInline('newsapiKeyStatus', await response.json());
        }
    } catch (e) {
        var el = document.getElementById('newsapiKeyStatus');
        if (el) { el.textContent = 'Error'; el.className = 'api-key-configured unset'; }
    }
}

async function fetchInterpolKeyStatus() {
    try {
        var response = await fetch('/api/v1/collectors/apikey/INTERPOL_API_KEY');
        if (response.ok) {
            _updateKeyStatusInline('interpolKeyStatus', await response.json());
        }
    } catch (e) {
        var el = document.getElementById('interpolKeyStatus');
        if (el) { el.textContent = 'Error'; el.className = 'api-key-configured unset'; }
    }
}

async function fetchVTKeyStatus() {
    try {
        var response = await fetch('/api/v1/collectors/apikey/VIRUSTOTAL_API_KEY');
        if (response.ok) {
            _updateKeyStatusInline('vtKeyStatus', await response.json());
        }
    } catch (e) {
        var el = document.getElementById('vtKeyStatus');
        if (el) { el.textContent = 'Error'; el.className = 'api-key-configured unset'; }
    }
}

async function fetchUSKeyStatus() {
    try {
        var response = await fetch('/api/v1/collectors/apikey/URLSCAN_API_KEY');
        if (response.ok) {
            _updateKeyStatusInline('usKeyStatus', await response.json());
        }
    } catch (e) {
        var el = document.getElementById('usKeyStatus');
        if (el) { el.textContent = 'Error'; el.className = 'api-key-configured unset'; }
    }
}

// ==================== API ON/OFF TOGGLES ====================

// Promise that resolves once the initial toggle fetch completes, so
// connection-status checks can wait for it before reading checkbox state.
var _apiTogglesReady = null;

async function fetchApiToggles() {
    try {
        var res = await fetch('/api/v1/collectors/api-toggles');
        if (!res.ok) {
            console.warn('[API Toggles] Server returned', res.status, '— using HTML defaults');
            return;
        }
        var data = await res.json();
        var toggles = data.toggles || {};
        console.log('[API Toggles] State from server:', JSON.stringify(toggles));
        var keys = Object.keys(toggles);
        for (var i = 0; i < keys.length; i++) {
            var el = document.getElementById('apiToggle_' + keys[i]);
            if (el) el.checked = !!toggles[keys[i]];
        }
    } catch (e) {
        console.error('[API Toggles] Fetch failed — using HTML defaults:', e);
    }
}

// Map toggle key names to their connection-check key (for immediate status refresh)
var _TOGGLE_TO_CONNECTION = {
    'FBI': 'fbi',
    'SANCTIONS_NETWORK': 'sanctionsnetwork',
    'WIKI_EVENTS': 'wikievents'
};

async function toggleApi(keyName, enabled) {
    try {
        var res = await fetch('/api/v1/collectors/api-toggle', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ key_name: keyName, enabled: enabled }),
        });
        if (!res.ok) {
            var err = await res.json().catch(function() { return {}; });
            console.error('[API Toggle] Error:', err.detail || 'Failed');
            // Revert checkbox
            var el = document.getElementById('apiToggle_' + keyName);
            if (el) el.checked = !enabled;
        } else {
            // Immediately refresh connection status for public APIs
            var connKey = _TOGGLE_TO_CONNECTION[keyName];
            if (connKey) checkApiConnection(connKey);
        }
    } catch (e) {
        console.error('[API Toggle] Error:', e);
        var el = document.getElementById('apiToggle_' + keyName);
        if (el) el.checked = !enabled;
    }
}


// ==================== PUBLIC API CONNECTION STATUS ====================

var API_CONNECTION_ENDPOINTS = {
    fbi: { id: 'fbiConnectionStatus', url: 'https://api.fbi.gov/@wanted', toggleId: 'apiToggle_FBI' },
    sanctionsnetwork: { id: 'sanctionsnetworkConnectionStatus', url: 'https://api.sanctions.network/rpc/search_sanctions', toggleId: 'apiToggle_SANCTIONS_NETWORK' },
    wikievents: { id: 'wikieventsConnectionStatus', url: 'https://www.wikidata.org/w/api.php?action=query&meta=siteinfo&format=json', toggleId: 'apiToggle_WIKI_EVENTS' }
};

function _setConnectionStatus(elementId, status) {
    var el = document.getElementById(elementId);
    if (!el) return;
    el.textContent = status;
    if (status === 'Connected') {
        el.className = 'api-connection-status connected';
    } else if (status === 'Connecting...') {
        el.className = 'api-connection-status connecting';
    } else if (status === 'Disabled') {
        el.className = 'api-connection-status disabled';
    } else {
        el.className = 'api-connection-status error';
    }
}

async function checkApiConnection(key) {
    var cfg = API_CONNECTION_ENDPOINTS[key];
    if (!cfg) return;

    // Respect the toggle: if disabled, show "Disabled" instead of pinging
    if (cfg.toggleId) {
        var toggle = document.getElementById(cfg.toggleId);
        if (toggle && !toggle.checked) {
            _setConnectionStatus(cfg.id, 'Disabled');
            return;
        }
    }

    _setConnectionStatus(cfg.id, 'Connecting...');
    try {
        var response = await fetch('/api/v1/collectors/ping', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url: cfg.url })
        });
        if (response.ok) {
            var data = await response.json();
            _setConnectionStatus(cfg.id, data.reachable ? 'Connected' : 'Error');
        } else {
            _setConnectionStatus(cfg.id, 'Error');
        }
    } catch (e) {
        _setConnectionStatus(cfg.id, 'Error');
    }
}

function checkAllApiConnections() {
    Object.keys(API_CONNECTION_ENDPOINTS).forEach(function(key) {
        checkApiConnection(key);
    });
}


// ==================== INITIALIZATION ====================

document.addEventListener('DOMContentLoaded', function() {
    // API toggles first — fetch server state, then check connections once it's done
    _apiTogglesReady = fetchApiToggles().then(function() {
        checkAllApiConnections();
    });
    setTimeout(fetchRSSStatus, 800);
    setTimeout(fetchNewsAPIStatus, 1000);
    setTimeout(fetchNP4KStatus, 1200);
    setTimeout(fetchContentFilterStatus, 1400);
    setTimeout(fetchGeminiKeyStatus, 1600);
    setTimeout(fetchNewsAPIKeyStatus, 1700);
    setTimeout(fetchInterpolKeyStatus, 1800);
    setTimeout(fetchVTKeyStatus, 1900);
    setTimeout(fetchUSKeyStatus, 2000);

    setInterval(fetchRSSStatus, 30000);
    setInterval(fetchNewsAPIStatus, 30000);
    setInterval(fetchNP4KStatus, 30000);
    setInterval(checkAllApiConnections, 60000);
});
