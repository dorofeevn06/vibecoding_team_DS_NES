# «Луzа и Шары» — анализ бильярдного рынка Москвы

## Структура

```
nikita/
├── src/                     # бизнес-логика
│   ├── base.py              # BaseScraper(ABC), мапинг округов/районов, helpers
│   ├── twogis.py            # TwoGISAPIScraper      — конкуренты (requests + JSON)
│   ├── sob.py               # SobRentScraper        — аренда (requests + BS4)
│   ├── osm.py               # OSMOverpassScraper    — координаты (Overpass API)
│   ├── zoon.py              # ZoonScraper, ZoonReviewScraper (Selenium)
│   └── geo.py               # GeoAnalyzer           — opportunity score
├── viz/
│   ├── figures.py           # функции make_*(df) → plotly Figure
│   └── dashboard.py         # make_app(...) → Dash с 5 вкладками
├── data/                    # CSV-кэш парсинга (создаётся автоматически)
├── analysis.ipynb           # тонкий отчётный ноутбук
└── requirements.txt
```

## Источники данных

| Источник | Метод парсинга | Что даёт |
|----------|----------------|----------|
| 2GIS Catalog API | requests + JSON | Конкуренты: имя, адрес, рейтинг, отзывы, координаты |
| sob.ru | **requests + BS4** (статика) | Аренда коммерческой недвижимости: цена/м², метро |
| OpenStreetMap (Overpass) | requests + JSON | Координаты всех бильярдных Москвы |
| Zoon.ru | **Selenium** (динамика) | Досуговые заведения по округам |
| Zoon.ru (отзывы) | **Selenium** | Негативные отзывы для анализа болей клиентов |

## Запуск

```bash
pip install -r requirements.txt
jupyter notebook analysis.ipynb     # → «Restart & Run All»
```

При первом запуске парсеры наполнят `data/`. Последующие запуски —
загрузка из кэша (мгновенно).

## Запуск отдельных компонентов (без ноутбука)

```python
from src.twogis import TwoGISAPIScraper
from src.sob    import SobRentScraper
from src.geo    import GeoAnalyzer

# Распарсить конкурентов
df_clubs = TwoGISAPIScraper().scrape()
df_clubs.to_csv('data/2gis_clubs.csv', index=False)

# Распарсить аренду
df_rent = SobRentScraper(max_pages=8).scrape()

# Анализ
geo = GeoAnalyzer(df_clubs)
print(geo.opportunity_score())
print(geo.full_opportunity_score(rent_df=df_rent))
```

## Кэширование

Все парсеры пишут результаты в `data/*.csv`. Логика `cached_csv()` в
ноутбуке:
- если файл существует и непустой → читаем
- иначе → запускаем парсер заново и сохраняем

Чтобы перепарсить — удали соответствующий CSV.
