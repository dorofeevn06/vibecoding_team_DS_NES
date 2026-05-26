"""Парсинг координат бильярдных в Москве из OpenStreetMap через Overpass API."""

import pandas as pd
import requests

from .base import BaseScraper, assign_district_by_nearest_zone


class OSMOverpassScraper(BaseScraper):
    """Дополняет 2GIS — в OSM попадаются мелкие клубы, которых нет в каталоге 2GIS."""

    # Зеркало используем потому что главный api.openstreetmap.org часто
    # тупит или возвращает 429.
    OVERPASS_URL = 'https://overpass.kumi.systems/api/interpreter'
    BBOX = (55.14, 36.80, 56.02, 37.97)  # Москва: south, west, north, east

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

    def __init__(self, timeout: int = 90):
        self.timeout = timeout

    def scrape(self) -> pd.DataFrame:
        print('Запрос к Overpass API...')
        bbox_str = ','.join(map(str, self.BBOX))
        resp = requests.post(
            self.OVERPASS_URL,
            data={'data': self.QUERY.format(bbox=bbox_str)},
            timeout=self.timeout,
        )
        resp.raise_for_status()

        records = []
        for el in resp.json().get('elements', []):
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
        if not df.empty:
            df['district'] = df.apply(
                lambda r: assign_district_by_nearest_zone(r['lat'], r['lon']),
                axis=1,
            )
        return df
