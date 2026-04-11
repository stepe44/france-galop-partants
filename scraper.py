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
    wait = WebDriverWait(driver, 30)
    
    today = datetime.now().strftime("%d/%m/%Y")
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%d/%m/%Y")
    today_results = []
    seen_runners = set()

    try:
        for i, trainer_url in enumerate(URLS_ENTRAINEURS):
            log(f"🌐 Accès direct à l'entraîneur : {trainer_url}")
            driver.get(trainer_url)
            time.sleep(5)

            # --- DÉTECTION ÉCRAN DE CONNEXION ---
            if "ciamlogin.com" in driver.current_url or driver.find_elements(By.CSS_SELECTOR, "input[name='username']"):
                log("🔑 Écran de connexion détecté sur la page. Authentification en cours...")
                
                # Saisie Email
                email_el = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[placeholder*='Email'], input[name='username']")))
                email_el.clear()
                for char in EMAIL_SENDER:
                    email_el.send_keys(char)
                driver.execute_script("arguments[0].dispatchEvent(new Event('blur', { bubbles: true }));", email_el)
                
                btn_next = driver.find_element(By.CSS_SELECTOR, "button[type='submit'], .next, #next")
                driver.execute_script("arguments[0].click();", btn_next)
                
                # Saisie Password
                time.sleep(4)
                pwd_el = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='password']")))
                driver.execute_script(f"arguments[0].value = '{FG_PASSWORD}';", pwd_el)
                driver.execute_script("arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", pwd_el)
                
                btn_login = driver.find_element(By.CSS_SELECTOR, "button[type='submit'], #next")
                driver.execute_script("arguments[0].click();", btn_login)
                
                log("⏳ Attente de redirection post-connexion...")
                time.sleep(15)

            # --- VÉRIFICATION DU TABLEAU ---
            driver.save_screenshot(f"check_after_login_trainer_{i}.png")
            
            try:
                # Force le clic sur l'onglet partants
                tab = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "a[href*='#partants']")))
                driver.execute_script("arguments[0].click();", tab)
                time.sleep(3)
                
                wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "#partants_entraineur tbody tr")))
                log("✅ Tableau chargé avec succès.")
            except:
                log(f"⚠️ Impossible de charger le tableau pour {trainer_url}. Session peut-être invalide.")
                continue

            # Extraction des données
            rows = driver.find_elements(By.CSS_SELECTOR, "#partants_entraineur tbody tr")
            trainer_name = driver.find_element(By.CSS_SELECTOR, "h1").text.replace("ENTRAINEUR", "").strip()

            for row in rows:
                txt = row.text
                if today in txt or tomorrow in txt:
                    cells = row.find_elements(By.TAG_NAME, "td")
                    full_name = cells[0].text.strip()
                    url = row.find_element(By.CSS_SELECTOR, "a[href*='/course/']").get_attribute("href")
                    
                    if f"{full_name}_{url}" not in seen_runners:
                        seen_runners.add(f"{full_name}_{url}")
                        # Extraction simplifiée pour ce log
                        today_results.append(f"🏇 *{get_pure_horse_name(full_name)}* - Entr: {trainer_name}")

        if today_results:
            log(f"📤 {len(today_results)} partants trouvés.")
            # Intégrer ici votre fonction d'envoi WhatsApp
        else:
            log("📝 Aucun partant détecté aujourd'hui.")

    except Exception as e:
        log(f"💥 ERREUR : {e}")
        driver.save_screenshot("fatal_error_direct.png")
    finally:
        driver.quit()
        log("🏁 Fin de session.")

if __name__ == "__main__":
    run_scraper()
