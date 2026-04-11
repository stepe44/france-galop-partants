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
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36")
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    wait = WebDriverWait(driver, 30)
    today = datetime.now().strftime("%d/%m/%Y")
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%d/%m/%Y")
    today_results = []
    seen_runners = set()

    try:
        for i, trainer_url in enumerate(URLS_ENTRAINEURS):
            log(f"🌐 Accès à : {trainer_url}")
            driver.get(trainer_url)
            time.sleep(5)

            if "ciamlogin.com" in driver.current_url or driver.find_elements(By.CSS_SELECTOR, "input[name='username']"):
                log("🔑 Connexion requise...")
                
                # Saisie Email Blindée
                email_el = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[placeholder*='Email'], input[name='username']")))
                email_el.clear()
                for char in EMAIL_SENDER:
                    email_el.send_keys(char)
                driver.execute_script("arguments[0].dispatchEvent(new Event('blur', { bubbles: true }));", email_el)
                driver.execute_script("arguments[0].click();", driver.find_element(By.CSS_SELECTOR, "button[type='submit'], .next, #next"))
                
                # Saisie Password Blindée (CORRECTION ICI)
                time.sleep(4)
                pwd_el = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='password']")))
                pwd_el.clear()
                for char in FG_PASSWORD:
                    pwd_el.send_keys(char)
                    time.sleep(0.05)
                driver.execute_script("arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", pwd_el)
                driver.execute_script("arguments[0].dispatchEvent(new Event('blur', { bubbles: true }));", pwd_el)
                
                driver.save_screenshot(f"debug_pwd_typed_{i}.png")
                driver.execute_script("arguments[0].click();", driver.find_element(By.CSS_SELECTOR, "button[type='submit'], #next, .sign-in"))
                
                log("⏳ Attente de redirection...")
                time.sleep(15)

            if trainer_url not in driver.current_url:
                log("🔄 Forçage vers l'URL entraîneur...")
                driver.get(trainer_url)
                time.sleep(8)

            # Scraping du tableau (Logique simplifiée)
            try:
                wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "#partants_entraineur tbody tr")))
                rows = driver.find_elements(By.CSS_SELECTOR, "#partants_entraineur tbody tr")
                log(f"✅ {len(rows)} chevaux trouvés.")
                # ... (Votre logique habituelle d'extraction)
            except:
                log(f"❌ Échec tableau pour {trainer_url}")

    except Exception as e:
        log(f"💥 Erreur : {e}")
    finally:
        driver.quit()
        log("🏁 Fin.")

if __name__ == "__main__":
    run_scraper()
