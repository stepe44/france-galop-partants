import os
import re
import time
import requests
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
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

def run_scraper():
    chrome_options = Options()
    # Configuration pour XVFB (non-headless)
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
    today_results = []

    try:
        log("🌐 Navigation vers France Galop...")
        driver.get(URL_HOME)
        time.sleep(7)
        
        # 1. Gestion des Cookies
        try:
            cookie_btn = wait.until(EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler")))
            driver.execute_script("arguments[0].click();", cookie_btn)
            log("🍪 Cookies acceptés.")
        except: pass

        # 2. Lancement Connexion
        log("🔑 Ouverture du portail de connexion...")
        login_btn = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='login'], .user-link")))
        driver.execute_script("arguments[0].click();", login_btn)

        # --- PHASE EMAIL ---
        log("📧 Traitement de l'étape Email...")
        email_el = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "input[type='email'], input[name='username']")))
        
        # On vérifie si l'email est déjà là (cas de la capture image_dc2724.png)
        if not email_el.get_attribute("value"):
            for char in EMAIL_SENDER: email_el.send_keys(char)
            log("⌨️ Email saisi.")
        
        driver.execute_script("arguments[0].dispatchEvent(new Event('blur', { bubbles: true }));", email_el)
        driver.save_screenshot("debug_email_ready.png")

        # Clic sur NEXT
        btn_next = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Next')] | //button[@id='next']")))
        driver.execute_script("arguments[0].click();", btn_next)
        
        # Attente que l'écran Email disparaisse
        wait.until(EC.staleness_of(email_el))
        log("➡️ Passage à l'étape Password.")

        # --- PHASE PASSWORD ---
        time.sleep(6)
        pwd_el = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "input[type='password'], #password")))
        log("🔒 Saisie du mot de passe...")
        for char in FG_PASSWORD:
            pwd_el.send_keys(char)
            time.sleep(0.05)
        
        driver.execute_script("arguments[0].dispatchEvent(new Event('blur', { bubbles: true }));", pwd_el)
        driver.save_screenshot("debug_pwd_ready.png")

        btn_submit = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Sign in')] | //button[@id='next']")))
        driver.execute_script("arguments[0].click();", btn_submit)
        
        log("⏳ Attente de redirection et fixation session (20s)...")
        time.sleep(20)
        driver.get(URL_HOME)
        time.sleep(5)

        # 3. ANALYSE DES ENTRAINEURS
        for i, trainer_url in enumerate(URLS_ENTRAINEURS):
            log(f"🚀 Analyse : {trainer_url.split('/')[-1][:15]}")
            driver.get(trainer_url)
            time.sleep(10)
            driver.save_screenshot(f"check_trainer_page_{i}.png")

            if "Accès refusé" in driver.page_source:
                log("❌ Accès refusé par le site.")
                continue

            try:
                # Activation onglet Partants
                tab = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='#partants']")))
                driver.execute_script("arguments[0].click();", tab)
                time.sleep(5)
                
                rows = driver.find_elements(By.CSS_SELECTOR, "#partants_entraineur tbody tr")
                log(f"📊 {len(rows)} lignes trouvées.")
                
                for row in rows:
                    if today in row.text:
                        name = row.find_elements(By.TAG_NAME, "td")[0].text.strip().split(' (')[0]
                        today_results.append(f"🏇 {name}")
            except Exception as e:
                log(f"⚠️ Erreur extraction : {str(e)[:50]}")

        if today_results:
            log(f"📤 {len(today_results)} partants trouvés.")

    except Exception as e:
        log(f"💥 ERREUR CRITIQUE : {e}")
        driver.save_screenshot("fatal_error_final.png")
    finally:
        driver.quit()
        log("🏁 Fin de session.")

if __name__ == "__main__":
    run_scraper()
