"""원신 HoYoLAB 출석 + 리딤 코드 자동 입력. GitHub Actions에서 하루 한 번 실행."""

import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

import aiohttp
import genshin
from genshin.client.manager.cookie import fetch_cookie_with_stoken_v2

CODES_API = "https://hoyo-codes.seria.moe/codes?game=genshin"
REDEEM_INTERVAL = 6  # 코드 입력 사이 쿨다운(초)
KST = timezone(timedelta(hours=9))


def env(name: str) -> str:
    return os.environ.get(name, "").strip()


async def notify(text: str) -> None:
    token, chat_id = env("TELEGRAM_BOT_TOKEN"), env("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("(Telegram 미설정, 알림 생략)")
        return
    async with aiohttp.ClientSession() as session:
        await session.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text},
        )


async def build_cookies() -> tuple[dict[str, str], str]:
    """stoken이 있으면 매번 ltoken/cookie_token을 새로 발급받고, 없으면 붙여넣은 쿠키를 그대로 쓴다."""
    ltuid, ltmid = env("LTUID_V2"), env("LTMID_V2")
    if env("STOKEN"):
        fresh = await fetch_cookie_with_stoken_v2(
            {"stoken": env("STOKEN"), "ltmid_v2": ltmid, "ltuid_v2": ltuid}, token_types=[2, 4]
        )
        cookies = {
            "ltoken_v2": fresh["ltoken_v2"],
            "cookie_token_v2": fresh["cookie_token_v2"],
            "ltuid_v2": ltuid,
            "ltmid_v2": ltmid,
            "account_id_v2": ltuid,
            "account_mid_v2": ltmid,
        }
        return cookies, "stoken"

    cookies = {"ltoken_v2": env("LTOKEN_V2"), "ltuid_v2": ltuid}
    if ltmid:
        cookies["ltmid_v2"] = ltmid
        cookies["account_mid_v2"] = ltmid
    if env("COOKIE_TOKEN_V2"):
        cookies["cookie_token_v2"] = env("COOKIE_TOKEN_V2")
        cookies["account_id_v2"] = ltuid
    return cookies, "pasted"


async def fetch_codes() -> list[dict]:
    async with aiohttp.ClientSession() as session:
        async with session.get(CODES_API, timeout=aiohttp.ClientTimeout(total=30)) as r:
            data = await r.json(content_type=None)
    return [c for c in data.get("codes", []) if c.get("status") == "OK"]


def kst_now() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d %H:%M")


def format_rewards(rewards: str) -> str:
    """'Primogem*30;Mora*20000' -> 'Primogem x30, Mora x20000'"""
    return ", ".join(r.replace("*", " x") for r in rewards.split(";") if r) or "보상 정보 없음"


async def redeem_all(client: genshin.Client, uid: int) -> dict:
    result = {"total": 0, "new": [], "claimed": 0, "skipped": 0, "errors": []}
    codes = await fetch_codes()
    result["total"] = len(codes)
    for c in codes:
        code = c["code"]
        for attempt in range(3):
            try:
                await client.redeem_code(code, uid)
                result["new"].append(f"{kst_now()} {code} → {format_rewards(c.get('rewards', ''))}")
                print(f"[redeem] {code}: 성공")
            except genshin.errors.RedemptionCooldown:
                print(f"[redeem] {code}: 쿨다운, 재시도 {attempt + 1}/3")
                await asyncio.sleep(REDEEM_INTERVAL * 2)
                continue
            except genshin.errors.RedemptionClaimed:
                result["claimed"] += 1
                print(f"[redeem] {code}: 이미 사용")
            except (genshin.errors.RedemptionInvalid, genshin.errors.RedemptionRegionLock) as e:
                result["skipped"] += 1
                print(f"[redeem] {code}: {type(e).__name__}")
            except genshin.InvalidCookies:
                raise
            except genshin.GenshinException as e:
                print(f"[redeem] {code}: {e}")
                result["errors"].append(f"{code}: {e.msg or e}")
            break
        else:
            result["errors"].append(f"{code}: 쿨다운으로 3회 실패")
        await asyncio.sleep(REDEEM_INTERVAL)
    return result


async def main() -> int:
    lines: list[str] = []
    failed = False

    try:
        cookies, source = await build_cookies()
    except genshin.GenshinException as e:
        await notify(f"❌ [원신] stoken 만료/무효: {e}\n→ 로컬에서 `uv run manage.py login` 다시 실행")
        print(f"stoken refresh 실패: {e}")
        return 1

    client = genshin.Client(cookies, game=genshin.Game.GENSHIN, region=genshin.Region.OVERSEAS)

    # 1) 출석
    try:
        reward = await client.claim_daily_reward()
        lines.append(f"✅ 출석 완료: {reward.name} x{reward.amount}")
    except genshin.AlreadyClaimed:
        lines.append("✅ 출석: 오늘 이미 완료")
    except genshin.InvalidCookies:
        failed = True
        hint = "uv run manage.py login" if source == "stoken" else "uv run manage.py login (또는 paste)"
        lines.append(f"❌ 출석 실패: 쿠키 만료/무효 → {hint}")
    except genshin.GenshinException as e:
        failed = True
        lines.append(f"❌ 출석 실패: {e}")

    # 2) 리딤 코드
    if "cookie_token_v2" not in cookies:
        lines.append("⚠️ 리딤 생략: cookie_token_v2/stoken 없음 → uv run manage.py login")
    elif not failed:
        try:
            accounts = [a for a in await client.get_game_accounts() if a.game == genshin.Game.GENSHIN]
            uid = int(env("GENSHIN_UID") or max(accounts, key=lambda a: a.level).uid)
            r = await redeem_all(client, uid)
            summary = f"🎁 코드 {r['total']}개 확인 · 새로 입력 {len(r['new'])} · 이미 사용 {r['claimed']}"
            if r["skipped"]:
                summary += f" · 무효/지역제한 {r['skipped']}"
            lines.append(summary)
            lines.extend(f"  • {n}" for n in r["new"])
            if r["errors"]:
                lines.append("⚠️ 코드 오류:\n" + "\n".join(f"  • {e}" for e in r["errors"]))
        except genshin.InvalidCookies:
            failed = True
            lines.append("❌ 리딤 실패: cookie_token 만료/무효 → uv run manage.py login")
        except Exception as e:  # 코드 API 장애 등은 출석 결과와 분리해서 알림
            failed = True
            lines.append(f"❌ 리딤 실패: {type(e).__name__}: {e}")

    message = "[원신 자동]\n" + "\n".join(lines)
    print(message)
    await notify(message)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
