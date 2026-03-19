/**
 * Observer Dashboard - Database Control Panel
 * DB details, MAX_SIGNALS_LIMIT config, backup/restore
 */

// ==================== STATE ====================

var _dbDetails = null;
var _dbBackups = [];
var _dbMaxSignals = 75000;


// ==================== FETCH ====================

async function fetchDbDetails() {
    var el = document.getElementById('dbDetailsContent');
    try {
        var res = await fetch('/api/v1/database/details');
        if (!res.ok) {
            var errData = await res.json().catch(function() { return {}; });
            throw new Error(errData.error || 'HTTP ' + res.status);
        }
        _dbDetails = await res.json();
        renderDbDetails();
    } catch (e) {
        console.error('DB details fetch error:', e);
        if (el) {
            el.innerHTML = '<span class="collector-api-status-text unavailable">' +
                'Error: ' + e.message + '</span>';
        }
    }
}

async function fetchDbConfig() {
    try {
        var res = await fetch('/api/v1/database/config');
        if (!res.ok) throw new Error('Failed to fetch DB config');
        var data = await res.json();
        _dbMaxSignals = data.max_signals_limit;
        var input = document.getElementById('dbMaxSignalsInput');
        if (input) input.value = _dbMaxSignals.toLocaleString();
    } catch (e) {
        console.error('DB config fetch error:', e);
        var input = document.getElementById('dbMaxSignalsInput');
        if (input) input.value = 'N/A';
    }
}

async function fetchDbBackups() {
    try {
        var res = await fetch('/api/v1/database/backups');
        if (!res.ok) throw new Error('Failed to fetch backups');
        var data = await res.json();
        _dbBackups = data.backups || [];
        renderBackupList();
    } catch (e) {
        console.error('DB backups fetch error:', e);
    }
}


// ==================== DB DETAILS RENDERING ====================

function renderDbDetails() {
    if (!_dbDetails) return;

    var d = _dbDetails;
    var s = d.signals;
    var p = d.pool;

    // Summary row (always visible)
    var sizeEl = document.getElementById('dbSummarySize');
    var signalsEl = document.getElementById('dbSummarySignals');
    var poolEl = document.getElementById('dbSummaryPool');

    if (sizeEl) sizeEl.textContent = d.database.size_pretty || '--';
    if (signalsEl) signalsEl.textContent = s.total.toLocaleString();
    if (poolEl) poolEl.textContent = p.current + '/' + p.max;

    // Expandable detail panel
    var panel = document.getElementById('dbDetailsPanel');
    if (!panel) return;

    var oldest = s.oldest ? new Date(s.oldest).toLocaleDateString() : '--';
    var newest = s.newest ? new Date(s.newest).toLocaleDateString() : '--';

    var html = '<div class="db-detail-grid">';
    html += _detailRow('Processed', s.processed.toLocaleString());
    html += _detailRow('Pending', s.unprocessed.toLocaleString());
    html += _detailRow('Oldest', oldest);
    html += _detailRow('Newest', newest);
    html += _detailRow('Pool Idle', p.idle);
    html += '</div>';

    panel.innerHTML = html;
}

function toggleDbDetails() {
    var panel = document.getElementById('dbDetailsPanel');
    var arrow = document.getElementById('dbDetailsArrow');
    if (!panel) return;

    var isOpen = panel.classList.contains('open');
    panel.classList.toggle('open');
    if (arrow) arrow.classList.toggle('expanded');
}

function _detailRow(label, value) {
    return '<div class="db-detail-row">' +
        '<span class="db-detail-label">' + label + '</span>' +
        '<span class="db-detail-value">' + value + '</span>' +
        '</div>';
}


// ==================== MAX SIGNALS LIMIT ====================

async function saveMaxSignalsLimit() {
    var input = document.getElementById('dbMaxSignalsInput');
    var statusEl = document.getElementById('dbConfigStatus');
    if (!input || !statusEl) return;

    var raw = input.value.replace(/,/g, '').trim();
    var val = parseInt(raw, 10);

    if (isNaN(val) || val < 1000) {
        statusEl.textContent = 'Min: 1,000';
        statusEl.className = 'db-config-status error';
        return;
    }
    if (val > 500000) {
        statusEl.textContent = 'Max: 500,000';
        statusEl.className = 'db-config-status error';
        return;
    }

    statusEl.textContent = 'Saving...';
    statusEl.className = 'db-config-status';

    try {
        var res = await fetch('/api/v1/database/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ max_signals_limit: val }),
        });
        var data = await res.json();

        if (data.success) {
            _dbMaxSignals = data.max_signals_limit;
            input.value = _dbMaxSignals.toLocaleString();
            statusEl.textContent = 'Saved (' + data.previous.toLocaleString() + ' \u2192 ' + _dbMaxSignals.toLocaleString() + ')';
            statusEl.className = 'db-config-status success';
        } else {
            statusEl.textContent = data.detail || 'Save failed';
            statusEl.className = 'db-config-status error';
        }
    } catch (e) {
        statusEl.textContent = 'Error: ' + e.message;
        statusEl.className = 'db-config-status error';
    }
}


// ==================== BACKUP ====================

async function createDbBackup() {
    var btn = document.getElementById('dbBackupBtn');
    var statusEl = document.getElementById('dbBackupStatus');
    if (!btn || !statusEl) return;

    btn.disabled = true;
    btn.textContent = 'Backing up...';
    statusEl.textContent = 'Creating backup...';
    statusEl.className = 'db-backup-status';

    try {
        var res = await fetch('/api/v1/database/backup', { method: 'POST' });
        var data = await res.json();

        if (data.success) {
            statusEl.textContent = 'Backup created: ' + data.size_pretty;
            statusEl.className = 'db-backup-status success';
            fetchDbBackups();
        } else {
            statusEl.textContent = data.detail || 'Backup failed';
            statusEl.className = 'db-backup-status error';
        }
    } catch (e) {
        statusEl.textContent = 'Error: ' + e.message;
        statusEl.className = 'db-backup-status error';
    } finally {
        btn.disabled = false;
        btn.textContent = 'Backup';
    }
}


// ==================== RESTORE ====================

function openRestoreDialog() {
    var overlay = document.getElementById('dbRestoreOverlay');
    if (overlay) {
        fetchDbBackups();
        overlay.classList.add('visible');
    }
}

function closeRestoreDialog() {
    var overlay = document.getElementById('dbRestoreOverlay');
    if (overlay) overlay.classList.remove('visible');
}

function renderBackupList() {
    var el = document.getElementById('dbBackupList');
    if (!el) return;

    if (_dbBackups.length === 0) {
        el.innerHTML = '<div class="db-no-backups">No backups available</div>';
        return;
    }

    var html = '';
    for (var i = 0; i < _dbBackups.length; i++) {
        var b = _dbBackups[i];
        var date = new Date(b.created).toLocaleString();
        html += '<div class="db-backup-item">';
        html += '<div class="db-backup-item-info">';
        html += '<span class="db-backup-item-name">' + b.filename + '</span>';
        html += '<span class="db-backup-item-meta">' + b.size_pretty + ' &middot; ' + date + '</span>';
        html += '</div>';
        html += '<div class="db-backup-item-actions">';
        html += '<a href="/api/v1/database/backup/download/' + b.filename + '" class="db-backup-dl-btn" title="Download">DL</a>';
        html += '<button class="db-backup-restore-btn" onclick="confirmRestore(\'' + b.filename + '\')" title="Restore">Restore</button>';
        html += '</div>';
        html += '</div>';
    }
    el.innerHTML = html;
}

async function confirmRestore(filename) {
    var statusEl = document.getElementById('dbRestoreStatus');

    // Show confirmation
    var ok = confirm('RESTORE DATABASE from:\n' + filename + '\n\nThis will overwrite the current database. Continue?');
    if (!ok) return;

    if (statusEl) {
        statusEl.textContent = 'Restoring...';
        statusEl.className = 'db-restore-status';
    }

    try {
        var res = await fetch('/api/v1/database/restore', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ filename: filename }),
        });
        var data = await res.json();

        if (data.success) {
            if (statusEl) {
                statusEl.textContent = 'Restored successfully!';
                statusEl.className = 'db-restore-status success';
            }
            // Refresh DB details
            fetchDbDetails();
        } else {
            if (statusEl) {
                statusEl.textContent = data.detail || 'Restore failed';
                statusEl.className = 'db-restore-status error';
            }
        }
    } catch (e) {
        if (statusEl) {
            statusEl.textContent = 'Error: ' + e.message;
            statusEl.className = 'db-restore-status error';
        }
    }
}


// ==================== INIT ====================

function initDatabasePanel() {
    fetchDbConfig();
    fetchDbDetails();
}
