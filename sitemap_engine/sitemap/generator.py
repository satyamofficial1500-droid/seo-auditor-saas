import os
import datetime
import urllib.parse

class SitemapGenerator:
    """
    Generates Google-compliant XML sitemaps and split indexes.
    Splits at 50,000 URLs or 50MB file size.
    """
    def __init__(self, urls, base_url, output_dir):
        self.urls = sorted(list(urls))
        self.base_url = base_url
        self.output_dir = output_dir
        
        # Google Sitemap Limits
        self.MAX_URLS = 50000
        self.MAX_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB
        
        # Formatting defaults
        self.today = datetime.date.today().isoformat()
        self.changefreq = "weekly"

    def calculate_priority(self, url):
        """
        Dynamically calculates priority based on path depth:
        - Root/index: 1.0
        - Depth 1 (e.g., /about): 0.8
        - Depth 2 (e.g., /about/contact): 0.6
        - Depth 3+: 0.5
        """
        try:
            parsed = urllib.parse.urlparse(url)
            path = parsed.path.strip('/')
            if not path:
                return "1.0"
                
            parts = [p for p in path.split('/') if p]
            depth = len(parts)
            
            if depth == 1:
                return "0.8"
            elif depth == 2:
                return "0.6"
            else:
                return "0.5"
        except Exception:
            return "0.5"

    def generate(self):
        """
        Generates sitemap files. Writes sitemap.xml directly if limits are not exceeded,
        otherwise writes sitemap1.xml, sitemap2.xml, etc., and a sitemap_index.xml.
        """
        if not self.urls:
            return [], []

        os.makedirs(self.output_dir, exist_ok=True)
        
        # Decide if we need to split based on URL count
        needs_split = len(self.urls) > self.MAX_URLS
        
        sitemaps_created = []
        
        if not needs_split:
            # Try building a single sitemap first, then check size limit
            xml_content = self._build_sitemap_xml(self.urls)
            xml_bytes = xml_content.encode('utf-8')
            
            if len(xml_bytes) <= self.MAX_SIZE_BYTES:
                sitemap_path = os.path.join(self.output_dir, "sitemap.xml")
                with open(sitemap_path, "wb") as f:
                    f.write(xml_bytes)
                sitemaps_created.append("sitemap.xml")
                return sitemaps_created, []
            else:
                # Exceeded 50MB, we must split
                needs_split = True
                
        # Split logic: chunk the URLs and write separate sitemaps
        current_chunk = []
        current_chunk_size = 0
        sitemap_idx = 1
        
        # Helper to get base size of XML structure
        header_len = len(self._get_header().encode('utf-8'))
        footer_len = len(self._get_footer().encode('utf-8'))
        
        for url in self.urls:
            url_xml = self._build_url_node(url)
            url_xml_bytes_len = len(url_xml.encode('utf-8'))
            
            # Check if this URL would violate the 50,000 count or 50MB size limit
            if (len(current_chunk) >= self.MAX_URLS or 
                (header_len + current_chunk_size + url_xml_bytes_len + footer_len) > self.MAX_SIZE_BYTES):
                
                # Write current chunk
                filename = f"sitemap{sitemap_idx}.xml"
                self._write_chunk(filename, current_chunk)
                sitemaps_created.append(filename)
                
                # Reset for next chunk
                sitemap_idx += 1
                current_chunk = [url]
                current_chunk_size = url_xml_bytes_len
            else:
                current_chunk.append(url)
                current_chunk_size += url_xml_bytes_len
                
        # Write any remaining URLs
        if current_chunk:
            filename = f"sitemap{sitemap_idx}.xml"
            self._write_chunk(filename, current_chunk)
            sitemaps_created.append(filename)
            
        # Write the Sitemap Index
        index_filename = "sitemap_index.xml"
        self._write_sitemap_index(index_filename, sitemaps_created)
        
        return sitemaps_created, [index_filename]

    def _write_chunk(self, filename, url_list):
        path = os.path.join(self.output_dir, filename)
        content = self._build_sitemap_xml(url_list)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    def _get_header(self):
        return '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'

    def _get_footer(self):
        return '</urlset>\n'

    def _build_url_node(self, url):
        priority = self.calculate_priority(url)
        return (
            f"  <url>\n"
            f"    <loc>{url}</loc>\n"
            f"    <lastmod>{self.today}</lastmod>\n"
            f"    <changefreq>{self.changefreq}</changefreq>\n"
            f"    <priority>{priority}</priority>\n"
            f"  </url>\n"
        )

    def _build_sitemap_xml(self, url_list):
        parts = [self._get_header()]
        for url in url_list:
            parts.append(self._build_url_node(url))
        parts.append(self._get_footer())
        return "".join(parts)

    def _write_sitemap_index(self, index_filename, sitemap_filenames):
        """Writes the sitemap_index.xml file."""
        # Ensure we have a trailing slash for base_url
        parsed_base = urllib.parse.urlparse(self.base_url)
        base_sitemap_dir = f"{parsed_base.scheme}://{parsed_base.netloc}/"
        
        parts = [
            '<?xml version="1.0" encoding="UTF-8"?>\n',
            '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        ]
        
        for filename in sitemap_filenames:
            sitemap_url = urllib.parse.urljoin(base_sitemap_dir, filename)
            parts.append(
                f"  <sitemap>\n"
                f"    <loc>{sitemap_url}</loc>\n"
                f"    <lastmod>{self.today}</lastmod>\n"
                f"  </sitemap>\n"
            )
            
        parts.append('</sitemapindex>\n')
        
        index_path = os.path.join(self.output_dir, index_filename)
        with open(index_path, "w", encoding="utf-8") as f:
            f.write("".join(parts))
