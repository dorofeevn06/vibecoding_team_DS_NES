"""
audience_parser.py

Этот файл нужен для первого этапа анализа целевой аудитории проекта:
мы берем список бильярдных из Excel-файла, открываем их страницы в Яндекс Картах
через Selenium, переходим на вкладку отзывов и собираем тексты отзывов.

Текущая версия проходит циклом по всем заведениям из таблицы places.
Для каждого заведения скрипт открывает карточку, ищет вкладку отзывов,
скроллит отзывы, раскрывает длинные отзывы через кнопку 'Ещё'
и добавляет найденные отзывы в общий CSV-файл.

Входной файл:
    projvenv/Biliard_places.xlsx

Ожидаемые столбцы во входном файле:
    place_name — название заведения
    district   — район Москвы
    url        — ссылка на карточку заведения в Яндекс Картах

Выходной файл:
    projvenv/audience_raw.csv

Основные поля в выходном файле:
    place_name    — название заведения
    district      — район
    source        — источник данных, сейчас yandex_maps
    review_text   — текст отзыва
    review_rating — оценка отзыва, если удалось достать
    review_date   — дата отзыва, если удалось достать
    place_url     — ссылка на заведение
"""

import time

import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


# Читаем Excel-файл со списком заведений.
# На этом этапе мы еще не парсим отзывы, а только загружаем подготовленную таблицу ссылок.
places = pd.read_excel('projvenv/Biliard_places.xlsx')

# Приводим основные столбцы к строкам и убираем лишние пробелы.
# Это нужно, чтобы в итоговом CSV не было случайных пробелов в названиях и ссылках.
places['place_name'] = places['place_name'].astype(str).str.strip()
places['district'] = places['district'].astype(str).str.strip()
places['url'] = places['url'].astype(str).str.strip()

# Убираем строки без названия или ссылки, потому что по ним нельзя перейти на страницу.
places = places.dropna(subset=['place_name', 'url'])

# Убираем дубли по ссылкам, чтобы не парсить одно и то же заведение два раза.
places = places.drop_duplicates(subset=['url'])


def find_reviews_url(driver):
    """
    Ищет ссылку на вкладку отзывов на странице заведения Яндекс Карт.

    Логика:
    1. Берем все ссылки <a> на странице.
    2. Смотрим их видимый текст.
    3. Если в тексте есть слово 'отзывы', считаем, что это нужная вкладка.
    4. Возвращаем href этой ссылки.

    Почему не кликаем сразу:
    в Яндекс Картах элементы могут быть видны в HTML, но не всегда кликабельны.
    Поэтому надежнее взять href и открыть его через driver.get().
    """
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
    """
    Функция очитки текста отзыва, помогает с ситуациями, когда текст отзыва содержит новые абазцы и тд
    """
    text = str(text)
    text = text.replace(',', ' ')
    text = text.replace('\n', ' ')
    text = text.replace('\r', ' ')
    text = ' '.join(text.split())
    return text.strip()


def expand_visible_reviews(driver):
    """
    Нажимает кнопки 'Ещё' у видимых отзывов.

    В Яндекс Картах длинные отзывы сначала показываются не полностью.
    Полный текст раскрывается кнопкой 'Ещё'.

    Селектор '.business-review-view__expand' был найден через просмотр кода страницы яндекс карт
    на странице отзывов.
    """
    buttons = driver.find_elements(By.CSS_SELECTOR, '.business-review-view__expand')

    for button in buttons:
        try:
            # Используем JavaScript-клик, обычный button.click()
            # ломается на динамических страницах Яндекс Карт.
            driver.execute_script('arguments[0].click();', button)
            time.sleep(0.2)
        except Exception:
            # Если конкретная кнопка не нажалась, пропускаем ее,
            # чтобы из-за одного элемента не падал весь парсер.
            pass


def scroll_reviews(driver, scroll_count=5):
    """
    Скроллит блок с отзывами несколько раз.

    В Яндекс Картах отзывы подгружаются динамически:
    чем ниже скроллим, тем больше карточек отзывов появляется в HTML.

    Параметр scroll_count отвечает за количество прокруток.
    Для теста достаточно 3–5, для большего сбора можно увеличить.
    """
    for i in range(scroll_count):
        # Перед каждой прокруткой раскрываем уже видимые длинные отзывы.
        expand_visible_reviews(driver)

        # Скроллим именно внутренний контейнер Яндекс Карт,
        # а не всю страницу браузера.
        scroll_container = driver.find_element(By.CSS_SELECTOR, '.scroll__container')
        driver.execute_script('arguments[0].scrollTop = arguments[0].scrollHeight', scroll_container)
        time.sleep(2)

        print('Скролл отзывов:', i + 1)


def collect_reviews_from_page(driver, place_name, district, url):
    """
    Собирает тексты отзывов с уже открытой страницы отзывов.

    На вход получает:
        driver     — открытый браузер Selenium
        place_name — название заведения
        district   — район
        url        — исходная ссылка на карточку заведения

    На выходе возвращает список словарей.
    Каждый словарь — это один отзыв.
    Потом из этого списка создается pandas DataFrame.
    """
    reviews = []

    # Один такой элемент соответствует одной карточке отзыва.
    # Селектор был найден через просмотр кода страницы.
    review_cards = driver.find_elements(By.CSS_SELECTOR, '.business-reviews-card-view__review')
    print('Найдено карточек отзывов:', len(review_cards))

    for card in review_cards:
        try:
            # Внутри карточки ищем контейнер с текстом отзыва.
            text_element = card.find_element(By.CSS_SELECTOR, '.spoiler-view__text-container')
            review_text = clean_review_text(text_element.text)
        except Exception:
            review_text = ''

        try:
            # В Яндекс Картах оценка лежит в meta-теге с itemprop='ratingValue'.
            # Например: <meta itemprop="ratingValue" content="3.0">
            rating_element = card.find_element(By.CSS_SELECTOR, 'meta[itemprop="ratingValue"]')
            review_rating = rating_element.get_attribute('content')
        except Exception:
            review_rating = ''

        try:
            # Видимая дата отзыва лежит в элементе .business-review-view__date.
            # Например: 26 октября 2025.
            date_element = card.find_element(By.CSS_SELECTOR, '.business-review-view__date')
            review_date = clean_review_text(date_element.text)
        except Exception:
            review_date = ''

        # Пустые отзывы не сохраняем.
        # После clean_review_text() отзыв должен быть одной строкой без запятых и переносов.
        if review_text:
            reviews.append({
                'place_name': place_name,
                'district': district,
                'source': 'yandex_maps',
                'review_text': review_text,
                'review_rating': review_rating,
                'review_date': review_date,
                'place_url': url
            })

    return reviews


# Запускаем Safari через Selenium.
# В Safari должна быть включена настройка Develop → Allow Remote Automation.
driver = webdriver.Safari()

# WebDriverWait нужен, чтобы ждать появления элементов на динамической странице.
wait = WebDriverWait(driver, 10)

# Здесь будут храниться все собранные отзывы по всем заведениям.
all_reviews = []

# Количество скроллов для каждого заведения.
# Чем больше число, тем больше отзывов потенциально соберется,
# но тем дольше будет работать парсер.
SCROLL_COUNT = 5

# Проходим по всем заведениям из Excel-таблицы.
for index, row in places.iterrows():
    place_name = row['place_name']
    district = row['district']
    url = row['url']

    print('\n' + '=' * 80)
    print('Обрабатываем заведение:', index, place_name)
    print('Район:', district)
    print('Ссылка:', url)

    try:
        # Открываем карточку заведения.
        driver.get(url)
        time.sleep(3)

        print('Заголовок страницы:', driver.title)

        # Находим ссылку на вкладку отзывов.
        reviews_url = find_reviews_url(driver)

        if reviews_url is None:
            print('Вкладка отзывов не найдена, пропускаем заведение')
            continue

        # Переходим на страницу отзывов.
        driver.get(reviews_url)
        time.sleep(3)
        print('Перешли на вкладку отзывов')

        # Ждем, пока появится хотя бы одна карточка отзыва.
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '.business-reviews-card-view__review')))

        # Скроллим отзывы, чтобы Яндекс Карты подгрузили больше карточек.
        scroll_reviews(driver, scroll_count=SCROLL_COUNT)

        # После финального скролла еще раз раскрываем длинные видимые отзывы.
        expand_visible_reviews(driver)

        # Собираем отзывы со страницы.
        place_reviews = collect_reviews_from_page(driver, place_name, district, url)
        all_reviews.extend(place_reviews)

        print('Собрано отзывов по заведению:', len(place_reviews))
        print('Всего собрано отзывов:', len(all_reviews))

        # Промежуточно сохраняем результат после каждого заведения.
        # Это полезно: если парсер упадет на следующем заведении,
        # уже собранные отзывы не потеряются.
        reviews_df = pd.DataFrame(all_reviews)
        reviews_df.to_csv('projvenv/audience_raw.csv', index=False, encoding='utf-8-sig')
        print('Промежуточный результат сохранен в projvenv/audience_raw.csv')

    except Exception as error:
        # Если одно заведение вызвало ошибку, мы не останавливаем весь парсер.
        # Просто выводим ошибку и переходим к следующему заведению.
        print('Ошибка при обработке заведения:', place_name)
        print('Текст ошибки:', error)
        continue

# Финальное сохранение после обработки всей таблицы.
reviews_df = pd.DataFrame(all_reviews)
reviews_df.to_csv('projvenv/audience_raw.csv', index=False, encoding='utf-8-sig')

print('\n' + '=' * 80)
print('Парсинг завершен')
print('Всего заведений в таблице:', len(places))
print('Всего собрано отзывов:', len(reviews_df))
print('Файл сохранен: projvenv/audience_raw.csv')

# Закрываем браузер после завершения работы.
driver.quit()