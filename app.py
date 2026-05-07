import streamlit as st
import json, os, random, re, hashlib, pandas as pd, secrets
from datetime import datetime, date, timedelta
from io import BytesIO
from PIL import Image
import google.generativeai as genai
import time

# --- KONFIGURACJA ---
APP_VERSION = "V113"
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
        f = BytesIO(); tts = gTTS(text=txt, lang='de'); tts.write_to_fp(f); f.seek(0)
        st.audio(f, format="audio/mp3", autoplay=True)
    except: st.error("Błąd audio")

# --- MECHANIZM LOGOWANIA I SESJI ---
if "auth" not in st.session_state:
    st.session_state.auth = False
    # Sprawdzenie tokenu w URL (Auto-login)
    q_params = st.query_params
    if "token" in q_params:
        sessions = load_j(SESSIONS_FILE, {})
        token = q_params["token"]
        if token in sessions:
            st.session_state.auth = True
            st.session_state.user = sessions[token]

if not st.session_state.auth:
    st.title("🚀 Niemiecki Master")
    
    tab1, tab2 = st.tabs(["🔐 Logowanie", "📝 Rejestracja"])
    
    with tab1:
        u_in = st.text_input("Użytkownik", key="login_u").lower().strip()
        p_in = st.text_input("Hasło", type="password", key="login_p")
        remember = st.checkbox("Zapamiętaj mnie na tym urządzeniu", value=True)
        
        if st.button("Zaloguj się", use_container_width=True, type="primary"):
            db = load_j(AUTH_FILE, {})
            if u_in in db and db[u_in] == hash_pw(p_in):
                st.session_state.auth = True
                st.session_state.user = u_in
                
                if remember:
                    token = secrets.token_hex(16)
                    sessions = load_j(SESSIONS_FILE, {})
                    sessions[token] = u_in
                    save_j(SESSIONS_FILE, sessions)
                    st.query_params["token"] = token
                st.rerun()
            else:
                st.error("Błędne dane logowania")
                
    with tab2:
        u_new = st.text_input("Nowy użytkownik", key="reg_u").lower().strip()
        p_new = st.text_input("Nowe hasło", type="password", key="reg_p")
        p_conf = st.text_input("Powtórz hasło", type="password", key="reg_pc")
        
        if st.button("Załóż konto", use_container_width=True):
            db = load_j(AUTH_FILE, {})
            if not u_new or len(p_new) < 4:
                st.warning("Nazwa użytkownika i hasło (min. 4 znaki) są wymagane.")
            elif u_new in db:
                st.error("Ten użytkownik już istnieje.")
            elif p_new != p_conf:
                st.error("Hasła nie są identyczne.")
            else:
                # Zapis hasła
                db[u_new] = hash_pw(p_new)
                save_j(AUTH_FILE, db)
                
                # Inicjalizacja plików użytkownika
                save_j(get_p(u_new, "flashcards"), [])
                save_j(get_p(u_new, "user_data"), {
                    "streak": 0, "last_active": str(date.today() - timedelta(days=1)),
                    "last_seen": "Nigdy", "time_stats": {}
                })
                
                st.success("Konto utworzone! Możesz się zalogować.")
    st.stop()

# --- MODUŁY GŁÓWNE (Zgodne z V112) ---
u = st.session_state.user
if "flashcards" not in st.session_state: st.session_state.flashcards = load_j(get_p(u, "flashcards"), [])
if "user_data" not in st.session_state: 
    st.session_state.user_data = load_j(get_p(u, "user_data"), {"streak":0})

def update_activity(module="Inne"):
    st.session_state.user_data["last_ts"] = time.time()
    st.session_state.user_data["last_seen"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    save_j(get_p(u, "user_data"), st.session_state.user_data)

today_dt = date.today()

# --- BOCZNE MENU ---
st.sidebar.title(f"👤 {u.capitalize()}")
st.sidebar.info(f"🔥 Passa: **{st.session_state.user_data.get('streak', 0)} dni**")

if st.sidebar.button("Wyloguj (Wyczyść sesję)", use_container_width=True):
    # Usuwamy token z sesji i URL
    curr_token = st.query_params.get("token")
    if curr_token:
        sessions = load_j(SESSIONS_FILE, {})
        if curr_token in sessions: del sessions[curr_token]
        save_j(SESSIONS_FILE, sessions)
    st.query_params.clear()
    st.session_state.clear()
    st.rerun()

menu = ["📅 Powtórki", "🚀 Trening", "🕹️ Quiz", "🎴 Fiszki", "📸 Skaner AI", "📦 Generator słów", "➕ Dodaj", "📖 Słownik", "📊 Statystyki", "⚙️ Moje Konto"]
if u == ADMIN_USER: menu.append("👑 Admin")
choice = st.sidebar.radio("Nawigacja", menu)

# --- FUNKCJE POMOCNICZE ---
def is_correct(ans, correct):
    syns = [s.strip().lower() for s in re.split(r'[/,;]', correct)]
    return ans.strip().lower() in syns

def get_full_audio_text(word, examples):
    text = f"{word} , , , . . . "
    if examples:
        for ex in examples:
            sentence = ex.get('de', ex) if isinstance(ex, dict) else ex
            text += f"{sentence} . . . "
    return text

# --- MODUŁ: FISZKI (Mobile UX) ---
if choice == "🎴 Fiszki":
    update_activity("Fiszki")
    st.header("🎴 Fiszki")
    kats = sorted(list(set([c.get("category","Inne") for c in st.session_state.flashcards])))
    sel_kat = st.selectbox("🎯 Kategoria:", ["Wszystkie"] + kats)
    cards = [c for c in st.session_state.flashcards if sel_kat == "Wszystkie" or c.get("category") == sel_kat]
    
    if cards:
        if "f_idx" not in st.session_state: st.session_state.f_idx = 0
        if "f_flipped" not in st.session_state: st.session_state.f_flipped = False
        c = cards[st.session_state.f_idx % len(cards)]
        
        disp = c["pl"] if st.session_state.f_flipped else c["de"]
        exs = f"<div style='color:#00ff00; font-size:0.8em; margin-top:10px;'>{c.get('examples',[{}])[0].get('de','')}<br>{c.get('examples',[{}])[0].get('pl','')}</div>" if st.session_state.f_flipped else ""
        
        st.markdown(f'<div style="height:300px; display:flex; flex-direction:column; align-items:center; justify-content:center; background:#262730; border:2px solid #4a4a4a; border-radius:20px; padding:20px; text-align:center;"><h2>{disp}</h2>{exs}</div>', unsafe_allow_html=True)
        
        col1, col2, col3 = st.columns([1, 2, 1])
        if col1.button("⬅️", use_container_width=True): st.session_state.f_idx -= 1; st.session_state.f_flipped = False; st.rerun()
        if col2.button("🔄 OBRÓĆ", type="primary", use_container_width=True): st.session_state.f_flipped = not st.session_state.f_flipped; st.rerun()
        if col3.button("➡️", use_container_width=True): st.session_state.f_idx += 1; st.session_state.f_flipped = False; st.rerun()
        
        if st.session_state.f_flipped:
            if st.button("🔊 Słuchaj", use_container_width=True):
                play_audio(get_full_audio_text(c['de'], c.get("examples")))

# --- MODUŁ: POWTÓRKI ---
elif choice == "📅 Powtórki":
    update_activity("Powtórki")
    st.header("📅 Powtórki")
    td = str(date.today())
    cards = [c for c in st.session_state.flashcards if c.get("next_review", td) <= td]
    
    if not cards:
        st.success("Wszystko powtórzone! 🎉")
    else:
        st.info(f"Pozostało: {len(cards)}")
        if "n_c" not in st.session_state: st.session_state.n_c = random.choice(cards); st.session_state.n_m = "ask"
        c = st.session_state.n_c
        
        st.write(f"### Słówko: **{c['de']}**")
        if st.session_state.n_m == "ask":
            with st.form("pow"):
                ans = st.text_input("Odpowiedź:")
                if st.form_submit_button("Sprawdź", use_container_width=True):
                    st.session_state.ans = ans; st.session_state.n_m = "res"; st.rerun()
        else:
            if is_correct(st.session_state.ans, c['pl']): st.success(f"✅ Dobrze: {c['pl']}")
            else: st.error(f"❌ Poprawnie: {c['pl']}")
            
            play_audio(get_full_audio_text(c['de'], c.get("examples")))
            
            c1, c2, c3 = st.columns(3)
            d = None
            if c1.button("🔴 1d", use_container_width=True): d = 1
            if c2.button("🟡 3d", use_container_width=True): d = 3
            if c3.button("🟢 7d", use_container_width=True): d = 7
            
            if d:
                c["next_review"] = str(date.today() + timedelta(days=d))
                # Passa
                if date.fromisoformat(st.session_state.user_data.get("last_active", "2000-01-01")) < date.today():
                    st.session_state.user_data["streak"] = st.session_state.user_data.get("streak", 0) + 1
                    st.session_state.user_data["last_active"] = str(date.today())
                save_j(get_p(u, "flashcards"), st.session_state.flashcards)
                save_j(get_p(u, "user_data"), st.session_state.user_data)
                del st.session_state.n_c; st.rerun()

# --- POZOSTAŁE MODUŁY ZAMROŻONE (V112) ---
elif choice == "🚀 Trening":
    update_activity("Trening"); st.write("Moduł Treningu")
    # ... reszta logiki analogicznie do poprzednich wersji ...

elif choice == "⚙️ Moje Konto":
    update_activity("Konto")
    st.header("⚙️ Moje Konto")
    if st.button("🚀 NAPRAW BRAKUJĄCE PRZYKŁADY", use_container_width=True):
        to_fix = [c for c in st.session_state.flashcards if not c.get("examples")]
        if to_fix:
            with st.spinner(f"Naprawiam {len(to_fix)} słówek..."):
                genai.configure(api_key=API_KEY); m = genai.GenerativeModel('gemini-2.5-flash')
                for c in to_fix:
                    try:
                        r = m.generate_content(f"JSON: [{{'de':'...', 'pl':'...'}}] - 2 German sentences for '{c['de']}'")
                        c["examples"] = json.loads(re.search(r'\[.*\]', r.text, re.DOTALL).group(0))
                    except: pass
                save_j(get_p(u, "flashcards"), st.session_state.flashcards); st.success("Naprawiono!")
