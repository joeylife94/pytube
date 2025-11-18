"""
간단한 데모: 사용자가 URL을 입력하면 다운로드하는 인터랙티브 스크립트
"""

from downloader_manager import DownloaderManager
import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def main():
    print("\n" + "="*70)
    print("  YouTube Downloader - DownloaderManager")
    print("="*70)
    
    print("\n사용 가능한 모드:")
    print("  1. video       - 비디오 다운로드 (MP4)")
    print("  2. mp3         - 오디오 추출 + MP3 변환")
    print("  3. video_subs  - 비디오 + 자막")
    print("  4. subs_only   - 자막만 (비디오 스킵)")
    
    # 사용자 입력
    url = input("\n\nYouTube URL을 입력하세요: ").strip()
    
    if not url:
        print("❌ URL이 입력되지 않았습니다.")
        return
    
    mode_input = input("모드를 선택하세요 (1-4, 기본값=1): ").strip()
    
    mode_map = {
        "1": "video",
        "2": "mp3",
        "3": "video_subs",
        "4": "subs_only",
        "": "video"
    }
    
    mode = mode_map.get(mode_input, "video")
    
    print(f"\n📥 다운로드 시작...")
    print(f"   URL: {url}")
    print(f"   모드: {mode}")
    
    # DownloaderManager 초기화
    manager = DownloaderManager(
        output_dir=f"downloads/{mode}",
        preferred_engine="yt-dlp",
        max_workers=1
    )
    
    # 다운로드 실행
    result = manager.download_single(url, mode=mode)
    
    print("\n" + "="*70)
    if result.success:
        print("✅ 다운로드 성공!")
        print(f"   파일: {result.file_path}")
        print(f"   엔진: {result.engine}")
    else:
        print("❌ 다운로드 실패!")
        print(f"   에러: {result.error}")
    print("="*70)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  사용자가 중단했습니다.")
    except Exception as e:
        print(f"\n❌ 에러: {str(e)}")
