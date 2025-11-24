from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Optional
import json
from dotenv import load_dotenv
from openai.types.chat import ChatCompletionFunctionToolParam
import os
from openai.types.chat import (
    ChatCompletionUserMessageParam,
    ChatCompletionSystemMessageParam,
)

from openai import OpenAI
from starlette.middleware.cors import CORSMiddleware

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

def run_dummy_backtest(**kwargs):
    print("Running dummy backtest...")
    return {
        "status": "ok",
        "echo": kwargs,
        "profit": 1234.56,
    }


# =========================
# 3. Tools schema (OpenAI SDK 2.x)
# =========================
TOOLS: list[ChatCompletionFunctionToolParam] = [
    ChatCompletionFunctionToolParam(
        type="function",
        function={
            "name": "run_dummy_backtest",
            "description": "Run a simple dummy backtest",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "period": {"type": "string"},
                },
                "required": ["symbol", "period"],
            },
        }
    )
]

SYSTEM_PROMPT = "You are an AI Quant Copilot."


# =========================
# 4. Chat API using new OpenAI 2.8.1 syntax
# =========================
@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):

    user_msg = req.message

    # --------------------------------------
    # FIRST CALL — let model decide tool usage
    # --------------------------------------
    messages: List[ChatCompletionSystemMessageParam | ChatCompletionUserMessageParam] = [
        ChatCompletionSystemMessageParam(role="system", content=SYSTEM_PROMPT),
        ChatCompletionUserMessageParam(role="user", content=user_msg),
    ]
    first = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        tools=TOOLS,
        tool_choice="auto",
    )

    ai_msg = first.choices[0].message

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

        if tool_name == "run_dummy_backtest":
            result = run_dummy_backtest(**args)
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
    # SECOND CALL — give tool results back to LLM
    # --------------------------------------
    second = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
            ai_msg.model_dump(),  # assistant with tool_calls
            *tool_messages        # tool outputs
        ]
    )

    final_text = second.choices[0].message.content

    return ChatResponse(
        reply=final_text,
        tool_result=tool_results,
    )
