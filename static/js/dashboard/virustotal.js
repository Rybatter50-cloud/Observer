/**
 * RYBAT Intelligence Platform - VirusTotal Source Scanning
 * =========================================================
 * Dashboard card JavaScript for the VirusTotal feed URL scanner.
 *
 * Handles:
 *   - Status polling (connection dot, quota bar, stats grid)
 *   - Manual URL scan from dashboard input
 *   - Scheduler start/stop toggle
 *   - Config threshold updates
 *   - WebSocket scan result handling
 *
 * Polls GET /api/v1/virustotal/status every 30 seconds.
 * Reuses the _setScreeningDot() helper from admin.js for dot styling.
 *
 * 2026-02-21 | Mr Cat + Claude | Initial VirusTotal integration
 */


// ==================== STATUS POLLING ====================

/**
 * Fetch VT service status and update all dashboard card elements.
 * Called on init (3s delay) and then every 30s via setInterval.
 */
async function fetchVTStatus() {
    try {
        var res = await fetch('/api/v1/virustotal/status');
        if (!res.ok) return;
        var data = await res.json();

        // Update connection dot and badge
        _renderVTConnectionStatus(data);

        // Update quota bar
        _renderVTQuota(data);

        // Update stats grid
        _renderVTStats(data);

        // Update scheduler toggle
        _renderVTScheduler(data);

        // Update config dropdowns to match server state
        _renderVTConfig(data);

    } catch (e) {
        // Service might not be available — show disabled state
        _setVTDot('vtDot', 'vtConnStatus', false, 'Unavailable');
        _setVTBadge('--', 'disabled');
    }
}


// ==================== CONNECTION STATUS ====================

/**
 * Update the connection dot and badge based on service state.
 */
function _renderVTConnectionStatus(data) {
    if (!data.enabled) {
        // Service disabled via config
        _setVTDot('vtDot', 'vtConnStatus', false, 'Disabled');
        var dot = document.getElementById('vtDot');
        if (dot) dot.className = 'screening-source-dot gray';
        _setVTBadge('OFF', 'disabled');
    } else if (data.connected) {
        // Service enabled and API client initialized
        _setVTDot('vtDot', 'vtConnStatus', true, 'Connected');
        _setVTBadge('ON', 'connected');
    } else {
        // Service enabled but no API key or client failed
        _setVTDot('vtDot', 'vtConnStatus', false, 'No API Key');
        _setVTBadge('ERR', 'disconnected');
    }
}

/**
 * Set the connection dot color and status text.
 * Mirrors the _setScreeningDot() pattern from admin.js.
 */
function _setVTDot(dotId, statusId, available, label) {
    var dot = document.getElementById(dotId);
    var status = document.getElementById(statusId);
    if (dot) {
        dot.className = available
            ? 'screening-source-dot green'
            : 'screening-source-dot red';
    }
    if (status) {
        status.textContent = label;
    }
}

/**
 * Update the badge in the card header.
 */
function _setVTBadge(text, state) {
    var badge = document.getElementById('vtConnBadge');
    if (!badge) return;
    badge.textContent = text;
    badge.className = 'vt-conn-badge ' + state;
}


// ==================== QUOTA BAR ====================

/**
 * Update the daily quota progress bar and text.
 * Bar color shifts from green → yellow → red as quota depletes.
 */
function _renderVTQuota(data) {
    var text = document.getElementById('vtQuotaText');
    var fill = document.getElementById('vtQuotaFill');
    if (!text || !fill) return;

    var used = data.quota_used_today || 0;
    var limit = data.quota_daily_limit || 450;
    var pct = limit > 0 ? Math.min(100, (used / limit) * 100) : 0;

    text.textContent = used + '/' + limit;
    fill.style.width = pct + '%';

    // Color coding based on usage percentage
    fill.className = 'vt-quota-fill';
    if (pct > 90) {
        fill.classList.add('high');
    } else if (pct > 60) {
        fill.classList.add('medium');
    }
}


// ==================== STATS GRID ====================

/**
 * Build the stats rows showing scan progress and results.
 * Uses the same HTML pattern as screening stats in admin.js.
 */
function _renderVTStats(data) {
    var el = document.getElementById('vtStatsContent');
    if (!el) return;

    var html = '';

    // Feeds scanned vs total
    html += _vtStatRow('Feeds Scanned',
        (data.feeds_scanned || 0) + ' / ' + (data.total_feeds || 0));

    // Feeds pending
    html += _vtStatRow('Feeds Pending', (data.feeds_pending || 0).toString());

    // Total scans (historical)
    html += _vtStatRow('Total Scans', (data.total_scans || 0).toLocaleString());

    // Threats found — highlighted red if > 0
    var threats = data.threats_found || 0;
    html += _vtStatRow('Threats Found',
        '<span class="vt-stat-value' + (threats > 0 ? ' threats' : '') + '">'
        + threats + '</span>');

    // Last scan time
    var lastScan = data.last_scan_time;
    if (lastScan) {
        html += _vtStatRow('Last Scan', _formatVTTime(lastScan));
    }

    // Currently scanning feed
    if (data.current_feed && data.scheduler_running && !data.scheduler_paused) {
        html += _vtStatRow('Scanning', '<em>' + _escapeHtml(data.current_feed) + '</em>');
    }

    el.innerHTML = html;
}

/**
 * Build a single stat row with label and value.
 */
function _vtStatRow(label, value) {
    return '<div class="vt-stat-row">'
        + '<span class="vt-stat-label">' + label + '</span>'
        + '<span class="vt-stat-value">' + value + '</span>'
        + '</div>';
}


// ==================== MANUAL URL SCAN ====================

/**
 * Trigger a manual scan of the URL in the input field.
 * Called on button click or Enter keypress.
 */
async function startVTScan() {
    var input = document.getElementById('vtUrlInput');
    var panel = document.getElementById('vtResultPanel');
    var btn = document.getElementById('vtScanBtn');
    if (!input || !panel) return;

    var url = input.value.trim();
    if (!url) return;

    // Show spinner
    panel.innerHTML = '<span class="vt-spinner"></span> Scanning...';
    if (btn) btn.disabled = true;

    try {
        var res = await fetch('/api/v1/virustotal/scan', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({url: url})
        });

        var data = await res.json();

        if (!res.ok || !data.success) {
            // API error or scan failure
            panel.innerHTML = '<div class="vt-result-error">'
                + (data.error_msg || data.detail || 'Scan failed') + '</div>';
        } else if (data.malicious_count >= 3) {
            // Malicious — red result
            panel.innerHTML = '<div class="vt-result-threat">'
                + 'MALICIOUS — ' + data.malicious_count + '/' + data.total_engines
                + ' engines detected threats'
                + (data.threat_names && data.threat_names.length > 0
                    ? '<br><small>' + _escapeHtml(data.threat_names.slice(0, 3).join(', ')) + '</small>'
                    : '')
                + '</div>';
        } else if (data.malicious_count > 0 || data.suspicious_count > 0) {
            // Suspicious — yellow result
            panel.innerHTML = '<div class="vt-result-warning">'
                + 'WARNING — ' + data.malicious_count + ' malicious, '
                + data.suspicious_count + ' suspicious / ' + data.total_engines + ' engines'
                + '</div>';
        } else {
            // Clean — green result
            panel.innerHTML = '<div class="vt-result-clean">'
                + 'CLEAN — 0/' + data.total_engines + ' engines'
                + ' (' + data.elapsed_ms.toFixed(0) + 'ms)'
                + '</div>';
        }

    } catch (e) {
        panel.innerHTML = '<div class="vt-result-error">Network error: ' + e.message + '</div>';
    }

    if (btn) btn.disabled = false;
}


// ==================== SCHEDULER TOGGLE ====================

/**
 * Update the scheduler toggle and status text from server state.
 */
function _renderVTScheduler(data) {
    var toggle = document.getElementById('vtSchedulerToggle');
    var status = document.getElementById('vtSchedulerStatus');

    if (toggle) {
        // Toggle is ON if scheduler is running and not paused
        toggle.checked = data.scheduler_running && !data.scheduler_paused;
    }

    if (status) {
        if (!data.enabled) {
            status.textContent = 'Disabled';
        } else if (data.scheduler_running && !data.scheduler_paused) {
            status.textContent = 'Running';
        } else if (data.scheduler_paused) {
            status.textContent = 'Paused';
        } else {
            status.textContent = 'Stopped';
        }
    }
}

/**
 * Start or stop the scheduler based on toggle state.
 */
async function toggleVTScheduler(enabled) {
    var endpoint = enabled
        ? '/api/v1/virustotal/scheduler/start'
        : '/api/v1/virustotal/scheduler/stop';

    try {
        await fetch(endpoint, {method: 'POST'});
        // Refresh status immediately to reflect the change
        setTimeout(fetchVTStatus, 500);
    } catch (e) {
        console.error('[VT] Scheduler toggle error:', e);
    }
}


// ==================== CONFIG THRESHOLDS ====================

/**
 * Populate config dropdowns from server state (on first load).
 */
function _renderVTConfig(data) {
    _setSelectValue('vtWarnThreshold', data.warning_threshold);
    _setSelectValue('vtDisableThreshold', data.auto_disable_threshold);
}

/**
 * Push updated config thresholds to the server.
 * Called onChange from the config dropdowns.
 */
async function updateVTConfig() {
    var body = {
        warning_threshold: parseInt(document.getElementById('vtWarnThreshold').value),
        auto_disable_threshold: parseInt(document.getElementById('vtDisableThreshold').value),
    };

    try {
        await fetch('/api/v1/virustotal/config', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(body),
        });
    } catch (e) {
        console.error('[VT] Config update error:', e);
    }
}


// ==================== HELPERS ====================

/**
 * Set a <select> element's value, creating the option if needed.
 */
function _setSelectValue(selectId, value) {
    var sel = document.getElementById(selectId);
    if (!sel || value === undefined || value === null) return;
    var strVal = String(value);
    // Check if option exists
    for (var i = 0; i < sel.options.length; i++) {
        if (sel.options[i].value === strVal) {
            sel.value = strVal;
            return;
        }
    }
}

/**
 * Format an ISO timestamp as a countdown to that future time.
 * e.g. "in 23h", "in 2d 5h", "soon"
 */
function _formatVTCountdown(isoStr) {
    try {
        var target = new Date(isoStr);
        var now = new Date();
        var diffMs = target - now;
        if (diffMs <= 0) return 'soon';
        var diffMins = Math.floor(diffMs / 60000);
        if (diffMins < 60) return 'in ' + diffMins + 'm';
        var diffHrs = Math.floor(diffMins / 60);
        if (diffHrs < 24) return 'in ' + diffHrs + 'h';
        var diffDays = Math.floor(diffHrs / 24);
        var remainHrs = diffHrs % 24;
        return 'in ' + diffDays + 'd' + (remainHrs > 0 ? ' ' + remainHrs + 'h' : '');
    } catch (e) {
        return isoStr;
    }
}

/**
 * Format an ISO timestamp to a relative time string.
 * e.g. "2m ago", "3h ago", "1d ago"
 */
function _formatVTTime(isoStr) {
    try {
        var d = new Date(isoStr);
        var now = new Date();
        var diffMs = now - d;
        var diffMins = Math.floor(diffMs / 60000);
        if (diffMins < 1) return 'just now';
        if (diffMins < 60) return diffMins + 'm ago';
        var diffHrs = Math.floor(diffMins / 60);
        if (diffHrs < 24) return diffHrs + 'h ago';
        var diffDays = Math.floor(diffHrs / 24);
        return diffDays + 'd ago';
    } catch (e) {
        return isoStr;
    }
}

/**
 * Escape HTML special characters to prevent XSS.
 */
function _escapeHtml(str) {
    if (!str) return '';
    return str
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}


// ==================== WEBSOCKET HANDLER ====================

/**
 * Handle incoming VT scan result from WebSocket.
 * Called from websocket.js when message type is 'vt_scan_result'.
 * Refreshes the stats to reflect the new scan.
 */
function handleVTScanResult(data) {
    // Refresh the full status to pick up new stats
    fetchVTStatus();
}


// ==================== INITIALIZATION ====================

// Start polling VT status after a 3s delay (let other services init first)
// Poll every 30s to keep the card fresh
setTimeout(fetchVTStatus, 3000);
setInterval(fetchVTStatus, 30000);
