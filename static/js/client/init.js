/**
 * RYBAT Lite - Client View Initialization
 * Read-only client initialization (no admin controls)
 *
 * IMPORTANT: This file must be loaded LAST after all other modules
 */

document.addEventListener('DOMContentLoaded', () => {
    initTheme();
    initEventListeners();
    connectWebSocket();
    fetchIntelligence();
    fetchFeedStatus();
    fetchTranslatorMetrics();
    updateClock();
    updateSessionTimer();

    setInterval(updateClock, 1000);
    setInterval(updateSessionTimer, 1000);
    setInterval(updateLastUpdateDisplay, 1000);
    setInterval(checkStaleData, 10000);
    setInterval(fetchIntelligence, 60000);
    setInterval(fetchFeedStatus, 30000);
    setInterval(fetchTranslatorMetrics, 10000);

    // Initialize column resize handles
    initColumnResize();
});

// ==================== SIDEBAR SEARCH INPUT ====================
// Bridges the sidebar search box into the sfm search pipeline.

var _sidebarSearchTimer = null;

function _sidebarOnSearchInput(val) {
    // Update sfm state so filter pipeline stays in sync
    if (typeof sfmState !== 'undefined') {
        sfmState.searchText = val;
        sfmState.dirty = true;
    }
    // Also sync the modal's input if it exists
    var modalInp = document.getElementById('sfmSearchInput');
    if (modalInp) modalInp.value = val;

    // Debounce 300ms, then apply client-side search
    if (_sidebarSearchTimer) clearTimeout(_sidebarSearchTimer);
    _sidebarSearchTimer = setTimeout(function() {
        if (typeof _sfmApplySearchOnly === 'function') {
            _sfmApplySearchOnly();
        } else {
            // Fallback: write to shared state and apply directly
            searchQuery = val;
            var hidden = document.getElementById('searchInput');
            if (hidden) hidden.value = val;
            if (typeof resetCardLimit === 'function') resetCardLimit();
            if (typeof applyFilters === 'function') applyFilters();
        }
        if (typeof _sfmUpdateBadge === 'function') _sfmUpdateBadge();
    }, 300);
}
