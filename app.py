import streamlit as st
import json
import random
import re
import hashlib
import pandas as pd
import time
import base64
import pytz
from datetime import datetime, date, timedelta
from io import BytesIO
from gtts import gTTS
from openai import OpenAI
from PIL import Image
import plotly.graph_objects as go
from postgrest import SyncPostgrestClient

# --- 1. KONFIGURACJA (V315 - Full Imports & Multilang Support) ---
import streamlit as st
import json
import random
import re
import hashlib
import pandas as pd
import time
import base64
import pytz
import unicodedata
from datetime import datetime, date, timedelta
from io import BytesIO
from gtts import gTTS
from openai import OpenAI
from PIL import Image
import plotly.graph_objects as go
import plotly.express as px  # <-- KLUCZOWY IMPORT DLA WYKRESÓW W STATYSTYKACH
from postgrest import SyncPostgrestClient

# USTAWIENIA STRONY (Musi być na samym początku skryptu)
st.set_page_config(
    page_title="Niemiecki Master",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded"
)

# SEKRETY I KLUCZE
SUPABASE_URL = st.secrets.get("SUPABASE_URL", "")
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY", "")
API_KEY = st.secrets.get("OPENAI_API_KEY", "")

APP_VERSION = "V315 (Multilang AI + Fixed Stats)"
ADMIN_USER = "wobo"

# SŁOWNIK MAPUJĄCY MODUŁY DO STATYSTYK CZASU
CLEAN_TIME_LABELS = {
    "powtorki": "Pow", 
    "trening": "Trn", 
    "quiz": "Qiz", 
    "fiszki": "Fis",
    "testy": "Tst", 
    "memory": "Mem", 
    "warsztat": "War", 
    "konstruktor": "Kon",
    "lingwistyczny waz": "Wan",
    "balonowy wyscig": "Bal",
    "skaner": "Skn", 
    "generator": "Gen", 
    "dodaj": "Dod",
    "slownik": "Słn", 
    "statystyki": "Sta", 
    "konto": "Kon", 
    "admin": "Adm"
}

# MAPOWANIE JĘZYKÓW
LANG_MAP = {
    "Niemiecki": {"code": "de", "label": "🇩🇪 Niemiecki"}, 
    "Czeski": {"code": "cs", "label": "🇨🇿 Czeski"}
}

# --- 2. SILNIK BAZY I POMOCNIKI (V221 - Multilang Audio, AI & Diacritics Normalize) ---
import unicodedata

def get_db():
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    return SyncPostgrestClient(f"{SUPABASE_URL}/rest/v1", headers=headers)

def hash_pw(pw): 
    return hashlib.sha256(str.encode(pw)).hexdigest()

def normalize_text(t):
    """
    Zaawansowana normalizacja tekstu:
    1. Małe litery i czyszczenie spacji.
    2. Zamiana niemieckich umlautów na formy ae/oe/ue/ss.
    3. Usunięcie wszystkich znaków diakrytycznych (czeskie haczki, polskie ogonki itp.).
    """
    if not t: return ""
    
    # Podstawowe czyszczenie
    t = str(t).lower().strip()
    
    # Specjalna obsługa niemieckich znaków (zgodnie z Twoim standardem)
    t = t.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    
    # Deakcentacja - usuwanie haczków, kresek i ogonków (np. č -> c, ł -> l, á -> a)
    # Rozbijamy znaki na bazę i akcent, a następnie filtrujemy akcenty (kategoria 'Mn')
    t = "".join(
        c for c in unicodedata.normalize('NFD', t)
        if unicodedata.category(c) != 'Mn'
    )
    
    # Obsługa specyficznych znaków, które NFD może pominąć (np. przekreślone L)
    t = t.replace("ł", "l")
    
    return t

def get_openai_response(prompt_text, img_obj=None):
    if not API_KEY: raise Exception("Brak klucza API OpenAI.")
    client = OpenAI(api_key=API_KEY)
    
    messages = [{"role": "system", "content": "Jesteś ekspertem językowym. Odpowiadaj TYLKO w JSON. Kategorie po polsku, przykłady jako lista {de, pl}."}]
    
    if img_obj:
        buf = BytesIO()
        img_obj.thumbnail((800, 800))
        img_obj.save(buf, format="JPEG")
        img_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        messages.append({"role": "user", "content": [
            {"type": "text", "text": prompt_text}, 
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}}
        ]})
    else:
        messages.append({"role": "user", "content": prompt_text})
        
    res = client.chat.completions.create(
        model="gpt-4o-mini", 
        messages=messages, 
        response_format={"type": "json_object"}
    )
    return res.choices[0].message.content

def play_audio(txt, ex_txt=None, lang='de'):
    """
    Odtwarza wymowę słowa i opcjonalnego przykładu w wybranym języku (de, cs, pl).
    """
    try:
        full_text = f"{txt}. . . . {ex_txt}" if ex_txt else txt
        f = BytesIO()
        tts = gTTS(text=full_text, lang=lang)
        tts.write_to_fp(f)
        f.seek(0)
        st.audio(f, format="audio/mp3", autoplay=True)
    except Exception as e:
        pass

# --- 3. FUNKCJE DANYCH (V7 - Polska strefa czasowa + Fix Resetu) ---
def get_now_pl():
    """Pomocnik zwracający aktualny czas w Polsce jako string."""
    tz_pl = pytz.timezone('Europe/Warsaw')
    return datetime.now(tz_pl).strftime("%d.%m %H:%M")

def load_user_data(username):
    db = get_db()
    res = db.table("user_data").select("*").eq("username", username).execute()
    today_str = date.today().isoformat()

    if res.data:
        data = res.data[0]
        
        # Pobieramy datę ostatniej wizyty do logiki resetu minut
        last_visit = data.get("last_visit_date")
        if not last_visit:
            last_visit = data.get("last_date", "2000-01-01")
        
        # Jeśli to pierwsze wejście dzisiaj - czyścimy licznik minut
        if last_visit != today_str:
            data["time_stats"] = {}
            data["last_visit_date"] = today_str
            # Przy okazji aktualizujemy czas ostatniej aktywności na polski
            data["last_seen"] = get_now_pl()
            save_user_data(username, data)
        
        return data

    # INICJALIZACJA NOWEGO UŻYTKOWNIKA
    init = {
        "username": username, 
        "streak": 0, 
        "historical_cost": 0.0, 
        "time_stats": {}, 
        "last_ts": time.time(), 
        "last_seen": get_now_pl(), # Czas PL
        "last_date": "2000-01-01", 
        "last_visit_date": today_str,
        "test_history": [],
        "settings": {"daily_goal": 20, "auto_audio": True, "show_hints": True}
    }
    db.table("user_data").insert(init).execute()
    return init

def save_user_data(username, data):
    d = data.copy()
    if "username" in d:
        del d["username"]
    
    if "time_stats" in d and isinstance(d["time_stats"], dict):
        d["time_stats"] = {str(k): float(v) for k, v in d["time_stats"].items()}
    
    if not d.get("last_date"):
        d["last_date"] = "2000-01-01"
    
    # Zawsze aktualizujemy datę wizyty i czas aktywności (czas PL) przy zapisie
    d["last_visit_date"] = date.today().isoformat()
    d["last_seen"] = get_now_pl()

    get_db().table("user_data").update(d).eq("username", username).execute()

def load_flashcards(username):
    db = get_db()
    res = db.table("flashcards").select("*").eq("username", username).order("id").execute()
    cards = res.data if res.data else []
    for c in cards:
        if not c.get("origin"): c["origin"] = "Dodaj"
    return cards

def save_word(username, word_obj):
    db = get_db()
    word_obj["username"] = username
    if "examples" not in word_obj: word_obj["examples"] = []
    db.table("flashcards").insert(word_obj).execute()

def update_word(word_id, fields):
    try:
        if "level" in fields and fields["level"] is not None:
            fields["level"] = int(fields["level"])
        if "interval" in fields and fields["interval"] is not None:
            fields["interval"] = int(fields["interval"])
        get_db().table("flashcards").update(fields).eq("id", word_id).execute()
    except Exception as e:
        st.error(f"⚠️ Błąd bazy danych (update_word): {e}")

def delete_word(word_id): 
    get_db().table("flashcards").delete().eq("id", word_id).execute()

# --- 4. LOGOWANIE I REJESTRACJA (V291 - Mobile Responsive Title) ---
if "auth" not in st.session_state:
    st.session_state.auth = False
    if "token" in st.query_params:
        u_tk = st.query_params["token"]
        st.session_state.auth, st.session_state.user = True, u_tk

if not st.session_state.auth:
    # --- NOWY, RESPNSYWNY TYTUŁ ---
    # Używamy markdown z HTML/CSS, aby czcionka skalowała się (vw) i nie łamała (white-space)
    st.markdown("""
        <style>
            .mobile-title {
                font-size: 8vw; /* Skaluje się zależnie od szerokości ekranu */
                font-weight: bold;
                white-space: nowrap; /* Wymusza jedną linijkę */
                overflow: hidden;
                text-overflow: ellipsis; /* Dodaje wielokropek, gdyby jednak było za ciasno */
                margin-bottom: 20px;
                display: flex;
                align-items: center;
                gap: 10px;
            }
            /* Dla większych ekranów (tablet/PC) ustalamy stały, ładny rozmiar */
            @media (min-width: 768px) {
                .mobile-title {
                    font-size: 40px;
                }
            }
        </style>
        <div class="mobile-title">
            <span>🚀</span>
            <span>Niemiecki Master</span>
        </div>
    """, unsafe_allow_html=True)
    # ---------------------------------

    t1, t2 = st.tabs(["🔐 Logowanie", "📝 Rejestracja"])
    db = get_db()
    with t1:
        un = st.text_input("Użytkownik", key="l_u").lower().strip()
        pw = st.text_input("Hasło", type="password", key="l_p")
        
        remember_me = st.checkbox("Zapamiętaj mnie na tym urządzeniu", value=True)
        
        if st.button("Zaloguj się", use_container_width=True, type="primary"):
            res = db.table("users_auth").select("*").eq("username", un).execute()
            if res.data and res.data[0]["password_hash"] == hash_pw(pw):
                st.session_state.auth, st.session_state.user = True, un
                if remember_me:
                    st.query_params["token"] = un
                else:
                    st.query_params.clear()
                st.rerun()
            else:
                st.error("Błędne dane logowania")
    with t2:
        rn = st.text_input("Nowy użytkownik", key="r_u").lower().strip()
        rp = st.text_input("Hasło", type="password", key="r_p")
        if st.button("Załóż konto", use_container_width=True):
            if len(rn) > 2 and len(rp) > 3:
                check = db.table("users_auth").select("*").eq("username", rn).execute()
                if not check.data:
                    get_db().table("users_auth").insert({"username": rn, "password_hash": hash_pw(rp)}).execute()
                    load_user_data(rn)
                    st.success("Konto gotowe! Logowanie...")
                    time.sleep(1.5)
                    st.rerun()
                else:
                    st.error("Ten użytkownik jest już zajęty!")
            else:
                st.warning("Login (min. 3) i Hasło (min. 4) są za krótkie.")
    st.stop()

# --- 5. LOGOWANIE I ŁADOWANIE DANYCH (V252 - Fix AttributeError NoneType) ---

# Najpierw sprawdzamy, czy użytkownik jest w sesji
if "user" in st.session_state:
    u = st.session_state.user
else:
    u = None

def load_user_data(username):
    """Pobiera dane profilu użytkownika i inicjalizuje strukturę wielu języków."""
    try:
        res = get_db().table("user_data").select("*").eq("username", username).execute()
        if res.data:
            data = res.data[0]
            
            # Inicjalizacja wymaganych kluczy (DE i CS)
            required_keys = [
                "memory_scores_de", "memory_scores_cs",
                "top_balloons_de", "top_balloons_cs",
                "time_stats", "settings", "test_history"
            ]
            
            for key in required_keys:
                if key not in data or data[key] is None:
                    data[key] = [] if any(x in key for x in ["scores", "top", "history"]) else {}

            # Migracja starych rekordów do wersji _de
            if "memory_scores" in data and not data["memory_scores_de"]:
                data["memory_scores_de"] = data["memory_scores"]
            if "top_balloons" in data and not data["top_balloons_de"]:
                data["top_balloons_de"] = data["top_balloons"]

            return data
    except Exception as e:
        st.error(f"Błąd ładowania danych: {e}")
    return None

def save_user_data(username, data):
    """Zapisuje dane do Supabase, usuwając klucze techniczne."""
    if not username: return
    try:
        clean_data = {k: v for k, v in data.items() if k not in ["id", "created_at", "username", "last_ts"]}
        get_db().table("user_data").update(clean_data).eq("username", username).execute()
    except Exception as e:
        st.error(f"Błąd zapisu danych: {e}")

def update_activity(current_choice):
    """Nalicza czas nauki i zapisuje postęp."""
    # --- DODANO ZABEZPIECZENIE PRZED None ---
    if not current_choice or "user_data" not in st.session_state or not st.session_state.user_data or not u:
        return

    now = time.time()
    if "last_ts_activity" not in st.session_state:
        st.session_state.last_ts_activity = now
        return

    delta = now - st.session_state.last_ts_activity
    
    if 0 < delta < 600:
        mapping = {
            "powtorki": "Pow", "trening": "Trn", "quiz": "Qiz", "fiszki": "Fis",
            "testy": "Tst", "memory": "Mem", "warsztat": "War", "konstruktor": "Kon",
            "wąż": "Wan", "wyścig": "Bal", "statystyki": "Sta"
        }
        
        # Bezpieczne przetwarzanie tekstu
        clean_choice = "".join(filter(str.isalpha, str(current_choice).lower()))
        label = "Inn"
        for k, v in mapping.items():
            if k in clean_choice:
                label = v
                break
        
        ud = st.session_state.user_data
        stats = dict(ud.get("time_stats", {}))
        stats[label] = stats.get(label, 0.0) + delta
        st.session_state.user_data["time_stats"] = stats
        
        save_user_data(u, st.session_state.user_data)

    st.session_state.last_ts_activity = now

# --- START SESJI ---
if u and "user_data" not in st.session_state:
    st.session_state.user_data = load_user_data(u)
    if "flashcards" not in st.session_state:
        st.session_state.flashcards = load_flashcards(u)

# --- 6. SIDEBAR (V361 - Fixed NameError & Laboratorium) ---
with st.sidebar:
    # 1. Stylizacja CSS dla minimalistycznego i spójnego menu
    st.markdown("""
        <style>
            [data-testid="stSidebarNav"] {display: none;}
            .st-emotion-cache-1avcm0n {padding: 0rem 0.4rem !important;}
            .st-emotion-cache-6q9sum {padding-top: 0rem !important;}
            div.stButton > button {
                width: 100%; text-align: left; background-color: transparent;
                border: none; padding: 1px 6px !important; margin: 0px !important;
                border-radius: 4px; font-size: 0.88rem; height: auto; min-height: 28px;
            }
            .st-emotion-cache-p5msec { padding: 0rem 0.4rem !important; font-size: 0.9rem !important; }
            .stProgress > div > div > div > div { height: 6px !important; }
            .stProgress { margin-bottom: 0.3rem !important; }
            [data-testid="stVerticalBlock"] > div { gap: 0rem !important; }
            .small-text { font-size: 0.75rem; color: #aaa; margin-bottom: -2px; }
            hr { margin: 0.4rem 0 !important; opacity: 0.3; }
        </style>
    """, unsafe_allow_html=True)

    # 2. Nagłówek profilu użytkownika
    ud = st.session_state.user_data
    st.markdown(f"""
        <div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;'>
            <span style='font-size:0.9rem;'><b>👤 {str(u).capitalize()}</b></span>
            <span style='color:#FF4B4B; font-size:0.85rem;'>🔥 {ud.get('streak', 0)}d</span>
        </div>
    """, unsafe_allow_html=True)

    # 3. Wybór Języka Nauki
    if "current_lang" not in st.session_state: st.session_state.current_lang = "Niemiecki"
    selected_lang = st.selectbox("Język nauki", options=list(LANG_MAP.keys()), 
                                   format_func=lambda x: LANG_MAP[x]["label"], key="lang_sel", label_visibility="collapsed")

    if selected_lang != st.session_state.current_lang:
        st.session_state.current_lang = selected_lang
        st.session_state.choice = "🏠 Start"
        st.rerun()

    L_CODE = LANG_MAP[st.session_state.current_lang]["code"]

    # 4. Wizualne Paski Postępu (Wiedza i Cel Dnia)
    all_c = [c for c in st.session_state.flashcards if c.get("lang", "de") == L_CODE]
    wiedza = 0
    if all_c:
        today = date.today()
        strong = len([c for c in all_c if (pd.to_datetime(c.get('next_review', today)).date() - today).days > 6])
        wiedza = int((strong / len(all_c)) * 100)

    current_stats = ud.get("time_stats", {})
    # Kod "Lab" musi być w liście, aby czas w Laboratorium się naliczał
    m_list = ["Pow", "Trn", "Qiz", "Fis", "Tst", "Mem", "War", "Kon", "Wan", "Bal", "Lab"]
    mins = int(sum(current_stats.get(c, 0) for c in m_list) // 60)
    goal = ud.get("settings", {}).get("daily_goal", 20)

    st.markdown(f"<div class='small-text'>🧠 Wiedza ({L_CODE.upper()}): {wiedza}%</div>", unsafe_allow_html=True)
    st.progress(min(wiedza / 100, 1.0))
    st.markdown(f"<div class='small-text'>🎯 Cel dnia: {mins}/{goal}m</div>", unsafe_allow_html=True)
    st.progress(min(mins / goal, 1.0))
    st.markdown("<hr>", unsafe_allow_html=True)

    # 5. Funkcja pomocnicza do elementów menu
    def menu_item(label, target):
        is_selected = st.session_state.get("choice") == target
        btn_label = f"{'▶ ' if is_selected else ''}{label}"
        if st.button(btn_label, key=f"btn_{target}"):
            st.session_state.choice = target
            st.rerun()

    # 6. Struktura Menu Głównego
    menu_item("🏠 Start", "🏠 Start")
    choice_now = st.session_state.get("choice", "🏠 Start")

    # GRUPA: NAUKA
    nauka_options = ["📅 Powtórki", "🚀 Trening", "🕹️ Quiz", "🎴 Fiszki", "🧪 Laboratorium", "🛠️ Warsztat", "📝 Testy", "🤖 Sparing AI"]
    with st.expander("📚 Nauka", expanded=(choice_now in nauka_options)):
        for item in nauka_options:
            menu_item(item, item)

    # GRUPA: GRY
    gry_options = ["🧠 Memory", "🏗️ Konstruktor", "🐍 Lingwistyczny Wąż", "🎈 Balonowy Wyścig", "🏆 Arena Wyzwań"]
    with st.expander("🎮 Gry", expanded=(choice_now in gry_options)):
        for item in gry_options:
            menu_item(item, item)

    # Narzędzia
    st.markdown("<div style='margin-top:4px;'></div>", unsafe_allow_html=True)
    for opt in ["📦 Generator", "📸 Skaner AI", "➕ Dodaj", "📖 Słownik", "📊 Statystyki", "⚙️ Konto"]:
        menu_item(opt, opt)

    if u == ADMIN_USER:
        menu_item("👑 Admin", "👑 Admin")

    st.markdown("<hr>", unsafe_allow_html=True)
    if st.button("🚪 Wyloguj", use_container_width=True):
        st.session_state.clear()
        st.rerun()

# --- KLUCZOWA LINIA (Naprawia NameError) ---
choice = st.session_state.get("choice", "🏠 Start")

# --- 7. START (V1.6 - Multilang AI + Fixed Recent Words) ---

# Pobieramy aktualny wybór z sesji, aby uniknąć błędu NameError
current_choice = st.session_state.get("choice", "🏠 Start")

# Aktualizacja czasu aktywności (naliczanie minut)
update_activity(current_choice)

if current_choice == "🏠 Start":
    # Pobieramy aktualny język i kod z sesji
    current_lang_name = st.session_state.get("current_lang", "Niemiecki")
    L_CODE = "de" if current_lang_name == "Niemiecki" else "cs"
    
    # 1. ANALIZA DANYCH BIEŻĄCYCH (Filtrowana pod język)
    all_cards_full = st.session_state.flashcards
    # Wybieramy tylko słówka z aktualnego języka do statystyk na kafelkach
    all_c = [c for c in all_cards_full if c.get("lang", "de") == L_CODE]
    
    ud = st.session_state.user_data
    today_str = str(date.today())
    
    # Statystyki czasu nauki
    current_stats = ud.get("time_stats", {})
    study_modules = ["Pow", "Trn", "Qiz", "Fis", "Tst", "Mem", "War", "Kon", "Wan", "Bal"]
    study_seconds = sum(current_stats.get(code, 0) for code in study_modules)
    study_minutes = int(study_seconds // 60)
    daily_goal = ud.get("settings", {}).get("daily_goal", 20)

    # Statystyki słówek
    total_words = len(all_c)
    to_review = len([c for c in all_c if str(c.get("next_review", today_str)) <= today_str])
    
    # Dynamiczne powitanie zależne od języka
    hello_msg = "Guten Morgen" if L_CODE == "de" else "Dobrý den"
    st.header(f"{hello_msg}, {str(u).capitalize()}! ☀️")
    
    # 2. UKŁAD KAFELKÓW (KPI)
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric(f"Słówek ({current_lang_name})", total_words)
    with col2:
        st.metric("Powtórki na dziś", to_review, delta=-to_review if to_review > 0 else "Gotowe!", delta_color="inverse")
    with col3:
        st.metric("Dzisiejsza nauka", f"{study_minutes} / {daily_goal} m")

    st.write("---")

    # 3. BRIEFING I ZADANIA
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f"### 📊 Status: {current_lang_name}")
        if study_minutes >= daily_goal:
            st.success(f"🌟 Cel dzienny osiągnięty! ({study_minutes} min)")
        elif study_minutes > 0:
            st.info(f"📈 Jesteś w trakcie nauki. Jeszcze {max(0, daily_goal - study_minutes)} min do celu.")
        else:
            st.warning(f"🆕 Czas na Twój dzisiejszy {current_lang_name}!")

    with c2:
        st.markdown("### 🏆 Zadania na dziś")
        t_done = "✅" if study_minutes >= daily_goal else "❌"
        st.write(f"{t_done} Cel czasowy: **{daily_goal} min**")
        st.write("✅ Sprawdź sekcję **Warsztat**")
        st.write("✅ Rozwiąż jeden **Quiz** lub **Test**")

    st.divider()

    # 4. CYTATY I OSTATNIE SŁÓWKA (Poprawione filtrowanie)
    col_q, col_w = st.columns([2, 1])
    
    with col_q:
        if L_CODE == "de":
            quotes = [
                "„Die Grenzen meiner Sprache bedeuten die Grenzen meiner Welt.” – Ludwig Wittgenstein",
                "„Übung macht den Meister!” – Praktyka czyni mistrza.",
                "„Aller Anfang ist schwer.” – Każdy początek jest trudny."
            ]
        else:
            quotes = [
                "„Kolik jazyků znáš, tolikrát jsi člověkem.” – Ile języků znasz, tyle razy jesteś człowiekiem.",
                "„Trpělivost přináší růže.” – Cierpliwość przynosi róże.",
                "„Učený nikdo z nebe nespadl.” – Nikt uczony z nieba nie spadł."
            ]
        st.info(random.choice(quotes))

    with col_w:
        # Sekcja wyświetlająca 3 ostatnio dodane słówka TYLKO dla wybranego języka
        with st.expander(f"🆕 Ostatnie ({current_lang_name})", expanded=True):
            if all_c:
                # Wybieramy 3 ostatnie słówka z przefiltrowanej listy all_c
                recent = all_c[-3:]
                for r in reversed(recent):
                    st.write(f"**{r['de']}**")
            else:
                st.write(f"Baza {current_lang_name} jest pusta.")

# --- 8. POWTÓRKI & TRENING (V264 - Fix SyntaxError + Multilang) ---
elif choice in ["📅 Powtórki", "🚀 Trening"]:
    is_r = (choice == "📅 Powtórki")
    current_lang_name = st.session_state.get("current_lang", "Niemiecki")
    L_CODE = "de" if current_lang_name == "Niemiecki" else "cs"
    
    st.header(f"{choice}: {current_lang_name}")
    
    pfx = "rep" if is_r else "trn"
    user_settings = st.session_state.user_data.get("settings", {})
    auto_audio = user_settings.get("auto_audio", True)
    
    # 1. FILTROWANIE SŁÓWEK POD AKTUALNY JĘZYK
    lang_cards = [c for c in st.session_state.flashcards if c.get("lang", "de") == L_CODE]
    
    all_tags = set()
    for c in lang_cards:
        all_tags.update([t.strip() for t in str(c.get('category','')).split(',') if t.strip()])
    
    sel_tag = st.selectbox(f"Zakres nauki ({current_lang_name}):", ["Wszystkie"] + sorted(list(all_tags)), key=f"{pfx}_tag_sel")

    # 2. INICJALIZACJA KOLEJKI
    if f"{pfx}_list" not in st.session_state or st.session_state.get(f"{pfx}_last_tag") != sel_tag or st.session_state.get(f"{pfx}_last_lang") != L_CODE:
        pool = [c for c in lang_cards if (sel_tag == "Wszystkie" or sel_tag in str(c.get('category','')))]
        if is_r:
            today_str = str(date.today())
            pool = [c for c in pool if str(c.get("next_review", today_str)) <= today_str]
        
        random.shuffle(pool)
        st.session_state[f"{pfx}_list"] = pool
        st.session_state[f"{pfx}_idx"] = 0
        st.session_state[f"{pfx}_last_tag"] = sel_tag
        st.session_state[f"{pfx}_last_lang"] = L_CODE
        st.session_state[f"{pfx}_mode"] = "ask"

    cards = st.session_state.get(f"{pfx}_list", [])
    
    if not cards:
        st.success(f"Świetnie! Brak słówek w sekcji {choice} ({current_lang_name}). ✨")
    elif st.session_state[f"{pfx}_idx"] >= len(cards):
        st.balloons()
        st.success("Sesja zakończona! 🏆")
        if st.button("Zacznij od nowa", key=f"{pfx}_restart_btn"):
            for k in [f"{pfx}_list", f"{pfx}_idx", f"{pfx}_mode", f"{pfx}_user_ans", f"{pfx}_dir"]:
                full_key = f"{pfx}_{k}" if k != "list" and k != "idx" and k != "mode" else f"{pfx}_{k}"
                # Bezpieczne czyszczenie kluczy
                if f"{pfx}_{k}" in st.session_state: 
                    del st.session_state[f"{pfx}_{k}"]
            st.rerun()
    else:
        @st.fragment
        def flashcard_engine():
            idx = st.session_state[f"{pfx}_idx"]
            if idx >= len(cards):
                st.rerun()
                return
            c = cards[idx]
            
            # Klucz kierunku (losowanie DE->PL lub PL->DE)
            dir_key = f"{pfx}_dir"
            if dir_key not in st.session_state:
                st.session_state[dir_key] = random.choice([0, 1])

            st.progress(idx / len(cards))
            st.caption(f"Słówko {idx + 1} z {len(cards)}")

            is_target_foreign = (st.session_state[dir_key] == 1)
            display_word = c["de"] if not is_target_foreign else c["pl"]
            target_lang_label = "Polski" if not is_target_foreign else current_lang_name
            correct_val = c["pl"] if not is_target_foreign else c["de"]

            border_color = "#4CAF50" if is_r else "#FF9800"
            st.markdown(f'''
                <div style="font-size:2.6em; text-align:center; padding:40px; 
                background: #111; border:3px solid {border_color}; 
                border-radius:20px; margin-bottom:10px; color: white; line-height: 1.2;">
                    <div style="font-size:0.35em; color:gray; margin-bottom:5px; text-transform: uppercase;">
                        Tłumaczysz na: {target_lang_label}
                    </div>
                    {display_word}
                </div>
            ''', unsafe_allow_html=True)

            if st.session_state[f"{pfx}_mode"] == "ask":
                with st.form(key=f"{pfx}_f_{idx}", clear_on_submit=True):
                    u_in = st.text_input(f"Odpowiedź ({target_lang_label}):", key=f"{pfx}_in_{idx}")
                    if st.form_submit_button("Sprawdź", use_container_width=True, type="primary"):
                        st.session_state[f"{pfx}_user_ans"] = u_in
                        st.session_state[f"{pfx}_mode"] = "res"
                        st.rerun(scope="fragment")
            else:
                def clean_text(text, is_foreign):
                    t = normalize_text(text)
                    if is_foreign and L_CODE == "de":
                        t = re.sub(r'^(der|die|das)\s+', '', t)
                    return t.strip()

                user_ans = clean_text(st.session_state.get(f"{pfx}_user_ans", ""), is_target_foreign)
                correct_synonyms = re.split(r'[/,;]', correct_val)
                correct_synonyms = [clean_text(s, is_target_foreign) for s in correct_synonyms if s.strip()]
                is_correct = user_ans in correct_synonyms
                
                if is_correct: st.success(f"✅ Dobrze! ({correct_val})")
                else: st.error(f"❌ Niepoprawnie. ({correct_val})")
                
                if auto_audio: play_audio(c['de'], lang=L_CODE)

                st.divider()
                if is_r:
                    st.write("Oceń trudność (SRS):")
                    col1, col2, col3 = st.columns(3)
                    d = None
                    if col1.button("🔴 Trudne"): d = 1
                    if col2.button("🟡 Średnie"): d = 3
                    if col3.button("🟢 Łatwe"): d = 7
                    
                    if d:
                        new_date = str(date.today() + timedelta(days=d))
                        update_word(c['id'], {"next_review": new_date})
                        
                        # Synchronizacja statystyk
                        for card in st.session_state.flashcards:
                            if card['id'] == c['id']:
                                card['next_review'] = new_date
                                break
                        
                        st.session_state[f"{pfx}_idx"] += 1
                        st.session_state[f"{pfx}_mode"] = "ask"
                        # POPRAWKA del:
                        if dir_key in st.session_state: 
                            del st.session_state[dir_key]
                            
                        if st.session_state[f"{pfx}_idx"] >= len(cards): st.rerun()
                        else: st.rerun(scope="fragment")
                else:
                    if st.button("Następne słówko ➡️", use_container_width=True, type="primary"):
                        st.session_state[f"{pfx}_idx"] += 1
                        st.session_state[f"{pfx}_mode"] = "ask"
                        # POPRAWKA del:
                        if dir_key in st.session_state: 
                            del st.session_state[dir_key]
                            
                        st.rerun() if st.session_state[f"{pfx}_idx"] >= len(cards) else st.rerun(scope="fragment")

        flashcard_engine()
        
# --- 9. QUIZ (V245 - Full Multilang & Distractor Fix) ---
elif choice == "🕹️ Quiz":
    current_lang_name = st.session_state.get("current_lang", "Niemiecki")
    L_CODE = "de" if current_lang_name == "Niemiecki" else "cs"
    
    st.header(f"🕹️ Quiz: {current_lang_name}")
    
    # 1. FILTROWANIE SŁÓWEK (Tylko dla aktualnie wybranego języka)
    all_cards_full = st.session_state.flashcards
    all_c = [c for c in all_cards_full if c.get("lang", "de") == L_CODE]
    
    ud = st.session_state.user_data
    user_settings = ud.get("settings", {})
    show_hints = user_settings.get("show_hints", True)
    auto_audio = user_settings.get("auto_audio", True)
    
    if len(all_c) < 4: 
        st.warning(f"Dodaj min. 4 słówka w języku {current_lang_name}, aby uruchomić quiz.")
    else:
        @st.fragment
        def quiz_engine():
            # 1. INICJALIZACJA PYTANIA
            if "q_c" not in st.session_state or st.session_state.get("q_lang_ref") != L_CODE:
                # Losujemy słowo testowe z puli wybranego języka
                t = random.choice(all_c)
                
                # POPRAWKA DYSTRAKTORÓW: Pobieramy błędne opcje TYLKO z przefiltrowanej bazy 'all_c'
                other_pls = [x['pl'] for x in all_c if x['pl'] != t['pl']]
                
                # Jeśli baza jest mała, bierzemy tyle ile się da (max 3)
                num_distractors = min(3, len(other_pls))
                distractors = random.sample(other_pls, num_distractors)
                
                opts = distractors + [t['pl']]
                random.shuffle(opts)
                
                # Zapis stanu pytania
                st.session_state.q_c = t
                st.session_state.q_a = t['pl']
                st.session_state.q_o = opts
                st.session_state.q_s = "ask"
                st.session_state.u_q = None
                st.session_state.q_key_seed = random.randint(1000, 9999)
                st.session_state.q_lang_ref = L_CODE

            q_c = st.session_state.q_c
            
            # Interfejs Pytania
            st.markdown(f"""
                <div style="background: rgba(255,255,255,0.05); padding: 25px; border-radius: 20px; text-align: center; border: 1px solid rgba(255,255,255,0.1);">
                    <div style="color: #888; font-size: 0.9rem; text-transform: uppercase; margin-bottom: 10px;">Jak przetłumaczysz:</div>
                    <div style="font-size: 2.5rem; font-weight: bold; color: white;">{q_c['de']}</div>
                </div>
            """, unsafe_allow_html=True)
            
            st.write("")
            
            if st.session_state.q_s == "ask":
                if show_hints:
                    first_letter = st.session_state.q_a[0].upper()
                    st.info(f"💡 Podpowiedź: Polskie słowo zaczyna się na literę **{first_letter}**")

                # Grid przycisków odpowiedzi
                current_seed = st.session_state.q_key_seed
                cols = st.columns(2)
                for i, o in enumerate(st.session_state.q_o):
                    if cols[i % 2].button(o, key=f"qbtn_{current_seed}_{i}", use_container_width=True):
                        st.session_state.u_q = o
                        st.session_state.q_s = "res"
                        st.rerun(scope="fragment")
            else:
                # 4. WYNIK I LOGIKA SRS
                is_correct = st.session_state.u_q == st.session_state.q_a
                word_id = q_c.get('id')
                
                if is_correct:
                    st.success(f"✅ **Świetnie!** Poprawna odpowiedź: {st.session_state.q_a}")
                    # Przesuwamy termin powtórki (SRS)
                    new_date = str(date.today() + timedelta(days=2))
                    update_word(word_id, {"next_review": new_date})
                else:
                    st.error(f"❌ **Błąd!** Poprawna odpowiedź to: **{st.session_state.q_a}**")
                    # Słowo wraca na dziś do powtórek
                    update_word(word_id, {"next_review": str(date.today()), "level": 0})
                
                # --- OBSŁUGA PRZYKŁADÓW I AUDIO ---
                exs = q_c.get("examples", [])
                example_foreign = None
                example_pl = None
                
                if exs and isinstance(exs, list) and len(exs) > 0:
                    example_foreign = exs[0].get("de")
                    example_pl = exs[0].get("pl")
                elif q_c.get('example'): # Fallback
                    example_foreign = q_c['example']

                if example_foreign:
                    st.info(f"📖 **Przykład:** {example_foreign}" + (f"\n\n🇵🇱 *{example_pl}*" if example_pl else ""))
                
                # Automatyczne odtwarzanie (z kluczową poprawką lang=L_CODE)
                if auto_audio:
                    play_audio(q_c['de'], example_foreign, lang=L_CODE)

                st.write("---")
                if st.button("Następne pytanie ➡️", use_container_width=True, type="primary"):
                    # Czyścimy stan, aby wylosować nowe pytanie
                    for key in ["q_c", "q_a", "q_o", "q_s", "u_q", "q_key_seed"]:
                        if key in st.session_state: del st.session_state[key]
                    st.rerun(scope="fragment")

        quiz_engine()
        
# --- 10. FISZKI (V351 - Multilang Themes + Shuffle Function) ---
elif choice == "🎴 Fiszki":
    current_lang_name = st.session_state.get("current_lang", "Niemiecki")
    L_CODE = "de" if current_lang_name == "Niemiecki" else "cs"
    
    st.header(f"🎴 Fiszki: {current_lang_name}")
    
    # 1. Pobieranie ustawienia z bazy
    user_settings = st.session_state.user_data.get("settings", {})
    auto_audio = user_settings.get("auto_audio", True)
    
    # Inicjalizacja stanu
    if "f_idx" not in st.session_state: st.session_state.f_idx = 0
    if "f_flipped" not in st.session_state: st.session_state.f_flipped = False
    
    # 2. Filtrowanie i Mieszanie
    lang_cards = [c for c in st.session_state.flashcards if c.get("lang", "de") == L_CODE]
    
    all_tags = set()
    for c in lang_cards:
        all_tags.update([t.strip() for t in str(c.get('category','')).split(',') if t.strip()])
    
    col_sel, col_shuf = st.columns([3, 1])
    sel_tag = col_sel.selectbox("Zakres:", ["Wszystkie"] + sorted(list(all_tags)), key="f_tag_sel")
    
    # Filtrujemy bazę wyjściową
    cards_to_show = [c for c in lang_cards if sel_tag == "Wszystkie" or sel_tag in str(c.get('category',''))]

    # Przycisk mieszania (Shuffle)
    if col_shuf.button("🔀 Pomieszaj", use_container_width=True):
        random.shuffle(cards_to_show)
        st.session_state.f_shuffled_list = cards_to_show
        st.session_state.f_idx = 0
        st.session_state.f_flipped = False
        st.toast("Kolejność pomieszana! 🎲")

    # Używamy pomieszanej listy jeśli istnieje, w przeciwnym razie standardowej
    if "f_shuffled_list" in st.session_state and sel_tag == st.session_state.get("f_last_tag"):
        cards = st.session_state.f_shuffled_list
    else:
        cards = cards_to_show
        st.session_state.f_last_tag = sel_tag
        if "f_shuffled_list" in st.session_state: del st.session_state.f_shuffled_list

    if not cards:
        st.warning(f"Brak słówek w języku {current_lang_name} dla wybranej kategorii.")
    else:
        # Silnik Fiszek jako izolowany fragment
        @st.fragment
        def flashcards_ui():
            if st.session_state.f_idx >= len(cards): st.session_state.f_idx = 0
            if st.session_state.f_idx < 0: st.session_state.f_idx = len(cards) - 1
            
            c = cards[st.session_state.f_idx]
            
            # --- LOGIKA KOLORÓW NARODOWYCH (BEZ ZMIAN) ---
            if st.session_state.f_flipped:
                txt = c["pl"]
                border_color = "#DC143C" 
                label = "🇵🇱 POLSKI"
                glow_style = "box-shadow: 0 10px 30px rgba(220, 20, 60, 0.4);"
            else:
                txt = c["de"]
                if L_CODE == "de":
                    border_color = "#FFCC00" 
                    label = "🇩🇪 DEUTSCH"
                    glow_style = "box-shadow: 0 10px 30px rgba(255, 204, 0, 0.3);"
                else:
                    border_color = "#11457E" 
                    label = "🇨🇿 ČEŠTINA"
                    glow_style = "box-shadow: 0 10px 30px rgba(17, 69, 126, 0.4);"

            # Renderowanie graficzne karty
            st.markdown(f"""
                <div style="min-height:300px; display:flex; flex-direction:column; align-items:center; justify-content:center; 
                background:#111; border:6px solid {border_color}; border-radius:40px; color:white; text-align:center; padding:30px; 
                {glow_style} margin-bottom: 20px; transition: all 0.3s ease;">
                    <div style="color:{border_color}; font-weight:bold; letter-spacing:3px; margin-bottom:15px; font-size:1.1em;">{label}</div>
                    <div style="font-size:3.5em; font-weight:700; line-height:1.1; margin-bottom:10px;">{txt}</div>
                </div>
            """, unsafe_allow_html=True)

            # Obsługa przykładów i dźwięku
            if st.session_state.f_flipped:
                exs = c.get("examples", [])
                fex = exs[0].get("de") if exs and isinstance(exs, list) and len(exs) > 0 else None
                
                if fex:
                    flag = "🇩🇪" if L_CODE == "de" else "🇨🇿"
                    st.info(f"{flag} **{fex}**\n\n🇵🇱 {exs[0].get('pl','')}")
                    if auto_audio: play_audio(c['de'], fex, lang=L_CODE)
                else:
                    if auto_audio: play_audio(c['de'], lang=L_CODE)

                if not auto_audio:
                    if st.button("🔊 Odsłuchaj wymowę", use_container_width=True):
                        play_audio(c['de'], fex if fex else None, lang=L_CODE)
            
            # Nawigacja
            st.write("")
            c1, c2, c3 = st.columns([1, 2, 1])
            
            if c1.button("⬅️ Poprzednia", use_container_width=True):
                st.session_state.f_idx -= 1
                st.session_state.f_flipped = False
                st.rerun(scope="fragment")
                
            if c2.button("🔄 OBRÓĆ KARTĘ", type="primary", use_container_width=True):
                st.session_state.f_flipped = not st.session_state.f_flipped
                st.rerun(scope="fragment")
                
            if c3.button("Następna ➡️", use_container_width=True):
                st.session_state.f_idx += 1
                st.session_state.f_flipped = False
                st.rerun(scope="fragment")

        flashcards_ui()

# --- 11. TESTY (V300 - Full Multilang + Lang-Specific History) ---
elif choice == "📝 Testy":
    current_lang_name = st.session_state.get("current_lang", "Niemiecki")
    L_CODE = "de" if current_lang_name == "Niemiecki" else "cs"
    
    st.header(f"📝 Test: {current_lang_name}")
    
    # 1. FILTROWANIE SŁÓWEK POD JĘZYK
    lang_cards = [c for c in st.session_state.flashcards if c.get("lang", "de") == L_CODE]
    
    if len(lang_cards) < 5:
        st.warning(f"Masz za mało słówek w języku {current_lang_name} (min. 5), aby wygenerować test. Dodaj nowe słówka lub użyj Skanera AI!")
    else:
        # 2. EKRAN KONFIGURACJI TESTU
        if "test_q" not in st.session_state:
            # Pobieramy preferencje z ustawień użytkownika
            user_prefs = st.session_state.user_data.get("settings", {})
            default_q_count = user_prefs.get("test_questions", 10)
            
            # Slider ograniczony do faktycznej liczby słówek w bazie
            max_possible = min(len(lang_cards), 30)
            n_q = st.slider("Liczba pytań w teście:", 5, max_possible, min(default_q_count, max_possible))
            
            if st.button(f"🚀 GENERUJ TEST ({current_lang_name})", use_container_width=True, type="primary"):
                with st.spinner(f"Sztuczna inteligencja przygotowuje zadania w języku {current_lang_name}..."):
                    try:
                        # Losujemy słówka do testu
                        sample = random.sample(lang_cards, n_q)
                        words_for_ai = [w['de'] for w in sample]
                        
                        # Dynamiczny prompt uwzględniający język
                        lang_instruction = "Każdy rzeczownik musi mieć rodzajnik (der/die/das)." if L_CODE == "de" else "Zwróć szczególną uwagę na czeską diakrytykę."
                        
                        prompt = f"""Jesteś nauczycielem języka {current_lang_name}. 
                        Stwórz test luk dla następujących słów: {words_for_ai}.
                        {lang_instruction}
                        
                        Dla każdego słowa przygotuj:
                        1. hint: krótkie naprowadzenie po polsku.
                        2. sentence: zdanie w języku {current_lang_name} z luką "_______" w miejscu słowa kluczowego.
                        3. correct: poprawne słowo (dokładnie w takiej formie, jak ma być w zdaniu).
                        4. distractors: 3 błędne ale gramatycznie podobne odpowiedzi w języku {current_lang_name}.
                        
                        Zwróć TYLKO czysty JSON:
                        {{ "questions": [
                            {{ "hint": "...", "sentence": "...", "correct": "...", "distractors": ["...", "...", "..."], "type": "QUIZ" }}
                        ] }}"""
                        
                        res_raw = get_openai_response(prompt)
                        data = json.loads(res_raw)
                        
                        # Inicjalizacja sesji testu
                        st.session_state.test_q = data["questions"]
                        st.session_state.test_idx = 0
                        st.session_state.test_score = 0
                        st.rerun()
                    except Exception as e:
                        st.error(f"Wystąpił błąd podczas generowania testu: {e}")
        
        # 3. SILNIK TESTU (EKRAN PYTAŃ)
        else:
            @st.fragment
            def test_engine():
                qs = st.session_state.test_q
                t_idx = st.session_state.test_idx
                
                if t_idx < len(qs):
                    q = qs[t_idx]
                    
                    # Pasek postępu i licznik
                    st.progress(t_idx / len(qs))
                    st.caption(f"Pytanie {t_idx + 1} z {len(qs)}")
                    
                    # Wizualizacja pytania
                    st.markdown(f"### {q.get('sentence', '???')}")
                    st.info(f"💡 Podpowiedź: {q.get('hint', '')}")
                    
                    # Przygotowanie opcji (Correct + Distractors)
                    correct_ans = q.get('correct')
                    options = list(set(q.get('distractors', []) + [correct_ans]))
                    random.shuffle(options)
                    
                    # Grid przycisków odpowiedzi
                    cols = st.columns(2)
                    for i, opt in enumerate(options):
                        if cols[i % 2].button(opt, key=f"t_opt_{t_idx}_{i}", use_container_width=True):
                            # Walidacja
                            st.session_state.test_q[t_idx]['user_ans'] = opt
                            if opt == correct_ans:
                                st.session_state.test_score += 1
                                st.toast("Świetnie! ✅", icon="🎉")
                            else:
                                st.toast(f"Błąd! Poprawnie: {correct_ans} ❌", icon="⚠️")
                            
                            st.session_state.test_idx += 1
                            st.rerun(scope="fragment")
                
                # 4. PODSUMOWANIE TESTU
                else:
                    score = st.session_state.test_score
                    total = len(qs)
                    perc = round((score / total) * 100) if total > 0 else 0
                    
                    st.markdown(f"""
                        <div style="text-align:center; padding:30px; border-radius:20px; background:rgba(255,255,255,0.05); border:2px solid #ff4b4b;">
                            <h1 style="margin:0; color:white;">Koniec Testu!</h1>
                            <h2 style="color:#ff4b4b; font-size:3rem;">{score} / {total}</h2>
                            <p style="font-size:1.5rem;">Twój wynik to <b>{perc}%</b></p>
                        </div>
                    """, unsafe_allow_html=True)
                    
                    # Szczegółowa lista odpowiedzi
                    with st.expander("🔍 Przeglądaj swoje odpowiedzi", expanded=True):
                        for i, res in enumerate(qs):
                            u_a = res.get('user_ans', 'Brak')
                            c_a = res.get('correct', '')
                            is_ok = (u_a == c_a)
                            icon = "✅" if is_ok else "❌"
                            color = "#4CAF50" if is_ok else "#FF5252"
                            
                            st.markdown(f"**{i+1}.** {res.get('sentence')}")
                            st.markdown(f"""
                                <div style="margin-left: 20px; font-size: 0.9em; margin-bottom: 10px;">
                                    {icon} Twoja: <span style="color:{color};">{u_a}</span><br>
                                    🎯 Poprawna: <span style="color:#4CAF50;">{c_a}</span>
                                </div>
                            """, unsafe_allow_html=True)

                    # ZAPIS DO BAZY (Z uwzględnieniem L_CODE)
                    if st.button("💾 Zapisz wynik i wyjdź", use_container_width=True, type="primary"):
                        new_result = {
                            "date": datetime.now().strftime("%d.%m %H:%M"),
                            "score": score,
                            "total": total,
                            "perc": perc,
                            "lang": L_CODE # Kluczowe do filtrowania w statystykach
                        }
                        
                        # Dodajemy do lokalnej listy i synchronizujemy z bazą
                        if "test_history" not in st.session_state.user_data:
                            st.session_state.user_data["test_history"] = []
                        
                        st.session_state.user_data["test_history"].append(new_result)
                        save_user_data(st.session_state.user, st.session_state.user_data)
                        
                        # Czyścimy stan testu
                        del st.session_state.test_q
                        st.rerun()

            test_engine()

# --- 12. GRA MEMORY (V287 - Fix AttributeError Restart) ---
elif choice == "🧠 Memory":
    current_lang_name = st.session_state.get("current_lang", "Niemiecki")
    L_CODE = "de" if current_lang_name == "Niemiecki" else "cs"
    
    st.header(f"🧠 Memory: {current_lang_name}")
    st.write(f"Znajdź pary ({current_lang_name} - Polski). Liczy się czas!")

    # 1. FILTROWANIE SŁÓWEK POD JĘZYK
    all_c = [c for c in st.session_state.flashcards if c.get("lang", "de") == L_CODE]

    # 2. FUNKCJA INICJALIZACJI / RESETU
    def init_memory_game():
        if len(all_c) < 6:
            return False
        cards_pool = random.sample(all_c, 6)
        grid = []
        for c in cards_pool:
            grid.append({"id": c["id"], "text": c["de"], "type": "foreign"})
            grid.append({"id": c["id"], "text": c["pl"], "type": "pl"})
        random.shuffle(grid)
        
        st.session_state.mem_grid = grid
        st.session_state.mem_status = ["hidden"] * 12
        st.session_state.mem_first = None
        st.session_state.mem_pairs = 0
        st.session_state.mem_start_time = None
        st.session_state.mem_final_time = None
        st.session_state.mem_lang_ref = L_CODE
        return True

    # Inicjalizacja przy pierwszym wejściu lub zmianie języka
    if "mem_grid" not in st.session_state or st.session_state.get("mem_lang_ref") != L_CODE:
        if not init_memory_game():
            st.warning(f"Dodaj przynajmniej 6 słówek w języku {current_lang_name}, aby móc zagrać.")
            st.stop()

    # 3. SILNIK GRY (FRAGMENT)
    @st.fragment
    def memory_engine():
        # Bezpiecznik: jeśli klucz zniknął, zainicjuj ponownie zamiast sypać błędem
        if "mem_grid" not in st.session_state:
            init_memory_game()
            
        grid = st.session_state.mem_grid
        status = st.session_state.mem_status
        
        c1, c2, _ = st.columns([1, 1, 2])
        
        if st.session_state.mem_start_time and st.session_state.mem_final_time is None:
            elapsed = round(time.time() - st.session_state.mem_start_time, 1)
            c1.metric("⏱️ Czas", f"{elapsed}s")
        elif st.session_state.mem_final_time:
            c1.metric("🏁 Wynik", f"{st.session_state.mem_final_time}s")
        else:
            c1.metric("⏱️ Czas", "0.0s")
            
        c2.metric("🧩 Pary", f"{st.session_state.mem_pairs}/6")
        
        # LOGIKA KOŃCA GRY
        if st.session_state.mem_pairs == 6:
            if st.session_state.mem_final_time is None:
                st.session_state.mem_final_time = round(time.time() - st.session_state.mem_start_time, 2)
                
                # ZAPIS REKORDU
                try:
                    db = get_db()
                    new_score = st.session_state.mem_final_time
                    mem_key = f"memory_scores_{L_CODE}"
                    ud = st.session_state.user_data
                    current_scores = ud.get(mem_key, [])
                    if not isinstance(current_scores, list): current_scores = []
                    current_scores.append(new_score)
                    current_scores = sorted([float(s) for s in current_scores])[:10]
                    
                    db.table("user_data").update({mem_key: current_scores}).eq("username", u).execute()
                    st.session_state.user_data[mem_key] = current_scores
                except:
                    pass

            st.balloons()
            st.success(f"Brawo! Twój czas: {st.session_state.mem_final_time}s")
            
            # POPRAWIONY RESTART: Zamiast del, robimy nową inicjalizację
            if st.button("Zagraj jeszcze raz", use_container_width=True):
                init_memory_game()
                st.rerun()
            return

        st.write("---")

        # RENDEROWANIE PRZYCISKÓW
        for row in range(3):
            cols = st.columns(4)
            for col in range(4):
                idx = row * 4 + col
                # Dodatkowe sprawdzenie bezpieczeństwa indeksu
                if idx >= len(status): continue
                
                tile_text = "❓"
                tile_type = "secondary"
                tile_disabled = False

                if status[idx] == "matched":
                    tile_text = "✅"
                    tile_disabled = True
                elif status[idx] == "flipped":
                    tile_text = grid[idx]["text"]
                    tile_type = "primary"
                    tile_disabled = True

                if cols[col].button(tile_text, key=f"mem_{idx}", use_container_width=True, disabled=tile_disabled, type=tile_type):
                    if st.session_state.mem_start_time is None:
                        st.session_state.mem_start_time = time.time()

                    if st.session_state.mem_first is None:
                        status[idx] = "flipped"
                        st.session_state.mem_first = idx
                        st.rerun(scope="fragment")
                    else:
                        status[idx] = "flipped"
                        st.rerun(scope="fragment") 

        # SPRAWDZANIE PAR
        flipped = [i for i, s in enumerate(status) if s == "flipped"]
        if len(flipped) == 2:
            idx1, idx2 = flipped
            time.sleep(0.6)
            
            if grid[idx1]["id"] == grid[idx2]["id"]:
                status[idx1] = "matched"
                status[idx2] = "matched"
                st.session_state.mem_pairs += 1
            else:
                status[idx1] = "hidden"
                status[idx2] = "hidden"
            
            st.session_state.mem_first = None
            st.rerun(scope="fragment")

    memory_engine()

    # PRZYCISK RESETU NA DOLE
    if st.button("Wygeneruj nową tablicę", type="secondary", use_container_width=True):
        init_memory_game()
        st.rerun()
                
# --- 13. WARSZTAT SŁÓWEK (V315 - Multilang & Ultra Fast) ---
elif choice == "🛠️ Warsztat":
    current_lang_name = st.session_state.get("current_lang", "Niemiecki")
    L_CODE = "de" if current_lang_name == "Niemiecki" else "cs"
    
    st.header(f"🛠️ Warsztat Słówek: {current_lang_name}")
    st.write(f"Tu trafiają słówka {current_lang_name.lower()}, które sprawiają Ci trudność. Opanuj je raz a dobrze!")

    # 1. IDENTYFIKACJA "TRUDNYCH" SŁÓWEK (Filtrowane pod język)
    if "w_list" not in st.session_state or st.session_state.get("w_lang_ref") != L_CODE:
        # Pobieramy karty tylko dla aktualnego języka
        lang_cards = [c for c in st.session_state.flashcards if c.get("lang", "de") == L_CODE]
        
        # Filtrujemy słówka: te z level < 2 lub interval < 2 (najświeższe błędy)
        hard_cards = [
            c for c in lang_cards 
            if c.get("level", 0) < 2 or c.get("interval", 0) < 2
        ]
        
        # Jeśli nie ma "bardzo trudnych", weźmy te z najniższym levelem ogólnie w tym języku
        if len(hard_cards) < 5 and lang_cards:
            hard_cards = sorted(lang_cards, key=lambda x: x.get("level", 0))[:10]

        random.shuffle(hard_cards)
        st.session_state.w_list = hard_cards[:15] # Sesja max 15 "koszmarów"
        st.session_state.w_idx = 0
        st.session_state.w_show = False
        st.session_state.w_lang_ref = L_CODE

    if not st.session_state.w_list:
        st.success(f"Twoja lista trudnych słówek ({current_lang_name}) jest pusta! ✨")
    
    elif st.session_state.w_idx >= len(st.session_state.w_list):
        st.balloons()
        st.success(f"Warsztat {current_lang_name} zakończony! Dobra robota.")
        if st.button("Zacznij od nowa", use_container_width=True):
            for k in ["w_list", "w_idx", "w_show", "w_lang_ref"]:
                if k in st.session_state: del st.session_state[k]
            st.rerun()
    else:
        # --- SILNIK WARSZTATU (FRAGMENT - BEZ ZMIAN W GRAFICE) ---
        @st.fragment
        def workshop_engine():
            idx = st.session_state.w_idx
            w_list = st.session_state.w_list
            curr = w_list[idx]
            
            progress = (idx) / len(w_list)
            st.progress(progress)
            st.caption(f"Słówko {idx + 1} z {len(w_list)}")

            with st.container(border=True):
                st.markdown(f"<h1 style='text-align: center; margin-bottom: 20px;'>{curr['de']}</h1>", unsafe_allow_html=True)
                
                if st.session_state.w_show:
                    st.markdown(f"<h3 style='text-align: center; color: #FF5252; margin-top: -10px;'>{curr['pl']}</h3>", unsafe_allow_html=True)
                    
                    # Obsługa przykładów (pobieranie z nowej struktury listy jeśli istnieje)
                    ex_obj = curr.get('examples', [])
                    example_text = ""
                    if ex_obj and isinstance(ex_obj, list):
                        example_text = ex_obj[0].get('de', '')
                    elif curr.get('example'): # fallback dla starych danych
                        example_text = curr['example']

                    if example_text:
                        st.info(f"💡 Przykład: {example_text}")
                    
                    user_settings = st.session_state.user_data.get("settings", {})
                    if user_settings.get("auto_audio", True):
                        # Kluczowa zmiana: lang=L_CODE dla poprawnej wymowy
                        play_audio(curr['de'], example_text if example_text else None, lang=L_CODE)
                
                st.write("")
                if not st.session_state.w_show:
                    if st.button("👁️ Pokaż odpowiedź", use_container_width=True, type="primary"):
                        st.session_state.w_show = True
                        st.rerun(scope="fragment")
                else:
                    col_a, col_b = st.columns(2)
                    if col_a.button("❌ Nadal trudne", use_container_width=True):
                        card = st.session_state.w_list.pop(st.session_state.w_idx)
                        st.session_state.w_list.append(card)
                        st.session_state.w_show = False
                        st.rerun(scope="fragment")
                    
                    if col_b.button("✅ Już rozumiem", use_container_width=True):
                        st.session_state.w_idx += 1
                        st.session_state.w_show = False
                        st.rerun(scope="fragment")

        workshop_engine()

    # Przycisk resetu
    if st.button("Wygeneruj nową listę warsztatową", type="secondary", use_container_width=True):
        for k in ["w_list", "w_idx", "w_show", "w_lang_ref"]:
            if k in st.session_state: del st.session_state[k]
        st.rerun()

    # Statystyki warsztatu w sidebarze
    st.sidebar.divider()
    st.sidebar.write(f"🔧 W warsztacie ({current_lang_name}): **{len(st.session_state.w_list)}**")

# --- 14. KONSTRUKTOR SŁÓW (V313 - CSS Isolation & Sidebar Fix) ---
elif choice == "🏗️ Konstruktor":
    current_lang_name = st.session_state.get("current_lang", "Niemiecki")
    L_CODE = "de" if current_lang_name == "Niemiecki" else "cs"
    
    st.markdown(f"<h1 style='text-align: center;'>🏗️ Konstruktor: {current_lang_name}</h1>", unsafe_allow_html=True)

    # 1. POPRAWIONY CSS - Izolacja stylu (nie dotyka Sidebaru)
    st.markdown("""
        <style>
            /* Stylizujemy przyciski TYLKO w głównej sekcji (Main Content) */
            [data-testid="stMain"] div.stButton > button {
                border: 1px solid rgba(255, 255, 255, 0.2) !important;
                background: rgba(255, 255, 255, 0.05) !important;
                border-radius: 8px !important;
                height: 50px !important;
                font-weight: bold !important;
                font-size: 1.2rem !important;
                margin-bottom: 0px !important;
            }
            
            /* Specyficzny styl dla slotu na odpowiedź */
            .slot-box {
                font-size: 2.5rem;
                letter-spacing: 10px;
                text-align: center;
                color: #ff4b4b;
                font-family: 'Courier New', monospace;
                padding: 20px;
                background: rgba(255, 75, 75, 0.05);
                border: 1px dashed #ff4b4b;
                border-radius: 15px;
                margin: 20px 0;
                min-height: 100px;
                display: flex;
                align-items: center;
                justify-content: center;
            }
            
            /* Resetujemy ewentualne konflikty dla przycisków w sidebarze w tej sekcji */
            [data-testid="stSidebar"] div.stButton > button {
                height: auto !important;
                min-height: 28px !important;
                font-size: 0.88rem !important;
                border: none !important;
                padding: 1px 6px !important;
            }
        </style>
    """, unsafe_allow_html=True)

    # 2. FILTROWANIE DANYCH
    lang_cards = [c for c in st.session_state.flashcards if c.get("lang") == L_CODE]
    
    if not lang_cards:
        st.warning(f"Baza {current_lang_name} jest pusta.")
    else:
        # Inicjalizacja gry
        if "konstr_word" not in st.session_state or st.session_state.get("konstr_lang_ref") != L_CODE:
            card = random.choice(lang_cards)
            word = str(card['de']).strip()
            letters = list(word)
            random.shuffle(letters)
            
            st.session_state.konstr_word = word
            st.session_state.konstr_pl = card['pl']
            st.session_state.konstr_pool = letters
            st.session_state.konstr_ans = ""
            st.session_state.konstr_used_indices = []
            st.session_state.konstr_lang_ref = L_CODE

        # Panel Zadania
        st.markdown(f"""
            <div style="background: rgba(255,255,255,0.05); padding: 20px; border-radius: 15px; text-align: center;">
                <div style="color: #888; font-size: 0.9rem; text-transform: uppercase;">Przetłumacz na {current_lang_name}:</div>
                <div style="font-size: 2rem; font-weight: bold; color: white;">{st.session_state.konstr_pl}</div>
            </div>
        """, unsafe_allow_html=True)

        # Slot na odpowiedź
        target_word = st.session_state.konstr_word
        display_ans = ""
        for i in range(len(target_word)):
            if i < len(st.session_state.konstr_ans):
                display_ans += st.session_state.konstr_ans[i]
            else:
                display_ans += "_"
        st.markdown(f"<div class='slot-box'>{display_ans}</div>", unsafe_allow_html=True)

        # 3. SIATKA LITER
        st.write("<div style='text-align:center; color: #888; margin-bottom:10px;'>DOSTĘPNE LITERY:</div>", unsafe_allow_html=True)
        cols = st.columns(6)
        for idx, char in enumerate(st.session_state.konstr_pool):
            col_idx = idx % 6
            with cols[col_idx]:
                label = "␣" if char == " " else char
                is_used = idx in st.session_state.konstr_used_indices
                if st.button(label, key=f"btn_k_{idx}", disabled=is_used, use_container_width=True):
                    st.session_state.konstr_ans += char
                    st.session_state.konstr_used_indices.append(idx)
                    st.rerun()

        st.divider()

        # 4. PRZYCISKI FUNKCYJNE
        c1, c2, c3 = st.columns(3)
        
        if c1.button("🔄 Reset", use_container_width=True):
            st.session_state.konstr_ans = ""
            st.session_state.konstr_used_indices = []
            st.rerun()
            
        can_undo = len(st.session_state.konstr_used_indices) > 0
        if c2.button("⬅️ Cofnij", use_container_width=True, disabled=not can_undo):
            if st.session_state.konstr_ans:
                st.session_state.konstr_ans = st.session_state.konstr_ans[:-1]
                st.session_state.konstr_used_indices.pop()
                st.rerun()
            
        if c3.button("⏭️ Pomiń", use_container_width=True):
            del st.session_state.konstr_word
            st.rerun()

        # 5. WALIDACJA
        if st.session_state.konstr_ans == target_word:
            st.balloons()
            st.success(f"Brawo! Poprawnie: **{target_word}**")
            if st.button("Następne ➡️", type="primary", use_container_width=True):
                del st.session_state.konstr_word
                st.rerun()

# --- 15. LINGWISTYCZNY WĄŻ (V1.6 - Multilang + Difficulty Levels + Logic Fix) ---
elif choice == "🐍 Lingwistyczny Wąż":
    current_lang_name = st.session_state.get("current_lang", "Niemiecki")
    L_CODE = "de" if current_lang_name == "Niemiecki" else "cs"
    
    st.header("🐍 Lingwistyczny Wąż")
    st.write("Rywalizuj z systemem! Wygrywa ten, kto doda ostatnie możliwe słowo z Twojej bazy.")

    # 1. FUNKCJE POMOCNICZE LOGIKI
    def is_noun(card):
        """Sprawdza czy słowo jest rzeczownikiem na podstawie kategorii lub rodzajnika."""
        c = str(card.get('category', '')).lower()
        d = str(card.get('de', '')).lower()
        return "rzeczownik" in c or "noun" in c or d.startswith(("der ", "die ", "das "))

    def get_first_letter(text):
        """Wyciąga pierwszą literę słowa, ignorując niemieckie rodzajniki."""
        clean = text.lower().strip()
        clean = re.sub(r'^(der|die|das)\s+', '', clean)
        clean = "".join(filter(str.isalpha, clean))
        return clean[0] if clean else ""

    def get_last_letter(text):
        """Wyciąga ostatnią literę słowa, ignorując niemieckie rodzajniki."""
        clean = text.lower().strip()
        clean = re.sub(r'^(der|die|das)\s+', '', clean)
        clean = "".join(filter(str.isalpha, clean))
        return clean[-1] if clean else ""

    # 2. PRZYGOTOWANIE BAZY
    # Filtrujemy tylko rzeczowniki dla aktualnego języka
    lang_cards = [c for c in st.session_state.flashcards if c.get("lang", "de") == L_CODE and is_noun(c)]

    if len(lang_cards) < 5:
        st.warning(f"Masz za mało rzeczowników w bazie ({current_lang_name}), aby zacząć grę (wymagane min. 5).")
        st.stop()

    # 3. EKRAN STARTOWY (WYBÓR TRUDNOŚCI)
    if "snake_active" not in st.session_state:
        st.subheader("Wybierz poziom trudności:")
        diff = st.radio("Poziom:", ["Łatwy", "Średni", "Trudny"], horizontal=True, label_visibility="collapsed")
        if st.button("Zacznij grę 🚀", use_container_width=True):
            first_word = random.choice(lang_cards)
            st.session_state.snake_active = True
            st.session_state.snake_chain = [first_word]
            st.session_state.snake_used_ids = {first_word['id']}
            st.session_state.snake_status = "player"
            st.session_state.snake_diff = diff
            st.session_state.snake_winner = None
            st.rerun()
        st.stop()

    # 4. SILNIK GRY (FRAGMENT)
    @st.fragment
    def snake_engine():
        chain = st.session_state.snake_chain
        last_word_obj = chain[-1]
        req_letter = get_last_letter(last_word_obj['de'])

        # UI: Łańcuch
        st.markdown("### Łańcuch:")
        display_chain = chain[-6:]
        cols = st.columns(len(display_chain))
        for i, word in enumerate(display_chain):
            with cols[i]:
                # Logika kolorów: parzystość od początku łańcucha
                is_system = (len(chain) - len(display_chain) + i) % 2 == 0
                color = "#1E88E5" if is_system else "#4CAF50"
                st.markdown(f"""
                    <div style="background:{color}; padding:15px; border-radius:10px; text-align:center; color:white; min-height:100px; display:flex; flex-direction:column; justify-content:center; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
                        <div style="font-weight:bold; font-size:1.1em;">{word['de']}</div>
                        <div style="font-size:0.8em; opacity:0.8;">{word['pl']}</div>
                    </div>
                """, unsafe_allow_html=True)
        
        st.write("")
        if st.session_state.snake_status != "end":
            st.info(f"Ostatnie słowo: **{last_word_obj['de']}**. Czekamy na słowo na literę: **{req_letter.upper()}**")

        # KOLEJ GRACZA
        if st.session_state.snake_status == "player":
            with st.form("snake_input_form", clear_on_submit=True):
                u_in = st.text_input(f"Twoja kolej ({L_CODE.upper()}):").strip().lower()
                c1, c2 = st.columns([3, 1])
                submit = c1.form_submit_button("Dodaj ogniwo 🔗", use_container_width=True)
                give_up = c2.form_submit_button("🏳️ Poddaję się", use_container_width=True)

                if submit:
                    # Szukamy słowa w przefiltrowanej bazie rzeczowników
                    found = [c for c in lang_cards if 
                             normalize_text(c['de']) == normalize_text(u_in) or 
                             normalize_text(re.sub(r'^(der|die|das)\s+', '', c['de'].lower())) == normalize_text(u_in)]
                    
                    if not found:
                        st.error("Nie znaleziono takiego rzeczownika w Twojej bazie!")
                    elif found[0]['id'] in st.session_state.snake_used_ids:
                        st.error("To słowo zostało już użyte!")
                    elif get_first_letter(u_in) != req_letter:
                        st.error(f"Słowo musi zaczynać się na literę '{req_letter.upper()}'!")
                    else:
                        st.session_state.snake_chain.append(found[0])
                        st.session_state.snake_used_ids.add(found[0]['id'])
                        st.session_state.snake_status = "system"
                        st.rerun(scope="fragment")

                if give_up:
                    st.session_state.snake_status = "end"
                    st.session_state.snake_winner = "System 🤖"
                    st.rerun(scope="fragment")

        # KOLEJ SYSTEMU
        elif st.session_state.snake_status == "system":
            with st.spinner("System myśli..."):
                time.sleep(1.5)
                # System szuka odpowiedzi w bazie gracza (pierwsza litera = wymagana litera)
                possible = [c for c in lang_cards if get_first_letter(c['de']) == req_letter and c['id'] not in st.session_state.snake_used_ids]
                
                # Szansa na błąd zależna od poziomu
                fail_chance = {"Łatwy": 0.40, "Średni": 0.15, "Trudny": 0.0}.get(st.session_state.snake_diff, 0)
                
                if possible and random.random() > fail_chance:
                    bot_choice = random.choice(possible)
                    st.session_state.snake_chain.append(bot_choice)
                    st.session_state.snake_used_ids.add(bot_choice['id'])
                    st.session_state.snake_status = "player"
                    st.rerun(scope="fragment")
                else:
                    st.session_state.snake_status = "end"
                    st.session_state.snake_winner = f"{u.capitalize()} 🏆"
                    st.balloons()
                    st.rerun(scope="fragment")

        # KONIEC GRY
        if st.session_state.snake_status == "end":
            st.success(f"### Koniec gry! Zwycięzca: {st.session_state.snake_winner}")
            if st.button("Zagraj jeszcze raz", use_container_width=True, type="primary"):
                for k in ["snake_active", "snake_chain", "snake_used_ids", "snake_status", "snake_winner", "snake_diff"]:
                    if k in st.session_state: del st.session_state[k]
                st.rerun()

    snake_engine()

# --- 16. BALONOWY WYŚCIG (V312 - Visible Balloons & Simple Scoring) ---
elif choice == "🎈 Balonowy Wyścig":
    current_lang_name = st.session_state.get("current_lang", "Niemiecki")
    L_CODE = "de" if current_lang_name == "Niemiecki" else "cs"
    
    st.markdown(f"<h2 style='text-align: center;'>🎈 Balonowy Wyścig: {current_lang_name}</h2>", unsafe_allow_html=True)

    # 1. CSS - POTĘŻNY UPGRADE WIDOCZNOŚCI PRZYCISKÓW
    st.markdown("""
        <style>
            /* Stylizacja przycisków jako kolorowe balony */
            [data-testid="stMain"] div.stButton > button {
                background: linear-gradient(135deg, #ff4b4b 0%, #ff7676 100%) !important;
                color: white !important;
                border: 2px solid #ff2a2a !important;
                border-radius: 30px !important; /* Zaokrąglone jak balony */
                padding: 15px 20px !important;
                font-weight: bold !important;
                font-size: 1.1rem !important;
                box-shadow: 0 4px 15px rgba(255, 75, 75, 0.3) !important;
                transition: all 0.2s ease !important;
                height: auto !important;
                min-height: 60px !important;
                margin-top: 10px !important;
            }
            
            [data-testid="stMain"] div.stButton > button:hover {
                transform: translateY(-3px) scale(1.02) !important;
                box-shadow: 0 6px 20px rgba(255, 75, 75, 0.5) !important;
                background: linear-gradient(135deg, #ff3333 0%, #ff5e5e 100%) !important;
            }

            /* Specyficzny styl dla przycisku wyjścia (mniej krzykliwy) */
            div.stButton > button[key*="exit_btn"] {
                background: transparent !important;
                color: #888 !important;
                border: 1px solid #444 !important;
                box-shadow: none !important;
                font-size: 0.9rem !important;
                min-height: 40px !important;
            }

            .target-card {
                background: rgba(255, 255, 255, 0.05);
                border: 2px solid #ff4b4b;
                border-radius: 20px;
                padding: 30px;
                text-align: center;
                font-size: 2.2rem;
                font-weight: bold;
                margin-bottom: 20px;
                color: white;
            }
        </style>
    """, unsafe_allow_html=True)

    # 2. LOGIKA GRY
    lang_cards = [c for c in st.session_state.flashcards if c.get("lang") == L_CODE]
    
    if len(lang_cards) < 4:
        st.warning(f"Potrzebujesz minimum 4 słówek w języku {current_lang_name}, aby zacząć!")
    else:
        # INICJALIZACJA
        if "bal_active" not in st.session_state or st.session_state.get("bal_lang_ref") != L_CODE:
            st.session_state.bal_active = True
            st.session_state.bal_score = 0
            st.session_state.bal_start_time = time.time()
            st.session_state.bal_duration = 30
            st.session_state.bal_lang_ref = L_CODE
            if "bal_target" in st.session_state: del st.session_state.bal_target

        if st.session_state.bal_active and "bal_start_time" in st.session_state:
            elapsed = time.time() - st.session_state.bal_start_time
            time_left = max(0, int(st.session_state.bal_duration - elapsed))
        else:
            time_left = 0

        # KONIEC CZASU
        if time_left <= 0 and st.session_state.bal_active:
            st.session_state.bal_active = False
            st.balloons()
            st.markdown(f"<div style='text-align:center;'><h1>Koniec czasu! 🏁</h1><h2>Wynik: {st.session_state.bal_score} pkt</h2></div>", unsafe_allow_html=True)
            if st.button("Zagraj jeszcze raz", use_container_width=True, type="primary"):
                del st.session_state.bal_active
                st.rerun()
        
        # EKRAN GRY
        elif st.session_state.bal_active:
            if "bal_target" not in st.session_state:
                target = random.choice(lang_cards)
                other_options = [c['pl'] for c in lang_cards if c['id'] != target['id']]
                num_wrong = min(len(other_options), 2)
                wrong = random.sample(other_options, num_wrong)
                options = [target['pl']] + wrong
                random.shuffle(options)
                
                st.session_state.bal_target = target
                st.session_state.bal_options = options

            # UI Statystyk
            st.markdown(f"""
                <div style='display:flex; justify-content:space-around; margin-bottom:10px;'>
                    <span style='font-size:1.2rem;'>⏱️ <b>{time_left}s</b></span>
                    <span style='font-size:1.2rem; color:#ffbc00;'>⭐ <b>{st.session_state.bal_score}</b></span>
                </div>
            """, unsafe_allow_html=True)
            
            st.markdown(f"<div class='target-card'>{st.session_state.bal_target['de']}</div>", unsafe_allow_html=True)

            # RENDEROWANIE BALONÓW (PRZYCISKÓW)
            cols = st.columns(len(st.session_state.bal_options))
            for i, opt in enumerate(st.session_state.bal_options):
                with cols[i]:
                    if st.button(opt, key=f"bal_btn_{i}", use_container_width=True):
                        if opt == st.session_state.bal_target['pl']:
                            # PROSTY SYSTEM PUNKTACJI: +1 pkt
                            st.session_state.bal_score += 1
                            del st.session_state.bal_target
                            st.rerun()
                        else:
                            # Kara za błąd
                            st.session_state.bal_score = max(0, st.session_state.bal_score - 1)
                            st.toast("Pudło! ❌", icon="💨")

        st.write("")
        if st.button("Wyjdź z gry", key="exit_btn", use_container_width=True):
            keys_to_del = ["bal_active", "bal_score", "bal_start_time", "bal_target", "bal_options", "bal_lang_ref"]
            for k in keys_to_del:
                if k in st.session_state: del st.session_state[k]
            st.rerun()
            
# --- 20. ARENA WYZWAŃ (V283 - Fix Column Missing Error) ---
elif choice == "🏆 Arena Wyzwań":
    current_lang_name = st.session_state.get("current_lang", "Niemiecki")
    L_CODE = "de" if current_lang_name == "Niemiecki" else "cs"
    
    st.header("🏆 Arena Wyzwań")
    st.write(f"Rywalizacja w języku {current_lang_name}")

    # 1. POBIERANIE DANYCH (Bezpieczna lista kolumn, które na pewno masz)
    try:
        db = get_db()
        # Wybieramy tylko te kolumny, które standardowo istnieją w Twoim systemie
        res = db.table("user_data").select("username, streak, memory_scores_de, memory_scores_cs, top_balloons_de, top_balloons_cs").execute()
        raw_users = res.data if res.data else []
    except Exception as e:
        st.error(f"Problem z bazą: {e}")
        raw_users = []

    leaderboard_data = []
    
    for u_row in raw_users:
        uname = u_row.get("username", "Anonim")
        streak = u_row.get("streak", 0)
        
        # Wiedza: Liczymy na żywo TYLKO dla aktualnego użytkownika (Ciebie)
        # Dla innych dajemy "---" lub 0, żeby nie przeciążać bazy zapytaniami o ich fiszki
        wiedza_str = "---"
        w_raw = 0
        
        if uname == u:
            my_cards = [c for c in st.session_state.flashcards if c.get("lang", "de") == L_CODE]
            if my_cards:
                today_dt = date.today()
                strong = len([c for c in my_cards if (pd.to_datetime(c.get('next_review', today_dt)).date() - today_dt).days > 6])
                w_raw = int((strong / len(my_cards)) * 100)
                wiedza_str = f"{w_raw}%"

        leaderboard_data.append({
            "Użytkownik": uname,
            "Ogień 🔥": streak,
            "Wiedza 🧠": wiedza_str,
            "w_raw": w_raw,
            "memory": u_row.get(f"memory_scores_{L_CODE}", []),
            "balloons": u_row.get(f"top_balloons_{L_CODE}", [])
        })

    if not leaderboard_data:
        st.info("Ranking jest obecnie pusty.")
    else:
        # 2. RANKINGI GŁÓWNE
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("🔥 Najdłuższa Passa")
            df_s = pd.DataFrame(leaderboard_data).sort_values("Ogień 🔥", ascending=False).head(10)
            st.table(df_s[["Użytkownik", "Ogień 🔥"]])
            
        with col2:
            st.subheader(f"🧠 Twoja Wiedza ({current_lang_name})")
            # Pokazujemy tylko użytkowników, którzy mają policzoną wiedzę (Ciebie)
            df_w = pd.DataFrame(leaderboard_data)
            df_w = df_w[df_w["Wiedza 🧠"] != "---"].sort_values("w_raw", ascending=False)
            if not df_w.empty:
                st.table(df_w[["Użytkownik", "Wiedza 🧠"]])
            else:
                st.caption("Ucz się dalej, aby pojawić się w rankingu!")

        st.divider()

        # 3. RANKINGI GIER
        st.subheader("🧩 Rekordy Gier")
        t_mem, t_bal = st.tabs(["⏱️ Memory", "🎈 Balony"])

        with t_mem:
            mem_rank = []
            for entry in leaderboard_data:
                scores = entry["memory"]
                if scores and isinstance(scores, list):
                    best = min([float(s) for s in scores])
                    mem_rank.append({"Użytkownik": entry["Użytkownik"], "Rekord": f"{best}s", "val": best})
            
            if mem_rank:
                df_m = pd.DataFrame(mem_rank).sort_values("val").head(10)
                st.table(df_m[["Użytkownik", "Rekord"]])
            else:
                st.caption("Brak rekordów w Memory.")

        with t_bal:
            bal_rank = []
            for entry in leaderboard_data:
                scores = entry["balloons"]
                if scores and isinstance(scores, list):
                    # Zabezpieczenie przed brakiem rzutowania na int
                    valid_scores = [int(s) for s in scores if str(s).isdigit()]
                    if valid_scores:
                        best = max(valid_scores)
                        bal_rank.append({"Użytkownik": entry["Użytkownik"], "Rekord": f"{best} pkt", "val": best})
            
            if bal_rank:
                df_b = pd.DataFrame(bal_rank).sort_values("val", ascending=False).head(10)
                st.table(df_b[["Użytkownik", "Rekord"]])
            else:
                st.caption("Brak rekordów w Balonach.")

        # 4. STATUS TWOJEJ POZYCJI
        st.info(f"Rywalizujesz z {len(leaderboard_data)} użytkownikami. Powodzenia!")

# --- 21. GENERATOR SŁÓW (V251 - Multilang + Sidebar Slim Match) ---
elif choice == "📦 Generator":
    # Pobieramy aktualny język i kod z sesji
    current_lang_name = st.session_state.get("current_lang", "Niemiecki")
    L_CODE = "de" if current_lang_name == "Niemiecki" else "cs"
    
    st.header(f"📦 Generator: {current_lang_name}")
    st.write(f"Generuj słówka w języku {current_lang_name} na podstawie poziomu lub tematu.")

    # 1. PANEL STEROWANIA
    with st.container(border=True):
        c1, c2, c3 = st.columns([2, 2, 1])
        with c1:
            gen_lvl = st.selectbox("Poziom (opcjonalnie):", ["Brak", "A1", "A2", "B1", "B2", "C1"], key="gen_lvl_sel")
        with c2:
            gen_topic = st.text_input("Temat (opcjonalnie):", placeholder="np. Podróże, Praca...", key="gen_top_in")
        with c3:
            gen_count = st.number_input("Ilość:", 3, 20, 5, key="gen_cnt_in")
        
        if st.button(f"✨ Generuj listę ({current_lang_name})", use_container_width=True, type="primary"):
            if gen_lvl == "Brak" and not gen_topic:
                st.warning("Wybierz poziom lub wpisz temat!")
            else:
                with st.spinner(f"AI dobiera słownictwo ({current_lang_name})..."):
                    context = f"na poziomie {gen_lvl}" if gen_lvl != "Brak" else ""
                    if gen_topic: context += f" o tematyce: {gen_topic}"
                    
                    # Instrukcja specyficzna dla języka
                    lang_instr = ""
                    if L_CODE == "de":
                        lang_instr = "UWAGA: Każdy rzeczownik NIEMIECKI MUSI posiadać rodzajnik (der, die lub das)."
                    elif L_CODE == "cs":
                        lang_instr = "UWAGA: Generuj słowa w języku CZESKIM."

                    prompt = f"""Wygeneruj {gen_count} unikalnych słówek/fraz w języku {current_lang_name} {context}.
                    {lang_instr}
                    Dla każdego elementu podaj:
                    1. de: słowo (w języku {current_lang_name})
                    2. pl: tłumaczenie na polski
                    3. tags: minimum 3 tagi
                    4. ex_de: przykład użycia (w języku {current_lang_name})
                    5. ex_pl: tłumaczenie przykładu na polski
                    Zwróć WYŁĄCZNIE JSON: {{"flashcards": [{{"de":"", "pl":"", "tags":"", "ex_de":"", "ex_pl":""}}]}}"""
                    
                    try:
                        raw_res = get_openai_response(prompt)
                        data = json.loads(raw_res)
                        st.session_state.temp_generated = data.get("flashcards", [])
                        st.session_state["last_gen_lvl"] = gen_lvl
                    except Exception as e:
                        st.error(f"Błąd AI: {e}")

    # --- 2. SEKCJA EDYCJI I ZATWIERDZANIA ---
    if "temp_generated" in st.session_state and st.session_state.temp_generated:
        st.divider()
        st.subheader("📝 Podgląd i personalizacja")
        
        saved_lvl = st.session_state.get("last_gen_lvl", "Brak")
        lang_col = "Niemiecki" if L_CODE == "de" else "Czeski"

        df_init = []
        for item in st.session_state.temp_generated:
            base_tags = item.get("tags", "")
            if saved_lvl != "Brak" and saved_lvl not in base_tags:
                base_tags = f"{saved_lvl}, {base_tags}"

            df_init.append({
                "Dodaj": True,
                lang_col: item.get("de", ""),
                "Polski": item.get("pl", ""),
                "Kategorie": base_tags,
                "Przykład (Oryg.)": item.get("ex_de", ""),
                "Przykład (PL)": item.get("ex_pl", "")
            })

        edited_df = st.data_editor(
            df_init, 
            use_container_width=True, 
            num_rows="dynamic",
            key="ai_editor_gen_v251"
        )

        col_save, col_cancel = st.columns(2)
        
        if col_save.button(f"🚀 Zapisz {len(edited_df)} słówek", use_container_width=True, type="primary"):
            success_count = 0
            for row in edited_df:
                if row.get("Dodaj", False):
                    new_word = {
                        "de": row[lang_col],
                        "pl": row["Polski"],
                        "category": row["Kategorie"],
                        "next_review": str(date.today()),
                        "level": 0,
                        "origin": "Generator",
                        "lang": L_CODE,
                        "examples": [{"de": row["Przykład (Oryg.)"], "pl": row["Przykład (PL)"]}]
                    }
                    save_word(u, new_word)
                    success_count += 1
            
            st.success(f"Dodano {success_count} słówek ({current_lang_name})!")
            st.session_state.flashcards = load_flashcards(u)
            if "temp_generated" in st.session_state:
                del st.session_state.temp_generated
            st.rerun()

        if col_cancel.button("🗑️ Anuluj", use_container_width=True):
            if "temp_generated" in st.session_state:
                del st.session_state.temp_generated
            st.rerun()

# --- 22. SKANER AI (V270 - Multilang + Vision OCR + Multi-Word Editor) ---
elif choice == "📸 Skaner AI":
    current_lang_name = st.session_state.get("current_lang", "Niemiecki")
    L_CODE = "de" if current_lang_name == "Niemiecki" else "cs"
    
    st.header(f"📸 Skaner AI: {current_lang_name}")
    st.write(f"Zrób zdjęcie tekstu lub wgraj grafikę, a AI wyciągnie z niej słówka w języku {current_lang_name}.")

    # 1. UPLOAD I CAMERA
    cam_col, file_col = st.columns(2)
    img_file = cam_col.camera_input("Zrób zdjęcie tekstu")
    uploaded_file = file_col.file_uploader("Lub wgraj plik obrazu", type=["jpg", "jpeg", "png"])

    active_img = img_file if img_file else uploaded_file

    if active_img:
        img_obj = Image.open(active_img)
        st.image(img_obj, caption="Podgląd skanu", use_container_width=True)
        
        if st.button("🔍 Analizuj obraz przez AI", use_container_width=True, type="primary"):
            with st.spinner(f"Sztuczna inteligencja czyta tekst ({current_lang_name})..."):
                # Dynamiczna instrukcja zależna od języka
                lang_instruction = ""
                if L_CODE == "de":
                    lang_instruction = "Jeśli znajdziesz niemieckie rzeczowniki, dodaj do nich rodzajniki (der, die, das)."
                elif L_CODE == "cs":
                    lang_instruction = "Analizuj tekst w języku CZESKIM. Zwróć uwagę na znaki diakrytyczne (haczki i kreski)."

                prompt = f"""Przeanalizuj ten obraz. Wyciągnij z niego listę najważniejszych słówek i fraz w języku {current_lang_name}.
                {lang_instruction}
                Dla każdego słowa przygotuj:
                - de: słowo w języku {current_lang_name}
                - pl: tłumaczenie na polski
                - tags: kategorie (np. Poziom, Temat)
                - ex_de: zdanie przykładowe w języku {current_lang_name}
                - ex_pl: tłumaczenie zdania na polski
                
                Zwróć TYLKO czysty JSON:
                {{"flashcards": [
                    {{"de": "...", "pl": "...", "tags": "...", "ex_de": "...", "ex_pl": "..."}}
                ]}}"""
                
                try:
                    res_raw = get_openai_response(prompt, img_obj=img_obj)
                    data = json.loads(res_raw)
                    st.session_state.scanner_results = data.get("flashcards", [])
                    st.success(f"Znaleziono {len(st.session_state.scanner_results)} słówek!")
                except Exception as e:
                    st.error(f"Błąd analizy: {e}")

    # --- 2. MASOWY EDYTOR WYNIKÓW SKANOWANIA ---
    if "scanner_results" in st.session_state and st.session_state.scanner_results:
        st.divider()
        st.subheader("📝 Edytuj i zatwierdź znalezione słówka")
        
        lang_col_label = "Niemiecki" if L_CODE == "de" else "Czeski"
        
        # Przygotowanie danych do edytora
        df_init = []
        for item in st.session_state.scanner_results:
            df_init.append({
                "Zapisz": True,
                lang_col_label: item.get("de", ""),
                "Polski": item.get("pl", ""),
                "Kategorie": item.get("tags", "Skaner AI"),
                "Przykład": item.get("ex_de", ""),
                "Przykład PL": item.get("ex_pl", "")
            })

        edited_df = st.data_editor(
            df_init,
            use_container_width=True,
            num_rows="dynamic",
            key="scanner_data_editor"
        )

        col_save, col_cancel = st.columns(2)
        
        if col_save.button(f"🚀 Dodaj wybrane do bazy ({current_lang_name})", use_container_width=True, type="primary"):
            success_count = 0
            for row in edited_df:
                if row.get("Zapisz", False):
                    new_word = {
                        "de": row[lang_col_label],
                        "pl": row["Polski"],
                        "category": row["Kategorie"],
                        "next_review": str(date.today()),
                        "level": 0,
                        "origin": "Skaner AI",
                        "lang": L_CODE,
                        "examples": [{"de": row["Przykład"], "pl": row["Przykład PL"]}]
                    }
                    save_word(u, new_word)
                    success_count += 1
            
            st.session_state.flashcards = load_flashcards(u)
            st.success(f"Dodano {success_count} nowych słówek do Twojej bazy {current_lang_name}!")
            del st.session_state.scanner_results
            st.rerun()

        if col_cancel.button("🗑️ Odrzuć skan", use_container_width=True):
            del st.session_state.scanner_results
            st.rerun()
        
# --- 23. DODAJ (V266 - Multilang + Obsługa Przykładów w obu trybach) ---
elif choice == "➕ Dodaj":
    current_lang_name = st.session_state.get("current_lang", "Niemiecki")
    L_CODE = "de" if current_lang_name == "Niemiecki" else "cs"
    
    st.header(f"➕ Dodaj nowe słówko ({current_lang_name})")
    
    tab1, tab2 = st.tabs(["✍️ Manualnie", "🤖 Asystent AI ✨"])
    
    with tab1:
        @st.fragment
        def manual_add_ui():
            with st.form("manual_add_form", clear_on_submit=True):
                col1, col2 = st.columns(2)
                label_lang = f"Słowo ({L_CODE.upper()}):"
                placeholder_lang = "np. der Hund" if L_CODE == "de" else "np. jablko"
                
                f_de = col1.text_input(label_lang, placeholder=placeholder_lang)
                f_pl = col2.text_input("Tłumaczenie (PL):", placeholder="np. pies / jabłko")
                
                f_cat = st.text_input("Kategorie / Tagi:", placeholder="rzeczownik, jedzenie, A1")
                
                st.write("---")
                st.caption("📖 Dodaj opcjonalne zdanie przykładowe:")
                c_ex1, c_ex2 = st.columns(2)
                f_ex_de = c_ex1.text_input(f"Przykład ({L_CODE.upper()}):", placeholder="Zastosowanie słowa w zdaniu")
                f_ex_pl = c_ex2.text_input("Tłumaczenie przykładu (PL):", placeholder="Tłumaczenie zdania")
                
                if st.form_submit_button("💾 Zapisz do bazy", use_container_width=True, type="primary"):
                    if f_de.strip() and f_pl.strip():
                        # Budujemy listę przykładów, jeśli nie są puste
                        examples_list = []
                        if f_ex_de.strip():
                            examples_list.append({"de": f_ex_de.strip(), "pl": f_ex_pl.strip()})

                        new_word = {
                            "username": u,
                            "de": f_de.strip(),
                            "pl": f_pl.strip(),
                            "category": f_cat.strip(),
                            "next_review": str(date.today()),
                            "level": 0,
                            "origin": "Dodaj",
                            "lang": L_CODE,
                            "examples": examples_list
                        }
                        save_word(u, new_word)
                        st.session_state.flashcards = load_flashcards(u)
                        st.success(f"Pomyślnie dodano ({current_lang_name}): **{f_de}**")
                    else:
                        st.error("Wypełnij przynajmniej słowo i jego tłumaczenie!")
        manual_add_ui()

    with tab2:
        st.info(f"Wpisz słowo, a AI automatycznie przetłumaczy je i stworzy zdanie przykładowe ({current_lang_name}).")
        ai_word = st.text_input(f"Jakie słowo ({L_CODE.upper()}) przygotować?", placeholder="np. Rozhodnutí", key="ai_input_field")
        
        if st.button("Przygotuj dane przez AI ✨", use_container_width=True):
            if ai_word:
                with st.spinner(f"AI analizuje słowo i tworzy przykłady..."):
                    lang_instruction = ""
                    if L_CODE == "de":
                        lang_instruction = "Jeśli słowo jest rzeczownikiem, MUSISZ dodać rodzajnik (der, die, das)."
                    
                    prompt = f"""Przygotuj dane dla słowa/frazy w języku {current_lang_name}: '{ai_word}'.
                    {lang_instruction}
                    Stwórz jedno naturalne zdanie przykładowe.
                    Zwróć WYŁĄCZNIE JSON w formacie:
                    {{
                      "de": "słowo",
                      "pl": "tłumaczenie",
                      "tags": "Poziom, Część mowy, Temat",
                      "ex_de": "zdanie przykładowe",
                      "ex_pl": "tłumaczenie zdania"
                    }}"""
                    
                    try:
                        res = get_openai_response(prompt)
                        data = json.loads(res)
                        st.session_state.single_temp = [data]
                    except Exception as e:
                        st.error(f"Błąd AI: {e}")
            else:
                st.warning("Wpisz słowo!")

        # --- SEKCJA EDYCJI AI ---
        if "single_temp" in st.session_state and st.session_state.single_temp:
            st.divider()
            st.subheader("📝 Sprawdź przykłady przed zapisem")
            
            item = st.session_state.single_temp[0]
            de_col_name = "Oryginał"
            
            df_init = [{
                "Dodaj": True,
                de_col_name: item.get("de", ""),
                "Polski": item.get("pl", ""),
                "Tagi": item.get("tags", ""),
                "Przykład (Oryg.)": item.get("ex_de", ""),
                "Przykład (PL)": item.get("ex_pl", "")
            }]

            edited_df = st.data_editor(
                df_init,
                use_container_width=True,
                num_rows="fixed",
                key="single_word_editor_v2"
            )

            c_save, c_cancel = st.columns(2)
            
            if c_save.button("✅ Dodaj to słówko", use_container_width=True, type="primary"):
                row = edited_df[0]
                if row.get("Dodaj", False):
                    new_word = {
                        "de": row[de_col_name],
                        "pl": row["Polski"],
                        "category": row["Tagi"],
                        "next_review": str(date.today()),
                        "level": 0,
                        "origin": "Dodaj (AI)",
                        "lang": L_CODE,
                        "examples": [{"de": row["Przykład (Oryg.)"], "pl": row["Przykład (PL)"]}]
                    }
                    save_word(u, new_word)
                    st.success(f"Słówko dodane z przykładem!")
                    st.session_state.flashcards = load_flashcards(u)
                    del st.session_state.single_temp
                    st.rerun()

            if c_cancel.button("🗑️ Odrzuć", use_container_width=True):
                del st.session_state.single_temp
                st.rerun()

# --- 24. SŁOWNIK (V275 - Multilang + Examples Display + Audio Fix) ---
elif choice == "📖 Słownik":
    # Pobieramy aktualny język i kody z sesji
    current_lang_name = st.session_state.get("current_lang", "Niemiecki")
    L_CODE = "de" if current_lang_name == "Niemiecki" else "cs"
    L_LABEL = "DE" if L_CODE == "de" else "CS"
    
    st.header(f"📖 Słownik: {current_lang_name}")
    
    # 1. Filtrowanie słówek pod wybrany język
    lang_cards = [c for c in st.session_state.flashcards if c.get("lang", "de") == L_CODE]
    
    # 2. Pobieranie unikalnych tagów dla filtrów
    all_tags = set()
    for c in lang_cards:
        all_tags.update([t.strip() for t in str(c.get('category','')).split(',') if t.strip()])
    
    # 3. UI Wyszukiwarki
    col1, col2 = st.columns([1, 2])
    f_tag = col1.selectbox(f"Kategorie ({current_lang_name}):", ["Wszystkie"] + sorted(list(all_tags)))
    search = col2.text_input("Szukaj słowa (ENTER ⏎):", placeholder=f"Szukaj w {current_lang_name} lub PL...")
    
    # 4. Logika wyszukiwania
    filtered = [
        c for c in lang_cards 
        if (f_tag == "Wszystkie" or f_tag in str(c.get('category',''))) 
        and (search.lower() in str(c.get('de','')).lower() or search.lower() in str(c.get('pl','')).lower())
    ]
    
    st.write("---")
    st.subheader(f"Znaleziono słówek: {len(filtered)}")
    
    # Zabezpieczenie wydajności
    MAX_DISPLAY = 50
    display_list = filtered[:MAX_DISPLAY]
    
    if len(filtered) > MAX_DISPLAY:
        st.warning(f"Wyświetlam pierwsze {MAX_DISPLAY} wyników. Zawęź wyszukiwanie.")
        
    if not display_list:
        st.info(f"Brak słówek w języku {current_lang_name} spełniających kryteria.")
        
    # 5. Renderowanie listy wyników
    for c in display_list:
        flag = "🇩🇪" if L_CODE == "de" else "🇨🇿"
        with st.expander(f"{flag} {c['de']} ➔ 🇵🇱 {c['pl']}"):
            
            # --- SEKCJA SZCZEGÓŁÓW I PRZYKŁADÓW ---
            st.caption(f"🗓️ Powtórka: {c.get('next_review', 'Brak')} | 🏷️ Tagi: {c.get('category', 'Brak')}")
            
            # Pobieranie tekstu przykładu (obsługa starego pola i nowej listy)
            exs = c.get("examples", [])
            example_to_play = None
            
            if exs and isinstance(exs, list) and len(exs) > 0:
                st.markdown("**Przykłady użycia:**")
                for ex in exs:
                    st.write(f"🔹 **{ex.get('de')}**")
                    st.write(f"&nbsp;&nbsp;&nbsp;&nbsp;*{ex.get('pl')}*")
                    example_to_play = ex.get('de') # Bierzemy pierwszy do audio
            elif c.get('example'):
                st.markdown("**Przykład użycia:**")
                st.write(f"🔹 **{c['example']}**")
                example_to_play = c['example']

            st.write("")
            
            # Przycisk Audio
            if st.button(f"🔊 Odsłuchaj wymowę ({L_LABEL})", key=f"audio_{c['id']}", use_container_width=True):
                play_audio(c['de'], example_to_play, lang=L_CODE)
            
            st.divider()
            
            # --- FORMULARZ EDYCJI ---
            with st.form(f"ed_form_{c['id']}"):
                st.markdown("🔍 **Edytuj dane słówka:**")
                n_de = st.text_input(f"Słowo ({current_lang_name})", c['de'])
                n_pl = st.text_input("Tłumaczenie (PL)", c['pl'])
                n_ca = st.text_input("Kategorie / Tagi", c.get('category',''))
                
                if st.form_submit_button("💾 Zapisz zmiany", use_container_width=True):
                    update_word(c['id'], {"de": n_de, "pl": n_pl, "category": n_ca, "lang": L_CODE})
                    st.session_state.flashcards = load_flashcards(u)
                    st.toast("Zaktualizowano! ✅")
                    st.rerun()
            
            # Przycisk Usuwania
            if st.button("🗑️ Usuń słówko", key=f"del_btn_{c['id']}", type="primary", use_container_width=True):
                delete_word(c['id'])
                st.session_state.flashcards = load_flashcards(u)
                st.toast("Słówko zostało usunięte.")
                st.rerun()

# --- 25. STATYSTYKI (V231 - Classic Look + Multilang Filter) ---
elif choice == "📊 Statystyki":
    current_lang_name = st.session_state.get("current_lang", "Niemiecki")
    L_CODE = "de" if current_lang_name == "Niemiecki" else "cs"
    
    st.header(f"📊 Statystyki: {current_lang_name}")
    
    # 1. FILTROWANIE DANYCH POD JĘZYK
    all_cards = st.session_state.flashcards
    # Wybieramy tylko te słówka, które należą do aktualnego języka
    df_full = pd.DataFrame(all_cards)
    if not df_full.empty:
        df = df_full[df_full.get("lang", "de") == L_CODE].copy()
    else:
        df = pd.DataFrame()
        
    ud = st.session_state.user_data
    
    if not df.empty:
        # 1. Metryki główne (Wielkość bazy i Passa)
        c1, c2 = st.columns(2)
        c1.metric(f"Wielkość Bazy ({current_lang_name})", len(df))
        c2.metric("Passa Nauki", f"{ud.get('streak', 0)} dni")
        
        st.write("---")

        # --- REKORDY GIER (Zależne od kluczy językowych de/cs) ---
        st.subheader("🏆 Moje Rekordy w Grach")
        t_mem, t_bal, t_snake = st.tabs(["🧩 Memory", "🎈 Balony", "🐍 Lingwistyczny Wąż"])
        
        with t_mem:
            # Używamy dynamicznego klucza np. memory_scores_de lub memory_scores_cs
            mem_key = f"memory_scores_{L_CODE}"
            mem_scores = ud.get(mem_key, [])
            if mem_scores:
                top3_mem = sorted([float(s) for s in mem_scores])[:3]
                m_cols = st.columns(3)
                icons = ["🥇", "🥈", "🥉"]
                for i, score in enumerate(top3_mem):
                    m_cols[i].metric(f"{icons[i]} Miejsce", f"{score}s")
            else:
                st.info(f"Zagraj w Memory ({current_lang_name}), aby ustanowić rekord!")

        with t_bal:
            # Używamy dynamicznego klucza np. top_balloons_de lub top_balloons_cs
            bal_key = f"top_balloons_{L_CODE}"
            bal_scores = ud.get(bal_key, [])
            if bal_scores:
                top3_bal = sorted([int(s) for s in bal_scores], reverse=True)[:3]
                b_cols = st.columns(3)
                icons = ["🥇", "🥈", "🥉"]
                for i, score in enumerate(top3_bal):
                    b_cols[i].metric(f"{icons[i]} Miejsce", f"{score} pkt")
            else:
                st.info(f"Zagraj w Balonowy Wyścig ({current_lang_name}), aby zdobyć punkty!")

        with t_snake:
            s_max = ud.get("snake_best_chain", 0) # Wąż obecnie jest globalny
            s_wins = ud.get("snake_wins", 0)
            s_loss = ud.get("snake_losses", 0)
            
            s_c1, s_c2, s_c3 = st.columns(3)
            s_c1.metric("Najdłuższa seria", f"{s_max} słów")
            s_c2.metric("Wygrane", f"{s_wins}")
            s_c3.metric("Przegrane", f"{s_loss}")
            
            if s_wins + s_loss > 0:
                win_rate = int((s_wins / (s_wins + s_loss)) * 100)
                st.caption(f"Skuteczność w walce z systemem: {win_rate}%")

        st.write("---")
        
        # 2. KOLUMNY: Czas nauki oraz Fazy zapamiętywania
        col_top1, col_top2 = st.columns(2)
        
        with col_top1:
            st.subheader("⏱️ Czas nauki (minuty)")
            time_stats = ud.get("time_stats", {})
            display_names = {
                "Pow": "Powtórki", "Trn": "Trening", "Qiz": "Quiz", 
                "Fis": "Fiszki", "Tst": "Testy", "Mem": "Memory",
                "War": "Warsztat", "Sta": "Statystyki", "Kon": "Konstruktor",
                "Wan": "Wąż", "Bal": "Balon"
            }
            nav_order = ["Powtórki", "Trening", "Quiz", "Fiszki", "Testy", "Memory", "Warsztat", "Konstruktor", "Wąż", "Bal", "Statystyki", "Inne"]
            
            aggregated_mins = {name: 0 for name in nav_order}
            for code, sec in time_stats.items():
                name = display_names.get(code, "Inne")
                if name in aggregated_mins: aggregated_mins[name] += sec
                else: aggregated_mins["Inne"] += sec
            
            t_data = []
            for name in nav_order:
                mins = int(aggregated_mins[name] // 60)
                if mins > 0 or name in ["Powtórki", "Trening"]:
                    t_data.append({"Moduł": name, "Minuty": mins})
            st.dataframe(pd.DataFrame(t_data), use_container_width=True, hide_index=True)

        with col_top2:
            st.subheader("🧠 Fazy zapamiętywania")
            today = date.today()
            phase_counts = {"Słaba (1-2 dni)": 0, "Średnia (3-6 dni)": 0, "Silna (7+ dni)": 0}
            
            for _, row in df.iterrows():
                try:
                    rev_str = str(row.get('next_review', today))
                    rev_date = datetime.strptime(rev_str, "%Y-%m-%d").date()
                    diff = (rev_date - today).days
                    if diff <= 1: phase_counts["Słaba (1-2 dni)"] += 1
                    elif 2 <= diff <= 6: phase_counts["Średnia (3-6 dni)"] += 1
                    else: phase_counts["Silna (7+ dni)"] += 1
                except:
                    phase_counts["Słaba (1-2 dni)"] += 1
            
            p_list = [{"Faza": k, "Słówek": v} for k, v in phase_counts.items()]
            st.dataframe(pd.DataFrame(p_list), use_container_width=True, hide_index=True)

        st.write("---")
        
        # 3. Tabela z prognozą powtórek
        st.subheader(f"📅 Prognoza powtórek: {current_lang_name}")
        sched = []
        for i in range(10):
            target_date = str(date.today() + timedelta(days=i))
            if i == 0:
                count = len(df[df['next_review'] <= target_date])
                label = "Dzisiaj"
            else:
                count = len(df[df['next_review'] == target_date])
                label = (date.today() + timedelta(days=i)).strftime("%d.%m")
            sched.append({"Dzień": label, "Liczba słówek": count})
        st.dataframe(pd.DataFrame(sched), use_container_width=True, hide_index=True)

        st.write("---")
        
        # 4. Tabele Poziomów i Źródeł
        col_stats1, col_stats2 = st.columns(2)
        
        with col_stats1:
            st.subheader("📈 Słówka wg poziomu")
            levels = ["A1", "A2", "B1", "B2", "C1"]
            level_totals = {lvl: 0 for lvl in levels}
            level_mastered = {lvl: 0 for lvl in levels}
            today_str = str(date.today())
            
            for _, row in df.iterrows():
                cat = row.get('category')
                if pd.isna(cat) or not cat: continue
                cat_str = str(cat).upper()
                next_rev = str(row.get('next_review', today_str))
                is_mastered = next_rev > today_str
                for lvl in levels:
                    if lvl in cat_str:
                        level_totals[lvl] += 1
                        if is_mastered: level_mastered[lvl] += 1
            
            level_data = []
            for lvl in levels:
                total = level_totals[lvl]
                mastered = level_mastered[lvl]
                perc = int(round((mastered / total) * 100)) if total > 0 else 0
                level_data.append({"Poziom": lvl, "Słówek": total, "Opanowane": f"{perc}%"})
            st.dataframe(pd.DataFrame(level_data), use_container_width=True, hide_index=True)
            
        with col_stats2:
            st.subheader("📌 Źródła pozyskania")
            if 'origin' in df.columns:
                origin_counts = df['origin'].value_counts().reset_index()
                origin_counts.columns = ['Źródło', 'Liczba słówek']
                st.table(origin_counts) # Tutaj st.table wyglądało dobrze
        
    else:
        st.info(f"Baza słówek ({current_lang_name}) jest pusta.")

    st.write("---")
    st.subheader(f"📝 Historia testów ({current_lang_name})")
    t_hist = ud.get("test_history", [])
    if t_hist:
        # Filtrujemy historię testów, aby pokazać tylko te z aktualnego języka
        filtered_hist = [t for t in t_hist if t.get("lang", "de") == L_CODE]
        if filtered_hist:
            hist_df = pd.DataFrame(filtered_hist)[::-1]
            hist_df = hist_df[["date", "score", "total", "perc"]]
            hist_df.columns = ["Data", "Wynik", "Suma pytań", "Procent (%)"]
            st.dataframe(hist_df, use_container_width=True, hide_index=True)
        else:
            st.info(f"Brak rozwiązanych testów w języku {current_lang_name}.")
    else:
        st.info("Brak historii testów.")

# --- 26. KONTO (V271 - Full Restore + CEFR Levels + Multilang Safety) ---
elif choice == "⚙️ Konto":
    current_lang_name = st.session_state.get("current_lang", "Niemiecki")
    L_CODE = "de" if current_lang_name == "Niemiecki" else "cs"
    st.header(f"⚙️ Zarządzanie Kontem")
    
    if "acc_msg" in st.session_state:
        st.success(st.session_state.acc_msg)
        del st.session_state.acc_msg

    # --- 1. PREFERENCJE NAUKI ---
    with st.expander("🛠️ Preferencje nauki", expanded=True):
        if "settings" not in st.session_state.user_data:
            st.session_state.user_data["settings"] = {"auto_audio": True, "show_hints": True, "daily_goal": 20, "test_questions": 10}
        
        s = st.session_state.user_data["settings"]
        
        col_pref1, col_pref2 = st.columns(2)
        with col_pref1:
            s["auto_audio"] = st.toggle("Automatyczne Audio", s.get("auto_audio", True))
            s["show_hints"] = st.toggle("Podpowiedzi PL w Quizie", s.get("show_hints", True))
        with col_pref2:
            s["daily_goal"] = st.slider("Cel dnia (min)", 5, 120, s.get("daily_goal", 20))
            s["test_questions"] = st.number_input("Domyślna ilość pytań w teście", 5, 50, s.get("test_questions", 10))
        
        if st.button("💾 Zapisz preferencje", use_container_width=True):
            save_user_data(u, st.session_state.user_data)
            st.toast("Zapisano ustawienia! 💾")

    # --- 2. ZMIANA HASŁA ---
    with st.expander("🔑 Zmień hasło"):
        with st.form("pw_change_form"):
            old_p = st.text_input("Stare hasło", type="password")
            new_p = st.text_input("Nowe hasło", type="password")
            if st.form_submit_button("Zaktualizuj hasło", use_container_width=True):
                db = get_db()
                res = db.table("users_auth").select("*").eq("username", u).execute()
                if res.data and res.data[0]["password_hash"] == hash_pw(old_p):
                    db.table("users_auth").update({"password_hash": hash_pw(new_p)}).eq("username", u).execute()
                    st.success("Hasło zmienione!")
                else:
                    st.error("Błędne stare hasło!")

    # --- 3. DANE (Eksport/Import) ---
    with st.expander("📥 Dane (CSV)"):
        if st.session_state.flashcards:
            df_export = pd.DataFrame(st.session_state.flashcards)
            csv = df_export[["de", "pl", "category", "lang"]].to_csv(index=False).encode('utf-8')
            st.download_button("📥 Pobierz bazę .CSV", data=csv, file_name=f"wobo_export.csv", mime="text/csv", use_container_width=True)
        
        up_file = st.file_uploader("Importuj CSV (de, pl, category, lang)", type="csv")
        if up_file and st.button("🚀 Importuj", use_container_width=True):
            try:
                imp_df = pd.read_csv(up_file)
                new_cards = []
                for _, row in imp_df.iterrows():
                    new_cards.append({
                        "username": u, "de": str(row["de"]), "pl": str(row["pl"]),
                        "category": str(row.get("category", "Import")),
                        "lang": str(row.get("lang", L_CODE)),
                        "next_review": str(date.today()), "level": 0
                    })
                get_db().table("flashcards").insert(new_cards).execute()
                st.session_state.flashcards = load_flashcards(u)
                st.success(f"Zaimportowano {len(new_cards)} słówek!")
            except Exception as e: st.error(f"Błąd: {e}")

    # --- 4. NIEBEZPIECZNA STREFA ---
    with st.expander("🗑️ Niebezpieczna strefa"):
        st.error(f"Tryb zarządzania bazą: **{current_lang_name.upper()}**")
        safety_lock = st.checkbox("Potwierdzam chęć skasowania danych")
        
        # --- KASOWANIE POZIOMÓW (CEFR) ---
        st.subheader("Usuwanie wg poziomów")
        st.caption(f"Usuwa słówka z tagiem poziomu TYLKO dla języka {current_lang_name}.")
        col_lvl1, col_lvl2 = st.columns([2, 1])
        lvl_to_del = col_lvl1.selectbox("Wybierz poziom:", ["A1", "A2", "B1", "B2", "C1"], key="lvl_del_sel")
        
        if col_lvl2.button(f"Skasuj {lvl_to_del}", disabled=not safety_lock, use_container_width=True):
            # Używamy operatora 'ilike', aby znaleźć poziom wewnątrz ciągu kategorii
            res = get_db().table("flashcards").delete().eq("username", u).eq("lang", L_CODE).ilike("category", f"%{lvl_to_del}%").execute()
            # Liczba skasowanych rekordów (Supabase zwraca je w .data przy delete)
            count = len(res.data) if res.data else 0
            st.session_state.flashcards = load_flashcards(u)
            st.session_state.acc_msg = f"Skasowano {count} słówek z poziomu {lvl_to_del} ({current_lang_name})."
            st.rerun()

        st.divider()
        st.subheader("Resety całkowite")
        
        # Reset bazy dla wybranego języka
        if st.button(f"💣 USUŃ WSZYSTKIE SŁÓWKA ({current_lang_name.upper()})", type="primary", disabled=not safety_lock, use_container_width=True):
            res = get_db().table("flashcards").delete().eq("username", u).eq("lang", L_CODE).execute()
            count = len(res.data) if res.data else 0
            st.session_state.flashcards = load_flashcards(u)
            st.session_state.acc_msg = f"Usunięto całą bazę słówek języka {current_lang_name} ({count} sztuk)."
            st.rerun()

        # Globalny reset passy
        if st.button("🔥 Wyzeruj Streak (Konto globalne)", disabled=not safety_lock, use_container_width=True):
            st.session_state.user_data["streak"] = 0
            st.session_state.user_data["last_date"] = "2000-01-01"
            save_user_data(u, st.session_state.user_data)
            st.session_state.acc_msg = "Globalna passa została wyzerowana."
            st.rerun()

# --- 27. ADMIN PRO (V300 - Pełny rozkład z Wężem i Balonem) ---
elif choice == "👑 Admin" and u == ADMIN_USER:
    st.header("👑 Panel Administratora")
    
    if st.button("🔄 Pobierz najświeższe statystyki z bazy"):
        st.cache_data.clear()
        st.rerun()

    st.link_button("💸 OpenAI Billing", "https://platform.openai.com/usage", use_container_width=True)
    
    db = get_db()
    ud_data = db.table("user_data").select("*").execute().data
    all_cards_res = db.table("flashcards").select("username", "origin", "next_review").execute().data

    df_cards_all = pd.DataFrame(all_cards_res) if all_cards_res else pd.DataFrame(columns=["username", "origin", "next_review"])
    
    adm_list = []
    global_time = {}
    
    # Rozszerzona lista kodów (zgodnie z nową kolejnością)
    tracked_codes = ["Pow", "Trn", "Qiz", "Fis", "Tst", "Mem", "War", "Kon", "Wan", "Bal", "Inn"]
    display_names = {
        "Pow": "📅 Powtórki", 
        "Trn": "🚀 Trening", 
        "Qiz": "🕹️ Quiz", 
        "Fis": "🎴 Fiszki",
        "Tst": "📝 Testy", 
        "Mem": "🧠 Memory", 
        "War": "🛠️ Warsztat",
        "Kon": "🏗️ Konstruktor",
        "Wan": "🐍 Lingwistyczny Wąż",
        "Bal": "🎈 Balonowy Wyścig",
        "Inn": "Inne"
    }
    
    today = date.today()

    for user in ud_data:
        username = user["username"]
        user_cards = df_cards_all[df_cards_all["username"] == username]
        oc = user_cards["origin"].value_counts() if not user_cards.empty else {}
        
        # 1. Obliczanie wiedzy (🧠 %)
        strong_cards = 0
        if not user_cards.empty:
            strong_cards = len([c for c in user_cards["next_review"] if (pd.to_datetime(c).date() - today).days > 6])
            wiedza_val = int((strong_cards / len(user_cards)) * 100)
        else:
            wiedza_val = 0

        # 2. Agregacja czasu
        user_stats = user.get("time_stats", {})
        current_user_merged = {code: 0 for code in tracked_codes}
        total_sec = 0
        
        for raw_key, seconds in user_stats.items():
            k = str(raw_key).strip()
            f_code = k if k in tracked_codes else "Inn"
            
            current_user_merged[f_code] += seconds
            total_sec += seconds
            if f_code != "Inn":
                global_time[f_code] = global_time.get(f_code, 0) + seconds

        # 3. Formatowanie danych do głównej tabeli
        raw_seen = user.get("last_seen", "Brak")
        formatted_seen = raw_seen.replace(" ", "  |  ") if " " in raw_seen else raw_seen
        
        r = int(oc.get("Dodaj", 0))
        g = int(oc.get("Generator", 0))
        s = int(oc.get("Skaner", 0))
            
        adm_list.append({
            "Użytkownik": username,
            "Aktywność (Data | Czas)": formatted_seen,
            "🔥": user.get("streak", 0),
            "🧠 %": wiedza_val,
            "Słówka (R|G|S)": f"{len(user_cards)} ({r}|{g}|{s})", 
            "Tst": len(user.get("test_history", [])),
            "Min": int(total_sec // 60),
            "PLN": round(user.get("historical_cost", 0.0), 2),
            "__raw_stats": current_user_merged 
        })
    
    if not adm_list:
        st.warning("Brak danych użytkowników.")
    else:
        df_admin = pd.DataFrame(adm_list)
        
        # --- TABELA 1: GLOBALNY ROZKŁAD AKTYWNOŚCI ---
        st.subheader("📈 Globalny rozkład aktywności")
        total_global_study = sum(global_time.values())
        
        if total_global_study > 0:
            analysis_rows = []
            # Wyświetlamy w zadanej kolejności (z Wężem i Balonem na końcu)
            for code in ["Pow", "Trn", "Qiz", "Fis", "Tst", "Mem", "War", "Kon", "Wan", "Bal"]:
                val_sec = global_time.get(code, 0)
                perc = (val_sec / total_global_study) * 100
                m, _ = divmod(int(val_sec), 60)
                h, m = divmod(m, 60)
                time_str = f"{h}h {m}m" if h > 0 else f"{m}m"

                analysis_rows.append({
                    "Moduł": display_names[code],
                    "Popularność (%)": f"{round(perc, 1)}%",
                    "Łączny czas": time_str
                })
            st.table(pd.DataFrame(analysis_rows).set_index("Moduł"))
        
        st.divider()

        # --- TABELA 2: GŁÓWNA LISTA UŻYTKOWNIKÓW ---
        st.subheader("📋 Podsumowanie kont")
        st.dataframe(
            df_admin.drop(columns=["__raw_stats"]), 
            use_container_width=True, 
            hide_index=True,
            column_config={
                "Użytkownik": st.column_config.TextColumn("Użytkownik", width=100),
                "Aktywność (Data | Czas)": st.column_config.TextColumn("Aktywność (Data | Czas)", width=170),
                "🔥": st.column_config.NumberColumn("🔥", width=45),
                "🧠 %": st.column_config.NumberColumn("🧠 %", width=55, format="%d%%"),
                "Słówka (R|G|S)": st.column_config.TextColumn("Słówka (R|G|S)", width=130),
                "Tst": st.column_config.NumberColumn("Tst", width=45),
                "Min": st.column_config.NumberColumn("Min", width=55),
                "PLN": st.column_config.NumberColumn("PLN", width=80, format="%.2f zł"),
            }
        )
        
        # --- TABELA 3: SZCZEGÓŁY CZASU ---
        with st.expander("🔍 Szczegółowy podział czasu użytkowników (minuty)"):
            detail_rows = []
            # Pełna lista dla tabeli szczegółowej
            valid_codes = ["Pow", "Trn", "Qiz", "Fis", "Tst", "Mem", "War", "Kon", "Wan", "Bal", "Inn"]
            
            for _, row in df_admin.iterrows():
                d_row = {"Użytkownik": row["Użytkownik"]}
                for code in valid_codes:
                    d_row[display_names[code]] = int(row["__raw_stats"][code] // 60)
                detail_rows.append(d_row)
            
            st.dataframe(pd.DataFrame(detail_rows), use_container_width=True, hide_index=True)

# --- 28. SPARING AI (V680 - Precision Correction & Stable Connection) ---
elif choice == "🤖 Sparing AI":
    import openai
    
    current_lang_name = st.session_state.get("current_lang", "Niemiecki")
    L_CODE = "de" if current_lang_name == "Niemiecki" else "cs"
    
    st.header(f"🤖 Sparing AI: {current_lang_name}")

    # --- 1. PRECYZYJNY PARSER ---
    def parse_stable(txt):
        res = {"r": txt, "t": "", "c": None}
        if "|||" in txt:
            p = txt.split("|||")
            r_part = p[0].strip()
            # Usuwamy techniczne przedrostki typu "Reakcja:"
            if r_part.lower().startswith("reakcja:"):
                r_part = r_part[8:].strip()
            
            res["r"] = r_part
            res["t"] = p[1].strip() if len(p) > 1 else ""
            
            if len(p) > 2:
                corr = p[2].strip()
                # Wyświetlamy tylko realne błędy
                if corr.upper() not in ["OK", "BRAK", "NONE", "NULL", "ZDANIE POPRAWNE", "BRAK BŁĘDÓW"]:
                    res["c"] = corr
        return res

    scenarios = {
        "🍽️ Restauracja": "Kellner", "🏥 U lekarza": "Arzt", 
        "💼 Praca": "Chef", "🛒 Zakupy": "Verkäufer", 
        "✈️ Podróż": "Zollbeamter", "☕ Smalltalk": "Freund"
    }

    if "chat_history" not in st.session_state: st.session_state.chat_history = []
    if "chat_scenario" not in st.session_state: st.session_state.chat_scenario = None

    if not st.session_state.chat_scenario:
        st.subheader("Wybierz temat rozmowy:")
        cols = st.columns(3)
        for i, name in enumerate(scenarios.keys()):
            if cols[i % 3].button(name, use_container_width=True):
                st.session_state.chat_scenario = name
                st.session_state.chat_history = []
                st.rerun()
    else:
        # Pasek nawigacji
        c1, c2 = st.columns([4, 1])
        c1.info(f"📍 Temat: **{st.session_state.chat_scenario}**")
        if c2.button("🏁 Koniec"):
            st.session_state.chat_scenario = None
            st.rerun()

        # Renderowanie historii
        for i, msg in enumerate(st.session_state.chat_history):
            role_icon = "🤖" if msg["role"] == "assistant" else "👤"
            with st.chat_message(msg["role"], avatar=role_icon):
                st.write(msg["content"])
                if msg.get("t"): 
                    with st.expander("👁️ Tłumaczenie"): st.caption(msg["t"])
                if msg.get("c"): 
                    st.warning(f"📝 **Korekta:** {msg['c']}")
                if msg["role"] == "assistant":
                    if st.button("🔊 Słuchaj", key=f"aud_{i}"): play_audio(msg["content"], L_CODE)

        # Logika inputu i API
        u_input = st.chat_input(f"Napisz po {current_lang_name.lower()}...")
        
        # Trigger: Brak historii lub nowa wiadomość
        if not st.session_state.chat_history or u_input:
            role = scenarios[st.session_state.chat_scenario]
            
            if u_input:
                st.session_state.chat_history.append({"role": "user", "content": u_input})
                # WZMOCNIONY PROMPT KOREKTY
                prompt = f"""Jesteś {role} ({current_lang_name}).
                Użytkownik napisał: "{u_input}".
                
                ZADANIA:
                1. Reakcja: Odpowiedz naturalnie (krótko!).
                2. Tłumaczenie: Twoja reakcja na PL.
                3. Korekta: Sprawdź "{u_input}". W DE rzeczowniki MUSZĄ być dużą literą (np. 'pommes' -> 'Pommes'). Jeśli jest błąd, popraw go. Jeśli OK, napisz 'OK'.

                FORMAT: Reakcja ||| Tłumaczenie ||| Korekta"""
            else:
                prompt = f"Jesteś {role} ({current_lang_name}). Przywitaj się krótko. FORMAT: Reakcja ||| Tłumaczenie"

            with st.spinner("AI myśli..."):
                try:
                    client = openai.OpenAI(api_key=API_KEY)
                    resp = client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[{"role": "system", "content": prompt}],
                        max_tokens=200,
                        timeout=15.0
                    )
                    data = parse_stable(resp.choices[0].message.content)
                    
                    if u_input:
                        st.session_state.chat_history[-1]["c"] = data["c"]
                    
                    st.session_state.chat_history.append({
                        "role": "assistant", "content": data["r"], "t": data["t"]
                    })
                    st.rerun()
                except Exception as e:
                    st.error("Problem techniczny. Spróbuj wysłać ponownie.")
                    if u_input: st.session_state.chat_history.pop()

# --- 29. LABORATORIUM RODZAJNIKÓW (V1.0 - Ending Rules & Color Feedback) ---
elif choice == "🧪 Laboratorium":
    current_lang_name = st.session_state.get("current_lang", "Niemiecki")
    L_CODE = "de" if current_lang_name == "Niemiecki" else "cs"
    
    st.header(f"🧪 Laboratorium Rodzajników: {current_lang_name}")
    st.write("Trenuj rozpoznawanie rodzaju rzeczownika na podstawie jego końcówki.")

    # 1. REGUŁY KOŃCÓWEK (Logika pedagogiczna)
    RULES = {
        "de": {
            "die": ["ung", "heit", "keit", "schaft", "in", "ion", "ei", "ität"],
            "der": ["ismus", "or", "ig", "ling", "er"],
            "das": ["chen", "lein", "ment", "um", "ma"]
        },
        "cs": {
            "ta": ["ost", "a", "ice", "ba"],
            "ten": ["r", "l", "n", "t", "d", "m", "s", "z"], # spółgłoski
            "to": ["o", "í", "e", "um"]
        }
    }

    # 2. PRZYGOTOWANIE DANYCH
    # Wyciągamy tylko rzeczowniki, które mają w bazie rodzajnik lub zaimek
    def get_gender(word, lang):
        w = word.lower().strip()
        if lang == "de":
            if w.startswith("der "): return "der", word[4:]
            if w.startswith("die "): return "die", word[4:]
            if w.startswith("das "): return "das", word[4:]
        else: # czeski - szukamy zaimków lub zakładamy na podstawie tagów, 
              # tutaj najbezpieczniej sprawdzić czy user dodał słowo z "Ten/Ta/To" 
              # lub po prostu filtrować po końcówce w bazie
            if w.startswith("ten "): return "ten", word[4:]
            if w.startswith("ta "): return "ta", word[4:]
            if w.startswith("to "): return "to", word[4:]
        return None, word

    all_cards = [c for c in st.session_state.flashcards if c.get("lang", "de") == L_CODE]
    nouns = []
    for c in all_cards:
        gender, clean_word = get_gender(c["de"], L_CODE)
        if gender:
            nouns.append({"full": c["de"], "clean": clean_word, "gender": gender, "pl": c["pl"]})

    if len(nouns) < 3:
        st.warning(f"Dodaj więcej rzeczowników z rodzajnikami (np. 'der Hund' lub 'ten dům'), aby odblokować ten moduł.")
    else:
        # Inicjalizacja stanu gry
        if "lab_idx" not in st.session_state:
            st.session_state.lab_idx = random.randint(0, len(nouns)-1)
            st.session_state.lab_feedback = None
            st.session_state.lab_score = 0

        curr = nouns[st.session_state.lab_idx]
        
        # UI: Licznik punktów
        st.caption(f"Punkty: {st.session_state.lab_score}")

        # GŁÓWNA KARTA
        # Kolory dynamiczne zależne od feedbacku
        border_color = "#333"
        if st.session_state.lab_feedback:
            if st.session_state.lab_feedback["is_correct"]:
                border_color = "#28a745" # Zielony (Dobrze)
            else:
                border_color = "#dc3545" # Czerwony (Źle)

        st.markdown(f"""
            <div style="text-align:center; padding:50px; border:5px solid {border_color}; 
            border-radius:20px; background:#111; margin-bottom:20px;">
                <div style="font-size:1.2rem; color:#aaa; margin-bottom:10px;">{curr['pl']}</div>
                <div style="font-size:3.5rem; font-weight:bold; color:white;">{curr['clean']}</div>
            </div>
        """, unsafe_allow_html=True)

        # PRZYCISKI
        options = ["DER", "DIE", "DAS"] if L_CODE == "de" else ["TEN", "TA", "TO"]
        cols = st.columns(3)
        
        for i, opt in enumerate(options):
            if cols[i].button(opt, use_container_width=True, type="primary" if opt.lower() == curr['gender'] and st.session_state.lab_feedback else "secondary"):
                if not st.session_state.lab_feedback:
                    is_correct = opt.lower() == curr['gender']
                    
                    # Szukanie reguły końcówki
                    rule_found = None
                    for g, endings in RULES[L_CODE].items():
                        for e in endings:
                            if curr['clean'].lower().endswith(e):
                                rule_found = f"Zasada końcówki: -{e} zazwyczaj oznacza rodzaj {g.upper()}."
                                break
                    
                    st.session_state.lab_feedback = {
                        "is_correct": is_correct,
                        "rule": rule_found or "To słowo może być wyjątkiem lub rzadszą formą."
                    }
                    if is_correct: st.session_state.lab_score += 1
                    st.rerun()

        # FEEDBACK
        if st.session_state.lab_feedback:
            st.divider()
            if st.session_state.lab_feedback["is_correct"]:
                st.success(f"✨ Doskonale! To jest **{curr['gender'].upper()} {curr['clean']}**")
            else:
                st.error(f"❌ Błąd. Poprawna forma to **{curr['gender'].upper()} {curr['clean']}**")
            
            st.info(st.session_state.lab_feedback["rule"])
            
            if st.button("Następne słowo ➡️", use_container_width=True):
                st.session_state.lab_idx = random.randint(0, len(nouns)-1)
                st.session_state.lab_feedback = None
                st.rerun()

    # Sidebar info
    # --- ZAKTUALIZOWANA ŚCIĄGA W SIDEBARZE (KOLORY FLAG) ---
        with st.sidebar:
            st.divider()
            st.subheader("💡 Ściąga końcówek")
            if L_CODE == "de":
                # NIEMCY: Czarny (Der), Czerwony (Die), Złoty (Das)
                st.markdown("⚫ **DER (Męski):** -ismus, -or, -er, -ig")
                st.markdown("<span style='color:#FF0000;'>🔴</span> **DIE (Żeński):** -ung, -heit, -keit, -schaft", unsafe_allow_html=True)
                st.markdown("<span style='color:#FFCC00;'>🟡</span> **DAS (Nijaki):** -chen, -lein, -um, -ment", unsafe_allow_html=True)
            else:
                # CZECHY: Biały (Ten), Niebieski (Ta), Czerwony (To)
                st.markdown("⚪ **TEN (Męski):** spółgłoski (h, k, r, d...)")
                st.markdown("<span style='color:#11457E;'>🔵</span> **TA (Żeński):** -ost, -a, -ice, -ba", unsafe_allow_html=True)
                st.markdown("<span style='color:#D71920;'>🔴</span> **TO (Nijaki):** -o, -í, -e, -um", unsafe_allow_html=True)
