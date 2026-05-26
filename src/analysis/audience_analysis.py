"""Анализ целевой аудитории по отзывам: темы, тональность, портреты.

Сохраняет таблицы в results/tables/audience/, графики в results/figures/audience/
и итоговый отчёт в results/reports/audience_summary.txt.
"""

from pathlib import Path

import pandas as pd
import plotly.express as px


PROJECT_ROOT = Path(__file__).resolve().parents[2]
INPUT_PATH = PROJECT_ROOT / 'data' / 'audience_clean.csv'

RESULTS_DIR = PROJECT_ROOT / 'results'
FIGURES_DIR = RESULTS_DIR / 'figures' / 'audience'
TABLES_DIR = RESULTS_DIR / 'tables' / 'audience'
REPORTS_DIR = RESULTS_DIR / 'reports'

FIGURES_DIR.mkdir(parents=True, exist_ok=True)
TABLES_DIR.mkdir(parents=True, exist_ok=True)
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

PLOTLY_TEMPLATE = 'plotly_white'

TOPIC_COLUMNS = {
    'topic_service': 'Сервис и персонал',
    'topic_atmosphere': 'Атмосфера и комфорт',
    'topic_tables_equipment': 'Столы и оборудование',
    'topic_price': 'Цены',
    'topic_food_bar': 'Еда и бар',
    'topic_booking': 'Бронь и ожидание',
    'topic_training': 'Тренировки и обучение',
    'topic_events_corporate': 'Корпоративы и мероприятия',
    'topic_noise_music': 'Шум и музыка',
    'topic_interior': 'Интерьер и чистота',
    'topic_location': 'Локация'
}


SENTIMENT_LABELS = {
    'negative': 'Негативные',
    'neutral': 'Нейтральные',
    'positive': 'Положительные',
    'unknown': 'Без оценки'
}


def build_topic_summary(df: pd.DataFrame) -> pd.DataFrame:
    """
    Считает сводку по темам отзывов.

    Один отзыв может относиться к нескольким темам, поэтому суммы по темам
    могут быть больше общего количества отзывов.
    """
    rows = []
    total_reviews = len(df)

    for column, label in TOPIC_COLUMNS.items():
        topic_df = df[df[column] == 1]
        positive_count = len(topic_df[topic_df['sentiment'] == 'positive'])
        neutral_count = len(topic_df[topic_df['sentiment'] == 'neutral'])
        negative_count = len(topic_df[topic_df['sentiment'] == 'negative'])
        reviews_count = len(topic_df)

        rows.append({
            'topic_column': column,
            'topic': label,
            'reviews_count': reviews_count,
            'reviews_share': reviews_count / total_reviews if total_reviews > 0 else 0,
            'mean_rating': topic_df['review_rating'].mean(),
            'positive_count': positive_count,
            'neutral_count': neutral_count,
            'negative_count': negative_count,
            'negative_share_inside_topic': negative_count / reviews_count if reviews_count > 0 else 0
        })

    return pd.DataFrame(rows).sort_values('reviews_count', ascending=False)


def build_sentiment_by_topic(topic_summary: pd.DataFrame) -> pd.DataFrame:
    """
    Переводит wide-таблицу topic_summary в длинный формат для stacked bar chart.
    """
    rows = []

    for _, row in topic_summary.iterrows():
        for sentiment, column in [
            ('negative', 'negative_count'),
            ('neutral', 'neutral_count'),
            ('positive', 'positive_count')
        ]:
            rows.append({
                'topic': row['topic'],
                'sentiment': sentiment,
                'sentiment_label': SENTIMENT_LABELS[sentiment],
                'reviews_count': row[column]
            })

    return pd.DataFrame(rows)


def build_reviews_by_place(df: pd.DataFrame) -> pd.DataFrame:
    """
    Считает статистику по каждому заведению.
    """
    return (
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


# 1. Insert build_data_overview after build_reviews_by_place
def build_data_overview(df: pd.DataFrame, topic_summary: pd.DataFrame, reviews_by_place: pd.DataFrame) -> list[str]:
    """
    Формирует короткую текстовую сводку о данных.

    Сводка нужна, чтобы после запуска файла сразу было понятно:
    сколько данных обработано, какие оценки преобладают,
    какие темы чаще всего встречаются и какие заведения дали больше всего отзывов.
    """
    total_reviews = len(df)
    total_places = df['place_name'].nunique()
    mean_rating = round(df['review_rating'].mean(), 2)
    median_rating = round(df['review_rating'].median(), 2)

    sentiment_counts = df['sentiment'].value_counts().to_dict()

    top_topics = topic_summary.head(5)[['topic', 'reviews_count']]
    top_places = reviews_by_place.head(25)[['place_name', 'district', 'reviews_count', 'mean_rating']]

    lines = [
        '',
        'Сводка по аудитории:',
        f'  отзывов: {total_reviews}, заведений: {total_places}',
        f'  средняя оценка: {mean_rating}, медиана: {median_rating}',
        '',
        'Тональность:',
    ]
    for sentiment, count in sentiment_counts.items():
        lines.append(f'  {sentiment}: {count}')

    lines.extend([
        '',
        'Топ-5 тем:',
        top_topics.to_string(index=False),
        '',
        'Топ-5 заведений:',
        top_places.to_string(index=False),
    ])
    return lines


def save_bar_chart(
    df: pd.DataFrame,
    x: str,
    y: str,
    color: str,
    title: str,
    filename: str,
    hover_data: dict
) -> Path:
    """
    Универсальная функция для горизонтального интерактивного bar chart.
    """
    figure_df = df.sort_values(x, ascending=True).copy()

    fig = px.bar(
        figure_df,
        x=x,
        y=y,
        orientation='h',
        color=color,
        color_continuous_scale='Blues',
        template=PLOTLY_TEMPLATE,
        title=title,
        hover_data=hover_data,
        labels={
            x: 'Количество отзывов',
            y: 'Тема'
        }
    )

    fig.update_layout(
        xaxis_title='Количество отзывов',
        yaxis_title='Тема',
        coloraxis_showscale=False
    )
    output_path = FIGURES_DIR / filename
    fig.write_html(output_path)
    return output_path


def save_topic_frequency_chart(topic_summary: pd.DataFrame) -> Path:
    """
    Сохраняет график самых обсуждаемых тем.
    """
    chart_df = topic_summary.copy()
    chart_df['reviews_share_percent'] = (chart_df['reviews_share'] * 100).round(1)

    return save_bar_chart(
        df=chart_df,
        x='reviews_count',
        y='topic',
        color='reviews_count',
        title='Наиболее обсуждаемые темы в отзывах',
        filename='topic_frequency_interactive.html',
        hover_data={
            'reviews_count': True,
            'reviews_share_percent': True,
            'mean_rating': ':.2f',
            'topic': False
        }
    )


def save_negative_topics_chart(topic_summary: pd.DataFrame) -> Path:
    """
    Сохраняет график главных болей клиентов.
    """
    chart_df = topic_summary.sort_values('negative_count', ascending=False).head(8).copy()
    chart_df['negative_share_percent'] = (chart_df['negative_share_inside_topic'] * 100).round(1)

    return save_bar_chart(
        df=chart_df,
        x='negative_count',
        y='topic',
        color='negative_count',
        title='Главные боли клиентов в негативных отзывах',
        filename='negative_topics_interactive.html',
        hover_data={
            'negative_count': True,
            'negative_share_percent': True,
            'reviews_count': True,
            'topic': False
        }
    )


def save_positive_topics_chart(topic_summary: pd.DataFrame) -> Path:
    """
    Сохраняет график положительных факторов выбора.
    """
    chart_df = topic_summary.sort_values('positive_count', ascending=False).head(8).copy()

    return save_bar_chart(
        df=chart_df,
        x='positive_count',
        y='topic',
        color='positive_count',
        title='Главные положительные факторы выбора',
        filename='positive_topics_interactive.html',
        hover_data={
            'positive_count': True,
            'reviews_count': True,
            'mean_rating': ':.2f',
            'topic': False
        }
    )


def save_sentiment_by_topic_chart(sentiment_by_topic: pd.DataFrame) -> Path:
    """
    Сохраняет stacked bar chart: темы по тональности отзывов.
    """
    topic_order = (
        sentiment_by_topic.groupby('topic')['reviews_count']
        .sum()
        .sort_values(ascending=True)
        .index
        .tolist()
    )

    fig = px.bar(
        sentiment_by_topic,
        x='reviews_count',
        y='topic',
        color='sentiment_label',
        orientation='h',
        template=PLOTLY_TEMPLATE,
        title='Упоминания тем по тональности отзывов',
        category_orders={
            'topic': topic_order,
            'sentiment_label': ['Негативные', 'Нейтральные', 'Положительные']
        },
        labels={
            'reviews_count': 'Количество отзывов',
            'topic': 'Тема',
            'sentiment_label': 'Тональность'
        },
        hover_data={
            'reviews_count': True,
            'topic': False,
            'sentiment_label': True
        }
    )

    fig.update_layout(
        xaxis_title='Количество отзывов',
        yaxis_title='Тема',
        legend_title='Тональность'
    )
    output_path = FIGURES_DIR / 'sentiment_by_topic_interactive.html'
    fig.write_html(output_path)
    return output_path


def build_audience_portraits(df: pd.DataFrame) -> list[str]:
    """
    Формирует портреты ЦА на основе тем отзывов.
    """
    portraits = []

    if df['topic_food_bar'].mean() > 0.2:
        portraits.append(
            'Компании для вечернего досуга: выбирают бильярдную как место, '
            'где можно не только играть, но и поесть, выпить и провести вечер.'
        )

    if df['topic_events_corporate'].mean() > 0.03:
        portraits.append(
            'Корпоративные и праздничные гости: используют бильярдную как площадку '
            'для дней рождения, корпоративов и встреч компаний.'
        )

    if df['topic_training'].mean() > 0.03:
        portraits.append(
            'Новички и любители обучения: обращают внимание на тренеров, инструкторов '
            'и возможность научиться играть.'
        )

    portraits.append(
        'Игроки, чувствительные к качеству оборудования: часто обсуждают столы, кии, шары и состояние инвентаря.'
    )
    portraits.append(
        'Гости, чувствительные к сервису: оценивают персонал, скорость ответа, бронь и решение конфликтных ситуаций.'
    )

    return portraits


def save_insights(df: pd.DataFrame, topic_summary: pd.DataFrame, portraits: list[str]) -> Path:
    """
    Сохраняет текстовые выводы по анализу ЦА.
    """
    total_reviews = len(df)
    total_places = df['place_name'].nunique()
    mean_rating = round(df['review_rating'].mean(), 2)

    top_topic = topic_summary.iloc[0]['topic']
    top_negative = topic_summary.sort_values('negative_count', ascending=False).iloc[0]['topic']
    top_positive = topic_summary.sort_values('positive_count', ascending=False).iloc[0]['topic']

    sentiment_counts = df['sentiment'].value_counts().to_dict()
    negative_count = sentiment_counts.get('negative', 0)
    neutral_count = sentiment_counts.get('neutral', 0)
    positive_count = sentiment_counts.get('positive', 0)

    lines = [
        'Анализ целевой аудитории',
        '',
        f'Всего проанализировано отзывов: {total_reviews}',
        f'Количество заведений: {total_places}',
        f'Средняя оценка заведений: {mean_rating}',
        f'Положительных отзывов: {positive_count}',
        f'Нейтральных отзывов: {neutral_count}',
        f'Негативных отзывов: {negative_count}',
        '',
        f'Самая обсуждаемая тема: {top_topic}',
        f'Главная боль клиентов: {top_negative}',
        f'Главный положительный фактор: {top_positive}',
        '',
        'Портреты аудитории:',
    ]

    lines.extend([f'- {portrait}' for portrait in portraits])

    lines.extend([
        '',
        'Что важно:',
        '- Бильярдные клубы воспринимаются не только как место для игры, но и как формат вечернего досуга.',
        '- Главные факторы выбора: атмосфера, качество столов, сервис, еда и бар.',
        '- Основные боли: состояние оборудования, проблемы брони и качество коммуникации с персоналом.',
        '- Для новой бильярдной важно строить не только спортивный, но и social leisure-формат.'
    ])
    output_path = REPORTS_DIR / 'audience_summary.txt'

    with open(output_path, 'w', encoding='utf-8') as file:
        file.write('\n'.join(lines))

    return output_path


def main() -> None:
    """
    Главная функция анализа ЦА.
    """
    df = pd.read_csv(INPUT_PATH, encoding='utf-8-sig')

    print('Загружено отзывов:', len(df))
    print('Количество заведений:', df['place_name'].nunique())

    topic_summary = build_topic_summary(df)
    sentiment_by_topic = build_sentiment_by_topic(topic_summary)
    reviews_by_place = build_reviews_by_place(df)
    data_overview_lines = build_data_overview(df, topic_summary, reviews_by_place)
    portraits = build_audience_portraits(df)

    saved_files = []

    topic_summary_path = TABLES_DIR / 'topic_summary.csv'
    sentiment_by_topic_path = TABLES_DIR / 'sentiment_by_topic.csv'
    reviews_by_place_path = TABLES_DIR / 'reviews_by_place.csv'

    topic_summary.to_csv(topic_summary_path, index=False, encoding='utf-8-sig')
    sentiment_by_topic.to_csv(sentiment_by_topic_path, index=False, encoding='utf-8-sig')
    reviews_by_place.to_csv(reviews_by_place_path, index=False, encoding='utf-8-sig')

    saved_files.extend([
        topic_summary_path,
        sentiment_by_topic_path,
        reviews_by_place_path
    ])

    saved_files.append(save_topic_frequency_chart(topic_summary))
    saved_files.append(save_negative_topics_chart(topic_summary))
    saved_files.append(save_positive_topics_chart(topic_summary))
    saved_files.append(save_sentiment_by_topic_chart(sentiment_by_topic))
    saved_files.append(save_insights(df, topic_summary, portraits))

    print('\n'.join(data_overview_lines))

    print('Анализ завершен')
    print('Сохранены файлы:')
    for path in saved_files:
        print('-', path)


if __name__ == '__main__':
    main()