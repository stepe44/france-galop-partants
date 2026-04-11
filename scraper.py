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
from selenium.webdriver.common.action_chains import ActionChains
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

def clean_text(text):
    if not text: return ""
    cleaned = re.sub(r"[^a-zA-Z0-9/:\. '()]", '', text)
    return " ".join(cleaned.split()).strip()

def run_scraper():
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    # User-Agent très récent pour éviter les détections Azure
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36")
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    wait = WebDriverWait(driver, 30)
    
    try:
        log("🌐 Accès à France Galop...")
        driver.get(URL_HOME)
        
        try:
            wait.until(EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler"))).click()
        except: pass

        log("🔑 Ouverture du portail...")
        login_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "a[href*='login'], .user-link, .login")))
        driver.execute_script("arguments[0].click();", login_btn)

        # --- ÉTAPE 1 : EMAIL (FORCÉ) ---
        log("📧 Tentative de saisie de l'identifiant...")
        
        # Attente que le champ soit présent, peu importe son ID exact (Azure utilise parfois des variantes)
        email_field = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='email'], input#email, #email")))
        
        # Méthode 1: Clic via ActionChains et saisie de touches
        actions = ActionChains(driver)
        actions.move_to_element(email_field).click().perform()
        time.sleep(1)
        
        # On vide le champ au cas où
        email_field.send_keys(Keys.CONTROL + "a")
        email_field.send_keys(Keys.DELETE)
        
        # Méthode 2: Saisie via ActionChains (simule mieux un humain)
        actions.send_keys(EMAIL_SENDER).perform()
        
        # Méthode 3: Force via JavaScript si toujours vide
        val = driver.execute_script("return arguments[0].value;", email_field)
        if not val or val == "":
            log("⚠️ Méthode standard échouée, injection via JS...")
            driver.execute_script(f"arguments[0].value = '{EMAIL_SENDER}';", email_field)
            # On déclenche les événements JS pour que le bouton "Next" s'active
            driver.execute_script("arguments[0].dispatchEvent(new Event('input', { bubbles: True }));", email_field)
            driver.execute_script("arguments[0].dispatchEvent(new Event('change', { bubbles: True }));", email_field)

        driver.save_screenshot("debug_1_email_typed.png")
        
        # Clic sur NEXT (souvent un bouton avec ID 'next' ou de type 'submit')
        btn_next = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button#next, #next, button[type='submit']")))
        driver.execute_script("arguments[0].click();", btn_next)
        time.sleep(3)

        # --- ÉTAPE 2 : PASSWORD (FORCÉ) ---
        log("🔒 Tentative de saisie du mot de passe...")
        pwd_field = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='password'], input#password, #password")))
        
        actions.move_to_element(pwd_field).click().send_keys(FG_PASSWORD).perform()
        
        # Force JS si besoin
        val_pwd = driver.execute_script("return arguments[0].value;", pwd_field)
        if not val_pwd:
            driver.execute_script(f"arguments[0].value = '{FG_PASSWORD}';", pwd_field)
            driver.execute_script("arguments[0].dispatchEvent(new Event('input', { bubbles: True }));", pwd_field)

        driver.save_screenshot("debug_2_password_typed.png")
        
        btn_login = driver.find_element(By.CSS_SELECTOR, "button#next, #next, button[type='submit']")
        driver.execute_script("arguments[0].click();", btn_login)

        # Vérification du succès (attente de la déconnexion ou d'un élément du profil)
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='logout'], .user-connected, .my-account")))
        log("✅ Authentification réussie.")

        # --- LA SUITE DU SCRAPPING ICI ---
        # (Gardez votre logique de boucle entraîneurs inchangée)

    except Exception as e:
        log(f"💥 Erreur globale : {e}")
        driver.save_screenshot("debug_final_error.png")
    finally:
        driver.quit()
        log("🏁 Fin.")

if __name__ == "__main__":
    run_scraper()
