import os
import re
import time
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# --- CONFIGURATION ---
URL_LOGIN = "https://www.france-galop.com/fr/login"
URLS_ENTRAINEURS = [
    "https://www.france-galop.com/fr/entraineur/Z1FxYXQ3cFJyM0ZlUitJQTlmUTNiUT09#partants",
    "https://www.france-galop.com/fr/entraineur/U0VNb0JtQlZ1bUphYndFTnJjSzg4dz09#partants"
]

FG_PASSWORD = os.getenv("FG_PASSWORD")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")
EMAIL_SENDER = os.getenv("EMAIL_SENDER")
EMAIL_DEST = os.getenv("EMAIL_DEST")

def clean_text(text):
    if not text: return ""
    cleaned = re.sub(r'[^a-zA-Z0-9/:\. ]', '', text)
    return " ".join(cleaned.split()).strip()

def save_screenshot(driver, label):
    timestamp = datetime.now().strftime("%Hh%M_%S")
    filename = f"debug_{label}_{timestamp}.png"
    driver.save_screenshot(filename)
    print(f"📸 Capture d'écran : {filename}")

def run_scraper():
    chrome_options = Options()
    chrome_options.add_argument("--headless")
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
    seen_course_urls = set() # Pour éviter les doublons

    try:
        # 1. CONNEXION
        driver.get(URL_LOGIN)
        try:
            wait.until(EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler"))).click()
        except: pass

        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "#user-login-form input[name='name']"))).send_keys(EMAIL_SENDER)
        driver.find_element(By.CSS_SELECTOR, "#user-login-form input[name='pass']").send_keys(FG_PASSWORD)
        driver.execute_script("arguments[0].click();", driver.find_element(By.ID, "edit-submit"))
        time.sleep(6)

        # 2. ANALYSE ENTRAINEURS
        for trainer_url in URLS_ENTRAINEURS:
            driver.get(trainer_url)
            time.sleep(8)
            
            try:
                t_name = driver.find_element(By.CSS_SELECTOR, "h1, .page-title").text
                trainer_name = clean_text(t_name).replace("ENTRAINEUR", "").strip()
            except: trainer_name = "Inconnu"

            rows = driver.find_elements(By.TAG_NAME, "tr")
            runners = []
            for row in rows:
                txt = row.text
                if today in txt or tomorrow in txt:
                    try:
                        link_el = row.find_element(By.CSS_SELECTOR, "a[href*='/course/']")
                        url = link_el.get_attribute("href")
                        
                        # --- GESTION DOUBLONS ---
                        # On ne traite le cheval que si l'URL de sa course n'a pas encore été vue
                        if url in seen_course_urls:
                            continue
                        seen_course_urls.add(url)

                        cells = row.find_elements(By.TAG_NAME, "td")
                        horse_name = clean_text(cells[4].text)
                        runners.append({
                            'date': today if today in txt else tomorrow,
                            'horse': horse_name,
                            'horse_search': horse_name[:10].lower(),
                            'url': url,
                            'trainer': trainer_name,
                            'course_simple': clean_text(cells[3].text)
                        })
                    except: continue

            # 3. EXTRACTION PRÉCISE (REGEX)
            for r in runners:
                print(f"   🔗 Navigation Course : {r['url']}")
                driver.get(r['url'])
                time.sleep(6)
                
                try:
                    # On récupère tous les paragraphes de la zone détail
                    paragraphs = driver.find_elements(By.CSS_SELECTOR, ".course-detail p")
                    header_line = ""
                    
                    # On cherche celui qui contient la date (ex: 2026)
                    for p in paragraphs:
                        if "2026" in p.text and "h" in p.text:
                            header_line = p.text
                            break
                    
                    print(f"      DEBUG Header Brut : {header_line}")
                    
                    # REGEX : 21/02/2026 11h28, FONTAINEBLEAU
                    # Extraction de l'heure
                    match_h = re.search(r'(\d{1,2}h\d{2})', header_line)
                    heure = match_h.group(1) if match_h else "00:00"
                    
                    # Extraction de l'hippodrome (Tout ce qui est après la dernière virgule)
                    hippodrome = "Inconnu"
                    if "," in header_line:
                        hippodrome = clean_text(header_line.split(",")[-1])

                    # Extraction du N° (raceTable)
                    xpath_horse = f"//div[contains(@class, 'raceTable')]//tr[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{r['horse_search']}')]"
                    horse_row = wait.until(EC.presence_of_element_located((By.XPATH, xpath_horse)))
                    num_raw = horse_row.find_elements(By.TAG_NAME, "td")[0].text.strip()
                    num_cheval = "".join(filter(str.isdigit, num_raw)) or "?"

                    final_line = f"{r['date']} / {hippodrome} / {heure} / {r['course_simple']} / N°{num_cheval} {r['horse']} (Entr: {r['trainer']})"
                    
                    if r['date'] == today:
                        today_results.append(final_line)
                    else:
                        tomorrow_logs.append(final_line)
                    print(f"      ✅ Trouvé : N°{num_cheval} à {heure} ({hippodrome})")

                except Exception as e:
                    print(f"      ⚠️ Échec extraction détails : {str(e)[:50]}")

        # 4. BILAN
        print(f"\n--- 📝 LOGS PARTANTS DEMAIN ({tomorrow}) ---")
        if tomorrow_logs:
            for l in tomorrow_logs: print(l)
        else: print("Aucun partant détecté.")
        
        if today_results:
            send_final_email("\n".join(today_results))

    except Exception as e: print(f"💥 Erreur globale : {e}")
    finally: driver.quit()

def send_final_email(content):
    msg = MIMEMultipart(); msg['From'] = EMAIL_SENDER; msg['To'] = EMAIL_DEST
    msg['Subject'] = f"Partants France Galop - {datetime.now().strftime('%d/%m/%Y')}"
    msg.attach(MIMEText(content, 'plain'))
    try:
        with smtplib.SMTP('smtp.gmail.com', 587) as s:
            s.starttls(); s.login(EMAIL_SENDER, GMAIL_APP_PASSWORD); s.send_message(msg)
        print("✅ Email envoyé.")
    except: print("❌ Erreur email.")

if __name__ == "__main__":
    run_scraper()
