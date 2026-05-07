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

# --- 1. KONFIGURACJA (Pobieranie z Secrets) ---
SUPABASE_URL = st.secrets.get("SUPABASE_URL", "")
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY", "")
API_KEY = st.secrets.get("OPENAI_API_KEY", "")

APP_VERSION = "V204 (Cloud Engine & Multi-Tags)"
ADMIN_USER = "wobo"

# Ujednolicenie etykiet czasu dla wykresów i tabeli admina
CLEAN_TIME_LABELS = {
    "Powtórki": "Pow", "Nauka": "Pow", "Pow": "Pow", "Nau": "Pow", "N": "Pow",
    "Trening": "Trn", "Trn": "Trn", "T": "Trn",
    "Quiz": "Qiz", "Qiz": "Qiz", "Q": "Qiz",
    "Fiszki": "Fis", "Fis": "Fis", "F": "Fis",
    "Testy": "Tst", "Tst": "Tst",
    "Skaner": "Skn", "Generator": "Gen", "Dodaj": "Dod", "Słownik": "Słn", "Konto": "Inn"
}

# --- 2. SILNIK BAZY DANYCH (SUPABASE) ---
def get_db():
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    return SyncPostgrestClient(f"{SUPABASE_URL}/rest/v1", headers=headers)

def hash_pw(pw): return hashlib.sha256(str.encode(pw)).hexdigest()

def normalize_text(t):
    if not t: return ""
    t = str(t).lower().strip().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    return re.sub(r'[?.!,;]', '', t)

# --- 3. SILNIK AI ---
def get_openai_response(prompt_text, img_obj=None):
    if not API_KEY: raise Exception("Brak klucza API.")
    client = OpenAI(api_key=API_KEY)
    messages = [{"role": "system", "content": "Jesteś nauczycielem niemieckiego. Odpowiadaj TYLKO w JSON. Kategorie tematyczne po polsku, rozdzielone przecinkami (tagi). Przykłady jako lista {de, pl}."}]
    if img_obj:
        buf = BytesIO(); img_obj.thumbnail((800, 800)); img_obj.save(buf, format="JPEG")
        img_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        messages.append({"role": "user", "content": [{"type": "text", "text": prompt_text}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}}]})
    else:
        messages.append({"role": "user", "content": prompt_text})
    res = client.chat.completions.create(model="gpt-4o-mini", messages=messages, response_format={"type": "json_object"})
    return res.choices[0].message.content

# --- 4. FUNKCJE DANYCH ---
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
    db = get_db(); res = db.table("flashcards").select("*").eq("username", username).order("id").execute()
    cards = res.data if res.data else []
    for c in cards: # Migracja wsteczna origin
        if not c.get("origin"):
            cat = str(c.get("category", "")).lower()
            c["origin"] = "Generator" if "gen" in cat else ("Skaner" if "skan" in cat else "Dodaj")
    return cards

def save_word(username, word_obj):
    db = get_db(); word_obj["username"] = username
    if "examples" not in word_obj: word_obj["examples"] = []
    db.table("flashcards").insert(word_obj).execute()

def delete_word(word_id): get_db().table("flashcards").delete().eq("id", word_id).execute()

def update_word(word_id, fields): get_db().table("flashcards").update(fields).eq("id", word_id).execute()

# --- 5. AUDIO ---
def play_audio(txt, ex_txt=None):
    try:
        from gtts import gTTS
        full = f"{txt}. . . . {ex_txt}" if ex_txt else txt
        f = BytesIO(); tts = gTTS(text=full, lang='de'); tts.write_to_fp(f); f.seek(0)
        st.audio(f, format="audio/mp3", autoplay=True)
    except: pass

# --- 6. LOGOWANIE ---
if "auth" not in st.session_state:
    st.session_state.auth = False
    if "token" in st.query_params:
        u_tk = st.query_params["token"]
        res = get_db().table("users_auth").select("*").eq("username", u_tk).execute()
        if res.data: st.session_state.auth, st.session_state.user = True, u_tk

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

# --- 7. INIT SESJI ---
u = st.session_state.user
st.session_state.user_data = load_user_data(u)
st.session_state.flashcards = load_flashcards(u)

def update_activity(m="Inne"):
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

# --- 8. SIDEBAR ---
st.sidebar.title(f"👤 {u.capitalize()}")
st.sidebar.caption(f"Wersja: {APP_VERSION}")
st.sidebar.info(f"🔥 Passa: **{st.session_state.user_data.get('streak', 0)} dni**")
if st.sidebar.button("Wyloguj", use_container_width=True):
    st.query_params.clear(); st.session_state.clear(); st.rerun()

menu = ["📅 Powtórki", "🚀 Trening", "🕹️ Quiz", "📝 Testy", "📸 Skaner AI", "📦 Generator słów", "➕ Dodaj", "📖 Słownik", "📊 Statystyki", "⚙️ Moje Konto"]
if u == ADMIN_USER: menu.append("👑 Admin")
choice = st.sidebar.radio("Nawigacja", menu)

# Reset stanów modułów
if "l_c" not in st.session_state or st.session_state.l_c != choice:
    for k in ["test_q", "test_idx", "test_score", "cur_review_list", "n_idx", "q_c", "q_s", "f_idx", "f_flipped", "pending"]:
        if k in st.session_state: del st.session_state[k]
    st.session_state.l_c, st.session_state.n_m, st.session_state.u_a = choice, "ask", ""

# --- 9. SŁOWNIK (Multi-Kategorie i Edycja) ---
if choice == "📖 Słownik":
    update_activity("Słownik")
    st.header("📖 Twój Słownik")
    all_tags = set()
    for c in st.session_state.flashcards:
        tags = [t.strip() for t in str(c.get('category', 'Inne')).split(',')]
        all_tags.update(tags)
    
    col1, col2 = st.columns([1, 2])
    f_tag = col1.selectbox("Filtruj kategorię/poziom:", ["Wszystkie"] + sorted(list(all_tags)))
    search = col2.text_input("Szukaj słowa:")
    
    filtered = [c for c in st.session_state.flashcards if (f_tag == "Wszystkie" or f_tag in [t.strip() for t in str(c.get('category','')).split(',')]) and (search.lower() in c['de'].lower() or search.lower() in c['pl'].lower())]
    st.write(f"Słówek: **{len(filtered)}**")
    
    for c in filtered:
        with st.expander(f"📝 {c['de']} — {c['pl']}"):
            with st.form(f"ed_{c['id']}"):
                n_de = st.text_input("Niemiecki", c['de'])
                n_pl = st.text_input("Polski", c['pl'])
                n_cat = st.text_input("Tagi (rozdziel przecinkiem)", c.get('category', ''))
                c1, c2 = st.columns(2)
                if c1.form_submit_button("Zapisz"):
                    update_word(c['id'], {"de": n_de, "pl": n_pl, "category": n_cat})
                    st.success("Zapisano!"); st.rerun()
                if c2.form_submit_button("Usuń"):
                    delete_word(c['id']); st.rerun()

# --- 10. GENERATOR (Baza SQL) ---
elif choice == "📦 Generator słów":
    update_activity("Generator")
    st.header("📦 Generator (z biblioteki Supabase)")
    cols = st.columns(5)
    lvls = ["A1", "A2", "B1", "B2", "C1"]
    for i, lvl in enumerate(lvls):
        if cols[i].button(lvl, use_container_width=True):
            with st.spinner(f"AI tłumaczy 25 słówek {lvl}..."):
                try:
                    db = get_db()
                    res = db.table("vocab_library").select("word").eq("level", lvl).execute()
                    if not res.data: st.error("Baza w chmurze jest pusta!")
                    else:
                        all_lib = [item['word'] for item in res.data]
                        my_w = [x['de'].lower() for x in st.session_state.flashcards]
                        avail = [w for w in all_lib if w.lower() not in my_w]
                        sel = random.sample(avail, min(25, len(avail)))
                        prompt = f"Przetłumacz na PL i otaguj tematycznie: {sel}. JSON: {{\"flashcards\": [{{ \"de\":\"...\", \"pl\":\"...\", \"category\":\"..., {lvl}\", \"examples\":[{{ \"de\":\"...\", \"pl\":\"...\" }}] }}]}}"
                        data = json.loads(get_openai_response(prompt))
                        for w in data.get("flashcards", []):
                            save_word(u, {**w, "next_review": str(date.today()), "origin": "Generator"})
                        st.session_state.user_data["historical_cost"] += 0.01; st.success("Dodano!"); st.rerun()
                except Exception as e: st.error(f"Błąd: {e}")

# --- 11. POWTÓRKI / TRENING ---
elif choice in ["📅 Powtórki", "🚀 Trening"]:
    is_r = (choice == "📅 Powtórki")
    update_activity("Powtórki")
    if "cur_review_list" not in st.session_state:
        pool = st.session_state.flashcards
        if is_r: pool = [c for c in pool if str(c.get("next_review", str(date.today()))) <= str(date.today())]
        random.shuffle(pool); st.session_state.cur_review_list, st.session_state.n_idx = pool, 0
    cards = st.session_state.cur_review_list
    if not cards: st.success("Wszystko opanowane! 🎊")
    else:
        idx = st.session_state.n_idx
        if idx >= len(cards): st.success("Koniec sesji!")
        else:
            c = cards[idx]
            st.write(f"### Słówko: **{c['de']}**")
            if st.session_state.n_m == "ask":
                u_in = st.text_input("Tłumaczenie (PL):", key=f"ans_{idx}")
                if st.button("Sprawdź"): st.session_state.u_a, st.session_state.n_m = u_in, "res"; st.rerun()
            else:
                if normalize_text(st.session_state.u_a) == normalize_text(c['pl']): st.success(f"✅ Dobrze: {c['pl']}")
                else: st.error(f"❌ Poprawnie: {c['pl']}")
                exs = c.get("examples", [])
                fex = exs[0].get("de") if exs and isinstance(exs, list) and len(exs)>0 else None
                play_audio(c['de'], fex)
                if is_r:
                    c1, c2, c3 = st.columns(3); d = None
                    if c1.button("🔴 Słabo"): d = 1
                    if c2.button("🟡 Średnio"): d = 3
                    if c3.button("🟢 Dobrze"): d = 7
                    if d:
                        update_word(c['id'], {"next_review": str(date.today() + timedelta(days=d))})
                        st.session_state.n_idx += 1; st.session_state.n_m = "ask"; st.rerun()
                elif st.button("Dalej ➡️"): st.session_state.n_idx += 1; st.session_state.n_m = "ask"; st.rerun()

# --- 12. TESTY (Robust & Hints) ---
elif choice == "📝 Testy":
    update_activity("Testy")
    if len(st.session_state.flashcards) < 5: st.warning("Min. 5 słówek.")
    else:
        if "test_q" not in st.session_state:
            n_q = st.slider("Liczba pytań", 5, 20, 5)
            if st.button("🚀 GENERUJ TEST", use_container_width=True, type="primary"):
                with st.spinner("AI przygotowuje zadania..."):
                    sample = random.sample(st.session_state.flashcards, n_q)
                    words = ", ".join([f"{w['de']} ({w['pl']})" for w in sample])
                    prompt = f"Generuj test dla: {words}. JSON: {{ \"questions\": [{{ \"hint\":\"PL hint\", \"sentence\":\"German sentence with word\", \"correct\":\"DE word\", \"distractors\":[\"...\"], \"type\":\"QUIZ\" }}] }}"
                    try:
                        data = json.loads(get_openai_response(prompt))
                        st.session_state.test_q, st.session_state.test_idx, st.session_state.test_score = data["questions"], 0, 0
                        st.rerun()
                    except: st.error("AI nie odpowiedziało. Spróbuj jeszcze raz.")
        else:
            qs = st.session_state.test_q; t_idx = st.session_state.test_idx
            if t_idx < len(qs):
                q = qs[t_idx]; correct = str(q.get('correct',''))
                st.info(f"💡 Wskazówka (PL): {q.get('hint','brak')}")
                st.markdown(f"#### {q.get('sentence','?')}")
                ans = None
                if q.get('type') == "QUIZ":
                    opts = list(set(q.get('distractors', []) + [correct])); random.shuffle(opts)
                    cols = st.columns(2)
                    for i, o in enumerate(opts):
                        if cols[i%2].button(o, key=f"t_{t_idx}_{i}"): ans = o
                else:
                    ui = st.text_input("Twoja odpowiedź:", key=f"ti_{t_idx}")
                    if st.button("Zatwierdź"): ans = ui
                if ans:
                    if normalize_text(ans) == normalize_text(correct): st.session_state.test_score += 1; st.toast("Dobrze! 🌟")
                    else: st.error(f"Źle. Poprawnie: {correct}"); time.sleep(1)
                    st.session_state.test_idx += 1; st.rerun()
            else:
                score, total = st.session_state.test_score, len(qs)
                perc = round((score/total)*100) if total > 0 else 0
                st.session_state.user_data["test_history"].append({"date": datetime.now().strftime("%d.%m"), "score": score, "total": total, "perc": perc})
                save_user_data(u, st.session_state.user_data); st.balloons(); st.success(f"Wynik: {score}/{total} ({perc}%)")
                if st.button("Powrót"): del st.session_state.test_q; st.rerun()

# --- 13. ADMIN (Full Analytics) ---
elif choice == "👑 Admin":
    st.header("👑 Panel Admina")
    st.link_button("💸 OpenAI Billing", "https://platform.openai.com/usage", use_container_width=True)
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
            lbl = CLEAN_TIME_LABELS.get(m.strip(), "Inn")
            merged[lbl] = merged.get(lbl, 0) + s
            global_time[lbl] = global_time.get(lbl, 0) + s
        
        u_times = ", ".join([f"{l}:{round(s/60)}m" for l, s in merged.items() if s > 15])
        adm_list.append({"Użytkownik":username, "Słów":len(cards), "Ręcznie":m_man, "Gen":m_gen, "Skan":m_skn, "Testy":len(user.get("test_history",[])), "Czas":u_times, "Koszt (PLN)":round(user.get("historical_cost",0),4)})
    
    st.columns(2)[0].metric("Łącznie słówek", sum(x['Słów'] for x in adm_list))
    st.columns(2)[1].metric("Suma kosztów AI", f"{total_cost:.2f} PLN")
    st.table(pd.DataFrame(adm_list))
    if global_time:
        fig = go.Figure(data=[go.Bar(x=list(global_time.keys()), y=list(global_time.values()), marker_color='#1E88E5')])
        fig.update_layout(template="plotly_dark", height=400, title="Czas globalny (minuty)"); st.plotly_chart(fig, use_container_width=True)

# --- 14. MOJE KONTO (Edycja poziomu) ---
elif choice == "⚙️ Moje Konto":
    st.header("⚙️ Zarządzanie Kontem"); update_activity("Inn")
    with st.expander("🔑 Zmień hasło"):
        with st.form("pw_f"):
            o, n, cp = st.text_input("Stare", type="password"), st.text_input("Nowe", type="password"), st.text_input("Powtórz", type="password")
            if st.form_submit_button("Zmień"):
                db = get_db(); res = db.table("users_auth").select("*").eq("username", u).execute()
                if res.data and res.data[0]["password_hash"] == hash_pw(o) and n == cp:
                    db.table("users_auth").update({"password_hash": hash_pw(n)}).eq("username", u).execute(); st.success("Hasło zmienione!")
    
    st.divider(); st.subheader("🗑️ Usuwanie danych")
    conf = st.checkbox("Potwierdzam usuwanie")
    col_d = st.columns(5)
    for i, lvl in enumerate(["A1", "A2", "B1", "B2", "C1"]):
        if col_d[i].button(f"Usuń {lvl}", disabled=not conf):
            get_db().table("flashcards").delete().eq("username", u).ilike("category", f"%{lvl}%").execute()
            st.success(f"Wyczyszczono {lvl}!"); time.sleep(1); st.rerun()
    if st.button("RESET CAŁEJ BAZY", type="primary", disabled=not conf):
        get_db().table("flashcards").delete().eq("username", u).execute(); st.rerun()

# --- 15. DODAJ RĘCZNIE ---
elif choice == "➕ Dodaj":
    st.header("➕ Dodaj nowe słówko")
    with st.form("manual"):
        de = st.text_input("Słówko po niemiecku")
        pl = st.text_input("Tłumaczenie")
        cat = st.text_input("Kategorie (np. A1, dom, czasownik)", "Inne")
        if st.form_submit_button("Dodaj"):
            if de and pl:
                save_word(u, {"de": de, "pl": pl, "category": cat, "next_review": str(date.today()), "origin": "Dodaj"})
                st.success("Dodano!")
