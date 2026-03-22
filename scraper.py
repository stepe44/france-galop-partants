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

def translate_performance(musique):
    """ Décode la musique (ex: 1s8s(25)Ah) et ne garde que les 3 dernières perfs """
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
        
        # Capture le rang/incident et la discipline (ex: 1s, Ah)
        matches = re.findall(r'([0-9A-Z])([a-z])', part)
        for rank, disc in matches:
            d_name = mapping_disc.get(disc, disc)
            if rank.isdigit():
                r_text = f"{rank}er" if rank == "1" else f"{rank}e"
                if rank == "0": r_text = "Non placé"
                decoded_parts.append(f"{r_text} en {d_name} ({current_year})")
            else:
                inc_text = mapping_inc.get(rank, rank)
                decoded_parts.append(f"{inc_text} en {d_name} ({current_year})")

    # Limitation aux 3 dernières performances pour la clarté
    return " | ".join(decoded_parts[:3])

def clean_text(text):
    if not text: return ""
    cleaned = re.sub(r"[^a-zA-Z0-9/:\. '()]", '', text)
    return " ".join(cleaned.split()).strip()

def get_pure_horse_name(full_name):
    """ Isole le nom du cheval des infos techniques """
    pure_name = re.split(r'\s[A-Z]\.', full_name)[0] 
    pure_name = re.split(r'\s\d\sa\.', pure_name)[0] 
    return pure_name.strip()

def normalize_for_xpath(text):
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
    wait = WebDriverWait(driver, 15)
    
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
            log(f"🌐 Analyse entraîneur : {trainer_url.split('/')[-1][:15]}...")
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
                log(f"   🐎 Extraction : {r['pure_name']}")
                driver.get(r['url'])
                time.sleep(4)
                
                try:
                    # 1. Infos course (Heure, Hippo, N°)
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
                    
                    if n_course == "?":
                        try:
                            m_n_title = re.search(r'C(\d+)', driver.find_element(By.TAG_NAME, "h1").text)
                            if m_n_title: n_course = m_n_title.group(1)
                        except: pass

                    # 2. Localisation ligne et perfs
                    search_key = normalize_for_xpath(r['pure_name'])
                    xpath_row = f"//tr[contains(translate(translate(., \"' \", ''), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{search_key}')]"
                    row_cheval = wait.until(EC.presence_of_element_located((By.XPATH, xpath_row)))
                    cells = row_cheval.find_elements(By.TAG_NAME, "td")
                    
                    perf_index = 11
                    try:
                        headers = driver.find_elements(By.CSS_SELECTOR, "thead th")
                        for i, h in enumerate(headers):
                            if "Performances" in h.text:
                                perf_index = i
                                break
                    except: pass

                    num_cheval = "".join(filter(str.isdigit, cells[0].text))
                    raw_perf = clean_text(cells[perf_index].text) if len(cells) > perf_index else "N/A"
                    
                    # Décodage limité aux 3 dernières
                    decoded_perf = translate_performance(raw_perf)

                    msg_line = (f"🏇 *{r['pure_name']}* (N°{num_cheval})\n"
                                f"📍 {hippo} - C{n_course} à {heure}\n"
                                f"📊 *Musique :* {decoded_perf}\n"
                                f"📝 {r['course_label']}\n"
                                f"👤 Entr: {r['trainer']}")
                    
                    if r['date'] == today:
                        today_results.append(msg_line)
                        log(f"      ✅ OK : {r['pure_name']}")
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
