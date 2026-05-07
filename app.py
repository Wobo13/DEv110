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
APP_VERSION = "V185 (Stats Restored & PL Categories)"
ADMIN_USER = "wobo"
AUTH_FILE = "users_auth.json"
SESSIONS_FILE = "sessions.json"
BONUS_START = 1089.0

# Pobieranie klucza API
API_KEY = st.secrets.get("OPENAI_API_KEY") or st.secrets.get("GEMINI_API_KEY") or st.session_state.get("manual_api_key", "")

# KOLEJNOŚĆ MENU
MODULE_ORDER = [
    "Powtórki", 
    "Trening", 
    "Quiz", 
    "Fiszki", 
    "Testy",
    "Skaner", 
    "Generator", 
    "Dodaj", 
    "Słownik"
]

# --- POTĘŻNA WEWNĘTRZNA BAZA SŁÓWEK (250 NA POZIOM) ---
VOCAB_DB = {
    "A1": [
        "Apfel", "Brot", "Haus", "Auto", "Schule", "Lehrer", "Wasser", "Milch", "Tisch", "Stuhl", "Buch", "Stift", "Kind", "Mutter", "Vater", "Freund", "Stadt", "Land", "Weg", "Zeit", "Essen", "Trinken", "Schlafen", "Lernen", "Arbeiten", "Gehen", "Kommen", "Hören", "Sehen", "Sprechen", "Groß", "Klein", "Gut", "Schlecht", "Schön", "Hässlich", "Alt", "Jung", "Neu", "Kalt", "Heute", "Morgen", "Gestern", "Woche", "Jahr", "Tag", "Nacht", "Name", "Zahl", "Geld",
        "Hund", "Katze", "Baum", "Blume", "Sonne", "Mond", "Regen", "Schnee", "Wind", "Bett", "Zimmer", "Küche", "Bad", "Fenster", "Tür", "Schlüssel", "Tasche", "Gabel", "Löffel", "Messer", "Teller", "Tasse", "Glas", "Saft", "Kaffee", "Tee", "Zucker", "Salz", "Fleisch", "Fisch", "Gemüse", "Obst", "Banane", "Ei", "Käse", "Reis", "Nudeln", "Kuchen", "Zeitung", "Radio", "Handy", "Fahrrad", "Zug", "Bus", "Bahnhof", "Flughafen", "Hotel", "Arzt", "Krankenhaus", "Apotheke",
        "Arbeit", "Pause", "Ferien", "Urlaub", "Meer", "Berg", "Wald", "Straße", "Platz", "Garten", "Park", "Schrank", "Sofa", "Lampe", "Bild", "Uhr", "Kleidung", "Hose", "Hemd", "Rock", "Kleid", "Schuh", "Jacke", "Mantel", "Hut", "Brille", "Kopf", "Hand", "Fuß", "Bein", "Arm", "Auge", "Ohr", "Nase", "Mund", "Haar", "Herz", "Frühstück", "Mittagessen", "Abendessen", "Kochen", "Backen", "Waschen", "Putzen", "Kaufen", "Verkaufen", "Bezahlen", "Rechnen", "Schreiben", "Lesen",
        "Singen", "Tanzen", "Spielen", "Laufen", "Schwimmen", "Reisen", "Besuchen", "Fragen", "Antworten", "Wissen", "Denken", "Glauben", "Hoffen", "Lieben", "Hassen", "Lachen", "Weinen", "Warten", "Suchen", "Finden", "Helfen", "Geben", "Nehmen", "Bringen", "Zeigen", "Sagen", "Erzählen", "Erklären", "Verstehen", "Vergessen", "Wichtig", "Richtig", "Falsch", "Einfach", "Schwer", "Leicht", "Heiß", "Warm", "Trocken", "Nass", "Hell", "Dunkel", "Laut", "Leise", "Schnell", "Langslow", "Müde", "Krank", "Gesund", "Glücklich",
        "Traurig", "Sauer", "Süß", "Bitter", "Teuer", "Billig", "Reich", "Arm", "Sauber", "Schmutzig", "Voll", "Leer", "Offen", "Geschlossen", "Erster", "Letzter", "Nächster", "Hier", "Dort", "Überall", "Nirgendwo", "Immer", "Oft", "Manchmal", "Selten", "Nie", "Vielleicht", "Sicher", "Gerne", "Zusammen", "Allein", "Wenig", "Viel", "Genug", "Echt", "Wirklich", "Wieder", "Noch", "Schon", "Erst", "Dann", "Danach", "Zuerst", "Schließlich", "Aber", "Oder", "Und", "Sondern", "Denn", "Weil"
    ],
    "A2": [
        "Urlaub", "Reise", "Bahnhof", "Flugzeug", "Hotel", "Küche", "Kühlschrank", "Gabel", "Löffel", "Messer", "Kleidung", "Hose", "Hemd", "Schuh", "Wetter", "Regen", "Sonne", "Wolke", "Gesundheit", "Krankheit", "Arzt", "Medizin", "Körper", "Kopf", "Hand", "Fuß", "Sport", "Spiel", "Musik", "Film", "Besuchen", "Verstehen", "Vergessen", "Bestellen", "Bezahlen", "Wohnen", "Mieten", "Kaufen", "Verkaufen", "Feiern", "Wichtig", "Wahr", "Falsch", "Fertig", "Glücklich", "Traurig", "Müde", "Sauer", "Süß", "Heiß",
        "Abwaschen", "Anrufen", "Anziehen", "Aufräumen", "Ausgeben", "Aussehen", "Baden", "Bedeuten", "Beeilen", "Benutzen", "Berichten", "Beschreiben", "Besichtigen", "Bestimmen", "Besprechen", "Bewerben", "Bezahlen", "Buchen", "Buchstabieren", "Danken", "Dauern", "Diskutieren", "Drucken", "Duschen", "Einkaufen", "Einladen", "Einziehen", "Enden", "Entschuldigen", "Erinnern", "Erkennen", "Erlauben", "Erleben", "Erzählen", "Fehlen", "Feiern", "Fernsehen", "Frühstücken", "Fühlen", "Füttern", "Gehören", "Gewinnen", "Glauben", "Grillen", "Grüßen", "Heiraten", "Hoffen", "Holen", "Interessieren", "Kämmen",
        "Kennenlernen", "Klettern", "Klingeln", "Klopf", "Kochen", "Korrigieren", "Kosten", "Lächeln", "Laden", "Landem", "Laufen", "Leiden", "Leihen", "Leiten", "Lernen", "Liefern", "Lösen", "Lügen", "Machen", "Malen", "Meinen", "Merken", "Mieten", "Mitbringen", "Mitkommen", "Mitmachen", "Mitteilen", "Nachsehen", "Nennen", "Notieren", "Öffnen", "Organisieren", "Packen", "Parken", "Passieren", "Planen", "Probieren", "Prüfen", "Putzen", "Rauchen", "Regnen", "Reisen", "Renovieren", "Reparieren", "Reservieren", "Riechen", "Rufen", "Sammeln", "Schalten", "Schenken",
        "Schicken", "Schmecken", "Schminken", "Schneiden", "Schneien", "Schreiben", "Schwimmen", "Segeln", "Sehen", "Senden", "Setzen", "Singen", "Sitzen", "Sparen", "Spazieren", "Speichern", "Spielen", "Sprechen", "Springen", "Spülen", "Starten", "Stecken", "Stehen", "Stehlen", "Steigen", "Stellen", "Sterben", "Stimmen", "Stören", "Studieren", "Suchen", "Surfen", "Tanken", "Tanzen", "Tauschen", "Teilen", "Teilnehmen", "Telefonieren", "Tragen", "Träumen", "Treffen", "Trennen", "Trinken", "Trocknen", "Tun", "Überweisen", "Üben", "Übernachten", "Übersetzen", "Überweisen",
        "Umziehen", "Unterhalten", "Unterschreiben", "Untersuchen", "Verabreden", "Verabschieden", "Verändern", "Verbessern", "Verbieten", "Verdienen", "Vergleichen", "Vergrößern", "Verkaufen", "Verlängern", "Verlassen", "Verlieren", "Vermieten", "Vermuten", "Verpassen", "Verreisen", "Verschieben", "Versprechen", "Verstehen", "Versuchen", "Verteilen", "Vertrauen", "Verursachen", "Verwenden", "Verzeihen", "Vorbereiten", "Vorstellen", "Wählen", "Wandern", "Warten", "Waschen", "Wechseln", "Wecken", "Wehtun", "Weitergehen", "Werden", "Werfen", "Wiederholen", "Wissen", "Wohnen", "Wünschen", "Zahlen", "Zeichnen", "Zeigen", "Zuhören", "Zumachen"
    ],
    "B1": [
        "Erfahrung", "Erfolg", "Entscheidung", "Meinung", "Gefühl", "Beziehung", "Zukunft", "Vergangenheit", "Umwelt", "Natur", "Gesellschaft", "Politik", "Wirtschaft", "Wissenschaft", "Technik", "Beruf", "Ausbildung", "Studium", "Gehalt", "Vertrag", "Vorbereiten", "Organisieren", "Diskutieren", "Argumentieren", "Erklären", "Empfehlen", "Vorschlagen", "Warnen", "Hoffen", "Träumen", "Gefährlich", "Sicher", "Möglich", "Unmöglich", "Nötig", "Nützlich", "Schwierig", "Leicht", "Interessant", "Langweilig", "Obwohl", "Trotzdem", "Deshalb", "Deswegen", "Falls", "Damit", "Stattdessen", "Zuerst", "Schließlich", "Besonders",
        "Abhängig", "Ablehnen", "Abmachen", "Abnehmen", "Abonnieren", "Absagen", "Abschließen", "Absolvieren", "Abstimmen", "Abwarten", "Achten", "Ändern", "Anerkennen", "Anfangen", "Anfordern", "Angeben", "Angehören", "Angreifen", "Anhalten", "Anklagen", "Ankommen", "Ankündigen", "Anmelden", "Annehmen", "Anpassen", "Anrufen", "Anschließen", "Ansehen", "Ansprechen", "Anstrengen", "Antworten", "Anwenden", "Anzeigen", "Anziehen", "Arbeiten", "Ärgern", "Aufbauen", "Aufgeben", "Aufhalten", "Aufhören", "Aufklären", "Aufmerksam", "Aufaufnahme", "Aufräumen", "Aufregen", "Aufstehen", "Auftreten", "Aufwachen", "Ausbilden", "Ausdehnen",
        "Ausdrücken", "Auseinander", "Ausfallen", "Ausfüllen", "Ausgeben", "Ausgehen", "Ausgleichen", "Aushalten", "Auskennen", "Auskommen", "Auslachen", "Ausleihen", "Ausmachen", "Ausnutzen", "Auspacken", "Ausprobieren", "Ausruhen", "Ausscheiden", "Ausschließen", "Aussehen", "Aussprechen", "Ausstellen", "Aussuchen", "Austauschen", "Austreten", "Ausüben", "Auswandern", "Auswählen", "Ausweisen", "Auswirken", "Ausziehen", "Backen", "Bauen", "Beachten", "Beantragen", "Beantworten", "Bebauen", "Bedanken", "Bedeuten", "Bedienen", "Bedingung", "Beeinflussen", "Beenden", "Befinden", "Befolgen", "Befreien", "Begegnen", "Begeistern", "Beginnen", "Begleiten",
        "Begrenzen", "Begründen", "Begrüßen", "Behalten", "Behandeln", "Behaupten", "Behindern", "Beibringen", "Beifügen", "Beilegen", "Beitragen", "Bekannt", "Bekommen", "Belegen", "Beleidigen", "Belohnen", "Bemühen", "Benutzen", "Benötigen", "Beraten", "Berechnen", "Bereiten", "Berichten", "Berücksichtigen", "Beruhigen", "Berühmt", "Beschädigen", "Beschäftigen", "Bescheiden", "Bescheinen", "Beschleunigen", "Beschließen", "Beschreiben", "Beschweren", "Besichtigen", "Besitzen", "Besonderer", "Besprechen", "Bestätigen", "Bestehen", "Bestellen", "Bestimmen", "Bestrafen", "Besuchen", "Beteiligen", "Betrachten", "Betreuen", "Betrügen", "Betteln", "Bevor",
        "Bevorzugen", "Bewahren", "Bewegen", "Beweisen", "Bewerben", "Bewerten", "Bewohner", "Bezahlen", "Bezeichnen", "Beziehen", "Beziehung", "Bezirk", "Bezug", "Bieten", "Bilden", "Bildung", "Billigen", "Binden", "Bitten", "Blasen", "Bleiben", "Blick", "Blind", "Blitz", "Bloß", "Blühen", "Blume", "Blut", "Boden", "Bogen", "Bohren", "Boot", "Bord", "Böse", "Braten", "Brauchen", "Brauen", "Brechen", "Breit", "Brennen", "Bringen", "Bruch", "Brücke", "Bruder", "Brust", "Bube", "Buch", "Buchen", "Bühne", "Bund"
    ],
    "B2": [
        "Herausforderung", "Verantwortung", "Voraussetzung", "Zusammenhang", "Unterschied", "Vergleich", "Entwicklung", "Fortschritt", "Ursache", "Wirkung", "Eindruck", "Einfluss", "Ergebnis", "Erwartung", "Gerechtigkeit", "Freiheit", "Sicherheit", "Vertrauen", "Geduld", "Vorsicht", "Beeinflussen", "Verbessern", "Verschlechtern", "Erreichen", "Vermeiden", "Lösen", "Teilnehmen", "Unterstützen", "Fördern", "Fordern", "Effizient", "Effektiv", "Kreativ", "Kritisch", "Logisch", "Objektiv", "Subjektiv", "Typisch", "Zufällig", "Regelmäßig", "Anscheinend", "Vermutlich", "Eventuell", "Tatsächlich", "Grundsätzlich", "Eigentlich", "Überall", "Nirgendwo", "Irgendwie", "Sowieso",
        "Abweichen", "Aneignen", "Anfordern", "Anordnen", "Anschaffen", "Anstellen", "Antreffen", "Appellieren", "Auffassen", "Aufgreifen", "Aufheben", "Aufwenden", "Ausarbeiten", "Ausdehnen", "Ausführen", "Auslösen", "Ausnutzen", "Ausstatten", "Ausüben", "Bedenken", "Begehen", "Begreifen", "Beharren", "Beifügen", "Beitragen", "Bekämpfen", "Belasten", "Belegen", "Bemängeln", "Bemessen", "Benachrichtigen", "Benachteiligen", "Beruhen", "Beschaffen", "Beseitigen", "Bestand", "Bestreiten", "Beteiligen", "Betreffen", "Beurteilen", "Bevorzugen", "Bewältigen", "Bewirken", "Beziehen", "Bezweifeln", "Bilanz", "Bündeln", "Darlegen", "Dazugehören", "Definieren",
        "Dementieren", "Differenzieren", "Diskriminieren", "Dokumentieren", "Durchdringen", "Durchführen", "Durchsetzen", "Eignen", "Einbeziehen", "Einführen", "Eingliedern", "Eingreifen", "Einhalten", "Einleiten", "Einreichen", "Einschränken", "Einsetzen", "Einstellen", "Einwenden", "Einwilligen", "Empfangen", "Empfehlen", "Entfalten", "Entgegennehmen", "Entlasten", "Entnehmen", "Entscheiden", "Entschärfen", "Entsprechen", "Entstehen", "Entwickeln", "Entwerfen", "Entziehen", "Erachten", "Erarbeiten", "Erfahren", "Erfassen", "Erfordern", "Erfüllen", "Ergänzen", "Ergreifen", "Erheben", "Erkennen", "Erlangen", "Erläutern", "Erledigen", "Erleichtern", "Ermöglichen", "Erneuern", "Ernennen",
        "Erörtern", "Erproben", "Erreichen", "Errichten", "Erscheinen", "Erschließen", "Ersetzen", "Erstatten", "Erstellen", "Erteilen", "Ertragen", "Erwarten", "Erweisen", "Erweitern", "Erwerben", "Erzielen", "Fahrlässig", "Festlegen", "Feststellen", "Filtern", "Finanzieren", "Fließen", "Folgen", "Forderung", "Förderung", "Formulieren", "Fortsetzen", "Führen", "Fügen", "Fungieren", "Garantieren", "Gedeihen", "Gefährden", "Gegenüberstellen", "Gehorchen", "Gehören", "Gelangen", "Gelten", "Genügen", "Geraten", "Gewährleisten", "Gewähren", "Gewichten", "Gewinnen", "Glauben", "Gleichen", "Gliedern", "Gönnen", "Greifen", "Grenzen",
        "Gründen", "Handeln", "Handhaben", "Hängen", "Häufen", "Heben", "Heften", "Heilen", "Hemmen", "Herangehen", "Herleiten", "Hervorgehen", "Hervorrufen", "Hinweisen", "Hinzufügen", "Hören", "Identifizieren", "Ignorieren", "Illustrieren", "Implementieren", "Importieren", "Indizieren", "Informieren", "Integrieren", "Interessieren", "Interpretieren", "Investieren", "Irren", "Isolieren", "Justieren", "Kalkulieren", "Kämpfen", "Kategorisieren", "Kaufen", "Kehren", "Kennzeichnen", "Klären", "Klassifizieren", "Kleben", "Klingen", "Kombinieren", "Kommen", "Kommentieren", "Kommunizieren", "Kompensieren", "Kompensieren", "Konfrontieren", "Konkretisieren", "Konkurrieren", "Konstatieren"
    ],
    "C1": [
        "Auseinandersetzung", "Auswirkung", "Bedeutung", "Erkenntnis", "Fähigkeit", "Maßnahme", "Notwendigkeit", "Perspektive", "Struktur", "Vielfalt", "Anforderung", "Bewältigung", "Darstellung", "Einschätzung", "Gewährleistung", "Hintergrund", "Integration", "Kompetenz", "Nachhaltigkeit", "Umsetzung", "Analysieren", "Berücksichtigen", "Differenzieren", "Evaluieren", "Gewährleisten", "Hinterfragen", "Implementieren", "Konkretisieren", "Reflektieren", "Veranschaulichen", "Außergewöhnlich", "Beträchtlich", "Eindeutig", "Erheblich", "Gravierend", "Kontrovers", "Nachhaltig", "Präzise", "Umfangreich", "Wesentliche", "Dementsprechend", "Demnach", "Infolgedessen", "Inwiefern", "Inwieweit", "Jegliche", "Lediglich", "Nichtsdestotrotz", "Stufenweise", "Zunehmend",
        "Abstrahieren", "Akquirieren", "Akzentuieren", "Antizipieren", "Artikulieren", "Assoziieren", "Attestieren", "Autarkie", "Autorisieren", "Bagatellisieren", "Bilateral", "Charakterisieren", "Chiffrieren", "Chronologisch", "Defizit", "Degradieren", "Deklarieren", "Delegieren", "Demokratisierung", "Demonstrieren", "Denunziieren", "Deplatzieren", "Deponieren", "Derivat", "Desillusionieren", "Destabilisieren", "Detailgenau", "Determinieren", "Diagnostizieren", "Diametral", "Diffamieren", "Differenzierung", "Diffus", "Diktieren", "Dilemma", "Dimensionieren", "Diskreditieren", "Diskrepanz", "Diskretion", "Diskurs", "Dislozieren", "Disponieren", "Disproportion", "Disput", "Dissonanz", "Distanzieren", "Distinktion", "Divergieren", "Diversifikation", "Diversität",
        "Dogmatisch", "Dominanz", "Dominieren", "Dramatisieren", "Dualismus", "Duplizieren", "Effektivität", "Effizienz", "Egalisieren", "Egomanie", "Eklatant", "Ekstatisch", "Elaborieren", "Elementar", "Eliminieren", "Elite", "Eloquent", "Emanzipieren", "Empathie", "Empirisch", "Emulgieren", "Enthusiasmus", "Entität", "Episodisch", "Equitabel", "Erodieren", "Erkenntnistheorie", "Eskalieren", "Etablieren", "Ethik", "Etymologie", "Euphemismus", "Euphorisch", "Evakuieren", "Evaluiert", "Evident", "Evolutionär", "Exazerbieren", "Exekutieren", "Exemplarisch", "Exemplifizieren", "Existenziell", "Exorbitant", "Exotisch", "Expandieren", "Expedieren", "Experimentell", "Explizit", "Explizieren", "Explodieren",
        "Exponieren", "Exposition", "Expressiv", "Exquisit", "Extrahieren", "Extraordinär", "Extrapolieren", "Extravagant", "Extremismus", "Exzentrisch", "Exzessiv", "Facettenreich", "Faktisch", "Fakultativ", "Fatalismus", "Feudalismus", "Fiktional", "Filigran", "Fluktuieren", "Fokussieren", "Formell", "Fragmentieren", "Fraktion", "Frivol", "Fundamental", "Fundiert", "Funktionalität", "Garant", "Generieren", "Globalisierung", "Glosse", "Gönnerhaft", "Gradualismus", "Gratifikation", "Gravitieren", "Grosso", "Habitus", "Haptisch", "Harmonisieren", "Hegemonie", "Heterogen", "Heuristisch", "Hierarchie", "Holistisch", "Homogenisieren", "Humanismus", "Hypothese", "Hysterisch", "Idealismus", "Identifikation",
        "Ideologie", "Idyllisch", "Ignoranz", "Illegalität", "Illusionär", "Illustrativ", "Imaginär", "Immanent", "Immerwährend", "Immobiliar", "Immunisieren", "Impartiell", "Impasse", "Imperativ", "Imperialismus", "Implikation", "Implizit", "Implodieren", "Imponieren", "Imposant", "Impulsiv", "Inadäquat", "Inaugurieren", "Indifferenz", "Individuierung", "Indoktrinieren", "Induktiv", "Industriell", "Ineffizient", "Inexistent", "Infaust", "Inferiorität", "Inflationär", "Inflexibel", "Informationell", "Infrastruktur", "Inhärent", "Inhibition", "Initiieren", "Inklusion", "Inkompatibel", "Inkompetenz", "Inkongruenz", "Inkonsistent", "Inkorporieren", "Inkrementell", "Inkubation", "Innovation", "Inoffiziell", "Inquisitorisch"
    ]
}

# --- SYSTEM POMOCNICZY ---
def hash_pw(pw):
    return hashlib.sha256(str.encode(pw)).hexdigest()

def get_p(u, t):
    return f"{t}_{u}.json"

def normalize_text(t):
    if not t: return ""
    t = str(t).lower().strip()
    t = t.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    t = re.sub(r'[?.!,;]', '', t)
    return t

def load_j(p, d):
    if os.path.exists(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return d
    return d

def save_j(p, d):
    dir_name = os.path.dirname(p) or '.'
    try:
        fd, temp_path = tempfile.mkstemp(dir=dir_name, text=True)
        with os.fdopen(fd, 'w', encoding='utf-8') as f: 
            json.dump(d, f, indent=4)
        os.replace(temp_path, p)
    except Exception as e:
        with open(p, "w", encoding="utf-8") as f:
            json.dump(d, f, indent=4)

def is_word_mastered(next_review_date):
    try:
        if not next_review_date: return False
        days_diff = (date.fromisoformat(str(next_review_date)) - date.today()).days
        return days_diff >= 7
    except: return False

def force_save():
    save_j(get_p(st.session_state.user, "flashcards"), st.session_state.flashcards)
    save_j(get_p(st.session_state.user, "user_data"), st.session_state.user_data)

def play_audio(txt, example_txt=None):
    try:
        from gtts import gTTS
        full_text = txt
        if example_txt:
            full_text = f"{txt}. . . . {example_txt}"
        f = BytesIO()
        tts = gTTS(text=full_text, lang='de')
        tts.write_to_fp(f)
        f.seek(0)
        st.audio(f, format="audio/mp3", autoplay=True)
    except:
        pass

def parse_ai_json(text):
    try:
        match = re.search(r'(\{.*\}|\[.*\])', text, re.DOTALL)
        if match:
            clean = match.group(0).strip()
            return json.loads(clean)
        return json.loads(text.strip())
    except: return None

def is_correct(u_ans, c_ans_str):
    user = normalize_text(u_ans)
    correct_options = [normalize_text(s) for s in re.split(r'[/,;]', str(c_ans_str))]
    return user in correct_options

def check_test_answer(u_ans, q_obj):
    user = normalize_text(u_ans)
    correct = normalize_text(q_obj.get('correct', ''))
    if not user or not correct: return False
    return user == correct

# --- SILNIK AI ---
def get_openai_response(prompt_text, img_obj=None):
    if not API_KEY: raise Exception("Brak klucza API OpenAI.")
    client = OpenAI(api_key=API_KEY)
    messages = [{"role": "system", "content": "You are a professional German teacher. Output ONLY valid JSON. All category names must be in Polish language."}]
    if img_obj:
        buffered = BytesIO()
        img_obj.thumbnail((800, 800)); img_obj.save(buffered, format="JPEG")
        img_b64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
        messages.append({"role": "user", "content": [{"type": "text", "text": prompt_text}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}}]})
    else:
        messages.append({"role": "user", "content": prompt_text})
    response = client.chat.completions.create(model="gpt-4o-mini", messages=messages, response_format={"type": "json_object"})
    return response.choices[0].message.content

# --- LOGOWANIE I SESJA ---
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
                save_j(SESSIONS_FILE, sessions); st.query_params["token"] = tk; st.rerun()
            else: st.error("Błędne dane")
    with t2:
        un = st.text_input("Nowy użytkownik", key="r_u").lower().strip()
        pn = st.text_input("Hasło", type="password", key="r_p")
        if st.button("Załóż konto", use_container_width=True):
            db = load_j(AUTH_FILE, {})
            if not un or len(pn) < 4: st.error("Hasło min. 4 znaki.")
            elif un in db: st.error("Użytkownik istnieje.")
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
        tk = st.query_params["token"]; ss = load_j(SESSIONS_FILE, {})
        if tk in ss: del ss[tk]; save_j(SESSIONS_FILE, ss)
    st.query_params.clear(); st.session_state.clear(); st.rerun()

menu = ["📅 Powtórki", "🚀 Trening", "🕹️ Quiz", "🎴 Fiszki", "📝 Testy", "📸 Skaner AI", "📦 Generator słów", "➕ Dodaj", "📖 Słownik", "📊 Statystyki", "⚙️ Moje Konto"]
if u == ADMIN_USER: menu.append("👑 Admin")
choice = st.sidebar.radio("Nawigacja", menu)

if "l_c" not in st.session_state or st.session_state.l_c != choice:
    for k in ["n_idx", "q_c", "q_s", "f_idx", "f_flipped", "pending", "success_msg", "del_msg", "test_q", "test_idx", "current_review_list", "last_kat"]:
        if k in st.session_state: del st.session_state[k]
    st.session_state.n_m, st.session_state.u_a, st.session_state.l_c = "ask", "", choice

# --- 📅 POWTÓRKI / 🚀 TRENING ---
if choice in ["📅 Powtórki", "🚀 Trening"]:
    is_r = (choice == "📅 Powtórki")
    update_activity("Powtórki" if is_r else "Trening")
    all_cats = sorted(list(set([c.get("category", "Inne") for c in st.session_state.flashcards])))
    sel_kat = st.selectbox("🎯 Kategoria:", ["Wszystkie"] + all_cats)
    
    if "current_review_list" not in st.session_state or st.session_state.get("last_kat") != sel_kat:
        indexed_cards = [(i, c) for i, c in enumerate(st.session_state.flashcards) if sel_kat == "Wszystkie" or c.get("category") == sel_kat]
        if is_r:
            st.session_state.current_review_list = [(i, c) for i, c in indexed_cards if c.get("next_review", str(today_dt)) <= str(today_dt)]
        else:
            st.session_state.current_review_list = indexed_cards
        random.shuffle(st.session_state.current_review_list)
        st.session_state.n_idx = 0; st.session_state.last_kat = sel_kat

    cards_to_show = st.session_state.current_review_list
    if not cards_to_show: st.success("Wszystko opanowane! 🎊")
    else:
        idx_p = st.session_state.n_idx
        if idx_p >= len(cards_to_show): st.success("Koniec sesji!")
        else:
            orig_idx, c = cards_to_show[idx_p]
            st.write(f"Słówek w kolejce: **{len(cards_to_show) - idx_p}**")
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
                first_ex_de = None
                if isinstance(ex_list, list) and len(ex_list) > 0:
                    for ex in ex_list:
                        if isinstance(ex, dict) and 'de' in ex:
                            st.markdown(f"🇩🇪 {ex['de']}<br>🇵🇱 {ex.get('pl','')}", unsafe_allow_html=True)
                            if not first_ex_de: first_ex_de = ex['de']
                play_audio(c['de'], first_ex_de)
                if is_r:
                    st.write("---")
                    col1, col2, col3 = st.columns(3); d = None
                    if col1.button("🔴 Słabo (1d)", use_container_width=True): d = 1
                    if col2.button("🟡 Średnio (3d)", use_container_width=True): d = 3
                    if col3.button("🟢 Dobrze (7d)", use_container_width=True): d = 7
                    if d:
                        st.session_state.flashcards[orig_idx]["next_review"] = str(today_dt + timedelta(days=d))
                        force_save(); st.session_state.n_idx += 1; st.session_state.n_m = "ask"; st.rerun()
                else:
                    if st.button("Dalej ➡️", use_container_width=True):
                        st.session_state.n_idx += 1; st.session_state.n_m = "ask"; st.rerun()

# --- 📝 TESTY ---
elif choice == "📝 Testy":
    update_activity("Testy"); st.header("📝 Egzamin Kontekstowy")
    if len(st.session_state.flashcards) < 5: st.warning("Min. 5 słówek.")
    else:
        if "test_q" not in st.session_state:
            all_cats = sorted(list(set([c.get("category", "Inne") for c in st.session_state.flashcards])))
            sel_kat = st.selectbox("🎯 Zakres:", ["Wszystkie"] + all_cats)
            n_q = st.slider("Liczba pytań", 5, 20, 5)
            if st.button("🚀 GENERUJ TEST", use_container_width=True, type="primary"):
                with st.spinner("AI przygotowuje..."):
                    filtered = [c for c in st.session_state.flashcards if sel_kat == "Wszystkie" or c.get("category") == sel_kat]
                    if len(filtered) < 5: st.error("Zbyt mało słówek.")
                    else:
                        sample = random.sample(filtered, min(n_q, len(filtered)))
                        words_str = ", ".join([f"{w['de']} ({w['pl']})" for w in sample])
                        prompt = f"Generate EXACTLY {len(sample)} questions for: {words_str}. Rotate types: 'LUKA', 'QUIZ', 'TLUMACZENIE'. Output JSON key 'questions'."
                        try:
                            res = get_openai_response(prompt); data = parse_ai_json(res)
                            if data and "questions" in data:
                                st.session_state.test_q, st.session_state.test_idx, st.session_state.test_score = data["questions"][:len(sample)], 0, 0
                                st.session_state.user_data["historical_cost"] += 0.01; st.rerun()
                        except Exception as e: st.error(f"Błąd AI: {e}")
        else:
            qs = st.session_state.test_q; t_idx = st.session_state.test_idx
            if t_idx < len(qs):
                q = qs[t_idx]; st.write(f"### Pytanie {t_idx+1} z {len(qs)}"); st.progress(t_idx / len(qs))
                correct_w = q.get('correct', ''); hint = q.get('hint', 'brak')
                place_h = " ".join(["_"] * len(correct_w)) if correct_w else "_______"
                if q['type'] == "LUKA":
                    st.info(f"Podpowiedź (PL): {hint}"); disp = q['sentence'].replace(correct_w, place_h).replace(correct_w.capitalize(), place_h)
                    st.markdown(f"#### `{disp}`"); u_ans = st.text_input("Wpisz słowo:", key=f"t_{t_idx}")
                elif q['type'] == "QUIZ":
                    st.info(f"Podpowiedź (PL): {hint}"); st.markdown(f"#### `{q['sentence'].replace(correct_w, '_______')}`")
                    opts = q.get('distractors', []) + [correct_w]; random.seed(t_idx); random.shuffle(opts)
                    u_ans = st.radio("Wybierz:", opts, key=f"t_{t_idx}")
                else:
                    st.info("Przetłumacz na niemiecki:"); st.markdown(f"#### {q['sentence']}")
                    u_ans = st.text_input("Twoja odpowiedź:", key=f"t_{t_idx}")
                if st.button("Zatwierdź", use_container_width=True):
                    st.session_state.test_q[t_idx]['user_ans'] = u_ans
                    if check_test_answer(u_ans, q): st.session_state.test_score += 1; st.toast("Dobrze!")
                    else: st.error(f"Źle. Poprawnie: {correct_w}"); time.sleep(1)
                    st.session_state.test_idx += 1; st.rerun()
            else:
                score = st.session_state.test_score; total = len(qs); perc = round((score/total)*100)
                st.session_state.user_data["test_history"].append({"date": datetime.now().strftime("%d.%m %H:%M"), "score": score, "total": total, "perc": perc})
                save_j(get_p(u, "user_data"), st.session_state.user_data); st.balloons()
                st.markdown(f'<div style="text-align:center; padding:30px; border-radius:20px; background:#111; border:2px solid #1E88E5;"><h1>Wynik: {score} / {total}</h1><h2>{perc}%</h2></div>', unsafe_allow_html=True)
                for i, q in enumerate(qs):
                    is_ok = check_test_answer(q.get('user_ans',''), q)
                    icon, col = ("✅", "#2E7D32") if is_ok else ("❌", "#C62828")
                    with st.expander(f"{icon} Pytanie {i+1}"):
                        st.write(f"**Zdanie:** {q['sentence']}")
                        st.markdown(f'<div style="border-left:5px solid {col}; padding-left:10px;">Twoja: {q.get("user_ans","")}<br>Poprawna: {q.get("correct","")}</div>', unsafe_allow_html=True)
                if st.button("Powrót", use_container_width=True): del st.session_state.test_q; st.rerun()

# --- 🕹️ QUIZ / 🎴 FISZKI ---
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
            c = st.session_state.q_c
            if is_correct(st.session_state.get("u_q"), st.session_state.q_a):
                st.success("✅ Brawo!"); orig_idx = st.session_state.q_idx
                if st.session_state.flashcards[orig_idx].get("next_review", str(today_dt)) <= str(today_dt):
                    st.session_state.flashcards[orig_idx]["next_review"] = str(today_dt + timedelta(days=1)); force_save()
            else: st.error(f"❌ Błąd. Poprawnie: {st.session_state.q_a}")
            ex_de = c.get('examples', [{}])[0].get('de') if c.get('examples') else None
            play_audio(c['de'], ex_de)
            if st.button("Dalej", use_container_width=True): del st.session_state.q_c; st.rerun()

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
            ex_de = c.get('examples', [{}])[0].get('de') if c.get('examples') else None
            play_audio(c['de'], ex_de)

# --- 📸 SKANER AI ---
elif choice == "📸 Skaner AI":
    update_activity("Skaner")
    src = st.camera_input("Zrób zdjęcie"); up = st.file_uploader("Lub wybierz plik")
    if (src or up) and st.button("🚀 ANALIZUJ", use_container_width=True):
        try:
            with st.spinner("Przetwarzanie obrazu..."):
                img = Image.open(src or up).convert("RGB")
                req = "Extract German vocabulary. Categories MUST be in Polish. Format: flashcards: [{de, pl, category, examples: [{de, pl}]}]"
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
            force_save(); del st.session_state.pending; st.rerun()

# --- 📦 GENERATOR SŁÓW ---
elif choice == "📦 Generator słów":
    update_activity("Generator")
    if "success_msg" in st.session_state: st.success(st.session_state.success_msg); del st.session_state.success_msg
    cols = st.columns(5); lvls = ["A1", "A2", "B1", "B2", "C1"]
    for i, lvl in enumerate(lvls):
        if cols[i].button(lvl, key=lvl, use_container_width=True):
            with st.spinner(f"Przygotowuję 25 słówek {lvl}..."):
                try:
                    my_w = [x['de'].lower() for x in st.session_state.flashcards]
                    all_available = [w for w in VOCAB_DB.get(lvl, []) if w.lower() not in my_w]
                    if len(all_available) < 5:
                        prompt = f"Generate EXACTLY 25 German words {lvl} NOT in: {my_w[:50]}. Category names MUST be in Polish language. JSON key 'flashcards'."
                    else:
                        selection = random.sample(all_available, min(25, len(all_available)))
                        prompt = f"Translate THESE words to PL: {selection}. Use Polish category names. JSON: flashcards: [{{de, pl, category, examples:[{{de,pl}}]}}]"
                    res = get_openai_response(prompt); data = parse_ai_json(res)
                    if isinstance(data, dict) and "flashcards" in data:
                        added = 0
                        for w in data["flashcards"]:
                            t_de, t_pl = w.get('de') or w.get('word'), w.get('pl') or w.get('translation')
                            if t_de and t_pl and t_de.lower() not in [x['de'].lower() for x in st.session_state.flashcards]:
                                w.update({"de": t_de, "pl": t_pl, "next_review": str(today_dt), "date_added": str(today_dt), "category": f"{lvl} - {w.get('category','Inne')}"})
                                st.session_state.flashcards.append(w); added += 1
                        st.session_state.user_data["historical_cost"] += 0.01; force_save(); st.session_state.success_msg = f"🎉 Dodano {added} słówek!"; st.rerun()
                except Exception as e: st.error(f"Błąd: {e}")

# --- ➕ DODAJ / 📖 SŁOWNIK ---
elif choice == "➕ Dodaj":
    st.header("➕ Dodaj słówko"); update_activity("Dodaj")
    with st.form("man_f"):
        de, pl, kat = st.text_input("Niemiecki"), st.text_input("Polski"), st.text_input("Kategoria")
        if st.form_submit_button("Zapisz"):
            if de and pl:
                st.session_state.flashcards.append({"de":de, "pl":pl, "category":kat or "Inne", "next_review":str(today_dt), "date_added":str(today_dt), "examples":[]}); force_save(); st.success("Dodano!")

elif choice == "📖 Słownik":
    update_activity("Słownik"); cats = sorted(list(set([c.get("category", "Inne") for c in st.session_state.flashcards])))
    f_kat = st.selectbox("Filtruj:", ["Wszystkie"] + cats); search = st.text_input("Szukaj:")
    for i, c in enumerate(st.session_state.flashcards):
        if (f_kat == "Wszystkie" or c.get("category") == f_kat) and (search.lower() in c['de'].lower() or search.lower() in c['pl'].lower()):
            with st.expander(f"📝 {c['de']} — {c['pl']}"):
                with st.form(f"ed_{i}"):
                    n_de, n_pl, n_ka = st.text_input("DE", c['de']), st.text_input("PL", c['pl']), st.text_input("KAT", c.get('category','Inne'))
                    c1, c2 = st.columns(2)
                    if c1.form_submit_button("Zapisz", use_container_width=True):
                        st.session_state.flashcards[i].update({"de":n_de, "pl":n_pl, "category":n_ka}); force_save(); st.rerun()
                    if c2.form_submit_button("Usuń", use_container_width=True):
                        del st.session_state.flashcards[i]; force_save(); st.rerun()

# --- 📊 STATYSTYKI (Przywrócone Tabele i Wykresy) ---
elif choice == "📊 Statystyki":
    update_activity("Statystyki"); df = pd.DataFrame(st.session_state.flashcards)
    st.header("📊 Twoje Statystyki")
    if df.empty: st.warning("Baza słówek jest pusta.")
    else:
        c1, c2, c3 = st.columns(3); c1.metric("Słówek", len(df)); c2.metric("Passa", f"{st.session_state.user_data['streak']} d"); c3.metric("Opanowane", len(df[df['next_review'].apply(is_word_mastered)]))
        
        # PRZYWRÓCONY PODZIAŁ NA POZIOMY
        st.subheader("🎯 Podział na poziomy")
        stats_rows = []
        for lvl in ["A1", "A2", "B1", "B2", "C1"]:
            l_df = df[df['category'].str.contains(lvl, na=False)]
            total = len(l_df)
            know = len(l_df[l_df['next_review'].apply(is_word_mastered)]) if total > 0 else 0
            perc = round((know/total)*100) if total > 0 else 0
            stats_rows.append({"Poziom": lvl, "Słówek": total, "Opanowane": know, "Wiedza %": f"{perc}%"})
        st.table(pd.DataFrame(stats_rows))

        # PRZYWRÓCONE NADCHODZĄCE POWTÓRKI
        st.subheader("📅 Nadchodzące powtórki")
        sched = []
        for i in range(10):
            d_target = str(today_dt + timedelta(days=i))
            count = len(df[df['next_review'] == d_target])
            sched.append({"Data": (today_dt + timedelta(days=i)).strftime("%d.%m"), "Słów": count})
        st.bar_chart(pd.DataFrame(sched).set_index("Data"))
        
        st.subheader("📜 Historia Twoich Testów")
        h = st.session_state.user_data.get("test_history", [])
        if h: st.table(pd.DataFrame(h[::-1]).head(10)[["date", "score", "total", "perc"]])
        else: st.info("Brak historii testów.")

# --- 👑 ADMIN ---
elif choice == "👑 Admin":
    st.header("👑 Panel Admina"); users_db = load_j(AUTH_FILE, {}); adm_list = []; global_time = {m: 0.0 for m in MODULE_ORDER}
    m1, m2 = st.columns(2); t_words, t_ai_cost = 0, 0.0
    for usr in users_db:
        ud, ub = load_j(get_p(usr, "user_data"), {}), load_j(get_p(usr, "flashcards"), [])
        u_cost = ud.get("historical_cost", 0.0); t_words += len(ub); t_ai_cost += u_cost
        mastery = "0%"
        if ub:
            op = len([x for x in ub if is_word_mastered(x.get('next_review'))]); mastery = f"{round((op/len(ub))*100)}%"
        t_s = ud.get("time_stats", {})
        for m in MODULE_ORDER: global_time[m] += t_s.get(m, 0.0)
        u_times = ", ".join([f"{m[0]}:{round(s/60)}m" for m, s in t_s.items() if s > 15])
        adm_list.append({"Użytkownik":usr, "Słów":len(ub), "Testy":len(ud.get("test_history", [])), "%":mastery, "Koszt (PLN)": round(u_cost, 2), "Ostatnio":ud.get("last_seen","Nigdy"), "Czas":u_times or "Brak"})
    m1.metric("Łącznie słówek", t_words); m2.metric("Suma kosztów AI", f"{t_ai_cost:.2f} PLN"); st.table(pd.DataFrame(adm_list))
    if sum(global_time.values()) > 0:
        v = [global_time[m] for m in MODULE_ORDER]; l = [f"{m}: {round(v/60,1)}m" for m, v in zip(MODULE_ORDER, v)]
        fig = go.Figure(data=[go.Bar(x=MODULE_ORDER, y=v, text=l, textposition='auto', marker_color='#1E88E5')])
        fig.update_layout(template="plotly_dark", height=400); st.plotly_chart(fig, use_container_width=True)

# --- ⚙️ MOJE KONTO ---
elif choice == "⚙️ Moje Konto":
    st.header("⚙️ Moje Konto"); update_activity("Konto")
    with st.expander("🔑 Zmień hasło"):
        with st.form("pw_f"):
            o, n, cp = st.text_input("Stare", type="password"), st.text_input("Nowe", type="password"), st.text_input("Powtórz", type="password")
            if st.form_submit_button("Zmień"):
                db = load_j(AUTH_FILE, {})
                if db.get(u) == hash_pw(o) and n == cp: db[u] = hash_pw(n); save_j(AUTH_FILE, db); st.success("OK!")
    st.divider(); st.subheader("⚠️ Usuwanie danych"); conf = st.checkbox("Potwierdzam usuwanie")
    lvls = ["A1", "A2", "B1", "B2", "C1"]; col_d = st.columns(5)
    for i, lvl in enumerate(lvls):
        if col_d[i].button(f"Usuń {lvl}", disabled=not conf, use_container_width=True):
            st.session_state.flashcards = [x for x in st.session_state.flashcards if lvl not in str(x.get('category',''))]
            force_save(); st.success("Usunięto!"); st.rerun()
    if st.button("RESET CAŁEJ BAZY", type="primary", disabled=not conf, use_container_width=True):
        save_j(get_p(u, "flashcards"), []); st.session_state.flashcards = []; st.rerun()
