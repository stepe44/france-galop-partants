import os
import re
import time
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# --- CONFIGURATION ---
URL_LOGIN = "https://www.france-galop.com/fr/login"
URLS_ENTRAINEURS = [
    "https://www.france-galop.com/fr/entraineur/Z1FxYXQ3cFJyM0ZlUitJQTlmUTNiUT09#partants",
    "https://www.france-galop.com/fr/entraineur/U0VNb0JtQlZ1bUphYndFTnJjSzg4dz09#partants"
]

FG_PASSWORD = os.getenv("FG_PASSWORD")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")
EMAIL_SENDER = os.getenv("EMAIL_SENDER")
EMAIL_DEST = os.getenv("EMAIL_DEST")

def clean_text(text):
    if not text: return ""
    cleaned = re.sub(r'[^a-zA-Z0-9/:\. ]', '', text)
    return " ".join(cleaned.split())

def save_debug_screenshot(driver, name):
    """Enregistre une capture d'écran pour le débuggage."""
    filename = f"debug_{name}_{int(time.time())}.png"
    driver.save_screenshot(filename)
    print(f"📸 Capture d'écran enregistrée : {filename}")

def run_scraper():
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    # Cache la détection Selenium
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    # Suppression du flag webdriver
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    
    wait = WebDriverWait(driver, 30)
    today = datetime.now().strftime("%d/%m/%Y")
    results = []

    try:
        # 1. TENTATIVE DE CONNEXION
        print(f"🚀 Accès à {URL_LOGIN}...")
        driver.get(URL_LOGIN)
        time.sleep(5)
        save_debug_screenshot(driver, "1_page_login")

        # Cookies
        try:
            cookie_btn = driver.find_element(By.ID, "onetrust-accept-btn-handler")
            cookie_btn.click()
            print("🍪 Cookies acceptés.")
            time.sleep(2)
        except:
            print("ℹ️ Bouton cookies non trouvé (ou déjà accepté).")

        # Remplissage par CSS Selector (plus précis)
        print("✍️ Saisie des identifiants...")
        user_input = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "input#edit-name, input[name='name']")))
        user_input.send_keys(EMAIL_SENDER)
        
        pass_input = driver.find_element(By.CSS_SELECTOR, "input#edit-pass, input[name='pass']")
        pass_input.send_keys(FG_PASSWORD)
        
        save_debug_screenshot(driver, "2_champs_remplis")
        
        submit_btn = driver.find_element(By.ID, "edit-submit")
        driver.execute_script("arguments[0].click();", submit_btn)
        
        print("⏳ Attente de la session...")
        time.sleep(8)
        save_debug_screenshot(driver, "3_apres_clic_login")

        # 2. VÉRIFICATION DE LA CONNEXION
        if "login" in driver.current_url.lower() and not "entraineur" in driver.current_url:
             print("⚠️ Attention : Il semble que nous soyons toujours sur la page login.")

        # 3. SCRAPING
        for url in URLS_ENTRAINEURS:
            print(f"🧐 Navigation vers : {url}")
            driver.get(url)
            time.sleep(10) # France Galop est lent à charger les tableaux AJAX
            save_debug_screenshot(driver, f"4_page_entraineur_{url.split('/')[-1][:5]}")

            # Recherche des lignes du tableau
            rows = driver.find_elements(By.XPATH, f"//tr[contains(., '{today}')]")
            print(f"🔎 Lignes trouvées pour aujourd'hui : {len(rows)}")

            for row in rows:
                cells = row.find_elements(By.TAG_NAME, "td")
                if len(cells) >= 5:
                    line = f"{today} / {clean_text(cells[1].text)} / {clean_text(cells[2].text)} / {clean_text(cells[3].text)} / {clean_text(cells[4].text)}"
                    results.append(line)
                    print(f"✅ Match : {line}")

        # 4. EMAIL
        if results:
            print(f"📧 Envoi de {len(results)} résultat(s)...")
            # (Appel à votre fonction send_email ici...)
        else:
            print("🏁 Fin de session : Aucun partant détecté.")

    except Exception as e:
        print(f"💥 ERREUR CRITIQUE : {e}")
        save_debug_screenshot(driver, "CRASH")
    finally:
        driver.quit()

if __name__ == "__main__":
    run_scraper()
