import os
import time
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def setup_driver():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    return webdriver.Chrome(options=options)

def login(driver):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🔑 Connexion à France Galop...")
    try:
        driver.get("https://www.france-galop.com/fr/user/login")
        # Attente du champ email (ajustez le sélecteur si besoin)
        wait = WebDriverWait(driver, 15)
        email_field = wait.until(EC.presence_of_element_located((By.ID, "edit-name")))
        pass_field = driver.find_element(By.ID, "edit-pass")
        
        email_field.send_keys(os.getenv("EMAIL_SENDER")) # Ou votre login
        pass_field.send_keys(os.getenv("FG_PASSWORD"))
        
        driver.find_element(By.ID, "edit-submit").click()
        time.sleep(5)
        print("✅ Connexion réussie.")
    except Exception as e:
        print(f"❌ Échec de la connexion : {e}")
        driver.save_screenshot("login_error.png")

def extract_gains(driver, coach_id):
    url = f"https://www.france-galop.com/fr/entraineur/{coach_id}"
    driver.get(url)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🚀 Analyse : {coach_id}")
    
    # Stabilisation
    time.sleep(5)
    
    # Capture d'écran pour vérification
    screenshot_name = f"view_{coach_id[:8]}.png"
    driver.save_screenshot(screenshot_name)
    
    total_gains = 0
    try:
        # On cible spécifiquement le tableau des dernières courses
        wait = WebDriverWait(driver, 10)
        table = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "table.table-striped")))
        
        rows = table.find_elements(By.CSS_SELECTOR, "tbody tr")
        
        for row in rows:
            cols = row.find_elements(By.TAG_NAME, "td")
            if len(cols) > 10: # Vérifie qu'on a bien toutes les colonnes
                # Colonne Gain est généralement l'index 9 (à vérifier selon le tableau)
                gain_text = cols[9].text.strip()
                
                if gain_text and gain_text != "-":
                    # Nettoyage du format : "11.440" -> 11440
                    clean_gain = int(gain_text.replace(".", "").replace(" ", ""))
                    total_gains += clean_gain
        
        print(f"💰 Total Gains extraits : {total_gains} €")
        return total_gains

    except Exception as e:
        print(f"⚠️ Format de stats inhabituel ou tableau absent pour {coach_id}")
        return 0

def main():
    driver = setup_driver()
    try:
        login(driver)
        
        # Exemple de liste d'IDs (à remplacer par votre logique de récupération d'IDs)
        list_of_ids = ["U0VNb0JtQlZ1bUpYndFTnJzZz4dz09"] 
        
        results = {}
        for cid in list_of_ids:
            gain = extract_gains(driver, cid)
            results[cid] = gain
            
        if not results or sum(results.values()) == 0:
            print("📝 Aucune donnée de gain extraite.")
        
    finally:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 🏁 Fin de session Gain.")
        driver.quit()

if __name__ == "__main__":
    main()
