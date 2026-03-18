/**
 * RYBAT Dashboard - State Management
 * Global state variables for the dashboard
 */

// ==================== STATE ====================
let allSignals = [];
let filteredSignals = [];
let pinnedIds = new Set();
let reviewedIds = new Set();
let selectedIndex = -1;
let currentView = 'compact';
let currentFilter = 'all';
let currentTimeWindow = 'all';
let searchQuery = '';
let compactSortField = 'age';
let compactSortDir = 'desc';
let ws = null;
let lastUpdateTime = null;
let totalDbCount = 0;

// Feed state
let feedState = {
    enabledGroups: ['global', 'osint'],
    availableGroups: [],
    pendingChanges: false,
    totalFeedCount: 0
};

// Performance metrics
let perfMetrics = {
    totalFeeds: 0,
    activeFeeds: 0,
    feedErrors: 0,
    articlesProcessed: 0,
    articlesRejected: 0
};

// Translator activity
let translatorMetrics = {
    callsPerMin: 0,
    cacheHits: 0
};
