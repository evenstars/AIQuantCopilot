from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Optional
import json
from dotenv import load_dotenv
from openai.types.chat import ChatCompletionFunctionToolParam
import traceback
from tasks import run_backtest_task
from openai.types.chat import (
    ChatCompletionUserMessageParam,
    ChatCompletionSystemMessageParam,
)

from openai import OpenAI
from starlette.middleware.cors import CORSMiddleware

# Load env variables
load_dotenv()
client = OpenAI()
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================
# 1. Request / Response Models
# =========================

class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    reply: str
    tool_result: Optional[List[dict]] = None


# =========================
# 2. Tool implementation
# =========================

STRATEGY_GENERATION_PROMPT = """
You are an AI Quant Research Copilot.

Your job is to take a natural-language description of a trading strategy
and output STRICT JSON with the following fields:

{
  "strategy_name": "...",
  "symbol": "...",
  "parameters": {...},
  "start_date": "YYYY-MM-DD",
  "end_date": "YYYY-MM-DD or null",
  "python_code": "..."
}

===========================
RULES — STRATEGY GENERATION
===========================

1. python_code MUST be fully executable Backtrader Python code.
2. The strategy must contain exactly one class named: GeneratedStrategy
3. DO NOT include any backtest runner logic (no cerebro.run, no yfinance downloads).
4. No placeholders. All code must be immediately runnable.
5. python_code must be plain Python, no markdown, no formatting fences.
6. Use self.data or self.data.close, never use any DataFrame variables like df.
7. Use official Backtrader indicators (SMA, EMA, RSI, Bollinger Bands, ATR, etc.).
8. DO NOT include comments in the JSON output.
9. Output must be STRICT JSON only — no explanations, no natural language outside JSON.

===========================
RULES — SYMBOL EXTRACTION
===========================

10. Extract the trading symbol from user input.
    Examples:
      - "AAPL", "TSLA", "MSFT"
      - ETFs like "VOO", "SPY", "QQQ"
      - Crypto like "BTC-USD", "ETH-USD"
      - International tickers like "0700.HK", "^N225"
    If no symbol is explicitly mentioned, default to: "VOO".

===========================
RULES — DATE RANGE PARSING
===========================

11. You MUST parse natural-language time expressions from the user.
    Supported forms include (examples assume today = 2025-01-01):
      - "past 10 years" → start_date = 2015-01-01, end_date = null
      - "last 5 years"  → start_date = 2020-01-01, end_date = null
      - "last 12 months" → start_date = 2024-01-01, end_date = null
      - "last 6 months" → start_date = 2024-07-01, end_date = null
      - "past decade" → start_date = 2015-01-01
      - "from 2015 to 2020" → start_date = 2015-01-01, end_date = 2020-01-01
      - "between 2010-01-01 and 2020-12-31" → exact dates

12. If the user gives a specific date such as:
       "start in 2015"
    then set:
       start_date = "2015-01-01"
       end_date = null unless stated otherwise.

13. If the user mentions ONLY an end year, such as:
       "until 2020"
    then set:
       end_date = "2020-01-01"
       start_date = default or inferred from context.

14. If NO time-related information is found:
      start_date = "2010-01-01"
      end_date = null

===========================
RULES — SAFETY AND COMPLIANCE
===========================

15. DO NOT hallucinate indicators or syntax not supported by Backtrader.
16. DO NOT invent parameters not explicitly required by the strategy.
17. All fields must be present — never omit any JSON key.

===========================
OUTPUT FORMAT (STRICT)
===========================

Return strictly:

{
  "strategy_name": "...",
  "symbol": "...",
  "parameters": {...},
  "start_date": "YYYY-MM-DD",
  "end_date": "YYYY-MM-DD or null",
  "python_code": "..."
}

No prose, no extra text, no markdown, no code fences.
"""


def generate_strategy_code(natural_language_strategy: str):
    """
    This function does NOT generate strategy code itself.
    Instead, it delegates the generation to the LLM by defining
    a tool schema the model can call.
    """
    return {
        "status": "received",
        "strategy_text": natural_language_strategy
    }

# =========================
# 3. Tools schema (OpenAI SDK 2.x)
# =========================
TOOLS: list[ChatCompletionFunctionToolParam] = [
    ChatCompletionFunctionToolParam(
        type="function",
        function={
            "name": "generate_strategy_code",
            "description": "Generate a Backtrader-ready Python strategy from natural language.",
            "parameters": {
                "type": "object",
                "properties": {
                    "natural_language_strategy": {"type": "string"}
                },
                "required": ["natural_language_strategy"]
            },
        }
    )
]

SYSTEM_PROMPT = (
    "You are an AI Quant Copilot. "
    "You convert natural language strategies into executable Python Backtrader code. "
    + STRATEGY_GENERATION_PROMPT
)

# =========================
# 4. Chat API using new OpenAI 2.8.1 syntax
# =========================
@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    user_msg = req.message

    # --------------------------------------
    # Initial CALL — let model decide tool usage
    # --------------------------------------
    messages: List[ChatCompletionSystemMessageParam | ChatCompletionUserMessageParam] = [
        ChatCompletionSystemMessageParam(role="system", content=SYSTEM_PROMPT),
        ChatCompletionUserMessageParam(role="user", content=user_msg),
    ]
    initial_call_result = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        tools=TOOLS,
        tool_choice="auto",
    )

    ai_msg = initial_call_result.choices[0].message

    # No tool call → just return model text
    if not hasattr(ai_msg, "tool_calls") or ai_msg.tool_calls is None:
        print("NO TOOLS NEEDED, RETURNING...:\n", ai_msg.content)
        return ChatResponse(
            reply=ai_msg.content,
            tool_result=None
        )

    # --------------------------------------
    # Execute tool(s)
    # --------------------------------------
    tool_results = []
    tool_messages = []

    for tool_call in ai_msg.tool_calls:
        tool_name = tool_call.function.name
        args = json.loads(tool_call.function.arguments)

        if tool_name == "generate_strategy_code":
            result = generate_strategy_code(**args)
        else:
            result = {"error": "Unknown tool"}

        tool_results.append(result)

        # prepare tool → LLM message
        tool_messages.append({
            "role": "tool",
            "tool_call_id": tool_call.id,
            "content": json.dumps(result)
        })

    # --------------------------------------
    # Completion CALL — give tool results back to LLM
    # --------------------------------------
    completion_call_result = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
            ai_msg.model_dump(),  # assistant with tool_calls
            *tool_messages  # tool outputs
        ]
    )

    final_text = completion_call_result.choices[0].message.content

    # Try to detect if the output contains strategy code JSON
    try:
        parsed = json.loads(final_text)
        print("generated result:\n",parsed)

        task = run_backtest_task.delay(
            python_code=parsed["python_code"],
            symbol=parsed.get("symbol", "VOO"),
            start_date=parsed.get("start_date"),
            end_date=parsed.get("end_date"),
            user_prompt=req.message
        )
        print("generated task:\n", task.id)
        return ChatResponse(
            reply="Backtest started.",
            tool_result=[{"task_id": task.id}]
        )
    except Exception as e:
        traceback.print_exc()
        print("Parsing/Backtest Error:", e)

    print("RUN BACKTEST FAILED")
    return ChatResponse(
        reply=final_text,
        tool_result=tool_results,
    )

@app.get("/api/backtest/status/{task_id}")
def get_backtest_status(task_id: str):
    task = run_backtest_task.AsyncResult(task_id)
    print("Backtest status:", task.status, " for task id: ", task_id)
    state = task.state or "UNKNOWN"
    info = task.info

    if state == "PENDING":
        return {"status": "pending"}

    if state == "STARTED":
        return {"status": "running"}

    if state == "SUCCESS":
        return {"status": "complete", "result": task.result}

    if state == "FAILURE":
        return {"status": "failed", "error": str(info)}

    return {
        "status": "unknown",
        "state": state,
        "info": str(info) if info else None,
    }
