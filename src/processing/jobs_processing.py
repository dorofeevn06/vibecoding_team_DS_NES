from pathlib import Path

import pandas as pd


class JobsProcessor:
    """
    Processing-файл для сырых данных по вакансиям.

    Назначение файла:
    1. Загрузить data/raw/jobs_raw.csv.
    2. Привести текстовые поля к аккуратному виду.
    3. Привести зарплатные поля к числовому формату.
    4. Восстановить salary_avg, если он отсутствует, но есть salary_from / salary_to.
    5. Убрать строки без пригодной зарплаты.
    6. Убрать дубли.
    7. Сохранить очищенные данные в data/processed/jobs_clean.csv.
    """

    def __init__(self, input_path, output_path):
        self.input_path = Path(input_path)
        self.output_path = Path(output_path)
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.df = None

    @staticmethod
    def _clean_text(value):
        if pd.isna(value):
            return pd.NA

        value = str(value).strip()
        value = " ".join(value.split())

        if value == "":
            return pd.NA

        return value

    @staticmethod
    def _to_number(series):
        return pd.to_numeric(series, errors="coerce")

    def load_data(self):
        if not self.input_path.exists():
            raise FileNotFoundError(f"Не найден файл с сырыми данными: {self.input_path}")

        self.df = pd.read_csv(self.input_path)
        print(f"Загружено строк из raw-файла: {len(self.df)}")
        return self.df

    def clean_text_columns(self):
        if self.df is None:
            self.load_data()

        text_columns = [
            "vacancy_id",
            "vacancy_name",
            "position_group",
            "search_query",
            "employer",
            "city",
            "currency",
            "experience",
            "employment_type",
            "schedule",
            "requirements",
            "responsibilities",
            "alternate_url",
            "source",
            "collected_at"
        ]

        for column in text_columns:
            if column in self.df.columns:
                self.df[column] = self.df[column].apply(self._clean_text)

        return self.df

    def clean_salary_columns(self):
        if self.df is None:
            self.load_data()

        required_salary_columns = ["salary_from", "salary_to", "salary_avg"]

        for column in required_salary_columns:
            if column not in self.df.columns:
                self.df[column] = pd.NA

        for column in required_salary_columns:
            self.df[column] = self._to_number(self.df[column])

        self.df["salary_avg"] = self.df["salary_avg"].fillna(
            self.df[["salary_from", "salary_to"]].mean(axis=1)
        )

        return self.df

    def clean_date_columns(self):
        if self.df is None:
            self.load_data()

        date_columns = ["published_at", "created_at", "collected_at"]

        for column in date_columns:
            if column in self.df.columns:
                self.df[column] = pd.to_datetime(self.df[column], errors="coerce")

        return self.df

    def filter_rows(self):
        if self.df is None:
            self.load_data()

        before_filter = len(self.df)

        self.df = self.df[self.df["salary_avg"].notna()].copy()
        self.df = self.df[self.df["salary_avg"] > 0].copy()

        # Техническая очистка выбросов: оставляем только реалистичные месячные зарплаты.
        # Более содержательный анализ распределения зарплат будет сделан отдельно.
        self.df = self.df[(self.df["salary_avg"] >= 15_000) & (self.df["salary_avg"] <= 400_000)].copy()

        after_filter = len(self.df)
        print(f"Удалено строк с пустой/некорректной зарплатой: {before_filter - after_filter}")

        return self.df

    def drop_duplicates(self):
        if self.df is None:
            self.load_data()

        before_duplicates = len(self.df)

        if "vacancy_id" in self.df.columns:
            self.df = self.df.drop_duplicates(subset=["vacancy_id"]).copy()
        else:
            self.df = self.df.drop_duplicates().copy()

        after_duplicates = len(self.df)
        print(f"Удалено дублей: {before_duplicates - after_duplicates}")

        return self.df

    def sort_data(self):
        if self.df is None:
            self.load_data()

        sort_columns = []

        if "position_group" in self.df.columns:
            sort_columns.append("position_group")

        if "salary_avg" in self.df.columns:
            sort_columns.append("salary_avg")

        if sort_columns:
            self.df = self.df.sort_values(sort_columns).reset_index(drop=True)
        else:
            self.df = self.df.reset_index(drop=True)

        return self.df

    def save_data(self):
        if self.df is None:
            raise ValueError("Нет данных для сохранения. Сначала запусти обработку.")

        self.df.to_csv(self.output_path, index=False, encoding="utf-8-sig")
        print(f"Сохранено: {self.output_path}")
        return self.df

    def run(self):
        self.load_data()
        self.clean_text_columns()
        self.clean_salary_columns()
        self.clean_date_columns()
        self.filter_rows()
        self.drop_duplicates()
        self.sort_data()
        self.save_data()

        print("\nProcessing вакансий завершён.")
        print(f"Итоговое количество строк в clean-файле: {len(self.df)}")

        return self.df


def main():
    project_root = Path(__file__).resolve().parents[1]

    input_path = project_root / "data" / "raw" / "jobs_raw.csv"
    output_path = project_root / "data" / "processed" / "jobs_clean.csv"

    processor = JobsProcessor(
        input_path=input_path,
        output_path=output_path
    )

    processor.run()


if __name__ == "__main__":
    main()