import streamlit as st
import json
import os
import random
import re
import hashlib
import pandas as pd
import secrets
import base64
from datetime import datetime, date, timedelta
from io import BytesIO
from PIL import Image
import time
import plotly.graph_objects as go

# Importujemy bibliotekę OpenAI
from openai import OpenAI

# --- KONFIGURACJA ---
APP_VERSION = "V164 (OpenAI Perfected)"
ADMIN_USER = "wobo"
AUTH_FILE = "users_auth.json"
SESSIONS_FILE = "sessions.json"

# Pobieranie klucza API (OpenAI)
API_KEY = st.secrets.get("OPENAI_API_KEY") or st.secrets.get("GEMINI_API_KEY") or st.session_state.get("manual_api_key", "")

MODULE_ORDER = [
    "Powtórki", "Trening", "Quiz", "Fiszki", 
    "Skaner", "Generator", "Dodaj", "Słownik"
]

# --- SYSTEM POMOCNICZY ---
def hash_pw(pw): 
    encoded = str.encode(pw)
    return hashlib.sha256(encoded).hexdigest()

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

# --- SILNIK AI: OPENAI ---
def get_openai_response(prompt_text, img_obj=None):
    if not API_KEY:
        raise Exception("Brak klucza API. Upewnij się, że wkleiłeś klucz OpenAI.")
        
    client = OpenAI(api_key=API_KEY)
    
    messages = [
        {"role": "system", "content": "You are a helpful assistant that outputs ONLY valid JSON."}
    ]
    
    if img_obj:
        buffered = BytesIO()
        img_obj.thumbnail((800, 800))
        img_obj.save(buffered, format="JPEG")
        img_b64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
        
        messages.append({
            "role": "user",
            "content": [
                {"type": "text", "text": prompt_text},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}}
            ]
        })
    else:
        messages.append({"role": "user", "content": prompt_text})
        
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        response_format={"type": "json_object"}
    )
    
    return response.choices[0].message.content

# --- LOGOWANIE ---
if "auth" not in st.session_state:
    st.session_state.auth = False
    if "token" in st.query_params:
        ss = load_j(SESSIONS_FILE, {})
        tk = st.query_params["token"]
        if tk in ss:
            st.session_state.auth = True
            st.session_state.user = ss[tk]

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
                st.success("Gotowe! Możesz się zalogować.")
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
    last_t = st.session_state.user_data.get("last_ts", curr)
    delta = curr - last_t
    
    if 0 < delta < 600:
        stats = st.session_state.user_data.get("time_stats", {})
        m_clean = m.strip("📅 🚀 🕹️ 🎴 📸 📦 ➕ 📖 📊 ⚙️ ")
        curr_t = stats.get(m_clean, 0.0)
        stats[m_clean] = curr_t + delta
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
val_streak = st.session_state.user_data.get('streak', 0)
st.sidebar.info(f"🔥 Passa: **{val_streak} dni**")

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
    for k in ["n_c", "q_c", "q_s", "f_idx", "f_flipped", "pending", "success_msg"]:
        if k in st.session_state: 
            del st.session_state[k]
    st.session_state.n_m = "ask"
    st.session_state.u_a = ""
    st.session_state.l_c = choice

def is_correct(a, c):
    u_ans = a.strip().lower()
    c_ans = [s.strip().lower() for s in re.split(r'[/,;]', c)]
    return u_ans in c_ans

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
        is_due = c.get("next_review", str(today_dt)) <= str(today_dt)
        if not is_r or is_due:
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
                    txt_ex = f"🇩🇪 {ex['de']}<br>🇵🇱 {ex['pl']}"
                    st.markdown(txt_ex, unsafe_allow_html=True)
                st.write("")
                
            audio_txt = f"{c['de']} . . "
            if c.get("examples"):
                audio_txt += " . . ".join([e['de'] for e in c["examples"]])
            play_audio(audio_txt)
            
            if is_r:
                st.write("---")
                c1, c2, c3 = st.columns(3)
                d = None
                if c1.button("🔴 Słabo", use_container_width=True): d = 1
                if c2.button("🟡 Średnio", use_container_width=True): d = 3
                if c3.button("🟢 Dobrze", use_container_width=True): d = 7
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
    sel_kat = st.selectbox("🎯 Wybierz:", kats)
    
    cards = []
    for c in st.session_state.flashcards:
        if sel_kat == "Wszystkie" or c.get("category") == sel_kat:
            cards.append(c)
    
    if cards:
        if "f_idx" not in st.session_state: 
            st.session_state.f_idx = 0
        if "f_flipped" not in st.session_state: 
            st.session_state.f_flipped = False
            
        cur_idx = st.session_state.f_idx % len(cards)
        c = cards[cur_idx]
        word_txt = c["pl"] if st.session_state.f_flipped else c["de"]
        ex_html = ""
        
        if st.session_state.f_flipped and c.get("examples"):
            for ex in c["examples"]:
                de_txt = f"<span style='color:#FFEB3B;'>🇩🇪 {ex['de']}</span>"
                pl_txt = f"<span style='color:white;'>🇵🇱 {ex['pl']}</span>"
                ex_html += f"<div style='margin-top:15px;'>{de_txt}<br>{pl_txt}</div>"
        
        box_style = "min-height:300px; display:flex; flex-direction:column; align-items:center; justify-content:center; background:black; border:3px solid #FF5252; border-radius:30px; text-align:center;"
        st.markdown(f'<div style="{box_style}"><h1 style="color:white;">{word_txt}</h1>{ex_html}</div>', unsafe_allow_html=True)
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

# --- 📸 SKANER AI (OPENAI) ---
elif choice == "📸 Skaner AI":
    update_activity("Skaner")
    
    if "success_msg" in st.session_state:
        st.success(st.session_state.success_msg)
        del st.session_state.success_msg
        
    src = st.camera_input("Zrób zdjęcie tekstu/słówek")
    up = st.file_uploader("Lub wybierz plik ze zdjęciem")
    
    if (src or up) and st.button("🚀 ANALIZUJ ZDJĘCIE", use_container_width=True):
        if not API_KEY:
            st.error("Brak klucza API OpenAI.")
        else:
            try:
                with st.spinner("Skanowanie i tworzenie przykładowych zdań..."):
                    img = Image.open(src or up).convert("RGB")
                    
                    # Mocny prompt wymuszający zdania i polskie kategorie
                    req_txt = (
                        "Extract German vocabulary from this image and translate to Polish. "
                        "You MUST generate 1-2 practical German example sentences (with Polish translations) for EACH extracted word to provide context. "
                        "Assign a broad, descriptive category in POLISH to each word (e.g., 'Jedzenie', 'Praca', 'Dom'). Do NOT use grammatical terms like 'Nomen'. "
                        "Output a JSON object containing a single key 'flashcards', which is a list of objects in this exact format: "
                        "[{'de':'word', 'pl':'translation', 'category':'Polish Category Name', 'examples':[{'de':'sentence', 'pl':'sentence translation'}]}]"
                    )
                    
                    res_text = get_openai_response(req_txt, img_obj=img)
                    data = parse_ai_json(res_text)
                    
                    if isinstance(data, dict) and "flashcards" in data:
                        data = data["flashcards"]
                    
                    if data and isinstance(data, list):
                        st.session_state.pending = data
                        c_cost = st.session_state.user_data.get("historical_cost", 0.0)
                        st.session_state.user_data["historical_cost"] = c_cost + 0.015
                        st.rerun()
                    else: 
                        st.error("AI odpowiedziało, ale nie w formacie JSON listy fiszek.")
            except Exception as e: 
                st.error(f"Błąd OpenAI: {e}")
            
    if "pending" in st.session_state:
        st.info("Poniżej znajdziesz zeskanowane słówka oraz wygenerowane do nich zdania. Możesz je edytować przed zapisem.")
        df_pending = pd.DataFrame(st.session_state.pending)
        ed = st.data_editor(df_pending, use_container_width=True)
        if st.button("✅ ZAPISZ DO BAZY", use_container_width=True):
            added_count = 0
            for w in ed.to_dict('records'):
                w["next_review"] = str(today_dt)
                w["date_added"] = str(today_dt)
                if "category" not in w:
                    w["category"] = "Skaner"
                if "examples" not in w or str(w["examples"]) == "nan":
                    w["examples"] = []
                st.session_state.flashcards.append(w)
                added_count += 1
            save_j(get_p(u, "flashcards"), st.session_state.flashcards)
            del st.session_state.pending
            st.session_state.success_msg = f"🎉 Sukces! Dodano {added_count} zeskanowanych słówek ze zdaniami do bazy!"
            st.rerun()

# --- 📦 GENERATOR SŁÓW (OPENAI) ---
elif choice == "📦 Generator słów":
    update_activity("Generator")
    
    if "success_msg" in st.session_state:
        st.success(st.session_state.success_msg)
        del st.session_state.success_msg
        
    cols = st.columns(5)
    lvls = ["A1", "A2", "B1", "B2", "C1"]
    
    for i, lvl in enumerate(lvls):
        if cols[i].button(lvl, use_container_width=True):
            if not API_KEY:
                st.error("Brak klucza API OpenAI.")
            else:
                with st.spinner(f"Generowanie dokładnie 25 słówek i zdań kontekstowych dla {lvl}..."):
                    try:
                        exist = []
                        for x in st.session_state.flashcards[:300]:
                            exist.append(x['de'])
                            
                        # Żelazny prompt
                        prompt = (
                            f"Generate EXACTLY 25 unique German words suitable for level {lvl}. You MUST provide exactly 25 words, no less. "
                            "Assign a diverse, descriptive category in POLISH to each word (e.g., 'Rodzina', 'Podróże', 'Zdrowie', 'Czynności'). DO NOT use grammatical categories like 'Nomen' or 'Verben'. "
                            "You MUST include 1-2 practical example sentences (German and Polish translation) for EACH word. "
                            f"Skip these words: {exist}. "
                            "Output a JSON object containing a single key 'flashcards', which is a list of objects in this exact format: "
                            "[{'de':'word', 'pl':'translation', 'category':'Polish Category Name', 'examples':[{'de':'sentence', 'pl':'sentence translation'}]}]"
                        )
                        
                        res_text = get_openai_response(prompt)
                        data = parse_ai_json(res_text)
                        
                        if isinstance(data, dict) and "flashcards" in data:
                            data = data["flashcards"]
                        
                        if data and isinstance(data, list):
                            added = 0
                            for w in data:
                                word_de = w['de'].lower()
                                exist_lower = [x['de'].lower() for x in st.session_state.flashcards]
                                if word_de not in exist_lower:
                                    w["next_review"] = str(today_dt)
                                    w["date_added"] = str(today_dt)
                                    cat_name = w.get('category', 'Inne')
                                    # Czasami AI dodaje poziom, zapobiegamy powielaniu
                                    if lvl not in cat_name:
                                        w["category"] = f"{lvl} - {cat_name}"
                                    else:
                                        w["category"] = cat_name
                                        
                                    if "examples" not in w:
                                        w["examples"] = []
                                    st.session_state.flashcards.append(w)
                                    added += 1
                                    
                            c_cost = st.session_state.user_data.get("historical_cost", 0.0)
                            st.session_state.user_data["historical_cost"] = c_cost + 0.01
                            save_j(get_p(u, "flashcards"), st.session_state.flashcards)
                            
                            st.session_state.success_msg = f"🎉 Sukces! Pomyślnie wygenerowano i dodano {added} nowych słówek (wraz ze zdaniami) do Twojej bazy!"
                            st.rerun()
                        else: 
                            st.error("Zły format JSON wygenerowany przez AI.")
                    except Exception as e: 
                        st.error(f"Błąd OpenAI: {e}")

# --- 🕹️ QUIZ ---
elif choice == "🕹️ Quiz":
    update_activity("Quiz")
    all_c = st.session_state.flashcards
    
    ilosc_fiszki = len(all_c)
    if ilosc_fiszki < 4: 
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
            
        word_de_q = st.session_state.q_c['de']
        st.write(f"### Jak przetłumaczysz: **{word_de_q}**")
        
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
                poprawna = st.session_state.q_a
                st.error(f"❌ Błąd. Poprawnie: {poprawna}")
                
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
        val_streak = st.session_state.user_data.get('streak', 0)
        c2.metric("Passa nauki", f"{val_streak} dni")
        
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
    
    btn_del_all = st.button("🗑️ USUŃ WSZYSTKO (RESET BAZY)", type="primary", disabled=not conf_del, use_container_width=True)
    if btn_del_all:
        save_j(get_p(u, "flashcards"), [])
        st.session_state.flashcards = []
        st.rerun()

# --- 👑 ADMIN ---
elif choice == "👑 Admin":
    st.header("👑 Panel Admina Master")
    
    users = load_j(AUTH_FILE, {})
    adm_list = []
    
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
            
            for cat in df_u['category']:
                if isinstance(cat, str) and 'skaner' in cat.lower():
                    ai_n += 1
            
        t_s = ud.get("time_stats", {})
        
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
    
    # Zmiana: Szacunkowe koszty w aplikacji a prawdziwe w OpenAI
    total_spent = 0.0
    for usr_n in users:
        usr_data = load_j(get_p(usr_n, 'user_data'), {})
        total_spent += usr_data.get('historical_cost', 0.0)
        
    m2.metric("Szacunkowy koszt w apce", f"{total_spent:.2f} PLN")
    
    st.markdown("[🔗 **Sprawdź prawdziwe i dokładne zużycie środków bezpośrednio na koncie OpenAI (Billing/Usage)**](https://platform.openai.com/usage)")
    
    st.table(pd.DataFrame(adm_list))
    
    total_g = sum(global_time.values())
    if total_g > 0:
        vals = []
        labels = []
        for m in MODULE_ORDER:
            val = global_time[m]
            vals.append(val)
            labels.append(f"{m}: {round(val/60,1)} min")
        
        my_bar = go.Bar(
            x=MODULE_ORDER, 
            y=vals, 
            text=labels, 
            textposition='auto', 
            marker_color='#1E88E5'
        )
        
        fig = go.Figure(data=[my_bar])
        fig.update_layout(template="plotly_dark", height=450)
        st.plotly_chart(fig, use_container_width=True)
