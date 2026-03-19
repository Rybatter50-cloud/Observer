/**
 * Observer Intelligence Platform - urlscan.io Source Scanning
 * =========================================================
 * Dashboard card JavaScript for the urlscan.io feed URL scanner.
 * Mirrors virustotal.js — same polling, manual scan, scheduler toggle.
 *
 * Polls GET /api/v1/urlscan/status every 30 seconds.
 *
 * 2026-02-21 | Mr Cat + Claude | Initial urlscan.io integration
 */


// ==================== STATUS POLLING ====================

async function fetchUSStatus() {
    try {
        var res = await fetch('/api/v1/urlscan/status');
        if (!res.ok) return;
        var data = await res.json();

        _renderUSConnectionStatus(data);
        _renderUSQuota(data);
        _renderUSStats(data);
        _renderUSScheduler(data);
        _renderUSConfig(data);

    } catch (e) {
        _setUSDot('usDot', 'usConnStatus', false, 'Unavailable');
        _setUSBadge('--', 'disabled');
    }
}


// ==================== CONNECTION STATUS ====================

function _renderUSConnectionStatus(data) {
    if (!data.enabled) {
        _setUSDot('usDot', 'usConnStatus', false, 'Disabled');
        var dot = document.getElementById('usDot');
        if (dot) dot.className = 'screening-source-dot gray';
        _setUSBadge('OFF', 'disabled');
    } else if (data.connected) {
        _setUSDot('usDot', 'usConnStatus', true, 'Connected');
        _setUSBadge('ON', 'connected');
    } else {
        _setUSDot('usDot', 'usConnStatus', false, 'No API Key');
        _setUSBadge('ERR', 'disconnected');
    }
}

function _setUSDot(dotId, statusId, available, label) {
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

function _setUSBadge(text, state) {
    var badge = document.getElementById('usConnBadge');
    if (!badge) return;
    badge.textContent = text;
    badge.className = 'us-conn-badge ' + state;
}


// ==================== QUOTA BAR ====================

function _renderUSQuota(data) {
    var text = document.getElementById('usQuotaText');
    var fill = document.getElementById('usQuotaFill');
    if (!text || !fill) return;

    var used = data.quota_used_today || 0;
    var limit = data.quota_daily_limit || 800;
    var pct = limit > 0 ? Math.min(100, (used / limit) * 100) : 0;

    text.textContent = used + '/' + limit;
    fill.style.width = pct + '%';

    fill.className = 'us-quota-fill';
    if (pct > 90) {
        fill.classList.add('high');
    } else if (pct > 60) {
        fill.classList.add('medium');
    }
}


// ==================== STATS GRID ====================

function _renderUSStats(data) {
    var el = document.getElementById('usStatsContent');
    if (!el) return;

    var html = '';

    html += _usStatRow('Feeds Scanned',
        (data.feeds_scanned || 0) + ' / ' + (data.total_feeds || 0));

    html += _usStatRow('Feeds Pending', (data.feeds_pending || 0).toString());

    html += _usStatRow('Total Scans', (data.total_scans || 0).toLocaleString());

    var threats = data.threats_found || 0;
    html += _usStatRow('Threats Found',
        '<span class="us-stat-value' + (threats > 0 ? ' threats' : '') + '">'
        + threats + '</span>');

    var lastScan = data.last_scan_time;
    if (lastScan) {
        html += _usStatRow('Last Scan', _formatUSTime(lastScan));
    }

    if (data.current_feed && data.scheduler_running && !data.scheduler_paused) {
        html += _usStatRow('Scanning', '<em>' + _escapeUSHtml(data.current_feed) + '</em>');
    }

    el.innerHTML = html;
}

function _usStatRow(label, value) {
    return '<div class="us-stat-row">'
        + '<span class="us-stat-label">' + label + '</span>'
        + '<span class="us-stat-value">' + value + '</span>'
        + '</div>';
}


// ==================== MANUAL URL SCAN ====================

async function startUSScan() {
    var input = document.getElementById('usUrlInput');
    var panel = document.getElementById('usResultPanel');
    var btn = document.getElementById('usScanBtn');
    if (!input || !panel) return;

    var url = input.value.trim();
    if (!url) return;

    panel.innerHTML = '<span class="us-spinner"></span> Scanning...';
    if (btn) btn.disabled = true;

    try {
        var res = await fetch('/api/v1/urlscan/scan', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({url: url})
        });

        var data = await res.json();

        if (!res.ok || !data.success) {
            panel.innerHTML = '<div class="us-result-error">'
                + (data.error_msg || data.detail || 'Scan failed') + '</div>';
        } else if (data.verdict_malicious) {
            // Malicious verdict
            panel.innerHTML = '<div class="us-result-threat">'
                + 'MALICIOUS — score: ' + data.verdict_score
                + (data.brands && data.brands.length > 0
                    ? '<br><small>Impersonating: ' + _escapeUSHtml(data.brands.join(', ')) + '</small>'
                    : '')
                + (data.categories && data.categories.length > 0
                    ? '<br><small>' + _escapeUSHtml(data.categories.join(', ')) + '</small>'
                    : '')
                + '</div>';
        } else if (data.risk_score >= 50) {
            // Suspicious
            panel.innerHTML = '<div class="us-result-warning">'
                + 'SUSPICIOUS — risk: ' + data.risk_score + '/100'
                + ', verdict: ' + data.verdict_score
                + '</div>';
        } else {
            // Clean
            panel.innerHTML = '<div class="us-result-clean">'
                + 'CLEAN — risk: ' + data.risk_score + '/100'
                + (data.page_domain ? ' (' + _escapeUSHtml(data.page_domain) + ')' : '')
                + ' (' + data.elapsed_ms.toFixed(0) + 'ms)'
                + '</div>';
        }

    } catch (e) {
        panel.innerHTML = '<div class="us-result-error">Network error: ' + e.message + '</div>';
    }

    if (btn) btn.disabled = false;
}


// ==================== SCHEDULER TOGGLE ====================

function _renderUSScheduler(data) {
    var toggle = document.getElementById('usSchedulerToggle');
    var status = document.getElementById('usSchedulerStatus');

    if (toggle) {
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

async function toggleUSScheduler(enabled) {
    var endpoint = enabled
        ? '/api/v1/urlscan/scheduler/start'
        : '/api/v1/urlscan/scheduler/stop';

    try {
        await fetch(endpoint, {method: 'POST'});
        setTimeout(fetchUSStatus, 500);
    } catch (e) {
        console.error('[urlscan] Scheduler toggle error:', e);
    }
}


// ==================== CONFIG THRESHOLDS ====================

function _renderUSConfig(data) {
    _setUSSelectValue('usWarnThreshold', data.warning_threshold);
    _setUSSelectValue('usDisableThreshold', data.auto_disable_threshold);
}

async function updateUSConfig() {
    var body = {
        warning_threshold: parseInt(document.getElementById('usWarnThreshold').value),
        auto_disable_threshold: parseInt(document.getElementById('usDisableThreshold').value),
    };

    try {
        await fetch('/api/v1/urlscan/config', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(body),
        });
    } catch (e) {
        console.error('[urlscan] Config update error:', e);
    }
}


// ==================== HELPERS ====================

function _setUSSelectValue(selectId, value) {
    var sel = document.getElementById(selectId);
    if (!sel || value === undefined || value === null) return;
    var strVal = String(value);
    for (var i = 0; i < sel.options.length; i++) {
        if (sel.options[i].value === strVal) {
            sel.value = strVal;
            return;
        }
    }
}

function _formatUSCountdown(isoStr) {
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

function _formatUSTime(isoStr) {
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

function _escapeUSHtml(str) {
    if (!str) return '';
    return str
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}


// ==================== WEBSOCKET HANDLER ====================

function handleURLScanResult(data) {
    fetchUSStatus();
}


// ==================== INITIALIZATION ====================

setTimeout(fetchUSStatus, 4000);
setInterval(fetchUSStatus, 30000);
