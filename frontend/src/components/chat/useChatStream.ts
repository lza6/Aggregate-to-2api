import { useCallback } from 'react';
import type { ChatMessage, SseResult } from './chat-utils';
import { ChatRequestError, getMessageContent, readResponseJson, getErrorPayload, appendAssistantMessage } from './chat-utils';
import type { Effort } from './chat-utils';

interface ConsumeSseOptions {
  response: Response;
  onDelta: (delta: { content?: string; reasoning?: string; toolCall?: string }) => void;
}

/** 流式 SSE 消费：逐行解析 data: 行，累积 content/reasoning/toolCalls/usage。
 * 抛 ChatRequestError 表示服务端在流中插入错误帧（v6.6.0 server_error 识别）。 */
export function useChatStream() {
  return useCallback(async ({ response, onDelta }: ConsumeSseOptions): Promise<SseResult> => {
    if (!response.body) throw new Error('服务端未返回可读取的响应流');
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let content = '';
    let reasoning = '';
    const toolCalls: string[] = [];
    let usage: ChatMessage['usage'];

    const processLine = (line: string) => {
      if (!line.startsWith('data:')) return;
      const data = line.slice(5).trim();
      if (!data || data === '[DONE]') return;
      let parsed: unknown;
      try {
        parsed = JSON.parse(data);
      } catch {
        return;
      }
      if (!parsed || typeof parsed !== 'object') return;
      const payload = parsed as Record<string, unknown>;
      if (payload.error && typeof payload.error === 'object') {
        const errObj = payload.error as Record<string, unknown>;
        const msg = typeof errObj.message === 'string' ? errObj.message
          : typeof payload.message === 'string' ? payload.message
          : '聊天流式调用失败';
        throw new ChatRequestError(msg, 500);
      }
      if (payload.usage && typeof payload.usage === 'object') {
        usage = payload.usage as ChatMessage['usage'];
      }
      const choices = Array.isArray(payload.choices) ? payload.choices : [];
      const choice = choices[0];
      if (!choice || typeof choice !== 'object') return;
      const delta = (choice as Record<string, unknown>).delta;
      const message = (choice as Record<string, unknown>).message;
      const source = delta && typeof delta === 'object' ? delta as Record<string, unknown> : message && typeof message === 'object' ? message as Record<string, unknown> : {};
      const nextContent = getMessageContent(source.content);
      const nextReasoning = getMessageContent(source.reasoning_content ?? source.reasoning);
      const nextToolCalls = Array.isArray(source.tool_calls) ? source.tool_calls : [];
      if (nextContent) {
        content += nextContent;
        onDelta({ content: nextContent });
      }
      if (nextReasoning) {
        reasoning += nextReasoning;
        onDelta({ reasoning: nextReasoning });
      }
      nextToolCalls.forEach(toolCall => {
        const text = typeof toolCall === 'string' ? toolCall : JSON.stringify(toolCall);
        if (text) {
          toolCalls.push(text);
          onDelta({ toolCall: text });
        }
      });
    };

    while (true) {
      const { done, value } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });
      const lines = buffer.split(/\r?\n/);
      buffer = lines.pop() ?? '';
      lines.forEach(processLine);
      if (done) break;
    }
    if (buffer) processLine(buffer);
    return { content, reasoning, toolCalls, usage };
  }, []);
}

export type { Effort };
export { ChatRequestError, readResponseJson, getErrorPayload, appendAssistantMessage };
