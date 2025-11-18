"""
Quick Start Demo - All 4 Features of DownloaderManager
Run this script to see all capabilities in action.
"""

from downloader_manager import DownloaderManager
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s: %(message)s'
)

def print_header(title):
    """Print a formatted section header"""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80 + "\n")


def print_results(results):
    """Print download results in a formatted way"""
    successful = [r for r in results if r.success]
    failed = [r for r in results if not r.success]
    
    print(f"\n📊 Summary: {len(successful)}/{len(results)} successful\n")
    
    if successful:
        print("✅ Successfully downloaded:")
        for result in successful:
            print(f"   {result.url}")
            print(f"   → {result.file_path}")
            print(f"   (Engine: {result.engine})\n")
    
    if failed:
        print("❌ Failed downloads:")
        for result in failed:
            print(f"   {result.url}")
            print(f"   → Error: {result.error}\n")


def demo_feature_1_batch_video():
    """
    FEATURE 1: Batch Video Download
    Downloads multiple videos concurrently using ThreadPoolExecutor
    """
    print_header("FEATURE 1: Batch Video Download (Concurrent)")
    
    # Test URLs (replace with real ones for actual downloads)
    urls = [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://www.youtube.com/watch?v=jNQXAC9IVRw",
        "https://www.youtube.com/watch?v=9bZkp7q19f0",
    ]
    
    print(f"📥 Downloading {len(urls)} videos concurrently (max 3 workers)...")
    print(f"   Engine preference: pytube (for speed)\n")
    
    manager = DownloaderManager(
        output_dir="downloads/demo_batch_video",
        preferred_engine="pytube",
        max_workers=3  # 3 concurrent downloads
    )
    
    # Download all at once
    results = manager.download_batch(urls, mode="video")
    
    print_results(results)
    
    print("💡 Key Points:")
    print("   - All downloads run concurrently (ThreadPoolExecutor)")
    print("   - One failure doesn't crash the batch")
    print("   - Used pytube for simple video downloads (faster)")


def demo_feature_2_mp3():
    """
    FEATURE 2: MP3 Audio Extraction
    Extracts audio and converts to MP3 using ffmpeg
    """
    print_header("FEATURE 2: MP3 Audio Extraction (Auto-forces yt-dlp)")
    
    urls = [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    ]
    
    print(f"🎵 Converting to MP3 (requires ffmpeg)...")
    print(f"   Preferred engine: pytube (will be overridden!)\n")
    
    manager = DownloaderManager(
        output_dir="downloads/demo_mp3",
        preferred_engine="pytube",  # Will be FORCED to yt-dlp
        max_workers=2
    )
    
    # Download as MP3
    results = manager.download_batch(urls, mode="mp3")
    
    print_results(results)
    
    print("💡 Key Points:")
    print("   - MP3 mode ALWAYS uses yt-dlp (pytube can't convert)")
    print("   - Uses ffmpeg for audio extraction + conversion")
    print("   - Preferred engine is automatically overridden")
    print(f"   - Engine used: {results[0].engine if results else 'N/A'}")


def demo_feature_3_video_subs():
    """
    FEATURE 3: Video + Subtitles
    Downloads video AND best available subtitles
    """
    print_header("FEATURE 3: Video + Subtitles Download")
    
    urls = [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    ]
    
    print(f"📹 + 📝 Downloading video with subtitles...")
    print(f"   Priority: Manual EN/KO → Auto-generated EN/KO\n")
    
    manager = DownloaderManager(
        output_dir="downloads/demo_video_subs",
        preferred_engine="pytube",  # Will be FORCED to yt-dlp
        max_workers=2
    )
    
    # Download with subtitles
    result = manager.download_single(urls[0], mode="video_subs")
    
    print_results([result])
    
    print("💡 Key Points:")
    print("   - Downloads video + subtitle files")
    print("   - Prioritizes manual subtitles over auto-generated")
    print("   - Tries English and Korean (configurable)")
    print("   - Converts to .srt format for compatibility")
    print(f"   - Engine used: {result.engine}")


def demo_feature_4_subs_only():
    """
    FEATURE 4: Subtitles Only (No Video)
    Downloads ONLY subtitle files, skips video/audio
    """
    print_header("FEATURE 4: Subtitles Only (Skip Video)")
    
    urls = [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://www.youtube.com/watch?v=jNQXAC9IVRw",
    ]
    
    print(f"📝 Downloading ONLY subtitles (no video/audio)...")
    print(f"   Use case: Subtitle archives, translation projects\n")
    
    manager = DownloaderManager(
        output_dir="downloads/demo_subs_only",
        preferred_engine="pytube",  # Will be FORCED to yt-dlp
        max_workers=3
    )
    
    # Download only subtitles
    results = manager.download_batch(urls, mode="subs_only")
    
    print_results(results)
    
    print("💡 Key Points:")
    print("   - Skips video/audio download entirely (fast)")
    print("   - Only downloads .srt/.vtt files")
    print("   - Batch processing supported")
    print("   - Saves bandwidth and storage")
    print(f"   - Engine used: {results[0].engine if results else 'N/A'}")


def demo_engine_selection_logic():
    """
    Demonstrate the intelligent engine selection logic
    """
    print_header("BONUS: Intelligent Engine Selection")
    
    print("The system automatically selects the best engine:\n")
    
    print("┌─────────────────┬──────────────────┬──────────────────┐")
    print("│ Mode            │ User Preference  │ Actual Engine    │")
    print("├─────────────────┼──────────────────┼──────────────────┤")
    print("│ video           │ pytube           │ pytube           │")
    print("│ video           │ yt-dlp           │ yt-dlp           │")
    print("│ mp3             │ pytube (ignored) │ yt-dlp (FORCED)  │")
    print("│ video_subs      │ pytube (ignored) │ yt-dlp (FORCED)  │")
    print("│ subs_only       │ pytube (ignored) │ yt-dlp (FORCED)  │")
    print("└─────────────────┴──────────────────┴──────────────────┘")
    
    print("\n💡 Why force yt-dlp for MP3/subtitles?")
    print("   - pytube doesn't support MP3 conversion")
    print("   - pytube has unreliable subtitle handling")
    print("   - pytube can't skip video download")
    print("   - yt-dlp is designed for advanced features")


def main():
    """Run all feature demonstrations"""
    print("\n" + "🚀" * 40)
    print("  DOWNLOADER MANAGER - QUICK START DEMO")
    print("  Demonstrating all 4 core features")
    print("🚀" * 40)
    
    print("\n⚠️  NOTE: Set DEMO_MODE = False to run actual downloads")
    print("         (Currently in dry-run mode - showing logic only)\n")
    
    DEMO_MODE = True  # Set to False to run real downloads
    
    if DEMO_MODE:
        print("=" * 80)
        print("  DEMO MODE: Showing feature descriptions without downloading")
        print("=" * 80)
        
        # Just show what each feature does
        demo_engine_selection_logic()
        
        print("\n" + "=" * 80)
        print("  To run actual downloads:")
        print("  1. Set DEMO_MODE = False in this script")
        print("  2. Ensure ffmpeg is installed (for MP3 conversion)")
        print("  3. Run: python quick_start_demo.py")
        print("=" * 80)
        
    else:
        # Run actual downloads
        try:
            print("\n⏳ Running actual downloads...\n")
            
            # Feature 1: Batch video download
            demo_feature_1_batch_video()
            input("\nPress Enter to continue to Feature 2...")
            
            # Feature 2: MP3 conversion
            demo_feature_2_mp3()
            input("\nPress Enter to continue to Feature 3...")
            
            # Feature 3: Video + subtitles
            demo_feature_3_video_subs()
            input("\nPress Enter to continue to Feature 4...")
            
            # Feature 4: Subtitles only
            demo_feature_4_subs_only()
            
            print("\n" + "🎉" * 40)
            print("  ALL FEATURES DEMONSTRATED SUCCESSFULLY!")
            print("🎉" * 40)
            
        except KeyboardInterrupt:
            print("\n\n⚠️  Demo interrupted by user")
        except Exception as e:
            print(f"\n\n❌ Error during demo: {str(e)}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "=" * 80)
    print("  For more details, see:")
    print("  - downloader_manager.py (implementation)")
    print("  - DOWNLOADER_MANAGER_README.md (documentation)")
    print("  - test_downloader_manager.py (test suite)")
    print("  - integration_examples.py (Streamlit/Tkinter/CLI examples)")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()
