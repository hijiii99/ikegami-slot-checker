"""
池上教習所 技能予約 空き通知スクリプト
- e-licenseにログインし、5週分のカレンダーを巡回
- 締切日（DEADLINE）以前の空き枠（td.status1）を検出
  ※ 現在の予約の有無には関係なく通知する
- LINE友だち全員にブロードキャスト通知
"""

import os
import requests
from playwright.sync_api import sync_playwright

# ── 環境変数（GitHub Secrets から取得） ─────────────────────────────────────
LOGIN_URL  = "https://www.e-license.jp/el32/mSg1DWxRvAI-brGQYS-1OA%3D%3D"
LOGIN_ID   = os.environ["ELICENSE_LOGIN_ID"]
PASSWORD   = os.environ["ELICENSE_PASSWORD"]
LINE_TOKEN = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]

# この日付「以前（当日を含む）」の空き枠を通知する（YYYYMMDD）
# 環境変数 DEADLINE で上書き可能
DEADLINE = os.environ.get("DEADLINE", "20261202")

WEEKS_TO_CHECK = 5   # 今週 + 4週先まで確認


# ── 1週分のスクレイプ ─────────────────────────────────────────────────────────
def scrape_week(page) -> list[tuple[str, str]]:
    """
    Returns:
      available_slots: (YYYYMMDD, 表示文字列) のリスト
    重複は seen で除去。
    """
    seen = set()
    available_slots = []

    # 空き枠: td.status1 > a.simei
    for a in page.locator("td.status1 a.simei").all():
        ymd  = a.get_attribute("data-yoyaku") or ""
        date = a.get_attribute("data-date")   or ""
        week = a.get_attribute("data-week")   or ""
        time = a.get_attribute("data-time")   or ""
        key  = f"{ymd}_{time}"
        if key not in seen:
            seen.add(key)
            available_slots.append((ymd, f"{date}{week} {time}〜"))

    return available_slots


# ── LINE ブロードキャスト ─────────────────────────────────────────────────────
def send_line_broadcast(slots: list[str], deadline_display: str) -> None:
    lines = [f"【池上教習所】{deadline_display}までに空きがあります！\n"]
    for s in slots:
        lines.append(f"・{s}")
    lines.append(f"\n▶ 予約する\n{LOGIN_URL}")

    resp = requests.post(
        "https://api.line.me/v2/bot/message/broadcast",
        headers={
            "Authorization": f"Bearer {LINE_TOKEN}",
            "Content-Type": "application/json",
        },
        json={"messages": [{"type": "text", "text": "\n".join(lines)}]},
        timeout=10,
    )
    resp.raise_for_status()
    print(f"LINE ブロードキャスト送信完了 (status={resp.status_code})")


def ymd_to_display(ymd: str) -> str:
    """20261202 → 12月2日"""
    return f"{int(ymd[4:6])}月{int(ymd[6:8])}日"


# ── メイン ───────────────────────────────────────────────────────────────────
def main():
    all_available: list[tuple[str, str]] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page    = browser.new_page()
        page.set_default_timeout(30_000)

        # ── ログイン ──
        print(f"ログインページを開きます: {LOGIN_URL}")
        page.goto(LOGIN_URL, wait_until="networkidle")

        page.locator('input[type="text"]:visible').first.fill(LOGIN_ID)
        page.locator('input[type="password"]:visible').first.fill(PASSWORD)
        page.locator('input[type="password"]:visible').first.press("Enter")
        page.wait_for_load_state("networkidle")
        print("ログイン完了")

        # ── 技能予約ページへ（必要なら） ──
        if "技能予約" not in page.content():
            try:
                page.locator("text=技能予約").first.click()
                page.wait_for_load_state("networkidle")
                print("技能予約ページへ移動しました")
            except Exception:
                pass

        # ── 週ごとに巡回 ──
        for week_num in range(WEEKS_TO_CHECK):
            try:
                title = page.locator("#ginou-title").inner_text().strip()
            except Exception:
                title = f"第{week_num + 1}週"

            print(f"[{week_num + 1}/{WEEKS_TO_CHECK}] {title} をチェック中...")
            available = scrape_week(page)
            print(f"  空き枠: {[a[1] for a in available]}")
            all_available.extend(available)

            # 締切日を過ぎた週まで見たら、それ以上先は不要
            if available and min(a[0] for a in available) > DEADLINE:
                print("  締切日より先の週に到達したので巡回を終了します。")
                break

            if week_num < WEEKS_TO_CHECK - 1:
                next_btn = page.locator("button.nextWeek")
                if next_btn.count() == 0:
                    print("「次週へ」ボタンが見つかりません。ここで終了します。")
                    break
                next_btn.first.click()
                page.wait_for_load_state("networkidle")

        browser.close()

    # ── フィルタリング：締切日以前（当日を含む）の空き枠 ──
    print(f"\n締切日: {DEADLINE}（この日までの空き枠を通知）")

    seen = set()
    filtered = []
    for ymd, display in all_available:
        if ymd and ymd <= DEADLINE and display not in seen:
            seen.add(display)
            filtered.append(display)

    print(f"フィルタ後の空き枠: {filtered}")

    if filtered:
        send_line_broadcast(filtered, ymd_to_display(DEADLINE))
    else:
        print("条件に合う空き枠なし → 通知スキップ")


if __name__ == "__main__":
    main()
