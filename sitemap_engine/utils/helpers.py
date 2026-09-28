import urllib.parse
import os

def normalize_url(url, base_url):
    """
    Normalizes a URL relative to a base URL:
    - Resolves relative URLs to absolute.
    - Strips fragment identifiers.
    - Sorts query parameters.
    - Strips trailing slashes from path where appropriate (excluding the root).
    """
    # 1. Resolve relative URLs
    absolute_url = urllib.parse.urljoin(base_url, url)
    
    # 2. Parse URL components
    parsed = urllib.parse.urlparse(absolute_url)
    
    # Force lowercase scheme and netloc
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    
    # 3. Clean path
    path = parsed.path
    if path:
        # Standardize path: replace multiple slashes, resolve relative references (like /./ or /../)
        path = os.path.normpath(path).replace('\\', '/')
        if parsed.path.endswith('/') and not path.endswith('/'):
            path += '/'
        # Normpath can strip leading slash on windows sometimes, ensure it starts with /
        if not path.startswith('/'):
            path = '/' + path
            
        # Strip trailing slash except for root directory to avoid duplicates
        if path != '/' and path.endswith('/'):
            path = path[:-1]
    else:
        path = '/'
        
    # 4. Sort query parameters to avoid duplicates like ?a=1&b=2 and ?b=2&a=1
    query_params = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    sorted_query = urllib.parse.urlencode(sorted(query_params)) if query_params else ''
    
    # Rebuild URL without fragment
    normalized = urllib.parse.urlunparse((
        scheme,
        netloc,
        path,
        parsed.params,
        sorted_query,
        '' # Strip fragment
    ))
    
    return normalized

def is_internal(url, base_url):
    """
    Determines if a URL is internal relative to a base URL.
    Compares domain (netloc) ignoring 'www.' prefix.
    """
    try:
        parsed_url = urllib.parse.urlparse(url)
        parsed_base = urllib.parse.urlparse(base_url)
        
        netloc_url = parsed_url.netloc.lower()
        netloc_base = parsed_base.netloc.lower()
        
        # Remove 'www.' prefix for comparison
        if netloc_url.startswith('www.'):
            netloc_url = netloc_url[4:]
        if netloc_base.startswith('www.'):
            netloc_base = netloc_base[4:]
            
        return netloc_url == netloc_base
    except Exception:
        return False

def should_skip(url, exclude_paths=None, include_pdf=False):
    """
    Decides if a URL should be skipped based on its extension, protocol, 
    or path patterns.
    """
    if not url:
        return True
        
    parsed = urllib.parse.urlparse(url)
    scheme = parsed.scheme.lower()
    
    # 1. Skip non-http/https protocols
    if scheme not in ('http', 'https'):
        return True
        
    # 2. Extract path for extension checking
    path = parsed.path.lower()
    
    # Check standard file extensions to skip
    skip_extensions = {
        # Style & Script
        '.css', '.js',
        # Images
        '.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico', '.webp', '.bmp', '.tiff',
        # Media / Video / Audio
        '.mp4', '.mp3', '.wav', '.avi', '.mov', '.flv', '.wmv', '.m4a', '.ogg',
        # Archives & Documents
        '.zip', '.tar', '.gz', '.rar', '.7z', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
        # System
        '.exe', '.dll', '.so', '.dmg'
    }
    
    # If include_pdf is False, skip pdf files
    if not include_pdf:
        skip_extensions.add('.pdf')
        
    _, ext = os.path.splitext(path)
    if ext in skip_extensions:
        return True
        
    # 3. Exclude specific path patterns (e.g. /wp-admin/, /search/)
    if exclude_paths:
        for pattern in exclude_paths:
            pattern = pattern.strip().lower()
            if not pattern:
                continue
            # If pattern matches anywhere in the path, skip
            if pattern in path:
                return True
                
    return False
