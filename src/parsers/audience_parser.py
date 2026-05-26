"""Парсинг отзывов с Яндекс.Карт через Selenium.

Берёт карточки бильярдных клубов из data/raw/location_links.csv,
открывает страницы заведений и собирает отзывы в data/raw/audience_raw.csv.
"""

import time
from pathlib import Path

import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


PROJECT_ROOT = Path(__file__).resolve().parents[1]

INPUT_PATH = PROJECT_ROOT / 'data' / 'raw' / 'location_links.csv'
OUTPUT_PATH = PROJECT_ROOT / 'data' / 'raw' / 'audience_raw.csv'

OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

# Если HEADLESS_MODE = True, Chrome работает в фоновом режиме без видимого окна.
# Если Яндекс часто показывает капчу, можно временно поставить False,
# чтобы пройти капчу вручную в открытом окне браузера.
HEADLESS_MODE = True


def create_driver(headless=True):
    """
    Создает браузер Google Chrome для Selenium.

    Раньше использовался Safari, но Chrome удобнее для проекта:
    он стабильнее работает с Selenium и поддерживает headless-режим.
    """
    options = Options()

    if headless:
        options.add_argument('--headless=new')

    options.add_argument('--window-size=1440,1000')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')

    driver = webdriver.Chrome(options=options)

    return driver


places = pd.read_csv(INPUT_PATH)

places['place_name'] = places['place_name'].astype(str).str.strip()
places['district'] = places['district'].astype(str).str.strip()
places['yandex_name'] = places['yandex_name'].astype(str).str.strip()
places['yandex_categories'] = places['yandex_categories'].astype(str).str.strip()
places['yandex_maps_url'] = places['yandex_maps_url'].astype(str).str.strip()
places['status'] = places['status'].astype(str).str.strip()

places = places.dropna(subset=['place_name', 'yandex_maps_url'])
places = places[places['status'].str.lower() == 'found']
places = places[places['yandex_maps_url'].str.startswith('http', na=False)]
places = places[places['yandex_categories'].str.lower().str.contains('бильярдный клуб', na=False)]
places = places.drop_duplicates(subset=['yandex_maps_url'])

print('Заведений после фильтра по категории бильярдный клуб:', len(places))


def find_reviews_url(driver):
    links = driver.find_elements(By.TAG_NAME, 'a')

    for link in links:
        text = link.text.strip().lower()
        href = link.get_attribute('href')

        if 'отзывы' in text and href is not None:
            print('Нашли вкладку отзывов:', link.text)
            print('Ссылка:', href)
            return href

    return None


def clean_review_text(text):
    text = str(text)
    text = text.replace(',', ' ')
    text = text.replace('\n', ' ')
    text = text.replace('\r', ' ')
    text = ' '.join(text.split())
    return text.strip()


def expand_visible_reviews(driver):
    buttons = driver.find_elements(By.CSS_SELECTOR, '.business-review-view__expand')

    for button in buttons:
        try:
            driver.execute_script('arguments[0].click();', button)
            time.sleep(0.2)
        except Exception:
            pass


def scroll_reviews(driver, scroll_count=5):
    for i in range(scroll_count):
        expand_visible_reviews(driver)

        scroll_container = driver.find_element(By.CSS_SELECTOR, '.scroll__container')
        driver.execute_script('arguments[0].scrollTop = arguments[0].scrollHeight', scroll_container)
        time.sleep(2)

        print('Скролл отзывов:', i + 1)


def collect_reviews_from_page(driver, place_name, district, yandex_name, yandex_categories, url):
    reviews = []

    review_cards = driver.find_elements(By.CSS_SELECTOR, '.business-reviews-card-view__review')
    print('Найдено карточек отзывов:', len(review_cards))

    for card in review_cards:
        try:
            text_element = card.find_element(By.CSS_SELECTOR, '.spoiler-view__text-container')
            review_text = clean_review_text(text_element.text)
        except Exception:
            review_text = ''

        try:
            rating_element = card.find_element(By.CSS_SELECTOR, 'meta[itemprop="ratingValue"]')
            review_rating = rating_element.get_attribute('content')
        except Exception:
            review_rating = ''

        try:
            date_element = card.find_element(By.CSS_SELECTOR, '.business-review-view__date')
            review_date = clean_review_text(date_element.text)
        except Exception:
            review_date = ''

        if review_text:
            reviews.append({
                'place_name': place_name,
                'district': district,
                'yandex_name': yandex_name,
                'yandex_categories': yandex_categories,
                'source': 'yandex_maps',
                'review_text': review_text,
                'review_rating': review_rating,
                'review_date': review_date,
                'place_url': url
            })

    return reviews


driver = create_driver(headless=HEADLESS_MODE)
wait = WebDriverWait(driver, 15)

if OUTPUT_PATH.exists():
    existing_reviews_df = pd.read_csv(OUTPUT_PATH)
    all_reviews = existing_reviews_df.to_dict('records')

    if 'place_url' in existing_reviews_df.columns:
        parsed_urls = set(existing_reviews_df['place_url'].dropna().astype(str))
    else:
        parsed_urls = set()

    print('Найден существующий файл audience_raw.csv')
    print('Отзывов подтянуто из кэша:', len(all_reviews))
    print('Заведений уже обработано и будет пропущено:', len(parsed_urls))
else:
    all_reviews = []
    parsed_urls = set()

    print('Кэш не найден, парсинг начнется с нуля')

SCROLL_COUNT = 4

for index, row in places.iterrows():
    place_name = row['place_name']
    district = row['district']
    yandex_name = row['yandex_name']
    yandex_categories = row['yandex_categories']
    url = row['yandex_maps_url']

    if url in parsed_urls:
        continue

    print()
    print('Обрабатываем заведение:', index, place_name)
    print('Район:', district)
    print('Название в Яндекс Картах:', yandex_name)
    print('Категории в Яндекс Картах:', yandex_categories)
    print('Ссылка:', url)

    try:
        driver.get(url)
        time.sleep(3)

        print('Заголовок страницы:', driver.title)

        reviews_url = find_reviews_url(driver)

        if reviews_url is None:
            print('Вкладка отзывов не найдена, пропускаем заведение')
            continue

        driver.get(reviews_url)
        time.sleep(3)
        print('Перешли на вкладку отзывов')

        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '.business-reviews-card-view__review')))

        scroll_reviews(driver, scroll_count=SCROLL_COUNT)
        expand_visible_reviews(driver)

        place_reviews = collect_reviews_from_page(
            driver,
            place_name,
            district,
            yandex_name,
            yandex_categories,
            url
        )

        all_reviews.extend(place_reviews)
        parsed_urls.add(url)

        print('Собрано отзывов по заведению:', len(place_reviews))
        print('Всего собрано отзывов:', len(all_reviews))

        reviews_df = pd.DataFrame(all_reviews)
        reviews_df.to_csv(OUTPUT_PATH, index=False, encoding='utf-8-sig')
        print(f'Промежуточный результат сохранен: {OUTPUT_PATH}')

    except Exception as error:
        print('Ошибка при обработке заведения:', place_name)
        print('Текст ошибки:', error)
        continue

reviews_df = pd.DataFrame(all_reviews)
reviews_df.to_csv(OUTPUT_PATH, index=False, encoding='utf-8-sig')

print()
print('Парсинг завершен')
print('Всего заведений в таблице:', len(places))
print('Всего собрано отзывов:', len(reviews_df))
print(f'Файл сохранен: {OUTPUT_PATH}')

driver.quit()