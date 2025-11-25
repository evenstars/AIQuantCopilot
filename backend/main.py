from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Optional
import json
from dotenv import load_dotenv
from openai.types.chat import ChatCompletionFunctionToolParam
import os
import traceback
from openai.types.chat import (
    ChatCompletionUserMessageParam,
    ChatCompletionSystemMessageParam,
)

from openai import OpenAI
from starlette.middleware.cors import CORSMiddleware

from utils import save_strategy_code_to_file, dynamic_import_strategy, run_backtest_with_strategy

# Load env variables
load_dotenv()
print("API KEY =", os.getenv("OPENAI_API_KEY"))

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

Your job is to take a natural language description of a trading strategy
and output STRICT JSON with the following fields:

{
  "strategy_name": "...",
  "parameters": {...},
  "python_code": "..."
}

Rules:
1. python_code MUST be executable Python code using Backtrader.
2. Use a single Strategy class named exactly: GeneratedStrategy
3. No backtest runner code should be included.
4. No placeholders. All code must be runnable.
5. python_code should be a CLEAN Python file, no markdown.
6. Use self.data.close or self.data, never df.
7. Use indicators like bt.indicators.SimpleMovingAverage, RSI, etc.
8. DO NOT include comments in JSON.
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

def backtest_generated_code(python_code: str, symbol: str = "VOO"):
    """
    Full pipeline:
    1. Save python code
    2. Dynamically load GeneratedStrategy
    3. Run Backtrader backtest
    """

    # 1. Save to file
    file_path = save_strategy_code_to_file(python_code)
    # 2. Load strategy class
    strategy_class = dynamic_import_strategy(file_path)
    # 3. Run backtest
    result = run_backtest_with_strategy(strategy_class, symbol=symbol)

    return result

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
        if "python_code" in parsed:
            backtest_report = backtest_generated_code(
                parsed["python_code"],
                symbol='VOO'  # parsed["parameters"]["symbol"] ???
            )
            print("backtest_report: \n", backtest_report)
            return ChatResponse(
                reply="Backtest completed.",
                tool_result=[backtest_report]
            )
    except Exception as e:
        traceback.print_exc()
        print("Parsing/Backtest Error:", e)

    return ChatResponse(
        reply=final_text,
        tool_result=tool_results,
    )
