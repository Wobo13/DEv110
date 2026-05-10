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

# --- 1. KONFIGURACJA (V219 - Poprawione Mapowanie Czasu) ---
SUPABASE_URL = st.secrets.get("SUPABASE_URL", "")
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY", "")
API_KEY = st.secrets.get("OPENAI_API_KEY", "")

APP_VERSION = "V219 (Time Stats Fix)"
ADMIN_USER = "wobo"

# Słownik mapujący nazwy z menu (choice) na krótkie kody w bazie danych
CLEAN_TIME_LABELS = {
    "powtorki": "Pow", 
    "trening": "Trn", 
    "quiz": "Qiz", 
    "fiszki": "Fis",
    "testy": "Tst", 
    "memory": "Mem",          # <--- DODANO
    "warsztat": "War",        # <--- DODANO
    "arena wyzwan": "Arn",    # <--- DODANO
    "skaner": "Skn", 
    "generator": "Gen", 
    "dodaj": "Dod",
    "slownik": "Słn", 
    "statystyki": "Sta", 
    "konto": "Kon", 
    "admin": "Adm"
}

# --- 2. SILNIK BAZY I POMOCNIKI (V220 - Multilang Audio & AI) ---
def get_db():
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    return SyncPostgrestClient(f"{SUPABASE_URL}/rest/v1", headers=headers)

def hash_pw(pw): 
    return hashlib.sha256(str.encode(pw)).hexdigest()

def normalize_text(t):
    if not t: return ""
    return str(t).lower().strip().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")

def get_openai_response(prompt_text, img_obj=None):
    if not API_KEY: raise Exception("Brak klucza API OpenAI.")
    client = OpenAI(api_key=API_KEY)
    
    # Dynamiczny system prompt - AI będzie wiedziało o jaki język chodzi z treści promptu użytkownika
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
    Odtwarza wymowę słowa i opcjonalnego przykładu.
    lang: 'de' dla niemieckiego, 'cs' dla czeskiego, 'en' dla angielskiego itd.
    """
    try:
        # Konstruujemy pełny tekst do przeczytania (z pauzą między słowem a przykładem)
        full_text = f"{txt}. . . . {ex_txt}" if ex_txt else txt
        
        f = BytesIO()
        # gTTS używa teraz dynamicznego kodu języka
        tts = gTTS(text=full_text, lang=lang)
        tts.write_to_fp(f)
        f.seek(0)
        
        # Odtwarzanie w Streamlit
        st.audio(f, format="audio/mp3", autoplay=True)
    except Exception as e:
        # Ciche pominięcie błędu audio, aby nie przerywać nauki
        pass

# --- KONIEC SEKCJI 2 ---

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

# --- 5. LOGOWANIE I ŁADOWANIE DANYCH (V251 - Fix NameError 'u') ---

# Najpierw sprawdzamy, czy użytkownik jest w sesji
if "user" in st.session_state:
    u = st.session_state.user  # <--- DEFINIUJEMY 'u' TUTAJ, ABY SIDEBAR GO WIDZIAŁ
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

            # Migracja starych rekordów do wersji _de (jeśli istnieją stare klucze)
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
        # Usuwamy id, created_at i inne pola, których Supabase nie pozwoli nadpisać
        clean_data = {k: v for k, v in data.items() if k not in ["id", "created_at", "username", "last_ts"]}
        get_db().table("user_data").update(clean_data).eq("username", username).execute()
    except Exception as e:
        st.error(f"Błąd zapisu danych: {e}")

def update_activity(current_choice):
    """Nalicza czas nauki i zapisuje postęp."""
    if "user_data" not in st.session_state or not st.session_state.user_data or not u:
        return

    now = time.time()
    # Inicjalizacja last_ts, jeśli nie istnieje
    if "last_ts_activity" not in st.session_state:
        st.session_state.last_ts_activity = now
        return

    delta = now - st.session_state.last_ts_activity
    
    # Tylko jeśli aktywność trwała krócej niż 10 min (zapobiega błędnym naliczeniom przy otwartej karcie)
    if 0 < delta < 600:
        # Mapowanie nazw menu na kody (Poprawione o Memory i Balony)
        mapping = {
            "powtorki": "Pow", "trening": "Trn", "quiz": "Qiz", "fiszki": "Fis",
            "testy": "Tst", "memory": "Mem", "warsztat": "War", "konstruktor": "Kon",
            "wąż": "Wan", "wyścig": "Bal", "statystyki": "Sta"
        }
        
        # Oczyszczamy wybór menu, aby dopasować do klucza
        clean_choice = "".join(filter(str.isalpha, current_choice.lower()))
        label = "Inn"
        for k, v in mapping.items():
            if k in clean_choice:
                label = v
                break
        
        ud = st.session_state.user_data
        stats = dict(ud.get("time_stats", {}))
        stats[label] = stats.get(label, 0.0) + delta
        st.session_state.user_data["time_stats"] = stats
        
        # Zapisujemy postęp
        save_user_data(u, st.session_state.user_data)

    st.session_state.last_ts_activity = now

# --- START SESJI ---
if u and "user_data" not in st.session_state:
    st.session_state.user_data = load_user_data(u)
    if "flashcards" not in st.session_state:
        st.session_state.flashcards = load_flashcards(u)

# --- 6. SIDEBAR (V310 - Fix Menu Navigation Reset) ---
with st.sidebar:
    # 1. Inicjalizacja i Wybór Języka
    if "current_lang" not in st.session_state:
        st.session_state.current_lang = "Niemiecki"

    LANG_MAP = {
        "Niemiecki": {"code": "de", "label": "🇩🇪 Niemiecki", "emoji": "🚀"},
        "Czeski": {"code": "cs", "label": "🇨🇿 Czeski", "emoji": "🦁"}
    }

    # Nagłówek użytkownika
    user_display = str(u).capitalize()
    ud = st.session_state.user_data
    streak = ud.get('streak', 0)
    
    st.markdown(f"""
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 5px;">
            <h2 style="margin:0;">👤 {user_display}</h2>
            <span style="font-size: 1.2em;">🔥 {streak}d</span>
        </div>
    """, unsafe_allow_html=True)

    st.write("---")

    # Selektor języka
    selected_lang_name = st.selectbox(
        "Język nauki:", 
        options=list(LANG_MAP.keys()),
        format_func=lambda x: LANG_MAP[x]["label"],
        key="lang_selector"
    )

    # --- KLUCZOWA ZMIANA: Logika resetu menu ---
    # Jeśli język się zmienił, ustawiamy flagę resetu menu
    menu_index = 0 # Domyślnie Start
    if selected_lang_name != st.session_state.current_lang:
        st.session_state.current_lang = selected_lang_name
        st.session_state.force_start_page = True # Flaga wymuszająca powrót do startu
        st.rerun()

    # Sprawdzamy czy musimy zresetować pozycję menu
    if st.session_state.get("force_start_page", False):
        menu_index = 0
        # Usuwamy flagę po jednorazowym użyciu
        del st.session_state.force_start_page
    else:
        # Jeśli nie ma resetu, próbujemy odczytać gdzie był użytkownik (opcjonalne)
        # Ale najprościej pozwolić radio działać naturalnie
        menu_index = None 

    # Pobieramy kody języka
    L_CODE = LANG_MAP[st.session_state.current_lang]["code"]

    st.write("---")

    # 2. Filtrowanie i paski postępu (Wiedza/Cel)
    all_c = [c for c in st.session_state.flashcards if c.get("lang", "de") == L_CODE]
    
    wiedza_perc = 0
    if all_c:
        today_dt = date.today()
        strong = len([c for c in all_c if (pd.to_datetime(c.get('next_review', today_dt)).date() - today_dt).days > 6])
        wiedza_perc = int((strong / len(all_c)) * 100)
    
    study_modules = ["Pow", "Trn", "Qiz", "Fis", "Tst", "Mem", "War", "Kon", "Wan", "Bal"]
    current_stats = ud.get("time_stats", {})
    study_minutes = int(sum(current_stats.get(code, 0) for code in study_modules) // 60)
    daily_goal = ud.get("settings", {}).get("daily_goal", 20)
    
    st.caption(f"🧠 Wiedza ({st.session_state.current_lang}): {wiedza_perc}%")
    st.progress(min(wiedza_perc / 100, 1.0))
    st.caption(f"🎯 Cel dnia: {study_minutes}/{daily_goal}m")
    st.progress(min(study_minutes / daily_goal, 1.0))
    
    st.markdown("<hr style='margin: 10px 0;'>", unsafe_allow_html=True)

    # 6. MENU NAWIGACYJNE z wymuszonym indeksem
    menu_options = [
        "🏠 Start", "📅 Powtórki", "🚀 Trening", "🕹️ Quiz", "🎴 Fiszki", 
        "📝 Testy", "🧠 Memory", "🛠️ Warsztat", "🏗️ Konstruktor", 
        "🐍 Lingwistyczny Wąż", "🎈 Balonowy Wyścig", "🏆 Arena Wyzwań",
        "📦 Generator słów", "📸 Skaner AI", "➕ Dodaj", "📖 Słownik", 
        "📊 Statystyki", "⚙️ Moje Konto"
    ]
    
    if u == ADMIN_USER:
        menu_options.append("👑 Admin")

    # Używamy parametru 'index', aby sterować podświetleniem menu
    choice = st.radio(
        "Menu", 
        menu_options, 
        index=menu_index, # <--- To wymusza podświetlenie na "Start" (index 0) po zmianie języka
        label_visibility="collapsed"
    )
    
    st.markdown("<hr style='margin: 10px 0;'>", unsafe_allow_html=True)
    
    if st.button("🚪 Wyloguj się", use_container_width=True):
        st.session_state.clear()
        st.query_params.clear()
        st.rerun()

    st.caption(f"{APP_VERSION}")

# --- 7. START (V1.3 - Dashboard z synchronizacją celu) ---
update_activity(choice)

if choice == "🏠 Start":
    st.header(f"Guten Morgen, {str(u).capitalize()}! ☀️")
    
    # 1. ANALIZA DANYCH BIEŻĄCYCH
    all_c = st.session_state.flashcards
    ud = st.session_state.user_data
    today_str = str(date.today())
    
    # --- SYNCHRONIZACJA CZASU NA DASHBOARDZIE ---
    # Pobieramy statystyki czasu (które po poprawkach w Sekcji 3 powinny być czyste)
    current_stats = ud.get("time_stats", {})
    study_modules = ["Pow", "Trn", "Qiz", "Fis", "Tst", "Mem", "War", "Kon", "Wan", "Bal"]
    study_seconds = sum(current_stats.get(code, 0) for code in study_modules)
    study_minutes = int(study_seconds // 60)
    daily_goal = ud.get("settings", {}).get("daily_goal", 20)

    # Statystyki słówek
    total_words = len(all_c)
    to_review = len([c for c in all_c if str(c.get("next_review", today_str)) <= today_str])
    
    # 2. UKŁAD KAFELKÓW (WIZUALNE PODSUMOWANIE)
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("Słówek w bazie", total_words)
    with col2:
        # Pokazuje ile słówek do powtórki
        st.metric("Powtórki na dziś", to_review, delta=-to_review if to_review > 0 else "Gotowe!", delta_color="inverse")
    with col3:
        # TUTAJ: Pokazuje czas z dzisiaj (study_minutes) zamiast stałej wartości celu
        st.metric("Dzisiejsza nauka", f"{study_minutes} / {daily_goal} m")

    st.write("---")

    # 3. BRIEFING I ZADANIA
    c1, c2 = st.columns(2)
    
    with c1:
        st.markdown("### 📊 Twój status")
        if study_minutes >= daily_goal:
            st.success(f"🌟 Cel dzienny osiągnięty! ({study_minutes} min)")
        elif study_minutes > 0:
            st.info(f"📈 Jesteś w trakcie nauki. Jeszcze {daily_goal - study_minutes} min do celu.")
        else:
            st.warning("🆕 Zaczynamy! Wybierz moduł z menu, aby nabić dzisiejsze minuty.")

        if to_review > 0:
            st.error(f"⚠️ Masz {to_review} słówek do powtórzenia!")

    with c2:
        st.markdown("### 🏆 Zadania na dziś")
        # Dynamiczne sprawdzanie zadań
        t_done = "✅" if study_minutes >= daily_goal else "❌"
        st.write(f"{t_done} Osiągnij cel czasowy (**{daily_goal} min**)")
        st.write("✅ Przejrzyj sekcję **Warsztat**")
        st.write("✅ Wykonaj min. jeden **Quiz** lub **Test**")

    st.divider()

    # 4. SEKRETY I OSTATNIE SŁÓWKA
    col_q, col_w = st.columns([2, 1])
    
    with col_q:
        quotes = [
            "„Die Grenzen meiner Sprache bedeuten die Grenzen meiner Welt.” – Ludwig Wittgenstein",
            "„Każdy nowy język jest jak otwarte okno.”",
            "„Übung macht den Meister!” – Praktyka czyni mistrza."
        ]
        st.info(random.choice(quotes))
        
        # PRZYCISK RATUNKOWY (Tylko jeśli dane są ewidentnie błędne)
        if study_minutes > 500: # Jeśli system zwariuje i pokaże np. 8 godzin nauki w sekundę
            if st.button("🔄 Resetuj błędny licznik czasu"):
                st.session_state.user_data["time_stats"] = {}
                save_user_data(u, st.session_state.user_data)
                st.rerun()

    with col_w:
        with st.expander("🆕 Ostatnio dodane", expanded=True):
            if all_c:
                recent = all_c[-3:]
                for r in reversed(recent):
                    st.write(f"**{r['de']}**")
            else:
                st.write("Baza jest pusta.")

# --- 8. POWTÓRKI & TRENING (V259 - Inteligentne synonimy) ---
elif choice in ["📅 Powtórki", "🚀 Trening"]:
    is_r = (choice == "📅 Powtórki")
    st.header(choice)
    
    pfx = "rep" if is_r else "trn"
    user_settings = st.session_state.user_data.get("settings", {})
    auto_audio = user_settings.get("auto_audio", True)
    
    all_tags = set()
    for c in st.session_state.flashcards:
        all_tags.update([t.strip() for t in str(c.get('category','')).split(',') if t.strip()])
    
    sel_tag = st.selectbox("Zakres nauki:", ["Wszystkie"] + sorted(list(all_tags)), key=f"{pfx}_tag_sel")

    if f"{pfx}_list" not in st.session_state or st.session_state.get(f"{pfx}_last_tag") != sel_tag:
        pool = [c for c in st.session_state.flashcards if (sel_tag == "Wszystkie" or sel_tag in str(c.get('category','')))]
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
        st.success("Brak słówek w tej sekcji! ✨")
    elif st.session_state[f"{pfx}_idx"] >= len(cards):
        st.balloons()
        st.success("Sesja zakończona! 🏆")
        if st.button("Zacznij od nowa", key=f"{pfx}_restart_btn"):
            for k in [f"{pfx}_list", f"{pfx}_idx", f"{pfx}_mode", f"{pfx}_user_ans", f"{pfx}_dir"]:
                if k in st.session_state: del st.session_state[k]
            st.rerun()
    else:
        @st.fragment
        def flashcard_engine():
            idx = st.session_state[f"{pfx}_idx"]
            if idx >= len(cards):
                st.rerun()
                return
            c = cards[idx]
            
            if f"{pfx}_dir" not in st.session_state:
                st.session_state[f"{pfx}_dir"] = random.choice([0, 1])

            st.progress(idx / len(cards))
            st.caption(f"Słówko {idx + 1} z {len(cards)}")

            is_target_de = (st.session_state[f"{pfx}_dir"] == 1)
            display_word = c["de"] if not is_target_de else c["pl"]
            target_lang = "Polski" if not is_target_de else "Niemiecki"
            correct_val = c["pl"] if not is_target_de else c["de"]

            st.markdown(f'''
                <div style="font-size:2.6em; text-align:center; padding:40px; 
                background: #111; border:3px solid {"#4CAF50" if is_r else "#FF9800"}; 
                border-radius:20px; margin-bottom:10px; color: white; line-height: 1.2;">
                    <div style="font-size:0.35em; color:gray; margin-bottom:5px; text-transform: uppercase;">
                        Tłumaczysz na: {target_lang}
                    </div>
                    {display_word}
                </div>
            ''', unsafe_allow_html=True)

            if st.session_state[f"{pfx}_mode"] == "ask":
                with st.form(key=f"{pfx}_f_{idx}", clear_on_submit=True):
                    u_in = st.text_input(f"Odpowiedź ({target_lang}):", key=f"{pfx}_in_{idx}")
                    if st.form_submit_button("Sprawdź", use_container_width=True, type="primary"):
                        st.session_state[f"{pfx}_user_ans"] = u_in
                        st.session_state[f"{pfx}_mode"] = "res"
                        st.rerun(scope="fragment")
            else:
                # --- NOWA LOGIKA SPRAWDZANIA SYNONIMÓW ---
                def clean_text(text, is_german):
                    t = normalize_text(text)
                    if is_german:
                        t = re.sub(r'^(der|die|das)\s+', '', t)
                    return t.strip()

                user_ans = clean_text(st.session_state.get(f"{pfx}_user_ans", ""), is_target_de)
                
                # Rozbijamy poprawną odpowiedź na listę synonimów
                # Dzielimy po: / lub , lub ;
                correct_synonyms = re.split(r'[/,;]', correct_val)
                correct_synonyms = [clean_text(s, is_target_de) for s in correct_synonyms if s.strip()]
                
                # Sprawdzamy czy odpowiedź użytkownika jest w liście synonimów
                is_correct = user_ans in correct_synonyms
                
                if is_correct:
                    st.success(f"✅ Dobrze! Poprawne znaczenia: {correct_val}")
                else:
                    st.error(f"❌ Niepoprawnie. Poprawne znaczenia: {correct_val}")
                
                exs = c.get("examples", [])
                fex = exs[0].get("de") if exs and isinstance(exs, list) and len(exs) > 0 else None
                if auto_audio: play_audio(c['de'], fex)
                if fex: st.info(f"💡 Przykład: **{fex}**\n\n({exs[0].get('pl','')})")

                st.divider()
                if is_r:
                    st.write("Oceń trudność:")
                    col1, col2, col3 = st.columns(3)
                    d = None
                    if col1.button("🔴 Trudne"): d = 1
                    if col2.button("🟡 Średnie"): d = 4
                    if col3.button("🟢 Łatwe"): d = 10
                    if d:
                        update_word(c['id'], {"next_review": str(date.today() + timedelta(days=d))})
                        st.session_state[f"{pfx}_idx"] += 1
                        st.session_state[f"{pfx}_mode"] = "ask"
                        if f"{pfx}_dir" in st.session_state: del st.session_state[f"{pfx}_dir"]
                        st.rerun() if st.session_state[f"{pfx}_idx"] >= len(cards) else st.rerun(scope="fragment")
                else:
                    if st.button("Następne słówko ➡️", use_container_width=True, type="primary"):
                        st.session_state[f"{pfx}_idx"] += 1
                        st.session_state[f"{pfx}_mode"] = "ask"
                        if f"{pfx}_dir" in st.session_state: del st.session_state[f"{pfx}_dir"]
                        st.rerun() if st.session_state[f"{pfx}_idx"] >= len(cards) else st.rerun(scope="fragment")

        flashcard_engine()

# --- 9. QUIZ (V240 - Obsługa Wielu Języków DE/CS) ---
elif choice == "🕹️ Quiz":
    # Dynamiczny tytuł z flagą i nazwą języka
    st.header(f"🕹️ Quiz: {st.session_state.current_lang}")
    
    # 1. FILTROWANIE SŁÓWEK (Tylko dla wybranego języka)
    # L_CODE pochodzi z Sidebaru (Sekcja 6)
    all_c_full = st.session_state.flashcards
    all_c = [c for c in all_c_full if c.get("lang", "de") == L_CODE]
    
    ud = st.session_state.user_data
    user_settings = ud.get("settings", {})
    show_hints = user_settings.get("show_hints", True)
    auto_audio = user_settings.get("auto_audio", True)
    
    if len(all_c) < 4: 
        st.warning(f"Dodaj min. 4 słówka w języku {st.session_state.current_lang}, aby uruchomić quiz.")
    else:
        @st.fragment
        def quiz_engine():
            # 1. INICJALIZACJA PYTANIA
            if "q_c" not in st.session_state:
                idx = random.randrange(len(all_c))
                t = all_c[idx]
                
                # Szukamy dystraktorów (błędnych odpowiedzi) tylko w obrębie tego samego języka
                other_pls = [x['pl'] for x in all_c if x['pl'] != t['pl']]
                distractors = random.sample(other_pls, min(3, len(other_pls)))
                
                opts = distractors + [t['pl']]
                random.shuffle(opts)
                
                st.session_state.q_c = t
                st.session_state.q_a = t['pl']
                st.session_state.q_o = opts
                st.session_state.q_s = "ask"
                st.session_state.u_q = None
                st.session_state.q_key_seed = random.randint(1000, 9999)

            if "q_key_seed" not in st.session_state:
                st.session_state.q_key_seed = random.randint(1000, 9999)

            q_c = st.session_state.q_c
            
            # Dynamiczne pytanie
            st.write(f"### Jak przetłumaczysz: **{q_c['de']}**")
            
            if st.session_state.q_s == "ask":
                if show_hints:
                    first_letter = st.session_state.q_a[0].upper()
                    st.caption(f"💡 Podpowiedź: Polskie słowo zaczyna się na literę **{first_letter}**...")

                current_seed = st.session_state.q_key_seed
                for i, o in enumerate(st.session_state.q_o):
                    if st.button(o, key=f"qbtn_{current_seed}_{i}", use_container_width=True):
                        st.session_state.u_q = o
                        st.session_state.q_s = "res"
                        st.rerun(scope="fragment")
            else:
                # 4. WYNIK I LOGIKA SRS
                is_correct = st.session_state.u_q == st.session_state.q_a
                word_id = q_c.get('id')
                
                if is_correct:
                    st.success("✅ Świetnie! (Słówko przesunięte o +2 dni)")
                    new_date = str(date.today() + timedelta(days=2))
                    update_word(word_id, {"next_review": new_date})
                else:
                    st.error(f"❌ Poprawnie: **{st.session_state.q_a}**")
                    payload = {"next_review": str(date.today())}
                    if 'level' in q_c:
                        payload["level"] = 0
                    update_word(word_id, payload)
                
                # Przeładowanie słówek, aby odświeżyć daty powtórek w sesji
                st.session_state.flashcards = load_flashcards(u)

                # --- OBSŁUGA AUDIO (Zmieniony L_CODE) ---
                exs = q_c.get("examples", [])
                fex_foreign = exs[0].get("de") if exs and isinstance(exs, list) and len(exs) > 0 else None
                fex_pl = exs[0].get("pl") if fex_foreign else None
                
                if fex_foreign:
                    st.info(f"💡 Przykład: **{fex_foreign}**" + (f"\n\n🇵🇱 *{fex_pl}*" if show_hints and fex_pl else ""))
                    if auto_audio: 
                        # Używamy L_CODE (np. 'de' lub 'cs'), aby lektor miał poprawny akcent
                        play_audio(q_c['de'], fex_foreign, lang=L_CODE)
                else:
                    if auto_audio: 
                        play_audio(q_c['de'], lang=L_CODE)
                
                if st.button("Następne pytanie ➡️", use_container_width=True, type="primary"):
                    for key in ["q_c", "q_a", "q_o", "q_s", "u_q", "q_key_seed"]:
                        if key in st.session_state: del st.session_state[key]
                    st.rerun(scope="fragment")

        quiz_engine()
        
# --- 10. FISZKI (Wersja z obsługą Auto-Audio) ---
elif choice == "🎴 Fiszki":
    st.header("🎴 Fiszki")
    
    # 1. Pobieranie ustawienia z bazy
    user_settings = st.session_state.user_data.get("settings", {})
    auto_audio = user_settings.get("auto_audio", True)
    
    # Inicjalizacja stanu
    if "f_idx" not in st.session_state: st.session_state.f_idx = 0
    if "f_flipped" not in st.session_state: st.session_state.f_flipped = False
    
    # Pobieranie tagów do filtra
    all_tags = set()
    for c in st.session_state.flashcards:
        all_tags.update([t.strip() for t in str(c.get('category','')).split(',') if t.strip()])
    
    sel_tag = st.selectbox("Zakres:", ["Wszystkie"] + sorted(list(all_tags)), key="f_tag_sel")
    cards = [c for c in st.session_state.flashcards if sel_tag == "Wszystkie" or sel_tag in str(c.get('category',''))]

    if not cards:
        st.warning("Brak słówek w wybranej kategorii.")
    else:
        # Silnik Fiszek jako izolowany fragment
        @st.fragment
        def flashcards_ui():
            # Zabezpieczenie indeksu
            if st.session_state.f_idx >= len(cards): st.session_state.f_idx = 0
            if st.session_state.f_idx < 0: st.session_state.f_idx = len(cards) - 1
            
            c = cards[st.session_state.f_idx]
            txt = c["pl"] if st.session_state.f_flipped else c["de"]
            color = "#2E7D32" if st.session_state.f_flipped else "#C62828"
            label = "POLSKI" if st.session_state.f_flipped else "DEUTSCH"

            # Renderowanie graficzne karty (HTML)
            st.markdown(f"""
                <div style="min-height:300px; display:flex; flex-direction:column; align-items:center; justify-content:center; 
                background:#111; border:5px solid {color}; border-radius:40px; color:white; text-align:center; padding:30px; 
                box-shadow: 0 10px 30px rgba(0,0,0,0.5); margin-bottom: 20px;">
                    <div style="color:{color}; font-weight:bold; letter-spacing:3px; margin-bottom:15px; font-size:0.9em;">{label}</div>
                    <div style="font-size:3.5em; font-weight:700; line-height:1.1; margin-bottom:10px;">{txt}</div>
                </div>
            """, unsafe_allow_html=True)

            # Obsługa przykładów i dźwięku (widoczne po obróceniu)
            if st.session_state.f_flipped:
                exs = c.get("examples", [])
                fex = exs[0].get("de") if exs and isinstance(exs, list) and len(exs) > 0 else None
                
                if fex:
                    st.info(f"🇩🇪 **{fex}**\n\n🇵🇱 {exs[0].get('pl','')}")
                    
                    # Logika Auto-Audio dla słówka i przykładu
                    if auto_audio:
                        play_audio(c['de'], fex)
                else:
                    # Logika Auto-Audio tylko dla słówka
                    if auto_audio:
                        play_audio(c['de'])

                # Manualny przycisk dźwięku, jeśli Auto-Audio jest na OFF
                if not auto_audio:
                    if st.button("🔊 Odsłuchaj wymowę", use_container_width=True):
                        if fex:
                            play_audio(c['de'], fex)
                        else:
                            play_audio(c['de'])
            
            # Nawigacja - używamy st.rerun(scope="fragment") dla maksymalnej płynności
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

        # Uruchomienie interfejsu
        flashcards_ui()

# --- 11. TESTY (V295 - Pełne podsumowanie odpowiedzi) ---
elif choice == "📝 Testy":
    st.header("📝 Test")
    
    if len(st.session_state.flashcards) < 5:
        st.warning("Dodaj min. 5 słówek, aby wygenerować test.")
    else:
        if "test_q" not in st.session_state:
            n_q = st.slider("Liczba pytań", 5, 20, 5)
            if st.button("🚀 GENERUJ TEST", use_container_width=True, type="primary"):
                with st.spinner("AI przygotowuje zadania..."):
                    try:
                        sample = random.sample(st.session_state.flashcards, n_q)
                        prompt = f"Generuj test dla: {[w['de'] for w in sample]}. JSON: {{ \"questions\": [{{ \"hint\":\"PL context\", \"sentence\":\"German sentence with target word replaced by _______\", \"correct\":\"DE word\", \"distractors\":[\"...\"], \"type\":\"QUIZ\" }}] }}"
                        data = json.loads(get_openai_response(prompt))
                        st.session_state.test_q = data["questions"]
                        st.session_state.test_idx = 0
                        st.session_state.test_score = 0
                        st.rerun()
                    except Exception as e:
                        st.error(f"Błąd AI: {e}. Spróbuj ponownie.")
        
        else:
            @st.fragment
            def test_engine():
                qs = st.session_state.test_q
                t_idx = st.session_state.test_idx
                
                if t_idx < len(qs):
                    q = qs[t_idx]
                    st.progress(t_idx / len(qs))
                    st.caption(f"Pytanie {t_idx + 1} z {len(qs)}")
                    
                    st.info(f"💡 Podpowiedź (PL): {q.get('hint','brak')}")
                    st.markdown(f"### {q.get('sentence','?')}")
                    
                    correct = str(q.get('correct',''))
                    
                    if q.get('type') == "QUIZ":
                        opts = list(set(q.get('distractors', []) + [correct]))
                        random.shuffle(opts)
                        cols = st.columns(2)
                        for i, o in enumerate(opts):
                            if cols[i%2].button(o, key=f"t_btn_{t_idx}_{o}", use_container_width=True):
                                st.session_state.test_q[t_idx]['user_ans'] = o
                                if o == correct:
                                    st.session_state.test_score += 1
                                    st.toast("Dobrze! ✅")
                                else:
                                    st.toast("Źle ❌")
                                st.session_state.test_idx += 1
                                st.rerun(scope="fragment")
                    else:
                        with st.form(key=f"test_form_{t_idx}", clear_on_submit=True):
                            ans = st.text_input("Twoja odpowiedź:")
                            if st.form_submit_button("Zatwierdź"):
                                st.session_state.test_q[t_idx]['user_ans'] = ans
                                if normalize_text(ans) == normalize_text(correct):
                                    st.session_state.test_score += 1
                                    st.toast("Dobrze! ✅")
                                else:
                                    st.toast("Źle ❌")
                                st.session_state.test_idx += 1
                                st.rerun(scope="fragment")
                
                else:
                    # --- PANEL PODSUMOWANIA ---
                    score, total = st.session_state.test_score, len(qs)
                    perc = round((score/total)*100) if total > 0 else 0
                    
                    st.markdown(f'''
                        <div style="text-align:center; padding:30px; border-radius:20px; 
                        background:#111; border:3px solid #1E88E5; margin-bottom:20px;">
                            <h1 style="margin:0; color:white;">Wynik: {score}/{total}</h1>
                            <h2 style="color:#1E88E5; margin:0;">{perc}%</h2>
                        </div>
                    ''', unsafe_allow_html=True)
                    
                    # --- KLUCZOWA ZMIANA: Zawsze pokazuj odpowiedzi ---
                    with st.expander("📝 Zobacz szczegóły odpowiedzi", expanded=True):
                        for i, q_res in enumerate(qs):
                            u_a = q_res.get('user_ans', 'Brak')
                            c_a = q_res.get('correct', '')
                            is_ok = normalize_text(u_a) == normalize_text(c_a)
                            
                            icon = "✅" if is_ok else "❌"
                            color = "#4CAF50" if is_ok else "#FF5252"
                            
                            st.markdown(f"**{i+1}.** {q_res.get('sentence')}")
                            # Wyświetlanie obu odpowiedzi w jednej linii z kolorowaniem
                            st.markdown(f"""
                                <div style="margin-left: 25px; margin-bottom: 15px; font-size: 0.9em;">
                                    {icon} Twoja: <span style="color:{color}; font-weight:bold;">{u_a}</span><br>
                                    🎯 Poprawna: <span style="color:#1E88E5; font-weight:bold;">{c_a}</span>
                                </div>
                            """, unsafe_allow_html=True)

                    if st.button("Zakończ i zapisz do statystyk", use_container_width=True, type="primary"):
                        st.session_state.user_data["test_history"].append({
                            "date": datetime.now().strftime("%d.%m %H:%M"), 
                            "score": score, "total": total, "perc": perc
                        })
                        save_user_data(u, st.session_state.user_data)
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
                
# --- 13. WARSZTAT SŁÓWEK (ANALIZA BŁĘDÓW - ULTRA FAST) ---
elif choice == "🛠️ Warsztat":
    st.header("🛠️ Warsztat Słówek")
    st.write("Tu trafiają słówka, które sprawiają Ci najwięcej trudności. Opanuj je raz a dobrze!")

    # 1. IDENTYFIKACJA "TRUDNYCH" SŁÓWEK
    if "w_list" not in st.session_state:
        # Filtrujemy słówka: te z level < 2 lub interval < 2 (najświeższe błędy)
        hard_cards = [
            c for c in st.session_state.flashcards 
            if c.get("level", 0) < 2 or c.get("interval", 0) < 2
        ]
        
        # Jeśli nie ma "bardzo trudnych", weźmy te z najniższym levelem ogólnie
        if len(hard_cards) < 5:
            hard_cards = sorted(st.session_state.flashcards, key=lambda x: x.get("level", 0))[:10]

        random.shuffle(hard_cards)
        st.session_state.w_list = hard_cards[:15] # Sesja max 15 "koszmarów"
        st.session_state.w_idx = 0
        st.session_state.w_show = False

    if not st.session_state.w_list:
        st.success("Twoja lista trudnych słówek jest pusta! Wygląda na to, że wszystko świetnie pamiętasz. ✨")
    
    elif st.session_state.w_idx >= len(st.session_state.w_list):
        st.balloons()
        st.success("Warsztat zakończony! Te słówka nie powinny Cię już straszyć.")
        if st.button("Zacznij od nowa", use_container_width=True):
            del st.session_state.w_list
            st.rerun()
    else:
        # --- SILNIK WARSZTATU (FRAGMENT) ---
        @st.fragment
        def workshop_engine():
            # Musimy pobrać aktualne dane ze stanu sesji wewnątrz fragmentu
            idx = st.session_state.w_idx
            w_list = st.session_state.w_list
            curr = w_list[idx]
            
            # Pasek postępu
            progress = (idx) / len(w_list)
            st.progress(progress)
            st.caption(f"Słówko {idx + 1} z {len(w_list)}")

            # Karta Warsztatowa
            with st.container(border=True):
                st.markdown(f"<h1 style='text-align: center; margin-bottom: 20px;'>{curr['de']}</h1>", unsafe_allow_html=True)
                
                if st.session_state.w_show:
                    st.markdown(f"<h3 style='text-align: center; color: #FF5252; margin-top: -10px;'>{curr['pl']}</h3>", unsafe_allow_html=True)
                    if curr.get('example'):
                        st.info(f"💡 Przykład: {curr['example']}")
                    # Automatyczne audio jeśli jest włączone w ustawieniach
                    user_settings = st.session_state.user_data.get("settings", {})
                    if user_settings.get("auto_audio", True):
                        play_audio(curr['de'], curr.get('example'))
                
                st.write("")
                if not st.session_state.w_show:
                    if st.button("👁️ Pokaż odpowiedź", use_container_width=True, type="primary"):
                        st.session_state.w_show = True
                        st.rerun(scope="fragment")
                else:
                    col_a, col_b = st.columns(2)
                    if col_a.button("❌ Nadal trudne", use_container_width=True):
                        # Przesuwamy na koniec listy
                        card = st.session_state.w_list.pop(st.session_state.w_idx)
                        st.session_state.w_list.append(card)
                        st.session_state.w_show = False
                        st.rerun(scope="fragment")
                    
                    if col_b.button("✅ Już rozumiem", use_container_width=True):
                        st.session_state.w_idx += 1
                        st.session_state.w_show = False
                        st.rerun(scope="fragment")

        # Uruchomienie silnika
        workshop_engine()

    # Przycisk resetu (poza fragmentem dla pełnego odświeżenia bazy słówek do warsztatu)
    if st.button("Wygeneruj nową listę warsztatową", type="secondary", use_container_width=True):
        for k in ["w_list", "w_idx", "w_show"]:
            if k in st.session_state: del st.session_state[k]
        st.rerun()

    # Statystyki warsztatu w sidebarze
    st.sidebar.divider()
    st.sidebar.write(f"🔧 W warsztacie: **{len(st.session_state.w_list)}** słówek")

# --- 14. KONSTRUKTOR (V1.4 - Poprawiona logika resetu i bezpiecznika) ---
elif choice == "🏗️ Konstruktor":
    st.header("🏗️ Konstruktor Słów")
    st.write("Ułóż niemieckie słowo lub frazę. Pamiętaj o spacjach!")

    # Funkcja pomocnicza do czyszczenia stanu gry
    def reset_konstructor():
        for k in ["kon_word", "kon_pl", "kon_shuffled", "kon_user", "kon_done", "kon_seed"]:
            if k in st.session_state: 
                del st.session_state[k]

    # 1. INICJALIZACJA GRY
    if "kon_word" not in st.session_state:
        if len(st.session_state.flashcards) < 3:
            st.warning("Dodaj min. 3 słówka, aby uruchomić ten moduł.")
            st.stop()
        
        pool = [c for c in st.session_state.flashcards if len(c['de']) > 2]
        target = random.choice(pool if pool else st.session_state.flashcards)
        
        de_word = target['de'].strip()
        letters = [l for l in de_word]
        random.shuffle(letters)
        
        st.session_state.kon_word = de_word
        st.session_state.kon_pl = target['pl']
        st.session_state.kon_shuffled = letters
        st.session_state.kon_user = []
        st.session_state.kon_done = False
        st.session_state.kon_seed = random.randint(1000, 9999)

    # 2. SILNIK GRY (Fragment UI)
    @st.fragment
    def constructor_engine():
        # BEZPIECZNIK: Jeśli sesja wyparuje, pokazujemy tylko jeden, działający przycisk
        if "kon_word" not in st.session_state or "kon_seed" not in st.session_state:
            st.warning("Sesja gry wygasła lub została zresetowana.")
            if st.button("🚀 Kliknij tutaj, aby zacząć nową rundę", use_container_width=True):
                reset_konstructor()
                st.rerun()
            return

        kon_w = st.session_state.kon_word
        kon_pl = st.session_state.kon_pl
        shuffled = st.session_state.kon_shuffled
        user_build = st.session_state.kon_user
        k_seed = st.session_state.kon_seed
        
        st.info(f"### 🇵🇱 {kon_pl}")
        
        # Podgląd postępu
        current_str = "".join(user_build)
        remaining = len(kon_w) - len(user_build)
        display_str = current_str.replace(" ", "•") + "_" * remaining
        
        st.markdown(f"""
            <div style="font-size: 2.5em; text-align: center; letter-spacing: 5px; 
            padding: 20px; background: #0e1117; border: 2px dashed #444; border-radius: 10px; color: #00ff00; font-family: monospace;">
                {display_str}
            </div>
            <div style="text-align: center; font-size: 0.8em; color: gray; margin-top: 5px;">(• = spacja)</div>
        """, unsafe_allow_html=True)
        
        st.write("")

        # Cofanie ruchu
        if user_build and not st.session_state.kon_done:
            if st.button("⬅️ Cofnij ostatni znak", use_container_width=True, key=f"back_{k_seed}"):
                last_l = st.session_state.kon_user.pop()
                st.session_state.kon_shuffled.append(last_l)
                st.rerun(scope="fragment")

        # Kafelki z literami
        cols = st.columns(min(len(shuffled), 8) if shuffled else 1)
        for i, letter in enumerate(shuffled):
            label = "Spacja ␣" if letter == " " else letter
            if cols[i % 8].button(label, key=f"k_{k_seed}_{i}", use_container_width=True):
                st.session_state.kon_user.append(letter)
                st.session_state.kon_shuffled.pop(i)
                if len(st.session_state.kon_user) == len(kon_w):
                    st.session_state.kon_done = True
                st.rerun(scope="fragment")

        # Sprawdzanie wyniku
        if st.session_state.kon_done:
            final_guess = "".join(st.session_state.kon_user)
            if final_guess.lower() == kon_w.lower():
                st.balloons()
                st.success(f"🎊 Idealnie! To: **{kon_w}**")
            else:
                st.error(f"❌ Prawie! Poprawny zapis: **{kon_w}**")
            
            if st.button("Następne słowo 🏗️", use_container_width=True, type="primary", key=f"next_{k_seed}"):
                reset_konstructor()
                st.rerun()

    # Uruchomienie fragmentu
    constructor_engine()

    # Główny reset (zawsze widoczny pod grą)
    if st.button("Zmień słowo (Reset)", type="secondary", use_container_width=True, key="global_reset_kon"):
        reset_konstructor()
        st.rerun()

# --- 15. LINGWISTYCZNY WĄŻ (V1.2 - Tryb Rywalizacji) ---
elif choice == "🐍 Lingwistyczny Wąż":
    st.header("🐍 Lingwistyczny Wąż")
    st.write("Rywalizuj z systemem! Wygrywa ten, kto doda ostatnie możliwe słowo z Twojej bazy.")

    # 1. INICJALIZACJA GRY
    if "snake_chain" not in st.session_state:
        if len(st.session_state.flashcards) < 5:
            st.warning("Dodaj min. 5 słówek, aby móc zagrać.")
            st.stop()
        
        # Pierwsze słowo losuje system
        first_word = random.choice(st.session_state.flashcards)
        st.session_state.snake_chain = [first_word]
        st.session_state.snake_used_ids = {first_word['id']}
        st.session_state.snake_status = "player" # player / system / end
        st.session_state.snake_winner = None

    # 2. SILNIK GRY (FRAGMENT)
    @st.fragment
    def snake_engine():
        chain = st.session_state.snake_chain
        last_word_obj = chain[-1]
        
        # Pobieranie ostatniej litery (obsługa znaków specjalnych)
        def get_last_char(text):
            clean = re.sub(r'[^a-zäöüß]', '', text.lower().strip())
            return clean[-1] if clean else ""

        last_letter = get_last_char(last_word_obj['de'])

        # --- UI: Wyświetlanie łańcucha ---
        st.markdown("### Łańcuch:")
        # Wyświetlamy max 6 ostatnich słów w rzędzie
        display_chain = chain[-6:]
        cols = st.columns(len(display_chain))
        for i, word in enumerate(display_chain):
            with cols[i]:
                # Kolor: Gracz (zielony), System (niebieski)
                # Sprawdzamy parzystość od końca łańcucha
                is_system_word = (len(chain) - len(display_chain) + i) % 2 == 0
                color = "#1E88E5" if is_system_word else "#4CAF50"
                st.markdown(f"""
                    <div style="background:{color}; padding:10px; border-radius:10px; text-align:center; color:white; font-size:0.9em; min-height:80px; display:flex; flex-direction:column; justify-content:center;">
                        <div style="font-weight:bold;">{word['de']}</div>
                        <div style="font-size:0.7em; opacity:0.9;">{word['pl']}</div>
                    </div>
                """, unsafe_allow_html=True)
        
        st.divider()

        if st.session_state.snake_status != "end":
            st.info(f"Ostatnie słowo: **{last_word_obj['de']}**. Czekamy na słowo na literę: **{last_letter.upper()}**")

        # --- TRYB GRACZA ---
        if st.session_state.snake_status == "player":
            with st.form("snake_form", clear_on_submit=True):
                u_input = st.text_input("Twoja kolej (DE):").strip().lower()
                col_f1, col_f2 = st.columns([3, 1])
                submit = col_f1.form_submit_button("Dodaj ogniwo 🔗", use_container_width=True)
                give_up = col_f2.form_submit_button("🏳️ Poddaję się")

                if submit:
                    # Szukamy słowa w bazie (z uwzględnieniem rodzajników i normalizacji)
                    found = [c for c in st.session_state.flashcards 
                             if (normalize_text(c['de']) == normalize_text(u_input) or 
                                 normalize_text(re.sub(r'^(der|die|das)\s+', '', c['de'].lower())) == normalize_text(u_input))
                             and c['id'] not in st.session_state.snake_used_ids]
                    
                    if not found:
                        st.error("Nie masz tego słowa w bazie lub już zostało użyte!")
                    elif normalize_text(u_input)[0] != last_letter:
                        st.error(f"Słowo musi zaczynać się na literę '{last_letter.upper()}'!")
                    else:
                        st.session_state.snake_chain.append(found[0])
                        st.session_state.snake_used_ids.add(found[0]['id'])
                        st.session_state.snake_status = "system"
                        st.rerun(scope="fragment")
                
                if give_up:
                    st.session_state.snake_status = "end"
                    st.session_state.snake_winner = "System 🤖"
                    st.rerun(scope="fragment")

        # --- TRYB SYSTEMU ---
        elif st.session_state.snake_status == "system":
            with st.spinner("System myśli..."):
                time.sleep(1)
                # System szuka w Twojej bazie
                possible = [c for c in st.session_state.flashcards 
                            if get_last_char(c['de']).startswith(last_letter) # błąd logiczny w starym kodzie (startswith na literze) - poprawione:
                            and normalize_text(re.sub(r'^(der|die|das)\s+', '', c['de'].lower())).startswith(last_letter)
                            and c['id'] not in st.session_state.snake_used_ids]
                
                if possible:
                    bot_word = random.choice(possible)
                    st.session_state.snake_chain.append(bot_word)
                    st.session_state.snake_used_ids.add(bot_word['id'])
                    st.session_state.snake_status = "player"
                    st.rerun(scope="fragment")
                else:
                    st.session_state.snake_status = "end"
                    st.session_state.snake_winner = f"{u.capitalize()} 🏆"
                    st.balloons()
                    st.rerun(scope="fragment")

        # --- KONIEC GRY ---
        if st.session_state.snake_status == "end":
            st.success(f"### Koniec gry! Zwycięzca: {st.session_state.snake_winner}")
            if st.button("Zagraj jeszcze raz", use_container_width=True, type="primary"):
                for k in ["snake_chain", "snake_used_ids", "snake_status", "snake_winner"]:
                    if k in st.session_state: del st.session_state[k]
                st.rerun()

    snake_engine()

# --- 16. BALONOWY WYŚCIG (V3.0 - Ostateczne Rozwiązanie) ---
elif choice == "🎈 Balonowy Wyścig":
    st.header("🎈 Balonowy Wyścig")
    
    if "bal_active" not in st.session_state:
        st.session_state.update({
            "bal_active": False, "bal_score": 0, "bal_word": None,
            "bal_opts": [], "bal_start_ts": 0, "bal_game_over": False
        })

    def next_bal_round():
        all_c = st.session_state.flashcards
        if len(all_c) < 4: return False
        target = random.choice(all_c)
        others = random.sample([c['pl'] for c in list(all_c) if c['id'] != target['id']], 2)
        opts = others + [target['pl']]
        random.shuffle(opts)
        st.session_state.bal_word = target
        st.session_state.bal_opts = opts
        return True

    if st.session_state.get("bal_active", False):
        if time.time() - st.session_state.bal_start_ts >= 30:
            f_score = st.session_state.bal_score
            st.session_state.bal_active = False
            st.session_state.bal_game_over = True
            
            if f_score > 0:
                try:
                    db = get_db()
                    # Pobieramy świeże dane
                    curr = db.table("user_data").select("top_balloons").eq("username", u).execute()
                    # Wyciągamy listę rekordów
                    old_list = []
                    if curr.data and isinstance(curr.data[0].get("top_balloons"), list):
                        old_list = curr.data[0]["top_balloons"]
                    
                    # Tworzymy nową listę Top 10
                    new_list = sorted(list(set(old_list + [f_score])), reverse=True)[:10]
                    
                    # ZAPIS
                    db.table("user_data").update({"top_balloons": new_list}).eq("username", u).execute()
                    
                    # Synchronizacja sesji
                    st.session_state.user_data["top_balloons"] = new_list
                    st.toast(f"Zapisano: {f_score} pkt!")
                except Exception as e:
                    st.error(f"Błąd krytyczny zapisu: {e}")
            st.rerun()

    if not st.session_state.bal_active:
        if st.session_state.bal_game_over:
            st.balloons()
            st.success(f"### Wynik: {st.session_state.bal_score} pkt")
            # Wyświetlamy z nowej kolumny
            rec = st.session_state.user_data.get("top_balloons", [])
            if rec: st.info(f"Twoje rekordy: {', '.join(map(str, rec))}")
            
            if st.button("Zagraj jeszcze raz", use_container_width=True):
                st.session_state.update({"bal_score": 0, "bal_active": True, "bal_game_over": False, "bal_start_ts": time.time()})
                next_bal_round(); st.rerun()
        else:
            if st.button("🚀 START", use_container_width=True, type="primary"):
                if next_bal_round():
                    st.session_state.update({"bal_active": True, "bal_score": 0, "bal_start_ts": time.time()})
                    st.rerun()
    else:
        @st.fragment(run_every=1.0)
        def engine():
            rem = max(0, int(30 - (time.time() - st.session_state.bal_start_ts)))
            if rem <= 0:
                st.session_state.bal_active = False; st.session_state.bal_game_over = True; st.rerun()
            
            c1, c2 = st.columns(2)
            c1.metric("⏱️ Czas", f"{rem}s")
            c2.metric("⭐ Punkty", st.session_state.bal_score)
            
            if st.session_state.bal_word:
                st.markdown(f'<div style="text-align:center; padding:20px; background:#111; border:2px solid #FF4B4B; border-radius:15px; margin-bottom:15px;"><h2 style="color:white; margin:0;">{st.session_state.bal_word["de"]}</h2></div>', unsafe_allow_html=True)
                cols = st.columns(3)
                for i, o in enumerate(st.session_state.bal_opts):
                    if cols[i].button(o, key=f"b_{i}", use_container_width=True):
                        if o == st.session_state.bal_word['pl']:
                            st.session_state.bal_score += 1
                            next_bal_round(); st.rerun(scope="fragment")
                        else:
                            st.toast("Pudło!"); next_bal_round(); st.rerun(scope="fragment")
        engine()
            
# --- 20. ARENA WYZWAŃ (V304 - Przywrócony klasyczny wygląd) ---
elif choice == "🏆 Arena Wyzwań":
    st.header("🏆 Arena Wyzwań")
    st.write("Sprawdź, jak wypadasz na tle innych użytkowników!")

    db = get_db()
    
    # 1. BEZPIECZNE POBIERANIE DANYCH
    try:
        all_users_res = db.table("user_data").select("*").execute().data
        all_cards_res = db.table("flashcards").select("username", "next_review").execute().data
    except Exception as e:
        st.error(f"Błąd bazy danych: {e}")
        st.stop()

    if not all_users_res:
        st.info("Ranking jest obecnie pusty. Bądź pierwszym, który go zapełni!")
    else:
        df_users = pd.DataFrame(all_users_res)
        df_cards = pd.DataFrame(all_cards_res) if all_cards_res else pd.DataFrame(columns=["username", "next_review"])
        
        today = date.today()
        ranking_data = []

        # 2. OBLICZANIE STATYSTYK DLA KAŻDEGO UŻYTKOWNIKA
        for _, user in df_users.iterrows():
            uname = user.get("username", "Anonim")
            u_cards = df_cards[df_cards["username"] == uname]
            
            # Obliczanie wiedzy %
            wiedza_val = 0
            if not u_cards.empty:
                try:
                    strong = len([r for r in u_cards["next_review"] if (pd.to_datetime(r).date() - today).days > 6])
                    wiedza_val = int((strong / len(u_cards)) * 100)
                except:
                    wiedza_val = 0
            
            # Najlepsze Memory (najniższy czas)
            m_scores = user.get("memory_scores", [])
            best_mem = min([float(s) for s in m_scores]) if isinstance(m_scores, list) and m_scores else None

            # Najlepszy Balon (NOWA KOLUMNA top_balloons)
            b_scores = user.get("top_balloons", [])
            best_bal = max([int(s) for s in b_scores]) if isinstance(b_scores, list) and b_scores else 0

            # Najlepszy Wąż (najdłuższa seria)
            best_snake = user.get("snake_best_chain", 0)

            ranking_data.append({
                "Użytkownik": uname.capitalize(),
                "Ogień 🔥": user.get("streak", 0),
                "Wiedza 🧠": wiedza_val,
                "Najlepsze Memory ⏱️": best_mem,
                "Rekord Balony 🎈": best_bal,
                "Seria Węża 🐍": best_snake,
                "Ostatnio aktywny": user.get("last_seen", "Brak")
            })

        df_final = pd.DataFrame(ranking_data)

        # 3. WYŚWIETLANIE TABEL (Klasyczny układ: 2 kolumny)
        
        # --- Rząd 1: Passa i Wiedza ---
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("🔥 Najdłuższa Passa")
            top_streak = df_final.sort_values(by="Ogień 🔥", ascending=False).head(5).reset_index(drop=True)
            top_streak.index += 1
            st.table(top_streak[["Użytkownik", "Ogień 🔥"]])

        with col2:
            st.subheader("🧠 Mistrzowie Wiedzy")
            top_knowledge = df_final.sort_values(by="Wiedza 🧠", ascending=False).head(5).reset_index(drop=True)
            top_knowledge.index += 1
            display_knowledge = top_knowledge[["Użytkownik", "Wiedza 🧠"]].copy()
            display_knowledge["Wiedza 🧠"] = display_knowledge["Wiedza 🧠"].apply(lambda x: f"{x}%")
            st.table(display_knowledge)

        st.write("---")

        # --- Rząd 2: Rankingi Gier (3 Zakładki) ---
        st.subheader("🧩 Mistrzowie Gier (Top 10)")
        t_m, t_b, t_s = st.tabs(["⏱️ Memory", "🎈 Balony", "🐍 Wąż"])

        with t_m:
            df_mem = df_final.dropna(subset=["Najlepsze Memory ⏱️"])
            if not df_mem.empty:
                df_mem_sorted = df_mem.sort_values(by="Najlepsze Memory ⏱️", ascending=True).head(10).reset_index(drop=True)
                df_mem_sorted.index += 1
                display_mem = df_mem_sorted[["Użytkownik", "Najlepsze Memory ⏱️"]].copy()
                display_mem["Najlepsze Memory ⏱️"] = display_mem["Najlepsze Memory ⏱️"].apply(lambda x: f"{x}s")
                st.table(display_mem)
            else:
                st.info("Brak rekordów w Memory.")

        with t_b:
            df_bal = df_final[df_final["Rekord Balony 🎈"] > 0]
            if not df_bal.empty:
                df_bal_sorted = df_bal.sort_values(by="Rekord Balony 🎈", ascending=False).head(10).reset_index(drop=True)
                df_bal_sorted.index += 1
                st.table(df_bal_sorted[["Użytkownik", "Rekord Balony 🎈"]])
            else:
                st.info("Brak rekordów w Balonach.")

        with t_s:
            df_snake = df_final[df_final["Seria Węża 🐍"] > 0]
            if not df_snake.empty:
                df_snake_sorted = df_snake.sort_values(by="Seria Węża 🐍", ascending=False).head(10).reset_index(drop=True)
                df_snake_sorted.index += 1
                st.table(df_snake_sorted[["Użytkownik", "Seria Węża 🐍"]])
            else:
                st.info("Brak rekordów w Wężu.")

        st.divider()
        
        # 4. TWOJA POZYCJA
        try:
            df_pos = df_final.sort_values(by="Ogień 🔥", ascending=False).reset_index(drop=True)
            my_rank = df_pos[df_pos["Użytkownik"] == u.capitalize()].index[0] + 1
            st.info(f"Twoja aktualna pozycja w rankingu ogólnym ognia: **{my_rank}** na **{len(df_final)}** użytkowników.")
        except:
            pass

# --- 21. GENERATOR SŁÓW (V247 - Gwarantowane Rodzajniki) ---
elif choice == "📦 Generator słów":
    st.header("📦 Generator słów")
    st.write("Generuj słówka na podstawie poziomu lub konkretnego tematu.")

    # 1. PANEL STEROWANIA
    with st.container(border=True):
        c1, c2, c3 = st.columns([2, 2, 1])
        with c1:
            gen_lvl = st.selectbox("Poziom (opcjonalnie):", ["Brak", "A1", "A2", "B1", "B2", "C1"], key="gen_lvl_sel")
        with c2:
            gen_topic = st.text_input("Temat (opcjonalnie):", placeholder="np. Kuchnia, Praca...", key="gen_top_in")
        with c3:
            gen_count = st.number_input("Ilość:", 3, 20, 5, key="gen_cnt_in")
        
        if st.button("✨ Generuj listę do sprawdzenia", use_container_width=True, type="primary"):
            if gen_lvl == "Brak" and not gen_topic:
                st.warning("Wybierz poziom lub wpisz temat!")
            else:
                with st.spinner("AI dobiera słownictwo i sprawdza rodzajniki..."):
                    context = f"na poziomie {gen_lvl}" if gen_lvl != "Brak" else ""
                    if gen_topic: context += f" o tematyce: {gen_topic}"
                    
                    # WZMOCNIONY PROMPT (Instrukcja o rodzajnikach jest teraz na początku i końcu)
                    prompt = f"""Wygeneruj {gen_count} unikalnych słówek/fraz po niemiecku {context}.
                    UWAGA: Każdy rzeczownik MUSI posiadać rodzajnik (der, die lub das).
                    Dla każdego elementu podaj:
                    1. de: słowo (BEZWZGLĘDNIE z rodzajnikiem dla rzeczowników)
                    2. pl: tłumaczenie
                    3. tags: minimum 3 tagi (np. 'Poziom, Część mowy, Temat')
                    4. ex_de: przykład użycia
                    5. ex_pl: tłumaczenie przykładu
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

        df_init = []
        for item in st.session_state.temp_generated:
            base_tags = item.get("tags", "")
            if saved_lvl != "Brak" and saved_lvl not in base_tags:
                base_tags = f"{saved_lvl}, {base_tags}"

            df_init.append({
                "Dodaj": True,
                "Niemiecki": item.get("de", ""),
                "Polski": item.get("pl", ""),
                "Kategorie (Tagi)": base_tags,
                "Przykład DE": item.get("ex_de", ""),
                "Przykład PL": item.get("ex_pl", "")
            })

        edited_df = st.data_editor(
            df_init, 
            use_container_width=True, 
            num_rows="dynamic",
            key="ai_editor_v247"
        )

        col_save, col_cancel = st.columns(2)
        
        if col_save.button("🚀 Zapisz wybrane słówka", use_container_width=True, type="primary"):
            success_count = 0
            for row in edited_df:
                if row.get("Dodaj", False):
                    new_word = {
                        "de": row["Niemiecki"],
                        "pl": row["Polski"],
                        "category": row["Kategorie (Tagi)"],
                        "next_review": str(date.today()),
                        "level": 0,
                        "origin": "Generator",
                        "examples": [{"de": row["Przykład DE"], "pl": row["Przykład PL"]}]
                    }
                    save_word(u, new_word)
                    success_count += 1
            
            st.success(f"Pomyślnie dodano {success_count} słówek!")
            st.session_state.flashcards = load_flashcards(u)
            if "temp_generated" in st.session_state:
                del st.session_state.temp_generated
            st.rerun()

        if col_cancel.button("🗑️ Anuluj listę", use_container_width=True):
            if "temp_generated" in st.session_state:
                del st.session_state.temp_generated
            st.rerun()

# --- 22. SKANER AI (V3.1 - Z licznikiem wyskanowanych słówek) ---
elif choice == "📸 Skaner AI":
    st.header("📸 Skaner AI")

    # Obsługa komunikatu o sukcesie po zapisie i odświeżeniu
    if "scan_msg" in st.session_state:
        st.success(st.session_state.scan_msg)
        del st.session_state.scan_msg

    # 1. Inicjalizacja tymczasowej listy w sesji, jeśli nie istnieje
    if "temp_scanned" not in st.session_state:
        st.session_state.temp_scanned = []

    # --- WIDOK 1: PRZETWARZANIE OBRAZU ---
    if not st.session_state.temp_scanned:
        st.write("Wgraj zdjęcie lub zrób fotkę notatek, aby AI wyciągnęła z nich nowe słówka.")
        t1, t2 = st.tabs(["📁 Wgraj plik", "📷 Zrób zdjęcie"])
        
        img_to_process = None
        with t1:
            uploaded_file = st.file_uploader("Wybierz zdjęcie (PNG, JPG)", type=["png", "jpg", "jpeg"])
            if uploaded_file: img_to_process = uploaded_file
        with t2:
            camera_file = st.camera_input("Zrób zdjęcie")
            if camera_file: img_to_process = camera_file

        if img_to_process:
            if st.button("🚀 Analizuj i przygotuj listę", type="primary", use_container_width=True):
                with st.spinner("AI analizuje tekst, wyklucza duplikaty i generuje przykłady..."):
                    try:
                        # Pobieramy obecne niemieckie słówka z bazy
                        existing_de = {str(w.get('de', '')).lower().strip() for w in st.session_state.flashcards}
                        
                        image = Image.open(img_to_process)
                        
                        prompt = """
                        Przeanalizuj zdjęcie. Znajdź na nim niemieckie słówka, wyrażenia lub fragmenty notatek.
                        Dla każdego znalezionego pojęcia:
                        1. Podaj poprawny niemiecki (z rodzajnikiem dla rzeczowników).
                        2. Podaj polskie tłumaczenie. 
                        3. MUSISZ wygenerować dokładnie 3 tagi: część mowy, kategoria tematyczna oraz poziom CEFR.
                        4. BEZWZGLĘDNIE wygeneruj 1 naturalne zdanie przykładowe po niemiecku z jego polskim tłumaczeniem.
                        Zwróć TYLKO JSON w formacie: {"flashcards": [{"de": "...", "pl": "...", "category": "...", "examples": [{"de": "...", "pl": "..."}]}]}
                        """
                        
                        raw_res = get_openai_response(prompt, img_obj=image)
                        raw_res = raw_res.replace("```json", "").replace("```", "").strip()
                        data = json.loads(raw_res)
                        
                        items = data.get("flashcards", data.get("words", []))
                        
                        if items:
                            unique_items = []
                            skipped_count = 0
                            
                            for item in items:
                                word_de = str(item.get("de", "")).lower().strip()
                                if word_de and word_de not in existing_de:
                                    unique_items.append(item)
                                else:
                                    skipped_count += 1

                            if unique_items:
                                st.session_state.temp_scanned = unique_items
                                if skipped_count > 0:
                                    st.toast(f"ℹ️ Pominięto {skipped_count} słówek (już są w bazie).")
                                st.rerun()
                            else:
                                st.warning(f"AI znalazło {len(items)} słówek, ale wszystkie masz już w słowniku!")
                        else:
                            st.warning("Nie znaleziono czytelnych słówek na zdjęciu.")
                            
                    except Exception as e:
                        st.error(f"Błąd analizy AI: {e}")

    # --- WIDOK 2: EDYCJA I WERYFIKACJA ---
    else:
        # NOWOŚĆ: Licznik słówek na górze panelu edycji
        scanned_count = len(st.session_state.temp_scanned)
        st.subheader(f"📝 Weryfikacja ({scanned_count} nowych słówek)")
        st.info("Pominięto duplikaty. Sprawdź i edytuj dane przed zapisem.")

        @st.fragment
        def review_scanned_items():
            temp_list = st.session_state.temp_scanned
            updated_list = []
            to_delete = None

            for i, item in enumerate(temp_list):
                with st.container(border=True):
                    c1, c2, c3, c4 = st.columns([3, 3, 3, 1])
                    
                    new_de = c1.text_input("Niemiecki (DE)", item.get('de', ''), key=f"sc_de_{i}")
                    new_pl = c2.text_input("Polski (PL)", item.get('pl', ''), key=f"sc_pl_{i}")
                    new_cat = c3.text_input("Tagi", item.get('category', ''), key=f"sc_cat_{i}")
                    
                    if c4.button("🗑️", key=f"sc_del_{i}", help="Usuń z listy"):
                        to_delete = i

                    examples = item.get('examples', [])
                    if examples and len(examples) > 0:
                        ex_de = examples[0].get('de', '')
                        ex_pl = examples[0].get('pl', '')
                        st.caption(f"💡 Przykład: **{ex_de}** (*{ex_pl}*)")
                    else:
                        st.caption("⚠️ Brak przykładu.")

                    updated_list.append({
                        "de": new_de,
                        "pl": new_pl,
                        "category": new_cat,
                        "examples": examples
                    })

            if to_delete is not None:
                st.session_state.temp_scanned.pop(to_delete)
                st.rerun(scope="fragment")

            st.write("---")
            col_act1, col_act2 = st.columns(2)
            
            if col_act1.button("🔥 Anuluj wszystko", use_container_width=True):
                del st.session_state.temp_scanned
                st.rerun()

            if col_act2.button(f"✅ Zapisz {len(updated_list)} słówek", type="primary", use_container_width=True):
                with st.spinner("Zapisywanie..."):
                    insert_payload = []
                    for card in updated_list:
                        if str(card["de"]).strip() and str(card["pl"]).strip():
                            insert_payload.append({
                                "username": u,
                                "de": str(card["de"]).strip(),
                                "pl": str(card["pl"]).strip(),
                                "category": str(card["category"]).strip(),
                                "examples": card["examples"],
                                "next_review": str(date.today()),
                                "origin": "Skaner"
                            })
                    
                    if insert_payload:
                        get_db().table("flashcards").insert(insert_payload).execute()
                        st.session_state.flashcards = load_flashcards(u)
                        st.session_state.user_data["historical_cost"] += 0.05
                        save_user_data(u, st.session_state.user_data)
                        
                        count = len(insert_payload)
                        del st.session_state.temp_scanned
                        st.session_state.scan_msg = f"✅ Gotowe! Pomyślnie dodano {count} zweryfikowanych słówek."
                        st.rerun()
                    else:
                        st.error("Lista jest pusta!")

        review_scanned_items()
        
# --- 23. DODAJ (V265 - Wsparcie dla wielu języków DE/CS) ---
elif choice == "➕ Dodaj":
    # Pobieramy aktualny język z sesji (ustawiony w Sidebarze)
    current_lang_name = st.session_state.get("current_lang", "Niemiecki")
    L_CODE = "de" if current_lang_name == "Niemiecki" else "cs"
    
    st.header(f"➕ Dodaj nowe słówko ({current_lang_name})")
    
    tab1, tab2 = st.tabs(["✍️ Manualnie", "🤖 Asystent AI ✨"])
    
    with tab1:
        @st.fragment
        def manual_add_ui():
            with st.form("manual_add_form", clear_on_submit=True):
                col1, col2 = st.columns(2)
                # Dynamiczna etykieta w zależności od języka
                label_lang = "Słowo (DE):" if L_CODE == "de" else "Słowo (CS):"
                placeholder_lang = "np. der Hund" if L_CODE == "de" else "np. jablko"
                
                f_de = col1.text_input(label_lang, placeholder=placeholder_lang)
                f_pl = col2.text_input("Tłumaczenie (PL):", placeholder="np. pies / jabłko")
                f_cat = st.text_input("Kategorie / Tagi:", placeholder="rzeczownik, jedzenie, A1")
                
                if st.form_submit_button("💾 Zapisz do bazy", use_container_width=True, type="primary"):
                    if f_de.strip() and f_pl.strip():
                        new_word = {
                            "username": u,
                            "de": f_de.strip(),
                            "pl": f_pl.strip(),
                            "category": f_cat.strip(),
                            "next_review": str(date.today()),
                            "level": 0,
                            "origin": "Dodaj",
                            "lang": L_CODE, # KLUCZOWE: Zapisujemy kod języka
                            "examples": []
                        }
                        save_word(u, new_word)
                        st.session_state.flashcards = load_flashcards(u)
                        st.success(f"Pomyślnie dodano ({current_lang_name}): **{f_de}**")
                    else:
                        st.error("Wypełnij wszystkie pola!")
        manual_add_ui()

    with tab2:
        st.info(f"Wpisz słowo, a AI przygotuje resztę dla języka **{current_lang_name}**.")
        ai_word = st.text_input(f"Jakie słowo ({L_CODE.upper()}) przygotować?", placeholder="np. Rozhodnutí", key="ai_input_field")
        
        if st.button("Przygotuj dane przez AI ✨", use_container_width=True):
            if ai_word:
                with st.spinner(f"AI analizuje słowo w języku {current_lang_name}..."):
                    # Dynamiczny PROMPT uwzględniający język
                    lang_instruction = ""
                    if L_CODE == "de":
                        lang_instruction = "Jeśli słowo jest rzeczownikiem, MUSISZ dodać rodzajnik (der, die, das)."
                    elif L_CODE == "cs":
                        lang_instruction = "Podaj słowo w poprawnej formie czeskiej."

                    prompt = f"""Przygotuj dane dla słowa/frazy w języku {current_lang_name}: '{ai_word}'.
                    {lang_instruction}
                    Zwróć WYŁĄCZNIE JSON w formacie:
                    {{
                      "de": "słowo w języku {current_lang_name}",
                      "pl": "tłumaczenie na polski",
                      "tags": "Poziom, Część mowy, Temat",
                      "ex_de": "przykład użycia w języku {current_lang_name}",
                      "ex_pl": "tłumaczenie przykładu na polski"
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
            st.subheader("📝 Sprawdź i popraw przed zapisem")
            
            item = st.session_state.single_temp[0]
            # Nagłówki w edytorze dopasowane do języka
            de_col_name = "Niemiecki" if L_CODE == "de" else "Czeski"
            
            df_init = [{
                "Dodaj": True,
                de_col_name: item.get("de", ""),
                "Polski": item.get("pl", ""),
                "Kategorie (Tagi)": item.get("tags", ""),
                "Przykład (Oryginał)": item.get("ex_de", ""),
                "Przykład PL": item.get("ex_pl", "")
            }]

            edited_df = st.data_editor(
                df_init,
                use_container_width=True,
                num_rows="fixed",
                key="single_word_editor_multilang"
            )

            c_save, c_cancel = st.columns(2)
            
            if c_save.button("✅ Wszystko gra, dodaj!", use_container_width=True, type="primary"):
                row = edited_df[0]
                if row.get("Dodaj", False):
                    new_word = {
                        "de": row[de_col_name],
                        "pl": row["Polski"],
                        "category": row["Kategorie (Tagi)"],
                        "next_review": str(date.today()),
                        "level": 0,
                        "origin": "Dodaj (AI)",
                        "lang": L_CODE, # Zapisujemy wybrany język
                        "examples": [{"de": row["Przykład (Oryginał)"], "pl": row["Przykład PL"]}]
                    }
                    save_word(u, new_word)
                    st.success(f"Słówko ({current_lang_name}) dodane do bazy!")
                    st.session_state.flashcards = load_flashcards(u)
                    del st.session_state.single_temp
                    st.rerun()

            if c_cancel.button("🗑️ Odrzuć", use_container_width=True):
                if "single_temp" in st.session_state:
                    del st.session_state.single_temp
                st.rerun()

# --- 24. SŁOWNIK (V270 - Multilang: Filtrowanie po Języku) ---
elif choice == "📖 Słownik":
    # Pobieramy aktualny język i kod z sesji
    current_lang_name = st.session_state.get("current_lang", "Niemiecki")
    L_CODE = "de" if current_lang_name == "Niemiecki" else "cs"
    L_LABEL = "DE" if L_CODE == "de" else "CS"
    
    st.header(f"📖 Słownik: {current_lang_name}")
    
    # 1. Pobranie słówek tylko dla wybranego języka
    # Używamy get("lang", "de"), aby stare słówka bez tagu domyślnie trafiły do niemieckiego
    lang_cards = [c for c in st.session_state.flashcards if c.get("lang", "de") == L_CODE]
    
    # 2. Pobranie unikalnych tagów (tylko z odfiltrowanych słówek)
    all_tags = set()
    for c in lang_cards:
        all_tags.update([t.strip() for t in str(c.get('category','')).split(',') if t.strip()])
    
    # 3. Wyszukiwarka i filtry
    col1, col2 = st.columns([1, 2])
    f_tag = col1.selectbox(f"Kategorie ({current_lang_name}):", ["Wszystkie"] + sorted(list(all_tags)))
    search = col2.text_input("Szukaj słowa (ENTER ⏎):", placeholder=f"Szukaj w {current_lang_name} lub PL...")
    
    # 4. Logika filtrowania wyników wyszukiwania
    filtered = [
        c for c in lang_cards 
        if (f_tag == "Wszystkie" or f_tag in str(c.get('category',''))) 
        and (search.lower() in str(c.get('de','')).lower() or search.lower() in str(c.get('pl','')).lower())
    ]
    
    st.write("---")
    st.subheader(f"Znaleziono słówek: {len(filtered)}")
    
    # Zabezpieczenie przed przeładowaniem strony
    MAX_DISPLAY = 50
    display_list = filtered[:MAX_DISPLAY] if len(filtered) > MAX_DISPLAY else filtered
    
    if len(filtered) > MAX_DISPLAY:
        st.warning(f"Wyświetlam pierwsze {MAX_DISPLAY} wyników. Zawęź wyszukiwanie.")
        
    if not display_list:
        st.info(f"Brak słówek w języku {current_lang_name} spełniających kryteria.")
        
    # 5. Wyświetlanie wyników
    for c in display_list:
        # Dynamiczna etykieta akordeonu (Flaga + Słowo)
        flag = "🇩🇪" if L_CODE == "de" else "🇨🇿"
        with st.expander(f"{flag} {c['de']} ➔ 🇵🇱 {c['pl']}"):
            
            st.caption(f"🗓️ Powtórka: {c.get('next_review', 'Brak')} | 🏷️ Tagi: {c.get('category', 'Brak')}")
            
            # Przycisk Audio z poprawnym kodem języka
            if st.button(f"🔊 Odsłuchaj ({L_LABEL})", key=f"audio_{c['id']}", use_container_width=True):
                play_audio(c['de'], lang=L_CODE)
            
            # Tryb Edycji
            with st.form(f"ed_{c['id']}"):
                input_label = f"Słowo {current_lang_name} ({L_LABEL})"
                n_de = st.text_input(input_label, c['de'])
                n_pl = st.text_input("Polski (PL)", c['pl'])
                n_ca = st.text_input("Kategorie / Tagi", c.get('category',''))
                
                if st.form_submit_button("💾 Zapisz zmiany", use_container_width=True):
                    # Przy aktualizacji zachowujemy obecny język (L_CODE)
                    update_word(c['id'], {"de": n_de, "pl": n_pl, "category": n_ca, "lang": L_CODE})
                    st.session_state.flashcards = load_flashcards(u)
                    st.toast("Zapisano! ✅")
                    st.rerun()
                    
            # Usuwanie
            if st.button("🗑️ Usuń", key=f"del_{c['id']}", type="primary", use_container_width=True):
                delete_word(c['id'])
                st.session_state.flashcards = load_flashcards(u)
                st.toast("Usunięto! 🗑️")
                st.rerun()

# --- 25. STATYSTYKI (V240 - Multilang: Pełna separacja rekordów i nauki) ---
elif choice == "📊 Statystyki":
    # Pobieramy aktualny język i kod z sesji (DE/CS)
    current_lang_name = st.session_state.get("current_lang", "Niemiecki")
    L_CODE = "de" if current_lang_name == "Niemiecki" else "cs"
    
    st.header(f"📊 Statystyki: {current_lang_name}")
    
    # 1. FILTROWANIE DANYCH POD JĘZYK (Słówka)
    df_full = pd.DataFrame(st.session_state.flashcards)
    if not df_full.empty:
        df = df_full[df_full.get("lang", "de") == L_CODE].copy()
    else:
        df = pd.DataFrame()

    ud = st.session_state.user_data
    
    # 2. METRYKI GŁÓWNE
    c1, c2 = st.columns(2)
    c1.metric(f"Słówek ({current_lang_name})", len(df))
    # Passa pozostaje globalna jako ogólna motywacja konta
    c2.metric("Passa Nauki (Global)", f"{ud.get('streak', 0)} dni")
    
    st.write("---")

    # --- 3. REKORDY GIER (Zależne od języka DE/CS) ---
    st.subheader(f"🏆 Moje Rekordy ({current_lang_name})")
    t_mem, t_bal, t_snake = st.tabs(["🧩 Memory", "🎈 Balonowy Wyścig", "🐍 Lingwistyczny Wąż"])
    
    # Dynamiczne klucze do bazy (np. memory_scores_de lub memory_scores_cs)
    mem_key = f"memory_scores_{L_CODE}"
    bal_key = f"top_balloons_{L_CODE}"
    # Zabezpieczenie dla starej nazwy kolumny balonu, jeśli istniała
    bal_legacy_key = f"baloon_scores_{L_CODE}"

    with t_mem:
        # Odczytujemy wyniki tylko dla wybranego języka
        mem_scores = ud.get(mem_key, [])
        if mem_scores and isinstance(mem_scores, list):
            top3_mem = sorted([float(s) for s in mem_scores])[:3]
            m_cols = st.columns(3)
            icons = ["🥇", "🥈", "🥉"]
            for i, score in enumerate(top3_mem):
                if i < len(m_cols):
                    m_cols[i].metric(f"{icons[i]} Miejsce", f"{score}s")
        else:
            st.info(f"Zagraj w Memory ({current_lang_name}), aby ustanowić rekord!")

    with t_bal:
        # Próba odczytu z nowej kolumny, a jeśli pusta - ze starej wersji językowej
        bal_scores = ud.get(bal_key, ud.get(bal_legacy_key, []))
        if bal_scores and isinstance(bal_scores, list):
            top3_bal = sorted([int(s) for s in bal_scores], reverse=True)[:3]
            b_cols = st.columns(3)
            icons = ["🥇", "🥈", "🥉"]
            for i, score in enumerate(top3_bal):
                if i < len(b_cols):
                    b_cols[i].metric(f"{icons[i]} Miejsce", f"{score} pkt")
        else:
            st.info(f"Zagraj w Balonowy Wyścig ({current_lang_name}), aby zdobyć punkty!")

    with t_snake:
        # Wąż na ten moment przechowuje rekord w user_data w sposób globalny, 
        # ale wyświetlamy go tutaj dla spójności
        s_max = ud.get("snake_best_chain", 0)
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
    
    # 4. CZAS NAUKI I FAZY (Zależne od języka)
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
        st.subheader(f"🧠 Fazy: {current_lang_name}")
        if not df.empty:
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
        else:
            st.info("Brak danych.")

    st.write("---")
    
    # 5. PROGNOZA POWTÓREK
    st.subheader(f"📅 Prognoza: {current_lang_name}")
    if not df.empty:
        sched = []
        today_dt = date.today()
        for i in range(10):
            target_date = str(today_dt + timedelta(days=i))
            count = len(df[df['next_review'] <= target_date]) if i == 0 else len(df[df['next_review'] == target_date])
            label = "Dzisiaj" if i == 0 else (today_dt + timedelta(days=i)).strftime("%d.%m")
            sched.append({"Dzień": label, "Liczba słówek": count})
        st.dataframe(pd.DataFrame(sched), use_container_width=True, hide_index=True)

    st.write("---")
    
    # 6. POZIOMY I ŹRÓDŁA
    col_stats1, col_stats2 = st.columns(2)
    with col_stats1:
        st.subheader("📈 Słówka wg poziomu")
        if not df.empty:
            levels = ["A1", "A2", "B1", "B2", "C1"]
            level_data = []
            today_str = str(date.today())
            for lvl in levels:
                mask = df['category'].str.contains(lvl, case=False, na=False)
                u_lvl = df[mask]
                total = len(u_lvl)
                mastered = len(u_lvl[u_lvl['next_review'] > today_str])
                perc = int(round((mastered / total) * 100)) if total > 0 else 0
                level_data.append({"Poziom": lvl, "Słówek": total, "Opanowane": f"{perc}%"})
            st.dataframe(pd.DataFrame(level_data), use_container_width=True, hide_index=True)
            
    with col_stats2:
        st.subheader("📌 Źródła pozyskania")
        if not df.empty and 'origin' in df.columns:
            origin_counts = df['origin'].value_counts().reset_index()
            origin_counts.columns = ['Źródło', 'Liczba słówek']
            st.dataframe(origin_counts, use_container_width=True, hide_index=True)
        
    st.write("---")
    st.subheader("📝 Historia rozwiązanych testów")
    t_hist = ud.get("test_history", [])
    if t_hist:
        hist_df = pd.DataFrame(t_hist)[::-1]
        hist_df = hist_df[["date", "score", "total", "perc"]]
        hist_df.columns = ["Data", "Wynik", "Suma pytań", "Procent (%)"]
        st.dataframe(hist_df, use_container_width=True, hide_index=True)

# --- 26. KONTO ---
elif choice == "⚙️ Moje Konto":
    st.header("⚙️ Zarządzanie Kontem")
    
    # --- WYŚWIETLANIE KOMUNIKATÓW PO PRZEŁADOWANIU ---
    if "acc_msg" in st.session_state:
        st.success(st.session_state.acc_msg)
        del st.session_state.acc_msg
    # ------------------------------------------------

    # --- 1. PREFERENCJE NAUKI ---
    with st.expander("🛠️ Preferencje nauki"):
        st.write("Dostosuj działanie aplikacji do swojego stylu:")
        
        # Inicjalizacja ustawień w user_data, jeśli ich nie ma
        if "settings" not in st.session_state.user_data:
            st.session_state.user_data["settings"] = {
                "auto_audio": True,
                "show_hints": True,
                "default_test_size": 10,
                "daily_goal": 20  # Wartość domyślna celu
            }
        
        s = st.session_state.user_data["settings"]
        
        s["auto_audio"] = st.toggle("Automatyczne odtwarzanie lektora (Audio)", s.get("auto_audio", True))
        s["show_hints"] = st.toggle("Pokazuj podpowiedzi PL w Quizie", s.get("show_hints", True))
        s["default_test_size"] = st.slider("Domyślna liczba pytań w teście", 5, 50, s.get("default_test_size", 10))
        
        # --- NOWOŚĆ: Ustawienie celu dziennego ---
        s["daily_goal"] = st.slider("Twój dzienny cel nauki (minuty)", 5, 120, s.get("daily_goal", 20))
        
        if st.button("Zapisz ustawienia", use_container_width=True):
            save_user_data(u, st.session_state.user_data)
            st.toast("Ustawienia zapisane! 💾")

    # --- 2. ZMIANA HASŁA ---
    with st.expander("🔑 Zmień hasło"):
        with st.form("pw_change"):
            o, n = st.text_input("Stare hasło", type="password"), st.text_input("Nowe hasło", type="password")
            if st.form_submit_button("Zmień hasło", use_container_width=True):
                db = get_db()
                res = db.table("users_auth").select("*").eq("username", u).execute()
                if res.data and res.data[0]["password_hash"] == hash_pw(o):
                    db.table("users_auth").update({"password_hash": hash_pw(n)}).eq("username", u).execute()
                    st.success("Hasło zaktualizowane!")
                else:
                    st.error("Błędne stare hasło!")

    # --- 3. EKSPORT I IMPORT (CSV) ---
    with st.expander("📥 Eksport i Import słówek (CSV)"):
        st.subheader("Eksportuj swoje dane")
        if st.session_state.flashcards:
            df_export = pd.DataFrame(st.session_state.flashcards)
            # Przygotowujemy czysty CSV do pobrania
            csv = df_export[["de", "pl", "category", "origin"]].to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Pobierz moją bazę jako plik .CSV",
                data=csv,
                file_name=f"niemiecki_master_backup_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
                use_container_width=True
            )
        
        st.write("---")
        st.subheader("Importuj słówka z pliku")
        st.info("Wymagane kolumny w pliku CSV: de, pl, category")
        uploaded_file = st.file_uploader("Wybierz plik .csv", type="csv")
        
        if uploaded_file and st.button("🚀 Rozpocznij import"):
            try:
                imp_df = pd.read_csv(uploaded_file)
                if all(col in imp_df.columns for col in ["de", "pl"]):
                    new_cards = []
                    for _, row in imp_df.iterrows():
                        new_cards.append({
                            "username": u,
                            "de": str(row["de"]),
                            "pl": str(row["pl"]),
                            "category": str(row.get("category", "Import")),
                            "next_review": str(date.today()),
                            "origin": "Import"
                        })
                    
                    if new_cards:
                        get_db().table("flashcards").insert(new_cards).execute()
                        st.session_state.flashcards = load_flashcards(u)
                        st.success(f"Pomyślnie zaimportowano {len(new_cards)} słówek!")
                        st.rerun()
                else:
                    st.error("Plik nie posiada wymaganych kolumn (de, pl).")
            except Exception as e:
                st.error(f"Błąd importu: {e}")

    # --- 4. USUWANIE I RESET DANYCH ---
    with st.expander("🗑️ Niebezpieczna strefa (Reset i Usuwanie)"):
        st.warning("Uwaga: Te operacje są nieodwracalne!")
        conf = st.checkbox("Potwierdzam chęć usunięcia danych")
        
        # --- NOWOŚĆ: RESET SAMEGO STREAKA ---
        st.write("---")
        st.subheader("🔥 Resetuj Passę (Streak)")
        st.caption("Ustawia ogień na 0 i pozwala zdobyć go dzisiaj od nowa po osiągnięciu celu.")
        if st.button("Ustaw Streak na 0", type="secondary", disabled=not conf, use_container_width=True):
            st.session_state.user_data["streak"] = 0
            st.session_state.user_data["last_date"] = "2000-01-01" # Ustawienie starej daty wymusza nowy start
            save_user_data(u, st.session_state.user_data)
            st.session_state.acc_msg = "✅ Twoja passa została wyzerowana. Do dzieła!"
            st.rerun()

        # --- RESET STATYSTYK ---
        st.write("---")
        st.subheader("🧹 Reset samych statystyk")
        st.caption("Zachowuje wszystkie Twoje słówka, ale zeruje czas nauki, historię testów i daty powtórek.")
        conf_stats = st.checkbox("Potwierdzam reset STATYSTYK (słówka zostaną)")
        
        if st.button("Zresetuj statystyki nauki", type="secondary", disabled=not conf_stats, use_container_width=True):
            with st.spinner("Resetowanie..."):
                # 1. Zerujemy user_data w bazie
                st.session_state.user_data["time_stats"] = {}
                st.session_state.user_data["test_history"] = []
                st.session_state.user_data["streak"] = 0
                save_user_data(u, st.session_state.user_data)
                
                # 2. Resetujemy daty powtórek wszystkich słówek na dzisiaj
                get_db().table("flashcards").update({"next_review": str(date.today())}).eq("username", u).execute()
                
                st.session_state.acc_msg = "✅ Statystyki nauki zostały zresetowane. Możesz zacząć od zera!"
                st.session_state.flashcards = load_flashcards(u)
                st.rerun()

        # --- USUWANIE POZIOMÓW ---
        st.write("---")
        st.subheader("Wybierz poziomy do usunięcia")
        col_d = st.columns(5)
        for i, lvl in enumerate(["A1", "A2", "B1", "B2", "C1"]):
            if col_d[i].button(lvl, disabled=not conf, key=f"del_lvl_{lvl}"):
                res = get_db().table("flashcards").delete().eq("username", u).ilike("category", f"%{lvl}%").execute()
                count = len(res.data) if res.data else 0
                st.session_state.acc_msg = f"🗑️ Usunięto {count} słówek z poziomu {lvl}."
                st.session_state.flashcards = load_flashcards(u)
                st.rerun()
        
        # --- HARD RESET ---
        st.write("---")
        if st.button("🔥 USUŃ TRWALE CAŁĄ BAZĘ SŁÓWEK", type="primary", disabled=not conf, use_container_width=True):
            res = get_db().table("flashcards").delete().eq("username", u).execute()
            count = len(res.data) if res.data else 0
            st.session_state.acc_msg = f"🔥 Baza została wyczyszczona (usunięto {count} słówek)."
            st.session_state.flashcards = []
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
