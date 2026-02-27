import { generateObject, generateText, jsonSchema, streamText } from 'ai';
import { openai } from '@ai-sdk/openai';

function buildPromptInput(body) {
  const system = String(body.system || '').trim();
  const prompt = String(body.prompt || body.user || '').trim();
  return { system, prompt };
}

function normalizeUsage(usage) {
  if (!usage || typeof usage !== 'object') return {};
  const prompt = Number(usage.promptTokens ?? usage.inputTokens ?? usage.prompt_tokens ?? 0) || 0;
  const completion = Number(usage.completionTokens ?? usage.outputTokens ?? usage.completion_tokens ?? 0) || 0;
  const total = Number(usage.totalTokens ?? usage.total_tokens ?? prompt + completion) || prompt + completion;
  return {
    prompt_tokens: prompt,
    completion_tokens: completion,
    total_tokens: total,
  };
}

function timeoutSignal(timeoutMs) {
  const ms = Number(timeoutMs || 0) || 0;
  if (ms <= 0) return undefined;
  return AbortSignal.timeout(ms);
}

export function createAiEngine(config) {
  const defaultModel = String(config.defaultModel || 'gpt-4o-mini');

  return {
    async generateText(body) {
      const modelName = String(body.model || defaultModel);
      const { system, prompt } = buildPromptInput(body);
      const result = await generateText({
        model: openai(modelName),
        system,
        prompt,
        temperature: body.temperature,
        maxRetries: body.max_retries,
        abortSignal: timeoutSignal(body.timeout_ms || config.timeoutMs),
      });
      return {
        text: String(result.text || ''),
        usage: normalizeUsage(result.usage),
        finish_reason: String(result.finishReason || 'stop'),
      };
    },

    async *streamText(body) {
      const modelName = String(body.model || defaultModel);
      const { system, prompt } = buildPromptInput(body);
      const result = streamText({
        model: openai(modelName),
        system,
        prompt,
        temperature: body.temperature,
        maxRetries: body.max_retries,
        abortSignal: timeoutSignal(body.timeout_ms || config.timeoutMs),
      });

      let aggregate = '';
      for await (const delta of result.textStream) {
        const text = String(delta || '');
        if (!text) continue;
        aggregate += text;
        yield { type: 'text-delta', delta: text };
      }

      yield {
        type: 'done',
        text: aggregate,
        usage: normalizeUsage(result.usage),
        finish_reason: String(result.finishReason || 'stop'),
      };
    },

    async generateObject(body) {
      const modelName = String(body.model || defaultModel);
      const { system, prompt } = buildPromptInput(body);
      if (!body.schema || typeof body.schema !== 'object') {
        throw new Error('schema required for generate-object');
      }
      const result = await generateObject({
        model: openai(modelName),
        system,
        prompt,
        schema: jsonSchema(body.schema),
        temperature: body.temperature,
        maxRetries: body.max_retries,
        abortSignal: timeoutSignal(body.timeout_ms || config.timeoutMs),
      });
      return {
        object: result.object,
        usage: normalizeUsage(result.usage),
        finish_reason: String(result.finishReason || 'stop'),
      };
    },
  };
}
