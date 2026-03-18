/**
 * RYBAT Dashboard - Configuration
 * Location coordinates, quick regions, constants
 * 
 * @created 2026-02-03 by Claude - Modularized from monolithic dashboard.html
 */

// ==================== QUICK REGIONS ====================
// Maps region buttons to feed groups
const QUICK_REGIONS = {
    'ukraine': ['ukraine', 'russia', 'belarus', 'estonia', 'latvia', 'lithuania', 'poland'],
    'middle_east': ['bahrain', 'iran', 'iraq', 'israel', 'jordan', 'kuwait', 'lebanon', 'oman', 'qatar', 'saudi_arabia', 'syria', 'uae', 'turkey', 'yemen'],
    'asia_pacific': ['australia', 'bangladesh', 'cambodia', 'china', 'hong_kong', 'india', 'indonesia', 'japan', 'malaysia', 'myanmar', 'nepal', 'new_zealand', 'north_korea', 'pakistan', 'philippines', 'singapore', 'south_korea', 'sri_lanka', 'taiwan', 'thailand', 'vietnam'],
    'europe': ['austria', 'belgium', 'bosnia', 'bulgaria', 'croatia', 'czechia', 'denmark', 'estonia', 'finland', 'france', 'germany', 'greece', 'hungary', 'ireland', 'italy', 'latvia', 'lithuania', 'netherlands', 'norway', 'poland', 'portugal', 'romania', 'serbia', 'slovakia', 'slovenia', 'spain', 'sweden', 'switzerland', 'uk'],
    'africa': ['algeria', 'egypt', 'ethiopia', 'ghana', 'kenya', 'libya', 'morocco', 'nigeria', 'rwanda', 'senegal', 'somalia', 'south_africa', 'south_sudan', 'sudan', 'tanzania', 'tunisia', 'uganda', 'zambia', 'zimbabwe'],
    'americas': ['argentina', 'brazil', 'canada', 'chile', 'colombia', 'cuba', 'ecuador', 'mexico', 'peru', 'usa', 'uruguay', 'venezuela'],
    'caucasus_central_asia': ['afghanistan', 'armenia', 'azerbaijan', 'georgia', 'kazakhstan', 'kyrgyzstan', 'tajikistan', 'turkmenistan', 'uzbekistan']
};

// ==================== CONSTANTS ====================
const MAX_FEEDS = 50; // Feed limit

// ==================== HTML ESCAPING ====================
// Shared utility to prevent XSS when inserting user/feed data into innerHTML.
// Must be used for ALL signal fields rendered via innerHTML (title, description,
// source, author, location, source_group, etc.).
function escapeHtml(text) {
    if (!text) return '';
    return String(text)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

// Sanitize a URL for safe use in href/onclick attributes.
// Blocks javascript:, data:, vbscript: and other dangerous schemes.
// Returns '' for anything that isn't http:// or https://.
function safeUrl(url) {
    if (!url) return '';
    var s = String(url).trim();
    if (/^https?:\/\//i.test(s)) return s;
    return '';
}
