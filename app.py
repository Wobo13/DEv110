import streamlit as st
import json, os, random, re, hashlib, pandas as pd, secrets
from datetime import datetime, date, timedelta
from io import BytesIO
from PIL import Image
import google.generativeai as genai
import time
import plotly.graph_objects as go

# --- KONFIGURACJA ---
APP_VERSION = "V130"
ADMIN_USER = "wobo"
AUTH_FILE, SESSIONS_FILE = "users_auth.json", "sessions.json"
BONUS_START = 1089.0
API_KEY = st.secrets.get("GEMINI_API_KEY") or st.session_state.get("manual_api_key", "")

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

# --- LOGOWANIE ---
if "auth" not in st.session_state:
    st.session_state.auth = False
    if "token" in st.query_params:
        sessions = load_j(SESSIONS_FILE, {})
        tk = st.query_params["token"]
        if tk in sessions:
            st.session_state.auth, st.session_state.user = True, sessions[tk]

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
                    tk = secrets.token_hex(16); ss = load_j(SESSIONS_FILE, {}); ss[tk] = u_in
                    save_j(SESSIONS_FILE, ss); st.query_params["token"] = tk
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
                save_j(get_p(u_n, "user_data"), {"streak":0, "last_active":str(date.today()-timedelta(days=1)), "historical_cost": 0.0, "time_stats": {}, "last_seen": "Nigdy"})
                st.success("Konto utworzone!")
    st.stop()

# --- INIT DANYCH ---
u = st.session_state.user
if "flashcards" not in st.session_state: st.session_state.flashcards = load_j(get_p(u, "flashcards"), [])
if "user_data" not in st.session_state: 
    d = load_j(get_p(u, "user_data"), {})
    for k,v in {"streak":0, "historical_cost":0.0, "time_stats":{}, "last_ts": time.time()}.items():
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

if "l_c" not in st.session_state: st.session_state.l_c = choice
if st.session_state.l_c != choice:
    for k in ["n_c", "n_m", "q_c", "q_s", "f_idx", "f_flipped", "u_a", "del_msg"]:
        if k in st.session_state: del st.session_state[k]
    st.session_state.l_c = choice

# --- MODUŁY NAUKI ---
if choice in ["📅 Powtórki", "🚀 Trening"]:
    m_name = "Powtórki" if choice == "📅 Powtórki" else "Trening"
    update_activity(m_name)
    kats = ["Wszystkie"] + sorted(list(set([c.get("category","Inne") for c in st.session_state.flashcards])))
    sel_kat = st.selectbox("🎯 Kategoria:", kats)
    all_c = [c for c in st.session_state.flashcards if sel_kat == "Wszystkie" or c.get("category") == sel_kat]
    cards = [c for c in all_c if not (choice == "📅 Powtórki") or c.get("next_review", str(today_dt)) <= str(today_dt)]
    
    st.info(f"Słówek: **{len(cards)}**")
    if not cards: st.success("Wszystko zrobione! 🎉")
    else:
        if "n_c" not in st.session_state: st.session_state.n_c = random.choice(cards); st.session_state.n_m = "ask"
        c = st.session_state.n_c
        st.write(f"### Słówko: **{c['de']}**")
        
        if st.session_state.n_m == "ask":
            with st.form("ans_f"):
                u_a_input = st.text_input("Twoja odpowiedź:")
                if st.form_submit_button("Sprawdź", use_container_width=True):
                    st.session_state.u_a = u_a_input; st.session_state.n_m = "res"; st.rerun()
        else:
            ans = st.session_state.get("u_a", "")
            if ans.strip().lower() in [s.strip().lower() for s in re.split(r'[/,;]', c['pl'])]: st.success(f"✅ Dobrze: {c['pl']}")
            else: st.error(f"❌ Poprawnie: {c['pl']}")
            
            if c.get("examples"):
                for ex in c["examples"]: st.markdown(f"🇩🇪 {ex['de']}<br>🇵🇱 {ex['pl']}", unsafe_allow_html=True); st.write("")
            play_audio(f"{c['de']} . . " + " . . ".join([e['de'] for e in c.get('examples', [])]))
            
            if choice == "📅 Powtórki":
                st.write("---")
                c1, c2, c3 = st.columns(3); d = None
                if c1.button("🔴 Słabo (1d)", use_container_width=True): d = 1
                if c2.button("🟡 Średnio (3d)", use_container_width=True): d = 3
                if c3.button("🟢 Dobrze (7d)", use_container_width=True): d = 7
                if d:
                    if date.fromisoformat(st.session_state.user_data.get("last_active", "2000-01-01")) < today_dt:
                        st.session_state.user_data["streak"] += 1; st.session_state.user_data["last_active"] = str(today_dt)
                    c["next_review"] = str(today_dt + timedelta(days=d)); save_j(get_p(u, "flashcards"), st.session_state.flashcards)
                    save_j(get_p(u, "user_data"), st.session_state.user_data); del st.session_state.n_c; st.rerun()
            else:
                if st.button("Następne ➡️", use_container_width=True): del st.session_state.n_c; st.rerun()

elif choice == "🎴 Fiszki":
    update_activity("Fiszki")
    st.header("🎴 Fiszki")
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
                ex_html += f"<div style='margin-top:15px; border-top:1px solid #444; padding-top:10px;'><span style='color:#FFEB3B; font-weight:bold;'>🇩🇪 {ex['de']}</span><br><span style='color:#FFFFFF; font-style:italic;'>🇵🇱 {ex['pl']}</span></div>"
        
        st.markdown(f'<div style="min-height:350px; display:flex; flex-direction:column; align-items:center; justify-content:center; background:#000000; border:3px solid #FF5252; border-radius:30px; padding:30px; text-align:center;"><h1 style="color:white; margin:0; font-size:2.2em;">{word_txt}</h1>{ex_html}</div>', unsafe_allow_html=True)
        st.write("<br>", unsafe_allow_html=True)
        c1, c2, c3 = st.columns([1, 1.2, 1])
        if col1 := c1.button("⬅️ Wstecz", use_container_width=True): st.session_state.f_idx -= 1; st.session_state.f_flipped = False; st.rerun()
        if col2 := c2.button("🔄 OBRÓĆ", type="primary", use_container_width=True): st.session_state.f_flipped = not st.session_state.f_flipped; st.rerun()
        if col3 := c3.button("Dalej ➡️", use_container_width=True): st.session_state.f_idx += 1; st.session_state.f_flipped = False; st.rerun()
        if st.session_state.f_flipped: play_audio(f"{c['de']} . . " + " . . ".join([e['de'] for e in c.get('examples', [])]))

elif choice == "👑 Admin":
    st.header("👑 Panel Admina Master")
    users = load_j(AUTH_FILE, {}); adm_data = []; global_time = {m: 0.0 for m in MODULE_ORDER}
    m1, m2 = st.columns(2)
    
    for usr in users:
        ud = load_j(get_p(usr, "user_data"), {})
        ub = load_j(get_p(usr, "flashcards"), [])
        df_u = pd.DataFrame(ub); mastery, ai_n = "0%", 0
        if not df_u.empty:
            opanowane = ((pd.to_datetime(df_u['next_review']).dt.date - today_dt).apply(lambda x: x.days if pd.notnull(x) else 0) >= 7).sum()
            mastery = f"{round((opanowane/len(df_u))*100)}%"
            ai_n = len(df_u[df_u['category'].str.contains('Skaner', na=False)])
        
        t_s = ud.get("time_stats", {})
        for m in MODULE_ORDER: global_time[m] += t_s.get(m, 0.0)
        u_times = ", ".join([f"{m}:{round(s/60)}m" for m,s in t_s.items() if s > 15])

        adm_data.append({
            "Użytkownik": usr, "Słów": len(ub), "AI (Skaner)": ai_n, "% Wiedzy": mastery, 
            "Ostatnio": ud.get("last_seen", "Nigdy"), "Czas Modułów": u_times or "Brak"
        })
    
    m1.metric("Łącznie Słówek", sum(x['Słów'] for x in adm_data))
    total_spent = sum(load_j(get_p(un, 'user_data'), {}).get('historical_cost', 0) for un in users)
    m2.metric("Pozostały Bonus AI", f"{BONUS_START - total_spent:.2f} PLN")
    st.subheader("👥 Baza Użytkowników"); st.dataframe(pd.DataFrame(adm_data), use_container_width=True)
    
    st.divider(); st.subheader("📊 Popularność Modułów")
    total_g = sum(global_time.values())
    if total_g > 0:
        vals = [global_time[m] for m in MODULE_ORDER]
        labels = [f"{m}: {round(v/60,1)} min" for m, v in zip(MODULE_ORDER, vals)]
        fig = go.Figure(data=[go.Bar(x=MODULE_ORDER, y=vals, text=labels, textposition='auto', marker_color='#1E88E5')])
        fig.update_layout(template="plotly_dark", height=400); st.plotly_chart(fig, use_container_width=True)

elif choice == "⚙️ Moje Konto":
    st.header("⚙️ Moje Konto")
    if "del_msg" in st.session_state: st.success(st.session_state.del_msg); del st.session_state.del_msg
    
    with st.expander("🔑 Zmień hasło"):
        with st.form("p_c"):
            o, n1, n2 = st.text_input("Stare", type="password"), st.text_input("Nowe", type="password"), st.text_input("Powtórz", type="password")
            if st.form_submit_button("Zaktualizuj hasło"):
                db = load_j(AUTH_FILE, {})
                if db[u] == hash_pw(o) and n1 == n2:
                    db[u] = hash_pw(n1); save_j(AUTH_FILE, db); st.success("Zmieniono!")
                else: st.error("Błąd haseł")
    
    st.divider(); st.subheader("⚠️ Strefa Niebezpieczna"); conf = st.checkbox("Potwierdzam chęć usunięcia")
    lvls = ["A1", "A2", "B1", "B2", "C1"]
    cols = st.columns(5)
    for i, l in enumerate(lvls):
        if cols[i].button(f"Usuń {l}", disabled=not conf, use_container_width=True):
            before = len(st.session_state.flashcards)
            st.session_state.flashcards = [x for x in st.session_state.flashcards if l not in str(x.get('category',''))]
            removed = before - len(st.session_state.flashcards)
            save_j(get_p(u, "flashcards"), st.session_state.flashcards)
            st.session_state.del_msg = f"Usunięto {removed} słówek!"; st.rerun()
            
    if st.button("🗑️ USUŃ WSZYSTKO", type="primary", disabled=not conf, use_container_width=True):
        st.session_state.flashcards = []; save_j(get_p(u, "flashcards"), []); st.rerun()

# --- POZOSTAŁE MODUŁY (ZAMROŻONE) ---
elif choice == "📸 Skaner AI":
    src = st.camera_input("Foto"); up = st.file_uploader("Plik")
    if (src or up) and st.button("🚀 ANALIZUJ", use_container_width=True):
        try:
            genai.configure(api_key=API_KEY); m = genai.GenerativeModel('gemini-2.5-flash')
            res = m.generate_content(["Zwróć JSON: [{'de':'...', 'pl':'...', 'category':'Skaner', 'examples':[{'de':'...', 'pl':'...'}]}]", Image.open(src or up).convert("RGB")])
            st.session_state.pending = json.loads(re.search(r'\[.*\]', res.text, re.DOTALL).group(0)); st.rerun()
        except: st.error("Błąd AI")
    if "pending" in st.session_state:
        ed = st.data_editor(pd.DataFrame(st.session_state.pending), use_container_width=True)
        if st.button("✅ ZAPISZ", use_container_width=True):
            for w in ed.to_dict('records'):
                w.update({"next_review": str(today_dt), "date_added": str(today_dt)}); st.session_state.flashcards.append(w)
            save_j(get_p(u, "flashcards"), st.session_state.flashcards); del st.session_state.pending; st.rerun()

elif choice == "📦 Generator słów":
    cols = st.columns(5); lvls = ["A1", "A2", "B1", "B2", "C1"]
    for i, lvl in enumerate(lvls):
        if cols[i].button(lvl, use_container_width=True):
            with st.spinner("AI pracuje..."):
                try:
                    genai.configure(api_key=API_KEY); m = genai.GenerativeModel('gemini-2.5-flash')
                    exist = [x['de'] for x in st.session_state.flashcards[:250]]
                    p = f"25 German words level {lvl}. PL. Skip: {exist}. JSON: [{{'de':'...', 'pl':'...', 'category':'...', 'examples':[{{'de':'...', 'pl':'...'}}]}}]"
                    res = m.generate_content(p); match = re.search(r'\[.*\]', res.text, re.DOTALL)
                    if match:
                        added = 0
                        for w in json.loads(match.group(0)):
                            if w['de'].lower() not in [x['de'].lower() for x in st.session_state.flashcards]:
                                w.update({"next_review": str(today_dt), "date_added": str(today_dt), "category": f"{lvl} - {w.get('category','Inne')}"})
                                st.session_state.flashcards.append(w); added += 1
                        save_j(get_p(u, "flashcards"), st.session_state.flashcards); st.success(f"Dodano {added}!"); st.rerun()
                except: st.error("Błąd AI")

elif choice == "🕹️ Quiz":
    all_c = st.session_state.flashcards
    if len(all_c) < 4: st.warning("Min. 4 słówka!")
    else:
        if "q_c" not in st.session_state:
            t = random.choice(all_c); opts = random.sample([x['pl'] for x in all_c if x['pl']!=t['pl']], 3) + [t['pl']]
            random.shuffle(opts); st.session_state.update({"q_c":t,"q_a":t['pl'],"q_o":opts,"q_s":"ask"})
        st.write(f"### **{st.session_state.q_c['de']}**")
        if st.session_state.q_s == "ask":
            for o in st.session_state.q_o:
                if st.button(o, key=o, use_container_width=True): st.session_state.u_q, st.session_state.q_s = o, "res"; st.rerun()
        else:
            if st.session_state.get("u_q") == st.session_state.q_a: st.success("✅ Brawo!")
            else: st.error(f"Poprawnie: {st.session_state.q_a}")
            play_audio(f"{st.session_state.q_c['de']} . . " + " . . ".join([e['de'] for e in st.session_state.q_c.get('examples', [])]))
            if st.button("Dalej", use_container_width=True): del st.session_state.q_c; st.rerun()

elif choice == "➕ Dodaj":
    with st.form("manual"):
        de, pl, kat = st.text_input("DE"), st.text_input("PL"), st.text_input("Kat")
        if st.form_submit_button("Zapisz", use_container_width=True):
            if de and pl:
                st.session_state.flashcards.append({"de":de,"pl":pl,"category":kat or "Inne","next_review":str(today_dt),"date_added":str(today_dt),"examples":[]})
                save_j(get_p(u,"flashcards"), st.session_state.flashcards); st.success("OK")

elif choice == "📖 Słownik":
    kats = ["Wszystkie"] + sorted(list(set([c.get("category","Inne") for c in st.session_state.flashcards])))
    f_kat = st.selectbox("📁 Kategoria:", kats); search = st.text_input("🔍 Szukaj:")
    for i, c in enumerate(st.session_state.flashcards):
        if (f_kat == "Wszystkie" or c.get("category") == f_kat) and (search.lower() in c['de'].lower()):
            with st.expander(f"📝 {c['de']} — {c['pl']}"):
                with st.form(f"ed_{i}"):
                    n_de = st.text_input("DE", c['de']); n_pl = st.text_input("PL", c['pl'])
                    if st.form_submit_button("Zapisz", use_container_width=True):
                        c.update({"de":n_de,"pl":n_pl}); save_j(get_p(u,"flashcards"), st.session_state.flashcards); st.rerun()
                    if st.form_submit_button("Usuń", use_container_width=True):
                        st.session_state.flashcards.pop(i); save_j(get_p(u,"flashcards"), st.session_state.flashcards); st.rerun()

elif choice == "📊 Statystyki":
    df = pd.DataFrame(st.session_state.flashcards)
    if not df.empty:
        c1, c2, c3 = st.columns(3); c1.metric("Słówek", len(df)); c2.metric("Passa", f"{st.session_state.user_data.get('streak', 0)} dni")
        def ck(x):
            try: return "Opanowane" if (date.fromisoformat(x)-today_dt).days >= 7 else "W trakcie"
            except: return "W trakcie"
        df['status'] = df['next_review'].apply(ck); c3.metric("Opanowane", len(df[df['status']=="Opanowane"]))
        st.bar_chart(pd.DataFrame([{"D": (today_dt + timedelta(days=i)).strftime("%d.%m"), "S": len(df[df['next_review']==str(today_dt + timedelta(days=i))])} for i in range(14)]).set_index("D"))
