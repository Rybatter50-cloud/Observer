/**
 * RYBAT Dashboard - Filters Module
 * Filter application, time window, search, region filtering
 * 
 * @created 2026-02-03 by Claude - Modularized from monolithic dashboard.html
 */

// ==================== FILTERING & SORTING ====================
function applyFilters() {
    // Build modal predicate if search_filter_modal.js is loaded
    var _sfmPred = (typeof sfmBuildPredicate === 'function') ? sfmBuildPredicate() : null;

    filteredSignals = allSignals.filter(signal => {
        // Google-like search: use parsed tokens if available (from search_filter_modal.js)
        if (searchQuery) {
            if (typeof sfmSearchTokens !== 'undefined' && sfmSearchTokens !== null) {
                // Use token-based matching: all required present, no excluded present
                if (typeof _sfmMatchesSearchTokens === 'function') {
                    if (!_sfmMatchesSearchTokens(signal, sfmSearchTokens)) return false;
                }
            } else {
                // Fallback: simple substring match (when modal JS not loaded)
                const q = searchQuery.toLowerCase();
                const matchesAny = (signal.title || '').toLowerCase().includes(q)
                    || (signal.description || '').toLowerCase().includes(q)
                    || (signal.location || '').toLowerCase().includes(q)
                    || (signal.source || '').toLowerCase().includes(q)
                    || (signal.author || '').toLowerCase().includes(q);
                if (!matchesAny) return false;
            }
        }
        const relevanceScore = signal.relevance_score || 0;
        if (currentFilter === 'critical' && relevanceScore < 85) return false;
        if (currentFilter === 'high' && relevanceScore < 65) return false;
        if (currentFilter === 'pinned' && !pinnedIds.has(signal.id)) return false;

        // Apply modal filter predicate (regions, score tier, builder conditions, etc.)
        if (_sfmPred && !_sfmPred(signal)) return false;

        return true;
    });
    
    // Sort by time arrived (created_at), pinned items first
    filteredSignals.sort((a, b) => {
        const aPinned = pinnedIds.has(a.id) ? 1 : 0;
        const bPinned = pinnedIds.has(b.id) ? 1 : 0;
        if (aPinned !== bPinned) return bPinned - aPinned;
        
        // Then by created_at descending (newest first)
        const aTime = getSignalTimestamp(a);
        const bTime = getSignalTimestamp(b);
        if (!aTime && !bTime) return 0;
        if (!aTime) return 1;
        if (!bTime) return -1;
        return bTime.getTime() - aTime.getTime();
    });
    
    updateActiveFilters();
    render();
    updateStats();
}

function updateActiveFilters() {
    const container = document.getElementById('activeFilters');
    const pills = [];

    if (currentFilter !== 'all') {
        pills.push(`<span class="filter-pill">${currentFilter} <span class="remove" onclick="setFilter('all')">✕</span></span>`);
    }
    if (currentTimeWindow !== 'all') {
        pills.push(`<span class="filter-pill">${currentTimeWindow} <span class="remove" onclick="clearTimeWindow()">✕</span></span>`);
    }
    // Search query is shown as grey text in the sfm badge area — no separate pill

    container.innerHTML = pills.join('');
}

function clearTimeWindow() {
    currentTimeWindow = 'all';
    // Sync to search modal state if loaded
    if (typeof sfmState !== 'undefined') sfmState.timeWindow = 'all';
    document.querySelectorAll('.time-btn').forEach(b => b.classList.remove('active'));
    var allBtn = document.querySelector('.time-btn[data-window="all"]');
    if (allBtn) allBtn.classList.add('active');
    // Sync modal time window buttons if open
    var twRow = document.getElementById('sfmTimeWindowRow');
    if (twRow) twRow.querySelectorAll('.sfm-tw-btn').forEach(function(b) {
        b.classList.toggle('active', b.dataset.tw === 'all');
    });
    // Reset card limit when time window changes
    if (typeof resetCardLimit === 'function') resetCardLimit();
    fetchIntelligence();
}

function clearSearch() {
    searchQuery = '';
    document.getElementById('searchInput').value = '';
    applyFilters();
}

function setFilter(filter) {
    currentFilter = filter;
    document.querySelectorAll('.filter-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.filter === filter);
    });
    // Reset card limit when filter changes
    if (typeof resetCardLimit === 'function') resetCardLimit();
    applyFilters();
}
