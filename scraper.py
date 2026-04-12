import os
import re
import json
import time
import requests
from datetime import datetime
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# --- CONFIGURATION ---
URL_HOME = "https://www.france-galop.com/fr"
URLS_ENTRAINEURS = [
    "https://www.france-galop.com/fr/entraineur/Z1FxYXQ3cFJyM0ZlUitJQTlmUTNiUT09#partants",
    "https://www.france-galop.com/fr/entraineur/U0VNb0JtQlZ1bUphYndFTnJjSzg4dz09#partants"
]

COOKIE_FILE = "cookies.json"
FG_PASSWORD = os.getenv("FG_PASSWORD")
EMAIL_SENDER = os.getenv("EMAIL_SENDER")
GREEN_API_URL = os.getenv("GREEN_API_URL")

def log(message):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")

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

def translate_performance(musique):
    if not musique or musique == "N/A": return "Aucune performance récente"
    mapping_disc = {'p': 'Plat', 's': 'Steeple', 'h': 'Haies', 'c': 'Cross', 'a': 'Attelé', 'm': 'Monté'}
    mapping_inc = {'A': 'Arrêté', 'T': 'Tombé', 'D': 'Disqualifié', 'R': 'Rétrogradé'}
    parts = re.split(r'(\(\d+\))', musique)
    decoded_parts = []
    current_year = str(datetime.now().year)
    for part in parts:
        if re.match(r'\(\d+\)', part):
            current_year = "20" + part.strip('()')
            continue
        matches = re.findall(r'([0-9A-Z])([a-z])', part)
        for rank, disc in matches:
            d_name = mapping_disc.get(disc, disc)
            r_text = f"{rank}er" if rank == "1" else (f"{rank}e" if rank.isdigit() else mapping_inc.get(rank, rank))
            if rank == "0": r_text = "Non placé"
            decoded_parts.append(f"{r_text} en {d_name} ({current_year})")
    return " | ".join(decoded_parts[:3])

def clean_text(text):
    if not text: return ""
    cleaned = re.sub(r"[^a-zA-Z0-9/:\. '()]", '', text)
    return " ".join(cleaned.split()).strip()

def get_pure_horse_name(full_name):
    pure_name = re.split(r'\s[A-Z]\.', full_name)[0] 
    return pure_name.strip()

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

def run_scraper():
    chrome_version = get_chrome_main_version()
    options = uc.ChromeOptions()
    options.add_argument("--headless=new") # Obligatoire pour GitHub Actions
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
   
    driver = uc.Chrome(options=options, version_main=chrome_version)
    wait = WebDriverWait(driver, 25)
    today = datetime.now().strftime("%d/%m/%Y")
    today_results = []

    try:
        log("🌐 Accès France Galop...")
        driver.get(URL_HOME)
        
        # Tentative de chargement de session
        if load_cookies(driver):
            driver.refresh()
            time.sleep(5)
        
        # Vérification si connexion nécessaire
        try:
            # Si le bouton de connexion est toujours présent, on se connecte
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='login']")))
            log("🔑 Session expirée ou inexistante. Authentification...")
            
            # (Le processus de login reste identique mais sans les time.sleep inutiles)
            login_btn = driver.find_element(By.CSS_SELECTOR, "a[href*='login'], .user-link")
            driver.execute_script("arguments[0].click();", login_btn)

            email_el = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "input[type='email']")))
            email_el.send_keys(EMAIL_SENDER)
            driver.find_element(By.XPATH, "//button[contains(., 'Next')] | //button[@id='next']").click()
            
            pwd_el = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "input[type='password']")))
            pwd_el.send_keys(FG_PASSWORD)
            wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Sign in')] | //button[@id='next']"))).click()
            
            # Attendre la redirection finale avant de sauvegarder
            wait.until(EC.presence_of_element_located((By.CLASS_NAME, "user-name")))
            save_cookies(driver)
        except:
            log("✅ Session déjà active.")

        # Extraction (Logique simplifiée pour la performance)
        seen_runners = set()
        for trainer_url in URLS_ENTRAINEURS:
            driver.get(trainer_url)
            # Attendre spécifiquement le tableau des partants
            rows = wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "#partants_entraineur tbody tr")))
            
            trainer_name = clean_text(driver.find_element(By.TAG_NAME, "h1").text).replace("ENTRAINEUR", "").strip()
            
            runners_to_process = []
            for row in rows:
                if today in row.text:
                    cells = row.find_elements(By.TAG_NAME, "td")
                    full_name = clean_text(cells[0].text)
                    url_course = row.find_element(By.CSS_SELECTOR, "a[href*='/course/']").get_attribute("href")
                    
                    if f"{full_name}_{url_course}" not in seen_runners:
                        seen_runners.add(f"{full_name}_{url_course}")
                        runners_to_process.append({
                            'pure_name': get_pure_horse_name(full_name),
                            'url': url_course,
                            'trainer': trainer_name,
                            'label': clean_text(cells[4].text)
                        })

            for r in runners_to_process:
                driver.get(r['url'])
                try:
                    # Extraction directe via sélecteurs plus précis
                    details_txt = wait.until(EC.presence_of_element_located((By.CLASS_NAME, "course-detail"))).text
                    heure = re.search(r'(\d{1,2}h\d{2})', details_txt).group(1) if re.search(r'(\d{1,2}h\d{2})', details_txt) else "00:00"
                    
                    # On cherche la ligne du cheval par son nom en minuscules
                    cheval_row = driver.find_element(By.XPATH, f"//tr[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{r['pure_name'].lower()}')]")
                    cells_c = cheval_row.find_elements(By.TAG_NAME, "td")
                    
                    num_cheval = "".join(filter(str.isdigit, cells_c[0].text))
                    raw_perf = cells_c[11].text if len(cells_c) > 11 else "N/A"
                    
                    msg = (f"🏇 *{r['pure_name']}* (N°{num_cheval})\n"
                           f"📍 C{heure}\n"
                           f"📊 *Perfs :* {translate_performance(raw_perf)}\n"
                           f"📝 {r['label']}\n"
                           f"👤 Entr: {r['trainer']}")
                    today_results.append(msg)
                except Exception as e:
                    log(f"⚠️ Erreur détails {r['pure_name']}")

        if today_results:
            send_whatsapp(f"✅ *PARTANTS DU JOUR ({today})*\n\n" + "\n\n---\n\n".join(today_results))
        else:
            log("📝 Aucun partant détecté.")

    except Exception as e:
        log(f"💥 ERREUR : {e}")
    finally:
        driver.quit()

if __name__ == "__main__":
    run_scraper()
