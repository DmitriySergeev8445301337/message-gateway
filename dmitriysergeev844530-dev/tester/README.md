# Публичный тестер

Тестер отправляет HTTP-запросы в запущенное решение и сверяет ответы с
`public_tests.json`.

## Запуск решения

Из корня репозитория можно запустить стартовую Python-заготовку так:

```bash
python3 -m pip install -r solution/requirements.txt
PORT=8080 python3 solution/main.py
```

Или через Docker:

```bash
docker build -t red-2026-solution solution
docker run --rm -p 8080:8080 red-2026-solution
```

## Запуск тестера

В другом терминале, из корня репозитория:

```bash
python3 tester/tester.py --url http://localhost:8080
```

Полезные опции:

```bash
# Запустить только тесты, в названии которых есть строка basic
python3 tester/tester.py --case basic

# Увеличить таймаут одного HTTP-запроса до 10 секунд
python3 tester/tester.py --timeout 10

# Использовать другой файл с тестами
python3 tester/tester.py --tests path/to/tests.json
```

Успешный прогон заканчивается строкой `result:      OK`. Если решение еще не
реализовано полностью, тестер покажет список отличий в блоке `PROBLEMS`.
