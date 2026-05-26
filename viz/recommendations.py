"""Вкладка Dash «План действий» с карточками рекомендаций."""

from collections import Counter
from typing import Optional

import pandas as pd
from dash import html

from src.zoon import ZoonReviewScraper


_PRIORITY_STYLES = {
    'высокий': {'background': '#fdecea', 'border': '#c0392b', 'tag': '#c0392b'},
    'средний': {'background': '#fff5e6', 'border': '#e67e22', 'tag': '#e67e22'},
    'низкий':  {'background': '#eaf5ea', 'border': '#27ae60', 'tag': '#27ae60'},
}


def _priority_tag(level: str) -> html.Span:
    s = _PRIORITY_STYLES.get(level, _PRIORITY_STYLES['средний'])
    return html.Span(
        f'приоритет: {level}',
        style={
            'background':   s['tag'],
            'color':        'white',
            'padding':      '3px 10px',
            'borderRadius': '4px',
            'fontSize':     '12px',
            'marginLeft':   '12px',
        },
    )


def _card(title: str, priority: str, data: str, actions: list[str]) -> html.Div:
    s = _PRIORITY_STYLES.get(priority, _PRIORITY_STYLES['средний'])
    return html.Div([
        html.Div([
            html.H3(title, style={'display': 'inline', 'margin': 0, 'fontSize': '17px'}),
            _priority_tag(priority),
        ], style={'marginBottom': '8px'}),
        html.P(data, style={'color': '#555', 'fontSize': '13px',
                            'marginBottom': '10px', 'fontStyle': 'italic'}),
        html.Ul([html.Li(a, style={'marginBottom': '4px'}) for a in actions],
                style={'marginTop': '6px'}),
    ], style={
        'background':   s['background'],
        'borderLeft':   f'4px solid {s["border"]}',
        'padding':      '14px 18px',
        'margin':       '12px 0',
        'borderRadius': '4px',
    })


def _count_complaints(df_reviews: pd.DataFrame) -> Counter:
    if df_reviews is None or df_reviews.empty or 'categories' not in df_reviews.columns:
        return Counter()
    cnt: Counter = Counter()
    for cats in df_reviews['categories'].dropna():
        for c in cats.split(', '):
            if c and c != 'Другое':
                cnt[c] += 1
    return cnt


# Меры по каждой категории жалоб. Хардкод — это типовые действия,
# которые мало зависят от конкретных цифр.
ACTIONS_BY_CATEGORY: dict[str, list[str]] = {
    'Столы и инвентарь': [
        'Поставить турнирные столы (Brunswick, Aramith) хотя бы на половину зала',
        'Менять сукно регулярно, раз в 2-3 месяца',
        'Полный набор киев на разный вес, чекать перед каждым днём',
    ],
    'Ожидание/запись': [
        'Сделать нормальное онлайн-бронирование, чтобы можно было ночью',
        'На сайте показывать, какие столы сейчас свободны',
        'За пару часов до брони присылать смс-напоминалку',
    ],
    'Сервис/кухня': [
        'Кухня работает до закрытия, ночью меню не урезаем',
        'Не стандартный спортбар: авторские закуски, крафт',
        'Кальяны делает отдельный мастер с нормальной картой',
    ],
    'Персонал': [
        'В каждом зале есть маркер, помогает считать и разруливает спорные моменты',
        'Регулярные тренинги по сервису и этикету',
        'Прозрачная система чаевых через QR',
    ],
    'Атмосфера/чистота': [
        'Нормальная вентиляция и отдельная зона для курящих',
        'В часы пик уборка каждые полчаса',
        'Над каждым столом настраиваемый свет',
    ],
    'Цены': [
        'Прайс на сайте без скрытых платежей и звёздочек',
        'Программа лояльности на часах игры',
        'Днём играть дешевле: и трафик утром, и выручка',
    ],
}


def build_recommendations_layout(
    df_clubs: pd.DataFrame,
    df_rent: pd.DataFrame,
    df_reviews: pd.DataFrame,
    full_opp_df: pd.DataFrame,
) -> html.Div:
    cards: list[html.Div] = []

    # Где открывать
    if full_opp_df is not None and not full_opp_df.empty:
        top3 = full_opp_df.head(3)
        top_districts = ', '.join(top3['district'].tolist())
        avg_rent: Optional[int] = None
        if (df_rent is not None and not df_rent.empty
                and 'price_per_sqm' in df_rent.columns):
            rent_top = df_rent[df_rent['district'].isin(top3['district'])]
            if not rent_top.empty:
                avg_rent = int(rent_top['price_per_sqm'].median())
        data_line = f'Лучшие три округа по скору: {top_districts}.'
        if avg_rent:
            data_line += f' Аренда там в среднем около {avg_rent:,} ₽/м²/мес.'
        cards.append(_card(
            '1. Где открывать',
            'высокий',
            data_line,
            [
                f'{top3.iloc[0]["district"]} - самый сбалансированный вариант: '
                'спрос есть, конкурентов мало',
                'В ЦАО соваться рискованно: аренда дорогая, а заведений и так перебор',
                'Под зал на 8-10 столов плюс бар нужно 250-350 м²',
            ],
        ))

    # Топ категорий жалоб
    counts = _count_complaints(df_reviews)
    priorities = ['высокий', 'высокий', 'средний', 'средний']
    for i, (cat, n) in enumerate(counts.most_common(4), start=2):
        prio = priorities[i - 2] if i - 2 < len(priorities) else 'низкий'
        if df_reviews is not None and not df_reviews.empty:
            high = df_reviews[df_reviews['rating'] >= 4]
            in_high = sum(
                1 for cats in high['categories'].dropna()
                if cat in cats.split(', ')
            )
            data_line = (
                f'Упоминается {n} раз из {len(df_reviews)} отзывов. '
                f'Из них {in_high} в позитивных (4-5/5), '
                'то есть проблема всплывает даже у довольных гостей.'
            )
        else:
            data_line = f'Упоминается {n} раз'
        actions = ACTIONS_BY_CATEGORY.get(cat, ['Конкретные меры зависят от деталей'])
        cards.append(_card(f'{i}. {cat}', prio, data_line, actions))

    # Что важно не испортить
    if df_reviews is not None and not df_reviews.empty and 'text' in df_reviews.columns:
        pos = df_reviews[df_reviews['rating'] == 5]
        if not pos.empty:
            pos_words = ZoonReviewScraper.top_words(pos['text'].tolist(), n=8)
            words_str = ', '.join(pos_words.index[:6].tolist())
            cards.append(_card(
                f'{len(cards) + 1}. Что важно не испортить',
                'средний',
                f'В позитивных отзывах ({len(pos)} штук) чаще всего пишут: {words_str}.',
                [
                    'Атмосфера и интерьер: без этого даже идеальные столы не спасут',
                    'Дружелюбный персонал, который замечает гостя и быстро реагирует',
                    'Что-то узнаваемое в месте, ради чего захочется вернуться и рассказать',
                ],
            ))

    # Целевой рейтинг
    if df_clubs is not None and not df_clubs.empty and 'rating' in df_clubs.columns:
        ratings = pd.to_numeric(df_clubs['rating'], errors='coerce').dropna()
        if len(ratings) > 5:
            median = round(ratings.median(), 1)
            p75 = round(ratings.quantile(0.75), 1)
            cards.append(_card(
                f'{len(cards) + 1}. Какой рейтинг ставим целью',
                'низкий',
                f'У конкурентов в 2GIS медиана {median}, верхняя четверть от {p75}.',
                [
                    f'За первый год выйти хотя бы на {p75}',
                    'Отвечать на все отзывы, особенно на негативные',
                    'Не выпрашивать оценки скидками: лучше позвать обратно тех, кому реально зашло',
                ],
            ))

    return html.Div([
        html.Div([
            html.H2('Что делать, чтобы «Луzа и Шары» получился',
                    style={'marginBottom': '4px', 'fontFamily': 'Arial'}),
            html.P(
                'Карточки собираются автоматически из данных: топ округов по скору, '
                'самые частые претензии в отзывах, рейтинги конкурентов. '
                'В каждой карточке конкретные шаги под её проблему.',
                style={'color': '#666', 'fontSize': '13px', 'marginTop': 0},
            ),
        ], style={'padding': '15px 25px', 'borderBottom': '1px solid #ddd'}),
        html.Div(cards, style={'padding': '10px 25px'}),
    ])
