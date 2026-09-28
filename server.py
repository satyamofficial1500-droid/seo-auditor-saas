#!/usr/bin/env python3
"""FastAPI Backend Server for SEO Error Auditor — Production-Grade.

Phase 1-19 SEO + AEO + GEO + Security + SSR upgrade.
Security:  JWT-based admin auth, per-IP rate limiting, HTML sanitization (bleach).
SEO:       Blog SSR, canonical, robots.txt, sitemap with lastmod, security headers.
APIs:      /api/contact, /rss.xml, PUT /api/posts/{slug}, /blog/category/{cat}.
"""

import os
import re
import json
import uuid
import time
import sys
import html as html_module
import logging
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List
from urllib.parse import urlparse

class SafeStreamHandler(logging.StreamHandler):
    def emit(self, record):
        try:
            super().emit(record)
        except Exception:
            pass

logging.basicConfig(level=logging.INFO, handlers=[SafeStreamHandler()])
logging.getLogger("urllib3").setLevel(logging.CRITICAL)
logging.getLogger("requests").setLevel(logging.CRITICAL)

from fastapi import FastAPI, BackgroundTasks, HTTPException, Depends, Request, status, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, PlainTextResponse, Response, JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

try:
    from jose import JWTError, jwt
    from passlib.context import CryptContext
    JOSE_AVAILABLE = True
except ImportError:
    JOSE_AVAILABLE = False
    logging.warning("python-jose / passlib not available -- auth disabled")

try:
    import bleach
    BLEACH_AVAILABLE = True
except ImportError:
    BLEACH_AVAILABLE = False
    logging.warning("bleach not available -- HTML sanitization disabled")

from seo_site_auditor import (
    normalise_url, crawl_site, find_broken_links,
    find_duplicates, parse_sitemap, generate_excel_report
)

try:
    from sitemap_engine.crawler.crawler import WebCrawler
    from sitemap_engine.sitemap.generator import SitemapGenerator
except Exception as e:
    logging.warning(f"Could not import sitemap_engine: {e}")

# ─────────────────────────────────────────────────────────────────────────────
# ENVIRONMENT / CONFIG
# ─────────────────────────────────────────────────────────────────────────────
SITE_DOMAIN   = os.environ.get("PUBLIC_SITE_URL", "https://seoerrorauditor.com")
SITE_DOMAIN   = SITE_DOMAIN.rstrip("/")
GA_ID         = os.environ.get("GA_MEASUREMENT_ID", "")   # e.g. G-XXXXXXXXXX
GSC_TOKEN     = os.environ.get("GSC_VERIFICATION", "")    # Google Search Console HTML tag token

SECRET_KEY    = os.environ.get("JWT_SECRET_KEY", "CHANGE_THIS_TO_A_RANDOM_64_CHAR_SECRET_IN_PRODUCTION")
ALGORITHM     = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 480

ADMIN_USERNAME       = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD_PLAIN = os.environ.get("ADMIN_PASSWORD", "seoauditor2026")

# Allowed CORS origins – restrict in production via env
_cors_env = os.environ.get("ALLOWED_ORIGINS", "")
ALLOWED_ORIGINS = [o.strip() for o in _cors_env.split(",") if o.strip()] if _cors_env else [
    "https://seoerrorauditor.com",
    "https://www.seoerrorauditor.com",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]

if JOSE_AVAILABLE:
    pwd_context   = CryptContext(schemes=["bcrypt"], deprecated="auto")
    oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/admin/token", auto_error=False)
else:
    oauth2_scheme = None

limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="SEO Auditor API",
    description="REST API for automated website SEO auditing and report generation",
    version="3.0.0",
    docs_url=None,   # hide Swagger from public
    redoc_url=None,
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# GZip all responses ≥ 1 KB
app.add_middleware(GZipMiddleware, minimum_size=1024)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

PUBLIC_DIR    = Path(__file__).parent / "public_html"
DOWNLOADS_DIR = Path(__file__).parent / "downloads"
UPLOADS_DIR   = Path(__file__).parent / "uploads"
DATA_DIR      = Path(__file__).parent / "data"

try:
    DOWNLOADS_DIR.mkdir(exist_ok=True)
    UPLOADS_DIR.mkdir(exist_ok=True)
    DATA_DIR.mkdir(exist_ok=True)
except (PermissionError, OSError):
    pass # Vercel read-only filesystem bypass

POSTS_FILE    = DATA_DIR / "posts.json"
CONTACTS_FILE = DATA_DIR / "contacts.json"
USERS_FILE    = DATA_DIR / "users.json"

jobs: dict = {}
sitemap_jobs: dict = {}

# ─────────────────────────────────────────────────────────────────────────────
# SECURITY HEADERS MIDDLEWARE
# ─────────────────────────────────────────────────────────────────────────────
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path
    # Apply X-Robots-Tag: noindex on API and admin paths
    if path.startswith("/api/") or path.startswith("/admin"):
        response.headers["X-Robots-Tag"] = "noindex, nofollow"
    # Security headers on all responses
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    # HSTS (only meaningful over HTTPS)
    response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response

# ─────────────────────────────────────────────────────────────────────────────
# AUTH HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def verify_password(plain: str) -> bool:
    return plain == ADMIN_PASSWORD_PLAIN

def create_access_token(data: dict, expires_delta: timedelta = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    if JOSE_AVAILABLE:
        return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return "NOAUTH"

def get_oauth2_scheme():
    if JOSE_AVAILABLE:
        return OAuth2PasswordBearer(tokenUrl="/api/admin/token", auto_error=False)
    return lambda: "NOAUTH"

_oauth2 = get_oauth2_scheme()

async def get_current_admin(token: str = Depends(_oauth2)):
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated. Please login at /admin/login.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not JOSE_AVAILABLE:
        return "admin"
    if not token:
        raise credentials_exc
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exc
    except JWTError:
        raise credentials_exc
    return username

# ─────────────────────────────────────────────────────────────────────────────
# HTML SANITIZATION
# ─────────────────────────────────────────────────────────────────────────────
ALLOWED_TAGS = [
    "a","abbr","b","blockquote","br","code","dd","del","div","dl","dt",
    "em","figure","figcaption","h1","h2","h3","h4","h5","h6","hr","i",
    "img","ins","kbd","li","mark","ol","p","pre","s","section","small",
    "span","strong","sub","sup","table","tbody","td","tfoot","th","thead",
    "tr","u","ul","var","article","aside","header","footer"
]
ALLOWED_ATTRS = {
    "*":   ["class","id","style"],
    "a":   ["href","title","target","rel"],
    "img": ["src","alt","width","height","loading"],
    "td":  ["colspan","rowspan"],
    "th":  ["colspan","rowspan","scope"],
}

def sanitize_html(html_content: str) -> str:
    if not BLEACH_AVAILABLE:
        return html_content
    return bleach.clean(html_content, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRS, strip=True)

# ─────────────────────────────────────────────────────────────────────────────
# DATA MODELS
# ─────────────────────────────────────────────────────────────────────────────
class AuditRequest(BaseModel):
    url: str
    max_pages: Optional[int] = 10000
    email: Optional[str] = None

class BlogPostRequest(BaseModel):
    title: str
    category: Optional[str] = "Technical SEO"
    summary: Optional[str] = ""
    content: str
    author: Optional[str] = "SEO Error Auditor Team"
    read_time: Optional[str] = "5 min read"
    status: Optional[str] = "published"
    featured_image_url: Optional[str] = ""
    seo_title: Optional[str] = ""
    seo_description: Optional[str] = ""
    canonical_url: Optional[str] = ""
    tags: Optional[List[str]] = []
    schema_markup: Optional[str] = ""

class EnquiryRequest(BaseModel):
    name: str
    email: str
    mobile: str

class ContactRequest(BaseModel):
    name: str
    email: str
    subject: str
    message: str

class SitemapGenRequest(BaseModel):
    url: str
    max_pages: Optional[int] = 10000

class AdminLoginRequest(BaseModel):
    username: str
    password: str

class UserRegisterRequest(BaseModel):
    email: str
    password: str

class UserLoginRequest(BaseModel):
    email: str
    password: str

# ─────────────────────────────────────────────────────────────────────────────
# DATA HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def load_posts() -> list:
    if not POSTS_FILE.exists():
        return []
    try:
        with open(POSTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def save_posts(posts: list):
    with open(POSTS_FILE, "w", encoding="utf-8") as f:
        json.dump(posts, f, indent=2, ensure_ascii=False)

def make_slug(title: str, existing_posts: list = None, exclude_slug: str = None) -> str:
    raw  = re.sub(r"[^a-zA-Z0-9]+", "-", title.strip().lower()).strip("-")
    slug = raw or f"post-{int(time.time())}"
    if existing_posts:
        taken = {p["slug"] for p in existing_posts if p.get("slug") != exclude_slug}
        if slug in taken:
            slug = f"{slug}-{int(time.time())}"
    return slug

def get_all_users() -> dict:
    if not USERS_FILE.exists():
        return {}
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_all_users(users: dict):
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=2)

# ─────────────────────────────────────────────────────────────────────────────
# SSR BLOG POST HTML GENERATOR
# ─────────────────────────────────────────────────────────────────────────────
def _read_template(name: str) -> str:
    fp = PUBLIC_DIR / name
    if fp.exists():
        return fp.read_text(encoding="utf-8")
    return ""

def build_blog_post_html(post: dict) -> str:
    """Generate a complete, SEO-friendly HTML page for a blog post server-side."""
    domain      = SITE_DOMAIN
    slug        = post.get("slug", "")
    post_url    = f"{domain}/blog/{slug}"
    title       = html_module.escape(post.get("title", ""))
    seo_title   = html_module.escape(post.get("seo_title") or post.get("title", ""))
    seo_desc    = html_module.escape(post.get("seo_description") or post.get("summary", ""))
    summary     = html_module.escape(post.get("summary", ""))
    author      = html_module.escape(post.get("author") or "SEO Error Auditor Team")
    category    = html_module.escape(post.get("category", "Technical SEO"))
    date_pub    = post.get("date", "")
    date_mod    = post.get("updated_at") or date_pub
    read_time   = html_module.escape(post.get("read_time", "5 min read"))
    og_img      = post.get("featured_image_url") or f"{domain}/logo.png"
    # Content is already sanitized HTML stored in the DB
    content_html = post.get("content", "")

    # JSON-LD schema
    schema = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "BlogPosting",
                "@id": post_url,
                "headline": post.get("title", ""),
                "description": post.get("seo_description") or post.get("summary", ""),
                "image": og_img,
                "author": {
                    "@type": "Organization",
                    "name": post.get("author") or "SEO Error Auditor Team",
                    "url": domain
                },
                "publisher": {
                    "@type": "Organization",
                    "name": "SEO Error Auditor",
                    "url": domain,
                    "logo": {"@type": "ImageObject", "url": f"{domain}/logo.png"}
                },
                "datePublished": date_pub,
                "dateModified": date_mod,
                "mainEntityOfPage": {"@type": "WebPage", "@id": post_url},
                "url": post_url,
                "keywords": ", ".join(post.get("tags") or []),
                "articleSection": post.get("category", "Technical SEO"),
            },
            {
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "Home",      "item": f"{domain}/"},
                    {"@type": "ListItem", "position": 2, "name": "SEO Guides","item": f"{domain}/blog"},
                    {"@type": "ListItem", "position": 3, "name": post.get("title",""), "item": post_url}
                ]
            }
        ]
    }
    schema_json = json.dumps(schema, ensure_ascii=False)

    # Format date nicely
    try:
        dt_nice = datetime.strptime(date_pub, "%Y-%m-%d").strftime("%B %d, %Y")
    except Exception:
        dt_nice = date_pub

    # Read shared assets versions from existing file (fallback to v=12)
    css_ver = "12"

    # OG/Twitter tags
    og_type = "article"

    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{seo_title} | SEO Error Auditor</title>
    <meta name="description" content="{seo_desc}">
    <meta name="robots" content="index, follow, max-image-preview:large, max-snippet:-1">
    <link rel="canonical" href="{post_url}">
    <link rel="icon" href="/favicon.png" type="image/png">

    <!-- Open Graph -->
    <meta property="og:type"        content="{og_type}">
    <meta property="og:url"         content="{post_url}" id="ogUrl">
    <meta property="og:title"       content="{seo_title}" id="ogTitle">
    <meta property="og:description" content="{seo_desc}" id="ogDesc">
    <meta property="og:image"       content="{og_img}" id="ogImage">
    <meta property="og:site_name"   content="SEO Error Auditor">
    <meta property="article:published_time" content="{date_pub}">
    <meta property="article:modified_time"  content="{date_mod}">
    <meta property="article:section"        content="{category}">

    <!-- Twitter/X -->
    <meta name="twitter:card"        content="summary_large_image">
    <meta name="twitter:title"       content="{seo_title}">
    <meta name="twitter:description" content="{seo_desc}">
    <meta name="twitter:image"       content="{og_img}" id="twitterImage">

    <!-- Fonts -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Outfit:wght@500;600;700;800&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
    <link rel="stylesheet" href="/style.css?v={css_ver}">

    <!-- JSON-LD Structured Data -->
    <script type="application/ld+json">{schema_json}</script>
</head>
<body>
    <div class="bg-blob blob-1"></div>
    <div class="bg-blob blob-2"></div>
    <div class="bg-blob blob-3"></div>

    <!-- Header Navigation -->
    <header class="navbar" role="banner">
        <div class="container nav-container">
            <a href="/" class="brand" aria-label="SEO Error Auditor Home">
                <img src="/logo.png" alt="SEO Error Auditor Logo" class="brand-logo-img" width="300" height="85">
            </a>
            <button class="mobile-menu-btn" id="mobileMenuBtn" aria-label="Toggle menu" aria-expanded="false" aria-controls="navLinks">
                <i class="fa-solid fa-bars" aria-hidden="true"></i>
            </button>
            <nav class="nav-links" id="navLinks" role="navigation" aria-label="Main navigation">
                <a href="/" class="nav-item"><i class="fa-solid fa-house" aria-hidden="true"></i> Home</a>
                <div class="nav-dropdown" id="navDropdownTools">
                    <button class="nav-item dropdown-toggle" id="dropdownToggleBtn" aria-haspopup="true" aria-expanded="false" type="button">
                        <i class="fa-solid fa-toolbox" aria-hidden="true"></i> Free SEO Tools <i class="fa-solid fa-chevron-down text-xs ml-1" aria-hidden="true"></i>
                    </button>
                    <div class="dropdown-menu" id="toolsDropdownMenu" role="menu" aria-label="Free SEO Tools">
                        <a href="/tools/sitemap-generator"      class="dropdown-item" role="menuitem"><i class="fa-solid fa-sitemap"></i> Sitemap Generator</a>
                        <a href="/tools/schema-generator"       class="dropdown-item" role="menuitem"><i class="fa-solid fa-code"></i> JSON-LD Schema Builder</a>
                        <a href="/tools/meta-tag-generator"     class="dropdown-item" role="menuitem"><i class="fa-solid fa-tags"></i> Meta Tags Generator</a>
                        <a href="/tools/og-graph-generator"     class="dropdown-item" role="menuitem"><i class="fa-solid fa-share-nodes"></i> Open Graph Generator</a>
                        <a href="/tools/twitter-card-generator" class="dropdown-item" role="menuitem"><i class="fa-brands fa-x-twitter"></i> Twitter Card Generator</a>
                        <a href="/tools/robots-txt-generator"   class="dropdown-item" role="menuitem"><i class="fa-solid fa-shield-halved"></i> Robots.txt Generator</a>
                        <a href="/tools/llms-txt-generator"     class="dropdown-item" role="menuitem"><i class="fa-solid fa-robot"></i> LLMs.txt AI Generator</a>
                        <a href="/tools/html-to-text"           class="dropdown-item" role="menuitem"><i class="fa-solid fa-file-lines"></i> HTML to Text Converter</a>
                        <a href="/tools/text-to-html"           class="dropdown-item" role="menuitem"><i class="fa-solid fa-code"></i> Text to HTML Converter</a>
                    </div>
                </div>
                <a href="/about"   class="nav-item"><i class="fa-solid fa-circle-info" aria-hidden="true"></i> About</a>
                <a href="/contact" class="nav-item"><i class="fa-solid fa-envelope" aria-hidden="true"></i> Contact</a>
                <a href="/blog"    class="nav-item active"><i class="fa-solid fa-newspaper" aria-hidden="true"></i> SEO Guides</a>
                <div class="nav-actions-mobile">
                    <button id="themeToggleBtnMobile" class="btn btn-sm btn-outline theme-toggle-btn" aria-label="Toggle dark/light mode"><i class="fa-solid fa-moon" aria-hidden="true"></i></button>
                </div>
            </nav>
            <div class="nav-actions" id="navActionsDesktop">
                <button id="themeToggleBtn" class="btn btn-sm btn-outline theme-toggle-btn" aria-label="Toggle dark/light mode"><i class="fa-solid fa-moon" aria-hidden="true"></i></button>
            </div>
        </div>
    </header>

    <main class="main-layout container">

        <!-- Breadcrumb (visible) -->
        <nav class="breadcrumb-nav" aria-label="Breadcrumb">
            <ol class="breadcrumb-list">
                <li><a href="/">Home</a></li>
                <li><span aria-hidden="true">›</span></li>
                <li><a href="/blog">SEO Guides</a></li>
                <li><span aria-hidden="true">›</span></li>
                <li aria-current="page">{title}</li>
            </ol>
        </nav>

        <!-- Article -->
        <article class="article-wrapper glass-card" itemscope itemtype="https://schema.org/BlogPosting">
            <div class="article-meta-top">
                <a href="/blog" class="back-link"><i class="fa-solid fa-arrow-left"></i> All SEO Guides</a>
                <span class="category-badge" id="articleCategory" itemprop="articleSection">{category}</span>
            </div>

            <h1 class="article-title" id="articleTitle" itemprop="headline">{title}</h1>

            <div class="article-author-row">
                <div class="author-avatar"><i class="fa-solid fa-user-tie"></i></div>
                <div>
                    <span class="author-name" id="articleAuthor" itemprop="author" itemscope itemtype="https://schema.org/Organization">
                        <span itemprop="name">{author}</span>
                    </span>
                    <div class="article-date-info">
                        <time id="articleDate" itemprop="datePublished" datetime="{date_pub}">{dt_nice}</time>
                        &bull; <span id="articleReadTime">{read_time}</span>
                    </div>
                </div>
            </div>

            <!-- Summary highlight -->
            <div class="article-summary-box" id="articleSummary" itemprop="description">
                {summary}
            </div>

            <!-- Main article content — server-rendered, crawlable -->
            <div class="article-body" id="articleBody" itemprop="articleBody">
                {content_html}
            </div>

            <!-- CTA -->
            <div class="article-cta-box text-center glass-card my-6">
                <h3><i class="fa-solid fa-magnifying-glass-chart"></i> Ready to Audit Your Own Website?</h3>
                <p>Detect 404 broken links, missing meta titles, thin pages, and duplicate content in seconds.</p>
                <a href="/" class="btn btn-emerald btn-glow btn-lg mt-3"><i class="fa-solid fa-bolt"></i> Run Free Website Audit Now</a>
            </div>

            <!-- Related tools internal links -->
            <div class="article-related-tools">
                <h3>Related Free SEO Tools</h3>
                <div class="related-tools-grid">
                    <a href="/tools/meta-tag-generator"     class="related-tool-card"><i class="fa-solid fa-tags"></i> Meta Tag Generator</a>
                    <a href="/tools/schema-generator"       class="related-tool-card"><i class="fa-solid fa-code"></i> Schema Builder</a>
                    <a href="/tools/sitemap-generator"      class="related-tool-card"><i class="fa-solid fa-sitemap"></i> Sitemap Generator</a>
                    <a href="/tools/robots-txt-generator"   class="related-tool-card"><i class="fa-solid fa-shield-halved"></i> Robots.txt Generator</a>
                </div>
            </div>
        </article>

        <!-- Related Posts Section (loaded client-side, non-critical) -->
        <section class="glass-card my-6" id="relatedPostsSection" style="display:none;" aria-label="Related guides">
            <div class="card-header-row">
                <h2><i class="fa-solid fa-newspaper"></i> Related SEO Guides</h2>
            </div>
            <div class="blog-grid" id="relatedPostsGrid"></div>
        </section>

    </main>

    <!-- Footer -->
    <footer class="footer">
        <div class="container footer-grid">
            <div class="footer-col brand-col">
                <a href="/" class="brand">
                    <img src="/footer-logo.png" alt="SEO Error Auditor Logo" class="footer-logo-img">
                </a>
                <p class="footer-desc">Automated technical SEO auditing engine &amp; 404 broken link scanner. Free website health reports for webmasters, marketers, &amp; SEO agencies.</p>
                <div class="footer-socials">
                    <span class="trust-badge"><i class="fa-solid fa-shield-halved"></i> 100% Free &amp; Secure Engine</span>
                </div>
            </div>
            <div class="footer-col">
                <h4>Audit Tools</h4>
                <ul class="footer-links">
                    <li><a href="/">Website SEO Audit Engine</a></li>
                    <li><a href="/#features">Broken 404 Link Checker</a></li>
                    <li><a href="/#features">Meta Title &amp; Tag Scanner</a></li>
                    <li><a href="/#features">Duplicate Content Detector</a></li>
                </ul>
            </div>
            <div class="footer-col">
                <h4>Resources</h4>
                <ul class="footer-links">
                    <li><a href="/blog">SEO Guides &amp; Tutorials</a></li>
                    <li><a href="/blog/complete-technical-seo-audit-checklist-2026">Technical SEO Checklist 2026</a></li>
                    <li><a href="/blog/how-to-fix-404-broken-links-guide">404 Error Fix Guide</a></li>
                    <li><a href="/#faq">Frequently Asked Questions</a></li>
                </ul>
            </div>
            <div class="footer-col">
                <h4>Company &amp; Legal</h4>
                <ul class="footer-links">
                    <li><a href="/privacy">Privacy Policy</a></li>
                    <li><a href="/terms">Terms of Service</a></li>
                    <li><a href="/about">About Us</a></li>
                    <li><a href="mailto:support@seoerrorauditor.com">Contact Support</a></li>
                </ul>
            </div>
        </div>
        <div class="container footer-bottom text-center">
            <p>&copy; 2026 SEO Error Auditor (seoerrorauditor.com). All rights reserved.</p>
        </div>
    </footer>

    <!-- Enquiry Popup -->
    <div id="enquiryPopupOverlay" class="popup-overlay">
        <div class="popup-modal">
            <button class="popup-close" id="popupCloseBtn" aria-label="Close">&times;</button>
            <div class="popup-header">
                <div class="popup-header-icon">&#128640;</div>
                <h3>Need Help With Your Project?</h3>
                <p>Tell us a few details &amp; our expert team will get in touch with you shortly.</p>
            </div>
            <div class="popup-body">
                <form id="enquiryFormPopup" autocomplete="off">
                    <div class="popup-field">
                        <label for="popupName">Full Name</label>
                        <div class="popup-input-wrap">
                            <input type="text" id="popupName" placeholder="Enter your full name" required minlength="2">
                        </div>
                    </div>
                    <div class="popup-field">
                        <label for="popupEmail">Email Address</label>
                        <div class="popup-input-wrap">
                            <input type="email" id="popupEmail" placeholder="Enter your email" required>
                        </div>
                    </div>
                    <div class="popup-field">
                        <label for="popupMobile">Mobile Number</label>
                        <div class="popup-input-wrap">
                            <input type="tel" id="popupMobile" placeholder="Enter your mobile number" pattern="[\\+]?[0-9]{{10,13}}" required>
                        </div>
                    </div>
                    <button type="submit" class="popup-submit-btn">Send Enquiry</button>
                    <div id="popupFormMessage" class="popup-form-msg"></div>
                </form>
                <div class="popup-trust">
                    <span class="popup-trust-item">&#128274; No Spam Ever</span>
                    <span class="popup-trust-item">&#9889; Quick Response</span>
                </div>
            </div>
        </div>
    </div>

    <script src="/config.js"></script>
    <script src="/app.js?v={css_ver}"></script>
    <script>
    // Load related posts (non-critical, does not affect SEO)
    document.addEventListener('DOMContentLoaded', () => {{
        const slug = "{slug}";
        const category = "{category}";
        loadRelatedPosts(category, slug);
    }});
    async function loadRelatedPosts(category, excludeSlug) {{
        try {{
            const catSlug = category.toLowerCase().replace(/\\s+/g, '-');
            const res = await fetch('/api/posts/category/' + catSlug);
            if (!res.ok) return;
            let posts = await res.json();
            posts = posts.filter(p => p.slug !== excludeSlug).slice(0, 3);
            if (!posts.length) return;
            const section = document.getElementById('relatedPostsSection');
            const grid = document.getElementById('relatedPostsGrid');
            if (!section || !grid) return;
            grid.innerHTML = posts.map(p => `
                <div class="glass-card blog-card">
                    <div>
                        <div class="blog-card-meta">
                            <span class="category-badge">${{p.category}}</span>
                            <span class="read-time"><i class="fa-regular fa-clock"></i> ${{p.read_time}}</span>
                        </div>
                        <h3 class="blog-card-title"><a href="/blog/${{p.slug}}">${{p.title}}</a></h3>
                        <p class="blog-card-summary">${{p.summary}}</p>
                    </div>
                    <div class="blog-card-footer">
                        <span><i class="fa-regular fa-calendar"></i> ${{p.date}}</span>
                        <a href="/blog/${{p.slug}}" class="btn btn-sm btn-outline">Read Guide <i class="fa-solid fa-arrow-right"></i></a>
                    </div>
                </div>`).join('');
            section.style.display = 'block';
        }} catch(e) {{ /* ignore */ }}
    }}
    </script>
</body>
</html>"""
    return page

# ─────────────────────────────────────────────────────────────────────────────
# API ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/api/health")
def health_check():
    return {"status": "ok", "service": "SEO Auditor API", "version": "3.0.0"}

@app.post("/api/admin/token")
async def admin_login_token(form_data: OAuth2PasswordRequestForm = Depends()):
    if form_data.username != ADMIN_USERNAME or not verify_password(form_data.password):
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    token = create_access_token({"sub": form_data.username})
    return {"access_token": token, "token_type": "bearer"}

@app.post("/api/admin/login")
async def admin_login_json(req: AdminLoginRequest):
    if req.username != ADMIN_USERNAME or not verify_password(req.password):
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    token = create_access_token({"sub": req.username})
    return {"access_token": token, "token_type": "bearer", "username": req.username}

@app.get("/api/admin/me")
async def admin_me(current_user: str = Depends(get_current_admin)):
    return {"username": current_user, "authenticated": True}

@app.post("/api/admin/upload")
async def upload_image(file: UploadFile = File(...), current_user: str = Depends(get_current_admin)):
    import shutil
    ext = os.path.splitext(file.filename)[1]
    new_filename = f"img_{uuid.uuid4().hex[:8]}{ext}"
    dest_dir  = PUBLIC_DIR / "uploads"
    dest_dir.mkdir(exist_ok=True)
    dest_path = dest_dir / new_filename
    with open(dest_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    return {"location": f"/uploads/{new_filename}"}

@app.post("/api/users/register")
async def register_user(req: UserRegisterRequest):
    users = get_all_users()
    if req.email in users:
        raise HTTPException(status_code=400, detail="Email already registered")
    hashed = pwd_context.hash(req.password) if JOSE_AVAILABLE else req.password
    users[req.email] = {"password": hashed, "created_at": datetime.now().isoformat()}
    save_all_users(users)
    return {"message": "Registration successful"}

@app.post("/api/users/login")
async def login_user(req: UserLoginRequest):
    users = get_all_users()
    user  = users.get(req.email)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    valid = pwd_context.verify(req.password, user["password"]) if JOSE_AVAILABLE else (req.password == user["password"])
    if not valid:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = create_access_token({"sub": req.email, "type": "user"})
    return {"access_token": token, "token_type": "bearer", "email": req.email}

@app.post("/api/enquiry")
def submit_enquiry(req: EnquiryRequest):
    file_path = "enquiries.json"
    data = []
    if os.path.exists(file_path):
        try:
            with open(file_path, "r") as f:
                data = json.load(f)
        except:
            pass
    data.append({"name": req.name[:100], "email": req.email[:200], "mobile": req.mobile[:20], "time": datetime.now().isoformat()})
    with open(file_path, "w") as f:
        json.dump(data, f)
    return {"status": "success", "message": "Enquiry received"}

@app.post("/api/contact")
@limiter.limit("5/hour")
async def submit_contact(req: ContactRequest, request: Request):
    contacts = []
    if CONTACTS_FILE.exists():
        try:
            with open(CONTACTS_FILE, "r", encoding="utf-8") as f:
                contacts = json.load(f)
        except Exception:
            contacts = []
    entry = {
        "id": str(uuid.uuid4())[:8],
        "name":    req.name.strip()[:100],
        "email":   req.email.strip()[:200],
        "subject": req.subject.strip()[:200],
        "message": req.message.strip()[:2000],
        "submitted_at": datetime.now().isoformat(),
    }
    contacts.insert(0, entry)
    contacts = contacts[:500]
    with open(CONTACTS_FILE, "w", encoding="utf-8") as f:
        json.dump(contacts, f, indent=2, ensure_ascii=False)
    return {"message": "Thank you! Your message has been received. We will reply within 24 hours.", "id": entry["id"]}

@app.get("/api/admin/contacts")
async def get_admin_contacts(current_user: str = Depends(get_current_admin)):
    contacts = []
    if CONTACTS_FILE.exists():
        try:
            with open(CONTACTS_FILE, "r", encoding="utf-8") as f:
                contacts = json.load(f)
        except Exception:
            pass
    file_path = "enquiries.json"
    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                for e in json.load(f):
                    contacts.append({
                        "id": "popup-" + str(e.get("time", "")),
                        "name":    e.get("name", "Unknown"),
                        "email":   e.get("email", "No Email"),
                        "subject": "Popup Enquiry (Mobile: " + e.get("mobile", "N/A") + ")",
                        "message": "Mobile: " + e.get("mobile", "N/A"),
                        "submitted_at": e.get("time", "")
                    })
        except Exception:
            pass
    contacts.sort(key=lambda x: x.get("submitted_at", ""), reverse=True)
    return contacts

# ─────────────────────────────────────────────────────────────────────────────
# AUDIT ENGINE
# ─────────────────────────────────────────────────────────────────────────────
def cleanup_old_files():
    try:
        now = time.time()
        for file in DOWNLOADS_DIR.glob("*.xlsx"):
            try:
                if now - file.stat().st_mtime > 3600:
                    file.unlink()
            except Exception:
                pass
    except Exception:
        pass

def run_audit_background(job_id: str, root_url: str, max_pages: int, email):
    job = jobs.get(job_id)
    if not job:
        return
    try:
        cleanup_old_files()
        job["status"] = "crawling"
        job["step"]   = "Scanning website pages..."
        job["percent"] = 10

        root   = normalise_url(root_url)
        domain = re.sub(r"[^A-Za-z0-9.-]+", "_", urlparse(root).netloc)
        file_name   = f"SEO_Audit_{domain}_{job_id[:8]}.pdf"
        output_path = DOWNLOADS_DIR / file_name

        import subprocess
        job["step"] = "Running Premium Audit & Generating PDF..."
        cmd = [
            sys.executable,
            str(Path(__file__).parent / "premium_auditor.py"),
            "--url", root,
            "--output", str(output_path)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        json_output = None
        for line in result.stdout.splitlines():
            if line.startswith("JSON_RESULT:"):
                json_output = json.loads(line[12:])
                break
        if not json_output:
            raise Exception("Failed to generate audit: " + result.stdout + " " + result.stderr)

        job.update({
            "status": "completed", "percent": 100,
            "step": "Audit Complete!", "file_name": file_name,
            "health_score": json_output["health_score"],
            "summary_metrics": {
                "total_crawled":       json_output["total_crawled"],
                "health_score":        json_output["health_score"],
                "broken_links":        json_output["broken_links"],
                "broken_images":       json_output["broken_images"],
                "missing_titles":      json_output["missing_titles"],
                "missing_descriptions":json_output["missing_descriptions"],
                "missing_h1s":         json_output["missing_h1s"],
                "thin_content_pages":  json_output["thin_content_pages"],
                "duplicate_titles":    json_output["duplicate_titles"],
                "unminified_assets":   json_output["unminified_assets"],
            },
            "audit_preview": {"pages": json_output["pages"], "broken_links": [], "duplicate_titles": []}
        })
    except Exception as exc:
        import traceback
        job["status"] = "failed"
        job["error"]  = str(exc)
        job["step"]   = "Audit failed. Please check the URL and try again."

@app.post("/api/audit")
@limiter.limit("5/hour")
def start_audit(req: AuditRequest, background_tasks: BackgroundTasks, request: Request):
    url = req.url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    max_pages = min(10000, max(5, req.max_pages or 10000))
    job_id    = str(uuid.uuid4())
    jobs[job_id] = {
        "job_id": job_id, "status": "pending", "percent": 0,
        "step": "Initializing audit engine...", "pages_crawled": 0,
        "max_pages": max_pages, "target_url": url, "file_name": None,
        "health_score": 0, "summary_metrics": None, "error": None,
        "created_at": time.time()
    }
    background_tasks.add_task(run_audit_background, job_id, url, max_pages, req.email)
    return {"job_id": job_id, "status": "pending", "message": "Audit started successfully"}

@app.get("/api/status/{job_id}")
def get_audit_status(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Audit job not found")
    return job

@app.get("/api/download/{job_id}")
def download_report(job_id: str):
    job = jobs.get(job_id)
    if not job or job["status"] != "completed" or not job["file_name"]:
        raise HTTPException(status_code=400, detail="Report not ready or job failed")
    file_path = DOWNLOADS_DIR / job["file_name"]
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File no longer exists")
    return FileResponse(path=file_path, filename=job["file_name"], media_type="application/pdf")

# ─────────────────────────────────────────────────────────────────────────────
# BLOG API
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/api/posts")
def get_posts():
    return [p for p in load_posts() if p.get("status", "published") == "published"]

@app.get("/api/posts/all")
def get_all_posts(current_user: str = Depends(get_current_admin)):
    return load_posts()

@app.get("/api/posts/category/{category_slug}")
def get_posts_by_category(category_slug: str):
    normalized = category_slug.replace("-", " ").lower()
    return [p for p in load_posts()
            if p.get("status", "published") == "published"
            and p.get("category", "").lower() == normalized]

@app.get("/api/posts/{slug}")
def get_post(slug: str):
    for p in load_posts():
        if p.get("slug") == slug:
            return p
    raise HTTPException(status_code=404, detail="Blog post not found")

@app.post("/api/posts")
def create_post(req: BlogPostRequest, current_user: str = Depends(get_current_admin)):
    try:
        posts = load_posts()
        slug  = make_slug(req.title, posts)
        new_post = {
            "slug": slug, "title": req.title.strip(),
            "category":  req.category or "Technical SEO",
            "read_time": req.read_time or "5 min read",
            "date":      datetime.now().strftime("%Y-%m-%d"),
            "author":    req.author or "SEO Error Auditor Team",
            "summary":   req.summary or "",
            "content":   sanitize_html(req.content or ""),
            "status":    req.status or "published",
            "featured_image_url": req.featured_image_url or "",
            "seo_title":       req.seo_title or req.title.strip(),
            "seo_description": req.seo_description or req.summary or "",
            "canonical_url":   req.canonical_url or "",
            "tags":            req.tags or [],
        }
        posts.insert(0, new_post)
        save_posts(posts)
        return {"message": "Post published successfully", "post": new_post}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

@app.put("/api/posts/{slug}")
def update_post(slug: str, req: BlogPostRequest, current_user: str = Depends(get_current_admin)):
    posts = load_posts()
    idx   = next((i for i, p in enumerate(posts) if p.get("slug") == slug), None)
    if idx is None:
        raise HTTPException(status_code=404, detail="Post not found")
    old  = posts[idx]
    updated = {
        **old,
        "title":    req.title.strip(),
        "category": req.category or old.get("category", "Technical SEO"),
        "read_time":req.read_time or old.get("read_time", "5 min read"),
        "author":   req.author or old.get("author", "SEO Error Auditor Team"),
        "summary":  req.summary or "",
        "content":  sanitize_html(req.content or ""),
        "status":   req.status or old.get("status", "published"),
        "featured_image_url": req.featured_image_url or old.get("featured_image_url", ""),
        "seo_title":       req.seo_title or req.title.strip(),
        "seo_description": req.seo_description or req.summary or "",
        "canonical_url":   req.canonical_url or old.get("canonical_url", ""),
        "tags":            req.tags or old.get("tags", []),
        "updated_at":      datetime.now().strftime("%Y-%m-%d"),
    }
    posts[idx] = updated
    save_posts(posts)
    return {"message": "Post updated successfully", "post": updated}

@app.delete("/api/posts/{slug}")
def delete_post(slug: str, current_user: str = Depends(get_current_admin)):
    posts   = load_posts()
    updated = [p for p in posts if p.get("slug") != slug]
    if len(updated) == len(posts):
        raise HTTPException(status_code=404, detail="Post not found")
    save_posts(updated)
    return {"message": "Post deleted successfully"}

# ─────────────────────────────────────────────────────────────────────────────
# SITEMAP GENERATOR TOOL API
# ─────────────────────────────────────────────────────────────────────────────
def run_sitemap_generator_job(job_id: str, target_url: str, max_pages: int):
    job = sitemap_jobs[job_id]
    try:
        root = normalise_url(target_url)
        job.update({"status": "running", "percent": 10, "step": "Connecting and discovering site URLs..."})
        job_dir = DOWNLOADS_DIR / f"sitemap_{job_id[:8]}"
        job_dir.mkdir(exist_ok=True)

        def stats_cb(stats):
            job["crawled"] = stats["crawled"]
            job["found"]   = stats["found"]
            job["percent"] = min(90, 10 + int((stats["crawled"] / max(1, max_pages)) * 80))
            job["step"]    = f"Crawled {stats['crawled']} URLs (Queue: {stats['queue_len']})..."

        crawler = WebCrawler(start_url=root, output_dir=str(job_dir), max_threads=16, stats_callback=stats_cb)
        try:
            import requests as req_lib
            r = req_lib.get(root.rstrip("/") + "/sitemap.xml", timeout=8, verify=False)
            if r.status_code == 200:
                urls = set(re.findall(r'<loc>(.*?)</loc>', r.text))
                if urls:
                    crawler.add_existing_sitemap_urls(urls)
        except Exception:
            pass
        crawler.start()
        while not crawler.is_finished() and len(crawler.visited_urls) < max_pages:
            time.sleep(0.2)
        crawler.stop()
        job["step"] = "Building Google-compliant XML Sitemap..."
        job["percent"] = 92
        if crawler.successful_urls:
            gen = SitemapGenerator(crawler.successful_urls, root, str(job_dir))
            gen.generate()
            primary_file = job_dir / "sitemap.xml" if (job_dir / "sitemap.xml").exists() else job_dir / "sitemap1.xml"
            xml_text = primary_file.read_text(encoding="utf-8") if primary_file.exists() else ""
            job.update({
                "status": "completed", "percent": 100,
                "step": f"Sitemap generated! ({len(crawler.successful_urls)} URLs)",
                "xml_text": xml_text,
                "urls_count": len(crawler.successful_urls),
                "download_file": str(primary_file)
            })
        else:
            job.update({"status": "error", "error": "No valid URLs discovered."})
    except Exception as exc:
        job.update({"status": "error", "error": str(exc)})

@app.post("/api/sitemap/generate")
def start_sitemap_generation(req: SitemapGenRequest, background_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())
    sitemap_jobs[job_id] = {"status": "queued", "percent": 0, "step": "Queued...",
                             "crawled": 0, "found": 0, "urls_count": 0, "xml_text": "",
                             "download_file": None, "error": None}
    background_tasks.add_task(run_sitemap_generator_job, job_id, req.url, req.max_pages)
    return {"job_id": job_id, "status": "queued"}

@app.get("/api/sitemap/status/{job_id}")
def get_sitemap_job_status(job_id: str):
    if job_id not in sitemap_jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    return sitemap_jobs[job_id]

@app.get("/api/sitemap/download/{job_id}")
def download_generated_sitemap(job_id: str):
    if job_id not in sitemap_jobs or not sitemap_jobs[job_id].get("download_file"):
        raise HTTPException(status_code=404, detail="Sitemap file not ready")
    filepath = Path(sitemap_jobs[job_id]["download_file"])
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(filepath, filename="sitemap.xml", media_type="application/xml")

# ─────────────────────────────────────────────────────────────────────────────
# RSS FEED
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/rss.xml")
def get_rss_feed():
    domain   = SITE_DOMAIN
    posts    = [p for p in load_posts() if p.get("status", "published") == "published"][:20]
    now_rfc  = datetime.now().strftime("%a, %d %b %Y %H:%M:%S +0000")
    def esc(s): return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    rss  = '<?xml version="1.0" encoding="UTF-8"?>\n'
    rss += '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">\n  <channel>\n'
    rss += f'    <title>SEO Error Auditor - SEO Guides &amp; Technical Articles</title>\n'
    rss += f'    <link>{domain}/blog</link>\n'
    rss += f'    <description>Expert tutorials on technical SEO, broken link fixing, and site audit optimization.</description>\n'
    rss += f'    <language>en-us</language>\n'
    rss += f'    <lastBuildDate>{now_rfc}</lastBuildDate>\n'
    rss += f'    <atom:link href="{domain}/rss.xml" rel="self" type="application/rss+xml"/>\n'
    for p in posts:
        pub_date = p.get("date", "2026-01-01")
        try:
            rfc_date = datetime.strptime(pub_date, "%Y-%m-%d").strftime("%a, %d %b %Y 09:00:00 +0000")
        except Exception:
            rfc_date = now_rfc
        slug    = p.get("slug", "")
        title   = esc(p.get("title", ""))
        summary = esc(p.get("summary", ""))
        rss += f'    <item>\n      <title>{title}</title>\n      <link>{domain}/blog/{slug}</link>\n'
        rss += f'      <guid>{domain}/blog/{slug}</guid>\n      <pubDate>{rfc_date}</pubDate>\n'
        rss += f'      <category>{esc(p.get("category","Technical SEO"))}</category>\n      <description>{summary}</description>\n    </item>\n'
    rss += '  </channel>\n</rss>'
    return Response(content=rss, media_type="application/rss+xml")

# ─────────────────────────────────────────────────────────────────────────────
# ROBOTS.TXT — production quality
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/robots.txt", response_class=PlainTextResponse)
def get_robots():
    domain = SITE_DOMAIN
    return (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /admin\n"
        "Disallow: /admin/\n"
        "Disallow: /api/\n"
        "Disallow: /uploads/\n"
        "\n"
        "# AI crawlers\n"
        "User-agent: GPTBot\n"
        "Allow: /\n"
        "Disallow: /api/\n"
        "Disallow: /admin\n"
        "\n"
        "User-agent: ClaudeBot\n"
        "Allow: /\n"
        "Disallow: /api/\n"
        "Disallow: /admin\n"
        "\n"
        "User-agent: PerplexityBot\n"
        "Allow: /\n"
        "Disallow: /api/\n"
        "Disallow: /admin\n"
        "\n"
        f"Sitemap: {domain}/sitemap.xml\n"
        f"Sitemap: {domain}/rss.xml\n"
    )

# ─────────────────────────────────────────────────────────────────────────────
# XML SITEMAP — dynamic with lastmod
# ─────────────────────────────────────────────────────────────────────────────
STATIC_ROUTES = [
    {"loc": "/",                             "priority": "1.0", "changefreq": "daily",   "lastmod": "2026-07-28"},
    {"loc": "/tools/sitemap-generator",      "priority": "0.9", "changefreq": "weekly",  "lastmod": "2026-07-28"},
    {"loc": "/tools/schema-generator",       "priority": "0.9", "changefreq": "weekly",  "lastmod": "2026-07-28"},
    {"loc": "/tools/meta-tag-generator",     "priority": "0.9", "changefreq": "weekly",  "lastmod": "2026-07-28"},
    {"loc": "/tools/og-graph-generator",     "priority": "0.9", "changefreq": "weekly",  "lastmod": "2026-07-28"},
    {"loc": "/tools/twitter-card-generator", "priority": "0.9", "changefreq": "weekly",  "lastmod": "2026-07-28"},
    {"loc": "/tools/robots-txt-generator",   "priority": "0.9", "changefreq": "weekly",  "lastmod": "2026-07-28"},
    {"loc": "/tools/llms-txt-generator",     "priority": "0.9", "changefreq": "weekly",  "lastmod": "2026-07-28"},
    {"loc": "/tools/html-to-text",           "priority": "0.9", "changefreq": "weekly",  "lastmod": "2026-07-28"},
    {"loc": "/tools/text-to-html",           "priority": "0.9", "changefreq": "weekly",  "lastmod": "2026-07-28"},
    {"loc": "/blog",                         "priority": "0.9", "changefreq": "daily",   "lastmod": "2026-07-28"},
    {"loc": "/about",                        "priority": "0.8", "changefreq": "monthly", "lastmod": "2026-07-28"},
    {"loc": "/contact",                      "priority": "0.8", "changefreq": "monthly", "lastmod": "2026-07-28"},
    {"loc": "/privacy",                      "priority": "0.3", "changefreq": "monthly", "lastmod": "2026-07-28"},
    {"loc": "/terms",                        "priority": "0.3", "changefreq": "monthly", "lastmod": "2026-07-28"},
]

@app.get("/sitemap.xml")
def get_sitemap():
    domain = SITE_DOMAIN
    pages  = [{"loc": f"{domain}{r['loc']}", **{k:v for k,v in r.items() if k != 'loc'}} for r in STATIC_ROUTES]
    for p in [p for p in load_posts() if p.get("status", "published") == "published"]:
        pages.append({
            "loc":        f"{domain}/blog/{p['slug']}",
            "priority":   "0.8",
            "changefreq": "weekly",
            "lastmod":    p.get("updated_at") or p.get("date", "2026-07-28")
        })
    xml  = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    for p in pages:
        xml += f'  <url>\n    <loc>{p["loc"]}</loc>\n'
        if p.get("lastmod"):
            xml += f'    <lastmod>{p["lastmod"]}</lastmod>\n'
        xml += f'    <changefreq>{p["changefreq"]}</changefreq>\n'
        xml += f'    <priority>{p["priority"]}</priority>\n  </url>\n'
    xml += '</urlset>'
    return Response(content=xml, media_type="application/xml",
                    headers={"Cache-Control": "public, max-age=3600"})

# ─────────────────────────────────────────────────────────────────────────────
# LLMS.TXT  (AI-readable site index — optional, informational)
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/llms.txt", response_class=PlainTextResponse)
def get_llms_txt():
    domain = SITE_DOMAIN
    posts  = [p for p in load_posts() if p.get("status", "published") == "published"]
    lines  = [
        f"# {domain}",
        "",
        "## SEO Error Auditor",
        "Free technical SEO auditing platform. Automated broken link detection, metadata analysis,",
        "XML sitemap generation, JSON-LD schema building, and on-page SEO tools.",
        "",
        "## Homepage",
        f"- {domain}/",
        "",
        "## Free SEO Tools",
        f"- {domain}/tools/sitemap-generator — XML Sitemap Generator",
        f"- {domain}/tools/schema-generator — JSON-LD Schema Builder",
        f"- {domain}/tools/meta-tag-generator — Meta Tag Generator",
        f"- {domain}/tools/og-graph-generator — Open Graph Tag Generator",
        f"- {domain}/tools/twitter-card-generator — Twitter Card Generator",
        f"- {domain}/tools/robots-txt-generator — Robots.txt Generator",
        f"- {domain}/tools/llms-txt-generator — LLMs.txt Generator",
        f"- {domain}/tools/html-to-text — HTML to Text Converter",
        f"- {domain}/tools/text-to-html — Text to HTML Converter",
        "",
        "## SEO Guides (Blog)",
        f"- {domain}/blog",
    ]
    for p in posts[:20]:
        lines.append(f"- {domain}/blog/{p['slug']} — {p['title']}")
    lines += [
        "",
        "## Company",
        f"- {domain}/about — About SEO Error Auditor",
        f"- {domain}/contact — Contact Us",
        "",
        "## Legal",
        f"- {domain}/privacy — Privacy Policy",
        f"- {domain}/terms — Terms of Service",
        "",
        "## Feeds",
        f"- {domain}/rss.xml — RSS Feed",
        f"- {domain}/sitemap.xml — XML Sitemap",
    ]
    return "\n".join(lines)

# ─────────────────────────────────────────────────────────────────────────────
# AI.TXT  (optional conservative AI policy file)
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/ai.txt", response_class=PlainTextResponse)
def get_ai_txt():
    domain = SITE_DOMAIN
    return (
        "# AI Access Policy — SEO Error Auditor\n"
        "# This is an optional informational file. It is NOT a Google ranking signal.\n\n"
        "allow: /\n"
        "allow: /blog/\n"
        "allow: /tools/\n"
        "allow: /about\n"
        "allow: /contact\n"
        "disallow: /api/\n"
        "disallow: /admin\n"
        "disallow: /uploads/\n\n"
        f"canonical-base: {domain}\n"
        "content-license: CC BY-NC-ND 4.0\n"
        "attribution: required\n"
    )

# ─────────────────────────────────────────────────────────────────────────────
# HTML PAGE ROUTES (SSR where applicable, static file otherwise)
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/about")
def serve_about():   return FileResponse(PUBLIC_DIR / "about.html")

@app.get("/contact")
def serve_contact(): return FileResponse(PUBLIC_DIR / "contact.html")

@app.get("/tools/og-graph-generator")
def serve_og():      return FileResponse(PUBLIC_DIR / "og-graph-generator.html")

@app.get("/tools/twitter-card-generator")
def serve_twitter(): return FileResponse(PUBLIC_DIR / "twitter-card-generator.html")

@app.get("/tools/llms-txt-generator")
def serve_llms():    return FileResponse(PUBLIC_DIR / "llms-txt-generator.html")

@app.get("/tools/robots-txt-generator")
def serve_robots_gen(): return FileResponse(PUBLIC_DIR / "robots-txt-generator.html")

@app.get("/tools/meta-tag-generator")
def serve_meta():    return FileResponse(PUBLIC_DIR / "meta-tag-generator.html")

@app.get("/tools/schema-generator")
def serve_schema():  return FileResponse(PUBLIC_DIR / "schema-generator.html")

@app.get("/tools/sitemap-generator")
def serve_sitemap_tool(): return FileResponse(PUBLIC_DIR / "sitemap-generator.html")

@app.get("/tools/html-to-text")
def serve_html_to_text(): return FileResponse(PUBLIC_DIR / "html-to-text-generator.html")

@app.get("/tools/text-to-html")
def serve_text_to_html(): return FileResponse(PUBLIC_DIR / "text-to-html-generator.html")

@app.get("/blog")
def serve_blog():    return FileResponse(PUBLIC_DIR / "blog.html")

@app.get("/blog/category/{category_slug}")
def serve_blog_category(category_slug: str):
    return FileResponse(PUBLIC_DIR / "blog-category.html")

# ── CRITICAL: SSR Blog Post ──
@app.get("/blog/{slug}")
def serve_blog_post(slug: str):
    """Server-side render a full SEO-complete HTML page for each blog post."""
    posts = load_posts()
    post  = next((p for p in posts if p.get("slug") == slug), None)
    if not post:
        # Return proper 404 — never soft-redirect
        raise HTTPException(status_code=404, detail=f"Blog post '{slug}' not found")
    if post.get("status", "published") != "published":
        raise HTTPException(status_code=404, detail="Post not found")
    html = build_blog_post_html(post)
    return HTMLResponse(content=html, status_code=200,
                        headers={"Cache-Control": "public, max-age=300, stale-while-revalidate=60"})

@app.get("/admin/login")
def serve_admin_login(): return FileResponse(PUBLIC_DIR / "admin-login.html")

@app.get("/admin")
def serve_admin():   return FileResponse(PUBLIC_DIR / "admin.html")

@app.get("/privacy")
def serve_privacy(): return FileResponse(PUBLIC_DIR / "privacy.html")

@app.get("/terms")
def serve_terms():   return FileResponse(PUBLIC_DIR / "terms.html")

# ─────────────────────────────────────────────────────────────────────────────
# 404 HANDLER — must come AFTER all explicit routes, BEFORE static mount
# ─────────────────────────────────────────────────────────────────────────────
@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    # Serve a proper 404 page (static file if exists, else minimal HTML)
    fp = PUBLIC_DIR / "404.html"
    if fp.exists():
        content = fp.read_text(encoding="utf-8")
        return HTMLResponse(content=content, status_code=404)
    return HTMLResponse(
        content='<html><head><title>404 Not Found | SEO Error Auditor</title>'
                '<meta name="robots" content="noindex"></head>'
                '<body><h1>404 — Page Not Found</h1>'
                '<p><a href="/">Return to Home</a></p></body></html>',
        status_code=404
    )

# ─────────────────────────────────────────────────────────────────────────────
# STATIC FILES
# ─────────────────────────────────────────────────────────────────────────────
if PUBLIC_DIR.exists():
    app.mount("/", StaticFiles(directory=PUBLIC_DIR, html=True), name="public_root")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, access_log=False, log_level="warning")
