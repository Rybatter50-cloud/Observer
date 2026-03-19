/**
 * Observer Dashboard - WebSocket Module
 * WebSocket connection and real-time message handling
 * 
 * @created 2026-02-03 by Claude - Modularized from monolithic dashboard.html
 * @updated 2026-02-02 by Claude - Removed report_update handler (Executive Summary removed)
 * @updated 2026-02-06 by Claude - Removed IRC message handler
 */

// ==================== WEBSOCKET ====================
function connectWebSocket() {
    const wsProto = (location.protocol === 'https:') ? 'wss:' : 'ws:';
    ws = new WebSocket(`${wsProto}//${window.location.host}/ws`);
    
    ws.onopen = () => updateStatus('online');
    ws.onclose = () => { updateStatus('offline'); setTimeout(connectWebSocket, 3000); };
    ws.onerror = () => updateStatus('error');
    
    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        
        if (data.type === 'new_signals') {
            // Filter incoming articles through active filters so the
            // live feed only shows signals matching the current view.
            var _wsPred = (typeof sfmBuildPredicate === 'function') ? sfmBuildPredicate() : null;
            data.data.forEach(signal => {
                if (allSignals.find(s => s.url === signal.url)) return; // dedup
                // Time window gate
                if (typeof sfmState !== 'undefined' && sfmState.timeWindow !== 'all') {
                    var _twHours = { '4h': 4, '24h': 24, '72h': 72, '7d': 168 };
                    var maxH = _twHours[sfmState.timeWindow];
                    if (maxH && signal.created_at) {
                        var raw = signal.created_at;
                        if (typeof raw === 'string') {
                            raw = raw.replace(' ', 'T');
                            if (!raw.endsWith('Z') && !raw.includes('+')) raw += 'Z';
                        }
                        if ((Date.now() - new Date(raw).getTime()) > maxH * 3600000) return;
                    }
                }
                // Modal filter predicate (regions, score, indicators, etc.)
                if (_wsPred && !_wsPred(signal)) return;
                allSignals.unshift(signal);
            });
            lastUpdateTime = Date.now();
            if (typeof applyFilters === 'function') applyFilters();
        } else if (data.type === 'signal_update') {
            const idx = allSignals.findIndex(s => s.id === data.id);
            if (idx !== -1) {
                allSignals[idx] = { ...allSignals[idx], ...data.data };
                if (typeof updateExistingCard === 'function') {
                    updateExistingCard(allSignals[idx]);
                }
                if (typeof applyFilters === 'function') applyFilters();
            }
        } else if (data.type === 'vt_scan_result') {
            // VirusTotal scan completed — refresh the Source Scanning card
            if (typeof handleVTScanResult === 'function') {
                handleVTScanResult(data.data);
            }
        } else if (data.type === 'urlscan_result') {
            // urlscan.io scan completed — refresh the urlscan card
            if (typeof handleURLScanResult === 'function') {
                handleURLScanResult(data.data);
            }
        }
    };
}

function updateStatus(status) {
    const dot = document.getElementById('statusDot');
    const text = document.getElementById('statusText');
    
    if (status === 'online') {
        dot.style.background = 'var(--accent-green)';
        text.textContent = 'ONLINE';
    } else if (status === 'error') {
        dot.style.background = 'var(--warn-red)';
        text.textContent = 'ERROR';
    } else {
        dot.style.background = 'var(--accent-orange)';
        text.textContent = 'RECONNECTING';
    }
}
