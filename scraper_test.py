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

UZ_URL = "https://www.uz.gov.ua/about/activity/electropostachannia/electro_consumers/temporary_shutdown/grafikiobmezhen/622368/"
UZ_TRANSLATE_URL = "https://www-uz-gov-ua.translate.goog/about/activity/electropostachannia/electro_consumers/temporary_shutdown/grafikiobmezhen/622368/?_x_tr_sl=uk&_x_tr_tl=en&_x_tr_hl=uk&_x_tr_pto=wapp"
FIREBASE_URL = "https://svitlo-12122-default-rtdb.europe-west1.firebasedatabase.app"
ADMIN_ID = "549556547"
DATA_FILE = "data_test.json"
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
    "Referer": "https://www.uz.gov.ua/",
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
            "https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/countries/UA/data.txt",
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
                f"https://api.proxyscrape.com/v2/?request=displayproxies&protocol={proto}&timeout=10000&country=UA",
                timeout=8,
            )
            if r.status_code == 200:
                for line in r.text.splitlines():
                    add_proxy(line, scheme)
        except Exception:
            pass

    try:
        r = requests.get(
            "https://proxylist.geonode.com/api/proxy-list?country=UA&limit=100&page=1&sort_by=lastChecked&sort_type=desc",
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
                f"https://www.proxy-list.download/api/v1/get?type={proto}&country=UA",
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
        ("allorigins", f"https://api.allorigins.win/get?url={quote(UZ_URL, safe='')}"),
        ("codetabs", f"https://api.codetabs.com/v1/proxy?quest={quote(UZ_URL, safe='')}"),
        ("corsproxy", f"https://corsproxy.io/?{quote(UZ_URL, safe='')}"),
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


TOE_QUEUES = [f"{q}.{s}" for q in range(1, 7) for s in (1, 2)]

TOE_API_URLS = [
    "https://api-poweron.toe.com.ua/api/a_gpv_g?before=1&after=2",
    "https://api-poweron.toe.com.ua/api/a_gpv_g",
    "https://api--poweron-toe-com-ua.translate.goog/api/a_gpv_g?before=1&after=2&_x_tr_sl=uk&_x_tr_tl=en&_x_tr_hl=uk&_x_tr_pto=wapp",
]

TOE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "application/ld+json, application/json, text/plain, */*",
    "Accept-Language": "uk-UA,uk;q=0.9,en;q=0.8",
    "Origin": "https://poweron.toe.com.ua",
    "Referer": "https://poweron.toe.com.ua/",
}


def _normalize_toe_q(raw_q: str) -> str | None:
    s = str(raw_q).strip().lower()
    s = s.replace("ch_", "").replace("queue_", "").replace("черг", "").replace("а", "").strip()
    m = re.search(r"([1-6])[._\-/\(\s]+([12])", s)
    if m:
        return f"{m.group(1)}.{m.group(2)}"
    return None


def _toe_val_to_off(val) -> int:
    if val is None:
        return 0
    if isinstance(val, bool):
        return 1 if val else 0
    if isinstance(val, (int, float)):
        return 1 if int(val) >= 1 else 0
    s = str(val).strip().lower()
    if s in ("", "0", "on", "yes", "true", "light", "green", "white", "ok", "none"):
        return 0
    return 1


def _fill_slots_from_series(obj) -> list[int]:
    slots = [0] * 48
    if isinstance(obj, list) and len(obj) >= 24:
        if all(isinstance(x, dict) for x in obj):
            found = False
            for i, row in enumerate(obj[:48]):
                idx = i
                for tk in ("time", "hour", "slot", "period", "time_from", "start"):
                    if tk in row:
                        m = re.search(r"(\d{1,2})[:.-](\d{2})", str(row[tk]))
                        if m:
                            idx = time_to_slot(int(m.group(1)), int(m.group(2)))
                        break
                if 0 <= idx < 48:
                    for vk in ("value", "status", "state", "off", "is_off", "type"):
                        if vk in row:
                            slots[idx] = _toe_val_to_off(row[vk])
                            found = True
                            break
            return slots if found else []
        if len(obj) >= 48:
            return [_toe_val_to_off(obj[i]) for i in range(48)]
        for h in range(24):
            v = _toe_val_to_off(obj[h])
            slots[h * 2] = v
            slots[h * 2 + 1] = v
        return slots

    if isinstance(obj, dict):
        found = False
        for t_key, val in obj.items():
            m = re.search(r"(\d{1,2})[:.-](\d{2})", str(t_key))
            if not m:
                continue
            idx = time_to_slot(int(m.group(1)), int(m.group(2)))
            if 0 <= idx < 48:
                found = True
                slots[idx] = _toe_val_to_off(val)
        return slots if found else []

    return []


def _extract_all_toe_queues(time_series, single_queue_hint: str | None = None) -> dict[str, list[int]]:
    slots_map = {q: [0] * 48 for q in TOE_QUEUES}
    found_queues = set()

    if single_queue_hint and single_queue_hint in slots_map:
        arr = _fill_slots_from_series(time_series)
        if arr and len(arr) == 48:
            slots_map[single_queue_hint] = arr
            return slots_map

    if isinstance(time_series, dict):
        for k, sub in time_series.items():
            nq = _normalize_toe_q(k)
            if nq and nq in slots_map:
                arr = _fill_slots_from_series(sub)
                if arr and len(arr) == 48:
                    slots_map[nq] = arr
                    found_queues.add(nq)
        if found_queues:
            return slots_map

        for t_key, val in time_series.items():
            m = re.search(r"(\d{1,2})[:.-](\d{2})", str(t_key))
            if not m or not isinstance(val, dict):
                continue
            idx = time_to_slot(int(m.group(1)), int(m.group(2)))
            if 0 <= idx < 48:
                for q_raw, q_val in val.items():
                    nq = _normalize_toe_q(q_raw)
                    if nq and nq in slots_map:
                        slots_map[nq][idx] = _toe_val_to_off(q_val)
                        found_queues.add(nq)
        if found_queues:
            return slots_map

    if isinstance(time_series, list) and len(time_series) >= 24:
        for i, row in enumerate(time_series[:48]):
            if not isinstance(row, dict):
                continue
            idx = i
            for tk in ("time", "hour", "slot", "period", "time_from"):
                if tk in row:
                    m = re.search(r"(\d{1,2})[:.-](\d{2})", str(row[tk]))
                    if m:
                        idx = time_to_slot(int(m.group(1)), int(m.group(2)))
                    break
            if 0 <= idx < 48:
                for q_raw, q_val in row.items():
                    nq = _normalize_toe_q(q_raw)
                    if nq and nq in slots_map:
                        slots_map[nq][idx] = _toe_val_to_off(q_val)
                        found_queues.add(nq)
        if found_queues:
            return slots_map

    return {}


def parse_toe_json(payload) -> list[dict]:
    items = []
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        for k in ("hydra:member", "data", "items", "results", "graphs", "schedules"):
            if isinstance(payload.get(k), list):
                items = payload[k]
                break
        if not items and any(k in payload for k in ("time_series", "date_graph", "date")):
            items = [payload]

    by_date: dict[str, dict] = {}
    for it in items:
        if not isinstance(it, dict):
            continue
        raw_date = ""
        for dk in ("date_graph", "date", "graph_date", "day", "start_date"):
            if it.get(dk):
                raw_date = str(it[dk]).strip()
                break
        if not raw_date:
            continue

        day_num, month_num = None, None
        m_iso = re.search(r"(\d{4})-(\d{2})-(\d{2})", raw_date)
        if m_iso:
            month_num = int(m_iso.group(2))
            day_num = int(m_iso.group(3))
        else:
            m_ua = re.search(r"(\d{1,2})\.(\d{2})(?:\.\d{4})?", raw_date)
            if m_ua:
                day_num = int(m_ua.group(1))
                month_num = int(m_ua.group(2))

        if not day_num or not month_num or not (1 <= month_num <= 12) or not (1 <= day_num <= 31):
            continue

        q_hint = None
        for qk in ("queue", "group", "cherga", "subqueue", "name"):
            if it.get(qk):
                q_hint = _normalize_toe_q(str(it[qk]))
                if q_hint:
                    break

        ts_obj = None
        for tk in ("time_series", "series", "hours", "slots", "schedule", "queues"):
            if it.get(tk) is not None:
                ts_obj = it[tk]
                break
        if ts_obj is None:
            ts_obj = it

        q_map = _extract_all_toe_queues(ts_obj, single_queue_hint=q_hint)
        if not q_map:
            continue

        d_label = f"{day_num} {MONTHS_UA[month_num - 1]}"
        if d_label not in by_date:
            by_date[d_label] = {
                "date": d_label,
                "day": day_num,
                "month": month_num,
                "slots_map": {q: [0] * 48 for q in TOE_QUEUES},
            }
        for q, arr in q_map.items():
            if any(arr):
                by_date[d_label]["slots_map"][q] = arr

    return list(by_date.values())


def _try_toe_request(session: requests.Session, url: str, proxy_url: str | None = None) -> tuple[list[dict], str]:
    kwargs = {"headers": TOE_HEADERS, "timeout": 10, "verify": False}
    if proxy_url:
        kwargs["proxies"] = {"http": proxy_url, "https": proxy_url}
    r = session.get(url, **kwargs)
    if r.status_code != 200:
        return [], f"http_{r.status_code}"
    raw_txt = r.content.decode("utf-8-sig", errors="ignore").strip()
    if not raw_txt:
        return [], "empty_200"
    try:
        data = json.loads(raw_txt)
    except Exception:
        snippet = re.sub(r"<[^>]+>", " ", raw_txt)
        snippet = " ".join(snippet.split())[:55]
        return [], f"non_json({snippet})"
    parsed = parse_toe_json(data)
    if parsed:
        return parsed, "ok"
    keys_hint = list(data.keys())[:4] if isinstance(data, dict) else f"list({len(data)})"
    return [], f"unparsed({keys_hint})"


def fetch_toe_all(ua_proxies: list[str] | None = None) -> tuple[list[dict], str]:
    session = make_session()
    errors = []

    for idx, url in enumerate(TOE_API_URLS):
        tag = "gt" if "translate.goog" in url else f"d{idx+1}"
        try:
            res, info = _try_toe_request(session, url, None)
            if res:
                return res, tag
            errors.append(f"{tag}:{info}")
        except Exception as e:
            errors.append(f"{tag}:{type(e).__name__}")

    if ua_proxies is None:
        ua_proxies = get_ua_proxies()
    if ua_proxies:
        target_url = TOE_API_URLS[0]
        executor = ThreadPoolExecutor(max_workers=35)
        futures = {executor.submit(_try_toe_request, make_session(), target_url, p): p for p in ua_proxies}
        try:
            for fut in as_completed(futures, timeout=22):
                try:
                    res, _ = fut.result()
                    if res:
                        p_used = futures[fut].split("://")[0]
                        executor.shutdown(wait=False, cancel_futures=True)
                        return res, f"ua_{p_used}"
                except Exception:
                    pass
        except Exception:
            pass
        finally:
            executor.shutdown(wait=False, cancel_futures=True)
        errors.append(f"ua({len(ua_proxies)}):0_ok")

    target_api = TOE_API_URLS[0]
    for name, p_url in [
        ("allorigins", f"https://api.allorigins.win/get?url={quote(target_api, safe='')}"),
        ("codetabs", f"https://api.codetabs.com/v1/proxy?quest={quote(target_api, safe='')}"),
        ("corsproxy", f"https://corsproxy.io/?{quote(target_api, safe='')}"),
    ]:
        try:
            r = session.get(p_url, headers={"User-Agent": HEADERS["User-Agent"]}, timeout=14)
            if r.status_code == 200:
                raw_json = r.json().get("contents", "") if name == "allorigins" else r.text
                if isinstance(raw_json, str) and raw_json.strip():
                    raw_json = json.loads(raw_json)
                res = parse_toe_json(raw_json)
                if res:
                    return res, name
            errors.append(f"{name}:{r.status_code}")
        except Exception as e:
            errors.append(f"{name}:{type(e).__name__}")

    return [], ", ".join(errors[:4]) or "unavailable"


def get_site_url() -> str:
    return "https://365mi.github.io/svitlo/test.html"


def _send_to_bot(token: str, chat_id: str, text: str, site_url: str, include_browser_btn: bool = True):
    if not token or not chat_id:
        return
    api_url = f"https://api.telegram.org/bot{token}/sendMessage"
    kb = [[{"text": "📊 Відкрити УЗ / ТОЕ", "web_app": {"url": site_url}}]]
    if include_browser_btn:
        kb.append([{"text": "🌐 Відкрити у браузері", "url": site_url}])

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


def format_ranges_dots(ranges_list: list[str]) -> str:
    if not ranges_list:
        return "🟢 Відключень не заплановано"
    return "\n".join(f"🔴 {r}" for r in ranges_list)


def handle_bot_starts(token: str, last_update_id: int, d0: dict | None, site_url: str, now: datetime) -> int:
    if not token:
        return last_update_id
    api_url = f"https://api.telegram.org/bot{token}/getUpdates"
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
            if d0:
                r_dots = format_ranges_dots(slots_to_ranges(d0["queues"][TARGET_QUEUE]["current"]))
                reply_txt = (
                    f"📅 <b>{d0['date']}</b> • <b>Світло УЗ / ТОЕ</b>\n\n"
                    f"📋 <b>Актуальний графік УЗ (Черга {TARGET_QUEUE}):</b>\n"
                    f"<b>{r_dots}</b>\n\n"
                    f"👇 Оберіть УЗ або ТОЕ та свою чергу:"
                )
            else:
                reply_txt = "⚡ <b>Світло УЗ / ТОЕ</b>\n\n👇 Натисніть кнопку нижче, щоб відкрити графік:"
            _send_to_bot(token, chat_id, reply_txt, site_url, include_browser_btn=True)

    return max_id


def main():
    now = datetime.now(KYIV_TZ)
    prev_data = {"days": [], "toe_days": [], "last_update_id": 0}
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                prev_data = json.load(f)
        except Exception:
            prev_data = {"days": [], "toe_days": [], "last_update_id": 0}

    prev_by_date = {d["date"]: d for d in prev_data.get("days", [])}
    last_update_id = int(prev_data.get("last_update_id", 0) or 0)

    ua_pool = get_ua_proxies()
    raw_content, status_info = fetch_content()
    parsed = parse_ternopil_html(raw_content) if raw_content else []
    toe_parsed, toe_status = fetch_toe_all(ua_pool)

    days_map = {}
    for d in prev_data.get("days", []):
        if not is_too_old(d["day"], d["month"], now):
            days_map[d["date"]] = d

    if parsed:
        for item in parsed:
            if is_too_old(item["day"], item["month"], now):
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

            days_map[d_label] = {
                "date": d_label,
                "day": item["day"],
                "month": item["month"],
                "queues": queues_out,
            }
        source_ok = True
    else:
        source_ok = False

    out_days = sorted(
        days_map.values(),
        key=lambda x: resolve_day_date(x["day"], x["month"], now),
    )

    prev_toe_by_date = {d["date"]: d for d in prev_data.get("toe_days", [])}
    toe_days_map = {}
    for d in prev_data.get("toe_days", []):
        if not is_too_old(d["day"], d["month"], now):
            toe_days_map[d["date"]] = d

    if toe_parsed:
        for item in toe_parsed:
            if is_too_old(item["day"], item["month"], now):
                continue
            d_label = item["date"]
            old_td = prev_toe_by_date.get(d_label)
            old_t_queues = old_td.get("queues", {}) if old_td else {}
            t_queues_out = {}
            for q in TOE_QUEUES:
                cur_s = item["slots_map"][q]
                base_s = old_t_queues.get(q, {}).get("baseline")
                if not base_s or len(base_s) != 48:
                    base_s = list(cur_s)
                t_queues_out[q] = {"baseline": base_s, "current": cur_s}

            toe_days_map[d_label] = {
                "date": d_label,
                "day": item["day"],
                "month": item["month"],
                "queues": t_queues_out,
            }
        toe_ok = True
    else:
        toe_ok = False

    out_toe_days = sorted(
        toe_days_map.values(),
        key=lambda x: resolve_day_date(x["day"], x["month"], now),
    )

    today_label = f"{now.day} {MONTHS_UA[now.month - 1]}"
    today_obj = next((d for d in out_days if d["date"] == today_label), None)

    token_test = os.environ.get("BOT_TOKEN", "").strip()
    chat_id = os.environ.get("CHAT_ID", "").strip()
    site_url = get_site_url()

    if os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch":
        test_msg = (
            f"🧪 <b>Тест УЗ / ТОЕ виконано</b>\n"
            f"• УЗ: {'✅ ' + status_info if source_ok else '⚠️ кеш (' + status_info + ')'}\n"
            f"• ТОЕ: {'✅ ' + toe_status if toe_ok else '⚠️ кеш (' + toe_status + ')'}"
        )
        _send_to_bot(token_test, chat_id, test_msg, site_url)

    d_for_start = today_obj or (out_days[-1] if out_days else None)
    new_last_update_id = handle_bot_starts(token_test, last_update_id, d_for_start, site_url, now)

    result = {
        "updated_at": now.isoformat(timespec="seconds"),
        "updated_str": now.strftime("%d.%m %H:%M"),
        "source_ok": source_ok,
        "fetch_info": status_info,
        "toe_ok": toe_ok,
        "toe_info": toe_status,
        "last_update_id": new_last_update_id,
        "days": out_days,
        "toe_days": out_toe_days,
    }

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
