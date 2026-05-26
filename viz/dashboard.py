"""Dash-дашборд проекта в логике бизнес-плана: от рынка к команде и закупкам.

Семь вкладок: рынок, аудитория, локация, сервис, команда, закупки, итоговый план.
В каждой вкладке наверху сводка с ключевыми цифрами, под графиками - выводы.
"""

from collections import Counter

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from dash import Dash, Input, Output, dash_table, dcc, html

from src.zoon import ZoonReviewScraper
from . import figures
from .recommendations import build_recommendations_layout


def _table(df: pd.DataFrame, header: str = '#2E86AB', page_size: int = 10):
    return dash_table.DataTable(
        data=df.to_dict('records'),
        columns=[{'name': c, 'id': c} for c in df.columns],
        style_cell={'fontFamily': 'Arial', 'textAlign': 'left', 'padding': '6px'},
        style_header={'backgroundColor': header, 'color': 'white', 'fontWeight': 'bold'},
        style_data_conditional=[{'if': {'row_index': 'odd'}, 'backgroundColor': '#f9f9f9'}],
        page_size=page_size,
        style_table={'margin': '0 20px'},
        sort_action='native',
    )


def _summary_strip(text):
    """Серая полоска сверху вкладки с ключевыми числами."""
    return html.Div(
        text,
        style={
            'padding': '14px 24px',
            'background': '#f5f5f5',
            'borderBottom': '1px solid #ddd',
            'fontSize': '15px',
            'lineHeight': '1.6',
        },
    )


def _conclusion(title, points):
    """Блок 'Что из этого следует' внизу вкладки."""
    return html.Div([
        html.H3(title, style={'fontFamily': 'Arial', 'marginTop': '20px',
                              'marginBottom': '8px'}),
        html.Ul(
            [html.Li(p, style={'marginBottom': '6px'}) for p in points],
            style={'fontSize': '14px', 'color': '#333'},
        ),
    ], style={'background': '#fafafa', 'padding': '16px 24px',
              'margin': '20px', 'borderLeft': '4px solid #2E86AB',
              'borderRadius': '4px'})


def make_app(
    df_clubs, df_osm, df_rent, df_zoon, df_reviews, opp_df, full_opp_df,
    df_audience, topic_summary, sentiment_by_topic, reviews_by_place,
    df_jobs, salary_by_position, schedule_breakdown, top_employers, payroll,
    df_equipment, category_summary, starter_kit, top_premium,
) -> Dash:
    app = Dash(__name__)

    # ── Подсчитываем ключевые числа ──────────────────────────────────────
    n_clubs = len(df_clubs)
    n_osm = len(df_osm)
    mean_rating = pd.to_numeric(df_clubs['rating'], errors='coerce').dropna().mean()
    top_district_by_count = df_clubs['district'].value_counts().index[0]

    rent_valid = df_rent[
        df_rent['price_per_sqm'].notna() & (df_rent['district'] != 'Другое')
    ] if not df_rent.empty else pd.DataFrame()
    rent_median_overall = rent_valid['price_per_sqm'].median() if not rent_valid.empty else 0
    rent_top3_districts = full_opp_df.head(3)['district'].tolist()
    rent_top3_median = (
        int(rent_valid[rent_valid['district'].isin(rent_top3_districts)]['price_per_sqm'].median())
        if not rent_valid.empty else 0
    )

    n_reviews = len(df_reviews)
    n_negative = int((df_reviews['rating'] <= 3).sum())
    n_positive_with_complaint = 0
    cat_counts_all: Counter = Counter()
    if 'categories' in df_reviews.columns:
        for cats in df_reviews['categories'].dropna():
            for c in cats.split(', '):
                if c != 'Другое':
                    cat_counts_all[c] += 1
        high = df_reviews[df_reviews['rating'] >= 4]
        for cats in high['categories'].dropna():
            if any(c != 'Другое' for c in cats.split(', ')):
                n_positive_with_complaint += 1
    top_complaint = cat_counts_all.most_common(1)[0][0] if cat_counts_all else '-'

    n_audience = len(df_audience)
    sentiment_counts = df_audience['sentiment'].value_counts().to_dict() if not df_audience.empty else {}

    total_payroll = int(payroll['monthly_cost'].sum()) if not payroll.empty else 0
    annual_payroll = total_payroll * 12
    n_employees = int(payroll['headcount'].sum()) if not payroll.empty else 0

    starter_totals = (
        starter_kit.groupby('segment_label')['subtotal'].sum().to_dict()
        if not starter_kit.empty else {}
    )
    starter_mid = int(starter_totals.get('Средний', 0))

    top3_text = ', '.join(rent_top3_districts)

    # ── Подготовка графиков ───────────────────────────────────────────────
    top10 = figures.make_top10_table(df_clubs)
    top10_reset = top10.reset_index().rename(columns={'index': '#'})

    fig_bar = figures.make_district_bar(df_clubs)
    fig_hist = figures.make_rating_hist(df_clubs)
    fig_rent = figures.make_rent_bar(df_rent)
    fig_zoon_stack = figures.make_zoon_stacked_bar(df_zoon)
    fig_scatter = figures.make_opportunity_scatter(full_opp_df)
    fig_complaints = figures.make_complaints_bar(df_reviews)
    fig_complaints_by_rating = figures.make_complaints_by_rating(df_reviews)
    fig_topic = figures.make_topic_frequency(topic_summary)
    fig_negative = figures.make_negative_topics(topic_summary)
    fig_sentiment = figures.make_sentiment_by_topic(sentiment_by_topic)
    fig_salary = figures.make_salary_by_position(salary_by_position)
    fig_ranges = figures.make_salary_ranges(salary_by_position)
    fig_vacancies = figures.make_vacancies_count(salary_by_position)
    fig_schedule = figures.make_schedule_pie(schedule_breakdown)
    fig_payroll = figures.make_payroll_estimate(payroll)
    fig_median = figures.make_median_price_by_category(category_summary)
    fig_segments = figures.make_segments_by_category(df_equipment)
    fig_box = figures.make_price_distribution(df_equipment)
    fig_kit = figures.make_starter_kit_cost(starter_kit)

    if not df_reviews.empty and 'text' in df_reviews.columns:
        top_words = ZoonReviewScraper.top_words(df_reviews['text'].tolist(), n=20)
        fig_words = figures.make_top_words_bar(top_words, n=20)
        reviews_tbl = df_reviews[['club', 'rating', 'categories', 'text']].copy()
        reviews_tbl['text'] = reviews_tbl['text'].str[:120] + '…'
    else:
        fig_words = go.Figure().update_layout(title='Нет отзывов')
        reviews_tbl = pd.DataFrame(columns=['club', 'rating', 'categories', 'text'])

    all_districts = sorted(set(
        list(df_clubs['district'].dropna().unique())
        + list(df_osm['district'].dropna().unique() if 'district' in df_osm.columns else [])
    ))
    all_districts = [d for d in all_districts if d not in ('', 'Другое')] + ['Другое']
    source_options = [{'label': '2GIS', 'value': '2GIS'}, {'label': 'OSM', 'value': 'OSM'}]

    # ── Layout ───────────────────────────────────────────────────────────
    app.layout = html.Div([
        html.H1('Бильярдные клубы Москвы - где открывать «Луzу и Шары»',
                style={'textAlign': 'center', 'fontFamily': 'Arial'}),

        dcc.Tabs(id='main-tabs', value='tab-market', children=[

            # 1. РЫНОК
            dcc.Tab(label='1. Рынок', value='tab-market', children=[
                _summary_strip(
                    f'На рынке {n_clubs} клубов в 2GIS плюс {n_osm} в OSM. '
                    f'Средний рейтинг {mean_rating:.2f}. '
                    f'Больше всего заведений в {top_district_by_count}.'
                ),

                html.Div([
                    html.Div([
                        html.Div([
                            html.Label('Округ:', style={'fontWeight': 'bold'}),
                            dcc.Dropdown(
                                id='map-district-filter',
                                options=[{'label': 'Все округа', 'value': 'ALL'}]
                                        + [{'label': d, 'value': d} for d in all_districts],
                                value='ALL', clearable=False, style={'width': '220px'},
                            ),
                        ], style={'marginRight': '30px'}),
                        html.Div([
                            html.Label('Источник:', style={'fontWeight': 'bold'}),
                            dcc.Checklist(
                                id='map-source-filter', options=source_options,
                                value=['2GIS', 'OSM'], inline=True,
                                style={'marginTop': '6px'},
                            ),
                        ]),
                    ], style={'display': 'flex', 'alignItems': 'flex-end',
                              'padding': '12px 20px', 'background': '#fafafa'}),
                    dcc.Graph(
                        id='map-graph',
                        style={'height': '580px', 'width': '100%'},
                        config={'responsive': True}, responsive=True,
                    ),
                    html.Div(id='map-stats',
                             style={'padding': '8px 20px', 'color': '#555', 'fontSize': '13px'}),
                ]),

                dcc.Graph(figure=fig_bar),
                dcc.Graph(figure=fig_hist),

                html.H3('Десять самых высоко оценённых клубов',
                        style={'fontFamily': 'Arial', 'marginLeft': '20px'}),
                _table(top10_reset, header='#2E86AB'),

                _conclusion('Что из этого следует', [
                    f'Рынок насыщенный: 200+ заведений, явного лидера нет (средний рейтинг {mean_rating:.2f}).',
                    'Чисто бильярдных клубов мало, большинство - смешанный формат (бар + бильярд). Есть свободная ниша.',
                    'Концентрация в ЦАО и ЮВАО - центр перегружен, лучше смотреть на периферию.',
                ]),
            ]),

            # 2. АУДИТОРИЯ
            dcc.Tab(label='2. Аудитория', children=[
                _summary_strip(
                    f'Проанализировано {n_audience:,} отзывов с Яндекс.Карт. '
                    f'Положительных: {sentiment_counts.get("positive", 0):,}, '
                    f'нейтральных: {sentiment_counts.get("neutral", 0):,}, '
                    f'негативных: {sentiment_counts.get("negative", 0):,}.'
                ),

                dcc.Graph(figure=fig_topic),
                dcc.Graph(figure=fig_sentiment),
                dcc.Graph(figure=fig_negative),

                html.H3('Заведения с наибольшим числом отзывов',
                        style={'fontFamily': 'Arial', 'marginLeft': '20px'}),
                _table(reviews_by_place.head(25).round(2), header='#2E86AB'),

                _conclusion('Кто наши клиенты и что им нужно', [
                    'Бильярдный клуб люди воспринимают как формат вечернего досуга, а не чисто спортивное место - атмосфера и интерьер важны не меньше столов.',
                    'Самые обсуждаемые темы: сервис, атмосфера, столы и оборудование. На этих трёх вещах будет складываться репутация.',
                    'Платежеспособная городская аудитория 25-40 лет: готовы платить за качество, но требовательны к деталям.',
                ]),
            ]),

            # 3. ЛОКАЦИЯ
            dcc.Tab(label='3. Локация', children=[
                _summary_strip(
                    f'Топ-3 округа по совокупному скору: {top3_text}. '
                    f'Медианная аренда в этих округах: {rent_top3_median:,} ₽/м²/мес '
                    f'против {int(rent_median_overall):,} ₽/м²/мес в среднем по выборке.'
                ),

                dcc.Graph(figure=fig_scatter),

                html.H3('Округа по совокупному скору',
                        style={'fontFamily': 'Arial', 'marginLeft': '20px'}),
                _table(full_opp_df.round(1), header='#A23B72'),

                dcc.Graph(figure=fig_rent),
                dcc.Graph(figure=fig_zoon_stack),

                _conclusion('Где открывать', [
                    f'Лучший баланс спроса и аренды - {rent_top3_districts[0] if rent_top3_districts else "-"}. '
                    'Спрос там есть, конкурентов мало, аренда заметно ниже центральной.',
                    'ЦАО не подходит для нишевого формата: аренда в разы дороже, конкурентов и так перебор.',
                    'Площадь под зал на 8-10 столов плюс бар - 250-350 м². При выбранной локации это '
                    f'обойдётся примерно в {rent_top3_median * 300 // 1000} тыс ₽/мес арендной платы.',
                ]),
            ]),

            # 4. СЕРВИС И УЛУЧШЕНИЯ
            dcc.Tab(label='4. Что улучшать', children=[
                _summary_strip(
                    f'Собрано {n_reviews:,} отзывов о клубах. '
                    f'Самая частая претензия: «{top_complaint}». '
                    f'В положительных отзывах (≥4/5) проблемы упоминают {n_positive_with_complaint:,} раз - '
                    'это то, что раздражает даже довольных гостей.'
                ),

                dcc.Graph(figure=fig_complaints),
                dcc.Graph(figure=fig_complaints_by_rating),
                dcc.Graph(figure=fig_words),

                html.H3('Что пишут в отзывах',
                        style={'fontFamily': 'Arial', 'marginLeft': '20px'}),
                _table(reviews_tbl, header='#E84855', page_size=15),

                # План действий внутри вкладки
                html.H3('План действий (генерируется из данных)',
                        style={'fontFamily': 'Arial', 'marginLeft': '20px', 'marginTop': '30px'}),
                build_recommendations_layout(
                    df_clubs=df_clubs, df_rent=df_rent,
                    df_reviews=df_reviews, full_opp_df=full_opp_df,
                ),

                _conclusion('Где можно обыграть конкурентов', [
                    f'Главная боль рынка - «{top_complaint}». Решить её - получить прямое преимущество.',
                    'Бронирование - проблема №1 даже у довольных клиентов. Нормальный онлайн-сервис c картой загруженности столов = плюс к лояльности.',
                    'На сукне и столах не экономить: это первое, на что жалуются в негативных отзывах.',
                ]),
            ]),

            # 5. КОМАНДА
            dcc.Tab(label='5. Команда', children=[
                _summary_strip(
                    f'Команда из {n_employees} человек. Месячный ФОТ ~{total_payroll:,} ₽, '
                    f'годовой ~{annual_payroll:,} ₽. '
                    f'Данные: {len(df_jobs)} вакансий с trudvsem.ru.'
                ),

                dcc.Graph(figure=fig_salary),
                dcc.Graph(figure=fig_ranges),
                dcc.Graph(figure=fig_payroll),
                dcc.Graph(figure=fig_vacancies),
                dcc.Graph(figure=fig_schedule),

                html.H3('Топ работодателей',
                        style={'fontFamily': 'Arial', 'marginLeft': '20px'}),
                _table(top_employers, header='#27ae60'),

                _conclusion('Что нужно знать про найм', [
                    f'На полный штат из {n_employees} человек уходит около {total_payroll:,} ₽ в месяц брутто.',
                    'Самые дорогие позиции - технический специалист и SMM. На них экономить не стоит, иначе пострадает оборудование и привлечение клиентов.',
                    'Линейный персонал (уборщики, охранники) - дешёвый, но текучка большая. Стоит закладывать бюджет на найм и обучение.',
                    'На рынке преобладает полный рабочий день, но 22% вакансий идут по сменам. Для бильярдной это правильный формат - вечерние и ночные пики.',
                ]),
            ]),

            # 6. ЗАКУПКИ
            dcc.Tab(label='6. Закупки', children=[
                _summary_strip(
                    f'Стартовый комплект на 8 столов: бюджетный - {int(starter_totals.get("Бюджетный", 0)):,} ₽, '
                    f'средний - {int(starter_totals.get("Средний", 0)):,} ₽, '
                    f'премиум - {int(starter_totals.get("Премиум", 0)):,} ₽. '
                    f'Каталог: {len(df_equipment):,} позиций.'
                ),

                dcc.Graph(figure=fig_median),
                dcc.Graph(figure=fig_segments),
                dcc.Graph(figure=fig_kit),
                dcc.Graph(figure=fig_box),

                html.H3('Самое дорогое в каталоге',
                        style={'fontFamily': 'Arial', 'marginLeft': '20px'}),
                _table(top_premium, header='#A23B72', page_size=20),

                _conclusion('Что закупать', [
                    f'Базовый бюджет ~{starter_mid:,} ₽ в среднем сегменте - оптимум по цене и качеству.',
                    'Основная статья расходов - столы и сукно (~60-70% бюджета). Здесь экономия дорого обходится по отзывам.',
                    'Премиум-столы (Brunswick, Aramith) - только 1-2 на зал под турниры. Основной зал в среднем сегменте.',
                    'Сукно меняется чаще остального - закладывайте регулярную замену каждые 2-3 месяца.',
                ]),
            ]),

            # 7. ИТОГОВЫЙ ПЛАН
            dcc.Tab(label='7. Итоговый план', children=[
                _summary_strip(
                    'Сводный бизнес-план из всех данных проекта.'
                ),

                html.Div([
                    html.H2('Что в итоге запускаем',
                            style={'fontFamily': 'Arial', 'marginBottom': '6px'}),
                    html.P(
                        'Нишевый бильярдный клуб формата «бильярд + бар + атмосфера», '
                        'на 8-10 столов, с приоритетом на качество столов, бронирование '
                        'и сервис. Ориентир - аудитория 25-40 лет, готовая платить '
                        'за качество вечернего досуга.',
                        style={'color': '#444', 'fontSize': '15px'},
                    ),
                ], style={'padding': '20px 24px', 'borderBottom': '1px solid #ddd'}),

                _conclusion('Локация', [
                    f'Округ: один из топ-3 по скору ({top3_text}). Не ЦАО.',
                    'Площадь: 250-350 м² (зал на 8-10 столов плюс бар).',
                    f'Аренда: около {rent_top3_median * 300 // 1000:,} тыс ₽/мес.',
                ]),

                _conclusion('Команда и ФОТ', [
                    f'Штат: {n_employees} человек (управляющий, администраторы, '
                    'технический, повара, официанты, бармены, охрана, уборка).',
                    f'Месячный ФОТ: {total_payroll:,} ₽ брутто.',
                    f'Годовой ФОТ: {annual_payroll:,} ₽.',
                ]),

                _conclusion('Стартовые закупки', [
                    f'Базовый бюджет на оборудование (средний сегмент): {starter_mid:,} ₽.',
                    'Турнирные столы Brunswick/Aramith - 1-2 на зал, остальные средний сегмент.',
                    'Запас сукна на регулярную замену.',
                ]),

                _conclusion('Приоритеты по сервису (из отзывов конкурентов)', [
                    f'Закрываем главную боль рынка - «{top_complaint}».',
                    'Онлайн-бронирование 24/7 с картой загруженности столов.',
                    'Сервис на уровне выше среднего по рынку - персонал, атмосфера, чистота.',
                ]),

                _conclusion('Целевые показатели первого года', [
                    f'Рейтинг в 2GIS: выйти на верхние 25% рынка (от {pd.to_numeric(df_clubs["rating"], errors="coerce").quantile(0.75):.1f}).',
                    'Загрузка столов в часы пик - не менее 80%.',
                    'Доля повторных гостей - 40%+.',
                ]),
            ]),

        ])
    ], style={'fontFamily': 'Arial', 'maxWidth': '1200px', 'margin': '0 auto'})

    @app.callback(
        Output('map-graph', 'figure'),
        Output('map-stats', 'children'),
        Input('map-district-filter', 'value'),
        Input('map-source-filter', 'value'),
        Input('main-tabs', 'value'),
    )
    def _update_map(selected_district, selected_sources, active_tab):
        df_2gis = df_clubs[df_clubs['lat'].notna()][
            ['name', 'lat', 'lon', 'district', 'rating', 'reviews']
        ].copy()
        df_2gis['source'] = '2GIS'
        df_2gis['size'] = 10

        if 'district' in df_osm.columns:
            df_osm_map = df_osm[df_osm['lat'].notna()][['name', 'lat', 'lon', 'district']].copy()
        else:
            df_osm_map = df_osm[df_osm['lat'].notna()][['name', 'lat', 'lon']].copy()
            df_osm_map['district'] = ''
        df_osm_map['rating'] = pd.Series(dtype='float64')
        df_osm_map['reviews'] = pd.Series(dtype='float64')
        df_osm_map['source'] = 'OSM'
        df_osm_map['size'] = 8

        df_all = pd.concat([df_2gis, df_osm_map], ignore_index=True)
        if selected_sources:
            df_all = df_all[df_all['source'].isin(selected_sources)]
        if selected_district and selected_district != 'ALL':
            df_all = df_all[df_all['district'] == selected_district]

        n_2gis = int((df_all['source'] == '2GIS').sum())
        n_osm = int((df_all['source'] == 'OSM').sum())

        fig = px.scatter_map(
            df_all, lat='lat', lon='lon', hover_name='name',
            hover_data={'district': True, 'rating': True, 'reviews': True,
                        'source': True, 'lat': False, 'lon': False, 'size': False},
            color='source',
            color_discrete_map={'2GIS': '#2E86AB', 'OSM': '#E84855'},
            size='size', size_max=12, zoom=10,
            center={'lat': 55.76, 'lon': 37.62},
            title=f'Бильярдные клубы Москвы - 2GIS: {n_2gis}, OSM: {n_osm}',
        )
        fig.update_layout(
            map_style='open-street-map',
            legend_title_text='Источник',
            margin={'r': 0, 't': 40, 'l': 0, 'b': 0},
            autosize=True,
            height=580,
        )
        avg_rating = df_all[df_all['source'] == '2GIS']['rating'].mean()
        stats_text = (
            f'На карте {len(df_all)} клубов - {n_2gis} из 2GIS, {n_osm} из OSM'
            + (f'. Средний рейтинг по 2GIS - {avg_rating:.2f}'
               if n_2gis > 0 and not pd.isna(avg_rating) else '')
        )
        return fig, stats_text

    return app
