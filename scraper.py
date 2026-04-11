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
    # xvfb-run gère l'affichage, donc pas de mode headless classique ici
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    
    # Stratégie Stealth
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option("useAutomationExtension", False)
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36")
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    
    wait = WebDriverWait(driver, 30)
    today = datetime.now().strftime("%d/%m/%Y")
    today_results = []

    try:
        for i, trainer_url in enumerate(URLS_ENTRAINEURS):
            log(f"🚀 DEBUT ANALYSE : {trainer_url}")
            driver.get(trainer_url)
            time.sleep(6)
            driver.save_screenshot(f"01_initial_load_{i}.png")

            # --- PHASE AUTHENTIFICATION ---
            if "ciamlogin.com" in driver.current_url or driver.find_elements(By.NAME, "username"):
                log("🔑 Écran de connexion détecté. Début de la saisie...")
                
                # 1. EMAIL
                log("📧 Recherche du champ Email...")
                email_field = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "input[type='email'], input[name='username'], #email")))
                email_field.clear()
                for char in EMAIL_SENDER: email_field.send_keys(char)
                log(f"✅ Email '{EMAIL_SENDER}' saisi.")
                
                # Blur pour valider aux yeux d'Azure
                driver.execute_script("arguments[0].dispatchEvent(new Event('blur', { bubbles: true }));", email_field)
                driver.save_screenshot(f"02_email_typed_{i}.png")
                
                log("🖱️ Clic sur le bouton 'Suivant'...")
                btn_next = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button#next, button[type='submit'], .next-button, #continue")))
                driver.execute_script("arguments[0].click();", btn_next)
                
                # 2. PASSWORD
                log("⏳ Attente du champ Mot de passe (Transition Azure)...")
                time.sleep(7)
                driver.save_screenshot(f"03_before_password_{i}.png")
                
                pwd_field = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "input[type='password'], #password")))
                pwd_field.clear()
                log("🔒 Saisie du mot de passe...")
                for char in FG_PASSWORD:
                    pwd_field.send_keys(char)
                    time.sleep(0.05)
                
                # Validation forcée du password
                driver.execute_script("arguments[0].dispatchEvent(new Event('blur', { bubbles: true }));", pwd_field)
                driver.save_screenshot(f"04_pwd_typed_{i}.png")
                
                log("🖱️ Clic sur 'Se connecter'...")
                btn_signin = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button#next, button[type='submit'], .sign-in, #continue")))
                driver.execute_script("arguments[0].click();", btn_signin)
                
                log("⏳ Attente redirection post-connexion (15s)...")
                time.sleep(15)

            # --- PHASE NAVIGATION POST-LOGIN ---
            log(f"📄 URL actuelle après auth : {driver.current_url}")
            driver.save_screenshot(f"05_post_auth_url_{i}.png")

            if "entraineur" not in driver.current_url:
                log("🔄 Toujours pas sur la fiche entraîneur. Forçage URL...")
                driver.get(trainer_url)
                time.sleep(10)
                driver.save_screenshot(f"06_forced_url_check_{i}.png")

            if "Accès refusé" in driver.page_source:
                log("❌ ERREUR : 'Accès refusé' détecté. Fin de tentative pour cet entraîneur.")
                continue

            # --- PHASE EXTRACTION ---
            try:
                log("🖱️ Tentative d'activation de l'onglet 'Partants'...")
                tab = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='#partants']")))
                driver.execute_script("arguments[0].click();", tab)
                time.sleep(5)
                driver.save_screenshot(f"07_tab_clicked_{i}.png")
                
                log("📊 Recherche du tableau de données...")
                wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "#partants_entraineur tbody tr")))
                rows = driver.find_elements(By.CSS_SELECTOR, "#partants_entraineur tbody tr")
                log(f"✅ SUCCÈS : {len(rows)} lignes trouvées dans le tableau.")
                
                for row in rows:
                    if today in row.text:
                        name = row.find_elements(By.TAG_NAME, "td")[0].text.strip().split(' (')[0]
                        today_results.append(f"🏇 {name}")
            except Exception as e:
                log(f"⚠️ Échec extraction tableau : {str(e)[:60]}")
                driver.save_screenshot(f"08_error_table_{i}.png")

        if today_results:
            log(f"📤 {len(today_results)} partants identifiés.")
        else:
            log("📝 Aucun partant trouvé pour aujourd'hui.")

    except Exception as e:
        log(f"💥 ERREUR CRITIQUE GLOBALE : {e}")
        driver.save_screenshot("99_fatal_error.png")
    finally:
        driver.quit()
        log("🏁 Session Selenium fermée.")

if __name__ == "__main__":
    run_scraper()
