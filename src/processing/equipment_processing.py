import os

import pandas as pd


class EquipmentProcessor:
    """
    Обработка сырых данных по оборудованию.

    Файл делает только processing:
    - загружает data/raw/equipment_raw.csv;
    - чистит названия, категории, ссылки и цены;
    - удаляет дубли;
    - добавляет русские названия категорий;
    - добавляет ценовой сегмент;
    - сохраняет data/processed/equipment_clean.csv.

    Анализ, смета и графики должны быть вынесены в отдельный файл.
    """

    CATEGORY_LABELS = {
        "tables": "Бильярдные столы",
        "cues": "Кии",
        "balls": "Шары",
        "cloth": "Сукно",
        "lighting": "Светильники",
        "game_sets": "Наборы для игры",
        "cue_accessories": "Аксессуары для кия",
    }

    def __init__(
        self,
        raw_path="data/raw/equipment_raw.csv",
        clean_path="data/processed/equipment_clean.csv",
    ):
        self.raw_path = raw_path
        self.clean_path = clean_path

    @staticmethod
    def define_segment(price):
        if pd.isna(price):
            return "unknown"
        if price <= 15000:
            return "budget"
        if price <= 80000:
            return "middle"
        return "premium"

    def load_raw_data(self):
        df = pd.read_csv(self.raw_path)

        print("\nЗагружены сырые данные по оборудованию.")
        print(f"Файл: {self.raw_path}")
        print(f"Строк: {len(df)}")
        print(f"Столбцы: {list(df.columns)}")

        return df

    def clean_data(self, df):
        df = df.copy()

        required_columns = [
            "product_name",
            "category",
            "price",
            "store",
            "product_url",
            "source_url",
            "parsed_at",
        ]

        missing_columns = [column for column in required_columns if column not in df.columns]
        if missing_columns:
            raise ValueError(f"В сыром файле не хватает столбцов: {missing_columns}")

        df["product_name"] = df["product_name"].astype(str).str.strip()
        df["category"] = df["category"].astype(str).str.strip()
        df["store"] = df["store"].fillna("").astype(str).str.strip()
        df["product_url"] = df["product_url"].fillna("").astype(str).str.strip()
        df["source_url"] = df["source_url"].fillna("").astype(str).str.strip()
        df["parsed_at"] = df["parsed_at"].fillna("").astype(str).str.strip()

        df["price"] = pd.to_numeric(df["price"], errors="coerce")
        df = df.dropna(subset=["product_name", "category", "price"])
        df = df[df["product_name"] != ""]
        df = df[df["category"] != ""]
        df = df[df["price"] > 0]

        df = df.drop_duplicates(
            subset=["product_name", "category", "price", "store"],
            keep="first",
        )

        df["category_ru"] = df["category"].map(self.CATEGORY_LABELS).fillna(df["category"])
        df["segment"] = df["price"].apply(self.define_segment)

        df = df[
            [
                "product_name",
                "category",
                "category_ru",
                "segment",
                "price",
                "store",
                "product_url",
                "source_url",
                "parsed_at",
            ]
        ]

        df = df.sort_values(["category", "price", "product_name"]).reset_index(drop=True)

        return df

    def save_clean_data(self, df):
        os.makedirs(os.path.dirname(self.clean_path), exist_ok=True)
        df.to_csv(self.clean_path, index=False, encoding="utf-8-sig")

        print("\nОчищенные данные сохранены.")
        print(f"Файл: {self.clean_path}")
        print(f"Строк после очистки: {len(df)}")

    def print_processing_summary(self, raw_df, clean_df):
        removed_rows = len(raw_df) - len(clean_df)

        print("\nКраткая сводка processing:")
        print(f"Сырых строк: {len(raw_df)}")
        print(f"Очищенных строк: {len(clean_df)}")
        print(f"Удалено строк: {removed_rows}")
        print("\nКоличество товаров по категориям:")
        print(clean_df["category"].value_counts())
        print("\nКоличество товаров по ценовым сегментам:")
        print(clean_df["segment"].value_counts())

    def run(self):
        raw_df = self.load_raw_data()
        clean_df = self.clean_data(raw_df)
        self.save_clean_data(clean_df)
        self.print_processing_summary(raw_df, clean_df)

        return clean_df


if __name__ == "__main__":
    processor = EquipmentProcessor(
        raw_path="data/raw/equipment_raw.csv",
        clean_path="data/processed/equipment_clean.csv",
    )

    equipment_clean = processor.run()

    print("\nПервые строки очищенной таблицы:")
    print(equipment_clean.head())
