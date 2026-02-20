import os
import re
import time
from datetime import datetime
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
    "https://www.france-galop.com/fr/entraineur/Z1FxYXQ3cFJyM0ZlUitJQTlmUTNiUT09#partants",
    "https://www.france-galop.com/fr/entraineur/U0VNb0JtQlZ1bUphYndFTnJjSzg4dz09#partants"
]

FG_PASSWORD = os.getenv("FG_PASSWORD")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")
EMAIL_SENDER = os.getenv("EMAIL_SENDER")
EMAIL_DEST = os.getenv("EMAIL_DEST")

def clean_text(text):
    if not text: return ""
    # Garde A-Z, 0-9, /, :, . et espaces
    cleaned = re.sub(r'[^a-zA-Z0-9/:\. ]', '', text)
    return " ".join(cleaned.split())

def send_email(content):
    date_str = datetime.now().strftime("%d/%m/%Y")
    msg = MIMEMultipart()
    msg['From'] = EMAIL_SENDER
    msg['To'] = EMAIL_DEST
    msg['Subject'] = f"Partants du jour - {date_str}"
    
    body = f"Bonjour,\n\nVoici les chevaux détectés pour aujourd'hui ({date_str}) :\n\n{content}"
    msg.attach(MIMEText(body, 'plain'))

    try:
        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            server.login(EMAIL_SENDER, GMAIL_APP_PASSWORD)
            server.send_message(msg)
        print("✅ Rapport envoyé par email.")
    except Exception as e:
        print(f"❌ Erreur envoi email : {e}")

def run_scraper():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    wait = WebDriverWait(driver, 20)
    today = datetime.now().strftime("%d/%m/%Y")
    results = []

    try:
        # 1. AUTHENTIFICATION
        print(f"🔑 Connexion via {URL_LOGIN}...")
        driver.get(URL_LOGIN)
        
        # Gestion des cookies (crucial pour débloquer la vue)
        try:
            time.sleep(2)
            cookie_btn = wait.until(EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler")))
            cookie_btn.click()
            print("🍪 Cookies acceptés.")
        except:
            print("ℹ️ Pas de bannière cookies.")

        # Saisie des identifiants
        wait.until(EC.presence_of_element_located((By.NAME, "name"))).send_keys(EMAIL_SENDER)
        driver.find_element(By.NAME, "pass").send_keys(FG_PASSWORD)
        
        # Clic sur le bouton de connexion (via JS pour plus de fiabilité)
        submit_btn = driver.find_element(By.ID, "edit-submit")
        driver.execute_script("arguments[0].click();", submit_btn)
        
        # On attend que la session soit établie (on vérifie la présence du bouton de déconnexion par ex)
        time.sleep(5)
        print("✅ Authentification réussie.")

        # 2. SCRAPING DES PAGES
        for url in URLS_ENTRAINEURS:
            print(f"🧐 Analyse : {url}")
            driver.get(url)
            time.sleep(6) # Attente du chargement du tableau dynamique

            # On cherche les lignes du tableau qui contiennent la date du jour
            # XPATH : Cherche un <tr> qui contient le texte de la date d'aujourd'hui
            rows = driver.find_elements(By.XPATH, f"//tr[contains(., '{today}')]")

            if not rows:
                print(f"   - Aucun partant trouvé pour cet entraîneur.")
                continue

            for row in rows:
                cells = row.find_elements(By.TAG_NAME, "td")
                if len(cells) >= 5:
                    # Extraction des colonnes
                    hippodrome = clean_text(cells[1].text)
                    heure = clean_text(cells[2].text)
                    course = clean_text(cells[3].text)
                    # Souvent le N° et le Nom sont dans la même cellule
                    cheval_info = clean_text(cells[4].text)
                    
                    line = f"{today} / {hippodrome} / {heure} / {course} / {cheval_info}"
                    results.append(line)
                    print(f"   📍 Trouvé : {line}")

        # 3. FINALISATION
        if results:
            send_email("\n".join(results))
        else:
            print("🏁 Aucun cheval ne court aujourd'hui. Fin du script.")

    except Exception as e:
        print(f"💥 Erreur lors du scraping : {e}")
        driver.save_screenshot("debug_error.png") # Capture d'écran pour voir le blocage
    finally:
        driver.quit()

if __name__ == "__main__":
    run_scraper()
