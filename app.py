import streamlit as st
import json, os, random, re, hashlib, pandas as pd, secrets
from datetime import datetime, date, timedelta
from io import BytesIO
from PIL import Image
import google.generativeai as genai
import time

# --- KONFIGURACJA ---
APP_VERSION = "V119"
ADMIN_USER = "wobo"
AUTH_FILE, SESSIONS_FILE = "users_auth.json", "sessions.json"
BONUS_START = 1089.0
API_KEY = st.secrets.get("GEMINI_API_KEY") or st.session_state.get("manual_api_key", "")

# --- SYSTEM POMOCNICZY ---
def hash_pw(pw): return hashlib.sha256(str.encode(pw)).hexdigest()
def get_p(u, t): return f"{t}_{u}.json"
def load_j(p, d): return json.load(open(p, "r", encoding="utf-8")) if os.path.exists(p) else d
def save_j(p, d): json.dump(d, open(p, "w", encoding="utf-8"), indent=4)

def play_audio(txt):
    try:
        from gtts import gTTS
        f = BytesIO()
        tts = gTTS(text=txt, lang='de')
        tts.write_to_fp(f); f.seek(0)
        st.audio(f, format="audio/mp3", autoplay=True)
    except: st.error("Błąd audio")

# --- LOGOWANIE I AUTO-LOGIN ---
if "auth" not in st.session_state:
    st.session_state.auth = False
    q_params = st.query_params
    if "token" in q_params:
        sessions = load_j(SESSIONS_FILE, {})
        if q_params["token"] in sessions:
            st.session_state.auth, st.session_state.user = True, sessions[q_params["token"]]

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
                save_j(get_p(u_n, "user_data"), {"streak":0, "last_active":str(date.today()-timedelta(days=1)), "historical_cost": 0.0, "time_stats": {}})
                st.success("Konto utworzone!")
    st.stop()

# --- INIT DANYCH ---
u = st.session_state.user
if "flashcards" not in st.session_state: st.session_state.flashcards = load_j(get_p(u, "flashcards"), [])
if "user_data" not in st.session_state: 
    d = load_j(get_p(u, "user_data"), {})
    defaults = {"streak":0, "historical_cost":0.0, "time_stats":{}, "last_ts": time.time(), "last_seen": "Nigdy"}
    for k,v in defaults.items(): 
        if k not in d: d[k] = v
    st.session_state.user_data = d

def update_activity(m="Inne"):
    curr = time.time()
    last = st.session_state.user_data.get("last_ts", curr)
    delta = curr - last
    if 0 < delta < 900:
        stats = st.session_state.user_data.get("time_stats", {})
        m_clean = m.strip("📅 🚀 🕹️ 🎴 📸 📦 ➕ 📖 📊 ⚙️ ")
        stats[m_clean] = stats.get(m_clean, 0) + delta
        st.session_state.user_data["time_stats"] = stats
    st.session_state.user_data["last_ts"] = curr
    st.session_state.user_data["last_seen"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    save_j(get_p(u, "user_data"), st.session_state.user_data)

today_dt = date.today()
update_activity()

# --- MENU ---
st.sidebar.title(f"👤 {u.capitalize()}")
st.sidebar.caption(f"🚀 Wersja: {APP_VERSION}")
st.sidebar.info(f"🔥 Passa: **{st.session_state.user_data.get('streak', 0)} dni**")
if st.sidebar.button("Wyloguj", use_container_width=True):
    tk = st.query_params.get("token")
    if tk:
        ss = load_j(SESSIONS_FILE, {})
        if tk in ss: del ss[tk]; save_j(SESSIONS_FILE, ss)
    st.query_params.clear(); st.session_state.clear(); st.rerun()

menu = ["📅 Powtórki", "🚀 Trening", "🕹️ Quiz", "🎴 Fiszki", "📸 Skaner AI", "📦 Generator słów", "➕ Dodaj", "📖 Słownik", "📊 Statystyki", "⚙️ Moje Konto"]
if u == ADMIN_USER: menu.append("👑 Admin")
choice = st.sidebar.radio("Nawigacja", menu)

if "l_c" not in st.session_state: st.session_state.l_c = choice
if st.session_state.l_c != choice:
    for k in ["n_c", "n_m", "q_c", "q_s", "f_idx", "f_flipped", "gen_report", "pending"]:
        if k in st.session_state: del st.session_state[k]
    st.session_state.l_c = choice

# --- POMOCNIKI ---
def is_correct(a, c): return a.strip().lower() in [s.strip().lower() for s in re.split(r'[/,;]', c)]
def format_ex(exs): return "\n\n".join([f"🇩🇪 {e['de']}\n🇵🇱 {e['pl']}" if isinstance(e, dict) else f"🇩🇪 {e}" for e in exs])
def get_audio_txt(w, exs):
    t = f"{w} , , , . . . "
    if exs:
        for e in exs: t += f"{e['de'] if isinstance(e, dict) else e} . . . "
    return t

# --- MODUŁY ---
if choice in ["📅 Powtórki", "🚀 Trening"]:
    is_r = (choice == "📅 Powtórki")
    update_activity("Powtórki" if is_r else "Trening")
    kats = ["Wszystkie"] + sorted(list(set([c.get("category","Inne") for c in st.session_state.flashcards])))
    sel_kat = st.selectbox("🎯 Kategoria:", kats)
    all_c = [c for c in st.session_state.flashcards if sel_kat == "Wszystkie" or c.get("category") == sel_kat]
    cards = [c for c in all_c if not is_r or c.get("next_review", str(today_dt)) <= str(today_dt)]
    
    st.info(f"{'Do powtórzenia' if is_r else 'W treningu'}: **{len(cards)}**")
    if not cards: st.success("Czysto!")
    else:
        if "n_c" not in st.session_state: st.session_state.n_c = random.choice(cards); st.session_state.n_m = "ask"
        c = st.session_state.n_c
        st.write(f"### Słówko: **{c['de']}**")
        if st.session_state.n_m == "ask":
            with st.form("ans"):
                u_a = st.text_input("Odpowiedź:"); ok = st.form_submit_button("Sprawdź", use_container_width=True)
                if ok: st.session_state.u_a, st.session_state.n_m = u_a, "res"; st.rerun()
        else:
            if is_correct(st.session_state.u_a, c['pl']): st.success(f"✅ {c['pl']}")
            else: st.error(f"❌ {c['pl']}")
            if c.get("examples"): st.info(format_ex(c["examples"]))
            play_audio(get_audio_txt(c['de'], c.get("examples")))
            if is_r:
                c1, c2, c3 = st.columns(3); d = None
                if c1.button("🔴 1d", use_container_width=True): d = 1
                if c2.button("🟡 3d", use_container_width=True): d = 3
                if c3.button("🟢 7d", use_container_width=True): d = 7
                if d:
                    if date.fromisoformat(st.session_state.user_data.get("last_active", "2000-01-01")) < today_dt:
                        st.session_state.user_data["streak"] += 1; st.session_state.user_data["last_active"] = str(today_dt)
                    c["next_review"] = str(today_dt + timedelta(days=d)); save_j(get_p(u, "flashcards"), st.session_state.flashcards)
                    save_j(get_p(u, "user_data"), st.session_state.user_data); del st.session_state.n_c; st.rerun()
            else:
                if st.button("Następne", use_container_width=True): del st.session_state.n_c; st.rerun()

elif choice == "🎴 Fiszki":
    update_activity("Fiszki")
    kats = ["Wszystkie"] + sorted(list(set([c.get("category","Inne") for c in st.session_state.flashcards])))
    sel_kat = st.selectbox("🎯 Kategoria:", kats)
    cards = [c for c in st.session_state.flashcards if sel_kat == "Wszystkie" or c.get("category") == sel_kat]
    if cards:
        if "f_idx" not in st.session_state: st.session_state.f_idx = 0
        if "f_flipped" not in st.session_state: st.session_state.f_flipped = False
        c = cards[st.session_state.f_idx % len(cards)]
        txt = c["pl"] if st.session_state.f_flipped else c["de"]
        exs = f"<div style='color:#00ff00;font-size:0.8em;'>{format_ex(c.get('examples',[]))[:100]}...</div>" if st.session_state.f_flipped else ""
        st.markdown(f'<div style="height:250px;display:flex;flex-direction:column;align-items:center;justify-content:center;background:#262730;border:2px solid #4a4a4a;border-radius:20px;padding:20px;text-align:center;"><h2>{txt}</h2>{exs}</div>', unsafe_allow_html=True)
        col1, col2, col3 = st.columns([1,2,1])
        if col1.button("⬅️", use_container_width=True): st.session_state.f_idx -= 1; st.session_state.f_flipped = False; st.rerun()
        if col2.button("🔄 OBRÓĆ", type="primary", use_container_width=True): st.session_state.f_flipped = not st.session_state.f_flipped; st.rerun()
        if col3.button("➡️", use_container_width=True): st.session_state.f_idx += 1; st.session_state.f_flipped = False; st.rerun()
        if st.session_state.f_flipped: play_audio(get_audio_txt(c['de'], c.get("examples")))

elif choice == "📸 Skaner AI":
    update_activity("Skaner")
    src = st.camera_input("Foto")
    up = st.file_uploader("Plik")
    f_src = src or up
    if f_src and st.button("🚀 ANALIZUJ", use_container_width=True):
        try:
            genai.configure(api_key=API_KEY); m = genai.GenerativeModel('gemini-2.5-flash')
            res = m.generate_content(["JSON: [{'de':'...', 'pl':'...', 'category':'PL', 'examples':[{'de':'...', 'pl':'...'}]}]", Image.open(f_src).convert("RGB")])
            st.session_state.pending = json.loads(re.search(r'\[.*\]', res.text, re.DOTALL).group(0))
            st.session_state.user_data["historical_cost"] += 0.005; st.rerun()
        except: st.error("Błąd AI")
    if "pending" in st.session_state:
        ed = st.data_editor(pd.DataFrame(st.session_state.pending), use_container_width=True)
        if st.button("✅ ZAPISZ", use_container_width=True):
            for w in ed.to_dict('records'):
                w.update({"next_review": str(today_dt), "date_added": str(today_dt)}); st.session_state.flashcards.append(w)
            save_j(get_p(u, "flashcards"), st.session_state.flashcards); del st.session_state.pending; st.rerun()

elif choice == "📦 Generator słów":
    update_activity("Generator")
    lvls = ["A1", "A2", "B1", "B2", "C1"]; cols = st.columns(len(lvls))
    for i, lvl in enumerate(lvls):
        if cols[i].button(lvl, use_container_width=True):
            with st.spinner("AI..."):
                try:
                    genai.configure(api_key=API_KEY); m = genai.GenerativeModel('gemini-2.5-flash')
                    exist = [x['de'] for x in st.session_state.flashcards[:250]]
                    p = f"25 German words {lvl}. Categories/Examples in Polish. Skip: {exist}. JSON: [{'de':'...', 'pl':'...', 'category':'...', 'examples':[{{'de':'...', 'pl':'...'}}]}]"
                    res = m.generate_content(p); match = re.search(r'\[.*\]', res.text, re.DOTALL)
                    if match:
                        new_data = json.loads(match.group(0)); added = 0
                        for w in new_data:
                            if w['de'].lower() not in [x['de'].lower() for x in st.session_state.flashcards]:
                                w.update({"next_review": str(today_dt), "date_added": str(today_dt), "category": f"{lvl} - {w.get('category','Inne')}"})
                                st.session_state.flashcards.append(w); added += 1
                        st.session_state.user_data["historical_cost"] += 0.002; save_j(get_p(u, "flashcards"), st.session_state.flashcards)
                        st.session_state.gen_report = added; st.rerun()
                except: st.error("Błąd")
    if "gen_report" in st.session_state: st.success(f"Dodano {st.session_state.gen_report}!")

elif choice == "🕹️ Quiz":
    update_activity("Quiz")
    all_c = st.session_state.flashcards
    if len(all_c) < 4: st.warning("Dodaj min. 4 słówka!")
    else:
        if "q_c" not in st.session_state:
            t = random.choice(all_c); opts = random.sample([x['pl'] for x in all_c if x['pl']!=t['pl']], 3) + [t['pl']]
            random.shuffle(opts); st.session_state.update({"q_c":t,"q_a":t['pl'],"q_o":opts,"q_s":"ask"})
        st.write(f"### **{st.session_state.q_c['de']}**")
        if st.session_state.q_s == "ask":
            for o in st.session_state.q_o:
                if st.button(o, key=o, use_container_width=True): st.session_state.u_q, st.session_state.q_s = o, "res"; st.rerun()
        else:
            if st.session_state.u_q == st.session_state.q_a: st.success("✅ Brawo!")
            else: st.error(f"Poprawnie: {st.session_state.q_a}")
            play_audio(get_audio_txt(st.session_state.q_c['de'], st.session_state.q_c.get("examples")))
            if st.button("Dalej", use_container_width=True): del st.session_state.q_c; st.rerun()

elif choice == "➕ Dodaj":
    with st.form("a"):
        de, pl, kat = st.text_input("DE"), st.text_input("PL"), st.text_input("Kat")
        if st.form_submit_button("Zapisz", use_container_width=True):
            if de and pl:
                try:
                    genai.configure(api_key=API_KEY); m = genai.GenerativeModel('gemini-2.5-flash')
                    r = m.generate_content(f"JSON: [{{'de':'...', 'pl':'...'}}] - 2 sentences for '{de}'")
                    exs = json.loads(re.search(r'\[.*\]', r.text, re.DOTALL).group(0))
                except: exs = []
                st.session_state.flashcards.append({"de":de,"pl":pl,"category":kat or "Inne","next_review":str(today_dt),"date_added":str(today_dt),"examples":exs})
                save_j(get_p(u,"flashcards"), st.session_state.flashcards); st.success("OK")

elif choice == "📖 Słownik":
    update_activity("Słownik")
    st.header("📖 Twój Słownik")
    kats = ["Wszystkie"] + sorted(list(set([c.get("category","Inne") for c in st.session_state.flashcards])))
    f_kat = st.selectbox("📁 Kategoria:", kats)
    search = st.text_input("🔍 Szukaj:")
    for i, c in enumerate(st.session_state.flashcards):
        if (f_kat == "Wszystkie" or c.get("category") == f_kat) and (search.lower() in c['de'].lower() or search.lower() in c['pl'].lower()):
            with st.expander(f"📝 {c['de']} — {c['pl']}"):
                with st.form(f"ed_{i}"):
                    n_de = st.text_input("DE", c['de'])
                    n_pl = st.text_input("PL", c['pl'])
                    n_ka = st.text_input("Kat", c.get('category','Inne'))
                    if st.form_submit_button("Zapisz", use_container_width=True):
                        c.update({"de":n_de,"pl":n_pl,"category":n_ka}); save_j(get_p(u,"flashcards"), st.session_state.flashcards); st.rerun()
                    if st.form_submit_button("Usuń", use_container_width=True):
                        st.session_state.flashcards.pop(i); save_j(get_p(u,"flashcards"), st.session_state.flashcards); st.rerun()

elif choice == "📊 Statystyki":
    update_activity("Statystyki")
    df = pd.DataFrame(st.session_state.flashcards)
    if not df.empty:
        c1, c2, c3 = st.columns(3); c1.metric("Słówek", len(df)); c2.metric("Passa", f"{st.session_state.user_data.get('streak', 0)} dni")
        def ck_st(x):
            try: return "Opanowane" if (date.fromisoformat(x)-today_dt).days >= 7 else "W trakcie"
            except: return "W trakcie"
        df['status'] = df['next_review'].apply(ck_st); c3.metric("Opanowane", len(df[df['status']=="Opanowane"]))
        st.bar_chart(pd.DataFrame([{"D": (today_dt + timedelta(days=i)).strftime("%d.%m"), "S": len(df[df['next_review']==str(today_dt + timedelta(days=i))])} for i in range(14)]).set_index("D"))

elif choice == "⚙️ Moje Konto":
    st.header("⚙️ Moje Konto")
    if st.button("🚀 NAPRAW BRAKUJĄCE PRZYKŁADY", use_container_width=True):
        to_fix = [c for c in st.session_state.flashcards if not c.get("examples")]
        if to_fix:
            with st.spinner("Praca AI..."):
                genai.configure(api_key=API_KEY); model = genai.GenerativeModel('gemini-2.5-flash')
                for c in to_fix:
                    try:
                        r = model.generate_content(f"JSON: [{{'de':'...', 'pl':'...'}}] - 2 German sentences for '{c['de']}'")
                        c["examples"] = json.loads(re.search(r'\[.*\]', r.text, re.DOTALL).group(0))
                    except: pass
                save_j(get_p(u, "flashcards"), st.session_state.flashcards); st.success("OK!"); st.rerun()
    st.divider(); st.subheader("⚠️ Strefa Niebezpieczna")
    conf = st.checkbox("Potwierdzam"); lvls = ["A1", "A2", "B1", "B2", "C1"]
    for l in lvls:
        if st.button(f"Usuń {l}", disabled=not conf, use_container_width=True):
            st.session_state.flashcards = [x for x in st.session_state.flashcards if l not in str(x.get('category',''))]
            save_j(get_p(u, "flashcards"), st.session_state.flashcards); st.rerun()
    if st.button("🗑️ USUŃ WSZYSTKO", type="primary", disabled=not conf, use_container_width=True):
        save_j(get_p(u, "flashcards"), []); st.session_state.flashcards = []; st.rerun()

elif choice == "👑 Admin":
    st.header("👑 Panel Zarządzania Master")
    users = load_j(AUTH_FILE, {}); adm_list = []
    global_time = {"Powtórki":0.0, "Trening":0.0, "Quiz":0.0, "Fiszki":0.0, "Skaner":0.0, "Generator":0.0, "Słownik":0.0}
    
    for usr in users:
        ud = load_j(get_p(usr, "user_data"), {})
        ub = load_j(get_p(usr, "flashcards"), [])
        df_u = pd.DataFrame(ub); mastery, ai_n = "0%", 0
        if not df_u.empty:
            opanowane = ((pd.to_datetime(df_u['next_review']).dt.date - today_dt).apply(lambda x: x.days if pd.notnull(x) else 0) >= 7).sum()
            mastery = f"{round((opanowane/len(df_u))*100)}%"; ai_n = len(df_u[df_u['category'].str.contains('Skaner', na=False)])
        
        t_s = ud.get("time_stats", {})
        for k in global_time: global_time[k] += t_s.get(k, 0.0)
        total_u = sum(t_s.values())
        dist = f"N:{round(t_s.get('Powtórki',0)/total_u*100)}%|T:{round(t_s.get('Trening',0)/total_u*100)}%|Q:{round(t_s.get('Quiz',0)/total_u*100)}%|F:{round(t_s.get('Fiszki',0)/total_u*100)}%" if total_u > 0 else "Brak"
        adm_list.append({"Użytkownik": usr, "Słówek": len(ub), "AI": ai_n, "% Wiedzy": mastery, "Rozkład": dist, "Ostatnio": ud.get("last_seen", "Nigdy"), "Koszt PLN": round(ud.get("historical_cost", 0.0), 4)})
    
    st.subheader("👥 Aktywność Użytkowników")
    st.table(pd.DataFrame(adm_list))
    
    st.divider()
    st.subheader("📊 Globalna Popularność Modułów")
    total_g = sum(global_time.values())
    if total_g > 0:
        g_data = pd.DataFrame([{"Moduł": k, "Czas (%)": round((v/total_g)*100, 1)} for k, v in global_time.items()])
        st.bar_chart(g_data.set_index("Moduł"))
        for k, v in global_time.items():
            st.write(f"**{k}**: {round(v/60, 1)} min ({round((v/total_g)*100, 1)}%)")
    else: st.info("Brak danych o czasie nauki.")
    st.metric("Pozostały Bonus AI", f"{BONUS_START - sum(x['Koszt PLN'] for x in adm_list):.4f} PLN")
