/**
 * Observer Dashboard - Theme Management
 * Light/dark theme toggle functionality
 * 
 * @created 2026-02-03 by Claude - Modularized from monolithic dashboard.html
 */

// ==================== THEME ====================
function initTheme() {
    const saved = localStorage.getItem('observer-theme') || 'dark';
    document.documentElement.setAttribute('data-theme', saved);
    updateThemeButton(saved);
}

function toggleTheme() {
    const current = document.documentElement.getAttribute('data-theme');
    const next = current === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem('observer-theme', next);
    updateThemeButton(next);
}

function updateThemeButton(theme) {
    document.getElementById('themeToggle').textContent = theme === 'dark' ? '🌙' : '☀️';
}
