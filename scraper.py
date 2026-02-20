import os
import re
import time
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# --- CONFIGURATION ---
URLS = [
    "https://www.france-galop.com/fr/entraineur/Z1FxYXQ3cFJyM0ZlUitJQTlmUTNiUT09#partants",
    "https://www.france-galop.com/fr/entraineur/U0VNb0JtQlZ1bUphYndFTnJjSzg4dz09#partants"
]
EMAIL_DEST = os.getenv("EMAIL_DEST")
EMAIL_SENDER = os.getenv("EMAIL_SENDER")
# Ces variables seront lues depuis les secrets GitHub
FG_PASSWORD = os.getenv("FG_PASSWORD")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD") 

def clean_text(text):
    if not text: return ""
    # Garde A-Z, 0-9, /, :, . et espaces
    cleaned = re.sub(r'[^a-zA-Z0-9/:\. ]', '', text)
    return " ".join(cleaned.split())

def send_email(content):
    msg = MIMEMultipart()
    date_str = datetime.now().strftime("%d/%m/%Y")
    msg['From'] = EMAIL_SENDER
    msg['To'] = EMAIL_DEST
    msg['Subject'] = f"Partants du jour - {date_str}"
    
    body = f"Bonjour,\n\nVoici les partants pour aujourd'hui ({date_str}) :\n\n" + content
    msg.attach(MIMEText(body, 'plain'))
    
    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(EMAIL_SENDER, GMAIL_APP_PASSWORD)
        server.send_message(msg)
        server.quit()
        print("Email envoyé avec succès.")
    except Exception as e:
        print(f"Erreur envoi email: {e}")

def scrape():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    driver = webdriver.Chrome(options=options)
    
    results = []
    today = datetime.now().strftime("%d/%m/%Y")
    
    try:
        # 1. Connexion (sur la page d'accueil ou login)
        driver.get("https://www.france-galop.com/fr/user/login")
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "edit-name"))).send_keys(EMAIL_SENDER)
        driver.find_element(By.ID, "edit-pass").send_keys(FG_PASSWORD)
        driver.find_element(By.ID, "edit-submit").click()
        time.sleep(3) # Attente redirection
        
        for url in URLS:
            driver.get(url)
            time.sleep(5) # Laisser le temps au JS de charger l'onglet partants
            
            # Cibler les lignes du tableau des partants
            # Note: Le sélecteur dépend de la structure exacte de France Galop
            rows = driver.find_elements(By.CSS_SELECTOR, "tr.even, tr.odd") 
            
            for row in rows:
                row_text = row.text
                if today in row_text:
                    # Extraction simplifiée des cellules (à ajuster selon le DOM réel)
                    cells = row.find_elements(By.TAG_NAME, "td")
                    if len(cells) >= 5:
                        date = today
                        hippodrome = clean_text(cells[1].text)
                        heure = clean_text(cells[2].text)
                        course = clean_text(cells[3].text)
                        cheval = clean_text(cells[4].text) # Contient souvent N° + Nom
                        
                        line = f"{date} / {hippodrome} / {heure} / {course} / {cheval}"
                        results.append(line)
        
        if results:
            send_email("\n".join(results))
        else:
            print("Aucun cheval ne court aujourd'hui. Status: Done.")
            
    finally:
        driver.quit()

if __name__ == "__main__":
    scrape()
