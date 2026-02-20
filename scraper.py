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
    "https://www.france-galop.com/fr/entraineur/Z1FxYXQ3cFJyM0ZlUitJQTlmUTNiUT09#partants",
    "https://www.france-galop.com/fr/entraineur/U0VNb0JtQlZ1bUphYndFTnJjSzg4dz09#partants"
]

FG_PASSWORD = os.getenv("FG_PASSWORD")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")
EMAIL_SENDER = os.getenv("EMAIL_SENDER")
EMAIL_DEST = os.getenv("EMAIL_DEST")

def clean_text(text):
    if not text: return ""
    cleaned = re.sub(r'[^a-zA-Z0-9/:\. ]', '', text)
    return " ".join(cleaned.split())

def run_scraper():
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36")
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    wait = WebDriverWait(driver, 25)
    
    # Dates
    today = datetime.now().strftime("%d/%m/%Y")
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%d/%m/%Y")
    
    today_results = []
    tomorrow_logs = []

    try:
        # 1. CONNEXION
        print(f"🚀 Accès à {URL_LOGIN}...")
        driver.get(URL_LOGIN)
        time.sleep(4)

        try:
            cookie_btn = driver.find_element(By.ID, "onetrust-accept-btn-handler")
            cookie_btn.click()
            print("🍪 Cookies acceptés.")
        except:
            pass

        print("✍️ Saisie des identifiants...")
        wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "input[name='name']"))).send_keys(EMAIL_SENDER)
        driver.find_element(By.CSS_SELECTOR, "input[name='pass']").send_keys(FG_PASSWORD)
        
        login_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "#user-login-form button[type='submit'], #edit-submit--2")))
        driver.execute_script("arguments[0].click();", login_button)
        
        time.sleep(7)
        print(f"🔗 Connecté. URL : {driver.current_url}")

        # 2. ANALYSE DES PAGES
        for url in URLS_ENTRAINEURS:
            print(f"🧐 Analyse de l'entraîneur : {url}")
            driver.get(url)
            time.sleep(8)

            # --- VÉRIFICATION POUR AUJOURD'HUI ---
            rows_today = driver.find_elements(By.XPATH, f"//tr[contains(., '{today}')]")
            for row in rows_today:
                cells = row.find_elements(By.TAG_NAME, "td")
                if len(cells) >= 5:
                    line = f"{today} / {clean_text(cells[1].text)} / {clean_text(cells[2].text)} / {clean_text(cells[3].text)} / {clean_text(cells[4].text)}"
                    today_results.append(line)
            
            # --- VÉRIFICATION POUR DEMAIN (LOGS UNIQUEMENT) ---
            rows_tomorrow = driver.find_elements(By.XPATH, f"//tr[contains(., '{tomorrow}')]")
            for row in rows_tomorrow:
                cells = row.find_elements(By.TAG_NAME, "td")
                if len(cells) >= 5:
                    line = f"{tomorrow} / {clean_text(cells[1].text)} / {clean_text(cells[2].text)} / {clean_text(cells[3].text)} / {clean_text(cells[4].text)}"
                    tomorrow_logs.append(line)

        # 3. AFFICHAGE DES LOGS POUR DEMAIN
        print("\n--- 📝 LOGS PARTANTS DEMAIN ---")
        if tomorrow_logs:
            for log in tomorrow_logs:
                print(f"[DEMAIN] {log}")
        else:
            print(f"Aucun partant détecté pour demain ({tomorrow}).")
        print("-------------------------------\n")

        # 4. ACTION E-MAIL (AUJOURD'HUI UNIQUEMENT)
        if today_results:
            print(f"📧 Envoi de l'email pour aujourd'hui ({len(today_results)} partants)...")
            send_final_email("\n".join(today_results))
        else:
            print("🏁 Aucun partant pour aujourd'hui.")

    except Exception as e:
        print(f"💥 Erreur : {e}")
    finally:
        driver.quit()

def send_final_email(content):
    msg = MIMEMultipart()
    msg['From'] = EMAIL_SENDER
    msg['To'] = EMAIL_DEST
    msg['Subject'] = f"Partants France Galop - {datetime.now().strftime('%d/%m/%Y')}"
    msg.attach(MIMEText(content, 'plain'))
    try:
        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            server.login(EMAIL_SENDER, GMAIL_APP_PASSWORD)
            server.send_message(msg)
        print("✅ Email envoyé.")
    except Exception as e:
        print(f"❌ Erreur email : {e}")

if __name__ == "__main__":
    run_scraper()
