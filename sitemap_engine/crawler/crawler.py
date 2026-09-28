import queue
import threading
import time
import requests
import urllib.parse
import urllib3
from bs4 import BeautifulSoup

from sitemap_engine.crawler.robots import RobotsParser
from sitemap_engine.utils.helpers import normalize_url, is_internal, should_skip
from sitemap_engine.utils.logger import CrawlLogger

# Disable SSL warnings for verify=False requests
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class WebCrawler:
    def __init__(self, start_url, output_dir, max_threads=20, include_pdf=False, custom_excludes=None, stats_callback=None, log_callback=None):
        self.start_url = start_url
        self.output_dir = output_dir
        self.max_threads = max_threads
        self.include_pdf = include_pdf
        self.custom_excludes = custom_excludes or []
        self.stats_callback = stats_callback
        self.log_callback = log_callback
        
        # State tracking
        self.visited_urls = set()      # URLs fully processed (or failed)
        self.queued_urls = set()       # URLs that have been added to the queue
        self.successful_urls = set()   # Final URLs for the sitemap
        self.state_lock = threading.Lock()
        
        # Threading objects
        self.queue = queue.Queue()
        self.active_workers = 0
        self.active_workers_lock = threading.Lock()
        self.threads = []
        
        # Pause, Resume, Stop events
        self.pause_event = threading.Event()
        self.pause_event.set()  # Clear = paused, Set = running
        self.stop_event = threading.Event()
        
        # Logger
        self.logger = CrawlLogger(output_dir)
        
        # Robots Parser
        self.robots_parser = RobotsParser(start_url)
        
        # Performance/Requests
        self.session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(pool_connections=max_threads, pool_maxsize=max_threads, max_retries=0)
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)
        
        # Statistics
        self.start_time = None
        self.crawled_count = 0
        self.total_found = 0
        self.stats_lock = threading.Lock()
        
        # Track existing sitemap URLs if we merge them
        self.existing_sitemap_urls = set()

    def add_existing_sitemap_urls(self, urls):
        """Pre-populate the crawler's list of URLs from an existing sitemap."""
        for url in urls:
            normalized = normalize_url(url, self.start_url)
            if is_internal(normalized, self.start_url) and not should_skip(normalized, self.custom_excludes, self.include_pdf):
                with self.state_lock:
                    if normalized not in self.queued_urls:
                        self.queued_urls.add(normalized)
                        self.queue.put(normalized)
                        self.total_found += 1

    def _log_to_console(self, message):
        if self.log_callback:
            self.log_callback(message)
        else:
            print(message)

    def start(self):
        """Starts the crawling process."""
        self.start_time = time.time()
        self.stop_event.clear()
        self.pause_event.set()
        
        self._log_to_console("Initializing crawl...")
        
        # Fetch robots.txt first
        try:
            self.robots_parser.fetch(self.session)
            self._log_to_console("robots.txt rules loaded.")
        except Exception as e:
            self._log_to_console(f"Warning loading robots.txt: {e}")
            
        # Normalize and queue the starting URL if queue is empty
        normalized_start = normalize_url(self.start_url, self.start_url)
        with self.state_lock:
            if not self.queued_urls:
                self.queued_urls.add(normalized_start)
                self.queue.put(normalized_start)
                self.total_found = 1
                
        # Start worker threads
        for i in range(self.max_threads):
            t = threading.Thread(target=self._worker_loop, name=f"Worker-{i+1}")
            t.daemon = True
            t.start()
            self.threads.append(t)
            
        self._log_to_console(f"Started crawler with {self.max_threads} workers.")

    def pause(self):
        """Pauses the crawler."""
        self.pause_event.clear()
        self._log_to_console("Crawl paused.")

    def resume(self):
        """Resumes the crawler."""
        self.pause_event.set()
        self._log_to_console("Crawl resumed.")

    def stop(self):
        """Stops the crawler."""
        self.stop_event.set()
        self.pause_event.set()  # Unblock anyone waiting on pause
        
        # Clear the queue to let threads exit quickly
        try:
            while not self.queue.empty():
                self.queue.get_nowait()
                self.queue.task_done()
        except queue.Empty:
            pass
            
        self._log_to_console("Stopping crawler...")

    def is_finished(self):
        """Checks if the crawler is complete (queue empty, no active workers, or stopped)."""
        if self.stop_event.is_set():
            return True
        with self.active_workers_lock:
            return self.queue.empty() and self.active_workers == 0

    def _worker_loop(self):
        """Main loop executed by worker threads."""
        while not self.stop_event.is_set():
            # Wait if paused
            self.pause_event.wait()
            if self.stop_event.is_set():
                break
                
            try:
                # Wait for a URL with a timeout so we don't block indefinitely and can exit on stop/pause
                url = self.queue.get(timeout=1.0)
            except queue.Empty:
                # If queue is empty and no workers are active, we are done
                if self.is_finished():
                    break
                continue
                
            # Track active worker count
            with self.active_workers_lock:
                self.active_workers += 1
                
            try:
                self._crawl_url(url)
            except Exception as e:
                self._log_to_console(f"Unexpected worker error crawling {url}: {e}")
            finally:
                with self.active_workers_lock:
                    self.active_workers -= 1
                self.queue.task_done()
                
                # Check again if this was the last item
                if self.is_finished():
                    # Notify UI that we completed
                    self._update_stats()

    def _crawl_url(self, url):
        """Fetches and parses a single URL."""
        # Double check visited set
        with self.state_lock:
            if url in self.visited_urls:
                return
            self.visited_urls.add(url)

        # 1. Respect Robots.txt
        if not self.robots_parser.can_fetch(url):
            self._log_to_console(f"Skipped (Robots.txt): {url}")
            self.logger.log_crawled(url, None, None, None, None, "Blocked by robots.txt")
            with self.stats_lock:
                self.crawled_count += 1
            self._update_stats()
            return

        # 2. Fetch URL with Retry Logic
        response = None
        error_msg = None
        retries = 3
        backoff = 1.0
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html) AntigravitySitemapBot/1.0',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5'
        }
        
        for attempt in range(retries):
            if self.stop_event.is_set():
                return
            self.pause_event.wait()
            
            try:
                response = self.session.get(url, timeout=10, headers=headers, allow_redirects=True, verify=False)
                break
            except requests.exceptions.Timeout:
                error_msg = "Timeout (10s)"
            except requests.exceptions.SSLError:
                error_msg = "SSL Error"
            except requests.exceptions.ConnectionError:
                error_msg = "Connection Error"
            except Exception as e:
                error_msg = str(e)
                
            if attempt < retries - 1:
                time.sleep(backoff)
                backoff *= 2  # Exponential backoff
                
        # If all retries failed
        if response is None:
            self._log_to_console(f"Failed ({error_msg}): {url}")
            self.logger.log_crawled(url, None, None, None, None, error_msg)
            with self.stats_lock:
                self.crawled_count += 1
            self._update_stats()
            return

        final_url = response.url
        status_code = response.status_code
        
        # Handle non-200 responses
        if status_code != 200:
            self._log_to_console(f"HTTP {status_code}: {url}")
            self.logger.log_crawled(url, status_code, None, None, None, f"HTTP Error Status {status_code}")
            with self.stats_lock:
                self.crawled_count += 1
            self._update_stats()
            return

        # Check for redirects
        redirect_history = response.history
        redirect_url = None
        if redirect_history:
            redirect_url = final_url
            self._log_to_console(f"Redirected: {url} -> {final_url}")
            
            # If the final redirect destination is external, skip processing
            if not is_internal(final_url, self.start_url):
                self.logger.log_crawled(url, status_code, redirect_url, None, None, "Redirects to external domain")
                with self.stats_lock:
                    self.crawled_count += 1
                self._update_stats()
                return

        # 3. Parse HTML
        soup = None
        title = ""
        canonical_url = None
        
        # Don't parse non-HTML content (e.g. PDFs, images, etc.)
        content_type = response.headers.get('Content-Type', '').lower()
        if 'text/html' not in content_type:
            # If PDF and we allowed it
            if 'application/pdf' in content_type and self.include_pdf:
                with self.state_lock:
                    self.successful_urls.add(final_url)
                self.logger.log_crawled(url, status_code, redirect_url, None, "PDF File", None)
                self.logger.log_successful_url(final_url)
            else:
                self.logger.log_crawled(url, status_code, redirect_url, None, None, f"Non-HTML content: {content_type}")
                
            with self.stats_lock:
                self.crawled_count += 1
            self._update_stats()
            return
            
        try:
            soup = BeautifulSoup(response.text, 'html.parser')
            # Extract title
            if soup.title and soup.title.string:
                title = soup.title.string.strip()
        except Exception as e:
            self.logger.log_crawled(url, status_code, redirect_url, None, None, f"HTML parse error: {e}")
            with self.stats_lock:
                self.crawled_count += 1
            self._update_stats()
            return

        # Every 200 OK internal page is included in the XML sitemap
        with self.state_lock:
            self.successful_urls.add(final_url)
        self.logger.log_crawled(url, status_code, redirect_url, None, title, None)
        self.logger.log_successful_url(final_url)

        # 5. Extract links
        discovered_links = 0
        for anchor in soup.find_all('a', href=True):
            if self.stop_event.is_set():
                return
            href = anchor['href']
            
            # Normalize link
            normalized_link = normalize_url(href, final_url)
            
            # Validate link (internal, not skipped, not already in queued list)
            if is_internal(normalized_link, self.start_url):
                if not should_skip(normalized_link, self.custom_excludes, self.include_pdf):
                    with self.state_lock:
                        if normalized_link not in self.queued_urls:
                            self.queued_urls.add(normalized_link)
                            self.queue.put(normalized_link)
                            self.total_found += 1
                            discovered_links += 1

        self._log_to_console(f"Crawled: {url} | Found {discovered_links} links")
        
        with self.stats_lock:
            self.crawled_count += 1
        self._update_stats()

    def _update_stats(self):
        """Calculates and reports crawl statistics to the GUI callback."""
        if not self.stats_callback:
            return
            
        with self.stats_lock:
            elapsed = time.time() - self.start_time if self.start_time else 0
            speed = self.crawled_count / elapsed if elapsed > 0 else 0
            
            # Calculate remaining URLs
            queue_len = self.queue.qsize()
            
            # Calculate ETA
            if speed > 0:
                eta = queue_len / speed
            else:
                eta = float('inf')
                
            self.stats_callback({
                'found': self.total_found,
                'crawled': self.crawled_count,
                'speed': speed,
                'elapsed': elapsed,
                'eta': eta,
                'queue_len': queue_len,
                'finished': self.is_finished()
            })
