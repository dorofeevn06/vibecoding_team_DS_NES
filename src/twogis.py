"""Парсинг бильярдных клубов через 2GIS Catalog API."""

import time
from typing import Optional

import pandas as pd
import requests

from .base import BaseScraper, TWOGIS_API_KEY


class TwoGISAPIScraper(BaseScraper):
    """2GIS Catalog API. Идём по 9 центрам округов, чтобы не упереться в лимит."""

    API_URL = 'https://catalog.api.2gis.com/3.0/items'
    ZONE_CENTERS = [
        ('ЦАО',  '37.617,55.756'), ('САО',  '37.543,55.827'),
        ('СВАО', '37.683,55.830'), ('ВАО',  '37.780,55.775'),
        ('ЮВАО', '37.760,55.700'), ('ЮАО',  '37.620,55.650'),
        ('ЮЗАО', '37.500,55.660'), ('ЗАО',  '37.390,55.740'),
        ('СЗАО', '37.430,55.820'),
    ]
    DEFAULT_QUERIES = ['бильярд', 'снукер', 'бильярдный клуб']

    def __init__(
        self,
        queries: Optional[list[str]] = None,
        radius_m: int = 15_000,
        page_size: int = 10,
        api_key: str = TWOGIS_API_KEY,
    ):
        self.queries = queries if queries is not None else self.DEFAULT_QUERIES
        self.radius = radius_m
        self.page_size = page_size
        self.api_key = api_key

    def _fetch_page(self, query: str, center: str, page: int) -> dict:
        params = {
            'q': query, 'location': center, 'radius': self.radius,
            'type': 'branch',
            'fields': 'items.point,items.reviews,items.rating,items.address,items.name_ex',
            'page_size': self.page_size, 'page': page, 'key': self.api_key,
        }
        resp = requests.get(self.API_URL, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if data.get('meta', {}).get('code', 200) != 200:
            raise ValueError(data['meta'].get('error', {}).get('message', 'API error'))
        return data

    def _scrape_zone(self, query: str, center: str) -> list[dict]:
        records = []
        page = 1
        while True:
            try:
                data = self._fetch_page(query, center, page)
            except ValueError:
                break
            except Exception as e:
                print(f'      ошибка: {e}')
                break

            items = data.get('result', {}).get('items', [])
            if not items:
                break

            for item in items:
                name = item.get('name', '')
                if not name:
                    continue
                rv = item.get('reviews') or {}
                pt = item.get('point') or {}
                records.append({
                    'name':     name,
                    'address':  item.get('address_name', '') or item.get('full_address_name', ''),
                    'district': 'Другое',
                    'rating':   rv.get('general_rating') or rv.get('org_rating'),
                    'reviews':  rv.get('org_review_count') or rv.get('general_review_count'),
                    'lat':      pt.get('lat'),
                    'lon':      pt.get('lon'),
                })

            total = data.get('result', {}).get('total', 0)
            if len(records) >= total or len(items) < self.page_size:
                break
            page += 1
            time.sleep(0.3)
        return records

    def scrape(self) -> pd.DataFrame:
        all_records = []
        seen_coords = set()
        for query in self.queries:
            print(f'\n  Запрос {query!r}:')
            for zone_name, center in self.ZONE_CENTERS:
                batch = self._scrape_zone(query, center)
                new = 0
                for r in batch:
                    key = (round(r.get('lat') or 0, 4), round(r.get('lon') or 0, 4))
                    if key in seen_coords:
                        continue
                    seen_coords.add(key)
                    all_records.append(r)
                    new += 1
                print(f'    {zone_name}: raw={len(batch)}, +{new} | итого: {len(all_records)}')
                time.sleep(0.4)
        return pd.DataFrame(all_records)
