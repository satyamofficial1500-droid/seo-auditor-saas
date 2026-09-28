/**
 * SEO Error Auditor — Global Config
 * Change API_BASE_URL here instead of hunting through app.js
 */
window.SEO_CONFIG = {
  // When running locally both frontend & backend are on same origin (port 8000)
  // On production Hostinger+Render split hosting, set this to your Render URL
  API_BASE_URL: (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1')
    ? 'http://localhost:8000'
    : 'https://seo-auditor-api.onrender.com',

  SITE_URL: 'https://seoerrorauditor.com',
  SITE_NAME: 'SEO Error Auditor',

  // GA4 — Replace with your actual Measurement ID after getting from Google Analytics
  GA4_MEASUREMENT_ID: 'G-XXXXXXXXXX',

  // Google Search Console verification — Replace with actual content value from GSC
  GSC_VERIFICATION: 'YOUR_GSC_VERIFICATION_CODE_HERE',
};
