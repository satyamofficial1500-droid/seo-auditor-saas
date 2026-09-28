"""
Phase 5 & 6 SEO upgrade script:
- Adds/fixes canonical tags on every public HTML page
- Adds/fixes robots meta (index,follow for public; noindex for admin)
- Fixes og:url, og:type, og:site_name, og:title, og:description per page
- Adds twitter:title, twitter:description per page
- Bumps style.css and app.js cache versions to v=13
- Adds <html lang="en"> if missing
- Adds Organization + WebSite JSON-LD to index.html
"""

import os, re, json
from pathlib import Path

DOMAIN   = "https://seoerrorauditor.com"
HTML_DIR = Path(__file__).parent / "public_html"
CSS_VER  = "13"

# ── Page metadata catalogue ─────────────────────────────────────────────────
PAGE_META = {
    "index.html": {
        "canonical": f"{DOMAIN}/",
        "robots":    "index, follow, max-image-preview:large, max-snippet:-1",
        "og_type":   "website",
        "og_title":  "Free SEO Tools Online 2026 | SEO Error Auditor",
        "og_desc":   "Use 10+ free SEO tools at SEO Error Auditor — meta tag generator, XML sitemap generator, JSON-LD schema builder, Open Graph generator, robots.txt creator & more. No sign-up required.",
        "title":     "Free SEO Tools Online 2026 | Meta Tag Generator, Sitemap Builder & Schema Creator",
        "desc":      "Use 10+ free SEO tools at SEO Error Auditor — meta tag generator, XML sitemap generator, JSON-LD schema builder, Open Graph generator, robots.txt creator & more. No sign-up required.",
        "schema":    True,
    },
    "blog.html": {
        "canonical": f"{DOMAIN}/blog",
        "robots":    "index, follow",
        "og_type":   "website",
        "og_title":  "SEO Guides & Technical SEO Tutorials | SEO Error Auditor",
        "og_desc":   "Expert tutorials on technical SEO, broken link fixing, schema markup, and site audit optimization.",
        "title":     "SEO Guides & Technical SEO Tutorials | SEO Error Auditor",
        "desc":      "Expert tutorials on technical SEO, broken link fixing, schema markup, and site audit optimization.",
    },
    "blog-post.html": {
        "canonical": f"{DOMAIN}/blog",   # dynamic; template only, SSR handles real posts
        "robots":    "index, follow",
        "og_type":   "article",
        "og_title":  "SEO Guide | SEO Error Auditor",
        "og_desc":   "Read technical SEO guides on SEO Error Auditor.",
        "title":     "SEO Guide | SEO Error Auditor",
        "desc":      "Read technical SEO guides on SEO Error Auditor.",
    },
    "blog-category.html": {
        "canonical": f"{DOMAIN}/blog",
        "robots":    "noindex, follow",  # category pages thin; noindex to avoid duplicate
        "og_type":   "website",
        "og_title":  "SEO Guides by Category | SEO Error Auditor",
        "og_desc":   "Browse SEO guides by category on SEO Error Auditor.",
        "title":     "SEO Guides by Category | SEO Error Auditor",
        "desc":      "Browse SEO guides by category on SEO Error Auditor.",
    },
    "about.html": {
        "canonical": f"{DOMAIN}/about",
        "robots":    "index, follow",
        "og_type":   "website",
        "og_title":  "About SEO Error Auditor — Free Technical SEO Platform",
        "og_desc":   "SEO Error Auditor is a free technical SEO platform offering automated audits, broken link detection, sitemap generation, and schema building tools.",
        "title":     "About SEO Error Auditor — Free Technical SEO Platform",
        "desc":      "SEO Error Auditor is a free technical SEO platform offering automated audits, broken link detection, sitemap generation, and schema building tools.",
    },
    "contact.html": {
        "canonical": f"{DOMAIN}/contact",
        "robots":    "index, follow",
        "og_type":   "website",
        "og_title":  "Contact SEO Error Auditor — Get Support",
        "og_desc":   "Get in touch with the SEO Error Auditor team for support, partnerships, or feedback.",
        "title":     "Contact Us | SEO Error Auditor",
        "desc":      "Get in touch with the SEO Error Auditor team for support, partnerships, or feedback.",
    },
    "privacy.html": {
        "canonical": f"{DOMAIN}/privacy",
        "robots":    "index, follow",
        "og_type":   "website",
        "og_title":  "Privacy Policy | SEO Error Auditor",
        "og_desc":   "Read the privacy policy for SEO Error Auditor — how we collect, use, and protect your data.",
        "title":     "Privacy Policy | SEO Error Auditor",
        "desc":      "Read the privacy policy for SEO Error Auditor.",
    },
    "terms.html": {
        "canonical": f"{DOMAIN}/terms",
        "robots":    "index, follow",
        "og_type":   "website",
        "og_title":  "Terms of Service | SEO Error Auditor",
        "og_desc":   "Read the terms of service for SEO Error Auditor.",
        "title":     "Terms of Service | SEO Error Auditor",
        "desc":      "Read the terms of service for SEO Error Auditor.",
    },
    "meta-tag-generator.html": {
        "canonical": f"{DOMAIN}/tools/meta-tag-generator",
        "robots":    "index, follow, max-image-preview:large",
        "og_type":   "website",
        "og_title":  "Free Meta Tag Generator — Preview in Google & Social | SEO Error Auditor",
        "og_desc":   "Generate optimized title tags, meta descriptions, and keyword tags with live SERP preview. Free meta tag generator, no sign-up.",
        "title":     "Free Meta Tag Generator — Live SERP Preview | SEO Error Auditor",
        "desc":      "Generate optimized title tags, meta descriptions, and keyword tags with live SERP preview. Free meta tag generator, no sign-up required.",
    },
    "schema-generator.html": {
        "canonical": f"{DOMAIN}/tools/schema-generator",
        "robots":    "index, follow",
        "og_type":   "website",
        "og_title":  "Free JSON-LD Schema Markup Generator | SEO Error Auditor",
        "og_desc":   "Build valid JSON-LD structured data for Article, Product, FAQ, LocalBusiness, and more. Free schema generator tool.",
        "title":     "Free JSON-LD Schema Markup Generator | SEO Error Auditor",
        "desc":      "Build valid JSON-LD structured data for Article, Product, FAQ, LocalBusiness, and more. Free JSON-LD schema generator.",
    },
    "sitemap-generator.html": {
        "canonical": f"{DOMAIN}/tools/sitemap-generator",
        "robots":    "index, follow",
        "og_type":   "website",
        "og_title":  "Free XML Sitemap Generator — Crawl & Download | SEO Error Auditor",
        "og_desc":   "Automatically crawl your website and generate a Google-compliant XML sitemap. Free sitemap generator tool — unlimited URLs.",
        "title":     "Free XML Sitemap Generator — Crawl & Download | SEO Error Auditor",
        "desc":      "Automatically crawl your website and generate a Google-compliant XML sitemap. Free XML sitemap generator — unlimited URLs, no sign-up.",
    },
    "robots-txt-generator.html": {
        "canonical": f"{DOMAIN}/tools/robots-txt-generator",
        "robots":    "index, follow",
        "og_type":   "website",
        "og_title":  "Free Robots.txt Generator — Block & Allow Rules | SEO Error Auditor",
        "og_desc":   "Create a valid robots.txt file with custom allow/disallow rules for search engine bots. Free robots.txt generator.",
        "title":     "Free Robots.txt Generator | SEO Error Auditor",
        "desc":      "Create a valid robots.txt file with custom allow/disallow rules. Free robots.txt generator tool.",
    },
    "og-graph-generator.html": {
        "canonical": f"{DOMAIN}/tools/og-graph-generator",
        "robots":    "index, follow",
        "og_type":   "website",
        "og_title":  "Free Open Graph Tag Generator — Facebook & Social Preview | SEO Error Auditor",
        "og_desc":   "Generate Open Graph meta tags for perfect Facebook, LinkedIn, and WhatsApp link previews. Free OG generator.",
        "title":     "Free Open Graph Tag Generator | SEO Error Auditor",
        "desc":      "Generate Open Graph meta tags for perfect Facebook, LinkedIn, and WhatsApp link previews. Free OG tag generator.",
    },
    "twitter-card-generator.html": {
        "canonical": f"{DOMAIN}/tools/twitter-card-generator",
        "robots":    "index, follow",
        "og_type":   "website",
        "og_title":  "Free Twitter Card Generator — X Summary Card Preview | SEO Error Auditor",
        "og_desc":   "Generate Twitter/X card meta tags with live preview. Free twitter card generator tool.",
        "title":     "Free Twitter / X Card Generator | SEO Error Auditor",
        "desc":      "Generate Twitter/X card meta tags with live preview. Free twitter card meta tag generator.",
    },
    "llms-txt-generator.html": {
        "canonical": f"{DOMAIN}/tools/llms-txt-generator",
        "robots":    "index, follow",
        "og_type":   "website",
        "og_title":  "Free LLMs.txt Generator — AI Search Readiness | SEO Error Auditor",
        "og_desc":   "Generate an llms.txt file to help AI systems understand your website content. Free LLMs.txt generator.",
        "title":     "Free LLMs.txt Generator — AI Search Readiness | SEO Error Auditor",
        "desc":      "Generate an llms.txt file to help AI search systems understand your website. Free LLMs.txt generator tool.",
    },
    "html-to-text-generator.html": {
        "canonical": f"{DOMAIN}/tools/html-to-text",
        "robots":    "index, follow",
        "og_type":   "website",
        "og_title":  "Free HTML to Text Converter | SEO Error Auditor",
        "og_desc":   "Convert HTML markup to clean plain text instantly. Free HTML to text converter tool.",
        "title":     "Free HTML to Text Converter | SEO Error Auditor",
        "desc":      "Convert HTML markup to clean plain text instantly. Free HTML to text converter.",
    },
    "text-to-html-generator.html": {
        "canonical": f"{DOMAIN}/tools/text-to-html",
        "robots":    "index, follow",
        "og_type":   "website",
        "og_title":  "Free Text to HTML Converter | SEO Error Auditor",
        "og_desc":   "Convert plain text to HTML markup with proper tags. Free text to HTML converter tool.",
        "title":     "Free Text to HTML Converter | SEO Error Auditor",
        "desc":      "Convert plain text to HTML markup with proper paragraph and heading tags. Free text to HTML converter.",
    },
    "admin.html": {
        "canonical": None,
        "robots":    "noindex, nofollow",
        "og_type":   None,
        "og_title":  None,
        "og_desc":   None,
        "title":     "Admin CMS | SEO Error Auditor",
        "desc":      None,
    },
    "admin-login.html": {
        "canonical": None,
        "robots":    "noindex, nofollow",
        "og_type":   None,
        "og_title":  None,
        "og_desc":   None,
        "title":     "Admin Login | SEO Error Auditor",
        "desc":      None,
    },
    "404.html": {
        "canonical": None,
        "robots":    "noindex, follow",
        "og_type":   None,
        "og_title":  None,
        "og_desc":   None,
        "title":     "404 — Page Not Found | SEO Error Auditor",
        "desc":      None,
    },
}

# Homepage Organization + WebSite schema
HOMEPAGE_SCHEMA = {
    "@context": "https://schema.org",
    "@graph": [
        {
            "@type": "Organization",
            "@id": f"{DOMAIN}/#organization",
            "name": "SEO Error Auditor",
            "url": DOMAIN,
            "logo": {
                "@type": "ImageObject",
                "url": f"{DOMAIN}/logo.png",
                "width": 300,
                "height": 85
            },
            "sameAs": []
        },
        {
            "@type": "WebSite",
            "@id": f"{DOMAIN}/#website",
            "url": DOMAIN,
            "name": "SEO Error Auditor",
            "description": "Free technical SEO tools — meta tag generator, sitemap generator, schema builder, and automated SEO auditing.",
            "publisher": {"@id": f"{DOMAIN}/#organization"},
            "potentialAction": {
                "@type": "SearchAction",
                "target": {"@type": "EntryPoint", "urlTemplate": f"{DOMAIN}/blog?q={{search_term_string}}"},
                "query-input": "required name=search_term_string"
            }
        }
    ]
}

def set_or_add_tag(content, selector, new_tag, position_after="<head>"):
    """Replace existing tag matching selector, or insert after position_after."""
    # Try to replace existing
    new_content = re.sub(selector, new_tag, content, count=1, flags=re.IGNORECASE | re.DOTALL)
    if new_content == content:
        # Tag didn't exist — insert right after position_after
        new_content = content.replace(position_after, position_after + "\n    " + new_tag, 1)
    return new_content

updated_files = []

for filename, meta in PAGE_META.items():
    fp = HTML_DIR / filename
    if not fp.exists():
        print(f"  SKIP (not found): {filename}")
        continue

    content = fp.read_text(encoding="utf-8")

    # 1. Ensure <html lang="en">
    content = re.sub(r'<html(?![^>]*lang)[^>]*>', '<html lang="en">', content, count=1, flags=re.IGNORECASE)

    # 2. Fix <title>
    if meta.get("title"):
        content = re.sub(r'<title>[^<]*</title>', f'<title>{meta["title"]}</title>', content, count=1, flags=re.IGNORECASE)

    # 3. Fix <meta name="description">
    if meta.get("desc"):
        desc_tag = f'<meta name="description" content="{meta["desc"]}">'
        pat = r'<meta\s+name=["\']description["\'][^>]*/?>|<meta\s+[^>]*name=["\']description["\'][^>]*/?>(?:.*?</meta>)?'
        content, n = re.subn(pat, desc_tag, content, count=1, flags=re.IGNORECASE)
        if n == 0:
            content = content.replace("</title>", f"</title>\n    {desc_tag}", 1)

    # 4. Fix robots meta
    robots_tag = f'<meta name="robots" content="{meta["robots"]}">'
    pat_robots = r'<meta\s+name=["\']robots["\'][^>]*/?>|<meta\s+[^>]*name=["\']robots["\'][^>]*/?>(?:.*?</meta>)?'
    content, n = re.subn(pat_robots, robots_tag, content, count=1, flags=re.IGNORECASE)
    if n == 0:
        content = content.replace("</title>", f"</title>\n    {robots_tag}", 1)

    # 5. Fix/add canonical
    if meta.get("canonical"):
        canonical_tag = f'<link rel="canonical" href="{meta["canonical"]}">'
        pat_can = r'<link\s+rel=["\']canonical["\'][^>]*/?>|<link\s+[^>]*rel=["\']canonical["\'][^>]*/?>(?:.*?</link>)?'
        content, n = re.subn(pat_can, canonical_tag, content, count=1, flags=re.IGNORECASE)
        if n == 0:
            content = content.replace("</title>", f"</title>\n    {canonical_tag}", 1)
    else:
        # Remove any existing canonical on noindex pages
        content = re.sub(r'\n?\s*<link\s+rel=["\']canonical["\'][^>]*/?>',
                         '', content, flags=re.IGNORECASE)

    # 6. Fix og:type
    if meta.get("og_type"):
        og_type_tag = f'<meta property="og:type" content="{meta["og_type"]}">'
        content, n = re.subn(r'<meta\s+property=["\']og:type["\'][^>]*/?>',
                              og_type_tag, content, count=1, flags=re.IGNORECASE)
        if n == 0:
            content = content.replace("<!-- Open Graph", f'{og_type_tag}\n    <!-- Open Graph', 1)

    # 7. Fix og:url
    if meta.get("canonical") and meta.get("og_type"):
        og_url_tag = f'<meta property="og:url" content="{meta["canonical"]}">'
        content, n = re.subn(r'<meta\s+property=["\']og:url["\'][^>]*/?>',
                              og_url_tag, content, count=1, flags=re.IGNORECASE)
        if n == 0:
            pass  # Will be added next time

    # 8. Fix og:title
    if meta.get("og_title"):
        og_title_tag = f'<meta property="og:title" content="{meta["og_title"]}">'
        content, n = re.subn(r'<meta\s+property=["\']og:title["\'][^>]*/?>',
                              og_title_tag, content, count=1, flags=re.IGNORECASE)
        if n == 0:
            content = content.replace('<meta property="og:url"', f'{og_title_tag}\n    <meta property="og:url"', 1)

    # 9. Fix og:description
    if meta.get("og_desc"):
        og_desc_tag = f'<meta property="og:description" content="{meta["og_desc"]}">'
        content, n = re.subn(r'<meta\s+property=["\']og:description["\'][^>]*/?>',
                              og_desc_tag, content, count=1, flags=re.IGNORECASE)

    # 10. Add/fix og:site_name
    if meta.get("og_type"):
        og_site_tag = '<meta property="og:site_name" content="SEO Error Auditor">'
        if 'og:site_name' not in content:
            content = content.replace('<meta property="og:image"',
                                      f'{og_site_tag}\n    <meta property="og:image"', 1)

    # 11. Fix twitter:title and twitter:description
    if meta.get("og_title"):
        tw_title_tag = f'<meta name="twitter:title" content="{meta["og_title"]}">'
        content, n = re.subn(r'<meta\s+name=["\']twitter:title["\'][^>]*/?>',
                              tw_title_tag, content, count=1, flags=re.IGNORECASE)
        if n == 0:
            content = content.replace('<meta name="twitter:card"',
                                      f'{tw_title_tag}\n    <meta name="twitter:card"', 1)
    if meta.get("og_desc"):
        tw_desc_tag = f'<meta name="twitter:description" content="{meta["og_desc"]}">'
        content, n = re.subn(r'<meta\s+name=["\']twitter:description["\'][^>]*/?>',
                              tw_desc_tag, content, count=1, flags=re.IGNORECASE)
        if n == 0:
            content = content.replace('<meta name="twitter:image"',
                                      f'{tw_desc_tag}\n    <meta name="twitter:image"', 1)

    # 12. Bump CSS version
    content = re.sub(r'/style\.css\?v=\d+', f'/style.css?v={CSS_VER}', content)
    content = re.sub(r'/app\.js\?v=\d+',   f'/app.js?v={CSS_VER}',    content)

    # 13. Add homepage schema if needed
    if filename == "index.html" and meta.get("schema"):
        schema_json = json.dumps(HOMEPAGE_SCHEMA, ensure_ascii=False)
        schema_tag  = f'<script type="application/ld+json">{schema_json}</script>'
        if 'application/ld+json' not in content:
            content = content.replace('</head>', f'    {schema_tag}\n</head>', 1)
        elif '"@type": "WebSite"' not in content:
            # Replace existing lone schema
            content = re.sub(r'<script type="application/ld\+json">.*?</script>',
                             schema_tag, content, count=1, flags=re.DOTALL)

    fp.write_text(content, encoding="utf-8")
    updated_files.append(filename)
    print(f"  UPDATED: {filename}")

print(f"\nTotal updated: {len(updated_files)} files")
print("Done — CSS/JS bumped to v=" + CSS_VER)
