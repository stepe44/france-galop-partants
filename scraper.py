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

def clean_text(text):
    if not text: return ""
    cleaned = re.sub(r"[^a-zA-Z0-9/:\. '()]", '', text)
    return " ".join(cleaned.split()).strip()

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

def send_whatsapp_notification(content):
    if not GREEN_API_URL: return
    payload = {"chatId": "33678723278-1540128478@g.us", "message": content}
    try:
        requests.post(GREEN_API_URL, json=payload, timeout=15)
        log("📲 Notification WhatsApp envoyée.")
    except Exception as e:
        log(f"❌ Erreur WhatsApp : {e}")

def login_procedure(driver, wait, i):
    """Effectue l'authentification blindée sur Azure AD."""
    log("🔑 Détection de l'écran de connexion. Début de l'authentification...")
    try:
        # 1. Saisie de l'Email
        email_el = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[placeholder*='Email'], input[name='username']")))
        email_el.clear()
        for char in EMAIL_SENDER:
            email_el.send_keys(char)
        driver.execute_script("arguments[0].dispatchEvent(new Event('blur', { bubbles: true }));", email_el)
        time.sleep(1)
        driver.execute_script("arguments[0].click();", driver.find_element(By.CSS_SELECTOR, "button[type='submit'], .next, #next"))
        log("📧 Identifiant envoyé.")

        # 2. Saisie du Mot de Passe (Blindée contre l'erreur rouge)
        time.sleep(5)
        pwd_el = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='password']")))
        pwd_el.clear()
        for char in FG_PASSWORD:
            pwd_el.send_keys(char)
            time.sleep(0.05) # Frappe simulant un humain
        
        # Validation forcée des événements JS pour Azure
        driver.execute_script("""
            arguments[0].dispatchEvent(new Event('input', { bubbles: true }));
            arguments[0].dispatchEvent(new Event('change', { bubbles: true }));
            arguments[0].dispatchEvent(new Event('blur', { bubbles: true }));
        """, pwd_el)
        
        driver.save_screenshot(f"debug_pwd_typed_{i}.png") # Vérification visuelle du champ rempli
        
        btn_login = driver.find_element(By.CSS_SELECTOR, "button[type='submit'], #next, .sign-in")
        driver.execute_script("arguments[0].click();", btn_login)
        log("🔒 Mot de passe envoyé. Attente de redirection...")
        time.sleep(15)
        return True
    except Exception as e:
        log(f"⚠️ Erreur lors de la connexion : {str(e)[:50]}")
        return False

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
            log(f"🌐 --- ANALYSE : {trainer_url.split('/')[-1]} ---")
            driver.get(trainer_url)
            time.sleep(5)

            # Gestion de l'authentification in-situ
            if "ciamlogin.com" in driver.current_url or driver.find_elements(By.CSS_SELECTOR, "input[name='username']"):
                login_procedure(driver, wait, i)
                # Double vérification si Azure AD renvoie une erreur ou reste sur la page
                if "ciamlogin.com" in driver.current_url:
                    log("🔄 Tentative de retour forcé vers l'URL entraîneur...")
                    driver.get(trainer_url)
                    time.sleep(8)

            # Vérification finale de la page
            driver.save_screenshot(f"final_check_trainer_{i}.png")
            log(f"📄 URL actuelle : {driver.current_url}")

            try:
                # Activation forcée de l'onglet 'Partants'
                tab = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "a[href*='#partants']")))
                driver.execute_script("arguments[0].click();", tab)
                time.sleep(3)
                
                # Attente du tableau de données
                wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "#partants_entraineur tbody tr")))
                rows = driver.find_elements(By.CSS_SELECTOR, "#partants_entraineur tbody tr")
                log(f"✅ {len(rows)} chevaux détectés dans le tableau.")

                trainer_name = clean_text(driver.find_element(By.CSS_SELECTOR, "h1").text).replace("ENTRAINEUR", "").strip()

                for row in rows:
                    txt = row.text
                    if today in txt or tomorrow in txt:
                        cells = row.find_elements(By.TAG_NAME, "td")
                        full_name = clean_text(cells[0].text)
                        url_course = row.find_element(By.CSS_SELECTOR, "a[href*='/course/']").get_attribute("href")
                        
                        if f"{full_name}_{url_course}" not in seen_runners:
                            seen_runners.add(f"{full_name}_{url_course}")
                            # Ajout au rapport final
                            horse_name = re.split(r'\s[A-Z]\.', full_name)[0].strip()
                            today_results.append(f"🏇 *{horse_name}* (Entr: {trainer_name})")
            except Exception as e:
                log(f"❌ Impossible de charger les données pour cet entraîneur : {str(e)[:50]}")

        if today_results:
            log(f"📤 {len(today_results)} partants trouvés. Envoi du rapport...")
            final_msg = f"✅ *PARTANTS DU {today}*\n\n" + "\n".join(today_results)
            send_whatsapp_notification(final_msg)
        else:
            log("📝 Aucun partant détecté pour aujourd'hui ou demain.")

    except Exception as e:
        log(f"💥 ERREUR CRITIQUE : {e}")
        driver.save_screenshot("fatal_error.png")
    finally:
        driver.quit()
        log("🏁 Session terminée.")

if __name__ == "__main__":
    run_scraper()
