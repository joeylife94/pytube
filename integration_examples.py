"""
Integration Example: Using DownloaderManager with existing pytube project
Shows how to integrate the new DownloaderManager into app.py or other modules.
"""

from downloader_manager import DownloaderManager, DownloadResult
from typing import List
import logging

logger = logging.getLogger(__name__)


class IntegratedDownloadService:
    """
    Service class that wraps DownloaderManager for use in the main application.
    Can be integrated into app.py, app_tkinter.py, or used standalone.
    """
    
    def __init__(self, output_dir: str = "downloads"):
        """
        Initialize the integrated download service.
        
        Args:
            output_dir: Base directory for downloads
        """
        self.output_dir = output_dir
        self.manager = DownloaderManager(
            output_dir=output_dir,
            preferred_engine="yt-dlp",  # Recommend yt-dlp for stability
            max_workers=3
        )
        logger.info(f"IntegratedDownloadService initialized with output_dir={output_dir}")
    
    def download_videos(self, urls: List[str], progress_callback=None) -> List[DownloadResult]:
        """
        Download multiple videos in batch.
        
        Args:
            urls: List of YouTube URLs
            progress_callback: Optional callback(current, total, url, status)
            
        Returns:
            List of DownloadResult objects
        """
        logger.info(f"Starting video download batch: {len(urls)} URLs")
        results = self.manager.download_batch(urls, mode="video")
        
        if progress_callback:
            for i, result in enumerate(results):
                status = "success" if result.success else "failed"
                progress_callback(i + 1, len(urls), result.url, status)
        
        return results
    
    def download_audio_mp3(self, urls: List[str], progress_callback=None) -> List[DownloadResult]:
        """
        Download and convert to MP3 in batch.
        
        Args:
            urls: List of YouTube URLs
            progress_callback: Optional callback(current, total, url, status)
            
        Returns:
            List of DownloadResult objects
        """
        logger.info(f"Starting MP3 download batch: {len(urls)} URLs")
        results = self.manager.download_batch(urls, mode="mp3")
        
        if progress_callback:
            for i, result in enumerate(results):
                status = "success" if result.success else "failed"
                progress_callback(i + 1, len(urls), result.url, status)
        
        return results
    
    def download_with_subtitles(self, urls: List[str], progress_callback=None) -> List[DownloadResult]:
        """
        Download videos with subtitles.
        
        Args:
            urls: List of YouTube URLs
            progress_callback: Optional callback(current, total, url, status)
            
        Returns:
            List of DownloadResult objects
        """
        logger.info(f"Starting video+subtitles download batch: {len(urls)} URLs")
        results = self.manager.download_batch(urls, mode="video_subs")
        
        if progress_callback:
            for i, result in enumerate(results):
                status = "success" if result.success else "failed"
                progress_callback(i + 1, len(urls), result.url, status)
        
        return results
    
    def download_subtitles_only(self, urls: List[str], progress_callback=None) -> List[DownloadResult]:
        """
        Download only subtitle files (skip video).
        
        Args:
            urls: List of YouTube URLs
            progress_callback: Optional callback(current, total, url, status)
            
        Returns:
            List of DownloadResult objects
        """
        logger.info(f"Starting subtitles-only download batch: {len(urls)} URLs")
        results = self.manager.download_batch(urls, mode="subs_only")
        
        if progress_callback:
            for i, result in enumerate(results):
                status = "success" if result.success else "failed"
                progress_callback(i + 1, len(urls), result.url, status)
        
        return results


# ============================================================================
# STREAMLIT INTEGRATION EXAMPLE
# ============================================================================

def streamlit_app_integration():
    """
    Example of how to integrate DownloaderManager into a Streamlit app.
    Add this to app.py.
    """
    import streamlit as st
    
    st.title("YouTube Downloader with Advanced Features")
    
    # Initialize service (use session state to persist)
    if 'download_service' not in st.session_state:
        st.session_state.download_service = IntegratedDownloadService(output_dir="downloads")
    
    service = st.session_state.download_service
    
    # URL input (multi-line for batch)
    urls_text = st.text_area(
        "Enter YouTube URLs (one per line):",
        height=150,
        placeholder="https://youtu.be/...\nhttps://youtu.be/..."
    )
    
    # Parse URLs
    urls = [url.strip() for url in urls_text.split('\n') if url.strip()]
    
    # Download mode selection
    mode = st.selectbox(
        "Download Mode:",
        options=[
            "Video (MP4)",
            "Audio (MP3)",
            "Video + Subtitles",
            "Subtitles Only"
        ]
    )
    
    # Download button
    if st.button("Start Download", disabled=not urls):
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        def progress_callback(current, total, url, status):
            progress_bar.progress(current / total)
            status_text.text(f"Processing {current}/{total}: {url} - {status}")
        
        # Execute download based on mode
        if mode == "Video (MP4)":
            results = service.download_videos(urls, progress_callback)
        elif mode == "Audio (MP3)":
            results = service.download_audio_mp3(urls, progress_callback)
        elif mode == "Video + Subtitles":
            results = service.download_with_subtitles(urls, progress_callback)
        else:  # Subtitles Only
            results = service.download_subtitles_only(urls, progress_callback)
        
        # Display results
        successful = [r for r in results if r.success]
        failed = [r for r in results if not r.success]
        
        st.success(f"✅ Completed: {len(successful)}/{len(urls)} successful")
        
        if successful:
            st.write("**Successfully downloaded:**")
            for result in successful:
                st.write(f"- {result.url}")
                st.write(f"  📁 {result.file_path}")
        
        if failed:
            st.error("**Failed downloads:**")
            for result in failed:
                st.write(f"- {result.url}")
                st.write(f"  ❌ {result.error}")


# ============================================================================
# TKINTER INTEGRATION EXAMPLE
# ============================================================================

def tkinter_app_integration():
    """
    Example of how to integrate DownloaderManager into a Tkinter app.
    Add this to app_tkinter.py.
    """
    import tkinter as tk
    from tkinter import ttk, scrolledtext, filedialog
    import threading
    
    class DownloaderGUI:
        def __init__(self, root):
            self.root = root
            self.root.title("YouTube Downloader")
            self.service = IntegratedDownloadService()
            
            # URL input
            ttk.Label(root, text="URLs (one per line):").pack(pady=5)
            self.url_text = scrolledtext.ScrolledText(root, height=10, width=60)
            self.url_text.pack(pady=5)
            
            # Mode selection
            ttk.Label(root, text="Download Mode:").pack(pady=5)
            self.mode_var = tk.StringVar(value="video")
            modes = [
                ("Video (MP4)", "video"),
                ("Audio (MP3)", "mp3"),
                ("Video + Subtitles", "video_subs"),
                ("Subtitles Only", "subs_only")
            ]
            for label, value in modes:
                ttk.Radiobutton(
                    root, text=label, variable=self.mode_var, value=value
                ).pack(anchor=tk.W, padx=20)
            
            # Download button
            self.download_btn = ttk.Button(
                root, text="Start Download", command=self.start_download
            )
            self.download_btn.pack(pady=10)
            
            # Progress
            self.progress = ttk.Progressbar(root, length=400, mode='determinate')
            self.progress.pack(pady=5)
            
            # Status
            self.status_label = ttk.Label(root, text="Ready")
            self.status_label.pack(pady=5)
            
            # Results
            self.result_text = scrolledtext.ScrolledText(root, height=10, width=60)
            self.result_text.pack(pady=5)
        
        def start_download(self):
            """Start download in background thread"""
            urls = [u.strip() for u in self.url_text.get("1.0", tk.END).split('\n') if u.strip()]
            
            if not urls:
                self.result_text.insert(tk.END, "❌ No URLs provided\n")
                return
            
            # Disable button during download
            self.download_btn.config(state='disabled')
            self.result_text.delete("1.0", tk.END)
            
            # Run in background thread
            thread = threading.Thread(target=self._download_worker, args=(urls,))
            thread.daemon = True
            thread.start()
        
        def _download_worker(self, urls):
            """Background download worker"""
            mode = self.mode_var.get()
            
            def progress_callback(current, total, url, status):
                progress_pct = (current / total) * 100
                self.progress['value'] = progress_pct
                self.status_label.config(text=f"Processing {current}/{total}: {status}")
                self.root.update_idletasks()
            
            # Execute download
            mode_map = {
                "video": self.service.download_videos,
                "mp3": self.service.download_audio_mp3,
                "video_subs": self.service.download_with_subtitles,
                "subs_only": self.service.download_subtitles_only
            }
            
            results = mode_map[mode](urls, progress_callback)
            
            # Display results
            successful = [r for r in results if r.success]
            failed = [r for r in results if not r.success]
            
            self.result_text.insert(tk.END, f"✅ Completed: {len(successful)}/{len(urls)}\n\n")
            
            if successful:
                self.result_text.insert(tk.END, "Successfully downloaded:\n")
                for result in successful:
                    self.result_text.insert(tk.END, f"  ✓ {result.url}\n")
                    self.result_text.insert(tk.END, f"    📁 {result.file_path}\n")
            
            if failed:
                self.result_text.insert(tk.END, "\nFailed:\n")
                for result in failed:
                    self.result_text.insert(tk.END, f"  ✗ {result.url}\n")
                    self.result_text.insert(tk.END, f"    ❌ {result.error}\n")
            
            # Re-enable button
            self.download_btn.config(state='normal')
            self.status_label.config(text="Complete!")
    
    # Run the GUI
    root = tk.Tk()
    app = DownloaderGUI(root)
    root.mainloop()


# ============================================================================
# CLI INTEGRATION EXAMPLE
# ============================================================================

def cli_integration():
    """
    Command-line interface example.
    Can be run standalone or integrated into existing CLI tools.
    """
    import argparse
    
    parser = argparse.ArgumentParser(description="YouTube Downloader CLI")
    parser.add_argument('urls', nargs='+', help='YouTube URLs to download')
    parser.add_argument(
        '--mode',
        choices=['video', 'mp3', 'video_subs', 'subs_only'],
        default='video',
        help='Download mode'
    )
    parser.add_argument(
        '--output',
        default='downloads',
        help='Output directory'
    )
    parser.add_argument(
        '--workers',
        type=int,
        default=3,
        help='Number of concurrent downloads'
    )
    
    args = parser.parse_args()
    
    # Initialize manager
    manager = DownloaderManager(
        output_dir=args.output,
        preferred_engine="yt-dlp",
        max_workers=args.workers
    )
    
    # Download
    print(f"📥 Downloading {len(args.urls)} URLs in '{args.mode}' mode...")
    results = manager.download_batch(args.urls, mode=args.mode)
    
    # Results
    successful = [r for r in results if r.success]
    failed = [r for r in results if not r.success]
    
    print(f"\n✅ Success: {len(successful)}/{len(args.urls)}")
    
    if successful:
        print("\nDownloaded files:")
        for result in successful:
            print(f"  📁 {result.file_path}")
    
    if failed:
        print("\n❌ Failed:")
        for result in failed:
            print(f"  {result.url}: {result.error}")
    
    return 0 if len(failed) == 0 else 1


# ============================================================================
# USAGE EXAMPLES
# ============================================================================

if __name__ == "__main__":
    print("Integration Examples for DownloaderManager\n")
    print("=" * 70)
    
    # Example 1: Simple service usage
    print("\n1. Simple Service Usage:")
    service = IntegratedDownloadService(output_dir="downloads/test")
    
    test_urls = ["https://www.youtube.com/watch?v=dQw4w9WgXcQ"]
    
    def simple_progress(current, total, url, status):
        print(f"  [{current}/{total}] {url}: {status}")
    
    results = service.download_videos(test_urls, progress_callback=simple_progress)
    print(f"  Result: {results[0].success}")
    
    # Example 2: CLI mode
    print("\n2. CLI Integration:")
    print("  Run: python integration_examples.py https://youtu.be/... --mode mp3")
    
    # Example 3: GUI modes
    print("\n3. GUI Integration:")
    print("  - Streamlit: See streamlit_app_integration()")
    print("  - Tkinter: See tkinter_app_integration()")
    
    print("\n" + "=" * 70)
    print("Integration examples ready. See function docstrings for details.")
