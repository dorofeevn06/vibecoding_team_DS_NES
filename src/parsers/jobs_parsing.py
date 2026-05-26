from pathlib import Path
from datetime import datetime
import time

import pandas as pd
import requests


class TrudvsemVacancyParser:
    """
    Парсер вакансий с портала «Работа России» через открытый API.

    Что делает:
    1. Ищет вакансии по списку ролей.
    2. Собирает основные поля: название, работодатель, регион/город, зарплата,
       график, занятость, требования, обязанности и ссылку на вакансию.
    3. Приводит данные к единому формату, близкому к прежнему формату hh.ru.
    4. Убирает дубли по vacancy_id.
    5. Сохраняет результат в data/raw/jobs_raw.csv.

    Источник данных:
    http://opendata.trudvsem.ru/api/v1/vacancies

    Важно:
    API «Работа России» может отдавать данные с разной вложенностью полей,
    поэтому ниже используются безопасные функции для извлечения значений.
    """

    BASE_URL = "http://opendata.trudvsem.ru/api/v1/vacancies"

    def __init__(
        self,
        roles,
        region_id="77",
        per_page=50,
        max_pages=3,
        only_with_salary=True,
        delay=0.5
    ):
        """
        roles: словарь вида {'администратор': ['администратор клуба', ...]}
        region_id: код региона для endpoint /region/{region_id}. '77' - Москва.
        per_page: сколько вакансий пытаться получить за один запрос.
        max_pages: сколько страниц собирать по каждому поисковому запросу.
        only_with_salary: оставлять только вакансии, где удалось найти зарплату.
        delay: пауза между запросами.
        """
        self.roles = roles
        self.region_id = region_id
        self.per_page = per_page
        self.max_pages = max_pages
        self.only_with_salary = only_with_salary
        self.delay = delay

        self.headers = {
            "User-Agent": "billiard-market-analysis/1.0 (student research project)",
            "Accept": "application/json",
            "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8"
        }

    @staticmethod
    def _deep_get(data, keys, default=None):
        """
        Безопасно достаёт вложенное значение из словаря.

        Пример:
        _deep_get(vacancy, ['company', 'name'])
        """
        current = data

        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return default

        return current

    @staticmethod
    def _first_not_empty(*values):
        for value in values:
            if value not in [None, "", [], {}]:
                return value
        return None

    @staticmethod
    def _as_number(value):
        if value is None:
            return None

        if isinstance(value, (int, float)):
            return value

        value = str(value)
        value = value.replace("руб.", "")
        value = value.replace("руб", "")
        value = value.replace("₽", "")
        value = value.replace(" ", "")
        value = value.replace(",", ".")

        digits = "".join(char for char in value if char.isdigit() or char == ".")

        if digits == "":
            return None

        try:
            return float(digits)
        except ValueError:
            return None

    def _build_url(self):
        if self.region_id:
            return f"{self.BASE_URL}/region/{self.region_id}"
        return self.BASE_URL

    def _get_json(self, params, retries=3):
        url = self._build_url()
        last_error = None

        for attempt in range(1, retries + 1):
            try:
                response = requests.get(
                    url,
                    headers=self.headers,
                    params=params,
                    timeout=40
                )

                if response.status_code == 404 and self.region_id:
                    fallback_url = self.BASE_URL
                    print("    Региональный endpoint не найден. Пробую общий endpoint без /region/.")
                    response = requests.get(
                        fallback_url,
                        headers=self.headers,
                        params=params,
                        timeout=40
                    )

                if response.status_code >= 400:
                    print(f"    HTTP-ошибка {response.status_code}.")
                    print(f"    Ответ сервера: {response.text[:500]}")

                response.raise_for_status()
                return response.json()

            except requests.exceptions.ConnectTimeout as error:
                last_error = error
                print(f"    Таймаут подключения. Попытка {attempt}/{retries}.")
                time.sleep(2 * attempt)

            except requests.exceptions.ReadTimeout as error:
                last_error = error
                print(f"    Сервер долго отвечает. Попытка {attempt}/{retries}.")
                time.sleep(2 * attempt)

            except requests.exceptions.ConnectionError as error:
                last_error = error
                print(f"    Ошибка соединения. Попытка {attempt}/{retries}.")
                time.sleep(2 * attempt)

            except requests.exceptions.HTTPError as error:
                last_error = error
                break

            except requests.exceptions.RequestException as error:
                last_error = error
                print(f"    Ошибка запроса. Попытка {attempt}/{retries}: {error}")
                time.sleep(2 * attempt)

        raise last_error

    def _extract_vacancy_items(self, data):
        """
        API может возвращать вакансии в разных вариантах структуры.
        Эта функция приводит ответ к списку словарей вакансий.
        """
        possible_lists = [
            self._deep_get(data, ["results", "vacancies"]),
            self._deep_get(data, ["vacancies"]),
            self._deep_get(data, ["vacancies", "vacancy"]),
            self._deep_get(data, ["results"]),
            data if isinstance(data, list) else None
        ]

        vacancies = None

        for candidate in possible_lists:
            if isinstance(candidate, list):
                vacancies = candidate
                break

        if vacancies is None:
            return []

        normalized = []

        for item in vacancies:
            if isinstance(item, dict) and "vacancy" in item and isinstance(item["vacancy"], dict):
                normalized.append(item["vacancy"])
            elif isinstance(item, dict):
                normalized.append(item)

        return normalized

    def _extract_salary(self, vacancy):
        salary_from = self._first_not_empty(
            vacancy.get("salary_min"),
            vacancy.get("salaryMin"),
            vacancy.get("salary_from"),
            vacancy.get("salary"),
            self._deep_get(vacancy, ["salary", "min"]),
            self._deep_get(vacancy, ["salary", "from"])
        )

        salary_to = self._first_not_empty(
            vacancy.get("salary_max"),
            vacancy.get("salaryMax"),
            vacancy.get("salary_to"),
            self._deep_get(vacancy, ["salary", "max"]),
            self._deep_get(vacancy, ["salary", "to"])
        )

        salary_from = self._as_number(salary_from)
        salary_to = self._as_number(salary_to)

        if salary_from is not None and salary_to is not None:
            salary_avg = (salary_from + salary_to) / 2
        elif salary_from is not None:
            salary_avg = salary_from
        elif salary_to is not None:
            salary_avg = salary_to
        else:
            salary_avg = None

        return {
            "salary_from": salary_from,
            "salary_to": salary_to,
            "salary_avg": salary_avg,
            "currency": "RUR" if salary_avg is not None else None,
            "salary_gross": None
        }

    def _parse_vacancy(self, vacancy, position_group, search_query):
        salary_data = self._extract_salary(vacancy)

        vacancy_id = self._first_not_empty(
            vacancy.get("id"),
            vacancy.get("vacancy_id"),
            vacancy.get("vacancyId"),
            vacancy.get("source_url"),
            vacancy.get("url")
        )

        vacancy_name = self._first_not_empty(
            vacancy.get("job-name"),
            vacancy.get("job_name"),
            vacancy.get("name"),
            vacancy.get("title")
        )

        employer = self._first_not_empty(
            self._deep_get(vacancy, ["company", "name"]),
            vacancy.get("company_name"),
            vacancy.get("companyName"),
            vacancy.get("employer"),
            vacancy.get("organization")
        )

        city = self._first_not_empty(
            self._deep_get(vacancy, ["region", "name"]),
            self._deep_get(vacancy, ["addresses", "address", 0, "location"]),
            vacancy.get("regionName"),
            vacancy.get("region"),
            vacancy.get("city")
        )

        requirements = self._first_not_empty(
            vacancy.get("requirement"),
            vacancy.get("requirements"),
            vacancy.get("qualification"),
            vacancy.get("education")
        )

        responsibilities = self._first_not_empty(
            vacancy.get("duty"),
            vacancy.get("responsibilities"),
            vacancy.get("description")
        )

        alternate_url = self._first_not_empty(
            vacancy.get("vac_url"),
            vacancy.get("url"),
            vacancy.get("source_url"),
            vacancy.get("contact_list")
        )

        return {
            "vacancy_id": vacancy_id,
            "vacancy_name": vacancy_name,
            "position_group": position_group,
            "search_query": search_query,
            "employer": employer,
            "city": city,
            "salary_from": salary_data["salary_from"],
            "salary_to": salary_data["salary_to"],
            "salary_avg": salary_data["salary_avg"],
            "currency": salary_data["currency"],
            "salary_gross": salary_data["salary_gross"],
            "experience": self._first_not_empty(vacancy.get("experience"), vacancy.get("work_experience")),
            "employment_type": self._first_not_empty(vacancy.get("employment"), vacancy.get("employment_type")),
            "schedule": self._first_not_empty(vacancy.get("schedule"), vacancy.get("schedule_type")),
            "requirements": requirements,
            "responsibilities": responsibilities,
            "published_at": self._first_not_empty(vacancy.get("creation-date"), vacancy.get("creation_date"), vacancy.get("published_at")),
            "created_at": self._first_not_empty(vacancy.get("creation-date"), vacancy.get("creation_date"), vacancy.get("created_at")),
            "alternate_url": alternate_url,
            "source": "Работа России",
            "collected_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

    def collect(self):
        all_rows = []

        for position_group, queries in self.roles.items():
            print(f"\nСобираю роль: {position_group}")

            for query in queries:
                print(f"  Поисковый запрос: {query}")

                for page in range(self.max_pages):
                    offset = page * self.per_page

                    params = {
                        "text": query,
                        "offset": offset,
                        "limit": self.per_page
                    }

                    try:
                        data = self._get_json(params)
                    except requests.exceptions.RequestException as error:
                        print(f"    Ошибка запроса на странице {page}: {error}")
                        break

                    vacancies = self._extract_vacancy_items(data)

                    if not vacancies:
                        print(f"    Страница {page}: вакансий нет, остановка.")
                        break

                    page_rows = []

                    for vacancy in vacancies:
                        row = self._parse_vacancy(
                            vacancy=vacancy,
                            position_group=position_group,
                            search_query=query
                        )

                        if self.only_with_salary and row["salary_avg"] is None:
                            continue

                        page_rows.append(row)
                        all_rows.append(row)

                    print(f"    Страница {page}: получено {len(vacancies)} вакансий, после фильтра зарплаты осталось {len(page_rows)}")

                    if len(vacancies) < self.per_page:
                        break

                    time.sleep(self.delay)

        df = pd.DataFrame(all_rows)

        if not df.empty:
            before = len(df)

            if "vacancy_id" in df.columns:
                df = df.drop_duplicates(subset=["vacancy_id"])
            else:
                df = df.drop_duplicates()

            after = len(df)
            print(f"\nУдалено дублей: {before - after}")
            print(f"Итоговое количество вакансий: {after}")
        else:
            print("\nВакансии не собраны. Проверь интернет, API или поисковые запросы.")

        return df

    def save(self, output_path):
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        df = self.collect()

        if df.empty:
            print("\nФайл не сохранён, потому что данные не были собраны.")
            return df

        df.to_csv(output_path, index=False, encoding="utf-8-sig")

        print(f"\nСохранено: {output_path}")
        return df


def main():
    project_root = Path(__file__).resolve().parents[1]
    output_path = project_root / "data" / "raw" / "jobs_raw.csv"

    roles = {
        "администратор": [
            "администратор",
            "администратор клуба",
            "администратор бильярдного клуба",
            "администратор ресторана",
            "администратор бара"
        ],
        "бармен": [
            "бармен",
            "бармен официант",
            "бармен в бар"
        ],
        "официант": [
            "официант",
            "официант ресторан",
            "официант бар"
        ],
        "управляющий": [
            "управляющий рестораном",
            "управляющий баром",
            "управляющий клубом",
            "менеджер смены",
            "менеджер зала"
        ],
        "уборщик": [
            "уборщик",
            "уборщица",
            "клинер"
        ],
        "инструктор по бильярду": [
            "инструктор по бильярду",
            "тренер по бильярду",
            "маркер бильярд",
            "сотрудник бильярдного клуба"
        ],
        "технический специалист": [
            "техник",
            "мастер по ремонту оборудования",
            "мастер по обслуживанию оборудования",
            "специалист по обслуживанию оборудования"
        ],
        "охранник": [
            "охранник",
            "контролер зала",
            "администратор охраны"
        ],
        "повар": [
            "повар",
            "помощник повара",
            "кухонный работник"
        ],
        "smm": [
            "smm специалист",
            "маркетолог",
            "специалист по рекламе"
        ],
        "event-менеджер": [
            "event менеджер",
            "ивент менеджер",
            "менеджер мероприятий",
            "организатор мероприятий"
        ]
    }

    parser = TrudvsemVacancyParser(
        roles=roles,
        region_id="77",
        per_page=50,
        max_pages=3,
        only_with_salary=True,
        delay=0.7
    )

    parser.save(output_path)


if __name__ == "__main__":
    main()