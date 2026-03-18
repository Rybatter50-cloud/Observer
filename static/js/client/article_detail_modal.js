/**
 * RYBAT Client - Article Detail Modal
 * Draggable modal showing full signal details with full-text fetch capability.
 *
 * Opens when the user clicks an article title in the compact table.
 * Replaces the old pin-to-card workflow and the Actions column.
 *
 * Loads blocked-domain list on init so Fetch Full Text buttons are grayed
 * out for paywalled / subscriber-walled sources.
 */

// ==================== STATE ====================
var _admOverlay = null;   // overlay element (lazy-created)
var _admDrag = { active: false, startX: 0, startY: 0, origX: 0, origY: 0 };
var _admBlockedDomains = {};  // domain → 'paywall' | 'subscriber_wall'

// ==================== BLOCKED DOMAINS ====================

/**
 * Fetch the list of domains flagged as paywall / subscriber-wall.
 * Called once on page load; the map is checked when the modal opens.
 */
async function _admLoadBlockedDomains() {
    try {
        var resp = await fetch('/api/v1/intelligence/blocked-domains');
        var data = await resp.json();
        _admBlockedDomains = data.domains || {};
    } catch (e) {
        // Non-critical — buttons will work normally if this fails
    }
}

/**
 * Extract the domain from a URL string.
 */
function _admGetDomain(url) {
    if (!url) return '';
    try {
        return new URL(url).hostname.toLowerCase();
    } catch (e) {
        return '';
    }
}

// Load on startup
_admLoadBlockedDomains();

// ==================== OPEN / CLOSE ====================

function openArticleDetailModal(signalId) {
    var signal = allSignals.find(function(s) { return s.id === signalId; });
    if (!signal) return;

    _admEnsureOverlay();
    _admPopulate(signal);
    _admOverlay.classList.add('active');
}

function closeArticleDetailModal() {
    if (_admOverlay) _admOverlay.classList.remove('active');
}

// ==================== LAZY DOM CREATION ====================

function _admEnsureOverlay() {
    if (_admOverlay) return;

    _admOverlay = document.createElement('div');
    _admOverlay.className = 'article-detail-overlay';
    _admOverlay.onclick = function(e) {
        if (e.target === _admOverlay) closeArticleDetailModal();
    };

    _admOverlay.innerHTML =
        '<div class="article-detail-modal" id="admModal">' +
            '<div class="article-detail-header" id="admHeader">' +
                '<h3 id="admTitle"></h3>' +
                '<button class="article-detail-close" onclick="closeArticleDetailModal()">&times;</button>' +
            '</div>' +
            '<div class="article-detail-body">' +
                '<div class="article-detail-meta" id="admMeta"></div>' +
                '<div class="article-detail-actions" id="admActions"></div>' +
                '<div class="article-detail-text">' +
                    '<div class="article-detail-text-label">Article Details</div>' +
                    '<div class="article-detail-text-content" id="admTextContent"></div>' +
                '</div>' +
            '</div>' +
        '</div>';

    document.body.appendChild(_admOverlay);

    // Dragging
    var header = document.getElementById('admHeader');
    header.addEventListener('mousedown', _admDragStart);
    document.addEventListener('mousemove', _admDragMove);
    document.addEventListener('mouseup', _admDragEnd);

    // Esc to close
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape' && _admOverlay.classList.contains('active')) {
            closeArticleDetailModal();
        }
    });
}

// ==================== POPULATE ====================

function _admPopulate(signal) {
    var title = document.getElementById('admTitle');
    var meta = document.getElementById('admMeta');
    var actions = document.getElementById('admActions');
    var textContent = document.getElementById('admTextContent');
    var modal = document.getElementById('admModal');

    // Reset position to center
    modal.style.left = '';
    modal.style.top = '';
    modal.style.transform = '';

    // Title
    title.textContent = signal.title || 'Untitled';

    // Metadata
    var score = signal.relevance_score || 0;
    var scoreCls = score >= 85 ? 'score-high' : score >= 40 ? 'score-med' : 'score-low';

    var indicators = (signal.risk_indicators || []).map(function(c) {
        var label = window.INDICATOR_LABELS && window.INDICATOR_LABELS[c] || c;
        return c + ' (' + _admEsc(label) + ')';
    }).join(', ') || 'None';

    var timeDisplay = formatCardTime(signal);
    var rawTime = signal.published_at || signal.created_at || '';

    var translationInfo = '';
    if (signal.is_translated) {
        var lang = (signal.source_language || '??').toUpperCase();
        var via = signal.translation_source || 'unknown';
        translationInfo = 'Translated from ' + _admEsc(lang) + ' via ' + _admEsc(via);
    } else {
        translationInfo = 'Original (not translated)';
    }

    meta.innerHTML =
        _admMetaItem('Date / Time', _admEsc(timeDisplay) + (rawTime ? ' <span style="color:var(--text-muted);font-size:9px">(' + _admEsc(rawTime) + ')</span>' : '')) +
        _admMetaItem('Relevance Score', '<span class="' + scoreCls + '">' + score + ' / 100</span>') +
        _admMetaItem('Source', _admEsc(signal.source || 'RSS') + (signal.source_confidence ? ' (confidence: ' + signal.source_confidence + ')' : '')) +
        _admMetaItem('Author', _admEsc(signal.author || 'Unknown') + (signal.author_confidence ? ' (confidence: ' + signal.author_confidence + ')' : '')) +
        _admMetaItem('Location', _admEsc(signal.location || 'Unknown')) +
        _admMetaItem('Risk Indicators', indicators) +
        _admMetaItem('Analysis Mode', _admEsc(signal.analysis_mode || 'N/A')) +
        _admMetaItem('Translation', translationInfo) +
        (signal.source_group ? _admMetaItem('Feed Group', _admEsc(signal.source_group)) : '') +
        (signal.collector ? _admMetaItem('Collector', _admEsc(signal.collector)) : '');

    // Actions — check if this source is blocked (paywall / subscriber wall)
    var safeLink = safeUrl(signal.url);
    var escapedLink = escapeHtml(safeLink);
    var domain = _admGetDomain(signal.url);
    var blockType = domain ? (_admBlockedDomains[domain] || null) : null;

    // Build fetch button: grayed out if blocked, normal otherwise
    var fetchBtnHtml;
    if (blockType) {
        var blockLabel = blockType === 'paywall' ? 'Paywall' : 'Subscriber Wall';
        fetchBtnHtml =
            '<button class="article-detail-btn blocked" id="admFetchBtn" disabled ' +
                'title="This source has a ' + _admEsc(blockLabel.toLowerCase()) + ' — full text is not available">' +
                blockLabel + ' — Unavailable' +
            '</button>';
    } else {
        fetchBtnHtml =
            '<button class="article-detail-btn primary" id="admFetchBtn" onclick="_admFetchFullText(' + signal.id + ')">' +
                'Fetch Full Text' +
            '</button>';
    }

    // No "View Article" button — opening unknown URLs in a browser is a
    // security risk.  Users should use "Fetch Full Text" (server-side
    // trafilatura) for content, or "Copy Link" if they need the URL.
    actions.innerHTML =
        (safeLink
            ? '<button class="article-detail-btn" onclick="copyToClipboard(\'' + escapedLink + '\', this)">Copy Link</button>'
            : '') +
        fetchBtnHtml +
        '<button class="article-detail-btn" onclick="_admOpenXPostModal(' + signal.id + ')">Create X Post</button>' +
        '<button class="article-detail-btn" onclick="event.stopPropagation(); toggleReviewed(' + signal.id + '); _admUpdateReviewedBtn(' + signal.id + ')" id="admReviewBtn">' +
            (reviewedIds.has(signal.id) ? 'Reviewed' : 'Mark Reviewed') +
        '</button>';

    // Article text (description + full_text)
    var text = '';
    if (signal.full_text) {
        text = signal.full_text;
    } else if (signal.description) {
        text = signal.description;
    }

    if (text) {
        _admRenderArticleText(textContent, text);
        textContent.className = 'article-detail-text-content';
    } else {
        textContent.textContent = 'No article text available. Click "Fetch Full Text" to download.';
        textContent.className = 'article-detail-text-content empty';
    }
    _admCheckOverflow();
}

function _admUpdateReviewedBtn(signalId) {
    var btn = document.getElementById('admReviewBtn');
    if (btn) btn.textContent = reviewedIds.has(signalId) ? 'Reviewed' : 'Mark Reviewed';
}

function _admMetaItem(label, value) {
    return '<div class="article-meta-item">' +
        '<span class="article-meta-label">' + _admEsc(label) + '</span>' +
        '<span class="article-meta-value">' + value + '</span>' +
    '</div>';
}

function _admEsc(str) {
    return escapeHtml(String(str || ''));
}

// ==================== TEXT FORMATTING ====================

/**
 * Render plain text into <p> elements inside the container.
 * Uses .textContent per paragraph to prevent XSS.
 *
 * Strategy (in priority order):
 *  1. Split on blank lines (double newlines) — structured source text
 *  2. Split on single newlines — line-oriented source text
 *  3. Split on sentence boundaries — continuous blocks from trafilatura
 */
function _admRenderArticleText(container, text) {
    container.innerHTML = '';
    var trimmed = text.trim();
    if (!trimmed) return;

    // 1) Try splitting on blank lines (double newlines)
    var chunks = trimmed.split(/\n\s*\n/);
    if (chunks.length > 1) {
        _admAppendParagraphs(container, chunks);
        return;
    }

    // 2) Try splitting on single newlines
    var lines = trimmed.split(/\n/);
    if (lines.length > 1) {
        _admAppendParagraphs(container, lines);
        return;
    }

    // 3) Continuous block — split into paragraphs at sentence boundaries.
    //    Group roughly 3 sentences per paragraph for readable chunks.
    var sentences = _admSplitSentences(trimmed);
    var SENTENCES_PER_PARA = 3;

    for (var i = 0; i < sentences.length; i += SENTENCES_PER_PARA) {
        var group = sentences.slice(i, i + SENTENCES_PER_PARA).join(' ');
        if (!group.trim()) continue;
        var p = document.createElement('p');
        p.textContent = group;
        container.appendChild(p);
    }
}

/**
 * Append an array of text chunks as <p> elements, skipping blanks.
 */
function _admAppendParagraphs(container, chunks) {
    for (var i = 0; i < chunks.length; i++) {
        var content = chunks[i].replace(/\s*\n\s*/g, ' ').trim();
        if (!content) continue;
        var p = document.createElement('p');
        p.textContent = content;
        container.appendChild(p);
    }
}

/**
 * Split a continuous text block into sentences.
 * Handles common abbreviations (Mr., Mrs., Dr., U.S., etc.) and
 * quoted speech to avoid false breaks.
 */
function _admSplitSentences(text) {
    // Match sentence-ending punctuation followed by a space and uppercase letter,
    // or followed by a quote/close-paren then space and uppercase letter.
    // Negative lookbehind avoids splitting on common abbreviations.
    var parts = [];
    // Use a simpler approach: walk through and split on '. ', '? ', '! '
    // when the next character is uppercase, accounting for quotes.
    var abbrevs = /(?:Mr|Mrs|Ms|Dr|Jr|Sr|St|vs|etc|U\.S|Gen|Gov|Rep|Sen|Sgt|Cpl|Pvt|Lt|Cmdr|Adm|Prof|Rev|Inc|Corp|Ltd|Co|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s*$/;
    var buf = '';

    for (var i = 0; i < text.length; i++) {
        buf += text[i];

        // Check for sentence-ending punctuation
        if (text[i] === '.' || text[i] === '?' || text[i] === '!') {
            // Peek ahead: optional closing quote/paren, then space, then uppercase
            var rest = text.substring(i + 1);
            var ahead = rest.match(/^(["'\u201D\u2019)\]]?\s)/);
            if (ahead) {
                var afterSpace = rest.substring(ahead[0].length);
                if (afterSpace.length > 0 && /[A-Z\u201C\u2018"']/.test(afterSpace[0])) {
                    // Check it's not a common abbreviation
                    if (!abbrevs.test(buf)) {
                        buf += ahead[0];
                        i += ahead[0].length;
                        parts.push(buf.trim());
                        buf = '';
                        continue;
                    }
                }
            }
        }
    }
    if (buf.trim()) parts.push(buf.trim());
    return parts;
}

/**
 * Toggle the scroll-fade indicator on the text panel based on overflow.
 */
function _admCheckOverflow() {
    var panel = document.querySelector('.article-detail-text');
    if (!panel) return;
    if (panel.scrollHeight > panel.clientHeight) {
        panel.classList.add('has-overflow');
    } else {
        panel.classList.remove('has-overflow');
    }
}

// ==================== FETCH FULL TEXT ====================

async function _admFetchFullText(signalId) {
    var btn = document.getElementById('admFetchBtn');
    if (!btn) return;

    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> Fetching...';

    try {
        var resp = await fetch('/api/v1/intelligence/' + signalId + '/fetch-fulltext', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        var data = await resp.json();

        if (data.success && data.full_text) {
            // Update the in-memory signal
            var signal = allSignals.find(function(s) { return s.id === signalId; });
            if (signal) signal.full_text = data.full_text;

            // Update modal text panel
            var textContent = document.getElementById('admTextContent');
            if (textContent) {
                _admRenderArticleText(textContent, data.full_text);
                textContent.className = 'article-detail-text-content';
                _admCheckOverflow();
            }

            btn.textContent = 'Fetched';
            btn.disabled = false;
        } else if (data.block_type) {
            // Server detected a paywall/subscriber wall — flag locally
            // so future opens of any article from this domain are blocked
            if (data.domain) {
                _admBlockedDomains[data.domain] = data.block_type;
            }
            var blockLabel = data.block_type === 'paywall' ? 'Paywall' : 'Subscriber Wall';
            btn.textContent = blockLabel + ' — Unavailable';
            btn.className = 'article-detail-btn blocked';
            btn.disabled = true;
            btn.onclick = null;
        } else {
            btn.textContent = 'Failed: ' + (data.error || 'Unknown error');
            btn.disabled = false;
        }
    } catch (e) {
        btn.textContent = 'Error: ' + e.message;
        btn.disabled = false;
    }
}

// ==================== DRAGGING ====================

function _admDragStart(e) {
    // Only drag from header, not from buttons
    if (e.target.tagName === 'BUTTON') return;

    var modal = document.getElementById('admModal');
    if (!modal) return;

    _admDrag.active = true;
    _admDrag.startX = e.clientX;
    _admDrag.startY = e.clientY;

    var rect = modal.getBoundingClientRect();
    _admDrag.origX = rect.left;
    _admDrag.origY = rect.top;

    // Switch from centered to positioned
    modal.style.transform = 'none';
    modal.style.left = rect.left + 'px';
    modal.style.top = rect.top + 'px';

    e.preventDefault();
}

function _admDragMove(e) {
    if (!_admDrag.active) return;

    var modal = document.getElementById('admModal');
    if (!modal) return;

    var dx = e.clientX - _admDrag.startX;
    var dy = e.clientY - _admDrag.startY;
    modal.style.left = (_admDrag.origX + dx) + 'px';
    modal.style.top = (_admDrag.origY + dy) + 'px';
}

function _admDragEnd() {
    _admDrag.active = false;
}

// ==================== X POST MODAL ====================

var _admXPostOverlay = null;

function _admOpenXPostModal(signalId) {
    var signal = allSignals.find(function(s) { return s.id === signalId; });
    if (!signal) return;

    _admEnsureXPostOverlay();

    // Build the formatted X post text
    var group = signal.source_group || signal.source || 'Intel';
    var ts = signal.published_at || signal.created_at || '';
    var dateStr = '';
    if (ts) {
        try {
            var d = new Date(ts);
            if (!isNaN(d.getTime())) {
                dateStr = d.toLocaleDateString('en-US', {
                    year: 'numeric', month: 'short', day: 'numeric'
                }) + ' ' + d.toLocaleTimeString('en-US', {
                    hour: '2-digit', minute: '2-digit', hour12: false
                }) + 'Z';
            }
        } catch (e) { /* use empty */ }
    }

    var headline = signal.title || 'Untitled';
    var link = safeUrl(signal.url) || '';

    var lines = [];
    lines.push(group + ' - ' + dateStr);
    lines.push('-');
    lines.push(headline);
    if (link) {
        lines.push('-');
        lines.push(link);
    }

    var postText = lines.join('\n');

    var textarea = document.getElementById('admXPostText');
    textarea.value = postText;

    // Character count
    _admUpdateXPostCount();

    _admXPostOverlay.classList.add('active');
}

function _admEnsureXPostOverlay() {
    if (_admXPostOverlay) return;

    _admXPostOverlay = document.createElement('div');
    _admXPostOverlay.className = 'adm-xpost-overlay';
    _admXPostOverlay.onclick = function(e) {
        if (e.target === _admXPostOverlay) _admCloseXPostModal();
    };

    _admXPostOverlay.innerHTML =
        '<div class="adm-xpost-modal">' +
            '<div class="adm-xpost-header">' +
                '<h3>Create X Post</h3>' +
                '<button class="article-detail-close" onclick="_admCloseXPostModal()">&times;</button>' +
            '</div>' +
            '<div class="adm-xpost-body">' +
                '<textarea id="admXPostText" class="adm-xpost-textarea" spellcheck="false"></textarea>' +
                '<div class="adm-xpost-footer">' +
                    '<span class="adm-xpost-count" id="admXPostCount"></span>' +
                    '<button class="article-detail-btn primary" onclick="_admCopyXPost()">Copy to Clipboard</button>' +
                '</div>' +
            '</div>' +
        '</div>';

    document.body.appendChild(_admXPostOverlay);

    var textarea = document.getElementById('admXPostText');
    textarea.addEventListener('input', _admUpdateXPostCount);
}

function _admCloseXPostModal() {
    if (_admXPostOverlay) _admXPostOverlay.classList.remove('active');
}

function _admUpdateXPostCount() {
    var textarea = document.getElementById('admXPostText');
    var counter = document.getElementById('admXPostCount');
    if (!textarea || !counter) return;
    var len = textarea.value.length;
    counter.textContent = len + ' / 280';
    counter.className = 'adm-xpost-count' + (len > 280 ? ' over' : '');
}

function _admCopyXPost() {
    var textarea = document.getElementById('admXPostText');
    if (!textarea) return;
    navigator.clipboard.writeText(textarea.value).then(function() {
        var btn = _admXPostOverlay.querySelector('.article-detail-btn.primary');
        if (btn) {
            btn.textContent = 'Copied!';
            setTimeout(function() { btn.textContent = 'Copy to Clipboard'; }, 1500);
        }
    });
}
