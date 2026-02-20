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

# --- CONFIGURATION DES SECRETS ---
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
    """Génère une capture d'écran pour les artifacts GitHub."""
    timestamp = datetime.now().strftime("%Hh%M_%S")
    filename = f"debug_{label}_{timestamp}.png"
    driver.save_screenshot(filename)
    print(f"📸 Screenshot : {filename}")

def check_session(driver):
    """Vérifie la session via l'indicateur 'Mon espace' et la classe 'user-logged-in'."""
    try:
        body_class = driver.find_element(By.TAG_NAME, "body").get_attribute("class")
        mon_espace = driver.find_elements(By.CSS_SELECTOR, "#block-francegalop-account-menu .menu-user")
        is_logged = "user-logged-in" in body_class and len(mon_espace) > 0
        print(f"--- 🔒 État Session : {'CONNECTÉ' if is_logged else 'DÉCONNECTÉ'} sur {driver.current_url} ---")
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
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    wait = WebDriverWait(driver, 25)
    
    today = datetime.now().strftime("%d/%m/%Y")
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%d/%m/%Y")
    
    today_results = []
    tomorrow_logs = []
    seen_course_urls = set()

    try:
        # 1. ÉTAPE DE CONNEXION
        driver.get(URL_LOGIN)
        try:
            wait.until(EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler"))).click()
        except: pass

        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "#user-login-form input[name='name']"))).send_keys(EMAIL_SENDER)
        driver.find_element(By.CSS_SELECTOR, "#user-login-form input[name='pass']").send_keys(FG_PASSWORD)
        
        login_btn = driver.find_element(By.CSS_SELECTOR, "#user-login-form button[type='submit']")
        driver.execute_script("arguments[0].click();", login_btn)
        
        time.sleep(7)
        if not check_session(driver):
            print("❌ Erreur : Connexion impossible.")
            return

        # 2. ANALYSE DES PAGES ENTRAINEURS
        for trainer_url in URLS_ENTRAINEURS:
            driver.get(trainer_url)
            time.sleep(8)
            check_session(driver)

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
                        course_url = link_el.get_attribute("href")
                        
                        if course_url in seen_course_urls: continue
                        seen_course_urls.add(course_url)

                        cells = row.find_elements(By.TAG_NAME, "td")
                        horse_name = clean_text(cells[0].text)
                        runners.append({
                            'date': today if today in txt else tomorrow,
                            'horse': horse_name,
                            'horse_search': horse_name[:10].lower(),
                            'url': course_url,
                            'trainer': trainer_name,
                            'course_simple': clean_text(cells[4].text)
                        })
                    except: continue

            # 3. EXTRACTION SUR LA FICHE COURSE
            for r in runners:
                print(f"   🔗 Ouverture Course : {r['url']}")
                driver.get(r['url'])
                time.sleep(6)
                check_session(driver)
                
                # --- CAPTURE D'ÉCRAN DE LA PAGE COURSE ---
                save_screenshot(driver, f"course_{r['horse'][:5]}")
                
                try:
                    paragraphs = driver.find_elements(By.CSS_SELECTOR, ".course-detail p")
                    heure, hippodrome, n_course = "00:00", "Inconnu", "?"
                    
                    for p in paragraphs:
                        p_txt = p.text
                        if "2026" in p_txt and "(" in p_txt:
                            print(f"      📝 Info Header : {p_txt}")
                            
                            # REGEX : Extrait le chiffre au début avant 'ème' ou '('
                            match_n = re.search(r'^(\d+)', p_txt.strip())
                            if match_n: n_course = match_n.group(1)
                            
                            # REGEX : Heure
                            match_h = re.search(r'(\d{1,2}h\d{2})', p_txt)
                            if match_h: heure = match_h.group(1)
                            
                            # Hippodrome
                            if "," in p_txt: hippodrome = clean_text(p_txt.split(",")[-1])
                            break

                    # Extraction du N° dans le tableau
                    xpath_horse = f"//div[contains(@class, 'raceTable')]//tr[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{r['horse_search']}')]"
                    horse_row = wait.until(EC.presence_of_element_located((By.XPATH, xpath_horse)))
                    num_cheval = "".join(filter(str.isdigit, horse_row.find_elements(By.TAG_NAME, "td")[0].text.strip()))

                    final_line = f"{r['date']} / {hippodrome} / {n_course} / {heure} / {r['course_simple']} / N°{num_cheval} {r['horse']} (Entr: {r['trainer']})"
                    
                    if r['date'] == today: today_results.append(final_line)
                    else: tomorrow_logs.append(final_line)
                    print(f"      ✅ Trouvé : Course {n_course} à {heure}")

                except Exception as e:
                    print(f"      ⚠️ Échec extraction : {str(e)[:50]}")

        # 4. BILAN FINAL
        print(f"\n--- 📝 LOGS PARTANTS DEMAIN ({tomorrow}) ---")
        if tomorrow_logs:
            for line in tomorrow_logs: print(line)
        else: print("Aucun partant pour demain.")
        
        if today_results:
            send_final_email("\n".join(today_results))

    except Exception as e:
        print(f"💥 Erreur globale : {e}")
    finally:
        driver.quit()

def send_final_email(content):
    msg = MIMEMultipart(); msg['From'] = EMAIL_SENDER; msg['To'] = EMAIL_DEST
    msg['Subject'] = f"Partants France Galop - {datetime.now().strftime('%d/%m/%Y')}"
    msg.attach(MIMEText(content, 'plain'))
    try:
        with smtplib.SMTP('smtp.gmail.com', 587) as s:
            s.starttls(); s.login(EMAIL_SENDER, GMAIL_APP_PASSWORD); s.send_message(msg)
    except: pass

if __name__ == "__main__":
    run_scraper()
