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

# Import biblioteki OpenAI
from openai import OpenAI

# --- KONFIGURACJA ---
APP_VERSION = "V172 (Full Recovery)"
ADMIN_USER = "wobo"
AUTH_FILE = "users_auth.json"
SESSIONS_FILE = "sessions.json"
BONUS_START = 1089.0

# Pobieranie klucza API
API_KEY = st.secrets.get("OPENAI_API_KEY") or st.secrets.get("GEMINI_API_KEY") or st.session_state.get("manual_api_key", "")

MODULE_ORDER = [
    "Powtórki", "Trening", "Quiz", "Fiszki", 
    "Skaner", "Generator", "Dodaj", "Słownik"
]

# --- WEWNĘTRZNA BAZA SŁÓWEK (LISTY STARTOWE) ---
VOCAB_DB = {
    "A1": [
        "Apfel", "Brot", "Haus", "Auto", "Schule", "Lehrer", "Wasser", "Milch", "Tisch", "Stuhl",
        "Buch", "Stift", "Kind", "Mutter", "Vater", "Freund", "Stadt", "Land", "Weg", "Zeit",
        "Essen", "Trinken", "Schlafen", "Lernen", "Arbeiten", "Gehen", "Kommen", "Hören", "Sehen", "Sprechen",
        "Groß", "Klein", "Gut", "Schlecht", "Schön", "Hässlich", "Alt", "Jung", "Neu", "Kalt",
        "Heute", "Morgen", "Gestern", "Woche", "Jahr", "Tag", "Nacht", "Name", "Zahl", "Geld"
    ],
    "A2": [
        "Urlaub", "Reise", "Bahnhof", "Flugzeug", "Hotel", "Küche", "Kühlschrank", "Gabel", "Löffel", "Messer",
        "Kleidung", "Hose", "Hemd", "Schuh", "Wetter", "Regen", "Sonne", "Wolke", "Gesundheit", "Krankheit",
        "Arzt", "Medizin", "Körper", "Kopf", "Hand", "Fuß", "Sport", "Spiel", "Musik", "Film",
        "Besuchen", "Verstehen", "Vergessen", "Bestellen", "Bezahlen", "Wohnen", "Mieten", "Kaufen", "Verkaufen", "Feiern",
        "Wichtig", "Wahr", "Falsch", "Fertig", "Glücklich", "Traurig", "Müde", "Sauer", "Süß", "Heiß"
    ],
    "B1": [
        "Erfahrung", "Erfolg", "Entscheidung", "Meinung", "Gefühl", "Beziehung", "Zukunft", "Vergangenheit", "Umwelt", "Natur",
        "Gesellschaft", "Politik", "Wirtschaft", "Wissenschaft", "Technik", "Beruf", "Ausbildung", "Studium", "Gehalt", "Vertrag",
        "Vorbereiten", "Organisieren", "Diskutieren", "Argumentieren", "Erklären", "Empfehlen", "Vorschlagen", "Warnen", "Hoffen", "Träumen",
        "Gefährlich", "Sicher", "Möglich", "Unmöglich", "Nötig", "Nützlich", "Schwierig", "Leicht", "Interessant", "Langweilig",
        "Obwohl", "Trotzdem", "Deshalb", "Deswegen", "Falls", "Damit", "Stattdessen", "Zuerst", "Schließlich", "Besonders"
    ],
    "B2": [
        "Herausforderung", "Verantwortung", "Voraussetzung", "Zusammenhang", "Unterschied", "Vergleich", "Entwicklung", "Fortschritt", "Ursache", "Wirkung",
        "Eindruck", "Einfluss", "Ergebnis", "Erwartung", "Gerechtigkeit", "Freiheit", "Sicherheit", "Vertrauen", "Geduld", "Vorsicht",
        "Beeinflussen", "Verbessern", "Verschlechtern", "Erreichen", "Vermeiden", "Lösen", "Teilnehmen", "Unterstützen", "Fördern", "Fordern",
        "Effizient", "Effektiv", "Kreativ", "Kritisch", "Logisch", "Objektiv", "Subjektiv", "Typisch", "Zufällig", "Regelmäßig",
        "Anscheinend", "Vermutlich", "Eventuell", "Tatsächlich", "Grundsätzlich", "Eigentlich", "Überall", "Nirgendwo", "Irgendwie", "Sowieso"
    ],
    "C1": [
        "Auseinandersetzung", "Auswirkung", "Bedeutung", "Erkenntnis", "Fähigkeit", "Maßnahme", "Notwendigkeit", "Perspektive", "Struktur", "Vielfalt",
        "Anforderung", "Bewältigung", "Darstellung", "Einschätzung", "Gewährleistung", "Hintergrund", "Integration", "Kompetenz", "Nachhaltigkeit", "Umsetzung",
        "Analysieren", "Berücksichtigen", "Differenzieren", "Evaluieren", "Gewährleisten", "Hinterfragen", "Implementieren", "Konkretisieren", "Reflektieren", "Veranschaulichen",
        "Außergewöhnlich", "Beträchtlich", "Eindeutig", "Erheblich", "Gravierend", "Kontrovers", "Nachhaltig", "Präzise", "Umfangreich", "Wesentliche",
        "Dementsprechend", "Demnach", "Infolgedessen", "Inwiefern", "Inwieweit", "Jegliche", "Lediglich", "Nichtsdestotrotz", "Stufenweise", "Zunehmend"
    ]
}

# --- SYSTEM POMOCNICZY ---
def hash_pw(pw): 
    return hashlib.sha256(str.encode(pw)).hexdigest()

def get_p(u, t): 
    return f"{t}_{u}.json"

def load_j(p, d): 
    if os.path.exists(p):
        try:
            with open(p, "r", encoding="utf-8") as f: return json.load(f)
        except: return d
    return d

def save_j(p, d): 
    with open(p, "w", encoding="utf-8") as f: json.dump(d, f, indent=4)

def play_audio(txt):
    try:
        from gtts import gTTS
        f = BytesIO(); tts = gTTS(text=txt, lang='de'); tts.write_to_fp(f); f.seek(0)
        st.audio(f, format="audio/mp3", autoplay=True)
    except: pass

def parse_ai_json(text):
    try:
        # Usuwamy ewentualne teksty przed i po JSON
        match = re.search(r'(\{.*\}|\[.*\])', text, re.DOTALL)
        if match:
            clean = match.group(0).strip()
            return json.loads(clean)
        return json.loads(text.strip())
    except: return None

# --- SILNIK AI: OPENAI ---
def get_openai_response(prompt_text, img_obj=None):
    if not API_KEY:
        raise Exception("Brak klucza API OpenAI.")
    client = OpenAI(api_key=API_KEY)
    messages = [{"role": "system", "content": "You are a professional German teacher. Output ONLY valid JSON."}]
    if img_obj:
        buffered = BytesIO()
        img_obj.thumbnail((800, 800)); img_obj.save(buffered, format="JPEG")
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
        ss = load_j(SESSIONS_FILE, {})
        tk = st.query_params["token"]
        if tk in ss:
            st.session_state.auth = True
            st.session_state.user = ss[tk]

if "u_a" not in st.session_state: st.session_state.u_a = ""
if "n_m" not in st.session_state: st.session_state.n_m = "ask"

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
                st.session_state.auth, st.session_state.user = True, u_in
                if rem:
                    tk = secrets.token_hex(16); sessions = load_j(SESSIONS_FILE, {}); sessions[tk] = u_in
                    save_j(SESSIONS_FILE, sessions); st.query_params["token"] = tk
                st.rerun()
            else: st.error("Błędne dane logowania")
    with t2:
        un = st.text_input("Nowy użytkownik", key="r_u").lower().strip()
        pn = st.text_input("Hasło", type="password", key="r_p")
        if st.button("Załóż konto", use_container_width=True):
            db = load_j(AUTH_FILE, {})
            if un and len(pn) >= 4 and un not in db:
                db[un] = hash_pw(pn); save_j(AUTH_FILE, db)
                save_j(get_p(un, "flashcards"), [])
                init_data = {"streak":0, "historical_cost":0.0, "time_stats":{}, "last_ts":time.time(), "last_seen":"Nigdy"}
                save_j(get_p(un, "user_data"), init_data)
                st.success("Konto utworzone!")
    st.stop()

# --- INIT DANYCH ---
u = st.session_state.user
st.session_state.flashcards = load_j(get_p(u, "flashcards"), [])
d_u = load_j(get_p(u, "user_data"), {})
for k, v in {"streak":0, "historical_cost":0.0, "time_stats":{}, "last_ts":time.time(), "last_seen":"Nigdy"}.items():
    if k not in d_u: d_u[k] = v
st.session_state.user_data = d_u

def update_activity(m="Inne"):
    curr = time.time()
    delta = curr - st.session_state.user_data.get("last_ts", curr)
    if 0 < delta < 600:
        stats = st.session_state.user_data.get("time_stats", {})
        m_clean = m.strip("📅 🚀 🕹️ 🎴 📸 📦 ➕ 📖 📊 ⚙️ ")
        stats[m_clean] = stats.get(m_clean, 0.0) + delta
        st.session_state.user_data["time_stats"] = stats
    st.session_state.user_data["last_ts"] = curr
    st.session_state.user_data["last_seen"] = datetime.now().strftime("%d.%m %H:%M:%S")
    save_j(get_p(u, "user_data"), st.session_state.user_data)

today_dt = date.today()
update_activity()

# --- MENU BOCZNE ---
st.sidebar.title(f"👤 {u.capitalize()}")
st.sidebar.caption(f"🚀 Wersja: {APP_VERSION}")
st.sidebar.info(f"🔥 Passa: **{st.session_state.user_data.get('streak', 0)} dni**")
if st.sidebar.button("Wyloguj", use_container_width=True):
    st.query_params.clear(); st.session_state.clear(); st.rerun()

menu = ["📅 Powtórki", "🚀 Trening", "🕹️ Quiz", "🎴 Fiszki", "📸 Skaner AI", "📦 Generator słów", "➕ Dodaj", "📖 Słownik", "📊 Statystyki", "⚙️ Moje Konto"]
if u == ADMIN_USER: menu.append("👑 Admin")
choice = st.sidebar.radio("Nawigacja", menu)

if "l_c" not in st.session_state or st.session_state.l_c != choice:
    for k in ["n_c", "q_c", "q_s", "f_idx", "f_flipped", "pending", "success_msg", "del_msg"]:
        if k in st.session_state: del st.session_state[k]
    st.session_state.n_m, st.session_state.u_a, st.session_state.l_c = "ask", "", choice

def is_correct(a, c):
    u_ans = str(a).strip().lower()
    c_ans = [s.strip().lower() for s in re.split(r'[/,;]', str(c))]
    return u_ans in c_ans

# --- 📅 POWTÓRKI / 🚀 TRENING ---
if choice in ["📅 Powtórki", "🚀 Trening"]:
    is_r = (choice == "📅 Powtórki")
    update_activity("Powtórki" if is_r else "Trening")
    all_cats = sorted(list(set([c.get("category", "Inne") for c in st.session_state.flashcards])))
    sel_kat = st.selectbox("🎯 Wybierz kategorię:", ["Wszystkie"] + all_cats)
    all_c = [c for c in st.session_state.flashcards if sel_kat == "Wszystkie" or c.get("category") == sel_kat]
    cards = [c for c in all_c if not is_r or c.get("next_review", str(today_dt)) <= str(today_dt)]
    
    st.info(f"Słówek do nauki: **{len(cards)}**")
    if not cards: st.success("Wszystko opanowane! 🎊")
    else:
        if "n_c" not in st.session_state: st.session_state.n_c = random.choice(cards)
        c = st.session_state.n_c
        st.write(f"### Słówko: **{c['de']}**")
        if st.session_state.n_m == "ask":
            with st.form("ans_f"):
                u_in = st.text_input("Twoja odpowiedź (PL):")
                if st.form_submit_button("Sprawdź", use_container_width=True):
                    st.session_state.u_a, st.session_state.n_m = u_in, "res"; st.rerun()
        else:
            if is_correct(st.session_state.u_a, c['pl']): st.success(f"✅ Dobrze: {c['pl']}")
            else: st.error(f"❌ Poprawnie: {c['pl']}")
            ex_list = c.get("examples")
            if isinstance(ex_list, list):
                for ex in ex_list:
                    if isinstance(ex, dict) and 'de' in ex:
                        st.markdown(f"🇩🇪 {ex['de']}<br>🇵🇱 {ex.get('pl','')}", unsafe_allow_html=True)
            play_audio(f"{c['de']} . . " + " . . ".join([e['de'] for e in ex_list if isinstance(e, dict) and 'de' in e]) if isinstance(ex_list, list) else c['de'])
            if is_r:
                st.write("---")
                c1, c2, c3 = st.columns(3); d = None
                if c1.button("🔴 Słabo (1d)", use_container_width=True): d = 1
                if c2.button("🟡 Średnio (3d)", use_container_width=True): d = 3
                if c3.button("🟢 Dobrze (7d)", use_container_width=True): d = 7
                if d:
                    c["next_review"] = str(today_dt + timedelta(days=d)); save_j(get_p(u, "flashcards"), st.session_state.flashcards)
                    st.toast(f"Powtórka za {d} dni!"); del st.session_state.n_c; st.session_state.n_m = "ask"; time.sleep(0.5); st.rerun()
            else:
                if st.button("Dalej ➡️", use_container_width=True):
                    del st.session_state.n_c; st.session_state.n_m = "ask"; st.rerun()

# --- 🎴 FISZKI ---
elif choice == "🎴 Fiszki":
    update_activity("Fiszki"); st.header("🎴 Fiszki")
    all_cats = sorted(list(set([c.get("category", "Inne") for c in st.session_state.flashcards])))
    sel_kat = st.selectbox("🎯 Wybierz kategorię:", ["Wszystkie"] + all_cats)
    cards = [c for c in st.session_state.flashcards if sel_kat == "Wszystkie" or c.get("category") == sel_kat]
    if cards:
        if "f_idx" not in st.session_state: st.session_state.f_idx = 0
        if "f_flipped" not in st.session_state: st.session_state.f_flipped = False
        c = cards[st.session_state.f_idx % len(cards)]
        word_txt = c["pl"] if st.session_state.f_flipped else c["de"]
        ex_html = ""
        if st.session_state.f_flipped:
            ex_list = c.get("examples")
            if isinstance(ex_list, list):
                for ex in ex_list:
                    if isinstance(ex, dict) and 'de' in ex:
                        ex_html += f"<div style='margin-top:15px; border-top:1px solid #444; padding-top:10px;'><span style='color:#FFEB3B; font-weight:bold;'>🇩🇪 {ex['de']}</span><br><span style='color:white;'>🇵🇱 {ex.get('pl','')}</span></div>"
        box_style = "min-height:350px; display:flex; flex-direction:column; align-items:center; justify-content:center; background:black; border:3px solid #FF5252; border-radius:30px; padding:30px; text-align:center;"
        st.markdown(f'<div style="{box_style}"><h1 style="color:white; margin:0; font-size:2.2em;">{word_txt}</h1>{ex_html}</div>', unsafe_allow_html=True)
        st.write("<br>", unsafe_allow_html=True)
        c1, c2, c3 = st.columns([1, 1.2, 1])
        if c1.button("⬅️ Wstecz", use_container_width=True): st.session_state.f_idx -= 1; st.session_state.f_flipped = False; st.rerun()
        if c2.button("🔄 OBRÓĆ", type="primary", use_container_width=True): st.session_state.f_flipped = not st.session_state.f_flipped; st.rerun()
        if c3.button("Dalej ➡️", use_container_width=True): st.session_state.f_idx += 1; st.session_state.f_flipped = False; st.rerun()
        if st.session_state.f_flipped: play_audio(f"{c['de']} . . " + " . . ".join([e['de'] for e in c.get('examples', []) if isinstance(e, dict) and 'de' in e]) if isinstance(c.get('examples'), list) else c['de'])

# --- 🕹️ QUIZ ---
elif choice == "🕹️ Quiz":
    update_activity("Quiz"); all_c = st.session_state.flashcards
    if len(all_c) < 4: st.warning("Dodaj min. 4 słówka!")
    else:
        if "q_c" not in st.session_state:
            t = random.choice(all_c); opts = random.sample([x['pl'] for x in all_c if x['pl']!=t['pl']], 3) + [t['pl']]
            random.shuffle(opts); st.session_state.update({"q_c":t, "q_a":t['pl'], "q_o":opts, "q_s":"ask"})
        st.write(f"### Jak przetłumaczysz: **{st.session_state.q_c['de']}**")
        if st.session_state.q_s == "ask":
            for o in st.session_state.q_o:
                if st.button(o, key=o, use_container_width=True):
                    st.session_state.u_q, st.session_state.q_s = o, "res"; st.rerun()
        else:
            if st.session_state.get("u_q") == st.session_state.q_a:
                st.success("✅ Brawo!"); c_q = st.session_state.q_c
                if c_q.get("next_review", str(today_dt)) <= str(today_dt):
                    c_q["next_review"] = str(today_dt + timedelta(days=1))
                    save_j(get_p(u, "flashcards"), st.session_state.flashcards); st.toast("+1 dzień!")
            else: st.error(f"❌ Błąd. Poprawnie: {st.session_state.q_a}")
            ex_list = st.session_state.q_c.get('examples')
            play_audio(f"{st.session_state.q_c['de']} . . " + " . . ".join([e['de'] for e in ex_list if isinstance(e, dict) and 'de' in e]) if isinstance(ex_list, list) else st.session_state.q_c['de'])
            if st.button("Dalej", use_container_width=True): del st.session_state.q_c; st.rerun()

# --- 📸 SKANER AI ---
elif choice == "📸 Skaner AI":
    update_activity("Skaner"); 
    if "success_msg" in st.session_state: st.success(st.session_state.success_msg); del st.session_state.success_msg
    src = st.camera_input("Zrób zdjęcie"); up = st.file_uploader("Lub wybierz plik")
    if (src or up) and st.button("🚀 ANALIZUJ", use_container_width=True):
        try:
            with st.spinner("Przetwarzanie..."):
                img = Image.open(src or up).convert("RGB")
                req = "Extract German vocabulary. For EACH word: translate to Polish, generate EXACTLY 2 independent sentences containing the word, and assign a Polish category. Output JSON object with key 'flashcards'."
                res = get_openai_response(req, img_obj=img); data = parse_ai_json(res)
                if isinstance(data, dict) and "flashcards" in data:
                    st.session_state.pending = data["flashcards"]
                    st.session_state.user_data["historical_cost"] += 0.02; st.rerun()
        except Exception as e: st.error(f"Błąd AI: {e}")
    if "pending" in st.session_state:
        df_p = pd.DataFrame(st.session_state.pending)
        ed = st.data_editor(df_p, use_container_width=True)
        if st.button("✅ ZAPISZ DO BAZY", use_container_width=True):
            added = 0
            for w in ed.to_dict('records'):
                if 'de' in w and 'pl' in w and w['de'].lower() not in [x['de'].lower() for x in st.session_state.flashcards]:
                    w.update({"next_review": str(today_dt), "date_added": str(today_dt)}); st.session_state.flashcards.append(w); added += 1
            save_j(get_p(u, "flashcards"), st.session_state.flashcards); del st.session_state.pending
            st.session_state.success_msg = f"🎉 Dodano {added} słówek!"; st.rerun()

# --- 📦 GENERATOR SŁÓW (HYBRYDOWY V172) ---
elif choice == "📦 Generator słów":
    update_activity("Generator"); 
    if "success_msg" in st.session_state: st.success(st.session_state.success_msg); del st.session_state.success_msg
    cols = st.columns(5); lvls = ["A1", "A2", "B1", "B2", "C1"]
    for i, lvl in enumerate(lvls):
        if cols[i].button(lvl, use_container_width=True):
            with st.spinner(f"Przygotowuję 25 słówek z poziomu {lvl}..."):
                try:
                    all_potential = VOCAB_DB.get(lvl, [])
                    my_words = [x['de'].lower() for x in st.session_state.flashcards]
                    new_selection = [w for w in all_potential if w.lower() not in my_words]
                    
                    if len(new_selection) < 25:
                        prompt = f"Generate EXACTLY 25 common, unique German words level {lvl} NOT IN: {my_words[:50]}. Translate to Polish, provide a Polish category, and EXACTLY 2 independent German sentences per word. Output JSON object with key 'flashcards'."
                    else:
                        subset = new_selection[:25]
                        prompt = (f"Translate these 25 German words to Polish: {subset}. "
                                 f"For EACH word provide: Polish translation, Polish category, and EXACTLY 2 independent sentences EACH containing that word. "
                                 f"Output ONLY a JSON object with key 'flashcards'. Use keys: 'de', 'pl', 'category', 'examples'.")
                    
                    res = get_openai_response(prompt); data = parse_ai_json(res)
                    if isinstance(data, dict) and "flashcards" in data:
                        added = 0
                        for w in data["flashcards"]:
                            # Auto-korekta kluczy, jeśli AI się pomyli
                            txt_de = w.get('de') or w.get('word') or w.get('german')
                            txt_pl = w.get('pl') or w.get('polish') or w.get('translation')
                            
                            if txt_de and txt_pl:
                                if txt_de.lower() not in [x['de'].lower() for x in st.session_state.flashcards]:
                                    w.update({"de": txt_de, "pl": txt_pl, "next_review": str(today_dt), "date_added": str(today_dt), "category": f"{lvl} - {w.get('category','Inne')}"})
                                    st.session_state.flashcards.append(w); added += 1
                        
                        st.session_state.user_data["historical_cost"] += 0.01; save_j(get_p(u, "flashcards"), st.session_state.flashcards)
                        if added > 0:
                            st.session_state.success_msg = f"🎉 Sukces! Dodano {added} nowych słówek!"; st.rerun()
                        else: st.warning("AI nie zwróciło nowych słówek. Spróbuj jeszcze raz.")
                    else: st.error("Błąd formatu AI. Spróbuj ponownie.")
                except Exception as e: st.error(f"Błąd: {e}")

# --- ➕ DODAJ / 📖 SŁOWNIK / 📊 STATYSTYKI ---
elif choice == "➕ Dodaj":
    st.header("➕ Dodaj słówko"); update_activity("Dodaj")
    with st.form("manual_f"):
        de, pl, kat = st.text_input("Niemiecki"), st.text_input("Polski"), st.text_input("Kategoria")
        if st.form_submit_button("Zapisz"):
            if de and pl:
                st.session_state.flashcards.append({"de":de, "pl":pl, "category":kat or "Inne", "next_review":str(today_dt), "date_added":str(today_dt), "examples":[]})
                save_j(get_p(u, "flashcards"), st.session_state.flashcards); st.success("Dodano!")

elif choice == "📖 Słownik":
    update_activity("Słownik"); cats = sorted(list(set([c.get("category", "Inne") for c in st.session_state.flashcards])))
    f_kat = st.selectbox("Filtruj:", ["Wszystkie"] + cats); search = st.text_input("Szukaj:")
    for i, c in enumerate(st.session_state.flashcards):
        if (f_kat == "Wszystkie" or c.get("category") == f_kat) and (search.lower() in c['de'].lower() or search.lower() in c['pl'].lower()):
            with st.expander(f"📝 {c['de']} — {c['pl']}"):
                with st.form(f"ed_{i}"):
                    n_de, n_pl, n_ka = st.text_input("DE", c['de']), st.text_input("PL", c['pl']), st.text_input("KAT", c.get('category','Inne'))
                    if st.form_submit_button("Zapisz"):
                        c.update({"de":n_de, "pl":n_pl, "category":n_ka}); save_j(get_p(u,"flashcards"), st.session_state.flashcards); st.rerun()
                    if st.form_submit_button("Usuń"):
                        st.session_state.flashcards.pop(i); save_j(get_p(u,"flashcards"), st.session_state.flashcards); st.rerun()

elif choice == "📊 Statystyki":
    update_activity("Statystyki"); df = pd.DataFrame(st.session_state.flashcards)
    if not df.empty:
        c1, c2, c3 = st.columns(3); c1.metric("Słów", len(df)); c2.metric("Passa", f"{st.session_state.user_data['streak']} dni")
        opanowane = len(df[df['next_review'].apply(lambda x: (date.fromisoformat(str(x)) - today_dt).days >= 7)])
        c3.metric("Opanowane", opanowane); st.subheader("Plan powtórek")
        stats_data = [{"Data": (today_dt + timedelta(days=i)).strftime("%d.%m"), "Słów": len(df[df['next_review'] == str(today_dt + timedelta(days=i))])} for i in range(10)]
        st.bar_chart(pd.DataFrame(stats_data).set_index("Data"))

# --- ⚙️ MOJE KONTO (RECOVERY & COUNTER) ---
elif choice == "⚙️ Moje Konto":
    st.header("⚙️ Moje Konto"); update_activity("Konto")
    if "del_msg" in st.session_state: st.success(st.session_state.del_msg); del st.session_state.del_msg
    with st.expander("🔑 Zmień hasło"):
        with st.form("pw_f"):
            o, n, cp = st.text_input("Stare", type="password"), st.text_input("Nowe", type="password"), st.text_input("Powtórz", type="password")
            if st.form_submit_button("Zmień"):
                db = load_j(AUTH_FILE, {})
                if db.get(u) == hash_pw(o) and n == cp:
                    db[u] = hash_pw(n); save_j(AUTH_FILE, db); st.success("Zmieniono!")
    st.divider(); st.subheader("⚠️ Usuwanie danych poziomami")
    conf = st.checkbox("Potwierdzam chęć usunięcia")
    lvls = ["A1", "A2", "B1", "B2", "C1"]
    col_d = st.columns(5)
    for i, lvl in enumerate(lvls):
        if col_d[i].button(f"Usuń {lvl}", disabled=not conf, use_container_width=True):
            before = len(st.session_state.flashcards)
            st.session_state.flashcards = [x for x in st.session_state.flashcards if lvl not in str(x.get('category',''))]
            save_j(get_p(u, "flashcards"), st.session_state.flashcards)
            diff = before - len(st.session_state.flashcards)
            st.session_state.del_msg = f"🗑️ Usunięto {diff} słówek z poziomu {lvl}!"; st.rerun()
    if st.button("🗑️ RESET CAŁEJ BAZY", type="primary", disabled=not conf, use_container_width=True):
        before = len(st.session_state.flashcards); save_j(get_p(u, "flashcards"), []); st.session_state.flashcards = []
        st.session_state.del_msg = f"🗑️ Usunięto wszystkie {before} słówek!"; st.rerun()

# --- 👑 ADMIN ---
elif choice == "👑 Admin":
    st.header("👑 Panel Admina"); users = load_j(AUTH_FILE, {}); adm_list = []; global_time = {m: 0.0 for m in MODULE_ORDER}
    m1, m2 = st.columns(2)
    for usr in users:
        ud, ub = load_j(get_p(usr, "user_data"), {}), load_j(get_p(usr, "flashcards"), [])
        df_u = pd.DataFrame(ub); mastery, ai_n = "0%", 0
        if not df_u.empty:
            opanowane = len(df_u[df_u['next_review'].apply(lambda x: (pd.to_datetime(x).date()-today_dt).days >= 7)])
            mastery = f"{round((opanowane/len(df_u))*100)}%"; ai_n = len(df_u[df_u['category'].str.contains('Skaner|Generator', case=False, na=False)])
        t_s = ud.get("time_stats", {})
        for m in MODULE_ORDER: global_time[m] += t_s.get(m, 0.0)
        u_times = ", ".join([f"{m[0]}:{round(s/60)}m" for m, s in t_s.items() if s > 15])
        adm_list.append({"Użytkownik":usr, "Słów":len(ub), "AI":ai_n, "%":mastery, "Ostatnio":ud.get("last_seen","Nigdy"), "Czas":u_times or "Brak"})
    m1.metric("Łącznie słówek", sum(x['Słów'] for x in adm_list))
    total_spent = sum(load_j(get_p(usr_n, 'user_data'), {}).get('historical_cost', 0.0) for usr_n in users)
    m2.metric("Szac. koszt AI", f"{total_spent:.2f} PLN")
    st.markdown("[🔗 **Panel Billing OpenAI**](https://platform.openai.com/usage)")
    st.table(pd.DataFrame(adm_list)); total_g = sum(global_time.values())
    if total_g > 0:
        vals = [global_time[m] for m in MODULE_ORDER]; labels = [f"{m}: {round(v/60,1)} min" for m, v in zip(MODULE_ORDER, vals)]
        fig = go.Figure(data=[go.Bar(x=MODULE_ORDER, y=vals, text=labels, textposition='auto', marker_color='#1E88E5')])
        fig.update_layout(template="plotly_dark", height=450); st.plotly_chart(fig, use_container_width=True)
