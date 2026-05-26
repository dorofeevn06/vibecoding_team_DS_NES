"""Парсеры Zoon.ru (Selenium):
- ZoonScraper: досуговые заведения по трём категориям;
- ZoonReviewScraper: отзывы (бильярдные через поиск + добиваем досуговыми).
"""

import random
import re
import time
from collections import Counter
from typing import Optional

import pandas as pd
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from .base import BaseScraper, _infer_district_from_address, make_chrome_driver


class ZoonScraper(BaseScraper):
    """Досуговые заведения Москвы по трём действующим категориям Zoon.

    Категории /msk/billiards/, /msk/bowling/, /msk/bars/ переехали в 404,
    оставляем рестораны, развлечения и фитнес.
    """

    CATEGORIES = {
        'рестораны':   'https://zoon.ru/msk/restaurants/',
        'развлечения': 'https://zoon.ru/msk/entertainment/',
        'фитнес':      'https://zoon.ru/msk/fitness/',
    }

    # Рейтинг хранится в CSS-переменной style="--rating: 4.9", не в тексте.
    CARD_SELECTORS    = ['li.minicard-item', '.minicard-item']
    TITLE_SELECTORS   = ['.minicard-item__title a.title-link',
                         '.minicard-item__title a', '.title-link',
                         'a[data-uitest="org-link"]']
    ADDR_SELECTORS    = ['.minicard-item__address', '[class*="address"]']
    RATING_STYLE_SEL  = '.z-stars[style*="--rating"]'
    REVIEWS_SELECTORS = ['.minicard-item__rating .comments', '.comments']
    REVIEW_LINK_ATTR  = 'data-js-lnk'

    def __init__(self, max_pages: int = 3):
        self.max_pages = max_pages

    def _make_driver(self):
        return make_chrome_driver()

    @staticmethod
    def _safe_text(element, *selectors: str) -> str:
        for sel in selectors:
            try:
                text = element.find_element(By.CSS_SELECTOR, sel).text.strip()
                if text:
                    return text
            except Exception:
                continue
        return ''

    def _find_cards(self, driver) -> list:
        for sel in self.CARD_SELECTORS:
            cards = driver.find_elements(By.CSS_SELECTOR, sel)
            if cards:
                return cards
        return []

    def _scrape_category(self, driver, category: str, base_url: str) -> list[dict]:
        driver.get(base_url)
        time.sleep(3)
        if '404' in driver.title.lower() or len(driver.page_source) < 50_000:
            print(f'    {category}: страница недоступна')
            return []

        records = []
        for page_num in range(1, self.max_pages + 1):
            if page_num > 1:
                driver.get(f'{base_url}?page={page_num}')

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
                break

            for card in cards:
                name = self._safe_text(card, *self.TITLE_SELECTORS)
                if not name:
                    continue
                address = self._safe_text(card, *self.ADDR_SELECTORS)

                rating = None
                try:
                    star_el = card.find_element(By.CSS_SELECTOR, self.RATING_STYLE_SEL)
                    m = re.search(r'--rating:\s*([\d.]+)', star_el.get_attribute('style') or '')
                    if m:
                        rating = float(m.group(1))
                except Exception:
                    pass

                reviews_count = None
                reviews_text = self._safe_text(card, *self.REVIEWS_SELECTORS)
                m = re.search(r'(\d+)', reviews_text.replace(' ', ''))
                if m:
                    reviews_count = int(m.group(1))

                review_url = ''
                try:
                    rating_block = card.find_element(By.CSS_SELECTOR, '.minicard-item__rating')
                    review_url = rating_block.get_attribute(self.REVIEW_LINK_ATTR) or ''
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

            print(f'    {category} стр.{page_num}: {len(records)} заведений')
            time.sleep(random.uniform(1.5, 3.0))
        return records

    def scrape(self) -> pd.DataFrame:
        driver = self._make_driver()
        all_records = []
        try:
            for category, url in self.CATEGORIES.items():
                print(f'  Zoon: категория {category!r}')
                all_records.extend(self._scrape_category(driver, category, url))
        finally:
            driver.quit()
        return pd.DataFrame(all_records)


class ZoonReviewScraper(BaseScraper):
    """Отзывы для анализа жалоб.

    Сначала ищем настоящие бильярдные через поиск Zoon, потом добиваем
    выборку популярными досуговыми из категории entertainment.
    """

    SEARCH_URL = 'https://zoon.ru/search/?city=msk&query=бильярд&page={page}'
    SEARCH_PAGES = 4

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

    STOPWORDS = {
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
    }

    NON_BILLIARD_WORDS = ['магазин', 'товар', 'трейд', 'компания', 'оборудование']

    def __init__(self, max_clubs: int = 25, max_rating: float = 3.0):
        self.max_clubs = max_clubs
        self.max_rating = max_rating

    def _make_driver(self):
        return make_chrome_driver()

    @staticmethod
    def _has_text_reviews(comments_text: str) -> bool:
        s = comments_text.lower()
        if 'нет отзыв' in s:
            return False
        return 'отзыв' in s

    def _harvest(
        self,
        driver,
        url_template: str,
        pages: int,
        require_billiard: bool,
        seen_urls: set,
        min_reviews: int = 0,
    ) -> list[tuple[str, str]]:
        results = []
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
                        By.CSS_SELECTOR, '.minicard-item__title a, .title-link'
                    ).text.strip()
                    nl = name.lower()
                    if require_billiard:
                        if 'бильярд' not in nl:
                            continue
                        if any(w in nl for w in self.NON_BILLIARD_WORDS):
                            continue
                    try:
                        cnt_text = card.find_element(
                            By.CSS_SELECTOR, '.minicard-item__rating .comments'
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
                        By.CSS_SELECTOR, '.minicard-item__rating'
                    )
                    review_url = rating_block.get_attribute('data-js-lnk') or ''
                    if name and review_url and review_url not in seen_urls:
                        seen_urls.add(review_url)
                        results.append((name, review_url))
                except Exception:
                    continue
            time.sleep(random.uniform(1.5, 3.0))
        return results

    def _get_club_links(self, driver) -> list[tuple[str, str]]:
        seen_urls: set[str] = set()
        clubs = self._harvest(
            driver, self.SEARCH_URL, self.SEARCH_PAGES,
            require_billiard=True, seen_urls=seen_urls, min_reviews=1,
        )
        print(f'  Бильярдных с текстовыми отзывами: {len(clubs)}')

        if len(clubs) < self.max_clubs:
            need = self.max_clubs - len(clubs)
            extra = self._harvest(
                driver,
                'https://zoon.ru/msk/entertainment/?page={page}',
                pages=3, require_billiard=False, seen_urls=seen_urls,
                min_reviews=10,
            )
            print(f'  Дополняем досуговыми: {min(need, len(extra))}')
            clubs.extend(extra[:need])
        return clubs[:self.max_clubs]

    def _scrape_reviews_page(self, driver, club_name: str, club_url: str) -> list[dict]:
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

        records = []
        for card in driver.find_elements(By.CSS_SELECTOR, '.comment-item'):
            # Ответы заведения и треды без .comment-item__stars пропускаем.
            try:
                star_el = card.find_element(
                    By.CSS_SELECTOR,
                    '.comment-item__stars .z-stars[style*="--rating"]',
                )
            except Exception:
                continue

            rating: Optional[float] = None
            m = re.search(r'--rating:\s*([\d.]+)', star_el.get_attribute('style') or '')
            if m:
                rating = float(m.group(1))

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
        text_lower = text.lower()
        found = [cat for cat, kws in cls.COMPLAINT_KEYWORDS.items()
                 if any(kw in text_lower for kw in kws)]
        return found or ['Другое']

    @classmethod
    def top_words(cls, texts: list[str], n: int = 30) -> pd.Series:
        words = []
        for text in texts:
            tokens = re.findall(r'[а-яёa-z]{3,}', text.lower())
            words.extend(t for t in tokens if t not in cls.STOPWORDS)
        return pd.Series(Counter(words)).sort_values(ascending=False).head(n)

    def scrape(self) -> pd.DataFrame:
        driver = self._make_driver()
        all_reviews = []
        try:
            print('Собираем ссылки на клубы...')
            clubs = self._get_club_links(driver)
            print(f'Найдено клубов: {len(clubs)}')

            for i, (name, url) in enumerate(clubs, 1):
                print(f'  {i}/{len(clubs)} {name[:45]}')
                batch = self._scrape_reviews_page(driver, name, url)
                all_reviews.extend(batch)
                print(f'    -> {len(batch)} негативных отзывов')
                time.sleep(1.5)
        finally:
            driver.quit()

        df = pd.DataFrame(all_reviews)
        if not df.empty:
            df['categories'] = df['text'].apply(
                lambda t: ', '.join(self.classify_complaint(t))
            )
        return df
