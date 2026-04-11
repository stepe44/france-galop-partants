import os
import re
import time
import requests
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
# Importation des outils pour la simulation "Blindée"
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# --- CONFIGURATION ---
URL_HOME = "https://www.france-galop.com/fr"
URLS_ENTRAINEURS = [
    "https://www.france-galop.com/fr/entraineur/Z1FxYXQ3cFJyM0ZlUitJQTlmUTNiUT09#dernieres-courses",
    "https://www.france-galop.com/fr/entraineur/U0VNb0JtQlZ1bUphYndFTnJjSzg4dz09#dernieres-courses"
]

FG_PASSWORD = os.getenv("FG_PASSWORD")
EMAIL_SENDER = os.getenv("EMAIL_SENDER")
GREEN_API_URL = os.getenv("GREEN_API_URL")

def log(message):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")

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
        log("❌ Erreur : GREEN_API_URL non configurée.")
        return
    payload = {"chatId": "33678723278-1540128478@g.us", "message": content}
    try:
        response = requests.post(GREEN_API_URL, json=payload, timeout=15)
        log(f"📲 Statut WhatsApp : {response.status_code}")
    except Exception as e:
        log(f"❌ Échec envoi WhatsApp : {e}")

def run_scraper_history():
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36")
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    wait = WebDriverWait(driver, 30)
    
    # Fenêtre de 7 jours
    today = datetime.now()
    start_date = today - timedelta(days=7)
    final_report = []

    try:
        log("🌐 Accès à France Galop...")
        driver.get(URL_HOME)
        
        try:
            wait.until(EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler"))).click()
        except: pass

        log("🔑 Ouverture du portail...")
        login_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "a[href*='login'], .user-link, .login")))
        driver.execute_script("arguments[0].click();", login_btn)

        # --- ÉTAPE 1 : EMAIL (VERSION BLINDÉE) ---
        log("📧 Tentative de saisie de l'identifiant...")
        email_field = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='email'], input#email, #email")))
        
        actions = ActionChains(driver)
        actions.move_to_element(email_field).click().perform()
        time.sleep(1)
        
        email_field.send_keys(Keys.CONTROL + "a")
        email_field.send_keys(Keys.DELETE)
        actions.send_keys(EMAIL_SENDER).perform()
        
        # Force JS + DispatchEvent
        driver.execute_script(f"arguments[0].value = '{EMAIL_SENDER}';", email_field)
        driver.execute_script("arguments[0].dispatchEvent(new Event('input', { bubbles: True }));", email_field)
        driver.execute_script("arguments[0].dispatchEvent(new Event('change', { bubbles: True }));", email_field)

        driver.save_screenshot("debug_gain_1_email.png")
        
        btn_next = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button#next, #next, button[type='submit']")))
        driver.execute_script("arguments[0].click();", btn_next)
        time.sleep(3)

        # --- ÉTAPE 2 : PASSWORD (VERSION BLINDÉE) ---
        log("🔒 Tentative de saisie du mot de passe...")
        pwd_field = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='password'], input#password, #password")))
        
        actions.move_to_element(pwd_field).click().send_keys(FG_PASSWORD).perform()
        
        # Force JS
        driver.execute_script(f"arguments[0].value = '{FG_PASSWORD}';", pwd_field)
        driver.execute_script("arguments[0].dispatchEvent(new Event('input', { bubbles: True }));", pwd_field)

        driver.save_screenshot("debug_gain_2_password.png")
        
        btn_login = driver.find_element(By.CSS_SELECTOR, "button#next, #next, button[type='submit']")
        driver.execute_script("arguments[0].click();", btn_login)

        # Vérification du succès
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='logout'], .user-connected")))
        log("✅ Authentification réussie.")

        # --- ANALYSE DES ENTRAINEURS ---
        for trainer_url in URLS_ENTRAINEURS:
            log(f"🌐 Analyse entraîneur : {trainer_url.split('/')[-1][:20]}...")
            driver.get(trainer_url)
            
            try:
                wait.until(EC.presence_of_element_located((By.ID, "dernieres-courses")))
                trainer_name = driver.find_element(By.CSS_SELECTOR, "h1").text.replace("ENTRAINEUR", "").strip()
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
                        line = f"🏆 *{horse_name}* ({rank}e)\n📅 {raw_date} | 📍 {hippodrome}\n💰 Gain : {prize}€\n👤 Entr: {trainer_name}"
                        final_report.append(line)
                        log(f"  ✅ Retenu : {horse_name} ({rank}e)")

        # --- ENVOI WHATSAPP ---
        if final_report:
            header = f"💰 *TOP PERFORMANCES (7 derniers jours)*\n\n"
            full_message = header + "\n\n---\n\n".join(final_report)
            send_whatsapp_notification(full_message)
        else:
            log("ℹ️ Aucune performance de top 4 trouvée.")

    except Exception as e:
        log(f"💥 Erreur globale : {e}")
        driver.save_screenshot("debug_gain_final_error.png")
    finally:
        driver.quit()
        log("🏁 Fin.")

if __name__ == "__main__":
    run_scraper_history()
