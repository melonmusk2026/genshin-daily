"""로컬 관리 스크립트: .env의 쿠키를 갱신하고 GitHub Secrets에 동기화한다.

  uv run manage.py login      # HoYoLAB 이메일/비번 로그인 → stoken 발급 (추천, ~1년 유지)
  uv run manage.py paste      # F12에서 복사한 쿠키를 직접 붙여넣기
  uv run manage.py telegram   # Telegram 알림 봇 설정
  uv run manage.py sync       # .env → GitHub Secrets 동기화
  uv run manage.py run        # 로컬에서 출석+리딤 1회 실행 (테스트용)
"""

import asyncio
import getpass
import subprocess
import sys
import time
from pathlib import Path

import aiohttp
import genshin
from dotenv import dotenv_values, load_dotenv, set_key, unset_key

ENV = Path(__file__).with_name(".env")
sys.stdout.reconfigure(encoding="utf-8")
KEYS = [
    "STOKEN", "LTUID_V2", "LTMID_V2", "LTOKEN_V2", "COOKIE_TOKEN_V2",
    "GENSHIN_UID", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID",
]


def save(**values: str | None) -> None:
    ENV.touch(exist_ok=True)
    for key, value in values.items():
        if value:
            set_key(ENV, key, value, quote_mode="never")
        elif value is None:
            unset_key(ENV, key, quote_mode="never")


def repo() -> str:
    out = subprocess.run(
        ["gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"],
        capture_output=True, text=True, check=True, cwd=ENV.parent,
    )
    return out.stdout.strip()


def sync() -> None:
    r = repo()
    values = {k: v for k, v in dotenv_values(ENV).items() if k in KEYS and v}
    existing = subprocess.run(
        ["gh", "secret", "list", "-R", r, "--json", "name", "-q", ".[].name"],
        capture_output=True, text=True, check=True,
    ).stdout.split()
    for key, value in values.items():
        subprocess.run(["gh", "secret", "set", key, "-R", r], input=value, text=True, check=True)
    for key in set(existing) & set(KEYS) - set(values):
        subprocess.run(["gh", "secret", "delete", key, "-R", r], check=True)
    print(f"✔ GitHub Secrets 동기화 완료 ({r}): {', '.join(values)}")


async def login() -> None:
    print("HoYoLAB 계정으로 로그인합니다. (비밀번호는 저장되지 않음)")
    print("캡차가 뜨면 브라우저가 열립니다. 새 기기 인증 메일이 오면 코드를 입력하세요.\n")
    account = input("이메일/아이디: ").strip()
    password = getpass.getpass("비밀번호: ")
    client = genshin.Client(region=genshin.Region.OVERSEAS)
    result = await client.login_with_app_password(account, password)
    save(STOKEN=result.stoken, LTUID_V2=result.ltuid_v2, LTMID_V2=result.ltmid_v2,
         LTOKEN_V2=None, COOKIE_TOKEN_V2=None)
    print("✔ stoken 저장 완료 (.env)")
    sync()


def paste() -> None:
    print("hoyolab.com 로그인 → F12 → Application → Cookies → https://www.hoyolab.com 에서 값 복사.")
    print("빈칸으로 두면 기존 값 유지.\n")
    current = dotenv_values(ENV) if ENV.exists() else {}
    values = {}
    for key in ["LTOKEN_V2", "LTUID_V2", "LTMID_V2", "COOKIE_TOKEN_V2"]:
        v = input(f"{key.lower()}: ").strip()
        values[key] = v or current.get(key) or ""
    if current.get("STOKEN"):
        print("※ 붙여넣은 쿠키를 쓰기 위해 STOKEN은 삭제합니다.")
    save(STOKEN=None, **values)
    print("✔ 쿠키 저장 완료 (.env)")
    sync()


async def telegram() -> None:
    print("1) Telegram에서 @BotFather → /newbot 으로 봇을 만들고 토큰을 복사하세요.")
    token = input("봇 토큰: ").strip()
    print("2) 방금 만든 봇과 대화를 열고 아무 메시지나 보내세요. (60초 대기)")
    chat_id = None
    async with aiohttp.ClientSession() as session:
        for _ in range(30):
            async with session.get(f"https://api.telegram.org/bot{token}/getUpdates") as r:
                data = await r.json()
            if not data.get("ok"):
                sys.exit(f"봇 토큰 오류: {data}")
            if data["result"]:
                chat_id = str(data["result"][-1]["message"]["chat"]["id"])
                break
            time.sleep(2)
        if not chat_id:
            sys.exit("메시지를 못 받았습니다. 봇에게 메시지를 보낸 뒤 다시 실행하세요.")
        await session.post(f"https://api.telegram.org/bot{token}/sendMessage",
                           json={"chat_id": chat_id, "text": "✅ 원신 자동 출석 알림 연결 완료"})
    save(TELEGRAM_BOT_TOKEN=token, TELEGRAM_CHAT_ID=chat_id)
    print(f"✔ Telegram 설정 완료 (chat_id={chat_id})")
    sync()


def run() -> int:
    load_dotenv(ENV, override=True)
    import checkin
    return asyncio.run(checkin.main())


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "login":
        asyncio.run(login())
    elif cmd == "paste":
        paste()
    elif cmd == "telegram":
        asyncio.run(telegram())
    elif cmd == "sync":
        sync()
    elif cmd == "run":
        sys.exit(run())
    else:
        print(__doc__)
