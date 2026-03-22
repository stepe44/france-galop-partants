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
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")

def clean_text(text):
    if not text: return ""
    cleaned = re.sub(r"[^a-zA-Z0-9/:\. ']", '', text)
    return " ".join(cleaned.split()).strip()

def get_pure_horse_name(full_name):
    """ Extrait 'OSANI' de 'OSANI H.PS. 4 a.' """
    # On coupe avant le premier bloc de type " H.AQ." ou " F.PS." ou " 5 a."
    pure_name = re.split(r'\s[A-Z]\.', full_name)[0] # Coupe au premier " X."
    pure_name = re.split(r'\s\d\sa\.', pure_name)[0] # Coupe au " 5 a."
    return pure_name.strip()

def normalize_for_xpath(text):
    """ Normalise pour la comparaison XPath (minuscules, sans ponctuation) """
    return re.sub(r'[^a-z0-9]', '', text.lower())

def send_whatsapp_notification(content):
    if not GREEN_API_URL:
        log("❌ GREEN_API_URL manquante.")
        return
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
    chrome_options.add_argument("--window-size=1920,1080")
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    wait = WebDriverWait(driver, 15) # 15s suffisent
    
    today = datetime.now().strftime("%d/%m/%Y")
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%d/%m/%Y")
    today_results = []
    seen_runners = set()

    try:
        log("🔑 Connexion France Galop...")
        driver.get(URL_LOGIN)
        try:
            wait.until(EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler"))).click()
        except: pass

        driver.find_element(By.NAME, "name").send_keys(EMAIL_SENDER)
        driver.find_element(By.NAME, "pass").send_keys(FG_PASSWORD)
        driver.execute_script("arguments[0].click();", driver.find_element(By.CSS_SELECTOR, "#user-login-form button[type='submit']"))
        time.sleep(5)

        for trainer_url in URLS_ENTRAINEURS:
            log(f"🌐 Analyse : {trainer_url.split('/')[-1][:15]}...")
            driver.get(trainer_url)
            time.sleep(5)

            rows = driver.find_elements(By.CSS_SELECTOR, "#partants_entraineur tbody tr")
            trainer_name = clean_text(driver.find_element(By.CSS_SELECTOR, "h1").text).replace("ENTRAINEUR", "").strip()

            runners = []
            for row in rows:
                txt = row.text
                if today in txt or tomorrow in txt:
                    cells = row.find_elements(By.TAG_NAME, "td")
                    full_name = clean_text(cells[0].text)
                    url = row.find_element(By.CSS_SELECTOR, "a[href*='/course/']").get_attribute("href")
                    
                    if f"{full_name}_{url}" in seen_runners: continue
                    seen_runners.add(f"{full_name}_{url}")

                    runners.append({
                        'date': today if today in txt else tomorrow,
                        'full_name': full_name,
                        'pure_name': get_pure_horse_name(full_name),
                        'url': url,
                        'trainer': trainer_name,
                        'course_label': clean_text(cells[4].text)
                    })

            for r in runners:
                log(f"   🐎 Cheval : {r['pure_name']} ({r['date']})")
                driver.get(r['url'])
                time.sleep(4)
                
                try:
                    # Extraction infos course (Heure, Hippo)
                    details = driver.find_elements(By.CSS_SELECTOR, ".course-detail p")
                    heure, hippo, n_course = "00:00", "Inconnu", "?"
                    for p in details:
                        p_txt = p.text
                        if "2026" in p_txt:
                            m_h = re.search(r'(\d{1,2}h\d{2})', p_txt)
                            if m_h: heure = m_h.group(1)
                            m_n = re.search(r'\((\d+)\)', p_txt)
                            if m_n: n_course = m_n.group(1)
                            if "," in p_txt: hippo = clean_text(p_txt.split(",")[-1])
                            break

                    # RECHERCHE DU NUMÉRO (XPATH ROBUSTE)
                    search_key = normalize_for_xpath(r['pure_name'])
                    log(f"      🔍 Recherche de la clé '{search_key}' dans le tableau...")
                    
                    # On cherche la ligne qui contient le nom du cheval normalisé
                    xpath_row = f"//tr[contains(translate(translate(., \"' \", ''), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{search_key}')]"
                    row_cheval = wait.until(EC.presence_of_element_located((By.XPATH, xpath_row)))
                    
                    num_cheval = "".join(filter(str.isdigit, row_cheval.find_elements(By.TAG_NAME, "td")[0].text))
                    log(f"      🎯 Trouvé ! N°{num_cheval}")

                    msg_line = f"{r['pure_name']} (N°{num_cheval})\n📍 {hippo} - C{n_course} à {heure}\n📝 {r['course_label']}\n👤 {r['trainer']}"
                    
                    if r['date'] == today:
                        today_results.append(f"🏇 *{msg_line}*")
                    else:
                        log(f"      📅 [DEMAIN] {r['pure_name']}")

                except Exception as e:
                    log(f"      ⚠️ Erreur détails {r['pure_name']} : {str(e)[:50]}")

        if today_results:
            final_msg = f"✅ *PARTANTS DU JOUR ({today})*\n\n" + "\n\n---\n\n".join(today_results)
            send_whatsapp_notification(final_msg)
        else:
            log("📝 Aucun partant pour aujourd'hui.")

    except Exception as e:
        log(f"💥 Erreur globale : {e}")
    finally:
        driver.quit()
        log("🏁 Fin.")

if __name__ == "__main__":
    run_scraper()
