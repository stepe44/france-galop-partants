import os
import re
import time
import requests
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
# ... (imports Selenium standards)
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

# --- OUTILS DE TRAITEMENT (Issus de scraper 2.py) ---
def log(message):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")

def translate_performance(musique):
    if not musique or musique == "N/A": return "Aucune performance récente"
    mapping_disc = {'p': 'Plat', 's': 'Steeple', 'h': 'Haies', 'c': 'Cross', 'a': 'Attelé', 'm': 'Monté'}
    mapping_inc = {'A': 'Arrêté', 'T': 'Tombé', 'D': 'Disqualifié', 'R': 'Rétrogradé'}
    parts = re.split(r'(\(\d+\))', musique)
    decoded_parts = []
    current_year = "2026"
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
    pure_name = re.split(r'\s\d\sa\.', pure_name)[0] 
    return pure_name.strip()

def normalize_for_xpath(text):
    return re.sub(r'[^a-z0-9]', '', text.lower())

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
    chrome_options = Options()
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36")
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    
    wait = WebDriverWait(driver, 35)
    today = datetime.now().strftime("%d/%m/%Y")
    today_results = []
    seen_runners = set()

    try:
        log("🌐 Initialisation France Galop...")
        driver.get(URL_HOME)
        time.sleep(5)
        
        # 1. Cookies
        try:
            wait.until(EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler"))).click()
            log("🍪 Cookies validés.")
        except: pass

        # 2. Connexion (Méthode scraper tomorrow.py)
        log("🔑 Authentification Azure AD...")
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
        
        log("⏳ Stabilisation session (20s)...")
        time.sleep(20)

        # 3. Extraction
        for trainer_url in URLS_ENTRAINEURS:
            log(f"🚀 Analyse : {trainer_url.split('/')[-1][:15]}...")
            driver.get(trainer_url)
            time.sleep(8)
            
            # Switch Onglet Partants
            try:
                tab = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='#partants']")))
                driver.execute_script("arguments[0].click();", tab)
                time.sleep(5)
                
                trainer_name = clean_text(driver.find_element(By.TAG_NAME, "h1").text).replace("ENTRAINEUR", "").strip()
                rows = driver.find_elements(By.CSS_SELECTOR, "#partants_entraineur tbody tr")
                
                runners_to_process = []
                for row in rows:
                    txt = row.text
                    if today in txt: # Filtrage strict sur AUJOURD'HUI
                        cells = row.find_elements(By.TAG_NAME, "td")
                        full_name = clean_text(cells[0].text)
                        url_course = row.find_element(By.CSS_SELECTOR, "a[href*='/course/']").get_attribute("href")
                        
                        if f"{full_name}_{url_course}" not in seen_runners:
                            seen_runners.add(f"{full_name}_{url_course}")
                            runners_to_process.append({
                                'full_name': full_name,
                                'pure_name': get_pure_horse_name(full_name),
                                'url': url_course,
                                'trainer': trainer_name,
                                'label': clean_text(cells[4].text)
                            })

                # Détails profonds pour chaque partant du jour
                for r in runners_to_process:
                    log(f"   🐎 Détails : {r['pure_name']}")
                    driver.get(r['url'])
                    time.sleep(5)
                    
                    try:
                        # Hippo, Heure, N° Course
                        details = driver.find_elements(By.CSS_SELECTOR, ".course-detail p")
                        heure, hippo, n_course = "00:00", "Inconnu", "?"
                        for p in details:
                            p_txt = p.text.strip()
                            if "2026" in p_txt:
                                m_h = re.search(r'(\d{1,2}h\d{2})', p_txt)
                                if m_h: heure = m_h.group(1)
                                m_n = re.search(r'(\d+)(?:er|ère|ème|eme)', p_txt, re.IGNORECASE)
                                if m_n: n_course = m_n.group(1)
                                if "," in p_txt: hippo = clean_text(p_txt.split(",")[-1])
                                break
                        
                        # Musique et Numéro
                        search_key = normalize_for_xpath(r['pure_name'])
                        xpath_row = f"//tr[contains(translate(translate(., \"' \", ''), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{search_key}')]"
                        row_cheval = wait.until(EC.presence_of_element_located((By.XPATH, xpath_row)))
                        cells_c = row_cheval.find_elements(By.TAG_NAME, "td")
                        
                        num_cheval = "".join(filter(str.isdigit, cells_c[0].text))
                        raw_perf = clean_text(cells_c[11].text) if len(cells_c) > 11 else "N/A"
                        
                        msg = (f"🏇 *{r['pure_name']}* (N°{num_cheval})\n"
                               f"📍 {hippo} - C{n_course} à {heure}\n"
                               f"📊 *Musique :* {translate_performance(raw_perf)}\n"
                               f"📝 {r['label']}\n"
                               f"👤 Entr: {r['trainer']}")
                        
                        today_results.append(msg)
                    except Exception as e:
                        log(f"      ⚠️ Erreur détails {r['pure_name']} : {str(e)[:50]}")

            except Exception as e:
                log(f"⚠️ Erreur entraîneur : {str(e)[:50]}")

        # 4. Rapport
        if today_results:
            final_msg = f"✅ *PARTANTS DU JOUR ({today})*\n\n" + "\n\n---\n\n".join(today_results)
            send_whatsapp(final_msg)
        else:
            log("📝 Aucun partant détecté pour aujourd'hui.")

    except Exception as e:
        log(f"💥 ERREUR CRITIQUE : {e}")
    finally:
        driver.quit()
        log("🏁 Fin.")

if __name__ == "__main__":
    run_scraper()
