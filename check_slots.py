"""
池上教習所 技能予約 空き通知スクリプト
- e-licenseにログインし、5週分のカレンダーを巡回
- 緑セル（予約可能）を検出したらLINEに通知
"""

import os
import re
import sys
import requests
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# ── 環境変数（GitHub Secrets から取得） ─────────────────────────────────────
LOGIN_URL       = "https://www.e-license.jp/el32/mSg1DWxRvAI-brGQYS-1OA%3D%3D"
LOGIN_ID        = os.environ["ELICENSE_LOGIN_ID"]
PASSWORD        = os.environ["ELICENSE_PASSWORD"]
LINE_TOKEN      = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]
LINE_USER_ID    = os.environ["LINE_USER_ID"]

WEEKS_TO_CHECK  = 5   # 今週 + 4週先まで確認


# ── 色判定：緑かどうか ──────────────────────────────────────────────────────
def is_green(rgb_str: str) -> bool:
    """
    CSS の rgb(R, G, B) 文字列を受け取り、緑系かどうかを返す。
    e-license の緑は概ね rgb(144,238,144) や rgb(0,176,80) 系。
    """
    m = re.match(r"rgb\(\s*(\d+),\s*(\d+),\s*(\d+)\s*\)", rgb_str)
    if not m:
        return False
    r, g, b = int(m.group(1)), int(m.group(2)), int(m.group(3))
    # 白・グレーを除外し、緑が支配的な色を検出
    if r > 230 and g > 230 and b > 230:
        return False          # ほぼ白
    if abs(r - g) < 20 and abs(g - b) < 20:
        return False          # グレー系
    return g > r and g > b and g > 100


# ── 1週分のカレンダーをスクレイプ ──────────────────────────────────────────
def scrape_week(page) -> list[str]:
    """現在表示されている週の緑セルを返す（例: ["6月25日(木) 17:00〜", ...]）"""

    # ---- 時刻ヘッダーを取得 ----
    # e-license のカレンダーは <table> 構造。
    # 1行目 th に「1\n9:00」「2\n10:00」の形で入っている。
    time_labels = []
    header_ths = page.locator("table th").all()
    for th in header_ths:
        text = th.inner_text().strip()
        # "1\n9:00" → "9:00" だけ抽出
        m = re.search(r"(\d{1,2}:\d{2})", text)
        if m:
            time_labels.append(m.group(1))

    # ---- 日付行を取得 ----
    slots = []
    rows = page.locator("table tr").all()

    col_index = 0
    for row in rows:
        # 行の最初のセル（日付）
        first_cell = row.locator("td:first-child, th:first-child").first
        date_text = first_cell.inner_text().strip()

        # 日付っぽくないヘッダー行はスキップ
        if not re.search(r"\d+月\d+日", date_text):
            continue

        # この行のデータセル（日付列を除いた td）
        cells = row.locator("td").all()
        # 最初の td が日付なら 1 つ飛ばす
        start = 1 if len(cells) > len(time_labels) else 0

        for i, cell in enumerate(cells[start:]):
            bg = cell.evaluate(
                "el => window.getComputedStyle(el).backgroundColor"
            )
            if is_green(bg):
                time_str = time_labels[i] if i < len(time_labels) else f"時限{i+1}"
                slots.append(f"{date_text} {time_str}〜")

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
        page = browser.new_page()
        page.set_default_timeout(30_000)

        # ── ログイン ──
        print(f"ログインページを開きます: {LOGIN_URL}")
        page.goto(LOGIN_URL, wait_until="networkidle")

        # フォームのセレクタ（e-license の実際の name 属性に合わせる）
        # ログインIDフィールド
        id_field = page.locator(
            'input[name="loginId"], input[name="userId"], '
            'input[type="text"]:visible'
        ).first
        id_field.fill(LOGIN_ID)

        # パスワードフィールド
        pw_field = page.locator('input[type="password"]:visible').first
        pw_field.fill(PASSWORD)

        # ログインボタン
        page.locator(
            'input[type="submit"]:visible, button[type="submit"]:visible, '
            'button:has-text("ログイン"):visible'
        ).first.click()

        page.wait_for_load_state("networkidle")
        print("ログイン完了")

        # ── 技能予約ページへ移動（まだそこでなければ） ──
        if "技能予約" not in page.content():
            try:
                page.locator("text=技能予約").first.click()
                page.wait_for_load_state("networkidle")
                print("技能予約ページへ移動しました")
            except Exception:
                print("技能予約リンクが見つかりませんでした（すでに表示中の可能性あり）")

        # ── 週ごとに巡回 ──
        for week_num in range(WEEKS_TO_CHECK):
            # 表示中の週タイトルを取得
            try:
                title = page.locator(
                    "h2:visible, h3:visible, .week-title:visible"
                ).first.inner_text().strip()
            except Exception:
                title = f"第{week_num + 1}週"

            print(f"[{week_num + 1}/{WEEKS_TO_CHECK}] {title} をチェック中...")
            slots = scrape_week(page)
            print(f"  → 空き {len(slots)} コマ: {slots}")
            all_slots.extend(slots)

            # 最終週以外は「次週へ」をクリック
            if week_num < WEEKS_TO_CHECK - 1:
                next_btn = page.locator(
                    'text=次週へ, input[value*="次週"], a:has-text("次週")'
                )
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
