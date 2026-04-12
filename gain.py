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

# --- NOUVELLE FONCTION : RÉCUPÉRATION RAPPORTS PMU ---
def get_pmu_rapports(date_str, hippodrome_name, horse_name):
    """
    date_str format: 'DD/MM/YYYY'
    """
    formatted_date = date_str.replace('/', '')
    base_url = "https://online.pmu.fr/rest/client/7/programme"
    
    try:
        # 1. Récupérer le programme du jour
        resp = requests.get(f"{base_url}/{formatted_date}", timeout=10)
        if resp.status_code != 200: return "Indisponible"
        
        programme = resp.json()
        
        # 2. Chercher la réunion et la course
        for reunion in programme['programme']['reunions']:
            # Match partiel sur l'hippodrome (ex: "COMPIEGNE" dans "COMPIEGNE")
            if hippodrome_name.upper() in reunion['libelle'].upper() or reunion['libelle'].upper() in hippodrome_name.upper():
                r_num = reunion['numOfficiel']
                
                for course in reunion['courses']:
                    c_num = course['numOrdre']
                    
                    # Vérifier les participants de cette course
                    part_resp = requests.get(f"{base_url}/{formatted_date}/R{r_num}/C{c_num}/participants")
                    partants = part_resp.json()
                    
                    for p in partants.get('participants', []):
                        if horse_name.upper() in p['nom'].upper():
                            # Cheval trouvé ! On cherche ses rapports
                            return fetch_dividendes(formatted_date, r_num, c_num, p['numProno'])
    except Exception as e:
        return f"Erreur API: {str(e)[:20]}"
    
    return "Non trouvé"

def fetch_dividendes(date, r, c, num_p):
    url = f"https://online.pmu.fr/rest/client/7/programme/{date}/R{r}/C{c}/rapports"
    try:
        data = requests.get(url).json()
        sg, sp = 0, 0
        for r_type in data.get('rapports', []):
            if r_type['typePari'] == 'SIMPLE_GAGNANT':
                for div in r_type['dividendes']:
                    if str(num_p) in div['combinaison']: sg = div['dividende'] / 100
            if r_type['typePari'] == 'SIMPLE_PLACE':
                for div in r_type['dividendes']:
                    if str(num_p) in div['combinaison']: sp = div['dividende'] / 100
        
        if sg > 0: return f"Gagnant: {sg}€ | Placé: {sp}€"
        if sp > 0: return f"Placé: {sp}€"
        return "Pas de rapport"
    except:
        return "Erreur rapports"

# --- RESTE DU SCRIPT ORIGINAL (MODIFIÉ) ---

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
        
        # Gestion des Cookies
        try:
            cookie_btn = wait.until(EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler")))
            driver.execute_script("arguments[0].click();", cookie_btn)
            log("🍪 Cookies validés.")
        except: pass

        # Authentification
        log("🔑 Authentification...")
        login_btn = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='login'], .user-link")))
        driver.execute_script("arguments[0].click();", login_btn)

        email_el = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "input[type='email'], input[name='username']")))
        for char in EMAIL_SENDER: email_el.send_keys(char)
        
        btn_next = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Next')] | //button[@id='next']")))
        driver.execute_script("arguments[0].click();", btn_next)
        time.sleep(6)

        pwd_el = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "input[type='password'], #password")))
        for char in FG_PASSWORD:
            pwd_el.send_keys(char)
            time.sleep(0.05)
        
        btn_submit = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Sign in')] | //button[@id='next']")))
        driver.execute_script("arguments[0].click();", btn_submit)
        
        log("⏳ Stabilisation (20s)...")
        time.sleep(20)

        # Analyse des Gains
        for trainer_url in URLS_ENTRAINEURS:
            log(f"🚀 Analyse : {trainer_url.split('/')[-1][:15]}...")
            driver.get(trainer_url)
            time.sleep(10)

            try:
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
                        match_place = re.search(r'^([1-4])$', place)
                        if match_place:
                            rank = match_place.group(1)
                            
                            # --- APPEL À L'API PMU POUR LE RAPPORT PARIEUR ---
                            log(f"🔍 Recherche rapport PMU pour {horse_name}...")
                            betting_rapport = get_pmu_rapports(raw_date, hippodrome, horse_name)
                            
                            line = (f"🏆 *{horse_name}* ({rank}e)\n"
                                    f"📅 {raw_date} | 📍 {hippodrome}\n"
                                    f"💰 Alloc. : {prize}€\n"
                                    f"📊 Rapports : *{betting_rapport}*\n"
                                    f"👤 Entr: {trainer_name}")
                            
                            final_report.append(line)
                            log(f"✅ Performance retenue : {horse_name} ({betting_rapport})")
            except Exception as e:
                log(f"⚠️ Erreur entraîneur : {str(e)[:50]}")

        # Envoi Final
        if final_report:
            header = f"💰 *TOP PERFORMANCES & RAPPORTS*\n\n"
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
