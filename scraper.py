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
        # 1. CONNEXION (Basé sur image_160a3b.png)
        print(f"🌐 Ouverture du login : {URL_LOGIN}")
        driver.get(URL_LOGIN)
        
        try:
            cookie_btn = wait.until(EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler")))
            cookie_btn.click()
        except: pass

        print("✍️ Saisie des identifiants dans 'Mon espace'...")
        # On cible précisément le formulaire de gauche
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "#user-login-form input[name='name']"))).send_keys(EMAIL_SENDER)
        driver.find_element(By.CSS_SELECTOR, "#user-login-form input[name='pass']").send_keys(FG_PASSWORD)
        
        # Clic sur le bouton noir "Se connecter" (image_160a3b.png)
        login_btn = driver.find_element(By.CSS_SELECTOR, "#user-login-form button[type='submit']")
        driver.execute_script("arguments[0].click();", login_btn)
        time.sleep(6)

        # 2. ANALYSE DES ENTRAINEURS
        for trainer_url in URLS_ENTRAINEURS:
            print(f"\n🌍 Navigation entraîneur : {trainer_url}")
            driver.get(trainer_url)
            time.sleep(8)

            try:
                t_name = driver.find_element(By.CSS_SELECTOR, "h1, .page-title").text
                trainer_name = clean_text(t_name).replace("ENTRAINEUR", "").strip()
            except: trainer_name = "Inconnu"

            runners = []
            rows = driver.find_elements(By.TAG_NAME, "tr")
            for row in rows:
                txt = row.text
                if today in txt or tomorrow in txt:
                    try:
                        link_el = row.find_element(By.CSS_SELECTOR, "a[href*='/course/']")
                        runners.append({
                            'date': today if today in txt else tomorrow,
                            'horse': clean_text(row.find_elements(By.TAG_NAME, "td")[4].text),
                            'url': link_el.get_attribute("href"),
                            'trainer': trainer_name,
                            'course_name_raw': clean_text(row.find_elements(By.TAG_NAME, "td")[3].text)
                        })
                    except: continue

            # 3. EXTRACTION FICHE COURSE (Basé sur image_169d39.png et image_169d3d.png)
            for r in runners:
                print(f"   📍 Analyse de {r['horse']} | URL : {r['url']}")
                driver.get(r['url'])
                
                try:
                    # Extraction depuis l'en-tête (image_169d39.png)
                    # Exemple: "1ère(O/ 3132), — 21/02/2026 11h28, FONTAINEBLEAU"
                    header_info = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".course-header-info, .course-date-place"))).text
                    
                    # Heure
                    match_h = re.search(r'\d{1,2}h\d{2}', header_info) # Format 11h28
                    heure = match_h.group(0) if match_h else "00:00"
                    
                    # Hippodrome (Texte après la virgule ou l'heure)
                    parts = header_info.split(",")
                    hippodrome = clean_text(parts[-1]) if len(parts) > 1 else "Inconnu"

                    # Extraction du N° dans le tableau vert (image_169d3d.png)
                    xpath_horse = f"//tr[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{r['horse'].lower()}')]"
                    horse_row = wait.until(EC.presence_of_element_located((By.XPATH, xpath_horse)))
                    
                    # Le N° est dans la première colonne (td)
                    num_cheval = horse_row.find_elements(By.TAG_NAME, "td")[0].text.strip()
                    num_cheval = "".join(filter(str.isdigit, num_cheval))

                    final_line = f"{r['date']} / {hippodrome} / {heure} / {r['course_name_raw']} / N°{num_cheval} {r['horse']} (Entr: {r['trainer']})"
                    
                    if r['date'] == today:
                        today_results.append(final_line)
                        print(f"      ✅ Trouvé : N°{num_cheval} à {heure} ({hippodrome})")
                    else:
                        tomorrow_logs.append(final_line)
                        print(f"      📝 Log demain : N°{num_cheval} à {heure} ({hippodrome})")

                except Exception as e:
                    print(f"      ⚠️ Erreur détails : {str(e)[:50]}")

        # 4. FINALISATION
        print("\n--- 📝 LOGS PARTANTS DEMAIN ---")
        for l in tomorrow_logs: print(l)
        
        if today_results:
            send_final_email("\n".join(today_results))
        else: print("\n🏁 Aucun partant aujourd'hui.")

    except Exception as e: print(f"💥 Erreur globale : {e}")
    finally: driver.quit()

def send_final_email(content):
    msg = MIMEMultipart()
    msg['From'] = EMAIL_SENDER
    msg['To'] = EMAIL_DEST
    msg['Subject'] = f"Partants France Galop - {datetime.now().strftime('%d/%m/%Y')}"
    msg.attach(MIMEText(content, 'plain'))
    try:
        with smtplib.SMTP('smtp.gmail.com', 587) as s:
            s.starttls()
            s.login(EMAIL_SENDER, GMAIL_APP_PASSWORD)
            s.send_message(msg)
        print("✅ Email envoyé.")
    except Exception as e: print(f"❌ Erreur email : {e}")

if __name__ == "__main__":
    run_scraper()
