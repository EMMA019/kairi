#!/usr/bin/env python3
"""
scripts/notify_email.py — 毎朝のACTION銘柄をメール送信
======================================================
環境変数:
  NOTIFY_EMAIL_TO    : 送信先メールアドレス
  NOTIFY_EMAIL_FROM  : 送信元（Gmail推奨）
  NOTIFY_EMAIL_PASS  : Gmailアプリパスワード
  SMTP_HOST          : (optional) デフォルト smtp.gmail.com
  SMTP_PORT          : (optional) デフォルト 587
"""
import os, json, smtplib, sys
from pathlib import Path
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

# ── 設定 ──────────────────────────────────────────────────
TO      = os.environ.get("NOTIFY_EMAIL_TO",   "")
FROM    = os.environ.get("NOTIFY_EMAIL_FROM",  "")
PASS    = os.environ.get("NOTIFY_EMAIL_PASS",  "")
HOST    = os.environ.get("SMTP_HOST", "smtp.gmail.com")
PORT    = int(os.environ.get("SMTP_PORT", "587"))

CONTENT = Path(__file__).parent.parent / "frontend" / "public" / "content"


def load_latest_daily():
    idx = json.loads((CONTENT / "index.json").read_text())
    slug = idx["articles"][0]["slug"]
    return json.loads((CONTENT / f"{slug}.json").read_text())


def format_text(daily: dict) -> str:
    d       = daily.get("date", "")
    actions = daily.get("data", {}).get("actions", [])
    wait    = daily.get("data", {}).get("wait_count", 0)
    idx     = daily.get("data", {}).get("index", {})

    lines = [
        f"SENTINEL PERSONAL — {d}",
        "=" * 50,
        "",
        "【指数】",
    ]

    for k, v in idx.items():
        r1d = v.get("ret_1d", 0)
        sign = "+" if r1d >= 0 else ""
        lines.append(f"  {v.get('name', k):12s}  {sign}{r1d:.2f}%")

    lines += [
        "",
        f"【ACTION銘柄】 {len(actions)}件 / WAIT {wait}件",
        "-" * 50,
    ]

    for i, t in enumerate(actions, 1):
        rr = None
        if t.get("_stop") and t.get("_entry") and t.get("_target"):
            rr = (t["_target"] - t["_entry"]) / (t["_entry"] - t["_stop"])

        line = (
            f"{i:>2}. {t['ticker']:<6}  "
            f"${t.get('_price', 0):>8.2f}  "
            f"VCP={t.get('vcp', 0):>3}  RS={t.get('rs', 0):>2}"
        )
        if t.get("_entry"):
            line += f"\n      Entry=${t['_entry']:.2f}  Stop=${t.get('_stop', 0):.2f}  Target=${t.get('_target', 0):.2f}"
        if rr:
            line += f"  RR=1:{rr:.1f}"

        lines.append(line)
        lines.append(f"      {t.get('sector', '')} — {t.get('name', '')}")
        lines.append("")

    lines += [
        "-" * 50,
        f"生成: {datetime.now().strftime('%Y-%m-%d %H:%M JST')}",
        "SENTINEL PERSONAL (private)",
    ]

    return "\n".join(lines)


def format_html(daily: dict) -> str:
    d       = daily.get("date", "")
    actions = daily.get("data", {}).get("actions", [])
    wait    = daily.get("data", {}).get("wait_count", 0)
    idx     = daily.get("data", {}).get("index", {})

    rows = ""
    for t in actions:
        rr = None
        if t.get("_stop") and t.get("_entry") and t.get("_target"):
            rr = (t["_target"] - t["_entry"]) / (t["_entry"] - t["_stop"])

        stop_pct = ""
        if t.get("_stop") and t.get("_entry"):
            stop_pct = f"({(t['_stop'] - t['_entry']) / t['_entry'] * 100:.1f}%)"

        rows += f"""
        <tr style="border-bottom:1px solid #182030">
          <td style="padding:8px 12px;font-family:monospace;font-weight:bold;color:#E8F4FF">
            <a href="https://finance.yahoo.com/quote/{t['ticker']}"
               style="color:#00FF88;text-decoration:none">{t['ticker']}</a>
          </td>
          <td style="padding:8px 12px;font-family:monospace;color:#6B8299;font-size:12px">
            {t.get('name', '')[:20]}
          </td>
          <td style="padding:8px 12px;font-family:monospace;color:#E8F4FF">
            ${t.get('_price', 0):.2f}
          </td>
          <td style="padding:8px 12px;font-family:monospace;color:#00FF88;font-weight:bold">
            ${t.get('_entry', 0):.2f}
          </td>
          <td style="padding:8px 12px;font-family:monospace;color:#FF4466">
            ${t.get('_stop', 0):.2f} <span style="color:#364858;font-size:11px">{stop_pct}</span>
          </td>
          <td style="padding:8px 12px;font-family:monospace;color:#FFB800">
            ${t.get('_target', 0):.2f}
          </td>
          <td style="padding:8px 12px;font-family:monospace;color:#6B8299;font-size:12px">
            {f"1:{rr:.1f}" if rr else "—"}
          </td>
          <td style="padding:8px 12px;font-family:monospace;color:#4499FF">
            {t.get('vcp', 0)}</td>
          <td style="padding:8px 12px;font-family:monospace;color:#AA66FF">
            {t.get('rs', 0)}
          </td>
        </tr>
        """

    index_rows = ""
    for k, v in idx.items():
        r1d = v.get("ret_1d", 0)
        color = "#00FF88" if r1d >= 0 else "#FF4466"
        sign  = "+" if r1d >= 0 else ""
        index_rows += f"""
        <tr>
          <td style="padding:6px 12px;font-family:monospace;color:#C8DCF0">{v.get('name', k)}</td>
          <td style="padding:6px 12px;font-family:monospace;color:{color};font-weight:bold">{sign}{r1d:.2f}%</td>
          <td style="padding:6px 12px;font-family:monospace;color:#6B8299;font-size:12px">
            5d: {v.get('ret_5d', 0):+.2f}%
          </td>
        </tr>
        """

    return f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="UTF-8"></head>
    <body style="background:#060A0F;color:#C8DCF0;font-family:'IBM Plex Sans',sans-serif;margin:0;padding:20px">
      <div style="max-width:800px;margin:0 auto">

        <div style="border-bottom:1px solid #182030;padding-bottom:16px;margin-bottom:20px">
          <div style="font-family:monospace;font-size:20px;font-weight:bold;color:#00FF88;
                      text-shadow:0 0 20px #00FF8880;letter-spacing:3px">SENTINEL</div>
          <div style="font-family:monospace;font-size:13px;color:#364858;margin-top:4px">
            PERSONAL REPORT — {d}
          </div>
        </div>

        <!-- 指数 -->
        <div style="margin-bottom:20px">
          <div style="font-family:monospace;font-size:11px;color:#364858;margin-bottom:8px">INDEX</div>
          <table style="border-collapse:collapse;width:100%">
            {index_rows}
          </table>
        </div>

        <!-- ACTION銘柄 -->
        <div style="font-family:monospace;font-size:11px;color:#364858;margin-bottom:8px">
          ACTION {len(actions)}銘柄 / WAIT {wait}銘柄
        </div>
        <table style="border-collapse:collapse;width:100%;background:#0C1117;
                      border:1px solid #182030;border-radius:8px;overflow:hidden">
          <thead>
            <tr style="background:#060A0F;border-bottom:1px solid #182030">
              <th style="padding:8px 12px;text-align:left;font-family:monospace;font-size:11px;color:#364858">Ticker</th>
              <th style="padding:8px 12px;text-align:left;font-family:monospace;font-size:11px;color:#364858">Name</th>
              <th style="padding:8px 12px;text-align:left;font-family:monospace;font-size:11px;color:#364858">Price</th>
              <th style="padding:8px 12px;text-align:left;font-family:monospace;font-size:11px;color:#00FF88">Entry</th>
              <th style="padding:8px 12px;text-align:left;font-family:monospace;font-size:11px;color:#FF4466">Stop</th>
              <th style="padding:8px 12px;text-align:left;font-family:monospace;font-size:11px;color:#FFB800">Target</th>
              <th style="padding:8px 12px;text-align:left;font-family:monospace;font-size:11px;color:#364858">RR</th>
              <th style="padding:8px 12px;text-align:left;font-family:monospace;font-size:11px;color:#364858">VCP</th>
              <th style="padding:8px 12px;text-align:left;font-family:monospace;font-size:11px;color:#364858">RS</th>
            </tr>
          </thead>
          <tbody>{rows}</tbody>
        </table>

        <div style="margin-top:20px;font-family:monospace;font-size:11px;color:#182030">
          Generated: {datetime.now().strftime('%Y-%m-%d %H:%M JST')} · SENTINEL PERSONAL (private)
        </div>
      </div>
    </body>
    </html>
    """


def send(subject: str, text: str, html: str):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = FROM
    msg["To"]      = TO
    msg.attach(MIMEText(text, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html",  "utf-8"))

    with smtplib.SMTP(HOST, PORT) as s:
        s.starttls()
        s.login(FROM, PASS)
        s.send_message(msg)


def main():
    if not all([TO, FROM, PASS]):
        print("⚠️  NOTIFY_EMAIL_TO / FROM / PASS が未設定 — スキップ")
        return

    try:
        daily = load_latest_daily()
    except Exception as e:
        print(f"❌ daily JSON 読み込み失敗: {e}")
        sys.exit(1)

    date    = daily.get("date", "")
    actions = daily.get("data", {}).get("actions", [])
    n       = len(actions)

    subject = f"🛡️ SENTINEL {date} — ACTION {n}銘柄"
    text    = format_text(daily)
    html    = format_html(daily)

    try:
        send(subject, text, html)
        print(f"✅ メール送信完了: {TO} ({n}銘柄)")
    except Exception as e:
        print(f"❌ メール送信失敗: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
