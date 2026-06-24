#!/usr/bin/env python3
"""Generate an 8-minute Heimdall demo walkthrough video (1920x1080).

Renders branded scene backgrounds with PIL using REAL data captured from the
live scoring API, the demo ops endpoint, and the local decision-logic scenarios,
then emits one frame per second (with a global progress bar + countdown) for
ffmpeg to encode into an MP4.
"""
import json, os, math, textwrap
from PIL import Image, ImageDraw, ImageFont

# ----------------------------------------------------------------------------- #
# Paths & data
# ----------------------------------------------------------------------------- #
OUT = "/tmp/demovid"
FRAMES = os.path.join(OUT, "frames")
os.makedirs(FRAMES, exist_ok=True)

OPS = json.load(open(os.path.join(OUT, "ops.json"))) if os.path.exists(os.path.join(OUT,"ops.json")) else {}
API = json.load(open(os.path.join(OUT, "api_real.json")))
SCN = json.load(open(os.path.join(OUT, "scenarios_real.json")))

W, H = 1920, 1080

# ----------------------------------------------------------------------------- #
# Brand palette (from docs/assets/heimdall-kpi-visual.html)
# ----------------------------------------------------------------------------- #
ACCENT      = (70, 79, 235)     # #464feb
ACCENT_SOFT = (115, 133, 255)   # #7385ff
BG          = (15, 17, 28)      # deep navy
BG2         = (24, 27, 43)      # card bg
CARD        = (31, 35, 56)
CARD_HI     = (40, 45, 72)
BORDER      = (54, 60, 92)
TXT         = (236, 239, 248)
SUB         = (170, 178, 205)
MUTED       = (120, 128, 158)
GREEN       = (46, 204, 113)
AMBER       = (241, 196, 15)
RED         = (231, 76, 60)
WHITE       = (255, 255, 255)

# ----------------------------------------------------------------------------- #
# Fonts — prefer Segoe UI (brand), fall back to DejaVu
# ----------------------------------------------------------------------------- #
SEGOE = "/mnt/c/Windows/Fonts/segoeui.ttf"
SEGOEB = "/mnt/c/Windows/Fonts/segoeuib.ttf"
SEGOEL = "/mnt/c/Windows/Fonts/segoeuil.ttf"
SEGOESB = "/mnt/c/Windows/Fonts/segoeuib.ttf"
DEJA = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
DEJAB = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
DEJAM = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"

def _f(path, fallback, size):
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.truetype(fallback, size)

def font(size, weight="r"):
    if weight == "b":
        return _f(SEGOEB, DEJAB, size)
    if weight == "sb":
        return _f(SEGOESB, DEJAB, size)
    if weight == "l":
        return _f(SEGOEL, DEJA, size)
    return _f(SEGOE, DEJA, size)

def mono(size):
    return _f(DEJAM, DEJAM, size)

# ----------------------------------------------------------------------------- #
# Drawing helpers
# ----------------------------------------------------------------------------- #
def rrect(d, xy, r, fill=None, outline=None, width=1):
    d.rounded_rectangle(xy, radius=r, fill=fill, outline=outline, width=width)

def text(d, xy, s, fnt, fill=TXT, anchor="la", spacing=4):
    d.text(xy, s, font=fnt, fill=fill, anchor=anchor, spacing=spacing)

def textw(d, s, fnt):
    b = d.textbbox((0,0), s, font=fnt)
    return b[2]-b[0]

def wrap(d, s, fnt, maxw):
    words = s.split()
    lines, cur = [], ""
    for w in words:
        t = (cur+" "+w).strip()
        if textw(d, t, fnt) <= maxw:
            cur = t
        else:
            if cur: lines.append(cur)
            cur = w
    if cur: lines.append(cur)
    return lines

def gradient_bg(top=BG, bottom=(10,12,22)):
    # fast vertical gradient: build a 1xH column then resize to full width
    col = Image.new("RGB", (1, H))
    p = col.load()
    for y in range(H):
        t = y/H
        p[0, y] = (int(top[0]*(1-t)+bottom[0]*t),
                   int(top[1]*(1-t)+bottom[1]*t),
                   int(top[2]*(1-t)+bottom[2]*t))
    return col.resize((W, H))

def base_canvas():
    img = gradient_bg()
    d = ImageDraw.Draw(img)
    # subtle accent bar top
    d.rectangle([0,0,W,6], fill=ACCENT)
    return img, d

def header(d, kicker, title, section_no, section_name):
    text(d, (90, 70), kicker, font(26, "sb"), ACCENT_SOFT)
    text(d, (90, 108), title, font(58, "b"), WHITE)
    # section pill top-right
    pill = f"  {section_name}  "
    fw = textw(d, pill, font(24, "sb"))
    rrect(d, [W-110-fw, 78, W-90, 78+44], 22, fill=CARD, outline=BORDER, width=2)
    text(d, (W-100-fw+10, 80), pill.strip(), font(24, "sb"), ACCENT_SOFT)
    text(d, (W-100-fw+10, 80), "", font(24,"sb"))

def chip(d, x, y, label, color):
    fw = textw(d, label, font(22, "sb"))
    rrect(d, [x, y, x+fw+28, y+40], 20, fill=(color[0]//5+20,color[1]//5+20,color[2]//5+20), outline=color, width=2)
    text(d, (x+14, y+7), label, font(22, "sb"), color)
    return fw+28

# ----------------------------------------------------------------------------- #
# Scene renderers — each returns a finished PIL image (no overlay yet)
# ----------------------------------------------------------------------------- #

def scene_title():
    img, d = base_canvas()
    # centered hero
    text(d, (W//2, 300), "HEIMDALL", font(150, "b"), WHITE, anchor="mm")
    text(d, (W//2, 410), "Fraud Intelligence Platform", font(54, "l"), ACCENT_SOFT, anchor="mm")
    rrect(d, [W//2-330, 470, W//2+330, 474], 2, fill=ACCENT)
    text(d, (W//2, 540), "Real-time fraud detection for the Nordics & Baltics", font(34), SUB, anchor="mm")
    # metric ribbon
    metrics = [("4.2B","transactions / year"),("5","countries"),("18ms","scoring SLA"),("–41%","fraud losses")]
    n=len(metrics); cw=320; gap=40; total=n*cw+(n-1)*gap; x0=(W-total)//2; y=660
    for i,(v,l) in enumerate(metrics):
        x=x0+i*(cw+gap)
        rrect(d, [x, y, x+cw, y+150], 16, fill=CARD, outline=BORDER, width=2)
        text(d, (x+cw//2, y+58), v, font(58,"b"), ACCENT_SOFT, anchor="mm")
        text(d, (x+cw//2, y+110), l, font(26), SUB, anchor="mm")
    text(d, (W//2, 900), "8-minute guided walkthrough", font(28, "sb"), MUTED, anchor="mm")
    text(d, (W//2, 945), "Live Scoring API  ·  Decision Spectrum  ·  Ops & Compliance", font(24), MUTED, anchor="mm")
    return img

def scene_exec_overview():
    img, d = base_canvas()
    header(d, "MINUTE 0–2  ·  CONTEXT", "Executive Overview", 1, "CONTEXT")
    cards = [
        ("Annual Transactions", "4.2 billion", "High-volume payments processed each year across five countries.", ACCENT_SOFT),
        ("Fraud Loss Reduction", "–41%", "Fraud losses cut by nearly half after deploying the AI platform.", GREEN),
        ("False Decline Rate", "1.1%", "Down from 2.8% — a ~60% improvement, less friction & churn.", GREEN),
        ("Real-Time Scoring", "18 ms", "Fraud risk scored per transaction, beating the 120 ms SLA.", ACCENT_SOFT),
    ]
    cw, ch, gap = 860, 290, 40
    x0, y0 = 90, 240
    for i,(t,v,desc,col) in enumerate(cards):
        cx = x0 + (i%2)*(cw+gap)
        cy = y0 + (i//2)*(ch+gap)
        rrect(d, [cx, cy, cx+cw, cy+ch], 18, fill=CARD, outline=BORDER, width=2)
        text(d, (cx+40, cy+34), t, font(34, "sb"), TXT)
        text(d, (cx+40, cy+90), v, font(82, "b"), col)
        for j,ln in enumerate(wrap(d, desc, font(28), cw-80)):
            text(d, (cx+40, cy+200+j*38), ln, font(28), SUB)
    return img

def scene_architecture():
    img, d = base_canvas()
    header(d, "MINUTE 0–2  ·  CONTEXT", "How a payment flows through Heimdall", 1, "CONTEXT")
    steps = [
        ("Ingest", "Event Hubs", "4.2B tx/yr streamed", ACCENT_SOFT),
        ("Score", "Scoring API\nONNX in-process", "p99 < 18 ms", GREEN),
        ("Decide", "PSD2 optimiser", "approve / SCA / decline", AMBER),
        ("Investigate", "Agentic case\n+ GNN rings", "analyst-ready in sec", ACCENT_SOFT),
        ("Report", "Fabric Gold →\nPower BI", "EBA auto-filed", ACCENT_SOFT),
    ]
    n=len(steps); bw=300; gap=58; total=n*bw+(n-1)*gap; x0=(W-total)//2; y=420
    for i,(t,sub,kpi,col) in enumerate(steps):
        x=x0+i*(bw+gap)
        rrect(d, [x, y, x+bw, y+220], 16, fill=CARD, outline=col, width=2)
        text(d, (x+bw//2, y+44), t, font(38,"b"), col, anchor="mm")
        for j,ln in enumerate(sub.split("\n")):
            text(d, (x+bw//2, y+96+j*34), ln, font(26), TXT, anchor="mm")
        text(d, (x+bw//2, y+178), kpi, font(23, "sb"), SUB, anchor="mm")
        if i<n-1:
            ax=x+bw+gap//2
            d.line([x+bw+8, y+110, x+bw+gap-8, y+110], fill=ACCENT, width=4)
            d.polygon([(x+bw+gap-8,y+110),(x+bw+gap-22,y+100),(x+bw+gap-22,y+120)], fill=ACCENT)
    text(d, (W//2, 720), "ONNX runs in-process — not a remote model call. That's how we hit 18 ms.", font(32, "sb"), ACCENT_SOFT, anchor="mm")
    text(d, (W//2, 770), "Graph Neural Networks detect fraud rings that rule-based systems miss.", font(30), SUB, anchor="mm")
    return img

def scene_switch_live():
    img, d = base_canvas()
    text(d, (W//2, H//2-60), "▶  Switching to the live environment", font(60, "b"), WHITE, anchor="mm")
    text(d, (W//2, H//2+30), "Production scoring API · Azure Container Apps · Sweden Central", font(34), SUB, anchor="mm")
    text(d, (W//2, H//2+110), "ca-scoring-prod-swc.purpleforest-f993111a.swedencentral.azurecontainerapps.io", mono(24), ACCENT_SOFT, anchor="mm")
    return img

def _json_block(d, x, y, w, h, title, obj, titlecol=TXT):
    rrect(d, [x, y, x+w, y+h], 14, fill=(18,20,32), outline=BORDER, width=2)
    rrect(d, [x, y, x+w, y+46], 14, fill=CARD)
    d.rectangle([x, y+30, x+w, y+46], fill=CARD)
    text(d, (x+22, y+10), title, font(26, "sb"), titlecol)
    s = json.dumps(obj, indent=2)
    f = mono(23)
    yy = y+62
    for ln in s.splitlines():
        col = TXT
        if ":" in ln:
            col = TXT
        text(d, (x+24, yy), ln, f, col)
        yy += 30
        if yy > y+h-20: break

def scene_swagger_intro():
    img, d = base_canvas()
    header(d, "MINUTE 2–4  ·  LIVE SCORING API", "Real-time fraud scoring engine", 2, "SCORING API")
    rrect(d, [90, 240, W-90, 330], 14, fill=CARD, outline=BORDER, width=2)
    text(d, (120, 262), "POST  /v1/score", mono(40, ), GREEN if False else GREEN)
    text(d, (120, 262), "POST  /v1/score", mono(40), GREEN)
    text(d, (W-110, 268), "Swagger UI · /docs", font(28), SUB, anchor="ra")
    bullets = [
        "Synchronous REST endpoint — one call per transaction, JSON in / JSON out.",
        "ONNX ensemble (XGBoost + LightGBM + Logistic) scored in-process for ~18 ms latency.",
        "Returns a calibrated fraud probability, a decision, and SHAP-derived reason codes.",
        "PSD2 SCA-exemption optimiser decides approve vs step-up vs decline within compliant bounds.",
    ]
    y=390
    for b in bullets:
        d.ellipse([100, y+12, 118, y+30], fill=ACCENT)
        for j,ln in enumerate(wrap(d, b, font(32), W-260)):
            text(d, (140, y+(j*40)), ln, font(32), TXT)
        y += 40*len(wrap(d, b, font(32), W-260)) + 36
    return img

def scene_api_request(kind):
    img, d = base_canvas()
    data = API[kind]
    label = "Legitimate transaction" if kind=="legit" else "Suspicious transaction"
    header(d, "MINUTE 2–4  ·  LIVE SCORING API", f"Try it out — {label}", 2, "SCORING API")
    _json_block(d, 90, 240, 880, 760, "Request  ·  POST /v1/score", data["req"], ACCENT_SOFT)
    # right column annotations
    x=1010
    text(d, (x, 250), "What we're sending", font(34, "sb"), WHITE)
    notes = {
        "legit": [
            ("Amount", "€24.90 — small online grocery order"),
            ("Country", "SE — domestic, expected geo"),
            ("Device", "known fingerprint, seen before"),
            ("Channel", "ECOM — card-not-present"),
        ],
        "suspicious": [
            ("Amount", "€5,200 — large, atypical"),
            ("Country", "NG — cross-border, high-risk geo"),
            ("Device", "brand-new fingerprint"),
            ("IP", "flagged hosting range"),
        ],
    }[kind]
    y=310
    for t,desc in notes:
        rrect(d, [x, y, W-90, y+96], 12, fill=CARD, outline=BORDER, width=2)
        text(d, (x+24, y+16), t, font(28, "sb"), ACCENT_SOFT)
        for j,ln in enumerate(wrap(d, desc, font(26), W-90-x-48)):
            text(d, (x+24, y+52+j*30), ln, font(26), SUB)
        y += 116
    return img

def scene_api_response(kind):
    img, d = base_canvas()
    data = API[kind]
    resp = data["resp"]
    decision = resp["decision"]
    col = {"APPROVE":GREEN, "SCA":AMBER, "DECLINE":RED}.get(decision, ACCENT_SOFT)
    header(d, "MINUTE 2–4  ·  LIVE SCORING API", "Response — explainable decision", 2, "SCORING API")
    _json_block(d, 90, 240, 880, 560, f"200 OK  ·  {data['rtt_ms']} ms round-trip", resp, GREEN)
    # decision banner
    x=1010
    rrect(d, [x, 240, W-90, 470], 18, fill=CARD, outline=col, width=3)
    text(d, (x+40, 270), "DECISION", font(28, "sb"), SUB)
    text(d, (x+40, 312), decision, font(96, "b"), col)
    text(d, (x+40, 430), f"fraud score  {resp['score']:.3f}", font(34, "sb"), TXT)
    # score gauge
    gx, gy, gw = x+40, 540, W-90-x-80
    rrect(d, [gx, gy, gx+gw, gy+34], 17, fill=(20,22,36), outline=BORDER, width=2)
    s = max(0.0, min(1.0, resp["score"]))
    rrect(d, [gx, gy, gx+int(gw*s), gy+34], 17, fill=col)
    text(d, (gx, gy+50), "0.0", font(22), MUTED)
    text(d, (gx+gw, gy+50), "1.0", font(22), MUTED, anchor="ra")
    # reason codes
    text(d, (x+40, 630), "Reason codes (SHAP-derived)", font(30, "sb"), WHITE)
    cy=685; cx=x+40
    for rc in resp.get("reason_codes", []):
        cw = chip(d, cx, cy, rc, ACCENT_SOFT)
        cx += cw + 16
        if cx > W-200: cx=x+40; cy+=56
    text(d, (x+40, 770), f"PSD2 exemption: {resp.get('psd2_exemption','NONE')}", font(28, "sb"), SUB)
    text(d, (x+40, 815), f"model {resp.get('model_version','')}  ·  inference {resp.get('latency_ms','?')} ms", font(24), MUTED)
    text(d, (120, 850), "Every decision in well under 18 ms, with explainable reason codes from SHAP.", font(30, "sb"), ACCENT_SOFT)
    return img

def scene_console_intro():
    img, d = base_canvas()
    header(d, "MINUTE 4–6  ·  DECISION SPECTRUM", "Demo web console — the full spectrum", 3, "CONSOLE")
    text(d, (90, 250), "The model returns not just yes/no, but a calibrated probability that drives", font(34), TXT)
    text(d, (90, 296), "SCA optimisation under PSD2. Six curated transactions show every outcome:", font(34), TXT)
    cats = [("APPROVE", GREEN, "frictionless — exemption applied"),
            ("SCA STEP-UP", AMBER, "challenge, not block — protects real customers"),
            ("DECLINE", RED, "hard stop + agentic case opened")]
    y=400
    for t,c,desc in cats:
        rrect(d, [90, y, W-90, y+120], 16, fill=CARD, outline=c, width=3)
        chip(d, 120, y+38, t, c)
        text(d, (470, y+44), desc, font(34), TXT)
        y += 150
    text(d, (90, 880), "http://127.0.0.1:8800   ·   start with ./scripts/demo-web.sh", mono(28), ACCENT_SOFT)
    return img

def scene_spectrum(decision_filter, title):
    img, d = base_canvas()
    col = {"APPROVE":GREEN, "SCA":AMBER, "DECLINE":RED}[decision_filter]
    header(d, "MINUTE 4–6  ·  DECISION SPECTRUM", title, 3, "CONSOLE")
    rows = [s for s in SCN if s["decision"]==decision_filter]
    y=250
    for s in rows:
        rrect(d, [90, y, W-90, y+300], 16, fill=CARD, outline=BORDER, width=2)
        rrect(d, [90, y, 100, y+300], 8, fill=col)
        text(d, (140, y+30), s["title"], font(40, "sb"), WHITE)
        chip(d, W-360, y+34, f"{decision_filter}", col)
        # amount + meta
        text(d, (140, y+96), f"{s['currency']} {s['amount']:,.2f}  ·  {s['country']}  ·  {s['channel']}", font(30, "sb"), ACCENT_SOFT)
        for j,ln in enumerate(wrap(d, s["narrative"], font(30), W-260)):
            text(d, (140, y+148+j*38), ln, font(30), SUB)
        # score gauge + exemption
        gx, gy, gw = 140, y+250, 900
        rrect(d, [gx, gy, gx+gw, gy+30], 15, fill=(20,22,36), outline=BORDER, width=2)
        sc=max(0.0,min(1.0,s["score"]))
        rrect(d, [gx, gy, gx+int(gw*sc), gy+30], 15, fill=col)
        text(d, (gx+gw+30, gy-2), f"score {s['score']:.3f}", font(30, "sb"), TXT)
        ex = s["exemption"] if s["exemption"]!="NONE" else "—"
        text(d, (gx+gw+260, gy-2), f"exemption {ex}", font(28), SUB)
        # reason codes
        cx=W-470; cyy=y+96
        for rc in s["reason_codes"][:3]:
            chip(d, cx, cyy, rc, ACCENT_SOFT); cyy+=52
        y += 340
    return img

def _kpi_tile(d, x, y, w, h, label, value, sub, col=ACCENT_SOFT, ok=None):
    rrect(d, [x, y, x+w, y+h], 16, fill=CARD, outline=BORDER, width=2)
    text(d, (x+28, y+24), label, font(28, "sb"), SUB)
    text(d, (x+28, y+66), value, font(64, "b"), col)
    if sub:
        text(d, (x+28, y+h-52), sub, font(26), MUTED)
    if ok is not None:
        c = GREEN if ok else RED
        d.ellipse([x+w-46, y+30, x+w-22, y+54], fill=c)

def scene_ops_dashboard():
    img, d = base_canvas()
    o = OPS
    header(d, "MINUTE 6–8  ·  DASHBOARDS", "Operations — live SLOs (Grafana)", 4, "OPS")
    tiles = [
        ("Throughput", f"{o.get('throughput_tps',0):,} tps", f"{o.get('replicas',0)}/{o.get('replicas_max',0)} replicas", ACCENT_SOFT, True),
        ("Scoring p99", f"{o.get('latency_p99_ms',0)} ms", f"SLO < {o.get('slo_p99_ms',18)} ms", GREEN, o.get('latency_p99_ms',99)<o.get('slo_p99_ms',18)),
        ("Availability 30d", f"{o.get('availability_30d',0)}%", "target 99.99%", GREEN, True),
        ("Fraud caught today", f"€{o.get('fraud_caught_eur_today',0):,}", f"{o.get('cases_opened_today',0):,} cases opened", GREEN, True),
        ("Model AUC", f"{o.get('model_auc',0)}", f"P {o.get('precision',0)} · R {o.get('recall',0)}", ACCENT_SOFT, True),
        ("False-positive rate", f"{o.get('false_positive_rate',0)}%", f"was {o.get('false_positive_baseline',0)}%", GREEN, True),
        ("Active regions", f"{o.get('regions_active',0)}", "multi-region active/active", ACCENT_SOFT, True),
        ("Model drift", f"{o.get('drift_status','—')}", "Azure ML Monitor", GREEN, o.get('drift_status')=='stable'),
    ]
    cols=4; tw=420; th=210; gx=40; gy=40; x0=90; y0=240
    for i,(l,v,s,c,ok) in enumerate(tiles):
        x=x0+(i%cols)*(tw+gx); y=y0+(i//cols)*(th+gy)
        _kpi_tile(d, x, y, tw, th, l, v, s, c, ok)
    # decision mix bar
    mix=o.get('decision_mix',{})
    by=770; bx=90; bw=W-180; bh=70
    text(d, (bx, by-46), "Decision mix (live)", font(30, "sb"), WHITE)
    segs=[("approve",mix.get('approve',0),GREEN),("sca",mix.get('sca',0),AMBER),("decline",mix.get('decline',0),RED)]
    cx=bx
    for name,val,c in segs:
        seg=int(bw*val/100.0)
        rrect(d, [cx, by, cx+seg, by+bh], 8, fill=c)
        if seg>120:
            text(d, (cx+16, by+18), f"{name} {val}%", font(28, "sb"), (12,14,20))
        cx+=seg+4
    text(d, (90, 880), f"{o.get('scored_total',0):,} transactions scored  ·  HITL queue {o.get('hitl_queue',0)}  ·  next EBA report in {o.get('eba_report_days','?')} days", font(28), SUB)
    return img

def scene_powerbi():
    img, d = base_canvas()
    header(d, "MINUTE 6–8  ·  DASHBOARDS", "Power BI — EBA quarterly report", 4, "POWER BI")
    text(d, (90, 230), "Auto-generated from the Fabric Gold layer — zero manual hours per quarter.", font(32), TXT)
    # mock report: slicers + breakdown tables
    rrect(d, [90, 290, 980, 350], 12, fill=CARD, outline=ACCENT, width=2)
    text(d, (110, 305), "Instrument ▾  Card payments - issuing", font(28, "sb"), ACCENT_SOFT)
    rrect(d, [1000, 290, W-90, 350], 12, fill=CARD, outline=ACCENT, width=2)
    text(d, (1020, 305), "Country ▾  Sweden", font(28, "sb"), ACCENT_SOFT)
    breakdowns = [
        ("By Instrument (Annex A)", [("Card - issuing","2.1B","€61.9M"),("Credit transfer","1.4B","€91.1M"),("Direct debit","0.7B","€42.3M")]),
        ("By SCA / Exemption (Annex C)", [("LOW_VALUE","41%","2.1 bps"),("TRA","33%","3.4 bps"),("SCA applied","26%","1.0 bps")]),
        ("By Channel", [("ECOM","1.9B","4.1 bps"),("POS","1.5B","1.2 bps"),("ATM","0.8B","0.7 bps")]),
        ("By Country / Geography", [("Sweden","0.9B","€48k"),("Norway","0.8B","€156k"),("Finland","0.7B","€74k")]),
    ]
    cw=860; ch=270; gap=40; x0=90; y0=380
    for i,(title,rows) in enumerate(breakdowns):
        x=x0+(i%2)*(cw+gap); y=y0+(i//2)*(ch+gap)
        rrect(d, [x, y, x+cw, y+ch], 14, fill=CARD, outline=BORDER, width=2)
        text(d, (x+26, y+18), title, font(30, "sb"), ACCENT_SOFT)
        d.line([x+26, y+62, x+cw-26, y+62], fill=BORDER, width=2)
        yy=y+78
        for r in rows:
            text(d, (x+26, yy), r[0], font(27), TXT)
            text(d, (x+cw//2+40, yy), r[1], font(27, "sb"), TXT)
            text(d, (x+cw-26, yy), r[2], font(27, "sb"), ACCENT_SOFT, anchor="ra")
            yy+=58
    text(d, (W//2, 980), "Same report, different instrument — all pre-computed. Full EBA/GL/2020/01 compliance, published automatically.", font(28, "sb"), SUB, anchor="mm")
    return img

def scene_compliance():
    img, d = base_canvas()
    header(d, "MINUTE 6–8  ·  COMPLIANCE", "Audit & governance — full traceability", 4, "AUDIT")
    items = [
        ("Application Insights", "Every /v1/score request traced — decision, score, latency, tx-id. KQL audit queries.", ACCENT_SOFT),
        ("Cosmos DB", "Each decision persisted 7 years (EBA retention) — reason codes, exemption, model version.", ACCENT_SOFT),
        ("Azure ML Monitor", "Data & prediction drift, precision/recall via confirmed-fraud feedback loop.", GREEN),
        ("Key Vault logs", "Full chain-of-custody for every secret access — who, what, when.", AMBER),
        ("EU AI Act", "Voluntary high-risk governance applied despite the Annex III fraud carve-out.", ACCENT_SOFT),
        ("Event Hub capture", "Raw transactions archived to storage for replay & forensic audit.", ACCENT_SOFT),
    ]
    cw=860; ch=200; gap=40; x0=90; y0=240
    for i,(t,desc,c) in enumerate(items):
        x=x0+(i%2)*(cw+gap); y=y0+(i//2)*(ch+gap)
        rrect(d, [x, y, x+cw, y+ch], 14, fill=CARD, outline=BORDER, width=2)
        rrect(d, [x, y, x+8, y+ch], 4, fill=c)
        text(d, (x+34, y+26), t, font(34, "sb"), c)
        for j,ln in enumerate(wrap(d, desc, font(28), cw-70)):
            text(d, (x+34, y+82+j*38), ln, font(28), SUB)
    return img

def scene_closing():
    img, d = base_canvas()
    text(d, (W//2, 180), "Key messages", font(50, "b"), WHITE, anchor="mm")
    msgs = [
        "ONNX in-process — not a remote model call. That's how we hit 18 ms.",
        "Graph Neural Networks detect fraud rings rule-based systems miss.",
        "EU AI Act compliant — voluntary high-risk governance for fraud detection.",
        "From raw transaction to analyst-ready case in seconds — not days.",
        "EBA reports auto-published from the Fabric Gold layer — zero manual hours.",
    ]
    y=290
    for m in msgs:
        d.ellipse([300, y+10, 322, y+32], fill=ACCENT)
        text(d, (350, y), m, font(36), TXT)
        y+=90
    rrect(d, [W//2-360, 800, W//2+360, 806], 3, fill=ACCENT)
    text(d, (W//2, 880), "HEIMDALL  ·  Fraud Intelligence Platform", font(40, "b"), ACCENT_SOFT, anchor="mm")
    text(d, (W//2, 940), "Thank you", font(32), SUB, anchor="mm")
    return img

# ----------------------------------------------------------------------------- #
# Timeline — (renderer, caption, duration seconds)
# ----------------------------------------------------------------------------- #
TIMELINE = [
    (scene_title,                      "Welcome to Heimdall — a real-time fraud intelligence platform for the Nordics and Baltics.", 18),
    (scene_exec_overview,              "4.2 billion transactions a year, fraud losses down 41%, false declines down to 1.1%, scored in 18 milliseconds.", 34),
    (scene_architecture,               "A payment is ingested, scored in-process with ONNX, a PSD2 decision is made, fraud rings investigated, and EBA reports auto-filed.", 34),
    (scene_switch_live,                "Let's switch to the live production environment running in Azure Container Apps.", 18),
    (scene_swagger_intro,              "This is our real-time fraud scoring engine — one REST call per transaction.", 26),
    (lambda: scene_api_request("legit"),     "First, a legitimate €24.90 grocery order from a known Swedish customer.", 24),
    (lambda: scene_api_response("legit"),     "Approved frictionlessly via the PSD2 low-value exemption — low score, explainable reason codes.", 28),
    (lambda: scene_api_request("suspicious"), "Now a suspicious €5,200 cross-border order from a brand-new device.", 24),
    (lambda: scene_api_response("suspicious"),"Every decision returns in well under 18 milliseconds with SHAP-derived reason codes.", 28),
    (scene_console_intro,              "The demo console shows the full decision spectrum — a calibrated probability, not just yes or no.", 24),
    (lambda: scene_spectrum("APPROVE", "Approve — frictionless, exemption applied"), "Genuine low-risk payments are approved frictionlessly under PSD2 exemptions.", 30),
    (lambda: scene_spectrum("SCA", "SCA step-up — challenge, not block"), "Borderline payments are stepped up to Strong Customer Authentication — challenged, never wrongly blocked.", 30),
    (lambda: scene_spectrum("DECLINE", "Decline — hard stop + agentic case"), "Confirmed fraud is declined and an agentic case is opened automatically for analysts.", 30),
    (scene_ops_dashboard,              "On the ops dashboard: live throughput, p99 latency under SLO, fraud caught today — all streaming in.", 34),
    (scene_powerbi,                    "In Power BI: the EBA quarterly report, filterable by instrument, SCA type, channel and country — all pre-computed.", 34),
    (scene_compliance,                 "Full audit and governance — every decision traceable from ingestion to outcome, retained for seven years.", 32),
    (scene_closing,                    "ONNX in-process for 18 ms, GNNs for fraud rings, EU AI Act compliant, and EBA reports with zero manual hours. Thank you.", 32),
]

# ----------------------------------------------------------------------------- #
# Overlay: caption bar + global progress + countdown
# ----------------------------------------------------------------------------- #
def draw_overlay(img, caption, elapsed, total):
    d = ImageDraw.Draw(img)
    # caption bar
    bar_y = H-150
    d.rectangle([0, bar_y, W, H], fill=(8,9,16))
    d.rectangle([0, bar_y, W, bar_y+4], fill=ACCENT)
    f = font(34)
    lines = wrap(d, caption, f, W-220)
    yy = bar_y + 26 + (0 if len(lines)>1 else 14)
    for ln in lines[:2]:
        text(d, (90, yy), ln, f, TXT)
        yy += 44
    # progress bar
    px0, px1 = 90, W-90
    pby = H-22
    d.rounded_rectangle([px0, pby, px1, pby+8], radius=4, fill=(40,44,66))
    frac = elapsed/total
    d.rounded_rectangle([px0, pby, px0+int((px1-px0)*frac), pby+8], radius=4, fill=ACCENT)
    # timer
    def mmss(s):
        return f"{int(s)//60}:{int(s)%60:02d}"
    text(d, (W-90, bar_y+22), f"{mmss(elapsed)} / {mmss(total)}", font(28, "sb"), ACCENT_SOFT, anchor="ra")
    return img

# ----------------------------------------------------------------------------- #
# Render
# ----------------------------------------------------------------------------- #
def main():
    total = sum(d for _,_,d in TIMELINE)
    print(f"Total duration: {total}s ({total/60:.1f} min)")
    # render & cache scene backgrounds
    backgrounds = []
    for i,(fn,cap,dur) in enumerate(TIMELINE):
        print(f"  rendering scene {i+1}/{len(TIMELINE)} ({dur}s) ...")
        backgrounds.append(fn().convert("RGB"))
    # emit one frame per second
    frame_idx = 0
    elapsed = 0
    for (fn,cap,dur), bg in zip(TIMELINE, backgrounds):
        for _ in range(dur):
            fr = bg.copy()
            draw_overlay(fr, cap, elapsed, total)
            fr.save(os.path.join(FRAMES, f"f{frame_idx:04d}.png"))
            frame_idx += 1
            elapsed += 1
    print(f"Wrote {frame_idx} frames -> {FRAMES}")

if __name__ == "__main__":
    main()
