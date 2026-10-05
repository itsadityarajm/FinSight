"""FinSight AI — Streamlit edition. Run: streamlit run app.py"""
from __future__ import annotations
import copy, hashlib, html, json, os
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import engine as E
import gemini_client as GC
from engine import NA, FIELDS, LABELS, fmt, pct, money, nv, calc, growth
from report import build_report

st.set_page_config(page_title="FinSight AI", page_icon="📊", layout="wide")
ss = st.session_state
PAGES = ["Overview", "Financials", "Ratios & Trends", "AI Analysis", "AI Auditor", "Documents"]
PAL = ["#53b7ff", "#35d39a", "#f4bd4f", "#ff6b7a", "#9a8cff", "#ff9f5a"]
esc = html.escape

CSS = """<style>
.card{background:#0f2238;border:1px solid #1e3a57;border-radius:14px;padding:14px 16px;height:100%}
.kl{font-size:11px;color:#8aa4be;text-transform:uppercase;letter-spacing:.6px}.kv{font-size:24px;font-weight:700;margin:4px 0}
.up{color:#35d39a}.down{color:#ff6b7a}.na{color:#6f879f;font-style:italic;font-size:12px}
.pill{display:inline-block;font-size:10px;font-weight:800;padding:3px 9px;border-radius:99px;letter-spacing:.5px}
.p-ok{background:#12372d;color:#65e0b1}.p-watch{background:#3b2f10;color:#f4bd4f}.p-risk{background:#40181f;color:#ff8d9a}.p-info,.p-na{background:#1a2e44;color:#8fc4f0}.p-calc{background:#1b2c52;color:#9db8ff}
.fx{background:#0a1929;border:1px solid #1e3a57;border-left:4px solid #3c7bab;border-radius:11px;padding:12px 14px;margin:9px 0}
.fx.ok{border-left-color:#35d39a}.fx.watch{border-left-color:#f4bd4f}.fx.risk{border-left-color:#ff6b7a}.fx.na{border-left-color:#5a6f86}
.fh{display:flex;justify-content:space-between;align-items:center;font-weight:700}.fb{font-size:13px;color:#b8cbe0;line-height:1.65;margin-top:6px}.fb b{color:#fff}
.conf{height:7px;background:#0d2238;border-radius:5px;margin-top:9px;overflow:hidden}.conf span{display:block;height:100%;background:linear-gradient(90deg,#1f79b8,#35d39a)}
.hero{padding:20px 22px;border-radius:16px;border:1px solid #2e5a86;background:linear-gradient(135deg,#12365a,#241f5e 70%,#0d1b2e);margin-bottom:14px}
.hero h2{margin:6px 0 4px}.hero p{margin:0;color:#b6c9de;font-size:13px}
.aic{background:#0b1b2e;border:1px solid #1e3a57;border-left:4px solid #3c7bab;border-radius:12px;padding:13px;margin-bottom:12px}
.aic ul{margin:8px 0 0;padding-left:18px;font-size:13px;color:#c1d3e6;line-height:1.6}
.k-fact{border-left-color:#35d39a}.k-calculation{border-left-color:#7a8cff}.k-inference{border-left-color:#f4bd4f}.k-risk{border-left-color:#ff6b7a}.k-verify{border-left-color:#53b7ff}
</style>"""
st.markdown(CSS, unsafe_allow_html=True)


# ------------------------------------------------------------------ state
def reset_state(keep_demo=False):
    ss.data = copy.deepcopy(E.DEMO) if keep_demo else []
    ss.company = "Trivani Consumer Products Ltd." if keep_demo else "No company loaded"
    ss.symbol = ""
    ss.analysis = ss.audit_ai = ss.notice = None
    ss.question = ""
    ss.dead = set()
    ss.gen = ss.get("gen", 0) + 1  # new keys → file uploaders cleared


if "data" not in ss:
    reset_state(keep_demo=True)
    ss.setdefault("cache", {})
if "_goto" in ss:
    ss.page = ss.pop("_goto")


def api_key():
    k = ss.get("user_key", "").strip()
    if k:
        return k
    try:
        return st.secrets.get("GEMINI_API_KEY", "") or os.environ.get("GEMINI_API_KEY", "")
    except Exception:
        return os.environ.get("GEMINI_API_KEY", "")


def need_data():
    if not ss.data:
        st.info("No data loaded. Open **Documents** to import a Screener Excel or an annual report, or load the demo from the sidebar.")
        return True
    return False


def status_cb(slot):
    return lambda m: slot.info(f"Analyzing with **{m}** …")


# ------------------------------------------------------------------ sidebar
with st.sidebar:
    st.markdown("## 📊 FinSight **AI**")
    st.radio("Navigate", PAGES, key="page", label_visibility="collapsed")
    st.divider()
    st.text_input("Gemini API key", type="password", key="user_key", help="Optional if GEMINI_API_KEY is set in Streamlit secrets. Kept only in this session.")
    st.caption("✅ API key set" if api_key() else "⚠️ No API key (Screener import and rule-based checks still work)")
    c1, c2 = st.columns(2)
    if c1.button("Load demo", width="stretch"):
        reset_state(True); st.rerun()
    if c2.button("Reset", width="stretch"):
        reset_state(False); st.rerun()
    st.caption("Calculations are deterministic; Gemini only interprets.")

# ------------------------------------------------------------------ pages
def kpi(label, val, chg=None, pp=False, prev_year=""):
    v = f'<span class="na">{NA}</span>' if val is None else val
    c = (f'<div class="na">vs {prev_year}: {NA}</div>' if chg is None else
         f'<div class="{"up" if chg >= 0 else "down"}">{"▲" if chg >= 0 else "▼"} {fmt(abs(chg))}{" pp" if pp else "%"} vs {prev_year}</div>')
    return f'<div class="card"><div class="kl">{label}</div><div class="kv">{v}</div>{c}</div>'


def style_fig(fig, h=330, unit=None):
    fig.update_layout(height=h, margin=dict(l=10, r=10, t=30, b=10), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      legend=dict(orientation="h", y=1.12), font=dict(color="#c1d3e6"), colorway=PAL)
    fig.update_yaxes(gridcolor="#1e3a57", title=unit)
    return fig


def page_overview():
    st.title("Overview")
    if need_data():
        return
    d = ss.data
    L, P = calc(d[-1]), calc(d[-2] if len(d) > 1 else d[-1])
    st.caption(f"{ss.company}{' · ' + ss.symbol if ss.symbol else ''} · {d[0]['year']}–{d[-1]['year']}")
    cols = st.columns(4)
    items = [("Revenue", money(L["revenue"]) if nv(L["revenue"]) is not None else None, growth(P["revenue"], L["revenue"]), False),
             ("EBITDA", money(L["ebitda"]) if nv(L["ebitda"]) is not None else None, growth(P["ebitda"], L["ebitda"]), False),
             ("EBITDA Margin", pct(L["ebitdaMargin"]) if nv(L["ebitdaMargin"]) is not None else None, E.sub(L["ebitdaMargin"], P["ebitdaMargin"]), True),
             ("PAT", money(L["pat"]) if nv(L["pat"]) is not None else None, growth(P["pat"], L["pat"]), False)]
    for c, (a, b, ch, pp) in zip(cols, items):
        c.markdown(kpi(a, b, ch, pp, P["year"]), unsafe_allow_html=True)
    st.write("")
    gr, ge = growth(P["revenue"], L["revenue"]), growth(P["ebitda"], L["ebitda"])
    take = f"Revenue trend: {NA}." if gr is None else f"Revenue moved **{pct(gr)}**" + (f" while EBITDA moved **{pct(ge)}**." if ge is not None else f"; EBITDA growth: {NA}.")
    flags = []
    if nv(L["debtEquity"]) is not None and L["debtEquity"] > .8: flags.append(f"🔴 Debt/equity is {fmt(L['debtEquity'], 2)}x")
    if nv(L["currentRatio"]) is not None and L["currentRatio"] < 1.2: flags.append(f"🟠 Current ratio is {fmt(L['currentRatio'], 2)}x")
    if nv(L["fcf"]) is not None and L["fcf"] < 0: flags.append("🔴 Free cash flow is negative")
    a, b, c = st.columns(3)
    a.markdown(f'<div class="card"><div class="kl">Key takeaway</div><p>{take}</p></div>', unsafe_allow_html=True)
    b.markdown('<div class="card"><div class="kl">Risk flags</div><p>' + ("<br>".join(flags) or "No automatic flags (only checked where data exists).") + "</p></div>", unsafe_allow_html=True)
    have = sum(nv(d[-1].get(k)) is not None for k in FIELDS)
    c.markdown(f'<div class="card"><div class="kl">Data quality</div><p><b>{len(d)} periods</b> loaded · <b>{have}/{len(FIELDS)}</b> fields available for {d[-1]["year"]}. Missing fields are never treated as zero.</p></div>', unsafe_allow_html=True)
    yrs = [r["year"] for r in d]
    rows = [calc(r) for r in d]
    c1, c2 = st.columns(2)
    f = go.Figure([go.Bar(name=n, x=yrs, y=[nv(r[k]) for r in rows]) for n, k in (("Revenue", "revenue"), ("EBITDA", "ebitda"), ("PAT", "pat"))])
    c1.plotly_chart(style_fig(f, unit="₹ Cr"), width="stretch")
    f = go.Figure([go.Scatter(name=n, x=yrs, y=[nv(r[k]) for r in rows], mode="lines+markers", connectgaps=True) for n, k in (("EBITDA margin %", "ebitdaMargin"), ("PAT margin %", "patMargin"), ("ROE %", "roe"))])
    c2.plotly_chart(style_fig(f, unit="%"), width="stretch")


def page_financials():
    st.title("Financials")
    if need_data():
        return
    df = pd.DataFrame({LABELS[k]: [money(r[k]) for r in ss.data] for k in FIELDS}, index=[r["year"] for r in ss.data]).T
    st.dataframe(df, width="stretch", height=min(800, 38 * (len(FIELDS) + 1)))
    raw = pd.DataFrame(ss.data)[["year"] + FIELDS]
    st.download_button("⬇ Download CSV", raw.to_csv(index=False), "finsight-financials.csv", "text/csv")


def page_ratios():
    st.title("Ratios & Trends")
    if need_data():
        return
    st.caption('28 ratios across 7 groups. Anything the documents do not support shows "Data not available".')
    if st.button("📄 Generate report (HTML → print to PDF)"):
        with st.spinner("Building report with charts …"):
            ss.report = build_report(ss.company, ss.symbol, ss.data)
    if ss.get("report"):
        st.download_button("⬇ Download report", ss.report, f"{ss.company.replace(' ', '_')}_report.html", "text/html")
        st.caption("Open the downloaded file in a browser → Ctrl+P → Save as PDF.")
    for title, ids in E.GROUPS:
        ok = E.computable(ids, ss.data)
        with st.expander(f"{title}   ·   {ok}/{len(ids)} computable", expanded=ok > 0):
            st.dataframe(E.ratio_table(ids, ss.data), width="stretch", hide_index=True)
            s = E.group_series(ids, ss.data)
            if s:
                fig = go.Figure([go.Scatter(name=n, x=s["labels"], y=v, mode="lines+markers", connectgaps=True) if len(s["labels"]) > 1
                                 else go.Bar(name=n, x=s["labels"], y=v) for n, v in s["series"]])
                st.plotly_chart(style_fig(fig, 300, {"%": "Percent", "days": "Days"}.get(s["unit"], "Times (x)")), width="stretch", key=f"rg_{title}")


KIND = {"fact": ("FACT", "ok"), "calculation": ("CALC", "calc"), "inference": ("INFERENCE", "watch"), "risk": ("RISK", "risk"), "verify": ("VERIFY", "info")}
SEV = {"ok": "PASS", "info": "INFO", "watch": "WATCH", "risk": "RISK", "na": "DATA N/A"}


def fx_card(title, sev, rows, conf=None):
    body = "".join(f"<div><b>{a}</b> {esc(str(b))}</div>" for a, b in rows if b)
    cb = f'<div class="conf"><span style="width:{max(0, min(100, conf))}%"></span></div><small>Confidence {round(conf)}%</small>' if nv(conf) is not None else ""
    return f'<div class="fx {sev}"><div class="fh"><span>{esc(title)}</span><span class="pill p-{sev}">{SEV.get(sev, "INFO")}</span></div><div class="fb">{body}</div>{cb}</div>'


def page_analysis():
    st.markdown('<div class="hero"><span class="pill p-calc">✦ GEMINI</span><h2>AI Financial Analyst</h2><p>Structured answers: facts, calculations, inferences, risks and what to verify.</p></div>', unsafe_allow_html=True)
    if need_data():
        return
    L, P = calc(ss.data[-1]), calc(ss.data[-2] if len(ss.data) > 1 else ss.data[-1])
    snap = [("Revenue growth", pct(growth(P["revenue"], L["revenue"]))), ("EBITDA margin", pct(L["ebitdaMargin"])), ("PAT margin", pct(L["patMargin"])),
            ("ROE", pct(L["roe"])), ("Debt / Equity", "N/A" if nv(L["debtEquity"]) is None else f"{fmt(L['debtEquity'], 2)}x"), ("Free cash flow", money(L["fcf"]))]
    for c, (a, b) in zip(st.columns(6), snap):
        c.metric(a, NA if b in ("N/A", NA) else b)
    left, right = st.columns([.8, 1.2])
    with left:
        for lab, q in (("Margin drivers", "Why did EBITDA margin change in the latest year?"), ("Key risks", "What are the key financial risks and what should management verify?"),
                       ("Financial health", "Is the company financially healthy? Assess liquidity, leverage and cash flow."), ("Return trends", "Explain profitability and return trends across all years.")):
            if st.button(lab, key="q_" + lab):
                ss.question = q
        st.text_area("Your question", key="question", height=120, placeholder="Why did margins change? What are the main risks?")
        ctx = st.text_area("Additional context (optional)", height=120, placeholder="Paste annual-report excerpts or notes.")
        go_ = st.button("✦ Analyze with Gemini", type="primary")
    with right:
        slot = st.empty()
        if go_:
            if not ss.question.strip():
                slot.warning("Enter a question first.")
            else:
                prompt = (f"Question: {ss.question}\nCompany: {ss.company}\nStructured data (₹ Cr; null = NOT available, never treat as zero): {json.dumps([calc(r) for r in ss.data], default=str)}\n"
                          f"Additional evidence: {ctx[:60000] or '(none)'}\nUse ONLY this data. Return JSON: headline, stance (positive|mixed|negative|insufficient_data), summary (2-3 sentences), "
                          "sections (4-6; kind = fact|calculation|inference|risk|verify; 2-4 short points each, with numbers), follow_ups (3 short questions). Say 'Data not available' where a figure is null.")
                arr = {"type": "array", "items": GC.S}
                schema = {"type": "object", "properties": {"headline": GC.S, "stance": GC.S, "summary": GC.S, "sections": {"type": "array", "items": {"type": "object", "properties": {"title": GC.S, "kind": GC.S, "points": arr}, "required": ["title", "kind", "points"]}}, "follow_ups": arr},
                          "required": ["headline", "stance", "summary", "sections", "follow_ups"]}
                try:
                    ss.analysis = GC.run_json(prompt, schema, api_key(), ss.dead, "You are a rigorous financial analyst. Never fabricate evidence. Distinguish fact from inference. Return only JSON.", status_cb(slot))
                except GC.GeminiError as e:
                    ss.analysis = None
                    slot.error(str(e))
        if ss.analysis:
            o, model = ss.analysis
            sp = {"positive": ("Positive", "ok"), "mixed": ("Mixed", "watch"), "negative": ("Negative", "risk")}.get(str(o.get("stance", "")).lower(), ("Insufficient data", "info"))
            h = f'<div class="aic" style="border-left-color:#53b7ff"><span class="pill p-{sp[1]}">{sp[0]}</span> <small style="float:right">{esc(model)}</small><h3>{esc(o.get("headline", ""))}</h3><p>{esc(o.get("summary", ""))}</p></div>'
            for s in o.get("sections", []):
                k = KIND.get(s.get("kind"), KIND["fact"])
                h += f'<div class="aic k-{s.get("kind", "fact")}"><div class="fh"><span>{esc(s.get("title", ""))}</span><span class="pill p-{k[1]}">{k[0]}</span></div><ul>' + "".join(f"<li>{esc(x)}</li>" for x in s.get("points", [])) + "</ul></div>"
            slot.markdown(h, unsafe_allow_html=True)
            for q in o.get("follow_ups", []):
                st.caption("↳ " + q)
        elif not go_:
            slot.info("Your analysis will appear here.")


def page_auditor():
    st.title("AI Auditor")
    st.caption("Rule-based checks run automatically (no API). The Gemini audit is an optional independent review.")
    if need_data():
        return
    chk = E.auto_checks(ss.data)
    for c, k in zip(st.columns(4), ("ok", "watch", "risk", "na")):
        c.metric(SEV[k], sum(1 for x in chk if x[1] == k))
    st.subheader("Automatic checks")
    st.markdown("".join(fx_card(t, s, r) for t, s, r in chk), unsafe_allow_html=True)
    st.subheader("Gemini audit findings")
    slot = st.empty()
    if st.button("Run Gemini Audit", type="primary"):
        S = GC.S
        schema = {"type": "object", "properties": {"scope_note": S, "findings": {"type": "array", "items": {"type": "object", "properties": {k: S for k in ("conclusion", "evidence", "calculation", "assumption", "severity", "human_check")} | {"confidence": {"type": "number"}},
                  "required": ["conclusion", "evidence", "calculation", "assumption", "severity", "confidence", "human_check"]}}}, "required": ["scope_note", "findings"]}
        prompt = (f"Audit the financial data of {ss.company}. Rows (JSON, ₹ Cr): {json.dumps([calc(r) for r in ss.data], default=str)}\n"
                  "IMPORTANT: null means NOT extracted / not available. Never treat null as zero or call it a data error; mention it only as missing data. Do not invent figures or sources.\n"
                  "Return 5-8 findings. severity ∈ ok|info|watch|risk. confidence 0-100. scope_note: one sentence on what was and was not verified.")
        try:
            ss.audit_ai = GC.run_json(prompt, schema, api_key(), ss.dead, "You are an independent, skeptical financial auditor. Return only JSON.", status_cb(slot))
        except GC.GeminiError as e:
            ss.audit_ai = None
            slot.error(str(e))
    if ss.audit_ai:
        o, model = ss.audit_ai
        h = f'<div class="fb">{esc(o.get("scope_note", ""))} <i>({esc(model)})</i></div>'
        for f in o.get("findings", []):
            sev = f.get("severity") if f.get("severity") in ("ok", "info", "watch", "risk") else "info"
            h += fx_card(f.get("conclusion", ""), sev, [("Evidence:", f.get("evidence")), ("Calculation:", f.get("calculation")), ("Assumption:", f.get("assumption")), ("Human check:", f.get("human_check"))], f.get("confidence"))
        slot.markdown(h, unsafe_allow_html=True)
    else:
        slot.info('Click "Run Gemini Audit" for an independent review.')


def page_documents():
    st.title("Document Intake")
    st.caption("Choose either a Screener Excel file (Option A) or an annual-report file (Option B).")
    if ss.notice:
        st.success(ss.notice) if ss.notice[0] != "!" else st.error(ss.notice[1:])
    with st.container(border=True):
        st.subheader("Option A — Screener.in Excel  ·  instant, no API")
        st.caption("Upload the file exported from screener.in (Export to Excel). Read locally — no Gemini quota used.")
        f = st.file_uploader("Screener Excel", type=["xlsx", "xlsm", "xls"], key=f"scr{ss.gen}")
        n = st.selectbox("Years to import", [3, 5, 10], index=1)
        if st.button("Import Screener Excel", type="primary", disabled=f is None):
            try:
                name, rows = E.parse_screener(f, n)
                ss.data, ss.company, ss.symbol = rows, name, ""
                ss.analysis = ss.audit_ai = None; ss.pop("report", None)
                ss.question = f"Provide an initial financial analysis of {name}: revenue, EBITDA, PAT, leverage, cash-flow and profitability trends. Distinguish facts from inference."
                ss.notice = (f"Screener import complete: {name} · {len(rows)} years ({rows[0]['year']}–{rows[-1]['year']}). Not in Screener's Data Sheet "
                             "(shown as 'Data not available'): current assets, current liabilities, payables. Capex is derived from Net Block, CWIP and depreciation changes; EBITDA excludes other income.")
                ss._goto = "Overview"; st.rerun()
            except Exception as e:
                ss.notice = f"!Screener import failed: {e}"; st.rerun()
    with st.container(border=True):
        st.subheader("Option B — Annual report with Gemini")
        st.caption("Upload the annual report as Markdown (.md/.txt) or PDF (text is extracted locally). Optional supporting files add context.")
        ar = st.file_uploader("Annual report (.md, .txt, .pdf)", type=["md", "txt", "pdf"], key=f"ar{ss.gen}")
        sup = st.file_uploader("Credit rating / concall (optional)", type=["md", "txt", "pdf"], accept_multiple_files=True, key=f"sup{ss.gen}")
        if st.button("Proceed & Analyze with Gemini", type="primary", disabled=ar is None):
            def text_of(u):
                return E.pdf_to_markdown(u) if u.name.lower().endswith(".pdf") else u.getvalue().decode("utf-8", "ignore")
            slot = st.empty()
            try:
                with st.spinner("Reading document …"):
                    text = text_of(ar)
                key_ = hashlib.sha256(text.encode()).hexdigest()
                if key_ in ss.cache:
                    ex, model = ss.cache[key_], "cache"
                else:
                    ex, model = GC.run_json(GC.EXTRACT_RULES + E.trim_markdown(text), GC.extraction_schema(FIELDS), api_key(), ss.dead,
                                            "You are a careful financial-document extraction engine. Return only valid JSON.", status_cb(slot))
                    ss.cache[key_] = ex
                per = [p for p in ex.get("periods", []) if p.get("year") and nv(p.get("revenue")) is not None]
                if not per:
                    raise GC.GeminiError("No usable financial periods were extracted. Check that the file contains the financial statements.")
                ss.data = sorted((E.norm_row(p) for p in per), key=lambda r: r["year"])
                ss.company, ss.symbol = ex.get("company_name") or ar.name, ex.get("symbol") or ""
                ss.analysis = ss.audit_ai = None; ss.pop("report", None)
                ss.notice = f"Extraction complete ({model}): {ss.company} · {len(ss.data)} years. " + " ".join(ex.get("extraction_notes", [])[:2])
                slot.empty(); ss._goto = "Overview"; st.rerun()
            except Exception as e:
                slot.error(str(e))


{"Overview": page_overview, "Financials": page_financials, "Ratios & Trends": page_ratios, "AI Analysis": page_analysis,
 "AI Auditor": page_auditor, "Documents": page_documents}[ss.get("page", "Overview")]()
