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
    # On ajoute le User-Agent souvent présent dans les scrapers stables
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
    return webdriver.Chrome(options=options)

def login_method_scraper(driver):
    """ Utilise la même approche que scraper.py """
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🔑 Connexion (Méthode Scraper)...")
    try:
        driver.get("https://www.france-galop.com/fr/user/login")
        wait = WebDriverWait(driver, 20)
        
        # Attente des champs avec les sélecteurs standard
        email_field = wait.until(EC.presence_of_element_located((By.ID, "edit-name")))
        pass_field = driver.find_element(By.ID, "edit-pass")
        
        email_field.send_keys(os.getenv("EMAIL_SENDER"))
        pass_field.send_keys(os.getenv("FG_PASSWORD"))
        
        # Clic sur le bouton submit
        submit_btn = driver.find_element(By.ID, "edit-submit")
        driver.execute_script("arguments[0].click();", submit_btn)
        
        # Temps de stabilisation comme dans scraper.py
        time.sleep(10) 
        driver.save_screenshot("after_login_check.png")
        print("✅ Session initialisée.")
    except Exception as e:
        print(f"❌ Échec de la connexion méthode scraper : {e}")
        driver.save_screenshot("error_login_method.png")

def process_gain_table(driver, coach_id):
    url = f"https://www.france-galop.com/fr/entraineur/{coach_id}"
    driver.get(url)
    time.sleep(5) # Attente chargement JS
    
    total_gains = 0
    try:
        wait = WebDriverWait(driver, 15)
        # On cherche le tableau des résultats comme sur votre capture
        # Le sélecteur 'table' générique est plus sûr si les classes changent
        table = wait.until(EC.presence_of_element_located((By.XPATH, "//table[contains(@class, 'table')]")))
        
        driver.save_screenshot(f"table_debug_{coach_id[:5]}.png")
        
        rows = table.find_elements(By.TAG_NAME, "tr")
        for row in rows[1:]: # Skip header
            cols = row.find_elements(By.TAG_NAME, "td")
            if len(cols) >= 10:
                # On nettoie le texte (ex: '11.440' -> '11440')
                raw_val = cols[9].text.strip().replace('.', '').replace(' ', '')
                if raw_val.isdigit():
                    total_gains += int(raw_val)
        
        print(f"📊 {coach_id} : {total_gains} € extraits.")
        return total_gains

    except Exception as e:
        print(f"⚠️ Erreur sur {coach_id} : Tableau introuvable.")
        return 0

def main():
    driver = setup_driver()
    try:
        login_method_scraper(driver)
        
        # Remplacez par votre liste dynamique
        ids_to_check = ["U0VNb0JtQlZ1bUpYndFTnJzZz4dz09"] 
        
        for cid in ids_to_check:
            process_gain_table(driver, cid)
            
    finally:
        driver.quit()
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 🏁 Terminé.")

if __name__ == "__main__":
    main()
