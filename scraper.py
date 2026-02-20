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
    wait = WebDriverWait(driver, 25)
    
    today = datetime.now().strftime("%d/%m/%Y")
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%d/%m/%Y")
    
    today_results = []
    tomorrow_logs = []

    try:
        # 1. CONNEXION
        print(f"🌐 Ouverture de la page login : {URL_LOGIN}")
        driver.get(URL_LOGIN)
        time.sleep(4)

        try:
            cookie_btn = driver.find_element(By.ID, "onetrust-accept-btn-handler")
            cookie_btn.click()
            print("🍪 Cookies acceptés.")
        except:
            pass

        print("✍️ Saisie des identifiants...")
        wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "input[name='name']"))).send_keys(EMAIL_SENDER)
        driver.find_element(By.CSS_SELECTOR, "input[name='pass']").send_keys(FG_PASSWORD)
        
        login_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "#user-login-form button[type='submit'], #edit-submit--2")))
        driver.execute_script("arguments[0].click();", login_button)
        print("🖱️ Clic sur 'Se connecter'")
        time.sleep(7)

        # 2. ANALYSE DES PAGES ENTRAINEURS
        for trainer_url in URLS_ENTRAINEURS:
            print(f"\n🌍 Ouverture page entraîneur : {trainer_url}")
            driver.get(trainer_url)
            time.sleep(8)

            # DETECTION ENTRAINEUR (Version stable reprise)
            try:
                trainer_name_raw = driver.find_element(By.CSS_SELECTOR, "h1, .page-title").text
                trainer_name = clean_text(trainer_name_raw).replace("ENTRAINEUR", "").strip()
            except:
                trainer_name = "Inconnu"
            
            print(f"👤 Entraîneur : {trainer_name}")

            # Collecte des lignes du jour et demain
            runners_to_check = []
            rows = driver.find_elements(By.TAG_NAME, "tr")

            for row in rows:
                row_text = row.text
                if today in row_text or tomorrow in row_text:
                    try:
                        cells = row.find_elements(By.TAG_NAME, "td")
                        link_element = row.find_element(By.CSS_SELECTOR, "td a[href*='/course/']")
                        
                        runners_to_check.append({
                            'date': today if today in row_text else tomorrow,
                            'horse_name': clean_text(cells[4].text),
                            'course_url': link_element.get_attribute("href"),
                            'trainer': trainer_name,
                            'hippodrome': clean_text(cells[1].text),
                            'course_name': clean_text(cells[3].text)
                        })
                    except:
                        continue

            # 3. NAVIGATION VERS LES COURSES
            for item in runners_to_check:
                print(f"   📍 Analyse de : {item['horse_name']} ({item['date']})")
                print(f"   🔗 Ouverture URL Course : {item['course_url']}")
                driver.get(item['course_url'])
                time.sleep(6)
                
                try:
                    # Extraction Heure
                    heure_text = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".course-info-time, .heure, .course-date"))).text
                    heure = "00:00"
                    match = re.search(r'\d{1,2}:\d{2}', heure_text)
                    if match:
                        heure = match.group(0)
                    
                    # Extraction N° (XPATH insensible à la casse)
                    xpath_horse = f"//tr[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{item['horse_name'].lower()}')]"
                    horse_row = driver.find_element(By.XPATH, xpath_horse)
                    num_cheval = clean_text(horse_row.find_element(By.TAG_NAME, "td").text).split()[0]
                    
                    final_line = f"{item['date']} / {item['hippodrome']} / {heure} / {item['course_name']} / N°{num_cheval} {item['horse_name']} (Entr: {item['trainer']})"
                    
                    if item['date'] == today:
                        today_results.append(final_line)
                        print(f"      ✅ OK (Aujourd'hui)")
                    else:
                        tomorrow_logs.append(final_line)
                        print(f"      📝 OK (Demain - Log uniquement)")
                
                except Exception as e:
                    print(f"   ⚠️ Échec détails pour {item['horse_name']}. Vérifiez l'URL manuellement.")

        # 4. LOGS ET EMAIL
        print("\n--- 📝 RÉCAPITULATIF DEMAIN ---")
        if tomorrow_logs:
            for l in tomorrow_logs: print(l)
        else:
            print("Aucun partant pour demain.")
        
        if today_results:
            print(f"\n📧 Envoi email (Aujourd'hui : {len(today_results)} partants)")
            send_final_email("\n".join(today_results))
        else:
            print("\n🏁 Aucun partant pour aujourd'hui.")

    except Exception as e:
        print(f"💥 Erreur globale : {e}")
    finally:
        driver.quit()

def send_final_email(content):
    msg = MIMEMultipart()
    msg['From'] = EMAIL_SENDER
    msg['To'] = EMAIL_DEST
    msg['Subject'] = f"Partants France Galop - {datetime.now().strftime('%d/%m/%Y')}"
    msg.attach(MIMEText(content, 'plain'))
    try:
        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            server.login(EMAIL_SENDER, GMAIL_APP_PASSWORD)
            server.send_message(msg)
        print("✅ Email envoyé.")
    except Exception as e:
        print(f"❌ Erreur email : {e}")

if __name__ == "__main__":
    run_scraper()
