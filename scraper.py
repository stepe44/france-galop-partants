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
URL_LOGIN = "https://www.france-galop.com/fr/login"
URLS_ENTRAINEURS = [
    "https://www.france-galop.com/fr/entraineur/Z1FxYXQ3cFJyM0ZlUitJQTlmUTNiUT09#partants",
    "https://www.france-galop.com/fr/entraineur/U0VNb0JtQlZ1bUphYndFTnJjSzg4dz09#partants"
]

FG_PASSWORD = os.getenv("FG_PASSWORD")
EMAIL_SENDER = os.getenv("EMAIL_SENDER")
GREEN_API_URL = os.getenv("GREEN_API_URL")

def log(message):
    """ Affiche un log horodaté dans la console """
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")

def clean_text(text):
    """ Nettoyage de base pour l'affichage (garde les apostrophes et points) """
    if not text: return ""
    cleaned = re.sub(r"[^a-zA-Z0-9/:\. ']", '', text)
    return " ".join(cleaned.split()).strip()

def get_pure_horse_name(full_name):
    """ Extrait 'OSANI' de 'OSANI H.PS. 4 a.' pour la recherche XPath """
    # Coupe avant les infos techniques type " H.AQ." ou " 5 a."
    pure_name = re.split(r'\s[A-Z]\.', full_name)[0] 
    pure_name = re.split(r'\s\d\sa\.', pure_name)[0] 
    return pure_name.strip()

def normalize_for_xpath(text):
    """ Supprime tout sauf lettres/chiffres pour une comparaison XPath infaillible """
    return re.sub(r'[^a-z0-9]', '', text.lower())

def send_whatsapp_notification(content):
    if not GREEN_API_URL:
        log("❌ Erreur : GREEN_API_URL non configurée.")
        return
    payload = {"chatId": "33678723278-1540128478@g.us", "message": content}
    try:
        response = requests.post(GREEN_API_URL, json=payload, timeout=15)
        log(f"📲 Statut WhatsApp : {response.status_code}")
    except Exception as e:
        log(f"❌ Échec envoi WhatsApp : {e}")

def run_scraper():
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--window-size=1920,1080")
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    wait = WebDriverWait(driver, 15)
    
    today = datetime.now().strftime("%d/%m/%Y")
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%d/%m/%Y")
    today_results = []
    seen_runners = set()

    try:
        log("🔑 Connexion à France Galop...")
        driver.get(URL_LOGIN)
        try:
            wait.until(EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler"))).click()
        except: pass

        driver.find_element(By.NAME, "name").send_keys(EMAIL_SENDER)
        driver.find_element(By.NAME, "pass").send_keys(FG_PASSWORD)
        driver.execute_script("arguments[0].click();", driver.find_element(By.CSS_SELECTOR, "#user-login-form button[type='submit']"))
        time.sleep(5)

        for trainer_url in URLS_ENTRAINEURS:
            log(f"🔍 Analyse entraîneur : {trainer_url.split('/')[-1][:15]}...")
            driver.get(trainer_url)
            time.sleep(5)

            rows = driver.find_elements(By.CSS_SELECTOR, "#partants_entraineur tbody tr")
            trainer_name = clean_text(driver.find_element(By.CSS_SELECTOR, "h1").text).replace("ENTRAINEUR", "").strip()

            runners_to_process = []
            for row in rows:
                txt = row.text
                if today in txt or tomorrow in txt:
                    cells = row.find_elements(By.TAG_NAME, "td")
                    full_name = clean_text(cells[0].text)
                    url = row.find_element(By.CSS_SELECTOR, "a[href*='/course/']").get_attribute("href")
                    
                    if f"{full_name}_{url}" in seen_runners: continue
                    seen_runners.add(f"{full_name}_{url}")

                    runners_to_process.append({
                        'date': today if today in txt else tomorrow,
                        'full_name': full_name,
                        'pure_name': get_pure_horse_name(full_name),
                        'url': url,
                        'trainer': trainer_name,
                        'course_label': clean_text(cells[4].text)
                    })

            for r in runners_to_process:
                log(f"   🐎 Extraction détails : {r['pure_name']}")
                driver.get(r['url'])
                time.sleep(4)
                
                try:
                    # 1. EXTRACTION INFOS COURSE (HEURE, HIPPO, N° COURSE)
                    details = driver.find_elements(By.CSS_SELECTOR, ".course-detail p")
                    heure, hippo, n_course = "00:00", "Inconnu", "?"
                    
                    for p in details:
                        p_txt = p.text.strip()
                        if "2026" in p_txt:
                            # Détection Heure
                            m_h = re.search(r'(\d{1,2}h\d{2})', p_txt)
                            if m_h: heure = m_h.group(1)
                            
                            # Détection Hippodrome
                            if "," in p_txt: hippo = clean_text(p_txt.split(",")[-1])
                            
                            # Détection N° de course (ex: 1ère, 2ème)
                            m_n = re.search(r'(\d+)(?:er|ère|ème|eme)', p_txt, re.IGNORECASE)
                            if m_n: 
                                n_course = m_n.group(1)
                            else:
                                # Fallback parenthèses (x)
                                m_n_alt = re.search(r'\((\d+)\)', p_txt)
                                if m_n_alt: n_course = m_n_alt.group(1)
                            break
                    
                    # Fallback ultime dans le titre H1 (C1, C2...)
                    if n_course == "?":
                        try:
                            m_n_title = re.search(r'C(\d+)', driver.find_element(By.TAG_NAME, "h1").text)
                            if m_n_title: n_course = m_n_title.group(1)
                        except: pass

                    # 2. EXTRACTION DU NUMÉRO DU CHEVAL
                    search_key = normalize_for_xpath(r['pure_name'])
                    xpath_row = f"//tr[contains(translate(translate(., \"' \", ''), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{search_key}')]"
                    row_cheval = wait.until(EC.presence_of_element_located((By.XPATH, xpath_row)))
                    num_cheval = "".join(filter(str.isdigit, row_cheval.find_elements(By.TAG_NAME, "td")[0].text))

                    # 3. MISE EN FORME
                    final_line = f"🏇 *{r['pure_name']}* (N°{num_cheval})\n📍 {hippo} - C{n_course} à {heure}\n📝 {r['course_label']}\n👤 Entr: {r['trainer']}"
                    
                    if r['date'] == today:
                        today_results.append(final_line)
                        log(f"      ✅ OK : Ajouté aux partants du jour.")
                    else:
                        log(f"      📅 LOG : Court demain ({tomorrow}).")

                except Exception as e:
                    log(f"      ⚠️ Erreur détails {r['pure_name']} : {str(e)[:50]}")

        # 4. ENVOI FINAL
        if today_results:
            msg = f"✅ *PARTANTS DU JOUR ({today})*\n\n" + "\n\n---\n\n".join(today_results)
            send_whatsapp_notification(msg)
        else:
            log("ℹ️ Aucun partant trouvé pour aujourd'hui.")

    except Exception as e:
        log(f"💥 ERREUR GLOBALE : {e}")
    finally:
        driver.quit()
        log("🏁 Fin du script.")

if __name__ == "__main__":
    run_scraper()
