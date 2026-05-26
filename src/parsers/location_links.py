"""Поиск карточек заведений в Яндекс.Картах по списку из 2GIS.

Берёт data/raw/2gis_clubs_geo.csv, через Selenium находит каждое место
в Яндекс.Картах и сохраняет ссылки в data/raw/location_links.csv.
"""

import time
from urllib.parse import quote_plus

import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


INPUT_FILE = 'projvenv/2gis_clubs_geo.csv'
OUTPUT_FILE = 'projvenv/location_links.csv'
MAX_PLACES = None
WAIT_SECONDS = 10

CARD_LINK_SELECTOR = 'a.card-title-view__title-link'
ADDRESS_SELECTOR = 'div.business-contacts-view__address-link'
CATEGORY_SELECTOR = 'a.business-categories-view__category'
SEARCH_RESULT_SELECTORS = [
    'a.search-business-snippet-view__link',
    'a.search-snippet-view__link',
    'div.search-business-snippet-view',
    'div.search-snippet-view',
    'li.suggest-item-view'
]


def clean_text(text):
    """Убирает переносы строк и лишние пробелы. Запятые сохраняются."""
    text = str(text).replace('\n', ' ').replace('\r', ' ')
    return ' '.join(text.split()).strip()


def load_places():
    places = pd.read_csv(INPUT_FILE)

    for column in ['name', 'district', 'address']:
        places[column] = places[column].astype(str).str.strip()

    places = places.dropna(subset=['name', 'address'])
    places = places.drop_duplicates(subset=['name', 'address'])

    if MAX_PLACES is not None:
        places = places.head(MAX_PLACES)

    return places


def build_search_query(place_name, address):
    place_name = clean_text(place_name)
    address = clean_text(address)

    if address and address.lower() != 'nan':
        return f'{place_name} {address} Москва'

    return f'{place_name} Москва'


def make_full_yandex_url(href):
    if not href:
        return ''

    href = href.strip()

    if href.startswith('https://'):
        return href

    if href.startswith('/maps/'):
        return 'https://yandex.ru' + href

    return href


def collect_categories(driver):
    categories = []

    for element in driver.find_elements(By.CSS_SELECTOR, CATEGORY_SELECTOR):
        category = clean_text(element.text)

        if category:
            categories.append(category)

    return ', '.join(categories)


def empty_result(status, error):
    return {
        'yandex_maps_url': '',
        'yandex_name': '',
        'yandex_address': '',
        'yandex_categories': '',
        'status': status,
        'error': error
    }


def get_card_info(driver):
    try:
        title_link = driver.find_element(By.CSS_SELECTOR, CARD_LINK_SELECTOR)
    except Exception:
        return None

    href = title_link.get_attribute('href')
    yandex_name = clean_text(title_link.text)
    yandex_maps_url = make_full_yandex_url(href)

    try:
        address_element = driver.find_element(By.CSS_SELECTOR, ADDRESS_SELECTOR)
        yandex_address = clean_text(address_element.text)
    except Exception:
        yandex_address = ''

    return {
        'yandex_maps_url': yandex_maps_url,
        'yandex_name': yandex_name,
        'yandex_address': yandex_address,
        'yandex_categories': collect_categories(driver),
        'status': 'found',
        'error': ''
    }


def click_first_search_result(driver):
    for selector in SEARCH_RESULT_SELECTORS:
        elements = driver.find_elements(By.CSS_SELECTOR, selector)

        if elements:
            driver.execute_script('arguments[0].click();', elements[0])
            time.sleep(2)
            return True

    return False


def find_yandex_card(driver, wait):
    card_info = get_card_info(driver)

    if card_info is not None:
        return card_info

    if click_first_search_result(driver):
        card_info = get_card_info(driver)

        if card_info is not None:
            return card_info

    try:
        wait.until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, ', '.join(SEARCH_RESULT_SELECTORS))
            )
        )
    except Exception:
        return empty_result('not_found', 'Не открылась карточка и не появились результаты поиска')

    if click_first_search_result(driver):
        card_info = get_card_info(driver)

        if card_info is not None:
            return card_info

    return empty_result('not_found', 'Результаты поиска появились, но карточка после клика не открылась')


def save_results(results):
    pd.DataFrame(results).to_csv(OUTPUT_FILE, index=False, encoding='utf-8-sig')


def make_output_row(row, search_query, search_result):
    return {
        'place_name': clean_text(row['name']),
        'district': clean_text(row['district']),
        'address': clean_text(row['address']),
        'search_query': clean_text(search_query),
        'yandex_name': search_result['yandex_name'],
        'yandex_address': search_result['yandex_address'],
        'yandex_categories': search_result['yandex_categories'],
        'yandex_maps_url': search_result['yandex_maps_url'],
        'status': search_result['status'],
        'error': search_result['error']
    }


def print_result(index, total, row, search_query, search_result):
    print()
    print(f'[{index + 1}/{total}] {row["name"]}')
    print('Район:', row['district'])
    print('Адрес:', row['address'])
    print('Запрос:', search_query)
    print('Статус:', search_result['status'])
    print('Название в Яндексе:', search_result['yandex_name'])
    print('Адрес в Яндексе:', search_result['yandex_address'])
    print('Категории:', search_result['yandex_categories'])
    print('Ссылка:', search_result['yandex_maps_url'])


def main():
    places = load_places()
    driver = webdriver.Safari()
    wait = WebDriverWait(driver, WAIT_SECONDS)
    results = []

    try:
        for index, row in places.iterrows():
            search_query = build_search_query(row['name'], row['address'])
            search_url = 'https://yandex.ru/maps/?text=' + quote_plus(search_query)

            try:
                driver.get(search_url)
                time.sleep(3)
                search_result = find_yandex_card(driver, wait)
            except Exception as error:
                search_result = empty_result('error', str(error))

            results.append(make_output_row(row, search_query, search_result))
            save_results(results)
            print_result(len(results) - 1, len(places), row, search_query, search_result)
            time.sleep(1)

    finally:
        driver.quit()

    print()
    print('Сбор ссылок завершен')
    print('Всего заведений в таблице:', len(places))
    print('Всего найдено ссылок:', len(pd.DataFrame(results).query("status == 'found'")))
    print('Файл сохранен:', OUTPUT_FILE)


if __name__ == '__main__':
    main()