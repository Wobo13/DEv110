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

# --- 1. KONFIGURACJA (Pobieranie z Secrets) ---
SUPABASE_URL = st.secrets.get("SUPABASE_URL", "")
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY", "")
API_KEY = st.secrets.get("OPENAI_API_KEY", "")

# --- KONFIGURACJA APKI ---
APP_VERSION = "V201 (Full Reconstruction - SQL Fix)"
ADMIN_USER = "wobo"
BONUS_START = 1089.0

# MAPOWANIE NAZW DLA STATYSTYK (Ujednolicenie)
CLEAN_TIME_LABELS = {
    "Powtórki": "Pow", "Nauka": "Pow", "Pow": "Pow", "Nau": "Pow",
    "Trening": "Trn", "Trn": "Trn",
    "Quiz": "Qiz", "Qiz": "Qiz",
    "Fiszki": "Fis", "Fis": "Fis",
    "Testy": "Tst", "Tst": "Tst",
    "Skaner": "Skn", "Skaner AI": "Skn",
    "Generator": "Gen", "Generator słów": "Gen",
    "Dodaj": "Dod", "➕ Dodaj": "Dod",
    "Słownik": "Słn", "📖 Słownik": "Słn",
    "Konto": "Inn", "Moje Konto": "Inn", "Inne": "Inn", "Inn": "Inn"
}

MODULE_ORDER = ["Powtórki", "Trening", "Quiz", "Fiszki", "Testy", "Skaner", "Generator", "Dodaj", "Słownik"]

# --- 2. POTĘŻNA WEWNĘTRZNA BAZA SŁÓWEK (1250 SŁÓW) ---
VOCAB_DB = {
    "A1": ["Apfel", "Brot", "Haus", "Auto", "Schule", "Lehrer", "Wasser", "Milch", "Tisch", "Stuhl", "Buch", "Stift", "Kind", "Mutter", "Vater", "Freund", "Stadt", "Land", "Weg", "Zeit", "Essen", "Trinken", "Schlafen", "Lernen", "Arbeiten", "Gehen", "Kommen", "Hören", "Sehen", "Sprechen", "Groß", "Klein", "Gut", "Schlecht", "Schön", "Hässlich", "Alt", "Jung", "Neu", "Kalt", "Heute", "Morgen", "Gestern", "Woche", "Jahr", "Tag", "Nacht", "Name", "Zahl", "Geld", "Hund", "Katze", "Baum", "Blume", "Sonne", "Mond", "Regen", "Schnee", "Wind", "Bett", "Zimmer", "Küche", "Bad", "Fenster", "Tür", "Schlüssel", "Tasche", "Gabel", "Löffel", "Messer", "Teller", "Tasse", "Glas", "Saft", "Kaffee", "Tee", "Zucker", "Salz", "Fleisch", "Fisch", "Gemüse", "Obst", "Banane", "Ei", "Käse", "Reis", "Nudeln", "Kuchen", "Zeitung", "Radio", "Handy", "Fahrrad", "Zug", "Bus", "Bahnhof", "Flughafen", "Hotel", "Arzt", "Krankenhaus", "Apotheke", "Arbeit", "Pause", "Ferien", "Urlaub", "Meer", "Berg", "Wald", "Straße", "Platz", "Garten", "Park", "Schrank", "Sofa", "Lampe", "Bild", "Uhr", "Kleidung", "Hose", "Hemd", "Rock", "Kleid", "Schuh", "Jacke", "Mantel", "Hut", "Brille", "Kopf", "Hand", "Fuß", "Bein", "Arm", "Auge", "Ohr", "Nase", "Mund", "Haar", "Herz", "Frühstück", "Mittagessen", "Abendessen", "Kochen", "Backen", "Waschen", "Putzen", "Kaufen", "Verkaufen", "Bezahlen", "Rechnen", "Schreiben", "Lesen", "Singen", "Tanzen", "Spielen", "Laufen", "Schwimmen", "Reisen", "Besuchen", "Fragen", "Antworten", "Wissen", "Denken", "Glauben", "Hoffen", "Lieben", "Hassen", "Lachen", "Weinen", "Warten", "Suchen", "Finden", "Helfen", "Geben", "Nehmen", "Bringen", "Zeigen", "Sagen", "Erzählen", "Erklären", "Verstehen", "Vergessen", "Wichtig", "Richtig", "Falsch", "Einfach", "Schwer", "Leicht", "Heiß", "Warm", "Trocken", "Nass", "Hell", "Dunkel", "Laut", "Leise", "Schnell", "Langsam", "Müde", "Krank", "Gesund", "Glücklich", "Traurig", "Sauer", "Süß", "Bitter", "Teuer", "Billig", "Reich", "Arm", "Sauber", "Schmutzig", "Voll", "Leer", "Offen", "Geschlossen", "Erster", "Letzter", "Nächster", "Hier", "Dort", "Überall", "Nirgendwo", "Immer", "Oft", "Manchmal", "Selten", "Nie", "Vielleicht", "Sicher", "Gerne", "Zusammen", "Allein", "Wenig", "Viel", "Genug", "Echt", "Wirklich", "Wieder", "Noch", "Schon", "Erst", "Dann", "Danach", "Zuerst", "Schließlich", "Aber", "Oder", "Und", "Sondern", "Denn", "Weil"],
    "A2": ["Urlaub", "Reise", "Bahnhof", "Flugzeug", "Hotel", "Küche", "Kühlschrank", "Gabel", "Löffel", "Messer", "Kleidung", "Hose", "Hemd", "Schuh", "Wetter", "Regen", "Sonne", "Wolke", "Gesundheit", "Krankheit", "Arzt", "Medizin", "Körper", "Kopf", "Hand", "Fuß", "Sport", "Spiel", "Musik", "Film", "Besuchen", "Verstehen", "Vergessen", "Bestellen", "Bezahlen", "Wohnen", "Mieten", "Kaufen", "Verkaufen", "Feiern", "Wichtig", "Wahr", "Falsch", "Fertig", "Glücklich", "Traurig", "Müde", "Sauer", "Süß", "Heiß", "Abwaschen", "Anrufen", "Anziehen", "Aufräumen", "Ausgeben", "Aussehen", "Baden", "Bedeuten", "Beeilen", "Benutzen", "Berichten", "Beschreiben", "Besichtigen", "Bestimmen", "Besprechen", "Bewerben", "Bezahlen", "Buchen", "Buchstabieren", "Danken", "Dauern", "Diskutieren", "Drucken", "Duschen", "Einkaufen", "Einladen", "Einziehen", "Enden", "Entschuldigen", "Erinnern", "Erkennen", "Erlauben", "Erleben", "Erzählen", "Fehlen", "Feiern", "Fernsehen", "Frühstücken", "Fühlen", "Füttern", "Gehören", "Gewinnen", "Glauben", "Grillen", "Grüßen", "Heiraten", "Hoffen", "Holen", "Interessieren", "Kämmen", "Kennenlernen", "Klettern", "Klingeln", "Klopf", "Kochen", "Korrigieren", "Kosten", "Lächeln", "Laden", "Landem", "Laufen", "Leiden", "Leihen", "Leiten", "Lernen", "Liefern", "Lösen", "Lügen", "Machen", "Malen", "Meinen", "Merken", "Mieten", "Mitbringen", "Mitkommen", "Mitmachen", "Mitteilen", "Nachsehen", "Nennen", "Notieren", "Öffnen", "Organisieren", "Packen", "Parken", "Passieren", "Planen", "Probieren", "Prüfen", "Putzen", "Rauchen", "Regnen", "Reisen", "Renovieren", "Reparieren", "Reservieren", "Riechen", "Rufen", "Sammeln", "Schalten", "Schenken", "Schicken", "Schmecken", "Schminken", "Schneiden", "Schneien", "Schreiben", "Schwimmen", "Segeln", "Sehen", "Senden", "Setzen", "Singen", "Sitzen", "Sparen", "Spazieren", "Speichern", "Spielen", "Sprechen", "Springen", "Spülen", "Starten", "Stecken", "Stehen", "Stehlen", "Steigen", "Stellen", "Sterben", "Stimmen", "Stören", "Studieren", "Suchen", "Surfen", "Tanken", "Tanzen", "Tauschen", "Teilen", "Teilnehmen", "Telefonieren", "Tragen", "Träumen", "Treffen", "Trennen", "Trinken", "Trocknen", "Tun", "Überweisen", "Üben", "Übernachten", "Übersetzen", "Überweisen", "Umziehen", "Unterhalten", "Unterschreiben", "Untersuch", "Verabreden", "Verabschieden", "Verändern", "Verbessern", "Verbieten", "Verdienen", "Vergleichen", "Vergrößern", "Verkaufen", "Verlängern", "Verlassen", "Verlieren", "Vermieten", "Vermuten", "Verpassen", "Verreisen", "Verschieben", "Versprechen", "Verstehen", "Versuchen", "Verteilen", "Vertrauen", "Verursachen", "Verwenden", "Verzeihen", "Vorbereiten", "Vorstellen", "Wählen", "Wandern", "Warten", "Waschen", "Wechseln", "Wecken", "Wehtun", "Weitergehen", "Werden", "Werfen", "Wiederholen", "Wissen", "Wohnen", "Wünschen", "Zahlen", "Zeichnen", "Zeigen", "Zuhören", "Zumachen"],
    "B1": ["Erfahrung", "Erfolg", "Entscheidung", "Meinung", "Gefühl", "Beziehung", "Zukunft", "Vergangenheit", "Umwelt", "Natur", "Gesellschaft", "Politik", "Wirtschaft", "Wissenschaft", "Technik", "Beruf", "Ausbildung", "Studium", "Gehalt", "Vertrag", "Vorbereiten", "Organisieren", "Diskutieren", "Argumentieren", "Erklären", "Empfehlen", "Vorschlagen", "Warnen", "Hoffen", "Träumen", "Gefährlich", "Sicher", "Möglich", "Unmöglich", "Nötig", "Nützlich", "Schwierig", "Leicht", "Interessant", "Langweilig", "Obwohl", "Trotzdem", "Deshalb", "Deswegen", "Falls", "Damit", "Stattdessen", "Zuerst", "Schließlich", "Besonders", "Abhängig", "Ablehnen", "Abmachen", "Abnehmen", "Abonnieren", "Absagen", "Abschließen", "Absolvieren", "Abstimmen", "Abwarten", "Achten", "Ändern", "Anerkennen", "Anfangen", "Anfordern", "Angeben", "Angehören", "Angreifen", "Anhalten", "Anklagen", "Ankommen", "Ankündigen", "Anmelden", "Annehmen", "Anpassen", "Anrufen", "Anschließen", "Ansehen", "Ansprechen", "Anstrengen", "Antworten", "Anwenden", "Anzeigen", "Anziehen", "Arbeiten", "Ärgern", "Aufbauen", "Aufgeben", "Aufhalten", "Aufhören", "Aufklären", "Aufmerksam", "Aufaufnahme", "Aufräumen", "Aufregen", "Aufstehen", "Aufutreten", "Aufwachen", "Ausbilden", "Ausdehnen", "Ausdrücken", "Auseinander", "Ausfallen", "Ausfüllen", "Ausgeben", "Ausgehen", "Ausgleichen", "Aushalten", "Auskennen", "Auskommen", "Auslachen", "Ausleihen", "Ausmachen", "Ausnutzen", "Auspacken", "Ausprobieren", "Ausruhen", "Ausscheiden", "Ausschließen", "Aussehen", "Aussprechen", "Ausstellen", "Aussuchen", "Austauschen", "Austreten", "Ausüben", "Auswandern", "Auswählen", "Ausweisen", "Auswirken", "Ausziehen", "Backen", "Bauen", "Beachten", "Beantragen", "Beantworten", "Bebauen", "Bedanken", "Bedeuten", "Bedienen", "Bedingung", "Beeinflussen", "Beenden", "Befinden", "Befolgen", "Befreien", "Begegnen", "Begeistern", "Beginnen", "Begleiten", "Begrenzen", "Begründen", "Begrüßen", "Behalten", "Behandeln", "Behaupten", "Behindern", "Beibringen", "Beifügen", "Beilegen", "Beitragen", "Bekannt", "Bekommen", "Belegen", "Beleidigen", "Belohnen", "Bemühen", "Benutzen", "Benötigen", "Beraten", "Berechnen", "Bereiten", "Berichten", "Berücksichtigen", "Beruhigen", "Berühmt", "Beschädigen", "Beschäftigen", "Bescheiden", "Bescheinen", "Beschleunigen", "Beschließen", "Beschreiben", "Beschweren", "Besichtigen", "Besitzen", "Besonderer", "Besprechen", "Bestätigen", "Bestehen", "Bestellen", "Bestimmen", "Bestrafen", "Besuchen", "Beteiligen", "Betrachten", "Betreuen", "Betrügen", "Betteln", "Bevor", "Bevorzugen", "Bewahren", "Bewegen", "Beweisen", "Bewerben", "Bewerten", "Bewohner", "Bezahlen", "Bezeichnen", "Beziehen", "Beziehung", "Bezirk", "Bezug", "Bieten", "Bilden", "Bildung", "Billigen", "Binden", "Bitten", "Blasen", "Bleiben", "Blick", "Blind", "Blitz", "Bloß", "Blühen", "Blume", "Blut", "Boden", "Bogen", "Bohren", "Boot", "Bord", "Böse", "Braten", "Brauchen", "Brauen", "Brechen", "Breit", "Brennen", "Bringen", "Bruch", "Brücke", "Bruder", "Brust", "Bube", "Buch", "Buchen", "Bühne", "Bund"],
    "B2": ["Herausforderung", "Verantwortung", "Voraussetzung", "Zusammenhang", "Unterschied", "Vergleich", "Entwicklung", "Fortschritt", "Ursache", "Wirkung", "Eindruck", "Einfluss", "Ergebnis", "Erwartung", "Gerechtigkeit", "Freiheit", "Sicherheit", "Vertrauen", "Geduld", "Vorsicht", "Beeinflussen", "Verbessern", "Verschlechtern", "Erreichen", "Vermeiden", "Lösen", "Teilnehmen", "Unterstützen", "Fördern", "Fordern", "Effizient", "Effektiv", "Kreativ", "Kritisch", "Logisch", "Objektiv", "Subjektiv", "Typisch", "Zufällig", "Regelmäßig", "Anscheinend", "Vermutlich", "Eventuell", "Tatsächlich", "Grundsätzlich", "Eigentlich", "Überall", "Nirgendwo", "Irgendwie", "Sowieso", "Abweichen", "Aneignen", "Anfordern", "Anordnen", "Anschaffen", "Anstellen", "Antreffen", "Appellieren", "Auffassen", "Aufgreifen", "Aufheben", "Aufwenden", "Ausarbeiten", "Ausdehnen", "Ausführen", "Auslösen", "Ausnutzen", "Ausstatten", "Ausüben", "Bedenken", "Begehen", "Begreifen", "Beharren", "Beifügen", "Beitragen", "Bekämpfen", "Belasten", "Belegen", "Bemängeln", "Bemessen", "Benachrichtigen", "Benachteiligen", "Beruhen", "Beschaffen", "Beseitigen", "Bestand", "Bestreiten", "Beteiligen", "Betreffen", "Beurteilen", "Bevorzugen", "Bewältigen", "Bewirken", "Beziehen", "Bezweifeln", "Bilanz", "Bündeln", "Darlegen", "Dazugehören", "Definieren", "Dementieren", "Differenzieren", "Diskriminieren", "Dokumentieren", "Durchdringen", "Durchführen", "Durchsetzen", "Eignen", "Einbeziehen", "Einführen", "Eingliedern", "Eingreifen", "Einhalten", "Einleiten", "Einreichen", "Einschränken", "Einsetzen", "Einstellen", "Einwenden", "Einwilligen", "Empfangen", "Empfehlen", "Entfalten", "Entgegennehmen", "Entlasten", "Entnehmen", "Entscheiden", "Entschärfen", "Entsprechen", "Entstehen", "Entwickeln", "Entwerfen", "Entziehen", "Erachten", "Erarbeiten", "Erfahren", "Erfassen", "Erfordern", "Erfüllen", "Ergänzen", "Ergreifen", "Erheben", "Erkennen", "Erlangen", "Erläutern", "Erledigen", "Erleichtern", "Ermöglichen", "Erneuern", "Ernennen", "Erörtern", "Erproben", "Erreichen", "Errichten", "Erscheinen", "Erschließen", "Ersetzen", "Erstatten", "Erstellen", "Erteilen", "Ertragen", "Erwarten", "Erweisen", "Erweitern", "Erwerben", "Erzielen", "Fahrlässig", "Festlegen", "Feststellen", "Filtern", "Finanzieren", "Fließen", "Folgen", "Forderung", "Förderung", "Formulieren", "Fortsetzen", "Führen", "Fügen", "Fungieren", "Garantieren", "Gedeihen", "Gefährden", "Gegenüberstellen", "Gehorchen", "Gehören", "Gelangen", "Gelten", "Genügen", "Geraten", "Gewährleisten", "Gewähren", "Gewichten", "Gewinnen", "Glauben", "Gleichen", "Gliedern", "Gönnen", "Greifen", "Grenzen", "Gründen", "Handeln", "Handhaben", "Hängen", "Häufen", "Heben", "Heften", "Heilen", "Hemmen", "Herangehen", "Herleiten", "Hervorgehen", "Hervorrufen", "Hinweisen", "Hinzufügen", "Hören", "Identifizieren", "Ignorieren", "Illustrieren", "Implementieren", "Importieren", "Indizieren", "Informieren", "Integrieren", "Interessieren", "Interpretieren", "Investieren", "Irren", "Isolieren", "Justieren", "Kalkulieren", "Kämpfen", "Kategorisieren", "Kaufen", "Kehren", "Kennzeichnen", "Klären", "Klassifizieren", "Kleben", "Klingen", "Kombinieren", "Kommen", "Kommentieren", "Kommunizieren", "Kompensieren", "Kompensieren", "Konfrontieren", "Konkretisieren", "Konkurrieren", "Konstatieren"],
    "C1": ["Auseinandersetzung", "Auswirkung", "Bedeutung", "Erkenntnis", "Fähigkeit", "Maßnahme", "Notwendigkeit", "Perspektive", "Struktur", "Vielfalt", "Anforderung", "Bewältigung", "Darstellung", "Einschätzung", "Gewährleistung", "Hintergrund", "Integration", "Kompetenz", "Nachhaltigkeit", "Umsetzung", "Analysieren", "Berücksichtigen", "Differenzieren", "Evaluieren", "Gewährleisten", "Hinterfragen", "Implementieren", "Konkretisieren", "Reflektieren", "Veranschaulichen", "Außergewöhnlich", "Beträchtlich", "Eindeutig", "Erheblich", "Gravierend", "Kontrovers", "Nachhaltig", "Präzise", "Umfangreich", "Wesentliche", "Dementsprechend", "Demnach", "Infolgedessen", "Inwiefern", "Inwieweit", "Jegliche", "Lediglich", "Nichtsdestotrotz", "Stufenweise", "Zunehmend", "Abstrahieren", "Akquirieren", "Akzentuieren", "Antizipieren", "Artikulieren", "Assoziieren", "Attestieren", "Autarkie", "Autorisieren", "Bagatellisieren", "Bilateral", "Charakterisieren", "Chiffrieren", "Chronologisch", "Defizit", "Degradieren", "Deklarieren", "Delegieren", "Demokratisierung", "Demonstrieren", "Denunziieren", "Deplatzieren", "Deponieren", "Derivat", "Desillusionieren", "Destabilisieren", "Detailgenau", "Determinieren", "Diagnostizieren", "Diametral", "Diffamieren", "Differenzierung", "Diffus", "Diktieren", "Dilemma", "Dimensionieren", "Diskreditieren", "Diskrepanz", "Diskretion", "Diskurs", "Dislozieren", "Disponieren", "Disproportion", "Disput", "Dissonanz", "Distanzieren", "Distinktion", "Divergieren", "Diversifikation", "Diversität", "Dogmatisch", "Dominanz", "Dominieren", "Dramatisieren", "Dualismus", "Duplizieren", "Effektivität", "Effizienz", "Egalisieren", "Egomanie", "Eklatant", "Ekstatisch", "Elaborieren", "Elementar", "Eliminieren", "Elite", "Eloquent", "Emanzipieren", "Empathie", "Empirisch", "Emulgieren", "Enthusiasmus", "Entität", "Episodisch", "Equitabel", "Erodieren", "Erkenntnistheorie", "Eskalieren", "Etablieren", "Ethik", "Etymologie", "Euphemismus", "Euphorisch", "Evakuieren", "Evaluiert", "Evident", "Evolutionär", "Exazerbieren", "Exekutieren", "Exemplarisch", "Exemplifizieren", "Existenziell", "Exorbitant", "Exotisch", "Expandieren", "Expedieren", "Experimentell", "Explizit", "Explizieren", "Explodieren", "Exponieren", "Exposition", "Expressiv", "Exquisit", "Extrahieren", "Extraordinär", "Extrapolieren", "Extravagant", "Extremismus", "Exzentrisch", "Exzessiv", "Facettenreich", "Faktisch", "Fakultativ", "Fatalismus", "Feudalismus", "Fiktional", "Filigran", "Fluktuieren", "Fokussieren", "Formell", "Fragmentieren", "Fraktion", "Frivol", "Fundamental", "Fundiert", "Funktionalität", "Garant", "Generieren", "Globalisierung", "Glosse", "Gönnerhaft", "Gradualismus", "Gratifikation", "Gravitieren", "Grosso", "Habitus", "Haptisch", "Harmonisieren", "Hegemonie", "Heterogen", "Heuristisch", "Hierarchie", "Holistisch", "Homogenisieren", "Humanismus", "Hypothese", "Hysterisch", "Idealismus", "Identifikation", "Ideologie", "Idyllisch", "Ignoranz", "Illegalität", "Illusionär", "Illustrativ", "Imaginär", "Immanent", "Immerwährend", "Immobiliar", "Immunisieren", "Impartiell", "Impasse", "Imperativ", "Imperialismus", "Implikation", "Implizit", "Implodieren", "Imponieren", "Imposant", "Impulsiv", "Inadäquat", "Inaugurieren", "Indifferenz", "Individuierung", "Indoktrinieren", "Induktiv", "Industriell", "Ineffizient", "Inexistent", "Infaust", "Inferiorität", "Inflationär", "Inflexibel", "Informationell", "Infrastruktur", "Inhärent", "Inhibition", "Initiieren", "Inklusion", "Inkompatibel", "Inkompetenz", "Inkongruenz", "Inkonsistent", "Inkorporieren", "Inkrementell", "Inkubation", "Innovation", "Inoffiziell", "Inquisitorisch"]
}

# --- 3. SYSTEM POMOCNICZY (POLACZENIE Z BAZA) ---
def get_db():
    if not SUPABASE_URL or not SUPABASE_KEY:
        st.error("Błąd konfiguracji Supabase. Sprawdź Secrets!")
        st.stop()
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    return SyncPostgrestClient(f"{SUPABASE_URL}/rest/v1", headers=headers)

def hash_pw(pw): return hashlib.sha256(str.encode(pw)).hexdigest()

def normalize_text(t):
    if not t: return ""
    t = str(t).lower().strip().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    return re.sub(r'[?.!,;]', '', t)

# --- 4. SILNIK AI (NAPRAWIONY) ---
def get_openai_response(prompt_text, img_obj=None):
    if not API_KEY: raise Exception("Brak klucza OpenAI API.")
    client = OpenAI(api_key=API_KEY)
    # Wzmocnienie prośby o polskie kategorie w system prompt
    messages = [{"role": "system", "content": "You are a professional German teacher. Output ONLY valid JSON. All category names MUST be in Polish language. Descriptive thematic categories (e.g. 'Owoce', 'Biuro') are required. Format examples as list of {de, pl}."}]
    if img_obj:
        buffered = BytesIO(); img_obj.thumbnail((800, 800)); img_obj.save(buffered, format="JPEG")
        img_b64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
        messages.append({"role": "user", "content": [{"type": "text", "text": prompt_text}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}}]})
    else:
        messages.append({"role": "user", "content": prompt_text})
    response = client.chat.completions.create(model="gpt-4o-mini", messages=messages, response_format={"type": "json_object"})
    return response.choices[0].message.content

def parse_ai_json(text):
    try: return json.loads(text)
    except: return None

# --- 5. FUNKCJE DANYCH (SUPABASE) ---
def load_user_data(username):
    db = get_db()
    res = db.table("user_data").select("*").eq("username", username).execute()
    if res.data: return res.data[0]
    init = {"username": username, "streak":0, "historical_cost":0.0, "time_stats":{}, "last_ts":time.time(), "last_seen":"Nigdy", "test_history": []}
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
    # Migracja pola origin i upewnienie się że to lista
    for c in cards:
        if not c.get("origin"):
            cat = str(c.get("category", "")).lower()
            c["origin"] = "Generator" if "gen" in cat else ("Skaner" if "skan" in cat else "Dodaj")
    return cards

def save_word(username, word_obj):
    db = get_db()
    word_obj["username"] = username
    if "examples" not in word_obj: word_obj["examples"] = []
    # Zapewnienie nazwy kolumny category (zamiast kategoria)
    if "kategoria" in word_obj:
        word_obj["category"] = word_obj.pop("kategoria")
    db.table("flashcards").insert(word_obj).execute()

def delete_word(word_id):
    get_db().table("flashcards").delete().eq("id", word_id).execute()

def update_word(word_id, update_fields):
    get_db().table("flashcards").update(update_fields).eq("id", word_id).execute()

# --- 6. AUDIO ---
def play_audio(txt, example_txt=None):
    try:
        from gtts import gTTS
        full = f"{txt}. . . . {example_txt}" if example_txt else txt
        f = BytesIO(); tts = gTTS(text=full, lang='de'); tts.write_to_fp(f); f.seek(0)
        st.audio(f, format="audio/mp3", autoplay=True)
    except: pass

def check_test_answer(u_ans, q_obj):
    u = normalize_text(u_ans); c = normalize_text(q_obj.get('correct', ''))
    return u == c if u and c else False

# --- 7. LOGOWANIE ---
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

# --- 8. SESJA ---
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

# --- 9. UI SIDEBAR ---
st.sidebar.title(f"👤 {u.capitalize()}")
st.sidebar.caption(f"Wersja: {APP_VERSION}")
st.sidebar.info(f"🔥 Passa: **{st.session_state.user_data.get('streak', 0)} dni**")
if st.sidebar.button("Wyloguj", use_container_width=True):
    st.query_params.clear(); st.session_state.clear(); st.rerun()

menu = ["📅 Powtórki", "🚀 Trening", "🕹️ Quiz", "🎴 Fiszki", "📝 Testy", "📸 Skaner AI", "📦 Generator słów", "➕ Dodaj", "📖 Słownik", "📊 Statystyki", "⚙️ Moje Konto"]
if u == ADMIN_USER: menu.append("👑 Admin")
choice = st.sidebar.radio("Nawigacja", menu)

if "l_c" not in st.session_state or st.session_state.l_c != choice:
    for k in ["test_q", "test_idx", "test_score", "cur_review_list", "n_idx", "q_c", "q_s", "f_idx", "f_flipped", "pending"]:
        if k in st.session_state: del st.session_state[k]
    st.session_state.l_c, st.session_state.n_m, st.session_state.u_a = choice, "ask", ""

# --- 10. MODUŁY NAUKI ---
if choice in ["📅 Powtórki", "🚀 Trening"]:
    is_r = (choice == "📅 Powtórki")
    update_activity("Powtórki")
    all_cats = sorted(list(set([str(c.get("category", "Inne")) for c in st.session_state.flashcards])))
    sel_kat = st.selectbox("🎯 Kategoria:", ["Wszystkie"] + all_cats)
    if "cur_review_list" not in st.session_state:
        pool = [c for c in st.session_state.flashcards if sel_kat == "Wszystkie" or str(c.get("category")) == sel_kat]
        if is_r: pool = [c for c in pool if str(c.get("next_review", str(today_dt))) <= str(today_dt)]
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
                with st.form("ans_f"):
                    u_in = st.text_input("Tłumaczenie (PL):")
                    if st.form_submit_button("Sprawdź", use_container_width=True):
                        st.session_state.u_a, st.session_state.n_m = u_in, "res"; st.rerun()
            else:
                if normalize_text(st.session_state.u_a) == normalize_text(c['pl']): st.success(f"✅ Dobrze: {c['pl']}")
                else: st.error(f"❌ Poprawnie: {c['pl']}")
                exs = c.get("examples", [])
                fex = exs[0].get("de") if exs and isinstance(exs, list) and len(exs) > 0 else None
                if isinstance(exs, list):
                    for ex in exs:
                        if isinstance(ex, dict) and 'de' in ex:
                            st.markdown(f"🇩🇪 {ex['de']}<br>🇵🇱 {ex.get('pl','')}", unsafe_allow_html=True)
                play_audio(c['de'], fex)
                if is_r:
                    c1, c2, c3 = st.columns(3); d = None
                    if c1.button("🔴 Słabo (1d)"): d = 1
                    if c2.button("🟡 Średnio (3d)"): d = 3
                    if c3.button("🟢 Dobrze (7d)"): d = 7
                    if d:
                        update_word(c['id'], {"next_review": str(today_dt + timedelta(days=d))})
                        st.session_state.n_idx += 1; st.session_state.n_m = "ask"; st.rerun()
                elif st.button("Dalej ➡️"):
                    st.session_state.n_idx += 1; st.session_state.n_m = "ask"; st.rerun()

elif choice == "🕹️ Quiz":
    update_activity("Quiz"); all_c = st.session_state.flashcards
    if len(all_c) < 4: st.warning("Dodaj min. 4 słówka!")
    else:
        if "q_c" not in st.session_state:
            idx = random.randrange(len(all_c)); t = all_c[idx]
            opts = random.sample([x['pl'] for x in all_c if x['pl']!=t['pl']], min(3, len(all_c)-1)) + [t['pl']]; random.shuffle(opts)
            st.session_state.update({"q_idx":idx, "q_c":t, "q_a":t['pl'], "q_o":opts, "q_s":"ask"})
        st.write(f"### Jak przetłumaczysz: **{st.session_state.q_c['de']}**")
        if st.session_state.q_s == "ask":
            for o in st.session_state.q_o:
                if st.button(o, key=o, use_container_width=True): st.session_state.u_q, st.session_state.q_s = o, "res"; st.rerun()
        else:
            c = st.session_state.q_c
            if normalize_text(st.session_state.get("u_q")) == normalize_text(st.session_state.q_a): st.success("✅ Brawo!")
            else: st.error(f"❌ Błąd. Poprawnie: {st.session_state.q_a}")
            exs = c.get('examples', [])
            fex = exs[0].get('de') if exs and isinstance(exs, list) and len(exs)>0 else None
            play_audio(c['de'], fex)
            if st.button("Dalej"): del st.session_state.q_c; st.rerun()

elif choice == "🎴 Fiszki":
    update_activity("Fiszki")
    cards = st.session_state.flashcards
    if cards:
        if "f_idx" not in st.session_state: st.session_state.f_idx = 0
        if "f_flipped" not in st.session_state: st.session_state.f_flipped = False
        c = cards[st.session_state.f_idx % len(cards)]
        txt = c["pl"] if st.session_state.f_flipped else c["de"]
        st.markdown(f'<div style="min-height:300px; display:flex; align-items:center; justify-content:center; background:black; border:2px solid red; border-radius:20px; color:white; font-size:2em; text-align:center; padding:20px;">{txt}</div>', unsafe_allow_html=True)
        c1, c2, c3 = st.columns(3)
        if c1.button("⬅️"): st.session_state.f_idx -= 1; st.session_state.f_flipped = False; st.rerun()
        if c2.button("🔄 OBRÓĆ"): st.session_state.f_flipped = not st.session_state.f_flipped; st.rerun()
        if c3.button("➡️"): st.session_state.f_idx += 1; st.session_state.f_flipped = False; st.rerun()
        if st.session_state.f_flipped:
            exs = c.get('examples', [])
            fex = exs[0].get('de') if exs and isinstance(exs, list) and len(exs)>0 else None
            play_audio(c['de'], fex)

# --- 11. GENERATOR (W PEŁNI NAPRAWIONY) ---
elif choice == "📦 Generator słów":
    update_activity("Generator"); lvls = ["A1", "A2", "B1", "B2", "C1"]; cols = st.columns(5)
    if "gen_msg" in st.session_state: st.success(st.session_state.gen_msg); del st.session_state.gen_msg
    for i, lvl in enumerate(lvls):
        if cols[i].button(lvl, use_container_width=True):
            with st.spinner(f"Generuję 25 słówek {lvl}..."):
                try:
                    my_w = [x['de'].lower() for x in st.session_state.flashcards]
                    available = [w for w in VOCAB_DB[lvl] if w.lower() not in my_w]
                    # Losowanie 25 słów
                    sel = random.sample(available, min(25, len(available)))
                    prompt = f"Przetłumacz te słowa na polski: {sel}. Podaj polskie kategorie i po 1 zdaniu przykładowym dla każdego. JSON key 'flashcards' jako lista obiektów."
                    res_raw = get_openai_response(prompt)
                    data = parse_ai_json(res_raw)
                    if data and "flashcards" in data:
                        added = 0
                        for w in data["flashcards"]:
                            # Zapewnienie mapowania kolumn SQL
                            cat_raw = w.get('category') or w.get('kategoria') or "Inne"
                            save_word(u, {
                                "de": w.get('de'), 
                                "pl": w.get('pl'), 
                                "category": f"{lvl}-{cat_raw}",
                                "next_review": str(today_dt), 
                                "origin": "Generator",
                                "examples": w.get('examples', [])
                            })
                            added += 1
                        st.session_state.user_data["historical_cost"] += 0.01
                        st.session_state.gen_msg = f"Dodano {added} słówek {lvl}!"
                        st.rerun()
                except Exception as e: st.error(f"Błąd generatora: {e}")

elif choice == "📝 Testy":
    update_activity("Testy")
    if len(st.session_state.flashcards) < 5: st.warning("Min. 5 słówek.")
    else:
        if "test_q" not in st.session_state:
            n_q = st.slider("Pytania", 5, 20, 5)
            if st.button("🚀 GENERUJ TEST", type="primary"):
                with st.spinner("AI przygotowuje..."):
                    sample = random.sample(st.session_state.flashcards, n_q)
                    words = ", ".join([f"{w['de']} ({w['pl']})" for w in sample])
                    prompt = f"Generuj test dla: {words}. Podaj 'hint' (PL context), 'sentence' (DE), 'correct' (DE). For QUIZ provide 3 'distractors'. JSON 'questions'."
                    try:
                        res = get_openai_response(prompt); data = parse_ai_json(res)
                        if data and "questions" in data:
                            st.session_state.test_q, st.session_state.test_idx, st.session_state.test_score = data["questions"], 0, 0
                            st.session_state.user_data["historical_cost"] += 0.01; st.rerun()
                    except: st.error("Błąd AI.")
        else:
            qs = st.session_state.test_q; t_idx = st.session_state.test_idx
            if t_idx < len(qs):
                q = qs[t_idx]; correct = str(q.get('correct',''))
                st.info(f"💡 Wskazówka: {q.get('hint','brak')}")
                sentence = q.get('sentence') or q.get('question','')
                ans = None
                if q.get('type') == "QUIZ":
                    st.markdown(f"#### {sentence.replace(correct, '_______')}")
                    opts = list(set(q.get('distractors', []) + [correct])); random.shuffle(opts)
                    cols = st.columns(2)
                    for i, o in enumerate(opts):
                        if cols[i%2].button(o, key=f"t_{t_idx}_{i}"): ans = o
                else:
                    st.markdown(f"#### {sentence.replace(correct, '_______')}")
                    ui = st.text_input("Twoja odpowiedź (DE):", key=f"ti_{t_idx}")
                    if st.button("OK"): ans = ui
                if ans:
                    st.session_state.test_q[t_idx]['user_ans'] = ans
                    if normalize_text(ans) == normalize_text(correct): st.session_state.test_score += 1; st.toast("Dobrze!")
                    else: st.error(f"Źle. Poprawnie: {correct}"); time.sleep(1)
                    st.session_state.test_idx += 1; st.rerun()
            else:
                score, total = st.session_state.test_score, len(qs)
                perc = round((score/total)*100) if total > 0 else 0
                st.session_state.user_data["test_history"].append({"date": datetime.now().strftime("%d.%m"), "score": score, "total": total, "perc": perc})
                save_user_data(u, st.session_state.user_data); st.success(f"Wynik: {score}/{total} ({perc}%)")
                if st.button("Koniec"): del st.session_state.test_q; st.rerun()

elif choice == "📸 Skaner AI":
    update_activity("Skaner"); src = st.camera_input("Zdjęcie"); up = st.file_uploader("Lub plik")
    if (src or up) and st.button("🚀 ANALIZUJ", use_container_width=True):
        try:
            with st.spinner("Analiza obrazu..."):
                res = get_openai_response("Extract German vocabulary. Format JSON key 'flashcards'.", Image.open(src or up))
                data = parse_ai_json(res)
                if "flashcards" in data: st.session_state.pending = data["flashcards"]; st.session_state.user_data["historical_cost"] += 0.02; st.rerun()
        except Exception as e: st.error(f"Błąd AI: {e}")
    if "pending" in st.session_state:
        ed = st.data_editor(pd.DataFrame(st.session_state.pending), use_container_width=True)
        if st.button("✅ ZAPISZ"):
            for w in ed.to_dict('records'):
                if 'de' in w and 'pl' in w: save_word(u, {"de":w['de'], "pl":w['pl'], "category":w.get('category','Skaner'), "next_review":str(today_dt), "origin":"Skaner"})
            del st.session_state.pending; st.success("Dodano!"); st.rerun()

elif choice == "➕ Dodaj":
    st.header("Dodaj słówko")
    with st.form("man_f"):
        de, pl, kat = st.text_input("Niemiecki"), st.text_input("Polski"), st.text_input("Kategoria")
        if st.form_submit_button("Zapisz"):
            if de and pl: save_word(u, {"de":de, "pl":pl, "category":kat or "Inne", "next_review":str(today_dt), "origin":"Dodaj"}); st.success("OK!"); st.rerun()

elif choice == "📖 Słownik":
    update_activity("Słownik"); search = st.text_input("Szukaj:")
    for c in st.session_state.flashcards:
        if search.lower() in str(c.get('de','')).lower():
            with st.expander(f"📝 {c['de']} - {c['pl']}"):
                if st.button("Usuń", key=f"del_{c['id']}"): delete_word(c['id']); st.rerun()

# --- 12. STATYSTYKI & ADMIN (PRZYWRÓCONE) ---
elif choice == "📊 Statystyki":
    update_activity("Inn"); df = pd.DataFrame(st.session_state.flashcards)
    st.header("📊 Twoje Statystyki")
    if not df.empty:
        c1, c2, c3 = st.columns(3); c1.metric("Słówek", len(df)); c2.metric("Passa", f"{st.session_state.user_data['streak']} d")
        kn = len(df[df['next_review'].apply(lambda x: (date.fromisoformat(x)-date.today()).days >= 7 if x else False)])
        c3.metric("Opanowane", kn)
        st.subheader("Podział na poziomy")
        stats = []
        for l in ["A1", "A2", "B1", "B2", "C1"]:
            l_df = df[df['category'].str.contains(l, na=False)]
            total = len(l_df); know = len(l_df[l_df['next_review'].apply(lambda x: (date.fromisoformat(x)-date.today()).days >= 7 if x else False)]) if total > 0 else 0
            stats.append({"Poziom":l, "Słów":total, "Opanowane":know, "%":f"{round((know/total)*100) if total > 0 else 0}%"})
        st.table(pd.DataFrame(stats))
        st.subheader("Nadchodzące powtórki")
        sched = [{"Data": (today_dt + timedelta(days=i)).strftime("%d.%m"), "Słów": len(df[df['next_review'] == str(today_dt + timedelta(days=i))])} for i in range(10)]
        st.bar_chart(pd.DataFrame(sched).set_index("Data"))
        st.subheader("📜 Historia Testów")
        st.table(pd.DataFrame(st.session_state.user_data.get("test_history", [])[::-1]).head(10))

elif choice == "👑 Admin":
    st.header("👑 Panel Admina"); st.link_button("💸 OpenAI Billing", "https://platform.openai.com/usage")
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
    st.columns(2)[1].metric("Suma kosztów AI", f"{total_cost:.2f} PLN"); st.table(pd.DataFrame(adm_list))
    if global_time:
        fig = go.Figure(data=[go.Bar(x=list(global_time.keys()), y=list(global_time.values()), marker_color='#1E88E5')])
        fig.update_layout(template="plotly_dark", height=400, title="Globalny czas (minuty)"); st.plotly_chart(fig, use_container_width=True)

elif choice == "⚙️ Moje Konto":
    st.header("⚙️ Moje Konto"); update_activity("Inn")
    with st.expander("🔑 Zmień hasło"):
        with st.form("pw_f"):
            o, n, cp = st.text_input("Stare", type="password"), st.text_input("Nowe", type="password"), st.text_input("Powtórz", type="password")
            if st.form_submit_button("Zmień"):
                db = get_db(); res = db.table("users_auth").select("*").eq("username", u).execute()
                if res.data and res.data[0]["password_hash"] == hash_pw(o) and n == cp:
                    db.table("users_auth").update({"password_hash": hash_pw(n)}).eq("username", u).execute(); st.success("OK!")
    st.divider(); st.subheader("🗑️ Usuwanie danych")
    conf = st.checkbox("Potwierdzam chęć usunięcia danych")
    lvls = ["A1", "A2", "B1", "B2", "C1"]
    col_d = st.columns(5)
    for i, lvl in enumerate(lvls):
        if col_d[i].button(lvl, key=f"del_{lvl}", disabled=not conf):
            get_db().table("flashcards").delete().eq("username", u).ilike("category", f"%{lvl}%").execute()
            st.success(f"Usunięto {lvl}!"); st.rerun()
    if st.button("RESET CAŁEJ MOJEJ BAZY", type="primary", disabled=not conf):
        get_db().table("flashcards").delete().eq("username", u).execute(); st.rerun()
