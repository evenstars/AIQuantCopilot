"use client";

import { useState } from "react";
import { BACKEND_BASE_URL } from "./api/config";

type Message = {
  role: "user" | "assistant";
  content: string;
};

type ToolResult = {
  symbol?: string;
  fast?: number;
  slow?: number;
  start?: string;
  end?: string;
  cagr?: number;
  max_drawdown?: number;
  win_rate?: number;
  trades?: number;
  note?: string;
};

export default function HomePage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [toolResult, setToolResult] = useState<ToolResult | null>(null);

  const sendMessage = async () => {
    if (!input.trim()) return;
    const userMsg: Message = { role: "user", content: input };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setLoading(true);

    try {
      const res = await fetch(`${BACKEND_BASE_URL}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: input }),
      });

      if (!res.ok) throw new Error("Request failed");

      const data = await res.json();
      const assistantMsg: Message = {
        role: "assistant",
        content: data.reply || "",
      };

      setMessages((prev) => [...prev, assistantMsg]);
      setToolResult(data.tool_result || null);
    } catch (err) {
      console.error(err);
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: "调用后端失败，请检查服务是否启动。",
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (
    e: React.KeyboardEvent<HTMLTextAreaElement>
  ) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  return (
    <main className="mx-auto flex min-h-screen max-w-4xl flex-col p-4">
      <header className="mb-4 border-b border-slate-800 pb-3">
        <h1 className="text-2xl font-bold">AI Quant Copilot</h1>
        <p className="text-sm text-slate-400">
          聊聊量化策略、回测、风险收益，试试问：
          &ldquo;帮我做VOO 5-20均线策略并回测&rdquo;
        </p>
      </header>

      <section className="flex-1 space-y-4 overflow-y-auto rounded-xl border border-slate-800 bg-slate-900/50 p-4">
        {messages.length === 0 && (
          <div className="text-sm text-slate-500">
            👋 你好，我是你的量化研究助手。你可以问：
            <ul className="mt-2 list-disc pl-5">
              <li>帮我写一个VOO的5-20日均线策略并回测</li>
              <li>分析一下这个回测结果的风险收益</li>
              <li>帮我比较均值回归和趋势跟随策略</li>
            </ul>
          </div>
        )}

        {messages.map((m, i) => (
          <div
            key={i}
            className={`flex ${
              m.role === "user" ? "justify-end" : "justify-start"
            }`}
          >
            <div
              className={`max-w-[80%] rounded-2xl px-3 py-2 text-sm ${
                m.role === "user"
                  ? "bg-blue-600 text-white"
                  : "bg-slate-800 text-slate-100"
              }`}
            >
              {m.content}
            </div>
          </div>
        ))}

        {loading && (
          <div className="text-xs text-slate-500">模型思考中...</div>
        )}
      </section>

      {toolResult && (
        <section className="mt-4 rounded-xl border border-emerald-700 bg-emerald-950/40 p-4 text-sm">
          <h2 className="mb-2 text-base font-semibold text-emerald-300">
            回测结果（示例）
          </h2>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <div className="text-slate-400">标的</div>
              <div className="font-medium">{toolResult.symbol}</div>
            </div>
            <div>
              <div className="text-slate-400">均线参数</div>
              <div className="font-medium">
                fast: {toolResult.fast}, slow: {toolResult.slow}
              </div>
            </div>
            <div>
              <div className="text-slate-400">时间区间</div>
              <div className="font-medium">
                {toolResult.start} ~ {toolResult.end}
              </div>
            </div>
            <div>
              <div className="text-slate-400">年化收益 CAGR</div>
              <div className="font-medium">
                {toolResult.cagr !== undefined
                  ? `${(toolResult.cagr * 100).toFixed(2)}%`
                  : "-"}
              </div>
            </div>
            <div>
              <div className="text-slate-400">最大回撤</div>
              <div className="font-medium">
                {toolResult.max_drawdown !== undefined
                  ? `${(toolResult.max_drawdown * 100).toFixed(2)}%`
                  : "-"}
              </div>
            </div>
            <div>
              <div className="text-slate-400">胜率</div>
              <div className="font-medium">
                {toolResult.win_rate !== undefined
                  ? `${(toolResult.win_rate * 100).toFixed(2)}%`
                  : "-"}
              </div>
            </div>
            <div>
              <div className="text-slate-400">交易次数</div>
              <div className="font-medium">
                {toolResult.trades ?? "-"}
              </div>
            </div>
          </div>
          {toolResult.note && (
            <p className="mt-2 text-xs text-emerald-300">
              {toolResult.note}
            </p>
          )}
        </section>
      )}

      <section className="mt-4 flex gap-2">
        <textarea
          className="flex-1 resize-none rounded-xl border border-slate-700 bg-slate-900 p-3 text-sm outline-none focus:border-blue-500"
          rows={3}
          placeholder="输入你的问题，Shift+Enter 换行，Enter 发送"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
        />
        <button
          onClick={sendMessage}
          disabled={loading}
          className="h-[88px] w-24 rounded-xl bg-blue-600 text-sm font-medium text-white hover:bg-blue-500 disabled:cursor-not-allowed disabled:bg-slate-700"
        >
          {loading ? "发送中..." : "发送"}
        </button>
      </section>
    </main>
  );
}
