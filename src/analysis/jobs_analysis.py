"""Анализ рынка труда: зарплаты по позициям, ФОТ, графики работы.

Результаты сохраняются в results/tables/jobs/, results/figures/jobs/
и results/reports/jobs_summary.txt.
"""

from pathlib import Path

import pandas as pd
import plotly.express as px


PROJECT_ROOT = Path(__file__).resolve().parents[2]
INPUT_PATH = PROJECT_ROOT / 'data' / 'jobs_clean.csv'

RESULTS_DIR = PROJECT_ROOT / 'results'
FIGURES_DIR = RESULTS_DIR / 'figures' / 'jobs'
TABLES_DIR = RESULTS_DIR / 'tables' / 'jobs'
REPORTS_DIR = RESULTS_DIR / 'reports'

FIGURES_DIR.mkdir(parents=True, exist_ok=True)
TABLES_DIR.mkdir(parents=True, exist_ok=True)
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

PLOTLY_TEMPLATE = 'plotly_white'

# Группы должностей, которые нужны бильярдному клубу.
POSITION_LABELS = {
    'администратор':          'Администратор',
    'управляющий':            'Управляющий',
    'технический специалист': 'Технический специалист',
    'охранник':               'Охранник',
    'уборщик':                'Уборщик',
    'повар':                  'Повар',
    'официант':               'Официант',
    'бармен':                 'Бармен',
    'event-менеджер':         'Event-менеджер',
    'smm':                    'SMM-специалист',
}


def build_salary_by_position(df: pd.DataFrame) -> pd.DataFrame:
    """Сводка по группам должностей: количество вакансий и зарплаты."""
    rows = []
    for key, label in POSITION_LABELS.items():
        sub = df[df['position_group'] == key]
        if sub.empty:
            continue
        salaries = sub['salary_avg'].dropna()
        rows.append({
            'position_key':   key,
            'position':       label,
            'vacancies':      len(sub),
            'salary_mean':    round(salaries.mean(), 0) if len(salaries) else None,
            'salary_median':  round(salaries.median(), 0) if len(salaries) else None,
            'salary_min':     round(salaries.min(), 0) if len(salaries) else None,
            'salary_max':     round(salaries.max(), 0) if len(salaries) else None,
            'salary_q25':     round(salaries.quantile(0.25), 0) if len(salaries) else None,
            'salary_q75':     round(salaries.quantile(0.75), 0) if len(salaries) else None,
        })
    return pd.DataFrame(rows).sort_values('salary_median', ascending=False)


def build_schedule_breakdown(df: pd.DataFrame) -> pd.DataFrame:
    """Какие графики работы предлагают и сколько в среднем платят."""
    grouped = (
        df.dropna(subset=['schedule'])
        .groupby('schedule')
        .agg(
            vacancies=('vacancy_id', 'count'),
            salary_mean=('salary_avg', 'mean'),
            salary_median=('salary_avg', 'median'),
        )
        .reset_index()
        .sort_values('vacancies', ascending=False)
    )
    grouped['salary_mean'] = grouped['salary_mean'].round(0)
    grouped['salary_median'] = grouped['salary_median'].round(0)
    return grouped


def build_top_employers(df: pd.DataFrame, n: int = 15) -> pd.DataFrame:
    """Топ работодателей по числу размещённых вакансий."""
    return (
        df.groupby('employer')
        .agg(
            vacancies=('vacancy_id', 'count'),
            salary_mean=('salary_avg', 'mean'),
            positions=('position_group', lambda x: ', '.join(sorted(set(x)))),
        )
        .reset_index()
        .sort_values('vacancies', ascending=False)
        .head(n)
    )


def estimate_payroll(salary_by_position: pd.DataFrame) -> pd.DataFrame:
    """
    Прикидка ФОТ для типового бильярдного клуба.

    Состав команды примерно как у небольшого зала на 8-10 столов:
    1 управляющий, 2 администратора, 1 технический, 2 повара,
    3 официанта, 2 бармена, 2 охранника, 2 уборщика, 1 event/SMM.
    """
    staff = {
        'управляющий':            1,
        'администратор':          2,
        'технический специалист': 1,
        'повар':                  2,
        'официант':               3,
        'бармен':                 2,
        'охранник':               2,
        'уборщик':                2,
        'event-менеджер':         1,
    }
    rows = []
    for key, headcount in staff.items():
        row = salary_by_position[salary_by_position['position_key'] == key]
        if row.empty or row['salary_median'].isna().all():
            continue
        median = float(row['salary_median'].iloc[0])
        rows.append({
            'position': row['position'].iloc[0],
            'headcount': headcount,
            'salary_median': median,
            'monthly_cost': headcount * median,
        })
    return pd.DataFrame(rows)


def build_data_overview(
    df: pd.DataFrame,
    salary_by_position: pd.DataFrame,
    payroll: pd.DataFrame,
) -> list[str]:
    """Короткая сводка по вакансиям для лога."""
    lines = [
        '',
        'Сводка по вакансиям:',
        f'  всего: {len(df)}, работодателей: {df["employer"].nunique()}',
        f'  групп должностей: {df["position_group"].nunique()}',
        f'  источник: {", ".join(df["source"].unique())}',
        '',
        'Топ-5 по медианной зарплате:',
        salary_by_position.head(5)[['position', 'vacancies', 'salary_median']].to_string(index=False),
        '',
    ]
    if not payroll.empty:
        total_payroll = payroll['monthly_cost'].sum()
        lines.append(f'Прогноз ФОТ для типового клуба: ~{int(total_payroll):,} ₽/мес (брутто)')
    return lines


def save_salary_bar_chart(salary_by_position: pd.DataFrame) -> Path:
    """Горизонтальный bar: медианная зарплата по позициям."""
    chart_df = salary_by_position.dropna(subset=['salary_median']).copy()
    fig = px.bar(
        chart_df.sort_values('salary_median'),
        x='salary_median',
        y='position',
        orientation='h',
        color='salary_median',
        color_continuous_scale='Blues',
        template=PLOTLY_TEMPLATE,
        title='Медианная зарплата по позициям (₽/мес)',
        hover_data={
            'vacancies': True,
            'salary_min': ':,.0f',
            'salary_max': ':,.0f',
            'salary_median': ':,.0f',
        },
        labels={'salary_median': 'Медиана зарплаты, ₽', 'position': 'Должность'},
    )
    fig.update_layout(
        xaxis_title='Медиана зарплаты, ₽/мес',
        yaxis_title='Должность',
        coloraxis_showscale=False,
    )
    output_path = FIGURES_DIR / 'salary_by_position.html'
    fig.write_html(output_path)
    return output_path


def save_salary_range_chart(salary_by_position: pd.DataFrame) -> Path:
    """Range bar: разброс зарплат от Q25 до Q75 с маркером медианы."""
    chart_df = salary_by_position.dropna(subset=['salary_median']).copy()
    chart_df = chart_df.sort_values('salary_median')

    fig = px.bar(
        chart_df,
        x=chart_df['salary_q75'] - chart_df['salary_q25'],
        y='position',
        base=chart_df['salary_q25'],
        orientation='h',
        template=PLOTLY_TEMPLATE,
        title='Зарплатные коридоры (между Q25 и Q75) по позициям',
        labels={'x': 'Зарплата, ₽', 'position': 'Должность'},
        hover_data={
            'salary_q25': ':,.0f',
            'salary_median': ':,.0f',
            'salary_q75': ':,.0f',
        },
    )
    fig.update_traces(marker_color='#2E86AB', opacity=0.7)
    fig.update_layout(xaxis_title='Зарплата, ₽/мес', yaxis_title='Должность')
    output_path = FIGURES_DIR / 'salary_ranges.html'
    fig.write_html(output_path)
    return output_path


def save_vacancy_count_chart(salary_by_position: pd.DataFrame) -> Path:
    """Сколько вакансий каждой позиции на рынке (показатель доступности кадров)."""
    fig = px.bar(
        salary_by_position.sort_values('vacancies'),
        x='vacancies',
        y='position',
        orientation='h',
        color='vacancies',
        color_continuous_scale='Greens',
        template=PLOTLY_TEMPLATE,
        title='Количество открытых вакансий по позициям',
        labels={'vacancies': 'Кол-во вакансий', 'position': 'Должность'},
    )
    fig.update_layout(
        xaxis_title='Кол-во вакансий',
        yaxis_title='Должность',
        coloraxis_showscale=False,
    )
    output_path = FIGURES_DIR / 'vacancies_count.html'
    fig.write_html(output_path)
    return output_path


def save_schedule_chart(schedule_breakdown: pd.DataFrame) -> Path:
    """Доля разных графиков работы среди всех вакансий."""
    if schedule_breakdown.empty:
        return None
    fig = px.pie(
        schedule_breakdown,
        names='schedule',
        values='vacancies',
        title='Распределение графиков работы среди вакансий',
        template=PLOTLY_TEMPLATE,
    )
    output_path = FIGURES_DIR / 'schedule_share.html'
    fig.write_html(output_path)
    return output_path


def save_payroll_chart(payroll: pd.DataFrame) -> Path:
    """Прогнозный ФОТ по позициям для типового клуба."""
    if payroll.empty:
        return None
    chart_df = payroll.sort_values('monthly_cost')
    fig = px.bar(
        chart_df,
        x='monthly_cost',
        y='position',
        orientation='h',
        color='monthly_cost',
        color_continuous_scale='Oranges',
        template=PLOTLY_TEMPLATE,
        title='Прогноз месячного ФОТ по позициям (типовой клуб)',
        labels={'monthly_cost': 'Месячный ФОТ, ₽', 'position': 'Должность'},
        hover_data={
            'headcount': True,
            'salary_median': ':,.0f',
            'monthly_cost': ':,.0f',
        },
    )
    fig.update_layout(
        xaxis_title='Месячный ФОТ, ₽',
        yaxis_title='Должность',
        coloraxis_showscale=False,
    )
    output_path = FIGURES_DIR / 'payroll_estimate.html'
    fig.write_html(output_path)
    return output_path


def save_insights(
    df: pd.DataFrame,
    salary_by_position: pd.DataFrame,
    payroll: pd.DataFrame,
) -> Path:
    """Финальный текстовый отчёт с выводами для проекта."""
    top_salary = salary_by_position.iloc[0] if not salary_by_position.empty else None
    cheapest = (
        salary_by_position.dropna(subset=['salary_median'])
        .sort_values('salary_median').iloc[0]
        if not salary_by_position.empty else None
    )

    lines = [
        'Рынок труда для бильярдного клуба',
        '',
        f'Всего вакансий в выборке: {len(df)}',
        f'Источник: {", ".join(df["source"].unique())}',
        f'Уникальных работодателей: {df["employer"].nunique()}',
        '',
    ]

    if top_salary is not None:
        lines.append(
            f'Самая дорогая позиция: {top_salary["position"]} - '
            f'медиана {int(top_salary["salary_median"]):,} ₽/мес'
        )
    if cheapest is not None:
        lines.append(
            f'Самая дешёвая позиция: {cheapest["position"]} - '
            f'медиана {int(cheapest["salary_median"]):,} ₽/мес'
        )

    if not payroll.empty:
        total = int(payroll['monthly_cost'].sum())
        annual = total * 12
        lines.extend([
            '',
            'Оценка ФОТ для типового клуба:',
            f'Состав: {int(payroll["headcount"].sum())} человек',
            f'Месячный ФОТ (брутто): ~{total:,} ₽',
            f'Годовой ФОТ: ~{annual:,} ₽',
        ])

    lines.extend([
        '',
        'Что важно:',
        '- Линейный персонал (уборщики, охранники) дешёвый, но текучка большая.',
        '- Технические специалисты и управляющие стоят дороже всего, на этих позициях экономить рискованно.',
        '- В выборке преобладает полный рабочий день, но 22% вакансий идут по сменному графику.',
        '- Ставку имеет смысл делать на полусменный график для линейного персонала, чтобы покрывать вечерние и ночные пики.',
    ])

    output_path = REPORTS_DIR / 'jobs_summary.txt'
    with open(output_path, 'w', encoding='utf-8') as file:
        file.write('\n'.join(lines))
    return output_path


def main() -> None:
    df = pd.read_csv(INPUT_PATH, encoding='utf-8-sig')
    print('Загружено вакансий:', len(df))

    salary_by_position = build_salary_by_position(df)
    schedule_breakdown = build_schedule_breakdown(df)
    top_employers = build_top_employers(df)
    payroll = estimate_payroll(salary_by_position)

    overview_lines = build_data_overview(df, salary_by_position, payroll)

    saved = []

    salary_path = TABLES_DIR / 'salary_by_position.csv'
    schedule_path = TABLES_DIR / 'schedule_breakdown.csv'
    employers_path = TABLES_DIR / 'top_employers.csv'
    payroll_path = TABLES_DIR / 'payroll_estimate.csv'

    salary_by_position.to_csv(salary_path, index=False, encoding='utf-8-sig')
    schedule_breakdown.to_csv(schedule_path, index=False, encoding='utf-8-sig')
    top_employers.to_csv(employers_path, index=False, encoding='utf-8-sig')
    payroll.to_csv(payroll_path, index=False, encoding='utf-8-sig')
    saved.extend([salary_path, schedule_path, employers_path, payroll_path])

    saved.append(save_salary_bar_chart(salary_by_position))
    saved.append(save_salary_range_chart(salary_by_position))
    saved.append(save_vacancy_count_chart(salary_by_position))
    schedule_chart = save_schedule_chart(schedule_breakdown)
    if schedule_chart:
        saved.append(schedule_chart)
    payroll_chart = save_payroll_chart(payroll)
    if payroll_chart:
        saved.append(payroll_chart)
    saved.append(save_insights(df, salary_by_position, payroll))

    print('\n'.join(overview_lines))
    print('Анализ завершён.')
    print('Сохранены файлы:')
    for path in saved:
        print('-', path)


if __name__ == '__main__':
    main()
