"""Базовый класс парсера, мапинг округов/районов и общие хелперы."""

import glob
import os
import re
from abc import ABC, abstractmethod
from typing import Optional

import pandas as pd
import requests


class BaseScraper(ABC):
    """Общий интерфейс: scrape() -> DataFrame, save() -> CSV."""

    @abstractmethod
    def scrape(self) -> pd.DataFrame:
        ...

    def save(self, df: pd.DataFrame, path: str) -> None:
        df.to_csv(path, index=False, encoding='utf-8-sig')
        print(f'Сохранено {len(df)} записей -> {path}')


TWOGIS_API_KEY = '861d5f18-1ef5-4fc1-9faf-f883c0044904'


# Округ -> районы. Используется для определения округа по адресу.
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

# Обратный словарь для быстрого поиска: район в нижнем регистре -> округ
RAYON_TO_OKRUG: dict[str, str] = {
    r.lower(): okrug
    for okrug, rayons in OKRUG_TO_RAYONS.items()
    for r in rayons
}

# Примерные центры округов, чтобы назначать округ по координатам без API
_ZONE_CENTERS = [
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
    """Округ по ближайшему из 9 центров. Грубо, но без обращений к API."""
    best, best_d = 'Другое', float('inf')
    for name, clat, clon in _ZONE_CENTERS:
        d = (lat - clat) ** 2 + (lon - clon) ** 2
        if d < best_d:
            best_d, best = d, name
    return best


def _normalize_rayon(raw: str) -> str:
    s = re.sub(r'^[Рр]айон\s+', '', raw).strip()
    s = re.sub(r'\s+[Рр]айон$', '', s).strip()
    return s.lower()


def _infer_district_from_address(address: str) -> str:
    """Округ по подстроке адреса."""
    if not address:
        return 'Другое'
    addr_lower = address.lower()
    for rayon, okrug in RAYON_TO_OKRUG.items():
        if rayon in addr_lower:
            return okrug
    return 'Другое'


def get_okrug_nominatim(lat: float, lon: float) -> str:
    """Уточнение округа через Nominatim. Лимит 1 запрос в секунду."""
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


def find_cached_chromedriver() -> Optional[str]:
    """Путь к локально закэшированному chromedriver."""
    # webdriver-manager хранит драйверы в ~/.wdm; если интернет к Google недоступен,
    # берём отсюда вместо повторной загрузки.
    paths = sorted(
        glob.glob(
            os.path.expanduser('~/.wdm/drivers/chromedriver/**/chromedriver'),
            recursive=True,
        ),
        reverse=True,
    )
    return paths[0] if paths else None


def make_chrome_driver():
    """Headless Chrome для Selenium-парсеров."""
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

    cached = find_cached_chromedriver()
    if cached:
        service = Service(cached)
    else:
        from webdriver_manager.chrome import ChromeDriverManager
        service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=options)
