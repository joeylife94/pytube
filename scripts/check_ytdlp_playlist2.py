import yt_dlp
url = 'https://www.youtube.com/watch?v=8E4GRrlDDrs&list=PLfXCqUzCr7k44JIZYJuQMi8rKeNxg7z4B'
opts = {'quiet': False, 'extract_flat': False}
with yt_dlp.YoutubeDL(opts) as ydl:
    info = ydl.extract_info(url, download=False)
    print('type:', info.get('_type'))
    print('title:', info.get('title'))
    entries = info.get('entries')
    print('entries:', None if entries is None else len(entries))
    if entries:
        for e in entries[:10]:
            print('entry sample:', e.get('webpage_url') or e.get('url'))
