/**
 * Observer Dashboard - Feeds Module
 * Feed group management, API calls, region toggles
 * 
 * @created 2026-02-03 by Claude - Modularized from monolithic dashboard.html
 * @updated 2026-02-02 by Claude - Removed warning (tuning/telemetry approach instead)
 * @updated 2026-02-03 by Claude - Fixed hit rate telemetry (was always 0%)
 */

// ==================== FEED DATA FETCHING ====================
async function fetchFeedStatus() {
    try {
        const response = await fetch('/api/v1/feeds/status');
        if (!response.ok) return;
        
        const data = await response.json();
        feedState.enabledGroups = data.enabled_groups || ['global', 'osint'];
        
        perfMetrics.totalFeeds = data.total_feeds || 0;
        perfMetrics.activeFeeds = data.total_enabled_feeds || 0;
        perfMetrics.feedErrors = data.feed_errors || 0;
        
        // =====================================================================
        // Hit rate telemetry - @fixed 2026-02-03 by Claude
        // These were never being populated, causing Hit Rate to always show 0%
        // =====================================================================
        perfMetrics.articlesProcessed = data.articles_processed || 0;
        perfMetrics.articlesRejected = data.articles_rejected || 0;
        
        updateStats();
        checkFeedLimit();
    } catch (error) {
        console.error('Feed status error:', error);
    }
}

async function fetchFeedGroups() {
    try {
        const response = await fetch('/api/v1/feeds/groups');
        if (!response.ok) return;
        
        const data = await response.json();
        feedState.availableGroups = data.groups || [];
        renderFeedGroups();
        checkFeedLimit();
    } catch (error) {
        console.error('Feed groups error:', error);
    }
}

// ==================== FEED MANAGEMENT ====================
function renderFeedGroups() {
    const container = document.getElementById('tier2Groups');
    if (!container) return;  // <-- add this line
    const tier2 = feedState.availableGroups.filter(g => g.tier === 2);
    tier2.sort((a, b) => a.name.localeCompare(b.name));
    
    container.innerHTML = tier2.map(group => {
        const enabled = feedState.enabledGroups.includes(group.name);
        const eName = escapeHtml(group.name);
        return `
            <div class="feed-group-item ${enabled ? 'enabled' : ''}" onclick="toggleFeedGroup('${eName}')">
                <input type="checkbox" ${enabled ? 'checked' : ''} onclick="event.stopPropagation(); toggleFeedGroup('${eName}')">
                <span class="feed-group-name">${escapeHtml(formatGroupName(group.name))}</span>
                <span class="feed-group-count">${group.feed_count}</span>
            </div>
        `;
    }).join('');
    
    // Update Select All button state - @created 2026-02-02 by Claude
    const btn = document.getElementById('selectAllBtn');
    if (btn && tier2.length > 0) {
        const allSelected = tier2.every(g => feedState.enabledGroups.includes(g.name));
        btn.textContent = allSelected ? 'Deselect All' : 'Select All';
        if (allSelected) {
            btn.classList.add('active');
        } else {
            btn.classList.remove('active');
        }
    }
}

function formatGroupName(name) {
    return name.replace(/_/g, ' ')
               .split(' ')
               .map(w => w.charAt(0).toUpperCase() + w.slice(1))
               .join(' ');
}

function toggleFeedGroup(groupName) {
    if (feedState.enabledGroups.includes(groupName)) {
        feedState.enabledGroups = feedState.enabledGroups.filter(g => g !== groupName);
    } else {
        feedState.enabledGroups.push(groupName);
    }
    feedState.pendingChanges = true;
    renderFeedGroups();
    updateApplyButton();
    checkFeedLimit();
}

function updateApplyButton() {
    const btn = document.getElementById('applyFeedsBtn');
    if (btn) {
        btn.disabled = !feedState.pendingChanges;
        btn.classList.toggle('pending', feedState.pendingChanges);
    }
}

// ==================== REGION PRESETS ====================
async function enableRegion(regionName) {
    try {
        const response = await fetch(`/api/v1/feeds/region/${regionName}`, {
            method: 'POST'
        });
        if (response.ok) {
            await fetchFeedStatus();
            await fetchFeedGroups();
        }
    } catch (error) {
        console.error('Region error:', error);
    }
}

function updateRegionButtons() {
    document.querySelectorAll('.region-btn').forEach(btn => {
        const region = btn.dataset.region;
        const regionGroups = getRegionGroups(region);
        const active = regionGroups.every(g => feedState.enabledGroups.includes(g));
        btn.classList.toggle('active', active);
    });
}

function getRegionGroups(region) {
    const regionMappings = {
        'ukraine': ['ukraine', 'russia', 'belarus', 'estonia', 'latvia', 'lithuania', 'poland'],
        'middle_east': ['bahrain', 'iran', 'iraq', 'israel', 'jordan', 'kuwait', 'lebanon', 'oman', 'qatar', 'saudi_arabia', 'syria', 'uae', 'turkey', 'yemen'],
        'asia': ['australia', 'bangladesh', 'china', 'hong_kong', 'india', 'indonesia', 'japan', 'malaysia', 'myanmar', 'new_zealand', 'north_korea', 'pakistan', 'philippines', 'singapore', 'south_korea', 'sri_lanka', 'taiwan', 'thailand', 'vietnam'],
        'africa': ['algeria', 'egypt', 'ethiopia', 'ghana', 'kenya', 'libya', 'morocco', 'nigeria', 'senegal', 'somalia', 'south_africa', 'south_sudan', 'sudan', 'tanzania', 'tunisia', 'uganda', 'zambia', 'zimbabwe'],
        'americas': ['argentina', 'brazil', 'canada', 'chile', 'colombia', 'cuba', 'ecuador', 'mexico', 'peru', 'usa', 'uruguay', 'venezuela'],
        'caucasus_central_asia': ['afghanistan', 'armenia', 'azerbaijan', 'georgia', 'kazakhstan', 'kyrgyzstan', 'tajikistan', 'turkmenistan', 'uzbekistan']
    };
    return regionMappings[region] || [];
}

// ==================== FEED LIMIT CHECK ====================
function checkFeedLimit() {
    // Visual warning if too many feeds enabled
    const MAX_RECOMMENDED = 150;
    const warningEl = document.getElementById('feedLimitWarning');
    
    if (warningEl && perfMetrics.activeFeeds > MAX_RECOMMENDED) {
        warningEl.style.display = 'block';
        warningEl.textContent = `⚠️ ${perfMetrics.activeFeeds} feeds enabled (>${MAX_RECOMMENDED} may impact performance)`;
    } else if (warningEl) {
        warningEl.style.display = 'none';
    }
}

// ==================== APPLY CHANGES ====================
async function applyFeedChanges() {
    const btn = document.getElementById('applyFeedsBtn');
    if (btn) btn.disabled = true;
    
    try {
        // Get current enabled groups from state
        const currentEnabled = new Set(feedState.enabledGroups);
        
        // Determine what to enable/disable
        const toEnable = feedState.enabledGroups.filter(g => g !== 'global' && g !== 'osint');
        const allTier2 = feedState.availableGroups.filter(g => g.tier === 2).map(g => g.name);
        const toDisable = allTier2.filter(g => !currentEnabled.has(g));
        
        // Enable selected groups
        if (toEnable.length > 0) {
            await fetch('/api/v1/feeds/groups/enable', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ groups: toEnable })
            });
        }
        
        // Disable unselected groups
        if (toDisable.length > 0) {
            await fetch('/api/v1/feeds/groups/disable', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ groups: toDisable })
            });
        }
        
        feedState.pendingChanges = false;
        await fetchFeedStatus();
    } catch (error) {
        console.error('Apply error:', error);
    }
    
    if (btn) btn.disabled = false;
    updateApplyButton();
}

async function resetFeedDefaults() {
    try {
        await fetch('/api/v1/feeds/reset', { method: 'POST' });
        feedState.enabledGroups = ['global', 'osint'];
        feedState.pendingChanges = false;
        renderFeedGroups();
        updateApplyButton();
        updateRegionButtons();
        checkFeedLimit();
        await fetchFeedStatus();
    } catch (error) {
        console.error('Reset error:', error);
    }
}

// ==================== SELECT ALL FEEDS ====================
// @created 2026-02-02 by Claude - Toggle all feed groups on/off
function toggleSelectAllFeeds() {
    const btn = document.getElementById('selectAllBtn');
    const tier2Groups = feedState.availableGroups.filter(g => 
        g.name !== 'global' && g.name !== 'osint'
    );
    
    // Check if all are currently selected
    const allSelected = tier2Groups.every(g => feedState.enabledGroups.includes(g.name));
    
    if (allSelected) {
        // Deselect all (keep only tier1)
        feedState.enabledGroups = ['global', 'osint'];
        btn.textContent = 'Select All';
        btn.classList.remove('active');
    } else {
        // Select all
        feedState.enabledGroups = ['global', 'osint', ...tier2Groups.map(g => g.name)];
        btn.textContent = 'Deselect All';
        btn.classList.add('active');
    }
    
    feedState.pendingChanges = true;
    renderFeedGroups();
    updateApplyButton();
    checkFeedLimit();
}
