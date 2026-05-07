import streamlit as st
import json
import os
import random
import re
import hashlib
import pandas as pd
import secrets
from datetime import datetime, date, timedelta
from io import BytesIO
from PIL import Image
import google.generativeai as genai
import time
import plotly.graph_objects as go

# --- KONFIGURACJA ---
APP_VERSION = "V158"
ADMIN_USER = "wobo"
AUTH_FILE = "users_auth.json"
SESSIONS_FILE = "sessions.json"
BONUS_START = 1089.0

# Pobieranie klucza API
API_KEY = st.secrets.get("GEMINI_API_KEY") 
if not API_KEY:
    API_KEY = st.session_state.get("manual_api_key", "")

MODULE_ORDER = [
    "Powtórki", "Trening", "Quiz", "Fiszki", 
    "Skaner", "Generator", "Dodaj", "Słownik"
]

# --- SYSTEM POMOCNICZY ---
def hash_pw(pw): 
    return hashlib.sha256(str.encode(pw)).hexdigest()

def get_p(u, t): 
    return f"{t}_{u}.json"

def load_j(p, d): 
    if os.path.exists(p):
        try:
            with open(p, "r", encoding="utf-8") as f: 
                return json.load(f)
        except: 
            return d
    return d

def save_j(p, d): 
    with open(p, "w", encoding="utf-8") as f: 
        json.dump(d, f, indent=4)

def play_audio(txt):
    try:
        from gtts import gTTS
        f = BytesIO()
        tts = gTTS(text=txt, lang='de')
        tts.write_to_fp(f)
        f.seek(0)
        st.audio(f, format="audio/mp3", autoplay=True)
    except: 
        pass

def parse_ai_json(text):
    try:
        match = re.search(r'\[.*\]', text, re.DOTALL)
        if match:
            clean = match.group(0).replace('```json', '')
            clean = clean.replace('```', '').strip()
            return json.loads(clean)
        return json.loads(text.strip())
    except: 
        return None

# --- LOGOWANIE ---
if "auth" not in st.session_state:
    st.session_state.auth = False
    if "token" in st.query_params:
        ss = load_j(SESSIONS_FILE, {})
        tk = st.query_params["token"]
        if tk in ss:
            st.session_state.auth = True
            st.session_state.user = ss[tk]

# Inicjalizacja kluczowych zmiennych
if "u_a" not in st.session_state: 
    st.session_state.u_a = ""
if "n_m" not in st.session_state: 
    st.session_state.n_m = "ask"

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
                st.session_state.auth = True
                st.session_state.user = u_in
                if rem:
                    tk = secrets.token_hex(16)
                    sessions = load_j(SESSIONS_FILE, {})
                    sessions[tk] = u_in
                    save_j(SESSIONS_FILE, sessions)
                    st.query_params["token"] = tk
                st.rerun()
            else: 
                st.error("Błędne dane logowania")
    with t2:
        un = st.text_input("Nowy użytkownik", key="r_u").lower().strip()
        pn = st.text_input("Hasło", type="password", key="r_p")
        if st.button("Załóż konto", use_container_width=True):
            db = load_j(AUTH_FILE, {})
            if un and len(pn) >= 4 and un not in db:
                db[un] = hash_pw(pn)
                save_j(AUTH_FILE, db)
                save_j(get_p(un, "flashcards"), [])
                
                init_data = {
                    "streak": 0, 
                    "historical_cost": 0.0, 
                    "time_stats": {}, 
                    "last_ts": time.time(), 
                    "last_seen": "Nigdy"
                }
                save_j(get_p(un, "user_data"), init_data)
                st.success("Konto utworzone! Możesz się zalogować.")
    st.stop()

# --- INIT DANYCH ---
u = st.session_state.user
st.session_state.flashcards = load_j(get_p(u, "flashcards"), [])
d_u = load_j(get_p(u, "user_data"), {})

default_user_data = {
    "streak": 0, 
    "historical_cost": 0.0, 
    "time_stats": {}, 
    "last_ts": time.time(), 
    "last_seen": "Nigdy"
}

for k, v in default_user_data.items():
    if k not in d_u: 
        d_u[k] = v
st.session_state.user_data = d_u

def update_activity(m="Inne"):
    curr = time.time()
    delta = curr - st.session_state.user_data.get("last_ts", curr)
    if 0 < delta < 600:
        stats = st.session_state.user_data.get("time_stats", {})
        m_clean = m.strip("📅 🚀 🕹️ 🎴 📸 📦 ➕ 📖 📊 ⚙️ ")
        
        current_time_spent = stats.get(m_clean, 0)
        stats[m_clean] = current_time_spent + delta
        
        st.session_state.user_data["time_stats"] = stats
        
    st.session_state.user_data["last_ts"] = curr
    
    now_str = datetime.now().strftime("%d.%m %H:%M:%S")
    st.session_state.user_data["last_seen"] = now_str
    
    save_j(get_p(u, "user_data"), st.session_state.user_data)

today_dt = date.today()
update_activity()

# --- MENU BOCZNE ---
st.sidebar.title(f"👤 {u.capitalize()}")
st.sidebar.caption(f"🚀 Wersja: {APP_VERSION}")
st.sidebar.info(f"🔥 Passa: **{st.session_state.user_data.get('streak', 0)} dni**")
if st.sidebar.button("Wyloguj", use_container_width=True):
    st.query_params.clear()
    st.session_state.clear()
    st.rerun()

menu = [
    "📅 Powtórki", "🚀 Trening", "🕹️ Quiz", "🎴 Fiszki", 
    "📸 Skaner AI", "📦 Generator słów", "➕ Dodaj", 
    "📖 Słownik", "📊 Statystyki", "⚙️ Moje Konto"
]

if u == ADMIN_USER: 
    menu.append("👑 Admin")
choice = st.sidebar.radio("Nawigacja", menu)

if "l_c" not in st.session_state or st.session_state.l_c != choice:
    keys_to_delete = ["n_c", "q_c", "q_s", "f_idx", "f_flipped", "pending"]
    for k in keys_to_delete:
        if k in st.session_state: 
            del st.session_state[k]
    st.session_state.n_m = "ask"
    st.session_state.u_a = ""
    st.session_state.l_c = choice

def is_correct(a, c):
    user_ans = a.strip().lower()
    correct_answers = [s.strip().lower() for s in re.split(r'[/,;]', c)]
    return user_ans in correct_answers

# --- MODUŁY NAUKI ---
if choice in ["📅 Powtórki", "🚀 Trening"]:
    is_r = (choice == "📅 Powtórki")
    update_activity("Powtórki" if is_r else "Trening")
    
    all_cats = [c.get("category", "Inne") for c in st.session_state.flashcards]
    kats = ["Wszystkie"] + sorted(list(set(all_cats)))
    sel_kat = st.selectbox("🎯 Kategoria:", kats)
    
    all_c = []
    for c in st.session_state.flashcards:
        if sel_kat == "Wszystkie" or c.get("category") == sel_kat:
            all_c.append(c)
            
    cards = []
    for c in all_c:
        if not is_r or c.get("next_review", str(today_dt)) <= str(today_dt):
            cards.append(c)
    
    st.info(f"Słówek: **{len(cards)}**")
    
    if not cards: 
        st.success("Czysto! 🎊")
    else:
        if "n_c" not in st.session_state: 
            st.session_state.n_c = random.choice(cards)
        c = st.session_state.n_c
        st.write(f"### Słówko: **{c['de']}**")
        
        if st.session_state.n_m == "ask":
            with st.form("ans_f"):
                u_in = st.text_input("Twoja odpowiedź:")
                if st.form_submit_button("Sprawdź", use_container_width=True):
                    st.session_state.u_a = u_in
                    st.session_state.n_m = "res"
                    st.rerun()
        else:
            if is_correct(st.session_state.u_a, c['pl']): 
                st.success(f"✅ Dobrze: {c['pl']}")
            else: 
                st.error(f"❌ Poprawnie: {c['pl']}")
                
            if c.get("examples"):
                for ex in c["examples"]: 
                    st.markdown(f"🇩🇪 {ex['de']}<br>🇵🇱 {ex['pl']}", unsafe_allow_html=True)
                st.write("")
                
            audio_txt = f"{c['de']} . . "
            if c.get("examples"):
                audio_txt += " . . ".join([e['de'] for e in c["examples"]])
            play_audio(audio_txt)
            
            if is_r:
                st.write("---")
                c1, c2, c3 = st.columns(3)
                d = None
                if c1.button("🔴 Słabo (1d)", use_container_width=True): d = 1
                if c2.button("🟡 Średnio (3d)", use_container_width=True): d = 3
                if c3.button("🟢 Dobrze (7d)", use_container_width=True): d = 7
                if d:
                    new_date = today_dt + timedelta(days=d)
                    c["next_review"] = str(new_date)
                    save_j(get_p(u, "flashcards"), st.session_state.flashcards)
                    del st.session_state.n_c
                    st.session_state.n_m = "ask"
                    st.rerun()
            else:
                if st.button("Dalej ➡️", use_container_width=True):
                    del st.session_state.n_c
                    st.session_state.n_m = "ask"
                    st.rerun()

elif choice == "🎴 Fiszki":
    update_activity("Fiszki")
    st.header("🎴 Fiszki")
    
    all_cats = [c.get("category", "Inne") for c in st.session_state.flashcards]
    kats = ["Wszystkie"] + sorted(list(set(all_cats)))
    sel_kat = st.selectbox("🎯 Wybierz kategorię:", kats)
    
    cards = []
    for c in st.session_state.flashcards:
        if sel_kat == "Wszystkie" or c.get("category") == sel_kat:
            cards.append(c)
    
    if cards:
        if "f_idx" not in st.session_state: 
            st.session_state.f_idx = 0
        if "f_flipped" not in st.session_state: 
            st.session_state.f_flipped = False
            
        c = cards[st.session_state.f_idx % len(cards)]
        word_txt = c["pl"] if st.session_state.f_flipped else c["de"]
        ex_html = ""
        
        if st.session_state.f_flipped and c.get("examples"):
            for ex in c["examples"]:
                de_txt = f"<span style='color:#FFEB3B; font-weight:bold;'>🇩🇪 {ex['de']}</span>"
                pl_txt = f"<span style='color:white; font-style:italic;'>🇵🇱 {ex['pl']}</span>"
                ex_html += f"<div style='margin-top:15px; border-top:1px solid #444; padding-top:10px;'>{de_txt}<br>{pl_txt}</div>"
        
        box_style = "min-height:350px; display:flex; flex-direction:column; align-items:center; justify-content:center; background:black; border:3px solid #FF5252; border-radius:30px; padding:30px; text-align:center;"
        st.markdown(f'<div style="{box_style}"><h1 style="color:white; margin:0; font-size:2.2em;">{word_txt}</h1>{ex_html}</div>', unsafe_allow_html=True)
        st.write("<br>", unsafe_allow_html=True)
        
        c1, c2, c3 = st.columns([1, 1.2, 1])
        if c1.button("⬅️ Wstecz", use_container_width=True): 
            st.session_state.f_idx -= 1
            st.session_state.f_flipped = False
            st.rerun()
        if c2.button("🔄 OBRÓĆ", type="primary", use_container_width=True): 
            st.session_state.f_flipped = not st.session_state.f_flipped
            st.rerun()
        if c3.button("Dalej ➡️", use_container_width=True): 
            st.session_state.f_idx += 1
            st.session_state.f_flipped = False
            st.rerun()
            
        if st.session_state.f_flipped: 
            audio_txt = f"{c['de']} . . "
            if c.get("examples"):
                audio_txt += " . . ".join([e['de'] for e in c["examples"]])
            play_audio(audio_txt)

# --- 📸 SKANER AI ---
elif choice == "📸 Skaner AI":
    update_activity("Skaner")
    src = st.camera_input("Zrób zdjęcie")
    up = st.file_uploader("Lub wybierz plik")
    
    if (src or up) and st.button("🚀 ANALIZUJ", use_container_width=True):
        if not API_KEY:
            st.error("Brak klucza API w ustawieniach.")
        else:
            try:
                with st.spinner("AI analizuje..."):
                    genai.configure(api_key=API_KEY)
                    model = genai.GenerativeModel('gemini-1.5-flash')
                    img = Image.open(src or up).convert("RGB")
                    
                    req_txt = "Extract German-Polish vocabulary. Return ONLY JSON list: [{'de':'...', 'pl':'...', 'category':'Skaner', 'examples':[{'de':'...', 'pl':'...'}]}]"
                    res = model.generate_content([req_txt, img])
                    data = parse_ai_json(res.text)
                    
                    if data:
                        st.session_state.pending = data
                        st.session_state.user_data["historical_cost"] += 0.015
                        st.rerun()
                    else: 
                        st.error(f"Otrzymano błędny format: {res.text}")
            except Exception as e: 
                st.error(f"Błąd AI: {e}")
            
    if "pending" in st.session_state:
        df_pending = pd.DataFrame(st.session_state.pending)
        ed = st.data_editor(df_pending, use_container_width=True)
        if st.button("✅ ZAPISZ DO BAZY", use_container_width=True):
            for w in ed.to_dict('records'):
                w["next_review"] = str(today_dt)
                w["date_added"] = str(today_dt)
                if "category" not in w:
                    w["category"] = "Skaner"
                st.session_state.flashcards.append(w)
            save_j(get_p(u, "flashcards"), st.session_state.flashcards)
            del st.session_state.pending
            st.rerun()

# --- 📦 GENERATOR SŁÓW ---
elif choice == "📦 Generator słów":
    update_activity("Generator")
    cols = st.columns(5)
    lvls = ["A1", "A2", "B1", "B2", "C1"]
    
    for i, lvl in enumerate(lvls):
        if cols[i].button(lvl, use_container_width=True):
            if not API_KEY:
                st.error("Brak klucza API w ustawieniach.")
            else:
                with st.spinner(f"AI generuje słówka dla {lvl}..."):
                    try:
                        genai.configure(api_key=API_KEY)
                        model = genai.GenerativeModel('gemini-1.5-flash')
                        exist = [x['de'] for x in st.session_state.flashcards[:300]]
                        
                        prompt = f"Generate 25 unique German words level {lvl}. Polish categories. Skip: {exist}. Return ONLY JSON: [{{'de':'...', 'pl':'...', 'category':'...', 'examples':[{{'de':'...', 'pl':'...'}}]}}]"
                        
                        res = model.generate_content(prompt)
                        data = parse_ai_json(res.text)
                        
                        if data:
                            added = 0
                            for w in data:
                                word_de = w['de'].lower()
                                exist_lower = [x['de'].lower() for x in st.session_state.flashcards]
                                if word_de not in exist_lower:
                                    w["next_review"] = str(today_dt)
                                    w["date_added"] = str(today_dt)
                                    cat_name = w.get('category', 'Inne')
                                    w["category"] = f"{lvl} - {cat_name}"
                                    st.session_state.flashcards.append(w)
                                    added += 1
                                    
                            cost = st.session_state.user_data.get("historical_cost", 0.0)
                            st.session_state.user_data["historical_cost"] = cost + 0.01
                            save_j(get_p(u, "flashcards"), st.session_state.flashcards)
                            st.success(f"Dodano {added} nowych słówek!")
                            st.rerun()
                        else: 
                            st.error(f"Zły format JSON: {res.text}")
                    except Exception as e: 
                        st.error(f"Błąd AI: {e}")

# --- 🕹️ QUIZ ---
elif choice == "🕹️ Quiz":
    update_activity("Quiz")
    all_c = st.session_state.flashcards
    
    if len(all_c) < 4: 
        st.warning("Dodaj min. 4 słówka do bazy!")
    else:
        if "q_c" not in st.session_state:
            t = random.choice(all_c)
            opts = []
            for x in all_c:
                if x['pl'] != t['pl']:
                    opts.append(x['pl'])
            
            if len(opts) >= 3:
                opts = random.sample(opts, 3)
            opts.append(t['pl'])
            random.shuffle(opts)
            
            st.session_state.q_c = t
            st.session_state.q_a = t['pl']
            st.session_state.q_o = opts
            st.session_state.q_s = "ask"
            
        st.write(f"### Jak przetłumaczysz: **{st.session_state.q_c['de']}**")
        
        if st.session_state.q_s == "ask":
            for o in st.session_state.q_o:
                if st.button(o, key=o, use_container_width=True):
                    st.session_state.u_q = o
                    st.session_state.q_s = "res"
                    st.rerun()
        else:
            if st.session_state.get("u_q") == st.session_state.q_a: 
                st.success("✅ Brawo! To poprawna odpowiedź.")
            else: 
                st.error(f"❌ Błąd. Poprawnie: {st.session_state.q_a}")
                
            c_word = st.session_state.q_c
            audio_txt = f"{c_word['de']} . . "
            if c_word.get('examples'):
                audio_txt += " . . ".join([e['de'] for e in c_word['examples']])
            play_audio(audio_txt)
            
            if st.button("Dalej", use_container_width=True): 
                del st.session_state.q_c
                st.rerun()

# --- ➕ DODAJ RĘCZNIE ---
elif choice == "➕ Dodaj":
    st.header("➕ Dodaj słówko ręcznie")
    update_activity("Dodaj")
    with st.form("manual_form"):
        de = st.text_input("Słówko po niemiecku")
        pl = st.text_input("Tłumaczenie po polsku")
        kat = st.text_input("Kategoria (np. Dom, Praca)")
        if st.form_submit_button("Zapisz do bazy", use_container_width=True):
            if de and pl:
                new_card = {
                    "de": de, 
                    "pl": pl, 
                    "category": kat or "Inne", 
                    "next_review": str(today_dt), 
                    "date_added": str(today_dt), 
                    "examples": []
                }
                st.session_state.flashcards.append(new_card)
                save_j(get_p(u,"flashcards"), st.session_state.flashcards)
                st.success("Słówko dodane!")

# --- 📖 SŁOWNIK ---
elif choice == "📖 Słownik":
    update_activity("Słownik")
    all_cats = [c.get("category", "Inne") for c in st.session_state.flashcards]
    kats = ["Wszystkie"] + sorted(list(set(all_cats)))
    f_kat = st.selectbox("📁 Filtruj kategorię:", kats)
    search = st.text_input("🔍 Szukaj słówka:")
    
    for i, c in enumerate(st.session_state.flashcards):
        match_kat = (f_kat == "Wszystkie" or c.get("category") == f_kat)
        match_txt = (search.lower() in c['de'].lower() or search.lower() in c['pl'].lower())
        
        if match_kat and match_txt:
            with st.expander(f"📝 {c['de']} — {c['pl']}"):
                with st.form(f"ed_{i}"):
                    n_de = st.text_input("Niemiecki", c['de'])
                    n_pl = st.text_input("Polski", c['pl'])
                    n_ka = st.text_input("Kategoria", c.get('category','Inne'))
                    c1, c2 = st.columns(2)
                    if c1.form_submit_button("Zapisz zmiany"):
                        c["de"] = n_de
                        c["pl"] = n_pl
                        c["category"] = n_ka
                        save_j(get_p(u,"flashcards"), st.session_state.flashcards)
                        st.rerun()
                    if c2.form_submit_button("Usuń słówko"):
                        st.session_state.flashcards.pop(i)
                        save_j(get_p(u,"flashcards"), st.session_state.flashcards)
                        st.rerun()

# --- 📊 STATYSTYKI ---
elif choice == "📊 Statystyki":
    update_activity("Statystyki")
    df = pd.DataFrame(st.session_state.flashcards)
    if not df.empty:
        c1, c2, c3 = st.columns(3)
        c1.metric("Słów w bazie", len(df))
        c2.metric("Passa nauki", f"{st.session_state.user_data.get('streak', 0)} dni")
        
        def is_mastered(x):
            try:
                days_diff = (date.fromisoformat(x) - today_dt).days
                return days_diff >= 7
            except:
                return False
                
        opanowane = len(df[df['next_review'].apply(is_mastered)])
        c3.metric("Opanowane (7d+)", opanowane)
        
        st.subheader("Plan powtórek")
        stats_data = []
        for i in range(10):
            target_date = (today_dt + timedelta(days=i)).strftime("%d.%m")
            target_iso = str(today_dt + timedelta(days=i))
            count = len(df[df['next_review'] == target_iso])
            stats_data.append({"Data": target_date, "Słów": count})
            
        stats_df = pd.DataFrame(stats_data)
        st.bar_chart(stats_df.set_index("Data"))

# --- ⚙️ MOJE KONTO ---
elif choice == "⚙️ Moje Konto":
    st.header("⚙️ Zarządzanie Kontem")
    update_activity("Konto")
    
    if "del_msg" in st.session_state: 
        st.success(st.session_state.del_msg)
        del st.session_state.del_msg
        
    with st.expander("🔑 Zmień hasło"):
        with st.form("pw_form"):
            old_p = st.text_input("Stare hasło", type="password")
            new_p = st.text_input("Nowe hasło", type="password")
            conf_p = st.text_input("Powtórz nowe hasło", type="password")
            if st.form_submit_button("Zmień hasło"):
                db = load_j(AUTH_FILE, {})
                if db.get(u) == hash_pw(old_p) and new_p == conf_p:
                    db[u] = hash_pw(new_p)
                    save_j(AUTH_FILE, db)
                    st.success("Hasło zmienione pomyślnie!")
                else: 
                    st.error("Błąd haseł. Sprawdź poprawność.")
    
    st.divider()
    st.subheader("⚠️ Usuwanie danych")
    conf_del = st.checkbox("Potwierdzam chęć trwałego usunięcia danych")
    lvls = ["A1", "A2", "B1", "B2", "C1"]
    col_del = st.columns(5)
    
    for i, lvl in enumerate(lvls):
        if col_del[i].button(f"Usuń {lvl}", disabled=not conf_del, use_container_width=True):
            before = len(st.session_state.flashcards)
            new_cards = []
            for x in st.session_state.flashcards:
                if lvl not in str(x.get('category','')):
                    new_cards.append(x)
                    
            st.session_state.flashcards = new_cards
            save_j(get_p(u, "flashcards"), st.session_state.flashcards)
            removed_count = before - len(st.session_state.flashcards)
            st.session_state.del_msg = f"Usunięto {removed_count} słówek z poziomu {lvl}!"
            st.rerun()
    
    if st.button("🗑️ USUŃ WSZYSTKO (RESET BAZY)", type="primary", disabled=not conf_del, use_container_width=True):
        save_j(get_p(u, "flashcards"), [])
        st.session_state.flashcards = []
        st.rerun()

# --- 👑 ADMIN ---
elif choice == "👑 Admin":
    st.header("👑 Panel Admina Master")
    st.warning("⚠️ Dane z komputera (Lokalne) i linku (Chmura) są oddzielne.")
    
    users = load_j(AUTH_FILE, {})
    adm_list = []
    
    # Inicjalizacja licznika czasu dla wszystkich modułów
    global_time = {}
    for m in MODULE_ORDER:
        global_time[m] = 0.0
        
    m1, m2 = st.columns(2)
    
    for usr in users:
        ud = load_j(get_p(usr, "user_data"), {})
        ub = load_j(get_p(usr, "flashcards"), [])
        df_u = pd.DataFrame(ub)
        
        mastery = "0%"
        ai_n = 0
        
        if not df_u.empty:
            opanowane = 0
            for x in df_u['next_review']:
                try:
                    if (date.fromisoformat(x) - today_dt).days >= 7:
                        opanowane += 1
                except:
                    pass
            mastery = f"{round((opanowane/len(df_u))*100)}%"
            
            ai_n = len(df_u[df_u['category'].str.contains('Skaner', case=False, na=False)])
            
        t_s = ud.get("time_stats", {})
        
        # Bezpieczne dodawanie czasu (Naprawa SyntaxError)
        for m in MODULE_ORDER: 
            added_time = t_s.get(m, 0.0)
            global_time[m] = global_time[m] + added_time
            
        time_strings = []
        for m, s in t_s.items():
            if s > 15:
                time_strings.append(f"{m[0]}:{round(s/60)}m")
        u_times = ", ".join(time_strings)
        
        adm_list.append({
            "Użytkownik": usr, 
            "Słów": len(ub), 
            "AI (Skaner)": ai_n, 
            "% Wiedzy": mastery, 
            "Ostatnio": ud.get("last_seen", "Nigdy"), 
            "Czas": u_times or "Brak"
        })
    
    total_words = sum(x['Słów'] for x in adm_list)
    m1.metric("Łącznie słówek w systemie", total_words)
    
    total_spent = 0.0
    for usr_n in users:
        usr_data = load_j(get_p(usr_n, 'user_data'), {})
        total_spent += usr_data.get('historical_cost', 0.0)
        
    m2.metric("Pozostały Bonus AI", f"{BONUS_START - total_spent:.2f} PLN")
    
    st.table(pd.DataFrame(adm_list))
    
    total_g = sum(global_time.values())
    if total_g > 0:
        vals = []
        labels = []
        for m in MODULE_ORDER:
            val = global_time[m]
            vals.append(val)
            labels.append(f"{m}: {round(val/60,1)} min")
        
        fig = go.Figure(
            data=[
                go.Bar(
                    x=MODULE_ORDER, 
                    y=vals, 
                    text=labels, 
                    textposition='auto', 
                    marker_color='#1E88E5'
                )
            ]
        )
        fig.update_layout(template="plotly_dark", height=450)
        st.plotly_chart(fig, use_container_width=True)
