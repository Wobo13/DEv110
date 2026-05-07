import streamlit as st
import json
import random
import re
import hashlib
import pandas as pd
import base64
import time
from datetime import datetime, date, timedelta
from io import BytesIO
from PIL import Image
import plotly.graph_objects as go
from openai import OpenAI
from postgrest import SyncPostgrestClient

# --- 1. KONFIGURACJA SUPABASE & API ---
SUPABASE_URL = st.secrets.get("SUPABASE_URL", "")
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY", "")
API_KEY = st.secrets.get("OPENAI_API_KEY", "")

APP_VERSION = "V203 (Dictionary Pro & Multi-Tags)"
ADMIN_USER = "wobo"

# --- 2. BAZA SŁÓWEK (Skrócona dla stabilności kodu - pobierana dynamicznie) ---
# Uwaga: Wersja pełna 1250 słów powinna być w osobnym pliku, tu zostawiam przykłady
# abyś mógł przetestować generator.
VOCAB_DB = {
    "A1": ["Apfel", "Brot", "Haus", "Auto", "Schule", "Mutter", "Vater", "Kind", "Zeit", "Geld", "Hund", "Katze", "Tisch", "Stuhl", "Buch"],
    "A2": ["Urlaub", "Reise", "Bahnhof", "Hotel", "Küche", "Körper", "Gesundheit", "Wetter", "Sport", "Musik"],
    "B1": ["Erfahrung", "Erfolg", "Entscheidung", "Meinung", "Gefühl", "Zukunft", "Natur", "Beruf", "Gehalt"],
    "B2": ["Herausforderung", "Verantwortung", "Zusammenhang", "Entwicklung", "Gerechtigkeit", "Freiheit"],
    "C1": ["Auseinandersetzung", "Nachhaltigkeit", "Kompetenz", "Perspektive", "Struktur", "Vielfalt"]
}

# --- 3. SILNIK BAZY DANYCH ---
def get_db():
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    return SyncPostgrestClient(f"{SUPABASE_URL}/rest/v1", headers=headers)

def hash_pw(pw): return hashlib.sha256(str.encode(pw)).hexdigest()

def normalize_text(t):
    if not t: return ""
    t = str(t).lower().strip().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    return re.sub(r'[?.!,;]', '', t)

# --- 4. SILNIK AI ---
def get_openai_response(prompt_text, img_obj=None):
    if not API_KEY: raise Exception("Brak klucza API.")
    client = OpenAI(api_key=API_KEY)
    messages = [{"role": "system", "content": "Jesteś ekspertem niemieckiego. Zawsze odpowiadaj w JSON. Tagi kategorii muszą być po polsku, rozdzielone przecinkami."}]
    if img_obj:
        buffered = BytesIO(); img_obj.thumbnail((800, 800)); img_obj.save(buffered, format="JPEG")
        img_b64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
        messages.append({"role": "user", "content": [{"type": "text", "text": prompt_text}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}}]})
    else:
        messages.append({"role": "user", "content": prompt_text})
    res = client.chat.completions.create(model="gpt-4o-mini", messages=messages, response_format={"type": "json_object"})
    return res.choices[0].message.content

# --- 5. FUNKCJE DANYCH ---
def load_user_data(username):
    db = get_db(); res = db.table("user_data").select("*").eq("username", username).execute()
    if res.data: return res.data[0]
    init = {"username": username, "streak":0, "historical_cost":0.0, "time_stats":{}, "last_ts":time.time(), "last_seen":"Nigdy", "test_history": []}
    db.table("user_data").insert(init).execute()
    return init

def save_user_data(username, data):
    d = data.copy()
    if "username" in d: del d["username"]
    get_db().table("user_data").update(d).eq("username", username).execute()

def load_flashcards(username):
    db = get_db(); res = db.table("flashcards").select("*").eq("username", username).execute()
    return res.data if res.data else []

def save_word(username, word_obj):
    db = get_db(); word_obj["username"] = username
    if "examples" not in word_obj: word_obj["examples"] = []
    db.table("flashcards").insert(word_obj).execute()

def delete_word(word_id): get_db().table("flashcards").delete().eq("id", word_id).execute()

def update_word(word_id, fields): get_db().table("flashcards").update(fields).eq("id", word_id).execute()

# --- 6. LOGOWANIE ---
if "auth" not in st.session_state:
    st.session_state.auth = False
    if "token" in st.query_params:
        user = st.query_params["token"]
        res = get_db().table("users_auth").select("*").eq("username", user).execute()
        if res.data: st.session_state.auth, st.session_state.user = True, user

if not st.session_state.auth:
    st.title(f"🚀 Niemiecki Master {APP_VERSION}")
    t1, t2 = st.tabs(["🔐 Logowanie", "📝 Rejestracja"])
    db = get_db()
    with t1:
        u_in = st.text_input("Użytkownik").lower().strip()
        p_in = st.text_input("Hasło", type="password")
        if st.button("Zaloguj się", use_container_width=True, type="primary"):
            res = db.table("users_auth").select("*").eq("username", u_in).execute()
            if res.data and res.data[0]["password_hash"] == hash_pw(p_in):
                st.session_state.auth, st.session_state.user = True, u_in
                st.query_params["token"] = u_in; st.rerun()
            else: st.error("Błąd logowania")
    with t2:
        un, pn = st.text_input("Nowy użytkownik").lower().strip(), st.text_input("Hasło", type="password")
        if st.button("Załóż konto"):
            if len(un) > 2 and len(pn) > 3:
                db.table("users_auth").insert({"username":un, "password_hash":hash_pw(pn)}).execute()
                st.success("Konto gotowe!"); time.sleep(1); st.rerun()
    st.stop()

# --- 7. START SESJI ---
u = st.session_state.user
st.session_state.user_data = load_user_data(u)
st.session_state.flashcards = load_flashcards(u)

def update_activity(m="Inne"):
    curr = time.time(); delta = curr - st.session_state.user_data.get("last_ts", curr)
    if 0 < delta < 600:
        stats = st.session_state.user_data.get("time_stats", {})
        stats[m] = stats.get(m, 0.0) + delta
        st.session_state.user_data["time_stats"] = stats
    st.session_state.user_data["last_ts"] = curr
    save_user_data(u, st.session_state.user_data)

update_activity("Inne")

# --- 8. SIDEBAR ---
st.sidebar.title(f"👤 {u.capitalize()}")
st.sidebar.caption(f"Wersja: {APP_VERSION}")
st.sidebar.info(f"🔥 Passa: **{st.session_state.user_data.get('streak', 0)} dni**")
if st.sidebar.button("Wyloguj"):
    st.query_params.clear(); st.session_state.clear(); st.rerun()

menu = ["📅 Powtórki", "🕹️ Quiz", "📝 Testy", "📸 Skaner AI", "📦 Generator słów", "➕ Dodaj", "📖 Słownik", "📊 Statystyki", "⚙️ Moje Konto"]
choice = st.sidebar.radio("Nawigacja", menu)

# --- 9. MODUŁ SŁOWNIK (NAPRAWIONY I ULEPSZONY) ---
if choice == "📖 Słownik":
    update_activity("Słownik")
    st.header("📖 Twój Słownik")
    
    # Wyciąganie wszystkich tagów z bazy
    all_tags = set()
    for c in st.session_state.flashcards:
        tags = [t.strip() for t in str(c.get('category', 'Inne')).split(',')]
        all_tags.update(tags)
    
    # Filtrowanie
    col1, col2 = st.columns([1, 2])
    f_tag = col1.selectbox("Filtruj kategorię/poziom:", ["Wszystkie"] + sorted(list(all_tags)))
    search = col2.text_input("Szukaj słowa:")
    
    filtered = []
    for c in st.session_state.flashcards:
        tags = [t.strip() for t in str(c.get('category', 'Inne')).split(',')]
        if (f_tag == "Wszystkie" or f_tag in tags) and (search.lower() in c['de'].lower() or search.lower() in c['pl'].lower()):
            filtered.append(c)

    st.write(f"Znaleziono słówek: **{len(filtered)}**")
    
    for c in filtered:
        with st.expander(f"🇩🇪 {c['de']} — 🇵🇱 {c['pl']}"):
            with st.form(f"edit_{c['id']}"):
                new_de = st.text_input("Niemiecki", c['de'])
                new_pl = st.text_input("Polski", c['pl'])
                new_tags = st.text_input("Kategorie (rozdzielaj przecinkiem)", c.get('category', 'Inne'))
                
                c1, c2 = st.columns(2)
                if c1.form_submit_button("Zapisz zmiany"):
                    update_word(c['id'], {"de": new_de, "pl": new_pl, "category": new_tags})
                    st.success("Zapisano!"); time.sleep(0.5); st.rerun()
                if c2.form_submit_button("Usuń słówko"):
                    delete_word(c['id'])
                    st.error("Usunięto!"); time.sleep(0.5); st.rerun()

# --- 10. GENERATOR (W PEŁNI NAPRAWIONY) ---
elif choice == "📦 Generator słów":
    update_activity("Generator")
    st.header("📦 Generator słów (Multi-Kategorie)")
    
    cols = st.columns(5)
    lvls = ["A1", "A2", "B1", "B2", "C1"]
    for i, lvl in enumerate(lvls):
        if cols[i].button(lvl, use_container_width=True):
            with st.spinner(f"AI tłumaczy i taguje 25 słówek {lvl}..."):
                try:
                    my_w = [x['de'].lower() for x in st.session_state.flashcards]
                    available = [w for w in VOCAB_DB[lvl] if w.lower() not in my_w]
                    sel = random.sample(available, min(25, len(available)))
                    
                    prompt = f"""Przetłumacz te słowa na polski: {sel}. 
                    Dla każdego słowa podaj:
                    1. Polskie znaczenie.
                    2. Polskie tagi (np. 'rodzina, rzeczownik, {lvl}'). 
                    3. Przykładowe zdanie.
                    Format JSON: {{"flashcards": [{{ "de": "...", "pl": "...", "category": "...", "examples": [{{"de":"...", "pl":"..."}}] }}]}}"""
                    
                    res_raw = get_openai_response(prompt)
                    data = json.loads(res_raw)
                    
                    if data and "flashcards" in data:
                        for w in data["flashcards"]:
                            save_word(u, {
                                "de": w['de'], "pl": w['pl'], 
                                "category": w.get('category', lvl), 
                                "next_review": str(date.today()), 
                                "origin": "Generator",
                                "examples": w.get('examples', [])
                            })
                        st.success(f"Dodano 25 słówek na poziomie {lvl}!"); time.sleep(1); st.rerun()
                except Exception as e:
                    st.error(f"Błąd: {e}")

# --- 11. DODAJ RĘCZNIE ---
elif choice == "➕ Dodaj":
    st.header("➕ Dodaj nowe słówko")
    with st.form("manual_add"):
        de = st.text_input("Słówko po niemiecku")
        pl = st.text_input("Tłumaczenie")
        tags = st.text_input("Tagi (np. A1, dom, czasownik)", "Inne")
        if st.form_submit_button("Zapisz do bazy"):
            if de and pl:
                save_word(u, {"de": de, "pl": pl, "category": tags, "next_review": str(date.today()), "origin": "Dodaj"})
                st.success("Dodano!")

# Pozostałe moduły (Quiz, Testy, Statystyki, Konto) dodajemy w kolejnych krokach
# aby utrzymać stabilność logiki słownika i bazy danych.
