import csv
import os
import threading

class CrawlLogger:
    """
    A thread-safe logger to record crawl details to crawl_log.csv and all_urls.csv.
    """
    def __init__(self, output_dir):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        
        self.crawl_log_path = os.path.join(output_dir, "crawl_log.csv")
        self.all_urls_path = os.path.join(output_dir, "all_urls.csv")
        
        self.lock = threading.Lock()
        
        # Initialize files with headers
        self._initialize_files()

    def _initialize_files(self):
        """Initializes the CSV files and writes headers if they do not exist."""
        with self.lock:
            # Initialize crawl_log.csv
            if not os.path.exists(self.crawl_log_path) or os.path.getsize(self.crawl_log_path) == 0:
                with open(self.crawl_log_path, mode='w', encoding='utf-8', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow(["URL", "Status Code", "Redirect", "Canonical", "Title", "Error"])
            
            # Initialize all_urls.csv
            if not os.path.exists(self.all_urls_path) or os.path.getsize(self.all_urls_path) == 0:
                with open(self.all_urls_path, mode='w', encoding='utf-8', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow(["URL"])

    def log_crawled(self, url, status_code, redirect_to, canonical_url, title, error_message):
        """
        Thread-safe logging of crawl status and metadata to crawl_log.csv.
        """
        with self.lock:
            try:
                with open(self.crawl_log_path, mode='a', encoding='utf-8', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow([
                        url,
                        status_code if status_code is not None else '',
                        redirect_to if redirect_to else '',
                        canonical_url if canonical_url else '',
                        title if title else '',
                        error_message if error_message else ''
                    ])
            except Exception as e:
                print(f"Error writing to crawl_log.csv: {e}")

    def log_successful_url(self, url):
        """
        Thread-safe logging of a verified successful URL to all_urls.csv.
        """
        with self.lock:
            try:
                with open(self.all_urls_path, mode='a', encoding='utf-8', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow([url])
            except Exception as e:
                print(f"Error writing to all_urls.csv: {e}")
