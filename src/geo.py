"""Анализ спроса и предложения по округам: opportunity score."""

from typing import Optional

import numpy as np
import pandas as pd


class GeoAnalyzer:
    """Считает базовый и комплексный score по округам Москвы."""

    # Население округов в тысячах, Росстат на 1 января 2024.
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

    def __init__(self, clubs_df: pd.DataFrame):
        self.df = clubs_df.copy()

    def supply_by_district(self) -> pd.DataFrame:
        return self.df.groupby('district').size().reset_index(name='clubs_count')

    def opportunity_score(self) -> pd.DataFrame:
        """Население делим на количество клубов — чем больше, тем интереснее."""
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
        rent_df: Optional[pd.DataFrame] = None,
        entertainment_df: Optional[pd.DataFrame] = None,
    ) -> pd.DataFrame:
        """Взвешенный score из 4 факторов.

        35% население + 30% мало конкурентов + 20% досуговая активность +
        15% низкая аренда. Каждый фактор нормируется на свой максимум.
        """
        base = self.opportunity_score()

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
            # Данных по аренде нет — берём нейтральное значение, чтобы фактор не перекосил итог.
            base['norm_rent_inv'] = 0.5

        base['full_score'] = (
            base['norm_pop']       * 0.35 +
            base['norm_clubs_inv'] * 0.30 +
            base['norm_entertain'] * 0.20 +
            base['norm_rent_inv']  * 0.15
        ).mul(100).round(1)

        cols = ['district', 'population_k', 'clubs_count',
                'entertainment_count', 'avg_rent_sqm', 'full_score']
        return base[cols].sort_values('full_score', ascending=False)

    def stats_summary(self) -> dict:
        ratings = pd.to_numeric(self.df['rating'], errors='coerce').dropna().values
        if len(ratings) == 0:
            return {}
        return {
            'mean':   round(float(np.mean(ratings)), 2),
            'median': round(float(np.median(ratings)), 2),
            'std':    round(float(np.std(ratings)), 2),
            'p25':    round(float(np.percentile(ratings, 25)), 2),
            'p75':    round(float(np.percentile(ratings, 75)), 2),
            'min':    round(float(np.min(ratings)), 2),
            'max':    round(float(np.max(ratings)), 2),
        }
