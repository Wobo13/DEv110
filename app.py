import streamlit as st
import json, os, random, re, hashlib, pandas as pd, secrets
from datetime import datetime, date, timedelta
from io import BytesIO
from PIL import Image
import google.generativeai as genai
import time
import plotly.graph_objects as go

# --- KONFIGURACJA ---
APP_VERSION = "V133"
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

def parse_ai_json(text):
    try:
        match = re.search(r'\[.*\]', text, re.DOTALL)
        if match:
            clean = match.group(0).replace('```json', '').replace('```', '').strip()
            return json.loads(clean)
        return None
    except: return None

# --- LOGOWANIE ---
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
                st.success("Konto utworzone!")
    st.stop()

# --- INIT DANYCH ---
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

if "l_c" not in st.session_state: st.session_state.l_c = choice
if st.session_state.l_c != choice:
    for k in ["n_c", "n_m", "q_c", "q_s", "f_idx", "f_flipped", "u_a", "del_msg", "pending"]:
        if k in st.session_state: del st.session_state[k]
    st.session_state.l_c = choice

def is_correct(a, c): return a.strip().lower() in [s.strip().lower() for s in re.split(r'[/,;]', c)]

# --- MODUŁY ---
if choice in ["📅 Powtórki", "🚀 Trening"]:
    m_name = "Powtórki" if choice == "📅 Powtórki" else "Trening"
    update_activity(m_name)
    kats = ["Wszystkie"] + sorted(list(set([c.get("category","Inne") for c in st.session_state.flashcards])))
    sel_kat = st.selectbox("🎯 Kategoria:", kats)
    all_c = [c for c in st.session_state.flashcards if sel_kat == "Wszystkie" or c.get("category") == sel_kat]
    cards = [c for c in all_c if choice == "🚀 Trening" or c.get("next_review", str(today_dt)) <= str(today_dt)]
    st.info(f"Słówek: **{len(cards)}**")
    if not cards: st.success("Gotowe!")
    else:
        if "n_c" not in st.session_state: st.session_state.n_c = random.choice(cards); st.session_state.n_m = "ask"
        c = st.session_state.n_c
        st.write(f"### Słówko: **{c['de']}**")
        if st.session_state.n_m == "ask":
            with st.form("ans_f"):
                ua = st.text_input("Twoja odpowiedź:")
                if st.form_submit_button("Sprawdź", use_container_width=True):
                    st.session_state.u_a = ua; st.session_state.n_m = "res"; st.rerun()
        else:
            ans = st.session_state.get("u_a", "")
            if is_correct(ans, c['pl']): st.success(f"✅ Dobrze: {c['pl']}")
            else: st.error(f"❌ Poprawnie: {c['pl']}")
            if c.get("examples"):
                for ex in c["examples"]: st.markdown(f"🇩🇪 {ex['de']}<br>🇵🇱 {ex['pl']}", unsafe_allow_html=True)
            play_audio(f"{c['de']} . . " + " . . ".join([e['de'] for e in c.get('examples', [])]))
            if choice == "📅 Powtórki":
                c1, c2, c3 = st.columns(3)
                if c1.button("🔴 Słabo", use_container_width=True):
                    c["next_review"] = str(today_dt + timedelta(days=1)); del st.session_state.n_c; st.rerun()
                if c2.button("🟡 Średnio", use_container_width=True):
                    c["next_review"] = str(today_dt + timedelta(days=3)); del st.session_state.n_c; st.rerun()
                if c3.button("🟢 Dobrze", use_container_width=True):
                    c["next_review"] = str(today_dt + timedelta(days=7)); del st.session
