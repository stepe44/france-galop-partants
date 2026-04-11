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
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    
    # Paramètres de furtivité pour éviter "Accès Refusé"
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option("useAutomationExtension", False)
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36")
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    
    wait = WebDriverWait(driver, 20)
    today = datetime.now().strftime("%d/%m/%Y")
    today_results = []

    try:
        for i, trainer_url in enumerate(URLS_ENTRAINEURS):
            log(f"🌐 Navigation vers : {trainer_url}")
            driver.get(trainer_url)
            time.sleep(5)

            if "ciamlogin.com" in driver.current_url:
                log("🔑 Écran de connexion détecté...")
                
                # 1. Saisie Email
                email_field = wait.until(EC.element_to_be_clickable((By.NAME, "username")))
                for char in EMAIL_SENDER: 
                    email_field.send_keys(char)
                driver.execute_script("arguments[0].dispatchEvent(new Event('blur', { bubbles: true }));", email_field)
                
                # Clic Next (Sélecteur renforcé)
                btn_next = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button#next, button[type='submit'], .next")))
                driver.execute_script("arguments[0].click();", btn_next)
                log("📧 Email validé.")
                
                # 2. Saisie Password
                time.sleep(5)
                pwd_field = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "input[type='password']")))
                for char in FG_PASSWORD:
                    pwd_field.send_keys(char)
                    time.sleep(0.05)
                driver.execute_script("arguments[0].dispatchEvent(new Event('blur', { bubbles: true }));", pwd_field)
                
                # Clic Sign-in (Sélecteur renforcé)
                btn_signin = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button#next, button[type='submit'], .sign-in")))
                driver.execute_script("arguments[0].click();", btn_signin)
                log("🔒 Mot de passe validé. Redirection...")
                
                time.sleep(15)

            # --- VÉRIFICATION POST-CONNEXION ---
            if trainer_url not in driver.current_url:
                driver.get(trainer_url)
                time.sleep(8)

            driver.save_screenshot(f"check_final_{i}.png")

            try:
                # Activation onglet Partants
                tab = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "a[href*='#partants']")))
                driver.execute_script("arguments[0].click();", tab)
                time.sleep(5)
                
                wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "#partants_entraineur tbody tr")))
                rows = driver.find_elements(By.CSS_SELECTOR, "#partants_entraineur tbody tr")
                log(f"✅ {len(rows)} chevaux trouvés.")
                
                for row in rows:
                    if today in row.text:
                        name = row.find_elements(By.TAG_NAME, "td")[0].text.strip()
                        today_results.append(f"🏇 {name}")
            except:
                log(f"⚠️ Aucun tableau visible pour {trainer_url}")

    except Exception as e:
        log(f"💥 Erreur Critique : {e}")
        driver.save_screenshot("fatal_error.png")
    finally:
        driver.quit()
        log("🏁 Fin de session.")

if __name__ == "__main__":
    run_scraper()
