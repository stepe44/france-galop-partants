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

def get_pure_horse_name(full_name):
    return re.split(r'\s[A-Z]\.', full_name)[0].strip()

def run_scraper():
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36")
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    wait = WebDriverWait(driver, 25)
    
    try:
        log("🌐 Navigation vers France Galop...")
        driver.get(URL_HOME)
        
        try:
            wait.until(EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler"))).click()
        except: pass

        # Clic Connexion
        login_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "a[href*='login'], .user-link, .login")))
        driver.execute_script("arguments[0].click();", login_btn)

        # --- ÉTAPE 1 : EMAIL (Sélecteur mis à jour via logs) ---
        log("📧 Saisie de l'identifiant...")
        # Utilisation du placeholder car l'ID est vide selon vos logs
        email_field = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "input[placeholder='Email address'], input[name='username']")))
        
        driver.execute_script(f"arguments[0].value = '{EMAIL_SENDER}';", email_field)
        driver.execute_script("arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", email_field)
        
        btn_next = driver.find_element(By.CSS_SELECTOR, "button[type='submit'], .next, #next")
        driver.execute_script("arguments[0].click();", btn_next)
        time.sleep(3)

        # --- ÉTAPE 2 : PASSWORD ---
        log("🔒 Saisie du mot de passe...")
        pwd_field = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "input[type='password']")))
        driver.execute_script(f"arguments[0].value = '{FG_PASSWORD}';", pwd_field)
        driver.execute_script("arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", pwd_field)
        
        btn_login = driver.find_element(By.CSS_SELECTOR, "button[type='submit'], #next")
        driver.execute_script("arguments[0].click();", btn_login)

        # IMPORTANT : Attendre la redirection vers le domaine principal
        log("⏳ Attente du retour sur France Galop...")
        wait.until(EC.url_contains("france-galop.com/fr"))
        # On attend qu'un élément de connexion (Logout ou Profil) soit présent
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='logout'], .user-connected")))
        log("✅ Authentification réussie.")

        # --- DÉBUT DU SCRAPPING ---
        # Ajoutez ici votre boucle for trainer_url in URLS_ENTRAINEURS...
        # ... (votre code de scraping précédent) ...

    except Exception as e:
        log(f"💥 Erreur : {e}")
        driver.save_screenshot("debug_final_error.png")
    finally:
        driver.quit()
        log("🏁 Fin de session.")

if __name__ == "__main__":
    run_scraper()
