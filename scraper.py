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
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] {message}")

def clean_text(text):
    if not text: return ""
    # On garde l'apostrophe pour l'affichage correct
    cleaned = re.sub(r"[^a-zA-Z0-9/:\. ']", '', text)
    return " ".join(cleaned.split()).strip()

def normalize_for_search(text):
    """ Transforme 'LE COUP D'ENVOI' en 'lecoupdenvoi' pour une recherche fiable """
    if not text: return ""
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
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36")
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    wait = WebDriverWait(driver, 20)
    
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

        driver.find_element(By.CSS_SELECTOR, "input[name='name']").send_keys(EMAIL_SENDER)
        driver.find_element(By.CSS_SELECTOR, "input[name='pass']").send_keys(FG_PASSWORD)
        driver.execute_script("arguments[0].click();", driver.find_element(By.CSS_SELECTOR, "button[type='submit']"))
        time.sleep(5)

        for trainer_url in URLS_ENTRAINEURS:
            log(f"🔍 Analyse entraîneur : {trainer_url.split('/')[-1][:10]}...")
            driver.get(trainer_url)
            time.sleep(5)

            try:
                rows = wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "#partants_entraineur tbody tr")))
            except:
                log("⚠️ Aucun partant trouvé dans le tableau.")
                continue

            trainer_name = clean_text(driver.find_element(By.CSS_SELECTOR, "h1").text).replace("ENTRAINEUR", "").strip()
            runners_to_process = []

            for row in rows:
                txt = row.text
                if today in txt or tomorrow in txt:
                    cells = row.find_elements(By.TAG_NAME, "td")
                    horse_raw = cells[0].text
                    horse_name = clean_text(horse_raw)
                    url = row.find_element(By.CSS_SELECTOR, "a[href*='/course/']").get_attribute("href")
                    
                    if f"{horse_name}_{url}" in seen_runners: continue
                    seen_runners.add(f"{horse_name}_{url}")

                    runners_to_process.append({
                        'date': today if today in txt else tomorrow,
                        'horse': horse_name,
                        'search_key': normalize_for_search(horse_name)[:12], # On prend les 12 premiers caractères normalisés
                        'url': url,
                        'trainer': trainer_name,
                        'course_simple': clean_text(cells[4].text)
                    })

            for r in runners_to_process:
                log(f"   🐎 Extraction détails pour : {r['horse']}")
                driver.get(r['url'])
                time.sleep(4)
                
                try:
                    # Extraction infos course
                    paragraphs = driver.find_elements(By.CSS_SELECTOR, ".course-detail p")
                    heure, hippo, n_course = "00:00", "Inconnu", "?"
                    for p in paragraphs:
                        p_txt = p.text.strip()
                        if "2026" in p_txt:
                            m_n = re.search(r'(\d+)', p_txt)
                            if m_n: n_course = m_n.group(1)
                            m_h = re.search(r'(\d{1,2}h\d{2})', p_txt)
                            if m_h: heure = m_h.group(1)
                            if "," in p_txt: hippo = clean_text(p_txt.split(",")[-1])
                            break

                    # Recherche du cheval avec normalisation XPath (ignore les apostrophes/points)
                    # On cherche une ligne tr qui contient la clé de recherche normalisée
                    xpath_horse = f"//tr[contains(translate(translate(., \"' \", ''), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{r['search_key']}')]"
                    horse_row = wait.until(EC.presence_of_element_located((By.XPATH, xpath_horse)))
                    num_cheval = "".join(filter(str.isdigit, horse_row.find_elements(By.TAG_NAME, "td")[0].text))

                    final_line = f"🏇 *{r['horse']}* (N°{num_cheval})\n📍 {hippo} - C{n_course} à {heure}\n📝 {r['course_simple']}\n👤 Entr: {r['trainer']}"
                    
                    if r['date'] == today:
                        today_results.append(final_line)
                        log(f"      ✅ OK : {r['horse']} ajouté aux partants du jour.")
                    else:
                        log(f"      📅 LOG : {r['horse']} court demain ({tomorrow}).")

                except Exception as e:
                    log(f"      ❌ Erreur sur {r['horse']} : {str(e)[:50]}...")

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
