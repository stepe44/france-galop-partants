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
        print(f"🚀 Connexion à France Galop via {URL_LOGIN}...")
        driver.get(URL_LOGIN)
        time.sleep(3)

        try:
            cookie_btn = driver.find_element(By.ID, "onetrust-accept-btn-handler")
            cookie_btn.click()
            time.sleep(1)
        except:
            pass

        wait.until(EC.presence_of_element_located((By.NAME, "name"))).send_keys(EMAIL_SENDER)
        driver.find_element(By.NAME, "pass").send_keys(FG_PASSWORD)
        
        login_btn = driver.find_element(By.ID, "edit-submit")
        driver.execute_script("arguments[0].click();", login_btn)
        time.sleep(6)

        # 2. ANALYSE DES ENTRAINEURS
        for trainer_url in URLS_ENTRAINEURS:
            driver.get(trainer_url)
            time.sleep(7)

            try:
                name_el = driver.find_element(By.CSS_SELECTOR, "h1, .page-title")
                trainer_name = clean_text(name_el.text).replace("ENTRAINEUR", "").strip()
            except:
                trainer_name = "Inconnu"
            
            print(f"🧐 Entraîneur détecté : {trainer_name}")

            # Collecte des chevaux partants Aujourd'hui ou Demain
            runners = []
            rows = driver.find_elements(By.TAG_NAME, "tr")
            for row in rows:
                txt = row.text
                if today in txt or tomorrow in txt:
                    try:
                        cells = row.find_elements(By.TAG_NAME, "td")
                        # On récupère l'URL de la course ici
                        link_el = row.find_element(By.CSS_SELECTOR, "a[href*='/course/']")
                        course_url = link_el.get_attribute("href")
                        
                        runners.append({
                            'date': today if today in txt else tomorrow,
                            'horse': clean_text(cells[4].text),
                            'url': course_url,
                            'trainer': trainer_name,
                            'hippodrome': clean_text(cells[1].text),
                            'course_name': clean_text(cells[3].text)
                        })
                    except:
                        continue

            # 3. NAVIGATION ET EXTRACTION PRÉCISE
            for r in runners:
                # --- LOG DE L'URL POUR VÉRIFICATION ---
                print(f"\n   📍 Analyse de : {r['horse']} ({r['date']})")
                print(f"   🔗 URL suivie : {r['url']}")
                
                driver.get(r['url'])
                time.sleep(5)
                
                try:
                    # Extraction Heure
                    heure = "00:00"
                    for selector in [".course-info-time", ".heure", ".course-date"]:
                        try:
                            el_txt = driver.find_element(By.CSS_SELECTOR, selector).text
                            if ":" in el_txt:
                                match = re.search(r'\d{1,2}:\d{2}', el_txt)
                                if match:
                                    heure = match.group(0)
                                    break
                        except: continue

                    # Extraction N° via XPATH insensible à la casse
                    xpath_horse = f"//tr[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{r['horse'].lower()}')]"
                    row_horse = wait.until(EC.presence_of_element_located((By.XPATH, xpath_horse)))
                    
                    n_cheval = row_horse.find_element(By.TAG_NAME, "td").text
                    n_cheval = clean_text(n_cheval).split()[0]

                    final_line = f"{r['date']} / {r['hippodrome']} / {heure} / {r['course_name']} / N°{n_cheval} {r['horse']} (Entr: {r['trainer']})"
                    
                    if r['date'] == today:
                        today_results.append(final_line)
                    else:
                        tomorrow_logs.append(final_line)
                    
                    print(f"      ✅ Trouvé : N°{n_cheval} - Départ à {heure}")

                except Exception as e:
                    print(f"      ⚠️ Échec de l'extraction sur la page course.")

        # 4. BILAN FINAL
        print("\n--- 📝 LOGS PARTANTS DEMAIN ---")
        if tomorrow_logs:
            for l in tomorrow_logs: print(log)
        else: print("Aucun partant détecté pour demain.")
        
        if today_results:
            print(f"\n📧 Envoi du récapitulatif par email...")
            send_final_email("\n".join(today_results))
        else:
            print("\n🏁 Aucun partant pour aujourd'hui. Fin de session.")

    except Exception as e:
        print(f"💥 ERREUR CRITIQUE : {e}")
    finally:
        driver.quit()

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
        print("✅ Email envoyé avec succès.")
    except Exception as e:
        print(f"❌ Échec de l'envoi de l'email : {e}")

if __name__ == "__main__":
    run_scraper()
