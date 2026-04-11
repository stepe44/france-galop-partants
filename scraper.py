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

# --- CONFIGURATION ---
URL_HOME = "https://www.france-galop.com/fr"
URLS_ENTRAINEURS = [
    "https://www.france-galop.com/fr/entraineur/Z1FxYXQ3cFJyM0ZlUitJQTlmUTNiUT09#partants",
    "https://www.france-galop.com/fr/entraineur/U0VNb0JtQlZ1bUphYndFTnJjSzg4dz09#partants"
]

FG_PASSWORD = os.getenv("FG_PASSWORD")
EMAIL_SENDER = os.getenv("EMAIL_SENDER")
GREEN_API_URL = os.getenv("GREEN_API_URL")

def log(message):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")

def send_whatsapp(message):
    if not GREEN_API_URL:
        log("⚠️ GREEN_API_URL manquante, envoi annulé.")
        return
    payload = {"chatId": "33678723278-1540128478@g.us", "message": message}
    try:
        response = requests.post(GREEN_API_URL, json=payload, timeout=15)
        if response.status_code == 200: log("📲 Notification WhatsApp envoyée.")
        else: log(f"❌ Erreur GreenAPI : {response.status_code}")
    except Exception as e:
        log(f"❌ Erreur lors de l'envoi WhatsApp : {e}")

def run_scraper():
    chrome_options = Options()
    # Configuration pour XVFB (simule un écran réel pour éviter 'Accès Refusé')
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option("useAutomationExtension", False)
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36")
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    
    wait = WebDriverWait(driver, 35)
    today = datetime.now().strftime("%d/%m/%Y")
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%d/%m/%Y")
    today_results = []
    seen_runners = set()

    try:
        log("🌐 Initialisation sur France Galop...")
        driver.get(URL_HOME)
        time.sleep(5)
        
        # 1. Gestion des Cookies
        try:
            cookie_btn = wait.until(EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler")))
            driver.execute_script("arguments[0].click();", cookie_btn)
            log("🍪 Cookies validés.")
        except: pass

        # 2. Authentification Azure AD (Méthode validée par les derniers logs)
        log("🔑 Accès au portail de connexion...")
        login_btn = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='login'], .user-link")))
        driver.execute_script("arguments[0].click();", login_btn)

        # Étape Email
        log("📧 Saisie identifiant...")
        email_el = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "input[type='email'], input[name='username']")))
        if not email_el.get_attribute("value"):
            for char in EMAIL_SENDER: email_el.send_keys(char)
        
        driver.execute_script("arguments[0].dispatchEvent(new Event('blur', { bubbles: true }));", email_el)
        btn_next = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Next')] | //button[@id='next']")))
        driver.execute_script("arguments[0].click();", btn_next)
        
        # Attente transition vers Password
        wait.until(EC.staleness_of(email_el))
        time.sleep(6)

        # Étape Mot de Passe
        log("🔒 Saisie mot de passe...")
        pwd_el = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "input[type='password'], #password")))
        for char in FG_PASSWORD:
            pwd_el.send_keys(char)
            time.sleep(0.05)
        
        driver.execute_script("arguments[0].dispatchEvent(new Event('blur', { bubbles: true }));", pwd_el)
        btn_submit = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Sign in')] | //button[@id='next']")))
        driver.execute_script("arguments[0].click();", btn_submit)
        
        log("⏳ Stabilisation de la session (20s)...")
        time.sleep(20)
        driver.get(URL_HOME)
        time.sleep(5)

        # 3. Extraction des Partants
        for i, trainer_url in enumerate(URLS_ENTRAINEURS):
            log(f"🚀 Analyse de la fiche : {trainer_url.split('/')[-1][:15]}...")
            driver.get(trainer_url)
            time.sleep(10)
            
            # Vérification 'Accès Refusé'
            if "Accès refusé" in driver.page_source:
                log(f"❌ Blocage détecté sur l'URL {i}. Rafraîchissement...")
                driver.refresh()
                time.sleep(8)

            try:
                # Activation de l'onglet 'Partants'
                tab = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='#partants']")))
                driver.execute_script("arguments[0].click();", tab)
                time.sleep(5)
                
                # Récupération du nom de l'entraîneur sur la page
                trainer_name = driver.find_element(By.TAG_NAME, "h1").text.replace("ENTRAINEUR", "").strip()
                
                rows = driver.find_elements(By.CSS_SELECTOR, "#partants_entraineur tbody tr")
                log(f"📊 {len(rows)} lignes détectées pour {trainer_name}.")
                
                for row in rows:
                    txt = row.text
                    if today in txt or tomorrow in txt:
                        cells = row.find_elements(By.TAG_NAME, "td")
                        horse_full = cells[0].text.strip()
                        horse_name = horse_full.split(' (')[0]
                        
                        # Création d'une clé unique pour éviter les doublons
                        uid = f"{horse_name}_{trainer_name}"
                        if uid not in seen_runners:
                            seen_runners.add(uid)
                            date_race = today if today in txt else tomorrow
                            today_results.append(f"🏇 *{horse_name}*\n📅 {date_race}\n👤 {trainer_name}")
                            log(f"✅ Partant ajouté : {horse_name}")
            except Exception as e:
                log(f"⚠️ Erreur sur cet entraîneur : {str(e)[:50]}")
                driver.save_screenshot(f"error_trainer_{i}.png")

        # 4. Rapport Final
        if today_results:
            log(f"📤 {len(today_results)} chevaux au total. Envoi WhatsApp...")
            final_msg = f"📌 *PARTANTS FRANCE GALOP*\n\n" + "\n\n".join(today_results)
            send_whatsapp(final_msg)
        else:
            log("📝 Aucun partant pour aujourd'hui ou demain.")

    except Exception as e:
        log(f"💥 ERREUR CRITIQUE : {e}")
        driver.save_screenshot("fatal_error_final.png")
    finally:
        driver.quit()
        log("🏁 Session terminée.")

if __name__ == "__main__":
    run_scraper()
