import json
import os
import re
import ssl
import subprocess
from datetime import datetime
from urllib.parse import quote
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.poolmanager import PoolManager

URL = "https://www.uz.gov.ua/about/activity/electropostachannia/electro_consumers/temporary_shutdown/grafikiobmezhen/622368/"
DATA_FILE = "data.json"
TARGET_QUEUE = "6(1)"
KYIV_TZ = ZoneInfo("Europe/Kyiv")

MONTHS = {
    "січня": 1, "лютого": 2, "березня": 3, "квітня": 4,
    "травня": 5, "червня": 6, "липня": 7, "серпня": 8,
    "вересня": 9, "жовтня": 10, "листопада": 11, "грудня": 12,
}

ALL_QUEUES = [f"{q}({s})" for q in range(1, 7) for s in (1, 2)]


class LegacySSLAdapter(HTTPAdapter):
    def init_poolmanager(self, connections, maxsize, block=False):
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        try:
            ctx.set_ciphers("DEFAULT:@SECLEVEL=1")
        except Exception:
            pass
        self.poolmanager = PoolManager(
            num_pools=connections, maxsize=maxsize, block=block, ssl_context=ctx
        )


def decode_html(raw: bytes) -> str:
    for enc in ("utf-8", "windows-1251", "cp1251"):
        try:
            text = raw.decode(enc)
            if "Тернопільська" in text or "Години" in text:
                return text
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="ignore")


def is_valid_uz_content(text: str) -> bool:
    if not text or len(text) < 500:
        return False
    low = text.lower()
    return ("тернопільська" in low) and ("годин" in low or "черг" in low)


def fetch_content() -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "uk-UA,uk;q=0.9,en;q=0.8",
        "Referer": "https://www.uz.gov.ua/",
    }

    session = requests.Session()
    session.mount("https://", LegacySSLAdapter())

    # 1. Direct request
    try:
        resp = session.get(URL, headers=headers, timeout=20)
        if resp.status_code == 200:
            html = decode_html(resp.content)
            if is_valid_uz_content(html):
                return html
    except Exception:
        pass

    # 2. Direct curl
    try:
        res = subprocess.run(
            ["curl", "-k", "-sL", "--max-time", "20", "-A", headers["User-Agent"], URL],
            capture_output=True,
            check=False,
        )
        if res.returncode == 0:
            html = decode_html(res.stdout)
            if is_valid_uz_content(html):
                return html
    except Exception:
        pass

    # 3. Jina Reader (Cloudflare headless Chrome -> Markdown)
    try:
        r = session.get(
            f"https://r.jina.ai/{URL}",
            headers={"User-Agent": headers["User-Agent"], "X-Return-Format": "markdown"},
            timeout=30,
        )
        if r.status_code == 200 and is_valid_uz_content(r.text):
            return r.text
    except Exception:
        pass

    # 4. AllOrigins JSON wrapper
    try:
        r = session.get(
            f"https://api.allorigins.win/get?url={quote(URL, safe='')}",
            headers={"User-Agent": headers["User-Agent"]},
            timeout=25,
        )
        if r.status_code == 200:
            data = r.json()
            contents = data.get("contents", "")
            if is_valid_uz_content(contents):
                return contents
    except Exception:
        pass

    # 5. CodeTabs proxy
    try:
        r = session.get(
            f"https://api.codetabs.com/v1/proxy?quest={quote(URL, safe='')}",
            headers={"User-Agent": headers["User-Agent"]},
            timeout=25,
        )
        if r.status_code == 200:
            html = decode_html(r.content)
            if is_valid_uz_content(html):
                return html
    except Exception:
        pass

    # 6. CorsProxy
    try:
        r = session.get(
            f"https://corsproxy.io/?{quote(URL, safe='')}",
            headers={"User-Agent": headers["User-Agent"]},
            timeout=25,
        )
        if r.status_code == 200:
            html = decode_html(r.content)
            if is_valid_uz_content(html):
                return html
    except Exception:
        pass

    return ""


def time_to_slot(hh: int, mm: int) -> int:
    total = hh * 60 + mm
    if total >= 1440:
        return 48
    if total <= 0:
        return 0
    return total // 30


def slot_to_str(idx: int) -> str:
    if idx >= 48:
        return "24:00"
    return f"{idx // 2:02d}:{'00' if idx % 2 == 0 else '30'}"


def slots_to_ranges(arr: list[int]) -> list[str]:
    res = []
    start = None
    for i in range(49):
        val = arr[i] if i < 48 else 0
        if val == 1 and start is None:
            start = i
        elif val == 0 and start is not None:
            res.append(f"{slot_to_str(start)}–{slot_to_str(i)}")
            start = None
    return res


def extract_queues(cell_text: str) -> set[str]:
    low = cell_text.lower()
    if "без гпв" in low:
        return set()
    found = set()
    for q_num, subs in re.findall(r"([1-6])\s*\(([^)]+)\)", cell_text):
        for s in re.split(r"[,.;\s/]+", subs.strip()):
            if s in ("1", "2"):
                found.add(f"{q_num}({s})")
    return found


def build_slots_from_cell_lists(t_texts: list[str], q_texts: list[str]) -> dict[str, list[int]]:
    cols = min(len(t_texts), len(q_texts))
    if cols < 2:
        return {}
    slots_map = {q: [0] * 48 for q in ALL_QUEUES}
    found_any_time = False
    for i in range(1, cols):
        times = re.findall(r"(\d{1,2})[-:.](\d{2})", t_texts[i])
        if len(times) < 2:
            continue
        found_any_time = True
        s_idx = time_to_slot(int(times[0][0]), int(times[0][1]))
        e_idx = time_to_slot(int(times[1][0]), int(times[1][1]))
        if e_idx <= s_idx:
            continue
        for q in extract_queues(q_texts[i]):
            for idx in range(s_idx, min(e_idx, 48)):
                slots_map[q][idx] = 1
    return slots_map if found_any_time else {}


def parse_html_table(table) -> dict[str, list[int]]:
    rows = table.find_all("tr")
    time_row = None
    queue_row = None
    for tr in rows:
        txt = tr.get_text(" ", strip=True).lower()
        if "годин" in txt and time_row is None:
            time_row = tr
        elif "черг" in txt and queue_row is None:
            queue_row = tr
    if not time_row or not queue_row:
        return {}
    t_texts = [c.get_text(" ", strip=True) for c in time_row.find_all(["td", "th"])]
    q_texts = [c.get_text(" ", strip=True) for c in queue_row.find_all(["td", "th"])]
    return build_slots_from_cell_lists(t_texts, q_texts)


def parse_ternopil_html(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    body = soup.body or soup
    in_ternopil = False
    current_date = None
    parsed_days = []
    seen_dates = set()

    for el in body.find_all(True):
        if el.find_parent("table"):
            continue
        if el.name == "table":
            if in_ternopil and current_date:
                slots_map = parse_html_table(el)
                if slots_map and current_date["date"] not in seen_dates:
                    seen_dates.add(current_date["date"])
                    parsed_days.append({
                        "date": current_date["date"],
                        "day": current_date["day"],
                        "month": current_date["month"],
                        "slots_map": slots_map,
                    })
            continue

        txt = " ".join(el.get_text(" ", strip=True).split())
        if not txt or len(txt) > 120:
            continue
        low = txt.lower()

        if "тернопільська область" in low:
            in_ternopil = True
            continue

        if in_ternopil:
            if "перелік адрес" in low or ("область" in low and "тернопільська" not in low):
                in_ternopil = False
                continue

            m = re.search(
                r"\b(\d{1,2})\s+(січня|лютого|березня|квітня|травня|червня|липня|серпня|вересня|жовтня|листопада|грудня)\b",
                low,
            )
            if m and len(txt) <= 45:
                day_num = int(m.group(1))
                month_name = m.group(2)
                current_date = {
                    "date": f"{day_num} {month_name}",
                    "day": day_num,
                    "month": MONTHS[month_name],
                }

    return parsed_days


def parse_ternopil_markdown(md: str) -> list[dict]:
    in_ternopil = False
    current_date = None
    parsed_days = []
    seen_dates = set()
    pending_time_cells = None

    for raw_line in md.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        if "|" in line:
            if not in_ternopil or not current_date:
                continue
            cells = [c.strip() for c in line.strip("|").split("|")]
            if not cells or all(set(c) <= set("-: ") for c in cells):
                continue
            first_low = cells[0].lower()
            if "годин" in first_low:
                pending_time_cells = cells
            elif "черг" in first_low and pending_time_cells:
                slots_map = build_slots_from_cell_lists(pending_time_cells, cells)
                pending_time_cells = None
                if slots_map and current_date["date"] not in seen_dates:
                    seen_dates.add(current_date["date"])
                    parsed_days.append({
                        "date": current_date["date"],
                        "day": current_date["day"],
                        "month": current_date["month"],
                        "slots_map": slots_map,
                    })
            continue

        clean = re.sub(r"[#*_`>]+", " ", line)
        clean = " ".join(clean.split())
        low = clean.lower()

        if "тернопільська область" in low:
            in_ternopil = True
            pending_time_cells = None
            continue

        if in_ternopil:
            if "перелік адрес" in low or ("область" in low and "тернопільська" not in low):
                in_ternopil = False
                pending_time_cells = None
                continue

            m = re.search(
                r"\b(\d{1,2})\s+(січня|лютого|березня|квітня|травня|червня|липня|серпня|вересня|жовтня|листопада|грудня)\b",
                low,
            )
            if m and len(clean) <= 50:
                day_num = int(m.group(1))
                month_name = m.group(2)
                current_date = {
                    "date": f"{day_num} {month_name}",
                    "day": day_num,
                    "month": MONTHS[month_name],
                }
                pending_time_cells = None

    return parsed_days


def parse_ternopil(content: str) -> list[dict]:
    res = parse_ternopil_html(content)
    if res:
        return res
    return parse_ternopil_markdown(content)


def is_past_day(day_num: int, month_num: int, now: datetime) -> bool:
    year = now.year
    if now.month == 12 and month_num == 1:
        year += 1
    elif now.month == 1 and month_num == 12:
        year -= 1
    target = datetime(year, month_num, day_num, tzinfo=KYIV_TZ).date()
    return target < now.date()


def get_site_url() -> str:
    custom = os.environ.get("SITE_URL", "").strip()
    if custom:
        return custom
    repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if "/" in repo:
        owner, name = repo.split("/", 1)
        return f"https://{owner}.github.io/{name}/"
    return URL


def send_telegram(text: str):
    token = os.environ.get("BOT_TOKEN", "").strip()
    chat_id = os.environ.get("CHAT_ID", "").strip()
    if not token or not chat_id:
        return
    api_url = f"https://api.telegram.org/bot{token}/sendMessage"
    site_url = get_site_url()
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
        "reply_markup": {
            "inline_keyboard": [
                [{"text": "📊 Відкрити графік", "web_app": {"url": site_url}}]
                if site_url.startswith("https://") and "github.io" in site_url
                else [{"text": "📊 Відкрити графік", "url": site_url}]
            ]
        },
    }
    try:
        requests.post(api_url, json=payload, timeout=15)
    except Exception:
        pass


def main():
    now = datetime.now(KYIV_TZ)
    prev_data = {"days": [], "notified": []}
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                prev_data = json.load(f)
        except Exception:
            prev_data = {"days": [], "notified": []}

    prev_by_date = {d["date"]: d for d in prev_data.get("days", [])}
    notified = list(prev_data.get("notified", []))
    raw_content = fetch_content()
    parsed = parse_ternopil(raw_content) if raw_content else []

    out_days = []
    alerts = []

    if parsed:
        for item in parsed:
            if is_past_day(item["day"], item["month"], now):
                continue
            d_label = item["date"]
            old_day = prev_by_date.get(d_label)
            old_queues = old_day.get("queues", {}) if old_day else {}
            queues_out = {}

            for q in ALL_QUEUES:
                cur = item["slots_map"][q]
                base = old_queues.get(q, {}).get("baseline")
                if not base or len(base) != 48:
                    base = list(cur)
                queues_out[q] = {"baseline": base, "current": cur}

            out_days.append({
                "date": d_label,
                "day": item["day"],
                "month": item["month"],
                "queues": queues_out,
            })

            new_61 = queues_out[TARGET_QUEUE]["current"]
            old_61 = old_queues.get(TARGET_QUEUE, {}).get("current")
            ranges_str = ", ".join(slots_to_ranges(new_61)) or "не заплановано"

            if old_61 is None:
                alerts.append(
                    f"📅 <b>Новий графік на {d_label}</b> (Черга {TARGET_QUEUE})\n"
                    f"Відключення: <b>{ranges_str}</b>"
                )
            elif old_61 != new_61:
                added = [1 if (new_61[i] == 1 and old_61[i] == 0) else 0 for i in range(48)]
                canceled = [1 if (new_61[i] == 0 and old_61[i] == 1) else 0 for i in range(48)]
                add_r = slots_to_ranges(added)
                can_r = slots_to_ranges(canceled)
                diff_lines = []
                if add_r:
                    diff_lines.append(f"🔴 Додали: <b>{', '.join(add_r)}</b>")
                if can_r:
                    diff_lines.append(f"🟢 Скасували: <b>{', '.join(can_r)}</b>")
                diff_txt = "\n".join(diff_lines)
                alerts.append(
                    f"⚠️ <b>Зміни у графіку на {d_label}</b> (Черга {TARGET_QUEUE})\n"
                    f"{diff_txt}\n"
                    f"Актуально: <b>{ranges_str}</b>"
                )
        source_ok = True
    else:
        out_days = [
            d for d in prev_data.get("days", [])
            if not is_past_day(d["day"], d["month"], now)
        ]
        source_ok = False

    today_label = f"{now.day} {list(MONTHS.keys())[now.month - 1]}"
    today_obj = next((d for d in out_days if d["date"] == today_label), None)
    if today_obj:
        cur_61 = today_obj["queues"][TARGET_QUEUE]["current"]
        now_mins = now.hour * 60 + now.minute
        for idx in range(48):
            prev_val = cur_61[idx - 1] if idx > 0 else 0
            cur_val = cur_61[idx]
            if cur_val != prev_val:
                event_mins = idx * 30
                diff = event_mins - now_mins
                if 1 <= diff <= 35:
                    t_str = slot_to_str(idx)
                    ev_type = "off" if cur_val == 1 else "on"
                    n_key = f"{today_label}_{ev_type}_{t_str}"
                    if n_key not in notified:
                        notified.append(n_key)
                        if ev_type == "off":
                            alerts.append(f"🔴 <b>Через {diff} хв (о {t_str})</b> відключення світла!")
                        else:
                            alerts.append(f"🟢 <b>Через {diff} хв (о {t_str})</b> увімкнуть світло!")

    if os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch" and not alerts:
        if source_ok and out_days:
            d0 = out_days[0]
            r0 = ", ".join(slots_to_ranges(d0["queues"][TARGET_QUEUE]["current"])) or "не заплановано"
            alerts.append(
                f"✅ <b>Синхронізація з УЗ працює!</b>\n"
                f"📅 <b>{d0['date']}</b> (Черга {TARGET_QUEUE}): <b>{r0}</b>"
            )
        elif not source_ok:
            alerts.append("⚠️ УЗ тимчасово заблокувала запит із сервера, використано кеш.")

    for msg in alerts:
        send_telegram(msg)

    result = {
        "updated_at": now.isoformat(timespec="seconds"),
        "updated_str": now.strftime("%d.%m %H:%M"),
        "source_ok": source_ok,
        "notified": notified[-30:],
        "days": out_days,
    }

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
