/**
 * RYBAT Dashboard - Keyboard Module
 * Keyboard shortcuts and navigation event listeners
 * 
 * @created 2026-02-03 by Claude - Modularized from monolithic dashboard.html
 */

// ==================== EVENT LISTENERS ====================
function initEventListeners() {
    // Search
    document.getElementById('searchInput').addEventListener('input', (e) => {
        searchQuery = e.target.value;
        if (typeof resetCardLimit === 'function') resetCardLimit();
        applyFilters();
    });
    
    // Filter buttons
    document.querySelectorAll('.filter-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            currentFilter = btn.dataset.filter;
            applyFilters();
        });
    });
    
    // Time buttons (sidebar) — sync with search modal state
    document.querySelectorAll('.time-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.time-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            currentTimeWindow = btn.dataset.window;
            // Sync to search modal state if loaded
            if (typeof sfmState !== 'undefined') {
                sfmState.timeWindow = btn.dataset.window;
                // Also sync the modal's time window buttons if open
                var twRow = document.getElementById('sfmTimeWindowRow');
                if (twRow) twRow.querySelectorAll('.sfm-tw-btn').forEach(function(b) {
                    b.classList.toggle('active', b.dataset.tw === sfmState.timeWindow);
                });
            }
            if (typeof resetCardLimit === 'function') resetCardLimit();
            fetchIntelligence();
        });
    });
    
    // Compact table sorting is handled by compact.js _initHeaderInteractions()

    // Keyboard navigation
    document.addEventListener('keydown', handleKeyboard);
}

// ==================== KEYBOARD NAVIGATION ====================

// Chord state for hidden key combos (e.g. Ctrl+S → 2)
var _chordPrefix = null;
var _chordTimer = null;

function handleKeyboard(e) {
    // --- Chord detection: second key after Ctrl+S prefix ---
    if (_chordPrefix === 'ctrl-s') {
        _chordPrefix = null;
        if (_chordTimer) { clearTimeout(_chordTimer); _chordTimer = null; }
        if (e.key === '2') {
            e.preventDefault();
            if (typeof openScreeningModalEmpty === 'function') openScreeningModalEmpty();
            return;
        }
        // Not a recognized chord — fall through to normal handling
    }

    // --- Ctrl+S starts a chord prefix ---
    if (e.ctrlKey && e.key.toLowerCase() === 's') {
        e.preventDefault();
        _chordPrefix = 'ctrl-s';
        // Expire chord after 1.5s if no second key
        _chordTimer = setTimeout(function() { _chordPrefix = null; }, 1500);
        return;
    }

    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') {
        if (e.key === 'Escape') e.target.blur();
        return;
    }

    // Escape closes search/filter modal if open
    if (e.key === 'Escape' && typeof sfmState !== 'undefined' && sfmState.open) {
        closeSearchFilterModal();
        return;
    }

    switch(e.key.toLowerCase()) {
        case 'j': selectSignal(selectedIndex + 1); break;
        case 'k': selectSignal(selectedIndex - 1); break;
        case 'o': openSelectedSource(); break;
        case 'p': togglePinSelected(); break;
        case 'r': toggleReviewedSelected(); break;
        case 'c': copySelectedLink(); break;
        case 'f':
            e.preventDefault();
            var sbi = document.getElementById('sidebarSearchInput');
            if (sbi) { sbi.focus(); } else { document.getElementById('searchInput').focus(); }
            break;
        case '/': e.preventDefault(); if (typeof openSearchFilterModal === 'function') openSearchFilterModal(); break;
        case '1': setFilter('all'); break;
        case '2': setFilter('critical'); break;
        case '3': setFilter('high'); break;
        case '4': setFilter('pinned'); break;
        case '?': toggleKeyboardHint(); break;
    }
}

function selectSignal(index) {
    if (filteredSignals.length === 0) return;
    selectedIndex = Math.max(0, Math.min(index, filteredSignals.length - 1));
    
    document.querySelectorAll('.intel-card, .compact-table tbody tr').forEach(el => {
        el.classList.remove('selected');
    });
    
    const signal = filteredSignals[selectedIndex];
    if (currentView === 'full') {
        const card = document.querySelector(`.intel-card[data-id="${signal.id}"]`);
        if (card) {
            card.classList.add('selected');
            card.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
    } else {
        const row = document.querySelector(`.compact-table tr[data-id="${signal.id}"]`);
        if (row) {
            row.classList.add('selected');
            row.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
    }
}

function openSelectedSource() {
    if (selectedIndex >= 0 && selectedIndex < filteredSignals.length) {
        window.open(filteredSignals[selectedIndex].url, '_blank');
    }
}

function togglePinSelected() {
    if (selectedIndex >= 0 && selectedIndex < filteredSignals.length) {
        togglePin(filteredSignals[selectedIndex].id);
    }
}

function toggleReviewedSelected() {
    if (selectedIndex >= 0 && selectedIndex < filteredSignals.length) {
        toggleReviewed(filteredSignals[selectedIndex].id);
    }
}

function copySelectedLink() {
    if (selectedIndex >= 0 && selectedIndex < filteredSignals.length) {
        copyToClipboard(filteredSignals[selectedIndex].url);
    }
}

function toggleKeyboardHint() {
    document.getElementById('keyboardHint').classList.toggle('visible');
}
