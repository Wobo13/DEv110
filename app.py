import streamlit as st
import json, os, random, re, hashlib, pandas as pd, secrets
from datetime import datetime, date, timedelta
from io import BytesIO
from PIL import Image
import google.generativeai as genai
import time

# --- KONFIGURACJA ---
APP_VERSION = "V109"
ADMIN_USER = "wobo"
AUTH_FILE, SESSIONS_FILE = "users_auth.json", "sessions.json"
BONUS_START = 1089.0
API_KEY = st.secrets.get("GEMINI_API_KEY") or st.session_state.get("manual_api_key", "")

# --- SYSTEM ---
def hash_pw(pw): return hashlib.sha256(str.encode(pw)).hexdigest()
def get_p(u, t): return f"{t}_{u}.json"
def load_j(p, d): return json.load(open(p, "r", encoding="utf-8")) if os.path.exists(p) else d
def save_j(p, d): json.dump(d, open(p, "w", encoding="utf-8"), indent=4)

def play_audio(txt):
    try:
        from gtts import gTTS
        f = BytesIO()
        tts = gTTS(text=txt, lang='de')
        tts.write_to_fp(f); f.seek(0)
        st.audio(f, format="audio/mp3", autoplay=True)
    except: st.error("Błąd audio")

# --- AUTOLOGOWANIE ---
if "auth" not in st.session_state:
    st.session_state.auth = False
    if "token" in st.query_params:
        s = load_j(SESSIONS_FILE, {})
        if st.query_params["token"] in s:
            st.session_state.auth, st.session_state.user = True, s[st.query_params["token"]]

if not st.session_state.auth:
    st.title("🔐 Niemiecki Master")
    u_in, p_in = st.text_input("Użytkownik").lower().strip(), st.text_input("Hasło", type="password")
    if st.button("Wejdź"):
        db = load_j(AUTH_FILE, {})
        if u_in in db and db[u_in] == hash_pw(p_in):
            st.session_state.auth, st.session_state.user = True, u_in; st.rerun()
    st.stop()

# --- INIT ---
u = st.session_state.user
if "flashcards" not in st.session_state: st.session_state.flashcards = load_j(get_p(u, "flashcards"), [])
if "user_data" not in st.session_state: 
    d = load_j(get_p(u, "user_data"), {})
    defaults = {"historical_cost":0.0, "streak":0, "last_active":str(date.today()-timedelta(days=1)), "last_seen":"Nigdy", "last_ts": time.time(), "time_stats": {}}
    for k, v in defaults.items():
        if k not in d: d[k] = v
    st.session_state.user_data = d

def update_activity(module="Inne"):
    current_ts = time.time()
    delta = current_ts - st.session_state.user_data.get("last_ts", current_ts)
    if 0 < delta < 900:
        stats = st.session_state.user_data.get("time_stats", {})
        stats[module] = stats.get(module, 0) + delta
        st.session_state.user_data["time_stats"] = stats
    st.session_state.user_data["last_ts"] = current_ts
    st.session_state.user_data["last_seen"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    save_j(get_p(u, "user_data"), st.session_state.user_data)

today_dt = date.today()

# --- MENU ---
st.sidebar.title(f"👤 {u.capitalize()}")
st.sidebar.caption(f"🚀 Wersja: {APP_VERSION}")
st.sidebar.info(f"🔥 Passa: **{st.session_state.user_data.get('streak', 0)} dni**")
if st.sidebar.button("Wyloguj"): st.session_state.clear(); st.rerun()

menu = ["📅 Powtórki", "🚀 Trening", "🕹️ Quiz", "🎴 Fiszki", "📸 Skaner AI", "📦 Generator słów", "➕ Dodaj", "📖 Słownik", "📊 Statystyki", "⚙️ Moje Konto"]
if u == ADMIN_USER: menu.append("👑 Admin")
choice = st.sidebar.radio("Nawigacja", menu)

if "last_choice" not in st.session_state: st.session_state.last_choice = choice
if st.session_state.last_choice != choice:
    for k in ["n_c", "n_m", "q_c", "q_s", "f_idx", "f_flipped"]:
        if k in st.session_state: del st.session_state[k]
    st.session_state.last_choice = choice

def is_correct(ans, correct):
    syns = [s.strip().lower() for s in re.split(r'[/,;]', correct)]
    return ans.strip().lower() in syns

def format_examples(ex_list):
    if not ex_list: return ""
    output = []
    for ex in ex_list:
        if isinstance(ex, dict): output.append(f"🇩🇪 {ex.get('de','')}\n🇵🇱 {ex.get('pl','')}")
        else: output.append(f"🇩🇪 {ex}")
    return "\n\n".join(output)

def get_full_audio_text(word, examples):
    text = f"{word} , , , . . . "
    if examples:
        for ex in examples:
            sentence = ex.get('de', ex) if isinstance(ex, dict) else ex
            text += f"{sentence} . . . "
    return text

# --- MODUŁY: POWTÓRKI / TRENING / QUIZ ---
if choice in ["📅 Powtórki", "🚀 Trening", "🕹️ Quiz"]:
    m_name = choice.replace("📅 ", "").replace("🚀 ", "").replace("🕹️ ", "")
    update_activity(m_name)
    is_l, is_q = (choice == "📅 Powtórki"), (choice == "🕹️ Quiz")
    kats = sorted(list(set([c.get("category","Inne") for c in st.session_state.flashcards])))
    sel_kat = st.selectbox("🎯 Kategoria:", ["Wszystkie"] + kats)
    td = str(date.today())
    all_cat_cards = [c for c in st.session_state.flashcards if sel_kat == "Wszystkie" or c.get("category") == sel_kat]
    
    if is_l:
        cards = [c for c in all_cat_cards if c.get("next_review", td) <= td]
        st.info(f"📝 Słówek do powtórzenia: **{len(cards)}**")
    else:
        cards = all_cat_cards
        if not is_q: st.info(f"🚀 Słówek w treningu: **{len(cards)}**")

    if not cards: st.success("Gotowe! 🎉")
    elif is_q:
        if "q_c" not in st.session_state:
            t = random.choice(cards); opts = random.sample([c['pl'] for c in all_cat_cards if c['pl']!=t['pl']], 3) + [t['pl']]
            random.shuffle(opts); st.session_state.update({"q_c":t,"q_a":t['pl'],"q_o":opts,"q_s":"ask"})
        st.write(f"### **{st.session_state.q_c['de']}**")
        if st.session_state.q_s == "ask":
            for o in st.session_state.q_o:
                if st.button(o, key=o, use_container_width=True):
                    st.session_state.u_c, st.session_state.q_s = o, "res"; st.session_state.q_c["next_review"] = str(date.today() + (timedelta(days=4) if is_correct(o, st.session_state.q_a) else timedelta(days=1)))
                    save_j(get_p(u, "flashcards"), st.session_state.flashcards); st.rerun()
        else:
            if is_correct(st.session_state.u_c, st.session_state.q_a): st.success("✅ Brawo!")
            else: st.error(f"❌ Poprawnie: {st.session_state.q_a}")
            play_audio(get_full_audio_text(st.session_state.q_c['de'], st.session_state.q_c.get("examples")))
            if st.button("Dalej"): st.session_state.pop("q_c"); st.rerun()
    else:
        if "n_c" not in st.session_state: st.session_state.update({"n_c":random.choice(cards),"n_m":"ask"})
        c = st.session_state.n_c
        st.write(f"### Słówko: **{c['de']}**")
        if st.session_state.n_m == "ask":
            with st.form("f"):
                u_a = st.text_input("Odpowiedź:"); ok = st.form_submit_button("Sprawdź")
                if ok: st.session_state.update({"u_a":u_a,"n_m":"res"}); st.rerun()
        else:
            if is_correct(st.session_state.u_a, c['pl']): st.success(f"✅ Dobrze: {c['pl']}")
            else: st.error(f"❌ Poprawnie: {c['pl']}")
            if c.get("examples"): st.info(format_examples(c["examples"]))
            play_audio(get_full_audio_text(c['de'], c.get("examples")))
            
            c1, c2, c3 = st.columns(3)
            days = None
            if is_l:
                if c1.button("🔴 1d", use_container_width=True): days = 1
                if c2.button("🟡 3d", use_container_width=True): days = 3
                if c3.button("🟢 7d", use_container_width=True): days = 7
            else:
                if st.button("Dalej", use_container_width=True): days = 0 # 0 oznacza po prostu przejście dalej

            if days is not None:
                if days > 0:
                    if date.fromisoformat(st.session_state.user_data.get("last_active", str(today_dt))) < today_dt:
                        st.session_state.user_data["streak"] = st.session_state.user_data.get("streak", 0) + 1
                        st.session_state.user_data["last_active"] = str(today_dt)
                    c["next_review"] = str(date.today() + timedelta(days=days))
                    save_j(get_p(u, "flashcards"), st.session_state.flashcards)
                st.session_state.pop("n_c"); st.rerun()

# --- MODUŁ: FISZKI ---
elif choice == "🎴 Fiszki":
    update_activity("Fiszki"); st.header("🎴 Fiszki")
    sel_kat = st.selectbox("🎯 Kategoria:", ["Wszystkie"] + sorted(list(set([c.get("category","Inne") for c in st.session_state.flashcards]))))
    cards = [c for c in st.session_state.flashcards if sel_kat == "Wszystkie" or c.get("category") == sel_kat]
    if cards:
        if "f_idx" not in st.session_state: st.session_state.f_idx = 0
        if "f_flipped" not in st.session_state: st.session_state.f_flipped = False
        c = cards[st.session_state.f_idx % len(cards)]
        ex_text = f"<div style='color:#00ff00; font-size: 0.9em; margin-top:10px;'>{format_examples(c.get('examples', [])).replace('\n', '<br>')}</div>" if st.session_state.f_flipped else ""
        st.markdown(f'<div style="height:280px;display:flex;flex-direction:column;align-items:center;justify-content:center;background:#262730;border:2px solid #4a4a4a;border-radius:15px;padding:20px;overflow-y:auto;"><h2 style="color:white;text-align:center;">{c["pl"] if st.session_state.f_flipped else c["de"]}</h2>{ex_text}</div>', unsafe_allow_html=True)
        col1, col2, col3 = st.columns([1,2,1])
        if col1.button("⬅️"): st.session_state.f_idx -= 1; st.session_state.f_flipped = False; st.rerun()
        if col2.button("🔄 OBRÓĆ", type="primary", use_container_width=True): st.session_state.f_flipped = not st.session_state.f_flipped; st.rerun()
        if col3.button("➡️"): st.session_state.f_idx += 1; st.session_state.f_flipped = False; st.rerun()
        if st.session_state.f_flipped: play_audio(get_full_audio_text(c['de'], c.get("examples")))

# --- MODUŁ: SKANER AI ---
elif choice == "📸 Skaner AI":
    update_activity("Inne"); src = st.camera_input("Foto") or st.file_uploader("Plik")
    if src and st.button("🚀 ANALIZUJ"):
        try:
            genai.configure(api_key=API_KEY); m = genai.GenerativeModel('gemini-2.5-flash')
            # Poprawiony prompt skanera (ucieczka klamerek)
            res = m.generate_content(["Zwróć JSON: [{'de':'...', 'pl':'...', 'category':'po polsku', 'examples':[{'de':'...', 'pl':'...'}]}]", Image.open(src).convert("RGB")])
            st.session_state.pending = json.loads(re.search(r'\[.*\]', res.text, re.DOTALL).group(0)); st.rerun()
        except: st.error("Błąd skanera")
    if "pending" in st.session_state:
        sk_kat = st.text_input("📁 Kategoria (PL):", "Skaner")
        ed = st.data_editor(pd.DataFrame(st.session_state.pending), use_container_width=True)
        if st.button("✅ Zapisz"):
            for w in ed.to_dict('records'):
                w.update({"next_review": str(date.today()), "category": sk_kat, "date_added": str(date.today())}); st.session_state.flashcards.append(w)
            save_j(get_p(u, "flashcards"), st.session_state.flashcards); st.session_state.pop("pending"); st.rerun()

# --- MODUŁ: GENERATOR SŁÓW (V109 - NAPRAWA F-STRING) ---
elif choice == "📦 Generator słów":
    update_activity("Inne"); st.header("📦 Generator")
    lvls = ["A1", "A2", "B1", "B2", "C1"]; cols = st.columns(len(lvls))
    for i, lvl in enumerate(lvls):
        if cols[i].button(lvl, use_container_width=True):
            with st.spinner(f"AI szuka nowych słówek {lvl}..."):
                try:
                    genai.configure(api_key=API_KEY); m = genai.GenerativeModel('gemini-2.5-flash')
                    existing = [c['de'] for c in st.session_state.flashcards[:300]]
                    # KLUCZOWA POPRAWKA V109: podwójne klamerki {{ }} by Python nie zgłosił błędu formatowania
                    prompt = f"""Generate exactly 25 unique German words level {lvl}. 
                    Category names MUST be in Polish.
                    Examples and translations MUST be in Polish.
                    Pomiń te słowa: {', '.join(existing)}. 
                    Return ONLY a JSON list of objects: 
                    [{{'de': 'word', 'pl': 'translation', 'category': 'kategoria_PL', 'examples': [{{'de': 'zdanie', 'pl': 'tłumaczenie'}}]}}]"""
                    
                    res = m.generate_content(prompt)
                    match = re.search(r'\[.*\]', res.text, re.DOTALL)
                    if match:
                        new = json.loads(match.group(0)); added = 0
                        for w in new:
                            if w['de'].lower().strip() not in [x['de'].lower() for x in st.session_state.flashcards]:
                                cat_pl = w.get('category','Inne')
                                w.update({"next_review": str(date.today()), "date_added": str(date.today()), "category": f"{lvl} - {cat_pl}"})
                                st.session_state.flashcards.append(w); added += 1
                        save_j(get_p(u, "flashcards"), st.session_state.flashcards); st.success(f"Dodano {added}!"); time.sleep(1); st.rerun()
                except Exception as e: st.error(f"Błąd generatora: {e}")

# --- POZOSTAŁE MODUŁY ---
elif choice == "➕ Dodaj":
    update_activity("Inne"); st.header("➕ Dodaj słówko")
    with st.form("add_f"):
        de, pl, kat = st.text_input("Niemiecki (DE)"), st.text_input("Polski (PL)"), st.text_input("Kategoria")
        if st.form_submit_button("Zapisz"):
            if de and pl:
                with st.spinner("Kontekst..."):
                    exs = []
                    try:
                        genai.configure(api_key=API_KEY); m = genai.GenerativeModel('gemini-2.5-flash')
                        r = m.generate_content(f"Zwróć JSON: [{{'de':'...', 'pl':'...'}}] - 2 krótkie zdania z '{de}'")
                        exs = json.loads(re.search(r'\[.*\]', r.text, re.DOTALL).group(0))
                    except: pass
                    st.session_state.flashcards.append({"de":de,"pl":pl,"category":kat or "Inne","next_review":str(date.today()),"date_added":str(date.today()), "examples": exs})
                    save_j(get_p(u, "flashcards"), st.session_state.flashcards); st.success("Dodano!"); st.rerun()

elif choice == "📖 Słownik":
    update_activity("Inne"); st.header("📖 Słownik")
    kats = sorted(list(set([c.get("category","Inne") for c in st.session_state.flashcards])))
    f_kat = st.selectbox("📁 Filtr:", ["Wszystkie"] + kats)
    search = st.text_input("🔍 Szukaj:")
    for i, c in enumerate(st.session_state.flashcards):
        if (f_kat == "Wszystkie" or c.get("category") == f_kat) and (search.lower() in c['de'].lower()):
            with st.expander(f"📝 {c['de']} — {c['pl']}"):
                with st.form(f"ed_{i}"):
                    n_de, n_pl, n_ka = st.text_input("DE", c['de']), st.text_input("PL", c['pl']), st.text_input("Kat", c.get('category','Inne'))
                    if st.form_submit_button("Zapisz"):
                        c.update({"de":n_de,"pl":n_pl,"category":n_ka}); save_j(get_p(u,"flashcards"), st.session_state.flashcards); st.rerun()
                    if st.form_submit_button("Usuń"):
                        st.session_state.flashcards.pop(i); save_j(get_p(u,"flashcards"), st.session_state.flashcards); st.rerun()

elif choice == "📊 Statystyki":
    update_activity("Inne"); df = pd.DataFrame(st.session_state.flashcards)
    if not df.empty:
        c1, c2, c3 = st.columns(3); c1.metric("Słówek", len(df)); c2.metric("Passa", f"{st.session_state.user_data.get('streak', 0)} dni")
        def m_v(r): return "Opanowane" if (date.fromisoformat(r) - today_dt).days >= 7 else "W trakcie"
        df['status'] = df['next_review'].apply(m_v); c3.metric("Opanowane", len(df[df['status']=="Opanowane"]))
        st.bar_chart(pd.DataFrame([{"D": (today_dt + timedelta(days=i)).strftime("%d.%m"), "S": len(df[df['next_review']==str(today_dt + timedelta(days=i))])} for i in range(14)]).set_index("D"))

elif choice == "👑 Admin":
    st.header("👑 Panel Zarządzania"); users = load_j(AUTH_FILE, {}); adm_list = []
    for user in users:
        ud = load_j(get_p(user, "user_data"), {}); ub = load_j(get_p(user, "flashcards"), [])
        df_u = pd.DataFrame(ub); mastery, ai_n = "0%", 0
        if not df_u.empty:
            opanowane = ((pd.to_datetime(df_u['next_review']).dt.date - today_dt).apply(lambda x: x.days if pd.notnull(x) else 0) >= 7).sum()
            mastery = f"{round((opanowane/len(df_u))*100)}%"; ai_n = len(df_u[df_u['category'] == "Skaner"])
        t_s = ud.get("time_stats", {}); total_t = sum(t_s.values())
        t_dist = f"N:{round(t_s.get('Nauka',0)/total_t*100)}%|T:{round(t_s.get('Trening',0)/total_t*100)}%|Q:{round(t_s.get('Quiz',0)/total_t*100)}%|F:{round(t_s.get('Fiszki',0)/total_t*100)}%|P:{round((total_t-sum([t_s.get(x,0) for x in ['Nauka','Trening','Quiz','Fiszki']]))/total_t*100)}%" if total_t > 0 else "Brak"
        adm_list.append({"Użytkownik": user, "Słówek": len(ub), "AI": ai_n, "Wiedza": mastery, "Czas": t_dist, "Widziany": ud.get("last_seen", "Nigdy"), "Koszt": round(ud.get("historical_cost", 0.0), 4)})
    st.table(pd.DataFrame(adm_list)); st.metric("Pozostały Bonus AI", f"{BONUS_START - sum(x['Koszt'] for x in adm_list):.4f} PLN")

elif choice == "⚙️ Moje Konto":
    update_activity("Inne"); st.header("⚙️ Moje Konto")
    with st.expander("🔑 Hasło"):
        with st.form("p"):
            o, n1, n2 = st.text_input("Stare", type="password"), st.text_input("Nowe", type="password"), st.text_input("Powtórz", type="password")
            if st.form_submit_button("Zmień"):
                db = load_j(AUTH_FILE, {})
                if db[u] == hash_pw(o) and n1 == n2: db[u] = hash_pw(n1); save_j(AUTH_FILE, db); st.success("OK")
    st.divider()
    with st.expander("⚠️ Strefa Niebezpieczna"):
        conf = st.checkbox("Potwierdzam"); lvls = ["A1", "A2", "B1", "B2", "C1"]; cols = st.columns(len(lvls))
        for i, l in enumerate(lvls):
            if cols[i].button(f"Usuń {l}", disabled=not conf):
                st.session_state.flashcards = [x for x in st.session_state.flashcards if l not in str(x.get('category',''))]
                save_j(get_p(u, "flashcards"), st.session_state.flashcards); st.rerun()
        if st.button("🗑️ USUŃ WSZYSTKO", type="primary", disabled=not conf):
            save_j(get_p(u, "flashcards"), []); st.session_state.flashcards = []; st.rerun()