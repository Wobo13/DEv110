import streamlit as st
import json
import random
import re
import hashlib
import pandas as pd
import time
import base64
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

# --- 2. SILNIK BAZY I POMOCNIKI ---
def get_db():
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    return SyncPostgrestClient(f"{SUPABASE_URL}/rest/v1", headers=headers)

def hash_pw(pw): return hashlib.sha256(str.encode(pw)).hexdigest()

def normalize_text(t):
    if not t: return ""
    return str(t).lower().strip().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")

def get_openai_response(prompt_text, img_obj=None):
    if not API_KEY: raise Exception("Brak klucza API OpenAI.")
    client = OpenAI(api_key=API_KEY)
    messages = [{"role": "system", "content": "Jesteś ekspertem niemieckiego. Odpowiadaj TYLKO w JSON. Kategorie po polsku, przykłady jako lista {de, pl}."}]
    if img_obj:
        buf = BytesIO(); img_obj.thumbnail((800, 800)); img_obj.save(buf, format="JPEG")
        img_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        messages.append({"role": "user", "content": [{"type": "text", "text": prompt_text}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}}]})
    else:
        messages.append({"role": "user", "content": prompt_text})
    res = client.chat.completions.create(model="gpt-4o-mini", messages=messages, response_format={"type": "json_object"})
    return res.choices[0].message.content

def play_audio(txt, ex_txt=None):
    try:
        full = f"{txt}. . . . {ex_txt}" if ex_txt else txt
        f = BytesIO(); tts = gTTS(text=full, lang='de'); tts.write_to_fp(f); f.seek(0)
        st.audio(f, format="audio/mp3", autoplay=True)
    except: pass

# --- 3. FUNKCJE DANYCH (SUPABASE) ---
def load_user_data(username):
    db = get_db(); res = db.table("user_data").select("*").eq("username", username).execute()
    if res.data: return res.data[0]
    init = {"username": username, "streak":0, "historical_cost":0.0, "time_stats":{}, "last_ts":time.time(), "last_seen":"Nigdy", "test_history": []}
    db.table("user_data").insert(init).execute()
    return init

def save_user_data(username, data):
    d = data.copy(); d.pop("username", None)
    get_db().table("user_data").update(d).eq("username", username).execute()

def load_flashcards(username):
    db = get_db(); res = db.table("flashcards").select("*").eq("username", username).order("id").execute()
    cards = res.data if res.data else []
    for c in cards:
        if not c.get("origin"): c["origin"] = "Dodaj"
    return cards

def save_word(username, word_obj):
    db = get_db(); word_obj["username"] = username
    if "examples" not in word_obj: word_obj["examples"] = []
    db.table("flashcards").insert(word_obj).execute()

def update_word(word_id, fields): get_db().table("flashcards").update(fields).eq("id", word_id).execute()
def delete_word(word_id): get_db().table("flashcards").delete().eq("id", word_id).execute()

# --- 4. LOGOWANIE I REJESTRACJA ---
if "auth" not in st.session_state:
    st.session_state.auth = False
    if "token" in st.query_params:
        u_tk = st.query_params["token"]
        st.session_state.auth, st.session_state.user = True, u_tk

if not st.session_state.auth:
    st.title(f"🚀 Niemiecki Master {APP_VERSION}")
    t1, t2 = st.tabs(["🔐 Logowanie", "📝 Rejestracja"])
    db = get_db()
    with t1:
        un = st.text_input("Użytkownik", key="l_u").lower().strip()
        pw = st.text_input("Hasło", type="password", key="l_p")
        if st.button("Zaloguj się", use_container_width=True, type="primary"):
            res = db.table("users_auth").select("*").eq("username", un).execute()
            if res.data and res.data[0]["password_hash"] == hash_pw(pw):
                st.session_state.auth, st.session_state.user = True, un
                st.query_params["token"] = un; st.rerun()
            else: st.error("Błędne dane logowania")
    with t2:
        rn = st.text_input("Nowy użytkownik", key="r_u").lower().strip()
        rp = st.text_input("Hasło", type="password", key="r_p")
        if st.button("Załóż konto"):
            if len(rn) > 2 and len(rp) > 3:
                check = db.table("users_auth").select("*").eq("username", rn).execute()
                if not check.data:
                    get_db().table("users_auth").insert({"username": rn, "password_hash": hash_pw(rp)}).execute()
                    load_user_data(rn)
                    st.success("Konto gotowe! Logowanie...")
                    time.sleep(1.5)
                    st.rerun()
                else: st.error("Ten użytkownik jest już zajęty!")
            else: st.warning("Login (min. 3) i Hasło (min. 4) są za krótkie.")
    st.stop()

# --- 5. START SESJI ---
u = st.session_state.user
st.session_state.user_data = load_user_data(u)
st.session_state.flashcards = load_flashcards(u)

def update_activity(m):
    curr = time.time()
    # Pobieramy dane bezpośrednio z session_state, by uniknąć opóźnień bazy
    user_data = st.session_state.user_data
    last_ts = user_data.get("last_ts", curr)
    delta = curr - last_ts
    
    if 0 < delta < 600:
        clean = re.sub(r'[^\w\s]', '', m).lower().strip()
        pl_map = str.maketrans("ąćęłńóśźż", "acelnoszz")
        clean = clean.translate(pl_map)
        label = CLEAN_TIME_LABELS.get(clean, "Inn")
        
        # Aktualizacja lokalna
        stats = dict(user_data.get("time_stats", {}))
        stats[label] = stats.get(label, 0.0) + delta
        st.session_state.user_data["time_stats"] = stats
    
    st.session_state.user_data["last_ts"] = curr
    st.session_state.user_data["last_seen"] = datetime.now().strftime("%d.%m %H:%M")
    
    # Zapis do bazy (asynchronicznie w tle dla systemu)
    save_user_data(u, st.session_state.user_data)

# --- 6. SIDEBAR I NAWIGACJA (V6 - Warsztat Słówek) ---
# Nick i Passa
st.sidebar.markdown(f"## 👤 {u.capitalize()} <span style='float:right; font-size:0.7em; padding-top:10px;'>🔥 **{st.session_state.user_data.get('streak', 0)}d**</span>", unsafe_allow_html=True)

# --- WIDGETY MOTYWACYJNE ---
user_settings = st.session_state.user_data.get("settings", {})

if st.session_state.flashcards:
    today = date.today()
    total_cards = len(st.session_state.flashcards)
    strong_cards = len([c for c in st.session_state.flashcards if (datetime.strptime(str(c.get('next_review', today)), "%Y-%m-%d").date() - today).days > 6])
    mastery_perc = int((strong_cards / total_cards) * 100) if total_cards > 0 else 0
    
    daily_goal = user_settings.get("daily_goal", 20)
    total_mins_today = sum(v for k, v in st.session_state.user_data.get("time_stats", {}).items()) // 60
    progress_goal = min(1.0, total_mins_today / daily_goal) if daily_goal > 0 else 0.0

    # Wskaźniki: Wiedza i Cel
    st.sidebar.markdown(f"<div style='margin-bottom: -15px; font-size: 0.85em;'>🧠 Wiedza: <b>{mastery_perc}%</b></div>", unsafe_allow_html=True)
    st.sidebar.progress(mastery_perc / 100)
    
    st.sidebar.markdown(f"<div style='margin-bottom: -15px; font-size: 0.85em;'>🎯 Cel: <b>{int(total_mins_today)}/{daily_goal}m</b></div>", unsafe_allow_html=True)
    st.sidebar.progress(progress_goal)

# --- DYSKRETNA PORADA ---
tips = [
    "Ucz się rano – mózg lepiej przyswaja słówka.",
    "Metoda 15 min dziennie jest najlepsza.",
    "Czytaj na głos – angażujesz słuch.",
    "Twórz śmieszne skojarzenia.",
    "Powtarzaj słówka tuż przed snem."
]
st.sidebar.markdown(f"<p style='font-size: 0.8em; color: gray; margin-top: 10px; margin-bottom: -10px;'>💡 {random.choice(tips)}</p>", unsafe_allow_html=True)

st.sidebar.divider()

# --- MENU NAWIGACJI ---
menu = [
    "📅 Powtórki", "🚀 Trening", "🕹️ Quiz", "🎴 Fiszki", 
    "📝 Testy", "🧠 Memory", "🛠️ Warsztat", "🏆 Arena Wyzwań", # <--- WARSZTAT DODANY TUTAJ
    "📦 Generator słów", "📸 Skaner AI", 
    "➕ Dodaj", "📖 Słownik", "📊 Statystyki", "⚙️ Moje Konto"
]
if u == ADMIN_USER:
    menu.append("👑 Admin")

if "l_c" not in st.session_state:
    st.session_state.l_c = "Inne"

choice = st.sidebar.radio("Menu", menu, label_visibility="collapsed")

update_activity(st.session_state.l_c)

# Logika czyszczenia sesji przy zmianie modułu
if st.session_state.l_c != choice:
    keys_to_clear = [
        "cur_list", "n_idx", "f_idx", "f_flipped", "test_q", "test_idx", 
        "test_score", "q_c", "q_s", 
        "mem_grid", "mem_status", "mem_first", "mem_pairs",
        "w_list", "w_idx", "w_show" # <--- KLUCZE DLA WARSZTATU
    ]
    for k in keys_to_clear:
        if k in st.session_state: 
            del st.session_state[k]
    
    st.session_state.l_c = choice
    st.session_state.n_m = "ask"
    st.session_state.u_a = ""

# --- STOPKA ---
st.sidebar.divider()

if st.sidebar.button("🚪 Wyloguj się", use_container_width=True):
    st.query_params.clear()
    st.session_state.clear()
    st.rerun()

st.sidebar.caption(f"v{APP_VERSION}")
# --- 7. POWTÓRKI & TRENING (Wersja z obsługą Auto-Audio) ---
if choice in ["📅 Powtórki", "🚀 Trening"]:
    is_r = (choice == "📅 Powtórki")
    st.header(choice)
    
    # 0. Pobieranie ustawień z bazy
    user_settings = st.session_state.user_data.get("settings", {})
    auto_audio = user_settings.get("auto_audio", True)
    
    # 1. Filtrowanie tagów
    all_tags = set()
    for c in st.session_state.flashcards:
        all_tags.update([t.strip() for t in str(c.get('category','')).split(',') if t.strip()])
    
    sel_tag = st.selectbox("Zakres:", ["Wszystkie"] + sorted(list(all_tags)), key="sel_tag_rep")

    # 2. Inicjalizacja listy
    if "cur_list" not in st.session_state or st.session_state.get("last_tag") != sel_tag:
        pool = [c for c in st.session_state.flashcards if (sel_tag == "Wszystkie" or sel_tag in str(c.get('category','')))]
        if is_r:
            pool = [c for c in pool if str(c.get("next_review", date.today())) <= str(date.today())]
        random.shuffle(pool)
        st.session_state.cur_list = pool
        st.session_state.n_idx = 0
        st.session_state.last_tag = sel_tag
        st.session_state.n_m = "ask"

    cards = st.session_state.cur_list
    
    if not cards:
        st.success("Pusto! 🎉 Wszystko powtórzone.")
    elif st.session_state.n_idx >= len(cards):
        st.balloons()
        st.success("Koniec sesji! 🏆")
        if st.button("Zacznij od nowa"):
            del st.session_state.cur_list
            st.rerun()
    else:
        # --- SILNIK POWTÓREK (FRAGMENT) ---
        @st.fragment
        def flashcard_engine():
            idx = st.session_state.n_idx
            c = cards[idx]
            
            # Pasek postępu
            st.progress(idx / len(cards))
            st.caption(f"Słówko {idx + 1} z {len(cards)}")

            # Karta (Niemiecki)
            st.markdown(f'''
                <div style="font-size:3em; text-align:center; padding:30px; 
                background: #111; border:3px solid #1E88E5; border-radius:20px; margin-bottom:10px; color: white;">
                    {c["de"]}
                </div>
            ''', unsafe_allow_html=True)

            if st.session_state.n_m == "ask":
                with st.form(key=f"f_{idx}", clear_on_submit=True):
                    u_in = st.text_input("Tłumaczenie (PL):")
                    if st.form_submit_button("Sprawdź", use_container_width=True):
                        st.session_state.u_a = u_in
                        st.session_state.n_m = "res"
                        st.rerun(scope="fragment")
            else:
                # Widok odpowiedzi
                is_correct = normalize_text(st.session_state.u_a) == normalize_text(c['pl'])
                if is_correct:
                    st.success(f"✅ Dobrze: {c['pl']}")
                else:
                    st.error(f"❌ Poprawnie: {c['pl']}")
                
                # Przykłady i audio
                exs = c.get("examples", [])
                fex = exs[0].get("de") if exs and isinstance(exs, list) and len(exs) > 0 else None
                if fex:
                    st.info(f"💡 {fex}\n\n({exs[0].get('pl','')})")
                    if auto_audio:
                        play_audio(c['de'], fex)
                else:
                    if auto_audio:
                        play_audio(c['de'])

                if not auto_audio:
                    if st.button("🔊 Odsłuchaj", use_container_width=True):
                        play_audio(c['de'], fex) if fex else play_audio(c['de'])

                # Oceny SRS lub przycisk Dalej
                if is_r:
                    st.write("Jak oceniasz trudność?")
                    col1, col2, col3 = st.columns(3)
                    d = None
                    if col1.button("🔴 Trudne"): d = 1
                    if col2.button("🟡 Średnie"): d = 3
                    if col3.button("🟢 Łatwe"): d = 7
                    
                    if d:
                        update_word(c['id'], {"next_review": str(date.today() + timedelta(days=d))})
                        st.session_state.n_idx += 1
                        st.session_state.n_m = "ask"
                        st.rerun(scope="fragment")
                else:
                    if st.button("Następne ➡️", use_container_width=True):
                        st.session_state.n_idx += 1
                        st.session_state.n_m = "ask"
                        st.rerun(scope="fragment")

        flashcard_engine()

# --- 8. QUIZ (V231 - Fix błędu zapisu SRS) ---
elif choice == "🕹️ Quiz":
    st.header("🕹️ Quiz")
    
    all_c = st.session_state.flashcards
    user_settings = st.session_state.user_data.get("settings", {})
    show_hints = user_settings.get("show_hints", True)
    auto_audio = user_settings.get("auto_audio", True)
    
    if len(all_c) < 4: 
        st.warning("Dodaj min. 4 słówka, aby uruchomić quiz.")
    else:
        @st.fragment
        def quiz_engine():
            if "q_c" not in st.session_state:
                idx = random.randrange(len(all_c))
                t = all_c[idx]
                other_pls = [x['pl'] for x in all_c if x['pl'] != t['pl']]
                distractors = random.sample(other_pls, min(3, len(other_pls)))
                opts = distractors + [t['pl']]
                random.shuffle(opts)
                
                st.session_state.update({
                    "q_c": t, "q_a": t['pl'], "q_o": opts, "q_s": "ask", "u_q": None
                })

            q_c = st.session_state.q_c
            st.write(f"### Jak przetłumaczysz: **{q_c['de']}**")
            
            if st.session_state.q_s == "ask":
                if show_hints:
                    first_letter = st.session_state.q_a[0].upper()
                    st.caption(f"💡 Podpowiedź: Polskie słowo zaczyna się na literę **{first_letter}**...")

                for o in st.session_state.q_o:
                    if st.button(o, key=f"btn_{o}", use_container_width=True):
                        st.session_state.u_q = o
                        st.session_state.q_s = "res"
                        st.rerun(scope="fragment")
            else:
                is_correct = st.session_state.u_q == st.session_state.q_a
                
                # --- LOGIKA AKTUALIZACJI SRS Z ZABEZPIECZENIEM ---
                try:
                    word_id = q_c['id']
                    if is_correct:
                        st.success("✅ Świetnie! (Słówko przesunięte o +2 dni)")
                        new_date = str(date.today() + timedelta(days=2))
                        # Używamy jawnego int() dla pewności
                        update_word(word_id, {"next_review": new_date})
                    else:
                        st.error(f"❌ Poprawnie: **{st.session_state.q_a}** (Słówko wraca do powtórek)")
                        # Wysyłamy level jako jawny Integer
                        update_word(word_id, {"next_review": str(date.today()), "level": int(0)})
                    
                    # Odświeżamy dane lokalne, by zmiany były widoczne od razu w sesji
                    st.session_state.flashcards = load_flashcards(u)
                except Exception as e:
                    st.warning(f"⚠️ Problem z zapisem SRS: {e}")
                # ------------------------------------------------

                exs = q_c.get("examples", [])
                fex_de = exs[0].get("de") if exs and isinstance(exs, list) and len(exs) > 0 else None
                fex_pl = exs[0].get("pl") if fex_de else None
                
                if fex_de:
                    st.info(f"💡 Przykład: **{fex_de}**" + (f"\n\n🇵🇱 *{fex_pl}*" if show_hints and fex_pl else ""))
                    if auto_audio: play_audio(q_c['de'], fex_de)
                else:
                    if auto_audio: play_audio(q_c['de'])
                
                if not auto_audio:
                    if st.button("🔊 Odsłuchaj wymowę", use_container_width=True):
                        play_audio(q_c['de'], fex_de) if fex_de else play_audio(q_c['de'])

                if st.button("Następne pytanie ➡️", use_container_width=True, type="primary"):
                    for key in ["q_c", "q_a", "q_o", "q_s", "u_q"]:
                        if key in st.session_state: del st.session_state[key]
                    st.rerun(scope="fragment")

        quiz_engine()
# --- 9. FISZKI (Wersja z obsługą Auto-Audio) ---
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

# --- 10. TESTY (Wersja ULTRA FAST z st.fragment) ---
elif choice == "📝 Testy":
    st.header("📝 Test")
    
    if len(st.session_state.flashcards) < 5:
        st.warning("Dodaj min. 5 słówek, aby wygenerować test.")
    else:
        # Etap 1: Konfiguracja testu (poza fragmentem, aby przycisk "Generuj" działał globalnie)
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
            # Etap 2: Silnik testu jako FRAGMENT
            @st.fragment
            def test_engine():
                qs = st.session_state.test_q
                t_idx = st.session_state.test_idx
                
                if t_idx < len(qs):
                    q = qs[t_idx]
                    
                    # Pasek postępu testu
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
                        # Obsługa pytań otwartych wewnątrz fragmentu
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
                    # Podsumowanie wyników (koniec fragmentu)
                    score, total = st.session_state.test_score, len(qs)
                    perc = round((score/total)*100) if total > 0 else 0
                    
                    st.markdown(f'''
                        <div style="text-align:center; padding:30px; border-radius:20px; 
                        background:#111; border:3px solid #1E88E5; margin-bottom:20px;">
                            <h1 style="margin:0;">Wynik: {score}/{total}</h1>
                            <h2 style="color:#1E88E5; margin:0;">{perc}%</h2>
                        </div>
                    ''', unsafe_allow_html=True)
                    
                    # Tabela z odpowiedziami (podgląd błędów)
                    with st.expander("📝 Zobacz szczegóły odpowiedzi"):
                        for i, q_res in enumerate(qs):
                            u_a = q_res.get('user_ans', 'Brak')
                            c_a = q_res.get('correct', '')
                            is_ok = normalize_text(u_a) == normalize_text(c_a)
                            st.write(f"**{i+1}.** {q_res.get('sentence')} -> {'✅' if is_ok else '❌'}")
                            if not is_ok:
                                st.caption(f"Twoja: {u_a} | Poprawna: {c_a}")

                    if st.button("Zakończ i zapisz do statystyk", use_container_width=True, type="primary"):
                        st.session_state.user_data["test_history"].append({
                            "date": datetime.now().strftime("%d.%m %H:%M"), 
                            "score": score, "total": total, "perc": perc
                        })
                        save_user_data(u, st.session_state.user_data)
                        del st.session_state.test_q # Resetuje test i wychodzi z fragmentu
                        st.rerun()

            # Uruchomienie silnika testu
            test_engine()

# --- 11. MEMORY GAME (V228 - Zabezpieczony zapis wyników) ---
elif choice == "🧠 Memory":
    st.header("🧠 Memory: Znajdź pary")
    st.write("Połącz niemieckie słówka z ich polskimi odpowiednikami. Liczy się czas!")

    # 1. INICJALIZACJA STANU GRY
    if "mem_grid" not in st.session_state:
        if len(st.session_state.flashcards) < 6:
            st.warning("Dodaj przynajmniej 6 słówek, aby móc zagrać.")
            st.stop()
        
        cards_pool = random.sample(st.session_state.flashcards, 6)
        grid = []
        for c in cards_pool:
            grid.append({"id": c["id"], "text": c["de"], "type": "de"})
            grid.append({"id": c["id"], "text": c["pl"], "type": "pl"})
        
        random.shuffle(grid)
        st.session_state.mem_grid = grid
        st.session_state.mem_status = ["hidden"] * 12
        st.session_state.mem_first = None
        st.session_state.mem_pairs = 0
        st.session_state.mem_start_time = None
        st.session_state.mem_final_time = None

    # 2. SILNIK GRY (FRAGMENT)
    @st.fragment
    def memory_engine():
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
                
                # BEZPIECZNY ZAPIS DO BAZY
                try:
                    db = get_db()
                    new_score = st.session_state.mem_final_time
                    # Pobieramy obecne wyniki (jeśli kolumna nie istnieje, get zwróci [])
                    current_scores = st.session_state.user_data.get("memory_scores", [])
                    if not isinstance(current_scores, list): current_scores = []
                    
                    current_scores.append(new_score)
                    current_scores = sorted([float(s) for s in current_scores])[:10]
                    
                    # Próba aktualizacji bazy
                    db.table("user_data").update({"memory_scores": current_scores}).eq("username", u).execute()
                    st.session_state.user_data["memory_scores"] = current_scores
                except Exception as e:
                    # Jeśli baza wyrzuci błąd (np. brak kolumny), nie crashujemy apki
                    st.warning("⚠️ Nie udało się zapisać rekordu w bazie (prawdopodobnie brak kolumny memory_scores).")
                    # Zapisujemy chociaż lokalnie w sesji na ten czas
                    st.session_state.user_data["memory_scores"] = current_scores

            st.balloons()
            st.success(f"Brawo! Twój czas: {st.session_state.mem_final_time}s")
            if st.button("Zagraj jeszcze raz", use_container_width=True):
                for k in ["mem_grid", "mem_status", "mem_first", "mem_pairs", "mem_start_time", "mem_final_time"]:
                    if k in st.session_state: del st.session_state[k]
                st.rerun(scope="fragment")
            return

        st.write("---")

        # RENDEROWANIE PRZYCISKÓW
        for row in range(3):
            cols = st.columns(4)
            for col in range(4):
                idx = row * 4 + col
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

        # SPRAWDZANIE PAR (opóźnienie ukrycia)
        flipped = [i for i, s in enumerate(status) if s == "flipped"]
        if len(flipped) == 2:
            idx1, idx2 = flipped
            time.sleep(0.8) # Czekamy chwilę, żeby użytkownik zobaczył drugą kartę
            
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

    if st.button("Wygeneruj nową tablicę", type="secondary", use_container_width=True):
        for k in ["mem_grid", "mem_status", "mem_first", "mem_pairs", "mem_start_time", "mem_final_time"]:
            if k in st.session_state: del st.session_state[k]
        st.rerun()

# --- 12. WARSZTAT SŁÓWEK (ANALIZA BŁĘDÓW - ULTRA FAST) ---
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

# --- 13. ARENA WYZWAŃ (V227 - Pełny Ranking z Fixem) ---
elif choice == "🏆 Arena Wyzwań":
    st.header("🏆 Arena Wyzwań")
    st.write("Sprawdź, jak wypadasz na tle innych użytkowników!")

    db = get_db()
    
    # 1. BEZPIECZNE POBIERANIE DANYCH
    try:
        # Pobieramy wszystko (*), aby nie wywaliło błędu przy braku kolumny memory_scores
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
                strong = len([r for r in u_cards["next_review"] if (pd.to_datetime(r).date() - today).days > 6])
                wiedza_val = int((strong / len(u_cards)) * 100)
            
            # Pobieranie najlepszego czasu Memory
            m_scores = user.get("memory_scores", [])
            best_mem = None
            if m_scores and isinstance(m_scores, list) and len(m_scores) > 0:
                try:
                    best_mem = min([float(s) for s in m_scores])
                except:
                    best_mem = None

            ranking_data.append({
                "Użytkownik": uname.capitalize(),
                "Ogień 🔥": user.get("streak", 0),
                "Wiedza 🧠": wiedza_val,
                "Najlepsze Memory ⏱️": best_mem,
                "Ostatnio aktywny": user.get("last_seen", "Brak")
            })

        df_final = pd.DataFrame(ranking_data)

        # 3. WYŚWIETLANIE TABEL
        
        # --- Rząd 1: Passa i Wiedza ---
        col1, col2 = st.columns(2)

        with col1:
            st.subheader("🔥 Najdłuższa Passa")
            top_streak = df_final.sort_values(by="Ogień 🔥", ascending=False).head(5)
            # Resetujemy indeks, aby ranking zaczynał się od 1
            top_streak = top_streak.reset_index(drop=True)
            top_streak.index += 1
            st.table(top_streak[["Użytkownik", "Ogień 🔥"]])

        with col2:
            st.subheader("🧠 Mistrzowie Wiedzy")
            top_knowledge = df_final.sort_values(by="Wiedza 🧠", ascending=False).head(5)
            top_knowledge = top_knowledge.reset_index(drop=True)
            top_knowledge.index += 1
            # Dodajemy znak % do wyświetlania
            display_knowledge = top_knowledge[["Użytkownik", "Wiedza 🧠"]].copy()
            display_knowledge["Wiedza 🧠"] = display_knowledge["Wiedza 🧠"].apply(lambda x: f"{x}%")
            st.table(display_knowledge)

        st.write("---")

        # --- Rząd 2: Globalny Ranking Memory (Top 10) ---
        st.subheader("🧩 Mistrzowie Pamięci (Memory Top 10)")
        df_mem = df_final.dropna(subset=["Najlepsze Memory ⏱️"])
        
        if not df_mem.empty:
            df_mem_sorted = df_mem.sort_values(by="Najlepsze Memory ⏱️", ascending=True).head(10)
            df_mem_sorted = df_mem_sorted.reset_index(drop=True)
            df_mem_sorted.index += 1
            
            # Formatowanie czasu na sekundy
            display_mem = df_mem_sorted[["Użytkownik", "Najlepsze Memory ⏱️"]].copy()
            display_mem["Najlepsze Memory ⏱️"] = display_mem["Najlepsze Memory ⏱️"].apply(lambda x: f"{x}s")
            
            st.table(display_mem)
        else:
            st.info("Nikt jeszcze nie ustanowił rekordu w Memory. Bądź pierwszy!")

        st.divider()
        
        # 4. TWOJA POZYCJA W RANKINGU OGNIA
        # Sortujemy wg ognia, żeby sprawdzić pozycję
        df_pos = df_final.sort_values(by="Ogień 🔥", ascending=False).reset_index(drop=True)
        # Szukamy siebie (u to nazwa użytkownika z sesji)
        try:
            my_rank = df_pos[df_pos["Użytkownik"] == u.capitalize()].index[0] + 1
            st.info(f"Twoja aktualna pozycja w rankingu ogólnym: **{my_rank}** na **{len(df_final)}** użytkowników. Powodzenia!")
        except:
            pass

# --- 14. GENERATOR ---
elif choice == "📦 Generator słów":
    st.header("📦 Generator")
    
    # --- WYŚWIETLANIE WYNIKÓW PO OSTATNIM GENEROWANIU ---
    if "last_generated" in st.session_state:
        st.success(f"🎉 Pomyślnie wygenerowano i dodano {len(st.session_state.last_generated)} nowych słówek!")
        
        # Tabela ze spisem dodanych słówek (teraz pokazuje też tagi)
        df_new = pd.DataFrame(st.session_state.last_generated)
        st.dataframe(df_new, use_container_width=True, hide_index=True)
        
        if st.button("Ukryj listę", use_container_width=True):
            del st.session_state.last_generated
            st.rerun()
            
        st.write("---")
    # ----------------------------------------------------

    cols = st.columns(5)
    for i, lvl in enumerate(["A1", "A2", "B1", "B2", "C1"]):
        if cols[i].button(lvl, use_container_width=True, key=f"gen_btn_{lvl}"):
            with st.spinner(f"AI pobiera i analizuje słówka dla poziomu {lvl}... To potrwa kilka sekund."):
                try:
                    # Pobieranie bazy i odfiltrowanie już posiadanych
                    res_lib = get_db().table("vocab_library").select("word").eq("level", lvl).execute()
                    my_w = [x['de'].lower() for x in st.session_state.flashcards]
                    avail = [w['word'] for w in res_lib.data if w['word'].lower() not in my_w]
                    
                    if not avail:
                        st.warning(f"Masz już wszystkie słówka z poziomu {lvl} w swojej bazie!")
                        st.stop()
                        
                    sel = random.sample(avail, min(25, len(avail)))
                    
                    # Generowanie danych przez AI - wymuszamy generowanie tematyki i części mowy
                    prompt = f"Przetłumacz i otaguj słowa: {sel}. Dodaj minimum 2 tagi (część mowy oraz kategoria tematyczna). Zwróć wynik TYLKO w formacie JSON: {{\"flashcards\": [{{ \"de\":\"...\", \"pl\":\"...\", \"category\":\"Rzeczownik, Dom\", \"examples\":[{{ \"de\":\"...\", \"pl\":\"...\" }}] }}]}}"
                    
                    raw_res = get_openai_response(prompt)
                    raw_res = raw_res.replace("```json", "").replace("```", "").strip()
                    data = json.loads(raw_res)
                    
                    flashcards_data = data.get("flashcards", data.get("words", []))
                    
                    insert_payload = []
                    display_list = [] # Do wyświetlenia użytkownikowi
                    
                    for w in flashcards_data:
                        # 1. Pobieramy tagi od AI
                        raw_cat = w.get("category", "")
                        
                        # 2. Rozbijamy, czyścimy ze spacji i zmieniamy z małych na duże litery (np. rzeczownik -> Rzeczownik)
                        tags = [t.strip().capitalize() for t in str(raw_cat).split(",") if t.strip()]
                        
                        # 3. Usuwamy złośliwe/pomieszane poziomy, które mogło dodać AI
                        clean_tags = [t for t in tags if t.upper() not in ["A1", "A2", "B1", "B2", "C1"]]
                        
                        # 4. Twardo doklejamy wciśnięty na przycisku poziom
                        clean_tags.append(lvl)
                        final_cat = ", ".join(clean_tags)
                        
                        card = {
                            "username": u,
                            "de": w.get("de", ""),
                            "pl": w.get("pl", ""),
                            "category": final_cat,
                            "examples": w.get("examples", []),
                            "next_review": str(date.today()),
                            "origin": "Generator"
                        }
                        insert_payload.append(card)
                        display_list.append({
                            "Niemiecki (DE)": card["de"], 
                            "Polski (PL)": card["pl"],
                            "Tagi": final_cat
                        })
                    
                    if insert_payload:
                        # Jedno zapytanie do bazy (Ogromny skok wydajności w komunikacji z Supabase)
                        get_db().table("flashcards").insert(insert_payload).execute()
                        
                        added = len(insert_payload)
                        st.session_state.user_data["historical_cost"] += (added * 0.005) 
                        save_user_data(u, st.session_state.user_data)
                        
                        # Aktualizacja lokalnej bazy
                        st.session_state.flashcards = load_flashcards(u)
                        
                        # Zapisanie listy do sesji, aby przetrwała st.rerun()
                        st.session_state.last_generated = display_list
                        st.rerun()
                    else:
                        st.error("AI zwróciło pustą odpowiedź. Spróbuj kliknąć jeszcze raz.")
                        
                except Exception as e: 
                    st.error(f"Wystąpił błąd podczas pracy AI: {e}")

# --- 15. SKANER AI ---
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
                        # Pobieramy obecne niemieckie słówka z bazy (małe litery, bez spacji), by filtrować duble
                        existing_de = {str(w.get('de', '')).lower().strip() for w in st.session_state.flashcards}
                        
                        image = Image.open(img_to_process)
                        
                        # Wzmocniony i bardzo precyzyjny prompt
                        prompt = """
                        Przeanalizuj zdjęcie. Znajdź na nim niemieckie słówka, wyrażenia lub fragmenty notatek.
                        Dla każdego znalezionego pojęcia:
                        1. Podaj poprawny niemiecki (z rodzajnikiem dla rzeczowników).
                        2. Podaj polskie tłumaczenie. 
                        3. MUSISZ wygenerować dokładnie 3 tagi, rozdzielone przecinkami: część mowy, kategoria tematyczna oraz przewidywany poziom CEFR (np. "Rzeczownik, Dom, A1").
                        4. BEZWZGLĘDNIE wygeneruj 1 naturalne zdanie przykładowe po niemiecku z jego polskim tłumaczeniem. Każde słowo musi mieć przykład!
                        Zwróć TYLKO JSON w formacie: {"flashcards": [{"de": "...", "pl": "...", "category": "...", "examples": [{"de": "...", "pl": "..."}]}]}
                        """
                        
                        raw_res = get_openai_response(prompt, img_obj=image)
                        raw_res = raw_res.replace("```json", "").replace("```", "").strip()
                        data = json.loads(raw_res)
                        
                        items = data.get("flashcards", data.get("words", []))
                        
                        if items:
                            # Logika odrzucania duplikatów
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
                                    st.toast(f"ℹ️ Pominięto {skipped_count} słówek (znajdują się już w Twojej bazie).")
                                st.rerun()
                            else:
                                st.warning(f"AI znalazło na zdjęciu słówka (łącznie: {len(items)}), ale wszystkie masz już w swoim słowniku!")
                        else:
                            st.warning("Nie znaleziono czytelnych słówek na zdjęciu.")
                            
                    except Exception as e:
                        st.error(f"Błąd analizy AI: {e}")

    # --- WIDOK 2: EDYCJA I WERYFIKACJA ---
    else:
        st.subheader("📝 Zweryfikuj i edytuj nowe słówka przed dodaniem")
        st.info("Pominięto duplikaty. Sprawdź, czy AI poprawnie wygenerowało przykłady i tagi (w tym poziomy).")

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
                    new_cat = c3.text_input("Tagi (z poziomami)", item.get('category', ''), key=f"sc_cat_{i}")
                    
                    if c4.button("🗑️", key=f"sc_del_{i}", help="Usuń słowo z listy do dodania"):
                        to_delete = i

                    # Podgląd przykładowego zdania
                    examples = item.get('examples', [])
                    if examples and len(examples) > 0:
                        ex_de = examples[0].get('de', '')
                        ex_pl = examples[0].get('pl', '')
                        st.caption(f"💡 Przykład: **{ex_de}** (*{ex_pl}*)")
                    else:
                        st.caption("⚠️ Brak wygenerowanego przykładu dla tego słówka.")

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

            if col_act2.button("✅ Zapisz wybrane słówka", type="primary", use_container_width=True):
                with st.spinner("Zapisywanie słówek do chmury..."):
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
                        
                        # Aktualizacja lokalnego stanu
                        st.session_state.flashcards = load_flashcards(u)
                        st.session_state.user_data["historical_cost"] += 0.05
                        save_user_data(u, st.session_state.user_data)
                        
                        count = len(insert_payload)
                        del st.session_state.temp_scanned
                        st.session_state.scan_msg = f"✅ Gotowe! Pomyślnie dodano {count} zweryfikowanych słówek do Twojej bazy."
                        st.rerun()
                    else:
                        st.error("Wszystkie pola słówek są puste. Nie zapisano danych.")

        review_scanned_items()

# --- 16. DODAJ SŁÓWKO ---
elif choice == "➕ Dodaj":
    st.header("➕ Dodaj Słówko")
    
    t1, t2 = st.tabs(["✍️ Wpisz ręcznie", "🤖 Asystent AI"])

    with t1:
        # Fragment dla formularza ręcznego
        @st.fragment
        def manual_add_ui():
            with st.form("manual_entry_form", clear_on_submit=True):
                col1, col2 = st.columns(2)
                de = col1.text_input("Słowo Niemieckie (DE):", placeholder="np. die Katze")
                pl = col2.text_input("Tłumaczenie Polskie (PL):", placeholder="np. kot")
                ca = st.text_input("Tagi / Kategorie (opcjonalnie):", placeholder="np. Rzeczownik, Zwierzęta, A1")

                submitted = st.form_submit_button("💾 Zapisz do bazy", use_container_width=True, type="primary")

                if submitted:
                    if de.strip() and pl.strip():
                        save_word(u, {
                            "de": de.strip(),
                            "pl": pl.strip(),
                            "category": ca.strip(),
                            "next_review": str(date.today()),
                            "origin": "Dodaj"
                        })
                        st.session_state.flashcards = load_flashcards(u)
                        st.toast(f"✅ Dodano: {de}", icon="📥")
                        st.success(f"Pomyślnie zapisano: **{de}** — *{pl}*")
                    else:
                        st.error("Musisz podać przynajmniej słowo niemieckie i jego tłumaczenie!")
        manual_add_ui()

    with t2:
        # Fragment dla Asystenta AI
        @st.fragment
        def ai_add_ui():
            with st.form("ai_entry_form", clear_on_submit=True):
                st.info("Wpisz polskie słowo, a AI znajdzie odpowiednik z rodzajnikiem, określi poziom, doda tagi i wygeneruje zdanie przykładowe!")
                pl_word = st.text_input("Co chcesz przetłumaczyć i dodać?", placeholder="np. latarnia morska, zachód słońca...")
                
                submitted_ai = st.form_submit_button("✨ Magicznie wygeneruj i dodaj", use_container_width=True, type="primary")
                
                if submitted_ai:
                    if pl_word.strip():
                        with st.spinner("AI analizuje i tworzy fiszkę..."):
                            try:
                                prompt = f"Przetłumacz polskie słowo lub wyrażenie '{pl_word.strip()}' na język niemiecki. Zawsze podawaj niemieckie rzeczowniki z odpowiednim rodzajnikiem (der, die, das). Określ docelowy poziom CEFR (A1-C1). Utwórz 2-3 tagi (w tym część mowy i kategorię tematyczną). Utwórz 1 naturalne i poprawne zdanie przykładowe z tym słowem. Zwróć wynik TYLKO jako czysty JSON: {{\"de\":\"...\", \"pl\":\"...\", \"category\":\"Rzeczownik, Natura, B2\", \"examples\":[{{\"de\":\"...\", \"pl\":\"...\"}}]}}"
                                
                                raw_res = get_openai_response(prompt)
                                raw_res = raw_res.replace("```json", "").replace("```", "").strip()
                                data = json.loads(raw_res)
                                
                                card = {
                                    "de": data.get("de", ""),
                                    "pl": data.get("pl", pl_word.strip()),
                                    "category": data.get("category", ""),
                                    "examples": data.get("examples", []),
                                    "next_review": str(date.today()),
                                    "origin": "Dodaj (AI)"
                                }
                                
                                # Zapis do bazy i aktualizacja kosztów
                                save_word(u, card)
                                st.session_state.user_data["historical_cost"] += 0.003
                                save_user_data(u, st.session_state.user_data)
                                
                                # Aktualizacja lokalnej listy
                                st.session_state.flashcards = load_flashcards(u)
                                
                                st.toast("Magicznie dodano! ✨", icon="🤖")
                                st.success(f"Dodano: **{card['de']}** ➔ *{card['pl']}*")
                                st.caption(f"🏷️ Tagi: {card['category']}")
                                if card.get("examples") and len(card["examples"]) > 0:
                                    ex = card["examples"][0]
                                    st.info(f"💡 Przykład: **{ex.get('de', '')}**\n\n🇵🇱 {ex.get('pl', '')}")
                                
                            except Exception as e:
                                st.error(f"Wystąpił błąd podczas pracy AI: {e}. Spróbuj ponownie.")
                    else:
                        st.error("Wpisz najpierw polskie słowo!")
        ai_add_ui()
# --- 17. SŁOWNIK ---
elif choice == "📖 Słownik":
    st.header("📖 Słownik")
    
    # 1. Pobranie unikalnych tagów
    all_tags = set()
    for c in st.session_state.flashcards:
        all_tags.update([t.strip() for t in str(c.get('category','')).split(',') if t.strip()])
    
    # 2. Wyszukiwarka i filtry
    col1, col2 = st.columns([1, 2])
    f_tag = col1.selectbox("Filtruj kategorię:", ["Wszystkie"] + sorted(list(all_tags)))
    
    # Dodana instrukcja o klawiszu Enter dla jasności
    search = col2.text_input("Szukaj słowa (wciśnij ENTER ⏎):", placeholder="Wpisz fragment np. 'lam'...")
    
    # 3. Logika filtrowania (szuka fragmentu we wszystkich słowach PL i DE)
    filtered = [
        c for c in st.session_state.flashcards 
        if (f_tag == "Wszystkie" or f_tag in str(c.get('category',''))) 
        and (search.lower() in str(c.get('de','')).lower() or search.lower() in str(c.get('pl','')).lower())
    ]
    
    st.write("---")
    st.subheader(f"Znaleziono słówek: {len(filtered)}")
    
    # Zabezpieczenie przed wyrenderowaniem tysięcy formularzy, co zawiesiłoby stronę
    MAX_DISPLAY = 50
    if len(filtered) > MAX_DISPLAY:
        st.warning(f"Wyników jest bardzo dużo. Wyświetlam pierwsze {MAX_DISPLAY}. Użyj wyszukiwarki, aby doprecyzować.")
        display_list = filtered[:MAX_DISPLAY]
    else:
        display_list = filtered
        
    if not display_list:
        st.info("Brak słówek spełniających kryteria.")
        
    # 4. Wyświetlanie wyników w rozwijanych akordeonach
    for c in display_list:
        with st.expander(f"🇩🇪 {c['de']} ➔ 🇵🇱 {c['pl']}"):
            
            # Dodatkowe informacje ukryte pod słowem
            st.caption(f"🗓️ Następna powtórka: {c.get('next_review', 'Brak')} | 🏷️ Tagi: {c.get('category', 'Brak')}")
            
            # Przycisk Audio
            if st.button("🔊 Odsłuchaj wymowę", key=f"audio_{c['id']}", use_container_width=True):
                play_audio(c['de'])
            
            # Tryb Edycji (Bezpieczny formularz)
            with st.form(f"ed_{c['id']}"):
                n_de = st.text_input("Niemiecki (DE)", c['de'])
                n_pl = st.text_input("Polski (PL)", c['pl'])
                n_ca = st.text_input("Kategorie / Tagi", c.get('category',''))
                
                if st.form_submit_button("💾 Zapisz zmiany", use_container_width=True):
                    update_word(c['id'], {"de": n_de, "pl": n_pl, "category": n_ca})
                    st.session_state.flashcards = load_flashcards(u) # Synchronizacja lokalna
                    st.toast("Zmiany zapisane! ✅")
                    st.rerun()
                    
            # Usuwanie słówka z bazy
            if st.button("🗑️ Usuń to słówko", key=f"del_{c['id']}", type="primary", use_container_width=True):
                delete_word(c['id'])
                st.session_state.flashcards = load_flashcards(u) # Synchronizacja lokalna
                st.toast("Słówko usunięte! 🗑️")
                st.rerun()

# --- 18. STATYSTYKI (V225 - Z Rekordami Memory) ---
elif choice == "📊 Statystyki":
    st.header("📊 Twoje Statystyki")
    df = pd.DataFrame(st.session_state.flashcards)
    ud = st.session_state.user_data
    
    if not df.empty:
        # 1. Metryki główne (Wielkość bazy i Passa)
        c1, c2 = st.columns(2)
        c1.metric("Wielkość Bazy", len(df))
        c2.metric("Passa Nauki", f"{ud.get('streak', 0)} dni")
        
        st.write("---")

        # --- NOWOŚĆ: REKORDY MEMORY ---
        st.subheader("🏆 Moje Rekordy Memory")
        mem_scores = ud.get("memory_scores", [])
        
        if mem_scores:
            # Wybieramy top 3 najlepsze (najkrótsze) czasy
            top3 = sorted([float(s) for s in mem_scores])[:3]
            m_cols = st.columns(3)
            icons = ["🥇", "🥈", "🥉"]
            for i, score in enumerate(top3):
                m_cols[i].metric(f"{icons[i]} Miejsce", f"{score}s")
        else:
            st.info("Zagraj w Memory, aby ustanowić swój pierwszy rekord!")
        
        st.write("---")
        
        # 2. KOLUMNY: Czas nauki oraz Fazy zapamiętywania
        col_top1, col_top2 = st.columns(2)
        
        with col_top1:
            st.subheader("⏱️ Czas nauki (minuty)")
            time_stats = ud.get("time_stats", {})
            
            display_names = {
                "Pow": "Powtórki", "Trn": "Trening", "Qiz": "Quiz", 
                "Fis": "Fiszki", "Tst": "Testy", "Mem": "Memory",
                "War": "Warsztat", "Sta": "Statystyki"
            }
            
            nav_order = [
                "Powtórki", "Trening", "Quiz", "Fiszki", "Testy", "Memory", "Warsztat", "Statystyki", "Inne"
            ]
            
            aggregated_mins = {name: 0 for name in nav_order}
            for code, sec in time_stats.items():
                name = display_names.get(code, "Inne")
                if name in aggregated_mins:
                    aggregated_mins[name] += sec
            
            t_data = []
            for name in nav_order:
                mins = int(aggregated_mins[name] // 60)
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
                    
                    if diff <= 1: 
                        phase_counts["Słaba (1-2 dni)"] += 1
                    elif 2 <= diff <= 6: 
                        phase_counts["Średnia (3-6 dni)"] += 1
                    else: 
                        phase_counts["Silna (7+ dni)"] += 1
                except:
                    phase_counts["Słaba (1-2 dni)"] += 1
            
            p_list = [{"Faza": k, "Słówek": v} for k, v in phase_counts.items()]
            st.dataframe(pd.DataFrame(p_list), use_container_width=True, hide_index=True)

        st.write("---")
        
        # 3. Tabela z prognozą powtórek
        st.subheader("📅 Prognoza powtórek (kolejne 10 dni)")
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
                        if is_mastered:
                            level_mastered[lvl] += 1
            
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
                st.dataframe(origin_counts, use_container_width=True, hide_index=True)
        
    st.write("---")
    st.subheader("📝 Historia rozwiązanych testów")
    t_hist = ud.get("test_history", [])
    if t_hist:
        hist_df = pd.DataFrame(t_hist)[::-1]
        hist_df = hist_df[["date", "score", "total", "perc"]]
        hist_df.columns = ["Data", "Wynik", "Suma pytań", "Procent (%)"]
        st.dataframe(hist_df, use_container_width=True, hide_index=True)
    else:
        st.info("Brak rozwiązanych testów.")
# --- 19. KONTO ---
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

# --- 20. ADMIN PRO (V220 - Fix wyświetlania i mapowania) ---
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
    
    # Definiujemy kody DOKŁADNIE tak jak w CLEAN_TIME_LABELS z Sekcji 1
    # Dodajemy 'Arn' (Arena), bo choć trafia do Innych w tabeli, w bazie może już istnieć
    tracked_codes = ["Pow", "Trn", "Qiz", "Fis", "Tst", "Mem", "War", "Inn"]
    display_names = {
        "Pow": "Powtórki", "Trn": "Trening", "Qiz": "Quiz", 
        "Fis": "Fiszki", "Tst": "Testy", "Mem": "Memory", 
        "War": "Warsztat", "Inn": "Inne"
    }
    
    today = date.today()

    for user in ud_data:
        username = user["username"]
        user_cards = df_cards_all[df_cards_all["username"] == username]
        oc = user_cards["origin"].value_counts() if not user_cards.empty else {}
        
        # Wiedza
        strong_cards = 0
        if not user_cards.empty:
            # Pancerne rzutowanie na datę
            strong_cards = len([c for c in user_cards["next_review"] if (pd.to_datetime(c).date() - today).days > 6])
            wiedza_val = int((strong_cards / len(user_cards)) * 100)
        else:
            wiedza_val = 0

        # Czas użytkownika
        user_stats = user.get("time_stats", {})
        current_user_merged = {code: 0 for code in tracked_codes}
        total_sec = 0
        
        for raw_key, seconds in user_stats.items():
            k = str(raw_key).strip()
            # Sprawdzamy czy kod jest na naszej liście, jeśli nie -> Inn
            f_code = k if k in tracked_codes else "Inn"
            
            # Arenę zgodnie z Twoją prośbą zliczamy do Innych
            if f_code == "Arn": f_code = "Inn"
            
            current_user_merged[f_code] += seconds
            total_sec += seconds
            global_time[f_code] = global_time.get(f_code, 0) + seconds

        # Formatowanie danych
        raw_seen = user.get("last_seen", "Brak")
        formatted_seen = raw_seen.replace(" ", "  |  ") if " " in raw_seen else raw_seen
        
        # Pancerne pobieranie wartości z origin counts
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
        st.subheader("📋 Podsumowanie")
        
        # TABELA 1: GŁÓWNA
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
        
        # TABELA 2: SZCZEGÓŁOWA
        with st.expander("🔍 Szczegółowy podział czasu (minuty)"):
            detail_rows = []
            # Wybieramy tylko te kody, które mają przypisane nazwy w display_names
            valid_codes = [c for c in tracked_codes if c in display_names]
            
            for _, row in df_admin.iterrows():
                d_row = {"Użytkownik": row["Użytkownik"]}
                for code in valid_codes:
                    d_row[display_names[code]] = int(row["__raw_stats"][code] // 60)
                detail_rows.append(d_row)
            
            st.dataframe(pd.DataFrame(detail_rows), use_container_width=True, hide_index=True)

        # WYKRES
        if global_time:
            st.write("---")
            chart_data = {display_names.get(k, k): int(v // 60) for k, v in global_time.items() if (v // 60) > 0}
            if chart_data:
                fig = go.Figure(data=[go.Bar(
                    x=list(chart_data.keys()), y=list(chart_data.values()), 
                    marker_color='#FF5252', text=list(chart_data.values()), textposition='auto'
                )])
                fig.update_layout(template="plotly_dark", height=300, margin=dict(l=10, r=10, t=30, b=10), title="Globalne minuty")
                st.plotly_chart(fig, use_container_width=True)
