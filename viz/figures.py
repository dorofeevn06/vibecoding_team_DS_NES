"""Функции построения графиков. Каждая принимает DataFrame и возвращает Plotly Figure."""

from collections import Counter

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


def make_top10_table(df_clubs: pd.DataFrame) -> pd.DataFrame:
    """Топ-10 клубов по рейтингу."""
    df = df_clubs.copy()
    df['rating'] = pd.to_numeric(df['rating'], errors='coerce')
    df['reviews'] = pd.to_numeric(df['reviews'], errors='coerce')
    top10 = (
        df[df['rating'].notna()]
        .sort_values(['rating', 'reviews'], ascending=[False, False])
        .head(10)[['name', 'address', 'district', 'rating', 'reviews']]
        .reset_index(drop=True)
    )
    top10.index += 1
    return top10


def make_rating_hist(df_clubs: pd.DataFrame) -> go.Figure:
    df = df_clubs.copy()
    df['rating'] = pd.to_numeric(df['rating'], errors='coerce')
    fig = px.histogram(
        df[df['rating'].notna()],
        x='rating',
        nbins=20,
        title='Распределение рейтингов бильярдных клубов Москвы (2GIS)',
        labels={'rating': 'Рейтинг', 'count': 'Количество'},
        color_discrete_sequence=['#2E86AB'],
    )
    fig.update_layout(bargap=0.05)
    return fig


def make_district_bar(df_clubs: pd.DataFrame) -> go.Figure:
    df = df_clubs.copy()
    df['rating'] = pd.to_numeric(df['rating'], errors='coerce')
    df['reviews'] = pd.to_numeric(df['reviews'], errors='coerce')
    by_district = (
        df.groupby('district')
        .agg(clubs=('name', 'count'),
             avg_rating=('rating', 'mean'),
             total_reviews=('reviews', 'sum'))
        .reset_index()
        .sort_values('clubs', ascending=False)
    )
    by_district['avg_rating'] = by_district['avg_rating'].round(2)
    fig = px.bar(
        by_district,
        x='district', y='clubs',
        color='avg_rating', color_continuous_scale='RdYlGn',
        title='Бильярдные клубы по округам Москвы',
        labels={'district': 'Округ', 'clubs': 'Кол-во клубов',
                'avg_rating': 'Средний рейтинг'},
        text='clubs',
    )
    fig.update_traces(textposition='outside')
    return fig


def make_rent_bar(df_rent: pd.DataFrame) -> go.Figure:
    if df_rent is None or df_rent.empty or 'price_per_sqm' not in df_rent.columns:
        return go.Figure().update_layout(title='Данные sob.ru недоступны')

    valid = df_rent[
        df_rent['price_per_sqm'].notna() & (df_rent['district'] != 'Другое')
    ]
    if valid.empty:
        return go.Figure().update_layout(title='Данные sob.ru недоступны')

    agg = (
        valid.groupby('district')['price_per_sqm']
        .agg(median_rent='median', count='count')
        .reset_index()
        .sort_values('median_rent')
    )
    fig = px.bar(
        agg,
        x='district', y='median_rent',
        color='median_rent',
        color_continuous_scale='RdYlGn_r',  # дорого -> красный, дёшево -> зелёный
        text=agg['median_rent'].apply(lambda x: f'{int(x):,}'),
        title='Медианная аренда коммерческих помещений (sob.ru, ₽/м²/мес)',
        labels={'district': 'Округ', 'median_rent': '₽/м²/мес'},
    )
    fig.update_traces(textposition='outside')
    fig.update_layout(coloraxis_showscale=False)
    return fig


def make_zoon_bar(df_zoon: pd.DataFrame) -> go.Figure:
    if df_zoon is None or df_zoon.empty or 'district' not in df_zoon.columns:
        return go.Figure().update_layout(title='Данные Zoon недоступны')

    agg = (
        df_zoon[df_zoon['district'] != 'Другое']
        .groupby('district').size()
        .reset_index(name='venue_count')
        .sort_values('venue_count', ascending=False)
    )
    if agg.empty:
        return go.Figure().update_layout(title='Данные Zoon недоступны')

    fig = px.bar(
        agg,
        x='district', y='venue_count',
        color='venue_count', color_continuous_scale='Blues',
        text='venue_count',
        title='Досуговые заведения по округам Москвы (Zoon)',
        labels={'district': 'Округ', 'venue_count': 'Кол-во заведений'},
    )
    fig.update_traces(textposition='outside')
    fig.update_layout(coloraxis_showscale=False)
    return fig


def make_zoon_stacked_bar(df_zoon: pd.DataFrame) -> go.Figure:
    if df_zoon is None or df_zoon.empty or 'district' not in df_zoon.columns:
        return go.Figure().update_layout(title='Данные Zoon недоступны')

    valid = df_zoon[df_zoon['district'] != 'Другое']
    if valid.empty:
        return go.Figure().update_layout(title='Данные Zoon недоступны')

    agg = valid.groupby(['district', 'category']).size().reset_index(name='count')
    return px.bar(
        agg, x='district', y='count', color='category', barmode='stack',
        title='Досуговые заведения по округам (Zoon)',
        labels={'district': 'Округ', 'count': 'Кол-во', 'category': 'Категория'},
    )


def make_complaints_bar(df_reviews: pd.DataFrame) -> go.Figure:
    """Жалобы по всем отзывам. Категории определяются классификатором по ключевым словам."""
    if df_reviews is None or df_reviews.empty or 'categories' not in df_reviews.columns:
        return go.Figure().update_layout(title='Данные отзывов недоступны')

    counts: Counter = Counter()
    for cats in df_reviews['categories'].dropna():
        for c in cats.split(', '):
            counts[c] += 1
    if not counts:
        return go.Figure().update_layout(title='Данные отзывов недоступны')

    cat_df = pd.DataFrame(counts.most_common(), columns=['category', 'count'])
    fig = px.bar(
        cat_df,
        x='count', y='category', orientation='h',
        color='count', color_continuous_scale='Reds', text='count',
        title=f'Упоминания проблем во всех отзывах ({len(df_reviews)} шт., Яндекс.Карты)',
        labels={'count': 'Кол-во упоминаний', 'category': 'Категория жалобы'},
    )
    fig.update_layout(
        yaxis={'categoryorder': 'total ascending'},
        coloraxis_showscale=False,
        height=400,
    )
    fig.update_traces(textposition='outside')
    return fig


def make_complaints_by_rating(df_reviews: pd.DataFrame) -> go.Figure:
    """Категории жалоб с разбивкой по уровню рейтинга."""
    if df_reviews is None or df_reviews.empty or 'categories' not in df_reviews.columns:
        return go.Figure().update_layout(title='Данные отзывов недоступны')

    rows = []
    for _, r in df_reviews.iterrows():
        if pd.isna(r.get('categories')) or pd.isna(r.get('rating')):
            continue
        rating = float(r['rating'])
        if rating <= 2:
            tier = '1-2/5 (резко негативные)'
        elif rating == 3:
            tier = '3/5 (нейтральные)'
        elif rating == 4:
            tier = '4/5 (хорошие)'
        else:
            tier = '5/5 (отличные)'
        for cat in str(r['categories']).split(', '):
            rows.append({'category': cat, 'tier': tier})

    if not rows:
        return go.Figure().update_layout(title='Данные отзывов недоступны')

    agg = (
        pd.DataFrame(rows)
        .groupby(['category', 'tier']).size()
        .reset_index(name='count')
    )
    tier_order = ['1-2/5 (резко негативные)', '3/5 (нейтральные)',
                  '4/5 (хорошие)', '5/5 (отличные)']
    color_map = {
        '1-2/5 (резко негативные)': '#c0392b',
        '3/5 (нейтральные)':        '#f39c12',
        '4/5 (хорошие)':            '#27ae60',
        '5/5 (отличные)':           '#2ecc71',
    }
    fig = px.bar(
        agg, x='count', y='category', color='tier', orientation='h',
        category_orders={'tier': tier_order},
        color_discrete_map=color_map,
        title='Упоминания проблем по уровню рейтинга',
        labels={'count': 'Упоминаний', 'category': 'Категория', 'tier': 'Уровень рейтинга'},
    )
    fig.update_layout(
        yaxis={'categoryorder': 'total ascending'},
        height=420,
        legend={'orientation': 'h', 'y': -0.15},
    )
    return fig


def make_top_words_bar(top_words: pd.Series, n: int = 25) -> go.Figure:
    if top_words is None or top_words.empty:
        return go.Figure().update_layout(title='Нет данных для анализа слов')

    words_df = top_words.head(n).reset_index()
    words_df.columns = ['word', 'count']
    fig = px.bar(
        words_df,
        x='count', y='word', orientation='h',
        color='count', color_continuous_scale='Oranges', text='count',
        title=f'Топ-{n} слов в негативных отзывах (без стоп-слов)',
        labels={'count': 'Частота', 'word': 'Слово'},
    )
    fig.update_layout(
        yaxis={'categoryorder': 'total ascending'},
        coloraxis_showscale=False,
        height=600,
    )
    fig.update_traces(textposition='outside')
    return fig


def make_opportunity_scatter(opp_df: pd.DataFrame) -> go.Figure:
    score_col = 'full_score' if 'full_score' in opp_df.columns else 'opportunity_score'
    score_label = 'Full Score' if score_col == 'full_score' else 'Opportunity Score'
    fig = px.scatter(
        opp_df,
        x='clubs_count', y='population_k',
        size=score_col, color=score_col,
        color_continuous_scale='Viridis',
        text='district',
        title=f'Спрос vs Предложение (размер = {score_label})',
        labels={
            'clubs_count':  'Кол-во бильярдных клубов',
            'population_k': 'Население (тыс. чел.)',
            score_col:      score_label,
        },
    )
    fig.update_traces(textposition='top center')
    return fig


def make_map(df_clubs: pd.DataFrame, df_osm: pd.DataFrame) -> go.Figure:
    """Карта Москвы с маркерами 2GIS и OSM."""
    df_2gis = df_clubs[df_clubs['lat'].notna()][
        ['name', 'lat', 'lon', 'district', 'rating']
    ].copy()
    df_2gis['source'] = '2GIS'
    df_2gis['size'] = 10

    df_o = df_osm[df_osm['lat'].notna()][['name', 'lat', 'lon']].copy()
    df_o['district'] = (
        df_osm.loc[df_osm['lat'].notna(), 'district']
        if 'district' in df_osm.columns else ''
    )
    df_o['rating'] = pd.Series(dtype='float64')
    df_o['source'] = 'OSM'
    df_o['size'] = 8

    df_map = pd.concat([df_2gis, df_o], ignore_index=True)

    fig = px.scatter_map(
        df_map, lat='lat', lon='lon', hover_name='name',
        hover_data={'district': True, 'rating': True, 'source': True,
                    'lat': False, 'lon': False, 'size': False},
        color='source',
        color_discrete_map={'2GIS': '#2E86AB', 'OSM': '#E84855'},
        size='size', size_max=12, zoom=10,
        center={'lat': 55.76, 'lon': 37.62},
        title=f'Бильярдные клубы Москвы (2GIS: {len(df_2gis)}, OSM: {len(df_o)})',
    )
    fig.update_layout(
        map_style='open-street-map',
        legend_title_text='Источник',
        margin={'r': 0, 't': 40, 'l': 0, 'b': 0},
    )
    return fig
