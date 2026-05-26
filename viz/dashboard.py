"""Сборка Dash-приложения со всеми вкладками."""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from dash import Dash, Input, Output, dash_table, dcc, html

from src.zoon import ZoonReviewScraper
from . import figures
from .recommendations import build_recommendations_layout


def make_app(
    df_clubs: pd.DataFrame,
    df_osm: pd.DataFrame,
    df_rent: pd.DataFrame,
    df_zoon: pd.DataFrame,
    df_reviews: pd.DataFrame,
    opp_df: pd.DataFrame,
    full_opp_df: pd.DataFrame,
) -> Dash:
    app = Dash(__name__)

    top10 = figures.make_top10_table(df_clubs)
    top10_reset = top10.reset_index().rename(columns={'index': '#'})

    fig_bar     = figures.make_district_bar(df_clubs)
    fig_hist    = figures.make_rating_hist(df_clubs)
    fig_rent    = figures.make_rent_bar(df_rent)
    fig_zoon    = figures.make_zoon_stacked_bar(df_zoon)
    fig_scatter = figures.make_opportunity_scatter(full_opp_df)
    fig_complaints           = figures.make_complaints_bar(df_reviews)
    fig_complaints_by_rating = figures.make_complaints_by_rating(df_reviews)

    if df_reviews is not None and not df_reviews.empty and 'text' in df_reviews.columns:
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

    app.layout = html.Div([
        html.H1('Бильярдные клубы Москвы - где открывать «Луzу и Шары»',
                style={'textAlign': 'center', 'fontFamily': 'Arial'}),

        dcc.Tabs(id='main-tabs', value='tab-map', children=[
            dcc.Tab(label='Карта', value='tab-map', children=[
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
                              'padding': '12px 20px', 'background': '#f5f5f5',
                              'borderBottom': '1px solid #ddd'}),
                    dcc.Graph(
                        id='map-graph',
                        style={'height': '580px', 'width': '100%'},
                        config={'responsive': True},
                        responsive=True,
                    ),
                    html.Div(id='map-stats',
                             style={'padding': '8px 20px', 'color': '#555', 'fontSize': '13px'}),
                ])
            ]),

            dcc.Tab(label='Конкуренты', children=[
                html.Div([
                    dcc.Graph(figure=fig_bar),
                    dcc.Graph(figure=fig_hist),
                    html.H3('Десять самых высоко оценённых клубов',
                            style={'fontFamily': 'Arial', 'marginLeft': '20px'}),
                    dash_table.DataTable(
                        data=top10_reset.to_dict('records'),
                        columns=[{'name': c, 'id': c} for c in top10_reset.columns],
                        style_cell={'fontFamily': 'Arial', 'textAlign': 'left', 'padding': '6px'},
                        style_header={'backgroundColor': '#2E86AB', 'color': 'white',
                                      'fontWeight': 'bold'},
                        style_data_conditional=[{'if': {'row_index': 'odd'},
                                                 'backgroundColor': '#f9f9f9'}],
                        page_size=10, style_table={'margin': '0 20px'},
                    ),
                ])
            ]),

            dcc.Tab(label='Аренда и досуг', children=[
                html.Div([
                    dcc.Graph(figure=fig_rent),
                    dcc.Graph(figure=fig_zoon),
                ])
            ]),

            dcc.Tab(label='Отзывы', children=[
                html.Div([
                    dcc.Graph(figure=fig_complaints),
                    dcc.Graph(figure=fig_complaints_by_rating),
                    dcc.Graph(figure=fig_words),
                    html.H3('Что пишут в отзывах',
                            style={'fontFamily': 'Arial', 'marginLeft': '20px'}),
                    dash_table.DataTable(
                        data=reviews_tbl.to_dict('records'),
                        columns=[{'name': c, 'id': c} for c in reviews_tbl.columns],
                        style_cell={'fontFamily': 'Arial', 'textAlign': 'left',
                                    'padding': '6px', 'whiteSpace': 'normal', 'maxWidth': '400px'},
                        style_header={'backgroundColor': '#E84855', 'color': 'white',
                                      'fontWeight': 'bold'},
                        style_data_conditional=[{'if': {'row_index': 'odd'},
                                                 'backgroundColor': '#fdf2f2'}],
                        page_size=15, style_table={'margin': '0 20px'},
                        filter_action='native', sort_action='native',
                    ),
                ])
            ]),

            dcc.Tab(label='Где открывать', children=[
                html.Div([
                    dcc.Graph(figure=fig_scatter),
                    html.H3('Округа по совокупному скору',
                            style={'fontFamily': 'Arial', 'marginLeft': '20px'}),
                    dash_table.DataTable(
                        data=full_opp_df.round(1).to_dict('records'),
                        columns=[{'name': c, 'id': c} for c in full_opp_df.columns],
                        style_cell={'fontFamily': 'Arial', 'textAlign': 'left', 'padding': '6px'},
                        style_header={'backgroundColor': '#A23B72', 'color': 'white',
                                      'fontWeight': 'bold'},
                        style_data_conditional=[{'if': {'row_index': 'odd'},
                                                 'backgroundColor': '#f9f9f9'}],
                        sort_action='native', style_table={'margin': '0 20px'},
                    ),
                ])
            ]),

            dcc.Tab(label='План действий', children=[
                build_recommendations_layout(
                    df_clubs=df_clubs,
                    df_rent=df_rent,
                    df_reviews=df_reviews,
                    full_opp_df=full_opp_df,
                ),
            ]),
        ])
    ], style={'fontFamily': 'Arial', 'maxWidth': '1200px', 'margin': '0 auto'})

    # Подписываемся на main-tabs, чтобы карта пересчитала размеры при возврате
    # на вкладку - иначе scatter_map отрисовывается с нулевым размером.
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
