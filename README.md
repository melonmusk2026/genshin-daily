# genshin-daily

원신 HoYoLAB **출석체크 + 리딤 코드 자동 입력**. GitHub Actions에서 매일 07:00 KST에 실행되며 PC가 꺼져 있어도 동작한다. 결과와 쿠키 만료는 Telegram으로 알림.

## 동작

`.github/workflows/daily.yml` → `uv run checkin.py`

1. **쿠키 갱신**: `STOKEN`으로 `ltoken_v2`, `cookie_token_v2`를 매번 새로 발급 (`STOKEN`이 없으면 붙여넣은 쿠키 사용)
2. **출석**: HoYoLAB 일일 출석 보상 수령
3. **리딤**: [hoyo-codes](https://hoyo-codes.seria.moe/codes?game=genshin) 에서 유효한 코드 목록을 받아 6초 간격으로 하나씩 입력 (쿨다운 시 재시도)
4. **알림**: Telegram으로 요약 전송. 실패하면 workflow도 실패 처리되어 GitHub 메일도 온다

```
[원신 자동]
✅ 출석: 오늘 이미 완료
🎁 코드 14개 확인 · 새로 입력 1 · 이미 사용 13
  • 2026-10-05 07:01 NEWCODE123 → Primogem x60, Mora x10000
```

새로 입력한 코드는 시각·보상과 함께 표시되므로 Telegram 대화 기록이 리딤 이력이 된다.

## 파일

| 파일 | 역할 |
|---|---|
| `checkin.py` | 출석 + 리딤 + 알림 (Actions에서 실행) |
| `manage.py` | 로컬 관리: `.env` 갱신 → GitHub Secrets 동기화 |
| `.env` | 쿠키/토큰 원본 (git 제외) |
| `.github/workflows/daily.yml` | 매일 07:00 KST 실행 + 60일 무활동 비활성화 방지(keepalive) |

## 처음 설정 / 쿠키 갱신

[uv](https://docs.astral.sh/uv/)와 로그인된 `gh` CLI가 필요하다. 이 폴더에서:

```sh
uv run manage.py telegram   # 알림 봇 연결 (@BotFather로 봇 생성 → 토큰 입력 → 봇에게 메시지 1개 전송)
uv run manage.py login      # HoYoLAB 이메일/비번 로그인 → STOKEN 발급 (비밀번호는 저장 안 함)
uv run manage.py run        # 로컬에서 1회 실행해서 확인
```

`login`/`paste`/`telegram`은 끝나면 자동으로 `sync`까지 한다.

| 명령 | 설명 |
|---|---|
| `login` | **추천.** stoken 발급(보통 ~1년 유지). 캡차가 뜨면 브라우저(`localhost:5000`), 새 기기면 메일 인증 코드 입력 |
| `paste` | 대체 방법. hoyolab.com 로그인 → F12 → Application → Cookies에서 `ltoken_v2`, `ltuid_v2`, `ltmid_v2`, `cookie_token_v2` 복사해 입력 (STOKEN은 삭제됨, 더 빨리 만료됨) |
| `telegram` | Telegram 봇 토큰/채팅 ID 설정 + 테스트 메시지 |
| `sync` | `.env` → GitHub Secrets 동기화 (`.env`에 없는 키는 Secrets에서도 삭제) |
| `run` | 로컬에서 출석 + 리딤 1회 실행 |

**만료 알림(`❌ ... 만료/무효`)을 받으면** `uv run manage.py login`만 다시 실행하면 된다.

## `.env` 키

| 키 | 설명 |
|---|---|
| `STOKEN`, `LTUID_V2`, `LTMID_V2` | `login`이 채움. 이것만 있으면 됨 |
| `LTOKEN_V2`, `COOKIE_TOKEN_V2` | `paste` 방식일 때만 사용 |
| `GENSHIN_UID` | 선택. 비우면 계정에서 가장 레벨 높은 원신 UID 자동 선택 |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | `telegram`이 채움 |

## 수동 실행

GitHub → Actions → **Genshin daily** → Run workflow, 또는 `gh workflow run daily.yml`
