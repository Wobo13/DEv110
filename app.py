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

# --- 1. KONFIGURACJA (Secrets) ---
SUPABASE_URL = st.secrets.get("SUPABASE_URL", "")
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY", "")
API_KEY = st.secrets.get("OPENAI_API_KEY", "")

APP_VERSION = "V218 (Admin PRO & Fiszki UI Fix)"
ADMIN_USER = "wobo"

CLEAN_TIME_LABELS = {
    "powtorki": "Pow", "trening": "Trn", "quiz": "Qiz", "fiszki": "Fis",
    "testy": "Tst", "skaner": "Skn", "generator": "Gen", "dodaj": "Dod",
    "slownik": "Słn", "statystyki": "Sta", "konto": "Kon", "admin": "Adm"
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

# --- 6. SIDEBAR I NAWIGACJA ---
st.sidebar.title(f"👤 {u.capitalize()}")
st.sidebar.caption(f"Wersja: {APP_VERSION}")
st.sidebar.info(f"🔥 Passa: **{st.session_state.user_data.get('streak', 0)} dni**")

if st.sidebar.button("Wyloguj", use_container_width=True):
    st.query_params.clear()
    st.session_state.clear()
    st.rerun()

menu = [
    "📅 Powtórki", "🚀 Trening", "🕹️ Quiz", "🎴 Fiszki", 
    "📝 Testy", "📦 Generator słów", "📸 Skaner AI", 
    "➕ Dodaj", "📖 Słownik", "📊 Statystyki", "⚙️ Moje Konto"
]

if u == ADMIN_USER:
    menu.append("👑 Admin")

# Zabezpieczenie przed pierwszym uruchomieniem
if "l_c" not in st.session_state:
    st.session_state.l_c = "Inne" # Domyślnie traktujemy wejście jako 'Inne'

# 1. Pobranie wyboru użytkownika
choice = st.sidebar.radio("Nawigacja", menu)

# 2. Zapis aktywności ZANIM zmienimy wewnętrzny stan aplikacji.
# Zapisujemy czas przypisany do modułu, w którym użytkownik BYŁ DO TEJ PORY.
update_activity(st.session_state.l_c)

# 3. Logika czyszczenia sesji przy zmianie modułu na nowy
if st.session_state.l_c != choice:
    # Czyścimy zbędne dane tymczasowe z poprzedniego modułu
    for k in ["cur_list", "n_idx", "f_idx", "f_flipped", "test_q", "test_idx", "test_score", "q_c", "q_s"]:
        if k in st.session_state: 
            del st.session_state[k]
    
    # Dopiero teraz aktualizujemy informację o tym, w jakim module jesteśmy
    st.session_state.l_c = choice
    st.session_state.n_m = "ask"
    st.session_state.u_a = ""

# --- 7. POWTÓRKI & TRENING (Wersja ULTRA FAST z st.fragment) ---
if choice in ["📅 Powtórki", "🚀 Trening"]:
    is_r = (choice == "📅 Powtórki")
    st.header(choice)
    
    # 1. Filtrowanie tagów (poza fragmentem, bo rzadko zmieniane)
    all_tags = set()
    for c in st.session_state.flashcards:
        all_tags.update([t.strip() for t in str(c.get('category','')).split(',') if t.strip()])
    
    sel_tag = st.selectbox("Zakres:", ["Wszystkie"] + sorted(list(all_tags)), key="sel_tag_rep")

    # 2. Inicjalizacja listy (poza fragmentem)
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
        st.success("Pusto! 🎉")
    elif st.session_state.n_idx >= len(cards):
        st.balloons()
        st.success("Koniec sesji! 🏆")
        if st.button("Zacznij od nowa"):
            del st.session_state.cur_list
            st.rerun()
    else:
        # --- TO JEST FRAGMENT (Tylko to będzie "migać" przy zmianie słówka) ---
        @st.fragment
        def flashcard_engine():
            idx = st.session_state.n_idx
            c = cards[idx]
            
            # Pasek postępu
            st.progress(idx / len(cards))
            st.caption(f"Słówko {idx + 1} z {len(cards)}")

            # Karta
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
                        st.rerun(scope="fragment") # Odświeża TYLKO ten fragment!
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
                
                play_audio(c['de'], fex)

                # Przycisk "Dalej" / "Oceny"
                if is_r:
                    st.write("Jak oceniasz?")
                    col1, col2, col3 = st.columns(3)
                    d = None
                    if col1.button("🔴 Słabo"): d = 1
                    if col2.button("🟡 Średnio"): d = 3
                    if col3.button("🟢 Dobrze"): d = 7
                    
                    if d:
                        update_word(c['id'], {"next_review": str(date.today() + timedelta(days=d))})
                        st.session_state.n_idx += 1
                        st.session_state.n_m = "ask"
                        st.rerun(scope="fragment")
                else:
                    if st.button("Dalej ➡️", use_container_width=True):
                        st.session_state.n_idx += 1
                        st.session_state.n_m = "ask"
                        st.rerun(scope="fragment")

        # Wywołanie fragmentu
        flashcard_engine()

# --- 8. QUIZ (Wersja z rozszerzonym Audio) ---
elif choice == "🕹️ Quiz":
    st.header("🕹️ Quiz")
    
    all_c = st.session_state.flashcards
    
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
                    "q_c": t, 
                    "q_a": t['pl'], 
                    "q_o": opts, 
                    "q_s": "ask",
                    "u_q": None
                })

            q_c = st.session_state.q_c
            
            st.write(f"### Jak przetłumaczysz: **{q_c['de']}**")
            
            if st.session_state.q_s == "ask":
                for o in st.session_state.q_o:
                    if st.button(o, key=f"btn_{o}", use_container_width=True):
                        st.session_state.u_q = o
                        st.session_state.q_s = "res"
                        st.rerun(scope="fragment")
            else:
                if st.session_state.u_q == st.session_state.q_a:
                    st.success("✅ Świetnie!")
                else:
                    st.error(f"❌ Poprawnie: **{st.session_state.q_a}**")
                
                # --- LOGIKA AUDIO ZE ZDANIEM ---
                exs = q_c.get("examples", [])
                # Sprawdzamy czy przykład istnieje i czy jest poprawnym formatem
                fex = exs[0].get("de") if exs and isinstance(exs, list) and len(exs) > 0 else None
                
                if fex:
                    st.info(f"💡 Przykład: {fex}")
                    # play_audio automatycznie doda pauzę między słowem a zdaniem dzięki Twojej definicji funkcji
                    play_audio(q_c['de'], fex)
                else:
                    play_audio(q_c['de'])
                # ------------------------------

                if st.button("Następne pytanie ➡️", use_container_width=True, type="primary"):
                    del st.session_state.q_c
                    del st.session_state.q_a
                    del st.session_state.q_o
                    del st.session_state.q_s
                    st.rerun(scope="fragment")

        quiz_engine()

# --- 9. FISZKI (Wersja ULTRA FAST z st.fragment) ---
elif choice == "🎴 Fiszki":
    st.header("🎴 Fiszki")
    
    # Inicjalizacja stanu (poza fragmentem, aby zachować ciągłość przy zmianie modułu)
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

# --- 11. GENERATOR ---
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

# --- 12. SKANER ---
elif choice == "📸 Skaner AI":
    st.header("📸 Skaner AI")
    src = st.camera_input("Zrób zdjęcie notatek")
    if src and st.button("Analizuj"):
        res = get_openai_response("Extract words to JSON 'flashcards' list.", Image.open(src))
        for w in json.loads(res).get("flashcards", []): 
            save_word(u, {**w, "origin":"Skaner", "next_review":str(date.today())})
        st.session_state.user_data["historical_cost"] += 0.05 # Dodanie kosztu skanera Vision
        save_user_data(u, st.session_state.user_data)
        st.success("Dodano zeskanowane słówka!"); st.rerun()

# --- 13. DODAJ RĘCZNIE ---
elif choice == "➕ Dodaj":
    st.header("➕ Dodaj Ręcznie")
    with st.form("manual"):
        de, pl, ca = st.text_input("Niemiecki"), st.text_input("Polski"), st.text_input("Tagi")
        if st.form_submit_button("Zapisz", use_container_width=True):
            save_word(u, {"de":de, "pl":pl, "category":ca, "next_review":str(date.today()), "origin":"Dodaj"}); st.rerun()

# --- 14. SŁOWNIK ---
elif choice == "📖 Słownik":
    st.header("📖 Słownik")
    all_tags = set()
    for c in st.session_state.flashcards:
        all_tags.update([t.strip() for t in str(c.get('category','')).split(',') if t.strip()])
    
    col1, col2 = st.columns([1, 2])
    f_tag = col1.selectbox("Filtruj kategorię:", ["Wszystkie"] + sorted(list(all_tags)))
    search = col2.text_input("Szukaj słowa:")
    
    filtered = [c for c in st.session_state.flashcards if (f_tag == "Wszystkie" or f_tag in str(c.get('category',''))) and (search.lower() in str(c.get('de','')).lower() or search.lower() in str(c.get('pl','')).lower())]
    
    st.write(f"Znaleziono: **{len(filtered)}**")
    for c in filtered:
        with st.expander(f"📝 {c['de']} - {c['pl']}"):
            with st.form(f"ed_{c['id']}"):
                n_de, n_pl, n_ca = st.text_input("DE", c['de']), st.text_input("PL", c['pl']), st.text_input("Tagi", c.get('category',''))
                if st.form_submit_button("Zapisz", use_container_width=True): update_word(c['id'], {"de": n_de, "pl": n_pl, "category": n_ca}); st.rerun()
            if st.button("Usuń", key=f"del_{c['id']}", use_container_width=True): delete_word(c['id']); st.rerun()

# --- 15. STATYSTYKI ---
elif choice == "📊 Statystyki":
    st.header("📊 Twoje Statystyki")
    df = pd.DataFrame(st.session_state.flashcards)
    if not df.empty:
        c1, c2 = st.columns(2); c1.metric("Wielkość Bazy", len(df)); c2.metric("Passa Nauki", f"{st.session_state.user_data['streak']} dni")
        
        st.write("---")
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
        
        # Nowa tabela z prognozą zamiast wykresu
        df_sched = pd.DataFrame(sched)
        st.dataframe(df_sched, use_container_width=True, hide_index=True)

        st.write("---")
        
        # Wyświetlanie tabel z poziomami i źródłami obok siebie
        col_stats1, col_stats2 = st.columns(2)
        
        with col_stats1:
            st.subheader("📈 Słówka wg poziomu")
            levels = ["A1", "A2", "B1", "B2", "C1"]
            level_totals = {lvl: 0 for lvl in levels}
            level_mastered = {lvl: 0 for lvl in levels}
            
            today_str = str(date.today())
            
            # Przeszukiwanie tagów w poszukiwaniu poziomów i sprawdzanie statusu opanowania
            if 'category' in df.columns:
                for _, row in df.iterrows():
                    cat = row.get('category')
                    if pd.isna(cat) or not cat: 
                        continue
                        
                    cat_str = str(cat).upper()
                    next_rev = str(row.get('next_review', today_str))
                    
                    # Słówko uznajemy za "opanowane" jeśli jego powtórka jest w przyszłości
                    is_mastered = next_rev > today_str
                    
                    for lvl in levels:
                        if lvl in cat_str:
                            level_totals[lvl] += 1
                            if is_mastered:
                                level_mastered[lvl] += 1
            
            # Generowanie danych do tabeli z procentami
            level_data = []
            for lvl in levels:
                total = level_totals[lvl]
                mastered = level_mastered[lvl]
                perc = int(round((mastered / total) * 100)) if total > 0 else 0
                level_data.append({
                    "Poziom": lvl, 
                    "Słówek": total, 
                    "Opanowane": f"{perc}%"
                })
                
            df_levels = pd.DataFrame(level_data)
            st.dataframe(df_levels, use_container_width=True, hide_index=True)
            
        with col_stats2:
            st.subheader("📌 Źródła pozyskania")
            if 'origin' in df.columns:
                origin_counts = df['origin'].value_counts().reset_index()
                origin_counts.columns = ['Źródło', 'Liczba słówek']
                st.dataframe(origin_counts, use_container_width=True, hide_index=True)
        
    st.write("---")
    st.subheader("📝 Historia rozwiązanych testów")
    t_hist = st.session_state.user_data.get("test_history", [])
    if t_hist:
        hist_df = pd.DataFrame(t_hist)[::-1]
        hist_df = hist_df[["date", "score", "total", "perc"]]
        hist_df.columns = ["Data", "Wynik", "Suma pytań", "Procent (%)"]
        st.dataframe(hist_df, use_container_width=True, hide_index=True)
    else:
        st.info("Brak rozwiązanych testów.")
# --- 16. KONTO ---
elif choice == "⚙️ Moje Konto":
    st.header("⚙️ Zarządzanie Kontem")
    
    # --- WYŚWIETLANIE KOMUNIKATÓW PO PRZEŁADOWANIU ---
    if "acc_msg" in st.session_state:
        st.success(st.session_state.acc_msg)
        del st.session_state.acc_msg
    # ------------------------------------------------

    with st.expander("🔑 Zmień hasło"):
        with st.form("pw"):
            o, n = st.text_input("Stare", type="password"), st.text_input("Nowe", type="password")
            if st.form_submit_button("Zmień", use_container_width=True):
                db = get_db()
                res = db.table("users_auth").select("*").eq("username", u).execute()
                if res.data and res.data[0]["password_hash"] == hash_pw(o):
                    db.table("users_auth").update({"password_hash": hash_pw(n)}).eq("username", u).execute()
                    st.success("Hasło zaktualizowane!")
                else:
                    st.error("Błędne stare hasło!")
    
    st.divider()
    st.subheader("🗑️ Usuwanie danych")
    conf = st.checkbox("Potwierdzam chęć usunięcia danych")
    
    st.write("Usuń konkretny poziom z chmury:")
    col_d = st.columns(5)
    for i, lvl in enumerate(["A1", "A2", "B1", "B2", "C1"]):
        # Dodany klucz (key), by przyciski w pętli działały stabilnie
        if col_d[i].button(lvl, disabled=not conf, key=f"del_lvl_{lvl}"):
            with st.spinner("Usuwanie..."):
                res = get_db().table("flashcards").delete().eq("username", u).ilike("category", f"%{lvl}%").execute()
                deleted_count = len(res.data) if res.data else 0
                
                # Zapisujemy wiadomość do sesji i odświeżamy lokalną bazę
                st.session_state.acc_msg = f"🗑️ Pomyślnie usunięto {deleted_count} słówek powiązanych z poziomem {lvl}."
                st.session_state.flashcards = load_flashcards(u)
                st.rerun()
    
    st.write("---")
    if st.button("🔥 ZRESETUJ CAŁĄ MOJĘ BAZĘ SŁÓWEK", type="primary", disabled=not conf, use_container_width=True):
        with st.spinner("Czyszczenie całej bazy..."):
            res = get_db().table("flashcards").delete().eq("username", u).execute()
            deleted_count = len(res.data) if res.data else 0
            
            # Zapisujemy wiadomość do sesji i czyścimy lokalną bazę
            st.session_state.acc_msg = f"🔥 Baza została zresetowana! Trwale usunięto {deleted_count} słówek."
            st.session_state.flashcards = []
            st.rerun()

# --- 17. ADMIN PRO ---
elif choice == "👑 Admin" and u == ADMIN_USER:
    st.header("👑 Panel Administratora")
    
    # Przycisk wymuszający przeładowanie, by zobaczyć najświeższy czas z bazy
    if st.button("🔄 Pobierz najświeższe statystyki z bazy"):
        st.cache_data.clear()
        st.rerun()

    st.link_button("💸 OpenAI Billing", "https://platform.openai.com/usage", use_container_width=True)
    
    db = get_db()
    # Pobieramy dane bezpośrednio (bez cache)
    ud_data = db.table("user_data").select("*").execute().data
    all_cards_res = db.table("flashcards").select("username", "origin").execute().data
    df_cards_all = pd.DataFrame(all_cards_res) if all_cards_res else pd.DataFrame(columns=["username", "origin"])
    
    adm_list = []
    global_time = {}
    tracked_codes = ["Pow", "Trn", "Qiz", "Fis", "Tst", "Inn"]
    display_names = {"Pow": "Powtórki", "Trn": "Trening", "Qiz": "Quiz", "Fis": "Fiszki", "Tst": "Testy", "Inn": "Inne"}
    
    for user in ud_data:
        username = user["username"]
        user_cards = df_cards_all[df_cards_all["username"] == username]
        oc = user_cards["origin"].value_counts()
        user_stats = user.get("time_stats", {})
        current_user_merged = {code: 0 for code in tracked_codes}
        total_sec = 0
        
        for raw_key, seconds in user_stats.items():
            k = str(raw_key).strip()
            k_low = k.lower()
            f_code = "Inn"
            
            # Pancerne mapowanie - radzi sobie ze starymi wpisami w bazie
            if k in tracked_codes: f_code = k
            elif "pow" in k_low: f_code = "Pow"
            elif "trn" in k_low or "tre" in k_low: f_code = "Trn"
            elif "qiz" in k_low or "qui" in k_low: f_code = "Qiz"
            elif "fis" in k_low: f_code = "Fis"
            elif "tst" in k_low or "tes" in k_low: f_code = "Tst"
            
            current_user_merged[f_code] += seconds
            total_sec += seconds
            global_time[f_code] = global_time.get(f_code, 0) + seconds
            
        adm_list.append({
            "Użytkownik": username, 
            "Słów": len(user_cards), 
            "Ręcznie": int(oc.get("Dodaj", 0)), 
            "AI (G+S)": int(oc.get("Generator", 0)) + int(oc.get("Skaner", 0)), 
            "Testy": len(user.get("test_history", [])),
            "Czas Total (min)": int(total_sec // 60),
            "Koszt (PLN)": round(user.get("historical_cost", 0.0), 2),
            "__raw_stats": current_user_merged
        })
    
    if not adm_list:
        st.warning("Brak danych.")
    else:
        df_admin = pd.DataFrame(adm_list)
        st.subheader("📋 Podsumowanie użytkowników")
        st.dataframe(df_admin.drop(columns=["__raw_stats"]), use_container_width=True, hide_index=True)
        
        with st.expander("🔍 Podział czasu (minuty)"):
            detail_rows = []
            for _, row in df_admin.iterrows():
                d_row = {"Użytkownik": row["Użytkownik"]}
                for code in tracked_codes:
                    d_row[display_names[code]] = int(row["__raw_stats"][code] // 60)
                detail_rows.append(d_row)
            st.dataframe(pd.DataFrame(detail_rows), use_container_width=True, hide_index=True)

        # WYŚWIETLANIE: Wykres sumaryczny (na samym końcu pliku)
        if global_time:
            st.write("---")
            # Filtrujemy kategorie, które mają więcej niż 0 minut
            chart_data = {display_names.get(k, k): int(v // 60) for k, v in global_time.items() if (v // 60) > 0}
            
            if chart_data:
                fig = go.Figure(data=[go.Bar(
                    x=list(chart_data.keys()), 
                    y=list(chart_data.values()), 
                    marker_color='#FF5252',
                    text=list(chart_data.values()),
                    textposition='auto'
                )])
                fig.update_layout(
                    template="plotly_dark", 
                    height=400, 
                    title="Globalny czas na modułach (minuty)"
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Brak wystarczającej ilości czasu (pełnych minut) do wygenerowania wykresu.")
