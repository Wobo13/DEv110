import streamlit as st
import json
import os
import random
import re
import hashlib
import pandas as pd
import secrets
import base64
import tempfile
from datetime import datetime, date, timedelta
from io import BytesIO
from PIL import Image
import time
import plotly.graph_objects as go

# Import biblioteki OpenAI
from openai import OpenAI

# --- KONFIGURACJA ---
APP_VERSION = "V178 (Test Score Fix & Stats)"
ADMIN_USER = "wobo"
AUTH_FILE = "users_auth.json"
SESSIONS_FILE = "sessions.json"
BONUS_START = 1089.0

# Pobieranie klucza API
API_KEY = st.secrets.get("OPENAI_API_KEY") or st.secrets.get("GEMINI_API_KEY") or st.session_state.get("manual_api_key", "")

# NOWA KOLEJNOŚĆ (Testy pod Fiszkami)
MODULE_ORDER = [
    "Powtórki", "Trening", "Quiz", "Fiszki", "Testy",
    "Skaner", "Generator", "Dodaj", "Słownik"
]

# --- WEWNĘTRZNA BAZA SŁÓWEK ---
VOCAB_DB = {
    "A1": ["Apfel", "Brot", "Haus", "Auto", "Schule", "Lehrer", "Wasser", "Milch", "Tisch", "Stuhl", "Buch", "Stift", "Kind", "Mutter", "Vater", "Freund", "Stadt", "Land", "Weg", "Zeit", "Essen", "Trinken", "Schlafen", "Lernen", "Arbeiten", "Gehen", "Kommen", "Hören", "Sehen", "Sprechen", "Groß", "Klein", "Gut", "Schlecht", "Schön", "Hässlich", "Alt", "Jung", "Neu", "Kalt", "Heute", "Morgen", "Gestern", "Woche", "Jahr", "Tag", "Nacht", "Name", "Zahl", "Geld"],
    "A2": ["Urlaub", "Reise", "Bahnhof", "Flugzeug", "Hotel", "Küche", "Kühlschrank", "Gabel", "Löffel", "Messer", "Kleidung", "Hose", "Hemd", "Schuh", "Wetter", "Regen", "Sonne", "Wolke", "Gesundheit", "Krankheit", "Arzt", "Medizin", "Körper", "Kopf", "Hand", "Fuß", "Sport", "Spiel", "Musik", "Film", "Besuchen", "Verstehen", "Vergessen", "Bestellen", "Bezahlen", "Wohnen", "Mieten", "Kaufen", "Verkaufen", "Feiern", "Wichtig", "Wahr", "Falsch", "Fertig", "Glücklich", "Traurig", "Müde", "Sauer", "Süß", "Heiß"],
    "B1": ["Erfahrung", "Erfolg", "Entscheidung", "Meinung", "Gefühl", "Beziehung", "Zukunft", "Vergangenheit", "Umwelt", "Natur", "Gesellschaft", "Politik", "Wirtschaft", "Wissenschaft", "Technik", "Beruf", "Ausbildung", "Studium", "Gehalt", "Vertrag", "Vorbereiten", "Organisieren", "Diskutieren", "Argumentieren", "Erklären", "Empfehlen", "Vorschlagen", "Warnen", "Hoffen", "Träumen", "Gefährlich", "Sicher", "Möglich", "Unmöglich", "Nötig", "Nützlich", "Schwierig", "Leicht", "Interessant", "Langweilig", "Obwohl", "Trotzdem", "Deshalb", "Deswegen", "Falls", "Damit", "Stattdessen", "Zuerst", "Schließlich", "Besonders"],
    "B2": ["Herausforderung", "Verantwortung", "Voraussetzung", "Zusammenhang", "Unterschied", "Vergleich", "Entwicklung", "Fortschritt", "Ursache", "Wirkung", "Eindruck", "Einfluss", "Ergebnis", "Erwartung", "Gerechtigkeit", "Freiheit", "Sicherheit", "Vertrauen", "Geduld", "Vorsicht", "Beeinflussen", "Verbessern", "Verschlechtern", "Erreichen", "Vermeiden", "Lösen", "Teilnehmen", "Unterstützen", "Fördern", "Fordern", "Effizient", "Effektiv", "Kreativ", "Kritisch", "Logisch", "Objektiv", "Subjektiv", "Typisch", "Zufällig", "Regelmäßig", "Anscheinend", "Vermutlich", "Eventuell", "Tatsächlich", "Grundsätzlich", "Eigentlich", "Überall", "Nirgendwo", "Irgendwie", "Sowieso"],
    "C1": ["Auseinandersetzung", "Auswirkung", "Bedeutung", "Erkenntnis", "Fähigkeit", "Maßnahme", "Notwendigkeit", "Perspektive", "Struktur", "Vielfalt", "Anforderung", "Bewältigung", "Darstellung", "Einschätzung", "Gewährleistung", "Hintergrund", "Integration", "Kompetenz", "Nachhaltigkeit", "Umsetzung", "Analysieren", "Berücksichtigen", "Differenzieren", "Evaluieren", "Gewährleisten", "Hinterfragen", "Implementieren", "Konkretisieren", "Reflektieren", "Veranschaulichen", "Außergewöhnlich", "Beträchtlich", "Eindeutig", "Erheblich", "Gravierend", "Kontrovers", "Nachhaltig", "Präzise", "Umfangreich", "Wesentliche", "Dementsprechend", "Demnach", "Infolgedessen", "Inwiefern", "Inwieweit", "Jegliche", "Lediglich", "Nichtsdestotrotz", "Stufenweise", "Zunehmend"]
}

# --- SYSTEM POMOCNICZY ---
def hash_pw(pw): return hashlib.sha256(str.encode(pw)).hexdigest()
def get_p(u, t): return f"{t}_{u}.json"

def load_j(p, d):
    if os.path.exists(p):
        try:
            with open(p, "r", encoding="utf-8") as f: return json.load(f)
        except: return d
    return d

def save_j(p, d):
    dir_name = os.path.dirname(p) or '.'
    try:
        fd, temp_path = tempfile.mkstemp(dir=dir_name, text=True)
        with os.fdopen(fd, 'w', encoding='utf-8') as f: 
            json.dump(d, f, indent=4)
        os.replace(temp_path, p)
    except Exception as e:
        with open(p, "w", encoding="utf-8") as f: json.dump(d, f, indent=4)

def is_word_mastered(next_review_date):
    try:
        if not next_review_date: return False
        days_diff = (date.fromisoformat(str(next_review_date)) - date.today()).days
        return days_diff >= 7
    except:
        return False

def force_save():
    save_j(get_p(st.session_state.user, "flashcards"), st.session_state.flashcards)
    save_j(get_p(st.session_state.user, "user_data"), st.session_state.user_data)

def play_audio(txt):
    try:
        from gtts import gTTS
        f = BytesIO(); tts = gTTS(text=txt, lang='de'); tts.write_to_fp(f); f.seek(0)
        st.audio(f, format="audio/mp3", autoplay=True)
    except: pass

def parse_ai_json(text):
    try:
        match = re.search(r'(\{.*\}|\[.*\])', text, re.DOTALL)
        if match:
            clean = match.group(0).strip()
            return json.loads(clean)
        return json.loads(text.strip())
    except: return None

# UNIWERSALNA FUNKCJA SPRAWDZAJĄCA ODPOWIEDŹ TESTOWĄ
def check_test_answer(u_ans, q_obj):
    user = str(u_ans).strip().lower()
    correct = str(q_obj['correct']).strip().lower()
    if not user: return False
    # Dla tłumaczeń pozwalamy na małe różnice (np. brak kropki), ale musi być zgodność słów
    if q_obj['type'] == "TLUMACZENIE":
        u_clean = re.sub(r'[^\w\s]', '', user)
        c_clean = re.sub(r'[^\w\s]', '', correct)
        return u_clean == c_clean
    return user == correct

# --- SILNIK AI: OPENAI ---
def get_openai_response(prompt_text, img_obj=None):
    if not API_KEY: raise Exception("Brak klucza API OpenAI.")
    client = OpenAI(api_key=API_KEY)
    messages = [{"role": "system", "content": "You are a professional German teacher. Output ONLY valid JSON in Polish language for categories and translations."}]
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
        if tk in ss: st.session_state.auth, st.session_state.user = True, ss[tk]

if "u_a" not in st.session_state: st.session_state.u_a = ""
if "n_m" not in st.session_state: st.session_state.n_m = "ask"

if not st.session_state.auth:
    st.title("🚀 Niemiecki Master")
    t1, t2 = st.tabs(["🔐 Logowanie", "📝 Rejestracja"])
    with t1:
        u_in = st.text_input("Użytkownik", key="l_u").lower().strip()
        p_in = st.text_input("Hasło", type="password", key="l_p")
        if st.button("Zaloguj się", use_container_width=True, type="primary"):
            db = load_j(AUTH_FILE, {})
            if u_in in db and db[u_in] == hash_pw(p_in):
                st.session_state.auth, st.session_state.user = True, u_in
                tk = secrets.token_hex(16); sessions = load_j(SESSIONS_FILE, {}); sessions[tk] = u_in
                save_j(SESSIONS_FILE, sessions); st.query_params["token"] = tk
                st.rerun()
            else: st.error("Błędne dane")
    with t2:
        un = st.text_input("Nowy użytkownik", key="r_u").lower().strip()
        pn = st.text_input("Hasło", type="password", key="r_p")
        if st.button("Załóż konto", use_container_width=True):
            db = load_j(AUTH_FILE, {})
            if not un or len(pn) < 4:
                st.error("Nazwa użytkownika jest wymagana, a hasło musi mieć min. 4 znaki.")
            elif un in db:
                st.error("Użytkownik o takiej nazwie już istnieje.")
            else:
                db[un] = hash_pw(pn); save_j(AUTH_FILE, db)
                save_j(get_p(un, "flashcards"), [])
                init_data = {"streak":0, "historical_cost":0.0, "time_stats":{}, "last_ts":time.time(), "last_seen":"Nigdy", "test_history": []}
                save_j(get_p(un, "user_data"), init_data); st.success("Utworzono konto!")
    st.stop()

# --- INIT DANYCH ---
u = st.session_state.user
st.session_state.flashcards = load_j(get_p(u, "flashcards"), [])
d_u = load_j(get_p(u, "user_data"), {})
# Migracja brakujących kluczy
for k, v in {"streak":0, "historical_cost":0.0, "time_stats":{}, "last_ts":time.time(), "last_seen":"Nigdy", "test_history": []}.items():
    if k not in d_u: d_u[k] = v
st.session_state.user_data = d_u

def update_activity(m="Inne"):
    curr = time.time()
    delta = curr - st.session_state.user_data.get("last_ts", curr)
    if 0 < delta < 600:
        stats = st.session_state.user_data.get("time_stats", {})
        m_clean = m.strip("📅 🚀 🕹️ 🎴 📸 📦 ➕ 📖 📊 ⚙️ 📝")
        stats[m_clean] = stats.get(m_clean, 0.0) + delta
        st.session_state.user_data["time_stats"] = stats
    st.session_state.user_data["last_ts"] = curr
    st.session_state.user_data["last_seen"] = datetime.now().strftime("%d.%m %H:%M:%S")
    save_j(get_p(st.session_state.user, "user_data"), st.session_state.user_data)

today_dt = date.today()
update_activity()

# --- MENU BOCZNE ---
st.sidebar.title(f"👤 {u.capitalize()}")
st.sidebar.caption(f"🚀 Wersja: {APP_VERSION}")
st.sidebar.info(f"🔥 Passa: **{st.session_state.user_data.get('streak', 0)} dni**")
if st.sidebar.button("Wyloguj", use_container_width=True):
    if "token" in st.query_params:
        tk = st.query_params["token"]
        ss = load_j(SESSIONS_FILE, {})
        if tk in ss: del ss[tk]; save_j(SESSIONS_FILE, ss)
    st.query_params.clear(); st.session_state.clear(); st.rerun()

# PRZEMIESZCZONE MENU (Testy pod Fiszkami)
menu = ["📅 Powtórki", "🚀 Trening", "🕹️ Quiz", "🎴 Fiszki", "📝 Testy", "📸 Skaner AI", "📦 Generator słów", "➕ Dodaj", "📖 Słownik", "📊 Statystyki", "⚙️ Moje Konto"]
if u == ADMIN_USER: menu.append("👑 Admin")
choice = st.sidebar.radio("Nawigacja", menu)

if "l_c" not in st.session_state or st.session_state.l_c != choice:
    for k in ["n_idx", "q_c", "q_s", "f_idx", "f_flipped", "pending", "success_msg", "del_msg", "test_q", "test_idx"]:
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
    sel_kat = st.selectbox("🎯 Kategoria:", ["Wszystkie"] + all_cats)
    indexed_cards = [(i, c) for i, c in enumerate(st.session_state.flashcards) if sel_kat == "Wszystkie" or c.get("category") == sel_kat]
    if is_r:
        cards_to_show = [(i, c) for i, c in indexed_cards if c.get("next_review", str(today_dt)) <= str(today_dt)]
    else:
        cards_to_show = indexed_cards
    st.info(f"Słówek w tej sekcji: **{len(cards_to_show)}**")
    if not cards_to_show:
        st.success("Wszystko opanowane! 🎊")
    else:
        if "n_idx" not in st.session_state or st.session_state.n_idx >= len(cards_to_show):
            st.session_state.n_idx = 0; random.shuffle(cards_to_show)
        orig_idx, c = cards_to_show[st.session_state.n_idx]
        st.write(f"### Słówko: **{c['de']}**")
        if st.session_state.n_m == "ask":
            with st.form("ans_f"):
                u_in = st.text_input("Twoja odpowiedź (PL):")
                if st.form_submit_button("Sprawdź", use_container_width=True):
                    st.session_state.u_a, st.session_state.n_m = u_in, "res"; st.rerun()
        else:
            if is_correct(st.session_state.u_a, c['pl']): st.success(f"✅ Dobrze: {c['pl']}")
            else: st.error(f"❌ Poprawnie: {c['pl']}")
            ex_list = c.get("examples", [])
            if isinstance(ex_list, list):
                for ex in ex_list:
                    if isinstance(ex, dict) and 'de' in ex:
                        st.markdown(f"🇩🇪 {ex['de']}<br>🇵🇱 {ex.get('pl','')}", unsafe_allow_html=True)
            play_audio(c['de'])
            if is_r:
                st.write("---")
                col1, col2, col3 = st.columns(3); d = None
                if col1.button("🔴 Słabo (1d)", use_container_width=True): d = 1
                if col2.button("🟡 Średnio (3d)", use_container_width=True): d = 3
                if col3.button("🟢 Dobrze (7d)", use_container_width=True): d = 7
                if d:
                    st.session_state.flashcards[orig_idx]["next_review"] = str(today_dt + timedelta(days=d))
                    force_save(); st.toast(f"Przesunięto o {d} dni!"); st.session_state.n_m = "ask"; st.rerun()
            else:
                if st.button("Dalej ➡️", use_container_width=True):
                    st.session_state.n_idx += 1; st.session_state.n_m = "ask"; st.rerun()

# --- 🎴 FISZKI ---
elif choice == "🎴 Fiszki":
    update_activity("Fiszki"); st.header("🎴 Fiszki")
    all_cats = sorted(list(set([c.get("category", "Inne") for c in st.session_state.flashcards])))
    sel_kat = st.selectbox("🎯 Kategoria:", ["Wszystkie"] + all_cats)
    cards = [c for c in st.session_state.flashcards if sel_kat == "Wszystkie" or c.get("category") == sel_kat]
    if cards:
        if "f_idx" not in st.session_state: st.session_state.f_idx = 0
        if "f_flipped" not in st.session_state: st.session_state.f_flipped = False
        c = cards[st.session_state.f_idx % len(cards)]
        word_txt = c["pl"] if st.session_state.f_flipped else c["de"]
        ex_html = ""
        if st.session_state.f_flipped:
            ex_list = c.get("examples", [])
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
        if st.session_state.f_flipped: play_audio(c['de'])

# --- 📝 TESTY (V178 - Score Fix & Stats) ---
elif choice == "📝 Testy":
    update_activity("Testy"); st.header("📝 Egzamin Kontekstowy")
    if len(st.session_state.flashcards) < 5: st.warning("Potrzebujesz min. 5 słówek.")
    else:
        if "test_q" not in st.session_state:
            all_cats = sorted(list(set([c.get("category", "Inne") for c in st.session_state.flashcards])))
            sel_kat = st.selectbox("🎯 Wybierz zakres testu:", ["Wszystkie"] + all_cats)
            n_q = st.slider("Liczba pytań", 5, 20, 5)
            if st.button("🚀 GENERUJ TEST", use_container_width=True, type="primary"):
                with st.spinner("Przygotowanie..."):
                    filtered = [c for c in st.session_state.flashcards if sel_kat == "Wszystkie" or c.get("category") == sel_kat]
                    if len(filtered) < 5: st.error("Zbyt mało słówek.")
                    else:
                        sample = random.sample(filtered, min(n_q, len(filtered)))
                        words_str = ", ".join([f"{w['de']} ({w['pl']})" for w in sample])
                        prompt = f"Generate a German test for: {words_str}. Rotate types: 'LUKA', 'QUIZ', 'TLUMACZENIE'. Output JSON: {{\"questions\": [ {{\"type\": \"LUKA\", \"sentence\": \"...\", \"correct\": \"...\", \"hint\": \"...\"}}, ... ]}}"
                        try:
                            res = get_openai_response(prompt); data = parse_ai_json(res)
                            if data and "questions" in data:
                                st.session_state.test_q, st.session_state.test_idx, st.session_state.test_score = data["questions"], 0, 0
                                st.session_state.user_data["historical_cost"] += 0.01; st.rerun()
                        except Exception as e: st.error(f"Błąd: {e}")
        else:
            qs = st.session_state.test_q; idx = st.session_state.test_idx
            if idx < len(qs):
                q = qs[idx]; st.write(f"### Pytanie {idx+1} z {len(qs)}"); st.progress(idx / len(qs))
                u_ans = ""
                if q['type'] == "LUKA":
                    st.info(f"Podpowiedź (PL): {q.get('hint', 'brak')}"); st.markdown(f"#### `{q['sentence']}`")
                    u_ans = st.text_input("Wpisz brakujące słowo (DE):", key=f"q_{idx}")
                elif q['type'] == "QUIZ":
                    st.info(f"Podpowiedź (PL): {q.get('hint', 'brak')}"); st.markdown(f"#### `{q['sentence']}`")
                    opts = q.get('distractors', []) + [q['correct']]; random.seed(idx); random.shuffle(opts)
                    u_ans = st.radio("Wybierz opcję:", opts, key=f"q_{idx}")
                elif q['type'] == "TLUMACZENIE":
                    st.info("Przetłumacz na niemiecki:"); st.markdown(f"#### {q['sentence']}")
                    u_ans = st.text_input("Twoja odpowiedź:", key=f"q_{idx}")
                if st.button("Zatwierdź ➡️", use_container_width=True):
                    st.session_state.test_q[idx]['user_ans'] = u_ans
                    if check_test_answer(u_ans, q):
                        st.session_state.test_score += 1; st.toast("Dobrze! 🌟")
                    else: st.error(f"Źle. Poprawnie: {q['correct']}"); time.sleep(1)
                    st.session_state.test_idx += 1; st.rerun()
            else:
                st.balloons(); score = st.session_state.test_score; total = len(qs); perc = round((score/total)*100)
                # ZAPIS DO HISTORII
                st.session_state.user_data["test_history"].append({"date": datetime.now().strftime("%d.%m %H:%M"), "score": score, "total": total, "perc": perc})
                save_j(get_p(u, "user_data"), st.session_state.user_data)
                st.markdown(f'<div style="text-align:center; padding:30px; border-radius:20px; background:#111; border:2px solid #1E88E5; margin-bottom:25px;"><h1>Wynik: {score} / {total}</h1><h2 style="color:#1E88E5;">Sprawność: {perc}%</h2></div>', unsafe_allow_html=True)
                st.subheader("📋 Szczegółowy raport:");
                for i, q in enumerate(qs):
                    u_a, c_a = q.get('user_ans', ''), q['correct']
                    is_ok = check_test_answer(u_a, q)
                    icon, color = ("✅", "#2E7D32") if is_ok else ("❌", "#C62828")
                    with st.expander(f"{icon} Pytanie {i+1}"):
                        st.write(f"**Zdanie:** {q['sentence']}")
                        st.markdown(f'<div style="padding:10px; border-radius:10px; background:{color}22; border-left:5px solid {color};"><p>Twoja: <b>{u_a}</b></p><p>Poprawna: <b>{c_a}</b></p></div>', unsafe_allow_html=True)
                if st.button("Powrót", use_container_width=True, type="primary"): del st.session_state.test_q; st.rerun()

# --- 🕹️ QUIZ ---
elif choice == "🕹️ Quiz":
    update_activity("Quiz"); all_c = st.session_state.flashcards
    if len(all_c) < 4: st.warning("Dodaj min. 4 słówka!")
    else:
        if "q_c" not in st.session_state:
            idx = random.randrange(len(all_c)); t = all_c[idx]
            opts = random.sample([x['pl'] for x in all_c if x['pl']!=t['pl']], 3) + [t['pl']]; random.shuffle(opts)
            st.session_state.update({"q_idx":idx, "q_c":t, "q_a":t['pl'], "q_o":opts, "q_s":"ask"})
        st.write(f"### Jak przetłumaczysz: **{st.session_state.q_c['de']}**")
        if st.session_state.q_s == "ask":
            for o in st.session_state.q_o:
                if st.button(o, key=o, use_container_width=True): st.session_state.u_q, st.session_state.q_s = o, "res"; st.rerun()
        else:
            if st.session_state.get("u_q") == st.session_state.q_a:
                st.success("✅ Brawo!")
                orig_idx = st.session_state.q_idx
                if st.session_state.flashcards[orig_idx].get("next_review", str(today_dt)) <= str(today_dt):
                    st.session_state.flashcards[orig_idx]["next_review"] = str(today_dt + timedelta(days=1))
                    force_save(); st.toast("+1 dzień do powtórki!")
            else: st.error(f"❌ Błąd. Poprawnie: {st.session_state.q_a}")
            play_audio(st.session_state.q_c['de'])
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
                req = "Extract German vocabulary. JSON object with key 'flashcards'."
                res = get_openai_response(req, img_obj=img); data = parse_ai_json(res)
                if isinstance(data, dict) and "flashcards" in data:
                    st.session_state.pending = data["flashcards"]
                    st.session_state.user_data["historical_cost"] += 0.02; st.rerun()
        except Exception as e: st.error(f"Błąd AI: {e}")
    if "pending" in st.session_state:
        ed = st.data_editor(pd.DataFrame(st.session_state.pending), use_container_width=True)
        if st.button("✅ ZAPISZ", use_container_width=True):
            added = 0
            for w in ed.to_dict('records'):
                if 'de' in w and 'pl' in w and w['de'].lower() not in [x['de'].lower() for x in st.session_state.flashcards]:
                    w.update({"next_review": str(today_dt), "date_added": str(today_dt)}); st.session_state.flashcards.append(w); added += 1
            force_save(); del st.session_state.pending; st.session_state.success_msg = f"🎉 Dodano {added}!"; st.rerun()

# --- 📦 GENERATOR SŁÓW ---
elif choice == "📦 Generator słów":
    update_activity("Generator"); 
    if "success_msg" in st.session_state: st.success(st.session_state.success_msg); del st.session_state.success_msg
    cols = st.columns(5); lvls = ["A1", "A2", "B1", "B2", "C1"]
    for i, lvl in enumerate(lvls):
        if cols[i].button(lvl, key=lvl, use_container_width=True):
            with st.spinner(f"Szukam 25 słówek {lvl}..."):
                try:
                    all_p = VOCAB_DB.get(lvl, []); my_w = [x['de'].lower() for x in st.session_state.flashcards]
                    sel = [w for w in all_p if w.lower() not in my_w]
                    prompt = f"Generate 25 German words {lvl}. Output JSON key 'flashcards'."
                    res = get_openai_response(prompt); data = parse_ai_json(res)
                    if isinstance(data, dict) and "flashcards" in data:
                        added = 0
                        for w in data["flashcards"]:
                            t_de = w.get('de') or w.get('word'); t_pl = w.get('pl') or w.get('translation')
                            if t_de and t_pl and t_de.lower() not in [x['de'].lower() for x in st.session_state.flashcards]:
                                w.update({"de": t_de, "pl": t_pl, "next_review": str(today_dt), "date_added": str(today_dt), "category": f"{lvl} - {w.get('category','Inne')}"})
                                st.session_state.flashcards.append(w); added += 1
                        st.session_state.user_data["historical_cost"] += 0.01; force_save(); st.session_state.success_msg = f"🎉 Dodano {added}!"; st.rerun()
                except Exception as e: st.error(f"Błąd: {e}")

# --- ➕ DODAJ / 📖 SŁOWNIK ---
elif choice == "➕ Dodaj":
    st.header("➕ Dodaj"); update_activity("Dodaj")
    with st.form("man_f"):
        de, pl, kat = st.text_input("Niemiecki"), st.text_input("Polski"), st.text_input("Kategoria")
        if st.form_submit_button("Zapisz"):
            if de and pl: st.session_state.flashcards.append({"de":de, "pl":pl, "category":kat or "Inne", "next_review":str(today_dt), "date_added":str(today_dt), "examples":[]}); force_save(); st.success("Dodano!")

elif choice == "📖 Słownik":
    update_activity("Słownik"); cats = sorted(list(set([c.get("category", "Inne") for c in st.session_state.flashcards])))
    f_kat = st.selectbox("Filtruj:", ["Wszystkie"] + cats); search = st.text_input("Szukaj:")
    for i, c in enumerate(st.session_state.flashcards):
        if (f_kat == "Wszystkie" or c.get("category") == f_kat) and (search.lower() in c['de'].lower() or search.lower() in c['pl'].lower()):
            with st.expander(f"📝 {c['de']} — {c['pl']}"):
                with st.form(f"ed_{i}"):
                    n_de, n_pl, n_ka = st.text_input("DE", c['de']), st.text_input("PL", c['pl']), st.text_input("KAT", c.get('category','Inne'))
                    col_save, col_del = st.columns(2)
                    if col_save.form_submit_button("Zapisz", use_container_width=True): st.session_state.flashcards[i].update({"de":n_de, "pl":n_pl, "category":n_ka}); force_save(); st.rerun()
                    if col_del.form_submit_button("Usuń", use_container_width=True): del st.session_state.flashcards[i]; force_save(); st.rerun()

# --- 📊 STATYSTYKI (Z historią testów) ---
elif choice == "📊 Statystyki":
    update_activity("Statystyki"); df = pd.DataFrame(st.session_state.flashcards)
    st.header("📊 Twoje Statystyki")
    if df.empty: st.warning("Baza słówek jest pusta.")
    else:
        c1, c2, c3 = st.columns(3); c1.metric("Łącznie słówek", len(df)); c2.metric("Passa", f"{st.session_state.user_data['streak']} dni")
        know_count = len(df[df['next_review'].apply(is_word_mastered)]); c3.metric("Opanowane (7d+)", know_count)
        
        st.subheader("Podział na poziomy")
        stats_rows = []
        for l in ["A1", "A2", "B1", "B2", "C1"]:
            l_df = df[df['category'].str.contains(l, na=False)]; total = len(l_df)
            know = len(l_df[l_df['next_review'].apply(is_word_mastered)]) if total > 0 else 0
            perc = round((know/total)*100) if total > 0 else 0
            stats_rows.append({"Poziom": l, "Słówek": total, "Opanowane": know, "%": f"{perc}%"})
        st.table(pd.DataFrame(stats_rows))
        
        # HISTORIA TESTÓW
        st.subheader("📜 Historia Twoich Testów")
        h = st.session_state.user_data.get("test_history", [])
        if h:
            h_df = pd.DataFrame(h[::-1]).head(10) # 10 ostatnich
            st.table(h_df[["date", "score", "total", "perc"]])
        else: st.info("Nie ukończyłeś jeszcze żadnego testu.")

# --- ⚙️ MOJE KONTO ---
elif choice == "⚙️ Moje Konto":
    st.header("⚙️ Zarządzanie Kontem"); update_activity("Konto")
    with st.expander("🔑 Zmień hasło"):
        with st.form("pw_f"):
            o, n, cp = st.text_input("Stare", type="password"), st.text_input("Nowe", type="password"), st.text_input("Powtórz", type="password")
            if st.form_submit_button("Zmień"):
                db = load_j(AUTH_FILE, {})
                if db.get(u) == hash_pw(o) and n == cp: db[u] = hash_pw(n); save_j(AUTH_FILE, db); st.success("OK!")
    st.divider(); conf = st.checkbox("Potwierdzam chęć usunięcia danych")
    if st.button("🗑️ RESET BAZY", type="primary", disabled=not conf, use_container_width=True):
        save_j(get_p(u, "flashcards"), []); st.session_state.flashcards = []; st.rerun()

# --- 👑 ADMIN (Z liczbą testów) ---
elif choice == "👑 Admin":
    st.header("👑 Panel Admina"); users = load_j(AUTH_FILE, {}); adm_list = []; global_time = {m: 0.0 for m in MODULE_ORDER}
    for usr in users:
        ud, ub = load_j(get_p(usr, "user_data"), {}), load_j(get_p(usr, "flashcards"), [])
        mastery = "0%"
        if ub:
            opanowane = len([x for x in ub if is_word_mastered(x.get('next_review'))])
            mastery = f"{round((opanowane/len(ub))*100)}%"
        t_s = ud.get("time_stats", {})
        for m in MODULE_ORDER: global_time[m] += t_s.get(m, 0.0)
        u_times = ", ".join([f"{m[0]}:{round(s/60)}m" for m, s in t_s.items() if s > 15])
        # LICZNIK TESTÓW
        t_count = len(ud.get("test_history", []))
        adm_list.append({"Użytkownik":usr, "Słów":len(ub), "Testy":t_count, "%":mastery, "Ostatnio":ud.get("last_seen","Nigdy"), "Czas":u_times or "Brak"})
    st.table(pd.DataFrame(adm_list))
    total_g = sum(global_time.values())
    if total_g > 0:
        vals = [global_time[m] for m in MODULE_ORDER]; labels = [f"{m}: {round(v/60,1)} min" for m, v in zip(MODULE_ORDER, vals)]
        fig = go.Figure(data=[go.Bar(x=MODULE_ORDER, y=vals, text=labels, textposition='auto', marker_color='#1E88E5')])
        fig.update_layout(template="plotly_dark", height=450); st.plotly_chart(fig, use_container_width=True)
