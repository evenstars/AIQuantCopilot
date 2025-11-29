from dotenv import load_dotenv
from openai.types.chat import ChatCompletionSystemMessageParam, ChatCompletionUserMessageParam

from celery_app import celery_app
from utils import backtest_generated_code
from openai import OpenAI
import json
import os

load_dotenv()
client = OpenAI()

MAX_RETRY = 3

REPAIR_PROMPT_TEMPLATE = """
The following is the original natural-language strategy description from the user:
=====================
USER STRATEGY REQUEST:
=====================
{user_prompt}

Your previously generated Backtrader strategy caused an execution error.

=====================
ERROR MESSAGE:
=====================
{error_msg}

=====================
ORIGINAL PYTHON CODE:
=====================
{python_code}

=====================
INSTRUCTIONS:
=====================
Fix the error and output a NEW python_code that defines a single Backtrader strategy:

- The class MUST be named: GeneratedStrategy
- MUST NOT use non-existent indicators
- Use only valid Backtrader indicators: SMA, EMA, RSI, ATR, MACD, Highest, Lowest
- Code must precisely follow the user's strategy intent described above
- Do NOT change the intended logic of the strategy
- Code must be immediately executable
- No placeholders, no TODOs
- Do NOT include cerebro, data download, or backtest logic
- Output MUST be ONLY python_code (raw string), no JSON, no markdown
"""


@celery_app.task(bind=True)
def run_backtest_task(self, python_code: str, symbol="VOO", start_date=None, end_date=None, user_prompt: str = ""):
    """
    FULL SHORT-LOOP AGENT BACKTEST PIPELINE:
    - Try backtest
    - If error → ask LLM to repair strategy code
    - Retry up to MAX_RETRY times
    """
    attempt = 0
    current_code = python_code

    while attempt < MAX_RETRY:
        try:
            print(f"[Attempt {attempt+1}/{MAX_RETRY}] Running backtest...")
            result = backtest_generated_code(current_code, symbol, start_date, end_date)
            print("BACKTEST SUCCESS:", result)
            return result

        except Exception as e:
            # Capture the error message
            error_msg = str(e)
            print(f"[Attempt {attempt+1}] ERROR OCCURRED:", error_msg)

            attempt += 1
            if attempt >= MAX_RETRY:
                print("MAX RETRIES REACHED. RETURNING ERROR.")
                return {"error": error_msg}

            # ---------------------
            # AUTO-REPAIR USING LLM
            # ---------------------
            repair_prompt = REPAIR_PROMPT_TEMPLATE.format(
                user_prompt=user_prompt,
                error_msg=error_msg,
                python_code=current_code
            )

            print("[AGENT] Requesting repair from LLM...")

            fix_response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    ChatCompletionSystemMessageParam(role="system", content="You repair broken Backtrader strategies."),
                    ChatCompletionUserMessageParam(role="user", content=repair_prompt),
                ]
            )

            fixed_code = fix_response.choices[0].message.content
            print("[AGENT] Fixed code received.")

            # Replace the code for next iteration
            current_code = fixed_code

    return {"error": "Unknown error in repair loop"}
