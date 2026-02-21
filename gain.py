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
# URLs ciblées sur les dernières courses
URLS_ENTRAINEURS = [
    "https://www.france-galop.com/fr/entraineur/Z1FxYXQ3cFJyM0ZlUitJQTlmUTNiUT09#dernieres-courses",
    "https://www.france-galop.com/fr/entraineur/U0VNb0JtQlZ1bUphYndFTnJjSzg4dz09#dernieres-courses"
]

FG_PASSWORD = os.getenv("FG_PASSWORD")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")
EMAIL_SENDER = os.getenv("EMAIL_SENDER")
EMAIL_DEST = os.getenv("EMAIL_DEST")

def clean_text(text):
    if not text: return "N/A"
    cleaned = re.sub(r'[^a-zA-Z0-9/:\.€ ]', '', text)
    return " ".join(cleaned.split()).strip()

def parse_date(date_str):
    """Convertit une chaîne DD/MM/YYYY en objet datetime."""
    try:
        return datetime.strptime(date_str.strip(), "%d/%m/%Y")
    except:
        return None

def run_scraper_history():
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36")
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    wait = WebDriverWait(driver, 20)
    
    # 1. Calcul de la fenêtre [J-7 ; J]
    today = datetime.now().replace(hour=23, minute=59)
    start_date = (today - timedelta(days=7)).replace(hour=0, minute=0)
    
    final_report = []

    try:
        # --- CONNEXION ---
        driver.get(URL_LOGIN)
        try:
            wait.until(EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler"))).click()
        except: pass

        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "#user-login-form input[name='name']"))).send_keys(EMAIL_SENDER)
        driver.find_element(By.CSS_SELECTOR, "#user-login-form input[name='pass']").send_keys(FG_PASSWORD)
        login_btn = driver.find_element(By.CSS_SELECTOR, "#user-login-form button[type='submit']")
        driver.execute_script("arguments[0].click();", login_btn)
        time.sleep(5)

        # --- ANALYSE DES ENTRAINEURS ---
        for trainer_url in URLS_ENTRAINEURS:
            print(f"Analyse de l'entraîneur : {trainer_url}")
            driver.get(trainer_url)
            time.sleep(5)
            
            try:
                trainer_name = clean_text(driver.find_element(By.CSS_SELECTOR, "h1").text).replace("ENTRAINEUR", "").strip()
            except:
                trainer_name = "Inconnu"

            # On cherche le tableau des dernières courses
            # Généralement situé dans une div spécifique ou identifié par sa structure
            rows = driver.find_elements(By.CSS_SELECTOR, "table.views-table tr, .last-races-table tr")
            
            if not rows:
                # Fallback si le sélecteur spécifique échoue, on prend tous les TR
                rows = driver.find_elements(By.TAG_NAME, "row") 

            for row in rows:
                cells = row.find_elements(By.TAG_NAME, "td")
                if len(cells) < 5: continue
                
                # Extraction des données par index (ajustable selon le DOM exact de France Galop)
                raw_date = cells[0].text.strip()
                horse_name = clean_text(cells[1].text)
                race_name = clean_text(cells[2].text)
                place = clean_text(cells[3].text)
                prize = clean_text(cells[4].text) if len(cells) > 4 else "N/A"
                odds = clean_text(cells[5].text) if len(cells) > 5 else "N/A"

                # 3. Filtrage Temporel
                race_dt = parse_date(raw_date)
                if race_dt and start_date <= race_dt <= today:
                    
                    # 4. Filtrage Place (1er, 2e, 3e, 4e)
                    # On cherche si le chiffre 1, 2, 3 ou 4 est présent dans la cellule place
                    match_place = re.search(r'([1-4])', place)
                    
                    if match_place:
                        rank_found = match_place.group(1)
                        # 9. Construction de la ligne
                        line = f"Entraîneur - cheval : {trainer_name} - {horse_name} - {raw_date} - {race_name} - {rank_found}e - {prize} - {odds}"
                        final_report.append(line)
                        print(f"  ✅ Retenu : {horse_name} ({rank_found}e)")

        # 10. Envoi de l'email
        if final_report:
            content = "\n".join(final_report)
            send_final_email(content)
            print("\n📧 Email envoyé avec succès.")
        else:
            print("\nℹ️ Aucune performance trouvée dans les critères.")

    except Exception as e:
        print(f"💥 Erreur globale : {e}")
    finally:
        driver.quit()

def send_final_email(content):
    msg = MIMEMultipart()
    msg['From'] = EMAIL_SENDER
    #msg['To'] = EMAIL_DEST
    msg['To'] = "stephane.evain@gmail.com"
    msg['Subject'] = f"Top Performances 7j - France Galop ({datetime.now().strftime('%d/%m/%Y')})"
    
    body = f"Voici les chevaux classés dans les 4 premiers sur les 7 derniers jours :\n\n{content}"
    msg.attach(MIMEText(body, 'plain'))
    
    try:
        with smtplib.SMTP('smtp.gmail.com', 587) as s:
            s.starttls()
            s.login(EMAIL_SENDER, GMAIL_APP_PASSWORD)
            s.send_message(msg)
    except Exception as e:
        print(f"❌ Erreur email : {e}")

if __name__ == "__main__":
    run_scraper_history()
