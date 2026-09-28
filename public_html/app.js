/**
 * SEO Auditor AI - Client JavaScript
 * Hostinger Shared Hosting Compatible & 100% Free SEO Audit
 */

// ── Theme & Dynamic Logo Management System ──────────────────────────────────
(function() {
    function updateThemeLogos() {
        const isLight = document.documentElement.getAttribute('data-theme') === 'light';

        // 1. Header brand logos
        const headerLogos = document.querySelectorAll('.brand-logo-img, .brand img');
        headerLogos.forEach(img => {
            if (!img.dataset.darkSrc) {
                img.dataset.darkSrc = img.getAttribute('src') || '/logo.png';
            }
            // Fallback safety: if logo fails to load (404/broken), revert to dark mode logo (/logo.png)
            img.onerror = function() {
                this.onerror = null;
                this.src = this.dataset.darkSrc || '/logo.png';
            };
            const targetSrc = isLight ? '/logo-light.png' : (img.dataset.darkSrc || '/logo.png');
            if (img.getAttribute('src') !== targetSrc) {
                img.src = targetSrc;
            }
        });

        // 2. Footer logos
        const footerLogos = document.querySelectorAll('.footer-logo-img, footer .footer-brand img, .footer-col img');
        footerLogos.forEach(img => {
            if (!img.dataset.darkSrc) {
                img.dataset.darkSrc = img.getAttribute('src') || '/footer-logo.png';
            }
            // Fallback safety: if light footer logo fails to load, fallback to dark footer logo or /logo.png
            img.onerror = function() {
                this.onerror = null;
                const fallbackSrc = this.dataset.darkSrc || '/footer-logo.png';
                this.src = fallbackSrc;
                this.onerror = function() {
                    this.onerror = null;
                    this.src = '/logo.png';
                };
            };
            const targetSrc = isLight ? '/footer-logo-light.png' : (img.dataset.darkSrc || '/footer-logo.png');
            if (img.getAttribute('src') !== targetSrc) {
                img.src = targetSrc;
            }
        });
    }

    window.updateThemeLogos = updateThemeLogos;

    const saved = localStorage.getItem('theme') || 'dark';
    if (saved === 'light') {
        document.documentElement.setAttribute('data-theme', 'light');
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', updateThemeLogos);
    } else {
        updateThemeLogos();
    }

    // Observe data-theme changes to synchronize logos immediately
    try {
        const observer = new MutationObserver(mutations => {
            for (const m of mutations) {
                if (m.type === 'attributes' && m.attributeName === 'data-theme') {
                    updateThemeLogos();
                    break;
                }
            }
        });
        observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    } catch (e) {
        // Fallback if MutationObserver unsupported
    }
})();


document.addEventListener('DOMContentLoaded', () => {
    // API Endpoint Auto-detection
    const API_BASE_URL = window.SEO_CONFIG?.API_BASE_URL || (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
        ? 'http://localhost:8000'
        : 'https://seo-auditor-api.onrender.com');

    // DOM Elements
    const auditForm = document.getElementById('auditForm');
    const targetUrlInput = document.getElementById('targetUrl');
    const maxPagesSelect = document.getElementById('maxPages');
    const submitBtn = document.getElementById('submitBtn');

    // Progress Elements
    const progressSection = document.getElementById('progressSection');
    const progressStepTitle = document.getElementById('progressStepTitle');
    const progressSubText = document.getElementById('progressSubText');
    const progressBarFill = document.getElementById('progressBarFill');
    const crawledCountEl = document.getElementById('crawledCount');
    const maxTargetCountEl = document.getElementById('maxTargetCount');
    const percentTextEl = document.getElementById('percentText');

    // Results Elements
    const resultsSection = document.getElementById('resultsSection');
    const auditedDomainPill = document.getElementById('auditedDomainPill');
    const scoreValueEl = document.getElementById('scoreValue');
    const gaugeFillEl = document.getElementById('gaugeFill');
    const scoreGradeTextEl = document.getElementById('scoreGradeText');

    const metricTotalCrawled = document.getElementById('metricTotalCrawled');
    const metricBrokenLinks = document.getElementById('metricBrokenLinks');
    const metricMissingTitles = document.getElementById('metricMissingTitles');
    const metricMissingMetas = document.getElementById('metricMissingMetas');
    const metricThinPages = document.getElementById('metricThinPages');
    const metricBrokenImages = document.getElementById('metricBrokenImages');
    const downloadBtn = document.getElementById('downloadBtn');

    // Preview Table Tabs
    const tabBtns = document.querySelectorAll('.tab-btn');
    const tabContents = document.querySelectorAll('.tab-content');

    tabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            tabBtns.forEach(b => b.classList.remove('active'));
            tabContents.forEach(c => c.classList.remove('active'));

            btn.classList.add('active');
            const targetTab = document.getElementById(btn.getAttribute('data-tab'));
            if (targetTab) targetTab.classList.add('active');
        });
    });

    let activeJobId = null;
    let pollInterval = null;

    // Form Submit Handler
    if (auditForm) {
        auditForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        let url = targetUrlInput.value.trim();
        if (!url) return;

        if (!url.startsWith('http://') && !url.startsWith('https://')) {
            url = 'https://' + url;
        }

        const maxPages = maxPagesSelect ? (parseInt(maxPagesSelect.value, 10) || 10000) : 10000;

        // UI Transition
        submitBtn.disabled = true;
        submitBtn.querySelector('span').innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Auditing...';
        
        resultsSection.classList.add('hidden');
        progressSection.classList.remove('hidden');

        // Reset progress UI
        progressBarFill.style.width = '5%';
        percentTextEl.textContent = '5%';
        crawledCountEl.textContent = '0';
        maxTargetCountEl.textContent = maxPages;
        progressStepTitle.textContent = 'Initializing Audit Engine...';
        progressSubText.textContent = `Connecting to ${url}...`;

        try {
            const response = await fetch(`${API_BASE_URL}/api/audit`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url: url, max_pages: maxPages })
            });

            if (!response.ok) {
                const errData = await response.json();
                throw new Error(errData.detail || 'Failed to start audit job');
            }

            const data = await response.json();
            activeJobId = data.job_id;

            // Start Polling
            startPollingStatus(activeJobId, url);

        } catch (error) {
            alert(`Error: ${error.message}. Please make sure the Python API server is running.`);
        }
    });
    }

    // Polling Loop
    function startPollingStatus(jobId, targetUrl) {
        if (pollInterval) clearInterval(pollInterval);

        pollInterval = setInterval(async () => {
            try {
                const res = await fetch(`${API_BASE_URL}/api/status/${jobId}`);
                if (!res.ok) return;

                const job = await res.json();

                // Update Progress UI
                const pct = job.percent || 5;
                if (progressBarFill) progressBarFill.style.width = `${pct}%`;
                if (percentTextEl) percentTextEl.textContent = `${pct}%`;
                if (crawledCountEl) crawledCountEl.textContent = job.pages_crawled || 0;
                if (progressStepTitle) progressStepTitle.textContent = job.step || 'Crawling site...';

                if (job.status === 'completed') {
                    clearInterval(pollInterval);
                    renderResults(job, targetUrl);
                } else if (job.status === 'failed') {
                    clearInterval(pollInterval);
                    alert(`Audit Failed: ${job.error || 'Unknown error'}`);
                    resetForm();
                }

            } catch (err) {
                console.error('Polling error:', err);
            }
        }, 1000);
    }

    // Render Audit Results Dashboard & Live Preview Tables
    function renderResults(job, targetUrl) {
        if (progressSection) progressSection.classList.add('hidden');
        if (resultsSection) resultsSection.classList.remove('hidden');

        if (auditedDomainPill) {
            try {
                const domain = new URL(targetUrl).hostname;
                auditedDomainPill.textContent = domain;
            } catch {
                auditedDomainPill.textContent = targetUrl;
            }
        }

        const metrics = job.summary_metrics || {};
        const score = job.health_score || 85;

        // Animate score counter
        if (scoreValueEl) animateCounter(scoreValueEl, 0, score, 1000);

        // Update SVG circle gauge
        if (gaugeFillEl) {
            gaugeFillEl.setAttribute('stroke-dasharray', `${score}, 100`);
            if (score >= 85) {
                gaugeFillEl.style.stroke = '#10b981';
                if (scoreGradeTextEl) {
                    scoreGradeTextEl.textContent = 'Excellent Health';
                    scoreGradeTextEl.style.color = '#10b981';
                }
            } else if (score >= 65) {
                gaugeFillEl.style.stroke = '#f59e0b';
                if (scoreGradeTextEl) {
                    scoreGradeTextEl.textContent = 'Moderate Issues Found';
                    scoreGradeTextEl.style.color = '#f59e0b';
                }
            } else {
                gaugeFillEl.style.stroke = '#f43f5e';
                if (scoreGradeTextEl) {
                    scoreGradeTextEl.textContent = 'Critical Action Needed';
                    scoreGradeTextEl.style.color = '#f43f5e';
                }
            }
        }

        // Metrics Counters
        if (metricTotalCrawled) metricTotalCrawled.textContent = metrics.total_crawled || 0;
        if (metricBrokenLinks) metricBrokenLinks.textContent = metrics.broken_links || 0;
        if (metricMissingTitles) metricMissingTitles.textContent = metrics.missing_titles || 0;
        if (metricMissingMetas) metricMissingMetas.textContent = metrics.missing_descriptions || 0;
        if (metricThinPages) metricThinPages.textContent = metrics.thin_content_pages || 0;
        if (metricBrokenImages) metricBrokenImages.textContent = metrics.broken_images || 0;

        // Render Preview Data Tables
        const preview = job.audit_preview || {};
        populatePagesTable(preview.pages || []);
        populateBrokenTable(preview.broken_links || []);
        populateDuplicateTable(preview.duplicate_titles || []);

        resetForm();

        // Smooth scroll to results
        if (resultsSection) resultsSection.scrollIntoView({ behavior: 'smooth' });
    }

    // Download Handler - Direct Instant Free Download
    if (downloadBtn) {
        downloadBtn.addEventListener('click', () => {
            if (!activeJobId) return;
            triggerDownload();
        });
    }

    function triggerDownload() {
        if (!activeJobId) return;
        const downloadUrl = `${API_BASE_URL}/api/download/${activeJobId}`;
        window.location.href = downloadUrl;
    }

    // Helper: Reset Form UI
    function resetForm() {
        if (submitBtn) {
            submitBtn.disabled = false;
            const span = submitBtn.querySelector('span');
            if (span) span.innerHTML = 'Audit';
        }
    }

    // Helper: Animate Counter
    function animateCounter(el, start, end, duration) {
        let startTime = null;
        function step(timestamp) {
            if (!startTime) startTime = timestamp;
            const progress = Math.min((timestamp - startTime) / duration, 1);
            el.textContent = Math.floor(progress * (end - start) + start);
            if (progress < 1) {
                window.requestAnimationFrame(step);
            }
        }
        window.requestAnimationFrame(step);
    }

    // Table Population Helpers
    function populatePagesTable(pages) {
        const tbody = document.getElementById('pagesTableBody');
        const countEl = document.getElementById('previewPageCount');
        if (countEl) countEl.textContent = pages.length;
        if (!tbody) return;

        if (!pages.length) {
            tbody.innerHTML = '<tr><td colspan="5" style="text-align:center; color:#94a3b8; padding:20px;">No pages crawled yet.</td></tr>';
            return;
        }

        tbody.innerHTML = pages.map(p => `
            <tr>
                <td><a href="${escapeHtml(p.url)}" target="_blank" rel="noopener" style="color:#38bdf8; text-decoration:none;">${escapeHtml(p.url)}</a></td>
                <td><span class="status-badge ${p.status >= 400 ? 'status-404' : p.status >= 300 ? 'status-301' : 'status-200'}">${p.status || 'N/A'}</span></td>
                <td>${escapeHtml(p.title)}</td>
                <td>${escapeHtml(p.meta_description)}</td>
                <td><strong>${p.word_count}</strong> words</td>
            </tr>
        `).join('');
    }

    function populateBrokenTable(broken) {
        const tbody = document.getElementById('brokenTableBody');
        const countEl = document.getElementById('previewBrokenCount');
        if (countEl) countEl.textContent = broken.length;
        if (!tbody) return;

        if (!broken.length) {
            tbody.innerHTML = '<tr><td colspan="4" style="text-align:center; color:#34d399; padding:20px;">No broken links detected! Clean site 🎉</td></tr>';
            return;
        }

        tbody.innerHTML = broken.map(b => `
            <tr>
                <td><a href="${escapeHtml(b.source)}" target="_blank" rel="noopener" style="color:#38bdf8; text-decoration:none;">${escapeHtml(b.source)}</a></td>
                <td style="color:#fb7185;">${escapeHtml(b.target)}</td>
                <td><span class="status-badge status-404">${escapeHtml(b.status)}</span></td>
                <td>${escapeHtml(b.anchor)}</td>
            </tr>
        `).join('');
    }

    function populateDuplicateTable(duplicates) {
        const tbody = document.getElementById('duplicateTableBody');
        const countEl = document.getElementById('previewDuplicateCount');
        if (countEl) countEl.textContent = duplicates.length;
        if (!tbody) return;

        if (!duplicates.length) {
            tbody.innerHTML = '<tr><td colspan="3" style="text-align:center; color:#34d399; padding:20px;">No duplicate title tags found. Great SEO!</td></tr>';
            return;
        }

        tbody.innerHTML = duplicates.map(d => `
            <tr>
                <td><strong>${escapeHtml(d.title)}</strong></td>
                <td>${escapeHtml(d.urls)}</td>
                <td><span class="status-badge status-301">${d.count} pages</span></td>
            </tr>
        `).join('');
    }

    // FAQ Accordion Handlers
    document.querySelectorAll('.faq-question').forEach(item => {
        item.addEventListener('click', () => {
            const parent = item.parentElement;
            parent.classList.toggle('active');
        });
    });

    // Blog Page Handler
    const blogGrid = document.getElementById('blogGrid');
    if (blogGrid) {
        loadBlogPosts();
    }

    async function loadBlogPosts() {
        try {
            const res = await fetch(`${API_BASE_URL}/api/posts`);
            if (!res.ok) throw new Error('Failed to load posts');
            const posts = await res.json();
            renderBlogGrid(posts);

            // Filter Buttons
            document.querySelectorAll('.filter-btn').forEach(btn => {
                btn.addEventListener('click', () => {
                    document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
                    btn.classList.add('active');
                    const cat = btn.getAttribute('data-cat');
                    if (cat === 'all') {
                        renderBlogGrid(posts);
                    } else {
                        renderBlogGrid(posts.filter(p => p.category === cat));
                    }
                });
            });
        } catch (err) {
            blogGrid.innerHTML = `<div class="text-center py-6" style="color:#fb7185;">Failed to load blog posts.</div>`;
        }
    }

    function renderBlogGrid(posts) {
        if (!posts.length) {
            blogGrid.innerHTML = `<div class="text-center py-6" style="color:#94a3b8;">No blog guides found in this category.</div>`;
            return;
        }
        blogGrid.innerHTML = posts.map(p => `
            <div class="glass-card blog-card">
                <div>
                    <div class="blog-card-meta">
                        <span class="category-badge">${escapeHtml(p.category)}</span>
                        <span class="read-time"><i class="fa-regular fa-clock"></i> ${escapeHtml(p.read_time)}</span>
                    </div>
                    <h3 class="blog-card-title"><a href="/blog/${escapeHtml(p.slug)}">${escapeHtml(p.title)}</a></h3>
                    <p class="blog-card-summary">${escapeHtml(p.summary)}</p>
                </div>
                <div class="blog-card-footer">
                    <span><i class="fa-regular fa-calendar"></i> ${escapeHtml(p.date)}</span>
                    <a href="/blog/${escapeHtml(p.slug)}" class="btn btn-sm btn-outline">Read Guide <i class="fa-solid fa-arrow-right"></i></a>
                </div>
            </div>
        `).join('');
    }

    // Article Reader Page Handler
    const articleBody = document.getElementById('articleBody');
    if (articleBody) {
        const pathParts = window.location.pathname.split('/');
        const slug = pathParts[pathParts.length - 1] || pathParts[pathParts.length - 2];
        if (slug && slug !== 'blog' && slug !== 'blog-post.html') {
            loadArticle(slug);
        }
    }

    async function loadArticle(slug) {
        try {
            const res = await fetch(`${API_BASE_URL}/api/posts/${slug}`);
            if (!res.ok) throw new Error('Article not found');
            const post = await res.json();
            
            document.title = `${post.title} | SEO Error Auditor`;
            const metaDesc = document.getElementById('articleMetaDesc');
            if (metaDesc) metaDesc.content = post.summary || post.title;

            document.getElementById('articleTitle').textContent = post.title;
            document.getElementById('articleCategory').textContent = post.category;
            document.getElementById('articleAuthor').textContent = post.author || 'SEO Error Auditor Team';
            document.getElementById('articleDate').textContent = post.date;
            document.getElementById('articleReadTime').textContent = post.read_time;
            
            const summaryBox = document.getElementById('articleSummary');
            if (summaryBox) summaryBox.textContent = post.summary;

            articleBody.innerHTML = post.content;
        } catch (err) {
            articleBody.innerHTML = `<div class="text-center py-6" style="color:#fb7185;">Article not found. <a href="/blog" style="color:#38bdf8;">Return to Blog</a></div>`;
        }
    }

    // Admin Publisher Panel Handler
    const adminPostForm = document.getElementById('adminPostForm');
    const adminPostsTableBody = document.getElementById('adminPostsTableBody');
    if (adminPostForm || adminPostsTableBody) {
        loadAdminPosts();

        if (adminPostForm) {
            adminPostForm.addEventListener('submit', async (e) => {
                e.preventDefault();
                const publishBtn = document.getElementById('publishBtn');
                publishBtn.disabled = true;
                publishBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Publishing...';

                const postData = {
                    title: document.getElementById('postTitle').value.trim(),
                    category: document.getElementById('postCategory').value,
                    author: document.getElementById('postAuthor').value.trim(),
                    read_time: document.getElementById('postReadTime').value.trim(),
                    summary: document.getElementById('postSummary').value.trim(),
                    content: document.getElementById('postContent').value.trim()
                };

                try {
                    const res = await fetch(`${API_BASE_URL}/api/posts`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(postData)
                    });
                    if (!res.ok) throw new Error('Failed to publish post');
                    const data = await res.json();
                    
                    showAdminToast(`Success! Published article: "${data.post.title}"`);
                    adminPostForm.reset();
                    loadAdminPosts();
                } catch (err) {
                    showAdminToast('Error publishing article. Please try again.', true);
                } finally {
                    publishBtn.disabled = false;
                    publishBtn.innerHTML = '<i class="fa-solid fa-paper-plane"></i> Publish Article Live';
                }
            });
        }
    }

    async function loadAdminPosts() {
        if (!adminPostsTableBody) return;
        try {
            const res = await fetch(`${API_BASE_URL}/api/posts`);
            const posts = await res.json();
            const countEl = document.getElementById('adminArticleCount');
            if (countEl) countEl.textContent = posts.length;

            if (!posts.length) {
                adminPostsTableBody.innerHTML = '<tr><td colspan="4" class="text-center py-4" style="color:#94a3b8;">No articles published yet.</td></tr>';
                return;
            }

            adminPostsTableBody.innerHTML = posts.map(p => `
                <tr>
                    <td>
                        <strong>${escapeHtml(p.title)}</strong><br>
                        <a href="/blog/${escapeHtml(p.slug)}" target="_blank" style="color:#38bdf8; font-size:0.85rem;">/blog/${escapeHtml(p.slug)}</a>
                    </td>
                    <td><span class="category-badge">${escapeHtml(p.category)}</span></td>
                    <td>${escapeHtml(p.date)}</td>
                    <td>
                        <button class="btn btn-sm btn-outline text-rose delete-post-btn" data-slug="${escapeHtml(p.slug)}">
                            <i class="fa-solid fa-trash"></i> Delete
                        </button>
                    </td>
                </tr>
            `).join('');

            // Attach Delete Handlers
            document.querySelectorAll('.delete-post-btn').forEach(btn => {
                btn.addEventListener('click', async () => {
                    const slug = btn.getAttribute('data-slug');
                    if (!confirm(`Are you sure you want to delete article "${slug}"?`)) return;
                    try {
                        const res = await fetch(`${API_BASE_URL}/api/posts/${slug}`, { method: 'DELETE' });
                        if (res.ok) {
                            showAdminToast(`Deleted post ${slug}`);
                            loadAdminPosts();
                        }
                    } catch (e) {
                        showAdminToast('Failed to delete post.', true);
                    }
                });
            });

        } catch (err) {
            adminPostsTableBody.innerHTML = '<tr><td colspan="4" class="text-center py-4" style="color:#fb7185;">Failed to load posts.</td></tr>';
        }
    }

    function showAdminToast(msg, isError = false) {
        const toast = document.getElementById('adminToast');
        if (!toast) return;
        toast.textContent = msg;
        toast.style.background = isError ? '#ef4444' : '#10b981';
        toast.classList.remove('hidden');
        setTimeout(() => toast.classList.add('hidden'), 4000);
    }

    function escapeHtml(str) {
        if (!str) return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }
});
// ── Freemium Model ──────────────────────────────────────────────────────────
(function initFreemium() {
    // Only run on tool pages
    if (window.location.pathname === '/' || window.location.pathname.startsWith('/admin') || window.location.pathname.startsWith('/blog') || window.location.pathname === '/about.html' || window.location.pathname === '/contact.html' || window.location.pathname === '/privacy.html' || window.location.pathname === '/terms.html') return;

    const token = localStorage.getItem('user_token');
    
    // Inject Modal HTML
    const modalHtml = `
    <div id="freemiumModal" style="display:none; position:fixed; inset:0; background:rgba(15,23,42,0.85); z-index:99999; align-items:center; justify-content:center; backdrop-filter:blur(5px);">
        <div style="background:#1e293b; border:1px solid rgba(255,255,255,0.1); border-radius:16px; padding:2rem; max-width:400px; width:90%; text-align:center; box-shadow:0 20px 40px rgba(0,0,0,0.5);">
            <div style="font-size:3rem; color:#38bdf8; margin-bottom:1rem;"><i class="fa-solid fa-lock"></i></div>
            <h3 style="font-family:'Outfit',sans-serif; color:#fff; font-size:1.5rem; margin-bottom:0.5rem;">Free Trial Limit Reached</h3>
            <p style="color:#94a3b8; font-size:0.95rem; margin-bottom:1.5rem;">You've used your 1 free tool generation. Create a free account to unlock unlimited access forever!</p>
            
            <div id="authTabs" style="display:flex; margin-bottom:1.5rem; border-bottom:1px solid rgba(255,255,255,0.1);">
                <button onclick="document.getElementById('loginFormView').style.display='none'; document.getElementById('registerFormView').style.display='block';" style="flex:1; background:none; border:none; color:#38bdf8; padding:0.5rem; cursor:pointer; font-weight:600;">Register</button>
                <button onclick="document.getElementById('registerFormView').style.display='none'; document.getElementById('loginFormView').style.display='block';" style="flex:1; background:none; border:none; color:#94a3b8; padding:0.5rem; cursor:pointer;">Login</button>
            </div>

            <form id="registerFormView" onsubmit="handleUserAuth(event, 'register')">
                <input type="email" id="regEmail" placeholder="Email Address" required style="width:100%; padding:0.8rem; border-radius:8px; border:1px solid rgba(255,255,255,0.1); background:rgba(0,0,0,0.2); color:#fff; margin-bottom:1rem;">
                <input type="password" id="regPass" placeholder="Password" required style="width:100%; padding:0.8rem; border-radius:8px; border:1px solid rgba(255,255,255,0.1); background:rgba(0,0,0,0.2); color:#fff; margin-bottom:1rem;">
                <button type="submit" style="width:100%; background:#38bdf8; color:#0f172a; border:none; padding:0.8rem; border-radius:8px; font-weight:700; cursor:pointer; font-family:'Outfit',sans-serif;">Create Free Account</button>
            </form>

            <form id="loginFormView" style="display:none;" onsubmit="handleUserAuth(event, 'login')">
                <input type="email" id="logEmail" placeholder="Email Address" required style="width:100%; padding:0.8rem; border-radius:8px; border:1px solid rgba(255,255,255,0.1); background:rgba(0,0,0,0.2); color:#fff; margin-bottom:1rem;">
                <input type="password" id="logPass" placeholder="Password" required style="width:100%; padding:0.8rem; border-radius:8px; border:1px solid rgba(255,255,255,0.1); background:rgba(0,0,0,0.2); color:#fff; margin-bottom:1rem;">
                <button type="submit" style="width:100%; background:#38bdf8; color:#0f172a; border:none; padding:0.8rem; border-radius:8px; font-weight:700; cursor:pointer; font-family:'Outfit',sans-serif;">Login</button>
            </form>
            <p id="authErrorMsg" style="color:#ef4444; font-size:0.85rem; margin-top:1rem; display:none;"></p>
        </div>
    </div>
    `;
    document.body.insertAdjacentHTML('beforeend', modalHtml);

    window.handleUserAuth = async function(e, action) {
        e.preventDefault();
        const email = action === 'register' ? document.getElementById('regEmail').value : document.getElementById('logEmail').value;
        const pass = action === 'register' ? document.getElementById('regPass').value : document.getElementById('logPass').value;
        const errorMsg = document.getElementById('authErrorMsg');
        
        try {
            const res = await fetch(`/api/users/${action}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email: email, password: pass })
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Authentication failed');
            
            if (action === 'register') {
                // Auto login after register
                window.handleUserAuth({preventDefault:()=>{}}, 'login');
            } else {
                localStorage.setItem('user_token', data.access_token);
                document.getElementById('freemiumModal').style.display = 'none';
                alert('Success! You now have unlimited access.');
                // Re-trigger the blocked action if needed, or just let them continue
            }
        } catch(err) {
            errorMsg.textContent = err.message;
            errorMsg.style.display = 'block';
        }
    };

    function checkFreemium(e) {
        if (localStorage.getItem('user_token')) return true; // Has account
        let count = parseInt(localStorage.getItem('tool_usage_count') || '0');
        if (count >= 1) {
            e.preventDefault();
            e.stopPropagation();
            document.getElementById('freemiumModal').style.display = 'flex';
            return false;
        }
        localStorage.setItem('tool_usage_count', count + 1);
        return true;
    }

    // Intercept Copy Buttons and Forms
    setTimeout(() => {
        const copyBtns = document.querySelectorAll('.ide-btn-copy, #copyXmlBtn, #btnCopyHtml');
        copyBtns.forEach(btn => {
            const clone = btn.cloneNode(true);
            btn.parentNode.replaceChild(clone, btn);
            clone.addEventListener('click', (e) => {
                if (checkFreemium(e)) {
                    // It passed, we just copy manually since we removed original listener
                    const editorContent = document.querySelector('.ide-editor-content, .code-editor-content, .xml-editor-content');
                    if(editorContent) {
                        navigator.clipboard.writeText(editorContent.textContent);
                        clone.innerHTML = '<i class="fa-solid fa-check text-emerald"></i> Copied!';
                        setTimeout(() => { clone.innerHTML = '<i class="fa-solid fa-copy"></i> Copy Code'; }, 2000);
                    }
                }
            });
        });
        
        const auditForm = document.getElementById('auditForm');
        if (auditForm) {
            auditForm.addEventListener('submit', (e) => {
                if (!checkFreemium(e)) {
                    e.stopImmediatePropagation();
                }
            }, true);
        }
    }, 1000); // Wait for other scripts to bind
})();


// ── Massive UX Fixes: Mobile Menu, Multiple Theme Toggles, Enquiry Popup ──

document.addEventListener('DOMContentLoaded', () => {
    // 1. Mobile Menu Toggle
    const mobileBtn = document.getElementById('mobileMenuBtn');
    const navLinks = document.getElementById('navLinks');
    if (mobileBtn && navLinks) {
        mobileBtn.addEventListener('click', () => {
            navLinks.classList.toggle('show');
            const icon = mobileBtn.querySelector('i');
            if (navLinks.classList.contains('show')) {
                icon.classList.remove('fa-bars');
                icon.classList.add('fa-xmark');
            } else {
                icon.classList.remove('fa-xmark');
                icon.classList.add('fa-bars');
            }
        });
    }

    // Dropdown toggle (click for mobile; hover is handled via CSS :hover)
    // Click also works on desktop for keyboard/accessibility users
    const dropdownToggles = document.querySelectorAll('.nav-dropdown > .dropdown-toggle');
    dropdownToggles.forEach(toggle => {
        toggle.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            const dropdown = toggle.parentElement;
            const isActive = dropdown.classList.contains('active');
            // Close all others first
            document.querySelectorAll('.nav-dropdown.active').forEach(d => {
                d.classList.remove('active');
                const t = d.querySelector('.dropdown-toggle');
                if (t) t.setAttribute('aria-expanded', 'false');
            });
            // Toggle current
            if (!isActive) {
                dropdown.classList.add('active');
                toggle.setAttribute('aria-expanded', 'true');
            }
        });
    });

    // Close dropdown on outside click
    document.addEventListener('click', (e) => {
        if (!e.target.closest('.nav-dropdown')) {
            document.querySelectorAll('.nav-dropdown.active').forEach(d => {
                d.classList.remove('active');
                const t = d.querySelector('.dropdown-toggle');
                if (t) t.setAttribute('aria-expanded', 'false');
            });
        }
    });

    // Close dropdown on ESC key
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            document.querySelectorAll('.nav-dropdown.active').forEach(d => {
                d.classList.remove('active');
                const t = d.querySelector('.dropdown-toggle');
                if (t) t.setAttribute('aria-expanded', 'false');
            });
        }
    });


    // 2. Fix Theme Toggle for both Desktop and Mobile buttons
    const themeBtns = document.querySelectorAll('.theme-toggle-btn');
    const updateThemeBtns = () => {
        const isLight = document.documentElement.getAttribute('data-theme') === 'light';
        themeBtns.forEach(btn => {
            btn.innerHTML = isLight ? '<i class="fa-solid fa-sun"></i>' : '<i class="fa-solid fa-moon"></i>';
            btn.style.color = isLight ? '#f59e0b' : '#94a3b8';
        });
    };
    
    // We already have a theme toggle in the old code, but this handles ALL instances
    updateThemeBtns();
    if (typeof window.updateThemeLogos === 'function') {
        window.updateThemeLogos();
    }

    themeBtns.forEach(btn => {
        // Remove old listeners by cloning (if any)
        const newBtn = btn.cloneNode(true);
        btn.parentNode.replaceChild(newBtn, btn);
        
        newBtn.addEventListener('click', () => {
            const isLight = document.documentElement.getAttribute('data-theme') === 'light';
            if (isLight) {
                document.documentElement.removeAttribute('data-theme');
                localStorage.setItem('theme', 'dark');
            } else {
                document.documentElement.setAttribute('data-theme', 'light');
                localStorage.setItem('theme', 'light');
            }
            // Update all buttons again
            const allBtns = document.querySelectorAll('.theme-toggle-btn');
            const newIsLight = !isLight;
            allBtns.forEach(b => {
                b.innerHTML = newIsLight ? '<i class="fa-solid fa-sun"></i>' : '<i class="fa-solid fa-moon"></i>';
                b.style.color = newIsLight ? '#f59e0b' : '#94a3b8';
            });
            if (typeof window.updateThemeLogos === 'function') {
                window.updateThemeLogos();
            }
        });
    });

    // 3. Enquiry Popup Logic
    const popupOverlay = document.getElementById('enquiryPopupOverlay');
    const popupCloseBtn = document.getElementById('popupCloseBtn');
    const enquiryForm = document.getElementById('enquiryFormPopup');
    const popupMessage = document.getElementById('popupFormMessage');

    if (popupOverlay) {
        // Check session storage
        const hasClosedOrSubmitted = sessionStorage.getItem('enquiry_action_taken');
        
        if (!hasClosedOrSubmitted) {
            // Show after 5 seconds
            setTimeout(() => {
                popupOverlay.classList.add('show');
            }, 5000);
        }

        const closePopup = () => {
            popupOverlay.classList.remove('show');
            sessionStorage.setItem('enquiry_action_taken', 'true');
        };

        if (popupCloseBtn) {
            popupCloseBtn.addEventListener('click', closePopup);
        }

        // Close on outside click
        popupOverlay.addEventListener('click', (e) => {
            if (e.target === popupOverlay) {
                closePopup();
            }
        });

        // Close on ESC
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && popupOverlay.classList.contains('show')) {
                closePopup();
            }
        });

        // Handle Form Submission
        if (enquiryForm) {
            enquiryForm.addEventListener('submit', async (e) => {
                e.preventDefault();
                const name = document.getElementById('popupName').value;
                const email = document.getElementById('popupEmail').value;
                const mobile = document.getElementById('popupMobile').value;
                const submitBtn = enquiryForm.querySelector('button[type="submit"]');

                submitBtn.disabled = true;
                submitBtn.innerText = "Sending...";
                popupMessage.innerText = "";

                try {
                    const API_BASE = window.SEO_CONFIG?.API_BASE_URL || "http://localhost:8000";
                    const res = await fetch(`${API_BASE}/api/enquiry`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ name, email, mobile })
                    });
                    
                    if (res.ok) {
                        popupMessage.style.color = "#10b981"; // Emerald
                        popupMessage.innerText = "Thank you! Your enquiry has been submitted successfully.";
                        sessionStorage.setItem('enquiry_action_taken', 'true');
                        setTimeout(() => closePopup(), 2500);
                    } else {
                        throw new Error('Server error');
                    }
                } catch (err) {
                    popupMessage.style.color = "#ef4444"; // Red
                    popupMessage.innerText = "Failed to send enquiry. Please try again.";
                    submitBtn.disabled = false;
                    submitBtn.innerText = "Send Enquiry";
                }
            });
        }
    }
});
