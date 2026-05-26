"""Парсинг аренды коммерческой недвижимости с sob.ru."""

import random
import re
import time
from typing import Optional

import pandas as pd
import requests
from bs4 import BeautifulSoup

from .base import BaseScraper, _infer_district_from_address


class SobRentScraper(BaseScraper):
    """Аренда коммерческой недвижимости Москвы. ~35 карточек на странице, ~8 страниц."""

    BASE_URL = 'https://sob.ru/arenda-commercheskaya-nedvizhimost-moskva'
    HEADERS = {
        'User-Agent':      'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                           'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Accept':          'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'ru-RU,ru;q=0.9',
    }

    # Маппинг станций метро в округа. Покрывает популярные станции,
    # на остальных fallback по адресу.
    METRO_TO_OKRUG: dict[str, str] = {
        # ЦАО
        'Охотный Ряд': 'ЦАО', 'Площадь Революции': 'ЦАО', 'Театральная': 'ЦАО',
        'Арбатская': 'ЦАО', 'Александровский Сад': 'ЦАО', 'Боровицкая': 'ЦАО',
        'Библиотека имени Ленина': 'ЦАО', 'Кропоткинская': 'ЦАО', 'Парк культуры': 'ЦАО',
        'Киевская': 'ЦАО', 'Смоленская': 'ЦАО', 'Белорусская': 'ЦАО',
        'Новослободская': 'ЦАО', 'Проспект Мира': 'ЦАО', 'Комсомольская': 'ЦАО',
        'Красносельская': 'ЦАО', 'Лубянка': 'ЦАО', 'Китай-город': 'ЦАО',
        'Третьяковская': 'ЦАО', 'Новокузнецкая': 'ЦАО', 'Павелецкая': 'ЦАО',
        'Таганская': 'ЦАО', 'Курская': 'ЦАО', 'Бауманская': 'ЦАО',
        'Маяковская': 'ЦАО', 'Тверская': 'ЦАО', 'Чеховская': 'ЦАО',
        'Пушкинская': 'ЦАО', 'Кузнецкий Мост': 'ЦАО', 'Трубная': 'ЦАО',
        'Чистые пруды': 'ЦАО', 'Цветной бульвар': 'ЦАО', 'Достоевская': 'ЦАО',
        'Деловой центр': 'ЦАО', 'Выставочная': 'ЦАО', 'Кутузовская': 'ЦАО',
        'Парк Победы': 'ЦАО',
        # САО
        'Войковская': 'САО', 'Водный стадион': 'САО', 'Речной вокзал': 'САО',
        'Сокол': 'САО', 'Аэропорт': 'САО', 'Динамо': 'САО',
        'Беломорская': 'САО', 'Ховрино': 'САО', 'Петровский парк': 'САО',
        'Савёловская': 'САО', 'Дмитровская': 'САО', 'Тимирязевская': 'САО',
        # СВАО
        'ВДНХ': 'СВАО', 'Алексеевская': 'СВАО', 'Рижская': 'СВАО',
        'Ботанический сад': 'СВАО', 'Свиблово': 'СВАО', 'Бабушкинская': 'СВАО',
        'Медведково': 'СВАО', 'Бибирево': 'СВАО', 'Отрадное': 'СВАО',
        'Владыкино': 'СВАО', 'Петровско-Разумовская': 'СВАО',
        # ВАО
        'Измайловская': 'ВАО', 'Партизанская': 'ВАО', 'Первомайская': 'ВАО',
        'Щёлковская': 'ВАО', 'Черкизовская': 'ВАО', 'Преображенская площадь': 'ВАО',
        'Сокольники': 'ВАО', 'Семёновская': 'ВАО', 'Электрозаводская': 'ВАО',
        'Авиамоторная': 'ВАО', 'Шоссе Энтузиастов': 'ВАО',
        'Перово': 'ВАО', 'Новогиреево': 'ВАО',
        # ЮВАО
        'Выхино': 'ЮВАО', 'Кузьминки': 'ЮВАО', 'Текстильщики': 'ЮВАО',
        'Печатники': 'ЮВАО', 'Люблино': 'ЮВАО', 'Братиславская': 'ЮВАО',
        'Марьино': 'ЮВАО', 'Дубровка': 'ЮВАО', 'Кожуховская': 'ЮВАО',
        'Рязанский проспект': 'ЮВАО', 'Нижегородская': 'ЮВАО',
        'Волгоградский проспект': 'ЮВАО',
        # ЮАО
        'Царицыно': 'ЮАО', 'Орехово': 'ЮАО', 'Домодедовская': 'ЮАО',
        'Красногвардейская': 'ЮАО', 'Каховская': 'ЮАО', 'Севастопольская': 'ЮАО',
        'Чертановская': 'ЮАО', 'Южная': 'ЮАО', 'Пражская': 'ЮАО',
        'Нагатинская': 'ЮАО', 'Коломенская': 'ЮАО', 'Каширская': 'ЮАО',
        'Технопарк': 'ЮАО', 'Автозаводская': 'ЮАО', 'Тульская': 'ЮАО',
        'Нагорная': 'ЮАО',
        # ЮЗАО
        'Юго-Западная': 'ЮЗАО', 'Тропарёво': 'ЮЗАО', 'Беляево': 'ЮЗАО',
        'Коньково': 'ЮЗАО', 'Тёплый Стан': 'ЮЗАО', 'Ясенево': 'ЮЗАО',
        'Новоясеневская': 'ЮЗАО', 'Калужская': 'ЮЗАО', 'Академическая': 'ЮЗАО',
        'Профсоюзная': 'ЮЗАО', 'Новые Черёмушки': 'ЮЗАО', 'Университет': 'ЮЗАО',
        'Ленинский проспект': 'ЮЗАО', 'Шаболовская': 'ЮЗАО',
        # ЗАО
        'Молодёжная': 'ЗАО', 'Кунцевская': 'ЗАО', 'Крылатское': 'ЗАО',
        'Пионерская': 'ЗАО', 'Филёвский парк': 'ЗАО', 'Багратионовская': 'ЗАО',
        'Фили': 'ЗАО', 'Студенческая': 'ЗАО', 'Славянский бульвар': 'ЗАО',
        'Минская': 'ЗАО', 'Раменки': 'ЗАО',
        # СЗАО
        'Митино': 'СЗАО', 'Строгино': 'СЗАО', 'Волоколамская': 'СЗАО',
        'Пятницкое шоссе': 'СЗАО', 'Тушинская': 'СЗАО', 'Сходненская': 'СЗАО',
        'Планерная': 'СЗАО', 'Щукинская': 'СЗАО', 'Октябрьское поле': 'СЗАО',
        'Полежаевская': 'СЗАО',
    }

    def __init__(self, max_pages: int = 8):
        self.max_pages = max_pages
        self._session = requests.Session()
        self._session.headers.update(self.HEADERS)

    @staticmethod
    def _parse_number(text: str) -> Optional[float]:
        # '1 500 000 Р' -> 1500000
        m = re.search(r'(\d[\d\s ]*)', text)
        if not m:
            return None
        digits = re.sub(r'[\s ]', '', m.group(1))
        return float(digits) if digits else None

    @staticmethod
    def _extract_metro(info_text: str) -> str:
        # '<Метро> (5 мин. транспортом) Адрес' -> 'Метро'
        m = re.match(r'^([^\(]+?)\s*\(', info_text)
        return m.group(1).strip() if m else ''

    @classmethod
    def _district_from_metro(cls, metro: str, address: str) -> str:
        for st, ok in cls.METRO_TO_OKRUG.items():
            if st.lower() in metro.lower():
                return ok
        return _infer_district_from_address(address)

    def _scrape_page(self, page: int) -> list[dict]:
        url = self.BASE_URL if page == 1 else f'{self.BASE_URL}?page={page}'
        try:
            resp = self._session.get(url, timeout=20)
            resp.raise_for_status()
        except Exception as e:
            print(f'  sob.ru стр.{page}: ошибка - {e}')
            return []

        soup = BeautifulSoup(resp.text, 'html.parser')
        records = []
        for card in soup.select('.adv-card'):
            title_el = card.select_one('.adv-card-title')
            addr_el  = card.select_one('.b-adAddress')
            mp_el    = card.select_one('.adv-card-meter-price')
            price_el = card.select_one('.adv-card-price')
            info_el  = card.select_one('.adv-card-info')

            name    = title_el.get_text(' ', strip=True) if title_el else ''
            address = addr_el.get_text(' ', strip=True) if addr_el else ''
            info    = info_el.get_text(' ', strip=True) if info_el else ''
            metro   = self._extract_metro(info)

            price_per_sqm = self._parse_number(mp_el.get_text(' ', strip=True)) if mp_el else None
            total_price   = self._parse_number(price_el.get_text(' ', strip=True)) if price_el else None
            area = (total_price / price_per_sqm) if (total_price and price_per_sqm) else None

            records.append({
                'name':          name,
                'address':       address,
                'metro':         metro,
                'price':         total_price,
                'area':          area,
                'price_per_sqm': price_per_sqm,
                'district':      self._district_from_metro(metro, address),
            })
        return records

    def scrape(self) -> pd.DataFrame:
        all_records = []
        for page in range(1, self.max_pages + 1):
            batch = self._scrape_page(page)
            if not batch:
                break
            all_records.extend(batch)
            print(f'  sob.ru стр.{page}: +{len(batch)} объявлений (итого {len(all_records)})')
            time.sleep(random.uniform(1.0, 2.5))
        return pd.DataFrame(all_records)
