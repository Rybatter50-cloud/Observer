/**
 * RYBAT Dashboard - Cards Module
 * Intel card rendering and creation
 *
 * @created 2026-02-03 by Claude - Modularized from monolithic dashboard.html
 * @updated 2026-02-04 by Claude - Analysis mode icon badges
 * @updated 2026-02-05 by Claude - Added staggered signal presentation
 * @updated 2026-02-05 by Claude - Added card limit for full view
 * @updated 2026-02-05 by Mr Cat + Claude - Added translation tracking badges
 * @updated 2026-02-06 by Mr Cat + Claude - Confidence scoring (replaces threat_score display)
 */

// US State Dept risk indicator labels
window.INDICATOR_LABELS = {
    'C': 'Crime', 'T': 'Terrorism', 'U': 'Civil Unrest', 'H': 'Health',
    'N': 'Natural Disaster', 'E': 'Time-Limited Event', 'K': 'Kidnapping',
    'D': 'Wrongful Detention', 'X': 'Cyber Threat', 'F': 'Financial/Economic',
    'M': 'Military'
};

// ==================== RENDERING ====================
function render() {
    const feedCountEl = document.getElementById('feedCount');
    if (feedCountEl) {
        var total = totalDbCount || allSignals.length;
        if (filteredSignals.length < total) {
            feedCountEl.textContent = `${filteredSignals.length} of ${total.toLocaleString()} articles`;
        } else {
            feedCountEl.textContent = `${total.toLocaleString()} articles`;
        }
    }

    // Clear legacy pinned card section (articles now open in modal)
    const pinnedSection = document.getElementById('pinnedSection');
    if (pinnedSection) pinnedSection.classList.remove('has-pins');
    const pinnedCards = document.getElementById('pinnedCards');
    if (pinnedCards) pinnedCards.innerHTML = '';

    // Render compact table with all filtered signals
    renderCompact(filteredSignals);
}

/**
 * Update an existing rendered card in-place (e.g. when screening_hits arrive via WebSocket).
 * Finds the card DOM element by signal ID and replaces it without disrupting scroll or animation.
 * @param {object} signal - The updated signal object (already merged in allSignals)
 * @returns {boolean} true if card was found and updated
 */
function updateExistingCard(signal) {
    if (!signal || !signal.id) return false;

    const card = document.querySelector(`.intel-card[data-id="${signal.id}"]`);
    if (!card) return false;

    const isPinnedSection = card.closest('#pinnedCards') !== null;
    const newHtml = createCard(signal, isPinnedSection);
    const temp = document.createElement('div');
    temp.innerHTML = newHtml;
    const newCard = temp.firstElementChild;

    // Preserve animation/transition classes from old card
    if (card.classList.contains('card-entering')) {
        newCard.classList.add('card-entering');
    }

    card.replaceWith(newCard);
    return true;
}

// Threshold for AI routing (signals with initial score >= this go to AI)
const AI_ROUTING_THRESHOLD = 75;

/**
 * Generate analysis mode badge HTML
 * @param {string} mode - 'LOCAL', 'FALLBACK', or 'SKIPPED'
 * @returns {string} HTML for the badge with icon
 *
 * - LOCAL mode: 🦙 (llama) - purple color (Ollama / sentence-transformer)
 * - FALLBACK: ⚠️ (warning) - orange color
 */
function getAnalysisModeBadge(mode) {
    if (!mode) return '';

    const modeUpper = mode.toUpperCase();

    if (modeUpper === 'LOCAL') {
        return `<span class="badge badge-analysis local" title="LOCAL mode - Ollama analysis">🦙</span>`;
    } else if (modeUpper === 'FALLBACK') {
        return `<span class="badge badge-analysis fallback" title="FALLBACK - No AI available">⚠️</span>`;
    } else if (modeUpper === 'MANUAL') {
        return `<span class="badge badge-analysis manual" title="MANUAL - Analyst hand-curated">✎</span>`;
    }

    return '';
}

/**
 * Generate translation badge HTML for card footer
 * @param {object} signal - Signal object with translation fields
 * @returns {string} HTML for translation badges (or empty string if not translated)
 *
 * @created 2026-02-05 by Mr Cat + Claude - Translation tracking badges
 * Fields used:
 * - is_translated: 1 if translated, 0 or null if not
 * - source_language: 2-letter ISO code (e.g., 'ru', 'ar', 'zh')
 * - translation_source: 'cache', 'api', or 'ollama'
 */
function getTranslationBadges(signal) {
    // Only show badges for translated signals
    if (!signal.is_translated) return '';

    const lang = signal.source_language || 'unknown';
    const via = signal.translation_source || 'unknown';

    // Language display names for tooltips
    const langNames = {
        'ru': 'Russian', 'uk': 'Ukrainian', 'bg': 'Bulgarian', 'sr': 'Serbian', 'be': 'Belarusian',
        'ar': 'Arabic', 'fa': 'Persian', 'ur': 'Urdu', 'he': 'Hebrew',
        'zh': 'Chinese', 'ja': 'Japanese', 'ko': 'Korean',
        'es': 'Spanish', 'fr': 'French', 'de': 'German', 'pt': 'Portuguese', 'it': 'Italian'
    };
    const langName = langNames[lang] || lang.toUpperCase();

    // Via display names
    const viaNames = {
        'cache': 'Cache (instant)',
        'api': 'API',
        'ollama': 'Ollama (local)'
    };
    const viaName = viaNames[via] || via;

    return `<div class="translation-badges">
        <span class="translation-badge translated" title="Translated from ${escapeHtml(langName)}">Translated</span>
        <span class="translation-badge lang lang-${escapeHtml(lang)}" title="${escapeHtml(langName)}">${escapeHtml(lang.toUpperCase())}</span>
        <span class="translation-badge via via-${escapeHtml(via)}" title="Via ${escapeHtml(viaName)}">${escapeHtml(via)}</span>
    </div>`;
}

/**
 * Generate entity pills HTML for card display.
 * Color-coded by type: PERSON=blue, ORG=green, GPE=orange.
 * Red warning icon on entities with screening hits.
 */
function getEntityPills(signal) {
    const entities = signal.entities_json;
    if (!entities || !Array.isArray(entities) || entities.length === 0) return '';

    const typeColors = {
        'PERSON': 'entity-person',
        'ORG': 'entity-org',
        'GPE': 'entity-gpe',
        'EVENT': 'entity-event',
    };

    const pills = entities.slice(0, 8).map(ent => {
        const cls = typeColors[ent.type] || 'entity-other';
        const conf = Math.round((ent.confidence || 0) * 100);
        const hasScreening = ent.screening_result && ent.screening_result.hit_count;
        const warn = hasScreening ? '<span class="entity-warn" title="Screening hit">!</span>' : '';
        return `<span class="entity-pill ${cls}" title="${escapeHtml(ent.type)}: ${escapeHtml(ent.text)} (${conf}%)">${warn}${escapeHtml(ent.text)}</span>`;
    }).join('');

    const more = entities.length > 8 ? `<span class="entity-pill entity-more">+${entities.length - 8}</span>` : '';

    return `<div class="entity-pills">${pills}${more}</div>`;
}

/**
 * Generate screening shield badge for card header.
 * Only shown when auto-screening found hits (red shield with count).
 * Clicking opens the screening modal with pre-loaded results.
 */
function getScreeningBadge(signal) {
    const hits = signal.screening_hits;
    if (!hits || !hits.hit_count) return '';

    const count = hits.hit_count;
    const maxScore = Math.round(hits.max_score || 0);
    const title = `${count} screening hit${count !== 1 ? 's' : ''} (max confidence: ${maxScore}%)`;

    return `<button class="screening-shield has-hits" onclick="openScreeningModal(${signal.id})" title="${title}">
        <span class="shield-icon">🛡</span><span class="shield-count">${count}</span>
    </button>`;
}

/**
 * Format a signal timestamp for display on cards.
 * Prefers published_at (original article time), falls back to created_at.
 * @param {object} signal
 * @returns {string} formatted time like "14:32" or "Feb 9 14:32"
 */
function formatCardTime(signal) {
    const raw = signal.published_at || signal.created_at;
    if (!raw) return '--:--';
    try {
        let ts = raw;
        if (typeof ts === 'string') {
            ts = ts.replace(' ', 'T');
            if (!ts.endsWith('Z') && !ts.includes('+')) ts += 'Z';
        }
        const d = new Date(ts);
        if (isNaN(d.getTime())) return '--:--';

        const now = new Date();
        const hhmm = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false });
        // If older than today, prepend short date
        if (d.toDateString() !== now.toDateString()) {
            const mon = d.toLocaleString('en', { month: 'short' });
            return `${mon} ${d.getDate()} ${hhmm}`;
        }
        return hhmm;
    } catch (e) {
        return '--:--';
    }
}

function createCard(signal, isPinnedSection) {
    const relevanceScore = signal.relevance_score || 0;
    const srcConf = signal.source_confidence || 0;
    const authConf = signal.author_confidence || 0;
    const age = getSignalAge(signal);
    const timeDisplay = formatCardTime(signal);

    // Card border uses relevance score
    const confClass = relevanceScore >= 80 ? 'conf-high' : relevanceScore >= 60 ? 'conf-moderate' : relevanceScore >= 40 ? 'conf-low' : 'conf-vlow';

    const isPinned = pinnedIds.has(signal.id);
    const isReviewed = reviewedIds.has(signal.id);

    const analysisModeBadge = getAnalysisModeBadge(signal.analysis_mode);
    const translationBadges = getTranslationBadges(signal);
    const screeningBadge = getScreeningBadge(signal);
    const entityPills = getEntityPills(signal);

    const eTitle = escapeHtml(signal.title || 'Untitled');
    const eSource = escapeHtml(signal.source || 'RSS');
    const eAuthor = escapeHtml(signal.author);
    const eLocation = escapeHtml(signal.location || 'Unknown');
    const eGroup = escapeHtml(signal.source_group);
    const eDesc = escapeHtml(signal.description);
    const eUrl = escapeHtml(safeUrl(signal.url));

    return `
        <div class="intel-card ${confClass} ${isPinned ? 'pinned' : ''} ${isReviewed ? 'reviewed' : ''}" data-id="${signal.id}">
            <div class="card-header">
                <div class="card-meta">
                    <div class="age-dot ${age.class}" title="${escapeHtml(age.text)}"></div>
                    <span class="time-badge" title="${escapeHtml(signal.published_at || signal.created_at || '')}">${timeDisplay}</span>
                    ${signal.source_group ? `<span class="badge badge-group" title="Feed group: ${eGroup}">${eGroup}</span>` : ''}
                    <span class="badge badge-source">${eSource}</span>
                    <span class="badge badge-src-score" title="Source confidence: ${srcConf}/100">${srcConf}</span>
                    ${signal.author ? `<span class="badge badge-author" title="Author: ${eAuthor}">${eAuthor}</span>` : ''}
                    <span class="badge badge-auth-score" title="Author confidence: ${authConf}/100">${authConf}</span>
                    <span class="badge badge-location">${eLocation}</span>
                    <span class="badge badge-score ie-clickable${signal.analysis_mode === 'MANUAL' ? ' ie-manual' : ''}" onclick="event.stopPropagation(); openScoreEditModal(${signal.id})" title="Relevance score: ${relevanceScore}/100 (click to edit)">${relevanceScore}</span>
                    <span class="ie-clickable" onclick="event.stopPropagation(); openIndicatorEditModal(${signal.id})" title="Click to edit indicators">${(signal.risk_indicators || []).map(c => `<span class="badge badge-indicator indicator-${escapeHtml(c).toLowerCase()}" title="${escapeHtml(window.INDICATOR_LABELS && window.INDICATOR_LABELS[c] || c)}">${escapeHtml(c)}</span>`).join('') || '<span class="ie-add-hint">+</span>'}</span>
                </div>
                <div class="card-actions">
                    ${screeningBadge}
                    <button class="card-action-btn ${isReviewed ? 'reviewed' : ''}" onclick="toggleReviewed(${signal.id})" title="Mark reviewed">✓</button>
                    <button class="card-action-btn ${isPinned ? 'pinned' : ''}" onclick="togglePin(${signal.id})" title="Pin">📌</button>
                </div>
            </div>
            <div class="card-title">${eTitle}</div>
            ${entityPills}
            <div class="card-footer">
                ${translationBadges}
                <button class="copy-link" onclick="copyToClipboard('${eUrl}', this)">Copy Link</button>
                <a href="${eUrl}" target="_blank" rel="noopener noreferrer" class="source-link">View Source →</a>
            </div>
            ${signal.description ? `<div class="card-desc-section">
                <button class="card-desc-toggle" onclick="toggleCardDesc(this)">&#9656; Description</button>
                <div class="card-desc-body">${eDesc}</div>
            </div>` : ''}
        </div>
    `;
}

function toggleCardDesc(btn) {
    const body = btn.nextElementSibling;
    if (!body) return;
    const isOpen = body.classList.contains('visible');
    body.classList.toggle('visible', !isOpen);
    btn.classList.toggle('expanded', !isOpen);
    btn.innerHTML = (isOpen ? '&#9656;' : '&#9662;') + ' Description';
}

function updateViewMode() {
    // Compact is the only view - just re-render
    render();
}
