import json
import os
import re
import ssl
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from urllib.parse import quote
from zoneinfo import ZoneInfo

try:
    import socks  # noqa: F401
except ImportError:
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "pysocks"], check=False)

import requests
import urllib3
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.poolmanager import PoolManager

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

UZ_URL = "[https://www.uz.gov.ua/about/activity/electropostachannia/electro_consumers/temporary_shutdown/grafikiobmezhen/622368/](https://www.uz.gov.ua/about/activity/electropostachannia/electro_consumers/temporary_shutdown/grafikiobmezhen/622368/)"
UZ_TRANSLATE_URL = "[https://www-uz-gov-ua.translate.goog/about/activity/electropostachannia/electro_consumers/temporary_shutdown/grafikiobmezhen/622368/?_x_tr_sl=uk&_x_tr_tl=en&_x_tr_hl=uk&_x_tr_pto=wapp](https://www-uz-gov-ua.translate.goog/about/activity/electropostachannia/electro_consumers/temporary_shutdown/grafikiobmezhen/622368/?_x_tr_sl=uk&_x_tr_tl=en&_x_tr_hl=uk&_x_tr_pto=wapp)"
FIREBASE_URL = "[https://svitlo-12122-default-rtdb.europe-west1.firebasedatabase.app](https://svitlo-12122-default-rtdb.europe-west1.firebasedatabase.app)"
ADMIN_ID = "549556547"
DATA_FILE = "data.json"
TARGET_QUEUE = "6(1)"
KYIV_TZ = ZoneInfo("Europe/Kyiv")
MAX_ARCHIVE_DAYS = 30

MONTHS_UA = [
    "січня", "лютого", "березня", "квітня", "травня", "червня",
    "липня", "серпня", "вересня", "жовтня", "листопада", "грудня",
]

MONTHS_MAP = {
    "січня": 1, "лютого": 2, "березня": 3, "квітня": 4,
    "травня": 5, "червня": 6, "липня": 7, "серпня": 8,
    "вересня": 9, "жовтня": 10, "листопада": 11, "грудня": 12,
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}

ALL_QUEUES = [f"{q}({s})" for q in range(1, 7) for s in (1, 2)]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "uk-UA,uk;q=0.9,en;q=0.8",
    "Referer": "[https://www.uz.gov.ua/](https://www.uz.gov.ua/)",
}


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


def make_session() -> requests.Session:
    s = requests.Session()
    s.mount("https://", LegacySSLAdapter())
    s.mount("http://", LegacySSLAdapter())
    return s


def decode_html(raw: bytes) -> str:
    for enc in ("utf-8", "windows-1251", "cp1251"):
        try:
            text = raw.decode(enc)
            low = text.lower()
            if "тернопільська" in low or "ternopil" in low or "години" in low:
                return text
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="ignore")


def is_valid_uz_content(text: str) -> bool:
    if not text or len(text) < 500:
        return False
    low = text.lower()
    has_region = ("тернопільська" in low) or ("ternopil" in low)
    has_table = ("годин" in low) or ("черг" in low) or ("hour" in low) or ("queue" in low)
    return has_region and has_table


def get_ua_proxies() -> list[str]:
    proxies = []
    seen = set()

    def add_proxy(p: str, default_scheme: str = "http"):
        p = p.strip()
        if not p or p.startswith("#"):
            return
        if "://" not in p:
            p = f"{default_scheme}://{p}"
        if p.startswith("socks5://"):
            p = "socks5h://" + p[len("socks5://"):]
        if p not in seen:
            seen.add(p)
            proxies.append(p)

    try:
        r = requests.get(
            "[https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/countries/UA/data.txt](https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/countries/UA/data.txt)",
            timeout=8,
        )
        if r.status_code == 200:
            for line in r.text.splitlines():
                add_proxy(line)
    except Exception:
        pass

    for proto, scheme in [("http", "http"), ("socks5", "socks5h"), ("socks4", "socks4")]:
        try:
            r = requests.get(
                f"[https://api.proxyscrape.com/v2/?request=displayproxies&protocol=](https://api.proxyscrape.com/v2/?request=displayproxies&protocol=){proto}&timeout=10000&country=UA",
                timeout=8,
            )
            if r.status_code == 200:
                for line in r.text.splitlines():
                    add_proxy(line, scheme)
        except Exception:
            pass

    try:
        r = requests.get(
            "[https://proxylist.geonode.com/api/proxy-list?country=UA&limit=100&page=1&sort_by=lastChecked&sort_type=desc](https://proxylist.geonode.com/api/proxy-list?country=UA&limit=100&page=1&sort_by=lastChecked&sort_type=desc)",
            timeout=8,
        )
        if r.status_code == 200:
            for item in r.json().get("data", []):
                ip = item.get("ip")
                port = item.get("port")
                protos = item.get("protocols") or ["http"]
                if ip and port:
                    sch = "socks5h" if "socks5" in protos else ("socks4" if "socks4" in protos else "http")
                    add_proxy(f"{ip}:{port}", sch)
    except Exception:
        pass

    for proto, scheme in [("http", "http"), ("socks5", "socks5h"), ("socks4", "socks4")]:
        try:
            r = requests.get(
                f"[https://www.proxy-list.download/api/v1/get?type=](https://www.proxy-list.download/api/v1/get?type=){proto}&country=UA",
                timeout=8,
            )
            if r.status_code == 200:
                for line in r.text.splitlines():
                    add_proxy(line, scheme)
        except Exception:
            pass

    return proxies[:120]


def fetch_via_proxy(proxy_url: str) -> str:
    try:
        s = make_session()
        resp = s.get(
            UZ_URL,
            headers=HEADERS,
            proxies={"http": proxy_url, "https": proxy_url},
            timeout=9,
            verify=False,
        )
        if resp.status_code == 200:
            html = decode_html(resp.content)
            if is_valid_uz_content(html):
                return html
    except Exception:
        pass
    return ""


def fetch_content() -> tuple[str, str]:
    errors = []
    session = make_session()

    try:
        resp = session.get(UZ_URL, headers=HEADERS, timeout=10, verify=False)
        if resp.status_code == 200:
            html = decode_html(resp.content)
            if is_valid_uz_content(html):
                return html, "direct"
            errors.append("direct:blocked")
        else:
            errors.append(f"direct:{resp.status_code}")
    except Exception as e:
        errors.append(f"direct:{type(e).__name__}")

    ua_proxies = get_ua_proxies()
    if ua_proxies:
        executor = ThreadPoolExecutor(max_workers=35)
        futures = {executor.submit(fetch_via_proxy, p): p for p in ua_proxies}
        try:
            for fut in as_completed(futures, timeout=22):
                html = fut.result()
                if html:
                    p_used = futures[fut].split("://")[0]
                    executor.shutdown(wait=False, cancel_futures=True)
                    return html, f"ua_{p_used}"
        except Exception:
            pass
        finally:
            executor.shutdown(wait=False, cancel_futures=True)
        errors.append(f"ua_proxies({len(ua_proxies)}):0_ok")
    else:
        errors.append("ua_proxies:empty")

    try:
        r = session.get(UZ_TRANSLATE_URL, headers=HEADERS, timeout=15)
        if r.status_code == 200:
            html = decode_html(r.content)
            if is_valid_uz_content(html):
                return html, "gtranslate"
        errors.append(f"gt:{r.status_code}")
    except Exception as e:
        errors.append(f"gt:{type(e).__name__}")

    for name, p_url in [
        ("allorigins", f"[https://api.allorigins.win/get?url=](https://api.allorigins.win/get?url=){quote(UZ_URL, safe='')}"),
        ("codetabs", f"[https://api.codetabs.com/v1/proxy?quest=](https://api.codetabs.com/v1/proxy?quest=){quote(UZ_URL, safe='')}"),
        ("corsproxy", f"[https://corsproxy.io/](https://corsproxy.io/)?{quote(UZ_URL, safe='')}"),
    ]:
        try:
            r = session.get(p_url, headers={"User-Agent": HEADERS["User-Agent"]}, timeout=15)
            if r.status_code == 200:
                txt = r.json().get("contents", "") if name == "allorigins" else decode_html(r.content)
                if is_valid_uz_content(txt):
                    return txt, name
            errors.append(f"{name}:{r.status_code}")
        except Exception as e:
            errors.append(f"{name}:{type(e).__name__}")

    reason = ", ".join(errors[:5])
    print("Fetch failed:", reason)
    return "", reason


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
    if "без гпв" in low or "without" in low:
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
        if ("годин" in txt or "hour" in txt) and time_row is None:
            time_row = tr
        elif ("черг" in txt or "queue" in txt) and queue_row is None:
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
    months_pattern = "|".join(MONTHS_MAP.keys())

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

        if "тернопільська область" in low or "ternopil region" in low or "ternopil oblast" in low:
            in_ternopil = True
            continue

        if in_ternopil:
            if (
                "перелік адрес" in low
                or "list of addresses" in low
                or ("область" in low and "тернопільська" not in low)
                or (("region" in low or "oblast" in low) and "ternopil" not in low)
            ):
                in_ternopil = False
                continue

            m = re.search(rf"\b(\d{{1,2}})\s+({months_pattern})\b", low)
            if not m:
                m2 = re.search(rf"\b({months_pattern})\s+(\d{{1,2}})\b", low)
                if m2 and len(txt) <= 45:
                    month_num = MONTHS_MAP[m2.group(1)]
                    day_num = int(m2.group(2))
                    current_date = {
                        "date": f"{day_num} {MONTHS_UA[month_num - 1]}",
                        "day": day_num,
                        "month": month_num,
                    }
            elif len(txt) <= 45:
                day_num = int(m.group(1))
                month_num = MONTHS_MAP[m.group(2)]
                current_date = {
                    "date": f"{day_num} {MONTHS_UA[month_num - 1]}",
                    "day": day_num,
                    "month": month_num,
                }

    return parsed_days


def resolve_day_date(day_num: int, month_num: int, now: datetime):
    year = now.year
    if now.month == 12 and month_num == 1:
        year += 1
    elif now.month == 1 and month_num == 12:
        year -= 1
    return datetime(year, month_num, day_num, tzinfo=KYIV_TZ).date()


def is_too_old(day_num: int, month_num: int, now: datetime) -> bool:
    target = resolve_day_date(day_num, month_num, now)
    return (now.date() - target).days > MAX_ARCHIVE_DAYS


def is_past_day(day_num: int, month_num: int, now: datetime) -> bool:
    target = resolve_day_date(day_num, month_num, now)
    return target < now.date()


def get_site_url() -> str:
    custom = os.environ.get("SITE_URL", "").strip()
    if custom:
        return custom
    repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if "/" in repo:
        owner, name = repo.split("/", 1)
        return f"https://{owner}.github.io/{name}/"
    return UZ_URL


def _send_to_bot(token: str, chat_id: str, text: str, site_url: str, include_browser_btn: bool = False):
    if not token or not chat_id:
        return
    api_url = f"[https://api.telegram.org/bot](https://api.telegram.org/bot){token}/sendMessage"
    is_gh = site_url.startswith("https://") and "github.io" in site_url
    kb = [
        [{"text": "📊 Відкрити графік", "web_app": {"url": site_url}}]
        if is_gh
        else [{"text": "📊 Відкрити графік", "url": site_url}]
    ]
    if include_browser_btn and is_gh:
        kb.append([{"text": "🌐 Відкрити сайт у браузері", "url": site_url}])

    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
        "reply_markup": {"inline_keyboard": kb},
    }
    try:
        requests.post(api_url, json=payload, timeout=15)
    except Exception:
        pass


def send_telegram(text: str):
    chat_id = os.environ.get("CHAT_ID", "").strip()
    token_main = os.environ.get("BOT_TOKEN", "").strip()
    token_test = os.environ.get("BOT_TOKEN_2", "").strip()

    base_url = get_site_url()
    _send_to_bot(token_main, chat_id, text, base_url)
    if token_test:
        _send_to_bot(token_test, chat_id, text, base_url)


def format_ranges_column(ranges_list: list[str], prefix: str = "") -> str:
    if not ranges_list:
        return "не заплановано"
    return "\n".join(f"{prefix}{r}" for r in ranges_list)


def format_ranges_dots(ranges_list: list[str]) -> str:
    if not ranges_list:
        return "🟢 Відключень не заплановано"
    return "\n".join(f"🔴 {r}" for r in ranges_list)


def get_active_vip_users(now: datetime) -> dict[str, str]:
    now_ms = int(now.timestamp() * 1000)
    try:
        r_vip = requests.get(f"{FIREBASE_URL}/config/vip.json", timeout=8)
        vip_map = r_vip.json() if r_vip.status_code == 200 else {}
        if not isinstance(vip_map, dict):
            return {}

        r_users = requests.get(f"{FIREBASE_URL}/users.json", timeout=8)
        users_map = r_users.json() if r_users.status_code == 200 else {}
        if not isinstance(users_map, dict):
            users_map = {}

        active_vips = {}
        for uid, entry in vip_map.items():
            uid_str = str(uid).strip()
            if not uid_str.isdigit() or uid_str == ADMIN_ID:
                continue
            is_active = False
            if entry is True:
                is_active = True
            elif isinstance(entry, dict) and entry.get("until", 0) > now_ms:
                is_active = True

            if is_active:
                u_info = users_map.get(uid_str) or {}
                q = u_info.get("queue", TARGET_QUEUE)
                if q not in ALL_QUEUES:
                    q = TARGET_QUEUE
                active_vips[uid_str] = q
        return active_vips
    except Exception:
        return {}


def handle_bot_starts(token: str, last_update_id: int, d0: dict | None, site_url: str, now: datetime) -> int:
    if not token:
        return last_update_id
    api_url = f"[https://api.telegram.org/bot](https://api.telegram.org/bot){token}/getUpdates"
    try:
        r = requests.get(api_url, params={"offset": last_update_id + 1, "timeout": 2}, timeout=10)
        if r.status_code != 200:
            return last_update_id
        updates = r.json().get("result", [])
    except Exception:
        return last_update_id

    max_id = last_update_id
    for upd in updates:
        uid_num = upd.get("update_id", 0)
        if uid_num > max_id:
            max_id = uid_num

        msg = upd.get("message") or {}
        txt = (msg.get("text") or "").strip()
        chat = msg.get("chat") or {}
        chat_id = str(chat.get("id", ""))

        if chat_id and txt.startswith("/start"):
            name = " ".join(filter(None, [chat.get("first_name"), chat.get("last_name")])) or "Користувач"
            username = f"@{chat['username']}" if chat.get("username") else ""
            try:
                requests.patch(
                    f"{FIREBASE_URL}/bot_subscribers/{chat_id}.json",
                    json={
                        "id": chat_id,
                        "name": name,
                        "username": username,
                        "last_start": now.strftime("%d.%m %H:%M"),
                        "ts": int(now.timestamp() * 1000),
                    },
                    timeout=5,
                )
            except Exception:
                pass

            if d0:
                r_dots = format_ranges_dots(slots_to_ranges(d0["queues"][TARGET_QUEUE]["current"]))
                reply_txt = (
                    f"📅 <b>{d0['date']}</b> • Черга <b>{TARGET_QUEUE}</b>\n\n"
                    f"📋 <b>Актуальний графік відключень:</b>\n"
                    f"<b>{r_dots}</b>\n\n"
                    f"🌐 Веб-версія: {site_url}\n"
                    f"👇 Оберіть свою чергу та відкрийте таймер:"
                )
            else:
                reply_txt = (
                    f"⚡ <b>Світло УЗ • Графік відключень</b>\n\n"
                    f"🌐 Веб-версія: {site_url}\n"
                    f"👇 Натисніть кнопку нижче, щоб переглянути графік:"
                )
            _send_to_bot(token, chat_id, reply_txt, site_url, include_browser_btn=True)

    return max_id


def main():
    now = datetime.now(KYIV_TZ)
    prev_data = {"days": [], "notified": [], "last_update_id": 0, "last_update_id_2": 0}
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                prev_data = json.load(f)
        except Exception:
            prev_data = {"days": [], "notified": [], "last_update_id": 0, "last_update_id_2": 0}

    prev_by_date = {d["date"]: d for d in prev_data.get("days", [])}
    notified = list(prev_data.get("notified", []))
    last_update_id = int(prev_data.get("last_update_id", 0) or 0)
    last_update_id_2 = int(prev_data.get("last_update_id_2", 0) or 0)

    raw_content, status_info = fetch_content()
    parsed = parse_ternopil_html(raw_content) if raw_content else []

    active_vips = get_active_vip_users(now)
    vip_alerts: list[tuple[str, str]] = []

    days_map = {}
    for d in prev_data.get("days", []):
        if not is_too_old(d["day"], d["month"], now):
            days_map[d["date"]] = d

    alerts = []

    if parsed:
        for item in parsed:
            if is_too_old(item["day"], item["month"], now):
                continue
            d_label = item["date"]
            old_day = prev_by_date.get(d_label)
            old_queues = old_day.get("queues", {}) if old_day else {}
            history_log = list(old_day.get("history", [])) if old_day else []
            queues_out = {}

            for q in ALL_QUEUES:
                cur = item["slots_map"][q]
                base = old_queues.get(q, {}).get("baseline")
                if not base or len(base) != 48:
                    base = list(cur)
                queues_out[q] = {"baseline": base, "current": cur}

            new_61 = queues_out[TARGET_QUEUE]["current"]
            old_61 = old_queues.get(TARGET_QUEUE, {}).get("current")
            ranges_list = slots_to_ranges(new_61)
            ranges_col = format_ranges_column(ranges_list)

            if old_61 is None:
                history_log.append({
                    "time": now.strftime("%H:%M"),
                    "type": "init",
                    "removed_light": [],
                    "added_light": [],
                    "ranges": ranges_list,
                })
                if not is_past_day(item["day"], item["month"], now):
                    alerts.append(
                        f"📅 <b>Новий графік на {d_label}</b> (Черга {TARGET_QUEUE})\n\n"
                        f"📋 <b>Актуальний графік:</b>\n"
                        f"<b>{ranges_col}</b>"
                    )
            elif old_61 != new_61:
                removed_light = [1 if (new_61[i] == 1 and old_61[i] == 0) else 0 for i in range(48)]
                added_light = [1 if (new_61[i] == 0 and old_61[i] == 1) else 0 for i in range(48)]
                rem_r = slots_to_ranges(removed_light)
                add_r = slots_to_ranges(added_light)

                history_log.append({
                    "time": now.strftime("%H:%M"),
                    "type": "update",
                    "removed_light": rem_r,
                    "added_light": add_r,
                    "ranges": ranges_list,
                })

                if not is_past_day(item["day"], item["month"], now):
                    diff_blocks = []
                    if rem_r:
                        diff_blocks.append(
                            f"🔴 <b>Додали відключення:</b>\n<b>{format_ranges_column(rem_r, '-')}</b>"
                        )
                    if add_r:
                        diff_blocks.append(
                            f"🟢 <b>Скасували відключення:</b>\n<b>{format_ranges_column(add_r, '+')}</b>"
                        )
                    diff_txt = "\n".join(diff_blocks)
                    alerts.append(
                        f"⚠️ <b>Зміни у графіку на {d_label}</b> (Черга {TARGET_QUEUE})\n"
                        f"{diff_txt}\n\n"
                        f"📋 <b>Актуальний графік:</b>\n"
                        f"<b>{ranges_col}</b>"
                    )

            if not is_past_day(item["day"], item["month"], now) and active_vips:
                for vip_uid, vip_q in active_vips.items():
                    new_vq = queues_out[vip_q]["current"]
                    old_vq = old_queues.get(vip_q, {}).get("current")
                    vq_dots = format_ranges_dots(slots_to_ranges(new_vq))
                    if old_vq is None:
                        vip_alerts.append((
                            vip_uid,
                            f"📅 <b>Новий графік на {d_label}</b> (Черга <b>{vip_q}</b>)\n\n"
                            f"📋 <b>Актуальний графік:</b>\n<b>{vq_dots}</b>"
                        ))
                    elif old_vq != new_vq:
                        v_rem = slots_to_ranges([1 if (new_vq[i] == 1 and old_vq[i] == 0) else 0 for i in range(48)])
                        v_add = slots_to_ranges([1 if (new_vq[i] == 0 and old_vq[i] == 1) else 0 for i in range(48)])
                        v_blocks = []
                        if v_rem:
                            v_blocks.append(f"🔴 <b>Додали відключення:</b>\n<b>{format_ranges_column(v_rem, '-')}</b>")
                        if v_add:
                            v_blocks.append(f"🟢 <b>Скасували відключення:</b>\n<b>{format_ranges_column(v_add, '+')}</b>")
                        v_diff = "\n".join(v_blocks)
                        vip_alerts.append((
                            vip_uid,
                            f"⚠️ <b>Зміни у графіку на {d_label}</b> (Черга <b>{vip_q}</b>)\n"
                            f"{v_diff}\n\n"
                            f"📋 <b>Актуальний графік:</b>\n<b>{vq_dots}</b>"
                        ))

            days_map[d_label] = {
                "date": d_label,
                "day": item["day"],
                "month": item["month"],
                "queues": queues_out,
                "history": history_log[-25:],
            }
        source_ok = True
    else:
        source_ok = False

    out_days = sorted(
        days_map.values(),
        key=lambda x: resolve_day_date(x["day"], x["month"], now),
    )

    today_label = f"{now.day} {MONTHS_UA[now.month - 1]}"
    today_obj = next((d for d in out_days if d["date"] == today_label), None)
    if today_obj:
        now_mins = now.hour * 60 + now.minute
        cur_61 = today_obj["queues"][TARGET_QUEUE]["current"]
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

        for vip_uid, vip_q in active_vips.items():
            cur_vq = today_obj["queues"][vip_q]["current"]
            for idx in range(48):
                prev_val = cur_vq[idx - 1] if idx > 0 else 0
                cur_val = cur_vq[idx]
                if cur_val != prev_val:
                    event_mins = idx * 30
                    diff = event_mins - now_mins
                    if 1 <= diff <= 35:
                        t_str = slot_to_str(idx)
                        ev_type = "off" if cur_val == 1 else "on"
                        n_key = f"vip_{vip_uid}_{today_label}_{ev_type}_{t_str}"
                        if n_key not in notified:
                            notified.append(n_key)
                            if ev_type == "off":
                                vip_alerts.append((
                                    vip_uid,
                                    f"🔴 <b>Через {diff} хв (о {t_str})</b> можливе відключення світла! (Черга <b>{vip_q}</b>)"
                                ))
                            else:
                                vip_alerts.append((
                                    vip_uid,
                                    f"🟢 <b>Через {diff} хв (о {t_str})</b> можливе увімкнення світла! (Черга <b>{vip_q}</b>)"
                                ))

    if os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch" and not alerts:
        if source_ok and out_days:
            d0 = today_obj or out_days[-1]
            r0_col = format_ranges_column(slots_to_ranges(d0["queues"][TARGET_QUEUE]["current"]))
            alerts.append(
                f"✅ <b>Синхронізація з УЗ працює!</b> ({status_info})\n"
                f"📅 <b>{d0['date']}</b> (Черга {TARGET_QUEUE})\n\n"
                f"📋 <b>Актуальний графік:</b>\n"
                f"<b>{r0_col}</b>"
            )
        elif not source_ok:
            alerts.append(f"⚠️ УЗ заблокувала запит ({status_info}), використано кеш.")

    for msg in alerts:
        send_telegram(msg)

    site_url = get_site_url()
    token_main = os.environ.get("BOT_TOKEN", "").strip()
    token_test = os.environ.get("BOT_TOKEN_2", "").strip()
    vip_bot_token = token_test or token_main

    for vip_uid, v_msg in vip_alerts:
        _send_to_bot(vip_bot_token, vip_uid, v_msg, site_url)

    d_for_start = today_obj or (out_days[-1] if out_days else None)
    new_last_update_id = handle_bot_starts(token_main, last_update_id, d_for_start, site_url, now)
    new_last_update_id_2 = handle_bot_starts(token_test, last_update_id_2, d_for_start, site_url, now)

    result = {
        "updated_at": now.isoformat(timespec="seconds"),
        "updated_str": now.strftime("%d.%m %H:%M"),
        "source_ok": source_ok,
        "fetch_info": status_info,
        "last_update_id": new_last_update_id,
        "last_update_id_2": new_last_update_id_2,
        "notified": notified[-150:],
        "days": out_days,
    }

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
