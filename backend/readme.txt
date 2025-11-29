Run `uvicorn main:app --reload --port 8000` to start

or Run `
python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
`
for .venv dependencies

see Uvicorn running on http://127.0.0.1:8000 means OK


because redis is a dependency by Celery, redis needs to be started beforehand by:
`
redis-server
`
this needs to be in a separate terminal

How to start Celery:
source ../.venv/bin/activate
celery -A tasks worker --loglevel=info

TODOs:
1. tests
2. multi symbols?

tested strategy prompts:
1. 帮我生成一个 AAPL 的 10-50 日均线策略，并回测过去 10 年。
2.
