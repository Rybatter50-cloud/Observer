/**
 * RYBAT Dashboard - Signals Module
 * Signal fetching, timestamp utilities, stale data checking
 * 
 * @created 2026-02-03 by Claude - Modularized from monolithic dashboard.html
 * @updated 2026-02-02 by Claude - Removed agent_report/gemini handling (Executive Summary removed)
 */

// ==================== DATA FETCHING ====================
async function fetchIntelligence() {
    try {
        // Build query params — use server-side filters from search modal if available
        var params = new URLSearchParams();
        params.set('limit', '5000');

        if (typeof _sfmBuildServerParams === 'function') {
            var sp = _sfmBuildServerParams();
            for (var key in sp) {
                if (sp[key] !== undefined && sp[key] !== '' && sp[key] !== false) {
                    params.set(key, sp[key]);
                }
            }
        } else {
            // Fallback: no search modal loaded (e.g. dashboard.html)
            params.set('time_window', currentTimeWindow);
        }

        const response = await fetch('/api/v1/intelligence?' + params.toString());
        if (!response.ok) {
            console.error('Intelligence API returned', response.status);
            updateStatus('error');
            return;
        }
        const data = await response.json();

        if (data.intel) {
            allSignals = data.intel;
            lastUpdateTime = Date.now();
            // Store total matching count from DB for accurate feed display
            if (data.pagination && data.pagination.total_count !== undefined) {
                totalDbCount = data.pagination.total_count;
            }
            applyFilters();
        }

        if (data.articles_processed !== undefined) perfMetrics.articlesProcessed = data.articles_processed;
        if (data.articles_rejected !== undefined) perfMetrics.articlesRejected = data.articles_rejected;

        updateStats();
        updateStatus('online');

        // Update match count in modal if open
        if (typeof _sfmUpdateMatchCount === 'function') _sfmUpdateMatchCount();
    } catch (error) {
        console.error('Fetch error:', error);
        updateStatus('error');
    }
}

// ==================== STALE DATA CHECK ====================
function checkStaleData() {
    const staleWarning = document.getElementById('staleWarning');
    const statusDot = document.getElementById('statusDot');
    
    if (!lastUpdateTime) return;
    
    const minutesSinceUpdate = (Date.now() - lastUpdateTime) / (1000 * 60);
    
    if (minutesSinceUpdate >= 5) {
        staleWarning.classList.add('visible');
        statusDot.classList.add('stale');
    } else {
        staleWarning.classList.remove('visible');
        statusDot.classList.remove('stale');
    }
}

// ==================== SIGNAL TIMESTAMP ====================
function getSignalTimestamp(signal) {
    if (!signal.created_at) return null;
    try {
        let timestamp = signal.created_at;
        if (typeof timestamp === 'string') {
            timestamp = timestamp.replace(' ', 'T');
            if (!timestamp.endsWith('Z') && !timestamp.includes('+')) {
                timestamp += 'Z';
            }
        }
        return new Date(timestamp);
    } catch (e) {
        return null;
    }
}

// ==================== SIGNAL UTILITIES ====================
function getSignalAge(signal) {
    const timestamp = getSignalTimestamp(signal);
    if (!timestamp) return { class: 'old', text: 'Unknown age' };
    
    const diffHours = (Date.now() - timestamp.getTime()) / (1000 * 60 * 60);
    
    if (diffHours < 1) return { class: 'fresh', text: 'Less than 1 hour old' };
    if (diffHours < 4) return { class: 'recent', text: '1-4 hours old' };
    return { class: 'old', text: 'More than 4 hours old' };
}

function togglePin(id) {
    if (pinnedIds.has(id)) {
        pinnedIds.delete(id);
    } else {
        pinnedIds.add(id);
    }
    render();
}

function toggleReviewed(id) {
    if (reviewedIds.has(id)) {
        reviewedIds.delete(id);
    } else {
        reviewedIds.add(id);
    }
    render();
}

function selectSignalById(id) {
    const idx = filteredSignals.findIndex(s => s.id === id);
    if (idx !== -1) selectSignal(idx);
}

function toggleAssessment(header) {
    header.parentElement.classList.toggle('collapsed');
}

function copyToClipboard(text, btn) {
    navigator.clipboard.writeText(text).then(() => {
        if (btn) {
            btn.textContent = 'Copied!';
            btn.classList.add('copied');
            setTimeout(() => {
                btn.textContent = 'Copy Link';
                btn.classList.remove('copied');
            }, 2000);
        }
    });
}
