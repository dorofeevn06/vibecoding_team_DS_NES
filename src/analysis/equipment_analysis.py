"""Анализ цен на оборудование: категории, сегменты, стоимость стартового комплекта.

Результаты сохраняются в results/tables/equipment/, results/figures/equipment/
и results/reports/equipment_summary.txt.
"""

from pathlib import Path

import pandas as pd
import plotly.express as px


PROJECT_ROOT = Path(__file__).resolve().parents[2]
INPUT_PATH = PROJECT_ROOT / 'data' / 'equipment_clean.csv'

RESULTS_DIR = PROJECT_ROOT / 'results'
FIGURES_DIR = RESULTS_DIR / 'figures' / 'equipment'
TABLES_DIR = RESULTS_DIR / 'tables' / 'equipment'
REPORTS_DIR = RESULTS_DIR / 'reports'

FIGURES_DIR.mkdir(parents=True, exist_ok=True)
TABLES_DIR.mkdir(parents=True, exist_ok=True)
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

PLOTLY_TEMPLATE = 'plotly_white'

SEGMENT_LABELS = {
    'budget':  'Бюджетный',
    'middle':  'Средний',
    'premium': 'Премиум',
}

# Что нужно купить для типового зала на 8 столов.
STARTER_KIT = {
    'Бильярдные столы':     8,
    'Сукно':                8,    # запас на замену
    'Кии':                  32,   # 4 кия на стол
    'Шары':                 8,    # набор шаров на стол
    'Аксессуары для кия':   16,   # мел, фишки, чашки
    'Светильники':          8,
}


def build_category_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Цены и количество товаров по каждой категории."""
    grouped = (
        df.groupby('category_ru')
        .agg(
            products=('product_name', 'count'),
            price_min=('price', 'min'),
            price_max=('price', 'max'),
            price_mean=('price', 'mean'),
            price_median=('price', 'median'),
        )
        .reset_index()
        .rename(columns={'category_ru': 'category'})
    )
    grouped['price_mean'] = grouped['price_mean'].round(0)
    grouped['price_median'] = grouped['price_median'].round(0)
    return grouped.sort_values('price_median', ascending=False)


def build_segment_breakdown(df: pd.DataFrame) -> pd.DataFrame:
    """Сводка по ценовым сегментам внутри каждой категории."""
    rows = []
    for category in df['category_ru'].unique():
        cat_df = df[df['category_ru'] == category]
        for segment in ('budget', 'middle', 'premium'):
            seg_df = cat_df[cat_df['segment'] == segment]
            if seg_df.empty:
                continue
            rows.append({
                'category':       category,
                'segment':        segment,
                'segment_label':  SEGMENT_LABELS[segment],
                'products':       len(seg_df),
                'price_min':      seg_df['price'].min(),
                'price_max':      seg_df['price'].max(),
                'price_median':   round(seg_df['price'].median(), 0),
            })
    return pd.DataFrame(rows)


def build_starter_kit_cost(df: pd.DataFrame) -> pd.DataFrame:
    """Стоимость стартового комплекта в трёх ценовых сегментах."""
    rows = []
    for category, qty in STARTER_KIT.items():
        cat_df = df[df['category_ru'] == category]
        if cat_df.empty:
            continue
        for segment in ('budget', 'middle', 'premium'):
            seg_df = cat_df[cat_df['segment'] == segment]
            if seg_df.empty:
                continue
            unit_price = float(seg_df['price'].median())
            rows.append({
                'category':      category,
                'segment':       segment,
                'segment_label': SEGMENT_LABELS[segment],
                'quantity':      qty,
                'unit_median':   round(unit_price, 0),
                'subtotal':      round(qty * unit_price, 0),
            })
    return pd.DataFrame(rows)


def build_top_premium_items(df: pd.DataFrame, n: int = 20) -> pd.DataFrame:
    """Самые дорогие позиции - для понимания потолка."""
    return (
        df.sort_values('price', ascending=False)
        .head(n)[['product_name', 'category_ru', 'segment', 'price', 'product_url']]
    )


def build_data_overview(
    df: pd.DataFrame,
    category_summary: pd.DataFrame,
    starter_kit: pd.DataFrame,
) -> list[str]:
    lines = [
        '',
        'Сводка по оборудованию:',
        f'  позиций: {len(df)}, категорий: {df["category_ru"].nunique()}',
        f'  магазин: {", ".join(df["store"].unique())}',
        '',
        'Топ-5 по медианной цене:',
        category_summary.head(5)[['category', 'products', 'price_median']].to_string(index=False),
        '',
    ]
    if not starter_kit.empty:
        totals = starter_kit.groupby('segment_label')['subtotal'].sum().sort_values()
        lines.append('Стоимость стартового комплекта:')
        for label, total in totals.items():
            lines.append(f'  {label}: {int(total):,} ₽')
    return lines


def save_median_price_chart(category_summary: pd.DataFrame) -> Path:
    fig = px.bar(
        category_summary.sort_values('price_median'),
        x='price_median',
        y='category',
        orientation='h',
        color='price_median',
        color_continuous_scale='Blues',
        template=PLOTLY_TEMPLATE,
        title='Медианная цена по категориям оборудования',
        labels={'price_median': 'Медианная цена, ₽', 'category': 'Категория'},
        hover_data={
            'products': True,
            'price_min': ':,.0f',
            'price_max': ':,.0f',
            'price_median': ':,.0f',
        },
    )
    fig.update_layout(
        xaxis_title='Медианная цена, ₽',
        yaxis_title='Категория',
        coloraxis_showscale=False,
    )
    output_path = FIGURES_DIR / 'median_price_by_category.html'
    fig.write_html(output_path)
    return output_path


def save_segment_share_chart(df: pd.DataFrame) -> Path:
    """Доля бюджетного / среднего / премиум сегментов по категориям."""
    agg = (
        df.groupby(['category_ru', 'segment']).size().reset_index(name='count')
    )
    agg['segment_label'] = agg['segment'].map(SEGMENT_LABELS)
    fig = px.bar(
        agg,
        x='category_ru',
        y='count',
        color='segment_label',
        barmode='stack',
        template=PLOTLY_TEMPLATE,
        title='Распределение товаров по ценовым сегментам внутри категорий',
        labels={'category_ru': 'Категория', 'count': 'Кол-во товаров',
                'segment_label': 'Сегмент'},
        category_orders={'segment_label': ['Бюджетный', 'Средний', 'Премиум']},
    )
    output_path = FIGURES_DIR / 'segments_by_category.html'
    fig.write_html(output_path)
    return output_path


def save_starter_kit_chart(starter_kit: pd.DataFrame) -> Path:
    if starter_kit.empty:
        return None
    totals = (
        starter_kit.groupby('segment_label')['subtotal'].sum()
        .reset_index()
        .sort_values('subtotal')
    )
    fig = px.bar(
        totals,
        x='subtotal',
        y='segment_label',
        orientation='h',
        color='subtotal',
        color_continuous_scale='Oranges',
        template=PLOTLY_TEMPLATE,
        title='Стоимость стартового комплекта в зависимости от сегмента',
        labels={'subtotal': 'Стоимость, ₽', 'segment_label': 'Сегмент'},
    )
    fig.update_layout(
        xaxis_title='Стоимость, ₽',
        yaxis_title='Сегмент',
        coloraxis_showscale=False,
    )
    output_path = FIGURES_DIR / 'starter_kit_cost.html'
    fig.write_html(output_path)
    return output_path


def save_price_box_chart(df: pd.DataFrame) -> Path:
    """Box plot цен по категориям - сразу видно разброс и выбросы."""
    fig = px.box(
        df,
        x='category_ru',
        y='price',
        color='segment',
        template=PLOTLY_TEMPLATE,
        title='Разброс цен по категориям и сегментам',
        labels={'category_ru': 'Категория', 'price': 'Цена, ₽',
                'segment': 'Сегмент'},
        log_y=True,
    )
    output_path = FIGURES_DIR / 'price_distribution.html'
    fig.write_html(output_path)
    return output_path


def save_insights(
    df: pd.DataFrame,
    category_summary: pd.DataFrame,
    starter_kit: pd.DataFrame,
) -> Path:
    most_expensive = category_summary.iloc[0] if not category_summary.empty else None
    cheapest = category_summary.iloc[-1] if not category_summary.empty else None

    lines = [
        'Цены на оборудование',
        '',
        f'Всего товарных позиций: {len(df)}',
        f'Магазин: {", ".join(df["store"].unique())}',
        f'Категорий: {df["category_ru"].nunique()}',
        '',
    ]

    if most_expensive is not None:
        lines.append(
            f'Самая дорогая категория по медиане: {most_expensive["category"]} - '
            f'{int(most_expensive["price_median"]):,} ₽'
        )
    if cheapest is not None and cheapest['category'] != most_expensive['category']:
        lines.append(
            f'Самая дешёвая категория по медиане: {cheapest["category"]} - '
            f'{int(cheapest["price_median"]):,} ₽'
        )

    if not starter_kit.empty:
        totals = starter_kit.groupby('segment_label')['subtotal'].sum()
        lines.extend([
            '',
            'Стоимость стартового комплекта (8 столов с инвентарём):',
        ])
        for label in ('Бюджетный', 'Средний', 'Премиум'):
            if label in totals.index:
                lines.append(f'- {label}: {int(totals[label]):,} ₽')

        if 'Средний' in totals.index:
            mid_total = int(totals['Средний'])
            lines.extend([
                '',
                f'Рекомендуемый базовый бюджет на старт: ~{mid_total:,} ₽',
                '(средний сегмент - оптимум по соотношению качество/цена для нишевого клуба)',
            ])

    lines.extend([
        '',
        'Что важно:',
        '- Основная статья расходов - столы и кии (~60-70% бюджета на оборудование).',
        '- Бюджетный сегмент годится для подсобки и тестовых столов, но не для основного зала.',
        '- На сукне экономить нельзя: его меняют чаще всего, разница в качестве заметна сразу.',
        '- Премиум-столы (Brunswick, Aramith) оправданы только для турнирных позиций - 1-2 на зал.',
    ])

    output_path = REPORTS_DIR / 'equipment_summary.txt'
    with open(output_path, 'w', encoding='utf-8') as file:
        file.write('\n'.join(lines))
    return output_path


def main() -> None:
    df = pd.read_csv(INPUT_PATH, encoding='utf-8-sig')
    print('Загружено позиций:', len(df))

    category_summary = build_category_summary(df)
    segment_breakdown = build_segment_breakdown(df)
    starter_kit = build_starter_kit_cost(df)
    top_premium = build_top_premium_items(df)

    overview = build_data_overview(df, category_summary, starter_kit)

    saved = []

    cat_path = TABLES_DIR / 'category_summary.csv'
    seg_path = TABLES_DIR / 'segment_breakdown.csv'
    kit_path = TABLES_DIR / 'starter_kit_cost.csv'
    top_path = TABLES_DIR / 'top_premium.csv'

    category_summary.to_csv(cat_path, index=False, encoding='utf-8-sig')
    segment_breakdown.to_csv(seg_path, index=False, encoding='utf-8-sig')
    starter_kit.to_csv(kit_path, index=False, encoding='utf-8-sig')
    top_premium.to_csv(top_path, index=False, encoding='utf-8-sig')
    saved.extend([cat_path, seg_path, kit_path, top_path])

    saved.append(save_median_price_chart(category_summary))
    saved.append(save_segment_share_chart(df))
    saved.append(save_price_box_chart(df))
    kit_chart = save_starter_kit_chart(starter_kit)
    if kit_chart:
        saved.append(kit_chart)
    saved.append(save_insights(df, category_summary, starter_kit))

    print('\n'.join(overview))
    print('Анализ завершён.')
    print('Сохранены файлы:')
    for path in saved:
        print('-', path)


if __name__ == '__main__':
    main()
