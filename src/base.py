"""Базовый модуль: BaseScraper, мапинги округов/районов, общие хелперы.

Используется всеми scraper-классами в `src/`.
"""
from __future__ import annotations

import glob
import os
import re
import time

import pandas as pd
import requests
from abc import ABC, abstractmethod


# ── Базовый класс scraper-а ───────────────────────────────────────────────────
class BaseScraper(ABC):
    """Общий интерфейс: scrape() → DataFrame, save() → CSV."""

    @abstractmethod
    def scrape(self) -> pd.DataFrame:
        ...

    def save(self, df: pd.DataFrame, path: str) -> None:
        df.to_csv(path, index=False, encoding='utf-8-sig')
        print(f'Сохранено {len(df)} записей → {path}')


# ── 2GIS API key ──────────────────────────────────────────────────────────────
TWOGIS_API_KEY = '861d5f18-1ef5-4fc1-9faf-f883c0044904'


# ── Источник истины: округ → список районов ──────────────────────────────────
OKRUG_TO_RAYONS: dict[str, list[str]] = {
    'ЦАО':  ['Арбат', 'Басманный', 'Замоскворечье', 'Красносельский', 'Мещанский',
              'Пресненский', 'Таганский', 'Тверской', 'Хамовники', 'Якиманка',
              'Беговой', 'Бауманка', 'Ивановская горка', 'Патриаршие пруды',
              'Китай-город', 'Чистые Пруды'],
    'САО':  ['Алтуфьевский', 'Бескудниковский', 'Войковский', 'Головинский',
              'Дмитровский', 'Коптево', 'Левобережный', 'Молжаниновский',
              'Савёловский', 'Тимирязевский', 'Ховрино', 'Хорошёвский',
              'Аэропорт', 'Беломорский', 'Восточное Дегунино',
              'Западное Дегунино', 'Сокол'],
    'СВАО': ['Алексеевский', 'Бабушкинский', 'Бутырский', 'Лосиноостровский',
              'Марфино', 'Марьина роща', 'Останкинский', 'Отрадное',
              'Ростокино', 'Свиблово', 'Северное Медведково', 'Южное Медведково',
              'Ярославский', 'Алтуфьево', 'Бибирево', 'Лианозово', 'Северный'],
    'ВАО':  ['Богородское', 'Вешняки', 'Восточное Измайлово', 'Гольяново',
              'Измайлово', 'Косино-Ухтомский', 'Метрогородок', 'Новогиреево',
              'Новокосино', 'Перово', 'Преображенское', 'Северное Измайлово',
              'Соколиная Гора', 'Сокольники', 'Восточный', 'Ивановское'],
    'ЮВАО': ['Выхино-Жулебино', 'Капотня', 'Кузьминки', 'Лефортово',
              'Люблино', 'Марьино', 'Некрасовка', 'Нижегородский',
              'Печатники', 'Рязанский', 'Текстильщики', 'Южнопортовый',
              'Кожухово'],
    'ЮАО':  ['Бирюлёво Восточное', 'Бирюлёво Западное', 'Братеево', 'Даниловский',
              'Донской', 'Зябликово', 'Москворечье-Сабурово', 'Нагатино-Садовники',
              'Нагатинский Затон', 'Нагорный', 'Орехово-Борисово Северное',
              'Орехово-Борисово Южное', 'Царицыно', 'Чертаново Центральное',
              'Чертаново Северное', 'Чертаново Южное', 'Канатчиково'],
    'ЮЗАО': ['Академический', 'Северное Бутово', 'Южное Бутово', 'Гагаринский',
              'Зюзино', 'Коньково', 'Котловка', 'Обручевский',
              'Теплый Стан', 'Черёмушки', 'Ясенево', 'Ломоносовский'],
    'ЗАО':  ['Дорогомилово', 'Крылатское', 'Кунцево', 'Можайский',
              'Ново-Переделкино', 'Очаково-Матвеевское', 'Проспект Вернадского',
              'Раменки', 'Солнцево', 'Тропарёво-Никулино', 'Филёвский парк',
              'Фили-Давыдково'],
    'СЗАО': ['Куркино', 'Митино', 'Покровское-Стрешнево', 'Строгино',
              'Северное Тушино', 'Южное Тушино', 'Хорошёво-Мнёвники', 'Щукино'],
}

# Обратный словарь для O(1)-поиска: район (lower) → округ
RAYON_TO_OKRUG: dict[str, str] = {
    r.lower(): okrug
    for okrug, rayons in OKRUG_TO_RAYONS.items()
    for r in rayons
}

# Центры округов для быстрого назначения district по координатам (без API)
_ZONE_CENTERS_LATLON: list[tuple[str, float, float]] = [
    ('ЦАО',  55.756, 37.617),
    ('САО',  55.827, 37.543),
    ('СВАО', 55.830, 37.683),
    ('ВАО',  55.775, 37.780),
    ('ЮВАО', 55.700, 37.760),
    ('ЮАО',  55.650, 37.620),
    ('ЮЗАО', 55.660, 37.500),
    ('ЗАО',  55.740, 37.390),
    ('СЗАО', 55.820, 37.430),
]


def assign_district_by_nearest_zone(lat: float, lon: float) -> str:
    """Округ по ближайшему из 9 центров — без API, мгновенно."""
    best, best_d = 'Другое', float('inf')
    for name, clat, clon in _ZONE_CENTERS_LATLON:
        d = (lat - clat) ** 2 + (lon - clon) ** 2
        if d < best_d:
            best_d, best = d, name
    return best


def _normalize_rayon(raw: str) -> str:
    """Убирает префикс 'район ' / суффикс ' район' и приводит к нижнему регистру."""
    s = re.sub(r'^[Рр]айон\s+', '', raw).strip()
    s = re.sub(r'\s+[Рр]айон$', '', s).strip()
    return s.lower()


def _infer_district_from_address(address: str) -> str:
    """Определяет округ по подстроке адреса через RAYON_TO_OKRUG."""
    if not address:
        return 'Другое'
    addr_lower = address.lower()
    for rayon, okrug in RAYON_TO_OKRUG.items():
        if rayon in addr_lower:
            return okrug
    return 'Другое'


def get_okrug_nominatim(lat: float, lon: float) -> str:
    """Уточнение округа через Nominatim (OSM reverse geocoding). 1 req/sec лимит."""
    try:
        resp = requests.get(
            'https://nominatim.openstreetmap.org/reverse',
            params={'lat': lat, 'lon': lon, 'format': 'json', 'accept-language': 'ru'},
            headers={'User-Agent': 'billiard-club-research/1.0'},
            timeout=10,
        )
        resp.raise_for_status()
        addr = resp.json().get('address', {})
        for field in ('suburb', 'city_district', 'quarter', 'neighbourhood'):
            raw = addr.get(field, '')
            if raw:
                rayon = _normalize_rayon(raw)
                if rayon in RAYON_TO_OKRUG:
                    return RAYON_TO_OKRUG[rayon]
    except Exception:
        pass
    return 'Другое'


# ── Общий хелпер для Selenium-парсеров ────────────────────────────────────────
def find_cached_chromedriver() -> str | None:
    """Возвращает путь к новейшему кэшированному chromedriver (~/.wdm) или None.

    Нужно чтобы обойти SSL-проблемы webdriver-manager при недоступности
    googlechromelabs.github.io: используем уже скачанный драйвер.
    """
    cached = sorted(
        glob.glob(
            os.path.expanduser('~/.wdm/drivers/chromedriver/**/chromedriver'),
            recursive=True,
        ),
        reverse=True,  # новейший первый
    )
    return cached[0] if cached else None


def make_chrome_driver():
    """Создаёт headless Chrome с правильными настройками + кэшированный driver.

    Lazy-импорт selenium внутри функции — модуль `base` не должен требовать
    selenium для импорта (используется requests-only парсерами).
    """
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service

    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_experimental_option('excludeSwitches', ['enable-automation'])
    options.add_experimental_option('useAutomationExtension', False)
    options.add_argument(
        '--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
        'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
    )

    cached_path = find_cached_chromedriver()
    if cached_path:
        service = Service(cached_path)
    else:
        from webdriver_manager.chrome import ChromeDriverManager
        service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=options)
