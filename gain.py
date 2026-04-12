import os
import re
import json
import time
import requests
import subprocess
from datetime import datetime, timedelta
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# --- CONFIGURATION ---
URL_HOME = "https://www.france-galop.com/fr"
URLS_ENTRAINEURS = [
    "https://www.france-galop.com/fr/entraineur/Z1FxYXQ3cFJyM0ZlUitJQTlmUTNiUT09#dernieres-courses",
    "https://www.france-galop.com/fr/entraineur/U0VNb0JtQlZ1bUphYndFTnJjSzg4dz09#dernieres-courses"
]

COOKIE_FILE = "cookies.json"
FG_PASSWORD = os.getenv("FG_PASSWORD")
EMAIL_SENDER = os.getenv("EMAIL_SENDER")
GREEN_API_URL = os.getenv("GREEN_API_URL")

def log(message):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")

def get_chrome_main_version():
    try:
        output = subprocess.check_output(['google-chrome', '--version']).decode('utf-8')
        version_str = output.strip().split()[2]
        return int(version_str.split('.')[0])
    except Exception as e:
        log(f"⚠️ Impossible de déterminer la version de Chrome : {e}")
        return None

def save_cookies(driver):
    with open(COOKIE_FILE, "w") as f:
        json.dump(driver.get_cookies(), f)
    log("💾 Cookies sauvegardés.")

def load_cookies(driver):
    if os.path.exists(COOKIE_FILE):
        with open(COOKIE_FILE, "r") as f:
            cookies = json.load(f)
            for cookie in cookies:
                try:
                    # Tente d'ajouter le cookie
                    driver.add_cookie(cookie)
                except Exception:
                    # Ignore silencieusement les cookies appartenant à d'autres domaines (Azure AD)
                    pass
        log("🍪 Cookies chargés depuis le cache.")
        return True
    return False

def clean_text(text):
    if not text: return "N/A"
    return " ".join(text.split()).strip()

def parse_date(date_str):
    try:
        return datetime.strptime(date_str.strip(), "%d/%m/%Y")
    except:
        return None

def send_whatsapp(message):
    if not GREEN_API_URL:
        log("⚠️ GREEN_API_URL manquante.")
        return
    payload = {"chatId": "33678723278-1540128478@g.us", "message": message}
    try:
        response = requests.post(GREEN_API_URL, json=payload, timeout=15)
        if response.status_code == 200: log("📲 Notification WhatsApp envoyée.")
    except Exception as e:
        log(f"❌ Erreur WhatsApp : {e}")

# --- PMU API HELPERS --- 
# --- PMU API HELPERS ---
def fetch_json_with_driver(driver, url, context=""):
    """Lit l'API PMU et affiche explicitement le résultat de chaque requête."""
    import urllib.parse
    
    try:
        log(f"   [DEBUG-PMU] [{context}] 🌐 GET {url}")
        driver.get(url)
        time.sleep(1.5) 
        
        page_source = driver.page_source
        
        if "ERR_NAME_NOT_RESOLVED" in page_source or "ERR_CONNECTION" in page_source:
            log(f"   [DEBUG-PMU] [{context}] ⚠️ Blocage DNS. Bascule sur Proxy...")
            encoded_url = urllib.parse.quote(url, safe='')
            proxy_url = f"https://api.allorigins.win/raw?url={encoded_url}"
            driver.get(proxy_url)
            time.sleep(2)
            
        try:
            json_text = driver.find_element(By.TAG_NAME, "pre").text
            data = json.loads(json_text)
            log(f"   [DEBUG-PMU] [{context}] ✅ JSON lu ! (Clés racines: {list(data.keys())[:5]})")
            return data
        except Exception as e:
            log(f"   [DEBUG-PMU] [{context}] ❌ Impossible de lire la balise <pre> JSON.")
            log(f"   [DEBUG-PMU] [{context}] Aperçu page: {driver.page_source[:150]}...")
            return None
    except Exception as e:
        log(f"   [DEBUG-PMU] [{context}] ❌ Erreur réseau critique: {e}")
        return None

def get_pmu_rapports(driver, date_str, hippodrome_name, horse_name):
    formatted_date = date_str.replace('/', '')
    base_url = "https://offline.turfinfo.api.pmu.fr/rest/client/7/programme"
    
    try:
        log(f"   [DEBUG-PMU] 🏁 START Recherche | Cheval: {horse_name} | Hippo: {hippodrome_name} | Date: {formatted_date}")
        programme = fetch_json_with_driver(driver, f"{base_url}/{formatted_date}", "Programme")
        
        if not programme or 'programme' not in programme: 
            log("   [DEBUG-PMU] ❌ Le JSON du programme est vide ou invalide.")
            return "Indisponible"
        
        reunions = programme['programme'].get('reunions', [])
        log(f"   [DEBUG-PMU] 📅 {len(reunions)} réunions trouvées ce jour-là.")
        
        fg_hippo_clean = re.sub(r'[^A-Z]', '', hippodrome_name.upper())
        fg_hippo_short = fg_hippo_clean[:6]
        
        for reunion in reunions:
            hippo_data = reunion.get('hippodrome', {})
            r_name = hippo_data.get('libelleCourt', '') + hippo_data.get('libelleLong', '') + reunion.get('libelle', '')
            r_name_clean = re.sub(r'[^A-Z]', '', r_name.upper())
            
            if fg_hippo_short and fg_hippo_short in r_name_clean:
                r_num = reunion.get('numOfficiel')
                log(f"   [DEBUG-PMU] 🏟️ Hippodrome matché ! C'est la R{r_num} ({r_name})")
                
                for course in reunion.get('courses', []):
                    c_num = course.get('numOrdre')
                    
                    partants = fetch_json_with_driver(driver, f"{base_url}/{formatted_date}/R{r_num}/C{c_num}/participants", f"Partants R{r_num}C{c_num}")
                    if not partants: continue
                    
                    for p in partants.get('participants', []):
                        if horse_name.upper() in p.get('nom', '').upper():
                            num_p = p.get('numero') or p.get('numProno') or p.get('num')
                            log(f"   [DEBUG-PMU] 🐎 Cheval matché ! {p.get('nom')} porte le N°{num_p}.")
                            return fetch_dividendes(driver, base_url, formatted_date, r_num, c_num, num_p, horse_name)
                            
        log(f"   [DEBUG-PMU] ❌ Cheval '{horse_name}' introuvable ou Hippodrome non matché.")
        return "Non trouvé"
        
    except Exception as e:
        log(f"   [DEBUG-PMU] 💥 Crash inattendu API PMU: {e}")
        return "Erreur API"

def fetch_dividendes(driver, base_url, date, r, c, num_p, horse_name="Cheval"):
    urls_a_tester = [
        f"{base_url}/{date}/R{r}/C{c}/rapports-definitifs",
        f"{base_url}/{date}/R{r}/C{c}/rapports"
    ]
    
    data = None
    for url in urls_a_tester:
        data = fetch_json_with_driver(driver, url, f"Rapports R{r}C{c}")
        if data: break
            
    if not data: 
        log("   [DEBUG-PMU] ❌ Aucun JSON de rapports lu pour cette course.")
        return "Pas de rapport"
    
    try:
        # Impression brute de l'architecture pour le débogage
        log(f"   [DEBUG-PMU] 🔍 Structure RAPPORTS brute : {str(data)[:250]}...")
        
        if isinstance(data, dict):
            paris_list = data.get('rapports', data.get('rapport', []))
        elif isinstance(data, list):
            paris_list = data
        else:
            return "Pas de rapport"
            
        sg, sp = 0.0, 0.0
        gagnants_debug = []
        
        for pari in paris_list:
            type_pari = pari.get('typePari', '')
            divs = pari.get('rapports', pari.get('dividendes', pari.get('gains', [])))
            
            if 'GAGNANT' in type_pari or type_pari == 'SG':
                for d in divs:
                    comb = d.get('combinaison', d.get('chevaux', d.get('numero', '')))
                    comb_str = str(comb[0]) if isinstance(comb, list) and comb else str(comb)
                    gagnants_debug.append(f"G({comb_str})")
                    if str(num_p) == comb_str or str(num_p).zfill(2) == comb_str:
                        val = d.get('dividende', d.get('dividendePourUnEuro', d.get('montant', 0)))
                        sg = float(val) / 100.0 if float(val) > 50 else float(val)
                        
            if 'PLACE' in type_pari or type_pari == 'SP':
                for d in divs:
                    comb = d.get('combinaison', d.get('chevaux', d.get('numero', '')))
                    comb_str = str(comb[0]) if isinstance(comb, list) and comb else str(comb)
                    gagnants_debug.append(f"P({comb_str})")
                    if str(num_p) == comb_str or str(num_p).zfill(2) == comb_str:
                        val = d.get('dividende', d.get('dividendePourUnEuro', d.get('montant', 0)))
                        sp = float(val) / 100.0 if float(val) > 50 else float(val)
        
        if sg > 0 and sp > 0: return f"Gagnant: {sg:.2f}€ | Placé: {sp:.2f}€"
        if sg > 0: return f"Gagnant: {sg:.2f}€"
        if sp > 0: return f"Placé: {sp:.2f}€"
        
        log(f"   [DEBUG-PMU] ❌ {horse_name} (N°{num_p}) introuvable dans les gains. Payés: {list(set(gagnants_debug))}")
        return "Pas de rapport"
        
    except Exception as e:
        log(f"   [DEBUG-PMU] 💥 Erreur d'analyse des dividendes: {e}")
        return "Erreur rapports"
        
# --- MAIN ---
def run_scraper_history():
    chrome_version = get_chrome_main_version()
    options = uc.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
   
    driver = uc.Chrome(options=options, version_main=chrome_version)
    wait = WebDriverWait(driver, 35)
    
    today = datetime.now()
    start_date = today - timedelta(days=7)
    final_report = []

    try:
        log("🌐 Accès France Galop...")
        driver.get(URL_HOME)
        
        if load_cookies(driver):
            driver.refresh()
            time.sleep(5)
            
        try:
            cookie_btn = wait.until(EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler")))
            cookie_btn.click()
            time.sleep(2)
        except:
            pass
        
        login_elements = driver.find_elements(By.CSS_SELECTOR, "a[href*='login'], .user-link")
        if login_elements:
            try:
                # ==========================================
                # DEBUT DU BLOC STRICTEMENT IDENTIQUE A gain(1).py
                # ==========================================
                log("🔑 Accès au portail de connexion...")
                login_btn = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='login'], .user-link")))
                driver.execute_script("arguments[0].click();", login_btn)

                log("📧 Saisie identifiant...")
                email_el = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "input[type='email'], input[name='username']")))
                for char in EMAIL_SENDER: email_el.send_keys(char)
                
                driver.execute_script("arguments[0].dispatchEvent(new Event('blur', { bubbles: true }));", email_el)
                btn_next = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Next')] | //button[@id='next']")))
                driver.execute_script("arguments[0].click();", btn_next)
                
                time.sleep(6)

                log("🔒 Saisie mot de passe...")
                pwd_el = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "input[type='password'], #password")))
                for char in FG_PASSWORD:
                    pwd_el.send_keys(char)
                    time.sleep(0.05)
                
                driver.execute_script("arguments[0].dispatchEvent(new Event('blur', { bubbles: true }));", pwd_el)
                btn_submit = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Sign in')] | //button[@id='next']")))
                driver.execute_script("arguments[0].click();", btn_submit)
                
                log("⏳ Stabilisation de la session (20s)...")
                time.sleep(20)
                # ==========================================
                # FIN DU BLOC STRICTEMENT IDENTIQUE A gain(1).py
                # ==========================================
                
                save_cookies(driver)
                log("✅ Connexion réussie.")
            except Exception as e:
                driver.save_screenshot("erreur_login_azure_gain.png")
                raise Exception("Impossible de passer l'écran de connexion.")
        else:
            log("✅ Session active via cookies.")

        # ==========================================
        # PHASE A : EXTRACTION DES PERFORMANCES (TOP 4)
        # ==========================================
        races_to_process = []
        
        for trainer_url in URLS_ENTRAINEURS:
            log(f"🚀 Analyse de la fiche : {trainer_url.split('/')[-1][:15]}...")
            driver.get(trainer_url)
            time.sleep(10)

            if "Accès refusé" in driver.page_source:
                log("❌ Blocage détecté. Rafraîchissement...")
                driver.refresh()
                time.sleep(8)

            try:
                tab = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='#dernieres-courses']")))
                driver.execute_script("arguments[0].click();", tab)
                time.sleep(5)
                
                trainer_name = driver.find_element(By.TAG_NAME, "h1").text.replace("ENTRAINEUR", "").strip()
                rows = driver.find_elements(By.CSS_SELECTOR, "#dernieres-courses table tbody tr")
                
                for row in rows:
                    cells = row.find_elements(By.TAG_NAME, "td")
                    if len(cells) < 12: continue 
                    
                    raw_date = cells[0].text.strip()       
                    place = cells[1].text.strip()          
                    horse_name = clean_text(cells[2].text) 
                    hippodrome = clean_text(cells[8].text) 
                    prize = clean_text(cells[11].text)     

                    race_dt = parse_date(raw_date)
                    if race_dt and start_date <= race_dt <= today:
                        match_place = re.search(r'^([1-4])$', place)
                        if match_place:
                            races_to_process.append({
                                'rank': match_place.group(1),
                                'date': raw_date,
                                'horse': horse_name,
                                'hippo': hippodrome,
                                'prize': prize,
                                'trainer': trainer_name
                            })
                            log(f"   ✅ Retenu : {horse_name} ({match_place.group(1)}e)")
            except Exception as e:
                log(f"⚠️ Erreur sur cet entraîneur : {str(e)[:50]}")

        # ==========================================
        # PHASE B : RECHERCHE DES RAPPORTS PARIEURS (PMU)
        # ==========================================
        for race in races_to_process:
            rapport_valide = None
            
            if race['rank'] in ['1', '2', '3']:
                log(f"   🔍 Recherche rapport PMU pour {race['horse']}...")
                
                rapport_pmu = get_pmu_rapports(
                    driver=driver,
                    date_str=race['date'],
                    hippodrome_name=race['hippo'],
                    horse_name=race['horse']
                )

                erreurs_exclues = ["Indisponible", "Non trouvé", "Erreur", "Pas de rapport"]
                if not any(err in rapport_pmu for err in erreurs_exclues):
                    rapport_valide = rapport_pmu

            lignes_msg = [
                f"🏆 *{race['horse']}* ({race['rank']}e)",
                f"📅 {race['date']} | 📍 {race['hippo']}",
                f"💰 Alloc: {race['prize']}€"
            ]
            
            if rapport_valide:
                lignes_msg.append(f"📈 PMU: {rapport_valide}")
                
            lignes_msg.append(f"👤 Entr: {race['trainer']}")
            
            final_report.append("\n".join(lignes_msg))

        # ==========================================
        # PHASE C : ENVOI WHATSAPP
        # ==========================================
        if final_report:
            header = f"💰 *TOP PERFORMANCES (7 derniers jours)*\n\n"
            full_message = header + "\n\n---\n\n".join(final_report)
            send_whatsapp(full_message)
            log("✅ Rapport hebdomadaire envoyé.")
        else:
            log("📝 Aucune performance de top 4 trouvée.")

    except Exception as e:
        log(f"💥 ERREUR CRITIQUE : {e}")
    finally:
        driver.quit()
        log("🏁 Session terminée.")

if __name__ == "__main__":
    run_scraper_history()
