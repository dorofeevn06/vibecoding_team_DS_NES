"""OSMOverpassScraper — гео-координаты бильярдных Москвы через Overpass API.

Запрос к Overpass: все объекты с тегами leisure=billiard_hall,
sport=billiards, amenity=billiard в bbox Москвы.
"""
from __future__ import annotations

import pandas as pd
import requests

from .base import BaseScraper, assign_district_by_nearest_zone


class OSMOverpassScraper(BaseScraper):
    """Парсинг гео-координат бильярдных Москвы из OpenStreetMap (Overpass API).

    Используем зеркало overpass.kumi.systems (главное api.openstreetmap.org
    бывает медленным/перегруженным). Дополняет 2GIS — некоторые мелкие клубы
    есть только в OSM.
    """

    OVERPASS_URL = 'https://overpass.kumi.systems/api/interpreter'

    # Bounding box Москвы (south, west, north, east)
    BBOX = (55.14, 36.80, 56.02, 37.97)

    QUERY = '''
    [out:json][timeout:60];
    (
      node["leisure"="billiard_hall"]({bbox});
      way["leisure"="billiard_hall"]({bbox});
      node["sport"="billiards"]({bbox});
      node["amenity"="billiard"]({bbox});
    );
    out center;
    '''

    def __init__(self, timeout: int = 90) -> None:
        self.timeout = timeout

    def scrape(self) -> pd.DataFrame:
        print('Запрос к Overpass API...')
        bbox_str = ','.join(map(str, self.BBOX))
        query = self.QUERY.format(bbox=bbox_str)

        resp = requests.post(
            self.OVERPASS_URL, data={'data': query}, timeout=self.timeout,
        )
        resp.raise_for_status()
        osm_data = resp.json()

        records: list[dict] = []
        for el in osm_data.get('elements', []):
            name = el.get('tags', {}).get('name', '')
            lat = el.get('lat') or el.get('center', {}).get('lat')
            lon = el.get('lon') or el.get('center', {}).get('lon')
            if lat and lon:
                records.append({
                    'name':   name,
                    'lat':    float(lat),
                    'lon':    float(lon),
                    'osm_id': el.get('id'),
                })

        df = pd.DataFrame(records)
        # Назначаем округ по ближайшему центру зоны (мгновенно, без API)
        if not df.empty:
            df['district'] = df.apply(
                lambda r: assign_district_by_nearest_zone(r['lat'], r['lon']), axis=1,
            )
        return df
