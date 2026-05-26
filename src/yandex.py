"""Загрузка отзывов с Яндекс.Карт из готового CSV (audience_raw.csv).

На Zoon почти нет текстовых отзывов про бильярдные клубы, поэтому отзывы
парсил коллега отдельно. Этот модуль читает CSV и приводит колонки
к тому же формату, что использует ZoonReviewScraper.
"""

import re
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

from .base import BaseScraper, RAYON_TO_OKRUG
from .zoon import ZoonReviewScraper


VALID_OKRUGS = {
    'ЦАО', 'САО', 'СВАО', 'ВАО', 'ЮВАО',
    'ЮАО', 'ЮЗАО', 'ЗАО', 'СЗАО', 'Другое',
}

RU_MONTHS = {
    'январь': 1, 'января': 1, 'февраль': 2, 'февраля': 2,
    'март': 3, 'марта': 3, 'апрель': 4, 'апреля': 4,
    'май': 5, 'мая': 5, 'июнь': 6, 'июня': 6,
    'июль': 7, 'июля': 7, 'август': 8, 'августа': 8,
    'сентябрь': 9, 'сентября': 9, 'октябрь': 10, 'октября': 10,
    'ноябрь': 11, 'ноября': 11, 'декабрь': 12, 'декабря': 12,
}


class YandexMapsReviewsLoader(BaseScraper):
    """Читает CSV с отзывами Яндекс.Карт и нормализует колонки."""

    def __init__(self, csv_path: str = 'audience_raw.csv'):
        self.csv_path = Path(csv_path)

    @staticmethod
    def _normalize_district(value: str) -> str:
        if pd.isna(value) or not value:
            return 'Другое'
        s = str(value).strip()
        if s in VALID_OKRUGS:
            return s
        return RAYON_TO_OKRUG.get(s.lower(), 'Другое')

    @staticmethod
    def _parse_russian_date(value: str) -> Optional[datetime]:
        # «11 декабря 2025» -> datetime
        if pd.isna(value) or not value:
            return None
        m = re.search(r'(\d{1,2})\s+([а-яё]+)\s+(\d{4})', str(value).lower())
        if not m:
            return None
        month = RU_MONTHS.get(m.group(2))
        if not month:
            return None
        try:
            return datetime(int(m.group(3)), month, int(m.group(1)))
        except ValueError:
            return None

    @staticmethod
    def _detect_billiard(row: pd.Series) -> bool:
        cats = str(row.get('yandex_categories', '') or '').lower()
        name = str(row.get('place_name', '') or '').lower()
        return 'бильярд' in cats or 'бильярд' in name

    def scrape(self) -> pd.DataFrame:
        if not self.csv_path.exists():
            raise FileNotFoundError(f'Нет файла: {self.csv_path.resolve()}')

        raw = pd.read_csv(self.csv_path)
        print(f'Прочитано {len(raw)} строк из {self.csv_path}')

        df = pd.DataFrame({
            'club':              raw['place_name'],
            'rating':            pd.to_numeric(raw['review_rating'], errors='coerce'),
            'text':              raw['review_text'].astype(str),
            'url':               raw['place_url'],
            'district':          raw['district'].apply(self._normalize_district),
            'review_date':       raw['review_date'].apply(self._parse_russian_date),
            'yandex_categories': raw['yandex_categories'],
        })
        df['is_billiard'] = raw.apply(self._detect_billiard, axis=1)
        df['categories'] = df['text'].apply(
            lambda t: ', '.join(ZoonReviewScraper.classify_complaint(t))
        )

        before = len(df)
        df = df[df['text'].str.len() >= 10].dropna(subset=['rating']).copy()
        if before != len(df):
            print(f'Отфильтровано {before - len(df)} коротких или пустых строк')

        print(f'Итого: {len(df)} отзывов, {df["club"].nunique()} заведений, '
              f'из них бильярдных: {df["is_billiard"].sum()}')
        return df.reset_index(drop=True)
