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
    "https://www.france-galop.com/fr/entraineur/Z1FxYXQ3cFJyM0ZlUitJQTlmUTNiUT09#dernieres-courses",
    "https://www.france-galop.com/fr/entraineur/U0VNb0JtQlZ1bUphYndFTnJjSzg4dz09#dernieres-courses"
]

FG_PASSWORD = os.getenv("FG_PASSWORD")
EMAIL_SENDER = os.getenv("EMAIL_SENDER")
GREEN_API_URL = os.getenv("GREEN_API_URL")

def log(message):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")

def clean_text(text):
    if not text: return "N/A"
    return " ".join(text.split()).strip()

def parse_date(date_str):
    try:
        return datetime.strptime(date_str.strip(), "%d/%m/%Y")
    except:
        return None

def send_whatsapp_notification(content):
    if not GREEN_API_URL:
        log("⚠️ GREEN_API_URL manquante, envoi annulé.")
        return
    payload = {"chatId": "33678723278-1540128478@g.us", "message": content}
    try:
        response = requests.post(GREEN_API_URL, json=payload, timeout=15)
        if response.status_code == 200: log("📲 Notification WhatsApp envoyée.")
        else: log(f"❌ Erreur GreenAPI : {response.status_code}")
    except Exception as e:
        log(f"❌ Erreur lors de l'envoi WhatsApp : {e}")

def run_scraper_history():
    chrome_options = Options()
    # Configuration identique à scraper.py pour éviter le blocage
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
    today = datetime.now()
    start_date = today - timedelta(days=7)
    final_report = []

    try:
        log("🌐 Initialisation sur France Galop...")
        driver.get(URL_HOME)
        time.sleep(5)
        
        # 1. Gestion des Cookies
        try:
            cookie_btn = wait.until(EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler")))
            driver.execute_script("arguments[0].click();", cookie_btn)
            log("🍪 Cookies validés.")
        except: pass

        # 2. Authentification Azure AD (Méthode de scraper.py)
        log("🔑 Accès au portail de connexion...")
        login_btn = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='login'], .user-link")))
        driver.execute_script("arguments[0].click();", login_btn)

        log("📧 Saisie identifiant...")
        email_el = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "input[type='email'], input[name='username']")))
        for char in EMAIL_SENDER: email_el.send_keys(char)
        
        driver.execute_script("arguments[0].dispatchEvent(new Event('blur', { bubbles: true }));", email_el)
        btn_next = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Next')] | //button[@id='next']")))
        driver.execute_script("arguments[0].click();", btn_next)
        
        time.sleep(6)

        log("🔒 Saisie mot de passe...")
        pwd_el = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "input[type='password'], #password")))
        for char in FG_PASSWORD:
            pwd_el.send_keys(char)
            time.sleep(0.05)
        
        driver.execute_script("arguments[0].dispatchEvent(new Event('blur', { bubbles: true }));", pwd_el)
        btn_submit = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Sign in')] | //button[@id='next']")))
        driver.execute_script("arguments[0].click();", btn_submit)
        
        log("⏳ Stabilisation de la session (20s)...")
        time.sleep(20)

        # 3. Analyse des Gains
        for trainer_url in URLS_ENTRAINEURS:
            log(f"🚀 Analyse de la fiche : {trainer_url.split('/')[-1][:15]}...")
            driver.get(trainer_url)
            time.sleep(10)

            if "Accès refusé" in driver.page_source:
                log("❌ Blocage détecté. Rafraîchissement...")
                driver.refresh()
                time.sleep(8)

            try:
                # Activation de l'onglet 'Dernières courses'
                tab = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='#dernieres-courses']")))
                driver.execute_script("arguments[0].click();", tab)
                time.sleep(5)
                
                trainer_name = driver.find_element(By.TAG_NAME, "h1").text.replace("ENTRAINEUR", "").strip()
                rows = driver.find_elements(By.CSS_SELECTOR, "#dernieres-courses table tbody tr")
                
                for row in rows:
                    cells = row.find_elements(By.TAG_NAME, "td")
                    if len(cells) < 12: continue 
                    
                    raw_date = cells[0].text.strip()       
                    place = cells[1].text.strip()          
                    horse_name = clean_text(cells[2].text) 
                    hippodrome = clean_text(cells[8].text) 
                    prize = clean_text(cells[11].text)     

                    race_dt = parse_date(raw_date)
                    if race_dt and start_date <= race_dt <= today:
                        # Filtrage Place (1er à 4e)
                        match_place = re.search(r'^([1-4])$', place)
                        if match_place:
                            rank = match_place.group(1)
                            line = f"🏆 *{horse_name}* ({rank}e)\n📅 {raw_date} | 📍 {hippodrome}\n💰 Gain : {prize}€\n👤 Entr: {trainer_name}"
                            final_report.append(line)
                            log(f"✅ Performance retenue : {horse_name}")
            except Exception as e:
                log(f"⚠️ Erreur sur cet entraîneur : {str(e)[:50]}")

        # 4. Envoi Final
        if final_report:
            header = f"💰 *TOP PERFORMANCES (7 derniers jours)*\n\n"
            full_message = header + "\n\n---\n\n".join(final_report)
            send_whatsapp_notification(full_message)
        else:
            log("📝 Aucune performance de top 4 trouvée.")

    except Exception as e:
        log(f"💥 ERREUR CRITIQUE : {e}")
    finally:
        driver.quit()
        log("🏁 Session terminée.")

if __name__ == "__main__":
    run_scraper_history()
