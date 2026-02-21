import os
import re
import time
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# --- CONFIGURATION ---
URL_LOGIN = "https://www.france-galop.com/fr/login"
URLS_ENTRAINEURS = [
    "https://www.france-galop.com/fr/entraineur/Z1FxYXQ3cFJyM0ZlUitJQTlmUTNiUT09#dernieres-courses",
    "https://www.france-galop.com/fr/entraineur/U0VNb0JtQlZ1bUphYndFTnJjSzg4dz09#dernieres-courses"
]

# Variables d'environnement
FG_PASSWORD = os.getenv("FG_PASSWORD")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")
EMAIL_SENDER = os.getenv("EMAIL_SENDER")
EMAIL_DEST = os.getenv("EMAIL_DEST", "votre.email@gmail.com") 

def clean_text(text):
    if not text: return "N/A"
    return " ".join(text.split()).strip()

def parse_date(date_str):
    """Convertit une chaîne DD/MM/YYYY en objet datetime."""
    try:
        return datetime.strptime(date_str.strip(), "%d/%m/%Y")
    except:
        return None

def run_scraper_history():
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    wait = WebDriverWait(driver, 15)
    
    # Fenêtre de 7 jours
    today = datetime.now()
    start_date = today - timedelta(days=7)
    
    final_report = []

    try:
        # --- CONNEXION ---
        driver.get(URL_LOGIN)
        try:
            # Acceptation des cookies si présents
            cookie_btn = wait.until(EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler")))
            cookie_btn.click()
        except: pass

        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[name='name']"))).send_keys(EMAIL_SENDER)
        driver.find_element(By.CSS_SELECTOR, "input[name='pass']").send_keys(FG_PASSWORD)
        driver.find_element(By.CSS_SELECTOR, "#user-login-form button[type='submit']").click()
        time.sleep(3)

        # --- ANALYSE DES ENTRAINEURS ---
        for trainer_url in URLS_ENTRAINEURS:
            print(f"Analyse de l'entraîneur : {trainer_url}")
            driver.get(trainer_url)
            
            # Attente du chargement du tableau spécifique
            try:
                wait.until(EC.presence_of_element_located((By.ID, "dernieres-courses")))
                trainer_name = driver.find_element(By.CSS_SELECTOR, "h1.page-header").text.strip()
            except:
                trainer_name = "Inconnu"

            # Sélection des lignes du tableau "Dernières courses"
            # On cible précisément le tbody de la section concernée
            rows = driver.find_elements(By.CSS_SELECTOR, "#dernieres-courses table tbody tr")

            for row in rows:
                cells = row.find_elements(By.TAG_NAME, "td")
                if len(cells) < 12: continue # Sécurité sur la structure
                
                # Correction des index basée sur le code source
                raw_date = cells[0].text.strip()       # Index 0: Date
                place = cells[1].text.strip()          # Index 1: Place
                horse_name = clean_text(cells[2].text) # Index 2: Cheval
                hippodrome = clean_text(cells[8].text) # Index 8: Hippodrome
                prize = clean_text(cells[11].text)     # Index 11: Gain

                # Filtrage Temporel
                race_dt = parse_date(raw_date)
                if race_dt and start_date <= race_dt <= today:
                    
                    # Filtrage Place (1er à 4e)
                    # re.search capture le chiffre, ignorant les mentions comme "AR" ou "T"
                    match_place = re.search(r'^([1-4])$', place)
                    
                    if match_place:
                        rank = match_place.group(1)
                        line = f"[{trainer_name}] {horse_name} - {raw_date} - {hippodrome} - {rank}e - {prize}€"
                        final_report.append(line)
                        print(f"  ✅ Retenu : {horse_name} ({rank}e)")

        # --- ENVOI DE L'EMAIL ---
        if final_report:
            send_final_email("\n".join(final_report))
            print(f"\n📧 Email envoyé avec {len(final_report)} performance(s).")
        else:
            print("\nℹ️ Aucune performance de top 4 trouvée sur les 7 derniers jours.")

    except Exception as e:
        print(f"💥 Erreur globale : {e}")
    finally:
        driver.quit()

def send_final_email(content):
    msg = MIMEMultipart()
    msg['From'] = EMAIL_SENDER
    #msg['To'] = EMAIL_DEST
    msg['To'] = "stephane.evain@gmail.com"
    msg['Subject'] = f"Top Performances 7j - France Galop ({datetime.now().strftime('%d/%m/%Y')})"
    
    body = f"Voici les chevaux classés dans les 4 premiers sur les 7 derniers jours :\n\n{content}"
    msg.attach(MIMEText(body, 'plain'))
    
    try:
        with smtplib.SMTP('smtp.gmail.com', 587) as s:
            s.starttls()
            s.login(EMAIL_SENDER, GMAIL_APP_PASSWORD)
            s.send_message(msg)
    except Exception as e:
        print(f"❌ Erreur email : {e}")

if __name__ == "__main__":
    run_scraper_history()
