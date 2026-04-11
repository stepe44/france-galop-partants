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
            decoded_parts.append(f"{r_text} en {d_name} ({current_year})")
    return " | ".join(decoded_parts[:3])

def clean_text(text):
    if not text: return ""
    cleaned = re.sub(r"[^a-zA-Z0-9/:\. '()]", '', text)
    return " ".join(cleaned.split()).strip()

def get_pure_horse_name(full_name):
    return re.split(r'\s[A-Z]\.', full_name)[0].strip()

def normalize_for_xpath(text):
    return re.sub(r'[^a-z0-9]', '', text.lower())

def send_whatsapp_notification(content):
    if not GREEN_API_URL: return
    payload = {"chatId": "33678723278-1540128478@g.us", "message": content}
    try:
        requests.post(GREEN_API_URL, json=payload, timeout=15)
        log("📲 WhatsApp envoyé.")
    except Exception as e:
        log(f"❌ Erreur WhatsApp : {e}")

def run_scraper():
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36")
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    wait = WebDriverWait(driver, 30)
    
    today = datetime.now().strftime("%d/%m/%Y")
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%d/%m/%Y")
    today_results = []
    seen_runners = set()

    try:
        log(f"🌐 Navigation : {URL_HOME}")
        driver.get(URL_HOME)
        
        try:
            wait.until(EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler"))).click()
        except: pass

        log("🔑 Connexion...")
        login_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "a[href*='login'], .user-link, .login")))
        driver.execute_script("arguments[0].click();", login_btn)

        # --- ÉTAPE 1 : EMAIL ---
        log("📧 Saisie Email...")
        time.sleep(5)
        email_el = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[placeholder*='Email'], input[name='username']")))
        
        email_el.clear()
        for char in EMAIL_SENDER:
            email_el.send_keys(char)
            time.sleep(0.1)
            
        driver.execute_script("""
            arguments[0].dispatchEvent(new Event('input', { bubbles: true }));
            arguments[0].dispatchEvent(new Event('change', { bubbles: true }));
            arguments[0].dispatchEvent(new Event('blur', { bubbles: true }));
        """, email_el)
        
        time.sleep(1)
        btn_next = driver.find_element(By.CSS_SELECTOR, "button[type='submit'], .next, #next")
        driver.execute_script("arguments[0].click();", btn_next)
        
        # --- ÉTAPE 2 : PASSWORD ---
        time.sleep(4)
        log("🔒 Saisie Password...")
        pwd_el = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='password']")))
        driver.execute_script(f"arguments[0].value = '{FG_PASSWORD}';", pwd_el)
        driver.execute_script("arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", pwd_el)
        
        btn_login = driver.find_element(By.CSS_SELECTOR, "button[type='submit'], #next")
        driver.execute_script("arguments[0].click();", btn_login)

        # --- FIXATION DE SESSION (Crucial) ---
        log("⏳ Fixation de la session (12s)...")
        time.sleep(12)
        driver.get(URL_HOME)
        time.sleep(5)
        driver.save_screenshot("check_session_home.png")

        # --- ÉTAPE 3 : SCRAPING ---
        for i, trainer_url in enumerate(URLS_ENTRAINEURS):
            log(f"🌐 Analyse entraîneur : {trainer_url.split('/')[-1][:20]}")
            driver.get(trainer_url)
            time.sleep(7) # Plus de temps pour charger le JS
            
            # Re-tentative si redirection login
            if "ciamlogin.com" in driver.current_url:
                log("🚨 Redirection Login ! Re-tentative...")
                driver.get(trainer_url)
                time.sleep(5)
            
            driver.save_screenshot(f"check_trainer_{i}.png")

            rows = driver.find_elements(By.CSS_SELECTOR, "#partants_entraineur tbody tr")
            if not rows:
                log(f"⚠️ Aucun tableau pour {trainer_url}")
                continue

            trainer_name = clean_text(driver.find_element(By.CSS_SELECTOR, "h1").text).replace("ENTRAINEUR", "").strip()

            runners = []
            for row in rows:
                txt = row.text
                if today in txt or tomorrow in txt:
                    cells = row.find_elements(By.TAG_NAME, "td")
                    if not cells: continue
                    full_name = clean_text(cells[0].text)
                    try:
                        url = row.find_element(By.CSS_SELECTOR, "a[href*='/course/']").get_attribute("href")
                        if f"{full_name}_{url}" not in seen_runners:
                            seen_runners.add(f"{full_name}_{url}")
                            runners.append({'date': today if today in txt else tomorrow, 'full_name': full_name, 'pure_name': get_pure_horse_name(full_name), 'url': url, 'trainer': trainer_name, 'course_label': clean_text(cells[4].text)})
                    except: continue

            for r in runners:
                log(f"   🐎 Extraction : {r['pure_name']}")
                driver.get(r['url'])
                time.sleep(3)
                try:
                    search_key = normalize_for_xpath(r['pure_name'])
                    xpath_row = f"//tr[contains(translate(translate(., \"' \", ''), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{search_key}')]"
                    row_cheval = wait.until(EC.presence_of_element_located((By.XPATH, xpath_row)))
                    cells = row_cheval.find_elements(By.TAG_NAME, "td")
                    num_cheval = "".join(filter(str.isdigit, cells[0].text))
                    raw_perf = clean_text(cells[-2].text)
                    decoded_perf = translate_performance(raw_perf)
                    
                    msg_line = (f"🏇 *{r['pure_name']}* (N°{num_cheval})\n📊 *Musique :* {decoded_perf}\n👤 Entr: {r['trainer']}")
                    if r['date'] == today: today_results.append(msg_line)
                except: pass

        if today_results:
            final_msg = f"✅ *PARTANTS DU JOUR ({today})*\n\n" + "\n\n---\n\n".join(today_results)
            send_whatsapp_notification(final_msg)
        else:
            log("📝 Aucun partant pour aujourd'hui.")

    except Exception as e:
        log(f"💥 ERREUR : {e}")
        driver.save_screenshot("debug_fatal_error.png")
    finally:
        driver.quit()
        log("🏁 Fin.")

if __name__ == "__main__":
    run_scraper()
