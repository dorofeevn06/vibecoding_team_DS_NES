"""Чистка и разметка отзывов после парсинга.

Удаляет дубли и пустые тексты, размечает отзывы по темам и тональности,
считает частоты тем и сохраняет результаты в data/processed/audience_clean.csv
и в results/.
"""

from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]

INPUT_PATH = PROJECT_ROOT / 'data' / 'raw' / 'audience_raw.csv'
CLEAN_OUTPUT_PATH = PROJECT_ROOT / 'data' / 'processed' /'audience_clean.csv'

RESULTS_DIR = PROJECT_ROOT / 'results'
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


TOPIC_KEYWORDS = {
    'service': [
        'персонал', 'сотрудник', 'сотрудники', 'администратор', 'менеджер',
        'официант', 'официанты', 'обслуживание', 'сервис', 'хамство',
        'вежлив', 'груб', 'отношение'
    ],
    'atmosphere': [
        'атмосфера', 'уют', 'уютно', 'комфорт', 'комфортно', 'обстановка',
        'место', 'пространство', 'вайб', 'приятно'
    ],
    'tables_equipment': [
        'стол', 'столы', 'сукно', 'кий', 'кии', 'шары', 'оборудование',
        'луза', 'борта', 'бильярд'
    ],
    'price': [
        'цена', 'цены', 'дорого', 'дешево', 'стоимость', 'чек',
        'прайс', 'руб', '₽', 'скидка'
    ],
    'food_bar': [
        'еда', 'кухня', 'бар', 'напитки', 'коктейль', 'пиво', 'кофе',
        'десерт', 'меню', 'вкусно', 'невкусно'
    ],
    'booking': [
        'бронь', 'забронировать', 'забронировал', 'забронировали',
        'бронирование', 'запись', 'столик', 'очередь', 'ждать',
        'ожидание', 'дозвониться', 'дозвонился', 'по телефону',
        'резерв', 'резервировали', 'свободных столов', 'занято'
    ],
    'training': [
        'тренер', 'тренировка', 'обучение', 'обучаться',
        'инструктор', 'научили', 'учиться', 'мастер',
        'урок', 'занятие', 'школа бильярда'
    ],
    'events_corporate': [
        'корпоратив', 'день рождения', 'мероприятие', 'праздник',
        'банкет', 'компания друзей', 'тимбилдинг', 'вечеринка',
        'отмечали', 'праздновали'
    ],
    'noise_music': [
        'шум', 'шумно', 'громко', 'музыка', 'тихо', 'звуки'
    ],
    'interior': [
        'интерьер', 'дизайн', 'красиво', 'ремонт', 'новый', 'современный',
        'чисто', 'чистота', 'грязно'
    ],
    'location': [
        'расположение', 'локация', 'метро', 'район', 'добраться',
        'парковка', 'адрес'
    ]
}


TOPIC_LABELS = {
    'service': 'Сервис и персонал',
    'atmosphere': 'Атмосфера и комфорт',
    'tables_equipment': 'Столы и оборудование',
    'price': 'Цены',
    'food_bar': 'Еда и бар',
    'booking': 'Бронь и ожидание',
    'training': 'Тренировки и обучение',
    'events_corporate': 'Корпоративы и мероприятия',
    'noise_music': 'Шум и музыка',
    'interior': 'Интерьер и чистота',
    'location': 'Локация'
}


def clean_text(text):
    """
    Чистит текст отзыва перед сохранением в CSV.

    
    CSV использует запятые как разделители столбцов. 
    Для анализа ЦА эти символы не критичны, поэтому мы заменяем их пробелами.
    Смысл отзыва при этом сохраняется.
    """
    text = str(text)

    text = text.replace(',', ' ')
    text = text.replace(';', ' ')
    text = text.replace('"', ' ')
    text = text.replace("'", ' ')
    text = text.replace('\n', ' ')
    text = text.replace('\r', ' ')

    text = ' '.join(text.split())

    return text.strip()


def define_sentiment(rating):
    """
    Определяет простую тональность отзыва по оценке.

    Логика:
        rating <= 2  → negative
        rating == 3  → neutral
        rating >= 4  → positive
    """
    if pd.isna(rating):
        return 'unknown'
    if rating <= 2:
        return 'negative'
    if rating == 3:
        return 'neutral'
    return 'positive'


def has_topic(text, keywords):
    """
    Проверяет, относится ли отзыв к теме.
    """
    text = str(text).lower()

    for keyword in keywords:
        if keyword in text:
            return 1

    return 0


def prepare_clean_reviews(df):
    """
    Делает основную очистку таблицы отзывов.
    """
    df = df.copy()

    df['review_text'] = df['review_text'].apply(clean_text)

    df = df[df['review_text'].notna()]
    df = df[df['review_text'].str.len() > 10]

    df = df.drop_duplicates(subset=['place_name', 'review_text', 'review_date'])

    df['review_rating'] = pd.to_numeric(df['review_rating'], errors='coerce')
    df['review_length'] = df['review_text'].str.len()
    df['sentiment'] = df['review_rating'].apply(define_sentiment)

    return df


def add_topic_columns(df):
    """
    Добавляет бинарные столбцы тем.
    """
    df = df.copy()

    for topic, keywords in TOPIC_KEYWORDS.items():
        column_name = f'topic_{topic}'
        df[column_name] = df['review_text'].apply(lambda text: has_topic(text, keywords))

    return df


def build_topics_summary(df):
    """
    Считает общую статистику по темам отзывов.
    """
    rows = []
    total_reviews = len(df)

    for topic in TOPIC_KEYWORDS:
        column_name = f'topic_{topic}'
        topic_reviews = df[df[column_name] == 1]

        rows.append({
            'topic': topic,
            'topic_label': TOPIC_LABELS[topic],
            'reviews_count': len(topic_reviews),
            'reviews_share': len(topic_reviews) / total_reviews if total_reviews > 0 else 0,
            'mean_rating': topic_reviews['review_rating'].mean(),
            'negative_count': len(topic_reviews[topic_reviews['sentiment'] == 'negative']),
            'positive_count': len(topic_reviews[topic_reviews['sentiment'] == 'positive']),
            'negative_share': (
                len(topic_reviews[topic_reviews['sentiment'] == 'negative']) / len(topic_reviews)
                if len(topic_reviews) > 0
                else 0
            )
        })

    summary = pd.DataFrame(rows)
    summary = summary.sort_values('reviews_count', ascending=False)

    return summary


def build_pain_points(df):
    """
    Выделяет главные боли клиентов.
    """
    negative_reviews = df[df['sentiment'] == 'negative']

    rows = []

    for topic in TOPIC_KEYWORDS:
        column_name = f'topic_{topic}'
        topic_negative = negative_reviews[negative_reviews[column_name] == 1]

        rows.append({
            'topic': topic,
            'topic_label': TOPIC_LABELS[topic],
            'negative_reviews_count': len(topic_negative),
            'share_among_negative': (
                len(topic_negative) / len(negative_reviews)
                if len(negative_reviews) > 0
                else 0
            )
        })

    pain_points = pd.DataFrame(rows)
    pain_points = pain_points.sort_values('negative_reviews_count', ascending=False)

    return pain_points


def build_positive_factors(df):
    """
    Выделяет положительные факторы выбора.
    """
    positive_reviews = df[df['sentiment'] == 'positive']

    rows = []

    for topic in TOPIC_KEYWORDS:
        column_name = f'topic_{topic}'
        topic_positive = positive_reviews[positive_reviews[column_name] == 1]

        rows.append({
            'topic': topic,
            'topic_label': TOPIC_LABELS[topic],
            'positive_reviews_count': len(topic_positive),
            'share_among_positive': (
                len(topic_positive) / len(positive_reviews)
                if len(positive_reviews) > 0
                else 0
            )
        })

    positive_factors = pd.DataFrame(rows)
    positive_factors = positive_factors.sort_values('positive_reviews_count', ascending=False)

    return positive_factors


def build_reviews_by_place(df):
    """
    Считает статистику по каждому заведению.
    """
    reviews_by_place = (
        df.groupby(['place_name', 'district', 'yandex_name'], dropna=False)
        .agg(
            reviews_count=('review_text', 'count'),
            mean_rating=('review_rating', 'mean'),
            negative_reviews=('sentiment', lambda x: (x == 'negative').sum()),
            positive_reviews=('sentiment', lambda x: (x == 'positive').sum())
        )
        .reset_index()
        .sort_values('reviews_count', ascending=False)
    )

    return reviews_by_place


def main():
    """
    Главная функция обработки ЦА.
    """
    df_raw = pd.read_csv(INPUT_PATH, encoding='utf-8-sig')

    print('Сырых отзывов загружено:', len(df_raw))
    print('Уникальных заведений:', df_raw['place_name'].nunique())

    df_clean = prepare_clean_reviews(df_raw)
    df_clean = add_topic_columns(df_clean)

    topics_summary = build_topics_summary(df_clean)
    pain_points = build_pain_points(df_clean)
    positive_factors = build_positive_factors(df_clean)
    reviews_by_place = build_reviews_by_place(df_clean)

    df_clean.to_csv(CLEAN_OUTPUT_PATH, index=False, encoding='utf-8-sig')
    topics_summary.to_csv(RESULTS_DIR / 'audience_topics_summary.csv', index=False, encoding='utf-8-sig')
    pain_points.to_csv(RESULTS_DIR / 'audience_pain_points.csv', index=False, encoding='utf-8-sig')
    positive_factors.to_csv(RESULTS_DIR / 'audience_positive_factors.csv', index=False, encoding='utf-8-sig')
    reviews_by_place.to_csv(RESULTS_DIR / 'reviews_by_place.csv', index=False, encoding='utf-8-sig')

    print('Топ тем по количеству отзывов:')
    print(topics_summary[['topic_label', 'reviews_count']].head(5))
    print('Обработка завершена')
    print('Очищенных отзывов:', len(df_clean))
    print('Файл сохранен:', CLEAN_OUTPUT_PATH)
    print('Таблицы сохранены в:', RESULTS_DIR)


if __name__ == '__main__':
    main()