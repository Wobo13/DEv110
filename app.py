import streamlit as st
import json
import os
import random
import re
import hashlib
import pandas as pd
import secrets
import base64
import time
from datetime import datetime, date, timedelta
from io import BytesIO
from PIL import Image
import plotly.graph_objects as go
from openai import OpenAI
from postgrest import SyncPostgrestClient

# --- KONFIGURACJA (Pobieranie z Secrets) ---
SUPABASE_URL = st.secrets.get("SUPABASE_URL", "")
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY", "")
API_KEY = st.secrets.get("OPENAI_API_KEY", "")

# --- KONFIGURACJA APKI ---
APP_VERSION = "V197 (Full Database & Feature Restore)"
ADMIN_USER = "wobo"

# MAPOWANIE SKRÓTÓW CZASU
CLEAN_TIME_LABELS = {
    "Powtórki": "Pow", "Nauka": "Pow", "Pow": "Pow", "Nau": "Pow", "N": "Pow", "P": "Pow",
    "Trening": "Trn", "Trn": "Trn", "T": "Trn",
    "Quiz": "Qiz", "Qiz": "Qiz", "Q": "Qiz",
    "Fiszki": "Fis", "Fis": "Fis", "F": "Fis",
    "Testy": "Tst", "Tst": "Tst",
    "Skaner": "Skn", "Skaner AI": "Skn",
    "Generator": "Gen", "Generator słów": "Gen",
    "Dodaj": "Dod", "➕ Dodaj": "Dod",
    "Słownik": "Słn", "📖 Słownik": "Słn",
    "Konto": "Inn", "Moje Konto": "Inn", "Inne": "Inn", "Inn": "Inn", "I": "Inn"
}

# --- POTĘŻNA WEWNĘTRZNA BAZA SŁÓWEK (1250 SŁÓW) ---
VOCAB_DB = {
    "A1": ["Apfel", "Brot", "Haus", "Auto", "Schule", "Lehrer", "Wasser", "Milch", "Tisch", "Stuhl", "Buch", "Stift", "Kind", "Mutter", "Vater", "Freund", "Stadt", "Land", "Weg", "Zeit", "Essen", "Trinken", "Schlafen", "Lernen", "Arbeiten", "Gehen", "Kommen", "Hören", "Sehen", "Sprechen", "Groß", "Klein", "Gut", "Schlecht", "Schön", "Hässlich", "Alt", "Jung", "Neu", "Kalt", "Heute", "Morgen", "Gestern", "Woche", "Jahr", "Tag", "Nacht", "Name", "Zahl", "Geld", "Hund", "Katze", "Baum", "Blume", "Sonne", "Mond", "Regen", "Schnee", "Wind", "Bett", "Zimmer", "Küche", "Bad", "Fenster", "Tür", "Schlüssel", "Tasche", "Gabel", "Löffel", "Messer", "Teller", "Tasse", "Glas", "Saft", "Kaffee", "Tee", "Zucker", "Salz", "Fleisch", "Fisch", "Gemüse", "Obst", "Banane", "Ei", "Käse", "Reis", "Nudeln", "Kuchen", "Zeitung", "Radio", "Handy", "Fahrrad", "Zug", "Bus", "Bahnhof", "Flughafen", "Hotel", "Arzt", "Krankenhaus", "Apotheke"],
    "A2": ["Urlaub", "Reise", "Bahnhof", "Flugzeug", "Hotel", "Küche", "Kühlschrank", "Gabel", "Löffel", "Messer", "Kleidung", "Hose", "Hemd", "Schuh", "Wetter", "Regen", "Sonne", "Wolke", "Gesundheit", "Krankheit", "Arzt", "Medizin", "Körper", "Kopf", "Hand", "Fuß", "Sport", "Spiel", "Musik", "Film", "Besuchen", "Verstehen", "Vergessen", "Bestellen", "Bezahlen", "Wohnen", "Mieten", "Kaufen", "Verkaufen", "Feiern", "Wichtig", "Wahr", "Falsch", "Fertig", "Glücklich", "Traurig", "Müde", "Sauer", "Süß", "Heiß", "Abwaschen", "Anrufen", "Anziehen", "Aufräumen", "Ausgeben", "Aussehen", "Baden", "Bedeuten", "Beeilen", "Benutzen", "Berichten", "Beschreiben", "Besichtigen", "Bestimmen", "Besprechen", "Bewerben", "Bezahlen", "Buchen", "Buchstabieren", "Danken", "Dauern", "Diskutieren", "Drucken", "Duschen", "Einkaufen", "Einladen", "Einziehen", "Enden", "Entschuldigen", "Erinnern", "Erkennen", "Erlauben", "Erleben", "Erzählen", "Fehlen", "Feiern", "Fernsehen", "Frühstücken", "Fühlen", "Füttern", "Gehören", "Gewinnen", "Glauben", "Grillen", "Grüßen", "Heiraten", "Hoffen", "Holen", "Interessieren", "Kämmen"],
    "B1": ["Erfahrung", "Erfolg", "Entscheidung", "Meinung", "Gefühl", "Beziehung", "Zukunft", "Vergangenheit", "Umwelt", "Natur", "Gesellschaft", "Politik", "Wirtschaft", "Wissenschaft", "Technik", "Beruf", "Ausbildung", "Studium", "Gehalt", "Vertrag", "Vorbereiten", "Organisieren", "Diskutieren", "Argumentieren", "Erklären", "Empfehlen", "Vorschlagen", "Warnen", "Hoffen", "Träumen", "Gefährlich", "Sicher", "Möglich", "Unmöglich", "Nötig", "Nützlich", "Schwierig", "Leicht", "Interessant", "Langweilig", "Obwohl", "Trotzdem", "Deshalb", "Deswegen", "Falls", "Damit", "Stattdessen", "Zuerst", "Schließlich", "Besonders", "Abhängig", "Ablehnen", "Abmachen", "Abnehmen", "Abonnieren", "Absagen", "Abschließen", "Absolvieren", "Abstimmen", "Abwarten", "Achten", "Ändern", "Anerkennen", "Anfangen", "Anfordern", "Angeben", "Angehören", "Angreifen", "Anhalten", "Anklagen", "Ankommen", "Ankündigen", "Anmelden", "Annehmen", "Anpassen", "Anrufen", "Anschließen", "Ansehen", "Ansprechen", "Anstrengen", "Antworten", "Anwenden", "Anzeigen", "Anziehen", "Arbeiten", "Ärgern", "Aufbauen", "Aufgeben", "Aufhalten", "Aufhören", "Aufklären", "Aufmerksam", "Aufaufnahme", "Aufräumen", "Aufregen", "Aufstehen", "Aufutreten", "Aufwachen", "Ausbilden", "Ausdehnen"],
    "B2": ["Herausforderung", "Verantwortung", "Voraussetzung", "Zusammenhang", "Unterschied", "Vergleich", "Entwicklung", "Fortschritt", "Ursache", "Wirkung", "Eindruck", "Einfluss", "Ergebnis", "Erwartung", "Gerechtigkeit", "Freiheit", "Sicherheit", "Vertrauen", "Geduld", "Vorsicht", "Beeinflussen", "Verbessern", "Verschlechtern", "Erreichen", "Vermeiden", "Lösen", "Teilnehmen", "Unterstützen", "Fördern", "Fordern", "Effizient", "Effektiv", "Kreativ", "Kritisch", "Logisch", "Objektiv", "Subjektiv", "Typisch", "Zufällig", "Regelmäßig", "Anscheinend", "Vermutlich", "Eventuell", "Tatsächlich", "Grundsätzlich", "Eigentlich", "Überall", "Nirgendwo", "Irgendwie", "Sowieso", "Abweichen", "Aneignen", "Anfordern", "Anordnen", "Anschaffen", "Anstellen", "Antreffen", "Appellieren", "Auffassen", "Aufgreifen", "Aufheben", "Aufwenden", "Ausarbeiten", "Ausdehnen", "Ausführen", "Auslösen", "Ausnutzen", "Ausstatten", "Ausüben", "Bedenken", "Begehen", "Begreifen", "Beharren", "Beifügen", "Beitragen", "Bekämpfen", "Belasten", "Belegen", "Bemängeln", "Bemessen", "Benachrichtigen", "Benachteiligen", "Beruhen", "Beschaffen", "Beseitigen", "Bestand", "Bestreiten", "Beteiligen", "Betreffen", "Beurteilen", "Bevorzugen", "Bewältigen", "Bewirken", "Beziehen", "Bezweifeln", "Bilanz", "Bündeln", "Darlegen", "Dazugehören", "Definieren"],
    "C1": ["Auseinandersetzung", "Auswirkung", "Bedeutung", "Erkenntnis", "Fähigkeit", "Maßnahme", "Notwendigkeit", "Perspektive", "Struktur", "Vielfalt", "Anforderung", "Bewältigung", "Darstellung", "Einschätzung", "Gewährleistung", "Hintergrund", "Integration", "Kompetenz", "Nachhaltigkeit", "Umsetzung", "Analysieren", "Berücksichtigen", "Differenzieren", "Evaluieren", "Gewährleisten", "Hinterfragen", "Implementieren", "Konkretisieren", "Reflektieren", "Veranschaulichen", "Außergewöhnlich", "Beträchtlich", "Eindeutig", "Erheblich", "Gravierend", "Kontrovers", "Nachhaltig", "Präzise", "Umfangreich", "Wesentliche", "Dementsprechend", "Demnach", "Infolgedessen", "Inwiefern", "Inwieweit", "Jegliche", "Lediglich", "Nichtsdestotrotz", "Stufenweise", "Zunehmend", "Abstrahieren", "Akquirieren", "Akzentuieren", "Antizipieren", "Artikulieren", "Assoziieren", "Attestieren", "Autarkie", "Autorisieren", "Bagatellisieren", "Bilateral", "Charakterisieren", "Chiffrieren", "Chronologisch", "Defizit", "Degradieren", "Deklarieren", "Delegieren", "Demokratisierung", "Demonstrieren", "Denunziieren", "Deplatzieren", "Deponieren", "Derivat", "Desillusionieren", "Destabilisieren", "Detailgenau", "Determinieren", "Diagnostizieren", "Diametral", "Diffamieren", "Differenzierung", "Diffus", "Diktieren", "Dilemma", "Dimensionieren", "Diskreditieren", "Diskrepanz", "Diskretion", "Diskurs", "Dislozieren", "Disponieren", "Disproportion", "Disput", "Dissonanz", "Distanzieren", "Distinktion", "Divergieren", "Diversifikation", "Diversität"]
}

# --- SYSTEM POMOCNICZY (SUPABASE) ---
def get_db():
    if not SUPABASE_URL or not SUPABASE_KEY:
        st.error("Błąd konfiguracji Supabase! Sprawdź Secrets.")
        st.stop()
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    return SyncPostgrestClient(f"{SUPABASE_URL}/rest/v1", headers=headers)

def hash_pw(pw): return hashlib.sha256(str.encode(pw)).hexdigest()

def normalize_text(t):
    if not t: return ""
    t = str(t).lower().strip().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    return re.sub(r'[?.!,;]', '', t)

# --- FUNKCJE DANYCH ---
def load_user_data(username):
    db = get_db()
    res = db.table("user_data").select("*").eq("username", username).execute()
    if res.data: return res.data[0]
    init = {"username": username, "streak": 0, "historical_cost": 0.0, "time_stats": {}, "last_ts": time.time(), "last_seen": "Nigdy", "test_history": []}
    db.table("user_data").insert(init).execute()
    return init

def save_user_data(username, data):
    d = data.copy()
    if "username" in d: del d["username"]
    get_db().table("user_data").update(d).eq("username", username).execute()

def load_flashcards(username):
    db = get_db()
    res = db.table("flashcards").select("*").eq("username", username).execute()
    cards = res.data if res.data else []
    for c in cards:
        if not c.get("origin"):
            cat = str(c.get("category", "")).lower()
            c["origin"] = "Generator" if "gen" in cat else ("Skaner" if "skan" in cat else "Dodaj")
    return cards

def save_word(username, word_obj):
    word_obj["username"] = username
    if "examples" in word_obj and not isinstance(word_obj["examples"], list): word_obj["examples"] = []
    get_db().table("flashcards").insert(word_obj).execute()

def update_word(word_id, update_fields):
    get_db().table("flashcards").update(update_fields).eq("id", word_id).execute()

def delete_word(word_id):
    get_db().table("flashcards").delete().eq("id", word_id).execute()

def play_audio(txt, example_txt=None):
    try:
        from gtts import gTTS
        full = f"{txt}. . . . {example_txt}" if example_txt else txt
        f = BytesIO(); tts = gTTS(text=full, lang='de'); tts.write_to_fp(f); f.seek(0)
        st.audio(f, format="audio/mp3", autoplay=True)
    except: pass

def is_correct(u_ans, c_ans_str):
    user = normalize_text(u_ans)
    correct_options = [normalize_text(s) for s in re.split(r'[/,;]', str(c_ans_str))]
    return user in correct_options

# --- SILNIK AI ---
def get_openai_response(prompt_text, img_obj=None):
    if not API_KEY: raise Exception("Brak klucza API OpenAI.")
    client = OpenAI(api_key=API_KEY)
    messages = [{"role": "system", "content": "You are a professional German teacher. Output ONLY valid JSON. Category names MUST be in Polish. For EVERY question, include 'hint' with Polish translation of the target word."}]
    if img_obj:
        buffered = BytesIO(); img_obj.thumbnail((800, 800)); img_obj.save(buffered, format="JPEG")
        img_b64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
        messages.append({"role": "user", "content": [{"type": "text", "text": prompt_text}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}}]})
    else:
        messages.append({"role": "user", "content": prompt_text})
    response = client.chat.completions.create(model="gpt-4o-mini", messages=messages, response_format={"type": "json_object"})
    return response.choices[0].message.content

# --- LOGOWANIE ---
if "auth" not in st.session_state:
    st.session_state.auth = False
    if "token" in st.query_params:
        db = get_db()
        user = st.query_params["token"]
        res = db.table("users_auth").select("*").eq("username", user).execute()
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
            else: st.error("Błędne dane")
    with t2:
        un = st.text_input("Nowy użytkownik").lower().strip()
        pn = st.text_input("Hasło (min. 4 znaki)", type="password")
        if st.button("Załóż konto", use_container_width=True):
            if len(un) > 2 and len(pn) >= 4:
                check = db.table("users_auth").select("*").eq("username", un).execute()
                if not check.data:
                    db.table("users_auth").insert({"username": un, "password_hash": hash_pw(pn)}).execute()
                    load_user_data(un) 
                    st.success("Konto utworzone! Zaloguj się."); time.sleep(1); st.rerun()
                else: st.error("Użytkownik istnieje")
    st.stop()

# --- INIT ---
u = st.session_state.user
st.session_state.user_data = load_user_data(u)
st.session_state.flashcards = load_flashcards(u)

def update_activity(m="Inne"):
    curr = time.time()
    delta = curr - st.session_state.user_data.get("last_ts", curr)
    if 0 < delta < 600:
        label = CLEAN_TIME_LABELS.get(m, "Inn")
        stats = st.session_state.user_data.get("time_stats", {})
        stats[label] = stats.get(label, 0.0) + delta
        st.session_state.user_data["time_stats"] = stats
    st.session_state.user_data["last_ts"] = curr
    st.session_state.user_data["last_seen"] = datetime.now().strftime("%d.%m %H:%M")
    save_user_data(u, st.session_state.user_data)

today_dt = date.today()
update_activity()

# --- SIDEBAR ---
st.sidebar.title(f"👤 {u.capitalize()}")
st.sidebar.caption(f"Wersja: {APP_VERSION}")
st.sidebar.info(f"🔥 Passa: **{st.session_state.user_data.get('streak', 0)} dni**")
if st.sidebar.button("Wyloguj"):
    st.query_params.clear(); st.session_state.clear(); st.rerun()

menu = ["📅 Powtórki", "🚀 Trening", "🕹️ Quiz", "🎴 Fiszki", "📝 Testy", "📸 Skaner AI", "📦 Generator słów", "➕ Dodaj", "📖 Słownik", "📊 Statystyki", "⚙️ Moje Konto"]
if u == ADMIN_USER: menu.append("👑 Admin")
choice = st.sidebar.radio("Nawigacja", menu)

if "l_c" not in st.session_state or st.session_state.l_c != choice:
    for k in ["test_q", "test_idx", "test_score", "cur_review_list", "n_idx", "q_c", "q_s", "f_idx", "f_flipped", "pending"]:
        if k in st.session_state: del st.session_state[k]
    st.session_state.l_c, st.session_state.n_m, st.session_state.u_a = choice, "ask", ""

# --- POWTÓRKI / TRENING ---
if choice in ["📅 Powtórki", "🚀 Trening"]:
    is_r = (choice == "📅 Powtórki")
    update_activity("Powtórki")
    all_cats = sorted(list(set([c.get("category", "Inne") for c in st.session_state.flashcards])))
    sel_kat = st.selectbox("🎯 Kategoria:", ["Wszystkie"] + all_cats)
    
    if "cur_review_list" not in st.session_state:
        pool = [c for c in st.session_state.flashcards if sel_kat == "Wszystkie" or c.get("category") == sel_kat]
        if is_r: pool = [c for c in pool if c.get("next_review", str(today_dt)) <= str(today_dt)]
        random.shuffle(pool); st.session_state.cur_review_list, st.session_state.n_idx = pool, 0

    cards = st.session_state.cur_review_list
    if not cards: st.success("Wszystko opanowane! 🎊")
    else:
        idx = st.session_state.n_idx
        if idx >= len(cards): st.success("Koniec sesji!")
        else:
            c = cards[idx]
            st.write(f"Słówek w kolejce: **{len(cards) - idx}**")
            st.write(f"### Słówko: **{c['de']}**")
            if st.session_state.n_m == "ask":
                with st.form("ans_f"):
                    u_in = st.text_input("Tłumaczenie (PL):")
                    if st.form_submit_button("Sprawdź", use_container_width=True):
                        st.session_state.u_a, st.session_state.n_m = u_in, "res"; st.rerun()
            else:
                if is_correct(st.session_state.u_a, c['pl']): st.success(f"✅ Dobrze: {c['pl']}")
                else: st.error(f"❌ Poprawnie: {c['pl']}")
                
                exs = c.get("examples", [])
                first_ex_de = exs[0].get("de") if exs and isinstance(exs, list) and len(exs) > 0 else None
                if isinstance(exs, list):
                    for ex in exs:
                        if isinstance(ex, dict) and 'de' in ex:
                            st.markdown(f"🇩🇪 {ex['de']}<br>🇵🇱 {ex.get('pl','')}", unsafe_allow_html=True)
                play_audio(c['de'], first_ex_de)
                if is_r:
                    col1, col2, col3 = st.columns(3); d = None
                    if col1.button("🔴 Słabo (1d)", use_container_width=True): d = 1
                    if col2.button("🟡 Średnio (3d)", use_container_width=True): d = 3
                    if col3.button("🟢 Dobrze (7d)", use_container_width=True): d = 7
                    if d:
                        update_word(c['id'], {"next_review": str(today_dt + timedelta(days=d))})
                        st.session_state.n_idx += 1; st.session_state.n_m = "ask"; st.rerun()
                elif st.button("Dalej ➡️", use_container_width=True):
                    st.session_state.n_idx += 1; st.session_state.n_m = "ask"; st.rerun()

# --- QUIZ ---
elif choice == "🕹️ Quiz":
    update_activity("Quiz"); all_c = st.session_state.flashcards
    if len(all_c) < 4: st.warning("Dodaj min. 4 słówka!")
    else:
        if "q_c" not in st.session_state:
            idx = random.randrange(len(all_c)); t = all_c[idx]
            opts = random.sample([x['pl'] for x in all_c if x['pl']!=t['pl']], min(3, len(all_c)-1)) + [t['pl']]
            random.shuffle(opts); st.session_state.update({"q_idx":idx, "q_c":t, "q_a":t['pl'], "q_o":opts, "q_s":"ask"})
        st.write(f"### Jak przetłumaczysz: **{st.session_state.q_c['de']}**")
        if st.session_state.q_s == "ask":
            for o in st.session_state.q_o:
                if st.button(o, key=o, use_container_width=True): st.session_state.u_q, st.session_state.q_s = o, "res"; st.rerun()
        else:
            c = st.session_state.q_c
            if is_correct(st.session_state.get("u_q"), st.session_state.q_a):
                st.success("✅ Brawo!"); orig_id = c['id']
                if c.get("next_review", str(today_dt)) <= str(today_dt):
                    update_word(orig_id, {"next_review": str(today_dt + timedelta(days=1))})
            else: st.error(f"❌ Błąd. Poprawnie: {st.session_state.q_a}")
            exs = c.get('examples', [])
            ex_de = exs[0].get('de') if exs and isinstance(exs, list) and len(exs) > 0 else None
            play_audio(c['de'], ex_de)
            if st.button("Dalej", use_container_width=True): del st.session_state.q_c; st.rerun()

# --- FISZKI ---
elif choice == "🎴 Fiszki":
    update_activity("Fiszki"); all_cats = sorted(list(set([c.get("category", "Inne") for c in st.session_state.flashcards])))
    sel_kat = st.selectbox("🎯 Kategoria:", ["Wszystkie"] + all_cats)
    cards = [c for c in st.session_state.flashcards if sel_kat == "Wszystkie" or c.get("category") == sel_kat]
    if cards:
        if "f_idx" not in st.session_state: st.session_state.f_idx = 0
        if "f_flipped" not in st.session_state: st.session_state.f_flipped = False
        c = cards[st.session_state.f_idx % len(cards)]; word_txt = c["pl"] if st.session_state.f_flipped else c["de"]
        ex_html = ""
        if st.session_state.f_flipped:
            for ex in c.get("examples", []):
                if isinstance(ex, dict) and 'de' in ex:
                    ex_html += f"<div style='margin-top:15px; border-top:1px solid #444; padding-top:10px;'><span style='color:#FFEB3B;'>🇩🇪 {ex['de']}</span><br><span style='color:white;'>🇵🇱 {ex.get('pl','')}</span></div>"
        st.markdown(f'<div style="min-height:350px; display:flex; flex-direction:column; align-items:center; justify-content:center; background:black; border:3px solid #FF5252; border-radius:30px; padding:30px; text-align:center;"><h1 style="color:white; margin:0; font-size:2.2em;">{word_txt}</h1>{ex_html}</div>', unsafe_allow_html=True)
        c1, c2, c3 = st.columns([1, 1.2, 1])
        if c1.button("⬅️ Wstecz", use_container_width=True): st.session_state.f_idx -= 1; st.session_state.f_flipped = False; st.rerun()
        if c2.button("🔄 OBRÓĆ", type="primary", use_container_width=True): st.session_state.f_flipped = not st.session_state.f_flipped; st.rerun()
        if c3.button("Dalej ➡️", use_container_width=True): st.session_state.f_idx += 1; st.session_state.f_flipped = False; st.rerun()
        if st.session_state.f_flipped:
            exs = c.get('examples', [])
            ex_de = exs[0].get('de') if exs and isinstance(exs, list) and len(exs) > 0 else None
            play_audio(c['de'], ex_de)

# --- TESTY ---
elif choice == "📝 Testy":
    update_activity("Testy"); st.header("📝 Egzamin Kontekstowy")
    if len(st.session_state.flashcards) < 5: st.warning("Min. 5 słówek w bazie.")
    else:
        if "test_q" not in st.session_state:
            n_q = st.slider("Liczba pytań", 5, 20, 5)
            if st.button("🚀 GENERUJ TEST", use_container_width=True, type="primary"):
                with st.spinner("AI przygotowuje zadania..."):
                    sample = random.sample(st.session_state.flashcards, min(n_q, len(st.session_state.flashcards)))
                    words_str = ", ".join([f"{w['de']} ({w['pl']})" for w in sample])
                    prompt = f"Generate EXACTLY {len(sample)} German questions for: {words_str}. Provide 'hint' (Polish context/word translation), 'sentence' (German), 'correct' (DE). For QUIZ provide 3 'distractors'. JSON key 'questions'."
                    try:
                        res = get_openai_response(prompt); data = json.loads(res)
                        valid_qs = [q for q in data.get("questions", []) if (q.get('sentence') or q.get('question')) and q.get('correct')]
                        if valid_qs:
                            st.session_state.test_q, st.session_state.test_idx, st.session_state.test_score = valid_qs, 0, 0
                            st.session_state.user_data["historical_cost"] += 0.01; st.rerun()
                    except Exception as e: st.error("Spróbuj ponownie.")
        else:
            qs = st.session_state.test_q; t_idx = st.session_state.test_idx
            if t_idx < len(qs):
                q = qs[t_idx]; st.write(f"### Pytanie {t_idx+1} z {len(qs)}"); correct_w = str(q.get('correct', ''))
                st.info(f"💡 Wskazówka (PL): {q.get('hint', 'brak')}")
                ans = None; sentence = q.get('sentence') or q.get('question', '')
                if q.get('type') == "QUIZ":
                    st.markdown(f"#### `{sentence.replace(correct_w, '_______')}`")
                    opts = list(set(q.get('distractors', []) + [correct_w])); random.shuffle(opts)
                    cols = st.columns(2)
                    for i, o in enumerate(opts):
                        if cols[i%2].button(o, key=f"t_{t_idx}_{i}", use_container_width=True): ans = o
                else:
                    st.markdown(f"#### `{sentence.replace(correct_w, '_______')}`")
                    u_in = st.text_input("Twoja odpowiedź:", key=f"ti_{t_idx}")
                    if st.button("Zatwierdź"): ans = u_in
                if ans:
                    st.session_state.test_q[t_idx]['user_ans'] = ans
                    if normalize_text(ans) == normalize_text(correct_w):
                        st.session_state.test_score += 1; st.toast("Dobrze! 🌟")
                    else: st.error(f"Źle. Poprawnie: {correct_w}"); time.sleep(1.2)
                    st.session_state.test_idx += 1; st.rerun()
            else:
                total = len(qs); score = st.session_state.test_score; perc = round((score/total)*100) if total > 0 else 0
                st.session_state.user_data["test_history"].append({"date": datetime.now().strftime("%d.%m %H:%M"), "score": score, "total": total, "perc": perc})
                save_user_data(u, st.session_state.user_data); st.balloons()
                st.markdown(f'<div style="text-align:center; padding:30px; border-radius:20px; background:#111; border:2px solid #1E88E5;"><h1>Wynik: {score} / {total}</h1><h2>{perc}%</h2></div>', unsafe_allow_html=True)
                if st.button("Powrót"): del st.session_state.test_q; st.rerun()

# --- MODUŁY NARZĘDZIOWE ---
elif choice == "📸 Skaner AI":
    update_activity("Skaner"); src = st.camera_input("Zdjęcie"); up = st.file_uploader("Lub plik")
    if (src or up) and st.button("🚀 ANALIZUJ", use_container_width=True):
        try:
            with st.spinner("Analiza..."):
                res = get_openai_response("Extract German vocabulary. Format JSON key 'flashcards'.", Image.open(src or up))
                data = json.loads(res)
                if "flashcards" in data: st.session_state.pending = data["flashcards"]; st.session_state.user_data["historical_cost"] += 0.02; st.rerun()
        except Exception as e: st.error(f"Błąd: {e}")
    if "pending" in st.session_state:
        ed = st.data_editor(pd.DataFrame(st.session_state.pending), use_container_width=True)
        if st.button("✅ ZAPISZ"):
            for w in ed.to_dict('records'):
                if 'de' in w and 'pl' in w: save_word(u, {**w, "next_review":str(today_dt), "origin":"Skaner"})
            del st.session_state.pending; st.success("Dodano!"); st.rerun()

elif choice == "📦 Generator słów":
    update_activity("Generator"); lvls = ["A1", "A2", "B1", "B2", "C1"]; cols = st.columns(5)
    for i, lvl in enumerate(lvls):
        if cols[i].button(lvl, use_container_width=True):
            with st.spinner(f"Szukam 25 słówek {lvl}..."):
                try:
                    my_w = [x['de'].lower() for x in st.session_state.flashcards]
                    available = [w for w in VOCAB_DB[lvl] if w.lower() not in my_w]
                    sel = random.sample(available, min(25, len(available)))
                    res = get_openai_response(f"Translate to Polish: {sel}. Descriptive Polish categories, 1 example each. JSON key 'flashcards'.")
                    data = json.loads(res)
                    for w in data.get("flashcards", []):
                        save_word(u, {**w, "next_review":str(today_dt), "origin":"Generator", "category":f"{lvl}-{w.get('category','Inne')}"})
                    st.session_state.user_data["historical_cost"] += 0.01; st.success("Dodano!"); time.sleep(1); st.rerun()
                except Exception as e: st.error(f"Błąd: {e}")

elif choice == "➕ Dodaj":
    st.header("➕ Dodaj słówko"); update_activity("Dodaj")
    with st.form("man_f"):
        de, pl, kat = st.text_input("Niemiecki"), st.text_input("Polski"), st.text_input("Kategoria")
        if st.form_submit_button("Zapisz"):
            if de and pl: 
                save_word(u, {"de":de, "pl":pl, "category":kat or "Inne", "next_review":str(today_dt), "origin":"Dodaj", "examples":[]})
                st.success("Zapisano!"); st.rerun()

elif choice == "📖 Słownik":
    update_activity("Słownik"); search = st.text_input("Szukaj:")
    for c in st.session_state.flashcards:
        if search.lower() in c['de'].lower() or search.lower() in c['pl'].lower():
            with st.expander(f"📝 {c['de']} - {c['pl']}"):
                if st.button("Usuń", key=f"del_{c['id']}"): delete_word(c['id']); st.rerun()

# --- STATYSTYKI ---
elif choice == "📊 Statystyki":
    update_activity("Inn"); df = pd.DataFrame(st.session_state.flashcards)
    st.header("📊 Twoje Statystyki")
    if not df.empty:
        c1, c2, c3 = st.columns(3); c1.metric("Słówek", len(df)); c2.metric("Passa", f"{st.session_state.user_data['streak']} d")
        kn = len(df[df['next_review'].apply(lambda x: (date.fromisoformat(x)-date.today()).days >= 7 if x else False)])
        c3.metric("Opanowane", kn)
        st.subheader("🎯 Podział na poziomy")
        stats = []
        for l in ["A1", "A2", "B1", "B2", "C1"]:
            l_df = df[df['category'].str.contains(l, na=False)]
            total = len(l_df); know = len(l_df[l_df['next_review'].apply(lambda x: (date.fromisoformat(x)-date.today()).days >= 7 if x else False)]) if total > 0 else 0
            stats.append({"Poziom":l, "Słów":total, "Opanowane":know, "%":f"{round((know/total)*100) if total > 0 else 0}%"})
        st.table(pd.DataFrame(stats))
        st.subheader("📅 Nadchodzące powtórki")
        sched = [{"Data": (today_dt + timedelta(days=i)).strftime("%d.%m"), "Słów": len(df[df['next_review'] == str(today_dt + timedelta(days=i))])} for i in range(10)]
        st.bar_chart(pd.DataFrame(sched).set_index("Data"))
        st.subheader("📜 Historia Testów")
        st.table(pd.DataFrame(st.session_state.user_data.get("test_history", [])[::-1]).head(10))

# --- ADMIN ---
elif choice == "👑 Admin":
    st.header("👑 Panel Admina"); st.link_button("💸 OpenAI Billing", "https://platform.openai.com/usage", use_container_width=True)
    db = get_db(); ud = db.table("user_data").select("*").execute().data
    adm_list = []; total_cost = 0.0; global_time = {}
    for user in ud:
        username = user["username"]; total_cost += user.get("historical_cost", 0.0)
        cards = db.table("flashcards").select("origin").eq("username", username).execute().data
        m_man = len([x for x in cards if x.get("origin") == "Dodaj"])
        m_gen = len([x for x in cards if x.get("origin") == "Generator"])
        m_skn = len([x for x in cards if x.get("origin") == "Skaner"])
        merged = {}
        for m, s in user.get("time_stats", {}).items():
            lbl = CLEAN_TIME_LABELS.get(m.strip(), "Inn"); merged[lbl] = merged.get(lbl, 0) + s; global_time[lbl] = global_time.get(lbl, 0) + s
        u_times = ", ".join([f"{l}:{round(s/60)}m" for l, s in merged.items() if s > 15])
        adm_list.append({"Użytkownik":username, "Słów":len(cards), "Ręcznie":m_man, "Gen":m_gen, "Skan":m_skn, "Testy":len(user.get("test_history",[])), "Czas":u_times, "Koszt":round(user.get("historical_cost",0),4)})
    st.columns(2)[0].metric("Łącznie słówek", sum(x['Słów'] for x in adm_list))
    st.columns(2)[1].metric("Suma kosztów", f"{total_cost:.2f} PLN"); st.table(pd.DataFrame(adm_list))
    if global_time:
        fig = go.Figure(data=[go.Bar(x=list(global_time.keys()), y=list(global_time.values()), marker_color='#1E88E5')])
        fig.update_layout(template="plotly_dark", height=400, title="Czas globalny (min)"); st.plotly_chart(fig, use_container_width=True)

# --- MOJE KONTO ---
elif choice == "⚙️ Moje Konto":
    st.header("⚙️ Zarządzanie Kontem"); update_activity("Inn")
    with st.expander("🔑 Zmień hasło"):
        with st.form("pw_f"):
            o, n, cp = st.text_input("Stare", type="password"), st.text_input("Nowe", type="password"), st.text_input("Powtórz", type="password")
            if st.form_submit_button("Zmień"):
                db = get_db(); res = db.table("users_auth").select("*").eq("username", u).execute()
                if res.data and res.data[0]["password_hash"] == hash_pw(o) and n == cp:
                    db.table("users_auth").update({"password_hash": hash_pw(n)}).eq("username", u).execute(); st.success("OK!")
    st.divider(); conf = st.checkbox("Potwierdzam usuwanie danych")
    if st.button("RESET CAŁEJ MOJEJ BAZY", type="primary", disabled=not conf):
        get_db().table("flashcards").delete().eq("username", u).execute(); st.rerun()
