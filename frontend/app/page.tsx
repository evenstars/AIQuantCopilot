"use client";

import { useState, useRef, useEffect } from "react";
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

  // === 单窗口关键：存储当前轮询 interval ===
  const pollRef = useRef<NodeJS.Timeout | null>(null);

  // 组件卸载时清理 interval
  useEffect(() => {
    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current);
      }
    };
  }, []);

  // ====== 单窗口轮询功能 ======
  const pollBacktestStatus = (taskId: string) => {
    // 停掉之前的轮询
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }

    pollRef.current = setInterval(async () => {
      try {
        const res = await fetch(`${BACKEND_BASE_URL}/api/backtest/status/${taskId}`);
        const data = await res.json();

        // 完成 → 停止轮询 & 显示结果
        if (data.status === "complete") {
          clearInterval(pollRef.current!);
          pollRef.current = null;

          setToolResult(data.result);
          setMessages((prev) => [
            ...prev,
            { role: "assistant", content: "回测完成！" },
          ]);
        }

        // 失败 → 停止轮询
        if (data.status === "failed") {
          clearInterval(pollRef.current!);
          pollRef.current = null;

          setMessages((prev) => [
            ...prev,
            { role: "assistant", content: "回测失败：" + data.error },
          ]);
        }
      } catch (err) {
        console.error("轮询失败:", err);
      }
    }, 1500);
  };

  // ====== 发送消息 ======
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

      const data = await res.json();

      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: data.reply || "" },
      ]);

      // 如果后端返回 task_id → 开始轮询
      if (data.tool_result && data.tool_result.length > 0) {
        const task = data.tool_result[0];
        if (task.task_id) {
          pollBacktestStatus(task.task_id);
        }
      }
    } catch (err) {
      console.error(err);
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: "调用后端失败，请检查服务是否启动。" },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
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
              <li>做一个 VOO 5-20 均线策略，从 2018 到 2022 的数据</li>
              <li>分析一下这个回测结果的风险收益</li>
              <li>帮我比较均值回归和趋势跟随策略</li>
            </ul>
          </div>
        )}

        {messages.map((m, i) => (
          <div
            key={i}
            className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}
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
            回测结果
          </h2>
          <pre className="text-xs text-emerald-200">
            {JSON.stringify(toolResult, null, 2)}
          </pre>
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
