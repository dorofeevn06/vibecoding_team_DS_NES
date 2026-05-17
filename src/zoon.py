"""Zoon.ru парсеры:

- ZoonScraper        — досуговые заведения по 3 категориям (Selenium).
- ZoonReviewScraper  — негативные отзывы через гибрид (бильярд-поиск +
                       entertainment fallback).

Общий headless Chrome через base.make_chrome_driver().
"""
from __future__ import annotations

import random
import re
import time
from collections import Counter

import pandas as pd
from bs4 import BeautifulSoup

# Selenium-импорты — тяжёлые, локализованы в этом модуле
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from .base import BaseScraper, _infer_district_from_address, make_chrome_driver


# ════════════════════════════════════════════════════════════════════════════
#  ZoonScraper — карточки заведений по 3 категориям
# ════════════════════════════════════════════════════════════════════════════
class ZoonScraper(BaseScraper):
    """Динамический парсинг Zoon.ru — досуговые заведения Москвы (Selenium).

    Использует 3 категории как прокси-данные для досуговой активности округа:
    рестораны/бары, развлекательные центры, фитнес-клубы. Категории
    /msk/billiards/, /msk/bowling/, /msk/bars/ — упразднены (404), не используем.
    """

    CATEGORIES: dict[str, str] = {
        'рестораны':    'https://zoon.ru/msk/restaurants/',
        'развлечения':  'https://zoon.ru/msk/entertainment/',
        'фитнес':       'https://zoon.ru/msk/fitness/',
    }
    FALLBACK_URLS: dict[str, list[str]] = {}

    # CSS-селекторы. Рейтинг хранится в CSS-переменной style="--rating: 4.9".
    CARD_SELECTORS    = ['li.minicard-item', '.minicard-item']
    TITLE_SELECTORS   = ['.minicard-item__title a.title-link', '.minicard-item__title a',
                         '.title-link', 'a[data-uitest="org-link"]']
    ADDR_SELECTORS    = ['.minicard-item__address', '[class*="address"]']
    RATING_STYLE_SEL  = '.z-stars[style*="--rating"]'
    REVIEWS_SELECTORS = ['.minicard-item__rating .comments', '.comments']
    REVIEW_LINK_ATTR  = 'data-js-lnk'

    def __init__(self, max_pages: int = 3) -> None:
        self.max_pages = max_pages

    def _make_driver(self) -> webdriver.Chrome:
        return make_chrome_driver()

    @staticmethod
    def _safe_text(element, *selectors: str) -> str:
        """Пробует CSS-селекторы по очереди, возвращает первый непустой результат."""
        for sel in selectors:
            try:
                text = element.find_element(By.CSS_SELECTOR, sel).text.strip()
                if text:
                    return text
            except Exception:
                continue
        return ''

    def _find_cards(self, driver: webdriver.Chrome) -> list:
        for sel in self.CARD_SELECTORS:
            cards = driver.find_elements(By.CSS_SELECTOR, sel)
            if cards:
                return cards
        return []

    def _scrape_category(
        self,
        driver: webdriver.Chrome,
        category: str,
        base_url: str,
    ) -> list[dict]:
        # Пробуем основной URL + резервные (если есть)
        urls_to_try = [base_url] + self.FALLBACK_URLS.get(category, [])
        working_url = None
        for candidate in urls_to_try:
            driver.get(candidate)
            time.sleep(3)
            if '404' not in driver.title.lower() and len(driver.page_source) > 50_000:
                working_url = candidate
                break
        if working_url is None:
            print(f'    {category}: все URL недоступны (404/пустая страница)')
            return []

        records: list[dict] = []
        for page_num in range(1, self.max_pages + 1):
            url = working_url if page_num == 1 else f'{working_url}?page={page_num}'
            if page_num > 1:
                driver.get(url)

            try:
                WebDriverWait(driver, 20).until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, ', '.join(self.CARD_SELECTORS))
                    )
                )
            except Exception:
                print(f'    {category} стр.{page_num}: карточки не найдены')
                break

            cards = self._find_cards(driver)
            if not cards:
                # Диагностика: какие классы есть на странице
                soup_dbg = BeautifulSoup(driver.page_source, 'html.parser')
                all_cls = {c for t in soup_dbg.find_all(True) for c in t.get('class', [])}
                print(f'    {category} стр.{page_num}: 0 карточек. '
                      f'Классы: {sorted(all_cls)[:15]}')
                break

            for card in cards:
                name = self._safe_text(card, *self.TITLE_SELECTORS)
                if not name:
                    continue
                address = self._safe_text(card, *self.ADDR_SELECTORS)

                # Рейтинг: из style="--rating: 4.9"
                rating: float | None = None
                try:
                    star_el = card.find_element(By.CSS_SELECTOR, self.RATING_STYLE_SEL)
                    style   = star_el.get_attribute('style') or ''
                    m = re.search(r'--rating:\s*([\d.]+)', style)
                    if m:
                        rating = float(m.group(1))
                except Exception:
                    pass

                # Кол-во отзывов: '314 отзывов' → 314
                reviews_count: int | None = None
                reviews_text = self._safe_text(card, *self.REVIEWS_SELECTORS)
                m = re.search(r'(\d+)', reviews_text.replace(' ', ''))
                if m:
                    reviews_count = int(m.group(1))

                # URL отзывов (используется ZoonReviewScraper)
                review_url = ''
                try:
                    rating_block = card.find_element(By.CSS_SELECTOR, '.minicard-item__rating')
                    review_url   = rating_block.get_attribute(self.REVIEW_LINK_ATTR) or ''
                except Exception:
                    pass

                records.append({
                    'name':          name,
                    'address':       address,
                    'category':      category,
                    'rating':        rating,
                    'reviews_count': reviews_count,
                    'review_url':    review_url,
                    'district':      _infer_district_from_address(address),
                })

            print(f'    {category} стр.{page_num}: {len(records)} заведений ({working_url})')
            time.sleep(random.uniform(1.5, 3.0))
        return records

    def scrape(self) -> pd.DataFrame:
        driver = self._make_driver()
        all_records: list[dict] = []
        try:
            for category, url in self.CATEGORIES.items():
                print(f'  Zoon: категория {category!r}')
                batch = self._scrape_category(driver, category, url)
                all_records.extend(batch)
        finally:
            driver.quit()
        return pd.DataFrame(all_records)


# ════════════════════════════════════════════════════════════════════════════
#  ZoonReviewScraper — негативные отзывы (гибрид: бильярд + entertainment)
# ════════════════════════════════════════════════════════════════════════════
class ZoonReviewScraper(BaseScraper):
    """Динамический парсинг негативных отзывов (Selenium).

    Гибридная стратегия:
      1. Поиск Zoon по слову «бильярд» → берём настоящие бильярдные места
         с текстовыми отзывами (обычно 1-3, остальные — только числовые оценки).
      2. Дополняем популярными досуговыми (entertainment) с ≥10 отзывов —
         боли клиентов те же (цены, персонал, атмосфера, ожидание, чистота).

    Результат: DataFrame с текстом жалоб + категорией (по KEYWORDS).
    """

    SEARCH_URL_TEMPLATE = 'https://zoon.ru/search/?city=msk&query=бильярд&page={page}'
    SEARCH_PAGES = 4   # ~30 карточек × 4 страницы = ~120 заведений

    COMPLAINT_KEYWORDS: dict[str, list[str]] = {
        'Столы и инвентарь': ['стол', 'кий', 'шар', 'покрытие', 'сукно', 'борт',
                               'луза', 'дырка', 'сломан', 'инвентарь'],
        'Цены':              ['дорого', 'цена', 'цены', 'ценник', 'стоимость',
                               'дорогой', 'переплатить', 'счёт', 'деньги'],
        'Персонал':          ['персонал', 'администратор', 'сотрудник', 'маркер',
                               'грубо', 'грубый', 'нагрубил', 'хамство', 'хам',
                               'невежливо', 'охрана'],
        'Атмосфера/чистота': ['накурено', 'дым', 'запах', 'грязно', 'грязь',
                               'туалет', 'шумно', 'темно', 'освещение', 'пьяные'],
        'Ожидание/запись':   ['ждать', 'очередь', 'занято', 'ожидание', 'бронь',
                               'бронирование', 'долго', 'мест', 'свободн'],
        'Сервис/кухня':      ['бар', 'еда', 'напитки', 'кухня', 'официант',
                               'wifi', 'интернет', 'кофе', 'меню'],
    }

    STOPWORDS: frozenset[str] = frozenset([
        'в', 'на', 'и', 'с', 'по', 'для', 'что', 'это', 'как', 'не', 'но',
        'а', 'к', 'от', 'за', 'из', 'до', 'у', 'о', 'же', 'так', 'все',
        'был', 'быть', 'или', 'при', 'есть', 'ещё', 'уже', 'очень', 'нет',
        'вот', 'раз', 'мне', 'нас', 'их', 'им', 'он', 'она', 'они', 'мы',
        'я', 'то', 'бы', 'ни', 'даже', 'где', 'когда', 'если', 'только',
        'там', 'тут', 'здесь', 'тоже', 'можно', 'его', 'её', 'нам', 'тебе',
        'может', 'который', 'которая', 'которые', 'после', 'через', 'перед',
        'этого', 'этой', 'этот', 'этим', 'такой', 'такие', 'просто', 'себя',
        'всего', 'всех', 'была', 'были', 'один', 'без', 'хотя', 'будет',
        'вы', 'ты', 'вас', 'тебя', 'моя', 'мой', 'наш', 'ваш', 'место',
        'клуб', 'бильярд', 'зал', 'заведение', 'раза', 'всё', 'мест',
        'пришли', 'пришёл', 'пришла', 'хорошо', 'плохо', 'нормально',
        'вообще', 'конечно', 'потому', 'либо',
    ])

    def __init__(self, max_clubs: int = 25, max_rating: float = 3.0) -> None:
        self.max_clubs  = max_clubs
        self.max_rating = max_rating

    def _make_driver(self) -> webdriver.Chrome:
        return make_chrome_driver()

    @staticmethod
    def _has_text_reviews(comments_text: str) -> bool:
        """True если в .comments указано N отзывов (а не «X оценок» или «Нет отзывов»)."""
        s = comments_text.lower()
        if 'нет отзыв' in s:
            return False
        return 'отзыв' in s

    def _harvest_from_url(
        self,
        driver: webdriver.Chrome,
        url_template: str,
        pages: int,
        require_billiard: bool,
        seen_urls: set,
        min_reviews: int = 0,
    ) -> list[tuple[str, str]]:
        """Сборщик ссылок: либо из поиска, либо из категории."""
        results: list[tuple[str, str]] = []
        for page in range(1, pages + 1):
            driver.get(url_template.format(page=page))
            try:
                WebDriverWait(driver, 20).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'li.minicard-item'))
                )
            except Exception:
                break

            cards = driver.find_elements(By.CSS_SELECTOR, 'li.minicard-item')
            if not cards:
                break

            for card in cards:
                try:
                    name = card.find_element(
                        By.CSS_SELECTOR,
                        '.minicard-item__title a, .title-link',
                    ).text.strip()
                    nl = name.lower()
                    if require_billiard:
                        if 'бильярд' not in nl:
                            continue
                        if any(w in nl for w in [
                            'магазин', 'товар', 'трейд', 'компания', 'оборудование',
                        ]):
                            continue
                    # Только заведения с текстовыми отзывами
                    try:
                        cnt_text = card.find_element(
                            By.CSS_SELECTOR, '.minicard-item__rating .comments',
                        ).text.strip()
                    except Exception:
                        cnt_text = ''
                    if not self._has_text_reviews(cnt_text):
                        continue
                    m = re.search(r'(\d+)', cnt_text)
                    n_reviews = int(m.group(1)) if m else 0
                    if n_reviews < min_reviews:
                        continue
                    rating_block = card.find_element(
                        By.CSS_SELECTOR, '.minicard-item__rating',
                    )
                    review_url = rating_block.get_attribute('data-js-lnk') or ''
                    if name and review_url and review_url not in seen_urls:
                        seen_urls.add(review_url)
                        results.append((name, review_url))
                except Exception:
                    continue
            time.sleep(random.uniform(1.5, 3.0))
        return results

    def _get_club_links(self, driver: webdriver.Chrome) -> list[tuple[str, str]]:
        """Гибрид: бильярдные через поиск + досуговые в дополнение."""
        seen_urls: set[str] = set()
        clubs: list[tuple[str, str]] = []

        # 1) Реальные бильярдные с текстовыми отзывами
        billiard_clubs = self._harvest_from_url(
            driver, self.SEARCH_URL_TEMPLATE, self.SEARCH_PAGES,
            require_billiard=True, seen_urls=seen_urls, min_reviews=1,
        )
        print(f'  Бильярдных с текстовыми отзывами: {len(billiard_clubs)}')
        clubs.extend(billiard_clubs)

        # 2) Дополняем популярными досуговыми (entertainment) до max_clubs
        if len(clubs) < self.max_clubs:
            need = self.max_clubs - len(clubs)
            entertainment_clubs = self._harvest_from_url(
                driver,
                'https://zoon.ru/msk/entertainment/?page={page}',
                pages=3,
                require_billiard=False,
                seen_urls=seen_urls,
                min_reviews=10,
            )
            print(f'  Дополняем досуговыми: {min(need, len(entertainment_clubs))}')
            clubs.extend(entertainment_clubs[:need])

        return clubs[:self.max_clubs]

    def _scrape_reviews_page(
        self,
        driver: webdriver.Chrome,
        club_name: str,
        club_url: str,
    ) -> list[dict]:
        """Парсит страницу отзывов конкретного заведения (Zoon BEM: .comment-item)."""
        driver.get(club_url)
        try:
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, '.comment-item, [class*="comment-item"]')
                )
            )
        except Exception:
            return []
        time.sleep(1)

        records: list[dict] = []
        review_cards = driver.find_elements(By.CSS_SELECTOR, '.comment-item')

        for card in review_cards:
            # Фильтр: только корневые отзывы (ответы заведения и подкомментарии
            # не имеют .comment-item__stars — пропускаем).
            try:
                star_el = card.find_element(
                    By.CSS_SELECTOR,
                    '.comment-item__stars .z-stars[style*="--rating"]',
                )
            except Exception:
                continue

            # Рейтинг из CSS-переменной --rating
            rating: float | None = None
            style = star_el.get_attribute('style') or ''
            m = re.search(r'--rating:\s*([\d.]+)', style)
            if m:
                rating = float(m.group(1))

            # Полный текст: .comment-item__body содержит summary
            # + основной текст + блоки «Достоинства/Недостатки».
            text = ''
            for tsel in ['.comment-item__body', '.js-comment-text',
                         '[itemprop="reviewBody"]', '.comment-text']:
                try:
                    candidate = card.find_element(By.CSS_SELECTOR, tsel).text.strip()
                    if len(candidate) > len(text):
                        text = candidate
                except Exception:
                    continue

            if not text or len(text) < 10:
                continue

            if rating is None or rating <= self.max_rating:
                records.append({
                    'club':   club_name,
                    'rating': rating,
                    'text':   text,
                    'url':    club_url,
                })

        return records

    @classmethod
    def classify_complaint(cls, text: str) -> list[str]:
        """Возвращает список категорий жалобы по ключевым словам."""
        text_lower = text.lower()
        found = [cat for cat, kws in cls.COMPLAINT_KEYWORDS.items()
                 if any(kw in text_lower for kw in kws)]
        return found or ['Другое']

    @classmethod
    def top_words(cls, texts: list[str], n: int = 30) -> pd.Series:
        """Частотный анализ слов из отзывов (без стоп-слов)."""
        words: list[str] = []
        for text in texts:
            tokens = re.findall(r'[а-яёa-z]{3,}', text.lower())
            words.extend(t for t in tokens if t not in cls.STOPWORDS)
        return pd.Series(Counter(words)).sort_values(ascending=False).head(n)

    def scrape(self) -> pd.DataFrame:
        driver = self._make_driver()
        all_reviews: list[dict] = []
        try:
            print('Собираем ссылки на клубы...')
            clubs = self._get_club_links(driver)
            print(f'Найдено клубов на Zoon: {len(clubs)}')

            for i, (name, url) in enumerate(clubs, 1):
                print(f'  {i}/{len(clubs)} {name[:45]}')
                batch = self._scrape_reviews_page(driver, name, url)
                all_reviews.extend(batch)
                print(f'    → {len(batch)} негативных отзывов')
                time.sleep(1.5)
        finally:
            driver.quit()

        df = pd.DataFrame(all_reviews)
        if not df.empty:
            df['categories'] = df['text'].apply(
                lambda t: ', '.join(self.classify_complaint(t))
            )
        return df
