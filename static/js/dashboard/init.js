/**
 * Observer Dashboard - Initialization Module
 * Main initialization - DOMContentLoaded handler
 *
 * IMPORTANT: This file must be loaded LAST after all other modules
 */

// ==================== INITIALIZATION ====================
document.addEventListener('DOMContentLoaded', () => {
    initTheme();
    connectWebSocket();
    fetchTranslatorMetrics();
    updateClock();
    updateSessionTimer();
    setInterval(updateClock, 1000);
    setInterval(updateSessionTimer, 1000);
    setInterval(fetchTranslatorMetrics, 10000);

    // Initialize Database Control Panel
    initDatabasePanel();

    // Initialize Admin Control Panel
    initAdminPanel();
});
