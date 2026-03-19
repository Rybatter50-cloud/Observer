/**
 * Observer Dashboard - Inline Score & Indicator Editing
 * ====================================================
 * Allows analysts to click score badges and indicator cells to edit
 * relevance_score and risk_indicators directly from the feed.
 *
 * Sets analysis_mode='MANUAL' on the server so hand-curated labels
 * can be distinguished for sentence-transformer retraining.
 *
 * 2026-02-18 | Mr Cat + Claude
 */

// Full indicator registry (matches backend VALID_INDICATORS)
const ALL_INDICATORS = {
    'C': 'Crime',
    'T': 'Terrorism',
    'U': 'Civil Unrest',
    'H': 'Health',
    'N': 'Natural Disaster',
    'E': 'Time-Limited Event',
    'K': 'Kidnapping/Hostage Taking',
    'D': 'Wrongful Detention',
    'X': 'Cyber Threat',
    'F': 'Financial/Economic',
    'M': 'Military',
};

// ── Shared helpers ──

/** Find the signal object by ID from allSignals global */
function _findSignal(id) {
    return (allSignals || []).find(s => s.id === id) || null;
}

/** PATCH the server, update local state, close modal */
async function _submitEdit(signalId, score, indicators) {
    const btn = document.querySelector('.ie-modal .ie-save-btn');
    if (btn) { btn.disabled = true; btn.textContent = 'Saving...'; }

    try {
        const resp = await fetch(`/api/v1/intelligence/${signalId}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                relevance_score: score,
                risk_indicators: indicators,
            }),
        });

        if (!resp.ok) {
            const err = await resp.json().catch(() => ({}));
            throw new Error(err.detail || `HTTP ${resp.status}`);
        }

        const result = await resp.json();

        // Update local signal so re-render picks it up without waiting for WS
        if (result.signal) {
            const idx = (allSignals || []).findIndex(s => s.id === signalId);
            if (idx !== -1) {
                allSignals[idx] = { ...allSignals[idx], ...result.signal };
            }
        }

        _closeModal();

        // Re-render the table/cards
        if (typeof applyFilters === 'function') applyFilters();

    } catch (e) {
        if (btn) { btn.disabled = false; btn.textContent = 'Save'; }
        alert('Save failed: ' + e.message);
    }
}

// ── Modal infrastructure ──

function _closeModal() {
    const overlay = document.getElementById('ieModalOverlay');
    if (overlay) overlay.remove();
}

function _createOverlay() {
    // Remove any existing
    _closeModal();

    const overlay = document.createElement('div');
    overlay.id = 'ieModalOverlay';
    overlay.className = 'ie-overlay';
    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) _closeModal();
    });

    document.body.appendChild(overlay);
    return overlay;
}


// ═══════════════════════════════════════════════════════════════
//  SCORE EDIT MODAL
// ═══════════════════════════════════════════════════════════════

function openScoreEditModal(signalId) {
    const signal = _findSignal(signalId);
    if (!signal) return;

    const currentScore = signal.relevance_score || 0;
    const currentIndicators = signal.risk_indicators || [];
    const overlay = _createOverlay();

    const modal = document.createElement('div');
    modal.className = 'ie-modal ie-score-modal';
    modal.innerHTML = `
        <div class="ie-modal-header">
            <span class="ie-modal-title">Edit Score</span>
            <button class="ie-close-btn" title="Close">&times;</button>
        </div>
        <div class="ie-modal-body">
            <div class="ie-signal-title">${_escHtml((signal.title || 'Untitled').substring(0, 100))}</div>
            <div class="ie-field">
                <label class="ie-label">Relevance Score (0-100)</label>
                <div class="ie-score-input-row">
                    <input type="range" class="ie-score-slider" min="0" max="100" value="${currentScore}">
                    <input type="number" class="ie-score-number" min="0" max="100" value="${currentScore}">
                </div>
                <div class="ie-score-presets">
                    <button class="ie-preset" data-val="10">10</button>
                    <button class="ie-preset" data-val="25">25</button>
                    <button class="ie-preset" data-val="40">40</button>
                    <button class="ie-preset" data-val="65">65</button>
                    <button class="ie-preset" data-val="85">85</button>
                    <button class="ie-preset" data-val="95">95</button>
                </div>
            </div>
            <div class="ie-current-indicators">Current: ${currentIndicators.length ? currentIndicators.join(', ') : 'None'}</div>
        </div>
        <div class="ie-modal-footer">
            <button class="ie-cancel-btn">Cancel</button>
            <button class="ie-save-btn">Save Score</button>
        </div>
    `;

    overlay.appendChild(modal);

    // Sync slider ↔ number
    const slider = modal.querySelector('.ie-score-slider');
    const number = modal.querySelector('.ie-score-number');
    slider.addEventListener('input', () => { number.value = slider.value; });
    number.addEventListener('input', () => { slider.value = number.value; });

    // Presets
    modal.querySelectorAll('.ie-preset').forEach(btn => {
        btn.addEventListener('click', () => {
            slider.value = btn.dataset.val;
            number.value = btn.dataset.val;
        });
    });

    // Close
    modal.querySelector('.ie-close-btn').addEventListener('click', _closeModal);
    modal.querySelector('.ie-cancel-btn').addEventListener('click', _closeModal);

    // Save — keep existing indicators, just update score
    modal.querySelector('.ie-save-btn').addEventListener('click', () => {
        const newScore = Math.max(0, Math.min(100, parseInt(number.value) || 0));
        _submitEdit(signalId, newScore, currentIndicators);
    });

    // Focus the number input
    number.focus();
    number.select();

    // Enter to save
    number.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            modal.querySelector('.ie-save-btn').click();
        } else if (e.key === 'Escape') {
            _closeModal();
        }
    });
}


// ═══════════════════════════════════════════════════════════════
//  INDICATOR EDIT MODAL
// ═══════════════════════════════════════════════════════════════

function openIndicatorEditModal(signalId) {
    const signal = _findSignal(signalId);
    if (!signal) return;

    const currentScore = signal.relevance_score || 0;
    const currentIndicators = new Set(signal.risk_indicators || []);
    const overlay = _createOverlay();

    const modal = document.createElement('div');
    modal.className = 'ie-modal ie-indicator-modal';

    // Build indicator checkboxes
    const checkboxesHtml = Object.entries(ALL_INDICATORS).map(([code, label]) => {
        const checked = currentIndicators.has(code) ? 'checked' : '';
        return `<label class="ie-ind-option ${checked ? 'active' : ''}" data-code="${code}">
            <input type="checkbox" value="${code}" ${checked}>
            <span class="ie-ind-code">${code}</span>
            <span class="ie-ind-label">${label}</span>
        </label>`;
    }).join('');

    // Common compound presets
    const compoundPresetsHtml = `
        <div class="ie-compound-section">
            <span class="ie-compound-label">Quick combos:</span>
            <button class="ie-compound-btn" data-combo="C,T">C,T</button>
            <button class="ie-compound-btn" data-combo="T,M">T,M</button>
            <button class="ie-compound-btn" data-combo="E,F">E,F</button>
            <button class="ie-compound-btn" data-combo="C,T,U">C,T,U</button>
            <button class="ie-compound-btn" data-combo="T,M,U">T,M,U</button>
            <button class="ie-compound-btn" data-combo="C,X">C,X</button>
        </div>
        <div class="ie-custom-compound">
            <label class="ie-label">Custom compound (comma-separated):</label>
            <input type="text" class="ie-compound-input" placeholder="e.g. C,T,U" value="${[...currentIndicators].join(',')}">
        </div>
    `;

    modal.innerHTML = `
        <div class="ie-modal-header">
            <span class="ie-modal-title">Edit Indicators</span>
            <button class="ie-close-btn" title="Close">&times;</button>
        </div>
        <div class="ie-modal-body">
            <div class="ie-signal-title">${_escHtml((signal.title || 'Untitled').substring(0, 100))}</div>
            <div class="ie-ind-grid">${checkboxesHtml}</div>
            ${compoundPresetsHtml}
        </div>
        <div class="ie-modal-footer">
            <button class="ie-clear-btn">Clear All</button>
            <div class="ie-footer-right">
                <button class="ie-cancel-btn">Cancel</button>
                <button class="ie-save-btn">Save Indicators</button>
            </div>
        </div>
    `;

    overlay.appendChild(modal);

    const compoundInput = modal.querySelector('.ie-compound-input');

    // Sync checkboxes → input
    function syncFromCheckboxes() {
        const selected = [];
        modal.querySelectorAll('.ie-ind-option input:checked').forEach(cb => {
            selected.push(cb.value);
        });
        compoundInput.value = selected.join(',');

        // Update active class on labels
        modal.querySelectorAll('.ie-ind-option').forEach(label => {
            const cb = label.querySelector('input');
            label.classList.toggle('active', cb.checked);
        });
    }

    // Sync input → checkboxes
    function syncFromInput() {
        const codes = compoundInput.value.split(',')
            .map(s => s.trim().toUpperCase())
            .filter(s => s && ALL_INDICATORS[s]);
        const codeSet = new Set(codes);

        modal.querySelectorAll('.ie-ind-option input').forEach(cb => {
            cb.checked = codeSet.has(cb.value);
        });
        modal.querySelectorAll('.ie-ind-option').forEach(label => {
            const cb = label.querySelector('input');
            label.classList.toggle('active', cb.checked);
        });
    }

    // Checkbox change handlers
    modal.querySelectorAll('.ie-ind-option input').forEach(cb => {
        cb.addEventListener('change', syncFromCheckboxes);
    });

    // Compound preset buttons
    modal.querySelectorAll('.ie-compound-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            compoundInput.value = btn.dataset.combo;
            syncFromInput();
        });
    });

    // Custom input sync on blur/enter
    compoundInput.addEventListener('blur', syncFromInput);
    compoundInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            syncFromInput();
            modal.querySelector('.ie-save-btn').click();
        } else if (e.key === 'Escape') {
            _closeModal();
        }
    });

    // Clear all
    modal.querySelector('.ie-clear-btn').addEventListener('click', () => {
        modal.querySelectorAll('.ie-ind-option input').forEach(cb => { cb.checked = false; });
        compoundInput.value = '';
        syncFromCheckboxes();
    });

    // Close
    modal.querySelector('.ie-close-btn').addEventListener('click', _closeModal);
    modal.querySelector('.ie-cancel-btn').addEventListener('click', _closeModal);

    // Save — keep existing score, just update indicators
    modal.querySelector('.ie-save-btn').addEventListener('click', () => {
        const indicators = compoundInput.value.split(',')
            .map(s => s.trim().toUpperCase())
            .filter(s => s && ALL_INDICATORS[s]);
        _submitEdit(signalId, currentScore, indicators);
    });
}


// ── HTML escaping ──

function _escHtml(str) {
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

// ── Global exposure ──
window.openScoreEditModal = openScoreEditModal;
window.openIndicatorEditModal = openIndicatorEditModal;
