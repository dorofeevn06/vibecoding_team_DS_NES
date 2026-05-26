import os
import re
from datetime import datetime
from urllib.parse import urljoin

import pandas as pd
import requests
from bs4 import BeautifulSoup


class EquipmentParser:
    """
    Статический парсер оборудования для бильярдной.

    Назначение файла:
    1. Собрать сырые данные о товарах и ценах на оборудование.
    2. Использовать статический парсинг: requests + BeautifulSoup.
    3. Сохранить результат в data/raw/equipment_raw.csv.

    Важно:
    этот файл не занимается обработкой, анализом, графиками и выводами.
    Processing оборудования должен быть вынесен в отдельный файл.
    """

    BASE_URL = "https://www.billiard1.ru"

    CATEGORY_URLS = {
        "tables": "https://www.billiard1.ru/catalog/bilyardnye_stoly/",
        "cues": "https://www.billiard1.ru/catalog/kii/",
        "balls": "https://www.billiard1.ru/catalog/bilyardnye_shary/",
        "cloth": "https://www.billiard1.ru/catalog/sukno/",
        "lighting": "https://www.billiard1.ru/catalog/svetilniki_lampy/",
        "game_sets": "https://www.billiard1.ru/catalog/nabory_dlya_igry/",
        "cue_accessories": "https://www.billiard1.ru/catalog/vsye_dlya_kiya/",
    }

    def __init__(self, output_path="data/raw/equipment_raw.csv", max_pages=10):
        self.output_path = output_path
        self.max_pages = max_pages
        self.store_name = "Billiard1 / Ozone Billiards"

        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
            }
        )

    @staticmethod
    def clean_text(value):
        if value is None:
            return ""
        return re.sub(r"\s+", " ", value).strip()

    @staticmethod
    def parse_price(value):
        if value is None:
            return None

        value = str(value).replace("\xa0", " ")
        value = re.sub(r"[^0-9]", "", value)

        if value == "":
            return None

        return int(value)

    def build_page_url(self, category_url, page):
        if page == 1:
            return category_url
        return f"{category_url}?PAGEN_1={page}"

    def get_soup(self, url):
        response = self.session.get(url, timeout=20)
        response.raise_for_status()
        response.encoding = response.apparent_encoding
        return BeautifulSoup(response.text, "lxml")

    def find_product_cards(self, soup):
        selectors = [
            ".catalog_block .item",
            ".catalog-item",
            ".product-item",
            ".catalog_item",
            ".item_block",
            "[data-entity='item']",
        ]

        for selector in selectors:
            cards = soup.select(selector)
            if len(cards) > 0:
                return cards

        return []

    def extract_product_name(self, card):
        selectors = [
            ".item-title a",
            ".item-title",
            ".title a",
            ".title",
            ".name a",
            ".name",
            "a[href*='/catalog/']",
        ]

        for selector in selectors:
            element = card.select_one(selector)
            if element:
                name = self.clean_text(element.get_text(" "))
                if len(name) >= 3:
                    return name

        return ""

    def extract_product_url(self, card):
        link = card.select_one("a[href*='/catalog/']")
        if not link:
            return ""

        href = link.get("href")
        if not href:
            return ""

        return urljoin(self.BASE_URL, href)

    def extract_price_from_card(self, card):
        price_selectors = [
            ".price",
            ".price_value",
            ".cost",
            ".current_price",
            ".catalog-item-price",
            "[class*='price']",
        ]

        for selector in price_selectors:
            elements = card.select(selector)
            for element in elements:
                text = self.clean_text(element.get_text(" "))
                if "руб" in text.lower() or "₽" in text:
                    price = self.parse_price(text)
                    if price is not None and price > 0:
                        return price

        text = self.clean_text(card.get_text(" "))
        price_candidates = re.findall(
            r"(?:от\s*)?(\d[\d\s]{2,})\s*(?:руб|₽)",
            text,
            flags=re.IGNORECASE,
        )

        parsed_prices = []
        for candidate in price_candidates:
            price = self.parse_price(candidate)
            if price is not None and price > 0:
                parsed_prices.append(price)

        if len(parsed_prices) == 0:
            return None

        return min(parsed_prices)

    def parse_category_page(self, category, page_url):
        soup = self.get_soup(page_url)
        cards = self.find_product_cards(soup)

        products = []
        for card in cards:
            product_name = self.extract_product_name(card)
            price = self.extract_price_from_card(card)
            product_url = self.extract_product_url(card)

            if product_name == "" or price is None:
                continue

            products.append(
                {
                    "product_name": product_name,
                    "category": category,
                    "price": price,
                    "store": self.store_name,
                    "product_url": product_url,
                    "source_url": page_url,
                    "parsed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }
            )

        return products

    def parse_all_categories(self):
        all_products = []

        for category, category_url in self.CATEGORY_URLS.items():
            print(f"\nСобираю категорию: {category}")
            previous_page_products = set()

            for page in range(1, self.max_pages + 1):
                page_url = self.build_page_url(category_url, page)
                print(f"  Страница {page}: {page_url}")

                try:
                    products = self.parse_category_page(category, page_url)
                except requests.exceptions.HTTPError as error:
                    print(f"    HTTP-ошибка: {error}")
                    break
                except requests.exceptions.RequestException as error:
                    print(f"    Ошибка запроса: {error}")
                    break

                if len(products) == 0:
                    print("    Товары не найдены, останавливаю категорию.")
                    break

                current_page_products = {
                    (product["product_name"], product["category"], product["price"])
                    for product in products
                }

                if page > 1 and current_page_products == previous_page_products:
                    print("    Страница повторяет предыдущую, пагинация закончилась.")
                    break

                print(f"    Найдено товаров: {len(products)}")
                all_products.extend(products)
                previous_page_products = current_page_products

        return all_products

    def save_to_csv(self, products):
        os.makedirs(os.path.dirname(self.output_path), exist_ok=True)

        df = pd.DataFrame(products)

        if not df.empty:
            df = df.drop_duplicates(subset=["product_name", "category", "price", "store"])
            df = df.sort_values(["category", "price", "product_name"])

        df.to_csv(self.output_path, index=False, encoding="utf-8-sig")

        print("\nСохранение завершено.")
        print(f"Файл: {self.output_path}")
        print(f"Итоговое количество строк: {len(df)}")

        if not df.empty:
            print("\nКоличество товаров по категориям:")
            print(df["category"].value_counts())

        return df

    def run(self):
        print("Запускаю статический парсинг оборудования.")
        print(f"Источник: {self.store_name}")
        print(f"Максимум страниц на категорию: {self.max_pages}")

        products = self.parse_all_categories()
        df = self.save_to_csv(products)

        return df


if __name__ == "__main__":
    parser = EquipmentParser(
        output_path="data/raw/equipment_raw.csv",
        max_pages=10,
    )

    equipment_df = parser.run()

    print("\nПервые строки итоговой сырой таблицы:")
    print(equipment_df.head())