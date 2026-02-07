from pytube_helper import extract_playlist_urls, get_video_streams

playlist = 'https://www.youtube.com/playlist?list=PLF9mJC4RrjIhS4MMm0x72-qWEn1LRvPuW'
print('Playlist URL:', playlist)
urls = extract_playlist_urls(playlist)
print('COUNT', len(urls))
if urls:
    first = urls[0]
    print('First URL:', first)
    try:
        streams = get_video_streams(first)
        print('get_video_streams returned type:', type(streams))
        if isinstance(streams, dict):
            print('backend:', streams.get('backend'))
            print('title:', streams.get('title'))
        else:
            print('title:', streams.get('title'))
            print('progressive count:', len(streams.get('progressive', [])))
            print('audio count:', len(streams.get('audio', [])))
    except Exception as e:
        print('get_video_streams raised:', e)
else:
    print('No URLs extracted')
