import os
import re
import time
import requests
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# --- CONFIGURATION (Scraping conservé / Notification mise à jour) ---
URL_LOGIN = "https://www.france-galop.com/fr/login"
URLS_ENTRAINEURS = [
    "https://www.france-galop.com/fr/entraineur/Z1FxYXQ3cFJyM0ZlUitJQTlmUTNiUT09#dernieres-courses",
    "https://www.france-galop.com/fr/entraineur/U0VNb0JtQlZ1bUphYndFTnJjSzg4dz09#dernieres-courses"
]

# Variables d'environnement
FG_PASSWORD = os.getenv("FG_PASSWORD")
EMAIL_SENDER = os.getenv("EMAIL_SENDER") # Utilisé pour le login
GREEN_API_URL = os.getenv("GREEN_API_URL")

def clean_text(text):
    if not text: return "N/A"
    return " ".join(text.split()).strip()

def parse_date(date_str):
    """Convertit une chaîne DD/MM/YYYY en objet datetime."""
    try:
        return datetime.strptime(date_str.strip(), "%d/%m/%Y")
    except:
        return None

def send_whatsapp_notification(content):
    """Envoie le message via Green-API"""
    if not GREEN_API_URL:
        print("❌ Erreur : GREEN_API_URL non configurée.")
        return

    payload = {
        "chatId": "33678723278-1540128478@g.us",
        "message": content
    }
    headers = {"Content-Type": "application/json"}

    try:
        response = requests.post(GREEN_API_URL, json=payload, headers=headers, timeout=15)
        print(f"📲 Statut WhatsApp : {response.status_code}")
    except Exception as e:
        print(f"❌ Échec envoi WhatsApp : {e}")

def run_scraper_history():
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
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
        # --- CONNEXION (Identique PJ) ---
        driver.get(URL_LOGIN)
        try:
            cookie_btn = wait.until(EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler")))
            cookie_btn.click()
        except: pass

        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[name='name']"))).send_keys(EMAIL_SENDER)
        driver.find_element(By.CSS_SELECTOR, "input[name='pass']").send_keys(FG_PASSWORD)
        driver.find_element(By.CSS_SELECTOR, "#user-login-form button[type='submit']").click()
        time.sleep(3)

        # --- ANALYSE DES ENTRAINEURS (Identique PJ) ---
        for trainer_url in URLS_ENTRAINEURS:
            print(f"Analyse de l'entraîneur : {trainer_url}")
            driver.get(trainer_url)
            
            try:
                wait.until(EC.presence_of_element_located((By.ID, "dernieres-courses")))
                trainer_name = driver.find_element(By.CSS_SELECTOR, "h1.page-header").text.replace("ENTRAINEUR", "").strip()
            except:
                trainer_name = "Inconnu"

            rows = driver.find_elements(By.CSS_SELECTOR, "#dernieres-courses table tbody tr")

            for row in rows:
                cells = row.find_elements(By.TAG_NAME, "td")
                if len(cells) < 12: continue 
                
                raw_date = cells[0].text.strip()       
                place = cells[1].text.strip()          
                horse_name = clean_text(cells[2].text) 
                hippodrome = clean_text(cells[8].text) 
                prize = clean_text(cells[11].text)     

                race_dt = parse_date(raw_date)
                if race_dt and start_date <= race_dt <= today:
                    # Filtrage Place (1er à 4e)
                    match_place = re.search(r'^([1-4])$', place)
                    
                    if match_place:
                        rank = match_place.group(1)
                        # Formatage pour WhatsApp
                        line = f"🏆 *{horse_name}* ({rank}e)\n📅 {raw_date} | 📍 {hippodrome}\n💰 Gain : {prize}€\n👤 Entr: {trainer_name}"
                        final_report.append(line)
                        print(f"  ✅ Retenu : {horse_name} ({rank}e)")

        # --- ENVOI WHATSAPP ---
        if final_report:
            header = f"💰 *TOP PERFORMANCES (7 derniers jours)*\n\n"
            full_message = header + "\n\n---\n\n".join(final_report)
            send_whatsapp_notification(full_message)
            print(f"\n📲 Notification WhatsApp envoyée ({len(final_report)} performances).")
        else:
            print("\nℹ️ Aucune performance de top 4 trouvée.")

    except Exception as e:
        print(f"💥 Erreur globale : {e}")
    finally:
        driver.quit()

if __name__ == "__main__":
    run_scraper_history()
