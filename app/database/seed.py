import random
from datetime import datetime, timedelta
from sqlalchemy import create_engine, text
from app.config import settings

# Списки для генерации случайных данных
FIRST_NAMES = ["Иван", "Петр", "Сидр", "Анна", "Мария", "Олег", "Елена", "Дмитрий", "Сергей", "Алексей"]
LAST_NAMES = ["Иванов", "Петров", "Сидоров", "Козлов", "Новиков", "Морозов", "Волков", "Соколов", "Попов", "Лебедев"]
CITIES = ["Москва", "Санкт-Петербург", "Новосибирск", "Екатеринбург", "Казань"]

def generate_mock_data():
    # Создаем подключение
    engine = create_engine(settings.DATABASE_URL)
    
    print("Подключение к БД успешно...")

    with engine.connect() as conn:
        # 1. Очищаем старые таблицы (если есть)
        print("Очистка старых таблиц...")
        conn.execute(text("DROP TABLE IF EXISTS orders;"))
        conn.execute(text("DROP TABLE IF EXISTS customers;"))
        conn.commit()

        # 2. Создаем таблицы заново
        print("Создание новых таблиц...")
        conn.execute(text("""
            CREATE TABLE customers (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                city VARCHAR(100)
            );
        """))
        
        conn.execute(text("""
            CREATE TABLE orders (
                id SERIAL PRIMARY KEY,
                customer_id INTEGER REFERENCES customers(id),
                amount FLOAT NOT NULL,
                profit FLOAT NOT NULL,
                order_date DATE NOT NULL
            );
        """))
        
        print("Создание таблицы пользователей...")
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                email VARCHAR(255) UNIQUE NOT NULL,
                hashed_password VARCHAR(255) NOT NULL
            );
        """))

        conn.commit()
        print("Таблицы созданы.")

        # 3. Генерируем клиентов
        customers_data = []
        for i in range(1, 21): # 20 клиентов
            name = f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"
            city = random.choice(CITIES)
            customers_data.append(f"('{name}', '{city}')")
        
        insert_customers_query = f"INSERT INTO customers (name, city) VALUES {', '.join(customers_data)};"
        conn.execute(text(insert_customers_query))
        conn.commit()
        print("Добавлено 20 клиентов.")

        # 4. Генерируем заказы
        orders_data = []
        start_date = datetime(2023, 1, 1)
        
        for _ in range(500): # 500 заказов
            cust_id = random.randint(1, 20)
            amount = round(random.uniform(100, 10000), 2)
            profit = round(amount * random.uniform(0.1, 0.4), 2) # Прибыль 10-40% от суммы
            days_offset = random.randint(0, 365)
            order_date = (start_date + timedelta(days=days_offset)).strftime('%Y-%m-%d')
            
            orders_data.append(f"({cust_id}, {amount}, {profit}, '{order_date}')")

        # Вставляем пачками для надежности (или одной строкой, если драйвер позволяет)
        insert_orders_query = f"INSERT INTO orders (customer_id, amount, profit, order_date) VALUES {', '.join(orders_data)};"
        conn.execute(text(insert_orders_query))
        conn.commit()
        print("Добавлено 500 заказов.")
        
        print("\n✅ Миграция и заполнение данных завершены успешно!")

if __name__ == "__main__":
    generate_mock_data()