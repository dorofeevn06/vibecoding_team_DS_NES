"""Статистические тесты по собранным данным.

Здесь несколько гипотез, которые имеют смысл для проекта, и тесты,
которые на эти гипотезы отвечают.
"""

from typing import Optional

import numpy as np
import pandas as pd
from scipy import stats


def t_test_billiard_vs_other(df_reviews: pd.DataFrame) -> dict:
    """Гипотеза: бильярдные клубы оцениваются ниже, чем остальные досуговые.

    H0: средние рейтинги бильярдных и других досуговых заведений одинаковы.
    Тест: двухвыборочный t-test (Welch, разные дисперсии).
    """
    if 'is_billiard' not in df_reviews.columns:
        return {'error': 'no is_billiard column'}

    billiard = df_reviews[df_reviews['is_billiard']]['rating'].dropna()
    other    = df_reviews[~df_reviews['is_billiard']]['rating'].dropna()
    if len(billiard) < 10 or len(other) < 10:
        return {'error': 'too few samples'}

    stat, pvalue = stats.ttest_ind(billiard, other, equal_var=False)
    return {
        'hypothesis':     'Рейтинги бильярдных и других досуговых одинаковы',
        'n_billiard':     int(len(billiard)),
        'n_other':        int(len(other)),
        'mean_billiard':  round(float(billiard.mean()), 3),
        'mean_other':     round(float(other.mean()), 3),
        'std_billiard':   round(float(billiard.std()), 3),
        'std_other':      round(float(other.std()), 3),
        't_statistic':    round(float(stat), 3),
        'p_value':        float(pvalue),
        'reject_h0':      bool(pvalue < 0.05),
        'conclusion':     (
            'Различие значимое (p<0.05)' if pvalue < 0.05
            else 'Различие незначимое (p>=0.05)'
        ),
    }


def chi2_complaints_by_type(df_reviews: pd.DataFrame) -> dict:
    """Гипотеза: тип заведения связан с тем, на что жалуются.

    H0: распределение жалоб по категориям не зависит от того, бильярдное это
    место или просто досуговое.
    Тест: хи-квадрат на таблице сопряжённости (тип x категория).
    """
    if 'is_billiard' not in df_reviews.columns or 'categories' not in df_reviews.columns:
        return {'error': 'missing columns'}

    rows = []
    for _, r in df_reviews.iterrows():
        if pd.isna(r['categories']):
            continue
        for cat in str(r['categories']).split(', '):
            if cat and cat != 'Другое':
                rows.append({
                    'type': 'billiard' if r['is_billiard'] else 'other',
                    'category': cat,
                })
    if not rows:
        return {'error': 'no data'}

    table = pd.DataFrame(rows).groupby(['type', 'category']).size().unstack(fill_value=0)
    chi2, pvalue, dof, expected = stats.chi2_contingency(table)
    return {
        'hypothesis':   'Тип заведения и категория жалобы независимы',
        'contingency':  table.to_dict(),
        'chi2':         round(float(chi2), 3),
        'p_value':      float(pvalue),
        'dof':          int(dof),
        'reject_h0':    bool(pvalue < 0.05),
        'conclusion':   (
            'Связь значимая (p<0.05): жалобы зависят от типа места'
            if pvalue < 0.05 else 'Связь незначимая (p>=0.05)'
        ),
    }


def anova_rent_by_district(df_rent: pd.DataFrame) -> dict:
    """Гипотеза: средняя аренда не одинакова между округами Москвы.

    H0: средние цены аренды одинаковы во всех 9 округах.
    Тест: однофакторный ANOVA по price_per_sqm.
    """
    if df_rent is None or df_rent.empty or 'price_per_sqm' not in df_rent.columns:
        return {'error': 'no rent data'}

    valid = df_rent[
        df_rent['price_per_sqm'].notna() & (df_rent['district'] != 'Другое')
    ]
    if valid.empty:
        return {'error': 'no valid data'}

    groups = [
        valid[valid['district'] == d]['price_per_sqm'].values
        for d in valid['district'].unique()
        if len(valid[valid['district'] == d]) >= 2
    ]
    if len(groups) < 2:
        return {'error': 'need at least 2 groups'}

    stat, pvalue = stats.f_oneway(*groups)
    return {
        'hypothesis':   'Средняя аренда одинакова по округам',
        'n_groups':     len(groups),
        'n_total':      sum(len(g) for g in groups),
        'f_statistic':  round(float(stat), 3),
        'p_value':      float(pvalue),
        'reject_h0':    bool(pvalue < 0.05),
        'conclusion':   (
            'Различие значимое (p<0.05): аренда статистически отличается между округами'
            if pvalue < 0.05 else 'Различие незначимое (p>=0.05)'
        ),
    }


def corr_rating_vs_reviews(df_clubs: pd.DataFrame) -> dict:
    """Гипотеза: рейтинг клуба коррелирует с количеством отзывов.

    Тест: коэффициент Спирмена (ранговая корреляция, нечувствительна к выбросам).
    """
    df = df_clubs[['rating', 'reviews']].apply(pd.to_numeric, errors='coerce').dropna()
    if len(df) < 10:
        return {'error': 'too few samples'}

    rho, pvalue = stats.spearmanr(df['rating'], df['reviews'])
    return {
        'hypothesis':   'Между рейтингом и количеством отзывов нет связи',
        'n':            int(len(df)),
        'spearman_rho': round(float(rho), 3),
        'p_value':      float(pvalue),
        'reject_h0':    bool(pvalue < 0.05),
        'conclusion':   (
            f'Связь {"положительная" if rho > 0 else "отрицательная"} '
            f'и значимая (p<0.05)'
            if pvalue < 0.05 else 'Связь незначимая (p>=0.05)'
        ),
    }


def ci_starter_kit(starter_kit: pd.DataFrame, confidence: float = 0.95) -> dict:
    """Доверительные интервалы стоимости стартового комплекта по сегментам.

    Дискретно по каждому сегменту считаем total субтотал, и через bootstrap
    оцениваем 95% доверительный интервал.
    """
    if starter_kit is None or starter_kit.empty:
        return {'error': 'no data'}

    result = {}
    for segment in starter_kit['segment_label'].unique():
        seg = starter_kit[starter_kit['segment_label'] == segment]
        # Bootstrap по позициям внутри сегмента
        rng = np.random.default_rng(42)
        boot = []
        for _ in range(1000):
            sample = seg['subtotal'].sample(len(seg), replace=True, random_state=rng.integers(1e9))
            boot.append(sample.sum())
        boot = np.array(boot)
        alpha = (1 - confidence) / 2
        lo, hi = np.quantile(boot, [alpha, 1 - alpha])
        result[segment] = {
            'point_estimate': int(seg['subtotal'].sum()),
            'ci_low':         int(lo),
            'ci_high':        int(hi),
            'confidence':     confidence,
        }
    return result


def run_all_tests(
    df_clubs: pd.DataFrame,
    df_rent: pd.DataFrame,
    df_reviews: pd.DataFrame,
    starter_kit: pd.DataFrame,
) -> dict:
    """Запускает все тесты сразу и возвращает один словарь с результатами."""
    return {
        't_test_billiard_vs_other':    t_test_billiard_vs_other(df_reviews),
        'chi2_complaints_by_type':     chi2_complaints_by_type(df_reviews),
        'anova_rent_by_district':      anova_rent_by_district(df_rent),
        'corr_rating_vs_reviews':      corr_rating_vs_reviews(df_clubs),
        'ci_starter_kit_bootstrap':    ci_starter_kit(starter_kit),
    }
