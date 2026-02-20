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
    """Génère une capture d'écran horodatée pour les artifacts."""
    timestamp = datetime.now().strftime("%Hh%M_%S")
    filename = f"debug_{label}_{timestamp}.png"
    driver.save_screenshot(filename)
    print(f"📸 Capture d'écran : {filename}")

def check_session(driver):
    """Vérifie la présence de la classe 'user-logged-in' et du bouton 'Mon espace'."""
    try:
        # Vérification technique : classe sur le body
        body_class = driver.find_element(By.TAG_NAME, "body").get_attribute("class")
        
        # Vérification visuelle : lien 'Mon espace'
        mon_espace = driver.find_elements(By.CSS_SELECTOR, "#block-francegalop-account-menu .menu-user")
        
        is_logged = "user-logged-in" in body_class and len(mon_espace) > 0
        
        status = "🔒 CONNECTÉ" if is_logged else "🔓 DÉCONNECTÉ"
        print(f"--- État Session : {status} sur {driver.current_url} ---")
        return is_logged
    except:
        return False

def run_scraper():
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36")
    
    # On utilise une seule instance de driver pour conserver les cookies
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    wait = WebDriverWait(driver, 25)
    
    today = datetime.now().strftime("%d/%m/%Y")
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%d/%m/%Y")
    
    today_results = []
    tomorrow_logs = []

    try:
        # 1. ÉTAPE DE CONNEXION (Image 160a3b)
        print(f"🌐 Navigation vers : {URL_LOGIN}")
        driver.get(URL_LOGIN)
        try:
            wait.until(EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler"))).click()
        except: pass

        print("🔑 Saisie des identifiants (Bloc de gauche)...")
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "#user-login-form input[name='name']"))).send_keys(EMAIL_SENDER)
        driver.find_element(By.CSS_SELECTOR, "#user-login-form input[name='pass']").send_keys(FG_PASSWORD)
        
        # Clic sur le bouton noir 'Se connecter'
        login_btn = driver.find_element(By.CSS_SELECTOR, "#user-login-form button[type='submit']")
        driver.execute_script("arguments[0].click();", login_btn)
        
        time.sleep(7) # Délai pour fixer la session
        save_screenshot(driver, "1_apres_login")

        if not check_session(driver):
            print("❌ Échec critique : Impossible d'établir la session initiale.")
            return

        # 2. ANALYSE DES ENTRAINEURS (La session est préservée ici)
        for trainer_url in URLS_ENTRAINEURS:
            print(f"\n🌍 Ouverture Entraîneur : {trainer_url}")
            driver.get(trainer_url)
            time.sleep(6)
            
            # Vérification de session sur la page
            check_session(driver)
            save_screenshot(driver, f"2_trainer_{trainer_url[-10:]}")

            try:
                t_name = driver.find_element(By.CSS_SELECTOR, "h1, .page-header").text
                trainer_name = clean_text(t_name).replace("ENTRAINEUR", "").strip()
            except: trainer_name = "Inconnu"

            # Lecture du tableau des partants
            rows = driver.find_elements(By.CSS_SELECTOR, "table tr")
            runners = []
            for row in rows:
                txt = row.text
                if today in txt or tomorrow in txt:
                    try:
                        cells = row.find_elements(By.TAG_NAME, "td")
                        horse_raw = clean_text(cells[0].text)
                        link = row.find_element(By.CSS_SELECTOR, "a[href*='/course/']").get_attribute("href")
                        
                        runners.append({
                            'date': today if today in txt else tomorrow,
                            'horse_full': horse_raw,
                            'horse_search': horse_raw[:10].lower(),
                            'url': link,
                            'trainer': trainer_name,
                            'course_name': clean_text(cells[4].text)
                        })
                    except: continue

            # 3. NAVIGATION VERS CHAQUE FICHE COURSE
            for r in runners:
                print(f"   🔗 Navigation Course : {r['url']}")
                driver.get(r['url'])
                time.sleep(6)
                
                # On s'assure que la session est toujours là pour voir les détails
                check_session(driver)
                
                try:
                    # Extraction Heure/Lieu (Image 17115d)
                    # On cible le paragraphe <p> dans .course-detail
                    header_p = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".course-detail p"))).text
                    print(f"      DEBUG Header : {header_p}")
                    
                    match_h = re.search(r'\d{1,2}[h:]\d{2}', header_p)
                    heure = match_h.group(0) if match_h else "00:00"
                    hippodrome = clean_text(header_p.split(",")[-1])

                    # Extraction du N° (Image 171578)
                    # Recherche dans la table.raceTable
                    xpath_horse = f"//div[contains(@class, 'raceTable')]//tr[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{r['horse_search']}')]"
                    horse_row = wait.until(EC.presence_of_element_located((By.XPATH, xpath_horse)))
                    
                    num_raw = horse_row.find_elements(By.TAG_NAME, "td")[0].text.strip()
                    num_cheval = "".join(filter(str.isdigit, num_raw)) or "?"

                    final_line = f"{r['date']} / {hippodrome} / {heure} / {r['course_name']} / N°{num_cheval} {r['horse_full']} (Entr: {r['trainer']})"
                    
                    if r['date'] == today:
                        today_results.append(final_line)
                    else:
                        tomorrow_logs.append(final_line)
                    
                    print(f"      ✅ Trouvé : N°{num_cheval} à {heure}")

                except Exception as e:
                    print(f"      ⚠️ Échec extraction détails : {str(e)[:50]}")

        # 4. BILAN FINAL
        print(f"\n--- 📝 LOGS PARTANTS DEMAIN ({tomorrow}) ---")
        if tomorrow_logs:
            for line in tomorrow_logs: print(line)
        else: print("Aucun partant pour demain.")
        
        if today_results:
            print(f"\n📧 Envoi email (Aujourd'hui : {len(today_results)})")
            send_final_email("\n".join(today_results))

    except Exception as e:
        print(f"💥 Erreur globale : {e}")
        save_screenshot(driver, "CRASH_FINAL")
    finally:
        driver.quit()

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
