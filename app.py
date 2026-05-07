import streamlit as st
import json
import random
import re
import hashlib
import pandas as pd
import time
from datetime import datetime, date, timedelta
from io import BytesIO
from gtts import gTTS
from openai import OpenAI
from postgrest import SyncPostgrestClient

# --- 1. KONFIGURACJA ---
SUPABASE_URL = st.secrets.get("SUPABASE_URL", "")
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY", "")
API_KEY = st.secrets.get("OPENAI_API_KEY", "")

APP_VERSION = "V205 (Learning Modules Restored)"
ADMIN_USER = "wobo"

# MAPOWANIE DLA ANALITYKI
CLEAN_TIME_LABELS = {
    "Powtórki": "Pow", "Trening": "Trn", "Quiz": "Qiz", "Fiszki": "Fis",
    "Testy": "Tst", "Skaner": "Skn", "Generator": "Gen", "Dodaj": "Dod",
    "Słownik": "Słn", "Konto": "Inn"
}

# --- 2. SILNIK BAZY I AI ---
def get_db():
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    return SyncPostgrestClient(f"{SUPABASE_URL}/rest/v1", headers=headers)

def get_openai_response(prompt_text):
    client = OpenAI(api_key=API_KEY)
    messages = [{"role": "system", "content": "Jesteś ekspertem niemieckiego. Odpowiadaj TYLKO w JSON. Tagi po polsku."}]
    res = client.chat.completions.create(model="gpt-4o-mini", messages=messages, response_format={"type": "json_object"})
    return res.choices[0].message.content

def play_audio(txt, ex_txt=None):
    try:
        full = f"{txt}. . . . {ex_txt}" if ex_txt else txt
        f = BytesIO(); tts = gTTS(text=full, lang='de'); tts.write_to_fp(f); f.seek(0)
        st.audio(f, format="audio/mp3", autoplay=True)
    except: pass

# --- 3. FUNKCJE DANYCH ---
def load_user_data(username):
    db = get_db(); res = db.table("user_data").select("*").eq("username", username).execute()
    return res.data[0] if res.data else None

def save_user_data(username, data):
    d = data.copy(); d.pop("username", None)
    get_db().table("user_data").update(d).eq("username", username).execute()

def load_flashcards(username):
    db = get_db(); res = db.table("flashcards").select("*").eq("username", username).execute()
    return res.data if res.data else []

def update_word(word_id, fields): get_db().table("flashcards").update(fields).eq("id", word_id).execute()

# --- 4. LOGOWANIE ---
if "auth" not in st.session_state:
    st.session_state.auth = False
    if "token" in st.query_params:
        u_tk = st.query_params["token"]
        st.session_state.auth, st.session_state.user = True, u_tk

if not st.session_state.auth:
    st.title(f"🚀 Niemiecki Master {APP_VERSION}")
    un = st.text_input("Użytkownik").lower().strip()
    pw = st.text_input("Hasło", type="password")
    if st.button("Zaloguj się", use_container_width=True, type="primary"):
        res = get_db().table("users_auth").select("*").eq("username", un).execute()
        if res.data and res.data[0]["password_hash"] == hashlib.sha256(str.encode(pw)).hexdigest():
            st.session_state.auth, st.session_state.user = True, un
            st.query_params["token"] = un; st.rerun()
    st.stop()

# --- 5. START SESJI ---
u = st.session_state.user
st.session_state.user_data = load_user_data(u)
st.session_state.flashcards = load_flashcards(u)

def update_activity(m):
    curr = time.time(); delta = curr - st.session_state.user_data.get("last_ts", curr)
    if 0 < delta < 600:
        label = CLEAN_TIME_LABELS.get(m, "Inn")
        stats = st.session_state.user_data.get("time_stats", {})
        stats[label] = stats.get(label, 0.0) + delta
        st.session_state.user_data["time_stats"] = stats
    st.session_state.user_data["last_ts"] = curr
    save_user_data(u, st.session_state.user_data)

# --- 6. SIDEBAR ---
st.sidebar.title(f"👤 {u.capitalize()}")
st.sidebar.info(f"🔥 Passa: **{st.session_state.user_data.get('streak', 0)} dni**")
menu = ["📅 Powtórki", "🎴 Fiszki", "📦 Generator słów", "📖 Słownik", "➕ Dodaj", "🕹️ Quiz", "📝 Testy", "📊 Statystyki", "⚙️ Moje Konto", "👑 Admin"]
choice = st.sidebar.radio("Nawigacja", menu)

# Reset stanów modułów
if "l_c" not in st.session_state or st.session_state.l_c != choice:
    for k in ["cur_list", "n_idx", "f_flipped"]:
        if k in st.session_state: del st.session_state[k]
    st.session_state.l_c, st.session_state.n_m = choice, "ask"

# --- 7. MODUŁ: POWTÓRKI (Restored) ---
if choice == "📅 Powtórki":
    update_activity("Powtórki")
    st.header("📅 Twoje Powtórki (SRS)")
    
    # Wyciąganie unikalnych tagów dla filtra
    all_tags = set()
    for c in st.session_state.flashcards:
        all_tags.update([t.strip() for t in str(c.get('category','')).split(',')])
    
    sel_tag = st.selectbox("Filtruj poziom/kategorię:", ["Wszystkie"] + sorted(list(all_tags)))
    
    if "cur_list" not in st.session_state:
        pool = [c for c in st.session_state.flashcards if (sel_tag == "Wszystkie" or sel_tag in str(c.get('category',''))) and str(c.get("next_review", date.today())) <= str(date.today())]
        random.shuffle(pool); st.session_state.cur_list, st.session_state.n_idx = pool, 0

    cards = st.session_state.cur_list
    if not cards: st.success("Wszystko powtórzone! 🎉")
    else:
        idx = st.session_state.n_idx
        if idx < len(cards):
            c = cards[idx]
            st.write(f"Zostało: **{len(cards) - idx}**")
            st.markdown(f'<div style="font-size:3em; text-align:center; padding:20px; border:2px solid #1E88E5; border-radius:15px;">{c["de"]}</div>', unsafe_allow_html=True)
            
            if st.session_state.n_m == "ask":
                u_in = st.text_input("Tłumaczenie (PL):", key=f"rev_{idx}")
                if st.button("Sprawdź"): st.session_state.u_a, st.session_state.n_m = u_in, "res"; st.rerun()
            else:
                is_ok = (u.strip().lower() == c['pl'].strip().lower() for u in st.session_state.u_a.split(','))
                if any(is_ok): st.success(f"✅ Dobrze: {c['pl']}")
                else: st.error(f"❌ Poprawnie: {c['pl']}")
                
                exs = c.get("examples", [])
                fex = exs[0].get("de") if exs and isinstance(exs, list) and len(exs) > 0 else None
                if fex: st.info(f"💡 {fex}\n\n({exs[0].get('pl','')})")
                play_audio(c['de'], fex)
                
                st.write("Jak oceniasz to słowo?")
                col1, col2, col3 = st.columns(3); d = None
                if col1.button("🔴 Słabo (1d)"): d = 1
                if col2.button("🟡 Średnio (3d)"): d = 3
                if col3.button("🟢 Dobrze (7d)"): d = 7
                if d:
                    update_word(c['id'], {"next_review": str(date.today() + timedelta(days=d))})
                    st.session_state.n_idx += 1; st.session_state.n_m = "ask"; st.rerun()

# --- 8. MODUŁ: FISZKI (Restored) ---
elif choice == "🎴 Fiszki":
    update_activity("Fiszki")
    st.header("🎴 Fiszki")
    
    all_tags = set()
    for c in st.session_state.flashcards:
        all_tags.update([t.strip() for t in str(c.get('category','')).split(',')])
    sel_tag = st.selectbox("Zakres:", ["Wszystkie"] + sorted(list(all_tags)))
    
    cards = [c for c in st.session_state.flashcards if sel_tag == "Wszystkie" or sel_tag in str(c.get('category',''))]
    
    if cards:
        if "f_idx" not in st.session_state: st.session_state.f_idx, st.session_state.f_flipped = 0, False
        c = cards[st.session_state.f_idx % len(cards)]
        
        display_text = c["pl"] if st.session_state.f_flipped else c["de"]
        color = "#FF5252" if not st.session_state.f_flipped else "#2E7D32"
        
        st.markdown(f'<div style="min-height:300px; display:flex; align-items:center; justify-content:center; background:black; border:4px solid {color}; border-radius:30px; color:white; font-size:2.5em; text-align:center; padding:20px;">{display_text}</div>', unsafe_allow_html=True)
        
        c1, c2, c3 = st.columns(3)
        if c1.button("⬅️ Poprzednia"): st.session_state.f_idx -= 1; st.session_state.f_flipped = False; st.rerun()
        if c2.button("🔄 OBRÓĆ", type="primary"): 
            st.session_state.f_flipped = not st.session_state.f_flipped
            if st.session_state.f_flipped:
                exs = c.get("examples", [])
                fex = exs[0].get("de") if exs and isinstance(exs, list) and len(exs) > 0 else None
                play_audio(c['de'], fex)
            st.rerun()
        if c3.button("Następna ➡️"): st.session_state.f_idx += 1; st.session_state.f_flipped = False; st.rerun()
        
        if st.session_state.f_flipped:
            exs = c.get("examples", [])
            if exs: st.write(f"🇩🇪 {exs[0].get('de','')}\n\n🇵🇱 {exs[0].get('pl','')}")

# --- 9. MODUŁ: GENERATOR (Zoptymalizowany) ---
elif choice == "📦 Generator słów":
    update_activity("Generator")
    st.header("📦 Generator z Chmury")
    cols = st.columns(5)
    for i, lvl in enumerate(["A1", "A2", "B1", "B2", "C1"]):
        if cols[i].button(lvl, use_container_width=True):
            with st.spinner(f"AI tłumaczy 25 słówek {lvl}..."):
                try:
                    res_db = get_db().table("vocab_library").select("word").eq("level", lvl).execute()
                    all_words = [item['word'] for item in res_db.data]
                    my_w = [x['de'].lower() for x in st.session_state.flashcards]
                    avail = [w for w in all_words if w.lower() not in my_w]
                    sel = random.sample(avail, min(25, len(avail)))
                    
                    prompt = f"Przetłumacz na polski i otaguj tematycznie: {sel}. JSON: {{\"flashcards\": [{{ \"de\":\"...\", \"pl\":\"...\", \"category\":\"..., {lvl}\", \"examples\":[{{ \"de\":\"...\", \"pl\":\"...\" }}] }}]}}"
                    data = json.loads(get_openai_response(prompt))
                    
                    for w in data.get("flashcards", []):
                        # Zapewnienie, że w jest słownikiem przed zapisem
                        if isinstance(w, dict) and 'de' in w:
                            w["origin"] = "Generator"
                            w["username"] = u
                            w["next_review"] = str(date.today())
                            get_db().table("flashcards").insert(w).execute()
                    st.success("Dodano pomyślnie!"); time.sleep(1); st.rerun()
                except Exception as e: st.error(f"Błąd: {e}")

# Pozostałe moduły (Słownik, Admin, Statystyki) zostaną uzupełnione o Multi-Tagi w V206.
