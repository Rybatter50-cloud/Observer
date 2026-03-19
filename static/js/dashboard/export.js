/**
 * Observer Dashboard - Export Module
 * Data export functionality (CSV/JSON)
 * 
 * @created 2026-02-03 by Claude - Modularized from monolithic dashboard.html
 */

// ==================== EXPORT ====================
function exportData(format) {
    const data = filteredSignals.map(s => ({
        id: s.id,
        relevance_score: s.relevance_score,
        title: s.title,
        location: s.location,
        source: s.source,
        risk_indicators: (s.risk_indicators || []).join(','),
        source_confidence: s.source_confidence || 0,
        author_confidence: s.author_confidence || 0,
        time: s.timeStr,
        created_at: s.created_at,
        url: s.url,
    }));
    
    let content, filename, type;
    
    if (format === 'json') {
        content = JSON.stringify(data, null, 2);
        filename = `observer-export-${Date.now()}.json`;
        type = 'application/json';
    } else {
        const headers = Object.keys(data[0] || {});
        const rows = data.map(d => headers.map(h => `"${(d[h] || '').toString().replace(/"/g, '""')}"`).join(','));
        content = [headers.join(','), ...rows].join('\n');
        filename = `observer-export-${Date.now()}.csv`;
        type = 'text/csv';
    }
    
    const blob = new Blob([content], { type });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
}
