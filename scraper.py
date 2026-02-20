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

def run_scraper():
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36")
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    wait = WebDriverWait(driver, 20)
    
    today = datetime.now().strftime("%d/%m/%Y")
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%d/%m/%Y")
    
    today_results = []
    tomorrow_logs = []

    try:
        # 1. CONNEXION
        driver.get(URL_LOGIN)
        try:
            wait.until(EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler"))).click()
        except: pass

        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "#user-login-form input[name='name']"))).send_keys(EMAIL_SENDER)
        driver.find_element(By.CSS_SELECTOR, "#user-login-form input[name='pass']").send_keys(FG_PASSWORD)
        driver.execute_script("arguments[0].click();", driver.find_element(By.CSS_SELECTOR, "#user-login-form button[type='submit']"))
        time.sleep(5)

        # 2. ANALYSE DES ENTRAINEURS
        for trainer_url in URLS_ENTRAINEURS:
            print(f"\n--- 🔎 ANALYSE PAGE : {trainer_url} ---")
            driver.get(trainer_url)
            time.sleep(7)
            
            try:
                t_name = driver.find_element(By.CSS_SELECTOR, "h1, .page-title").text
                trainer_name = clean_text(t_name).replace("ENTRAINEUR", "").strip()
                print(f"👤 Entraîneur : {trainer_name}")
            except: trainer_name = "Inconnu"

            rows = driver.find_elements(By.TAG_NAME, "tr")
            print(f"📊 Nombre de lignes détectées dans le tableau : {len(rows)}")

            runners = []
            for idx, row in enumerate(rows):
                txt = row.text
                if not txt.strip(): continue
                
                # DEBUG : Affiche ce que le robot voit sur chaque ligne
                if today in txt or tomorrow in txt:
                    print(f"DEBUG [Ligne {idx}] : {txt}")
                    try:
                        cells = row.find_elements(By.TAG_NAME, "td")
                        horse_raw = cells[4].text.strip()
                        course_url = row.find_element(By.CSS_SELECTOR, "a[href*='/course/']").get_attribute("href")
                        
                        runners.append({
                            'date': today if today in txt else tomorrow,
                            'horse_full': horse_raw,
                            'horse_search': clean_text(horse_raw)[:10].lower(),
                            'url': course_url,
                            'trainer': trainer_name,
                            'course_name': clean_text(cells[3].text)
                        })
                    except Exception as e:
                        print(f"⚠️ Erreur parsing ligne {idx} : {e}")

            # 3. EXTRACTION FICHE COURSE
            for r in runners:
                print(f"\n👉 NAVIGATION : {r['url']}")
                driver.get(r['url'])
                time.sleep(6)
                
                try:
                    # DEBUG EN-TETE
                    header_txt = ""
                    for selector in [".course-header-info", ".course-date-place", ".course-info"]:
                        try:
                            el = driver.find_element(By.CSS_SELECTOR, selector)
                            if el.is_displayed():
                                header_txt = el.text
                                break
                        except: continue
                    
                    print(f"DEBUG [En-tête Course] : {header_txt.replace(chr(10), ' | ')}")
                    
                    match_h = re.search(r'\d{1,2}[h:]\d{2}', header_txt)
                    heure = match_h.group(0) if match_h else "00:00"
                    hippodrome = clean_text(header_txt.split(",")[-1]) if "," in header_txt else "Inconnu"

                    # DEBUG TABLEAU PARTANTS
                    xpath_horse = f"//tr[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{r['horse_search']}')]"
                    try:
                        horse_row = wait.until(EC.presence_of_element_located((By.XPATH, xpath_horse)))
                        print(f"DEBUG [Ligne Cheval trouvée] : {horse_row.text}")
                        
                        num_raw = horse_row.find_elements(By.TAG_NAME, "td")[0].text
                        num_cheval = "".join(filter(str.isdigit, num_raw)) or "?"
                    except:
                        print(f"❌ Impossible de trouver le cheval '{r['horse_search']}' dans le tableau de la course.")
                        num_cheval = "?"

                    res_line = f"{r['date']} / {hippodrome} / {heure} / {r['course_name']} / N°{num_cheval} {r['horse_full']} (Entr: {r['trainer']})"
                    
                    if r['date'] == today:
                        today_results.append(res_line)
                    else:
                        tomorrow_logs.append(res_line)

                except Exception as e:
                    print(f"⚠️ Erreur détails course : {e}")

        # 4. BILAN
        print("\n--- 📝 LOGS DEMAIN ---")
        for l in tomorrow_logs: print(l)
        
        if today_results:
            print(f"\n📧 Envoi email...")
            send_final_email("\n".join(today_results))
        else: print("\n🏁 Aucun partant aujourd'hui.")

    except Exception as e: print(f"💥 Erreur : {e}")
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
