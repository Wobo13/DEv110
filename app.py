import streamlit as st
import json, os, random, re, hashlib, pandas as pd, secrets
from datetime import datetime, date, timedelta
from io import BytesIO
from PIL import Image
import google.generativeai as genai
import time
import plotly.graph_objects as go

# --- KONFIGURACJA ---
APP_VERSION = "V134"
ADMIN_USER = "wobo"
AUTH_FILE, SESSIONS_FILE = "users_auth.json", "sessions.json"
BONUS_START = 1089.0
API_KEY = st.secrets.get("GEMINI_API_KEY") or st.session_state.get("manual_api_key", "")

# Kolejność modułów do statystyk (identyczna z menu)
MODULE_ORDER = ["Powtórki", "Trening", "Quiz", "Fiszki", "Skaner", "Generator", "Dodaj", "Słownik"]

# --- SYSTEM POMOCNICZY ---
def hash_pw(pw): return hashlib.sha256(str.encode(pw)).hexdigest()
def get_p(u, t): return f"{t}_{u}.json"

def load_j(p, d): 
    if os.path.exists(p):
        try:
            with open(p, "r", encoding="utf-8") as f: return json.load(f)
        except: return d
    return d

def save_j(p, d): 
    with open(p, "w", encoding="utf-8") as f: json.dump(d, f, indent=4)

def play_audio(txt):
    try:
        from gtts import gTTS
        f = BytesIO(); tts = gTTS(text=txt, lang='de'); tts.write_to_fp(f); f.seek(0)
        st.audio(f, format="audio/mp3", autoplay=True)
    except: pass

def parse_ai_json(text):
    try:
        # Wyciąga listę JSON z odpowiedzi, usuwając znaczniki markdown
        match = re.search(r'\[.*\]', text, re.DOTALL)
        if match:
            clean = match.group(0).replace('```json', '').replace('```', '').strip()
            return json.loads(clean)
        return None
    except: return None

# --- LOGOWANIE I AUTO-LOGIN ---
if "auth" not in st.session_state:
    st.session_state.auth = False
    if "token" in st.query_params:
        ss = load_j(SESSIONS_FILE, {})
        tk = st.query_params["token"]
        if tk in ss:
            st.session_state.auth, st.session_state.user = True, ss[tk]

if not st.session_state.auth:
    st.title("🚀 Niemiecki Master")
    t1, t2 = st.tabs(["🔐 Logowanie", "📝 Rejestracja"])
    with t1:
        u_in = st.text_input("Użytkownik", key="l_u").lower().strip()
        p_in = st.text_input("Hasło", type="password", key="l_p")
        rem = st.checkbox("Zapamiętaj mnie", value=True)
        if st.button("Zaloguj się", use_container_width=True, type="primary"):
            db = load_j(AUTH_FILE, {})
            if u_in in db and db[u_in] == hash_pw(p_in):
                st.session_state.auth, st.session_state.user = True, u_in
                if rem:
                    tk = secrets.token_hex(16); sessions = load_j(SESSIONS_FILE, {}); sessions[tk] = u_in
                    save_j(SESSIONS_FILE, sessions); st.query_params["token"] = tk
                st.rerun()
            else: st.error("Błędne dane")
    with t2:
        u_n = st.text_input("Nowy użytkownik", key="r_u").lower().strip()
        p_n = st.text_input("Hasło", type="password", key="r_p")
        if st.button("Załóż konto", use_container_width=True):
            db = load_j(AUTH_FILE, {})
            if u_n and len(p_n) >= 4 and u_n not in db:
                db[u_n] = hash_pw(p_n); save_j(AUTH_FILE, db)
                save_j(get_p(u_n, "flashcards"), [])
                save_j(get_p(u_n, "user_data"), {"streak":0, "historical_cost": 0.0, "time_stats": {}, "last_seen": "Nigdy"})
                st.success("Konto utworzone! Możesz się zalogować.")
    st.stop()

# --- INICJALIZACJA DANYCH UŻYTKOWNIKA ---
u = st.session_state.user
if "flashcards" not in st.session_state: st.session_state.flashcards = load_j(get_p(u, "flashcards"), [])
if "user_data" not in st.session_state: 
    d = load_j(get_p(u, "user_data"), {})
    for k,v in {"streak":0, "historical_cost":0.0, "time_stats":{}, "last_ts": time.time(), "last_seen": "Nigdy"}.items():
        if k not in d: d[k] = v
    st.session_state.user_data = d

def update_activity(m="Inne"):
    curr = time.time()
    delta = curr - st.session_state.user_data.get("last_ts", curr)
    if 0 < delta < 600:
        stats = st.session_state.user_data.get("time_stats", {})
        m_clean = m.strip("📅 🚀 🕹️ 🎴 📸 📦 ➕ 📖 📊 ⚙️ ")
        stats[m_clean] = stats.get(m_clean, 0) + delta
        st.session_state.user_data["time_stats"] = stats
    st.session_state.user_data["last_ts"] = curr
    st.session_state.user_data["last_seen"] = datetime.now().strftime("%d.%m %H:%M:%S")
    save_j(get_p(u, "user_data"), st.session_state.user_data)

today_dt = date.today()
update_activity()

# --- MENU BOCZNE ---
st.sidebar.title(f"👤 {u.capitalize()}")
st.sidebar.caption(f"🚀 Wersja: {APP_VERSION}")
st.sidebar.info(f"🔥 Passa: **{st.session_state.user_data.get('streak', 0)} dni**")
if st.sidebar.button("Wyloguj", use_container_width=True):
    st.query_params.clear(); st.session_state.clear(); st.rerun()

menu = ["📅 Powtórki", "🚀 Trening", "🕹️ Quiz", "🎴 Fiszki", "📸 Skaner AI", "📦 Generator słów", "➕ Dodaj", "📖 Słownik", "📊 Statystyki", "⚙️ Moje Konto"]
if u == ADMIN_USER: menu.append("👑 Admin")
choice = st.sidebar.radio("Nawigacja", menu)

# Czyszczenie stanów przy zmianie modułu
if "l_c" not in st.session_state: st.session_state.l_c = choice
if st.session_state.l_c != choice:
    for k in ["n_c", "n_m", "q_c", "q_s", "f_idx", "f_flipped", "u_a", "del_msg", "pending"]:
        if k in st.session_state: del st.session_state[k]
    st.session_state.l_c = choice

def is_correct(a, c): return a.strip().lower() in [s.strip().lower() for s in re.split(r'[/,;]', c)]

# --- 📅 POWTÓRKI / 🚀 TRENING ---
if choice in ["📅 Powtórki", "🚀 Trening"]:
    is_r = (choice == "📅 Powtórki")
    update_activity("Powtórki" if is_r else "Trening")
    kats = ["Wszystkie"] + sorted(list(set([c.get("category","Inne") for c in st.session_state.flashcards])))
    sel_kat = st.selectbox("🎯 Kategoria:", kats)
    all_c = [c for c in st.session_state.flashcards if sel_kat == "Wszystkie" or c.get("category") == sel_kat]
    cards = [c for c in all_c if not is_r or c.get("next_review", str(today_dt)) <= str(today_dt)]
    
    st.info(f"Słówek: **{len(cards)}**")
    if not cards: st.success("Czysto! 🎉")
    else:
        if "n_c" not in st.session_state: st.session_state.n_c = random.choice(cards); st.session_state.n_m = "ask"
        c = st.session_state.n_c
        st.write(f"### Słówko: **{c['de']}**")
        if st.session_state.n_m == "ask":
            with st.form("ans_form"):
                ua = st.text_input("Odpowiedź:")
                if st.form_submit_button("Sprawdź", use_container_width=True):
                    st.session_state.u_a = ua; st.session_state.n_m = "res"; st.rerun()
        else:
            ans = st.session_state.get("u_a", "")
            if is_correct(ans, c['pl']): st.success(f"✅ Dobrze: {c['pl']}")
            else: st.error(f"❌ Poprawnie: {c['pl']}")
            if c.get("examples"):
                for ex in c["examples"]: st.markdown(f"🇩🇪 {ex['de']}<br>🇵🇱 {ex['pl']}", unsafe_allow_html=True); st.write("")
            play_audio(f"{c['de']} . . " + " . . ".join([e['de'] for e in c.get('examples', [])]))
            if is_r:
                st.write("---")
                c1, c2, c3 = st.columns(3)
                if c1.button("🔴 Słabo (1d)", use_container_width=True):
                    c["next_review"] = str(today_dt + timedelta(days=1)); del st.session_state.n_c; st.rerun()
                if c2.button("🟡 Średnio (3d)", use_container_width=True):
                    c["next_review"] = str(today_dt + timedelta(days=3)); del st.session_state.n_c; st.rerun()
                if c3.button("🟢 Dobrze (7d)", use_container_width=True):
                    c["next_review"] = str(today_dt + timedelta(days=7)); del st.session_state.n_c; st.rerun()
            else:
                if st.button("Następne ➡️", use_container_width=True): del st.session_state.n_c; st.rerun()

# --- 🎴 FISZKI ---
elif choice == "🎴 Fiszki":
    update_activity("Fiszki")
    kats = ["Wszystkie"] + sorted(list(set([c.get("category","Inne") for c in st.session_state.flashcards])))
    sel_kat = st.selectbox("🎯 Kategoria:", kats)
    cards = [c for c in st.session_state.flashcards if sel_kat == "Wszystkie" or c.get("category") == sel_kat]
    if cards:
        if "f_idx" not in st.session_state: st.session_state.f_idx = 0
        if "f_flipped" not in st.session_state: st.session_state.f_flipped = False
        c = cards[st.session_state.f_idx % len(cards)]
        word_txt = c["pl"] if st.session_state.f_flipped else c["de"]
        ex_html = ""
        if st.session_state.f_flipped and c.get("examples"):
            for ex in c["examples"]:
                ex_html += f"<div style='margin-top:15px; border-top:1px solid #444; padding-top:10px;'><span style='color:#FFEB3B; font-weight:bold;'>🇩🇪 {ex['de']}</span><br><span style='color:white; font-style:italic;'>🇵🇱 {ex['pl']}</span></div>"
        st.markdown(f'<div style="min-height:350px; display:flex; flex-direction:column; align-items:center; justify-content:center; background:black; border:2px solid #FF5252; border-radius:30px; padding:30px; text-align:center;"><h1 style="color:white; margin:0; font-size:2.2em;">{word_txt}</h1>{ex_html}</div>', unsafe_allow_html=True)
        st.write("<br>", unsafe_allow_html=True)
        c1, c2, c3 = st.columns([1, 1.2, 1])
        if c1.button("⬅️ Wstecz", use_container_width=True): st.session_state.f_idx -= 1; st.session_state.f_flipped = False; st.rerun()
        if c2.button("🔄 OBRÓĆ", type="primary", use_container_width=True): st.session_state.f_flipped = not st.session_state.f_flipped; st.rerun()
        if c3.button("Dalej ➡️", use_container_width=True): st.session_state.f_idx += 1; st.session_state.f_flipped = False; st.rerun()
        if st.session_state.f_flipped: play_audio(f"{c['de']} . . " + " . . ".join([e['de'] for e in c.get('examples', [])]))

# --- 📸 SKANER AI (Gemini 1.5 Pro) ---
elif choice == "📸 Skaner AI":
    update_activity("Skaner"); src = st.camera_input("Foto"); up = st.file_uploader("Wgraj plik")
    if (src or up) and st.button("🚀 ANALIZUJ", use_container_width=True):
        try:
            genai.configure(api_key=API_KEY); m = genai.GenerativeModel('gemini-1.5-pro')
            res = m.generate_content(["Extract German-Polish vocabulary. Return ONLY JSON list: [{'de':'...', 'pl':'...', 'category':'Skaner', 'examples':[{'de':'...', 'pl':'...'}]}]", Image.open(src or up).convert("RGB")])
            data = parse_ai_json(res.text)
            if data: st.session_state.pending = data; st.session_state.user_data["historical_cost"] += 0.015; st.rerun()
            else: st.error("AI nie zwróciło poprawnego formatu.")
        except: st.error("Błąd połączenia z AI Pro.")
    if "pending" in st.session_state:
        ed = st.data_editor(pd.DataFrame(st.session_state.pending), use_container_width=True)
        if st.button("✅ ZAPISZ", use_container_width=True):
            for w in ed.to_dict('records'):
                w.update({"next_review": str(today_dt), "date_added": str(today_dt), "category": w.get("category", "Skaner")})
                st.session_state.flashcards.append(w)
            save_j(get_p(u, "flashcards"), st.session_state.flashcards); del st.session_state.pending; st.rerun()

# --- 📦 GENERATOR SŁÓW (Gemini 1.5 Pro) ---
elif choice == "📦 Generator słów":
    update_activity("Generator"); cols = st.columns(5); lvls = ["A1", "A2", "B1", "B2", "C1"]
    for i, lvl in enumerate(lvls):
        if cols[i].button(lvl, use_container_width=True):
            with st.spinner("Generowanie Pro..."):
                try:
                    genai.configure(api_key=API_KEY); m = genai.GenerativeModel('gemini-1.5-pro')
                    exist = [x['de'] for x in st.session_state.flashcards[:300]]
                    p = f"Generate 25 unique German words for level {lvl}. Polish categories/examples. Skip: {exist}. JSON: [{{'de':'...', 'pl':'...', 'category':'...', 'examples':[{{'de':'...', 'pl':'...'}}]}}]"
                    res = m.generate_content(p); data = parse_ai_json(res.text)
                    if data:
                        added = 0
                        for w in data:
                            if w['de'].lower() not in [x['de'].lower() for x in st.session_state.flashcards]:
                                w.update({"next_review": str(today_dt), "date_added": str(today_dt), "category": f"{lvl} - {w.get('category','Inne')}"})
                                st.session_state.flashcards.append(w); added += 1
                        st.session_state.user_data["historical_cost"] += 0.01; save_j(get_p(u, "flashcards"), st.session_state.flashcards); st.rerun()
                except: st.error("Błąd generatora.")

# --- 🕹️ QUIZ ---
elif choice == "🕹️ Quiz":
    update_activity("Quiz"); all_c = st.session_state.flashcards
    if len(all_c) < 4: st.warning("Dodaj min. 4 słówka!")
    else:
        if "q_c" not in st.session_state:
            t = random.choice(all_c); opts = random.sample([x['pl'] for x in all_c if x['pl']!=t['pl']], 3) + [t['pl']]
            random.shuffle(opts); st.session_state.update({"q_c":t,"q_a":t['pl'],"q_o":opts,"q_s":"ask"})
        st.write(f"### Jak przetłumaczysz: **{st.session_state.q_c['de']}**")
        if st.session_state.q_s == "ask":
            for o in st.session_state.q_o:
                if st.button(o, use_container_width=True): st.session_state.u_q, st.session_state.q_s = o, "res"; st.rerun()
        else:
            if st.session_state.get("u_q") == st.session_state.q_a: st.success("✅ Brawo!")
            else: st.error(f"Poprawnie: {st.session_state.q_a}")
            play_audio(f"{st.session_state.q_c['de']} . . " + " . . ".join([e['de'] for e in st.session_state.q_c.get('examples', [])]))
            if st.button("Dalej", use_container_width=True): del st.session_state.q_c; st.rerun()

# --- ➕ DODAJ ---
elif choice == "➕ Dodaj":
    st.header("Dodaj ręcznie")
    with st.form("manual"):
        de, pl, kat = st.text_input("Niemiecki"), st.text_input("Polski"), st.text_input("Kategoria")
        if st.form_submit_button("Zapisz", use_container_width=True):
            if de and pl:
                st.session_state.flashcards.append({"de":de,"pl":pl,"category":kat or "Inne","next_review":str(today_dt),"date_added":str(today_dt),"examples":[]})
                save_j(get_p(u,"flashcards"), st.session_state.flashcards); st.success("Dodano!")

# --- 📖 SŁOWNIK ---
elif choice == "📖 Słownik":
    update_activity("Słownik"); kats = ["Wszystkie"] + sorted(list(set([c.get("category","Inne") for c in st.session_state.flashcards])))
    f_kat = st.selectbox("📁 Kategoria:", kats); search = st.text_input("🔍 Szukaj:")
    for i, c in enumerate(st.session_state.flashcards):
        if (f_kat == "Wszystkie" or c.get("category") == f_kat) and (search.lower() in c['de'].lower() or search.lower() in c['pl'].lower()):
            with st.expander(f"📝 {c['de']} — {c['pl']}"):
                with st.form(f"ed_{i}"):
                    n_de, n_pl, n_ka = st.text_input("DE", c['de']), st.text_input("PL", c['pl']), st.text_input("Kat", c.get('category','Inne'))
                    if st.form_submit_button("Zapisz", use_container_width=True):
                        c.update({"de":n_de,"pl":n_pl,"category":n_ka}); save_j(get_p(u,"flashcards"), st.session_state.flashcards); st.rerun()
                    if st.form_submit_button("Usuń", use_container_width=True):
                        st.session_state.flashcards.pop(i); save_j(get_p(u,"flashcards"), st.session_state.flashcards); st.rerun()

# --- 📊 STATYSTYKI ---
elif choice == "📊 Statystyki":
    update_activity("Statystyki"); df = pd.DataFrame(st.session_state.flashcards)
    if not df.empty:
        c1, c2, c3 = st.columns(3); c1.metric("Słówek", len(df)); c2.metric("Passa", f"{st.session_state.user_data.get('streak', 0)} dni")
        def ck(x):
            try: return "Opanowane" if (date.fromisoformat(x)-today_dt).days >= 7 else "W trakcie"
            except: return "W trakcie"
        df['status'] = df['next_review'].apply(ck); c3.metric("Opanowane", len(df[df['status']=="Opanowane"]))
        st.bar_chart(pd.DataFrame([{"D": (today_dt + timedelta(days=i)).strftime("%d.%m"), "S": len(df[df['next_review']==str(today_dt + timedelta(days=i))])} for i in range(14)]).set_index("D"))

# --- ⚙️ MOJE KONTO ---
elif choice == "⚙️ Moje Konto":
    st.header("Konto"); update_activity("Konto")
    if "del_msg" in st.session_state: st.success(st.session_state.del_msg); del st.session_state.del_msg
    with st.expander("🔑 Zmień hasło"):
        with st.form("p_c"):
            o, n1, n2 = st.text_input("Stare", type="password"), st.text_input("Nowe", type="password"), st.text_input("Powtórz", type="password")
            if st.form_submit_button("Zmień"):
                db = load_j(AUTH_FILE, {}); (db.update({u: hash_pw(n1)}) if db[u] == hash_pw(o) and n1 == n2 else st.error("Błąd")); save_j(AUTH_FILE, db); st.success("OK")
    st.divider(); st.subheader("⚠️ Usuń"); conf = st.checkbox("Tak, chcę usunąć")
    lvls = ["A1", "A2", "B1", "B2", "C1"]; cols = st.columns(5)
    for i, l in enumerate(lvls):
        if cols[i].button(l, disabled=not conf, use_container_width=True):
            before = len(st.session_state.flashcards); st.session_state.flashcards = [x for x in st.session_state.flashcards if l not in str(x.get('category',''))]
            save_j(get_p(u, "flashcards"), st.session_state.flashcards); st.session_state.del_msg = f"Usunięto {before - len(st.session_state.flashcards)}!"; st.rerun()

# --- 👑 ADMIN ---
elif choice == "👑 Admin":
    st.header("👑 Admin Master"); users = load_j(AUTH_FILE, {}); adm_data = []; global_time = {m: 0.0 for m in MODULE_ORDER}
    m1, m2 = st.columns(2)
    for usr in users:
        ud = load_j(get_p(usr, "user_data"), {}); ub = load_j(get_p(usr, "flashcards"), [])
        df_u = pd.DataFrame(ub); mastery, ai_n = "0%", 0
        if not df_u.empty:
            opanowane = ((pd.to_datetime(df_u['next_review']).dt.date - today_dt).apply(lambda x: x.days if pd.notnull(x) else 0) >= 7).sum()
            mastery = f"{round((opanowane/len(df_u))*100)}%"; ai_n = len(df_u[df_u['category'].str.contains('Skaner', case=False, na=False)])
        t_s = ud.get("time_stats", {})
        for m in MODULE_ORDER: global_time[m] += t_s.get(m, 0.0)
        adm_data.append({"Użytkownik": usr, "Słów": len(ub), "AI": ai_n, "%": mastery, "Ostatnio": ud.get("last_seen", "Nigdy")})
    m1.metric("Baza Słów", sum(x['Słów'] for x in adm_data))
    m2.metric("Bonus AI", f"{BONUS_START - sum(load_j(get_p(un, 'user_data'), {}).get('historical_cost', 0) for un in users):.2f} PLN")
    st.dataframe(pd.DataFrame(adm_data), use_container_width=True)
    total_g = sum(global_time.values())
    if total_g > 0:
        vals = [global_time[m] for m in MODULE_ORDER]; labels = [f"{m}: {round(v/60,1)} min" for m, v in zip(MODULE_ORDER, vals)]
        fig = go.Figure(data=[go.Bar(x=MODULE_ORDER, y=vals, text=labels, textposition='auto', marker_color='#1E88E5')])
        fig.update_layout(template="plotly_dark", height=400); st.plotly_chart(fig, use_container_width=True)
