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

# --- 2. SILNIK BAZY I POMOCNIKI (V222 - AI Cost Tracker & Diacritics Normalize) ---
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
    3. Usunięcie znaków diakrytycznych (haczki, ogonki).
    """
    if not t: return ""
    t = str(t).lower().strip()
    t = t.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    t = "".join(
        c for c in unicodedata.normalize('NFD', t)
        if unicodedata.category(c) != 'Mn'
    )
    t = t.replace("ł", "l")
    return t

def get_openai_response(prompt_text, img_obj=None):
    """
    Wysyła zapytanie do OpenAI i nalicza koszty w PLN do profilu użytkownika.
    """
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

    # --- LOGIKA NALICZANIA KOSZTÓW (PLN) ---
    try:
        # Ceny gpt-4o-mini (Input: $0.15/1M, Output: $0.60/1M)
        usage = res.usage
        cost_usd = (usage.prompt_tokens * 0.00000015) + (usage.completion_tokens * 0.00000060)
        cost_pln = cost_usd * 4.1  # Przelicznik USD/PLN z lekkim zapasem
        
        if "user_data" in st.session_state and u:
            # Dodanie do obecnej wartości
            current_cost = st.session_state.user_data.get("historical_cost", 0.0)
            st.session_state.user_data["historical_cost"] = current_cost + cost_pln
            # Natychmiastowy zapis do bazy danych
            save_user_data(u, st.session_state.user_data)
    except Exception:
        pass # Błąd naliczania kosztów nie powinien przerywać działania AI

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

# --- 3. FUNKCJE DANYCH (V8 - Indentation Fix & Always Update Activity) ---
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
        
        # AKTUALIZACJA AKTYWNOŚCI: Zawsze odświeżamy godzinę przy ładowaniu
        data["last_seen"] = get_now_pl()

        # Reset statystyk czasu (tylko przy pierwszej wizycie danego dnia)
        if last_visit != today_str:
            data["time_stats"] = {} 
            data["last_visit_date"] = today_str

        save_user_data(username, data)
        return data

    # INICJALIZACJA NOWEGO UŻYTKOWNIKA (jeśli nie istnieje w user_data)
    init = {
        "username": username, 
        "streak": 0, 
        "historical_cost": 0.0, 
        "time_stats": {}, 
        "last_ts": time.time(), 
        "last_seen": get_now_pl(),
        "last_date": "2000-01-01", 
        "last_visit_date": today_str,
        "test_history": [],
        "workshop_progress": {},
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
    
    # Przy zapisie również upewniamy się, że data wizyty jest aktualna
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

# --- 4. LOGOWANIE I REJESTRACJA (V560 - Mandatory Email Registration) ---

import hmac
import base64
import time
import hashlib
import re

# Pomocnicza funkcja do pobierania klucza
def get_signature_key():
    key = SUPABASE_KEY
    if not key:
        st.error("⚠️ Błąd bezpieczeństwa: Klucz SUPABASE_KEY nie został odnaleziony. Aplikacja wstrzymana.")
        st.stop()
    return key

def generate_secure_token(username, days_valid=30):
    """Tworzy bezpieczny token z kryptograficznym podpisem."""
    secret = get_signature_key()
    expires = int(time.time()) + (days_valid * 86400)
    message = f"{username}.{expires}"
    signature = hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()
    token_raw = f"{message}.{signature}"
    return base64.urlsafe_b64encode(token_raw.encode()).decode()

def verify_secure_token(token_b64):
    """Weryfikuje token i jego integralność."""
    try:
        secret = get_signature_key()
        token_raw = base64.urlsafe_b64decode(token_b64.encode()).decode()
        parts = token_raw.split('.')
        if len(parts) != 3: return None
        username, expires, signature = parts
        if int(time.time()) > int(expires): return None
        expected_sig = hmac.new(secret.encode(), f"{username}.{expires}".encode(), hashlib.sha256).hexdigest()
        if hmac.compare_digest(signature, expected_sig):
            return username
    except Exception:
        return None
    return None

def is_valid_email(email):
    """Prosta walidacja formatu e-mail."""
    return re.match(r"[^@]+@[^@]+\.[^@]+", email)

if "auth" not in st.session_state:
    st.session_state.auth = False
    st.session_state.is_admin = False
    
    if "token" in st.query_params:
        secure_token = st.query_params["token"]
        verified_user = verify_secure_token(secure_token)
        
        if verified_user:
            db = get_db()
            res = db.table("user_data").select("is_banned, is_admin").eq("username", verified_user).execute()
            if res.data:
                user_info = res.data[0]
                if user_info.get("is_banned"):
                    st.query_params.clear()
                    st.error("Twoja sesja wygasła lub konto zostało zablokowane.")
                    st.stop()
                
                st.session_state.auth = True
                st.session_state.user = verified_user
                st.session_state.is_admin = user_info.get("is_admin", False)
        else:
            st.query_params.clear()
            st.rerun()

if not st.session_state.auth:
    # --- RESPNSYWY TYTUŁ ---
    st.markdown("""
        <style>
            .mobile-title {
                font-size: 8vw;
                font-weight: bold;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
                margin-bottom: 20px;
                display: flex;
                align-items: center;
                gap: 10px;
            }
            @media (min-width: 768px) {
                .mobile-title { font-size: 40px; }
            }
        </style>
        <div class="mobile-title"><span>🚀</span><span>Niemiecki Master</span></div>
    """, unsafe_allow_html=True)

    t1, t2 = st.tabs(["🔐 Logowanie", "📝 Rejestracja"])
    db = get_db()
    
    with t1:
        un = st.text_input("Użytkownik", key="l_u").lower().strip()
        pw = st.text_input("Hasło", type="password", key="l_p")
        remember_me = st.checkbox("Zapamiętaj mnie na tym urządzeniu", value=True)
        
        if st.button("Zaloguj się", use_container_width=True, type="primary"):
            res_auth = db.table("users_auth").select("*").eq("username", un).execute()
            if res_auth.data and res_auth.data[0]["password_hash"] == hash_pw(pw):
                res_data = db.table("user_data").select("is_banned, is_admin").eq("username", un).execute()
                
                if res_data.data and res_data.data[0].get("is_banned"):
                    st.error("🚫 Twoje konto zostało zablokowane.")
                else:
                    st.session_state.auth = True
                    st.session_state.user = un
                    st.session_state.is_admin = res_data.data[0].get("is_admin", False) if res_data.data else False
                    
                    if remember_me:
                        st.query_params["token"] = generate_secure_token(un)
                    else:
                        st.query_params.clear()
                    st.rerun()
            else:
                st.error("Błędne dane logowania")
                
    with t2:
        rn = st.text_input("Nowy użytkownik", key="r_u").lower().strip()
        re_mail = st.text_input("Adres e-mail", key="r_e").strip()
        rp = st.text_input("Hasło", type="password", key="r_p")
        
        st.caption("📧 E-mail jest wymagany do bezpiecznego odzyskiwania hasła.")

        if st.button("Załóż konto", use_container_width=True):
            # 1. Walidacja podstawowa
            if len(rn) < 3 or len(rp) < 4:
                st.error("Login (min. 3) i Hasło (min. 4) są za krótkie.")
            elif not re_mail or not is_valid_email(re_mail):
                st.error("Podaj poprawny adres e-mail!")
            else:
                # 2. Sprawdzenie czy użytkownik lub email istnieją
                check_user = db.table("users_auth").select("username").eq("username", rn).execute()
                check_email = db.table("user_data").select("username").eq("email", re_mail).execute()
                
                if check_user.data:
                    st.error("Ta nazwa użytkownika jest już zajęta!")
                elif check_email.data:
                    st.error("Ten adres e-mail jest już przypisany do innego konta!")
                else:
                    # 3. Rejestracja w obu tabelach
                    try:
                        db.table("users_auth").insert({
                            "username": rn, 
                            "password_hash": hash_pw(rp),
                            "email": re_mail # Synchronizacja e-maila w auth dla porządku
                        }).execute()

                        db.table("user_data").insert({
                            "username": rn, 
                            "email": re_mail,
                            "is_banned": False, 
                            "is_admin": False,
                            "is_shadowbanned": False,
                            "provider": "legacy",
                            "password": rp # Twoja kopia hasła do Panelu Admina
                        }).execute()
                        
                        load_user_data(rn)
                        st.success("Konto gotowe! Logowanie...")
                        time.sleep(1.5)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Błąd podczas tworzenia konta: {e}")
    st.stop()

# --- 5. LOGOWANIE I ŁADOWANIE DANYCH (V560 - Robust Safety Sync) ---

u = st.session_state.get("user")

def load_user_data(username):
    """Pobiera dane profilu i zarządza resetem dziennym oraz blokadami."""
    try:
        res = get_db().table("user_data").select("*").eq("username", username).execute()
        if res.data:
            data = res.data[0]
            
            # --- 1. BEZPIECZNIK: INICJALIZACJA NOWYCH KOLUMN (Dla starych kont) ---
            # Jeśli kolumny w DB są puste (NULL), przypisujemy wartości bezpieczne
            if data.get("is_banned") is None: data["is_banned"] = False
            if data.get("is_shadowbanned") is None: data["is_shadowbanned"] = False
            if data.get("is_admin") is None: data["is_admin"] = False
            if data.get("provider") is None: data["provider"] = "legacy"
            if "email" not in data: data["email"] = None

            # --- 2. ZABEZPIECZENIE: SPRAWDZENIE BANA PRZY ŁADOWANIU ---
            if data.get("is_banned"):
                st.session_state.auth = False
                st.session_state.user = None
                st.error("Konto zostało zablokowane.")
                st.stop()

            today_str = date.today().isoformat()
            yesterday_str = (date.today() - timedelta(days=1)).isoformat()

            # 3. INICJALIZACJA SŁOWNIKÓW (Zabezpieczenie przed brakiem struktur JSON)
            keys_to_init = ["time_stats", "total_time_stats", "settings", "workshop_progress"]
            for key in keys_to_init:
                if key not in data or data[key] is None:
                    data[key] = {}
            
            if "test_history" not in data or data.get("test_history") is None:
                data["test_history"] = []

            # 4. RESET DZIENNY (Czyścimy tylko minuty z dziś)
            last_visit = data.get("last_visit_date", "2000-01-01")
            if last_visit != today_str:
                data["time_stats"] = {}
                data["last_visit_date"] = today_str

            # 5. LOGIKA RESETU PASSY (STREAK)
            last_success = data.get("last_date", "2000-01-01")
            if last_success != today_str and last_success != yesterday_str:
                data["streak"] = 0
            
            return data
    except Exception as e:
        st.error(f"Błąd ładowania profilu: {e}")
    return None

def save_user_data(username, data):
    """Zapisuje dane profilu do bazy i odświeża datę aktywności."""
    if not username: return
    try:
        # Usuwamy pola systemowe Supabase przed wysyłką, aby nie nadpisywać ID
        clean_data = {k: v for k, v in data.items() if k not in ["id", "created_at", "username"]}
        clean_data["last_seen"] = get_now_pl()
        get_db().table("user_data").update(clean_data).eq("username", username).execute()
    except:
        pass

def update_activity(current_choice):
    """Główny silnik: Naliczanie czasu (Dziś + Łącznie) oraz sprawdzanie Celu Dnia."""
    if not current_choice or "user_data" not in st.session_state or not u:
        return

    now = time.time()
    if "last_ts_activity" not in st.session_state:
        st.session_state.last_ts_activity = now
        return

    delta = now - st.session_state.last_ts_activity
    
    # Naliczamy tylko jeśli aktywność trwała od 0.5s do 10 min (anty-idle)
    if 0.5 < delta < 600:
        ud = st.session_state.user_data
        
        # --- PRECYZYJNE MAPOWANIE MODUŁÓW ---
        mapping = {
            "powtorki": "Pow", "trening": "Trn", "quiz": "Qiz", "fiszki": "Fis",
            "laborat": "Lab", "asystent": "Wri", "detektyw": "Det", "warsztat": "War",
            "testy": "Tst", "sparing": "Spa", "memory": "Mem", "konstruktor": "Kon",
            "waz": "Wan", "wyscig": "Bal", "ruletka": "Sur", "pojedynkow": "Due",
            "skaner": "Skn"
        }
        
        # Normalizujemy wybór
        clean_choice = normalize_text(str(current_choice))
        label = "Inn" 
        
        for key_word, code in mapping.items():
            if key_word in clean_choice:
                label = code
                break
        
        # 1. Aktualizacja czasu DZIŚ oraz ŁĄCZNIE
        for stat_key in ["time_stats", "total_time_stats"]:
            curr_dict = dict(ud.get(stat_key, {}))
            curr_val = float(curr_dict.get(label, 0.0))
            curr_dict[label] = curr_val + delta
            ud[stat_key] = curr_dict

        # 2. SPRAWDZANIE CELU DNIA (Skn wykluczony z naliczania postępu, ale czas w Skn jest mierzony)
        target_modules = ["Pow", "Trn", "Qiz", "Fis", "Tst", "Mem", "War", "Kon", "Wan", "Bal", "Lab", "Wri", "Det", "Sur", "Spa", "Due"]
        total_sec_today = sum(ud["time_stats"].get(code, 0) for code in target_modules)
        
        goal_min = ud.get("settings", {}).get("daily_goal", 20)
        today_str = date.today().isoformat()
        
        if total_sec_today >= (goal_min * 60) and ud.get("last_date") != today_str:
            ud["streak"] = ud.get("streak", 0) + 1
            ud["last_date"] = today_str 
            st.toast(f"🔥 Cel dnia osiągnięty! Twoja passa: {ud['streak']} dni", icon="🚀")

        # 3. Zapis zmian do session_state i bazy
        st.session_state.user_data = ud
        save_user_data(u, ud)

    st.session_state.last_ts_activity = now

# --- INICJALIZACJA SESJI ---
if u:
    # Pobierz dane przy wejściu
    if "user_data" not in st.session_state:
        st.session_state.user_data = load_user_data(u)
        # Zabezpieczenie: jeśli po załadowaniu okazało się, że użytkownik ma bana
        if not st.session_state.user_data:
            st.rerun()
            
        st.session_state.flashcards = load_flashcards(u)
        save_user_data(u, st.session_state.user_data)


    # Synchronizacja co 5 minut
    if "last_db_ping" not in st.session_state or time.time() - st.session_state.last_db_ping > 300:
        save_user_data(u, st.session_state.user_data)
        st.session_state.last_db_ping = time.time()

# --- 6. SIDEBAR (V450 - Study Time Sync & Mastery XP) ---
with st.sidebar:
    st.markdown("""
        <style>
            [data-testid="stSidebarNav"] {display: none;}
            
            /* Stylizacja przycisków menu w sidebarze */
            [data-testid="stSidebar"] div.stButton > button {
                width: 100%; 
                text-align: left; 
                background-color: transparent !important;
                border: none; 
                padding: 1px 6px !important; 
                margin: 0px !important;
                border-radius: 4px; 
                font-size: 0.88rem; 
                height: auto; 
                min-height: 28px;
                color: var(--text-color) !important;
            }
            
            hr { margin: 0.4rem 0 !important; opacity: 0.3; }
            
            /* Płynna animacja paska postępu */
            .stProgress > div > div > div > div {
                transition: width 0.5s ease-in-out;
            }
        </style>
    """, unsafe_allow_html=True)

    # 1. DANE UŻYTKOWNIKA I NAGŁÓWEK
    ud = st.session_state.user_data
    st.markdown(f"""
        <div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;'>
            <span style='font-size:0.9rem;'><b>👤 {str(u).capitalize()}</b></span>
            <span style='color:#FF4B4B; font-size:0.85rem;'>🔥 {ud.get('streak', 0)}d</span>
        </div>
    """, unsafe_allow_html=True)

    # 2. WYBÓR JĘZYKA
    if "current_lang" not in st.session_state: 
        st.session_state.current_lang = "Niemiecki"
        
    selected_lang = st.selectbox("Język", options=list(LANG_MAP.keys()), 
                                   format_func=lambda x: LANG_MAP[x]["label"], 
                                   key="lang_sel", label_visibility="collapsed")

    if selected_lang != st.session_state.current_lang:
        st.session_state.current_lang = selected_lang
        st.session_state.choice = "🏠 Start"
        st.rerun()

    L_CODE = LANG_MAP[st.session_state.current_lang]["code"]

    # 3. STATYSTYKI WIEDZY (Oparte na Mastery XP) ORAZ CELU DNIA
    all_c = [c for c in st.session_state.flashcards if c.get("lang") == L_CODE]
    
    wiedza = 0
    if all_c:
        # LICZENIE WIEDZY NA PODSTAWIE XP:
        # Przyjmujemy, że 150 XP to 100% opanowania jednego słowa
        current_total_xp = sum(c.get("mastery_xp", 0) for c in all_c)
        max_possible_xp = len(all_c) * 150
        
        if max_possible_xp > 0:
            wiedza = int((current_total_xp / max_possible_xp) * 100)
        
        wiedza = min(wiedza, 100)

    # --- ZSYNCHRONIZOWANA LISTA MODUŁÓW (Zgodnie z Sekcją 7) ---
    # Dodano: 'Spa' (Sparing AI), 'Due' (Pojedynki) | Wykluczono: 'Skn' (Skaner)
    m_list = [
        "Pow", "Trn", "Qiz", "Fis", "Tst", "Mem", "War", "Kon", 
        "Wan", "Bal", "Lab", "Wri", "Det", "Sur", "Spa", "Due"
    ]
    time_stats = ud.get("time_stats", {})
    total_sec = sum(time_stats.get(c, 0) for c in m_list)
    
    mins_done = int(total_sec // 60)
    goal_mins = ud.get("settings", {}).get("daily_goal", 20)

    st.markdown(f"<div style='font-size:0.75rem; color:#aaa;'>🧠 Wiedza ({L_CODE.upper()}): {wiedza}%</div>", unsafe_allow_html=True)
    st.progress(min(wiedza / 100, 1.0))
    
    st.markdown(f"<div style='font-size:0.75rem; color:#aaa;'>🎯 Cel dnia: {mins_done}/{goal_mins}m</div>", unsafe_allow_html=True)
    st.progress(min(total_sec / (goal_mins * 60), 1.0))
    st.markdown("<hr>", unsafe_allow_html=True)

    # 4. FUNKCJA GENERUJĄCA ELEMENTY MENU
    def menu_item(label, target):
        is_selected = st.session_state.get("choice") == target
        btn_label = f"{'▶ ' if is_selected else ''}{label}"
        if st.button(btn_label, key=f"btn_{target}"):
            st.session_state.choice = target
            st.rerun()

    # 5. STRUKTURA MENU
    choice_now = st.session_state.get("choice", "🏠 Start")
    menu_item("🏠 Start", "🏠 Start")

    # Sekcja NAUKA
    with st.expander("📚 Nauka", expanded=(choice_now in ["📅 Powtórki", "🚀 Trening", "🕹️ Quiz", "🎴 Fiszki", "🧪 Laboratorium", "✍️ Asystent Pisania", "🕵️ Kulturowy Detektyw", "🛠️ Warsztat", "📝 Testy", "🤖 Sparing AI"])):
        for item in ["📅 Powtórki", "🚀 Trening", "🕹️ Quiz", "🎴 Fiszki", "🧪 Laboratorium", "✍️ Asystent Pisania", "🕵️ Kulturowy Detektyw", "🛠️ Warsztat", "📝 Testy", "🤖 Sparing AI"]:
            menu_item(item, item)

    # Sekcja GRY
    list_gry = ["🧠 Memory", "🏗️ Konstruktor", "🐍 Lingwistyczny Wąż", "🎈 Balonowy Wyścig", "🎲 Językowa Ruletka", "⚔️ Klub Pojedynków", "🏆 Arena Wyzwań"]
    with st.expander("🎮 Gry", expanded=(choice_now in list_gry)):
        for item in list_gry:
            menu_item(item, item)

    # Sekcja BAZA SŁÓW
    with st.expander("🗂️ Baza słów", expanded=(choice_now in ["📦 Generator", "📸 Skaner AI", "➕ Dodaj", "📖 Słownik"])):
        for item in ["📦 Generator", "📸 Skaner AI", "➕ Dodaj", "📖 Słownik"]:
            menu_item(item, item)

    st.markdown("<div style='margin-top:4px;'></div>", unsafe_allow_html=True)
    for opt in ["📊 Statystyki", "⚙️ Konto"]:
        menu_item(opt, opt)

    # Sekcja Admina
    if st.session_state.get("is_admin"):
        st.markdown("<hr>", unsafe_allow_html=True)
        st.write("🏁 **STREFA VIP**")
        menu_item("👑 Admin", "👑 Admin")
        menu_item("🏟️ Dynamo Fan-Zone", "🏟️ Dynamo Fan-Zone")

    st.markdown("<hr>", unsafe_allow_html=True)
    
    if st.button("🚪 Wyloguj", use_container_width=True, key="logout_btn"):
        st.query_params.clear()
        for key in list(st.session_state.keys()):
            if key in st.session_state:
                del st.session_state[key]
        st.rerun()

# --- 7. START (V3.7 - Unified Notification Center & Dashboard) ---

choice = st.session_state.get("choice", "🏠 Start")
update_activity(choice)

if choice == "🏠 Start":
    current_lang_name = st.session_state.get("current_lang", "Niemiecki")
    L_CODE = "de" if current_lang_name == "Niemiecki" else "cs"
    u_name = st.session_state.get("user", "Anonim")
    db = get_db()
    
    # --- 0. ZINTEGROWANE CENTRUM POWIADOMIEŃ ---
    all_notices = []
    
    # A. Pobieranie ogłoszeń systemowych
    try:
        res_ann = db.table("system_announcements")\
            .select("*")\
            .or_(f"target.eq.all,target.eq.{u_name}")\
            .eq("is_active", True)\
            .order("created_at", desc=True)\
            .execute()
        if res_ann.data:
            for a in res_ann.data:
                all_notices.append({
                    "title": a['title'],
                    "message": a['message'],
                    "icon": a.get("icon", "📢"),
                    "color": a.get("color", "#2E86C1"),
                    "type": "info"
                })
    except: pass

    # B. Pobieranie oczekujących pojedynków (Wirtualne Ogłoszenie)
    try:
        res_pending = db.table("duels").select("challenger")\
            .eq("opponent", u_name).eq("status", "pending").execute()
        
        if res_pending.data:
            challengers = ", ".join(list(set([d['challenger'] for d in res_pending.data])))
            all_notices.append({
                "title": "Masz nowe wyzwania! ⚔️",
                "message": f"Użytkownicy rzucili Ci rękawicę: {challengers}",
                "icon": "⚔️",
                "color": "#FF4B4B", # Czerwony dla pojedynków
                "type": "duel"
            })
    except: pass

    # C. Wyświetlanie powiadomień w ujednoliconym stylu
    if all_notices:
        for notice in all_notices:
            st.markdown(f"""
                <div style="background-color: {notice['color']}; padding: 12px; border-radius: 10px; 
                            color: white; margin-bottom: 10px; border-left: 5px solid rgba(0,0,0,0.2);">
                    <span style="font-size: 1.2rem; margin-right: 10px;">{notice['icon']}</span>
                    <b>{notice['title']}</b>: {notice['message']}
                </div>
            """, unsafe_allow_html=True)
            
            # Jeśli to pojedynek, dodajemy przycisk akcji bezpośrednio pod ramką
            if notice['type'] == "duel":
                if st.button("ODPOWIEDZ NA WYZWANIE ➔", use_container_width=True, key="go_to_duels_unified"):
                    st.session_state.choice = "⚔️ Klub Pojedynków"
                    st.rerun()

    # --- 1. ANALIZA DANYCH BIEŻĄCYCH ---
    all_cards_full = st.session_state.flashcards
    all_c = [c for c in all_cards_full if c.get("lang", "de") == L_CODE]
    ud = st.session_state.user_data
    today_str = date.today().isoformat()
    
    due_cards = [c for c in all_c if str(c.get("next_review", today_str)) <= today_str]
    hard_cards = [c for c in all_c if c.get("level", 0) < 2]

    # Statystyki czasu (Skn wykluczony z naliczania celu)
    current_stats = ud.get("time_stats", {})
    study_modules = ["Pow", "Trn", "Qiz", "Fis", "Tst", "Mem", "War", "Kon", "Wan", "Bal", "Lab", "Wri", "Det", "Sur", "Spa", "Due"]
    study_seconds = sum(current_stats.get(code, 0) for code in study_modules)
    study_minutes = int(study_seconds // 60)
    daily_goal = ud.get("settings", {}).get("daily_goal", 20)

    # --- 2. NAGŁÓWEK ---
    hello_msg = "Guten Morgen" if L_CODE == "de" else "Dobrý den"
    st.markdown(f"<h3 style='margin-bottom: 0px; font-size: 1.4rem;'>{hello_msg}, {str(u_name).capitalize()}! ☀️</h3>", unsafe_allow_html=True)

    # --- 3. SEKCJA 1: SŁÓWKO DNIA (SPOTLIGHT) ---
    if hard_cards:
        idx_spot = int(hashlib.md5((today_str + "spot").encode()).hexdigest(), 16) % len(hard_cards)
        spot_word = hard_cards[idx_spot]
        
        with st.container(border=True):
            st.markdown(f"<div style='color: #4CAF50; font-size: 0.8rem; font-weight: bold; text-transform: uppercase;'>🔍 Słówko pod lupą</div>", unsafe_allow_html=True)
            st.markdown(f"<h2 style='margin: 0px; padding: 0px;'>{spot_word['de']}</h2>", unsafe_allow_html=True)
            
            col_a, col_b = st.columns([1, 1])
            with col_a:
                with st.expander("👁️ Znaczenie"):
                    st.write(f"**{spot_word['pl']}**")
            with col_b:
                if st.button("🔊 Słuchaj", key="spot_audio_home", use_container_width=True):
                    play_audio(spot_word['de'], lang=L_CODE)
    else:
        st.success("✨ Wszystkie trudne słowa opanowane!")

    # --- 4. SEKCJA 2: ZADANIA NA DZIŚ ---
    st.markdown(f"<div style='margin-top: 10px; font-weight: bold; font-size: 1.1rem;'>🏆 Zadania na dziś</div>", unsafe_allow_html=True)
    
    try:
        # A. Pisanie
        topics_for_teaser = {
            "de": ["Beschreibe deinen Morgen.", "Was sind deine Ziele?", "Erzähle von deinem Hobby."],
            "cs": ["Popiš své ráno.", "Jaké są Twoje cele?", "Vyprávěj o svém koníčku."]
        }
        t_idx = int(hashlib.md5(today_str.encode()).hexdigest(), 16) % len(topics_for_teaser.get(L_CODE, ["..."]))
        current_writing_topic = topics_for_teaser.get(L_CODE, ["..."])[t_idx]
        
        res_w = db.table("writing_history").select("id").eq("username", u_name).eq("lang", L_CODE).gte("created_at", today_str).execute()
        writing_done = len(res_w.data) > 0 if res_w.data else False

        # B. Detektyw
        res_idioms = db.table("idioms_library").select("phrase").eq("lang", L_CODE).execute()
        daily_phrase = "Brak spraw"
        if res_idioms.data:
            idx_det = int(hashlib.md5(today_str.encode()).hexdigest(), 16) % len(res_idioms.data)
            daily_phrase = res_idioms.data[idx_det]['phrase']
        det_done = any(c.get("de") == daily_phrase and c.get("lang") == L_CODE for c in all_cards_full)

        # C. Warsztat
        wrk_goal = 3
        wrk_key_day = f"{today_str}_{L_CODE}"
        mastered_today = ud.get("workshop_progress", {}).get(wrk_key_day, 0)
        workshop_done = mastered_today >= wrk_goal
    except:
        writing_done = det_done = workshop_done = False
        current_writing_topic = daily_phrase = "Błąd połączenia"
        mastered_today = 0

    # Status czasu
    t_icon = "✅" if study_minutes >= daily_goal else "❌"
    st.markdown(f"<div style='font-size: 0.9rem; margin-bottom: 5px;'>{t_icon} Cel czasowy: <b>{study_minutes}/{daily_goal} m</b></div>", unsafe_allow_html=True)

    with st.container(border=True):
        c_w1, c_w2 = st.columns([4, 1])
        c_w1.markdown(f"**{'✅' if writing_done else '✍️'} Pisanie:** *{current_writing_topic[:30]}...*")
        if not writing_done:
            if c_w2.button("GO", key="go_w_home", use_container_width=True):
                st.session_state.choice = "✍️ Asystent Pisania"; st.rerun()
    
    with st.container(border=True):
        c_d1, c_d2 = st.columns([4, 1])
        c_d1.markdown(f"**{'✅' if det_done else '🕵️'} Detektyw:** *{daily_phrase[:30]}...*")
        if not det_done:
            if c_d2.button("GO", key="go_d_home", use_container_width=True):
                st.session_state.choice = "🕵️ Kulturowy Detektyw"; st.rerun()

    with st.container(border=True):
        c_r1, c_r2 = st.columns([4, 1])
        c_r1.markdown(f"**{'✅' if workshop_done else '🛠️'} Warsztat:** *Postęp {mastered_today}/{wrk_goal}*")
        if not workshop_done:
            if c_r2.button("GO", key="go_wr_home", use_container_width=True):
                st.session_state.choice = "🛠️ Warsztat"; st.rerun()

    # --- 5. SEKCJA 3: KULTURA ---
    try:
        res_trivia = db.table("cultural_trivia").select("*").eq("lang", L_CODE).execute()
        if res_trivia.data:
            idx_tr = int(hashlib.md5((today_str + "trivia").encode()).hexdigest(), 16) % len(res_trivia.data)
            trivia = res_trivia.data[idx_tr]
            with st.expander(f"🥨 Ciekawostka: {trivia['title']}"):
                st.write(trivia['content_orig'])
                st.caption(f"PL: {trivia['content_pl']}")
    except: pass

    st.divider()

    # --- 6. SEKCJA 4: FOOTER ---
    col_f1, col_f2 = st.columns(2)
    col_f1.metric("Baza słów", len(all_c))
    col_f2.metric("Do powtórki", len(due_cards))

    with st.expander("🆕 Ostatnio dodane"):
        if all_c:
            for r in reversed(all_c[-3:]): st.write(f"• {r['de']} ({r['pl']})")

# --- 8. POWTÓRKI & TRENING (V401 - Mastery XP & Dual Mode SRS) ---
elif choice in ["📅 Powtórki", "🚀 Trening"]:
    is_r = (choice == "📅 Powtórki")
    current_lang_name = st.session_state.get("current_lang", "Niemiecki")
    L_CODE = "de" if current_lang_name == "Niemiecki" else "cs"
    
    st.header(f"{choice}: {current_lang_name}")
    
    pfx = "rep" if is_r else "trn"
    user_settings = st.session_state.user_data.get("settings", {})
    auto_audio = user_settings.get("auto_audio", True)
    
    # 1. FILTROWANIE SŁÓWEK
    lang_cards = [c for c in st.session_state.flashcards if c.get("lang", "de") == L_CODE]
    
    all_tags = set()
    for c in lang_cards:
        all_tags.update([t.strip() for t in str(c.get('category','')).split(',') if t.strip()])
    
    sel_tag = st.selectbox(f"Zakres nauki ({current_lang_name}):", ["Wszystkie"] + sorted(list(all_tags)), key=f"{pfx}_tag_sel_v401")

    # 2. INICJALIZACJA KOLEJKI
    if f"{pfx}_list" not in st.session_state or st.session_state.get(f"{pfx}_last_tag") != sel_tag:
        pool = [c for c in lang_cards if (sel_tag == "Wszystkie" or sel_tag in str(c.get('category','')))]
        if is_r:
            today_str = str(date.today())
            pool = [c for c in pool if str(c.get("next_review", today_str)) <= today_str]
        
        random.shuffle(pool)
        st.session_state[f"{pfx}_list"] = pool
        st.session_state[f"{pfx}_idx"] = 0
        st.session_state[f"{pfx}_last_tag"] = sel_tag
        st.session_state[f"{pfx}_mode"] = "ask"

    cards = st.session_state.get(f"{pfx}_list", [])
    
    if not cards:
        st.info(f"Brak słówek w sekcji {choice} dla języka {current_lang_name}. ✨")
        if st.button("🔄 Odśwież bazę", use_container_width=True):
            st.session_state.flashcards = load_flashcards(u)
            st.rerun()
    elif st.session_state[f"{pfx}_idx"] >= len(cards):
        st.balloons()
        st.success("Sesja zakończona! Wiedza zaktualizowana. 🏆")
        if st.button("Zacznij od nowa", key=f"{pfx}_restart_v401"):
            for k in [f"{pfx}_list", f"{pfx}_idx", f"{pfx}_mode", f"{pfx}_user_ans"]:
                if k in st.session_state: del st.session_state[k]
            st.rerun()
    else:
        @st.fragment
        def flashcard_engine_xp():
            idx = st.session_state[f"{pfx}_idx"]
            if idx >= len(cards):
                st.rerun()
                return
            
            c_cached = cards[idx]
            c = next((item for item in st.session_state.flashcards if item['id'] == c_cached['id']), c_cached)
            
            # Kierunek (0: obcy->pl, 1: pl->obcy)
            dir_key = f"{pfx}_dir_{c['id']}"
            if dir_key not in st.session_state:
                st.session_state[dir_key] = random.choice([0, 1])

            st.progress(idx / len(cards))
            st.caption(f"Słówko {idx + 1} z {len(cards)} | Poziom: {c.get('mastery_xp', 0)} XP")

            is_target_foreign = (st.session_state[dir_key] == 1)
            display_word = c["de"] if not is_target_foreign else c["pl"]
            target_lang_label = "Polski" if not is_target_foreign else current_lang_name
            correct_val = c["pl"] if not is_target_foreign else c["de"]

            st.markdown(f'''
                <div style="font-size:2.6em; text-align:center; padding:40px; 
                background: #111; border:3px solid {"#4CAF50" if is_r else "#FF9800"}; 
                border-radius:20px; margin-bottom:10px; color: white; line-height: 1.2;">
                    <div style="font-size:0.35em; color:gray; margin-bottom:5px; text-transform: uppercase;">
                        Tłumaczysz na: {target_lang_label}
                    </div>
                    {display_word}
                </div>
            ''', unsafe_allow_html=True)

            if st.session_state[f"{pfx}_mode"] == "ask":
                with st.form(key=f"{pfx}_f_{idx}", clear_on_submit=True):
                    u_in = st.text_input(f"Odpowiedź:", key=f"{pfx}_in_{idx}")
                    if st.form_submit_button("SPRAWDŹ", use_container_width=True, type="primary"):
                        st.session_state[f"{pfx}_user_ans"] = u_in
                        st.session_state[f"{pfx}_mode"] = "res"
                        update_activity(choice)
                        st.rerun(scope="fragment")
            else:
                # NORMALIZACJA I SPRAWDZANIE
                def permissive_clean(text):
                    if not text: return ""
                    t = str(text).lower().strip()
                    t = re.sub(r'^(der|die|das|ten|ta|to)\s+', '', t)
                    t = t.replace("ä", "a").replace("ö", "o").replace("ü", "u").replace("ß", "ss")
                    t = "".join(char for char in unicodedata.normalize('NFD', t) if unicodedata.category(char) != 'Mn')
                    return t.replace("ł", "l").strip()

                user_ans_clean = permissive_clean(st.session_state.get(f"{pfx}_user_ans", ""))
                correct_synonyms = [permissive_clean(s) for s in re.split(r'[/,;]', correct_val) if s.strip()]
                is_correct = user_ans_clean in correct_synonyms
                
                if is_correct: st.success(f"✅ Dobrze! ({correct_val})")
                else: st.error(f"❌ Niepoprawnie. ({correct_val})")
                
                # AUDIO I PRZYKŁADY
                exs = c.get("examples", [])
                ex_foreign = exs[0].get("de") if (exs and isinstance(exs, list) and len(exs) > 0) else c.get('example')
                if ex_foreign:
                    ex_pl = exs[0].get("pl") if (exs and isinstance(exs, list) and len(exs) > 0) else ""
                    st.info(f"📖 **Przykład:** {ex_foreign}" + (f"\n\n🇵🇱 *{ex_pl}*" if ex_pl else ""))
                
                if auto_audio: play_audio(c['de'], ex_foreign, lang=L_CODE)

                st.divider()
                
                # --- NOWA LOGIKA XP I SRS ---
                current_xp = int(c.get("mastery_xp", 0))

                if is_correct:
                    st.write("Oceń łatwość tego słówka (zdobędziesz XP):")
                    c1, c2, c3 = st.columns(3)
                    
                    # Definicje nagród XP i dni
                    rewards = {
                        "🔴 Trudne": {"xp": 5, "days": 1},
                        "🟡 Średnie": {"xp": 10, "days": 3},
                        "🟢 Łatwe": {"xp": 20, "days": 7}
                    }
                    
                    for i, (label, val) in enumerate(rewards.items()):
                        cols = [c1, c2, c3]
                        if cols[i].button(label, use_container_width=True):
                            new_xp = min(current_xp + val["xp"], 200) # Max 200 (Level 5+)
                            new_date = str(date.today() + timedelta(days=val["days"]))
                            
                            # ZAPIS DO BAZY I SESJI
                            update_word(c['id'], {"mastery_xp": new_xp, "next_review": new_date})
                            for card in st.session_state.flashcards:
                                if card['id'] == c['id']: 
                                    card['mastery_xp'] = new_xp
                                    card['next_review'] = new_date
                                    break
                            
                            st.session_state[f"{pfx}_idx"] += 1
                            st.session_state[f"{pfx}_mode"] = "ask"
                            update_activity(choice)
                            st.rerun(scope="fragment")
                else:
                    # KARA ZA BŁĄD (-15 XP, powtórka na dziś)
                    st.warning("Przez błąd słówko traci -15 XP i wraca do kolejki na dzisiaj.")
                    if st.button("Kontynuuj ➡️", use_container_width=True, type="primary"):
                        new_xp = max(current_xp - 15, 0)
                        today_str = str(date.today())
                        
                        update_word(c['id'], {"mastery_xp": new_xp, "next_review": today_str})
                        for card in st.session_state.flashcards:
                            if card['id'] == c['id']: 
                                card['mastery_xp'] = new_xp
                                card['next_review'] = today_str
                                break
                        
                        st.session_state[f"{pfx}_idx"] += 1
                        st.session_state[f"{pfx}_mode"] = "ask"
                        update_activity(choice)
                        st.rerun(scope="fragment")

        flashcard_engine_xp()
        
# --- 9. QUIZ (V400 - Mastery XP Integration) ---
elif choice == "🕹️ Quiz":
    current_lang_name = st.session_state.get("current_lang", "Niemiecki")
    L_CODE = "de" if current_lang_name == "Niemiecki" else "cs"
    
    st.header(f"🕹️ Quiz: {current_lang_name}")
    
    # 1. FILTROWANIE SŁÓWEK (Tylko dla wybranego języka)
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
        def quiz_engine_xp():
            # 1. INICJALIZACJA PYTANIA
            if "q_c" not in st.session_state or st.session_state.get("q_lang_ref") != L_CODE:
                t_raw = random.choice(all_c)
                # Pobieramy najświeższe dane o XP z bazy sesji
                t = next((item for item in st.session_state.flashcards if item['id'] == t_raw['id']), t_raw)
                
                other_pls = [x['pl'] for x in all_c if x['pl'] != t['pl']]
                num_distractors = min(3, len(other_pls))
                distractors = random.sample(other_pls, num_distractors)
                
                opts = distractors + [t['pl']]
                random.shuffle(opts)
                
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
                    <div style="color: #4CAF50; font-size: 0.8rem; margin-top: 10px;">OBECNY POZIOM: {q_c.get('mastery_xp', 0)} XP</div>
                </div>
            """, unsafe_allow_html=True)
            
            st.write("")
            
            if st.session_state.q_s == "ask":
                if show_hints:
                    first_letter = st.session_state.q_a[0].upper()
                    st.info(f"💡 Podpowiedź: Polskie słowo zaczyna się na literę **{first_letter}**")

                current_seed = st.session_state.q_key_seed
                cols = st.columns(2)
                for i, o in enumerate(st.session_state.q_o):
                    if cols[i % 2].button(o, key=f"qbtn_{current_seed}_{i}", use_container_width=True):
                        st.session_state.u_q = o
                        st.session_state.q_s = "res"
                        update_activity(choice)
                        st.rerun(scope="fragment")
            else:
                # 4. WYNIK I NOWA LOGIKA XP/SRS
                is_correct = st.session_state.u_q == st.session_state.q_a
                word_id = q_c.get('id')
                current_xp = int(q_c.get("mastery_xp", 0))
                
                if is_correct:
                    new_xp = min(current_xp + 5, 200) # Stabilny wzrost +5 w Quizie
                    new_date = str(date.today() + timedelta(days=2))
                    st.success(f"✅ **Świetnie!** (+5 XP) Poprawna odpowiedź: {st.session_state.q_a}")
                else:
                    new_xp = max(current_xp - 15, 0) # Kara -15 za błąd
                    new_date = str(date.today())
                    st.error(f"❌ **Błąd!** (-15 XP) Poprawna odpowiedź to: **{st.session_state.q_a}**")
                
                # AKTUALIZACJA BAZY I LOKALNEGO CACHE
                update_word(word_id, {"mastery_xp": new_xp, "next_review": new_date, "level": 0 if not is_correct else q_c.get('level', 0)})
                for card in st.session_state.flashcards:
                    if card['id'] == word_id:
                        card['mastery_xp'] = new_xp
                        card['next_review'] = new_date
                        break

                # --- OBSŁUGA PRZYKŁADÓW I AUDIO ---
                exs = q_c.get("examples", [])
                example_foreign = exs[0].get("de") if (exs and isinstance(exs, list) and len(exs) > 0) else q_c.get('example')
                
                if example_foreign:
                    example_pl = exs[0].get("pl") if (exs and isinstance(exs, list) and len(exs) > 0) else ""
                    st.info(f"📖 **Przykład:** {example_foreign}" + (f"\n\n🇵🇱 *{example_pl}*" if example_pl else ""))
                
                if auto_audio:
                    play_audio(q_c['de'], example_foreign, lang=L_CODE)

                st.write("---")
                if st.button("Następne pytanie ➡️", use_container_width=True, type="primary"):
                    for key in ["q_c", "q_a", "q_o", "q_s", "u_q", "q_key_seed"]:
                        if key in st.session_state: del st.session_state[key]
                        update_activity(choice)
                    st.rerun(scope="fragment")

        quiz_engine_xp()
        
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
                update_activity(choice)
                st.rerun(scope="fragment")
                
            if c2.button("🔄 OBRÓĆ KARTĘ", type="primary", use_container_width=True):
                st.session_state.f_flipped = not st.session_state.f_flipped
                update_activity(choice)
                st.rerun(scope="fragment")
                
            if c3.button("Następna ➡️", use_container_width=True):
                st.session_state.f_idx += 1
                st.session_state.f_flipped = False
                update_activity(choice)
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
                            update_activity(choice)
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

# --- 12. GRA MEMORY (V288 - SQL Scores Integration) ---
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
        
        # --- LOGIKA KOŃCA GRY ---
        if st.session_state.mem_pairs == 6:
            if st.session_state.mem_final_time is None:
                final_t = round(time.time() - st.session_state.mem_start_time, 2)
                st.session_state.mem_final_time = final_t
                
                # ZAPIS DO BAZY (Dual Write: user_data + game_scores)
                try:
                    db = get_db()
                    
                    # A. Nowy System: Centralna tabela wyników (dla Areny Tydzień/Miesiąc)
                    db.table("game_scores").insert({
                        "username": u,
                        "game_name": "memory",
                        "lang": L_CODE,
                        "score": final_t
                    }).execute()

                    # B. Stary System: Top 10 w profilu (dla kompatybilności statystyk)
                    mem_key = f"memory_scores_{L_CODE}"
                    ud = st.session_state.user_data
                    current_scores = ud.get(mem_key, [])
                    if not isinstance(current_scores, list): current_scores = []
                    current_scores.append(final_t)
                    # Sortujemy rosnąco (najlepsze czasy) i bierzemy top 10
                    current_scores = sorted([float(s) for s in current_scores])[:10]
                    
                    db.table("user_data").update({mem_key: current_scores}).eq("username", u).execute()
                    st.session_state.user_data[mem_key] = current_scores
                    
                except Exception as e:
                    pass # Cichy błąd, żeby nie psuć zabawy użytkownikowi

            st.balloons()
            st.success(f"Brawo! Twój czas: {st.session_state.mem_final_time}s")
            
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
                        update_activity(choice)
                        st.rerun(scope="fragment")
                    else:
                        status[idx] = "flipped"
                        update_activity(choice)
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
            update_activity(choice)
            st.rerun(scope="fragment")

    memory_engine()

    # PRZYCISK RESETU NA DOLE
    if st.button("Wygeneruj nową tablicę", type="secondary", use_container_width=True):
        init_memory_game()
        st.rerun()
                
# --- 13. WARSZTAT SŁÓWEK (V323 - Persistent Progress Edition) ---
elif choice == "🛠️ Warsztat":
    current_lang_name = st.session_state.get("current_lang", "Niemiecki")
    L_CODE = "de" if current_lang_name == "Niemiecki" else "cs"
    today_str = date.today().isoformat()
    
    # TRWAŁA LOGIKA LICZNIKA (zsynchronizowana z Sekcją 7)
    ud = st.session_state.user_data
    if "workshop_progress" not in ud or ud["workshop_progress"] is None:
        ud["workshop_progress"] = {}
    
    # Klucz unikalny dla dnia i języka (np. 2026-05-11_de)
    wrk_day_key = f"{today_str}_{L_CODE}"
    mastered_today = ud["workshop_progress"].get(wrk_day_key, 0)
    
    st.header(f"🛠️ Warsztat: {current_lang_name}")
    st.write(f"Skup się na słowach, które wymagają utrwalenia. Opanuj 3, by zaliczyć zadanie dnia!")

    # 1. INICJALIZACJA LISTY SESJI (tymczasowa lista słów do przerobienia)
    if "w_list" not in st.session_state or st.session_state.get("w_lang_ref") != L_CODE:
        lang_cards = [c for c in st.session_state.flashcards if c.get("lang", "de") == L_CODE]
        hard_cards = [c for c in lang_cards if c.get("level", 0) < 2]
        
        if len(hard_cards) < 5 and lang_cards:
            hard_cards = sorted(lang_cards, key=lambda x: x.get("level", 0))[:10]

        random.shuffle(hard_cards)
        st.session_state.w_list = hard_cards[:15] 
        st.session_state.w_idx = 0
        st.session_state.w_show = False
        st.session_state.w_lang_ref = L_CODE

    # 2. LOGIKA WYŚWIETLANIA
    if not st.session_state.w_list:
        st.success(f"Twoja lista trudnych słówek dla języka {current_lang_name} jest pusta! ✨")
        if st.button("Odśwież bazę"): st.rerun()
    
    elif st.session_state.w_idx >= len(st.session_state.w_list):
        st.balloons()
        st.success(f"Sesja warsztatowa ({current_lang_name}) zakończona!")
        if st.button("Zacznij kolejną rundę", use_container_width=True):
            for k in ["w_list", "w_idx", "w_show", "w_lang_ref"]:
                if k in st.session_state: del st.session_state[k]
            st.rerun()
    else:
        # Silnik warsztatu
        @st.fragment
        def workshop_engine():
            idx = st.session_state.w_idx
            w_list = st.session_state.w_list
            curr = w_list[idx]
            
            # Paski postępu (persistent mastered_today)
            st.progress(min(mastered_today / 3, 1.0))
            st.caption(f"Słówko {idx + 1}/{len(w_list)} | Dzisiejszy cel ({current_lang_name}): {mastered_today}/3")

            with st.container(border=True):
                st.markdown(f"<h1 style='text-align: center; margin-bottom: 20px;'>{curr['de']}</h1>", unsafe_allow_html=True)
                
                if st.session_state.w_show:
                    st.markdown(f"<h3 style='text-align: center; color: #FF5252; margin-top: -10px;'>{curr['pl']}</h3>", unsafe_allow_html=True)
                    
                    ex_obj = curr.get('examples', [])
                    example_text = ""
                    if ex_obj and isinstance(ex_obj, list) and len(ex_obj) > 0:
                        example_text = ex_obj[0].get('de', '')
                    elif curr.get('example'): 
                        example_text = curr['example']

                    if example_text:
                        st.info(f"💡 Przykład: {example_text}")
                    
                    if st.session_state.user_data.get("settings", {}).get("auto_audio", True):
                        play_audio(curr['de'], example_text if example_text else None, lang=L_CODE)
                
                st.write("")
                if not st.session_state.w_show:
                    if st.button("👁️ Pokaż odpowiedź", use_container_width=True, type="primary"):
                        st.session_state.w_show = True
                        update_activity(choice)
                        st.rerun(scope="fragment")
                else:
                    col_a, col_b = st.columns(2)
                    with col_a:
                        if st.button("❌ Nadal trudne", use_container_width=True):
                            card = st.session_state.w_list.pop(st.session_state.w_idx)
                            st.session_state.w_list.append(card)
                            st.session_state.w_show = False
                            update_activity(choice)
                            st.rerun(scope="fragment")
                    
                    with col_b:
                        if st.button("✅ Już rozumiem", use_container_width=True):
                            # --- TRWAŁY ZAPIS POSTĘPU ---
                            current_val = ud["workshop_progress"].get(wrk_day_key, 0)
                            ud["workshop_progress"][wrk_day_key] = current_val + 1
                            save_user_data(u, ud)
                            # ----------------------------
                            
                            st.session_state.w_idx += 1
                            st.session_state.w_show = False
                            # Rerun całości, aby odświeżyć licznik mastered_today w nagłówku fragmentu
                            st.rerun()

        workshop_engine()

    st.divider()
    if st.button("🔄 Wylosuj inny zestaw słów", type="secondary", use_container_width=True):
        for k in ["w_list", "w_idx", "w_show", "w_lang_ref"]:
            if k in st.session_state: del st.session_state[k]
        st.rerun()

# --- 14. KONSTRUKTOR SŁÓW (V317 - Ultra-Force Mobile Grid) ---
elif choice == "🏗️ Konstruktor":
    current_lang_name = st.session_state.get("current_lang", "Niemiecki")
    L_CODE = "de" if current_lang_name == "Niemiecki" else "cs"
    
    st.markdown(f"<h2 style='text-align: center;'>🏗️ Konstruktor</h2>", unsafe_allow_html=True)

    # 1. CSS - NUCLEAR OPTION DLA UKŁADU POZIOMEGO
    st.markdown("""
        <style>
            /* WYMUSZENIE POZIOMEGO UKŁADU NAWET NA MAŁYCH EKRANACH */
            @media (max-width: 640px) {
                /* Celujemy w kontener kolumn dla liter */
                div[data-testid="stHorizontalBlock"]:has(button[key*="btn_k"]) {
                    flex-direction: row !important;
                    flex-wrap: wrap !important;
                    display: flex !important;
                    justify-content: center !important;
                }
                
                /* Blokujemy rozciąganie się kolumn do 100% szerokości */
                div[data-testid="stHorizontalBlock"]:has(button[key*="btn_k"]) div[data-testid="column"] {
                    width: auto !important;
                    flex: 0 1 auto !important;
                    min-width: 50px !important; /* Szerokość przycisku + margines */
                }
            }

            /* WYGLĄD PRZYCISKÓW-LITEREK (Przywrócenie wyglądu przycisku) */
            button[key*="btn_k"] {
                height: 50px !important;
                width: 45px !important;
                background-color: rgba(128, 128, 128, 0.2) !important;
                border: 2px solid rgba(128, 128, 128, 0.4) !important;
                border-radius: 10px !important;
                color: var(--text-color) !important;
                font-weight: bold !important;
                font-size: 1.3rem !important;
                box-shadow: 0 2px 4px rgba(0,0,0,0.2) !important;
                margin: 2px !important;
            }

            button[key*="btn_k"]:disabled {
                opacity: 0.3 !important;
                border: 1px solid transparent !important;
                box-shadow: none !important;
            }

            /* SLOT NA ODPOWIEDŹ */
            .slot-box {
                font-size: 2rem;
                letter-spacing: 5px;
                text-align: center;
                background: rgba(255, 75, 75, 0.05);
                border: 2px dashed #ff4b4b;
                border-radius: 15px;
                padding: 15px;
                margin: 20px 0;
                color: var(--text-color);
                min-height: 70px;
                display: flex;
                align-items: center;
                justify-content: center;
            }
        </style>
    """, unsafe_allow_html=True)

    # 2. LOGIKA DANYCH
    lang_cards = [c for c in st.session_state.flashcards if c.get("lang") == L_CODE]
    
    if not lang_cards:
        st.warning(f"Baza {current_lang_name} jest pusta.")
    else:
        if "konstr_word" not in st.session_state or st.session_state.get("konstr_lang_ref") != L_CODE:
            card = random.choice(lang_cards)
            word = str(card[L_CODE]).strip()
            letters = list(word)
            random.shuffle(letters)
            st.session_state.konstr_word = word
            st.session_state.konstr_pl = card['pl']
            st.session_state.konstr_pool = letters
            st.session_state.konstr_ans = ""
            st.session_state.konstr_used_indices = []
            st.session_state.konstr_lang_ref = L_CODE

        # Zadanie
        st.info(f"Przetłumacz: **{st.session_state.konstr_pl}**")

        # Slot na odpowiedź
        target_len = len(st.session_state.konstr_word)
        current_ans = st.session_state.konstr_ans
        display_ans = "".join([current_ans[i] if i < len(current_ans) else "_" for i in range(target_len)])
        st.markdown(f"<div class='slot-box'>{display_ans}</div>", unsafe_allow_html=True)

        # 3. KLAWIATURA (Wymuszone kolumny)
        # Tworzymy rząd liter
        letter_cols = st.columns(len(st.session_state.konstr_pool))
        for idx, char in enumerate(st.session_state.konstr_pool):
            with letter_cols[idx]:
                label = "␣" if char == " " else char
                is_used = idx in st.session_state.konstr_used_indices
                # Klucz przycisku zawiera 'btn_k' dla selektora CSS
                if st.button(label, key=f"btn_k_{idx}", disabled=is_used):
                    st.session_state.konstr_ans += char
                    st.session_state.konstr_used_indices.append(idx)
                    st.rerun()

        st.write("") # Odstęp

        # 4. PRZYCISKI FUNKCYJNE (Standardowe st.columns - będą się układać pionowo na mobile, co jest OK)
        f1, f2, f3 = st.columns(3)
        with f1:
            if st.button("🔄 Reset", key="f_reset", use_container_width=True):
                st.session_state.konstr_ans = ""; st.session_state.konstr_used_indices = []; st.rerun()
        with f2:
            can_undo = len(st.session_state.konstr_used_indices) > 0
            if st.button("⬅️ Cofnij", key="f_undo", use_container_width=True, disabled=not can_undo):
                st.session_state.konstr_ans = st.session_state.konstr_ans[:-1]
                st.session_state.konstr_used_indices.pop(); st.rerun()
        with f3:
            if st.button("⏭️ Pomiń", key="f_skip", use_container_width=True):
                del st.session_state.konstr_word; st.rerun()

        # 5. WALIDACJA
        if st.session_state.konstr_ans == st.session_state.konstr_word:
            st.balloons()
            st.success(f"Poprawnie: **{st.session_state.konstr_word}**")
            if st.button("Następne ➡️", key="f_next", type="primary", use_container_width=True):
                del st.session_state.konstr_word; st.rerun()

# --- 15. LINGWISTYCZNY WĄŻ (V2.4 - Global Leaderboard Sync) ---
elif choice == "🐍 Lingwistyczny Wąż":
    import re
    import random
    import time
    
    current_lang_name = st.session_state.get("current_lang", "Niemiecki")
    L_CODE = "de" if current_lang_name == "Niemiecki" else "cs"
    
    st.markdown(f"## 🐍 Lingwistyczny Wąż: {current_lang_name}")

    # 1. LOGIKA CZYSZCZENIA TEKSTU
    def get_clean_text(text):
        if not text: return ""
        clean = text.lower().strip()
        # Usuwamy rodzajniki/zaimki, żeby nie psuły gry w węża
        clean = re.sub(r'^(der|die|das|ten|ta|to)\s+', '', clean)
        # Zostawiamy same litery
        clean = "".join([c for c in clean if c.isalpha()])
        return clean

    def is_valid_snake_word(card):
        # Wykluczamy czasowniki, bo w wężu najlepiej gra się rzeczownikami
        cat = str(card.get('category', '')).lower()
        return "czasownik" not in cat and "verb" not in cat

    # 2. PRZYGOTOWANIE BAZY
    pool = [c for c in st.session_state.flashcards if c.get("lang") == L_CODE and is_valid_snake_word(c)]

    if len(pool) < 3:
        st.warning(f"Masz za mało słówek w bazie {current_lang_name}, by zacząć (wymagane min. 3 nie-czasowniki).")
        st.stop()

    # 3. FUNKCJA ZAPISU WYNIKÓW (Zintegrowana z nową Areną)
    def save_snake_results(is_win):
        ud = st.session_state.user_data
        chain_len = len(st.session_state.snake_chain)
        
        try:
            db = get_db()
            
            # A. NOWY SYSTEM: Zapis do tabeli globalnej dla Areny (Tydzień/Miesiąc)
            db.table("game_scores").insert({
                "username": u,
                "game_name": "snake",
                "lang": L_CODE,
                "score": chain_len
            }).execute()

            # B. STARY SYSTEM: Statystyki profilu
            if chain_len > ud.get("snake_best_chain", 0):
                ud["snake_best_chain"] = chain_len
                st.toast(f"🔥 NOWY REKORD: {chain_len} słów!", icon="🏆")
            
            if is_win:
                ud["snake_wins"] = ud.get("snake_wins", 0) + 1
            else:
                ud["snake_losses"] = ud.get("snake_losses", 0) + 1
                
            save_user_data(u, ud)
        except Exception as e:
            # Cichy błąd, by nie przerywać gry
            pass

    # 4. EKRAN STARTOWY
    if "snake_status" not in st.session_state:
        st.info("Zasady: Dodaj słowo zaczynające się na ostatnią literę poprzedniego. Tylko słowa z Twojej bazy!")
        diff = st.selectbox("Poziom trudności bota:", ["Łatwy", "Średni", "Trudny"], key="snake_diff_sel")
        if st.button("Zacznij grę 🚀", use_container_width=True):
            first_word = random.choice(pool)
            st.session_state.snake_chain = [first_word]
            st.session_state.snake_used_ids = {first_word['id']}
            st.session_state.snake_status = "player"
            st.session_state.snake_diff = diff
            st.rerun()
        st.stop()

    # 5. WIZUALIZACJA ŁAŃCUCHA
    chain = st.session_state.snake_chain
    last_word_clean = get_clean_text(chain[-1][L_CODE])
    req_letter = last_word_clean[-1] if last_word_clean else ""

    st.write("⛓️ **Łańcuch słów:**")
    for i, word in enumerate(chain[-5:]):
        pos = len(chain) - len(chain[-5:]) + i
        is_sys = (pos % 2 == 0)
        with st.chat_message("assistant" if is_sys else "user"):
            st.write(f"**{word[L_CODE]}** — {word['pl']}")

    st.divider()

    # --- KOLEJ GRACZA ---
    if st.session_state.snake_status == "player":
        player_moves = [c for c in pool if get_clean_text(c[L_CODE]).startswith(req_letter) and c['id'] not in st.session_state.snake_used_ids]
        
        if not player_moves:
            st.error(f"💀 Koniec gry! Nie masz w bazie słowa na literę: **{req_letter.upper()}**")
            st.session_state.snake_winner = "System 🤖"
            st.session_state.snake_status = "end"
            save_snake_results(is_win=False)
            st.rerun()
        
        st.write(f"👉 Twoja kolej! Wpisz słowo na literę: **{req_letter.upper()}**")
        
        with st.form("snake_input_form", clear_on_submit=True):
            u_in = st.text_input("Słowo:").strip()
            c1, c2 = st.columns([2, 1])
            
            if c1.form_submit_button("Dodaj 🔗", use_container_width=True):
                u_clean = get_clean_text(u_in)
                found = [c for c in pool if get_clean_text(c[L_CODE]) == u_clean]
                
                if not found:
                    st.error("Nie znaleziono tego słowa w Twojej bazie.")
                elif found[0]['id'] in st.session_state.snake_used_ids:
                    st.error("To słowo już zostało użyte!")
                elif u_clean[0] != req_letter:
                    st.error(f"Zła litera! Musisz zacząć od '{req_letter.upper()}'.")
                else:
                    st.session_state.snake_chain.append(found[0])
                    st.session_state.snake_used_ids.add(found[0]['id'])
                    st.session_state.snake_status = "system"
                    st.rerun()
            
            if c2.form_submit_button("Poddaję się"):
                st.session_state.snake_status = "end"
                st.session_state.snake_winner = "System 🤖"
                save_snake_results(is_win=False)
                st.rerun()

    # --- KOLEJ SYSTEMU ---
    elif st.session_state.snake_status == "system":
        with st.status("System szuka odpowiedzi...", expanded=True):
            time.sleep(1.0)
            bot_moves = [c for c in pool if get_clean_text(c[L_CODE]).startswith(req_letter) and c['id'] not in st.session_state.snake_used_ids]
            
            fail_chance = {"Łatwy": 0.4, "Średni": 0.15, "Trudny": 0.01}.get(st.session_state.snake_diff, 0)
            
            if bot_moves and random.random() > fail_chance:
                bot_choice = random.choice(bot_moves)
                st.session_state.snake_chain.append(bot_choice)
                st.session_state.snake_used_ids.add(bot_choice['id'])
                st.session_state.snake_status = "player"
                st.rerun()
            else:
                st.session_state.snake_status = "end"
                st.session_state.snake_winner = f"{u.capitalize()} 🏆"
                st.balloons()
                save_snake_results(is_win=True)
                st.rerun()

    # --- EKRAN KOŃCOWY ---
    elif st.session_state.snake_status == "end":
        st.success(f"### 🎉 Zwycięzca: {st.session_state.snake_winner}")
        st.info(f"Długość łańcucha: **{len(st.session_state.snake_chain)}** słów.")
        
        if st.button("Zagraj jeszcze raz 🔄", use_container_width=True, type="primary"):
            for k in ["snake_status", "snake_chain", "snake_used_ids", "snake_winner", "snake_diff"]:
                if k in st.session_state: del st.session_state[k]
            st.rerun()


# --- 16. BALONOWY WYŚCIG (V3.18 - Rules & Global Leaderboard Sync) ---
elif choice == "🎈 Balonowy Wyścig":
    import time
    import random
    
    current_lang_name = st.session_state.get("current_lang", "Niemiecki")
    L_CODE = "de" if current_lang_name == "Niemiecki" else "cs"
    u = st.session_state.get("user", "Anonim")
    
    # 1. STYLIZACJA CSS
    st.markdown("""
        <style>
            .target-card {
                background: rgba(255, 75, 75, 0.1);
                border: 3px solid #ff4b4b;
                border-radius: 20px;
                padding: 20px;
                text-align: center;
                font-size: 2.2rem;
                font-weight: bold;
                margin-bottom: 20px;
                color: var(--text-color);
            }
            [data-testid="stMain"] div.stButton > button {
                background: #ff4b4b !important;
                color: white !important;
                border-radius: 30px !important;
                font-weight: bold !important;
                height: 60px !important;
                transition: transform 0.1s !important;
            }
            [data-testid="stMain"] div.stButton > button:active {
                transform: scale(0.95) !important;
            }
        </style>
    """, unsafe_allow_html=True)

    # 2. PRZYGOTOWANIE PULI SŁÓWEK
    if "bal_cards_pool" not in st.session_state or st.session_state.get("bal_lang_ref") != L_CODE:
        st.session_state.bal_cards_pool = [c for c in st.session_state.flashcards if c.get("lang") == L_CODE]
        st.session_state.bal_lang_ref = L_CODE

    if len(st.session_state.bal_cards_pool) < 4:
        st.warning(f"Potrzebujesz przynajmniej 4 słówek w języku {current_lang_name}, aby rozpocząć wyścig!")
        st.stop()

    if "bal_state" not in st.session_state:
        st.session_state.bal_state = "START"

    # --- EKRAN STARTOWY ---
    if st.session_state.bal_state == "START":
        st.markdown("<h2 style='text-align: center;'>🎈 Balonowy Wyścig</h2>", unsafe_allow_html=True)
        
        st.info("""
        🚀 **ZASADY WYŚCIGU:**
        * Masz równe **30 sekund** na zdobycie jak największej liczby punktów.
        * Dopasuj polskie tłumaczenie do słowa wyświetlonego na głównej karcie.
        * **Punktacja:** Poprawna odpowiedź to **+1 pkt**, błędna to **-1 pkt**.
        * Walcz o jak najwyższy wynik, aby wspiąć się na szczyt **Areny Wyzwań**!
        """)
        
        if st.button("🚀 ROZPOCZNIJ WYŚCIG", use_container_width=True, type="primary"):
            st.session_state.bal_state = "PLAYING"
            st.session_state.bal_score = 0
            st.session_state.bal_start_time = time.time()
            if "bal_target" in st.session_state: del st.session_state.bal_target
            st.rerun()

    # --- EKRAN WYNIKÓW (GAME OVER) ---
    elif st.session_state.bal_state == "FINISHED":
        st.balloons()
        st.markdown(f"""
            <div style='text-align:center;'>
                <h1>Koniec Wyścigu! 🏁</h1>
                <h2 style='color:#ff4b4b;'>TWÓJ WYNIK: {st.session_state.bal_score} pkt</h2>
            </div>
        """, unsafe_allow_html=True)
        
        col1, col2 = st.columns(2)
        if col1.button("🔄 Spróbuj ponownie", use_container_width=True):
            st.session_state.bal_state = "START"
            st.rerun()
        if col2.button("🏆 Zobacz Arenę", use_container_width=True):
            st.session_state.choice = "🏆 Arena Wyzwań"
            st.rerun()

    # --- EKRAN GRY ---
    elif st.session_state.bal_state == "PLAYING":
        
        @st.fragment(run_every="1s") 
        def game_fragment():
            elapsed = time.time() - st.session_state.bal_start_time
            time_left = max(0, int(30 - elapsed))

            # --- LOGIKA ZAKOŃCZENIA I ZAPISU ---
            if time_left <= 0:
                final_score = st.session_state.bal_score
                ud = st.session_state.user_data
                bal_key = f"top_balloons_{L_CODE}"
                
                try:
                    db = get_db()
                    # 1. Zapis do globalnej tabeli rankingowej
                    db.table("game_scores").insert({
                        "username": u,
                        "game_name": "balloons",
                        "lang": L_CODE,
                        "score": float(final_score)
                    }).execute()

                    # 2. Aktualizacja lokalnego Top 10 użytkownika
                    current_scores = ud.get(bal_key, [])
                    if not isinstance(current_scores, list): current_scores = []
                    current_scores.append(final_score)
                    current_scores = sorted([int(s) for s in current_scores], reverse=True)[:10]
                    
                    ud[bal_key] = current_scores
                    save_user_data(u, ud)
                except:
                    pass # Zabezpieczenie przed błędem połączenia
                
                st.session_state.bal_state = "FINISHED"
                st.rerun()

            # GENEROWANIE NOWEGO ZADANIA
            if "bal_target" not in st.session_state:
                pool = st.session_state.bal_cards_pool
                target = random.choice(pool)
                # Przygotowanie błędnych opcji
                others = [c['pl'] for c in pool if c['id'] != target['id']]
                wrong = random.sample(others, min(len(others), 2))
                options = [target['pl']] + wrong
                random.shuffle(options)
                
                st.session_state.bal_target = target
                st.session_state.bal_options = options

            # INTERFEJS GRY
            st.markdown(f"""
                <div style='display:flex; justify-content:space-between; font-weight:bold; font-size:1.5rem;'>
                    <span>⏱️ Pozostało: {time_left}s</span>
                    <span style='color:#ffbc00;'>⭐ Wynik: {st.session_state.bal_score}</span>
                </div>
            """, unsafe_allow_html=True)
            
            st.markdown(f"<div class='target-card'>{st.session_state.bal_target[L_CODE]}</div>", unsafe_allow_html=True)

            cols = st.columns(3)
            for i, opt in enumerate(st.session_state.bal_options):
                if cols[i].button(opt, key=f"bal_btn_{i}", use_container_width=True):
                    if opt == st.session_state.bal_target['pl']:
                        st.session_state.bal_score += 1
                        st.toast("Świetnie! +1", icon="✅")
                    else:
                        st.session_state.bal_score = max(0, st.session_state.bal_score - 1)
                        st.toast("Błąd! -1", icon="❌")
                    
                    # Usunięcie celu wymusza losowanie nowego przy następnym fragmencie
                    del st.session_state.bal_target
                    st.rerun()

        game_fragment()


# --- 17. JĘZYKOWA RULETKA (V400 - Survival XP & Memory Refresh Edition) ---
elif choice == "🎲 Językowa Ruletka":
    import hashlib
    from datetime import datetime, date, timedelta
    
    current_lang_name = st.session_state.get("current_lang", "Niemiecki")
    L_CODE = "de" if current_lang_name == "Niemiecki" else "cs"
    today_str = date.today().isoformat()
    
    st.header(f"🎲 Językowa Ruletka: {current_lang_name}")
    st.markdown("""
        <style>
            .survival-card {
                background: #111;
                border: 4px solid #ff4b4b;
                border-radius: 25px;
                padding: 30px;
                text-align: center;
                margin-bottom: 20px;
                box-shadow: 0 10px 30px rgba(255, 75, 75, 0.2);
            }
            .stat-box {
                font-size: 1.5rem; font-weight: bold; color: #ff4b4b; text-align: center;
            }
            .bonus-text {
                color: #FFD700; font-weight: bold; font-size: 1.1rem;
            }
        </style>
    """, unsafe_allow_html=True)

    # 1. PRZYGOTOWANIE BAZY
    all_c = [c for c in st.session_state.flashcards if c.get("lang", "de") == L_CODE]
    if len(all_c) < 10:
        st.warning(f"Dodaj min. 10 słówek, aby odblokować Ruletkę.")
        st.stop()

    def extract_gender(word, lang):
        w = word.lower().strip()
        if lang == "de":
            if w.startswith("der "): return "der", word[4:]
            if w.startswith("die "): return "die", word[4:]
            if w.startswith("das "): return "das", word[4:]
        else:
            if w.startswith("ten "): return "ten", word[4:]
            if w.startswith("ta "): return "ta", word[3:]
            if w.startswith("to "): return "to", word[3:]
        return None, word

    if "surv_state" not in st.session_state or st.session_state.get("surv_lang_ref") != L_CODE:
        st.session_state.surv_state = "START"
        st.session_state.surv_score = 0
        st.session_state.surv_lang_ref = L_CODE

    # --- EKRAN STARTOWY / GAMEOVER ---
    if st.session_state.surv_state == "START":
        st.info("⚠️ **REWOLUCJA RULETKI:** Każda dobra odpowiedź odsuwa powtórkę o **+1 dzień** i daje **XP**. Przetrwaj serię 15 rund, aby zgarnąć **Survival Bonus!**")
        if st.button("🔥 ROZPOCZNIJ PRZETRWANIE", use_container_width=True, type="primary"):
            st.session_state.surv_state = "PLAYING"; st.session_state.surv_score = 0
            if "surv_task" in st.session_state: del st.session_state.surv_task
            st.rerun()

    elif st.session_state.surv_state == "GAMEOVER":
        st.error(f"### 💀 KONIEC GRY!")
        st.markdown(f"<div class='stat-box'>TWÓJ WYNIK: {st.session_state.surv_score}</div>", unsafe_allow_html=True)
        col1, col2 = st.columns(2)
        if col1.button("🔄 Spróbuj ponownie", use_container_width=True, type="primary"):
            st.session_state.surv_state = "START"; st.rerun()
        if col2.button("🏆 Arena Wyzwań", use_container_width=True):
            st.session_state.choice = "🏆 Arena Wyzwań"; st.rerun()

    # --- EKRAN GRY ---
    elif st.session_state.surv_state == "PLAYING":
        @st.fragment
        def survival_engine_xp():
            if "surv_task" not in st.session_state:
                word_raw = random.choice(all_c)
                # Świeże dane z sesji
                word = next((item for item in st.session_state.flashcards if item['id'] == word_raw['id']), word_raw)
                
                score = st.session_state.surv_score
                
                # Losowanie trybu
                if score < 5:
                    mode = random.choice(["QUIZ_DE_PL", "FAST_MATCH"])
                elif score < 12:
                    mode = random.choice(["QUIZ_DE_PL", "QUIZ_PL_DE", "LAB", "FAST_MATCH"])
                else:
                    mode = random.choice(["QUIZ_PL_DE", "LAB", "WRITE", "FAST_MATCH"])
                
                gender, clean = extract_gender(word['de'], L_CODE)
                if mode == "LAB" and not gender: mode = "QUIZ_DE_PL"
                
                task = {"word": word, "mode": mode, "gender": gender, "clean": clean}
                
                if mode == "QUIZ_DE_PL":
                    others = [x['pl'] for x in all_c if x['id'] != word['id']]
                    opts = random.sample(others, min(len(others), 3)) + [word['pl']]
                    random.shuffle(opts); task["opts"] = opts
                elif mode == "QUIZ_PL_DE":
                    others = [x['de'] for x in all_c if x['id'] != word['id']]
                    opts = random.sample(others, min(len(others), 3)) + [word['de']]
                    random.shuffle(opts); task["opts"] = opts
                elif mode == "FAST_MATCH":
                    is_correct = random.random() > 0.5
                    display_pl = word['pl'] if is_correct else random.choice([x['pl'] for x in all_c if x['id'] != word['id']])
                    task["fast_pl"] = display_pl
                    task["fast_is_correct"] = is_correct

                st.session_state.surv_task = task

            t = st.session_state.surv_task
            
            # Nagłówek statusu
            c_header1, c_header2 = st.columns([1, 1])
            c_header1.markdown(f"🔥 SERIA: **{st.session_state.surv_score}**")
            c_header2.markdown(f"<div style='text-align:right; font-size:0.8rem; color:gray;'>SŁOWO: {t['word'].get('mastery_xp', 0)} XP</div>", unsafe_allow_html=True)
            
            # Karta pytania
            display_word = t['word']['de']
            if t['mode'] == 'QUIZ_PL_DE': display_word = t['word']['pl']
            if t['mode'] == 'LAB': display_word = t['clean']
            
            st.markdown(f"""
                <div class="survival-card">
                    <div style="color:#888; font-size:0.8rem; text-transform:uppercase; margin-bottom:10px;">Tryb: {t['mode'].replace('_',' ')}</div>
                    <div style="font-size:2.2rem; font-weight:bold; color:white;">{display_word}</div>
                    {"<div style='font-size:1.5rem; color:#ff4b4b; margin-top:10px;'>= " + t['fast_pl'] + "?</div>" if t['mode'] == 'FAST_MATCH' else ""}
                </div>
            """, unsafe_allow_html=True)

            user_ans = None
            
            # Obsługa trybów
            if t['mode'] in ["QUIZ_DE_PL", "QUIZ_PL_DE"]:
                cols = st.columns(2)
                for i, o in enumerate(t['opts']):
                    if cols[i%2].button(o, key=f"surv_q_{i}", use_container_width=True):
                        user_ans = (o == (t['word']['pl'] if t['mode']=="QUIZ_DE_PL" else t['word']['de']))

            elif t['mode'] == "FAST_MATCH":
                c1, c2 = st.columns(2)
                if c1.button("✅ PRAWDA", use_container_width=True): user_ans = (t['fast_is_correct'] == True)
                if c2.button("❌ FAŁSZ", use_container_width=True): user_ans = (t['fast_is_correct'] == False)

            elif t['mode'] == "LAB":
                options = ["DER", "DIE", "DAS"] if L_CODE == "de" else ["TEN", "TA", "TO"]
                cols = st.columns(3)
                for i, o in enumerate(options):
                    if cols[i].button(o, key=f"surv_l_{i}", use_container_width=True):
                        user_ans = (o.lower() == t['gender'])

            elif t['mode'] == "WRITE":
                with st.form("surv_w_form", clear_on_submit=True):
                    u_txt = st.text_input("Wpisz tłumaczenie PL:").strip().lower()
                    if st.form_submit_button("ZATWIERDŹ", use_container_width=True):
                        correct_synonyms = [normalize_text(s) for s in re.split(r'[/,;]', t['word']['pl'])]
                        user_ans = normalize_text(u_txt) in correct_synonyms

            # --- LOGIKA WYNIKU I REWOLUCYJNYCH ZMIAN ---
            if user_ans is not None:
                if user_ans:
                    st.session_state.surv_score += 1
                    word_id = t['word']['id']
                    
                    # 1. Obliczanie XP i Survival Bonus
                    xp_gain = 2 # Baza
                    if st.session_state.surv_score % 15 == 0:
                        xp_gain += 10 # Bonus co 15 punktów serii
                        st.toast(f"🔥 SURVIVAL BONUS! +10 XP dodatkowo!", icon="🔥")
                    
                    current_xp = int(t['word'].get('mastery_xp', 0))
                    new_xp = min(current_xp + xp_gain, 200)
                    
                    # 2. Memory Refresh (Push Date +1)
                    # Bierzemy obecną datę powtórki słowa; jeśli jest w przeszłości, zaczynamy od dzisiaj
                    try:
                        current_rev = datetime.strptime(t['word'].get('next_review', today_str), "%Y-%m-%d").date()
                        base_date = max(current_rev, date.today())
                    except:
                        base_date = date.today()
                    
                    new_date = (base_date + timedelta(days=1)).isoformat()
                    
                    # 3. Zapis do DB i lokalnego Cache
                    update_word(word_id, {"mastery_xp": new_xp, "next_review": new_date})
                    for card in st.session_state.flashcards:
                        if card['id'] == word_id:
                            card['mastery_xp'] = new_xp
                            card['next_review'] = new_date
                            break
                    
                    del st.session_state.surv_task
                    st.toast(f"Dobrze! XP: +{xp_gain} | Pamięć: +1 dzień", icon="✅")
                    update_activity(choice)
                    st.rerun(scope="fragment")
                else:
                    # KONIEC GRY
                    final_score = st.session_state.surv_score
                    try:
                        db = get_db()
                        db.table("game_scores").insert({
                            "username": u, 
                            "game_name": "survival", 
                            "lang": L_CODE, 
                            "score": float(final_score)
                        }).execute()
                        
                        ud = st.session_state.user_data
                        surv_key = f"survival_scores_{L_CODE}"
                        scores = ud.get(surv_key, [])
                        if not isinstance(scores, list): scores = []
                        scores.append(final_score)
                        ud[surv_key] = sorted([int(s) for s in scores], reverse=True)[:10]
                        save_user_data(u, ud)
                    except: pass
                    st.session_state.surv_state = "GAMEOVER"; st.rerun()

        survival_engine_xp()

# --- 19. KLUB POJEDYNKÓW (V1.6 - Battle Reports & Points Fix) ---
elif choice == "⚔️ Klub Pojedynków":
    import json
    import time
    import random

    current_lang_name = st.session_state.get("current_lang", "Niemiecki")
    L_CODE = "de" if current_lang_name == "Niemiecki" else "cs"
    u_name = st.session_state.get("user", "Anonim")
    db = get_db()

    st.markdown("<h1 style='text-align: center;'>⚔️ Klub Pojedynków</h1>", unsafe_allow_html=True)

    # --- 1. CENTRUM RAPORTÓW (POWIADOMIENIA DLA CHALLENGERA) ---
    try:
        # Szukamy pojedynków, które my wysłaliśmy, są zakończone, ale ich jeszcze nie widzieliśmy
        res_reports = db.table("duels").select("*")\
            .eq("challenger", u_name)\
            .eq("status", "finished")\
            .eq("challenger_seen", False).execute()
        
        if res_reports.data:
            st.subheader("🚩 Nowe raporty z Twoich wyzwań")
            for rep in res_reports.data:
                win_status = "✅ WYGRANA!" if u_name in str(rep['winner']) else "❌ PRZEGRANA"
                with st.container(border=True):
                    col_r1, col_r2 = st.columns([3, 1])
                    col_r1.markdown(f"**{win_status}** vs **{rep['opponent']}** ({rep['level']})")
                    col_r1.caption(f"Twój wynik: {rep['score_challenger']}/10 | Przeciwnik: {rep['score_opponent']}/10")
                    if col_r2.button("Oznacz jako przeczytane", key=f"seen_{rep['id']}"):
                        db.table("duels").update({"challenger_seen": True}).eq("id", rep['id']).execute()
                        st.rerun()
            st.divider()
    except Exception as e:
        pass

    # --- 2. PANCERNA FUNKCJA AKTUALIZACJI STATYSTYK ---
    def update_user_duel_results(username, pts, is_win, is_loss):
        try:
            res = db.table("user_data").select("duel_points, duel_wins, duel_losses").eq("username", username).execute()
            if res.data:
                curr = res.data[0]
                # Obsługa None/NULL - kluczowe dla zliczania punktów
                new_pts = int(curr.get('duel_points') or 0) + pts
                new_wins = int(curr.get('duel_wins') or 0) + (1 if is_win else 0)
                new_losses = int(curr.get('duel_losses') or 0) + (1 if is_loss else 0)
                
                db.table("user_data").update({
                    "duel_points": new_pts,
                    "duel_wins": new_wins,
                    "duel_losses": new_losses
                }).eq("username", username).execute()
        except:
            pass

    t1, t2, t3, t4 = st.tabs(["🆕 Nowe Wyzwanie", "📥 Oczekujące", "📜 Historia", "🏆 Ranking"])

    # --- TAB 1: NOWE WYZWANIE ---
    with t1:
        if "duel_setup" not in st.session_state:
            st.subheader("Rzuć wyzwanie")
            res_users = db.table("user_data").select("username").execute()
            all_users = sorted([row['username'] for row in res_users.data if row['username'] != u_name])
            
            col1, col2 = st.columns(2)
            target_user = col1.selectbox("Wybierz przeciwnika:", all_users)
            duel_level = col2.selectbox("Poziom trudności:", ["A1", "A2", "B1", "B2", "C1"])

            if st.button("🚀 Rozpocznij i wyślij wyzwanie", use_container_width=True, type="primary"):
                res_v = db.table("master_vocab").select("id, word, translation").eq("lang", L_CODE).eq("level", duel_level).limit(100).execute()
                if len(res_v.data) >= 10:
                    selected = random.sample(res_v.data, 10)
                    st.session_state.duel_setup = {"opp": target_user, "lvl": duel_level, "voc": selected, "ids": [v['id'] for v in selected]}
                    st.session_state.duel_step = 0
                    st.session_state.duel_score = 0
                    st.session_state.duel_start_time = time.time()
                    st.session_state.duel_sent = False 
                    st.rerun()
                else: st.error("Za mało słówek w bazie na tym poziomie.")
        
        else:
            setup = st.session_state.duel_setup
            idx = st.session_state.duel_step
            if idx < 10:
                word_obj = setup['voc'][idx]
                st.info(f"Pytanie {idx+1}/10 | Wyzwanie dla: **{setup['opp']}**")
                
                opt_key = f"opts_game_{idx}"
                if opt_key not in st.session_state:
                    correct = word_obj['translation']
                    others = list(set([v['translation'] for v in setup['voc'] if v['translation'] != correct]))
                    all_opts = random.sample(others, min(len(others), 3)) + [correct]
                    random.shuffle(all_opts)
                    st.session_state[opt_key] = all_opts
                
                st.subheader(f"Jak przetłumaczysz: **{word_obj['word']}**?")
                cols = st.columns(2)
                for i, o in enumerate(st.session_state[opt_key]):
                    if cols[i%2].button(o, key=f"dbtn_{idx}_{i}", use_container_width=True):
                        if o == word_obj['translation']: st.session_state.duel_score += 1
                        st.session_state.duel_step += 1
                        st.rerun()
            else:
                if not st.session_state.get("duel_sent"):
                    t_fin = round(time.time() - st.session_state.duel_start_time, 2)
                    s_fin = st.session_state.duel_score
                    db.table("duels").insert({
                        "challenger": u_name, "opponent": setup['opp'], "lang": L_CODE, "level": setup['lvl'],
                        "word_ids": setup['ids'], "score_challenger": s_fin, "time_challenger": t_fin, "status": "pending"
                    }).execute()
                    st.session_state.duel_sent = True
                    st.session_state.duel_final_msg = f"Wyzwanie wysłane do {setup['opp']}! Wynik zapisany."
                
                st.success(st.session_state.duel_final_msg)
                if st.button("Powrót do menu"):
                    for k in list(st.session_state.keys()):
                        if k.startswith("opts_game_") or k.startswith("duel_"): del st.session_state[k]
                    st.rerun()

    # --- TAB 2: OCZEKUJĄCE (ODPOWIADANIE NA WYZWANIE) ---
    with t2:
        if "active_duel" not in st.session_state:
            res_p = db.table("duels").select("*").eq("opponent", u_name).eq("status", "pending").execute()
            if not res_p.data: 
                st.info("Brak nowych wyzwań.")
            else:
                for d in res_p.data:
                    with st.expander(f"⚔️ {d['challenger']} wyzywa Cię! ({d['level']})"):
                        st.write(f"Język: **{d['lang'].upper()}**")
                        c1, c2 = st.columns(2)
                        if c1.button("✅ Akceptuj", key=f"acc_{d['id']}", use_container_width=True):
                            res_v = db.table("master_vocab").select("*").in_("id", d['word_ids']).execute()
                            v_map = {v['id']: v for v in res_v.data}
                            st.session_state.active_duel = d
                            st.session_state.active_voc = [v_map[vid] for vid in d['word_ids']]
                            st.session_state.active_step = 0
                            st.session_state.active_score = 0
                            st.session_state.active_time = time.time()
                            st.session_state.active_sent = False 
                            st.rerun()
                        if c2.button("❌ Odrzuć", key=f"rej_{d['id']}", use_container_width=True):
                            db.table("duels").update({"status": "declined"}).eq("id", d['id']).execute()
                            st.rerun()
        else:
            ad, av = st.session_state.active_duel, st.session_state.active_voc
            idx = st.session_state.active_step
            if idx < 10:
                w_obj = av[idx]
                st.error(f"POJEDYNEK: {ad['challenger']} vs {u_name} | {idx+1}/10")
                opt_key = f"aopts_game_{idx}"
                if opt_key not in st.session_state:
                    correct = w_obj['translation']
                    others = list(set([v['translation'] for v in av if v['translation'] != correct]))
                    all_opts = random.sample(others, min(len(others), 3)) + [correct]
                    random.shuffle(all_opts)
                    st.session_state[opt_key] = all_opts
                
                st.subheader(f"Słowo: **{w_obj['word']}**")
                cols = st.columns(2)
                for i, o in enumerate(st.session_state[opt_key]):
                    if cols[i%2].button(o, key=f"abtn_{idx}_{i}", use_container_width=True):
                        if o == w_obj['translation']: st.session_state.active_score += 1
                        st.session_state.active_step += 1
                        st.rerun()
            else:
                if not st.session_state.get("active_sent"):
                    t_opp = round(time.time() - st.session_state.active_time, 2)
                    s_opp = st.session_state.active_score
                    s_cha, t_cha = ad['score_challenger'], ad['time_challenger']
                    c_name = ad['challenger']
                    
                    # ROZSTRZYGNIĘCIE
                    winner_final = ""
                    if s_opp > s_cha:
                        winner_final = u_name
                        update_user_duel_results(u_name, 10, True, False) # My wygrywamy
                        update_user_duel_results(c_name, 0, False, True) # Challenger przegrywa
                    elif s_cha > s_opp:
                        winner_final = c_name
                        update_user_duel_results(c_name, 10, True, False) # Challenger wygrywa
                        update_user_duel_results(u_name, 0, False, True) # My przegrywamy
                    else:
                        if t_opp < t_cha: # My szybsi
                            winner_final = f"{u_name} (Szybszy)"
                            update_user_duel_results(u_name, 5, True, False)
                            update_user_duel_results(c_name, 3, False, False)
                        else: # Challenger szybszy
                            winner_final = f"{c_name} (Szybszy)"
                            update_user_duel_results(c_name, 5, True, False)
                            update_user_duel_results(u_name, 3, False, False)

                    db.table("duels").update({
                        "score_opponent": s_opp, "time_opponent": t_opp, 
                        "status": "finished", "winner": winner_final, "challenger_seen": False
                    }).eq("id", ad['id']).execute()
                    
                    st.session_state.active_sent = True
                    st.session_state.active_final_msg = f"Koniec! Wynik {s_opp}:{s_cha}. Zwycięzca: {winner_final}"

                st.success(st.session_state.active_final_msg)
                if st.button("Zamknij i odbierz nagrodę"):
                    for k in list(st.session_state.keys()):
                        if k.startswith("aopts_game_") or k.startswith("active_"): del st.session_state[k]
                    st.rerun()

    # --- TAB 3: HISTORIA ---
    with t3:
        res_h = db.table("duels").select("*").or_(f"challenger.eq.{u_name},opponent.eq.{u_name}").order("created_at", desc=True).limit(20).execute()
        if res_h.data:
            for d in res_h.data:
                if d['status'] == 'finished':
                    win_icon = "🏆" if u_name in str(d['winner']) else "💀"
                    res_str = f"{d['score_challenger']}:{d['score_opponent']}"
                else:
                    win_icon = "⏳"
                    res_str = f"{d['score_challenger']}:?"
                
                st.write(f"{win_icon} **{d['challenger']}** vs **{d['opponent']}** | {res_str} | Zwycięzca: {d['winner'] or 'w trakcie'}")
        else: st.info("Brak historii.")

    # --- TAB 4: RANKING ---
    with t4:
        res_r = db.table("user_data").select("username, duel_points, duel_wins, duel_losses").order("duel_points", desc=True).execute()
        if res_r.data:
            df_rank = pd.DataFrame(res_r.data)
            df_rank.columns = ["Wojownik", "Suma Punktów", "Wygrane (W)", "Przegrane (P)"]
            st.table(df_rank)

# --- 20. ARENA WYZWAŃ (V560 - Optimized XP Knowledge & Shadowban) ---
elif choice == "🏆 Arena Wyzwań":
    current_lang_name = st.session_state.get("current_lang", "Niemiecki")
    L_CODE = "de" if current_lang_name == "Niemiecki" else "cs"
    u_name = st.session_state.get("user", "Anonim") 
    
    st.markdown(f"<h1 style='text-align: center;'>🏆 Arena Wyzwań</h1>", unsafe_allow_html=True)
    st.write(f"Język: **{current_lang_name}** ({L_CODE})")

    # --- 0. DATY ---
    now_pl = datetime.now(pytz.timezone('Europe/Warsaw'))
    start_of_week = (now_pl - timedelta(days=now_pl.weekday())).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    start_of_month = now_pl.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()

    # --- 1. FUNKCJA POBIERAJĄCA Z FILTREM SHADOWBAN ---
    def get_game_leaderboard(game_id, lang_code, start_date=None):
        try:
            db = get_db()
            query = db.table("game_scores").select("username, score, created_at, user_data(is_shadowbanned)").eq("game_name", game_id).eq("lang", lang_code)
            
            if start_date:
                query = query.gte("created_at", start_date)
            
            is_desc = False if game_id == "memory" else True
            res = query.order("score", desc=is_desc).execute()
            data = res.data if res.data else []
            
            if not data: return []
            
            # Filtrowanie shadowbanów
            filtered = [d for d in data if not (d.get('user_data') and d['user_data'].get('is_shadowbanned'))]
            return filtered[:10]
        except Exception as e:
            return []

    # --- 2. POBIERANIE DANYCH DO RANKINGÓW OGÓLNYCH ---
    try:
        db = get_db()
        # Pobieramy statusy użytkowników
        raw_users = db.table("user_data").select("username, streak, is_shadowbanned").execute().data or []
        # Optymalizacja: Pobieramy mastery_xp zamiast dat, aby zliczyć wiedzę wg nowego systemu
        all_cards_global = db.table("flashcards").select("username, mastery_xp").eq("lang", L_CODE).execute().data or []
        
        cards_per_user = {}
        for c in all_cards_global:
            un = c['username']
            if un not in cards_per_user: cards_per_user[un] = []
            cards_per_user[un].append(c)
    except:
        raw_users, cards_per_user = [], {}

    def assign_medals(df):
        medals = ["🥇", "🥈", "🥉"]
        new_indices = []
        for i in range(len(df)):
            place = i + 1
            if i < 3: new_indices.append(f"{medals[i]} {place}")
            else: new_indices.append(str(place))
        df.index = new_indices
        df.index.name = "Miejsce"
        return df

    # --- 4. RENDEROWANIE GIER ---
    st.subheader("🎮 Rekordy Gier")
    t_mem, t_bal, t_surv, t_snake = st.tabs(["⏱️ Memory", "🎈 Balony", "🎲 Ruletka", "🐍 Wąż"])

    games_config = [
        {"tab": t_mem, "id": "memory", "unit": "s"},
        {"tab": t_bal, "id": "balloons", "unit": " pkt"},
        {"tab": t_surv, "id": "survival", "unit": " popr."},
        {"tab": t_snake, "id": "snake", "unit": " słów"}
    ]

    for g in games_config:
        with g["tab"]:
            st_all, st_month, st_week = st.tabs(["🏆 Wszech czasów", "📅 Ten miesiąc", "⏳ Ten tydzień"])
            periods = [{"tab": st_all, "date": None}, {"tab": st_month, "date": start_of_month}, {"tab": st_week, "date": start_of_week}]
            for p in periods:
                with p["tab"]:
                    data = get_game_leaderboard(g["id"], L_CODE, p["date"])
                    if data:
                        df_game = pd.DataFrame(data)
                        df_game["Rekord"] = df_game["score"].apply(lambda x: f"{x}{g['unit']}")
                        df_game = df_game.rename(columns={"username": "Użytkownik"})
                        st.table(assign_medals(df_game[["Użytkownik", "Rekord"]].head(10)))
                    else:
                        st.caption(f"Brak rekordów dla tego okresu.")

    st.divider()

    # --- 5. PASSA I WIEDZA (Zoptymalizowana pod Mastery XP) ---
    col1, col2 = st.columns(2)
    leaderboard_data = []
    visible_leaderboard = []
    
    for u_row in raw_users:
        uname = u_row.get("username", "Anonim")
        is_ghost = u_row.get("is_shadowbanned", False)
        u_cards = cards_per_user.get(uname, [])
        
        w_raw = 0
        total_words = len(u_cards)
        
        if total_words > 0:
            # NOWA LOGIKA: Sumujemy XP i dzielimy przez max możliwy XP (ilość słów * 150)
            # Zgodne z algorytmem z Sekcji 27
            xp_sum = sum(c.get('mastery_xp', 0) or 0 for c in u_cards)
            wiedza_val = int((xp_sum / (total_words * 150)) * 100)
            w_raw = min(wiedza_val, 100)
        
        entry = {
            "Użytkownik": uname, 
            "Ogień 🔥": int(u_row.get("streak", 0)), 
            "w_raw": w_raw, 
            "Wiedza 🧠": f"{w_raw}%" if total_words > 0 else "---"
        }
        
        leaderboard_data.append(entry)
        if not is_ghost:
            visible_leaderboard.append(entry)

    if visible_leaderboard:
        with col1:
            st.subheader("🔥 Top 10: Passa")
            df_s = pd.DataFrame(visible_leaderboard).sort_values("Ogień 🔥", ascending=False).head(10)
            st.table(assign_medals(df_s.reset_index(drop=True))[["Użytkownik", "Ogień 🔥"]])
        with col2:
            st.subheader(f"🧠 Top 10: Wiedza ({L_CODE.upper()})")
            # Sortujemy po surowej wartości XP (w_raw)
            df_w = pd.DataFrame(visible_leaderboard)
            df_w = df_w[df_w["Wiedza 🧠"] != "---"].sort_values("w_raw", ascending=False).head(10)
            if not df_w.empty: 
                st.table(assign_medals(df_w.reset_index(drop=True))[["Użytkownik", "Wiedza 🧠"]])
            else: 
                st.caption("Brak danych.")

    # Podświetlenie pozycji aktualnego gracza
    st.write("---")
    my_stats = next((item for item in leaderboard_data if item["Użytkownik"] == u_name), None)
    if my_stats:
        st.info(f"Twoje statystyki ({current_lang_name}): Wiedza (Mastery XP): **{my_stats['Wiedza 🧠']}** | Passa: **{my_stats['Ogień 🔥']} dni**.")

# --- 21. GENERATOR SŁÓW (V3.0 - Master Vocab Integration) ---
elif choice == "📦 Generator":
    current_lang_name = st.session_state.get("current_lang", "Niemiecki")
    L_CODE = "de" if current_lang_name == "Niemiecki" else "cs"
    
    st.header(f"📦 Generator: {current_lang_name}")
    st.write("System korzysta z nowej, pancernej biblioteki słówek Master Vocab.")

    # 1. PANEL STEROWANIA
    with st.container(border=True):
        c1, c2, c3 = st.columns([2, 2, 1])
        with c1:
            gen_lvl = st.selectbox("Poziom CEFR:", ["A1", "A2", "B1", "B2", "C1", "C2"], key="gen_lvl_sel")
        with c2:
            gen_topic = st.text_input("Temat (opcjonalnie):", placeholder="np. praca, dom...", key="gen_top_in")
        with c3:
            gen_count = st.number_input("Ilość:", 3, 50, 10, key="gen_cnt_in")
        
        if st.button(f"✨ Generuj listę ({current_lang_name})", use_container_width=True, type="primary"):
            with st.spinner("Przeszukuję Master Vocab..."):
                db = get_db()
                
                # A. POBIERZ AKTUALNE SŁÓWKA UŻYTKOWNIKA (Unikanie duplikatów)
                known_words = {normalize_text(c['de']) for c in st.session_state.flashcards if c.get('lang') == L_CODE}
                
                final_results = []

                # B. POBIERANIE Z NOWEJ TABELI master_vocab
                try:
                    # Zapytanie do nowej tabeli
                    res_lib = db.table("master_vocab").select("*").eq("lang", L_CODE).eq("level", gen_lvl).execute()
                    
                    if res_lib.data:
                        # Filtrujemy słowa, których uczeń NIE ma jeszcze w bazie
                        available_in_lib = [
                            w for w in res_lib.data 
                            if normalize_text(w['word']) not in known_words
                        ]
                        
                        # Opcjonalne filtrowanie po temacie w kolumnie 'category'
                        if gen_topic:
                            available_in_lib = [w for w in available_in_lib if gen_topic.lower() in str(w.get('category','')).lower()]

                        random.shuffle(available_in_lib)
                        picked_from_lib = available_in_lib[:gen_count]
                        
                        for p in picked_from_lib:
                            final_results.append({
                                "de": p['word'],
                                "pl": p['translation'],
                                "tags": p.get('category', gen_lvl),
                                "ex_de": p.get('example_orig', ''),
                                "ex_pl": p.get('example_pl', '')
                            })
                except Exception as e:
                    st.error(f"Błąd bazy Master Vocab: {e}")

                # C. FALLBACK DO AI (Jeśli w bibliotece brakuje słów)
                needed_more = gen_count - len(final_results)
                
                if needed_more > 0:
                    exclude_list = list(known_words)[:100]
                    lang_instr = "Niemiecki: der/die/das" if L_CODE == "de" else "Czeski: ten/ta/to"
                    
                    prompt = f"""Wygeneruj {needed_more} UNIKALNYCH słówek ({current_lang_name}, {gen_lvl}).
                    {f"Temat: {gen_topic}" if gen_topic else ""}
                    ZASADY: 1. {lang_instr}. 2. Tłumaczenie PL: czyste. 
                    3. UNIKAJ TYCH SŁÓW: {exclude_list}.
                    
                    Zwróć TYLKO JSON: {{"flashcards": [{{"de":"", "pl":"", "tags":"", "ex_de":"", "ex_pl":""}}]}}"""
                    
                    try:
                        raw_res = get_openai_response(prompt)
                        ai_data = json.loads(raw_res)
                        ai_words = ai_data.get("flashcards", [])
                        # Mapowanie nazw pól z AI na nasz standard
                        for aw in ai_words:
                            final_results.append({
                                "de": aw['de'], "pl": aw['pl'], "tags": aw['tags'],
                                "ex_de": aw['ex_de'], "ex_pl": aw['ex_pl']
                            })
                    except:
                        st.warning("AI nie mogło dopełnić listy.")

                st.session_state.temp_generated = final_results[:gen_count]

    # --- 2. SEKCJA EDYCJI I ZAPISU ---
    if "temp_generated" in st.session_state and st.session_state.temp_generated:
        st.divider()
        st.subheader("📝 Podgląd przed dodaniem")
        
        df_list = []
        for item in st.session_state.temp_generated:
            exists = any(normalize_text(c['de']) == normalize_text(item['de']) for c in st.session_state.flashcards if c.get('lang') == L_CODE)
            df_list.append({
                "Dodaj": not exists,
                "Słowo": item.get("de", ""),
                "Polski": item.get("pl", ""),
                "Kategorie": item.get("tags", ""),
                "Status": "⚠️ Dubel" if exists else "✅ Nowe"
            })

        edited_df = st.data_editor(df_list, use_container_width=True, key="gen_editor_v30")

        c_save, c_cancel = st.columns(2)
        if c_save.button("🚀 Zapisz do mojego słownika", use_container_width=True, type="primary"):
            added = 0
            for i, row in enumerate(edited_df):
                if row["Dodaj"]:
                    orig = st.session_state.temp_generated[i]
                    new_word = {
                        "de": orig["de"], "pl": orig["pl"], 
                        "category": orig["tags"], "lang": L_CODE,
                        "next_review": str(date.today()), "level": 0, "origin": "Generator",
                        "examples": [{"de": orig.get("ex_de",""), "pl": orig.get("ex_pl","")}]
                    }
                    save_word(u, new_word)
                    added += 1
            
            st.success(f"Dodano {added} słówek!"); st.session_state.flashcards = load_flashcards(u)
            del st.session_state.temp_generated
            st.rerun()

        if c_cancel.button("🗑️ Anuluj", use_container_width=True):
            del st.session_state.temp_generated
            st.rerun()

# --- 22. SKANER AI (V471 - Full Implementation & Quality Fix) ---
elif choice == "📸 Skaner AI":
    from streamlit_cropper import st_cropper
    from PIL import ImageEnhance, ImageOps
    
    current_lang_name = st.session_state.get("current_lang", "Niemiecki")
    L_CODE = "de" if current_lang_name == "Niemiecki" else "cs"
    
    st.header(f"📸 Skaner AI: {current_lang_name}")
    st.info("💡 Protip: Najlepszą jakość uzyskasz robiąc zdjęcie aparatem telefonu i wgrywając plik.")

    cam_col, file_col = st.columns(2)
    img_file = cam_col.camera_input("Zrób zdjęcie")
    uploaded_file = file_col.file_uploader("Wgraj plik", type=["jpg", "jpeg", "png"])

    active_raw_img = img_file if img_file else uploaded_file

    if active_raw_img:
        img_obj = Image.open(active_raw_img)
        
        st.subheader("✂️ Przytnij i wyostrz")
        cropped_img = st_cropper(img_obj, realtime_update=True, box_color='#ff4b4b', aspect_ratio=None, key="cropper_v3")
        
        if cropped_img:
            # --- CYFROWY TUNING OBRAZU ---
            enhanced_img = ImageOps.grayscale(cropped_img)
            enhanced_img = ImageEnhance.Contrast(enhanced_img).enhance(2.0)
            enhanced_img = ImageEnhance.Sharpness(enhanced_img).enhance(2.0)

            st.write("🔍 Podgląd wycinka do analizy:")
            st.image(enhanced_img, width=400)

            if st.button("🚀 Analizuj wykadrowany tekst", use_container_width=True, type="primary"):
                with st.spinner("AI przeprowadza głęboki skan..."):
                    prompt = f"""DOKŁADNY SKAN TEKSTU. Wyciągnij WSZYSTKIE słówka i frazy widoczne na obrazku w języku {current_lang_name}. 
                    Nie pomijaj żadnego wyrazu. Jeśli słowo występuje obok innego, potraktuj je jako osobne rekordy.
                    
                    Język: {current_lang_name}. 
                    Zasady: Niemieckie rzeczowniki z rodzajnikami (der/die/das). Czeskie znaki diakrytyczne nienaruszone.
                    
                    Zwróć TYLKO czysty JSON:
                    {{"flashcards": [
                        {{"de": "słowo", "pl": "tłumaczenie", "tags": "poziom i kategoria", "ex_de": "przykład", "ex_pl": "tłumaczenie przykładu"}}
                    ]}}"""
                    
                    try:
                        res_raw = get_openai_response(prompt, img_obj=enhanced_img).strip()
                        
                        # Oczyszczanie JSON
                        cleaned_res = res_raw.strip()
                        if cleaned_res.startswith("```"):
                            cleaned_res = cleaned_res.strip("`").strip()
                            if cleaned_res.lower().startswith("json"):
                                cleaned_res = cleaned_res[4:].strip()
                            
                        data = json.loads(cleaned_res)
                        st.session_state.scanner_results = data.get("flashcards", [])
                        st.success(f"Sukces! Wykryto {len(st.session_state.scanner_results)} rekordów.")
                    except Exception as e:
                        st.error(f"Błąd analizy: {e}")

    # --- 2. EDYTOR WYNIKÓW I MASOWA EDYCJA ---
    if "scanner_results" in st.session_state and st.session_state.scanner_results:
        st.divider()
        st.subheader("📝 Zatwierdź wyniki")
        
        with st.expander("🛠️ Masowa edycja kategorii"):
            col_m1, col_m2 = st.columns([2, 1])
            new_mass_cat = col_m1.text_input("Kategoria dla wszystkich:", placeholder="np. Dom, B2")
            
            m_btn_c1, m_btn_c2 = st.columns(2)
            if m_btn_c1.button("✅ Zastosuj", use_container_width=True):
                for item in st.session_state.scanner_results:
                    item["tags"] = new_mass_cat
                st.rerun()
            if m_btn_c2.button("🗑️ Wyczyść", use_container_width=True):
                for item in st.session_state.scanner_results:
                    item["tags"] = ""
                st.rerun()

        lang_col_label = "Niemiecki" if L_CODE == "de" else "Czeski"
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

        edited_df = st.data_editor(df_init, use_container_width=True, num_rows="dynamic", key="scanner_v6")

        c_save, c_cancel = st.columns(2)
        if c_save.button("🚀 Dodaj do słownika", use_container_width=True, type="primary"):
            added = 0
            for row in edited_df:
                if row.get("Zapisz", False):
                    new_word = {
                        "de": row[lang_col_label], "pl": row["Polski"], "category": row["Kategorie"],
                        "next_review": str(date.today()), "level": 0, "origin": "Skaner AI",
                        "lang": L_CODE, "mastery_xp": 0,
                        "examples": [{"de": row["Przykład"], "pl": row["Przykład PL"]}]
                    }
                    save_word(u, new_word)
                    added += 1
            st.session_state.flashcards = load_flashcards(u)
            st.success(f"Dodano {added} słówek!")
            del st.session_state.scanner_results
            st.rerun()

        if c_cancel.button("🗑️ Odrzuć", use_container_width=True):
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

# --- 24. SŁOWNIK (V450 - Mass Edit & Alpha Filter) ---
elif choice == "📖 Słownik":
    import re
    import unicodedata

    # Pobieramy aktualny język i kody z sesji
    current_lang_name = st.session_state.get("current_lang", "Niemiecki")
    L_CODE = "de" if current_lang_name == "Niemiecki" else "cs"
    L_LABEL = "DE" if L_CODE == "de" else "CS"
    
    st.header(f"📖 Słownik: {current_lang_name}")
    
    # 1. Filtrowanie słówek pod wybrany język
    lang_cards = [c for c in st.session_state.flashcards if c.get("lang", "de") == L_CODE]
    
    # 2. Pomocnicza funkcja do wyciągania litery (pomijanie rodzajników)
    def get_sort_char(text):
        t = text.lower().strip()
        # Usuwanie rodzajników DE i CS
        t = re.sub(r'^(der|die|das|ten|ta|to)\s+', '', t)
        # Normalizacja diakrytyki (np. Ä -> A)
        t = "".join(c for c in unicodedata.normalize('NFD', t) if unicodedata.category(c) != 'Mn')
        return t[0].upper() if t else "#"

    # 3. Pobieranie unikalnych tagów i dostępnych liter
    all_tags = set()
    available_letters = set()
    for c in lang_cards:
        all_tags.update([t.strip() for t in str(c.get('category','')).split(',') if t.strip()])
        available_letters.add(get_sort_char(c['de']))
    
    # --- UI FILTRÓW ---
    with st.container(border=True):
        col1, col2, col3 = st.columns([1.5, 2, 1])
        f_tag = col1.selectbox(f"Kategorie:", ["Wszystkie"] + sorted(list(all_tags)))
        search = col2.text_input("Szukaj słowa:", placeholder="Szukaj w obu językach...")
        
        # Opcje dodatkowe
        show_all = col3.toggle("Pokaż wszystkie", value=False, help="Wyłącza limit 50 wyników")
        mass_edit_mode = col3.toggle("Masowa edycja", value=False, help="Pozwala zmieniać tagi wielu słów na raz")

    # Filtr alfabetyczny (poziomy pasek)
    alphabet = sorted(list(available_letters))
    selected_letter = st.radio("Litera:", ["Wszystkie"] + alphabet, horizontal=True)

    # Przyciski akcji (Dubla)
    if "show_dupes" not in st.session_state: st.session_state.show_dupes = False
    dupe_btn_label = "🔙 Powrót" if st.session_state.show_dupes else "👯 Znajdź duble"
    if st.button(dupe_btn_label, use_container_width=True):
        st.session_state.show_dupes = not st.session_state.show_dupes
        st.rerun()

    # 4. Logika wyszukiwania / Dubli
    if st.session_state.show_dupes:
        from collections import defaultdict
        groups = defaultdict(list)
        for c in lang_cards:
            norm = normalize_text(c['de'])
            groups[norm].append(c)
        filtered = [c for norm, cards in groups.items() if len(cards) > 1 for c in cards]
        st.warning(f"Tryb duplikatów: Znaleziono {len(filtered)} wpisów.")
    else:
        filtered = [
            c for c in lang_cards 
            if (f_tag == "Wszystkie" or f_tag in str(c.get('category',''))) 
            and (search.lower() in str(c.get('de','')).lower() or search.lower() in str(c.get('pl','')).lower())
            and (selected_letter == "Wszystkie" or get_sort_char(c['de']) == selected_letter)
        ]

    st.write("---")
    
    # --- MASOWA EDYCJA ---
    if mass_edit_mode and filtered:
        with st.expander("🛠️ Panel Masowej Edycji", expanded=True):
            st.info("Zaznacz słówka na liście poniżej, wpisz nową kategorię i zatwierdź.")
            new_cat = st.text_input("Nowa kategoria dla wybranych:", placeholder="np. Dom, Praca")
            if st.button("ZASTOSUJ DO ZAZNACZONYCH", type="primary", use_container_width=True):
                selected_ids = [idx for idx, val in st.session_state.items() if str(idx).startswith("sel_") and val is True]
                if selected_ids and new_cat:
                    for s_id in selected_ids:
                        real_id = s_id.replace("sel_", "")
                        update_word(real_id, {"category": new_cat})
                    st.session_state.flashcards = load_flashcards(u)
                    st.success(f"Zaktualizowano {len(selected_ids)} słówek! ✅")
                    st.rerun()
                else:
                    st.error("Musisz wybrać słówka i wpisać nazwę kategorii!")

    st.subheader(f"Liczba słówek: {len(filtered)}")
    
    # Zabezpieczenie wydajności
    limit = len(filtered) if show_all else 50
    display_list = filtered[:limit]
    
    if len(filtered) > limit:
        st.warning(f"Wyświetlam pierwsze {limit} wyników. Użyj filtrów lub 'Pokaż wszystkie'.")
        
    if not display_list:
        st.info(f"Brak słówek spełniających kryteria.")
        
    # 5. Renderowanie listy wyników
    for c in display_list:
        flag = "🇩🇪" if L_CODE == "de" else "🇨🇿"
        header_color = "⚠️" if st.session_state.show_dupes else flag
        
        # Checkbox dla masowej edycji
        cols = st.columns([0.1, 0.9]) if mass_edit_mode else [st.container()]
        
        if mass_edit_mode:
            is_selected = cols[0].checkbox("", key=f"sel_{c['id']}")
            
        with cols[-1].expander(f"{header_color} {c['de']} ➔ 🇵🇱 {c['pl']}"):
            # Metadata
            st.caption(f"🗓️ Powtórka: {c.get('next_review', 'Brak')} | 🏷️ Tagi: {c.get('category', 'Brak')} | ID: {c['id']}")
            
            # Wizualizacja XP
            xp = int(c.get("mastery_xp", 0))
            if xp <= 10: lvl_name, lvl_color = "Nowicjusz", "gray"
            elif xp <= 30: lvl_name, lvl_color = "Zaznajomiony", "#FF8C00"
            elif xp <= 60: lvl_name, lvl_color = "Uczeń", "#1E90FF"
            elif xp <= 100: lvl_name, lvl_color = "Średniozaawansowany", "#9932CC"
            elif xp <= 150: lvl_name, lvl_color = "Ekspert", "#228B22"
            else: lvl_name, lvl_color = "Mistrz 🏆", "#FFD700"

            c_xp1, c_xp2 = st.columns([3, 1])
            c_xp1.progress(min(xp / 150, 1.0))
            c_xp2.markdown(f"<div style='text-align: right; color: {lvl_color}; font-weight: bold; font-size: 0.85rem;'>{lvl_name} ({xp} XP)</div>", unsafe_allow_html=True)

            # Przykłady
            exs = c.get("examples", [])
            example_to_play = None
            if exs and isinstance(exs, list) and len(exs) > 0:
                st.markdown("**Przykłady:**")
                for ex in exs:
                    st.write(f"🔹 **{ex.get('de')}**")
                    st.write(f"&nbsp;&nbsp;&nbsp;&nbsp;*{ex.get('pl')}*")
                    if not example_to_play: example_to_play = ex.get('de')
            elif c.get('example'):
                st.write(f"🔹 **{c['example']}**")
                example_to_play = c['example']

            # Akcje
            col_a1, col_a2 = st.columns(2)
            if col_a1.button(f"🔊 Odsłuchaj", key=f"audio_{c['id']}", use_container_width=True):
                play_audio(c['de'], example_to_play, lang=L_CODE)
            
            # --- FORMULARZ EDYCJI ---
            with st.form(f"ed_form_{c['id']}"):
                n_de = st.text_input("Słowo", c['de'])
                n_pl = st.text_input("Tłumaczenie", c['pl'])
                n_ca = st.text_input("Kategorie", c.get('category',''))
                if st.form_submit_button("💾 Zapisz", use_container_width=True):
                    update_word(c['id'], {"de": n_de, "pl": n_pl, "category": n_ca, "lang": L_CODE})
                    st.session_state.flashcards = load_flashcards(u)
                    st.rerun()
            
            if st.button("🗑️ Usuń", key=f"del_{c['id']}", type="primary", use_container_width=True):
                delete_word(c['id'])
                st.session_state.flashcards = [card for card in st.session_state.flashcards if card['id'] != c['id']]
                st.rerun()

# --- 25. STATYSTYKI (V411 - Robust XP Analytics Fix) ---
elif choice == "📊 Statystyki":
    current_lang_name = st.session_state.get("current_lang", "Niemiecki")
    L_CODE = "de" if current_lang_name == "Niemiecki" else "cs"
    u = st.session_state.get("user", "Anonim")
    
    st.header(f"📊 Statystyki: {current_lang_name}")

    # --- KROK 1: POBRANIE DANYCH ---
    try:
        db = get_db()
        res = db.table("user_data").select("*").eq("username", u).execute()
        if res.data:
            fresh_ud = res.data[0]
            st.session_state.user_data = fresh_ud
            ud = fresh_ud
        else:
            ud = st.session_state.user_data
    except Exception as e:
        st.error(f"Błąd odświeżania danych: {e}")
        ud = st.session_state.user_data
    
    # --- SZCZEGÓŁOWA ANALIZA POJEDYNKÓW ---
    st.subheader("⚔️ Moje Statystyki Pojedynków")
    try:
        res_duels = db.table("duels").select("*").or_(f"challenger.eq.{u},opponent.eq.{u}").eq("status", "finished").execute()
        
        d_total = len(res_duels.data)
        d_win_pts = 0
        d_win_time = 0
        d_loss_time = 0
        d_loss_pts = 0

        for d in res_duels.data:
            is_challenger = (d['challenger'] == u)
            my_score = d['score_challenger'] if is_challenger else d['score_opponent']
            opp_score = d['score_opponent'] if is_challenger else d['score_challenger']
            my_time = d['time_challenger'] if is_challenger else d['time_opponent']
            opp_time = d['time_opponent'] if is_challenger else d['time_challenger']

            if my_score > opp_score: d_win_pts += 1
            elif opp_score > my_score: d_loss_pts += 1
            else:
                if my_time < opp_time: d_win_time += 1
                else: d_loss_time += 1

        duel_summary = {
            "Kategoria": ["Wszystkie gry", "Wygrane (Punkty)", "Wygrane (Czas)", "Przegrane (Czas)", "Przegrane (Punkty)"],
            "Liczba": [d_total, d_win_pts, d_win_time, d_loss_time, d_loss_pts]
        }
        st.dataframe(pd.DataFrame(duel_summary), use_container_width=True, hide_index=True)
        st.caption(f"Łączne punkty w rankingu: **{ud.get('duel_points', 0)} pkt**")
    except:
        st.info("Rozegraj swój pierwszy pojedynek, aby zobaczyć tu statystyki!")

    st.write("---")

    # --- KROK 2: ANALIZA BAZY SŁÓWEK ---
    all_cards = st.session_state.flashcards
    df_full = pd.DataFrame(all_cards)
    if not df_full.empty:
        df = df_full[df_full.get("lang", "de") == L_CODE].copy()
    else:
        df = pd.DataFrame()

    if not df.empty:
        # 1. Metryki główne
        c1, c2 = st.columns(2)
        c1.metric(f"Wielkość Bazy ({current_lang_name})", len(df))
        c2.metric("Passa Nauki", f"{ud.get('streak', 0)} dni")
        
        st.write("---")

        # --- NOWOŚĆ: ROZKŁAD BIEGŁOŚCI (POPRAWIONY SILNIK) ---
        st.subheader("📈 Rozwój Biegłości Słownictwa")
        
        # PANCERNA FUNKCJA KATEGORYZACJI (Fix dla NaN/None)
        def get_xp_label_safe(xp_val):
            try:
                # Zamiana na float, potem na int (bezpieczne dla Pandas)
                val = int(float(xp_val)) if pd.notnull(xp_val) else 0
            except:
                val = 0
                
            if val <= 10: return "Nowicjusz"
            if val <= 30: return "Zaznajomiony"
            if val <= 60: return "Uczeń"
            if val <= 100: return "Średniozaawansowany"
            if val <= 150: return "Ekspert"
            return "Mistrz 🏆"

        # Bezpieczne mapowanie
        df['Biegłość'] = df['mastery_xp'].apply(get_xp_label_safe)
        order = ["Nowicjusz", "Zaznajomiony", "Uczeń", "Średniozaawansowany", "Ekspert", "Mistrz 🏆"]
        
        dist = df['Biegłość'].value_counts().reindex(order, fill_value=0).reset_index()
        dist.columns = ['Poziom Biegłości', 'Liczba słówek']
        
        st.dataframe(
            dist,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Poziom Biegłości": st.column_config.TextColumn("Stopień Opanowania"),
                "Liczba słówek": st.column_config.ProgressColumn(
                    "Ilość Słów",
                    format="%d",
                    min_value=0,
                    max_value=int(dist['Liczba słówek'].max() or 1)
                )
            }
        )
        
        fig = px.pie(dist, values='Liczba słówek', names='Poziom Biegłości', 
                     color='Poziom Biegłości',
                     color_discrete_map={
                         "Nowicjusz": "gray", "Zaznajomiony": "#FF8C00", "Uczeń": "#1E90FF",
                         "Średniozaawansowany": "#9932CC", "Ekspert": "#228B22", "Mistrz 🏆": "#FFD700"
                     },
                     hole=0.4)
        fig.update_layout(margin=dict(t=0, b=0, l=0, r=0), height=300, showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

        st.write("---")

        # --- 2. REKORDY GIER ---
        st.subheader("🏆 Moje Rekordy w Grach")
        t_mem, t_bal, t_snake, t_surv = st.tabs(["🧩 Memory", "🎈 Balony", "🐍 Wąż", "🎲 Językowa Ruletka"])
        
        with t_mem:
            mem_scores = ud.get(f"memory_scores_{L_CODE}", [])
            if mem_scores:
                valid_scores = sorted([float(s) for s in mem_scores])[:3]
                m_cols = st.columns(3)
                icons = ["🥇", "🥈", "🥉"]
                for i, score in enumerate(valid_scores):
                    m_cols[i].metric(f"{icons[i]} Miejsce", f"{score}s")
            else: st.info("Zagraj w Memory!")

        with t_bal:
            bal_scores = ud.get(f"top_balloons_{L_CODE}", [])
            if bal_scores:
                top3_bal = sorted([int(s) for s in bal_scores], reverse=True)[:3]
                b_cols = st.columns(3)
                icons = ["🥇", "🥈", "🥉"]
                for i, score in enumerate(top3_bal):
                    b_cols[i].metric(f"{icons[i]} Miejsce", f"{score} pkt")
            else: st.info("Brak rekordów.")

        with t_snake:
            s_c1, s_c2, s_c3 = st.columns(3)
            s_c1.metric("Najdłuższa seria", f"{ud.get('snake_best_chain', 0)} słów")
            s_c2.metric("Wygrane", f"{ud.get('snake_wins', 0)}")
            s_c3.metric("Przegrane", f"{ud.get('snake_losses', 0)}")

        with t_surv:
            surv_scores = ud.get(f"survival_scores_{L_CODE}", [])
            if surv_scores:
                top3_surv = sorted([int(s) for s in surv_scores], reverse=True)[:3]
                s_cols = st.columns(3)
                icons = ["🥇", "🥈", "🥉"]
                for i, score in enumerate(top3_surv):
                    s_cols[i].metric(f"{icons[i]} Miejsce", f"{score} popr.")
            else: st.info("Zagraj w Ruletkę!")

        st.write("---")
        
        # --- 3. CZAS NAUKI ---
        col_top1, col_top2 = st.columns(2)
        with col_top1:
            st.subheader("⏱️ Czas nauki (minuty)")
            time_stats = ud.get("time_stats", {})
            display_names = {
                "Pow": "Powtórki", "Trn": "Trening", "Qiz": "Quiz", "Fis": "Fiszki", 
                "Tst": "Testy", "Mem": "Memory", "War": "Warsztat", "Kon": "Konstruktor", 
                "Wan": "Wąż", "Bal": "Balon", "Sur": "Ruletka", "Sta": "Statystyki"
            }
            nav_order = ["Powtórki", "Trening", "Quiz", "Fiszki", "Testy", "Memory", "Ruletka", "Wąż", "Bal", "Statystyki"]
            
            aggregated_mins = {name: 0 for name in nav_order}
            for code, sec in time_stats.items():
                name = display_names.get(code, "Inne")
                if name in aggregated_mins: aggregated_mins[name] += sec
            
            t_data = [{"Moduł": n, "Minuty": int(aggregated_mins[n]//60)} for n in nav_order if aggregated_mins[n] > 0]
            st.dataframe(pd.DataFrame(t_data), use_container_width=True, hide_index=True)

        with col_top2:
            st.subheader("📅 Plan powtórek")
            today = date.today()
            sched = []
            for i in range(7):
                target = str(today + timedelta(days=i))
                count = len(df[df['next_review'] <= target]) if i==0 else len(df[df['next_review'] == target])
                sched.append({"Dzień": "Dziś" if i==0 else (today + timedelta(days=i)).strftime("%d.%m"), "Słówka": count})
            st.dataframe(pd.DataFrame(sched), use_container_width=True, hide_index=True)

    else:
        st.info(f"Baza słówek ({current_lang_name}) jest pusta.")

    st.write("---")
    st.subheader(f"📝 Historia testów ({current_lang_name})")
    t_hist = ud.get("test_history", [])
    filtered_hist = [t for t in t_hist if t.get("lang", "de") == L_CODE]
    if filtered_hist:
        hist_df = pd.DataFrame(filtered_hist)[::-1][["date", "score", "total", "perc"]]
        hist_df.columns = ["Data", "Wynik", "Suma pytań", "Procent (%)"]
        st.dataframe(hist_df, use_container_width=True, hide_index=True)
    else: st.info("Brak historii testów.")

# --- 26. KONTO (V550 - Email Linking & Security Migration) ---
elif choice == "⚙️ Konto":
    current_lang_name = st.session_state.get("current_lang", "Niemiecki")
    L_CODE = "de" if current_lang_name == "Niemiecki" else "cs"
    st.header(f"⚙️ Zarządzanie Kontem")
    
    if "acc_msg" in st.session_state:
        st.success(st.session_state.acc_msg)
        del st.session_state.acc_msg

    # --- 0. BEZPIECZEŃSTWO I E-MAIL (Nowa Sekcja) ---
    with st.expander("🛡️ Bezpieczeństwo i E-mail", expanded=True):
        u_data = st.session_state.user_data
        current_email = u_data.get("email", "")
        
        st.subheader("Powiązanie konta")
        st.caption("Podaj e-mail, aby zabezpieczyć konto i umożliwić odzyskiwanie hasła w przyszłości.")
        
        email_input = st.text_input("Twój adres e-mail:", value=current_email, placeholder="przyklad@poczta.pl")
        
        if st.button("💾 Zapisz e-mail", use_container_width=True):
            if "@" in email_input and "." in email_input:
                db = get_db()
                # Sprawdzamy czy mail nie jest zajęty przez kogoś innego
                check = db.table("user_data").select("username").eq("email", email_input).neq("username", u).execute()
                
                if check.data:
                    st.error("Ten adres e-mail jest już powiązany z innym kontem.")
                else:
                    # Aktualizacja maila i ustawienie providera na legacy (jeśli nie istnieje)
                    upd = {"email": email_input}
                    if not u_data.get("provider"):
                        upd["provider"] = "legacy"
                    
                    db.table("user_data").update(upd).eq("username", u).execute()
                    st.session_state.user_data["email"] = email_input
                    st.success("Adres e-mail został zapisany! 🛡️")
            elif email_input == "":
                st.warning("E-mail został wyczyszczony. Pamiętaj, że utrudni to odzyskanie konta.")
                get_db().table("user_data").update({"email": None}).eq("username", u).execute()
                st.session_state.user_data["email"] = None
            else:
                st.error("Wpisz poprawny adres e-mail.")

    # --- 1. PREFERENCJE NAUKI ---
    with st.expander("🛠️ Preferencje nauki", expanded=False):
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
                    # Synchronizujemy też hasło w user_data, jeśli je tam przechowujesz w celach backupu
                    db.table("user_data").update({"password": new_p}).eq("username", u).execute()
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
        
        st.subheader("Resety rekordów gier")
        st.caption(f"Wyczyść swoje najlepsze wyniki (tylko dla języka {current_lang_name}).")
        
        r_col1, r_col2 = st.columns(2)
        
        if r_col1.button(f"🧩 Resetuj Memory ({L_CODE.upper()})", disabled=not safety_lock, use_container_width=True):
            st.session_state.user_data[f"memory_scores_{L_CODE}"] = []
            save_user_data(u, st.session_state.user_data)
            st.session_state.acc_msg = f"Wyczyszczono rekordy Memory dla języka {current_lang_name}."
            st.rerun()

        if r_col2.button(f"🎈 Resetuj Balony ({L_CODE.upper()})", disabled=not safety_lock, use_container_width=True):
            st.session_state.user_data[f"top_balloons_{L_CODE}"] = []
            save_user_data(u, st.session_state.user_data)
            st.session_state.acc_msg = f"Wyczyszczono rekordy Balonowego Wyścigu dla języka {current_lang_name}."
            st.rerun()

        if r_col1.button(f"🎲 Resetuj Ruletkę ({L_CODE.upper()})", disabled=not safety_lock, use_container_width=True):
            st.session_state.user_data[f"survival_scores_{L_CODE}"] = []
            save_user_data(u, st.session_state.user_data)
            st.session_state.acc_msg = f"Wyczyszczono rekordy Językowej Ruletki dla języka {current_lang_name}."
            st.rerun()

        if r_col2.button(f"🐍 Resetuj Węża (Global)", disabled=not safety_lock, use_container_width=True):
            st.session_state.user_data["snake_best_chain"] = 0
            st.session_state.user_data["snake_wins"] = 0
            st.session_state.user_data["snake_losses"] = 0
            save_user_data(u, st.session_state.user_data)
            st.session_state.acc_msg = "Statystyki Lingwistycznego Węża zostały wyzerowane."
            st.rerun()

        st.divider()

        st.subheader("Usuwanie wg poziomów")
        st.caption(f"Usuwa słówka z tagiem poziomu TYLKO dla języka {current_lang_name}.")
        col_lvl1, col_lvl2 = st.columns([2, 1])
        lvl_to_del = col_lvl1.selectbox("Wybierz poziom:", ["A1", "A2", "B1", "B2", "C1"], key="lvl_del_sel")
        
        if col_lvl2.button(f"Skasuj {lvl_to_del}", disabled=not safety_lock, use_container_width=True):
            res = get_db().table("flashcards").delete().eq("username", u).eq("lang", L_CODE).ilike("category", f"%{lvl_to_del}%").execute()
            count = len(res.data) if res.data else 0
            st.session_state.flashcards = load_flashcards(u)
            st.session_state.acc_msg = f"Skasowano {count} słówek z poziomu {lvl_to_del} ({current_lang_name})."
            st.rerun()

        st.divider()
        st.subheader("Resety całkowite")
        
        if st.button(f"💣 USUŃ WSZYSTKIE SŁÓWKA ({current_lang_name.upper()})", type="primary", disabled=not safety_lock, use_container_width=True):
            res = get_db().table("flashcards").delete().eq("username", u).eq("lang", L_CODE).execute()
            count = len(res.data) if res.data else 0
            st.session_state.flashcards = load_flashcards(u)
            st.session_state.acc_msg = f"Usunięto całą bazę słówek języka {current_lang_name} ({count} sztuk)."
            st.rerun()

        if st.button("🔥 Wyzeruj Streak (Konto globalne)", disabled=not safety_lock, use_container_width=True):
            st.session_state.user_data["streak"] = 0
            st.session_state.user_data["last_date"] = "2000-01-01"
            save_user_data(u, st.session_state.user_data)
            st.session_state.acc_msg = "Globalna passa została wyzerowana."
            st.rerun()

# --- 27. ADMIN PRO (V571 - Rerun Exception Fix & Analytics) ---
elif choice == "👑 Admin" and st.session_state.get("is_admin"):
    st.header("👑 Panel Administratora")

    # Aktualizacja aktywności admina
    st.session_state.user_data["last_seen"] = get_now_pl()
    save_user_data(u, st.session_state.user_data)

    # --- 1. DEFINICJE I MAPOWANIE ---
    ADMIN_ORDER = [
        "Pow", "Trn", "Qiz", "Fis", "Lab", "Wri", "Det", "War", "Tst", 
        "Spa", "Mem", "Kon", "Wan", "Bal", "Sur", "Due", "Skn", "Inn"
    ]

    MOD_MAP = {
        "Pow": "📅 Powtórki", "Trn": "🚀 Trening", "Qiz": "🕹️ Quiz", "Fis": "🎴 Fiszki",
        "Lab": "🧪 Laboratorium", "Wri": "✍️ Asystent Pisania", "Det": "🕵️ Kulturowy Detektyw", 
        "War": "🛠️ Warsztat", "Tst": "📝 Testy", "Spa": "🤖 Sparing AI", 
        "Mem": "🧠 Memory", "Kon": "🏗️ Konstruktor", "Wan": "🐍 Lingwistyczny Wąż", 
        "Bal": "🎈 Balonowy Wyścig", "Sur": "🎲 Językowa Ruletka", "Due": "⚔️ Klub Pojedynków", 
        "Skn": "📸 Skaner AI", "Inn": "⚙️ Inne"
    }

    STUDY_MODULES = [c for c in ADMIN_ORDER if c not in ["Inn", "Skn"]]

    # --- 2. SEEDERY I FUNKCJE ADMINA ---
    def seed_master_vocab(target_lang, target_lvl, total_goal):
        import json, time
        l_code = "de" if target_lang == "Niemiecki" else "cs"
        st.info(f"🚀 Generowanie {total_goal} słów ({target_lvl})...")
        db = get_db()
        progress_bar = st.progress(0)
        current_count = 0
        batch_size = 25 
        while current_count < total_goal:
            prompt = f"Wygeneruj {batch_size} unikalnych słów {target_lvl} ({target_lang}). JSON: vocab: [{{word, translation, level, lang, category, example_orig, example_pl}}]"
            try:
                raw_res = get_openai_response(prompt)
                items = json.loads(raw_res).get("vocab", [])
                if items:
                    db.table("master_vocab").insert(items).execute()
                    current_count += len(items)
                    progress_bar.progress(min(current_count / total_goal, 1.0))
                else: break
            except Exception: break
            time.sleep(0.5)
        st.success("Gotowe!")

    def seed_idioms(lang):
        import json
        st.info(f"📚 Generowanie idiomów ({lang})...")
        prompt = f"Wygeneruj 10 unikalnych idiomów ({lang}). JSON: idioms: [{{phrase_orig, phrase_pl, lang, level}}]"
        try:
            l_code = "de" if lang == "Niemiecki" else "cs"
            raw = get_openai_response(prompt)
            items = json.loads(raw).get("idioms", [])
            for item in items: item["lang"] = l_code
            get_db().table("idioms").insert(items).execute()
            st.success("Dodano idiomy!")
        except Exception: st.error("Błąd generatora idiomów.")

    def seed_cultural_trivia(lang):
        import json
        st.info(f"🌍 Generowanie ciekawostek ({lang})...")
        prompt = f"Wygeneruj 10 ciekawostek ({lang}). JSON: trivia: [{{title, content_orig, content_pl, lang}}]"
        try:
            l_code = "de" if lang == "Niemiecki" else "cs"
            raw = get_openai_response(prompt)
            items = json.loads(raw).get("trivia", [])
            for item in items: item["lang"] = l_code
            get_db().table("cultural_trivia").insert(items).execute()
            st.success("Dodano ciekawostki!")
        except Exception: st.error("Błąd generatora ciekawostek.")

    # --- 3. LOGIKA DANYCH ---
    db = get_db()
    ud_raw = db.table("user_data").select("*").execute().data
    
    tabs = st.tabs(["👥 Analiza Użytkowników", "🛠️ Zarządzanie", "📢 Ogłoszenia"])

    with tabs[0]:
        all_cards_res = db.table("flashcards").select("username", "mastery_xp", "origin").execute().data
        df_cards_all = pd.DataFrame(all_cards_res) if all_cards_res else pd.DataFrame(columns=["username", "mastery_xp", "origin"])

        col_adm1, col_adm2 = st.columns(2)
        with col_adm1:
            if st.button("🔄 Odśwież Dane", use_container_width=True): st.rerun()
        with col_adm2:
            st.link_button("💸 Koszty OpenAI", "https://platform.openai.com/usage", use_container_width=True)

        today_iso = date.today().isoformat()
        adm_summary = []
        global_daily = {code: 0.0 for code in ADMIN_ORDER}
        global_total = {code: 0.0 for code in ADMIN_ORDER}

        for user in ud_raw:
            uname = user["username"]
            u_cards = df_cards_all[df_cards_all["username"] == uname]
            is_u_admin = user.get("is_admin", False)
            status_prefix = ""
            if user.get("is_banned"): status_prefix += "🚫 "
            if user.get("is_shadowbanned"): status_prefix += "👻 "
            total_words = len(u_cards)
            oc = u_cards["origin"].fillna("Dodaj").tolist() if not u_cards.empty else []
            r_cnt = sum(1 for x in oc if any(s in str(x) for s in ["Dodaj", "Detektyw", "Manual"]))
            g_cnt = sum(1 for x in oc if "Generator" in str(x))
            s_cnt = sum(1 for x in oc if "Skaner" in str(x))
            w_str = "0%"
            if total_words > 0:
                xp_sum = u_cards["mastery_xp"].fillna(0).sum()
                w_val = int((xp_sum / (total_words * 150)) * 100)
                w_str = f"{min(w_val, 100)}%"
            def proc_stats(raw_dict):
                p = {code: 0.0 for code in ADMIN_ORDER}
                for k, v in (raw_dict or {}).items():
                    if k in p: p[k] += v
                    else: p["Inn"] += v
                return p
            u_daily = proc_stats(user.get("time_stats", {}) if user.get("last_visit_date") == today_iso else {})
            u_total = proc_stats(user.get("total_time_stats", {}))
            for code in ADMIN_ORDER:
                if is_u_admin and code == "Inn": continue
                global_daily[code] += u_daily[code]
                global_total[code] += u_total[code]
            adm_summary.append({
                "Użytkownik": f"{status_prefix}{uname}",
                "E-mail": user.get("email", "-"),
                "Ostatnio": user.get("last_seen", "-"),
                "🔥": user.get("streak", 0),
                "Słówka (R|G|S)": f"{total_words} ({r_cnt}|{g_cnt}|{s_cnt})", 
                "Wiedza": w_str, 
                "Nauka dziś": int(sum(u_daily[c] for c in STUDY_MODULES) // 60),
                "Łącznie (min)": int(sum(u_total.values()) // 60), 
                "Koszt": f"{user.get('historical_cost', 0.0):.2f} zł",
                "u_total_map": u_total,
                "raw_uname": uname.lower()
            })
        def adm_sort(x):
            n = x["raw_uname"]
            if n == "wobo": return (0, "")
            if n == "wiola": return (1, "")
            return (2, n)
        adm_summary.sort(key=adm_sort)
        st.subheader("📋 Podsumowanie Kont")
        df_main = pd.DataFrame(adm_summary)
        st.dataframe(df_main.drop(columns=["u_total_map", "raw_uname"]), use_container_width=True, hide_index=True,
            column_config={
                "Nauka dziś": st.column_config.ProgressColumn("Nauka dziś (cel 60m)", min_value=0, max_value=60, format="%d min")
            })
        st.divider()
        st.subheader("🕵️ Szczegółowy Czas Historyczny (minuty)")
        hist_table = []
        for item in adm_summary:
            row = {"Użytkownik": item["Użytkownik"]}
            for code in ADMIN_ORDER:
                row[MOD_MAP[code]] = int(item["u_total_map"][code] // 60)
            hist_table.append(row)
        st.dataframe(pd.DataFrame(hist_table), use_container_width=True, hide_index=True)
        st.divider()
        cg1, cg2 = st.columns(2)
        def show_glob(cont, title, d_dict):
            cont.subheader(title)
            t_s = sum(d_dict.values())
            rows = []
            for code in ADMIN_ORDER:
                v = d_dict[code]
                p = f"{round((v/t_s)*100, 1)}%" if t_s > 0 else "0%"
                t_str = f"{int(v//3600)}h {int((v%3600)//60)}m" if v >= 3600 else f"{int(v//60)} min"
                rows.append({"Moduł": MOD_MAP[code], "%": p, "Czas": t_str})
            cont.table(pd.DataFrame(rows))
        show_glob(cg1, "📈 Globalnie (Dziś)", global_daily)
        show_glob(cg2, "📊 Globalnie (Historycznie)", global_total)

    with tabs[1]:
        st.subheader("👤 Edytor Profili")
        u_list = [d["username"] for d in ud_raw]
        sel_u = st.selectbox("Wybierz konto:", u_list)
        t_data = next((i for i in ud_raw if i["username"] == sel_u), None)
        if t_data:
            with st.expander(f"🛠️ Narzędzia: {sel_u}", expanded=True):
                ce1, ce2 = st.columns(2)
                with ce1:
                    n_mail = st.text_input("E-mail:", value=t_data.get("email", ""))
                    n_pass = st.text_input("Hasło (puste=brak zmian):", type="password")
                    a_notes = st.text_area("Notatki:", value=t_data.get("admin_notes", ""))
                with ce2:
                    is_b = st.checkbox("🚫 Zablokuj (BAN)", value=t_data.get("is_banned", False))
                    is_a = st.checkbox("👑 Admin", value=t_data.get("is_admin", False))
                    is_s = st.checkbox("👻 Shadowban", value=t_data.get("is_shadowbanned", False))
                if st.button(f"💾 Zapisz: {sel_u}", use_container_width=True, type="primary"):
                    upd = {"email": n_mail, "is_banned": is_b, "is_admin": is_a, "is_shadowbanned": is_s, "admin_notes": a_notes}
                    if n_pass: upd["password"] = n_pass
                    db.table("user_data").update(upd).eq("username", sel_u).execute()
                    st.success("Zaktualizowano!"); st.rerun()
        st.divider()
        st.subheader("📂 Backupy")
        cb1, cb2 = st.columns(2)
        with cb1:
            if st.button("📦 Backup Flashcards", use_container_width=True):
                d_fc = db.table("flashcards").select("*").execute().data
                st.download_button("⬇️ Pobierz CSV", pd.DataFrame(d_fc).to_csv(index=False).encode('utf-8'), "fc_backup.csv", "text/csv")
        with cb2:
            if st.button("👤 Backup Users", use_container_width=True):
                d_ud = db.table("user_data").select("*").execute().data
                st.download_button("⬇️ Pobierz CSV", pd.DataFrame(d_ud).to_csv(index=False).encode('utf-8'), "users_backup.csv", "text/csv")
        st.divider()
        st.subheader("🤖 AI Seeders")
        g1, g2, g3 = st.tabs(["📚 Vocab", "📖 Idiomy", "🌍 Trivia"])
        with g1:
            vl, vv = st.selectbox("Język", ["Niemiecki", "Czeski"], key="g1l"), st.selectbox("Poziom", ["A1", "A2", "B1", "B2", "C1"], key="g1v")
            vg = st.number_input("Ilość", 10, 500, 50, key="g1g")
            if st.button("Start Vocab Seeder"): seed_master_vocab(vl, vv, vg)
        with g2:
            il = st.selectbox("Język", ["Niemiecki", "Czeski"], key="g2l")
            if st.button("Generuj 10 Idiomów"): seed_idioms(il)
        with g3:
            cl = st.selectbox("Język", ["Niemiecki", "Czeski"], key="g3l")
            if st.button("Generuj 10 Ciekawostek"): seed_cultural_trivia(cl)

    with tabs[2]:
        st.subheader("📢 Zarządzanie Ogłoszeniami")
        with st.form("new_announcement_form"):
            st.write("**Wyślij nową wiadomość systemową**")
            col_an1, col_ann2 = st.columns([3, 1])
            ann_title = col_an1.text_input("Tytuł ogłoszenia:", placeholder="np. Nowa aktualizacja!")
            ann_target = col_ann2.selectbox("Adresat:", ["all"] + [u["username"] for u in ud_raw])
            ann_message = st.text_area("Treść wiadomości:", placeholder="Wpisz co chcesz przekazać użytkownikom...")
            col_an3, col_ann4, col_ann5 = st.columns([1, 2, 1])
            ann_icon = col_an3.text_input("Ikona (Emoji):", value="📢")
            ann_color = col_ann4.color_picker("Kolor tła wiadomości:", value="#2E86C1")
            if st.form_submit_button("🚀 Opublikuj ogłoszenie", use_container_width=True):
                if ann_title and ann_message:
                    try:
                        db.table("system_announcements").insert({"title": ann_title, "message": ann_message, "target": ann_target, "icon": ann_icon, "color": ann_color, "is_active": True}).execute()
                        st.success("Ogłoszenie zostało wysłane!")
                        st.rerun()
                    except Exception as e: st.error(f"Błąd bazy: {e}")
                else: st.warning("Tytuł i treść nie mogą być puste.")

        st.divider()
        st.write("**Historia ogłoszeń**")
        
        ann_data = []
        try:
            # Pobieramy dane bezpiecznie
            ann_res = db.table("system_announcements").select("*").order("created_at", desc=True).execute()
            ann_data = ann_res.data if ann_res.data else []
        except Exception as e:
            st.error(f"Błąd ładowania: {e}")

        if ann_data:
            for a in ann_data:
                # Dodajemy status wizualny do nagłówka expandera
                status_label = "✅ AKTYWNE" if a['is_active'] else "⚪ WYŁĄCZONE"
                with st.expander(f"{a['icon']} {a['title']} ({status_label} | Dla: {a['target']})"):
                    st.write(a['message'])
                    st.caption(f"Utworzono: {a['created_at']} | Kolor: {a['color']}")
                    c_ann1, c_ann2 = st.columns(2)
                    
                    # Logika przycisku zmiany stanu
                    new_state = not a['is_active']
                    btn_text = "✅ Aktywuj" if new_state else "⚪ Dezaktywuj"
                    if c_ann1.button(btn_text, key=f"state_{a['id']}", use_container_width=True):
                        db.table("system_announcements").update({"is_active": new_state}).eq("id", a['id']).execute()
                        st.rerun()
                        
                    if c_ann2.button("🗑️ Usuń trwale", key=f"del_ann_{a['id']}", use_container_width=True):
                        db.table("system_announcements").delete().eq("id", a['id']).execute()
                        st.rerun()
        else:
            st.info("Brak ogłoszeń w historii.")

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

# --- 29. LABORATORIUM RODZAJNIKÓW (V1.2 - Anti-Error & Auto-Reset) ---
elif choice == "🧪 Laboratorium":
    current_lang_name = st.session_state.get("current_lang", "Niemiecki")
    L_CODE = "de" if current_lang_name == "Niemiecki" else "cs"
    
    st.header(f"🧪 Laboratorium Rodzajników: {current_lang_name}")
    st.write("Rozpoznaj rodzaj. Kolor czcionki po odpowiedzi wskaże Ci właściwą barwę rodzajnika.")

    # 1. KONFIGURACJA KOLORÓW
    GENDER_COLORS = {
        "de": {"der": "#000000", "die": "#FF0000", "das": "#FFCC00"},
        "cs": {"ten": "#FFFFFF", "ta": "#11457E", "to": "#D71920"}
    }

    RULES = {
        "de": {
            "die": ["ung", "heit", "keit", "schaft", "in", "ion", "ei", "ität"],
            "der": ["ismus", "or", "ig", "ling", "er"],
            "das": ["chen", "lein", "ment", "um", "ma"]
        },
        "cs": {
            "ta": ["ost", "a", "ice", "ba"],
            "ten": ["r", "l", "n", "t", "d", "m", "s", "z"],
            "to": ["o", "í", "e", "um"]
        }
    }

    # 2. PRZYGOTOWANIE DANYCH
    def get_gender(word, lang):
        w = word.lower().strip()
        if lang == "de":
            if w.startswith("der "): return "der", word[4:]
            if w.startswith("die "): return "die", word[4:]
            if w.startswith("das "): return "das", word[4:]
        else:
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

    # --- BEZPIECZNIK: Reset sesji przy zmianie języka lub braku danych ---
    if "lab_lang_ref" not in st.session_state or st.session_state.lab_lang_ref != L_CODE:
        st.session_state.lab_lang_ref = L_CODE
        st.session_state.lab_idx = 0
        st.session_state.lab_feedback = None

    if len(nouns) < 3:
        st.warning(f"Dodaj więcej rzeczowników z rodzajnikami (np. 'der Hund' lub 'ten dům'), aby odblokować ten moduł dla języka {current_lang_name}.")
    else:
        # Zabezpieczenie przed Indexem poza zakresem (np. po usunięciu słówek)
        if st.session_state.lab_idx >= len(nouns):
            st.session_state.lab_idx = 0

        curr = nouns[st.session_state.lab_idx]
        
        # LOGIKA KOLORÓW I RAMKI
        word_color = "white"
        border_color = "#333"
        text_glow = "none"

        if st.session_state.lab_feedback:
            border_color = "#28a745" if st.session_state.lab_feedback["is_correct"] else "#dc3545"
            word_color = GENDER_COLORS[L_CODE].get(curr['gender'], "white")
            if L_CODE == "de" and curr['gender'] == "der":
                text_glow = "0px 0px 10px rgba(255,255,255,0.8), 1px 1px 2px white"
            if L_CODE == "cs" and curr['gender'] == "ten":
                text_glow = "0px 0px 8px rgba(0,0,0,0.5)" # Lekki cień dla białego TEN na ciemnym tle

        # GŁÓWNA KARTA
        st.markdown(f"""
            <div style="text-align:center; padding:50px; border:6px solid {border_color}; 
            border-radius:25px; background:#111; margin-bottom:20px; transition: all 0.3s ease;">
                <div style="font-size:1.2rem; color:#aaa; margin-bottom:10px;">{curr['pl']}</div>
                <div style="font-size:4rem; font-weight:bold; color:{word_color}; text-shadow:{text_glow};">
                    {curr['clean']}
                </div>
            </div>
        """, unsafe_allow_html=True)

        # PRZYCISKI
        options = ["DER", "DIE", "DAS"] if L_CODE == "de" else ["TEN", "TA", "TO"]
        cols = st.columns(3)
        
        for i, opt in enumerate(options):
            is_correct_btn = opt.lower() == curr['gender']
            btn_type = "secondary"
            if st.session_state.lab_feedback and is_correct_btn:
                btn_type = "primary"

            if cols[i].button(opt, key=f"lab_btn_{i}", use_container_width=True, type=btn_type):
                if not st.session_state.lab_feedback:
                    is_correct = opt.lower() == curr['gender']
                    rule_found = None
                    for g, endings in RULES[L_CODE].items():
                        for e in endings:
                            if curr['clean'].lower().endswith(e):
                                rule_found = f"Zasada końcówki: -{e} oznacza rodzaj {g.upper()}."
                                break
                    
                    st.session_state.lab_feedback = {
                        "is_correct": is_correct,
                        "rule": rule_found or "To słowo może być wyjątkiem lub rzadszą formą."
                    }
                    if is_correct: 
                        if "lab_score" not in st.session_state: st.session_state.lab_score = 0
                        st.session_state.lab_score += 1
                    st.rerun()

        # FEEDBACK
        if st.session_state.lab_feedback:
            st.divider()
            if st.session_state.lab_feedback["is_correct"]:
                st.success(f"✨ Dobrze! To jest **{curr['gender'].upper()} {curr['clean']}**")
            else:
                st.error(f"❌ Błąd. Poprawna forma to **{curr['gender'].upper()} {curr['clean']}**")
            
            st.info(st.session_state.lab_feedback["rule"])
            
            if st.button("Następne słowo ➡️", use_container_width=True, type="primary"):
                st.session_state.lab_idx = random.randint(0, len(nouns)-1)
                st.session_state.lab_feedback = None
                st.rerun()

    # SIDEBAR
    with st.sidebar:
        st.divider()
        st.subheader("💡 Ściąga końcówek")
        if L_CODE == "de":
            st.markdown("⚫ **DER (Męski):** -ismus, -or, -er, -ig")
            st.markdown("<span style='color:#FF0000;'>🔴</span> **DIE (Żeński):** -ung, -heit, -keit, -schaft", unsafe_allow_html=True)
            st.markdown("<span style='color:#FFCC00;'>🟡</span> **DAS (Nijaki):** -chen, -lein, -um, -ment", unsafe_allow_html=True)
        else:
            st.markdown("⚪ **TEN (Męski):** spółgłoski (h, k, r, d...)")
            st.markdown("<span style='color:#11457E;'>🔵</span> **TA (Żeński):** -ost, -a, -ice, -ba", unsafe_allow_html=True)
            st.markdown("<span style='color:#D71920;'>🔴</span> **TO (Nijaki):** -o, -í, -e, -um", unsafe_allow_html=True)

# --- 30. ASYSTENT PISANIA (V1.9 - Custom Topic Translation Fix) ---
elif choice == "✍️ Asystent Pisania":
    import openai
    import hashlib

    current_lang_name = st.session_state.get("current_lang", "Niemiecki")
    L_CODE = "de" if current_lang_name == "Niemiecki" else "cs"
    st.header(f"✍️ Asystent Pisania: {current_lang_name}")

    # --- FUNKCJE BAZODANOWE ---
    def save_writing(data):
        try:
            get_db().table("writing_history").insert(data).execute()
            return True
        except: return False

    def load_writing_history(username, lang_code):
        try:
            res = get_db().table("writing_history").select("*").eq("username", username).eq("lang", lang_code).order("created_at", desc=True).execute()
            return res.data if res.data else []
        except: return []

    # --- ROZBUDOWANA BAZA 25 TEMATÓW DNIA ---
    daily_topics = {
        "de": [
            {"orig": "Beschreibe deinen Morgen.", "pl": "Opisz swój poranek."},
            {"orig": "Was sind deine Ziele für dieses Jahr?", "pl": "Jakie są Twoje cele na ten rok?"},
            {"orig": "Erzähle von deinem Hobby.", "pl": "Opowiedz o swoim hobby."},
            {"orig": "Warum lernst du Deutsch?", "pl": "Dlaczego uczysz się niemieckiego?"},
            {"orig": "Wie sieht dein Traumhaus aus?", "pl": "Jak wygląda Twój dom marzeń?"},
            {"orig": "Beschreibe deinen letzten Urlaub.", "pl": "Opisz swoje ostatnie wakacje."},
            {"orig": "Was ist deine Lieblingsspeise und warum?", "pl": "Jaka jest Twoja ulubiona potrawa i dlaczego?"},
            {"orig": "Ein tag ohne Internet: Was würdest du tun?", "pl": "Dzień bez internetu: co byś robił?"},
            {"orig": "Erzähle von deiner besten Freundin oder deinem besten Freund.", "pl": "Opowiedz o swojej najlepszej przyjaciółce lub przyjacielu."},
            {"orig": "Welche Stadt möchtest du besuchen?", "pl": "Jakie miasto chciałbyś odwiedzić?"},
            {"orig": "Wie sieht ein typischer Arbeitstag bei dir aus?", "pl": "Jak wygląda Twój typowy dzień pracy?"},
            {"orig": "Was ist dein Lieblingsbuch oder dein Lieblingsfilm?", "pl": "Jaka jest Twoja ulubiona książka lub film?"},
            {"orig": "Beschreibe dein Haustier (oder dein Traum-Haustier).", "pl": "Opisz swoje zwierzę (lub zwierzę marzeń)."},
            {"orig": "Was war dein schönstes Kindheitserlebnis?", "pl": "Jakie było Twoje najpiękniejsze wspomnienie z dzieciństwa?"},
            {"orig": "Wie verbringst du normalerweise deinen Sonntag?", "pl": "Jak zwykle spędzasz niedzielę?"},
            {"orig": "Welche Rolle spielt Sport in deinem Leben?", "pl": "Jaką rolę odgrywa sport w Twoim życiu?"},
            {"orig": "Was würdest du tun, wenn du im Lotto gewinnen würdest?", "pl": "Co byś zrobił, gdybyś wygrał w lotto?"},
            {"orig": "Beschreibe das Wetter heute.", "pl": "Opisz dzisiejszą pogodę."},
            {"orig": "Kochen oder im Restaurant essen? Was bevorzugst du?", "pl": "Gotowanie czy jedzenie w restauracji? Co wolisz?"},
            {"orig": "Welche Jahreszeit magst du am meisten?", "pl": "Którą porę roku lubisz najbardziej?"},
            {"orig": "Erzähle von einer Person, die dich inspiriert.", "pl": "Opowiedz o osobie, która Cię inspiruje."},
            {"orig": "Wie stellst du dir die Welt in 50 Jahren vor?", "pl": "Jak wyobrażasz sobie świat za 50 lat?"},
            {"orig": "Was ist dein wichtigster Ratschlag fürs Leben?", "pl": "Jaka jest Twoja najważniejsza rada życiowa?"},
            {"orig": "Beschreibe deinen Lieblingsort in deiner Stadt.", "pl": "Opisz swoje ulubione miejsce w Twoim mieście."},
            {"orig": "Was planst du für heute Abend?", "pl": "Co planujesz na dzisiejszy wieczór?"}
        ],
        "cs": [
            {"orig": "Popiš své ráno.", "pl": "Opisz swój poranek."},
            {"orig": "Jaké jsou tvé cíle pro tento rok?", "pl": "Jakie są Twoje cele na ten rok?"},
            {"orig": "Vyprávěj o svém koníčku.", "pl": "Opowiedz o swoim hobby."},
            {"orig": "Proč se učíš česky?", "pl": "Proč se učíš česky?"},
            {"orig": "Jak vypadá tvůj dům snů?", "pl": "Jak wygląda Twój dom marzeń?"},
            {"orig": "Popiš svou poslední dovolenou.", "pl": "Opisz swoje ostatnie wakacje."},
            {"orig": "Jaké je tvé nejoblíbenější jídlo a proč?", "pl": "Jaka jest Twoja ulubiona potrawa i dlaczego?"},
            {"orig": "Den bez internetu: Co bys dělal?", "pl": "Dzień bez internetu: co byś robił?"},
            {"orig": "Vyprávěj o svém nejlepším příteli nebo přítelkyni.", "pl": "Opowiedz o swoim najlepszym przyjacielu lub przyjaciółce."},
            {"orig": "Které město bys chtěl navštívit?", "pl": "Jakie miasto chciałbyś odwiedzić?"},
            {"orig": "Jak vypadá tvůj typický pracovní den?", "pl": "Jak wygląda Twój typowy dzień pracy?"},
            {"orig": "Jaká je tvá nejoblíbenější kniha nebo film?", "pl": "Jaka jest Twoja ulubiona książka lub film?"},
            {"orig": "Popiš svého domácího mazlíčka (nebo vysněné zvíře).", "pl": "Opisz swoje zwierzę (lub zwierzę marzeń)."},
            {"orig": "Jaký byl tvůj nejkrásnější zážitek z dětství?", "pl": "Jakie było Twoje najpiękniejsze wspomnienie z dzieciństwa?"},
            {"orig": "Jak obvykle trávíš svou neděli?", "pl": "Jak zwykle spędzasz niedzielę?"},
            {"orig": "Jakou roli hraje sport ve tvém životě?", "pl": "Jakou roli hraje sport ve tvém životě?"},
            {"orig": "Co bys dělal, kdybys vyhrál v loterii?", "pl": "Co byś zrobił, gdybyś wygrał w loterii?"},
            {"orig": "Popiš dnešní počasí.", "pl": "Opisz dzisiejszą pogodę."},
            {"orig": "Vaření nebo jídlo v restauraci? Co preferuješ?", "pl": "Gotování czy jedzenie w restauracji? Co wolisz?"},
            {"orig": "Které roční období máš nejraději?", "pl": "Którą porę roku lubisz najbardziej?"},
            {"orig": "Vyprávěj o osobě, která tě inspiruje.", "pl": "Opowiedz o osobie, która Cię inspiruje."},
            {"orig": "Jak si představuješ svět za 50 let?", "pl": "Jak wyobrażasz sobie świat za 50 lat?"},
            {"orig": "Jaká je tvá nejdůležitější rada do života?", "pl": "Jaka jest Twoja najważniejsza rada życiowa?"},
            {"orig": "Popiš své nejoblíbenější místo ve tvém městě.", "pl": "Opisz swoje ulubione miejsce w Twoim mieście."},
            {"orig": "Co plánuješ na dnešní večer?", "pl": "Co planujesz na dzisiejszy wieczór?"}
        ]
    }
    
    today_str = date.today().isoformat()
    topic_idx = int(hashlib.md5(today_str.encode()).hexdigest(), 16) % len(daily_topics[L_CODE])
    daily_obj = daily_topics[L_CODE][topic_idx]

    # --- TABS ---
    tab_daily, tab_custom, tab_history = st.tabs(["📅 Zadanie Dnia", "🎯 Wyzwanie Własne", "📖 Moje Archiwum"])
    show_eval = "writing_result" in st.session_state

    with tab_daily:
        if not show_eval:
            st.subheader("Dzisiejszy temat:")
            st.info(f"### {daily_obj['orig']}")
            with st.expander("👁️ Pokaż tłumaczenie tematu"):
                st.write(daily_obj['pl'])
            
            user_text_daily = st.text_area("Twoja wypowiedź (min. 3 zdania):", key="daily_area_v19", height=200)
            
            if st.button("🚀 Wyślij do oceny", key="btn_daily_v19", disabled=len(user_text_daily.strip()) < 10):
                s_count = len(re.findall(r'[^.!?]+[.!?]', user_text_daily))
                if s_count < 3: 
                    st.warning(f"Zbyt krótki tekst ({s_count}/3 zdania).")
                else:
                    st.session_state.writing_action = ("eval", user_text_daily, daily_obj['orig'])
                    st.rerun()
        else:
            st.warning("Przeglądasz wynik. Zamknij go na dole, aby napisać nowy tekst.")

    with tab_custom:
        if not show_eval:
            st.subheader("Własne zadanie")
            c1, c2 = st.columns([3, 1])
            custom_t = c1.text_input("Temat:", placeholder="np. Mój ulubiony film", key="custom_t_in_v19")
            min_s = c2.number_input("Zdania:", 3, 15, 3)
            
            if st.button("🎲 Losuj / Ustaw temat", key="btn_custom_gen_v19"):
                if not custom_t or custom_t.lower() == "losowy temat":
                    with st.spinner("AI losuje..."):
                        client = openai.OpenAI(api_key=API_KEY)
                        res = client.chat.completions.create(
                            model="gpt-4o-mini", 
                            messages=[{"role": "user", "content": f"Podaj krótki temat wypracowania po {current_lang_name} i jego tłumaczenie PL. Format: Temat_PL ||| Temat_ORIG"}]
                        )
                        st.session_state.custom_topic_active = res.choices[0].message.content
                else:
                    st.session_state.custom_topic_active = f"{custom_t} ||| {custom_t}"
            
            if "custom_topic_active" in st.session_state:
                t_parts = st.session_state.custom_topic_active.split("|||")
                t_pl = t_parts[0].strip()
                t_orig = t_parts[1].strip() if len(t_parts) > 1 else t_pl
                
                st.markdown(f"📍 Temat: **{t_orig}**")
                # --- PRZYWRÓCONE ROZWIJANE TŁUMACZENIE ---
                with st.expander("👁️ Pokaż tłumaczenie tematu"):
                    st.write(t_pl)
                # ----------------------------------------
                
                user_text_custom = st.text_area("Pisz tutaj:", key="custom_area_v19", height=200)
                if st.button("🚀 Oceń wyzwanie", key="btn_custom_eval_v19", disabled=len(user_text_custom.strip()) < 10):
                    s_count = len(re.findall(r'[^.!?]+[.!?]', user_text_custom))
                    if s_count < min_s: st.warning(f"Zbyt mało zdań ({s_count}/{min_s}).")
                    else: 
                        st.session_state.writing_action = ("eval", user_text_custom, t_orig)
                        st.rerun()

    with tab_history:
        st.subheader("Archiwum prac")
        history = load_writing_history(u, L_CODE)
        if not history:
            st.write("Brak zapisanych prac w tym języku.")
        else:
            for item in history:
                with st.expander(f"📅 {item['created_at'][:10]} | {item['topic'][:40]}..."):
                    st.markdown(f"**Poziom:** `{item['level']}`")
                    st.caption("Twoja praca:")
                    st.write(item['user_text'])
                    st.divider()
                    st.warning(f"**Korekta:**\n{item['corrections']}")
                    st.success(f"**Wersja Mistrzowska:**\n{item['master_version']}")
                    st.info(f"💡 {item['motivation']}")

    # --- LOGIKA PRZETWARZANIA PRZEZ AI ---
    if "writing_action" in st.session_state:
        action, text, topic = st.session_state.writing_action
        with st.spinner("Nauczyciel AI analizuje tekst..."):
            try:
                client = openai.OpenAI(api_key=API_KEY)
                prompt = f"""Jesteś nauczycielem {current_lang_name}. Oceń tekst ucznia.
                Temat: {topic}
                Tekst: {text}
                WYMAGANY FORMAT (bezwzględnie 4 części oddzielone |||):
                Poziom (np. A2) ||| Lista błędów i poprawki ||| Wersja C1 tego tekstu ||| Krótka motywacja
                ZASADA: Nie pisz żadnych wstępów. Tylko te 4 części."""
                
                resp = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}])
                raw_res = resp.choices[0].message.content.strip().replace("```", "").replace("JSON", "").strip()
                res_parts = raw_res.split("|||")
                
                if len(res_parts) < 4:
                    res_parts = raw_res.split("\n\n")
                    if len(res_parts) < 4: raise Exception("Błąd formatu AI.")

                final_res = {
                    "username": u, "lang": L_CODE, "topic": topic,
                    "user_text": text, "level": res_parts[0].strip(),
                    "corrections": res_parts[1].strip(),
                    "master_version": res_parts[2].strip(),
                    "motivation": res_parts[3].strip()
                }
                save_writing(final_res)
                st.session_state.writing_result = final_res
                del st.session_state.writing_action
                st.rerun()
            except Exception as e:
                st.error(f"Błąd analizy: {e}")
                del st.session_state.writing_action

    # --- WYŚWIETLANIE WYNIKU ---
    if "writing_result" in st.session_state:
        res = st.session_state.writing_result
        st.divider()
        st.balloons()
        st.success("✅ Praca oceniona i zapisana!")
        c1, c2 = st.columns([1, 3])
        c1.metric("Poziom", res["level"])
        c2.info(res['motivation'])
        st.subheader("🔍 Szczegółowa korekta")
        st.warning(res["corrections"])
        with st.expander("✨ Wersja Mistrzowska (Native C1)"):
            st.write(res["master_version"])
        if st.button("Wróć do zadań", use_container_width=True, key="back_btn_v19"):
            del st.session_state.writing_result
            st.rerun()

# --- 31. KULTUROWY DETEKTYW (V1.0 - Idioms investigation module) ---
elif choice == "🕵️ Kulturowy Detektyw":
    import hashlib
    current_lang_name = st.session_state.get("current_lang", "Niemiecki")
    L_CODE = "de" if current_lang_name == "Niemiecki" else "cs"
    
    st.header(f"🕵️ Kulturowy Detektyw: {current_lang_name}")
    st.write("Rozwiązuj zagadki językowe i brzmij jak native speaker.")

    # --- FUNKCJE POMOCNICZE ---
    def load_idioms_from_db(lang, category=None):
        try:
            query = get_db().table("idioms_library").select("*").eq("lang", lang)
            if category and category != "Wszystkie":
                query = query.eq("category", category)
            res = query.execute()
            return res.data if res.data else []
        except: return []

    def get_idiom_from_ai(lang, cat, excluded_list):
        with st.spinner("Przeszukuję archiwa wywiadu (AI)..."):
            l_full = "niemieckim" if lang == "de" else "czeskim"
            prompt = f"""Podaj jeden unikalny idiom lub zwrot slangowy w języku {l_full} z kategorii: {cat}.
            NIE MOŻE to być żadna z tych fraz: {excluded_list}.
            Zwróć WYŁĄCZNIE JSON:
            {{
              "phrase": "...", "literal_pl": "...", "meaning_pl": "...", 
              "origin_pl": "...", "example_orig": "...", "example_pl": "...", 
              "formality": "🟢", "category": "{cat}"
            }}"""
            try:
                raw = get_openai_response(prompt) # Twoja funkcja globalna
                return json.loads(raw)
            except: return None

    # --- UI: ZAKŁADKI ---
    tab_daily, tab_search = st.tabs(["📍 Sprawa Dnia", "🔍 Archiwum X (Kategorie)"])

    # Pobieramy Twoje obecne fiszki, żeby nie proponować tego, co już znasz
    my_idioms = [c['de'].lower() for c in st.session_state.flashcards if "#idiom" in str(c.get('category',''))]

    with tab_daily:
        # Logika Sprawy Dnia (Seed oparty na dacie)
        today_str = date.today().isoformat()
        all_db_idioms = load_idioms_from_db(L_CODE)
        
        if all_db_idioms:
            # Algorytm wyboru "tego samego idiomu dla wszystkich"
            idx = int(hashlib.md5(today_str.encode()).hexdigest(), 16) % len(all_db_idioms)
            daily_case = all_db_idioms[idx]
            
            st.subheader("📍 Dzisiejszy raport terenowy:")
            
            # --- WIZUALIZACJA TECZKI DOWODOWEJ ---
            with st.container(border=True):
                c1, c2 = st.columns([3, 1])
                c1.markdown(f"### 🏷️ `{daily_case['phrase']}`")
                c2.markdown(f"**Status:** {daily_case['formality']}")
                
                st.markdown(f"**📂 Kategoria:** {daily_case['category']}")
                st.write("---")
                
                col_a, col_b = st.columns(2)
                with col_a:
                    st.error(f"**🧐 Dosłownie:** {daily_case['literal_pl']}")
                with col_b:
                    st.success(f"**🎯 Naprawdę znaczy:** {daily_case['meaning_pl']}")
                
                with st.expander("🕵️ Geneza i Dowody (Dlaczego tak mówimy?)"):
                    st.info(daily_case['origin_pl'])
                    st.write("**Przykład użycia:**")
                    st.markdown(f"> *{daily_case['example_orig']}*")
                    st.caption(f"PL: {daily_case['example_pl']}")

                # PRZYCISK DODAWANIA DO TWOJEJ BAZY
                if daily_case['phrase'].lower() in my_idioms:
                    st.button("✅ Masz to już w słowniku", disabled=True, use_container_width=True)
                else:
                    if st.button("➕ Dodaj do moich akt (Słownik)", use_container_width=True, type="primary"):
                        new_card = {
                            "de": daily_case['phrase'],
                            "pl": daily_case['meaning_pl'],
                            "category": f"#idiom, {daily_case['category']}, {daily_case['formality']}",
                            "lang": L_CODE,
                            "next_review": str(date.today()),
                            "level": 0, "origin": "Kulturowy Detektyw",
                            "examples": [{"de": daily_case['example_orig'], "pl": daily_case['example_pl']}]
                        }
                        save_word(u, new_card)
                        st.session_state.flashcards = load_flashcards(u)
                        st.toast("Dodano do bazy nauki! 🚀")
                        st.rerun()

    with tab_search:
        st.subheader("🔍 Przeszukaj bazę tematyczną")
        cats = ["Wszystkie", "Jedzenie", "Pieniądze", "Emocje", "Praca", "Pogoda", "Zwierzęta", "Czas", "Ludzie"]
        sel_cat = st.selectbox("Wybierz kategorię śledztwa:", cats)
        
        if st.button("🔎 Rozpocznij dochodzenie", use_container_width=True):
            # 1. Szukamy w Supabase
            potential_cases = load_idioms_from_db(L_CODE, sel_cat)
            # Filtrujemy te, których user jeszcze nie zna
            new_cases = [i for i in potential_cases if i['phrase'].lower() not in my_idioms]
            
            if len(new_cases) >= 1:
                # Losujemy jeden z bazy
                st.session_state.active_investigation = random.choice(new_cases)
            else:
                # 2. Jeśli brak w bazie -> AI Fallback
                excluded = [i['phrase'] for i in potential_cases] + my_idioms
                ai_case = get_idiom_from_ai(L_CODE, sel_cat, excluded[:20])
                if ai_case:
                    st.session_state.active_investigation = ai_case
                    st.warning("🕵️ Znaleziono nowy dowód poza oficjalną bazą (Wygenerowane przez AI)")

        # Wyświetlanie aktywnego śledztwa (jeśli wybrano)
        if "active_investigation" in st.session_state:
            case = st.session_state.active_investigation
            st.write("---")
            with st.container(border=True):
                st.markdown(f"### 📂 Sprawa: `{case['phrase']}`")
                st.write(f"**Znaczenie:** {case['meaning_pl']}")
                st.caption(f"Dosłownie: {case['literal_pl']}")
                
                with st.expander("Zobacz pełne akta"):
                    st.write(f"💡 {case['origin_pl']}")
                    st.info(f"💬 {case['example_orig']}\n\n*(PL: {case['example_pl']})*")
                
                if st.button("➕ Wpisz do moich akt", key="add_investigation"):
                    new_card = {
                        "de": case['phrase'], "pl": case['meaning_pl'],
                        "category": f"#idiom, {case['category']}, {case['formality']}",
                        "lang": L_CODE, "next_review": str(date.today()),
                        "level": 0, "origin": "Kulturowy Detektyw",
                        "examples": [{"de": case['example_orig'], "pl": case['example_pl']}]
                    }
                    save_word(u, new_card)
                    st.session_state.flashcards = load_flashcards(u)
                    st.success("Zapisano!")
                    del st.session_state.active_investigation
                    st.rerun()

    # --- SIDEBAR: LEGENDA DETEKTYWA ---
    with st.sidebar:
        st.divider()
        st.subheader("🕵️ Legenda Detektywa")
        st.write("🟢 **Bezpieczny:** Można użyć wszędzie.")
        st.write("🟡 **Potoczny:** Do znajomych i rodziny.")
        st.write("🔴 **Uliczny:** Tylko w bardzo luźnych sytuacjach.")
        st.caption("Każdy idiom dodany do słownika otrzymuje tag #idiom.")

# --- 32. DYNAMO FAN-ZONE (V2.1 - Empty State Fix) ---
elif choice == "🏟️ Dynamo Fan-Zone" and st.session_state.get("is_admin"):
    st.markdown("<style>.stApp { background-color: #000000; } h1, h2, h3, p, span { color: #f9d71c !important; }</style>", unsafe_allow_html=True)
    st.title("🏟️ SGD Karaoke Player")
    
    db = get_db()
    try:
        res = db.table("fan_chants").select("*").execute()
        chants = res.data if res.data else []
    except:
        chants = []

    # Sprawdzamy czy mamy co wyświetlić
    if chants:
        sel_name = st.selectbox("Wybierz hymn:", [c['title'] for c in chants])
        chant = next(item for item in chants if item["title"] == sel_name)
        
        timed_data = chant.get('lyrics_timed', "")
        audio_url = chant.get('audio_url', "")

        if timed_data and audio_url:
            # --- MODUŁ KARAOKE ---
            import json
            lines = []
            for l in timed_data.split('\n'):
                if '|' in l:
                    t, txt = l.split('|', 1)
                    lines.append({"time": float(t), "text": txt.strip()})
            lines_json = json.dumps(lines)

            st.components.v1.html(f"""
                <div id="lyrics-box" style="height: 250px; overflow-y: auto; background: #111; padding: 20px; border: 2px solid #f9d71c; border-radius: 10px; text-align: center; font-family: sans-serif;">
                    <div id="display" style="color: #f9d71c;">Rozpocznij audio...</div>
                </div>
                <br>
                <audio id="player" controls style="width: 100%; filter: invert(100%) hue-rotate(180deg);">
                    <source src="{audio_url}" type="audio/mpeg">
                </audio>
                <script>
                    const lines = {lines_json};
                    const audio = document.getElementById('player');
                    const display = document.getElementById('display');
                    const box = document.getElementById('lyrics-box');
                    audio.ontimeupdate = () => {{
                        const cur = audio.currentTime;
                        let activeIndex = -1;
                        for (let i = 0; i < lines.length; i++) {{ if (cur >= lines[i].time) activeIndex = i; }}
                        if (activeIndex !== -1) {{
                            let html = "";
                            lines.forEach((l, idx) => {{
                                const cls = idx === activeIndex ? "color: #fff; font-size: 1.5rem; font-weight: bold; text-shadow: 0 0 10px #f9d71c;" : "opacity: 0.3;";
                                html += `<div id="line-${{idx}}" style="margin: 10px 0; transition: 0.3s; ${{cls}}">${{l.text}}</div>`;
                            }});
                            display.innerHTML = html;
                            const activeEl = document.getElementById("line-" + activeIndex);
                            if (activeEl) box.scrollTo({{ top: activeEl.offsetTop - 100, behavior: 'smooth' }});
                        }}
                    }};
                </script>
            """, height=450)
        else:
            st.info("Dodaj URL audio i tekst z czasem w sekcji poniżej, aby uruchomić Karaoke.")
    else:
        st.warning("Baza przyśpiewek jest pusta. Dodaj swoją pierwszą pieśń w formularzu poniżej! 👇")

    # Formularz dodawania (zawsze widoczny)
    with st.expander("🛠️ Edytuj / Dodaj nową przyśpiewkę"):
        with st.form("edit_sgd_v2"):
            f_title = st.text_input("Tytuł (musi być unikalny)")
            f_audio = st.text_input("URL do pliku MP3")
            f_timed = st.text_area("Tekst ZSYNCHRONIZOWANY (Format: sekunda|tekst)")
            f_pl = st.text_input("Tłumaczenie PL")
            
            if st.form_submit_button("Zapisz w K-Blocku"):
                if f_title and f_timed:
                    try:
                        data_obj = {
                            "title": f_title, "audio_url": f_audio, 
                            "lyrics_timed": f_timed, "translation_pl": f_pl,
                            "lyrics": f_timed
                        }
                        db.table("fan_chants").upsert(data_obj, on_conflict="title").execute()
                        st.success("Zapisano! Odświeżam listę...")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Błąd zapisu: {e}. Czy dodałeś UNIQUE w SQL?")
                else:
                    st.error("Tytuł i tekst są wymagane!")
