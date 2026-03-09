import os
import random
import datetime as dt
import requests
from dateutil import tz

# ================== 基础配置（通过 GitHub Secrets / env 注入）==================
TIMEZONE = os.getenv("TIMEZONE", "Asia/Singapore").strip()

# NewsAPI
NEWS_API_KEY = os.getenv("NEWS_API_KEY", "").strip()
NEWS_LANG = os.getenv("NEWS_LANG", "en").strip()
NEWS_SOURCES_FINANCE = os.getenv("NEWS_SOURCES_FINANCE", "").strip()  # 逗号分隔，可空
NEWS_SOURCES_TECH = os.getenv("NEWS_SOURCES_TECH", "").strip()        # 逗号分隔，可空

# Twelve Data（金价）
TWELVE_DATA_API_KEY = os.getenv("TWELVE_DATA_API_KEY", "").strip()
GOLD_SYMBOL = os.getenv("GOLD_SYMBOL", "XAU/USD").strip()

# “缺 key 就隐藏模块”的开关（默认开启隐藏）
# - HIDE_MODULE_ON_MISSING_KEY=1：缺 key 就不显示该模块（默认）
# - HIDE_MODULE_ON_MISSING_KEY=0：缺 key 显示“获取失败/未配置”提示
HIDE_MODULE_ON_MISSING_KEY = os.getenv("HIDE_MODULE_ON_MISSING_KEY", "1").strip() == "1"

# IELTS 线上词库 + 释义/例句开关
IELTS_WORDLIST_URL = os.getenv(
    "IELTS_WORDLIST_URL",
    "https://raw.githubusercontent.com/fanhongtao/IELTS/master/IELTS%20Word%20List.txt"
).strip()
DICT_API_ENABLED = os.getenv("DICT_API_ENABLED", "1").strip() == "1"

# ================== 文案库 ==================
GREETINGS_WORKDAY = [
    "愿你今天状态在线，推进顺利。",
    "新的一天，稳稳推进，开心收工。",
    "早安☀️ 先喝水，再开工，节奏慢一点也没关系。",
    "愿你今天心情明朗，事情都朝着更好的方向走。"
]
GREETINGS_WEEKEND = [
    "周末早安☀️ 放松一点，按自己的节奏过今天。",
    "早安～ 今天适合睡到自然醒，也适合慢慢变好。",
    "周末愉快🌿 祝你有休息、有快乐、有能量。"
]

# 名人名言（英文）
QUOTES = [
    ("The future depends on what you do today.", "Mahatma Gandhi"),
    ("It always seems impossible until it’s done.", "Nelson Mandela"),
    ("Well begun is half done.", "Aristotle"),
    ("Success is the sum of small efforts repeated day in and day out.", "Robert Collier"),
    ("Simplicity is the ultimate sophistication.", "Leonardo da Vinci"),
    ("The only way to do great work is to love what you do.", "Steve Jobs"),
    ("Do what you can, with what you have, where you are.", "Theodore Roosevelt"),
]

def pick_quote() -> str:
    q, a = random.choice(QUOTES)
    return f"「{q}」—— {a}"

# ================== 天气（Open-Meteo，无需 Key）==================
def geocode_qingpu():
    """
    Open-Meteo Geocoding 对中文有时无结果，因此：
    1) 多个关键词轮询（中文/英文）
    2) 加 country_code=CN 限定
    3) 全失败就使用青浦区兜底经纬度
    """
    url = "https://geocoding-api.open-meteo.com/v1/search"
    queries = [
        "上海市青浦区",
        "青浦区",
        "Qingpu District, Shanghai",
        "Qingpu, Shanghai",
        "Qingpu District",
        "Qingpu Shanghai China",
    ]

    for q in queries:
        params = {
            "name": q,
            "count": 5,
            "language": "en",
            "format": "json",
            "country_code": "CN",
        }
        r = requests.get(url, params=params, timeout=12)
        r.raise_for_status()
        data = r.json()
        results = data.get("results") or []
        if results:
            top = results[0]
            return float(top["latitude"]), float(top["longitude"]), top.get("name", "Qingpu")

    # 兜底：青浦区大致中心点坐标
    return 31.150681, 121.124176, "青浦区(兜底坐标)"

def get_weather_qingpu():
    lat, lon, place = geocode_qingpu()
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
        "timezone": TIMEZONE,
        "forecast_days": 1,
    }
    r = requests.get(url, params=params, timeout=12)
    r.raise_for_status()
    data = r.json()

    cur = data.get("current") or {}
    daily = data.get("daily") or {}

    code = cur.get("weather_code")
    code_map = {
        0: "晴 ☀️", 1: "大致晴 🌤️", 2: "局部多云 ⛅", 3: "阴 ☁️",
        45: "雾 🌫️", 48: "雾凇 ❄️",
        51: "毛毛雨 🌧️", 53: "小毛毛雨 🌧️", 55: "强毛毛雨 🌧️",
        61: "小雨 🌧️", 63: "中雨 🌧️", 65: "大雨 🌧️",
        71: "小雪 🌨️", 73: "中雪 🌨️", 75: "大雪 🌨️",
        80: "阵雨 🌦️", 81: "强阵雨 🌦️", 82: "暴阵雨 ⛈️",
        95: "雷暴 ⛈️"
    }
    desc = code_map.get(code, f"天气码{code}" if code is not None else "未知")

    t = cur.get("temperature_2m")
    feels = cur.get("apparent_temperature")
    wind = cur.get("wind_speed_10m")

    tmax = (daily.get("temperature_2m_max") or [None])[0]
    tmin = (daily.get("temperature_2m_min") or [None])[0]
    pop = (daily.get("precipitation_probability_max") or [None])[0]

    return {
        "place": place,
        "desc": desc,
        "t": t,
        "feels": feels,
        "wind": wind,
        "tmax": tmax,
        "tmin": tmin,
        "pop": pop,
    }

# ================== 新闻（NewsAPI：everything + popularity）==================
def _news_everything(query: str, sources: str, page_size: int = 3):
    if not NEWS_API_KEY:
        raise RuntimeError("NEWS_API_KEY 未配置")

    url = "https://newsapi.org/v2/everything"
    params = {
        "q": query,
        "language": NEWS_LANG,
        "sortBy": "popularity",
        "pageSize": page_size,
        "apiKey": NEWS_API_KEY,
    }
    if sources:
        params["sources"] = sources

    r = requests.get(url, params=params, timeout=12)
    r.raise_for_status()
    data = r.json()

    titles = []
    for a in (data.get("articles") or [])[:page_size]:
        t = (a.get("title") or "").strip()
        if t:
            titles.append(t)
    return titles

def get_international_tech_top3():
    query = '(technology OR AI OR semiconductor OR chip OR cybersecurity OR software)'
    return _news_everything(query=query, sources=NEWS_SOURCES_TECH, page_size=3)

def get_international_finance_top3():
    query = '(finance OR economy OR markets OR stocks OR inflation OR "central bank")'
    return _news_everything(query=query, sources=NEWS_SOURCES_FINANCE, page_size=3)

# ================== 金价（Twelve Data）==================
def get_gold_daily_series(outputsize: int = 120):
    if not TWELVE_DATA_API_KEY:
        raise RuntimeError("TWELVE_DATA_API_KEY 未配置")

    url = "https://api.twelvedata.com/time_series"
    params = {
        "symbol": GOLD_SYMBOL,
        "interval": "1day",
        "outputsize": outputsize,
        "apikey": TWELVE_DATA_API_KEY,
        "format": "JSON",
    }
    r = requests.get(url, params=params, timeout=12)
    r.raise_for_status()
    data = r.json()

    if data.get("status") == "error":
        raise RuntimeError(data.get("message") or str(data))

    values = data.get("values") or []
    if not values:
        raise RuntimeError(f"time_series 返回异常: {data}")
    return values

def pick_close_on_or_before(values, target_date: dt.date):
    for row in values:
        d_str = (row.get("datetime") or "")[:10]
        if not d_str:
            continue
        d = dt.date.fromisoformat(d_str)
        if d <= target_date:
            return d, float(row["close"])
    raise RuntimeError(f"找不到 {target_date} 或之前的交易日数据")

# ================== 单词（IELTS + 词典释义/例句）==================
def fetch_ielts_wordlist(url: str, timeout: int = 15) -> list[str]:
    """
    兼容“单词 + 音标 + 释义”的词表；避免抓到 HTML 导致出现 README。
    """
    r = requests.get(url, timeout=timeout)
    r.raise_for_status()
    text = r.text or ""

    # 防止抓到 GitHub HTML 页面
    lower = text.lower()
    if "<html" in lower or "<!doctype html" in lower:
        raise RuntimeError("IELTS 词表抓取到 HTML 页面（请检查 IELTS_WORDLIST_URL 是否为 raw 直链）")

    ignore = {"ielts", "readme", "word", "list"}
    words = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue

        first = s.split()[0].strip()
        w = first.strip("•*#=-—_[](){}.,;:'\"!?/\\|<>`~")
        lw = w.lower()

        if not w or lw in ignore:
            continue
        if not w.isalpha():
            continue
        words.append(w)

    # 去重保序
    seen = set()
    uniq = []
    for w in words:
        lw = w.lower()
        if lw not in seen:
            seen.add(lw)
            uniq.append(w)

    if not uniq:
        raise RuntimeError("IELTS 词表解析后为空（可能 URL 不对或文件格式变化）")
    return uniq

def pick_word_of_day_from_list(words: list[str], d: dt.date) -> str:
    base = dt.date(2024, 1, 1)
    idx = (d - base).days % len(words)
    return words[idx]

def lookup_definition_free_dict(word: str, timeout: int = 12) -> dict:
    url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}"
    r = requests.get(url, timeout=timeout)
    if r.status_code != 200:
        return {}
    data = r.json()
    if not isinstance(data, list) or not data:
        return {}

    entry = data[0]
    meanings = entry.get("meanings") or []
    for m in meanings:
        pos = m.get("partOfSpeech")
        defs = m.get("definitions") or []
        if defs:
            definition = defs[0].get("definition")
            example = defs[0].get("example")
            out = {}
            if pos: out["pos"] = pos
            if definition: out["definition"] = definition
            if example: out["example"] = example
            return out
    return {}

# ================== “缺 key 就隐藏模块”的封装 ==================
def maybe_section(title: str, builder_fn, required_keys_ok: bool, show_when_missing: str = ""):
    if not required_keys_ok:
        if HIDE_MODULE_ON_MISSING_KEY:
            return ""
        return "\n".join([title, show_when_missing]).strip()

    try:
        content = builder_fn()
        if not content:
            return "" if HIDE_MODULE_ON_MISSING_KEY else "\n".join([title, "暂无内容。"])
        return "\n".join([title, content]).strip()
    except Exception as e:
        return "\n".join([title, f"获取失败：{e}"]).strip()

# ================== 生成邮件内容（顺序：单词 -> 天气 -> 金价 -> 科技 -> 财经）==================
def build_text(now_local: dt.datetime) -> str:
    date_str = now_local.strftime("%Y-%m-%d")
    weekdays_cn = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    weekday_cn = weekdays_cn[now_local.weekday()]
    is_weekend = now_local.weekday() >= 5

    base_greeting = random.choice(GREETINGS_WEEKEND if is_weekend else GREETINGS_WORKDAY)
    greeting = f"{base_greeting}\n{pick_quote()}"

    # 天气
    try:
        w = get_weather_qingpu()
        weather_block = "\n".join([
            f"当前：{w['desc']} {w['t']}°C（体感 {w['feels']}°C）",
            f"今日：{w['tmin']}°C ~ {w['tmax']}°C | 降水概率 {w['pop']}% | 风速 {w['wind']} km/h"
        ])
    except Exception as e:
        weather_block = f"天气（上海市青浦区）\n获取失败：{e}"

    # 每日 IELTS 单词（线上词库）
    word_section = ""
    try:
        words = fetch_ielts_wordlist(IELTS_WORDLIST_URL)
        word = pick_word_of_day_from_list(words, now_local.date())

        info = lookup_definition_free_dict(word) if DICT_API_ENABLED else {}

        lines = ["📚 每日单词", word]
        lines.append(f"词性：{info.get('pos', '—')}")
        lines.append(f"释义：{info.get('definition', '—（词典未返回）')}")
        lines.append(f"例句：{info.get('example', '—（该词条未提供例句）')}")
        word_section = "\n".join(lines)
    except Exception:
        word_section = ""

    # 金价（含对比/周/月涨幅）
    def build_gold_content():
        values = get_gold_daily_series(outputsize=120)

        today = now_local.date()
        d0, p0 = pick_close_on_or_before(values, today)
        d1, p1 = pick_close_on_or_before(values, d0 - dt.timedelta(days=1))
        d7, p7 = pick_close_on_or_before(values, d0 - dt.timedelta(days=7))
        d30, p30 = pick_close_on_or_before(values, d0 - dt.timedelta(days=30))

        def fmt_change(new, old):
            diff = new - old
            pct = (diff / old) * 100 if old else 0.0
            sign = "+" if diff >= 0 else ""
            return f"{sign}{diff:.2f} ({sign}{pct:.2f}%)"

        return "\n".join([
            f"最新收盘（{d0}）：{p0:.2f} 美元/盎司",
            f"较前一交易日（{d1}）：{fmt_change(p0, p1)}",
            f"近 7 天（对比 {d7}）：{fmt_change(p0, p7)}",
            f"近 30 天（对比 {d30}）：{fmt_change(p0, p30)}",
        ])

    gold_section = maybe_section(
        title="💰 金价播报",
        builder_fn=build_gold_content,
        required_keys_ok=bool(TWELVE_DATA_API_KEY),
        show_when_missing="未配置金价数据源（TWELVE_DATA_API_KEY）。"
    )

    # 新闻（科技在财经上面；周末默认隐藏新闻）
    def build_tech_content():
        tech = get_international_tech_top3()
        return "\n".join([f"{i+1}. {t}" for i, t in enumerate(tech[:3])])

    def build_fin_content():
        fin = get_international_finance_top3()
        return "\n".join([f"{i+1}. {t}" for i, t in enumerate(fin[:3])])

    news_enabled = (not is_weekend) and bool(NEWS_API_KEY)

    tech_section = maybe_section(
        title="国际科技热度 Top3",
        builder_fn=build_tech_content,
        required_keys_ok=news_enabled,
        show_when_missing="未配置新闻数据源（NEWS_API_KEY），或当前为周末已默认隐藏新闻。"
    )
    fin_section = maybe_section(
        title="国际财经热度 Top3",
        builder_fn=build_fin_content,
        required_keys_ok=news_enabled,
        show_when_missing="未配置新闻数据源（NEWS_API_KEY），或当前为周末已默认隐藏新闻。"
    )

    # 组装：天气 -> 金价 -> 单词 -> 科技 -> 财经
    blocks = [
        greeting,
        "",
        "☀️☀️☀️☀️☀️☀️☀️☀️☀️☀️☀️",
        "👑👑👑🌸公主早安🌸👑👑👑",
        "☀️☀️☀️☀️☀️☀️☀️☀️☀️☀️☀️",
        f"{date_str} {weekday_cn}",
        weather_block,
    ]

    # 金价先放
    if gold_section.strip():
        blocks += ["", gold_section]

    # 单词放在金价后
    if word_section.strip():
        blocks += ["", word_section]

    # 新闻（科技在财经上面）
    for section in [tech_section, fin_section]:
        if section.strip():
            blocks += ["", section]

    return "\n".join(blocks).strip() + "\n"

def main():
    local_tz = tz.gettz(TIMEZONE)
    now_local = dt.datetime.now(tz=local_tz)

    subject = f"早安播报 {now_local.strftime('%Y-%m-%d')}"
    body = build_text(now_local)

    with open("email_subject.txt", "w", encoding="utf-8") as f:
        f.write(subject)
    with open("email_body.txt", "w", encoding="utf-8") as f:
        f.write(body)

    print("Generated email_subject.txt & email_body.txt")

if __name__ == "__main__":
    main()