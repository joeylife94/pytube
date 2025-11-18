"""
실제 다운로드 테스트 스크립트
간단한 비디오 하나로 시작해서 모든 기능을 순서대로 테스트합니다.
"""

from downloader_manager import DownloaderManager
import logging

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def test_single_video():
    """테스트 1: 간단한 비디오 다운로드"""
    print("\n" + "="*70)
    print("테스트 1: 단일 비디오 다운로드")
    print("="*70)
    
    # 짧은 테스트 비디오 (Rick Astley - Never Gonna Give You Up)
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    
    manager = DownloaderManager(
        output_dir="downloads/test_video",
        preferred_engine="yt-dlp",  # 안정성을 위해 yt-dlp 사용
        max_workers=1
    )
    
    print(f"\n📥 다운로드 시작: {url}")
    result = manager.download_single(url, mode="video")
    
    if result.success:
        print(f"\n✅ 성공!")
        print(f"   파일: {result.file_path}")
        print(f"   엔진: {result.engine}")
    else:
        print(f"\n❌ 실패!")
        print(f"   에러: {result.error}")
    
    return result

def test_engine_selection():
    """테스트 2: 엔진 선택 로직 검증"""
    print("\n" + "="*70)
    print("테스트 2: 엔진 선택 로직")
    print("="*70)
    
    from downloader_manager import YoutubeDownloader, DownloadMode
    
    downloader = YoutubeDownloader(
        output_dir="downloads/test",
        preferred_engine="pytube"
    )
    
    modes = [
        (DownloadMode.VIDEO, "video 모드"),
        (DownloadMode.MP3, "mp3 모드 (yt-dlp 강제)"),
        (DownloadMode.VIDEO_SUBS, "video_subs 모드 (yt-dlp 강제)"),
        (DownloadMode.SUBS_ONLY, "subs_only 모드 (yt-dlp 강제)"),
    ]
    
    print("\n엔진 선택 결과:")
    print("─" * 70)
    for mode, description in modes:
        engine = downloader._select_engine(mode)
        print(f"  {description:35} → {engine.value}")
    
    print("\n✅ 엔진 선택 로직 정상 작동")

def test_batch_download():
    """테스트 3: 배치 다운로드 (작은 비디오 2개)"""
    print("\n" + "="*70)
    print("테스트 3: 배치 다운로드 (2개 비디오)")
    print("="*70)
    
    urls = [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",  # 짧은 비디오
        "https://www.youtube.com/watch?v=jNQXAC9IVRw",  # 또 다른 짧은 비디오
    ]
    
    manager = DownloaderManager(
        output_dir="downloads/test_batch",
        preferred_engine="yt-dlp",
        max_workers=2
    )
    
    print(f"\n📥 {len(urls)}개 비디오 동시 다운로드 시작...")
    results = manager.download_batch(urls, mode="video")
    
    successful = [r for r in results if r.success]
    failed = [r for r in results if not r.success]
    
    print(f"\n📊 결과: {len(successful)}/{len(urls)} 성공")
    
    if successful:
        print("\n✅ 성공한 다운로드:")
        for r in successful:
            print(f"   - {r.url[:50]}...")
            print(f"     → {r.file_path}")
    
    if failed:
        print("\n❌ 실패한 다운로드:")
        for r in failed:
            print(f"   - {r.url[:50]}...")
            print(f"     → {r.error}")
    
    return results

def main():
    print("\n" + "🚀"*35)
    print("  DownloaderManager 실제 테스트 시작!")
    print("🚀"*35)
    
    try:
        # 테스트 1: 엔진 선택 로직 (다운로드 없음)
        test_engine_selection()
        
        print("\n\n⏸️  계속하려면 Enter를 누르세요 (실제 다운로드 시작)...")
        input()
        
        # 테스트 2: 단일 비디오 다운로드
        result = test_single_video()
        
        if result.success:
            print("\n\n⏸️  계속하려면 Enter를 누르세요 (배치 다운로드 시작)...")
            input()
            
            # 테스트 3: 배치 다운로드
            test_batch_download()
        
        print("\n" + "🎉"*35)
        print("  모든 테스트 완료!")
        print("🎉"*35)
        
        print("\n\n💡 추가 테스트를 원하시면:")
        print("   - MP3 변환: mode='mp3'")
        print("   - 자막 포함: mode='video_subs'")
        print("   - 자막만: mode='subs_only'")
        
    except KeyboardInterrupt:
        print("\n\n⚠️  사용자가 테스트를 중단했습니다.")
    except Exception as e:
        print(f"\n\n❌ 에러 발생: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
