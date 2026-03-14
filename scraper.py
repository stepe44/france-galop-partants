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

def clean_text(text):
    if not text: return ""
    cleaned = re.sub(r'[^a-zA-Z0-9/:\. ]', '', text)
    return " ".join(cleaned.split()).strip()

def save_screenshot(driver, label):
    timestamp = datetime.now().strftime("%Hh%M_%S")
    filename = f"debug_{label}_{timestamp}.png"
    driver.save_screenshot(filename)
    print(f"📸 Screenshot : {filename}")

def send_whatsapp_notification(content):
    if not GREEN_API_URL:
        print("❌ Erreur : GREEN_API_URL non configurée.")
        return

    payload = {
        "chatId": "33678723278-1540128478@g.us",
        "message": content
    }
    headers = {"Content-Type": "application/json"}

    try:
        response = requests.post(GREEN_API_URL, json=payload, headers=headers, timeout=15)
        print(f"📲 Statut WhatsApp : {response.status_code}")
    except Exception as e:
        print(f"❌ Échec envoi WhatsApp : {e}")

def run_scraper():
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36")
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    wait = WebDriverWait(driver, 25)
    
    today = datetime.now().strftime("%d/%m/%Y")
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%d/%m/%Y")
    
    today_results = []
    tomorrow_logs = []
    seen_runners = set() # CHANGEMENT : On stocke les couples cheval+course

    try:
        # 1. CONNEXION
        driver.get(URL_LOGIN)
        try:
            wait.until(EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler"))).click()
        except: pass

        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "#user-login-form input[name='name']"))).send_keys(EMAIL_SENDER)
        driver.find_element(By.CSS_SELECTOR, "#user-login-form input[name='pass']").send_keys(FG_PASSWORD)
        login_btn = driver.find_element(By.CSS_SELECTOR, "#user-login-form button[type='submit']")
        driver.execute_script("arguments[0].click();", login_btn)
        time.sleep(7)

        # 2. ANALYSE ENTRAINEURS
        for trainer_url in URLS_ENTRAINEURS:
            driver.get(trainer_url)
            time.sleep(8)

            try:
                partants_table = wait.until(EC.presence_of_element_located((By.ID, "partants_entraineur")))
                rows = partants_table.find_elements(By.CSS_SELECTOR, "tbody tr")
            except:
                print(f"⚠️ Aucun tableau trouvé sur {trainer_url}")
                continue

            runners = []
            trainer_name = clean_text(driver.find_element(By.CSS_SELECTOR, "h1").text).replace("ENTRAINEUR", "").strip()

            for row in rows:
                txt = row.text
                if today in txt or tomorrow in txt:
                    try:
                        cells = row.find_elements(By.TAG_NAME, "td")
                        horse_name = clean_text(cells[0].text)
                        link_el = row.find_element(By.CSS_SELECTOR, "a[href*='/course/']")
                        url = link_el.get_attribute("href")
                        
                        # CHANGEMENT : Unicité basée sur le nom du cheval ET l'URL de la course
                        runner_id = f"{horse_name}_{url}"
                        if runner_id in seen_runners: continue
                        seen_runners.add(runner_id)

                        runners.append({
                            'date': today if today in txt else tomorrow,
                            'horse': horse_name,
                            'horse_search': horse_name[:10].lower(),
                            'url': url,
                            'trainer': trainer_name,
                            'course_simple': clean_text(cells[4].text)
                        })
                    except: continue

            # 3. EXTRACTION DÉTAILLÉE
            for r in runners:
                driver.get(r['url'])
                time.sleep(6)
                
                try:
                    paragraphs = driver.find_elements(By.CSS_SELECTOR, ".course-detail p")
                    heure, hippodrome, n_course = "00:00", "Inconnu", "?"
                    
                    for p in paragraphs:
                        p_txt = p.text.strip()
                        if "2026" in p_txt and "(" in p_txt:
                            match_n = re.search(r'(\d+)', p_txt)
                            if match_n: n_course = match_n.group(1)
                            match_h = re.search(r'(\d{1,2}h\d{2})', p_txt)
                            if match_h: heure = match_h.group(1)
                            if "," in p_txt: hippodrome = clean_text(p_txt.split(",")[-1])
                            break

                    xpath_horse = f"//div[contains(@class, 'raceTable')]//tr[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{r['horse_search']}')]"
                    horse_row = wait.until(EC.presence_of_element_located((By.XPATH, xpath_horse)))
                    num_cheval = "".join(filter(str.isdigit, horse_row.find_elements(By.TAG_NAME, "td")[0].text))

                    final_line = f"🏇 *{r['horse']}* (N°{num_cheval})\n📍 {hippodrome} - C{n_course} à {heure}\n📝 {r['course_simple']}\n👤 Entr: {r['trainer']}"
                    
                    if r['date'] == today: today_results.append(final_line)
                    else: tomorrow_logs.append(final_line)
                    print(f"      ✅ OK : {r['horse']}")

                except Exception as e:
                    print(f"      ⚠️ Erreur extraction : {str(e)[:30]}")

        # 4. ENVOI DES RAPPORTS
        if today_results:
            message_final = f"✅ *PARTANTS DU JOUR ({today})*\n\n" + "\n\n---\n\n".join(today_results)
            send_whatsapp_notification(message_final)
        
        print(f"\n--- 📝 LOGS DEMAIN ({tomorrow}) ---")
        for line in tomorrow_logs: print(line)

    except Exception as e: 
        print(f"💥 Erreur globale : {e}")
        save_screenshot(driver, "global_error")
    finally: 
        driver.quit()

if __name__ == "__main__":
    run_scraper()
