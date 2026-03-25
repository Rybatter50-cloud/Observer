/**
 * Observer Dashboard - Compact Table Module
 * Data-driven compact table with column reorder, resize, and hide/show.
 */

// ==================== COLUMN DEFINITIONS ====================
// Default column order. Each column: { id, label, sortKey (optional), cssClass, render, defaultWidth, defaultVisible }
const COMPACT_COLUMNS = [
    {
        id: 'age',
        label: 'Age',
        sortKey: 'age',
        cssClass: 'compact-age',
        defaultWidth: '60px',
        defaultVisible: true,
        render: (signal) => {
            const age = getSignalAge(signal);
            return `<div class="age-dot-small ${age.class}" title="${escapeHtml(age.text)}"></div><div class="compact-time">${formatCardTime(signal)}</div>`;
        },
        sortFn: (a, b) => {
            const aVal = getSignalTimestamp(a)?.getTime() || 0;
            const bVal = getSignalTimestamp(b)?.getTime() || 0;
            return { aVal, bVal };
        }
    },
    {
        id: 'title',
        label: 'Title',
        cssClass: 'compact-title',
        defaultVisible: true,
        render: (signal) =>
            `<span class="compact-title-link" onclick="event.stopPropagation(); openArticleDetailModal(${signal.id})">${escapeHtml(signal.title || 'Untitled')}</span>`
    },
    {
        id: 'indicators',
        label: 'Indicators',
        cssClass: 'compact-indicators',
        defaultWidth: '100px',
        defaultVisible: true,
        render: (signal) => {
            // Screening dot (red = exact 100% match, amber = partial)
            let screeningDot = '';
            const hits = signal.screening_hits;
            if (hits && hits.hit_count) {
                const maxScore = Math.round(hits.max_score || 0);
                const cls = maxScore >= 100 ? 'exact' : 'partial';
                const title = `${hits.hit_count} screening hit${hits.hit_count !== 1 ? 's' : ''} (max: ${maxScore}%)`;
                screeningDot = `<span class="compact-screening-dot ${cls}" title="${title}" onclick="event.stopPropagation(); openScreeningModal(${signal.id})"></span>`;
            }
            const transFlag = signal.is_translated
                ? `<span class="compact-translated" title="Translated from ${escapeHtml(signal.source_language || '?')}">${escapeHtml((signal.source_language || '??').toUpperCase())}</span>`
                : '';
            const indicators = (signal.risk_indicators || []).map(c =>
                `<span class="compact-indicator" title="${escapeHtml(window.INDICATOR_LABELS && window.INDICATOR_LABELS[c] || c)}">${escapeHtml(c)}</span>`
            ).join('');
            return screeningDot + transFlag + `<span class="ie-clickable" onclick="event.stopPropagation(); openIndicatorEditModal(${signal.id})" title="Click to edit indicators">${indicators || '<span class="ie-add-hint">+</span>'}</span>`;
        }
    },
    {
        id: 'entities',
        label: 'Entities',
        cssClass: 'compact-entities',
        defaultWidth: '200px',
        defaultVisible: true,
        render: (signal) => {
            const entities = signal.entities_json;
            if (!entities || !Array.isArray(entities) || entities.length === 0) return '';

            const typeColors = {
                'PERSON': 'entity-person', 'ORG': 'entity-org', 'GPE': 'entity-gpe',
                'COUNTRY': 'entity-country', 'MILITARY': 'entity-military',
                'WEAPON': 'entity-weapon', 'EVENT': 'entity-event',
            };

            const pills = entities.slice(0, 5).map(ent => {
                const cls = typeColors[ent.type] || 'entity-other';
                const hasScreening = ent.screening_result && ent.screening_result.hit_count;
                const warn = hasScreening ? '<span class="entity-warn">!</span>' : '';
                return `<span class="entity-pill ${cls}" title="${escapeHtml(ent.type)}: ${escapeHtml(ent.text)}">${warn}${escapeHtml(ent.text)}</span>`;
            }).join('');

            const more = entities.length > 5 ? `<span class="entity-pill entity-more">+${entities.length - 5}</span>` : '';
            return `<div class="entity-pills">${pills}${more}</div>`;
        }
    },
    {
        id: 'score',
        label: 'Score',
        sortKey: 'score',
        cssClass: 'compact-score',
        defaultWidth: '36px',
        defaultVisible: true,
        render: (signal) => {
            const s = signal.relevance_score || 0;
            const cls = s >= 85 ? 'score-critical' : s >= 65 ? 'score-high' : s >= 40 ? 'score-medium' : 'score-low';
            const manual = signal.analysis_mode === 'MANUAL' ? ' ie-manual' : '';
            return `<span class="score-badge ${cls}${manual} ie-clickable" onclick="event.stopPropagation(); openScoreEditModal(${signal.id})" title="Click to edit score">${s}</span>`;
        },
        sortFn: (a, b) => ({ aVal: a.relevance_score || 0, bVal: b.relevance_score || 0 })
    },
    {
        id: 'location',
        label: 'Location',
        cssClass: 'compact-location',
        defaultWidth: '120px',
        defaultVisible: true,
        render: (signal) => escapeHtml(signal.location || 'Unknown')
    },
    {
        id: 'author',
        label: 'Author',
        sortKey: 'author',
        cssClass: 'compact-author',
        defaultWidth: '100px',
        defaultVisible: false,
        render: (signal) => escapeHtml(signal.author || ''),
        sortFn: (a, b) => {
            const aVal = (a.author || '').toLowerCase();
            const bVal = (b.author || '').toLowerCase();
            return { aVal, bVal, text: true };
        }
    },
    {
        id: 'group',
        label: 'Group',
        sortKey: 'group',
        cssClass: 'compact-group',
        defaultWidth: '90px',
        defaultVisible: false,
        render: (signal) => escapeHtml(signal.source_group || ''),
        sortFn: (a, b) => {
            const aVal = (a.source_group || '').toLowerCase();
            const bVal = (b.source_group || '').toLowerCase();
            return { aVal, bVal, text: true };
        }
    },
    {
        id: 'source',
        label: 'Source',
        sortKey: 'source',
        cssClass: 'compact-source',
        defaultWidth: '110px',
        defaultVisible: true,
        render: (signal) => escapeHtml(signal.source || 'RSS'),
        sortFn: (a, b) => {
            const aVal = (a.source || '').toLowerCase();
            const bVal = (b.source || '').toLowerCase();
            return { aVal, bVal, text: true };
        }
    },
];

// ==================== COLUMN STATE ====================
let _colOrder = [];    // ordered column ids
let _colVisible = {};  // { id: bool }
const _COL_STORAGE_KEY = 'observer_col_config';

function _getVisibleColumns() {
    return _colOrder.filter(id => _colVisible[id]).map(id => COMPACT_COLUMNS.find(c => c.id === id)).filter(Boolean);
}

function _loadColumnConfig() {
    // Defaults
    _colOrder = COMPACT_COLUMNS.map(c => c.id);
    _colVisible = {};
    COMPACT_COLUMNS.forEach(c => { _colVisible[c.id] = c.defaultVisible; });

    try {
        const saved = JSON.parse(localStorage.getItem(_COL_STORAGE_KEY));
        if (saved && saved.order && saved.visible) {
            // Validate saved order contains known ids
            const knownIds = new Set(COMPACT_COLUMNS.map(c => c.id));
            const validOrder = saved.order.filter(id => knownIds.has(id));
            // Append any new columns not in saved config
            COMPACT_COLUMNS.forEach(c => {
                if (!validOrder.includes(c.id)) validOrder.push(c.id);
            });
            _colOrder = validOrder;
            // Merge visibility, defaulting new columns
            COMPACT_COLUMNS.forEach(c => {
                _colVisible[c.id] = c.id in saved.visible ? saved.visible[c.id] : c.defaultVisible;
            });
            // Restore widths
            if (saved.widths) {
                _savedWidths = saved.widths;
            }
        }
    } catch(e) {}
}

let _savedWidths = {};

function _saveColumnConfig() {
    // Capture current widths from DOM
    const table = document.getElementById('compactTable');
    if (table) {
        table.querySelectorAll('thead th[data-col]').forEach(th => {
            if (th.style.width) _savedWidths[th.dataset.col] = th.style.width;
        });
    }
    try {
        localStorage.setItem(_COL_STORAGE_KEY, JSON.stringify({
            order: _colOrder,
            visible: _colVisible,
            widths: _savedWidths,
        }));
    } catch(e) {}
}

// ==================== HEADER RENDERING ====================
function _renderTableHeader() {
    const table = document.getElementById('compactTable');
    if (!table) return;

    const thead = table.querySelector('thead');
    const cols = _getVisibleColumns();

    thead.innerHTML = `<tr>${cols.map(col => {
        const sortAttr = col.sortKey ? ` data-sort="${col.sortKey}"` : '';
        const sortIcon = col.sortKey ? ` <span class="sort-icon">${col.sortKey === compactSortField ? (compactSortDir === 'desc' ? '▼' : '▲') : ''}</span>` : '';
        const w = _savedWidths[col.id] || col.defaultWidth || '';
        const style = w ? ` style="width:${w}"` : '';
        return `<th data-col="${col.id}"${sortAttr}${style} draggable="true">${col.label}${sortIcon}</th>`;
    }).join('')}</tr>`;

    // Attach sort, resize, and drag listeners
    _initHeaderInteractions();
}

function _initHeaderInteractions() {
    const table = document.getElementById('compactTable');
    if (!table) return;

    table.querySelectorAll('thead th[data-col]').forEach(th => {
        // Sort click
        if (th.dataset.sort) {
            th.addEventListener('click', (e) => {
                if (e.target.classList.contains('col-resize-handle')) return;
                const field = th.dataset.sort;
                if (compactSortField === field) {
                    compactSortDir = compactSortDir === 'desc' ? 'asc' : 'desc';
                } else {
                    compactSortField = field;
                    compactSortDir = 'desc';
                }
                updateCompactTableHeaders();
                render();
            });
        }

        // Right-click for column visibility menu
        th.addEventListener('contextmenu', (e) => {
            e.preventDefault();
            _showColumnMenu(e.pageX, e.pageY);
        });

        // Resize handle — drag adjusts this column and its right neighbour inversely
        if (!th.querySelector('.col-resize-handle')) {
            const handle = document.createElement('div');
            handle.className = 'col-resize-handle';
            th.appendChild(handle);
            let startX, startWidth, nextTh, nextStartWidth;
            handle.addEventListener('mousedown', (e) => {
                e.preventDefault();
                e.stopPropagation();
                startX = e.pageX;
                startWidth = th.offsetWidth;
                nextTh = th.nextElementSibling;
                nextStartWidth = nextTh ? nextTh.offsetWidth : 0;
                handle.classList.add('active');
                table.classList.add('resizing');
                function onMove(e) {
                    const dx = e.pageX - startX;
                    const newWidth = Math.max(30, startWidth + dx);
                    th.style.width = newWidth + 'px';
                    // Adjust neighbour inversely so total width stays constant
                    if (nextTh) {
                        const newNextWidth = Math.max(30, nextStartWidth - dx);
                        nextTh.style.width = newNextWidth + 'px';
                    }
                }
                function onUp() {
                    handle.classList.remove('active');
                    table.classList.remove('resizing');
                    document.removeEventListener('mousemove', onMove);
                    document.removeEventListener('mouseup', onUp);
                    _saveColumnConfig();
                }
                document.addEventListener('mousemove', onMove);
                document.addEventListener('mouseup', onUp);
            });
        }

        // Drag-and-drop reorder
        th.addEventListener('dragstart', (e) => {
            e.dataTransfer.effectAllowed = 'move';
            e.dataTransfer.setData('text/plain', th.dataset.col);
            th.classList.add('dragging');
        });
        th.addEventListener('dragend', () => {
            th.classList.remove('dragging');
            table.querySelectorAll('thead th').forEach(h => h.classList.remove('drag-over'));
        });
        th.addEventListener('dragover', (e) => {
            e.preventDefault();
            e.dataTransfer.dropEffect = 'move';
            th.classList.add('drag-over');
        });
        th.addEventListener('dragleave', () => {
            th.classList.remove('drag-over');
        });
        th.addEventListener('drop', (e) => {
            e.preventDefault();
            th.classList.remove('drag-over');
            const fromId = e.dataTransfer.getData('text/plain');
            const toId = th.dataset.col;
            if (fromId && toId && fromId !== toId) {
                const fromIdx = _colOrder.indexOf(fromId);
                const toIdx = _colOrder.indexOf(toId);
                if (fromIdx > -1 && toIdx > -1) {
                    _colOrder.splice(fromIdx, 1);
                    _colOrder.splice(toIdx, 0, fromId);
                    _saveColumnConfig();
                    _renderTableHeader();
                    render();
                }
            }
        });
    });
}

// ==================== COLUMN VISIBILITY MENU ====================
function _showColumnMenu(x, y) {
    // Remove existing menu
    _hideColumnMenu();

    const menu = document.createElement('div');
    menu.id = 'colVisibilityMenu';
    menu.className = 'col-menu';
    menu.innerHTML = '<div class="col-menu-title">Columns</div>' +
        _colOrder.map(id => {
            const col = COMPACT_COLUMNS.find(c => c.id === id);
            if (!col) return '';
            const checked = _colVisible[id] ? 'checked' : '';
            return `<label class="col-menu-item"><input type="checkbox" ${checked} data-col-id="${id}"> ${col.label}</label>`;
        }).join('') +
        '<div class="col-menu-hint">Drag headers to reorder</div>';

    // Position
    menu.style.left = Math.min(x, window.innerWidth - 180) + 'px';
    menu.style.top = Math.min(y, window.innerHeight - 300) + 'px';

    document.body.appendChild(menu);

    // Stop clicks inside menu from bubbling to document's outside-click handler.
    // Without this, clicking a label removes the menu from DOM before the
    // label's default action toggles the checkbox, so 'change' never fires.
    menu.addEventListener('click', (e) => e.stopPropagation());

    // Checkbox handlers
    menu.querySelectorAll('input[data-col-id]').forEach(cb => {
        cb.addEventListener('change', () => {
            const colId = cb.dataset.colId;
            // Prevent hiding all columns
            const visibleCount = Object.values(_colVisible).filter(Boolean).length;
            if (!cb.checked && visibleCount <= 2) {
                cb.checked = true;
                return;
            }
            _colVisible[colId] = cb.checked;
            _saveColumnConfig();
            _renderTableHeader();
            render();
        });
    });

    // Close on outside click (deferred so this click doesn't immediately close).
    // Clicks inside the menu are stopped above, so only true outside clicks close it.
    setTimeout(() => {
        document.addEventListener('click', _hideColumnMenu, { once: true });
    }, 0);
}

function _hideColumnMenu() {
    const existing = document.getElementById('colVisibilityMenu');
    if (existing) existing.remove();
}

// ==================== COMPACT TABLE RENDERING ====================
function renderCompact(signals) {
    const cols = _getVisibleColumns();

    // Sort
    let sortedSignals = [...signals];
    const sortCol = cols.find(c => c.sortKey === compactSortField) || COMPACT_COLUMNS.find(c => c.sortKey === compactSortField);
    if (sortCol && sortCol.sortFn) {
        sortedSignals.sort((a, b) => {
            const { aVal, bVal, text } = sortCol.sortFn(a, b);
            if (text) {
                return compactSortDir === 'desc' ? bVal.localeCompare(aVal) : aVal.localeCompare(bVal);
            }
            return compactSortDir === 'desc' ? bVal - aVal : aVal - bVal;
        });
    }

    const tbody = document.getElementById('compactBody');
    const colCount = cols.length;

    if (sortedSignals.length === 0) {
        tbody.innerHTML = `<tr><td colspan="${colCount}" style="text-align:center;color:var(--text-muted);padding:40px;">No signals match current filters</td></tr>`;
        return;
    }

    const COMPACT_VIEW_PAGE = 250;
    if (!window._compactDisplayLimit) window._compactDisplayLimit = COMPACT_VIEW_PAGE;
    const displaySignals = sortedSignals.slice(0, window._compactDisplayLimit);

    tbody.innerHTML = displaySignals.map(signal => {
        const isPinned = pinnedIds.has(signal.id);
        const isReviewed = reviewedIds.has(signal.id);

        const cells = cols.map(col =>
            `<td class="${col.cssClass}">${col.render(signal, isPinned, isReviewed)}</td>`
        ).join('');

        return `<tr data-id="${signal.id}" class="${isPinned ? 'pinned' : ''} ${isReviewed ? 'reviewed' : ''}" onclick="selectSignalById(${signal.id})">${cells}</tr>`;
    }).join('');

    if (sortedSignals.length > window._compactDisplayLimit) {
        const remaining = sortedSignals.length - window._compactDisplayLimit;
        tbody.innerHTML += `<tr><td colspan="${colCount}" style="text-align:center;color:var(--text-muted);padding:8px;font-size:11px;">
            Showing ${window._compactDisplayLimit} of ${sortedSignals.length} articles &nbsp;·&nbsp;
            <a href="#" onclick="event.preventDefault();window._compactDisplayLimit+=${COMPACT_VIEW_PAGE};render();" style="color:var(--accent);cursor:pointer;text-decoration:underline;">Load ${Math.min(COMPACT_VIEW_PAGE, remaining)} more</a>
        </td></tr>`;
    }
}

/**
 * Reset the compact table display limit back to page size.
 * Called when time window, filter, or search changes so the
 * user starts from the first page of results.
 */
function resetCardLimit() {
    window._compactDisplayLimit = 250;
}

function updateCompactTableHeaders() {
    document.querySelectorAll('.compact-table th[data-sort]').forEach(th => {
        th.classList.remove('sorted');
        const icon = th.querySelector('.sort-icon');
        if (icon) icon.textContent = '';

        if (th.dataset.sort === compactSortField) {
            th.classList.add('sorted');
            if (icon) icon.textContent = compactSortDir === 'desc' ? '▼' : '▲';
        }
    });
}

// ==================== INITIALIZATION ====================
function initColumnResize() {
    _loadColumnConfig();
    _renderTableHeader();
}
