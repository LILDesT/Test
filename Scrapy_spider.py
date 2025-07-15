from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
import json
import time
import requests
from config import TOKEN
import os

# Перемещаем импорты selenium.webdriver.common.by и keys сюда, после инициализации selenium
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

options = Options()
options.add_argument("--headless")
driver = webdriver.Chrome(options=options)

proxies = []

# 1 стр
url1 = "https://advanced.name/freeproxy"
driver.get(url1)
time.sleep(5)
soup = BeautifulSoup(driver.page_source, "html.parser")
table = soup.find("table")
if table and table.name == "table":
    rows = table.find_all("tr")[1:]
    for row in rows:
        if len(proxies) >= 150:
            break
        cols = row.find_all("td")
        if len(cols) >= 4:
            ip = cols[1].get_text(strip=True)
            port_str = cols[2].get_text(strip=True)
            try:
                port = int(port_str)
            except ValueError:
                continue  # пропускаем если порт не число
            proto_tags = cols[3].find_all("a")
            if proto_tags:
                protocols = [a.get_text(strip=True) for a in proto_tags]
            else:
                protocols = [cols[3].get_text(strip=True)]
            proxies.append({
                "ip": ip,
                "port": port,
                "protocols": protocols
            })

# 2 стр
if len(proxies) < 150:
    url2 = "https://advanced.name/freeproxy?page=2"
    driver.get(url2)
    time.sleep(5)
    soup = BeautifulSoup(driver.page_source, "html.parser")
    table = soup.find("table")
    if table and table.name == "table":
        rows = table.find_all("tr")[1:]
        for row in rows:
            if len(proxies) >= 150:
                break
            cols = row.find_all("td")
            if len(cols) >= 4:
                ip = cols[1].get_text(strip=True)
                port_str = cols[2].get_text(strip=True)
                try:
                    port = int(port_str)
                except ValueError:
                    continue
                proto_tags = cols[3].find_all("a")
                if proto_tags:
                    protocols = [a.get_text(strip=True) for a in proto_tags]
                else:
                    protocols = [cols[3].get_text(strip=True)]
                proxies.append({
                    "ip": ip,
                    "port": port,
                    "protocols": protocols
                })

driver.quit()

with open("proxies.json", "w", encoding="utf-8") as f:
    json.dump(proxies, f, ensure_ascii=False, indent=4)

print(f"Сохранено {len(proxies)} прокси в proxies.json")

# --- Отправка чанками по 10 --
MAX_FIELDS = 10 
MIN_PROXIES = 3

def chunked_min(lst, min_n, max_fields):
    for i in range(0, len(lst), max_fields):
        chunk = lst[i:i + max_fields]
        if len(chunk) < min_n:
            break
        yield chunk

results = {}
if os.path.exists("results.json"):
    with open("results.json", "r", encoding="utf-8") as f:
        try:
            results = json.load(f)
        except Exception:
            results = {}

options = Options()
options.add_argument("--headless")
driver = webdriver.Chrome(options=options)

url = "https://test-rg8.ddns.net/task"

start_time = time.time()
chunks = list(chunked_min(proxies, MIN_PROXIES, MAX_FIELDS))
chunk_idx = 0
while chunk_idx < len(chunks):
    chunk = chunks[chunk_idx]
    # До 3 попыток загрузить форму
    for attempt in range(3):
        driver.get(url)
        time.sleep(3)
        try:
            token_input = driver.find_element(By.NAME, "token")
            break
        except Exception:
            time.sleep(3)
    else:
        print("Не удалось найти форму для отправки, пропускаем чанк")
        chunk_idx += 1
        continue

    repeat_chunk = False
    try:
        token_input.clear()
        token_input.send_keys(TOKEN)
        for idx, proxy in enumerate(chunk):
            field_name = f"proxies.{idx}.value"
            try:
                proxy_input = driver.find_element(By.NAME, field_name)
                proxy_input.clear()
                proxy_input.send_keys(f'{proxy["ip"]}:{proxy["port"]}')
            except Exception as e:
                print(f"Не найдено поле {field_name}: {e}")

        submit_btn = driver.find_element(By.XPATH, "//button[@type='submit']")
        submit_btn.click()
        time.sleep(3)

        try:
            success_div = driver.find_element(By.XPATH, "//*[contains(text(), 'Success! Your save_id:')]")
            save_id = success_div.text.split(":")[-1].strip()
            print(f"Отправлено {len(chunk)} прокси, save_id: {save_id}")
            results[save_id] = [f'{proxy["ip"]}:{proxy["port"]}' for proxy in chunk]
            
            try:
                close_btn = driver.find_element(By.XPATH, "//button[@aria-label='Close']")
                close_btn.click()
                time.sleep(1)
            except Exception:
                pass
        except Exception:
            print("Не удалось найти save_id на странице")
            with open(f"error_page_{chunk_idx}.html", "w", encoding="utf-8") as f:
                f.write(driver.page_source)
            
            if "Too Many Requests" in driver.page_source or "429" in driver.page_source:
                print("Достигнут лимит запросов. Ожидание 1 минуту...")
                time.sleep(60)
                repeat_chunk = True
    except Exception as e:
        print(f"Ошибка при обработке чанка: {e}")

    driver.delete_all_cookies()
    time.sleep(10)

    if repeat_chunk:
        continue  # повторить тот же чанк

    chunk_idx += 1
    if chunk_idx % 3 == 0:
        driver.quit()
        driver = webdriver.Chrome(options=options)

with open("results.json", "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=4)

driver.quit()
print("Готово! Все save_id и прокси сохранены в results.json") 
end_time = time.time()
elapsed = int(end_time - start_time)
hours = elapsed // 3600
minutes = (elapsed % 3600) // 60
seconds = elapsed % 60
with open("time.txt", "w", encoding="utf-8") as f:
    f.write(f"Время выполнения: {hours:02d}:{minutes:02d}:{seconds:02d}\n") 