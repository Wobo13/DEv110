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

# --- 3. FUNKCJE DANYCH (SUPABASE) (V232 - Pancerna aktualizacja słów) ---
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

# --- POPRAWIONA FUNKCJA UPDATE_WORD ---
def update_word(word_id, fields):
    try:
        # Zabezpieczenie typów danych dla bazy (BigInt/Integer)
        if "level" in fields and fields["level"] is not None:
            fields["level"] = int(fields["level"])
        
        if "interval" in fields and fields["interval"] is not None:
            fields["interval"] = int(fields["interval"])

        # Wykonanie aktualizacji
        get_db().table("flashcards").update(fields).eq("id", word_id).execute()
    except Exception as e:
        # Logujemy błąd do konsoli Streamlit, ale nie przerywamy działania aplikacji
        st.error(f"⚠️ Błąd krytyczny bazy danych (update_word): {e}")

def delete_word(word_id): 
    get_db().table("flashcards").delete().eq("id", word_id).execute()

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

# --- 6. SIDEBAR (V287 - Kompaktowy & Naprawiony) ---
with st.sidebar:
    # 1. Nagłówek: Nazwa Wielką Literą + Streak w jednej linii
    user_display = str(u).capitalize()
    streak = st.session_state.user_data.get('streak', 0)
    
    st.markdown(f"""
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 5px;">
            <h2 style="margin:0;">👤 {user_display}</h2>
            <span style="font-size: 1.2em;">🔥 {streak}d</span>
        </div>
    """, unsafe_allow_html=True)

    # 2. Obliczanie statystyk (Wiedza i Cel)
    # Wiedza (🧠 %)
    all_c = st.session_state.flashcards
    wiedza_perc = 0
    if all_c:
        strong = len([c for c in all_c if (pd.to_datetime(c.get('next_review', date.today())).date() - date.today()).days > 6])
        wiedza_perc = int((strong / len(all_c)) * 100)
    
    # Cel (Realna nauka - minuty)
    study_modules = ["Pow", "Trn", "Qiz", "Fis", "Tst", "Mem", "War"]
    current_stats = st.session_state.user_data.get("time_stats", {})
    study_seconds = sum(current_stats.get(code, 0) for code in study_modules)
    study_minutes = int(study_seconds // 60)
    daily_goal = st.session_state.user_data.get("settings", {}).get("daily_goal", 20)
    
    # 3. Wyświetlanie pasków postępu
    st.caption(f"🧠 Wiedza: {wiedza_perc}%")
    st.progress(wiedza_perc / 100)
    
    st.caption(f"🎯 Cel: {study_minutes}/{daily_goal}m")
    goal_progress = min(study_minutes / daily_goal, 1.0)
    st.progress(goal_progress)
    
    if study_minutes >= daily_goal:
        st.markdown("<p style='color: #4CAF50; font-size: 0.8em; margin-top: -10px; font-weight: bold;'>✅ Cel na dziś osiągnięty!</p>", unsafe_allow_html=True)

    st.markdown("<hr style='margin: 10px 0;'>", unsafe_allow_html=True)

    # 4. MENU (Nawigacja)
    menu_options = [
        "🏠 Start", "📅 Powtórki", "🚀 Trening", "🕹️ Quiz", "🎴 Fiszki", 
        "📝 Testy", "🧠 Memory", "🛠️ Warsztat", "🏆 Arena Wyzwań",
        "📦 Generator słów", "📸 Skaner AI", "➕ Dodaj", "📖 Słownik", 
        "📊 Statystyki", "⚙️ Moje Konto"
    ]
    
    # Panel Admina tylko dla uprawnionych
    if u == ADMIN_USER:
        menu_options.append("👑 Admin")

    # Radio button bez widocznego napisu "Menu", by zaoszczędzić miejsce
    choice = st.radio("Menu", menu_options, label_visibility="collapsed")
    
    st.markdown("<hr style='margin: 10px 0;'>", unsafe_allow_html=True)
    
    # Przycisk wylogowania
    if st.button("🚪 Wyloguj się", use_container_width=True):
        st.session_state.clear()
        st.rerun()

    # Stopka z wersją
    st.caption(f"{APP_VERSION}")

# --- KONIEC SEKCJI 6 (Wszystkie bloki 'with' zamknięte) ---

# --- 7. START (V1.2 - Centrum Dowodzenia) ---
update_activity(choice)

if choice == "🏠 Start":
    st.header(f"Guten Morgen, {str(u).capitalize()}! ☀️")
    
    # 1. ANALIZA DANYCH BIEŻĄCYCH
    all_c = st.session_state.flashcards
    today_str = str(date.today())
    
    # Statystyki do podsumowania
    total_words = len(all_c)
    to_review = len([c for c in all_c if str(c.get("next_review", today_str)) <= today_str])
    
    # 2. UKŁAD KAFELKÓW (WIZUALNE PODSUMOWANIE)
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("Słówek w bazie", total_words)
    with col2:
        st.metric("Powtórki na dziś", to_review, delta=-to_review if to_review > 0 else None, delta_color="inverse")
    with col3:
        goal_min = st.session_state.user_data.get("settings", {}).get("daily_goal", 20)
        st.metric("Twój cel", f"{goal_min} min")

    st.write("---")

    # 3. BRIEFING PORANNY
    c1, c2 = st.columns(2)
    
    with c1:
        st.markdown("### 📊 Twój status")
        if to_review > 0:
            st.warning(f"Masz **{to_review}** słówek do powtórzenia. System SRS czeka!")
        else:
            st.success("Wszystkie powtórki na dziś wykonane. Możesz dodać nowe słówka!")
        
        # Prosta motywacja oparta na wielkości bazy
        if total_words < 50:
            st.info("🌱 Twoja baza rośnie! Dodaj jeszcze kilka słówek, aby odblokować pełny potencjał Quizów.")
        elif total_words > 200:
            st.info("🌳 Imponująca kolekcja! Pamiętaj o regularnych powtórkach, by nie zapomnieć starszych słów.")

    with c2:
        st.markdown("### 🏆 Zadania na dziś")
        st.write(f"✅ Osiągnij cel czasowy (**{goal_min} min**)")
        st.write("✅ Przejrzyj sekcję **Warsztat**")
        st.write("✅ Wykonaj min. jeden **Quiz** lub **Test**")

    st.divider()

    # 4. MOTYWACJA I OSTATNIE SŁÓWKA
    quotes = [
        "„Die Grenzen meiner Sprache bedeuten die Grenzen meiner Welt.” – Ludwig Wittgenstein",
        "„Każdy nowy język jest jak otwarte okno, które ukazuje nowy widok na świat.”",
        "„Wer fremde Sprachen nie kennt, weiß nichts von seiner eigenen.” – J.W. Goethe"
    ]
    
    col_q, col_w = st.columns([2, 1])
    
    with col_q:
        st.info(random.choice(quotes))
        st.caption("💡 Porada: Najlepiej uczyć się rano, gdy mózg jest najbardziej chłonny.")

    with col_w:
        with st.expander("🆕 Ostatnio dodane", expanded=True):
            if all_c:
                # Pokazujemy 3 ostatnio dodane słówka
                recent = all_c[-3:]
                for r in reversed(recent):
                    st.write(f"**{r['de']}**")
            else:
                st.write("Brak słówek.")

# --- KONIEC SEKCJI 7 ---

# --- 8. POWTÓRKI & TRENING (V256 - Losowy kierunek & Sprytne rodzajniki) ---
elif choice in ["📅 Powtórki", "🚀 Trening"]:
    is_r = (choice == "📅 Powtórki")
    st.header(choice)
    
    # 1. POBIERANIE USTAWIEŃ
    user_settings = st.session_state.user_data.get("settings", {})
    auto_audio = user_settings.get("auto_audio", True)
    
    # Przygotowanie tagów do filtra
    all_tags = set()
    for c in st.session_state.flashcards:
        all_tags.update([t.strip() for t in str(c.get('category','')).split(',') if t.strip()])
    
    sel_tag = st.selectbox("Zakres nauki:", ["Wszystkie"] + sorted(list(all_tags)), key="sel_tag_rep")

    # 2. INICJALIZACJA PULI SŁÓWEK (Tylko przy zmianie filtra lub wejściu)
    if "cur_list" not in st.session_state or st.session_state.get("last_tag") != sel_tag:
        pool = [c for c in st.session_state.flashcards if (sel_tag == "Wszystkie" or sel_tag in str(c.get('category','')))]
        
        if is_r:
            # Dla powtórek filtrujemy po dacie SRS
            today_str = str(date.today())
            pool = [c for c in pool if str(c.get("next_review", today_str)) <= today_str]
        
        random.shuffle(pool)
        st.session_state.cur_list = pool
        st.session_state.n_idx = 0
        st.session_state.last_tag = sel_tag
        st.session_state.n_m = "ask" # Tryb: ask (pytanie) lub res (wynik)

    cards = st.session_state.cur_list
    
    if not cards:
        st.success("Brak słówek w tej sekcji! Wszystko opanowane. ✨")
    elif st.session_state.n_idx >= len(cards):
        st.balloons()
        st.success("Sesja zakończona! Dobra robota. 🏆")
        if st.button("Zacznij od nowa"):
            for k in ["cur_list", "n_idx", "n_m", "u_a", "q_dir"]:
                if k in st.session_state: del st.session_state[k]
            st.rerun()
    else:
        # --- SILNIK POWTÓREK (FRAGMENT) ---
        @st.fragment
        def flashcard_engine():
            idx = st.session_state.n_idx
            c = cards[idx]
            
            # Losowanie kierunku (tylko raz na dane słówko)
            if "q_dir" not in st.session_state:
                # 0: DE -> PL, 1: PL -> DE
                st.session_state.q_dir = random.choice([0, 1])

            st.progress(idx / len(cards))
            st.caption(f"Słówko {idx + 1} z {len(cards)}")

            # Kierunek pytania
            is_target_de = (st.session_state.q_dir == 1)
            display_word = c["de"] if not is_target_de else c["pl"]
            target_lang = "Polski" if not is_target_de else "Niemiecki"
            correct_val = c["pl"] if not is_target_de else c["de"]

            # Graficzna karta pytania
            st.markdown(f'''
                <div style="font-size:2.6em; text-align:center; padding:40px; 
                background: #111; border:3px solid {"#4CAF50" if is_r else "#FF9800"}; 
                border-radius:20px; margin-bottom:10px; color: white; line-height: 1.2;">
                    <div style="font-size:0.35em; color:gray; margin-bottom:5px; text-transform: uppercase; letter-spacing: 2px;">
                        Tłumaczysz na: {target_lang}
                    </div>
                    {display_word}
                </div>
            ''', unsafe_allow_html=True)

            # --- TRYB: PYTANIE ---
            if st.session_state.n_m == "ask":
                with st.form(key=f"f_{idx}", clear_on_submit=True):
                    u_in = st.text_input(f"Wpisz odpowiedź ({target_lang}):", key=f"in_{idx}")
                    if st.form_submit_button("Sprawdź", use_container_width=True, type="primary"):
                        st.session_state.u_a = u_in
                        st.session_state.n_m = "res"
                        st.rerun(scope="fragment")
            
            # --- TRYB: WYNIK ---
            else:
                # Logika porównywania (ignoruje rodzajniki przy odpowiedziach niemieckich)
                def clean_for_compare(text, is_german):
                    t = normalize_text(text)
                    if is_german:
                        # Usuwamy rodzajniki der/die/das na początku stringa
                        t = re.sub(r'^(der|die|das)\s+', '', t)
                    return t.strip()

                user_ans = clean_for_compare(st.session_state.u_a, is_target_de)
                actual_correct = clean_for_compare(correct_val, is_target_de)
                
                is_correct = user_ans == actual_correct
                
                if is_correct:
                    st.success(f"✅ Dobrze: {correct_val}")
                else:
                    st.error(f"❌ Poprawnie: {correct_val}")
                
                # Audio i Przykłady (Audio zawsze z niemieckiego słowa w bazie)
                exs = c.get("examples", [])
                fex = exs[0].get("de") if exs and isinstance(exs, list) and len(exs) > 0 else None
                
                if auto_audio:
                    play_audio(c['de'], fex)

                if fex:
                    st.info(f"💡 Przykład: **{fex}**\n\n({exs[0].get('pl','')})")
                
                if not auto_audio:
                    if st.button("🔊 Odsłuchaj", use_container_width=True):
                        play_audio(c['de'], fex) if fex else play_audio(c['de'])

                st.divider()

                # Obsługa ocen SRS (tylko w trybie Powtórki)
                if is_r:
                    st.write("Oceń trudność (wybór planuje datę kolejnej powtórki):")
                    col1, col2, col3 = st.columns(3)
                    d = None
                    if col1.button("🔴 Trudne"): d = 1
                    if col2.button("🟡 Średnie"): d = 4
                    if col3.button("🟢 Łatwe"): d = 10
                    
                    if d:
                        new_date = str(date.today() + timedelta(days=d))
                        update_word(c['id'], {"next_review": new_date})
                        st.session_state.n_idx += 1
                        st.session_state.n_m = "ask"
                        if "q_dir" in st.session_state: del st.session_state.q_dir
                        st.rerun(scope="fragment")
                else:
                    if st.button("Następne słówko ➡️", use_container_width=True, type="primary"):
                        st.session_state.n_idx += 1
                        st.session_state.n_m = "ask"
                        if "q_dir" in st.session_state: del st.session_state.q_dir
                        st.rerun(scope="fragment")

        flashcard_engine()

# --- 9. QUIZ (V236 - Bezpiecznik dla kolumny level) ---
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
                word_id = q_c.get('id')
                
                # --- LOGIKA SRS ---
                if is_correct:
                    st.success("✅ Świetnie! (Słówko przesunięte o +2 dni)")
                    new_date = str(date.today() + timedelta(days=2))
                    update_word(word_id, {"next_review": new_date})
                else:
                    st.error(f"❌ Poprawnie: **{st.session_state.q_a}** (Słówko wraca do powtórek)")
                    
                    # BEZPIECZNA AKTUALIZACJA: Próbujemy wysłać level, jeśli się nie uda - tylko datę
                    payload = {"next_review": str(date.today())}
                    # Sprawdzamy czy karta w ogóle posiada klucz 'level' w sesji (czy kolumna istnieje)
                    if 'level' in q_c:
                        payload["level"] = 0
                    
                    update_word(word_id, payload)
                
                st.session_state.flashcards = load_flashcards(u)

                # --- PRZYKŁADY I AUDIO ---
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

# --- 11. TESTY (Wersja ULTRA FAST z st.fragment) ---
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

# --- 12. MEMORY GAME (V228 - Zabezpieczony zapis wyników) ---
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

# --- 20. ARENA WYZWAŃ (V227 - Pełny Ranking z Fixem) ---
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

# --- 22. SKANER AI ---
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

# --- 23. DODAJ (V262 - Wymuszone rodzajniki) ---
elif choice == "➕ Dodaj":
    st.header("➕ Dodaj nowe słówko")
    
    tab1, tab2 = st.tabs(["✍️ Manualnie", "🤖 Asystent AI ✨"])
    
    with tab1:
        @st.fragment
        def manual_add_ui():
            with st.form("manual_add_form", clear_on_submit=True):
                col1, col2 = st.columns(2)
                f_de = col1.text_input("Słowo (DE):", placeholder="np. der Hund")
                f_pl = col2.text_input("Tłumaczenie (PL):", placeholder="np. pies")
                f_cat = st.text_input("Kategorie / Tagi:", placeholder="rzeczownik, zwierzęta, A1")
                
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
                            "examples": []
                        }
                        save_word(u, new_word)
                        st.session_state.flashcards = load_flashcards(u)
                        st.success(f"Pomyślnie dodano: **{f_de}**")
                    else:
                        st.error("Wypełnij pola Niemiecki i Polski!")
        manual_add_ui()

    with tab2:
        st.info("Wpisz słowo, a AI przygotuje resztę (zawsze z rodzajnikiem).")
        ai_word = st.text_input("Jakie słowo przygotować?", placeholder="np. Entscheidung", key="ai_input_field")
        
        if st.button("Przygotuj dane przez AI ✨", use_container_width=True):
            if ai_word:
                with st.spinner("AI analizuje słowo i sprawdza rodzajnik..."):
                    # WZMOCNIONY PROMPT: Dodany rygorystyczny wymóg rodzajnika
                    prompt = f"""Przygotuj dane dla niemieckiego słowa/frazy: '{ai_word}'.
                    ZASADA KRYTYCZNA: Jeśli słowo jest rzeczownikiem, MUSISZ dodać rodzajnik (der, die, das).
                    Zwróć WYŁĄCZNIE JSON:
                    {{
                      "de": "tutaj słowo koniecznie z rodzajnikiem jeśli to rzeczownik",
                      "pl": "tłumaczenie",
                      "tags": "Poziom, Część mowy, Temat",
                      "ex_de": "przykład użycia po niemiecku",
                      "ex_pl": "tłumaczenie przykładu"
                    }}"""
                    try:
                        res = get_openai_response(prompt)
                        data = json.loads(res)
                        st.session_state.single_temp = [data]
                    except Exception as e:
                        st.error(f"Błąd AI: {e}")
            else:
                st.warning("Wpisz słowo!")

        # --- SEKCJA EDYCJI ---
        if "single_temp" in st.session_state and st.session_state.single_temp:
            st.divider()
            st.subheader("📝 Sprawdź i popraw przed zapisem")
            
            item = st.session_state.single_temp[0]
            df_init = [{
                "Dodaj": True,
                "Niemiecki": item.get("de", ""),
                "Polski": item.get("pl", ""),
                "Kategorie (Tagi)": item.get("tags", ""),
                "Przykład DE": item.get("ex_de", ""),
                "Przykład PL": item.get("ex_pl", "")
            }]

            edited_df = st.data_editor(
                df_init,
                use_container_width=True,
                num_rows="fixed",
                key="single_word_editor_v2"
            )

            c_save, c_cancel = st.columns(2)
            
            if c_save.button("✅ Wszystko gra, dodaj!", use_container_width=True, type="primary"):
                row = edited_df[0]
                if row.get("Dodaj", False):
                    new_word = {
                        "de": row["Niemiecki"],
                        "pl": row["Polski"],
                        "category": row["Kategorie (Tagi)"],
                        "next_review": str(date.today()),
                        "level": 0,
                        "origin": "Dodaj (AI)",
                        "examples": [{"de": row["Przykład DE"], "pl": row["Przykład PL"]}]
                    }
                    save_word(u, new_word)
                    st.success("Słówko dodane do bazy!")
                    st.session_state.flashcards = load_flashcards(u)
                    del st.session_state.single_temp
                    st.rerun()

            if c_cancel.button("🗑️ Odrzuć", use_container_width=True):
                if "single_temp" in st.session_state:
                    del st.session_state.single_temp
                st.rerun()

# --- 24. SŁOWNIK ---
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

# --- 25. STATYSTYKI (V225 - Z Rekordami Memory) ---
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

# --- 27. ADMIN PRO (V280 - Klasyczny widok + Procentowy Rozkład Czasu) ---
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
    
    # Kody z Twojej bazy (zgodnie z logiką nawigacji)
    tracked_codes = ["Pow", "Trn", "Qiz", "Mem", "Tst", "War", "Inn"]
    display_names = {
        "Pow": "📅 Powtórki", 
        "Trn": "🚀 Trening", 
        "Qiz": "🕹️ Quiz", 
        "Mem": "🧠 Memory", 
        "Tst": "📝 Testy", 
        "War": "🛠️ Warsztat",
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
            # Przypisanie do kategorii lub do 'Inn' (Inne)
            f_code = k if k in tracked_codes else "Inn"
            
            current_user_merged[f_code] += seconds
            total_sec += seconds
            # Do globalnych statystyk bierzemy tylko te z nawigacji (bez 'Inn')
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
        
        # --- TABELA 1: NOWY GLOBALNY ROZKŁAD AKTYWNOŚCI ---
        st.subheader("📈 Globalny rozkład aktywności")
        total_global_study = sum(global_time.values())
        
        if total_global_study > 0:
            analysis_rows = []
            # Wyświetlamy w kolejności nawigacji (bez 'Inn')
            for code in ["Pow", "Trn", "Qiz", "Mem", "Tst", "War"]:
                val_sec = global_stats_val = global_time.get(code, 0)
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
            valid_codes = ["Pow", "Trn", "Qiz", "Mem", "Tst", "War", "Inn"]
            
            for _, row in df_admin.iterrows():
                d_row = {"Użytkownik": row["Użytkownik"]}
                for code in valid_codes:
                    d_row[display_names[code]] = int(row["__raw_stats"][code] // 60)
                detail_rows.append(d_row)
            
            st.dataframe(pd.DataFrame(detail_rows), use_container_width=True, hide_index=True)
