"""GeoAnalyzer — географический анализ: спрос vs предложение по округам Москвы.

Население — Росстат, оценка на 1 января 2024 г. (https://77.rosstat.gov.ru).
"""
from __future__ import annotations

import numpy as np
import pandas as pd


class GeoAnalyzer:
    """Анализ спроса (население) и предложения (кол-во клубов) по округам.

    Возможности:
      - supply_by_district()       — кол-во клубов по округам
      - opportunity_score()        — базовый: население / клубы
      - full_opportunity_score()   — 4-факторный с учётом аренды и досуга
      - stats_summary()            — NumPy сводка по рейтингам
    """

    # Население округов в тысячах человек (Росстат, 1 января 2024)
    POPULATION: dict[str, int] = {
        'ЦАО':   774,
        'САО':  1218,
        'СВАО': 1456,
        'ВАО':  1509,
        'ЮВАО': 1516,
        'ЮАО':  1769,
        'ЮЗАО': 1436,
        'ЗАО':  1425,
        'СЗАО': 1040,
    }

    def __init__(self, clubs_df: pd.DataFrame) -> None:
        self.df = clubs_df.copy()

    def supply_by_district(self) -> pd.DataFrame:
        return self.df.groupby('district').size().reset_index(name='clubs_count')

    def opportunity_score(self) -> pd.DataFrame:
        """Базовый score: население / кол-во клубов (чем выше — тем интереснее)."""
        supply = self.supply_by_district()
        pop_df = pd.DataFrame(
            list(self.POPULATION.items()),
            columns=['district', 'population_k'],
        )
        merged = pop_df.merge(supply, on='district', how='left')
        merged['clubs_count'] = merged['clubs_count'].fillna(0).astype(int)
        merged['opportunity_score'] = (
            merged['population_k'] / merged['clubs_count'].replace(0, 0.5)
        ).round(1)
        return merged.sort_values('opportunity_score', ascending=False)

    def full_opportunity_score(
        self,
        rent_df: pd.DataFrame | None = None,
        entertainment_df: pd.DataFrame | None = None,
    ) -> pd.DataFrame:
        """Комплексный 4-факторный score (взвешенная сумма нормированных факторов).

        Формула:
          +35% население          — чем больше жителей, тем шире аудитория
          +30% мало конкурентов   — обратная плотность бильярдных
          +20% досуговая активность — плотность баров/боулингов/развлечений
          +15% низкая аренда      — обратная стоимость м²
        """
        base = self.opportunity_score()

        # Аренда
        if rent_df is not None and not rent_df.empty and 'price_per_sqm' in rent_df.columns:
            rent_agg = (
                rent_df[rent_df['price_per_sqm'].notna()]
                .groupby('district')['price_per_sqm']
                .median()
                .reset_index(name='avg_rent_sqm')
            )
            base = base.merge(rent_agg, on='district', how='left')
        else:
            base['avg_rent_sqm'] = None

        # Досуговая активность
        if entertainment_df is not None and not entertainment_df.empty:
            ent_cnt = (
                entertainment_df.groupby('district')
                .size()
                .reset_index(name='entertainment_count')
            )
            base = base.merge(ent_cnt, on='district', how='left')
            base['entertainment_count'] = base['entertainment_count'].fillna(0).astype(int)
        else:
            base['entertainment_count'] = 0

        # Нормировка
        base['norm_pop'] = base['population_k'] / base['population_k'].max()

        clubs_inv = 1 / base['clubs_count'].replace(0, 0.5)
        base['norm_clubs_inv'] = clubs_inv / clubs_inv.max()

        max_ent = base['entertainment_count'].max()
        base['norm_entertain'] = (
            base['entertainment_count'] / max_ent if max_ent > 0 else 0.0
        )

        if base['avg_rent_sqm'].notna().any():
            rent_fill = base['avg_rent_sqm'].median()
            base['avg_rent_sqm'] = base['avg_rent_sqm'].fillna(rent_fill)
            base['norm_rent_inv'] = 1 - base['avg_rent_sqm'] / base['avg_rent_sqm'].max()
        else:
            base['norm_rent_inv'] = 0.5  # нет данных — нейтральное значение

        base['full_score'] = (
            base['norm_pop']        * 0.35 +
            base['norm_clubs_inv']  * 0.30 +
            base['norm_entertain']  * 0.20 +
            base['norm_rent_inv']   * 0.15
        ).mul(100).round(1)

        cols = ['district', 'population_k', 'clubs_count',
                'entertainment_count', 'avg_rent_sqm', 'full_score']
        return base[cols].sort_values('full_score', ascending=False)

    def stats_summary(self) -> dict:
        """NumPy-сводка по рейтингам: mean, median, std, percentiles."""
        ratings = pd.to_numeric(self.df['rating'], errors='coerce').dropna().values
        if len(ratings) == 0:
            return {}
        return {
            'mean':   round(float(np.mean(ratings)),           2),
            'median': round(float(np.median(ratings)),         2),
            'std':    round(float(np.std(ratings)),            2),
            'p25':    round(float(np.percentile(ratings, 25)), 2),
            'p75':    round(float(np.percentile(ratings, 75)), 2),
            'min':    round(float(np.min(ratings)),            2),
            'max':    round(float(np.max(ratings)),            2),
        }
