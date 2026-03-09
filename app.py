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
            "language": "en",        # 英文索引通常更稳；返回字段不影响后续
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
    # 来源参考：Qingpu, Shanghai, China lat/long ≈ 31.150681, 121.124176
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
        0: "晴", 1: "大致晴", 2: "局部多云", 3: "阴",
        45: "雾", 48: "雾凇",
        51: "毛毛雨", 53: "小毛毛雨", 55: "强毛毛雨",
        61: "小雨", 63: "中雨", 65: "大雨",
        71: "小雪", 73: "中雪", 75: "大雪",
        80: "阵雨", 81: "强阵雨", 82: "暴阵雨",
        95: "雷暴"
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
def get_gold_price():
    if not TWELVE_DATA_API_KEY:
        raise RuntimeError("TWELVE_DATA_API_KEY 未配置")
    url = "https://api.twelvedata.com/price"
    params = {"symbol": GOLD_SYMBOL, "apikey": TWELVE_DATA_API_KEY}
    r = requests.get(url, params=params, timeout=12)
    r.raise_for_status()
    data = r.json()
    price = data.get("price")
    if not price:
        raise RuntimeError(f"金价返回异常: {data}")
    return float(price)
def get_gold_daily_series(outputsize: int = 120):
    """
    Twelve Data time_series：拉最近一段 1day 日线（values 按时间倒序）
    """
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

    values = data.get("values") or []
    if not values:
        raise RuntimeError(f"time_series 返回异常: {data}")

    # values 形如：[{ "datetime": "2026-03-08", "close": "2918.35", ... }, ...]
    return values

def pick_close_on_or_before(values, target_date: dt.date):
    """
    从 time_series values（倒序）中，取“<= target_date”的最近一个交易日 close
    """
    for row in values:
        # datetime 可能是 "YYYY-MM-DD" 或 "YYYY-MM-DD HH:MM:SS"
        d_str = (row.get("datetime") or "")[:10]
        if not d_str:
            continue
        d = dt.date.fromisoformat(d_str)
        if d <= target_date:
            return d, float(row["close"])
    raise RuntimeError(f"找不到 {target_date} 或之前的交易日数据")

# ================== 单词（IELTS）==================
def fetch_ielts_wordlist(url: str, timeout: int = 15) -> list[str]:
    """
    从线上 IELTS 词表拉取单词列表（每次 run 拉一次，足够用）
    """
    r = requests.get(url, timeout=timeout)
    r.raise_for_status()
    text = r.text

    words = []
    for line in text.splitlines():
        w = line.strip()
        if not w:
            continue
        # 过滤明显不是单词的行（有些词表可能带序号/注释）
        if any(ch.isdigit() for ch in w):
            continue
        # 只保留单个词（你也可以放开短语，这里先保守）
        if " " in w:
            continue
        words.append(w)

    # 去重、保持顺序
    seen = set()
    uniq = []
    for w in words:
        lw = w.lower()
        if lw not in seen:
            seen.add(lw)
            uniq.append(w)
    if not uniq:
        raise RuntimeError("IELTS 词表为空/解析失败")
    return uniq

def pick_word_of_day_from_list(words: list[str], d: dt.date) -> str:
    """
    用日期做确定性选择：同一天永远选同一个词；无需保存状态
    """
    base = dt.date(2024, 1, 1)
    idx = (d - base).days % len(words)
    return words[idx]

def lookup_definition_free_dict(word: str, timeout: int = 12) -> dict:
    """
    dictionaryapi.dev：返回英文释义/词性/例句（尽力取第一个）
    """
    url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}"
    r = requests.get(url, timeout=timeout)
    if r.status_code != 200:
        return {}  # 有些词可能查不到
    data = r.json()
    if not isinstance(data, list) or not data:
        return {}

    # 结构大致：[ { meanings: [ { partOfSpeech, definitions: [ { definition, example } ] } ] } ]
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
    """
    返回一个可选的模块文本块（含标题）。缺 key 时按开关决定隐藏/显示提示。
    - required_keys_ok=False：表示该模块依赖的 key 不齐
    """
    if not required_keys_ok:
        if HIDE_MODULE_ON_MISSING_KEY:
            return ""  # 隐藏模块
        # 显示一个友好提示
        return "\n".join([title, show_when_missing]).strip()

    try:
        content = builder_fn()
        if not content:
            return "" if HIDE_MODULE_ON_MISSING_KEY else "\n".join([title, "暂无内容。"])
        return "\n".join([title, content]).strip()
    except Exception as e:
        # 接口失败：默认也显示（因为 key 是齐的，只是暂时取数失败）
        return "\n".join([title, f"获取失败：{e}"]).strip()

# ================== 生成邮件内容（工作日/周末模板 + 排序要求）==================
def build_text(now_local: dt.datetime) -> str:
    date_str = now_local.strftime("%Y-%m-%d")
    weekdays_cn = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    weekday_cn = weekdays_cn[now_local.weekday()]
    is_weekend = now_local.weekday() >= 5

    greeting = random.choice(GREETINGS_WEEKEND if is_weekend else GREETINGS_WORKDAY)

    # 天气模块（不需要 key，失败则显示失败信息）
    try:
        w = get_weather_qingpu()
        weather_block = "\n".join([
            "天气（上海市青浦区）",
            f"当前：{w['desc']} {w['t']}°C（体感 {w['feels']}°C）",
            f"今日：{w['tmin']}°C ~ {w['tmax']}°C | 降水概率 {w['pop']}% | 风速 {w['wind']} km/h"
        ])
    except Exception as e:
        weather_block = f"天气（上海市青浦区）\n获取失败：{e}"
    
    # 每日 IELTS 单词（线上词库）
    word_section = ""
    try:
        words = fetch_ielts_wordlist(IELTS_WORDLIST_URL)
        w = pick_word_of_day_from_list(words, now_local.date())

        # 词典释义（可开关）
        if DICT_API_ENABLED:
            info = lookup_definition_free_dict(w)
        else:
            info = {}

        lines = ["每日英文单词（IELTS）", w]
        if info.get("pos"):
            lines.append(f"词性：{info['pos']}")
        if info.get("definition"):
            lines.append(f"释义：{info['definition']}")
        if info.get("example"):
            lines.append(f"例句：{info['example']}")
        word_section = "\n".join(lines)
    except Exception:
        # 缺 key 隐藏模块逻辑：这里不需要 key，但网络/解析失败时直接隐藏即可
        word_section = ""

    # 金价模块（放在新闻上面）
    def build_gold_content():
        values = get_gold_daily_series(outputsize=120)

        # “今日”用最近一个交易日收盘价
        today = dt.datetime.now(tz=tz.gettz(TIMEZONE)).date()
        d0, p0 = pick_close_on_or_before(values, today)

        # 前一交易日：用 d0-1 天去找“<=目标日”的最近交易日即可
        d1, p1 = pick_close_on_or_before(values, d0 - dt.timedelta(days=1))

        # 近 7 天 / 近 30 天：同样找“<=目标日”的最近交易日
        d7, p7 = pick_close_on_or_before(values, d0 - dt.timedelta(days=7))
        d30, p30 = pick_close_on_or_before(values, d0 - dt.timedelta(days=30))

        def fmt_change(new, old):
            diff = new - old
            pct = (diff / old) * 100 if old else 0.0
            sign = "+" if diff >= 0 else ""
            return f"{sign}{diff:.2f} ({sign}{pct:.2f}%)"

        lines = [
            f"最新收盘（{d0}）：{p0:.2f} 美元/盎司",
            f"较前一交易日（{d1}）：{fmt_change(p0, p1)}",
            f"近 7 天（对比 {d7}）：{fmt_change(p0, p7)}",
            f"近 30 天（对比 {d30}）：{fmt_change(p0, p30)}",
        ]
        return "\n".join(lines)

    gold_section = maybe_section(
        title="金价播报",
        builder_fn=build_gold_content,
        required_keys_ok=bool(TWELVE_DATA_API_KEY),
        show_when_missing="未配置金价数据源（TWELVE_DATA_API_KEY）。"
    )

    # 新闻模块（科技在财经上面；周末默认隐藏新闻）
    def build_tech_content():
        tech = get_international_tech_top3()
        return "\n".join([f"{i+1}. {t}" for i, t in enumerate(tech[:3])])

    def build_fin_content():
        fin = get_international_finance_top3()
        return "\n".join([f"{i+1}. {t}" for i, t in enumerate(fin[:3])])

    # 周末：默认不放新闻（你想周末也放，把 is_weekend 判断去掉即可）
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

    # 组装：天气 -> 金价 -> 科技 -> 财经
    blocks = [
        "早安☀️",
        f"{date_str} {weekday_cn}",
        "",
        greeting,
        "",
        weather_block,
    ]

    # 只添加非空模块
    for section in [gold_section,word_section, tech_section, fin_section]:
        if section.strip():
            blocks += ["", section]

    return "\n".join(blocks).strip() + "\n"

def main():
    local_tz = tz.gettz(TIMEZONE)
    now_local = dt.datetime.now(tz=local_tz)

    subject = f"早安播报 {now_local.strftime('%Y-%m-%d')}"
    body = build_text(now_local)

    # 写入文件供 GitHub Action 读
    with open("email_subject.txt", "w", encoding="utf-8") as f:
        f.write(subject)
    with open("email_body.txt", "w", encoding="utf-8") as f:
        f.write(body)

    print("Generated email_subject.txt & email_body.txt")

if __name__ == "__main__":
    main()