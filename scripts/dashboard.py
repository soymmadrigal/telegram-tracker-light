import argparse
import base64
import csv
import html
import json
import math
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, unquote

try:
    from nltk.corpus import stopwords as nltk_stopwords
except Exception:
    nltk_stopwords = None


REQUIRED_COLS = {"date", "message", "views", "msg_link"}

URL_RE = re.compile(r"https?://[^\s\])>\"']+", re.IGNORECASE)
MARKDOWN_RE = re.compile(r"[*_`#\[\]()]+")

DEFAULT_FOCUS_TERMS_PATTERN = (
    r"\b(imputad[oa]s?|imputaci[oó]n|imputar|investigad[oa]s?|investigar|"
    r"citado como investigado|citad[oa] a declarar|procesad[oa]|encausad[oa]|"
    r"querella|blanqueo|malversaci[oó]n|tr[aá]fico de influencias|"
    r"organizaci[oó]n criminal)\b"
)

IMPUTACION_TERMS_RE = re.compile(
    r"\b(imputad[oa]s?|imputaci[oó]n|imputar|investigad[oa]s?|investigar|"
    r"citado como investigado|citad[oa] a declarar|procesad[oa]|encausad[oa]|"
    r"querella|blanqueo|malversaci[oó]n|tr[aá]fico de influencias|"
    r"organizaci[oó]n criminal)\b",
    re.IGNORECASE,
)

TOPIC_PATTERNS = {
    "Plus Ultra": re.compile(r"\bplus ultra|sepi|rescate\b", re.IGNORECASE),
    "Venezuela / Maduro / Delcy": re.compile(r"\bvenezuela|maduro|delcy|chavismo|caracas|pdvsa\b", re.IGNORECASE),
    "Aldama / Koldo / Abalos": re.compile(r"\baldama|koldo|[aá]balos|abalos|uco|udef\b", re.IGNORECASE),
    "Panama / Delgado": re.compile(r"\bpanam[aá]|dolores delgado|delgado\b", re.IGNORECASE),
    "ETA / pactos": re.compile(r"\beta|bildu|presos|terrorismo\b", re.IGNORECASE),
    "Marruecos / exterior": re.compile(r"\bmarruecos|sahara|ceuta|melilla|exteriores\b", re.IGNORECASE),
}

TOPIC_STOPWORDS = {
    "para", "pero", "porque", "como", "cuando", "donde", "desde", "hasta", "entre",
    "sobre", "contra", "ante", "bajo", "tras", "durante", "mediante", "segun", "sin",
    "este", "esta", "estos", "estas", "ese", "esa", "esos", "esas", "aquel", "aquella",
    "todo", "toda", "todos", "todas", "otro", "otra", "otros", "otras", "algo", "nada",
    "mucho", "mucha", "muchos", "muchas", "poco", "poca", "cada", "mismo", "misma",
    "tambien", "aunque", "solo", "puede", "pueden", "tiene", "tienen", "hacer", "hace",
    "hecho", "ser", "estar", "haber", "hay", "son", "fue", "han", "una", "uno", "unos",
    "unas", "del", "las", "los", "que", "con", "por", "mas", "muy", "sus", "esto",
    "eso", "aqui", "alli", "ahora", "bien", "mal", "dice", "dijo", "ver", "vamos",
    "gracias", "hola", "buenos", "buenas", "canal", "grupo", "mensaje", "mensajes",
    "telegram", "video", "foto", "audio", "enlace", "http", "https", "www", "com", "org",
    "haz", "clic", "reporte", "reportar", "enviado", "bot", "privado", "privada",
    "the", "and", "that", "this", "with", "from", "have", "has", "had", "been",
    "were", "was", "are", "for", "you", "your", "they", "their", "them", "his",
    "her", "its", "our", "who", "what", "when", "where", "which", "will", "would",
    "could", "should", "can", "cannot", "than", "then", "there", "here", "more",
    "most", "some", "any", "all", "not", "but", "about", "into", "over", "after",
    "before", "being", "because", "through", "during", "while", "just", "only",
    "also", "very", "much", "many", "make", "made", "get", "got", "now", "new",
    "one", "two", "year", "years", "old", "subscribe", "please", "click", "share",
    "look", "looks", "like", "admin", "post", "posts", "tiktok", "retards_tiktok",
    "retardsoftiktok",
}
TOPIC_TOKEN_RE = re.compile(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ][A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9_]{2,}")
MAX_DETECTED_TOPICS = 8

CHARTS = [
    ("KPIs principales", "00_kpi_cards.png"),
    ("Top forwards recibidos", "06_top10_forwards_recibidos.png"),
    ("Top forwards realizados", "07_top10_forwards_realizados.png"),
    ("Timeline forwards", "timeline_forwards_send.png"),
    ("Timeline respuestas", "timeline_replies_send.png"),
    ("Top dominios", "top_15_domains.png"),
    ("Timeline dominios", "top_10_domains_timeline.png"),
    ("Nube de palabras", "wordcloud_messages.png"),
]

EXPLORER_EMBED_LIMIT = 5000


def sniff_delimiter(path: Path) -> str:
    sample = path.read_text(encoding="utf-8-sig", errors="replace")[:8192]
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;").delimiter
    except csv.Error:
        first = sample.splitlines()[0] if sample else ""
        return ";" if first.count(";") > first.count(",") else ","


def load_rows(path: Path):
    delimiter = sniff_delimiter(path)
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh, delimiter=delimiter)
        if not reader.fieldnames:
            raise ValueError("CSV vacio o sin cabecera.")
        missing = REQUIRED_COLS - set(reader.fieldnames)
        if missing:
            raise ValueError(f"Faltan columnas requeridas: {sorted(missing)}")
        return [normalise_row(row) for row in reader]


def normalise_row(row):
    row = {key: repair_text(value) for key, value in row.items()}
    msg = row.get("message") or ""
    links = extract_links(row.get("links") or row.get("url") or "", msg)
    domains = extract_domains(row.get("domains") or row.get("domain") or "", links)
    dt = parse_date(row.get("date") or "")
    views = to_int(row.get("views"))
    forwards = to_int(row.get("number_forwards"))
    replies = to_int(row.get("number_replies"))
    title = make_title(msg, links)
    return {
        "username": (row.get("username") or row.get("channel_name") or "").strip() or "(sin_canal)",
        "date": row.get("date") or "",
        "dt": dt,
        "month": dt.strftime("%Y-%m") if dt else "",
        "message": msg,
        "title": title,
        "views": views,
        "forwards": forwards,
        "replies": replies,
        "msg_link": row.get("msg_link") or "",
        "links": links,
        "domains": domains,
        "topic_hits": [],
        "is_focus": False,
    }


def repair_text(value):
    if not isinstance(value, str):
        return value
    if not any(mark in value for mark in ("Ã", "Â", "ðŸ", "â€", "â€œ", "â€")):
        return value

    best = value
    best_score = mojibake_score(value)
    for encoding in ("cp1252", "latin1"):
        try:
            fixed = value.encode(encoding).decode("utf-8")
        except UnicodeError:
            continue
        score = mojibake_score(fixed)
        if score < best_score:
            best = fixed
            best_score = score
    return best


def mojibake_score(value):
    markers = ("Ã", "Â", "ðŸ", "â€", "â€œ", "â€", "�")
    return sum(value.count(mark) for mark in markers)


def parse_date(value):
    value = value.strip()
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed
    except ValueError:
        return None


def to_int(value):
    try:
        if value is None or value == "":
            return 0
        return int(float(str(value).replace(".", "").replace(",", ".")))
    except ValueError:
        return 0


def extract_links(links_field, message):
    found = []
    for part in re.split(r",\s*", links_field.strip()):
        if part.startswith("http"):
            found.append(clean_url(part))
    found.extend(clean_url(x) for x in URL_RE.findall(message or ""))
    return dedupe([x for x in found if x.startswith("http")])


def clean_url(url):
    return url.strip().rstrip(".,;:*)]")


def extract_domains(domains_field, links):
    domains = []
    for part in re.split(r",\s*", domains_field.strip()):
        part = part.strip().lower()
        if part:
            domains.append(part[4:] if part.startswith("www.") else part)
    for link in links:
        host = urlparse(link).netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        if host:
            domains.append(host)
    return dedupe(domains)


def dedupe(items):
    seen = set()
    out = []
    for item in items:
        if item and item not in seen:
            out.append(item)
            seen.add(item)
    return out


def make_title(message, links):
    text = URL_RE.sub(" ", message or "")
    text = MARKDOWN_RE.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip(" -:\n\t")
    if text:
        return truncate(text, 180)
    if links:
        return title_from_url(links[0])
    return "(sin texto)"


def title_from_url(url):
    parsed = urlparse(url)
    slug = unquote(parsed.path.strip("/").split("/")[-1])
    slug = re.sub(r"[-_]+", " ", slug)
    return truncate(slug.strip() or parsed.netloc, 180)


def truncate(text, max_len):
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rstrip() + "..."


def message_score(row, extra=0):
    return row["views"] + row["forwards"] * 250 + row["replies"] * 100 + extra


def dedupe_message_rows(rows):
    unique = []
    seen = set()
    for row in rows:
        fingerprint = normalise_topic_text(URL_RE.sub(" ", row["message"]))
        fingerprint = re.sub(r"\s+", " ", fingerprint).strip()
        key = ("text", fingerprint) if len(fingerprint) >= 30 else ("link", row["msg_link"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)
    return unique


def build_subject_regex(subject, aliases):
    terms = [subject] + list(aliases or [])
    terms = [t.strip() for t in terms if t and t.strip()]
    if not terms:
        return None
    pattern = "|".join(re.escape(t) for t in sorted(set(terms), key=len, reverse=True))
    return re.compile(pattern, re.IGNORECASE)


def build_focus_regex(pattern):
    if not pattern:
        return None
    return re.compile(pattern, re.IGNORECASE)


def build_focus_terms_regex(value):
    terms = [term.strip() for term in (value or "").split(",") if term.strip()]
    if not terms:
        return None
    pattern = "|".join(re.escape(term) for term in sorted(set(terms), key=len, reverse=True))
    return re.compile(pattern, re.IGNORECASE)


def normalise_topic_text(value):
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(char for char in value if not unicodedata.combining(char))
    return value.lower()


def load_multilingual_stopwords():
    words = set(TOPIC_STOPWORDS)
    if nltk_stopwords is None:
        return words
    for language in ("spanish", "english", "french", "german", "italian", "portuguese", "dutch"):
        try:
            words.update(normalise_topic_text(word) for word in nltk_stopwords.words(language))
        except LookupError:
            break
    return words


MULTILINGUAL_STOPWORDS = load_multilingual_stopwords()


def topic_tokens(message):
    tokens = []
    for token in TOPIC_TOKEN_RE.findall(normalise_topic_text(URL_RE.sub(" ", message or ""))):
        if token not in MULTILINGUAL_STOPWORDS and not token.isdigit():
            tokens.append(token)
    return tokens


def detect_dataset_topics(rows):
    if not rows:
        return []
    sample_limit = 100000
    step = max(1, math.ceil(len(rows) / sample_limit))
    phrase_counts = Counter()
    sampled = rows[::step]
    tokenised_messages = [topic_tokens(row["message"]) for row in sampled]
    message_counts = Counter(" ".join(tokens) for tokens in tokenised_messages if tokens)

    for tokens in tokenised_messages:
        fingerprint = " ".join(tokens)
        if not tokens or message_counts[fingerprint] > 5:
            continue
        seen = set()
        for size in (3, 2):
            for index in range(len(tokens) - size + 1):
                phrase = tuple(tokens[index:index + size])
                if len(set(phrase)) > 1:
                    seen.add(phrase)
        phrase_counts.update(seen)

    minimum = max(3, len(sampled) // 2000)
    candidates = [
        (phrase, count)
        for phrase, count in phrase_counts.most_common(200)
        if count >= minimum
    ]
    selected = []
    used_tokens = set()
    for phrase, _count in candidates:
        phrase_tokens = set(phrase)
        if len(phrase_tokens & used_tokens) >= max(1, len(phrase_tokens) - 1):
            continue
        selected.append(" ".join(phrase))
        used_tokens.update(phrase_tokens)
        if len(selected) >= MAX_DETECTED_TOPICS:
            break
    return selected


def analyse(rows, subject_re, focus_re, focus_label):
    detected_topics = detect_dataset_topics(rows)
    for row in rows:
        msg = row["message"]
        normalised_message = " ".join(topic_tokens(msg))
        row["topic_hits"] = [
            topic.title()
            for topic in detected_topics
            if topic in normalised_message
        ]
        row["is_focus"] = is_focus_message(msg, subject_re, focus_re)

    dated = [r for r in rows if r["dt"]]
    total_views = sum(r["views"] for r in rows)
    channel_counts = Counter(r["username"] for r in rows)
    channel_views = Counter()
    domain_counts = Counter()
    month_counts = Counter(r["month"] for r in dated)
    topic_counts = Counter()

    for r in rows:
        channel_views[r["username"]] += r["views"]
        for d in r["domains"]:
            domain_counts[d] += 1
        for t in r["topic_hits"]:
            topic_counts[t] += 1

    imputacion = [r for r in rows if r["is_focus"]]
    high_impact = dedupe_message_rows(
        sorted(rows, key=lambda r: message_score(r), reverse=True)
    )[:30]
    imputacion_top = dedupe_message_rows(
        sorted(imputacion, key=lambda r: message_score(r, 50000), reverse=True)
    )[:40]
    linked = [r for r in rows if r["links"]]
    linked_top = sorted(linked, key=lambda r: message_score(r), reverse=True)[:40]

    domain_examples = defaultdict(list)
    for r in sorted(linked, key=lambda x: message_score(x), reverse=True):
        for d in r["domains"]:
            if len(domain_examples[d]) < 4:
                domain_examples[d].append(r)

    return {
        "total": len(rows),
        "channels": len(channel_counts),
        "domains": len(domain_counts),
        "total_views": total_views,
        "date_min": min((r["dt"] for r in dated), default=None),
        "date_max": max((r["dt"] for r in dated), default=None),
        "channel_counts": channel_counts,
        "channel_views": channel_views,
        "domain_counts": domain_counts,
        "month_counts": month_counts,
        "topic_counts": topic_counts,
        "imputacion": imputacion,
        "imputacion_top": imputacion_top,
        "high_impact": high_impact,
        "linked_top": linked_top,
        "domain_examples": domain_examples,
    }


def is_focus_message(message, subject_re, focus_re):
    if not message:
        return False
    if subject_re and not subject_re.search(message):
        return False
    if focus_re and focus_re.search(message):
        return True
    return bool(
        re.search(r"\b(audiencia nacional|juez|juzgado|udef|fiscal[ií]a)\b", message, re.IGNORECASE)
        and re.search(r"\b(cita|citado|declara|declarar|causa|auto|registro|registra)\b", message, re.IGNORECASE)
    )


def fmt_int(n):
    return f"{int(n):,}".replace(",", ".")


def pct(part, total):
    if not total:
        return "0%"
    return f"{part * 100 / total:.1f}%".replace(".", ",")


def h(text):
    return html.escape(str(text), quote=True)


def link(url, label):
    if not url:
        return ""
    return f'<a href="{h(url)}" target="_blank" rel="noreferrer">{h(label)}</a>'


def row_card(row, label=None):
    domains = ", ".join(row["domains"][:3])
    links = " ".join(link(u, f"enlace {i + 1}") for i, u in enumerate(row["links"][:3]))
    telegram = link(row["msg_link"], "Telegram") if row["msg_link"] else ""
    tag = f'<span class="tag">{h(label)}</span>' if label else ""
    topics = " ".join(f'<span class="pill">{h(t)}</span>' for t in row["topic_hits"][:3])
    return f"""
    <article class="message-card" data-search="{h((row['title'] + ' ' + row['username'] + ' ' + domains).lower())}">
      <div class="message-meta">
        {tag}<span>{h(row['date'][:19])}</span><span>@{h(row['username'])}</span>
        <span>{fmt_int(row['views'])} vistas</span><span>{fmt_int(row['forwards'])} reenvios</span>
      </div>
      <h4>{h(row['title'])}</h4>
      <p>{h(truncate(row['message'], 420))}</p>
      <div class="message-links">{telegram} {links}</div>
      <div class="message-topics">{topics}</div>
    </article>
    """


def table_rows(counter, limit=10):
    out = []
    for name, count in counter.most_common(limit):
        out.append(f"<tr><td>{h(name)}</td><td>{fmt_int(count)}</td></tr>")
    return "\n".join(out)


def domain_cards(stats, limit=12):
    cards = []
    for domain, count in stats["domain_counts"].most_common(limit):
        examples = stats["domain_examples"].get(domain, [])
        items = []
        for ex in examples[:3]:
            href = ex["links"][0] if ex["links"] else ex["msg_link"]
            items.append(f"<li>{link(href, ex['title'])}<span>{h(ex['username'])} · {h(ex['date'][:10])}</span></li>")
        cards.append(f"""
        <article class="domain-card">
          <div class="domain-head"><strong>{h(domain)}</strong><span>{fmt_int(count)}</span></div>
          <ul>{''.join(items)}</ul>
        </article>
        """)
    return "\n".join(cards)


def topic_bars(stats):
    if not stats["topic_counts"]:
        return '<p class="small">No hay suficiente repeticion textual para extraer temas fiables.</p>'
    max_count = max(stats["topic_counts"].values() or [1])
    bars = []
    for topic, count in stats["topic_counts"].most_common():
        width = max(4, math.ceil(count * 100 / max_count))
        bars.append(f"""
        <div class="bar-row">
          <div class="bar-label">{h(topic)}<span>{fmt_int(count)}</span></div>
          <div class="bar-track"><div style="width:{width}%"></div></div>
        </div>
        """)
    return "\n".join(bars)


def chart_gallery(dataset_dir: Path):
    cards = []
    for title, filename in CHARTS:
        chart_path = dataset_dir / "images" / filename
        src = f"images/{filename}"
        if not chart_path.exists():
            chart_path = dataset_dir / filename
            src = filename
        if chart_path.exists():
            cards.append(f"""
            <figure class="chart-card">
              <img src="{h(src)}" alt="{h(title)}">
              <figcaption>{h(title)}</figcaption>
            </figure>
            """)
    return "\n".join(cards)


def image_data_uri(path: Path):
    mime = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }.get(path.suffix.lower(), "application/octet-stream")
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{data}"


def file_data_uri(path: Path, mime: str):
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{data}"


def render_dashboard(dataset_name: str, dataset_dir: Path, csv_path: Path, rows, stats, subject_display, focus_label):
    date_min = stats["date_min"].strftime("%Y-%m-%d") if stats["date_min"] else "n/d"
    date_max = stats["date_max"].strftime("%Y-%m-%d") if stats["date_max"] else "n/d"
    peak_month, peak_count = stats["month_counts"].most_common(1)[0] if stats["month_counts"] else ("n/d", 0)
    top_channel, top_channel_count = stats["channel_counts"].most_common(1)[0] if stats["channel_counts"] else ("n/d", 0)
    top_domain, top_domain_count = stats["domain_counts"].most_common(1)[0] if stats["domain_counts"] else ("n/d", 0)
    imputacion_count = len(stats["imputacion"])

    csv_size = csv_path.stat().st_size

    explorer_rows = sorted(rows, key=lambda r: r["dt"] or datetime.min, reverse=True)
    explorer_total = len(explorer_rows)
    explorer_embedded = explorer_rows[:EXPLORER_EMBED_LIMIT]
    explorer_json = json.dumps(
        [
            {
                "date": r["date"][:19],
                "channel": r["username"],
                "views": r["views"],
                "title": r["title"],
                "topics": r["topic_hits"],
                "telegram": r["msg_link"],
                "links": r["links"][:2],
            }
            for r in explorer_embedded
        ],
        ensure_ascii=False,
    )

    html_doc = f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Dashboard Telegram - {h(dataset_name)}</title>
  <style>
    :root {{
      --bg: #f5f7fa;
      --panel: #ffffff;
      --text: #20242a;
      --muted: #606a78;
      --line: #d8dee8;
      --accent: #0f766e;
      --accent-2: #b45309;
      --danger: #b42318;
      --blue: #255a8f;
      --shadow: 0 14px 30px rgba(24, 38, 57, .08);
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: var(--bg); color: var(--text); font-family: "Segoe UI", Arial, sans-serif; }}
    a {{ color: var(--blue); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    .shell {{ max-width: 1500px; margin: 0 auto; padding: 28px; }}
    header {{ display: grid; grid-template-columns: 1.4fr .9fr; gap: 20px; align-items: end; margin-bottom: 22px; }}
    h1 {{ margin: 0 0 8px; font-size: clamp(30px, 4vw, 56px); line-height: 1; letter-spacing: 0; }}
    h2 {{ margin: 0 0 14px; font-size: 24px; letter-spacing: 0; }}
    h3 {{ margin: 0 0 10px; font-size: 19px; letter-spacing: 0; }}
    h4 {{ margin: 8px 0; font-size: 17px; letter-spacing: 0; }}
    p {{ line-height: 1.52; }}
    .subtitle {{ color: var(--muted); max-width: 880px; font-size: 16px; }}
    .notice {{ background: #fff8e6; border: 1px solid #f1d493; color: #62420c; padding: 12px 14px; border-radius: 8px; font-size: 14px; }}
    .actions {{ display: flex; flex-wrap: wrap; gap: 10px; margin-top: 14px; }}
    .button {{ display: inline-flex; align-items: center; justify-content: center; min-height: 40px; padding: 9px 13px; border: 1px solid var(--accent); border-radius: 8px; background: var(--accent); color: #fff; font-weight: 700; }}
    .button:hover {{ background: #115e59; text-decoration: none; }}
    .button.secondary {{ background: #fff; color: var(--accent); }}
    .grid {{ display: grid; gap: 16px; }}
    .kpis {{ grid-template-columns: repeat(5, minmax(0, 1fr)); margin: 20px 0; }}
    .card, .message-card, .domain-card, .chart-card {{ background: var(--panel); border: 1px solid var(--line); border-radius: 8px; box-shadow: var(--shadow); }}
    .card {{ padding: 18px; }}
    .kpi strong {{ display: block; font-size: 30px; margin-bottom: 4px; }}
    .kpi span {{ color: var(--muted); font-size: 13px; }}
    .two {{ grid-template-columns: 1fr 1fr; }}
    .three {{ grid-template-columns: 1fr 1fr 1fr; }}
    .section {{ margin-top: 22px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
    td, th {{ padding: 9px 8px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; overflow-wrap: anywhere; }}
    th {{ color: var(--muted); font-weight: 600; }}
    .bar-row {{ margin: 12px 0; }}
    .bar-label {{ display: flex; justify-content: space-between; gap: 12px; margin-bottom: 5px; font-size: 14px; }}
    .bar-track {{ height: 10px; border-radius: 999px; background: #e8edf3; overflow: hidden; }}
    .bar-track div {{ height: 100%; border-radius: 999px; background: var(--accent); }}
    .message-list {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }}
    .message-card {{ padding: 15px; }}
    .message-card, .domain-card, .chart-card {{ min-width: 0; overflow: hidden; }}
    .message-card p {{ color: #343a42; font-size: 14px; margin: 8px 0 10px; }}
    .message-meta {{ display: flex; flex-wrap: wrap; gap: 7px; color: var(--muted); font-size: 12px; }}
    .message-links {{ display: flex; flex-wrap: wrap; gap: 10px; font-size: 13px; margin-top: 8px; }}
    .pill, .tag {{ display: inline-flex; align-items: center; min-height: 24px; padding: 3px 8px; border-radius: 999px; font-size: 12px; }}
    .pill {{ background: #eef4f8; color: #405064; margin: 3px 4px 0 0; }}
    .tag {{ background: #f9e5e2; color: var(--danger); font-weight: 700; }}
    .domain-grid {{ grid-template-columns: repeat(3, minmax(0, 1fr)); }}
    .domain-card {{ padding: 14px; }}
    .domain-head {{ display: flex; justify-content: space-between; gap: 12px; margin-bottom: 8px; }}
    .domain-head span {{ color: var(--accent); font-weight: 700; }}
    .domain-card ul {{ margin: 0; padding-left: 18px; }}
    .domain-card li {{ margin: 9px 0; }}
    .domain-card li span {{ display: block; color: var(--muted); font-size: 12px; margin-top: 2px; }}
    .charts {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    .chart-card {{ margin: 0; padding: 12px; }}
    .chart-card img {{ width: 100%; max-height: 72vh; object-fit: contain; display: block; border-radius: 6px; border: 1px solid var(--line); background: #fff; }}
    .chart-card figcaption {{ padding-top: 8px; color: var(--muted); font-size: 13px; }}
    .toolbar {{ display: flex; gap: 10px; margin-bottom: 12px; }}
    input {{ width: 100%; border: 1px solid var(--line); border-radius: 8px; padding: 11px 12px; font-size: 15px; background: white; }}
    .explorer {{ max-height: 680px; overflow: auto; border: 1px solid var(--line); border-radius: 8px; background: white; }}
    .explorer table {{ min-width: 980px; }}
    .small {{ color: var(--muted); font-size: 13px; }}
    @media (max-width: 1000px) {{
      .shell {{ padding: 16px; }}
      header, .two, .three, .charts, .domain-grid, .message-list {{ grid-template-columns: 1fr; }}
      .kpis {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    }}
  </style>
</head>
<body>
  <main class="shell">
    <header>
      <div>
        <h1>Dashboard {h(subject_display)}</h1>
        <p class="subtitle">Analisis exploratorio de mensajes de Telegram sobre {h(subject_display)}. Dataset: <strong>{h(dataset_name)}</strong>, periodo {h(date_min)} a {h(date_max)}.</p>
        <div class="actions">
          <a class="button" href="{h(csv_path.name)}" download="{h(csv_path.name)}">Descargar CSV original</a>
          <a class="button secondary" href="#explorador">Explorar mensajes</a>
        </div>
      </div>
      <div class="notice">Nota: todas las secciones generales analizan el conjunto completo de mensajes recuperados sobre {h(subject_display)}. La seccion especial es un subconjunto configurable: {h(focus_label)}. El dashboard no verifica si esas afirmaciones son ciertas; sirve para localizar, comparar y auditar mensajes y enlaces. El CSV original completo pesa {fmt_int(csv_size)} bytes y queda enlazado como archivo local.</div>
    </header>

    <section class="grid kpis">
      <div class="card kpi"><strong>{fmt_int(stats['total'])}</strong><span>mensajes</span></div>
      <div class="card kpi"><strong>{fmt_int(stats['channels'])}</strong><span>canales</span></div>
      <div class="card kpi"><strong>{fmt_int(stats['total_views'])}</strong><span>vistas acumuladas</span></div>
      <div class="card kpi"><strong>{fmt_int(imputacion_count)}</strong><span>{h(focus_label)} ({pct(imputacion_count, stats['total'])})</span></div>
      <div class="card kpi"><strong>{h(peak_month)}</strong><span>mes de mayor actividad ({fmt_int(peak_count)})</span></div>
    </section>

    <section class="grid two section">
      <div class="card">
        <h2>Lectura rapida</h2>
        <p>El canal con mas mensajes en este dataset es <strong>{h(top_channel)}</strong> ({fmt_int(top_channel_count)} mensajes). El dominio mas repetido es <strong>{h(top_domain)}</strong> ({fmt_int(top_domain_count)} apariciones). El pico mensual cae en <strong>{h(peak_month)}</strong>.</p>
        <p>Las secciones de canales, dominios, graficos, impacto y explorador cubren todo el contenido del dataset. La seccion especial separa los mensajes que cumplen el patron configurado para <strong>{h(focus_label)}</strong>.</p>
      </div>
      <div class="card">
        <h2>Temas detectados automaticamente</h2>
        <p class="small">Expresiones frecuentes extraidas del contenido del dataset. No son categorias predefinidas.</p>
        {topic_bars(stats)}
      </div>
    </section>

    <section class="grid two section">
      <div class="card">
        <h2>Top canales por mensajes</h2>
        <table><tbody>{table_rows(stats['channel_counts'], 12)}</tbody></table>
      </div>
      <div class="card">
        <h2>Top canales por vistas</h2>
        <table><tbody>{table_rows(stats['channel_views'], 12)}</tbody></table>
      </div>
    </section>

    <section class="section">
      <h2>Foco especial: {h(focus_label)}</h2>
      <div class="message-list">
        {''.join(row_card(r, 'foco especial') for r in stats['imputacion_top'][:16])}
      </div>
    </section>

    <section class="section">
      <h2>Dominios, enlaces y titulares</h2>
      <div class="grid domain-grid">
        {domain_cards(stats, 15)}
      </div>
    </section>

    <section class="section">
      <h2>Mensajes de mayor impacto</h2>
      <div class="message-list">
        {''.join(row_card(r, 'impacto') for r in stats['high_impact'][:16])}
      </div>
    </section>

    <section class="section">
      <h2>Graficos existentes</h2>
      <div class="grid charts">
        {chart_gallery(dataset_dir)}
      </div>
    </section>

    <section id="explorador" class="section card">
      <h2>Explorador rapido</h2>
      <p class="small">Las estadisticas usan los {fmt_int(explorer_total)} mensajes del dataset. Para mantener fluida la pantalla, este explorador carga los {fmt_int(len(explorer_embedded))} mensajes mas recientes y cada busqueda muestra hasta 250 resultados.</p>
      <div class="toolbar"><input id="search" type="search" placeholder="Buscar: imputado, Plus Ultra, Maduro, canal, dominio..."></div>
      <div class="explorer"><table>
        <thead><tr><th>Fecha</th><th>Canal</th><th>Vistas</th><th>Titular / resumen</th><th>Temas</th><th>Links</th></tr></thead>
        <tbody id="explorer-body"></tbody>
      </table></div>
    </section>
  </main>

  <script>
    const rows = {explorer_json};
    const tbody = document.getElementById('explorer-body');
    const search = document.getElementById('search');
    function esc(s) {{ return String(s ?? '').replace(/[&<>"']/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c])); }}
    function render(filter = '') {{
      const q = filter.trim().toLowerCase();
      const data = rows.filter(r => !q || JSON.stringify(r).toLowerCase().includes(q)).slice(0, 250);
      tbody.innerHTML = data.map(r => {{
        const links = [r.telegram, ...(r.links || [])].filter(Boolean).map((u, i) => `<a href="${{esc(u)}}" target="_blank" rel="noreferrer">${{i === 0 ? 'Telegram' : 'enlace ' + i}}</a>`).join(' ');
        const topics = (r.topics || []).map(t => `<span class="pill">${{esc(t)}}</span>`).join(' ');
        return `<tr><td>${{esc(r.date)}}</td><td>@${{esc(r.channel)}}</td><td>${{Number(r.views || 0).toLocaleString('es-ES')}}</td><td>${{esc(r.title)}}</td><td>${{topics}}</td><td>${{links}}</td></tr>`;
      }}).join('');
    }}
    search.addEventListener('input', () => render(search.value));
    render();
  </script>
</body>
</html>
"""
    return html_doc


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", nargs="?", help="Nombre de dataset o canal")
    parser.add_argument("--base", default="dataset", help="Carpeta base (default: dataset)")
    parser.add_argument("--channel", action="store_true", help="Buscar en data/<nombre> en lugar de dataset/<nombre>")
    parser.add_argument("--subject", default=None, help="Nombre visible del sujeto buscado (default: nombre del dataset)")
    parser.add_argument("--aliases", default="", help="Alias separados por comas para detectar el sujeto en el foco")
    parser.add_argument("--focus-label", default=None, help="Nombre de la seccion especial")
    parser.add_argument(
        "--focus-terms",
        default="",
        help="Terminos literales separados por comas. Si se indican, sustituyen el foco predeterminado.",
    )
    parser.add_argument(
        "--focus-regex",
        default=DEFAULT_FOCUS_TERMS_PATTERN,
        help="Regex para seleccionar mensajes del foco especial (default: terminos judiciales/imputacion)",
    )
    args = parser.parse_args()

    dataset_name = args.dataset or input("Nombre del dataset (subcarpeta dentro de dataset/): ").strip()
    if not dataset_name:
        print("ERROR: dataset vacio.")
        sys.exit(1)

    if args.channel:
        dataset_dir = Path("data") / dataset_name
    else:
        dataset_dir = Path(args.base) / dataset_name
        if not dataset_dir.exists() and (Path("data") / dataset_name).exists():
            dataset_dir = Path("data") / dataset_name
    csv_path = dataset_dir / "msgs_dataset.csv"
    if not csv_path.exists():
        print(f"ERROR: No existe {csv_path}.")
        print("El dashboard espera un archivo msgs_dataset.csv generado por la aplicacion.")
        sys.exit(1)

    subject_display = args.subject or dataset_name.replace("_", " ").replace("-", " ").title()
    aliases = [part.strip() for part in args.aliases.split(",") if part.strip()]
    if dataset_name.lower() == "zapatero" and not aliases:
        aliases = ["zapatero", "rodriguez zapatero", "rodriguez", "jose luis rodriguez"]
    custom_focus_re = build_focus_terms_regex(args.focus_terms)
    if custom_focus_re:
        focus_label = args.focus_label or "Foco personalizado"
        subject_re = None
        focus_re = custom_focus_re
    else:
        focus_label = args.focus_label or f"Imputacion / investigacion de {subject_display}"
        subject_re = build_subject_regex(subject_display, aliases)
        focus_re = build_focus_regex(args.focus_regex)

    rows = load_rows(csv_path)
    stats = analyse(rows, subject_re, focus_re, focus_label)
    out = dataset_dir / "dashboard.html"
    out.write_text(
        render_dashboard(dataset_name, dataset_dir, csv_path, rows, stats, subject_display, focus_label),
        encoding="utf-8",
    )
    print(f"OK: Dashboard generado en: {out.resolve()}")


if __name__ == "__main__":
    main()
