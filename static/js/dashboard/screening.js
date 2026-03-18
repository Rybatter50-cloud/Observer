/**
 * RYBAT Intelligence Platform - Entity Screening (Redesigned)
 * =============================================================
 * Table-based screening modal with source summary bar, inline filters,
 * sortable columns, expandable detail rows, and screening log.
 *
 * Sources: FBI, Interpol, OpenSanctions, Sanctions Network
 *
 * 2026-02-12 | Mr Cat + Claude - Original card-based modal
 * 2026-02-18 | Mr Cat + Claude - Redesigned: table results, source bar, tabs
 */


// ==================== ENTITY EXTRACTION ====================
// (preserved from original — solid regex NLP extraction)

const _ENTITY_STOP = new Set([
    'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
    'of', 'with', 'by', 'from', 'up', 'about', 'into', 'through', 'after',
    'over', 'between', 'out', 'against', 'during', 'before', 'under', 'around',
    'among', 'says', 'said', 'says', 'report', 'reports', 'reported',
    'news', 'breaking', 'update', 'analysis', 'latest', 'new', 'more',
    'according', 'officials', 'official', 'sources', 'source', 'government',
    'state', 'national', 'international', 'global', 'world', 'country',
    'president', 'minister', 'prime', 'foreign', 'defence', 'defense',
    'military', 'army', 'forces', 'police', 'security', 'intelligence',
    'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday',
    'january', 'february', 'march', 'april', 'may', 'june', 'july', 'august',
    'september', 'october', 'november', 'december', 'today', 'yesterday',
    'unknown', 'untitled', 'reuters', 'associated', 'press', 'afp',
    'killed', 'dead', 'attack', 'attacks', 'bomb', 'bombing', 'war',
    'conflict', 'crisis', 'threat', 'threats', 'alert', 'warns', 'warning',
    'north', 'south', 'east', 'west', 'central', 'northern', 'southern',
    'eastern', 'western', 'former', 'current', 'first', 'second', 'third',
    'people', 'group', 'groups', 'region', 'area', 'city', 'province',
]);

function _extractNamesFromText(text) {
    if (!text) return [];
    const entities = [];
    const regex = /\b([A-Z][a-zA-Z'-]+(?:\s+(?:(?:al|bin|ibn|von|van|de|del|el|al-|Abu|Ben)\s+)?[A-Z][a-zA-Z'-]+)+)\b/g;
    let match;
    while ((match = regex.exec(text)) !== null) {
        const candidate = match[1].trim();
        const words = candidate.split(/\s+/);
        const meaningfulWords = words.filter(w => !_ENTITY_STOP.has(w.toLowerCase()));
        if (meaningfulWords.length >= 1 && candidate.length >= 4) {
            entities.push(candidate);
        }
    }
    const singleRegex = /(?:^|[.!?]\s+|\b(?:the|a|an|and|or|in|of|by|to|for|from|with|at)\s+)([A-Z][a-z]{3,})/g;
    while ((match = singleRegex.exec(text)) !== null) {
        const word = match[1];
        if (!_ENTITY_STOP.has(word.toLowerCase()) && word.length >= 4) {
            entities.push(word);
        }
    }
    return entities;
}

function _extractEntities(signal) {
    if (!signal) return [];
    const seen = new Set();
    const entities = [];
    function add(name, type) {
        if (!name || typeof name !== 'string') return;
        name = name.trim();
        if (name.length < 2) return;
        const key = name.toLowerCase();
        if (seen.has(key)) return;
        seen.add(key);
        entities.push({ name, type });
    }
    if (signal.author) add(signal.author, 'person');
    if (signal.location && signal.location !== 'Unknown' && signal.location !== 'Global') {
        add(signal.location, 'location');
    }
    if (signal.source_group) add(signal.source_group, 'org');
    for (const e of _extractNamesFromText(signal.title || '')) add(e, 'extracted');
    for (const e of _extractNamesFromText(signal.description || '')) add(e, 'extracted');
    return entities;
}


// ==================== MODAL STATE ====================

var _scrState = {
    allHits: [],           // all hits from latest search (unfiltered)
    autoHits: [],          // auto-screening hits from signal
    sourceFilter: null,    // null = all, or a source string
    scoreTier: 'all',      // 'all', '60', '80'
    catFilter: null,       // null = all, or category string
    textFilter: '',        // search within results
    sortCol: 'score',      // 'score', 'source', 'name', 'category'
    sortDir: 'desc',
    expandedRow: null,     // hit index currently expanded
    sourceCounts: {},      // { fbi: 3, opensanctions: 12, ... }
    sourcesFailed: [],
    query: '',
    elapsedMs: 0,
    signalId: null
};

var _SCR_SOURCES = ['fbi', 'opensanctions', 'sanctions_network', 'interpol'];
var _SCR_SOURCE_LABELS = {
    fbi: 'FBI',
    opensanctions: 'OpenSanctions',
    sanctions_network: 'Sanctions Network',
    interpol: 'Interpol'
};


// ==================== MODAL LIFECYCLE ====================

function _createScreeningModal() {
    var overlay = document.createElement('div');
    overlay.id = 'screeningOverlay';
    overlay.className = 'screening-overlay';
    overlay.onclick = function(e) {
        if (e.target === overlay) closeScreeningModal();
    };

    overlay.innerHTML = [
        '<div class="screening-modal redesigned">',
        '  <div class="screening-modal-header">',
        '    <h3>Entity Screening</h3>',
        '    <button class="screening-modal-close" onclick="closeScreeningModal()">&times;</button>',
        '  </div>',
        // Search row
        '  <div class="screening-search-row">',
        '    <input type="text" id="screeningInput" class="screening-search-input"',
        '           placeholder="Enter name to screen, or click an entity below..."',
        '           onkeydown="if(event.key===\'Enter\') runScreening()">',
        '    <select id="screeningEntityType" class="scr-entity-type">',
        '      <option value="Person">Person</option>',
        '      <option value="Organization">Organization</option>',
        '    </select>',
        '    <button id="screeningSearchBtn" class="screening-search-btn" onclick="runScreening()">Screen</button>',
        '  </div>',
        // Entity buttons
        '  <div class="screening-entities-row" id="screeningEntities"></div>',
        // Source summary bar
        '  <div class="scr-source-bar" id="scrSourceBar">',
        _SCR_SOURCES.map(function(src) {
            return '    <div class="scr-source-badge" data-source="' + src + '" onclick="_scrToggleSource(\'' + src + '\')">' +
                '<span class="scr-src-label">' + _SCR_SOURCE_LABELS[src] + '</span>' +
                '<span class="scr-src-count" id="scrCount_' + src + '">&mdash;</span></div>';
        }).join('\n'),
        '  </div>',
        // Tabs
        '  <div class="scr-tabs">',
        '    <button class="scr-tab active" data-tab="results" onclick="_scrSwitchTab(\'results\')">Results</button>',
        '    <button class="scr-tab" data-tab="context" onclick="_scrSwitchTab(\'context\')">Article Context</button>',
        '    <button class="scr-tab" data-tab="log" onclick="_scrSwitchTab(\'log\')">Screening Log</button>',
        '  </div>',
        // Body
        '  <div class="scr-body">',
        // Results tab
        '    <div class="scr-tab-panel active" data-panel="results">',
        '      <div class="scr-filter-row" id="scrFilterRow">',
        '        <span class="scr-filter-label">Filter:</span>',
        '        <input type="text" class="scr-filter-search" id="scrResultSearch" placeholder="Search results..." oninput="_scrOnFilterChange()">',
        '        <button class="scr-score-btn active" data-tier="all" onclick="_scrSetScoreTier(\'all\')">All</button>',
        '        <button class="scr-score-btn" data-tier="60" onclick="_scrSetScoreTier(\'60\')">60+</button>',
        '        <button class="scr-score-btn" data-tier="80" onclick="_scrSetScoreTier(\'80\')">80+</button>',
        '        <span id="scrCatChips"></span>',
        '      </div>',
        '      <div id="scrSummary"></div>',
        '      <div class="scr-results-wrap">',
        '        <table class="scr-results-table">',
        '          <thead><tr>',
        '            <th onclick="_scrSort(\'score\')" id="scrTh_score" class="sorted-desc">Score</th>',
        '            <th onclick="_scrSort(\'source\')" id="scrTh_source">Source</th>',
        '            <th onclick="_scrSort(\'name\')" id="scrTh_name">Name</th>',
        '            <th onclick="_scrSort(\'category\')" id="scrTh_category">Category</th>',
        '            <th>Details</th>',
        '            <th>Link</th>',
        '          </tr></thead>',
        '          <tbody id="scrResultsBody"></tbody>',
        '        </table>',
        '      </div>',
        '      <div id="scrResultsEmpty" class="scr-results-empty" style="display:none">Enter a name above and click Screen to begin.</div>',
        '    </div>',
        // Context tab
        '    <div class="scr-tab-panel" data-panel="context">',
        '      <div class="scr-context-grid" id="scrContextGrid"></div>',
        '    </div>',
        // Log tab
        '    <div class="scr-tab-panel" data-panel="log">',
        '      <table class="scr-log-table">',
        '        <thead><tr><th>Time</th><th>IP</th><th>Name</th><th>Hits</th><th>Sources</th></tr></thead>',
        '        <tbody id="scrLogBody"><tr><td colspan="5" style="text-align:center;color:var(--text-muted)">Loading...</td></tr></tbody>',
        '      </table>',
        '    </div>',
        '  </div>',
        '</div>'
    ].join('\n');

    document.body.appendChild(overlay);
    return overlay;
}


// ==================== OPEN / CLOSE ====================

function openScreeningModal(signalId, prefillName) {
    var overlay = document.getElementById('screeningOverlay') || _createScreeningModal();
    _scrState.signalId = signalId || null;
    _scrState.allHits = [];
    _scrState.autoHits = [];
    _scrState.expandedRow = null;
    _scrResetFilters();

    var input = document.getElementById('screeningInput');
    if (input) input.value = prefillName || '';

    var signal = _getSignalById(signalId);
    _populateEntityButtons(signal);
    _scrPopulateContext(signal);
    _scrResetSourceBar();

    // Load auto-screening hits from signal
    if (signal && signal.screening_hits && signal.screening_hits.hits) {
        _scrState.autoHits = signal.screening_hits.hits;
        _scrState.allHits = signal.screening_hits.hits.slice();
        _scrState.query = '(auto-screened)';
        _scrState.elapsedMs = signal.screening_hits.elapsed_ms || 0;
        _scrState.sourcesFailed = signal.screening_hits.sources_failed || [];
        _scrUpdateSourceCounts();
        _scrRenderResults();
    } else {
        _scrRenderEmpty();
    }

    _scrUpdateSourceBar();
    overlay.classList.add('active');
    if (input) input.focus();
}

function openScreeningModalEmpty(prefillName) {
    var overlay = document.getElementById('screeningOverlay') || _createScreeningModal();
    _scrState.signalId = null;
    _scrState.allHits = [];
    _scrState.autoHits = [];
    _scrState.expandedRow = null;
    _scrResetFilters();

    var input = document.getElementById('screeningInput');
    if (input) input.value = prefillName || '';

    var entities = document.getElementById('screeningEntities');
    if (entities) { entities.innerHTML = ''; entities.style.display = 'none'; }

    _scrPopulateContext(null);
    _scrResetSourceBar();
    _scrRenderEmpty();

    overlay.classList.add('active');
    if (input) input.focus();

    if (prefillName && prefillName.length >= 2) {
        runScreening();
    }
}

function closeScreeningModal() {
    var overlay = document.getElementById('screeningOverlay');
    if (overlay) overlay.classList.remove('active');
}


// ==================== TAB SWITCHING ====================

function _scrSwitchTab(tabName) {
    var overlay = document.getElementById('screeningOverlay');
    if (!overlay) return;
    overlay.querySelectorAll('.scr-tab').forEach(function(t) {
        t.classList.toggle('active', t.dataset.tab === tabName);
    });
    overlay.querySelectorAll('.scr-tab-panel').forEach(function(p) {
        p.classList.toggle('active', p.dataset.panel === tabName);
    });
    if (tabName === 'log') _scrFetchLog();
}


// ==================== ENTITY BUTTONS ====================

function _populateEntityButtons(signal) {
    var container = document.getElementById('screeningEntities');
    if (!container) return;
    if (!signal) { container.innerHTML = ''; container.style.display = 'none'; return; }

    var entities = _extractEntities(signal);
    if (entities.length === 0) {
        container.innerHTML = '<span class="screening-entities-empty">No entities detected</span>';
        container.style.display = 'flex';
        return;
    }

    var html = '<span class="screening-entities-label">Entities:</span>';
    for (var i = 0; i < entities.length; i++) {
        var ent = entities[i];
        var escaped = _escapeHtml(ent.name);
        html += '<button class="screening-entity-btn ' + ent.type + '" ' +
            'onclick="_selectEntity(this, \'' + escaped.replace(/'/g, "\\'") + '\')" ' +
            'title="' + ent.type + '">' + escaped + '</button>';
    }
    container.innerHTML = html;
    container.style.display = 'flex';
}

function _selectEntity(btn, name) {
    var input = document.getElementById('screeningInput');
    if (!input) return;
    input.value = name;
    document.querySelectorAll('.screening-entity-btn.selected').forEach(function(b) { b.classList.remove('selected'); });
    btn.classList.add('selected');
    runScreening();
}


// ==================== ARTICLE CONTEXT ====================

function _scrPopulateContext(signal) {
    var grid = document.getElementById('scrContextGrid');
    if (!grid) return;
    if (!signal) { grid.innerHTML = '<div style="padding:20px;color:var(--text-muted);font-size:12px">No signal context available.</div>'; return; }

    var fields = [
        ['Title', signal.title],
        ['Author', signal.author],
        ['Source', (signal.source || '') + (signal.source_group ? ' / ' + signal.source_group : '')],
        ['Location', signal.location && signal.location !== 'Unknown' ? signal.location : null],
        ['Risk Indicators', signal.risk_indicators && signal.risk_indicators.length > 0 ?
            signal.risk_indicators.map(function(c) { return (window.INDICATOR_LABELS && window.INDICATOR_LABELS[c]) || c; }).join(', ') : null],
        ['Relevance', signal.relevance_score ? signal.relevance_score + '/100' : null],
        ['Published', signal.published_at || signal.created_at]
    ];

    var html = '';
    for (var i = 0; i < fields.length; i++) {
        if (fields[i][1]) {
            html += '<div class="scr-context-label">' + fields[i][0] + '</div>';
            html += '<div class="scr-context-value">' + _escapeHtml(fields[i][1]) + '</div>';
        }
    }
    if (signal.description) {
        html += '<div class="scr-context-label">Description</div>';
        html += '<div class="scr-context-value">' + _escapeHtml(signal.description) + '</div>';
    }
    if (signal.full_text) {
        var trunc = signal.full_text.length > 2000 ? signal.full_text.substring(0, 2000) + '...' : signal.full_text;
        html += '<div class="scr-context-fulltext">' + _escapeHtml(trunc) + '</div>';
    }
    grid.innerHTML = html;
}


// ==================== RUN SCREENING ====================

async function runScreening() {
    var input = document.getElementById('screeningInput');
    var btn = document.getElementById('screeningSearchBtn');
    var entityType = document.getElementById('screeningEntityType');
    if (!input) return;

    var name = input.value.trim();
    if (name.length < 2) return;

    btn.disabled = true;
    btn.textContent = 'Checking...';

    // Show loading in results
    var tbody = document.getElementById('scrResultsBody');
    var empty = document.getElementById('scrResultsEmpty');
    var summary = document.getElementById('scrSummary');
    if (tbody) tbody.innerHTML = '<tr><td colspan="6" class="scr-results-loading"><div class="spinner"></div>Screening "' + _escapeHtml(name) + '"...</td></tr>';
    if (empty) empty.style.display = 'none';
    if (summary) summary.innerHTML = '';

    try {
        var response = await fetch('/api/v1/screening/check', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                name: name,
                entity_type: entityType ? entityType.value : 'Person'
            })
        });

        if (!response.ok) {
            var err = await response.json().catch(function() { return {}; });
            throw new Error(err.detail || 'HTTP ' + response.status);
        }

        var data = await response.json();
        _scrState.allHits = data.hits || [];
        _scrState.autoHits = [];
        _scrState.query = data.query;
        _scrState.elapsedMs = data.elapsed_ms || 0;
        _scrState.sourcesFailed = data.sources_failed || [];
        _scrResetFilters();
        _scrUpdateSourceCounts();
        _scrUpdateSourceBar();
        _scrRenderResults();
        _scrSwitchTab('results');

    } catch (error) {
        if (summary) {
            summary.innerHTML = '<div class="scr-summary has-hits"><span class="scr-summary-icon">&#9888;</span><span class="scr-summary-text">Screening failed: ' + _escapeHtml(error.message) + '</span></div>';
        }
        if (tbody) tbody.innerHTML = '';
    } finally {
        btn.disabled = false;
        btn.textContent = 'Screen';
    }
}


// ==================== SOURCE BAR ====================

function _scrResetSourceBar() {
    _scrState.sourceCounts = {};
    _scrState.sourcesFailed = [];
    _SCR_SOURCES.forEach(function(src) {
        _scrState.sourceCounts[src] = 0;
        var el = document.getElementById('scrCount_' + src);
        if (el) el.innerHTML = '&mdash;';
    });
    var bar = document.getElementById('scrSourceBar');
    if (bar) bar.querySelectorAll('.scr-source-badge').forEach(function(b) {
        b.classList.remove('active', 'disabled', 'failed');
    });
}

function _scrUpdateSourceCounts() {
    var counts = {};
    _SCR_SOURCES.forEach(function(s) { counts[s] = 0; });
    _scrState.allHits.forEach(function(h) { counts[h.source] = (counts[h.source] || 0) + 1; });
    _scrState.sourceCounts = counts;
}

function _scrUpdateSourceBar() {
    _SCR_SOURCES.forEach(function(src) {
        var badge = document.querySelector('.scr-source-badge[data-source="' + src + '"]');
        var countEl = document.getElementById('scrCount_' + src);
        if (!badge) return;

        var count = _scrState.sourceCounts[src] || 0;
        var failed = _scrState.sourcesFailed.indexOf(src) !== -1;

        badge.classList.toggle('failed', failed);
        badge.classList.toggle('active', _scrState.sourceFilter === src);
        // Don't mark as disabled if we have hits or it was explicitly checked
        if (countEl) countEl.textContent = failed ? '\u2717' : String(count);
    });
}

function _scrToggleSource(src) {
    var badge = document.querySelector('.scr-source-badge[data-source="' + src + '"]');
    if (badge && badge.classList.contains('disabled')) return;
    _scrState.sourceFilter = (_scrState.sourceFilter === src) ? null : src;
    _scrUpdateSourceBar();
    _scrRenderResults();
}


// ==================== INLINE FILTERS ====================

function _scrResetFilters() {
    _scrState.sourceFilter = null;
    _scrState.scoreTier = 'all';
    _scrState.catFilter = null;
    _scrState.textFilter = '';
    _scrState.sortCol = 'score';
    _scrState.sortDir = 'desc';
    _scrState.expandedRow = null;

    var search = document.getElementById('scrResultSearch');
    if (search) search.value = '';
}

function _scrOnFilterChange() {
    var search = document.getElementById('scrResultSearch');
    _scrState.textFilter = search ? search.value.toLowerCase() : '';
    _scrRenderResults();
}

function _scrSetScoreTier(tier) {
    _scrState.scoreTier = tier;
    var overlay = document.getElementById('screeningOverlay');
    if (overlay) overlay.querySelectorAll('.scr-score-btn').forEach(function(b) {
        b.classList.toggle('active', b.dataset.tier === tier);
    });
    _scrRenderResults();
}

function _scrToggleCat(cat) {
    _scrState.catFilter = (_scrState.catFilter === cat) ? null : cat;
    _scrRenderCatChips();
    _scrRenderResults();
}

function _scrRenderCatChips() {
    var container = document.getElementById('scrCatChips');
    if (!container) return;
    var cats = {};
    _scrState.allHits.forEach(function(h) { cats[h.category] = 1; });
    var html = '';
    for (var cat in cats) {
        var display = cat.replace(/_/g, ' ');
        html += '<button class="scr-cat-chip' + (_scrState.catFilter === cat ? ' active' : '') + '" onclick="_scrToggleCat(\'' + cat + '\')">' + display + '</button> ';
    }
    container.innerHTML = html;
}


// ==================== SORT ====================

function _scrSort(col) {
    if (_scrState.sortCol === col) {
        _scrState.sortDir = _scrState.sortDir === 'asc' ? 'desc' : 'asc';
    } else {
        _scrState.sortCol = col;
        _scrState.sortDir = col === 'score' ? 'desc' : 'asc';
    }
    // Update th classes
    ['score', 'source', 'name', 'category'].forEach(function(c) {
        var th = document.getElementById('scrTh_' + c);
        if (th) {
            th.classList.remove('sorted-asc', 'sorted-desc');
            if (c === _scrState.sortCol) th.classList.add('sorted-' + _scrState.sortDir);
        }
    });
    _scrRenderResults();
}


// ==================== RENDER RESULTS ====================

function _scrGetFilteredHits() {
    var hits = _scrState.allHits.slice();

    // Source filter
    if (_scrState.sourceFilter) {
        hits = hits.filter(function(h) { return h.source === _scrState.sourceFilter; });
    }

    // Score tier
    if (_scrState.scoreTier !== 'all') {
        var min = parseInt(_scrState.scoreTier, 10);
        hits = hits.filter(function(h) { return h.score >= min; });
    }

    // Category filter
    if (_scrState.catFilter) {
        hits = hits.filter(function(h) { return h.category === _scrState.catFilter; });
    }

    // Text search within results
    if (_scrState.textFilter) {
        var q = _scrState.textFilter;
        hits = hits.filter(function(h) {
            return (h.name || '').toLowerCase().indexOf(q) !== -1 ||
                   (h.category || '').toLowerCase().indexOf(q) !== -1 ||
                   (h.source || '').toLowerCase().indexOf(q) !== -1 ||
                   JSON.stringify(h.details || {}).toLowerCase().indexOf(q) !== -1;
        });
    }

    // Sort
    var col = _scrState.sortCol;
    var dir = _scrState.sortDir === 'asc' ? 1 : -1;
    hits.sort(function(a, b) {
        var av = a[col] || '', bv = b[col] || '';
        if (typeof av === 'number' && typeof bv === 'number') return (av - bv) * dir;
        return String(av).localeCompare(String(bv)) * dir;
    });

    return hits;
}

function _scrRenderEmpty() {
    var tbody = document.getElementById('scrResultsBody');
    var empty = document.getElementById('scrResultsEmpty');
    var summary = document.getElementById('scrSummary');
    if (tbody) tbody.innerHTML = '';
    if (empty) empty.style.display = 'block';
    if (summary) summary.innerHTML = '';
}

function _scrRenderResults() {
    var tbody = document.getElementById('scrResultsBody');
    var empty = document.getElementById('scrResultsEmpty');
    var summary = document.getElementById('scrSummary');
    if (!tbody) return;

    var hits = _scrGetFilteredHits();
    _scrRenderCatChips();

    // Summary
    if (summary && _scrState.allHits.length > 0) {
        var totalHits = _scrState.allHits.length;
        var showingHits = hits.length;
        var cls = totalHits > 0 ? 'has-hits' : 'no-hits';
        var icon = totalHits > 0 ? '&#9888;' : '&#10003;';
        var text = totalHits === 0
            ? 'No matches found for "' + _escapeHtml(_scrState.query) + '"'
            : totalHits + ' match' + (totalHits !== 1 ? 'es' : '') + ' found for "' + _escapeHtml(_scrState.query) + '"';
        if (showingHits !== totalHits) text += ' (showing ' + showingHits + ')';
        summary.innerHTML = '<div class="scr-summary ' + cls + '">' +
            '<span class="scr-summary-icon">' + icon + '</span>' +
            '<span class="scr-summary-text">' + text + '</span>' +
            '<span class="scr-summary-meta">' + Math.round(_scrState.elapsedMs) + 'ms</span></div>';
    } else if (summary && _scrState.allHits.length === 0 && _scrState.query && _scrState.query !== '(auto-screened)') {
        summary.innerHTML = '<div class="scr-summary no-hits"><span class="scr-summary-icon">&#10003;</span><span class="scr-summary-text">No matches found for "' + _escapeHtml(_scrState.query) + '"</span><span class="scr-summary-meta">' + Math.round(_scrState.elapsedMs) + 'ms</span></div>';
    }

    if (hits.length === 0) {
        if (_scrState.allHits.length === 0) {
            tbody.innerHTML = '';
            if (empty) empty.style.display = _scrState.query ? 'none' : 'block';
        } else {
            tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;padding:20px;color:var(--text-muted)">No results match current filters.</td></tr>';
            if (empty) empty.style.display = 'none';
        }
        return;
    }

    if (empty) empty.style.display = 'none';

    var html = '';
    for (var i = 0; i < hits.length; i++) {
        var hit = hits[i];
        var scoreClass = hit.score >= 80 ? 'high' : hit.score >= 60 ? 'medium' : 'low';
        var catDisplay = (hit.category || '').replace(/_/g, ' ');
        var detailSummary = _scrBuildDetailSummary(hit.details || {});
        var isExpanded = _scrState.expandedRow === i;

        html += '<tr class="' + (isExpanded ? 'expanded' : '') + '" onclick="_scrToggleExpand(' + i + ')" style="cursor:pointer">';
        html += '<td><span class="scr-score-cell ' + scoreClass + '">' + Math.round(hit.score) + '%</span></td>';
        html += '<td><span class="scr-src-cell ' + hit.source + '">' + _SCR_SOURCE_LABELS[hit.source] || hit.source.toUpperCase() + '</span></td>';
        html += '<td title="' + _escapeHtml(hit.name) + '">' + _escapeHtml(hit.name) + '</td>';
        html += '<td class="scr-cat-cell">' + catDisplay + '</td>';
        html += '<td class="scr-detail-cell">' + detailSummary + '</td>';
        html += '<td>' + (hit.url ? '<a href="' + _escapeHtml(hit.url) + '" target="_blank" rel="noopener noreferrer" class="scr-link-btn" onclick="event.stopPropagation()" title="View source record">&#8599;</a>' : '') + '</td>';
        html += '</tr>';

        // Expandable detail row
        if (isExpanded) {
            html += '<tr class="scr-detail-row"><td colspan="6">' + _scrBuildDetailGrid(hit) + '</td></tr>';
        }
    }

    tbody.innerHTML = html;
}

function _scrToggleExpand(idx) {
    _scrState.expandedRow = (_scrState.expandedRow === idx) ? null : idx;
    _scrRenderResults();
}


// ==================== DETAIL RENDERING ====================

function _scrBuildDetailSummary(details) {
    var parts = [];
    var dob = details.dates_of_birth_used || details.date_of_birth || details.birth_date || details.birthDate;
    if (dob) parts.push('DOB: ' + _escapeHtml(Array.isArray(dob) ? dob[0] : dob));
    var nat = details.nationality || details.nationalities || details.countries;
    if (nat) parts.push(_escapeHtml(Array.isArray(nat) ? nat.join(', ') : nat));
    if (details.datasets) parts.push(_escapeHtml(Array.isArray(details.datasets) ? details.datasets.join(', ') : details.datasets));
    if (details.charges) parts.push('Charges: ' + _escapeHtml((Array.isArray(details.charges) ? details.charges[0] : details.charges).substring(0, 80)));
    if (details.sanctions) parts.push(_escapeHtml(details.sanctions.substring(0, 80)));
    return parts.join(' &middot; ') || '<span style="color:var(--text-muted)">—</span>';
}

function _scrBuildDetailGrid(hit) {
    var details = hit.details || {};
    var fields = [];

    // Source & entity context
    if (hit.entity) fields.push(['Searched Entity', hit.entity]);
    if (hit.entity_type) fields.push(['Entity Type', hit.entity_type]);

    // Identity
    var dob = details.dates_of_birth_used || details.date_of_birth || details.birth_date || details.birthDate;
    if (dob) fields.push(['Date of Birth', Array.isArray(dob) ? dob.join(', ') : dob]);
    if (details.nationality) fields.push(['Nationality', Array.isArray(details.nationality) ? details.nationality.join(', ') : details.nationality]);
    if (details.nationalities) fields.push(['Nationalities', Array.isArray(details.nationalities) ? details.nationalities.join(', ') : details.nationalities]);
    if (details.countries) fields.push(['Countries', Array.isArray(details.countries) ? details.countries.join(', ') : details.countries]);
    if (details.place_of_birth) fields.push(['Place of Birth', details.place_of_birth]);
    if (details.sex || details.sex_id) fields.push(['Sex', details.sex || details.sex_id]);

    // Physical
    if (details.hair) fields.push(['Hair', details.hair]);
    if (details.eyes) fields.push(['Eyes', details.eyes]);
    if (details.height || details.height_min) fields.push(['Height', details.height || details.height_min]);
    if (details.weight) fields.push(['Weight', details.weight]);

    // Legal
    if (details.charges) fields.push(['Charges', Array.isArray(details.charges) ? details.charges.join('; ') : details.charges]);
    if (details.sanctions) fields.push(['Sanctions', details.sanctions]);
    if (details.caution) fields.push(['Caution', details.caution]);
    if (details.reward_text) fields.push(['Reward', details.reward_text]);
    if (details.warning_message) fields.push(['Warning', details.warning_message]);

    // Metadata
    if (details.datasets) fields.push(['Datasets', Array.isArray(details.datasets) ? details.datasets.join(', ') : details.datasets]);
    if (details.subjects) fields.push(['Subjects', Array.isArray(details.subjects) ? details.subjects.join(', ') : details.subjects]);
    if (details.topics) fields.push(['Topics', Array.isArray(details.topics) ? details.topics.join(', ') : details.topics]);
    if (details.identifiers) fields.push(['Identifiers', details.identifiers]);
    if (details.matched_alias) fields.push(['Matched Alias', details.matched_alias]);
    if (details.aliases) fields.push(['Aliases', Array.isArray(details.aliases) ? details.aliases.join(', ') : details.aliases]);
    if (details.target_type) fields.push(['Target Type', details.target_type]);
    if (details.source_id) fields.push(['Source ID', details.source_id]);
    if (details.listed_on) fields.push(['Listed On', details.listed_on]);
    if (details.positions) fields.push(['Positions', details.positions]);
    if (details.remarks) fields.push(['Remarks', details.remarks]);
    if (details.description) fields.push(['Description', details.description]);

    if (fields.length === 0) return '<div style="color:var(--text-muted);font-size:11px">No additional details available.</div>';

    var html = '<div class="scr-detail-grid">';
    for (var i = 0; i < fields.length; i++) {
        var val = String(fields[i][1] || '');
        if (val.length > 500) val = val.substring(0, 500) + '...';
        html += '<div class="scr-detail-field"><span class="scr-detail-key">' + fields[i][0] + '</span><span class="scr-detail-val">' + _escapeHtml(val) + '</span></div>';
    }
    html += '</div>';
    if (hit.url) {
        html += '<div style="margin-top:8px"><a href="' + _escapeHtml(hit.url) + '" target="_blank" rel="noopener noreferrer" style="color:var(--accent-primary);font-size:10px;text-decoration:none">View Full Source Record &rarr;</a></div>';
    }
    return html;
}


// ==================== SCREENING LOG ====================

async function _scrFetchLog() {
    var tbody = document.getElementById('scrLogBody');
    if (!tbody) return;

    try {
        var resp = await fetch('/api/v1/screening/log/recent');
        var data = await resp.json();
        var entries = data.entries || [];

        if (entries.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:var(--text-muted);padding:20px">No screening history.</td></tr>';
            return;
        }

        tbody.innerHTML = entries.map(function(e) {
            var time = '';
            try {
                var d = new Date(e.created_at);
                time = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false });
                if (d.toDateString() !== new Date().toDateString()) {
                    time = d.toLocaleDateString('en', { month: 'short', day: 'numeric' }) + ' ' + time;
                }
            } catch (err) { time = e.created_at || ''; }

            var hitsClass = e.hit_count > 0 ? 'scr-log-hits-positive' : 'scr-log-hits-zero';
            return '<tr>' +
                '<td style="color:var(--text-muted);font-variant-numeric:tabular-nums">' + time + '</td>' +
                '<td style="font-family:monospace;font-size:9px;color:var(--text-muted)">' + _escapeHtml(e.client_ip || '') + '</td>' +
                '<td class="log-name-cell" onclick="_scrSearchFromLog(\'' + _escapeHtml((e.queried_name || '').replace(/'/g, "\\'")) + '\')">' + _escapeHtml(e.queried_name) + '</td>' +
                '<td class="' + hitsClass + '">' + e.hit_count + '</td>' +
                '<td style="font-size:9px;color:var(--text-muted)">' + _escapeHtml(e.sources_checked || '') + '</td>' +
                '</tr>';
        }).join('');
    } catch (e) {
        tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:var(--text-muted)">Failed to load log.</td></tr>';
    }
}

function _scrSearchFromLog(name) {
    var input = document.getElementById('screeningInput');
    if (input) input.value = name;
    _scrSwitchTab('results');
    runScreening();
}


// ==================== HELPERS ====================

function _getSignalById(signalId) {
    if (!signalId || typeof allSignals === 'undefined') return null;
    var id = parseInt(signalId);
    return allSignals.find(function(s) { return s.id === id; }) || null;
}

// _escapeHtml is now a thin wrapper around the shared escapeHtml() from config.js
function _escapeHtml(text) {
    return escapeHtml(text);
}
