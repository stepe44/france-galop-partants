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

def log(message):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")

def run_scraper():
    chrome_options = Options()
    # xvfb-run simule l'écran sur GitHub Actions
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option("useAutomationExtension", False)
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36")
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    wait = WebDriverWait(driver, 40) # Timeout étendu
    today = datetime.now().strftime("%d/%m/%Y")
    today_results = []

    try:
        log("🌐 Navigation Home...")
        driver.get(URL_HOME)
        time.sleep(8)
        
        # 1. ACCEPTER LES COOKIES (IMPÉRATIF)
        try:
            log("🍪 Tentative acceptation cookies...")
            cookie_btn = wait.until(EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler")))
            driver.execute_script("arguments[0].click();", cookie_btn)
            time.sleep(2)
        except: log("ℹ️ Pas de bannière de cookies détectée.")

        # 2. OUVERTURE CONNEXION
        log("🔑 Clic sur bouton de connexion...")
        login_btn = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='login'], .user-link, .login")))
        driver.execute_script("arguments[0].click();", login_btn)
        
        # 3. SAISIE EMAIL
        log("📧 Attente champ Email (Azure AD)...")
        email_el = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "input[name='username'], input[type='email'], #email")))
        email_el.clear()
        for char in EMAIL_SENDER: email_el.send_keys(char)
        driver.execute_script("arguments[0].dispatchEvent(new Event('blur', { bubbles: true }));", email_el)
        
        # Clic "Suivant" avec sélecteurs de secours
        next_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button#next, input[type='submit'], .next-button")))
        driver.execute_script("arguments[0].click();", next_btn)
        
        # 4. SAISIE PASSWORD
        log("🔒 Attente champ Password...")
        time.sleep(6)
        pwd_el = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "input[type='password'], #password")))
        for char in FG_PASSWORD: 
            pwd_el.send_keys(char)
            time.sleep(0.05)
        driver.execute_script("arguments[0].dispatchEvent(new Event('blur', { bubbles: true }));", pwd_el)
        
        # Clic "Se connecter"
        submit_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button#next, input[type='submit'], .sign-in")))
        driver.execute_script("arguments[0].click();", submit_btn)
        
        log("⏳ Fixation session (20s)...")
        time.sleep(20)
        driver.get(URL_HOME) # Force retour Home connecté
        time.sleep(5)
        driver.save_screenshot("check_final_home.png")

        # 5. SCRAPING ENTRAINEURS
        for i, trainer_url in enumerate(URLS_ENTRAINEURS):
            log(f"🚀 Navigation vers : {trainer_url}")
            driver.get(trainer_url)
            time.sleep(10)
            
            if "Accès refusé" in driver.page_source:
                log(f"❌ Accès refusé pour {trainer_url}.")
                continue

            try:
                # Activation onglet Partants
                tab = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='#partants']")))
                driver.execute_script("arguments[0].click();", tab)
                time.sleep(5)
                
                rows = driver.find_elements(By.CSS_SELECTOR, "#partants_entraineur tbody tr")
                log(f"✅ {len(rows)} chevaux trouvés.")
                
                for row in rows:
                    if today in row.text:
                        name = row.find_elements(By.TAG_NAME, "td")[0].text.strip()
                        today_results.append(f"🏇 {name}")
            except Exception as e:
                log(f"⚠️ Erreur : {str(e)[:50]}")

    except Exception as e:
        log(f"💥 Erreur Critique : {e}")
        driver.save_screenshot("fatal_error_home.png")
    finally:
        driver.quit()
        log("🏁 Session terminée.")

if __name__ == "__main__":
    run_scraper()
