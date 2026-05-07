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

# --- 1. KONFIGURACJA ---
SUPABASE_URL = st.secrets.get("SUPABASE_URL", "")
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY", "")
API_KEY = st.secrets.get("OPENAI_API_KEY", "")

APP_VERSION = "V206 (Full Restoration & Fiszki Fix)"
ADMIN_USER = "wobo"

# MAPOWANIE DLA ANALITYKI (Ujednolicenie)
CLEAN_TIME_LABELS = {
    "Powtórki": "Pow", "Trening": "Trn", "Quiz": "Qiz", "Fiszki": "Fis",
    "Testy": "Tst", "Skaner": "Skn", "Generator": "Gen", "Dodaj": "Dod",
    "Słownik": "Słn", "Konto": "Inn"
}

# --- 2. SILNIK BAZY I AI ---
def get_db():
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    return SyncPostgrestClient(f"{SUPABASE_URL}/rest/v1", headers=headers)

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

def normalize_text(t):
    if not t: return ""
    return str(t).lower().strip().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")

# --- 3. FUNKCJE DANYCH ---
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
        if not c.get("origin"):
            cat = str(c.get("category", "")).lower()
            c["origin"] = "Generator" if "gen" in cat else ("Skaner" if "skan" in cat else "Dodaj")
    return cards

def save_word(username, word_obj):
    word_obj["username"] = username
    if "examples" not in word_obj: word_obj["examples"] = []
    get_db().table("flashcards").insert(word_obj).execute()

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
    with t1:
        un = st.text_input("Użytkownik").lower().strip()
        pw = st.text_input("Hasło", type="password")
        if st.button("Zaloguj się", use_container_width=True, type="primary"):
            res = get_db().table("users_auth").select("*").eq("username", un).execute()
            if res.data and res.data[0]["password_hash"] == hashlib.sha256(str.encode(pw)).hexdigest():
                st.session_state.auth, st.session_state.user = True, un
                st.query_params["token"] = un; st.rerun()
            else: st.error("Błąd logowania")
    with t2:
        rn, rp = st.text_input("Nowy użytkownik").lower().strip(), st.text_input("Nowe hasło", type="password")
        if st.button("Załóż konto"):
            if len(rn) > 2 and len(rp) > 3:
                get_db().table("users_auth").insert({"username": rn, "password_hash": hashlib.sha256(str.encode(rp)).hexdigest()}).execute()
                load_user_data(rn); st.success("Gotowe! Zaloguj się."); st.rerun()
    st.stop()

# --- 5. SESJA ---
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

# --- 6. SIDEBAR ---
st.sidebar.title(f"👤 {u.capitalize()}")
st.sidebar.caption(f"Wersja: {APP_VERSION}")
st.sidebar.info(f"🔥 Passa: **{st.session_state.user_data.get('streak', 0)} dni**")
if st.sidebar.button("Wyloguj", use_container_width=True):
    st.query_params.clear(); st.session_state.clear(); st.rerun()

menu = ["📅 Powtórki", "🎴 Fiszki", "📖 Słownik", "📦 Generator słów", "📸 Skaner AI", "➕ Dodaj", "🕹️ Quiz", "📝 Testy", "📊 Statystyki", "⚙️ Moje Konto"]
if u == ADMIN_USER: menu.append("👑 Admin")
choice = st.sidebar.radio("Nawigacja", menu)

# Reset stanów
if "l_c" not in st.session_state or st.session_state.l_c != choice:
    for k in ["cur_list", "n_idx", "f_idx", "f_flipped", "test_q", "test_idx", "test_score", "pending"]:
        if k in st.session_state: del st.session_state[k]
    st.session_state.l_c, st.session_state.n_m, st.session_state.u_a = choice, "ask", ""

# --- 7. MODUŁ: POWTÓRKI (SRS) ---
if choice == "📅 Powtórki":
    update_activity("Powtórki"); st.header("📅 Powtórki")
    all_tags = set()
    for c in st.session_state.flashcards: all_tags.update([t.strip() for t in str(c.get('category','')).split(',')])
    sel_tag = st.selectbox("Zakres:", ["Wszystkie"] + sorted(list(all_tags)))
    
    if "cur_list" not in st.session_state:
        pool = [c for c in st.session_state.flashcards if (sel_tag == "Wszystkie" or sel_tag in str(c.get('category',''))) and str(c.get("next_review", date.today())) <= str(date.today())]
        random.shuffle(pool); st.session_state.cur_list, st.session_state.n_idx = pool, 0

    cards = st.session_state.cur_list
    if not cards: st.success("Pusto! 🎉")
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
                if normalize_text(st.session_state.u_a) == normalize_text(c['pl']): st.success(f"✅ Dobrze: {c['pl']}")
                else: st.error(f"❌ Poprawnie: {c['pl']}")
                exs = c.get("examples", [])
                fex = exs[0].get("de") if exs and isinstance(exs, list) and len(exs) > 0 else None
                play_audio(c['de'], fex)
                col1, col2, col3 = st.columns(3); d = None
                if col1.button("🔴 Słabo"): d = 1
                if col2.button("🟡 Średnio"): d = 3
                if col3.button("🟢 Dobrze"): d = 7
                if d:
                    update_word(c['id'], {"next_review": str(date.today() + timedelta(days=d))})
                    st.session_state.n_idx += 1; st.session_state.n_m = "ask"; st.rerun()

# --- 8. MODUŁ: FISZKI (Fix AttributeError) ---
elif choice == "🎴 Fiszki":
    update_activity("Fiszki"); st.header("🎴 Fiszki")
    if "f_idx" not in st.session_state: st.session_state.f_idx = 0
    if "f_flipped" not in st.session_state: st.session_state.f_flipped = False
    
    all_tags = set()
    for c in st.session_state.flashcards: all_tags.update([t.strip() for t in str(c.get('category','')).split(',')])
    sel_tag = st.selectbox("Zakres:", ["Wszystkie"] + sorted(list(all_tags)))
    cards = [c for c in st.session_state.flashcards if sel_tag == "Wszystkie" or sel_tag in str(c.get('category',''))]
    
    if cards:
        c = cards[st.session_state.f_idx % len(cards)]
        txt = c["pl"] if st.session_state.f_flipped else c["de"]
        color = "#2E7D32" if st.session_state.f_flipped else "#FF5252"
        st.markdown(f'<div style="min-height:300px; display:flex; align-items:center; justify-content:center; background:black; border:4px solid {color}; border-radius:30px; color:white; font-size:2.5em; text-align:center; padding:20px;">{txt}</div>', unsafe_allow_html=True)
        
        c1, c2, c3 = st.columns(3)
        if c1.button("⬅️"): st.session_state.f_idx -= 1; st.session_state.f_flipped = False; st.rerun()
        if c2.button("🔄 OBRÓĆ", type="primary"):
            st.session_state.f_flipped = not st.session_state.f_flipped
            if st.session_state.f_flipped:
                exs = c.get("examples", [])
                fex = exs[0].get("de") if exs and isinstance(exs, list) and len(exs) > 0 else None
                play_audio(c['de'], fex)
            st.rerun()
        if c3.button("➡️"): st.session_state.f_idx += 1; st.session_state.f_flipped = False; st.rerun()
    else: st.warning("Brak słówek w tym zakresie.")

# --- 9. MODUŁ: SŁOWNIK (Restore Full) ---
elif choice == "📖 Słownik":
    update_activity("Słownik"); st.header("📖 Słownik")
    all_tags = set()
    for c in st.session_state.flashcards: all_tags.update([t.strip() for t in str(c.get('category','')).split(',')])
    f_tag = st.selectbox("Filtruj tag:", ["Wszystkie"] + sorted(list(all_tags)))
    search = st.text_input("Szukaj:")
    
    filtered = [c for c in st.session_state.flashcards if (f_tag == "Wszystkie" or f_tag in str(c.get('category',''))) and (search.lower() in str(c.get('de','')).lower() or search.lower() in str(c.get('pl','')).lower())]
    
    for c in filtered:
        with st.expander(f"📝 {c['de']} - {c['pl']}"):
            with st.form(f"ed_{c['id']}"):
                n_de, n_pl, n_ca = st.text_input("DE", c['de']), st.text_input("PL", c['pl']), st.text_input("Tagi", c.get('category',''))
                if st.form_submit_button("Zapisz"):
                    update_word(c['id'], {"de": n_de, "pl": n_pl, "category": n_ca}); st.rerun()
            if st.button("Usuń", key=f"del_{c['id']}"): delete_word(c['id']); st.rerun()

# --- 10. GENERATOR (Fix 'str' object) ---
elif choice == "📦 Generator słów":
    update_activity("Generator"); st.header("📦 Generator")
    cols = st.columns(5)
    for i, lvl in enumerate(["A1", "A2", "B1", "B2", "C1"]):
        if cols[i].button(lvl, use_container_width=True):
            with st.spinner(f"AI pobiera 25 słówek {lvl}..."):
                try:
                    res_lib = get_db().table("vocab_library").select("word").eq("level", lvl).execute()
                    avail = [w['word'] for w in res_lib.data if w['word'].lower() not in [x['de'].lower() for x in st.session_state.flashcards]]
                    sel = random.sample(avail, min(25, len(avail)))
                    prompt = f"Przetłumacz na PL i otaguj tematycznie: {sel}. JSON: {{\"flashcards\": [{{ \"de\":\"...\", \"pl\":\"...\", \"category\":\"..., {lvl}\", \"examples\":[{{ \"de\":\"...\", \"pl\":\"...\" }}] }}]}}"
                    data = json.loads(get_openai_response(prompt))
                    for w in data.get("flashcards", []):
                        if isinstance(w, dict) and 'de' in w:
                            w.update({"username": u, "next_review": str(date.today()), "origin": "Generator"})
                            get_db().table("flashcards").insert(w).execute()
                    st.success("Dodano!"); time.sleep(1); st.rerun()
                except Exception as e: st.error(f"Błąd: {e}")

# --- 11. ADMIN (Full Analytics) ---
elif choice == "👑 Admin":
    st.header("👑 Admin"); st.link_button("💸 OpenAI Billing", "https://platform.openai.com/usage")
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
    st.table(pd.DataFrame(adm_list))
    if global_time:
        fig = go.Figure(data=[go.Bar(x=list(global_time.keys()), y=list(global_time.values()), marker_color='#1E88E5')])
        fig.update_layout(template="plotly_dark", height=400, title="Czas globalny (min)"); st.plotly_chart(fig, use_container_width=True)

# --- 12. TESTY, QUIZ, SKANER, KONTO (Restore logic) ---
elif choice == "📝 Testy":
    update_activity("Testy"); st.header("📝 Testy")
    if len(st.session_state.flashcards) < 5: st.warning("Min. 5 słówek.")
    else:
        if "test_q" not in st.session_state:
            n_q = st.slider("Liczba pytań", 5, 20, 5)
            if st.button("🚀 GENERUJ"):
                with st.spinner("AI przygotowuje..."):
                    sample = random.sample(st.session_state.flashcards, n_q)
                    prompt = f"Generuj test dla: {[w['de'] for w in sample]}. JSON: {{\"questions\": [{{ \"hint\":\"PL hint\", \"sentence\":\"German sentence\", \"correct\":\"DE word\", \"distractors\":[\"...\"], \"type\":\"QUIZ\" }}] }}"
                    data = json.loads(get_openai_response(prompt))
                    st.session_state.test_q, st.session_state.test_idx, st.session_state.test_score = data["questions"], 0, 0; st.rerun()
        else:
            qs = st.session_state.test_q; t_idx = st.session_state.test_idx
            if t_idx < len(qs):
                q = qs[t_idx]; st.info(f"Podpowiedź: {q.get('hint','brak')}"); st.write(f"#### {q.get('sentence','?')}")
                correct = q.get('correct','')
                if q.get('type') == "QUIZ":
                    opts = list(set(q.get('distractors', []) + [correct])); random.shuffle(opts)
                    cols = st.columns(2)
                    for i, o in enumerate(opts):
                        if cols[i%2].button(o, key=f"t_{t_idx}_{o}"):
                            if o == correct: st.session_state.test_score += 1; st.toast("Dobrze!")
                            else: st.error(f"Źle. Poprawnie: {correct}"); time.sleep(1)
                            st.session_state.test_idx += 1; st.rerun()
                else:
                    ans = st.text_input("Twoja odpowiedź:", key=f"in_{t_idx}")
                    if st.button("OK"):
                        if normalize_text(ans) == normalize_text(correct): st.session_state.test_score += 1; st.toast("OK!")
                        else: st.error(f"Poprawnie: {correct}"); time.sleep(1)
                        st.session_state.test_idx += 1; st.rerun()
            else:
                st.success(f"Koniec! Wynik: {st.session_state.test_score}/{len(qs)}"); del st.session_state.test_q

elif choice == "📸 Skaner AI":
    update_activity("Skaner"); src = st.camera_input("Foto")
    if src and st.button("🚀 ANALIZUJ"):
        data = json.loads(get_openai_response("Extract German words to JSON 'flashcards' list.", Image.open(src)))
        for w in data.get("flashcards", []): save_word(u, {**w, "origin":"Skaner", "next_review":str(date.today())})
        st.success("Dodano!"); st.rerun()

elif choice == "➕ Dodaj":
    with st.form("add"):
        de, pl, ca = st.text_input("DE"), st.text_input("PL"), st.text_input("Tagi")
        if st.form_submit_button("Zapisz"):
            save_word(u, {"de":de, "pl":pl, "category":ca, "next_review":str(date.today()), "origin":"Dodaj"}); st.rerun()

elif choice == "⚙️ Moje Konto":
    st.header("⚙️ Konto")
    conf = st.checkbox("Potwierdzam usuwanie")
    col_d = st.columns(5)
    for i, lvl in enumerate(["A1", "A2", "B1", "B2", "C1"]):
        if col_d[i].button(lvl, disabled=not conf):
            get_db().table("flashcards").delete().eq("username", u).ilike("category", f"%{lvl}%").execute(); st.rerun()
