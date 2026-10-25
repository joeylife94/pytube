# 홈서버에 올리기 (Ubuntu · Docker · Tailscale)

미니PC 같은 리눅스 서버에 올려 두고 집 밖에서도 쓰는 방법이에요.

웹 UI에는 로그인이 없어서 인터넷에 그대로 열면 누구나 쓸 수 있어요. 그래서 포트는 서버 안(`127.0.0.1`)에만 열어 두고, [Tailscale](https://tailscale.com)(무료 VPN)로 내 기기에서만 접속해요.

```
휴대폰 · 노트북 ──(Tailscale, HTTPS)──▶ 서버의 tailscale serve ──▶ 127.0.0.1:8501 (Docker)
```

## 1. Docker 설치

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER   # 로그아웃 후 다시 로그인하면 sudo 없이 docker를 쓸 수 있어요
```

## 2. 코드 받기와 설정

```bash
git clone https://github.com/joeylife94/pytube.git
cd pytube
cp .env.example .env
nano .env
mkdir -p downloads
```

`.env`에서 확인할 것:

| 이름 | 설명 |
|---|---|
| `PUID` · `PGID` | `id -u`, `id -g` 값이에요. 받은 파일이 root가 아니라 내 계정 소유가 돼요 |
| `DOWNLOAD_DIR` | 다른 디스크에 저장하려면 경로를 적어요 (예: `/mnt/media/youtube`). 그 폴더도 내 계정으로 미리 만들어 두세요 |
| `TZ` | 예약 시각 기준 시간대예요 (기본 `Asia/Seoul`) |
| `BIND_ADDR` | `127.0.0.1` 그대로 두세요 |
| `API_TOKEN` | REST API를 다른 기기에서 쓸 때만 필요해요 (`openssl rand -hex 32`로 만들어요) |

`.env`는 git이 무시하는 파일이라 나중에 업데이트해도 설정이 그대로 남아요.

## 3. 실행

```bash
docker compose up -d --build
docker compose ps                              # web, api가 healthy가 되면 준비 끝
curl http://127.0.0.1:8501/_stcore/health      # ok가 나오면 정상
```

서버를 재부팅해도 자동으로 다시 떠요.

## 4. Tailscale로 밖에서 접속하기

1. 서버에 Tailscale을 설치하고 로그인해요.
   ```bash
   curl -fsSL https://tailscale.com/install.sh | sh
   sudo tailscale up
   ```
2. 휴대폰과 노트북에도 Tailscale 앱을 설치하고 같은 계정으로 로그인해요.
3. [관리 페이지](https://login.tailscale.com/admin/dns)의 DNS 메뉴에서 MagicDNS와 HTTPS Certificates를 켜요.
4. 서버에서 웹 UI를 Tailscale 네트워크에 연결해요.
   ```bash
   sudo tailscale serve --bg 8501
   tailscale serve status    # 접속 주소가 나와요: https://<서버이름>.<tailnet>.ts.net
   ```

이제 Tailscale이 켜진 기기에서 그 주소로 접속하면 돼요. HTTPS라서 다운로드 완료 알림도 동작해요.

REST API도 밖에서 쓰려면:

```bash
# .env에 API_TOKEN을 넣은 뒤
docker compose up -d
sudo tailscale serve --bg --https=8443 8000
curl -H "X-API-Key: <토큰>" https://<서버이름>.<tailnet>.ts.net:8443/api/status
```

토큰이 없으면 API는 서버 안(`localhost`)에서 온 요청만 받아요.

## 하지 말아야 할 것

- **공유기 포트포워딩으로 8501·8000을 인터넷에 열지 마세요.** 로그인이 없어서 누구나 다운로드를 걸고 받은 파일을 가져갈 수 있어요.
- **`BIND_ADDR`을 `0.0.0.0`으로 바꾸지 마세요.** 집 네트워크 전체에 열려요. Docker가 연 포트는 `ufw` 방화벽 규칙을 거치지 않아서 방화벽으로도 막을 수 없어요.

## 업데이트

YouTube가 바뀌면 오래된 yt-dlp는 금방 막혀요. 업데이트 스크립트는 코드를 받고, 최신 yt-dlp로 이미지를 다시 빌드하고, 재시작해요.

```bash
./scripts/update_server.sh
```

매주 자동으로 돌리려면 `crontab -e`에 추가해요 (월요일 새벽 4시):

```
0 4 * * 1 /home/<사용자>/pytube/scripts/update_server.sh >> /home/<사용자>/pytube-update.log 2>&1
```

## 알아 두면 좋은 것

- **쿠키:** 서버에는 브라우저가 없어서 「브라우저 쿠키」 옵션은 동작하지 않아요. 로그인이 필요한 영상은 사이드바의 「cookies.txt 업로드」를 쓰세요.
- **받은 파일 가져오기:** 「다운로드 현황」의 💾 버튼으로 지금 쓰는 기기에 내려받을 수 있어요 (2GB 이하). 자주 본다면 `DOWNLOAD_DIR`을 Jellyfin이나 Samba 공유 폴더로 지정하세요.
- **폴더 버튼:** 「폴더 열기」·📂 버튼은 서버에서는 의미가 없어서 숨겨져요.
- **로그 보기:** `docker compose logs -f web` (API는 `api`)

## 문제가 생기면

| 증상 | 확인할 것 |
|---|---|
| 컨테이너가 계속 재시작해요 | `docker compose logs web`. `Permission denied`가 보이면 다운로드 폴더 주인이 `PUID`와 같은지 확인하세요 (`ls -ld downloads`) |
| Tailscale 주소로 열리지만 「연결 중」에서 멈춰요 | `curl -I https://<서버이름>.<tailnet>.ts.net`이 되는지, `tailscale serve status`에 `127.0.0.1:8501`로 연결돼 있는지 확인하세요 |
| 상단 배지에 ffmpeg나 JS 해석기 경고가 떠요 | 이미지 빌드가 잘못된 거예요. `docker compose build --no-cache` 후 다시 실행하세요 |
| 「봇이 아님을 확인」 오류가 나요 | cookies.txt를 업로드하세요. 그래도 안 되면 `./scripts/update_server.sh`로 yt-dlp를 업데이트하세요 |
