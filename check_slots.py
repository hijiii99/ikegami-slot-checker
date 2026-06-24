"""
池上教習所 技能予約 空き通知スクリプト
- e-licenseにログインし、5週分のカレンダーを巡回
- 予約済みの最新日程より前の空き枠（td.status1）を検出
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

WEEKS_TO_CHECK = 5   # 今週 + 4週先まで確認


# ── 1週分のスクレイプ ─────────────────────────────────────────────────────────
def scrape_week(page) -> tuple[list[str], list[tuple[str, str]]]:
    """
    Returns:
      reserved_dates : 予約済みの YYYYMMDD リスト
      available_slots: (YYYYMMDD, 表示文字列) のリスト
    重複は seen で除去。
    """
    seen_res = set()
    seen_avl = set()
    reserved_dates = []
    available_slots = []

    # 予約済み: td.status3 > a.cancel
    for a in page.locator("td.status3 a.cancel").all():
        ymd = a.get_attribute("data-yoyaku") or ""
        if ymd and ymd not in seen_res:
            seen_res.add(ymd)
            reserved_dates.append(ymd)

    # 空き枠: td.status1 > a.simei
    for a in page.locator("td.status1 a.simei").all():
        ymd  = a.get_attribute("data-yoyaku") or ""
        date = a.get_attribute("data-date")   or ""
        week = a.get_attribute("data-week")   or ""
        time = a.get_attribute("data-time")   or ""
        key  = f"{ymd}_{time}"
        if key not in seen_avl:
            seen_avl.add(key)
            available_slots.append((ymd, f"{date}{week} {time}〜"))

    return reserved_dates, available_slots


# ── LINE ブロードキャスト ─────────────────────────────────────────────────────
def send_line_broadcast(slots: list[str], latest_reserved_display: str) -> None:
    lines = [f"【池上教習所】{latest_reserved_reply}より前に空きがあります！\n"]
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


# ── メイン ───────────────────────────────────────────────────────────────────
def main():
    all_reserved: list[str]              = []
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
            reserved, available = scrape_week(page)
            print(f"  予約済み日程: {reserved}")
            print(f"  空き枠: {[a[1] for a in available]}")
            all_reserved.extend(reserved)
            all_available.extend(available)

            if week_num < WEEKS_TO_CHECK - 1:
                next_btn = page.locator("button.nextWeek")
                if next_btn.count() == 0:
                    print("「次週へ」ボタンが見つかりません。ここで終了します。")
                    break
                next_btn.first.click()
                page.wait_for_load_state("networkidle")

        browser.close()

    # ── フィルタリング ──
    if not all_reserved:
        print("予約済み日程が見つかりませんでした。通知をスキップします。")
        return

    # 最新の予約日（YYYYMMDD の文字列比較で最大値）
    latest_ymd = max(all_reserved)
    print(f"\n最新予約日: {latest_ymd}（これより前の空き枠のみ通知）")

    # 最新予約日より前（strictly before）の空き枠を収集
    seen = set()
    filtered = []
    for ymd, display in all_available:
        if ymd < latest_ymd and display not in seen:
            seen.add(display)
            filtered.append(display)

    print(f"フィルタ後の空き枠: {filtered}")

    if filtered:
        # 表示用に最新予約日を変換（20260630 → 6月30日）
        y, m, d = latest_ymd[:4], latest_ymd[4:6].lstrip("0"), latest_ymd[6:].lstrip("0")
        latest_display = f"{m}月{d}日"
        global latest_reserved_reply
        latest_reserved_reply = latest_display
        send_line_broadcast(filtered, latest_display)
    else:
        print("条件に合う空き枠なし → 通知スキップ")


if __name__ == "__main__":
    latest_reserved_reply = ""
    main()
