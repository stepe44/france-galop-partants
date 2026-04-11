import os
import re
import time
import requests
import base64
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

def get_pure_horse_name(full_name):
    return re.split(r'\s[A-Z]\.', full_name)[0].strip()

def normalize_for_xpath(text):
    return re.sub(r'[^a-z0-9]', '', text.lower())

def run_scraper():
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36")
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    wait = WebDriverWait(driver, 20)
    
    try:
        log("🌐 Navigation vers la Home...")
        driver.get(URL_HOME)
        
        # Gestion des cookies
        try:
            wait.until(EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler"))).click()
            log("🍪 Cookies acceptés.")
        except:
            log("ℹ️ Pas de bannière cookies.")

        log("🔑 Clic sur le bouton de connexion...")
        login_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "a[href*='login'], .user-link, .login")))
        driver.execute_script("arguments[0].click();", login_btn)
        
        # --- PHASE DE DIAGNOSTIC DE LA PAGE DE LOGIN ---
        time.sleep(5) # Laisser le temps à Azure de charger
        log(f"📄 URL actuelle : {driver.current_url}")
        
        # 1. Analyse des IFrames (Cause fréquente de blocage sur Azure)
        iframes = driver.find_elements(By.TAG_NAME, "iframe")
        log(f"🔎 Nombre d'iframes détectées : {len(iframes)}")
        for i, frame in enumerate(iframes):
            log(f"   - IFrame {i}: ID={frame.get_attribute('id')}, Name={frame.get_attribute('name')}, Src={frame.get_attribute('src')[:50]}...")

        # 2. Recherche exhaustive du champ Email
        log("🔍 Recherche du champ Email dans le DOM...")
        potential_inputs = driver.find_elements(By.TAG_NAME, "input")
        log(f"📊 Nombre d'inputs trouvés : {len(potential_inputs)}")
        for inp in potential_inputs:
            log(f"   - Input: ID='{inp.get_attribute('id')}', Type='{inp.get_attribute('type')}', Name='{inp.get_attribute('name')}', Placeholder='{inp.get_attribute('placeholder')}'")

        # --- TENTATIVE DE SAISIE AVANCÉE ---
        log("📧 Tentative de saisie de l'identifiant...")
        
        # On cherche l'élément le plus probable
        selectors = ["#email", "input[type='email']", "input[name='Email Address']", "input[placeholder*='Email']"]
        email_el = None
        for sel in selectors:
            try:
                email_el = driver.find_element(By.CSS_SELECTOR, sel)
                if email_el:
                    log(f"✅ Élément trouvé avec le sélecteur : {sel}")
                    break
            except: continue

        if not email_el:
            log("❌ Aucun champ email trouvé avec les sélecteurs standards.")
            driver.save_screenshot("debug_no_email_field.png")
            # Loguer le code source partiel pour inspection
            log("📝 Code source réduit de la page :")
            print(driver.page_source[:2000]) 
            return

        # Saisie par injection brutale et simulation
        driver.execute_script("arguments[0].scrollIntoView(true);", email_el)
        time.sleep(1)
        
        # Simulation humaine
        actions = ActionChains(driver)
        actions.move_to_element(email_el).click().send_keys(EMAIL_SENDER).perform()
        
        # Double vérification JS
        driver.execute_script(f"arguments[0].value = '{EMAIL_SENDER}';", email_el)
        driver.execute_script("arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", email_el)
        
        log(f"✍️ Valeur injectée. Longueur détectée par JS : {driver.execute_script('return arguments[0].value.length;', email_el)}")
        driver.save_screenshot("debug_step1_email.png")

        # Clic sur Suivant
        try:
            btn_next = driver.find_element(By.ID, "next")
            log("🔘 Bouton Next trouvé, clic...")
            driver.execute_script("arguments[0].click();", btn_next)
        except:
            log("⚠️ Bouton 'next' non trouvé par ID, tentative par CSS...")
            btn_next = driver.find_element(By.CSS_SELECTOR, "button[type='submit'], .next")
            driver.execute_script("arguments[0].click();", btn_next)

        time.sleep(3)
        log(f"📄 URL après clic Next : {driver.current_url}")
        driver.save_screenshot("debug_step2_after_next.png")

        # --- PHASE PASSWORD ---
        log("🔒 Tentative de saisie du mot de passe...")
        pwd_field = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='password'], #password")))
        driver.execute_script(f"arguments[0].value = '{FG_PASSWORD}';", pwd_field)
        driver.execute_script("arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", pwd_field)
        
        btn_login = driver.find_element(By.CSS_SELECTOR, "#next, button[type='submit']")
        driver.execute_script("arguments[0].click();", btn_login)

        # Attente de redirection finale
        wait.until(EC.url_contains("france-galop.com"))
        log("✅ Authentification réussie.")

    except Exception as e:
        log(f"💥 ERREUR CRITIQUE : {str(e)}")
        driver.save_screenshot("debug_final_crash.png")
    finally:
        driver.quit()
        log("🏁 Fin de session.")

if __name__ == "__main__":
    run_scraper()
