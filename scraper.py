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
    
    # 1. DEFINITION DES DATES
    now = datetime.now()
    today = now.strftime("%d/%m/%Y")
    tomorrow = (now + timedelta(days=1)).strftime("%d/%m/%Y")
    
    print(f"--- 📅 INITIALISATION DES DATES ---")
    print(f"Aujourd'hui recherché : [{today}]")
    print(f"Demain recherché     : [{tomorrow}]")
    print(f"----------------------------------\n")
    
    today_results = []
    tomorrow_logs = []

    try:
        # 2. CONNEXION
        print(f"🌐 Navigation vers : {URL_LOGIN}")
        driver.get(URL_LOGIN)
        try:
            wait.until(EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler"))).click()
            print("🍪 Cookies acceptés.")
        except: pass

        print("🔑 Saisie des identifiants...")
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "#user-login-form input[name='name']"))).send_keys(EMAIL_SENDER)
        driver.find_element(By.CSS_SELECTOR, "#user-login-form input[name='pass']").send_keys(FG_PASSWORD)
        driver.execute_script("arguments[0].click();", driver.find_element(By.ID, "edit-submit"))
        time.sleep(5)

        # 3. ANALYSE DES ENTRAINEURS
        for trainer_url in URLS_ENTRAINEURS:
            print(f"\n--- 🏠 ANALYSE ENTRAINEUR : {trainer_url} ---")
            driver.get(trainer_url)
            time.sleep(8) # On laisse bien charger le JS
            
            try:
                t_name = driver.find_element(By.CSS_SELECTOR, "h1, .page-title").text
                trainer_name = clean_text(t_name).replace("ENTRAINEUR", "").strip()
                print(f"👤 Nom détecté : {trainer_name}")
            except: trainer_name = "Inconnu"

            # Récupération de toutes les lignes du tableau
            rows = driver.find_elements(By.CSS_SELECTOR, "table tr")
            print(f"📊 {len(rows)} lignes trouvées dans le tableau.")

            runners_to_process = []

            for idx, row in enumerate(rows):
                txt = row.text.strip()
                if not txt: continue
                
                # LOG DE CHAQUE LIGNE POUR VOIR LE FORMAT DES DATES
                is_today = today in txt
                is_tomorrow = tomorrow in txt
                
                if is_today or is_tomorrow:
                    status = "✅ MATCH AUJOURD'HUI" if is_today else "🕒 MATCH DEMAIN"
                    print(f"   [Ligne {idx}] {status} | Contenu : {txt[:100]}...")
                    
                    try:
                        link_el = row.find_element(By.CSS_SELECTOR, "a[href*='/course/']")
                        cells = row.find_elements(By.TAG_NAME, "td")
                        
                        runners_to_process.append({
                            'date_label': today if is_today else tomorrow,
                            'horse_name': clean_text(cells[4].text),
                            'horse_search': clean_text(cells[4].text)[:10].lower(),
                            'url': link_el.get_attribute("href"),
                            'trainer': trainer_name,
                            'course_simple': clean_text(cells[3].text)
                        })
                    except Exception as e:
                        print(f"   ⚠️ Erreur d'extraction sur ligne {idx} : {e}")
                else:
                    # Optionnel : décommenter la ligne suivante pour voir TOUTES les lignes même celles qui ne matchent pas
                    # print(f"   [Ligne {idx}] Ignorée (Date non match)")
                    pass

            # 4. EXTRACTION PRÉCISE SUR LA FICHE COURSE
            for r in runners_to_process:
                print(f"\n   🔎 FICHE COURSE : {r['horse_name']} ({r['date_label']})")
                print(f"   🔗 URL : {r['url']}")
                driver.get(r['url'])
                time.sleep(6)
                
                try:
                    # INFOS EN-TETE (Image 17115d)
                    header_p = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".course-detail p, .course-date-place"))).text
                    print(f"      DEBUG Header : {header_p}")
                    
                    match_h = re.search(r'\d{1,2}[h:]\d{2}', header_p)
                    heure = match_h.group(0) if match_h else "00:00"
                    hippodrome = clean_text(header_p.split(",")[-1])

                    # NUMÉRO (Image 171578)
                    xpath_horse = f"//div[contains(@class, 'raceTable')]//tr[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{r['horse_search']}')]"
                    horse_row = wait.until(EC.presence_of_element_located((By.XPATH, xpath_horse)))
                    print(f"      DEBUG Ligne Cheval : {horse_row.text[:80]}...")
                    
                    num_raw = horse_row.find_elements(By.TAG_NAME, "td")[0].text.strip()
                    num_cheval = "".join(filter(str.isdigit, num_raw)) or "?"

                    final_line = f"{r['date_label']} / {hippodrome} / {heure} / {r['course_simple']} / N°{num_cheval} {r['horse_name']} (Entr: {r['trainer']})"
                    
                    if r['date_label'] == today:
                        today_results.append(final_line)
                    else:
                        tomorrow_logs.append(final_line)
                    print(f"      ✨ SUCCÈS : Ajouté à la liste.")

                except Exception as e:
                    print(f"      ❌ ÉCHEC EXTRACTION : {str(e)[:100]}")

        # 5. RÉSULTATS FINAUX
        print("\n==========================================")
        print(f"🏁 BILAN : {len(today_results)} auj. / {len(tomorrow_logs)} demain.")
        print("==========================================")
        
        print("\n--- 📝 LOGS PARTANTS DEMAIN ---")
        if tomorrow_logs:
            for line in tomorrow_logs:
                print(line)
        else:
            print(f"AUCUN PARTANT TROUVÉ POUR DEMAIN ({tomorrow}).")
        print("-------------------------------\n")

        if today_results:
            print(f"📧 Envoi de l'email pour aujourd'hui...")
            send_final_email("\n".join(today_results))

    except Exception as e:
        print(f"💥 ERREUR CRITIQUE : {e}")
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
