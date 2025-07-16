import scrapy
import json
import time
import os
import base64
from config import TOKEN



class ProxySpider(scrapy.Spider):

    name = "proxyspider"
    allowed_domains = ["advanced.name", "test-rg8.ddns.net"]
    start_urls = [
        "https://advanced.name/freeproxy",
        "https://advanced.name/freeproxy?page=2"
    ]
    custom_settings = {
        'DOWNLOAD_DELAY': 0.5,
        'CONCURRENT_REQUESTS': 1,
        'ROBOTSTXT_OBEY': False,
    }

    MAX_FIELDS = 10
    MIN_PROXIES = 3
    form_url = "https://test-rg8.ddns.net/task"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.proxies = []
        self.results = {}
        self.start_time = None
        if os.path.exists("results.json"):
            try:
                with open("results.json", "r", encoding="utf-8") as f:
                    self.results = json.load(f)
            except Exception:
                self.results = {}

    def start_requests(self):
        self.start_time = time.time()
        for url in self.start_urls:
            yield scrapy.Request(url, callback=self.parse_proxy_page)

    def parse_proxy_page(self, response):
        with open(f'debug_{int(time.time())}.html', 'w', encoding='utf-8') as f:
            f.write(response.text)
        rows = response.xpath("/html/body/section[2]/div[4]/table/tbody/tr")
        self.logger.info(f"Найдено строк: {len(rows)}")
        for row in rows:
            if len(self.proxies) >= 150:
                break
            ip_b64 = row.xpath("./td[2]/@data-ip").get(default='').strip()
            port_b64 = row.xpath("./td[3]/@data-port").get(default='').strip()
            try:
                ip = base64.b64decode(ip_b64).decode() if ip_b64 else ''
                port = int(base64.b64decode(port_b64).decode()) if port_b64 else 0
            except Exception:
                continue
            proto_tags = row.xpath("./td[4]/a/text()").getall()
            protocols = [p.strip() for p in proto_tags] if proto_tags else []
            self.proxies.append({
                "ip": ip,
                "port": port,
                "protocols": protocols
            })
        if response.url.endswith('page=2') or len(self.proxies) >= 150:
            with open("proxies.json", "w", encoding="utf-8") as f:
                json.dump(self.proxies, f, ensure_ascii=False, indent=4)
            self.logger.info(f"Сохранено {len(self.proxies)} прокси в proxies.json")
            yield from self.send_chunks()

    def chunked_min(self, lst, min_n, max_fields):
        for i in range(0, len(lst), max_fields):
            chunk = lst[i:i + max_fields]
            if len(chunk) < min_n:
                break
            yield chunk

    def send_chunks(self):
        chunks = list(self.chunked_min(self.proxies, self.MIN_PROXIES, self.MAX_FIELDS))
        for chunk_idx, chunk in enumerate(chunks):
            meta = {
                'chunk': chunk,
                'chunk_idx': chunk_idx,
                'attempt': 1
            }
            yield scrapy.Request(
                self.form_url,
                callback=self.fill_form,
                meta=meta,
                dont_filter=True
            )

    def fill_form(self, response):
        chunk = response.meta['chunk']
        chunk_idx = response.meta['chunk_idx']
        attempt = response.meta['attempt']
        formdata = {"token": TOKEN}
        for idx, proxy in enumerate(chunk):
            formdata[f"proxies.{idx}.value"] = f'{proxy["ip"]}:{proxy["port"]}'
        yield scrapy.FormRequest(
            self.form_url,
            formdata=formdata,
            callback=self.after_submit,
            meta={
                'chunk': chunk,
                'chunk_idx': chunk_idx,
                'attempt': attempt,
                'formdata': formdata
            },
            dont_filter=True
        )

    def after_submit(self, response):
        chunk = response.meta['chunk']
        chunk_idx = response.meta['chunk_idx']
        attempt = response.meta['attempt']
        formdata = response.meta['formdata']
        page_text = response.text
        if "Success! Your save_id:" in page_text:
            save_id = page_text.split("Success! Your save_id:")[-1].split("<")[0].strip().split()[0]
            self.logger.info(f"Отправлено {len(chunk)} прокси, save_id: {save_id}")
            self.results[save_id] = [f'{proxy["ip"]}:{proxy["port"]}' for proxy in chunk]
            self.save_results()
        else:
            if "Too Many Requests" in page_text or "429" in page_text:
                self.logger.warning("Достигнут лимит запросов. Ожидание 1 минуту...")
                time.sleep(60)
                if attempt < 3:
                    yield scrapy.FormRequest(
                        self.form_url,
                        formdata=formdata,
                        callback=self.after_submit,
                        meta={
                            'chunk': chunk,
                            'chunk_idx': chunk_idx,
                            'attempt': attempt + 1,
                            'formdata': formdata
                        },
                        dont_filter=True
                    )
            else:
                self.logger.warning(f"Не удалось найти save_id на странице для чанка {chunk_idx}")
        time.sleep(10)

    def save_results(self):
        with open("results.json", "w", encoding="utf-8") as f:
            json.dump(self.results, f, ensure_ascii=False, indent=4)

    def closed(self, reason):
        if self.start_time is not None:
            end_time = time.time()
            elapsed = int(end_time - self.start_time)
            hours = elapsed // 3600
            minutes = (elapsed % 3600) // 60
            seconds = elapsed % 60
            with open("time.txt", "w", encoding="utf-8") as f:
                f.write(f"Время выполнения: {hours:02d}:{minutes:02d}:{seconds:02d}\n")
            self.logger.info("Готово! Все save_id и прокси сохранены в results.json")
        else:
            self.logger.warning("Spider closed before start_time was set.")
