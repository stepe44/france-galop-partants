import os
import time
import requests
from datetime import datetime
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
    "https://www.france-galop.com/fr/entraineur/Z1FxYXQ3cFJyM0ZlUitJQTlmUTNiUT09",
    "https://www.france-galop.com/fr/entraineur/U0VNb0JtQlZ1bUphYndFTnJjSzg4dz09"
]

FG_PASSWORD = os.getenv("FG_PASSWORD")
EMAIL_SENDER = os.getenv("EMAIL_SENDER")
GREEN_API_URL = os.getenv("GREEN_API_URL")

def log(message):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")

def send_whatsapp(message):
    if not GREEN_API_URL: return
    payload = {"chatId": "33678723278-1540128478@g.us", "message": message}
    try:
        requests.post(GREEN_API_URL, json=payload, timeout=15)
        log("📲 Rapport Hebdo envoyé via WhatsApp.")
    except Exception as e:
        log(f"❌ Erreur WhatsApp : {e}")

def run_gain_scraper():
    chrome_options = Options()
    # Configuration XVFB pour environnement serveur
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
    stats_rapport = []

    try:
        log("🌐 Connexion initiale pour le rapport des gains...")
        driver.get(URL_HOME)
        time.sleep(5)
        
        # Acceptation cookies
        try:
            cookie_btn = wait.until(EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler")))
            driver.execute_script("arguments[0].click();", cookie_btn)
        except: pass

        # Authentification Azure AD (Méthode validée par les logs précédents)
        login_btn = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='login'], .user-link")))
        driver.execute_script("arguments[0].click();", login_btn)

        # Email
        email_el = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "input[type='email'], input[name='username']")))
        if not email_el.get_attribute("value"):
            for char in EMAIL_SENDER: email_el.send_keys(char)
        
        driver.execute_script("arguments[0].dispatchEvent(new Event('blur', { bubbles: true }));", email_el)
        btn_next = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Next')] | //button[@id='next']")))
        driver.execute_script("arguments[0].click();", btn_next)
        
        wait.until(EC.staleness_of(email_el))
        time.sleep(6)

        # Password
        pwd_el = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "input[type='password'], #password")))
        for char in FG_PASSWORD:
            pwd_el.send_keys(char)
            time.sleep(0.05)
        
        driver.execute_script("arguments[0].dispatchEvent(new Event('blur', { bubbles: true }));", pwd_el)
        btn_submit = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Sign in')] | //button[@id='next']")))
        driver.execute_script("arguments[0].click();", btn_submit)
        
        log("⏳ Stabilisation session (20s)...")
        time.sleep(20)

        # --- EXTRACTION DES GAINS ---
        for i, trainer_url in enumerate(URLS_ENTRAINEURS):
            log(f"🚀 Analyse des gains : {trainer_url.split('/')[-1][:15]}...")
            driver.get(trainer_url)
            time.sleep(8)
            
            if "Accès refusé" in driver.page_source:
                driver.refresh()
                time.sleep(8)

            try:
                # Récupération du nom de l'entraîneur
                name = driver.find_element(By.TAG_NAME, "h1").text.replace("ENTRAINEUR", "").strip()
                
                # Extraction des blocs de statistiques (Gains / Victoires / Places)
                # On cible les éléments de la classe 'key-stat-value' ou les tableaux récapitulatifs
                stats_elements = driver.find_elements(By.CSS_SELECTOR, ".key-stat-value, .stat-value")
                
                if len(stats_elements) >= 3:
                    victoires = stats_elements[0].text.strip()
                    places = stats_elements[1].text.strip()
                    gains = stats_elements[2].text.strip()
                    
                    stats_rapport.append(f"🏆 *{name}*\n💰 Gains : {gains}€\n🥇 Victoires : {victoires}\n🥈 Places : {places}")
                    log(f"✅ Stats extraites pour {name}")
                else:
                    log(f"⚠️ Format de stats inhabituel pour {name}")

            except Exception as e:
                log(f"❌ Erreur sur {trainer_url} : {str(e)[:50]}")

        # Envoi du rapport final
        if stats_rapport:
            message_final = f"📊 *BILAN HEBDOMADAIRE GAINS*\n\n" + "\n\n---\n\n".join(stats_rapport)
            send_whatsapp(message_final)
        else:
            log("📝 Aucune donnée de gain extraite.")

    except Exception as e:
        log(f"💥 ERREUR CRITIQUE GAIN : {e}")
    finally:
        driver.quit()
        log("🏁 Fin de session Gain.")

if __name__ == "__main__":
    run_gain_scraper()
