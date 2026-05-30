import argparse
import base64
import csv
import html
import json
import math
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse, unquote


REQUIRED_COLS = {"username", "date", "message", "views", "msg_link", "links", "domains"}

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

CHARTS = [
    ("Timeline mensual", "01_mensajes_mes_timeline_global.png"),
    ("Timeline top canales", "01b_mensajes_mes_timeline_top_canales.png"),
    ("Mensajes por hora", "01c_mensajes_hora_global.png"),
    ("Pico de 5 minutos", "01d_pico_minuto_5m_global.png"),
    ("Top canales por mensajes", "02_top10_mensajes_canal.png"),
    ("Top canales por vistas", "03_top10_vistas_canal.png"),
    ("Top dominios", "04_top10_dominios.png"),
    ("Nube de palabras", "05_wordcloud.png"),
]


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
    links = extract_links(row.get("links") or "", msg)
    domains = extract_domains(row.get("domains") or "", links)
    dt = parse_date(row.get("date") or "")
    views = to_int(row.get("views"))
    forwards = to_int(row.get("number_forwards"))
    replies = to_int(row.get("number_replies"))
    title = make_title(msg, links)
    return {
        "username": (row.get("username") or "").strip() or "(sin_username)",
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
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
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


def analyse(rows, subject_re, focus_re, focus_label):
    for row in rows:
        msg = row["message"]
        row["topic_hits"] = [name for name, rx in TOPIC_PATTERNS.items() if rx.search(msg)]
        if is_focus_message(msg, subject_re, focus_re):
            row["topic_hits"].insert(0, focus_label)

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

    imputacion = [r for r in rows if focus_label in r["topic_hits"]]
    high_impact = sorted(rows, key=lambda r: message_score(r), reverse=True)[:30]
    imputacion_top = sorted(imputacion, key=lambda r: message_score(r, 50000), reverse=True)[:40]
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
        chart_path = dataset_dir / filename
        if chart_path.exists():
            src = image_data_uri(chart_path)
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

    csv_data_uri = file_data_uri(csv_path, "text/csv")
    csv_size = csv_path.stat().st_size

    explorer_rows = sorted(rows, key=lambda r: r["dt"] or datetime.min, reverse=True)
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
            for r in explorer_rows
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
    td, th {{ padding: 9px 8px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }}
    th {{ color: var(--muted); font-weight: 600; }}
    .bar-row {{ margin: 12px 0; }}
    .bar-label {{ display: flex; justify-content: space-between; gap: 12px; margin-bottom: 5px; font-size: 14px; }}
    .bar-track {{ height: 10px; border-radius: 999px; background: #e8edf3; overflow: hidden; }}
    .bar-track div {{ height: 100%; border-radius: 999px; background: var(--accent); }}
    .message-list {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }}
    .message-card {{ padding: 15px; }}
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
    .chart-card img {{ width: 100%; display: block; border-radius: 6px; border: 1px solid var(--line); }}
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
          <a class="button" href="{h(csv_data_uri)}" download="messages.csv">Descargar CSV original</a>
          <a class="button secondary" href="#explorador">Explorar mensajes</a>
        </div>
      </div>
      <div class="notice">Nota: todas las secciones generales analizan el conjunto completo de mensajes recuperados sobre {h(subject_display)}. La seccion especial es un subconjunto configurable: {h(focus_label)}. El dashboard no verifica si esas afirmaciones son ciertas; sirve para localizar, comparar y auditar mensajes y enlaces. Este HTML incluye el CSV original completo ({fmt_int(csv_size)} bytes) para descarga offline.</div>
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
        <h2>Temas detectados</h2>
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
      <p class="small">Filtra sobre los {fmt_int(len(explorer_rows))} mensajes del dataset. Para mantener fluida la pantalla, cada busqueda muestra hasta 250 resultados.</p>
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
    parser.add_argument("dataset", nargs="?", help="Subcarpeta dentro de dataset/")
    parser.add_argument("--base", default="dataset", help="Carpeta base (default: dataset)")
    parser.add_argument("--subject", default=None, help="Nombre visible del sujeto buscado (default: nombre del dataset)")
    parser.add_argument("--aliases", default="", help="Alias separados por comas para detectar el sujeto en el foco")
    parser.add_argument("--focus-label", default=None, help="Nombre de la seccion especial")
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

    dataset_dir = Path(args.base) / dataset_name
    csv_path = dataset_dir / "messages.csv"
    if not csv_path.exists():
        print(f"ERROR: No existe {csv_path}.")
        sys.exit(1)

    subject_display = args.subject or dataset_name.replace("_", " ").replace("-", " ").title()
    aliases = [part.strip() for part in args.aliases.split(",") if part.strip()]
    if dataset_name.lower() == "zapatero" and not aliases:
        aliases = ["zapatero", "rodriguez zapatero", "rodriguez", "jose luis rodriguez"]
    focus_label = args.focus_label or f"Imputacion / investigacion de {subject_display}"

    rows = load_rows(csv_path)
    subject_re = build_subject_regex(subject_display, aliases)
    focus_re = build_focus_regex(args.focus_regex)
    stats = analyse(rows, subject_re, focus_re, focus_label)
    out = dataset_dir / "dashboard.html"
    out.write_text(
        render_dashboard(dataset_name, dataset_dir, csv_path, rows, stats, subject_display, focus_label),
        encoding="utf-8",
    )
    print(f"OK: Dashboard generado en: {out.resolve()}")


if __name__ == "__main__":
    main()
