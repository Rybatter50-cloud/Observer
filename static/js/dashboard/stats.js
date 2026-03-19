/**
 * Observer Dashboard - Stats Module
 * Stats updates, translator activity, clock
 */

// ==================== STATS ====================
function updateStats() {
    // Active feeds
    const activeFeedsEl = document.getElementById('statActiveFeeds');
    activeFeedsEl.textContent = perfMetrics.activeFeeds;
    activeFeedsEl.className = 'stat-value ' + (perfMetrics.feedErrors > 0 ? 'red' : 'green');

    // Total feeds
    document.getElementById('statTotalFeeds').textContent = perfMetrics.totalFeeds;

    // Accept rate (formerly Hit Rate)
    const totalArticles = perfMetrics.articlesProcessed + perfMetrics.articlesRejected;
    const hitRate = totalArticles > 0 ? Math.round((perfMetrics.articlesProcessed / totalArticles) * 100) : 0;
    document.getElementById('statHitRate').textContent = `${hitRate}%`;

    // Errors
    const errorsEl = document.getElementById('statErrors');
    errorsEl.textContent = perfMetrics.feedErrors;
    errorsEl.className = 'stat-value ' + (perfMetrics.feedErrors > 0 ? 'red' : 'green');

    // Feed count in header (element may not exist in admin panel layout)
    const feedCountEl = document.getElementById('feedCount');
    if (feedCountEl) {
        var total = (typeof totalDbCount !== 'undefined' && totalDbCount) ? totalDbCount : allSignals.length;
        if (filteredSignals.length < total) {
            feedCountEl.textContent = `${filteredSignals.length} of ${total.toLocaleString()} articles`;
        } else {
            feedCountEl.textContent = `${total.toLocaleString()} articles`;
        }
    }
}

function updateLastUpdateDisplay() {
    const el = document.getElementById('statLastUpdate');
    if (!el) return;

    if (!lastUpdateTime) {
        el.textContent = '--';
        return;
    }

    const diff = Math.floor((Date.now() - lastUpdateTime) / 1000);
    if (diff < 60) {
        el.textContent = `${diff}s`;
        el.className = 'stat-value green';
    } else if (diff < 3600) {
        el.textContent = `${Math.floor(diff / 60)}m`;
        el.className = 'stat-value red';
    } else {
        el.textContent = `${Math.floor(diff / 3600)}h`;
        el.className = 'stat-value red';
    }
}

function updateClock() {
    const now = new Date();
    document.getElementById('statTime').textContent =
        `${now.getHours().toString().padStart(2,'0')}:${now.getMinutes().toString().padStart(2,'0')}`;
    document.getElementById('statTimeUTC').textContent =
        ` ${now.getUTCHours().toString().padStart(2,'0')}:${now.getUTCMinutes().toString().padStart(2,'0')}Z`;
}

// ==================== SESSION TIMER ====================
const sessionStartTime = Date.now();

function updateSessionTimer() {
    const elapsed = Date.now() - sessionStartTime;
    const hours = Math.floor(elapsed / 3600000);
    const minutes = Math.floor((elapsed % 3600000) / 60000);
    const seconds = Math.floor((elapsed % 60000) / 1000);

    const timerEl = document.getElementById('sessionTimer');
    if (timerEl) {
        timerEl.textContent =
            `${hours.toString().padStart(2,'0')}:${minutes.toString().padStart(2,'0')}:${seconds.toString().padStart(2,'0')}`;
    }
}

// ==================== TRANSLATOR METRICS ====================
async function fetchTranslatorMetrics() {
    try {
        const response = await fetch('/api/v1/metrics/ai');
        if (!response.ok) return;

        const data = await response.json();

        translatorMetrics.callsPerMin = data.translator_calls_per_min || 0;
        translatorMetrics.cacheHits = data.translator_cache_hits || 0;

        updateTranslatorDisplay();
    } catch (error) {
        console.debug('Translator metrics fetch error:', error);
    }
}

function updateTranslatorDisplay() {
    var dot = document.getElementById('translatorDot');
    var value = document.getElementById('translatorValue');

    if (value) {
        value.textContent = translatorMetrics.callsPerMin + '/min';
    }

    if (dot) {
        if (translatorMetrics.callsPerMin > 0) {
            dot.classList.add('active');
        } else {
            dot.classList.remove('active');
        }
    }
}
