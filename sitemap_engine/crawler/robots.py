import urllib.parse
import urllib.robotparser
import requests

class RobotsParser:
    """
    Fetches and parses robots.txt for a website domain, checking if URLs can be crawled.
    """
    def __init__(self, base_url, user_agent="*"):
        self.base_url = base_url
        self.user_agent = user_agent
        self.parser = urllib.robotparser.RobotFileParser()
        self.parsed = False
        
        # Determine the robots.txt URL
        parsed_base = urllib.parse.urlparse(base_url)
        self.robots_url = f"{parsed_base.scheme}://{parsed_base.netloc}/robots.txt"

    def fetch(self, session=None, timeout=10):
        """
        Fetches and parses robots.txt using the provided requests session.
        If robots.txt is missing (404) or fails, we default to allowing everything.
        """
        if self.parsed:
            return
            
        # Use provided session or create a temporary one
        req_session = session if session else requests.Session()
        headers = {'User-Agent': self.user_agent}
        
        try:
            response = req_session.get(self.robots_url, headers=headers, timeout=timeout, verify=False)
            if response.status_code == 200:
                # Parse the lines of the robots.txt file
                lines = response.text.splitlines()
                self.parser.parse(lines)
            elif response.status_code in (401, 403):
                # If forbidden, disallow everything according to standard interpretation,
                # but for crawling we might want to allow. Let's make it standard: disallow if strictly forbidden,
                # or just block all. Let's follow standard: if 403, disallow all.
                # Actually, some sites block robots.txt with 403 due to Cloudflare, but we want to crawl them.
                # Let's log it and allow everything or disallow? Usually, if robots.txt returns 403,
                # a strict crawler blocks everything. But since users want to crawl, we'll allow but log a warning, 
                # or treat as allowed. Let's write a standard parser fallback.
                # Let's set disallow all if 401/403.
                self.parser.disallow_all = True
            else:
                # 404 or other errors mean allow all
                self.parser.allow_all = True
        except Exception as e:
            # On connection error, timeout or SSL error, allow all as fallback
            print(f"Error fetching robots.txt: {e}. Defaulting to allow all.")
            self.parser.allow_all = True
            
        self.parsed = True

    def can_fetch(self, url):
        """
        Checks if the URL is allowed to be crawled according to robots.txt rules.
        """
        if not self.parsed:
            self.fetch()
        return self.parser.can_fetch(self.user_agent, url)
