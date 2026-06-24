"""
池上教習所 技能予約 空き通知スクリプト
- e-licenseにログインし、5週分のカレンダーを巡回
- td.status1（予約可能セル）を検出したらLINEに通知
"""

import os
import re
import requests
from playwright.sync_api import sync_playwright

# ── 環境変数（GitHub Secrets から取得） ─────────────────────────────────────
LOGIN_URL    = "https://www.e-license.jp/el32/mSg1DWxRvAI-brGQYS-1OA%3D%3D"
LOGIN_ID     = os.environ["ELICENSE_LOGIN_ID"]
PASSWORD     = os.environ["ELICENSE_PASSWORD"]
LINE_TOKEN   = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]
LINE_USER_ID = os.environ["LINE_USER_ID"]

WEEKS_TO_CHECK = 5   # 今週 + 4週先まで確認


# ── 1週分の空き枠を取得 ──────────────────────────────────────────────────────
def scrape_week(page) -> list[str]:
    """
    td.status1 内の <a class="simei"> のデータ属性から空き枠を取得。
    同じ枠が2つのテーブルレイアウトに重複して存在するため seen で重複除去。
    """
    seen = set()
    slots = []

    anchors = page.locator("td.status1 a.simei").all()
    for a in anchors:
        date = a.get_attribute("data-date") or ""   # 例: "7月16日"
        week = a.get_attribute("data-week") or ""   # 例: "(木)"
        time = a.get_attribute("data-time") or ""   # 例: "17:00"
        key  = f"{date}{week}_{time}"
        if key not in seen:
            seen.add(key)
            slots.append(f"{date}{week} {time}〜")

    return slots


# ── LINE 通知 ────────────────────────────────────────────────────────────────
def send_line(slots: list[str]) -> None:
    lines = ["【池上教習所】技能予約の空きがあります！\n"]
    for s in slots:
        lines.append(f"・{s}")
    lines.append(f"\n▶ 予約する\n{LOGIN_URL}")

    resp = requests.post(
        "https://api.line.me/v2/bot/message/push",
        headers={
            "Authorization": f"Bearer {LINE_TOKEN}",
            "Content-Type": "application/json",
        },
        json={
            "to": LINE_USER_ID,
            "messages": [{"type": "text", "text": "\n".join(lines)}],
        },
        timeout=10,
    )
    resp.raise_for_status()
    print(f"LINE 通知送信完了 (status={resp.status_code})")


# ── メイン ───────────────────────────────────────────────────────────────────
def main():
    all_slots: list[str] = []

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
                print("技能予約リンクが見つかりませんでした（すでに表示中の可能性あり）")

        # ── 週ごとに巡回 ──
        for week_num in range(WEEKS_TO_CHECK):
            # 週のタイトルを取得（例: "7月15日～7月21日の 技能予約"）
            try:
                title = page.locator("#ginou-title").inner_text().strip()
            except Exception:
                title = f"第{week_num + 1}週"

            print(f"[{week_num + 1}/{WEEKS_TO_CHECK}] {title} をチェック中...")
            slots = scrape_week(page)
            print(f"  → 空き {len(slots)} コマ: {slots}")
            all_slots.extend(slots)

            # 最終週以外は「次週へ」をクリック
            if week_num < WEEKS_TO_CHECK - 1:
                next_btn = page.locator("button.nextWeek")
                if next_btn.count() == 0:
                    print("「次週へ」ボタンが見つかりません。ここで終了します。")
                    break
                next_btn.first.click()
                page.wait_for_load_state("networkidle")

        browser.close()

    # ── 結果 ──
    print(f"\n合計 {len(all_slots)} コマの空きを検出しました。")

    if all_slots:
        send_line(all_slots)
    else:
        print("空きなし → LINE 通知はスキップ")


if __name__ == "__main__":
    main()
