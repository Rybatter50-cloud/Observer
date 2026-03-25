/**
 * Observer Client - Search & Filter Modal
 * 4-tab modal: Quick Filters, Filter Builder, SQL Query, Saved Filters
 *
 * Follows screening.js lazy-creation pattern.
 * Quick Filters + Builder run client-side against allSignals.
 * SQL tab runs server-side via POST /api/v1/intelligence/query.
 */

// ==================== SOC REGION DEFINITIONS ====================
var SOC_REGIONS = {
    SOCNORTH: {
        label: 'North America',
        desc: 'SOCNORTH',
        groups: ['usa', 'canada', 'mexico', 'bahamas'],
        countries: ['United States', 'USA', 'Canada', 'Mexico', 'Bahamas']
    },
    SOCSOUTH: {
        label: 'Central & South America',
        desc: 'SOCSOUTH',
        groups: [
            'brazil', 'colombia', 'el_salvador', 'panama', 'peru', 'argentina',
            'chile', 'honduras', 'guatemala', 'antigua_and_barbuda', 'barbados',
            'cuba', 'dominica', 'dominican_republic', 'grenada', 'haiti',
            'jamaica', 'saint_kitts_and_nevis', 'saint_lucia',
            'saint_vincent_and_the_grenadines', 'trinidad_and_tobago',
            'belize', 'bolivia', 'costa_rica', 'ecuador', 'guyana',
            'nicaragua', 'paraguay', 'suriname', 'uruguay', 'venezuela'
        ],
        countries: [
            'Brazil', 'Colombia', 'El Salvador', 'Panama', 'Peru', 'Argentina',
            'Chile', 'Honduras', 'Guatemala', 'Antigua', 'Barbados',
            'Cuba', 'Dominica', 'Dominican Republic', 'Grenada', 'Haiti',
            'Jamaica', 'Saint Kitts', 'Saint Lucia', 'Saint Vincent',
            'Trinidad', 'Tobago', 'Belize', 'Bolivia', 'Costa Rica',
            'Ecuador', 'Guyana', 'Nicaragua', 'Paraguay', 'Suriname',
            'Uruguay', 'Venezuela'
        ]
    },
    SOCEUR: {
        label: 'Europe',
        desc: 'SOCEUR',
        groups: [
            'germany', 'uk', 'france', 'poland', 'ukraine', 'estonia',
            'latvia', 'lithuania', 'turkey', 'israel', 'russia'
        ],
        countries: [
            'Germany', 'United Kingdom', 'Britain', 'France', 'Poland',
            'Ukraine', 'Estonia', 'Latvia', 'Lithuania', 'Turkey', 'Israel',
            'Russia', 'Kyiv', 'Moscow', 'Berlin', 'Paris', 'London'
        ]
    },
    SOCCENT: {
        label: 'Middle East & Central Asia',
        desc: 'SOCCENT',
        groups: [
            'iraq', 'afghanistan', 'saudi_arabia', 'uae', 'jordan', 'qatar',
            'kuwait', 'iran', 'pakistan', 'egypt', 'kazakhstan', 'uzbekistan'
        ],
        countries: [
            'Iraq', 'Afghanistan', 'Saudi Arabia', 'UAE', 'Emirates',
            'Jordan', 'Qatar', 'Kuwait', 'Iran', 'Pakistan', 'Egypt',
            'Kazakhstan', 'Uzbekistan', 'Baghdad', 'Kabul', 'Tehran', 'Cairo'
        ]
    },
    SOCAFRICA: {
        label: 'Africa',
        desc: 'SOCAFRICA',
        groups: [
            'niger', 'somalia', 'djibouti', 'kenya', 'nigeria', 'mali',
            'chad', 'uganda', 'ethiopia', 'libya', 'tunisia'
        ],
        countries: [
            'Niger', 'Somalia', 'Djibouti', 'Kenya', 'Nigeria', 'Mali',
            'Chad', 'Uganda', 'Ethiopia', 'Libya', 'Tunisia',
            'Mogadishu', 'Nairobi', 'Lagos', 'Tripoli'
        ]
    },
    SOCPAC: {
        label: 'Indo-Pacific',
        desc: 'SOCPAC',
        groups: [
            'japan', 'south_korea', 'philippines', 'thailand', 'vietnam',
            'australia', 'india', 'indonesia', 'taiwan'
        ],
        countries: [
            'Japan', 'South Korea', 'Korea', 'Philippines', 'Thailand',
            'Vietnam', 'Australia', 'India', 'Indonesia', 'Taiwan',
            'Tokyo', 'Seoul', 'Manila', 'Taipei'
        ]
    },
    SOCKOR: {
        label: 'Korean Peninsula',
        desc: 'SOCKOR',
        groups: ['south_korea'],
        countries: ['South Korea', 'North Korea', 'Korea', 'Seoul', 'Pyongyang', 'DPRK']
    }
};

// ==================== RISK INDICATOR LABELS ====================
var SFM_INDICATORS = {
    'T': 'Terrorism', 'K': 'Kidnapping', 'U': 'Civil Unrest',
    'F': 'Financial', 'H': 'Health', 'X': 'Cyber Threat',
    'N': 'Natural Disaster', 'C': 'Crime', 'D': 'Wrongful Detention',
    'E': 'Time-Limited Event', 'M': 'Military'
};

// ==================== FILTER BUILDER FIELD DEFS ====================
var SFM_FIELDS = {
    title:              { label: 'Title',             type: 'text',    highCard: true },
    description:        { label: 'Description',       type: 'text',    highCard: true },
    location:           { label: 'Location',          type: 'text',    highCard: true },
    source:             { label: 'Source',             type: 'text',    highCard: false },
    author:             { label: 'Author',             type: 'text',    highCard: true },
    source_group:       { label: 'Feed Group',         type: 'text',    highCard: false },
    source_language:    { label: 'Language',            type: 'text',    highCard: false },
    collector:          { label: 'Collector',           type: 'text',    highCard: false },
    relevance_score:    { label: 'Relevance Score',    type: 'number' },
    source_confidence:  { label: 'Source Confidence',  type: 'number' },
    author_confidence:  { label: 'Author Confidence',  type: 'number' },
    casualties:         { label: 'Casualties',         type: 'number' },
    risk_indicators:    { label: 'Risk Indicators',    type: 'array' },
    is_translated:      { label: 'Translated',         type: 'boolean' },
    created_at:         { label: 'Ingested At',        type: 'timestamp' },
    published_at:       { label: 'Published At',       type: 'timestamp' }
};

var SFM_OPS = {
    text:      ['contains', 'equals', 'starts with', 'not contains', 'regex'],
    number:    ['=', '>', '<', '>=', '<=', 'between'],
    array:     ['includes any', 'includes all', 'excludes'],
    boolean:   ['is true', 'is false'],
    timestamp: ['after', 'before', 'between', 'last N hours']
};

// SQL column reference
var SFM_SQL_COLS = [
    ['id', 'int'], ['title', 'text'], ['description', 'text'], ['location', 'text'],
    ['relevance_score', 'int'], ['casualties', 'int'], ['published_at', 'timestamptz'],
    ['url', 'text'], ['source', 'text'], ['collector', 'text'],
    ['risk_indicators', 'text[]'], ['is_translated', 'bool'],
    ['source_language', 'text'], ['author', 'text'], ['source_group', 'text'],
    ['source_confidence', 'int'], ['author_confidence', 'int'],
    ['screening_hits', 'jsonb'], ['created_at', 'timestamptz']
];

// ==================== DRAG STATE ====================
var _sfmDrag = { active: false, startX: 0, startY: 0, offsetX: 0, offsetY: 0 };

function _sfmOnDragStart(e) {
    // Only left mouse button; ignore clicks on buttons/inputs inside header
    if (e.button !== 0) return;
    var tag = e.target.tagName;
    if (tag === 'BUTTON' || tag === 'INPUT' || tag === 'SELECT') return;
    var modal = document.querySelector('.sfm-modal');
    if (!modal) return;
    _sfmDrag.active = true;
    _sfmDrag.startX = e.clientX;
    _sfmDrag.startY = e.clientY;
    // Read current transform translate if any
    var style = modal.style.transform || '';
    var match = style.match(/translate\(([^,]+),\s*([^)]+)\)/);
    _sfmDrag.offsetX = match ? parseFloat(match[1]) : 0;
    _sfmDrag.offsetY = match ? parseFloat(match[2]) : 0;
    document.addEventListener('mousemove', _sfmOnDragMove);
    document.addEventListener('mouseup', _sfmOnDragEnd);
    e.preventDefault();
}

function _sfmOnDragMove(e) {
    if (!_sfmDrag.active) return;
    var dx = e.clientX - _sfmDrag.startX + _sfmDrag.offsetX;
    var dy = e.clientY - _sfmDrag.startY + _sfmDrag.offsetY;
    var modal = document.querySelector('.sfm-modal');
    if (modal) modal.style.transform = 'translate(' + dx + 'px, ' + dy + 'px)';
}

function _sfmOnDragEnd() {
    if (!_sfmDrag.active) return;
    _sfmDrag.active = false;
    // Persist final offset so next drag continues from here
    var modal = document.querySelector('.sfm-modal');
    if (modal) {
        var style = modal.style.transform || '';
        var match = style.match(/translate\(([^,]+),\s*([^)]+)\)/);
        _sfmDrag.offsetX = match ? parseFloat(match[1]) : 0;
        _sfmDrag.offsetY = match ? parseFloat(match[2]) : 0;
    }
    document.removeEventListener('mousemove', _sfmOnDragMove);
    document.removeEventListener('mouseup', _sfmOnDragEnd);
}

// ==================== MODAL STATE ====================
var sfmState = {
    open: false,
    activeTab: 'quick',
    // Quick filters
    timeWindow: 'all', // '4h', '24h', '72h', '7d', 'all'
    searchText: '',
    regions: [],       // active SOC region keys (source_group filter)
    newsRegions: [],   // active SOC region keys (content/country-name filter)
    negateRegions: false,
    scoreTier: 'all',  // 'all', '40', '65', '85'
    translated: false,
    screening: false,
    riskIndicators: [],
    // Builder
    conditions: [],
    builderLogic: 'AND',
    // SQL
    sqlQuery: '',
    sqlActive: false,
    sqlBackup: null,   // backup of allSignals before SQL override
    // Dirty tracking
    dirty: false
};

var _sfmNextCondId = 1;
var _sfmDebounceTimer = null;
var _sfmFetchTimer = null;

// Parsed search tokens from Google-like search input
// { required: ['term1', 'term2'], excluded: ['term3'], phrases: ['"exact phrase"'] }
var sfmSearchTokens = null;

// ==================== LAZY MODAL CREATION ====================

function _sfmCreateModal() {
    var overlay = document.createElement('div');
    overlay.className = 'sfm-overlay';
    overlay.id = 'sfmOverlay';
    overlay.onclick = function(e) {
        if (e.target === overlay) closeSearchFilterModal();
    };

    overlay.innerHTML = [
        '<div class="sfm-modal">',
        '  <div class="sfm-header">',
        '    <h3>Search &amp; Filter</h3>',
        '    <div class="sfm-header-actions">',
        '      <span class="sfm-match-count" id="sfmMatchCount"></span>',
        '      <button class="sfm-close" onclick="closeSearchFilterModal()">&times;</button>',
        '    </div>',
        '  </div>',
        '  <div class="sfm-tabs">',
        '    <button class="sfm-tab active" data-tab="quick" onclick="_sfmSwitchTab(\'quick\')">Quick Filters</button>',
        '    <button class="sfm-tab" data-tab="builder" onclick="_sfmSwitchTab(\'builder\')">Filter Builder</button>',
        '    <button class="sfm-tab" data-tab="sql" onclick="_sfmSwitchTab(\'sql\')">SQL Query</button>',
        '    <button class="sfm-tab" data-tab="saved" onclick="_sfmSwitchTab(\'saved\')">Saved Filters</button>',
        '  </div>',
        '  <div class="sfm-body">',
        _sfmBuildQuickTab(),
        _sfmBuildBuilderTab(),
        _sfmBuildSqlTab(),
        _sfmBuildSavedTab(),
        '  </div>',
        '</div>'
    ].join('\n');

    document.body.appendChild(overlay);

    // Make header a drag handle
    var header = overlay.querySelector('.sfm-header');
    if (header) header.addEventListener('mousedown', _sfmOnDragStart);

    return overlay;
}

// ==================== TAB HTML BUILDERS ====================

function _sfmBuildQuickTab() {
    var regionChips = '';
    var newsChips = '';
    for (var key in SOC_REGIONS) {
        var r = SOC_REGIONS[key];
        regionChips += '<button class="sfm-chip" data-region="' + key + '" onclick="_sfmToggleRegion(\'' + key + '\')" title="' + _sfmEsc(r.desc) + '">' + r.label + '</button>';
        newsChips += '<button class="sfm-chip sfm-news-chip" data-newsregion="' + key + '" onclick="_sfmToggleNewsRegion(\'' + key + '\')" title="' + _sfmEsc(r.desc) + ' — search article content for country names">' + r.label + '</button>';
    }

    var tierBtns = [
        { val: 'all', label: 'All' },
        { val: '40', label: 'Medium 40+' },
        { val: '65', label: 'High 65+' },
        { val: '85', label: 'Critical 85+' }
    ].map(function(t) {
        return '<button class="sfm-tier-btn' + (t.val === 'all' ? ' active' : '') + '" data-tier="' + t.val + '" onclick="_sfmSetTier(\'' + t.val + '\')">' + t.label + '</button>';
    }).join('');

    var riskChips = '';
    for (var code in SFM_INDICATORS) {
        riskChips += '<button class="sfm-risk-chip" data-risk="' + code + '" onclick="_sfmToggleRisk(\'' + code + '\')" title="' + SFM_INDICATORS[code] + '">' + code + ' ' + SFM_INDICATORS[code] + '</button>';
    }

    var twBtns = [
        { val: '4h', label: '4 Hours' },
        { val: '24h', label: '24 Hours' },
        { val: '72h', label: '3 Days' },
        { val: '7d', label: '7 Days' },
        { val: 'all', label: 'All Time' }
    ].map(function(t) {
        var active = t.val === sfmState.timeWindow ? ' active' : '';
        return '<button class="sfm-tw-btn' + active + '" data-tw="' + t.val + '" onclick="_sfmSetTimeWindow(\'' + t.val + '\')">' + t.label + '</button>';
    }).join('');

    return [
        '<div class="sfm-tab-panel active" data-panel="quick">',
        '  <div class="sfm-section-label">Time Window <span style="font-size:10px;color:var(--text-muted);font-weight:normal">(search scope — articles from server)</span></div>',
        '  <div class="sfm-tw-row" id="sfmTimeWindowRow">' + twBtns + '</div>',
        '  <div class="sfm-search-row">',
        '    <input type="text" class="sfm-search-input" id="sfmSearchInput" placeholder="ukraine &quot;military base&quot; -russia ..." oninput="_sfmOnSearchInput(this.value)">',
        '    <div class="sfm-search-hint">Searches within the filtered view below &nbsp;|&nbsp; &quot;quotes&quot; = exact &nbsp;|&nbsp; -word = exclude</div>',
        '  </div>',
        '  <div class="sfm-section-label">Region <span style="font-size:10px;color:var(--text-muted);font-weight:normal">(by feed source location)</span></div>',
        '  <div class="sfm-chip-grid" id="sfmRegionChips">' + regionChips + '</div>',
        '  <label class="sfm-toggle" style="margin-top:6px"><input type="checkbox" id="sfmNegateRegions" onchange="_sfmToggleNegateRegions(this.checked)"> Exclude selected regions (show everything else)</label>',
        '  <div class="sfm-section-label">Region / News <span style="font-size:10px;color:var(--text-muted);font-weight:normal">(by article content — searches titles &amp; descriptions for country names)</span></div>',
        '  <div class="sfm-chip-grid" id="sfmNewsChips">' + newsChips + '</div>',
        '  <div class="sfm-stack-hint" id="sfmStackHint" style="display:none;font-size:10px;color:var(--accent);padding:3px 0">&#9889; Stacked: Region feeds + News mentions combined (OR)</div>',
        '  <div class="sfm-section-label">Score Tier</div>',
        '  <div class="sfm-tier-row" id="sfmTierRow">' + tierBtns + '</div>',
        '  <div class="sfm-section-label">Toggles</div>',
        '  <div class="sfm-toggle-row">',
        '    <label class="sfm-toggle"><input type="checkbox" id="sfmTranslated" onchange="_sfmToggleTranslated(this.checked)"> Translated only</label>',
        '    <label class="sfm-toggle"><input type="checkbox" id="sfmScreening" onchange="_sfmToggleScreening(this.checked)"> Has screening hits</label>',
        '  </div>',
        '  <div class="sfm-section-label">Risk Indicators</div>',
        '  <div class="sfm-risk-grid" id="sfmRiskGrid">' + riskChips + '</div>',
        '  <div class="sfm-actions-row">',
        '    <button class="sfm-btn sfm-btn-danger" onclick="_sfmClearAll()">Clear All</button>',
        '    <div style="display:flex;gap:8px">',
        '      <button class="sfm-btn sfm-btn-ghost" onclick="_sfmSavePrompt()">Save Filter</button>',
        '      <button class="sfm-btn sfm-btn-primary" onclick="_sfmApplyAndClose()">Apply</button>',
        '    </div>',
        '  </div>',
        '</div>'
    ].join('\n');
}

function _sfmBuildBuilderTab() {
    return [
        '<div class="sfm-tab-panel" data-panel="builder">',
        '  <div class="sfm-section-label">Conditions <span style="font-size:10px;color:var(--text-muted);font-weight:normal">(click AND/OR between rows to toggle)</span></div>',
        '  <div class="sfm-conditions" id="sfmConditions"></div>',
        '  <div class="sfm-logic-row">',
        '    <button class="sfm-btn sfm-btn-ghost" onclick="_sfmAddCondition()" style="padding:5px 12px;font-size:9px">+ Add Condition</button>',
        '    <span style="font-size:10px;color:var(--text-muted);margin-left:auto" id="sfmBuilderCount"></span>',
        '  </div>',
        '  <div class="sfm-actions-row">',
        '    <button class="sfm-btn sfm-btn-danger" onclick="_sfmClearAll()">Clear All</button>',
        '    <div style="display:flex;gap:8px">',
        '      <button class="sfm-btn sfm-btn-ghost" onclick="_sfmSavePrompt()">Save Filter</button>',
        '      <button class="sfm-btn sfm-btn-primary" onclick="_sfmApplyAndClose()">Apply</button>',
        '    </div>',
        '  </div>',
        '</div>'
    ].join('\n');
}

function _sfmBuildSqlTab() {
    var refHtml = SFM_SQL_COLS.map(function(c) {
        return '<div class="sfm-sql-ref-col" onclick="_sfmInsertCol(\'' + c[0] + '\')"><span class="col-name">' + c[0] + '</span><span class="col-type">' + c[1] + '</span></div>';
    }).join('');

    return [
        '<div class="sfm-tab-panel" data-panel="sql">',
        '  <div class="sfm-sql-layout">',
        '    <div class="sfm-sql-editor-wrap">',
        '      <textarea class="sfm-sql-textarea" id="sfmSqlTextarea" placeholder="SELECT * FROM intel_signals WHERE processed = TRUE ORDER BY created_at DESC LIMIT 500">SELECT * FROM intel_signals\nWHERE processed = TRUE\nORDER BY created_at DESC\nLIMIT 500</textarea>',
        '      <div class="sfm-sql-actions">',
        '        <button class="sfm-btn sfm-btn-primary" onclick="_sfmExecuteSql()">Execute</button>',
        '        <button class="sfm-btn sfm-btn-ghost" onclick="_sfmClearSql()">Clear SQL Override</button>',
        '        <span class="sfm-sql-status" id="sfmSqlStatus"></span>',
        '      </div>',
        '    </div>',
        '    <div class="sfm-sql-ref">',
        '      <div class="sfm-sql-ref-title">Columns (click to insert)</div>',
        '      ' + refHtml,
        '    </div>',
        '  </div>',
        '  <div class="sfm-sql-results" id="sfmSqlResults"></div>',
        '</div>'
    ].join('\n');
}

function _sfmBuildSavedTab() {
    return [
        '<div class="sfm-tab-panel" data-panel="saved">',
        '  <div class="sfm-saved-list" id="sfmSavedList"></div>',
        '  <div class="sfm-actions-row">',
        '    <div style="display:flex;gap:8px">',
        '      <button class="sfm-btn sfm-btn-ghost" onclick="_sfmExportFilters()">Export All</button>',
        '      <button class="sfm-btn sfm-btn-ghost" onclick="_sfmImportFilters()">Import</button>',
        '    </div>',
        '  </div>',
        '  <div id="sfmSavePromptArea"></div>',
        '</div>'
    ].join('\n');
}

// ==================== OPEN / CLOSE ====================

function openSearchFilterModal() {
    var overlay = document.getElementById('sfmOverlay');
    if (!overlay) overlay = _sfmCreateModal();
    // Reset drag position so modal opens centered
    var modal = overlay.querySelector('.sfm-modal');
    if (modal) modal.style.transform = '';
    _sfmDrag.offsetX = 0;
    _sfmDrag.offsetY = 0;
    overlay.classList.add('active');
    sfmState.open = true;

    // Sync time window from sidebar state on open
    sfmState.timeWindow = currentTimeWindow || 'all';
    var twRow = document.getElementById('sfmTimeWindowRow');
    if (twRow) twRow.querySelectorAll('.sfm-tw-btn').forEach(function(b) {
        b.classList.toggle('active', b.dataset.tw === sfmState.timeWindow);
    });

    // Sync search input with current state
    var inp = document.getElementById('sfmSearchInput');
    if (inp) inp.value = sfmState.searchText;

    // Render saved list
    _sfmRenderSaved();
    // Update match count
    _sfmUpdateMatchCount();
    // Focus search
    setTimeout(function() { if (inp) inp.focus(); }, 100);
}

function closeSearchFilterModal() {
    var overlay = document.getElementById('sfmOverlay');
    if (overlay) overlay.classList.remove('active');
    sfmState.open = false;
}

// ==================== TAB SWITCHING ====================

function _sfmSwitchTab(tabName) {
    sfmState.activeTab = tabName;
    var overlay = document.getElementById('sfmOverlay');
    if (!overlay) return;

    overlay.querySelectorAll('.sfm-tab').forEach(function(t) {
        t.classList.toggle('active', t.dataset.tab === tabName);
    });
    overlay.querySelectorAll('.sfm-tab-panel').forEach(function(p) {
        p.classList.toggle('active', p.dataset.panel === tabName);
    });
}

// ==================== QUICK FILTER HANDLERS ====================

function _sfmOnSearchInput(val) {
    sfmState.searchText = val;
    sfmState.dirty = true;
    // Sync sidebar search input
    var sbi = document.getElementById('sidebarSearchInput');
    if (sbi && sbi.value !== val) sbi.value = val;
    // Search operates client-side on the filtered view — no server fetch.
    // Debounce 300ms for typing, then just re-filter locally.
    if (_sfmDebounceTimer) clearTimeout(_sfmDebounceTimer);
    _sfmDebounceTimer = setTimeout(function() {
        _sfmApplySearchOnly();
    }, 300);
}

function _sfmToggleRegion(key) {
    var idx = sfmState.regions.indexOf(key);
    if (idx === -1) {
        sfmState.regions.push(key);
    } else {
        sfmState.regions.splice(idx, 1);
    }
    _sfmRefreshRegionChips();
    sfmState.dirty = true;
    _sfmApplyLive();
}

function _sfmToggleNewsRegion(key) {
    var idx = sfmState.newsRegions.indexOf(key);
    if (idx === -1) {
        sfmState.newsRegions.push(key);
    } else {
        sfmState.newsRegions.splice(idx, 1);
    }
    _sfmRefreshRegionChips();
    sfmState.dirty = true;
    _sfmApplyLive();
}

function _sfmToggleNegateRegions(checked) {
    sfmState.negateRegions = checked;
    _sfmRefreshRegionChips();
    sfmState.dirty = true;
    _sfmApplyLive();
}

function _sfmSetTier(val) {
    sfmState.scoreTier = val;
    var row = document.getElementById('sfmTierRow');
    if (row) row.querySelectorAll('.sfm-tier-btn').forEach(function(b) {
        b.classList.toggle('active', b.dataset.tier === val);
    });
    sfmState.dirty = true;
    _sfmApplyLive();
}

function _sfmToggleTranslated(checked) {
    sfmState.translated = checked;
    sfmState.dirty = true;
    _sfmApplyLive();
}

function _sfmToggleScreening(checked) {
    sfmState.screening = checked;
    sfmState.dirty = true;
    _sfmApplyLive();
}

function _sfmToggleRisk(code) {
    var idx = sfmState.riskIndicators.indexOf(code);
    if (idx === -1) {
        sfmState.riskIndicators.push(code);
    } else {
        sfmState.riskIndicators.splice(idx, 1);
    }
    var grid = document.getElementById('sfmRiskGrid');
    if (grid) grid.querySelectorAll('.sfm-risk-chip').forEach(function(c) {
        c.classList.toggle('active', sfmState.riskIndicators.indexOf(c.dataset.risk) !== -1);
    });
    sfmState.dirty = true;
    _sfmApplyLive();
}

function _sfmRefreshRegionChips() {
    var container = document.getElementById('sfmRegionChips');
    if (container) {
        container.querySelectorAll('.sfm-chip').forEach(function(c) {
            var active = sfmState.regions.indexOf(c.dataset.region) !== -1;
            c.classList.toggle('active', active && !sfmState.negateRegions);
            c.classList.toggle('negated', active && sfmState.negateRegions);
        });
    }
    // News region chips
    var newsContainer = document.getElementById('sfmNewsChips');
    if (newsContainer) {
        newsContainer.querySelectorAll('.sfm-news-chip').forEach(function(c) {
            c.classList.toggle('active', sfmState.newsRegions.indexOf(c.dataset.newsregion) !== -1);
        });
    }
    // Show stacked hint when both Region and News are active
    var hint = document.getElementById('sfmStackHint');
    if (hint) {
        hint.style.display = (sfmState.regions.length > 0 && sfmState.newsRegions.length > 0) ? '' : 'none';
    }
}

function _sfmSetTimeWindow(val) {
    sfmState.timeWindow = val;
    // Sync sidebar time buttons
    currentTimeWindow = val;
    document.querySelectorAll('.time-btn').forEach(function(b) {
        b.classList.toggle('active', b.dataset.window === val);
    });
    // Sync modal buttons
    var row = document.getElementById('sfmTimeWindowRow');
    if (row) row.querySelectorAll('.sfm-tw-btn').forEach(function(b) {
        b.classList.toggle('active', b.dataset.tw === val);
    });
    sfmState.dirty = true;
    _sfmApplyLive();
}

function _sfmClearQuick() {
    sfmState.searchText = '';
    sfmState.timeWindow = 'all';
    sfmState.regions = [];
    sfmState.newsRegions = [];
    sfmState.negateRegions = false;
    sfmState.scoreTier = 'all';
    sfmState.translated = false;
    sfmState.screening = false;
    sfmState.riskIndicators = [];
    sfmState.dirty = false;

    var inp = document.getElementById('sfmSearchInput');
    if (inp) inp.value = '';
    var neg = document.getElementById('sfmNegateRegions');
    if (neg) neg.checked = false;
    var tr = document.getElementById('sfmTranslated');
    if (tr) tr.checked = false;
    var sc = document.getElementById('sfmScreening');
    if (sc) sc.checked = false;

    _sfmRefreshRegionChips();
    _sfmSetTier('all');
    _sfmSetTimeWindow('all');

    var grid = document.getElementById('sfmRiskGrid');
    if (grid) grid.querySelectorAll('.sfm-risk-chip').forEach(function(c) { c.classList.remove('active'); });

    _sfmApplyLive();
}

// ==================== FILTER BUILDER HANDLERS ====================

function _sfmAddCondition() {
    // First condition has no connector; subsequent default to 'AND'
    var connector = sfmState.conditions.length === 0 ? null : 'AND';
    var cond = { id: _sfmNextCondId++, field: 'title', op: 'contains', value: '', value2: '', connector: connector };
    sfmState.conditions.push(cond);
    _sfmRenderConditions();
}

function _sfmToggleCondConnector(id) {
    var cond = sfmState.conditions.find(function(c) { return c.id === id; });
    if (!cond || !cond.connector) return;
    cond.connector = cond.connector === 'AND' ? 'OR' : 'AND';
    _sfmRenderConditions();
    sfmState.dirty = true;
    _sfmApplyLive();
}

function _sfmRemoveCondition(id) {
    sfmState.conditions = sfmState.conditions.filter(function(c) { return c.id !== id; });
    _sfmRenderConditions();
    sfmState.dirty = true;
    _sfmApplyLive();
}

function _sfmSetLogic(logic) {
    sfmState.builderLogic = logic;
    var overlay = document.getElementById('sfmOverlay');
    if (overlay) overlay.querySelectorAll('.sfm-logic-option').forEach(function(b) {
        b.classList.toggle('active', b.dataset.logic === logic);
    });
    sfmState.dirty = true;
    _sfmApplyLive();
}

function _sfmRenderConditions() {
    var container = document.getElementById('sfmConditions');
    if (!container) return;

    if (sfmState.conditions.length === 0) {
        container.innerHTML = '<div style="color:var(--text-muted);font-size:11px;padding:10px 0">No conditions. Click "+ Add Condition" to start building a filter.</div>';
        return;
    }

    // Migrate legacy conditions that lack a connector field
    sfmState.conditions.forEach(function(cond, idx) {
        if (idx === 0) { cond.connector = null; }
        else if (!cond.connector) { cond.connector = sfmState.builderLogic || 'AND'; }
    });

    var html = '';
    sfmState.conditions.forEach(function(cond, idx) {
        var fieldDef = SFM_FIELDS[cond.field] || SFM_FIELDS.title;
        var ops = SFM_OPS[fieldDef.type] || SFM_OPS.text;

        var fieldOpts = '';
        for (var key in SFM_FIELDS) {
            fieldOpts += '<option value="' + key + '"' + (key === cond.field ? ' selected' : '') + '>' + SFM_FIELDS[key].label + '</option>';
        }

        var opOpts = ops.map(function(op) {
            return '<option value="' + op + '"' + (op === cond.op ? ' selected' : '') + '>' + op + '</option>';
        }).join('');

        var valueHtml = _sfmBuildValueInput(cond, fieldDef);
        var count = _sfmCountMatches(cond);

        // Show AND/OR connector pill between rows (clickable toggle)
        if (idx > 0 && cond.connector) {
            var connClass = cond.connector === 'OR' ? 'sfm-connector-or' : 'sfm-connector-and';
            html += '<div class="sfm-connector-row">' +
                '<button class="sfm-connector-pill ' + connClass + '" onclick="_sfmToggleCondConnector(' + cond.id + ')" title="Click to toggle AND/OR">' +
                cond.connector + '</button></div>';
        }

        html += '<div class="sfm-condition-row" data-cid="' + cond.id + '">' +
            '<select class="sfm-condition-field" onchange="_sfmCondFieldChange(' + cond.id + ',this.value)">' + fieldOpts + '</select>' +
            '<select class="sfm-condition-op" onchange="_sfmCondOpChange(' + cond.id + ',this.value)">' + opOpts + '</select>' +
            valueHtml +
            '<span class="sfm-condition-count">' + count + '</span>' +
            '<button class="sfm-condition-remove" onclick="_sfmRemoveCondition(' + cond.id + ')">&times;</button>' +
            '</div>';
    });

    container.innerHTML = html;
}

function _sfmBuildValueInput(cond, fieldDef) {
    if (fieldDef.type === 'boolean') {
        return '<span class="sfm-condition-value" style="font-size:11px;color:var(--text-muted)">(no value needed)</span>';
    }
    if (fieldDef.type === 'timestamp') {
        if (cond.op === 'last N hours') {
            return '<input class="sfm-condition-value" type="number" min="1" placeholder="Hours" value="' + _sfmEsc(cond.value) + '" onchange="_sfmCondValueChange(' + cond.id + ',this.value)">';
        }
        if (cond.op === 'between') {
            return '<input class="sfm-condition-value" type="datetime-local" value="' + _sfmEsc(cond.value) + '" onchange="_sfmCondValueChange(' + cond.id + ',this.value)" style="flex:1">' +
                '<input class="sfm-condition-value" type="datetime-local" value="' + _sfmEsc(cond.value2 || '') + '" onchange="_sfmCondValue2Change(' + cond.id + ',this.value)" style="flex:1">';
        }
        return '<input class="sfm-condition-value" type="datetime-local" value="' + _sfmEsc(cond.value) + '" onchange="_sfmCondValueChange(' + cond.id + ',this.value)">';
    }
    if (fieldDef.type === 'number') {
        if (cond.op === 'between') {
            return '<input class="sfm-condition-value" type="number" placeholder="Min" value="' + _sfmEsc(cond.value) + '" onchange="_sfmCondValueChange(' + cond.id + ',this.value)" style="flex:1">' +
                '<input class="sfm-condition-value" type="number" placeholder="Max" value="' + _sfmEsc(cond.value2 || '') + '" onchange="_sfmCondValue2Change(' + cond.id + ',this.value)" style="flex:1">';
        }
        return '<input class="sfm-condition-value" type="number" placeholder="Value" value="' + _sfmEsc(cond.value) + '" onchange="_sfmCondValueChange(' + cond.id + ',this.value)">';
    }
    if (fieldDef.type === 'array') {
        // Multi-select for risk indicators
        var codes = Object.keys(SFM_INDICATORS);
        var selected = (cond.value || '').split(',').filter(Boolean);
        return '<div class="sfm-condition-value" style="display:flex;flex-wrap:wrap;gap:3px">' +
            codes.map(function(c) {
                var active = selected.indexOf(c) !== -1;
                return '<button class="sfm-risk-chip' + (active ? ' active' : '') + '" style="font-size:8px;padding:2px 6px" ' +
                    'onclick="_sfmCondToggleArrayVal(' + cond.id + ',\'' + c + '\')">' + c + '</button>';
            }).join('') + '</div>';
    }
    // Text fields - plain input
    return '<input class="sfm-condition-value" type="text" placeholder="Value" value="' + _sfmEsc(cond.value) + '" ' +
        'oninput="_sfmCondValueChange(' + cond.id + ',this.value)">';
}

function _sfmCondFieldChange(id, field) {
    var cond = sfmState.conditions.find(function(c) { return c.id === id; });
    if (!cond) return;
    cond.field = field;
    var def = SFM_FIELDS[field] || SFM_FIELDS.title;
    cond.op = (SFM_OPS[def.type] || SFM_OPS.text)[0];
    cond.value = '';
    cond.value2 = '';
    _sfmRenderConditions();
}

function _sfmCondOpChange(id, op) {
    var cond = sfmState.conditions.find(function(c) { return c.id === id; });
    if (cond) { cond.op = op; cond.value = ''; cond.value2 = ''; }
    _sfmRenderConditions();
}

function _sfmCondValueChange(id, val) {
    var cond = sfmState.conditions.find(function(c) { return c.id === id; });
    if (cond) cond.value = val;
    sfmState.dirty = true;
    // Debounce text input to reduce lag
    if (_sfmDebounceTimer) clearTimeout(_sfmDebounceTimer);
    _sfmDebounceTimer = setTimeout(function() {
        _sfmApplyLive();
    }, 300);
}

function _sfmCondValue2Change(id, val) {
    var cond = sfmState.conditions.find(function(c) { return c.id === id; });
    if (cond) cond.value2 = val;
    sfmState.dirty = true;
    _sfmApplyLive();
}

function _sfmCondToggleArrayVal(id, code) {
    var cond = sfmState.conditions.find(function(c) { return c.id === id; });
    if (!cond) return;
    var selected = (cond.value || '').split(',').filter(Boolean);
    var idx = selected.indexOf(code);
    if (idx === -1) selected.push(code); else selected.splice(idx, 1);
    cond.value = selected.join(',');
    _sfmRenderConditions();
    sfmState.dirty = true;
    _sfmApplyLive();
}

// ==================== SQL TAB HANDLERS ====================

function _sfmInsertCol(colName) {
    var ta = document.getElementById('sfmSqlTextarea');
    if (!ta) return;
    var start = ta.selectionStart;
    var before = ta.value.substring(0, start);
    var after = ta.value.substring(ta.selectionEnd);
    ta.value = before + colName + after;
    ta.selectionStart = ta.selectionEnd = start + colName.length;
    ta.focus();
}

async function _sfmExecuteSql() {
    var ta = document.getElementById('sfmSqlTextarea');
    var status = document.getElementById('sfmSqlStatus');
    var resultsContainer = document.getElementById('sfmSqlResults');
    if (!ta || !ta.value.trim()) return;

    status.textContent = 'Executing...';
    status.className = 'sfm-sql-status';
    if (resultsContainer) resultsContainer.innerHTML = '';

    try {
        var resp = await fetch('/api/v1/intelligence/query', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ sql: ta.value.trim() })
        });
        var data = await resp.json();

        if (!data.success) {
            status.textContent = 'Error: ' + (data.error || 'Unknown error');
            status.className = 'sfm-sql-status error';
            return;
        }

        // Backup current signals
        if (!sfmState.sqlActive) {
            sfmState.sqlBackup = allSignals.slice();
        }
        sfmState.sqlActive = true;
        sfmState.sqlQuery = ta.value.trim();

        // Override allSignals with results
        var rows = data.results || [];
        allSignals = rows;
        status.textContent = data.row_count + ' rows in ' + (data.execution_time_ms || 0) + 'ms';
        status.className = 'sfm-sql-status success';

        // Render results table inside the SQL tab
        _sfmRenderSqlResults(rows, data.columns || []);

        applyFilters();
        _sfmUpdateBadge();
        _sfmUpdateMatchCount();
    } catch (e) {
        status.textContent = 'Network error: ' + e.message;
        status.className = 'sfm-sql-status error';
    }
}

function _sfmRenderSqlResults(rows, columns) {
    var container = document.getElementById('sfmSqlResults');
    if (!container) return;

    if (!rows || rows.length === 0) {
        container.innerHTML = '<div class="sfm-sql-no-results">No results</div>';
        return;
    }

    // Determine columns from data if not provided by backend
    var cols = columns && columns.length > 0 ? columns : Object.keys(rows[0]);

    // Limit display columns for readability — show first 10, user can scroll
    var displayCols = cols;
    var colNote = '';
    if (cols.length > 12) {
        colNote = '<div class="sfm-sql-col-note">Showing all ' + cols.length + ' columns — scroll right to see more</div>';
    }

    var headerHtml = '<tr>' + displayCols.map(function(c) {
        return '<th>' + _sfmEsc(c) + '</th>';
    }).join('') + '</tr>';

    // Limit rows rendered in modal to 200 for performance
    var displayRows = rows.slice(0, 200);
    var bodyHtml = displayRows.map(function(row) {
        return '<tr>' + displayCols.map(function(c) {
            var val = row[c];
            if (val === null || val === undefined) return '<td class="sfm-sql-null">NULL</td>';
            var str = typeof val === 'object' ? JSON.stringify(val) : String(val);
            // Truncate long values
            if (str.length > 120) str = str.substring(0, 117) + '...';
            return '<td>' + _sfmEsc(str) + '</td>';
        }).join('') + '</tr>';
    }).join('');

    var truncNote = rows.length > 200
        ? '<div class="sfm-sql-col-note">Showing 200 of ' + rows.length + ' rows in preview. All ' + rows.length + ' rows loaded in feed.</div>'
        : '';

    container.innerHTML = colNote +
        '<div class="sfm-sql-table-wrap"><table class="sfm-sql-table"><thead>' +
        headerHtml + '</thead><tbody>' + bodyHtml + '</tbody></table></div>' + truncNote;
}

function _sfmClearSql() {
    if (sfmState.sqlBackup) {
        allSignals = sfmState.sqlBackup;
        sfmState.sqlBackup = null;
    }
    sfmState.sqlActive = false;
    sfmState.sqlQuery = '';

    var status = document.getElementById('sfmSqlStatus');
    if (status) { status.textContent = 'SQL override cleared'; status.className = 'sfm-sql-status'; }
    var resultsContainer = document.getElementById('sfmSqlResults');
    if (resultsContainer) resultsContainer.innerHTML = '';

    applyFilters();
    _sfmUpdateBadge();
    _sfmUpdateMatchCount();
}

// ==================== SAVED FILTERS ====================

function _sfmLoadSaved() {
    try {
        return JSON.parse(localStorage.getItem('observer_saved_filters')) || [];
    } catch (e) { return []; }
}

function _sfmStoreSaved(list) {
    try {
        localStorage.setItem('observer_saved_filters', JSON.stringify(list));
    } catch (e) {}
}

function _sfmRenderSaved() {
    var container = document.getElementById('sfmSavedList');
    if (!container) return;
    var saved = _sfmLoadSaved();

    if (saved.length === 0) {
        container.innerHTML = '<div class="sfm-saved-empty">No saved filters. Use "Save Filter" from the Quick Filters or Builder tab.</div>';
        return;
    }

    container.innerHTML = saved.map(function(f, idx) {
        var date = f.date ? new Date(f.date).toLocaleDateString() : '';
        var tabLabel = f.tab === 'quick' ? 'Quick' : f.tab === 'builder' ? 'Builder' : 'SQL';
        return '<div class="sfm-saved-card" onclick="_sfmRecallFilter(' + idx + ')">' +
            '<div class="sfm-saved-info">' +
            '  <div class="sfm-saved-name">' + _sfmEsc(f.name) + '</div>' +
            '  <div class="sfm-saved-meta">' + tabLabel + ' filter &middot; ' + date + '</div>' +
            '</div>' +
            '<div class="sfm-saved-actions">' +
            '  <button class="sfm-saved-action-btn" onclick="event.stopPropagation();_sfmRenameFilter(' + idx + ')" title="Rename">&#9998;</button>' +
            '  <button class="sfm-saved-action-btn delete" onclick="event.stopPropagation();_sfmDeleteFilter(' + idx + ')" title="Delete">&times;</button>' +
            '</div>' +
            '</div>';
    }).join('');
}

function _sfmSavePrompt() {
    // Insert save-name input directly into the current tab's actions row
    // so it's visible regardless of which tab the user is on.
    var activePanel = document.querySelector('.sfm-tab-panel.active');
    var target = activePanel ? activePanel.querySelector('.sfm-actions-row') : null;

    if (!target) {
        // Fallback: use prompt dialog
        var name = prompt('Filter name:');
        if (name) _sfmSaveFilter(name);
        return;
    }

    // Remove any previous save prompt
    var prev = target.querySelector('.sfm-save-prompt');
    if (prev) prev.remove();

    var row = document.createElement('div');
    row.className = 'sfm-save-prompt';
    row.style.marginTop = '8px';
    row.innerHTML =
        '<input type="text" id="sfmSaveNameInput" placeholder="Filter name..." ' +
        'onkeydown="if(event.key===\'Enter\'){_sfmSaveFilter(this.value);this.parentElement.remove()}" ' +
        'onkeyup="if(event.key===\'Escape\'){this.parentElement.remove()}">' +
        '<button class="sfm-btn sfm-btn-primary" onclick="_sfmSaveFilter(document.getElementById(\'sfmSaveNameInput\').value);this.parentElement.remove()">Save</button>';
    target.appendChild(row);

    setTimeout(function() {
        var inp = document.getElementById('sfmSaveNameInput');
        if (inp) inp.focus();
    }, 50);
}

function _sfmSaveFilter(name) {
    if (!name || !name.trim()) return;
    var saved = _sfmLoadSaved();
    var entry = {
        name: name.trim(),
        date: new Date().toISOString(),
        tab: sfmState.activeTab,
        state: JSON.parse(JSON.stringify(sfmState))
    };
    // Don't save sqlBackup (too large)
    delete entry.state.sqlBackup;
    saved.push(entry);
    _sfmStoreSaved(saved);
    _sfmRenderSaved();
}

function _sfmRecallFilter(idx) {
    var saved = _sfmLoadSaved();
    var f = saved[idx];
    if (!f || !f.state) return;

    // Restore quick filter state
    sfmState.timeWindow = f.state.timeWindow || 'all';
    sfmState.searchText = f.state.searchText || '';
    sfmState.regions = f.state.regions || [];
    sfmState.newsRegions = f.state.newsRegions || [];
    sfmState.negateRegions = f.state.negateRegions || false;
    sfmState.scoreTier = f.state.scoreTier || 'all';
    sfmState.translated = f.state.translated || false;
    sfmState.screening = f.state.screening || false;
    sfmState.riskIndicators = f.state.riskIndicators || [];

    // Restore builder state
    sfmState.conditions = f.state.conditions || [];
    sfmState.builderLogic = f.state.builderLogic || 'AND';

    // Restore SQL state
    sfmState.sqlQuery = f.state.sqlQuery || '';

    sfmState.dirty = true;

    // Refresh UI
    _sfmRefreshAllUI();
    _sfmSwitchTab(f.tab || 'quick');
    _sfmApplyLive();
}

function _sfmDeleteFilter(idx) {
    var saved = _sfmLoadSaved();
    saved.splice(idx, 1);
    _sfmStoreSaved(saved);
    _sfmRenderSaved();
}

function _sfmRenameFilter(idx) {
    var saved = _sfmLoadSaved();
    var newName = prompt('New name:', saved[idx].name);
    if (newName && newName.trim()) {
        saved[idx].name = newName.trim();
        _sfmStoreSaved(saved);
        _sfmRenderSaved();
    }
}

function _sfmExportFilters() {
    var saved = _sfmLoadSaved();
    var blob = new Blob([JSON.stringify(saved, null, 2)], { type: 'application/json' });
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url;
    a.download = 'observer_filters_' + new Date().toISOString().slice(0, 10) + '.json';
    a.click();
    URL.revokeObjectURL(url);
}

function _sfmImportFilters() {
    var input = document.createElement('input');
    input.type = 'file';
    input.accept = '.json';
    input.onchange = function(e) {
        var file = e.target.files[0];
        if (!file) return;
        var reader = new FileReader();
        reader.onload = function(ev) {
            try {
                var imported = JSON.parse(ev.target.result);
                if (!Array.isArray(imported)) { alert('Invalid filter file'); return; }
                var saved = _sfmLoadSaved();
                saved = saved.concat(imported);
                _sfmStoreSaved(saved);
                _sfmRenderSaved();
            } catch (err) { alert('Invalid JSON: ' + err.message); }
        };
        reader.readAsText(file);
    };
    input.click();
}

// ==================== REFRESH UI (after recall) ====================

function _sfmRefreshAllUI() {
    // Time window
    var twRow = document.getElementById('sfmTimeWindowRow');
    if (twRow) twRow.querySelectorAll('.sfm-tw-btn').forEach(function(b) {
        b.classList.toggle('active', b.dataset.tw === sfmState.timeWindow);
    });

    // Search input
    var inp = document.getElementById('sfmSearchInput');
    if (inp) inp.value = sfmState.searchText;
    var sbi = document.getElementById('sidebarSearchInput');
    if (sbi) sbi.value = sfmState.searchText;

    // Region chips
    _sfmRefreshRegionChips();
    var neg = document.getElementById('sfmNegateRegions');
    if (neg) neg.checked = sfmState.negateRegions;

    // Tier buttons
    _sfmSetTier(sfmState.scoreTier);

    // Toggles
    var tr = document.getElementById('sfmTranslated');
    if (tr) tr.checked = sfmState.translated;
    var sc = document.getElementById('sfmScreening');
    if (sc) sc.checked = sfmState.screening;

    // Risk grid
    var grid = document.getElementById('sfmRiskGrid');
    if (grid) grid.querySelectorAll('.sfm-risk-chip').forEach(function(c) {
        c.classList.toggle('active', sfmState.riskIndicators.indexOf(c.dataset.risk) !== -1);
    });

    // Builder
    _sfmRenderConditions();

    // SQL
    var ta = document.getElementById('sfmSqlTextarea');
    if (ta && sfmState.sqlQuery) ta.value = sfmState.sqlQuery;
}

// ==================== CORE FILTER PIPELINE ====================

/**
 * Build server-side query params from the current sfmState.
 * These are sent to GET /api/v1/intelligence for DB-level filtering.
 */
function _sfmBuildServerParams() {
    var params = {};

    // Time window
    params.time_window = sfmState.timeWindow || 'all';

    // NOTE: search text is NOT sent to server — it runs client-side on
    // the filtered view so users can search WITHIN their active filters
    // (e.g. search "cartel" within a SOCSOUTH AOR filter).

    // AOR Region → expand to source_group list
    if (sfmState.regions.length > 0 && !sfmState.negateRegions) {
        var groups = [];
        sfmState.regions.forEach(function(key) {
            var r = SOC_REGIONS[key];
            if (r) r.groups.forEach(function(g) {
                if (groups.indexOf(g) === -1) groups.push(g);
            });
        });
        if (groups.length > 0) params.source_groups = groups.join(',');
    }

    // AOR News → expand to country name list for content search
    if (sfmState.newsRegions.length > 0) {
        var countries = [];
        sfmState.newsRegions.forEach(function(key) {
            var r = SOC_REGIONS[key];
            if (r && r.countries) r.countries.forEach(function(c) {
                if (countries.indexOf(c) === -1) countries.push(c);
            });
        });
        if (countries.length > 0) params.content_search = countries.join(',');
    }

    // Score tier
    if (sfmState.scoreTier !== 'all') {
        params.min_score = parseInt(sfmState.scoreTier, 10);
    }

    // Risk indicators
    if (sfmState.riskIndicators.length > 0) {
        params.risk_indicators = sfmState.riskIndicators.join(',');
    }

    // Toggles
    if (sfmState.translated) params.translated_only = true;
    if (sfmState.screening) params.screening_only = true;

    return params;
}

/**
 * Apply search text client-side only — no server fetch.
 * Search refines the already-loaded filtered view (e.g. AOR results).
 */
function _sfmApplySearchOnly() {
    searchQuery = sfmState.searchText;
    var inp = document.getElementById('searchInput');
    if (inp) inp.value = sfmState.searchText;
    sfmSearchTokens = _sfmParseSearchTokens(sfmState.searchText);
    if (typeof resetCardLimit === 'function') resetCardLimit();
    if (typeof applyFilters === 'function') applyFilters();
    _sfmUpdateBadge();
    if (typeof _sfmUpdateMatchCount === 'function') _sfmUpdateMatchCount();
}

function _sfmApplyLive() {
    // Write search to shared state for applyFilters compatibility
    searchQuery = sfmState.searchText;
    var inp = document.getElementById('searchInput');
    if (inp) inp.value = sfmState.searchText;

    // Parse search tokens for Google-like matching (client-side refinement)
    sfmSearchTokens = _sfmParseSearchTokens(sfmState.searchText);

    // Reset display limit so user sees results from the top
    if (typeof resetCardLimit === 'function') resetCardLimit();

    // Sync time window to shared state
    currentTimeWindow = sfmState.timeWindow;

    // Immediate client-side filter for visual feedback against loaded articles
    if (typeof applyFilters === 'function') applyFilters();

    // Debounce the server fetch (400ms) so rapid clicks don't hammer the API.
    // Server fetch searches the ENTIRE database and replaces allSignals with
    // the full result set (up to 5000), not just the previously-loaded subset.
    if (_sfmFetchTimer) clearTimeout(_sfmFetchTimer);
    _sfmFetchTimer = setTimeout(function() {
        if (typeof fetchIntelligence === 'function') {
            fetchIntelligence();
        }
    }, 400);

    _sfmUpdateBadge();

    // Notify the analyst console that filters changed so it can re-poll
    // with the new filter params. Uses a custom DOM event to decouple
    // the modal from the console_analyst module.
    document.dispatchEvent(new CustomEvent('sfm-filters-changed'));
}

/**
 * Parse Google-like search syntax into structured tokens.
 *
 * Supported syntax:
 *   word          → required term (AND with other terms)
 *   "exact phrase" → required exact phrase
 *   -word         → excluded term
 *   -"phrase"     → excluded phrase
 *
 * Returns { required: string[], excluded: string[] } with all terms lowercased.
 * Returns null if the search text is empty.
 */
function _sfmParseSearchTokens(text) {
    if (!text || !text.trim()) return null;

    var required = [];
    var excluded = [];

    // Match: -"phrase", "phrase", -word, word
    var regex = /(-?"[^"]*"|-\S+|\S+)/g;
    var match;
    while ((match = regex.exec(text)) !== null) {
        var token = match[1];
        var negate = false;

        if (token.charAt(0) === '-') {
            negate = true;
            token = token.substring(1);
        }

        // Strip quotes from phrases
        if (token.charAt(0) === '"' && token.charAt(token.length - 1) === '"') {
            token = token.substring(1, token.length - 1);
        }

        token = token.toLowerCase().trim();
        if (!token) continue;

        if (negate) {
            excluded.push(token);
        } else {
            required.push(token);
        }
    }

    if (required.length === 0 && excluded.length === 0) return null;
    return { required: required, excluded: excluded };
}

/**
 * Test whether a signal matches the parsed search tokens.
 * Searches across title, description, location, source, author.
 * All required terms must match. No excluded terms may match.
 */
function _sfmMatchesSearchTokens(signal, tokens) {
    if (!tokens) return true;

    // Build a single searchable string from all text fields + extracted entities
    var entityText = '';
    if (signal.entities_json && Array.isArray(signal.entities_json)) {
        entityText = signal.entities_json.map(function(e) { return e.text || ''; }).join(' ');
    }
    var haystack = [
        signal.title || '',
        signal.description || '',
        signal.location || '',
        signal.source || '',
        signal.author || '',
        entityText
    ].join(' ').toLowerCase();

    // All required terms must be present
    for (var i = 0; i < tokens.required.length; i++) {
        if (haystack.indexOf(tokens.required[i]) === -1) return false;
    }

    // No excluded terms may be present
    for (var j = 0; j < tokens.excluded.length; j++) {
        if (haystack.indexOf(tokens.excluded[j]) !== -1) return false;
    }

    return true;
}

function _sfmApplyAndClose() {
    // Flush any pending debounce and apply immediately
    if (_sfmFetchTimer) clearTimeout(_sfmFetchTimer);
    searchQuery = sfmState.searchText;
    sfmSearchTokens = _sfmParseSearchTokens(sfmState.searchText);
    currentTimeWindow = sfmState.timeWindow;
    if (typeof resetCardLimit === 'function') resetCardLimit();
    if (typeof fetchIntelligence === 'function') fetchIntelligence();
    _sfmUpdateBadge();
    closeSearchFilterModal();
}

/**
 * Build a filter predicate from the current sfmState.
 * Called by the patched applyFilters().
 */
function sfmBuildPredicate() {
    return function(signal) {
        // Compound AOR filter: Region (source_group) + News (content)
        // When both are active, they are OR'd (stacked).
        // When only one is active, it filters independently.
        var hasRegion = sfmState.regions.length > 0;
        var hasNews = sfmState.newsRegions.length > 0;

        if (hasRegion || hasNews) {
            var passesRegion = false;
            var passesNews = false;

            // Region: check source_group membership
            if (hasRegion) {
                var groupSet = {};
                sfmState.regions.forEach(function(key) {
                    var r = SOC_REGIONS[key];
                    if (r) r.groups.forEach(function(g) { groupSet[g] = 1; });
                });
                var inRegion = groupSet[signal.source_group] === 1;
                if (sfmState.negateRegions) {
                    passesRegion = !inRegion;
                } else {
                    passesRegion = inRegion;
                }
            }

            // News: check article content for country names
            if (hasNews) {
                var entText = '';
                if (signal.entities_json && Array.isArray(signal.entities_json)) {
                    entText = signal.entities_json.map(function(e) { return e.text || ''; }).join(' ');
                }
                var haystack = [
                    signal.title || '',
                    signal.description || '',
                    signal.location || '',
                    entText
                ].join(' ').toLowerCase();
                sfmState.newsRegions.forEach(function(key) {
                    if (passesNews) return; // already matched
                    var r = SOC_REGIONS[key];
                    if (r && r.countries) {
                        for (var i = 0; i < r.countries.length; i++) {
                            if (haystack.indexOf(r.countries[i].toLowerCase()) !== -1) {
                                passesNews = true;
                                break;
                            }
                        }
                    }
                });
            }

            // Stacked: OR when both active; single filter when only one active
            if (hasRegion && hasNews) {
                if (!passesRegion && !passesNews) return false;
            } else if (hasRegion) {
                if (!passesRegion) return false;
            } else if (hasNews) {
                if (!passesNews) return false;
            }
        }

        // Quick filter: score tier
        if (sfmState.scoreTier !== 'all') {
            var minScore = parseInt(sfmState.scoreTier, 10);
            if ((signal.relevance_score || 0) < minScore) return false;
        }

        // Quick filter: translated
        if (sfmState.translated && !signal.is_translated) return false;

        // Quick filter: screening hits
        if (sfmState.screening) {
            if (!signal.screening_hits || !signal.screening_hits.hit_count) return false;
        }

        // Quick filter: risk indicators
        if (sfmState.riskIndicators.length > 0) {
            var sigRisks = signal.risk_indicators || [];
            var hasAny = sfmState.riskIndicators.some(function(r) { return sigRisks.indexOf(r) !== -1; });
            if (!hasAny) return false;
        }

        // Builder conditions with per-row AND/OR and standard precedence
        // AND binds tighter than OR: "A AND B OR C AND D" = "(A AND B) OR (C AND D)"
        if (sfmState.conditions.length > 0) {
            if (!_sfmEvalConditionsWithPrecedence(signal, sfmState.conditions)) return false;
        }

        return true;
    };
}

/**
 * Evaluate conditions with standard AND/OR precedence.
 * AND binds tighter than OR, so we group consecutive AND conditions
 * into clusters, evaluate each cluster, then OR the cluster results.
 *
 * Example: A AND B OR C AND D → (A AND B) OR (C AND D)
 */
function _sfmEvalConditionsWithPrecedence(signal, conditions) {
    // Split conditions into OR-separated groups of AND-connected conditions
    var groups = [[]];
    conditions.forEach(function(cond, idx) {
        if (idx > 0 && cond.connector === 'OR') {
            groups.push([]);
        }
        groups[groups.length - 1].push(cond);
    });

    // A group passes if ALL its conditions pass (AND within group)
    // The overall result passes if ANY group passes (OR between groups)
    return groups.some(function(group) {
        return group.every(function(cond) {
            return _sfmEvalCondition(signal, cond);
        });
    });
}

function _sfmEvalCondition(signal, cond) {
    var fieldDef = SFM_FIELDS[cond.field];
    if (!fieldDef) return true;
    var val = signal[cond.field];

    if (fieldDef.type === 'boolean') {
        return cond.op === 'is true' ? !!val : !val;
    }

    if (fieldDef.type === 'text') {
        var sv = (val || '').toLowerCase();
        var cv = (cond.value || '').toLowerCase();
        if (!cv) return true;  // empty value = no filter
        switch (cond.op) {
            case 'contains': return sv.indexOf(cv) !== -1;
            case 'equals': return sv === cv;
            case 'starts with': return sv.indexOf(cv) === 0;
            case 'not contains': return sv.indexOf(cv) === -1;
            case 'regex':
                try { return new RegExp(cond.value, 'i').test(val || ''); }
                catch (e) { return true; }
            default: return true;
        }
    }

    if (fieldDef.type === 'number') {
        var nv = parseFloat(val) || 0;
        var nc = parseFloat(cond.value) || 0;
        switch (cond.op) {
            case '=': return nv === nc;
            case '>': return nv > nc;
            case '<': return nv < nc;
            case '>=': return nv >= nc;
            case '<=': return nv <= nc;
            case 'between': return nv >= nc && nv <= (parseFloat(cond.value2) || 0);
            default: return true;
        }
    }

    if (fieldDef.type === 'array') {
        var sigArr = val || [];
        var filterArr = (cond.value || '').split(',').filter(Boolean);
        if (filterArr.length === 0) return true;
        switch (cond.op) {
            case 'includes any': return filterArr.some(function(f) { return sigArr.indexOf(f) !== -1; });
            case 'includes all': return filterArr.every(function(f) { return sigArr.indexOf(f) !== -1; });
            case 'excludes': return !filterArr.some(function(f) { return sigArr.indexOf(f) !== -1; });
            default: return true;
        }
    }

    if (fieldDef.type === 'timestamp') {
        var ts = _sfmParseTimestamp(val);
        if (!ts) return true;
        if (cond.op === 'last N hours') {
            var hours = parseFloat(cond.value) || 0;
            return (Date.now() - ts.getTime()) <= hours * 3600000;
        }
        var cv1 = cond.value ? new Date(cond.value) : null;
        var cv2 = cond.value2 ? new Date(cond.value2) : null;
        switch (cond.op) {
            case 'after': return cv1 ? ts > cv1 : true;
            case 'before': return cv1 ? ts < cv1 : true;
            case 'between': return cv1 && cv2 ? ts >= cv1 && ts <= cv2 : true;
            default: return true;
        }
    }

    return true;
}

function _sfmParseTimestamp(val) {
    if (!val) return null;
    try {
        var s = typeof val === 'string' ? val.replace(' ', 'T') : val;
        if (typeof s === 'string' && !s.endsWith('Z') && !s.includes('+')) s += 'Z';
        var d = new Date(s);
        return isNaN(d.getTime()) ? null : d;
    } catch (e) { return null; }
}

// ==================== LIVE MATCH COUNT ====================

function _sfmCountMatches(cond) {
    var count = 0;
    for (var i = 0; i < allSignals.length; i++) {
        if (_sfmEvalCondition(allSignals[i], cond)) count++;
    }
    return count;
}

function _sfmUpdateMatchCount() {
    var el = document.getElementById('sfmMatchCount');
    if (!el) return;
    var total = (typeof totalDbCount !== 'undefined' && totalDbCount) ? totalDbCount : allSignals.length;
    if (total > allSignals.length) {
        el.innerHTML = '<strong>' + filteredSignals.length + '</strong> / ' + total.toLocaleString() + ' in DB';
    } else {
        el.innerHTML = '<strong>' + filteredSignals.length + '</strong> / ' + allSignals.length + ' signals';
    }
}

// ==================== FILTER BADGE IN FEED HEADER ====================

function _sfmIsActive() {
    if (sfmState.sqlActive) return true;
    if (sfmState.timeWindow !== 'all') return true;
    if (sfmState.searchText) return true;
    if (sfmState.regions.length > 0) return true;
    if (sfmState.newsRegions.length > 0) return true;
    if (sfmState.scoreTier !== 'all') return true;
    if (sfmState.translated) return true;
    if (sfmState.screening) return true;
    if (sfmState.riskIndicators.length > 0) return true;
    if (sfmState.conditions.length > 0 && sfmState.conditions.some(function(c) { return c.value; })) return true;
    return false;
}

function _sfmRegionLabel(key) {
    // Convert SOC region key to human-readable label
    var r = SOC_REGIONS[key];
    return r ? r.label : key;
}

function _sfmBuildBadgeText() {
    // Build only the filter summary for the teal badge (NO search text here).
    var parts = [];
    if (sfmState.sqlActive) return 'SQL query active';
    if (sfmState.timeWindow !== 'all') parts.push(sfmState.timeWindow);
    if (sfmState.regions.length > 0) {
        var prefix = sfmState.negateRegions ? 'NOT ' : '';
        var labels = sfmState.regions.map(_sfmRegionLabel);
        if (labels.length <= 2) {
            parts.push(prefix + labels.join(' + '));
        } else {
            parts.push(prefix + labels[0] + ' +' + (labels.length - 1) + ' more');
        }
    }
    if (sfmState.newsRegions.length > 0) {
        var newsLabels = sfmState.newsRegions.map(_sfmRegionLabel);
        var newsLabel = newsLabels.length <= 2
            ? newsLabels.join(' + ') + ' News'
            : newsLabels[0] + ' +' + (newsLabels.length - 1) + ' News';
        parts.push(newsLabel);
    }
    if (sfmState.scoreTier !== 'all') parts.push('score \u2265 ' + sfmState.scoreTier);
    if (sfmState.translated) parts.push('translated');
    if (sfmState.screening) parts.push('screening hits');
    if (sfmState.riskIndicators.length > 0) parts.push('risk: ' + sfmState.riskIndicators.join(','));
    if (sfmState.conditions.length > 0) {
        var active = sfmState.conditions.filter(function(c) { return c.value; }).length;
        if (active > 0) {
            var hasOr = sfmState.conditions.some(function(c) { return c.connector === 'OR'; });
            var hasAnd = sfmState.conditions.some(function(c) { return c.connector === 'AND'; });
            var logicLabel = hasOr && hasAnd ? 'AND+OR' : hasOr ? 'OR' : 'AND';
            parts.push(active + ' condition' + (active > 1 ? 's' : '') + ' (' + logicLabel + ')');
        }
    }
    return parts.join(' \u00B7 ') || '';
}

function _sfmUpdateBadge() {
    var badge = document.getElementById('sfmFilterBadge');
    if (!badge) return;

    // Remove any previous search text label (lives outside the badge)
    var oldLabel = document.getElementById('sfmSearchTextLabel');
    if (oldLabel) oldLabel.remove();

    var active = _sfmIsActive();
    var badgeText = _sfmBuildBadgeText();
    var hasFilterBadge = active && badgeText;

    // Teal badge: only filter criteria (regions, score, time, etc.)
    badge.classList.toggle('visible', hasFilterBadge);
    if (hasFilterBadge) {
        badge.innerHTML = '\u26A1 ' + _sfmEsc(badgeText) +
            ' <span class="badge-clear" onclick="event.stopPropagation();_sfmClearAll()">\u2715</span>';
    } else {
        badge.innerHTML = '';
    }

    // Search text: plain grey text OUTSIDE the teal badge
    if (sfmState.searchText) {
        var label = document.createElement('span');
        label.id = 'sfmSearchTextLabel';
        label.className = 'sfm-search-label';
        var truncated = sfmState.searchText.length > 30
            ? sfmState.searchText.substring(0, 27) + '...'
            : sfmState.searchText;
        label.textContent = '"' + truncated + '"';
        label.onclick = function() { openSearchFilterModal(); };
        // Insert right after the badge in the feed-title-row
        badge.parentNode.insertBefore(label, badge.nextSibling);
    }
}

function _sfmClearAll() {
    // Cancel any pending fetch debounce
    if (_sfmFetchTimer) clearTimeout(_sfmFetchTimer);

    // -- Reset Quick filter state --
    sfmState.searchText = '';
    sfmState.timeWindow = 'all';
    sfmState.regions = [];
    sfmState.newsRegions = [];
    sfmState.negateRegions = false;
    sfmState.scoreTier = 'all';
    sfmState.translated = false;
    sfmState.screening = false;
    sfmState.riskIndicators = [];

    var inp = document.getElementById('sfmSearchInput');
    if (inp) inp.value = '';
    var sbi = document.getElementById('sidebarSearchInput');
    if (sbi) sbi.value = '';
    var neg = document.getElementById('sfmNegateRegions');
    if (neg) neg.checked = false;
    var tr = document.getElementById('sfmTranslated');
    if (tr) tr.checked = false;
    var sc = document.getElementById('sfmScreening');
    if (sc) sc.checked = false;
    _sfmRefreshRegionChips();
    var tierRow = document.getElementById('sfmTierRow');
    if (tierRow) tierRow.querySelectorAll('.sfm-tier-btn').forEach(function(b) {
        b.classList.toggle('active', b.dataset.tier === 'all');
    });
    var twRow = document.getElementById('sfmTimeWindowRow');
    if (twRow) twRow.querySelectorAll('.sfm-tw-btn').forEach(function(b) {
        b.classList.toggle('active', b.dataset.tw === 'all');
    });
    var grid = document.getElementById('sfmRiskGrid');
    if (grid) grid.querySelectorAll('.sfm-risk-chip').forEach(function(c) { c.classList.remove('active'); });

    // -- Reset Builder state --
    sfmState.conditions = [];
    sfmState.builderLogic = 'AND';
    _sfmRenderConditions();

    // -- Reset SQL state --
    if (sfmState.sqlBackup) {
        // Don't restore backup — we'll fetch fresh data below
        sfmState.sqlBackup = null;
    }
    sfmState.sqlActive = false;
    sfmState.sqlQuery = '';
    var status = document.getElementById('sfmSqlStatus');
    if (status) { status.textContent = ''; status.className = 'sfm-sql-status'; }
    var resultsContainer = document.getElementById('sfmSqlResults');
    if (resultsContainer) resultsContainer.innerHTML = '';

    // -- Sync shared state and fetch once --
    sfmState.dirty = false;
    searchQuery = '';
    sfmSearchTokens = null;
    currentTimeWindow = 'all';
    document.querySelectorAll('.time-btn').forEach(function(b) {
        b.classList.toggle('active', b.dataset.window === 'all');
    });
    var hiddenInp = document.getElementById('searchInput');
    if (hiddenInp) hiddenInp.value = '';

    if (typeof resetCardLimit === 'function') resetCardLimit();
    if (typeof fetchIntelligence === 'function') fetchIntelligence();
    _sfmUpdateBadge();

    // Notify analyst console that filters were cleared
    document.dispatchEvent(new CustomEvent('sfm-filters-changed'));
}

function _sfmClearBuilder() {
    sfmState.conditions = [];
    sfmState.builderLogic = 'AND';
    _sfmRenderConditions();
    _sfmApplyLive();
}

// ==================== UTILITY ====================

function _sfmEsc(text) {
    if (!text) return '';
    return String(text).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
