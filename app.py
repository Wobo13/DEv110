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

APP_VERSION = "V210 (Full System Restoration)"
ADMIN_USER = "wobo"

# MAPOWANIE DLA ANALITYKI
CLEAN_TIME_LABELS = {
    "Powtórki": "Pow", "Trening": "Trn", "Quiz": "Qiz", "Fiszki": "Fis",
    "Testy": "Tst", "Skaner": "Skn", "Generator": "Gen", "Dodaj": "Dod",
    "Słownik": "Słn", "Statystyki": "Sta", "Konto": "Kon", "Admin": "Adm"
}

# --- 2. SILNIK BAZY I AI ---
def get_db():
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    return SyncPostgrestClient(f"{SUPABASE_URL}/rest/v1", headers=headers)

def hash_pw(pw): return hashlib.sha256(str.encode(pw)).hexdigest()

def get_openai_response(prompt_text, img_obj=None):
    if not API_KEY: raise Exception("Brak klucza API OpenAI.")
    client = OpenAI(api_key=API_KEY)
    messages = [{"role": "system", "content": "Jesteś ekspertem niemieckiego. Odpowiadaj TYLKO w JSON. Kategorie tematyczne po polsku (tagi), przykłady jako lista {de, pl}."}]
    if img_obj:
        buf = BytesIO(); img_obj.thumbnail((800, 800)); img_obj.save(buf, format="JPEG")
        img_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        messages.append({"role": "user", "content": [{"type": "text", "text": prompt_text}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}}]})
    else:
        messages.append({"role": "user", "content": prompt_text})
    res = client.chat.completions.create(model="gpt-4o-mini", messages=messages, response_format={"type": "json_object"})
    return res.choices[0].message.content

def get_audio_bytes(txt, ex_txt=None):
    try:
        full = f"{txt}. . . . {ex_txt}" if ex_txt else txt
        f = BytesIO(); tts = gTTS(text=full, lang='de'); tts.write_to_fp(f); f.seek(0)
        return f
    except: return None

def normalize_text(t):
    if not t: return ""
    return str(t).lower().strip().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")

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

# --- 4. LOGOWANIE ---
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
        un = st.text_input("Użytkownik").lower().strip()
        pw = st.text_input("Hasło", type="password")
        if st.button("Zaloguj się", use_container_width=True, type="primary"):
            res = db.table("users_auth").select("*").eq("username", un).execute()
            if res.data and res.data[0]["password_hash"] == hashlib.sha256(str.encode(pw)).hexdigest():
                st.session_state.auth, st.session_state.user = True, un
                st.query_params["token"] = un; st.rerun()
            else: st.error("Błędne dane")
    with t2:
        rn, rp = st.text_input("Nowy użytkownik").lower().strip(), st.text_input("Nowe hasło", type="password")
        if st.button("Załóż konto"):
            if len(rn) > 2 and len(rp) > 3:
                get_db().table("users_auth").insert({"username": rn, "password_hash": hashlib.sha256(str.encode(rp)).hexdigest()}).execute()
                load_user_data(rn); st.success("Konto gotowe!"); st.rerun()
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
    st.session_state.user_data["last_seen"] = datetime.now().strftime("%d.%m %H:%M")
    save_user_data(u, st.session_state.user_data)

update_activity("Inne")

# --- 6. SIDEBAR & MENU ---
st.sidebar.title(f"👤 {u.capitalize()}")
st.sidebar.caption(f"Wersja: {APP_VERSION}")
st.sidebar.info(f"🔥 Passa: **{st.session_state.user_data.get('streak', 0)} dni**")
if st.sidebar.button("Wyloguj", use_container_width=True):
    st.query_params.clear(); st.session_state.clear(); st.rerun()

menu = ["📅 Powtórki", "🚀 Trening", "🕹️ Quiz", "🎴 Fiszki", "📝 Testy", "📦 Generator słów", "📸 Skaner AI", "➕ Dodaj", "📖 Słownik", "📊 Statystyki", "⚙️ Moje Konto", "👑 Admin"]
choice = st.sidebar.radio("Nawigacja", menu)

if "l_c" not in st.session_state or st.session_state.l_c != choice:
    for k in ["cur_list", "n_idx", "f_idx", "f_flipped", "test_q", "test_idx", "test_score", "q_c", "q_s"]:
        if k in st.session_state: del st.session_state[k]
    st.session_state.l_c, st.session_state.n_m, st.session_state.u_a = choice, "ask", ""

# --- 7. MODUŁY NAUKI (Powtórki / Trening) ---
if choice in ["📅 Powtórki", "🚀 Trening"]:
    is_r = (choice == "📅 Powtórki")
    update_activity("Powtórki" if is_r else "Trening")
    st.header(f"{choice}")
    
    all_tags = set()
    for c in st.session_state.flashcards:
        tags = [t.strip() for t in str(c.get('category','')).split(',') if t.strip()]
        all_tags.update(tags)
    
    sel_tag = st.selectbox("Zakres:", ["Wszystkie"] + sorted(list(all_tags)))
    
    if "cur_list" not in st.session_state:
        pool = [c for c in st.session_state.flashcards if (sel_tag == "Wszystkie" or sel_tag in str(c.get('category','')))]
        if is_r: 
            pool = [c for c in pool if str(c.get("next_review", date.today())) <= str(date.today())]
        random.shuffle(pool); st.session_state.cur_list, st.session_state.n_idx = pool, 0

    cards = st.session_state.cur_list
    if not cards: st.success("Pusto! Odpocznij. 🎊")
    else:
        idx = st.session_state.n_idx
        if idx < len(cards):
            c = cards[idx]
            st.write(f"Słówek w kolejce: **{len(cards) - idx}**")
            st.markdown(f'<div style="font-size:3em; text-align:center; padding:30px; border:3px solid #1E88E5; border-radius:20px;">{c["de"]}</div>', unsafe_allow_html=True)
            
            if st.session_state.n_m == "ask":
                u_in = st.text_input("Tłumaczenie (PL):", key=f"ans_{idx}")
                if st.button("Sprawdź", use_container_width=True): 
                    st.session_state.u_a, st.session_state.n_m = u_in, "res"; st.rerun()
            else:
                if normalize_text(st.session_state.u_a) == normalize_text(c['pl']): st.success(f"✅ Dobrze: {c['pl']}")
                else: st.error(f"❌ Poprawnie: {c['pl']}")
                
                exs = c.get("examples", [])
                fex = exs[0].get("de") if exs and isinstance(exs, list) and len(exs) > 0 else None
                if fex: st.info(f"💡 {fex}\n({exs[0].get('pl','')})")
                
                audio_file = get_audio_bytes(c['de'], fex)
                if audio_file: st.audio(audio_file, format="audio/mp3", autoplay=True)
                
                if is_r:
                    st.write("Jak oceniasz?")
                    col1, col2, col3 = st.columns(3); d = None
                    if col1.button("🔴 Słabo (1d)"): d = 1
                    if col2.button("🟡 Średnio (3d)"): d = 3
                    if col3.button("🟢 Dobrze (7d)"): d = 7
                    if d:
                        update_word(c['id'], {"next_review": str(date.today() + timedelta(days=d))})
                        st.session_state.n_idx += 1; st.session_state.n_m = "ask"; st.rerun()
                else:
                    if st.button("Dalej ➡️", use_container_width=True):
                        st.session_state.n_idx += 1; st.session_state.n_m = "ask"; st.rerun()

# --- 8. QUIZ ---
elif choice == "🕹️ Quiz":
    update_activity("Quiz"); st.header("🕹️ Szybki Quiz")
    all_c = st.session_state.flashcards
    if len(all_c) < 4: st.warning("Dodaj min. 4 słówka!")
    else:
        if "q_c" not in st.session_state:
            idx = random.randrange(len(all_c)); t = all_c[idx]
            opts = random.sample([x['pl'] for x in all_c if x['pl']!=t['pl']], 3) + [t['pl']]
            random.shuffle(opts); st.session_state.update({"q_c":t, "q_a":t['pl'], "q_o":opts, "q_s":"ask"})
        
        st.write(f"### Jak przetłumaczysz: **{st.session_state.q_c['de']}**")
        if st.session_state.q_s == "ask":
            for o in st.session_state.q_o:
                if st.button(o, key=o, use_container_width=True):
                    st.session_state.u_q, st.session_state.q_s = o, "res"; st.rerun()
        else:
            if st.session_state.u_q == st.session_state.q_a: st.success("✅ Świetnie!")
            else: st.error(f"❌ Poprawnie: {st.session_state.q_a}")
            play_audio(st.session_state.q_c['de'])
            if st.button("Następne", use_container_width=True): del st.session_state.q_c; st.rerun()

# --- 9. FISZKI (Rendering Fix) ---
elif choice == "🎴 Fiszki":
    update_activity("Fiszki"); st.header("🎴 Fiszki")
    if "f_idx" not in st.session_state: st.session_state.f_idx = 0
    if "f_flipped" not in st.session_state: st.session_state.f_flipped = False
    
    all_tags = set()
    for c in st.session_state.flashcards:
        all_tags.update([t.strip() for t in str(c.get('category','')).split(',') if t.strip()])
    sel_tag = st.selectbox("Wybierz zakres:", ["Wszystkie"] + sorted(list(all_tags)))
    cards = [c for c in st.session_state.flashcards if sel_tag == "Wszystkie" or sel_tag in str(c.get('category',''))]
    
    if cards:
        if st.session_state.f_idx >= len(cards): st.session_state.f_idx = 0
        c = cards[st.session_state.f_idx]
        
        ex_html = ""
        fex_de = None
        if st.session_state.f_flipped:
            exs = c.get("examples", [])
            if exs and isinstance(exs, list) and len(exs) > 0:
                fex_de = exs[0].get('de','')
                ex_html = f"""
                <div style='margin-top:20px; padding-top:20px; border-top:1px solid #444;'>
                    <div style='color:#FFEB3B; font-size:1.3rem; margin-bottom:5px;'>🇩🇪 {exs[0].get('de','')}</div>
                    <div style='color:white; font-size:1.1rem; opacity:0.8;'>🇵🇱 {exs[0].get('pl','')}</div>
                </div>
                """
        
        display_text = c["pl"] if st.session_state.f_flipped else c["de"]
        color = "#2E7D32" if st.session_state.f_flipped else "#C62828"
        label = "POLSKI" if st.session_state.f_flipped else "DEUTSCH"
        
        st.markdown(f"""
            <div style="min-height:380px; display:flex; flex-direction:column; align-items:center; justify-content:center; background:#111; border:5px solid {color}; border-radius:40px; color:white; text-align:center; padding:30px; box-shadow: 0 10px 30px rgba(0,0,0,0.5);">
                <div style="color:{color}; font-weight:bold; letter-spacing:3px; margin-bottom:15px; font-size:0.9em;">{label}</div>
                <div style="font-size:3.5em; font-weight:700; line-height:1.1; margin-bottom:10px;">{display_text}</div>
                {ex_html}
            </div>
        """, unsafe_allow_html=True)
        
        if st.session_state.f_flipped:
            audio_f = get_audio_bytes(c['de'], fex_de)
            if audio_f: st.audio(audio_f, format="audio/mp3", autoplay=True)
        
        st.write("")
        c1, c2, c3 = st.columns([1, 2, 1])
        if c1.button("⬅️ Wstecz", use_container_width=True): st.session_state.f_idx -= 1; st.session_state.f_flipped = False; st.rerun()
        if c2.button("🔄 OBRÓĆ KARTĘ", type="primary", use_container_width=True): st.session_state.f_flipped = not st.session_state.f_flipped; st.rerun()
        if c3.button("Dalej ➡️", use_container_width=True): st.session_state.f_idx += 1; st.session_state.f_flipped = False; st.rerun()
    else: st.warning("Brak słówek w tej kategorii.")

# --- 10. TESTY ---
elif choice == "📝 Testy":
    update_activity("Testy"); st.header("📝 Egzamin Kontekstowy")
    if len(st.session_state.flashcards) < 5: st.warning("Dodaj min. 5 słówek.")
    else:
        if "test_q" not in st.session_state:
            n_q = st.slider("Liczba pytań", 5, 20, 5)
            if st.button("🚀 GENERUJ TEST", type="primary"):
                with st.spinner("AI przygotowuje zadania..."):
                    sample = random.sample(st.session_state.flashcards, n_q)
                    prompt = f"Generuj test dla: {[w['de'] for w in sample]}. JSON: {{ \"questions\": [{{ \"hint\":\"PL hint\", \"sentence\":\"German sentence\", \"correct\":\"DE word\", \"distractors\":[\"...\"], \"type\":\"QUIZ\" }}] }}"
                    data = json.loads(get_openai_response(prompt))
                    st.session_state.test_q, st.session_state.test_idx, st.session_state.test_score = data["questions"], 0, 0; st.rerun()
        else:
            qs = st.session_state.test_q; t_idx = st.session_state.test_idx
            if t_idx < len(qs):
                q = qs[t_idx]; correct = str(q.get('correct',''))
                st.info(f"💡 Wskazówka: {q.get('hint','brak')}"); st.write(f"#### {q.get('sentence','?')}")
                if q.get('type') == "QUIZ":
                    opts = list(set(q.get('distractors', []) + [correct])); random.shuffle(opts)
                    cols = st.columns(2)
                    for i, o in enumerate(opts):
                        if cols[i%2].button(o, key=f"t_{t_idx}_{o}"):
                            if o == correct: st.session_state.test_score += 1; st.toast("Dobrze!")
                            else: st.error(f"Poprawnie: {correct}"); time.sleep(1)
                            st.session_state.test_idx += 1; st.rerun()
                else:
                    ans = st.text_input("Twoja odpowiedź:", key=f"in_{t_idx}")
                    if st.button("Zatwierdź"):
                        if normalize_text(ans) == normalize_text(correct): st.session_state.test_score += 1; st.toast("OK!")
                        else: st.error(f"Poprawnie: {correct}"); time.sleep(1)
                        st.session_state.test_idx += 1; st.rerun()
            else:
                st.success(f"Wynik: {st.session_state.test_score}/{len(qs)}"); del st.session_state.test_q

# --- 11. GENERATOR (Fix Column Name) ---
elif choice == "📦 Generator słów":
    update_activity("Generator"); st.header("📦 Generator z Chmury SQL")
    cols = st.columns(5)
    for i, lvl in enumerate(["A1", "A2", "B1", "B2", "C1"]):
        if cols[i].button(lvl, use_container_width=True):
            with st.spinner(f"AI pobiera 25 słówek {lvl}..."):
                try:
                    res_lib = get_db().table("vocab_library").select("word").eq("level", lvl).execute()
                    my_w = [x['de'].lower() for x in st.session_state.flashcards]
                    avail = [w['word'] for w in res_lib.data if w['word'].lower() not in my_w]
                    sel = random.sample(avail, min(25, len(avail)))
                    prompt = f"Przetłumacz na polski i otaguj tematycznie: {sel}. JSON: {{\"flashcards\": [{{ \"de\":\"...\", \"pl\":\"...\", \"category\":\"..., {lvl}\", \"examples\":[{{ \"de\":\"...\", \"pl\":\"...\" }}] }}]}}"
                    data = json.loads(get_openai_response(prompt))
                    for w in data.get("flashcards", []):
                        if isinstance(w, dict) and 'de' in w:
                            save_word(u, {**w, "next_review": str(date.today()), "origin": "Generator"})
                    st.success("Dodano pomyślnie!"); st.rerun()
                except Exception as e: st.error(f"Błąd AI: {e}")

# --- 12. SKANER AI ---
elif choice == "📸 Skaner AI":
    update_activity("Skaner"); st.header("📸 Skaner Tekstu")
    src = st.camera_input("Zrób zdjęcie")
    if src and st.button("Analizuj"):
        res = get_openai_response("Extract words to JSON 'flashcards' list.", Image.open(src))
        for w in json.loads(res).get("flashcards", []): 
            save_word(u, {**w, "origin":"Skaner", "next_review":str(date.today())})
        st.success("Dodano!"); st.rerun()

# --- 13. DODAJ RĘCZNIE ---
elif choice == "➕ Dodaj":
    st.header("➕ Dodaj słówko")
    with st.form("manual"):
        de, pl, ca = st.text_input("Niemiecki"), st.text_input("Polski"), st.text_input("Tagi (rozdziel przecinkiem)")
        if st.form_submit_button("Zapisz"):
            save_word(u, {"de":de, "pl":pl, "category":ca, "next_review":str(date.today()), "origin":"Dodaj"}); st.rerun()

# --- 14. SŁOWNIK (Pełna Edycja) ---
elif choice == "📖 Słownik":
    update_activity("Słownik"); st.header("📖 Twój Słownik")
    search = st.text_input("Szukaj słowa:")
    for c in st.session_state.flashcards:
        if search.lower() in str(c.get('de','')).lower() or search.lower() in str(c.get('pl','')).lower():
            with st.expander(f"📝 {c['de']} - {c['pl']}"):
                with st.form(f"ed_{c['id']}"):
                    n_de = st.text_input("DE", c['de'])
                    n_pl = st.text_input("PL", c['pl'])
                    n_ca = st.text_input("Tagi", c.get('category',''))
                    if st.form_submit_button("Zatwierdź"):
                        update_word(c['id'], {"de": n_de, "pl": n_pl, "category": n_ca}); st.rerun()
                if st.button("Usuń", key=f"del_{c['id']}"): delete_word(c['id']); st.rerun()

# --- 15. STATYSTYKI ---
elif choice == "📊 Statystyki":
    update_activity("Statystyki"); st.header("📊 Twoje Postępy")
    df = pd.DataFrame(st.session_state.flashcards)
    if not df.empty:
        c1, c2 = st.columns(2); c1.metric("Baza słówek", len(df)); c2.metric("Passa", f"{st.session_state.user_data['streak']} d")
        st.subheader("Źródła słówek")
        st.table(df.groupby('origin').size())

# --- 16. MOJE KONTO ---
elif choice == "⚙️ Moje Konto":
    st.header("⚙️ Zarządzanie Kontem"); update_activity("Konto")
    with st.expander("🔑 Zmień hasło"):
        with st.form("pw"):
            o, n = st.text_input("Stare", type="password"), st.text_input("Nowe", type="password")
            if st.form_submit_button("Zmień"):
                db = get_db(); res = db.table("users_auth").select("*").eq("username", u).execute()
                if res.data and res.data[0]["password_hash"] == hash_pw(o):
                    db.table("users_auth").update({"password_hash": hash_pw(n)}).eq("username", u).execute(); st.success("OK!")
    
    st.divider(); st.subheader("🗑️ Usuwanie danych")
    conf = st.checkbox("Potwierdzam usuwanie")
    col_d = st.columns(5)
    for lvl in ["A1", "A2", "B1", "B2", "C1"]:
        if col_d[["A1", "A2", "B1", "B2", "C1"].index(lvl)].button(lvl, disabled=not conf):
            get_db().table("flashcards").delete().eq("username", u).ilike("category", f"%{lvl}%").execute(); st.rerun()

# --- 17. ADMIN (Full Analityka) ---
elif choice == "👑 Admin":
    st.header("👑 Administrator"); st.link_button("💸 OpenAI Billing", "https://platform.openai.com/usage")
    db = get_db(); ud = db.table("user_data").select("*").execute().data
    adm_list = []
    for user in ud:
        username = user["username"]; total_cost = user.get("historical_cost", 0.0)
        cards = db.table("flashcards").select("origin").eq("username", username).execute().data
        merged = {}
        for m, s in user.get("time_stats", {}).items():
            lbl = CLEAN_TIME_LABELS.get(m.strip(), "Inn"); merged[lbl] = merged.get(lbl, 0) + s
        u_times = ", ".join([f"{l}:{round(s/60)}m" for l, s in merged.items() if s > 15])
        adm_list.append({"Użytkownik":username, "Słów":len(cards), "Ręcznie":len([x for x in cards if x['origin']=='Dodaj']), "Gen":len([x for x in cards if x['origin']=='Generator']), "Skan":len([x for x in cards if x['origin']=='Skaner']), "Czas":u_times, "Koszt":round(total_cost,4)})
    st.table(pd.DataFrame(adm_list))
