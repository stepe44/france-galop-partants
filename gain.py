import os
import re
import json
import time
import requests
import subprocess
from datetime import datetime, timedelta
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# --- CONFIGURATION ---
URL_HOME = "https://www.france-galop.com/fr"
URLS_ENTRAINEURS = [
    "https://www.france-galop.com/fr/entraineur/Z1FxYXQ3cFJyM0ZlUitJQTlmUTNiUT09#dernieres-courses",
    "https://www.france-galop.com/fr/entraineur/U0VNb0JtQlZ1bUphYndFTnJjSzg4dz09#dernieres-courses"
]

COOKIE_FILE = "cookies.json"
FG_PASSWORD = os.getenv("FG_PASSWORD")
EMAIL_SENDER = os.getenv("EMAIL_SENDER")
GREEN_API_URL = os.getenv("GREEN_API_URL")

def log(message):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")

def get_chrome_main_version():
    try:
        output = subprocess.check_output(['google-chrome', '--version']).decode('utf-8')
        version_str = output.strip().split()[2]
        return int(version_str.split('.')[0])
    except Exception as e:
        log(f"⚠️ Impossible de déterminer la version de Chrome : {e}")
        return None

def save_cookies(driver):
    with open(COOKIE_FILE, "w") as f:
        json.dump(driver.get_cookies(), f)
    log("💾 Cookies sauvegardés.")

def load_cookies(driver):
    if os.path.exists(COOKIE_FILE):
        with open(COOKIE_FILE, "r") as f:
            cookies = json.load(f)
            for cookie in cookies:
                driver.add_cookie(cookie)
        log("🍪 Cookies chargés depuis le cache.")
        return True
    return False

def clean_text(text):
    if not text: return "N/A"
    return " ".join(text.split()).strip()

def parse_date(date_str):
    try:
        return datetime.strptime(date_str.strip(), "%d/%m/%Y")
    except:
        return None

def send_whatsapp(message):
    if not GREEN_API_URL:
        log("⚠️ GREEN_API_URL manquante.")
        return
    payload = {"chatId": "33678723278-1540128478@g.us", "message": message}
    try:
        response = requests.post(GREEN_API_URL, json=payload, timeout=15)
        if response.status_code == 200: log("📲 Notification WhatsApp envoyée.")
    except Exception as e:
        log(f"❌ Erreur WhatsApp : {e}")

# --- PMU API HELPERS ---
def fetch_json_with_driver(driver, url):
    """Utilise le navigateur camouflé pour lire l'API PMU et contourner le blocage."""
    try:
        driver.get(url)
        time.sleep(1) # Laisse le temps au navigateur de rendre le JSON brut
        json_text = driver.find_element(By.TAG_NAME, "pre").text
        return json.loads(json_text)
    except Exception as e:
        return None

def get_pmu_rapports(driver, date_str, hippodrome_name, horse_name):
    """Recherche les rapports PMU via l'API en utilisant le driver."""
    formatted_date = date_str.replace('/', '')
    base_url = "https://online.pmu.fr/rest/client/7/programme"
    
    try:
        # 1. Récupérer le programme du jour
        programme = fetch_json_with_driver(driver, f"{base_url}/{formatted_date}")
        if not programme or 'programme' not in programme: 
            return "Indisponible"
        
        # 2. Chercher la réunion et la course
        for reunion in programme['programme'].get('reunions', []):
            if hippodrome_name.upper() in reunion['libelle'].upper() or reunion['libelle'].upper() in hippodrome_name.upper():
                r_num = reunion['numOfficiel']
                
                for course in reunion.get('courses', []):
                    c_num = course['numOrdre']
                    
                    # Vérifier les participants de cette course
                    partants = fetch_json_with_driver(driver, f"{base_url}/{formatted_date}/R{r_num}/C{c_num}/participants")
                    if not partants: continue
                    
                    for p in partants.get('participants', []):
                        if horse_name.upper() in p.get('nom', '').upper():
                            return fetch_dividendes(driver, formatted_date, r_num, c_num, p['numProno'])
                            
    except Exception as e:
        return f"Erreur API: {str(e)[:20]}"
    
    return "Non trouvé"

def fetch_dividendes(driver, date, r, c, num_p):
    url = f"https://online.pmu.fr/rest/client/7/programme/{date}/R{r}/C{c}/rapports"
    try:
        data = fetch_json_with_driver(driver, url)
        if not data: return "Erreur rapports"
        
        sg, sp = 0, 0
        for r_type in data.get('rapports', []):
            if r_type['typePari'] == 'SIMPLE_GAGNANT':
                for div in r_type.get('dividendes', []):
                    if str(num_p) in div.get('combinaison', ''): 
                        sg = div['dividende'] / 100
            if r_type['typePari'] == 'SIMPLE_PLACE':
                for div in r_type.get('dividendes', []):
                    if str(num_p) in div.get('combinaison', ''): 
                        sp = div['dividende'] / 100
        
        if sg > 0: return f"Gagnant: {sg}€ | Placé: {sp}€"
        if sp > 0: return f"Placé: {sp}€"
        return "Pas de rapport"
    except:
        return "Erreur rapports"

# --- MAIN ---
def run_scraper_history():
    chrome_version = get_chrome_main_version()
    options = uc.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
   
    driver = uc.Chrome(options=options, version_main=chrome_version)
    wait = WebDriverWait(driver, 25)
    
    today = datetime.now()
    start_date = today - timedelta(days=7)
    final_report = []

    try:
        log("🌐 Accès France Galop...")
        driver.get(URL_HOME)
        
        if load_cookies(driver):
            driver.refresh()
            time.sleep(5)
            
        try:
            cookie_btn = wait.until(EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler")))
            cookie_btn.click()
            time.sleep(2)
        except:
            pass
        
        login_elements = driver.find_elements(By.CSS_SELECTOR, "a[href*='login'], .user-link")
        if login_elements:
            log("🔑 Authentification requise...")
            try:
                driver.execute_script("arguments[0].click();", login_elements[0])
                email_el = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "input[type='email']")))
                email_el.send_keys(EMAIL_SENDER)
                driver.find_element(By.XPATH, "//button[contains(., 'Next')] | //button[@id='next']").click()
                
                pwd_el = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "input[type='password']")))
                pwd_el.send_keys(FG_PASSWORD)
                wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Sign in')] | //button[@id='next']"))).click()
                
                wait.until(EC.presence_of_element_located((By.CLASS_NAME, "user-name")))
                save_cookies(driver)
                log("✅ Connexion réussie.")
            except Exception as e:
                driver.save_screenshot("erreur_login_azure_gain.png")
                raise Exception("Impossible de passer l'écran de connexion.")
        else:
            log("✅ Session active via cookies.")

        # ==========================================
        # PHASE A : EXTRACTION DES PERFORMANCES (TOP 4)
        # ==========================================
        races_to_process = []
        
        for trainer_url in URLS_ENTRAINEURS:
            log(f"🚀 Analyse de la fiche : {trainer_url.split('/')[-1][:15]}...")
            driver.get(trainer_url)
            time.sleep(5)

            try:
                # Activation de l'onglet 'Dernières courses'
                tab = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='#dernieres-courses']")))
                driver.execute_script("arguments[0].click();", tab)
                time.sleep(3)
                
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
                            races_to_process.append({
                                'rank': match_place.group(1),
                                'date': raw_date,
                                'horse': horse_name,
                                'hippo': hippodrome,
                                'prize': prize,
                                'trainer': trainer_name
                            })
                            log(f"   ✅ Retenu : {horse_name} ({match_place.group(1)}e)")
            except Exception as e:
                log(f"⚠️ Erreur sur cet entraîneur : {str(e)[:50]}")

        # ==========================================
        # PHASE B : RECHERCHE DES RAPPORTS PARIEURS (PMU)
        # ==========================================
        for race in races_to_process:
            log(f"   🔍 Recherche rapport PMU pour {race['horse']}...")
            
            # Appel de la nouvelle fonction utilisant l'API PMU via le driver
            rapport_parieur = get_pmu_rapports(
                driver=driver,
                date_str=race['date'],
                hippodrome_name=race['hippo'],
                horse_name=race['horse']
            )

            # Construction du message
            line = (f"🏆 *{race['horse']}* ({race['rank']}e)\n"
                    f"📅 {race['date']} | 📍 {race['hippo']}\n"
                    f"💰 Alloc: {race['prize']}€\n"
                    f"📈 PMU: {rapport_parieur}\n"
                    f"👤 Entr: {race['trainer']}")
            final_report.append(line)

        # ==========================================
        # PHASE C : ENVOI WHATSAPP
        # ==========================================
        if final_report:
            header = f"💰 *TOP PERFORMANCES (7 derniers jours)*\n\n"
            full_message = header + "\n\n---\n\n".join(final_report)
            send_whatsapp(full_message)
            log("✅ Rapport hebdomadaire envoyé.")
        else:
            log("📝 Aucune performance de top 4 trouvée.")

    except Exception as e:
        log(f"💥 ERREUR CRITIQUE : {e}")
    finally:
        driver.quit()
        log("🏁 Session terminée.")

if __name__ == "__main__":
    run_scraper_history()
