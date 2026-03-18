/**
 * RYBAT Dashboard - Ollama Chat Panel
 * Context-aware chat with Ollama + filter generation
 *
 * @created 2026-02-10 by Mr Cat + Claude
 */

// ==================== STATE ====================

var _chatBusy = false;
var _chatAvailable = false;

// ==================== DOM HELPERS ====================

function _chatEl(id) {
    return document.getElementById(id);
}

function _scrollChatToBottom() {
    var messages = _chatEl('chatMessages');
    if (messages) {
        messages.scrollTop = messages.scrollHeight;
    }
}

function _appendChatMessage(role, text) {
    var messages = _chatEl('chatMessages');
    if (!messages) return null;

    var msg = document.createElement('div');
    msg.className = 'chat-msg ' + role;
    msg.textContent = text;
    messages.appendChild(msg);
    _scrollChatToBottom();
    return msg;
}

function _appendFilterResult(filename, count) {
    var messages = _chatEl('chatMessages');
    if (!messages) return;

    var msg = document.createElement('div');
    msg.className = 'chat-msg analyst';
    // Friendly name: strip WL_ollama_ prefix
    var displayName = filename.replace(/^WL_ollama_/, '').replace(/_/g, ' ');
    displayName = displayName.charAt(0).toUpperCase() + displayName.slice(1);
    msg.innerHTML =
        '\u{1F916} Filter generated!' +
        '<div class="filter-result">' +
        '<span class="filter-badge-ai">AI</span> ' +
        '<span class="filter-name">' + _escHtml(displayName) + '</span>' +
        ' — ' + count + ' patterns<br>' +
        'Available in the Content Filter dropdown.' +
        '</div>';
    messages.appendChild(msg);
    _scrollChatToBottom();

    // Refresh content filter dropdowns so the new filter appears
    if (typeof fetchContentFilterStatus === 'function') {
        fetchContentFilterStatus();
    }
}

function _setThinking(on) {
    var existing = document.querySelector('.chat-msg.thinking');
    if (existing) existing.remove();

    if (on) {
        var messages = _chatEl('chatMessages');
        if (messages) {
            var msg = document.createElement('div');
            msg.className = 'chat-msg thinking';
            msg.textContent = 'Thinking';
            messages.appendChild(msg);
            _scrollChatToBottom();
        }
    }
}

function _setChatStatus(state) {
    var dot = _chatEl('chatStatusDot');
    if (dot) {
        dot.className = 'chat-status-dot ' + state;
    }
}

// ==================== COMMANDS ====================

/**
 * Detect special commands in user input.
 * Returns {type, args} or null for normal chat.
 */
function _parseCommand(text) {
    var lower = text.toLowerCase().trim();

    // "build filter for X" / "create filter for X"
    var filterMatch = lower.match(/^(?:build|create|make|generate)\s+(?:a\s+)?filter\s+(?:for|about|on)\s+(.+)/);
    if (filterMatch) {
        return { type: 'build-filter', topic: filterMatch[1].trim() };
    }

    // "/filter append <filename> "pattern1" "pattern2" ..."
    if (lower.startsWith('/filter append ')) {
        var appendArgs = text.slice(15).trim();
        // Extract filename (first token) and quoted patterns
        var parts = appendArgs.match(/^(\S+)\s+(.*)/);
        if (parts) {
            var patterns = [];
            var patternStr = parts[2];
            // Match quoted strings or bare words
            var re = /"([^"]+)"|'([^']+)'|(\S+)/g;
            var m;
            while ((m = re.exec(patternStr)) !== null) {
                patterns.push(m[1] || m[2] || m[3]);
            }
            return { type: 'append-filter', filename: parts[1], patterns: patterns };
        }
    }

    // "/filter X"
    if (lower.startsWith('/filter ')) {
        return { type: 'build-filter', topic: text.slice(8).trim() };
    }

    // "/discover <country>"
    if (lower.startsWith('/discover ')) {
        return { type: 'discover-feeds', country: text.slice(10).trim() };
    }

    // "/lang <code>"
    if (lower.startsWith('/lang ')) {
        return { type: 'filter-lang', lang: text.slice(6).trim() };
    }

    // "/feeds reset"
    if (lower === '/feeds reset') {
        return { type: 'feeds-reset' };
    }

    // "/feeds all"
    if (lower === '/feeds all') {
        return { type: 'feeds-all' };
    }

    // "/feeds <region>"
    if (lower.startsWith('/feeds ')) {
        return { type: 'manage-feeds', region: text.slice(7).trim() };
    }

    // "/screen [entity]"
    if (lower === '/screen') {
        return { type: 'screen', entity: '' };
    }
    if (lower.startsWith('/screen ')) {
        return { type: 'screen', entity: text.slice(8).trim() };
    }

    // "/clear"
    if (lower === '/clear' || lower === 'clear chat') {
        return { type: 'clear' };
    }

    // "/status"
    if (lower === '/status') {
        return { type: 'status' };
    }

    return null;
}

// ==================== API CALLS ====================

/**
 * Send a chat message to Ollama via the API.
 */
async function sendChatMessage() {
    if (_chatBusy) return;

    var input = _chatEl('chatInput');
    if (!input) return;

    var text = input.value.trim();
    if (!text) return;

    // Check for commands
    var cmd = _parseCommand(text);

    // Clear input immediately
    input.value = '';

    // Show user message
    _appendChatMessage('user', text);

    if (cmd && cmd.type === 'clear') {
        await _clearChat();
        return;
    }

    if (cmd && cmd.type === 'status') {
        await _showStatus();
        return;
    }

    if (cmd && cmd.type === 'build-filter') {
        await _buildFilter(cmd.topic);
        return;
    }

    if (cmd && cmd.type === 'append-filter') {
        await _appendToFilter(cmd.filename, cmd.patterns);
        return;
    }

    if (cmd && cmd.type === 'discover-feeds') {
        await _discoverFeeds(cmd.country);
        return;
    }

    if (cmd && cmd.type === 'filter-lang') {
        await _filterByLang(cmd.lang);
        return;
    }

    if (cmd && cmd.type === 'manage-feeds') {
        await _manageFeeds(cmd.region);
        return;
    }

    if (cmd && cmd.type === 'feeds-all') {
        await _enableAllFeeds();
        return;
    }

    if (cmd && cmd.type === 'feeds-reset') {
        await _resetFeeds();
        return;
    }

    if (cmd && cmd.type === 'screen') {
        _appendChatMessage('assistant', 'Opening screening panel...');
        openScreeningModalEmpty(cmd.entity);
        return;
    }

    // Normal chat message
    _chatBusy = true;
    _setChatStatus('busy');
    _setThinking(true);
    _chatEl('chatSendBtn').disabled = true;

    try {
        var response = await fetch('/api/v1/chat/message', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: text })
        });

        _setThinking(false);

        if (response.ok) {
            var data = await response.json();
            _appendChatMessage('analyst', data.response || 'No response.');
        } else {
            _appendChatMessage('system', 'Error: server returned ' + response.status);
        }
    } catch (error) {
        _setThinking(false);
        _appendChatMessage('system', 'Connection error: ' + error.message);
    } finally {
        _chatBusy = false;
        _setChatStatus(_chatAvailable ? 'connected' : 'error');
        _chatEl('chatSendBtn').disabled = false;
    }
}

/**
 * Build a filter via Ollama.
 */
async function _buildFilter(topic) {
    _chatBusy = true;
    _setChatStatus('busy');
    _setThinking(true);
    _chatEl('chatSendBtn').disabled = true;

    _appendChatMessage('system', 'Generating filter for: ' + topic + '...');

    try {
        // Sanitize topic into filename
        var name = topic.toLowerCase().replace(/[^a-z0-9]/g, '_').replace(/_+/g, '_').slice(0, 30).replace(/_$/, '');

        var response = await fetch('/api/v1/chat/build-filter', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ topic: topic, name: name })
        });

        _setThinking(false);

        if (response.ok) {
            var data = await response.json();
            if (data.success) {
                _appendFilterResult(data.filename, data.valid);
            } else {
                _appendChatMessage('system', 'Filter generation failed: ' + (data.error || 'unknown error'));
                if (data.raw_output) {
                    _appendChatMessage('analyst', 'Raw output:\n' + data.raw_output);
                }
            }
        } else {
            _appendChatMessage('system', 'Error: server returned ' + response.status);
        }
    } catch (error) {
        _setThinking(false);
        _appendChatMessage('system', 'Error: ' + error.message);
    } finally {
        _chatBusy = false;
        _setChatStatus(_chatAvailable ? 'connected' : 'error');
        _chatEl('chatSendBtn').disabled = false;
    }
}

/**
 * Append patterns to an existing filter file.
 */
async function _appendToFilter(filename, patterns) {
    _chatBusy = true;
    _setChatStatus('busy');
    _chatEl('chatSendBtn').disabled = true;

    _appendChatMessage('system', 'Appending ' + patterns.length + ' pattern(s) to ' + filename + '...');

    try {
        var response = await fetch('/api/v1/chat/append-filter', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ filename: filename, patterns: patterns })
        });

        if (response.ok) {
            var data = await response.json();
            if (data.success) {
                _appendChatMessage('analyst',
                    'Appended ' + data.added + ' pattern(s) to <b>' + _escHtml(data.filename) + '</b>' +
                    (data.duplicates > 0 ? ' (' + data.duplicates + ' duplicate(s) skipped)' : '') +
                    (data.invalid > 0 ? ' (' + data.invalid + ' invalid pattern(s) skipped)' : '') +
                    '. Total patterns: ' + data.total + '.');
                if (typeof fetchContentFilterStatus === 'function') {
                    fetchContentFilterStatus();
                }
            } else {
                _appendChatMessage('system', 'Append failed: ' + (data.error || 'unknown error'));
            }
        } else {
            _appendChatMessage('system', 'Error: server returned ' + response.status);
        }
    } catch (error) {
        _appendChatMessage('system', 'Error: ' + error.message);
    } finally {
        _chatBusy = false;
        _setChatStatus(_chatAvailable ? 'connected' : 'error');
        _chatEl('chatSendBtn').disabled = false;
    }
}

/**
 * Manage feeds by region via Ollama.
 */
async function _manageFeeds(region) {
    _chatBusy = true;
    _setChatStatus('busy');
    _setThinking(true);
    _chatEl('chatSendBtn').disabled = true;

    _appendChatMessage('system', 'Matching feeds for: ' + region + '...');

    try {
        var response = await fetch('/api/v1/chat/manage-feeds', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ region: region })
        });

        _setThinking(false);

        if (response.ok) {
            var data = await response.json();
            if (data.success) {
                _appendFeedsResult(data);
            } else {
                _appendChatMessage('system', 'Feed matching failed: ' + (data.error || 'unknown error'));
            }
        } else {
            _appendChatMessage('system', 'Error: server returned ' + response.status);
        }
    } catch (error) {
        _setThinking(false);
        _appendChatMessage('system', 'Error: ' + error.message);
    } finally {
        _chatBusy = false;
        _setChatStatus(_chatAvailable ? 'connected' : 'error');
        _chatEl('chatSendBtn').disabled = false;
    }
}

function _appendFeedsResult(data) {
    var messages = _chatEl('chatMessages');
    if (!messages) return;

    var enabled = data.enabled || [];
    var region = data.region || '?';
    var feedCount = data.enabled_feed_count || 0;
    var disabledCount = data.disabled_count || 0;
    var unchanged = data.unchanged || [];

    // Build enabled group list
    var groupList = enabled.map(function(g) {
        return g.replace(/_/g, ' ');
    }).join(', ');

    var msg = document.createElement('div');
    msg.className = 'chat-msg analyst';
    msg.innerHTML =
        '\u{1F4E1} Feeds updated for <b>' + _escHtml(region) + '</b>' +
        '<div class="feeds-result">' +
        '<span class="feeds-result-stat enabled">' + enabled.length + ' groups enabled</span> ' +
        '<span class="feeds-result-stat disabled">' + disabledCount + ' disabled</span> ' +
        '<span class="feeds-result-stat unchanged">' + _escHtml(unchanged.join(', ')) + ' unchanged</span>' +
        '<div class="feeds-result-groups">' + _escHtml(groupList) + '</div>' +
        '<div class="feeds-result-total">' + feedCount + ' feeds active</div>' +
        '<div class="feeds-result-hint">' +
        'Type <b>/filter ' + _escHtml(region.toLowerCase()) + '</b> to build a matching content filter, ' +
        'or <b>/feeds reset</b> to undo.' +
        '</div>' +
        '</div>';
    messages.appendChild(msg);
    _scrollChatToBottom();

    // Refresh dashboard feed status so counters update
    if (typeof fetchFeedStatus === 'function') {
        fetchFeedStatus();
    }
}

/**
 * Enable all feeds across all groups.
 */
async function _enableAllFeeds() {
    _chatBusy = true;
    _setChatStatus('busy');
    _chatEl('chatSendBtn').disabled = true;

    try {
        var response = await fetch('/api/v1/chat/enable-all-feeds', {
            method: 'POST'
        });

        if (response.ok) {
            var data = await response.json();
            if (data.success) {
                _appendChatMessage('analyst',
                    '\u{1F4E1} All feeds enabled. ' + data.enabled_count + ' feeds across ' + data.group_count + ' groups now active.');
                if (typeof fetchFeedStatus === 'function') {
                    fetchFeedStatus();
                }
            } else {
                _appendChatMessage('system', 'Failed: ' + (data.error || 'unknown error'));
            }
        } else {
            _appendChatMessage('system', 'Error: server returned ' + response.status);
        }
    } catch (error) {
        _appendChatMessage('system', 'Error: ' + error.message);
    } finally {
        _chatBusy = false;
        _setChatStatus(_chatAvailable ? 'connected' : 'error');
        _chatEl('chatSendBtn').disabled = false;
    }
}

/**
 * Reset feeds to pre-command state.
 */
async function _resetFeeds() {
    _chatBusy = true;
    _setChatStatus('busy');
    _chatEl('chatSendBtn').disabled = true;

    try {
        var response = await fetch('/api/v1/chat/reset-feeds', {
            method: 'POST'
        });

        if (response.ok) {
            var data = await response.json();
            if (data.success) {
                _appendChatMessage('analyst',
                    '\u2705 Feeds restored. ' + data.restored_feeds + ' feed states reset to previous configuration.');
                if (typeof fetchFeedStatus === 'function') {
                    fetchFeedStatus();
                }
            } else {
                _appendChatMessage('system', 'Reset failed: ' + (data.error || 'unknown error'));
            }
        } else {
            _appendChatMessage('system', 'Error: server returned ' + response.status);
        }
    } catch (error) {
        _appendChatMessage('system', 'Error: ' + error.message);
    } finally {
        _chatBusy = false;
        _setChatStatus(_chatAvailable ? 'connected' : 'error');
        _chatEl('chatSendBtn').disabled = false;
    }
}

/**
 * Discover RSS feeds for a country.
 */
async function _discoverFeeds(country) {
    _chatBusy = true;
    _setChatStatus('busy');
    _setThinking(true);
    _chatEl('chatSendBtn').disabled = true;

    _appendChatMessage('system', 'Discovering feeds for: ' + country + '...\nThis may take 30-60 seconds (probing domains for RSS).');

    try {
        var response = await fetch('/api/v1/chat/discover-feeds', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ country: country })
        });

        _setThinking(false);

        if (response.ok) {
            var data = await response.json();
            if (data.success) {
                _appendDiscoverResult(data);
            } else {
                _appendChatMessage('system', 'Discovery failed: ' + (data.error || 'unknown error'));
            }
        } else {
            _appendChatMessage('system', 'Error: server returned ' + response.status);
        }
    } catch (error) {
        _setThinking(false);
        _appendChatMessage('system', 'Error: ' + error.message);
    } finally {
        _chatBusy = false;
        _setChatStatus(_chatAvailable ? 'connected' : 'error');
        _chatEl('chatSendBtn').disabled = false;
    }
}

function _appendDiscoverResult(data) {
    var messages = _chatEl('chatMessages');
    if (!messages) return;

    var discovered = data.discovered || [];
    var scraperSites = data.scraper_sites || [];
    var failed = data.failed || [];
    var skipped = data.skipped || [];
    var country = data.country || '?';

    if (discovered.length === 0 && scraperSites.length === 0) {
        _appendChatMessage('analyst',
            'No feeds found for ' + country + '.\n' +
            failed.length + ' outlets checked — none had discoverable RSS or scrapable endpoints.\n' +
            'Try a different country or check manually.');
        return;
    }

    var msg = document.createElement('div');
    msg.className = 'chat-msg analyst';

    // Build RSS feed list with checkboxes
    var feedListHtml = '';
    if (discovered.length > 0) {
        feedListHtml += '<div class="discover-section-label">RSS Feeds</div>';
        for (var i = 0; i < discovered.length; i++) {
            var feed = discovered[i];
            var rssCount = feed.rss_urls ? feed.rss_urls.length : 0;
            feedListHtml +=
                '<label class="discover-feed-item">' +
                '<input type="checkbox" checked data-idx="' + i + '" class="discover-cb"> ' +
                '<span class="discover-feed-name">' + _escHtml(feed.name) + '</span> ' +
                '<span class="discover-feed-domain">' + _escHtml(feed.domain) + '</span> ' +
                '<span class="discover-feed-lang">' + _escHtml(feed.language || 'en') + '</span> ' +
                '<span class="discover-feed-rss">' + rssCount + ' RSS</span>' +
                '</label>';
        }
    }

    // Build scraper site list with checkboxes
    var scraperListHtml = '';
    if (scraperSites.length > 0) {
        scraperListHtml += '<div class="discover-section-label">Scraper Sites <span class="discover-section-note">(no RSS \u2014 scraped when Scraper enabled)</span></div>';
        for (var j = 0; j < scraperSites.length; j++) {
            var site = scraperSites[j];
            scraperListHtml +=
                '<label class="discover-feed-item discover-scraper-item">' +
                '<input type="checkbox" checked data-scraper-idx="' + j + '" class="discover-scraper-cb"> ' +
                '<span class="discover-feed-name">' + _escHtml(site.name) + '</span> ' +
                '<span class="discover-feed-domain">' + _escHtml(site.domain) + '</span> ' +
                '<span class="discover-feed-lang">' + _escHtml(site.language || 'en') + '</span> ' +
                '<span class="discover-feed-rss">Scraper</span>' +
                '</label>';
        }
    }

    var skippedHtml = '';
    if (skipped.length > 0) {
        var skippedNames = skipped.map(function(s) { return s.name; }).join(', ');
        skippedHtml = '<div class="discover-skipped">Already in registry: ' + _escHtml(skippedNames) + '</div>';
    }

    var failedHtml = '';
    if (failed.length > 0) {
        var failedNames = failed.map(function(f) { return f.name; }).join(', ');
        failedHtml = '<div class="discover-failed">' + _escHtml(failedNames) + '</div>';
    }

    // Gemini usage counter
    var usageHtml = '';
    var usage = data.gemini_usage;
    if (usage && typeof usage.remaining !== 'undefined') {
        usageHtml = '<div class="discover-usage">' + usage.remaining + ' USES REMAINING TODAY \u2014 RESETS AT 12:00 AM Pacific Time</div>';
    }

    // Summary line
    var summaryParts = [];
    if (discovered.length > 0) summaryParts.push('<b>' + discovered.length + '</b> RSS');
    if (scraperSites.length > 0) summaryParts.push('<b>' + scraperSites.length + '</b> Scraper');
    var summaryText = '\u{1F50D} Found ' + summaryParts.join(' + ') + ' sources in <b>' + _escHtml(country) + '</b>';

    msg.innerHTML =
        summaryText +
        '<div class="discover-result">' +
        '<div class="discover-feeds-list">' + feedListHtml + scraperListHtml + '</div>' +
        skippedHtml + failedHtml +
        '<div class="discover-actions">' +
        '<button class="discover-btn confirm" onclick="_confirmDiscoveredFeeds(this)">Add Selected</button> ' +
        '<button class="discover-btn skip" onclick="_skipDiscoveredFeeds(this)">Skip</button>' +
        '</div>' +
        usageHtml +
        '</div>';

    messages.appendChild(msg);
    _scrollChatToBottom();
}

function _escHtml(text) {
    var div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

async function _confirmDiscoveredFeeds(btn) {
    // Find the parent discover-result and get checked indices
    var result = btn.closest('.discover-result');
    if (!result) return;

    // RSS feed selections
    var checkboxes = result.querySelectorAll('.discover-cb:checked');
    var selected = [];
    for (var i = 0; i < checkboxes.length; i++) {
        selected.push(parseInt(checkboxes[i].getAttribute('data-idx')));
    }

    // NP4K scraper site selections
    var scraperCheckboxes = result.querySelectorAll('.discover-scraper-cb:checked');
    var selectedScrapers = [];
    for (var k = 0; k < scraperCheckboxes.length; k++) {
        selectedScrapers.push(parseInt(scraperCheckboxes[k].getAttribute('data-scraper-idx')));
    }

    if (selected.length === 0 && selectedScrapers.length === 0) {
        _appendChatMessage('system', 'No feeds selected.');
        return;
    }

    // Disable buttons
    var buttons = result.querySelectorAll('.discover-btn');
    for (var j = 0; j < buttons.length; j++) { buttons[j].disabled = true; }

    var totalCount = selected.length + selectedScrapers.length;
    _appendChatMessage('system', 'Adding ' + totalCount + ' sources to registry...');

    try {
        var response = await fetch('/api/v1/chat/confirm-feeds', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ selected: selected, selected_scrapers: selectedScrapers })
        });

        if (response.ok) {
            var data = await response.json();
            if (data.success) {
                var lines = ['\u2705 Added to "' + data.group + '" group:'];
                if (data.added_count > 0) {
                    lines.push('RSS feeds (' + data.added_count + '): ' + data.added.join(', '));
                }
                if (data.added_scraper_count > 0) {
                    lines.push('Scraper sites (' + data.added_scraper_count + '): ' + data.added_scrapers.join(', '));
                }
                lines.push('Group totals: ' + data.total_group_feeds + ' RSS feeds, ' + data.total_group_scrapers + ' scraper sites');
                _appendChatMessage('analyst', lines.join('\n'));
                if (typeof fetchFeedStatus === 'function') {
                    fetchFeedStatus();
                }
            } else {
                _appendChatMessage('system', 'Failed: ' + (data.error || 'unknown error'));
            }
        } else {
            _appendChatMessage('system', 'Error: server returned ' + response.status);
        }
    } catch (error) {
        _appendChatMessage('system', 'Error: ' + error.message);
    }
}

function _skipDiscoveredFeeds(btn) {
    var result = btn.closest('.discover-result');
    if (!result) return;
    var buttons = result.querySelectorAll('.discover-btn');
    for (var j = 0; j < buttons.length; j++) { buttons[j].disabled = true; }
    _appendChatMessage('system', 'Discovery results discarded.');
}

// ==================== LANGUAGE FILTER ====================

/**
 * Filter feeds by language code.
 */
async function _filterByLang(lang) {
    _chatBusy = true;
    _setChatStatus('busy');
    _chatEl('chatSendBtn').disabled = true;

    _appendChatMessage('system', 'Filtering feeds to language: ' + lang.toUpperCase() + '...');

    try {
        var response = await fetch('/api/v1/chat/filter-lang', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ lang: lang })
        });

        if (response.ok) {
            var data = await response.json();
            if (data.success) {
                var groups = (data.groups || []).map(function(g) { return g.replace(/_/g, ' '); }).join(', ');
                _appendChatMessage('analyst',
                    '\u{1F310} Language filter: <b>' + data.lang.toUpperCase() + '</b>\n' +
                    data.enabled_count + ' feeds enabled, ' + data.disabled_count + ' disabled\n' +
                    'Groups: ' + groups + '\n' +
                    '<span style="color:#9ca3af;font-size:9px">Type <b>/feeds reset</b> to undo, or <b>/feeds all</b> to re-enable everything.</span>'
                );
                if (typeof fetchFeedStatus === 'function') {
                    fetchFeedStatus();
                }
            } else {
                _appendChatMessage('system', 'Language filter: ' + (data.error || 'unknown error'));
            }
        } else {
            _appendChatMessage('system', 'Error: server returned ' + response.status);
        }
    } catch (error) {
        _appendChatMessage('system', 'Error: ' + error.message);
    } finally {
        _chatBusy = false;
        _setChatStatus(_chatAvailable ? 'connected' : 'error');
        _chatEl('chatSendBtn').disabled = false;
    }
}

/**
 * Clear conversation history.
 */
async function _clearChat() {
    try {
        await fetch('/api/v1/chat/clear', { method: 'POST' });
    } catch (e) { /* ignore */ }

    var messages = _chatEl('chatMessages');
    if (messages) messages.innerHTML = '';
    _appendChatMessage('system', 'Chat cleared. Type /filter <topic> to generate a filter.');
}

/**
 * Show Ollama status in chat.
 */
async function _showStatus() {
    try {
        var response = await fetch('/api/v1/chat/status');
        var data = await response.json();
        var text = 'Model: ' + data.model +
            '\nAvailable: ' + (data.available ? 'yes' : 'no') +
            '\nLoaded: ' + (data.model_loaded ? 'yes' : 'no');
        if (data.models && data.models.length > 0) {
            text += '\nInstalled: ' + data.models.join(', ');
        }
        if (data.error) {
            text += '\nError: ' + data.error;
        }
        _appendChatMessage('analyst', text);
    } catch (e) {
        _appendChatMessage('system', 'Cannot reach Ollama: ' + e.message);
    }
}

/**
 * Check Ollama availability on load.
 */
async function checkChatStatus() {
    try {
        var response = await fetch('/api/v1/chat/status');
        if (response.ok) {
            var data = await response.json();
            _chatAvailable = data.available || false;
            _setChatStatus(_chatAvailable ? 'connected' : 'error');

            if (!_chatAvailable) {
                _appendChatMessage('system', 'Ollama not available. Install: ollama pull ' + data.model);
            }
        }
    } catch (e) {
        _chatAvailable = false;
        _setChatStatus('error');
    }
}

// ==================== INITIALIZATION ====================

document.addEventListener('DOMContentLoaded', function() {
    var input = _chatEl('chatInput');
    if (input) {
        input.addEventListener('keypress', function(e) {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendChatMessage();
            }
        });
    }

    // Show welcome message
    _appendChatMessage('system',
        'RYBAT Analyst — Ollama-powered intelligence chat.\n' +
        'Commands: /discover <country>, /feeds <region>, /feeds all, /feeds reset, /lang <code>, /filter <topic>, /filter append <file> "patterns...", /screen [entity], /status, /clear'
    );

    // Check Ollama status
    setTimeout(checkChatStatus, 2000);
});
