/**
 * The evaluator model for the usability harness.
 *
 * It plays a professional oncology researcher who sees ONLY the rendered page (no repo, no README,
 * no source) and works a concrete task. The point is comprehension: does the reader understand what
 * a number or a label actually claims? A term the model misreads -- and says what it *assumed* it
 * meant -- is the finding; the wrong guess means the label failed, not the reader.
 *
 * Model parity with the app's chat: Anthropic when ANTHROPIC_API_KEY is set (the chat's default),
 * else Ollama (the keyless fallback the chat uses, llama3.1:8b by default). No model reachable -> we
 * throw and the run exits. A stub never misunderstands anything, so a stubbed run would prove
 * nothing; the harness refuses to fake it.
 */

export const RESEARCHER_SYSTEM = `You are a professional oncology researcher evaluating a web tool for real work. You are given a task and the TEXT of the page(s) you are looking at. Work the task using ONLY what is on the page -- you cannot see the code, the README, or any documentation, and you must not speculate about how it is built.

At each step ask yourself: Does this matter to me? Is it incomplete? Am I missing information I would need? Do I actually understand what this number or label means?

Be specific. When a word or number is unclear, say exactly which wording confused you and what you ASSUMED it meant -- your wrong guess is the most useful thing you can report. If you cannot finish the task, say exactly where you got stuck. Judge only what is on the screen; never guess at the implementation.`

export interface Evaluator {
  name: string
  /** Send the researcher system prompt + a task/page prompt; return the model's raw text. */
  complete(system: string, user: string): Promise<string>
}

class AnthropicEvaluator implements Evaluator {
  name: string
  constructor(
    private key: string,
    private model = 'claude-opus-4-8',
  ) {
    this.name = `anthropic:${model}`
  }
  async complete(system: string, user: string): Promise<string> {
    const r = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        'x-api-key': this.key,
        'anthropic-version': '2023-06-01',
      },
      body: JSON.stringify({
        model: this.model,
        max_tokens: 1500,
        system,
        messages: [{ role: 'user', content: user }],
      }),
    })
    if (!r.ok) throw new Error(`anthropic ${r.status}: ${(await r.text()).slice(0, 300)}`)
    const body = (await r.json()) as { content: { type: string; text?: string }[] }
    return body.content.map((c) => c.text ?? '').join('')
  }
}

class OllamaEvaluator implements Evaluator {
  name: string
  constructor(
    private url: string,
    private model = 'llama3.1:8b',
  ) {
    this.name = `ollama:${model}`
  }
  async complete(system: string, user: string): Promise<string> {
    // format:"json" nudges the small model to emit parseable JSON; the caller still parses
    // defensively. A generous timeout: the first call after a cold Ollama pays to load the weights.
    const r = await fetch(`${this.url}/api/chat`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({
        model: this.model,
        stream: false,
        format: 'json',
        options: { temperature: 0.2 },
        messages: [
          { role: 'system', content: system },
          { role: 'user', content: user },
        ],
      }),
      signal: AbortSignal.timeout(300_000),
    })
    if (!r.ok) throw new Error(`ollama ${r.status}: ${(await r.text()).slice(0, 300)}`)
    const body = (await r.json()) as { message?: { content?: string } }
    return body.message?.content ?? ''
  }
}

/**
 * Resolve the evaluator like the chat provider does: Anthropic if a key is present, else Ollama.
 * No key and no reachable Ollama -> throw (the harness must not silently degrade to a stub).
 */
export async function resolveEvaluator(): Promise<Evaluator> {
  const key = process.env.ANTHROPIC_API_KEY
  if (key) return new AnthropicEvaluator(key, process.env.EVAL_MODEL ?? 'claude-opus-4-8')

  const url = process.env.OLLAMA_URL ?? 'http://localhost:11434'
  try {
    const ping = await fetch(`${url}/api/tags`, { signal: AbortSignal.timeout(5000) })
    if (!ping.ok) throw new Error(`status ${ping.status}`)
  } catch (e) {
    throw new Error(
      `No evaluator model. Set ANTHROPIC_API_KEY, or run Ollama at ${url} ` +
        `(pull llama3.1:8b). Ping failed: ${String(e)}. The harness will not stub a model.`,
    )
  }
  return new OllamaEvaluator(url, process.env.EVAL_MODEL ?? 'llama3.1:8b')
}

/** Parse the model's JSON judgment defensively -- a small model may wrap it or add prose. */
export interface Judgment {
  completed: 'yes' | 'no' | 'partially' | 'unknown'
  answer: string
  termsMisread: { term: string; assumed: string }[]
  assumptions: string[]
  stuckAt: string | null
}

export function parseJudgment(raw: string): Judgment {
  const fallback: Judgment = {
    completed: 'unknown',
    answer: raw.slice(0, 500),
    termsMisread: [],
    assumptions: [],
    stuckAt: 'evaluator response was not parseable JSON',
  }
  const start = raw.indexOf('{')
  const end = raw.lastIndexOf('}')
  if (start < 0 || end <= start) return fallback
  try {
    const o = JSON.parse(raw.slice(start, end + 1)) as Record<string, unknown>
    // A small model may return termsMisread as an array of objects (the asked-for shape), a single
    // unwrapped object, an array of bare strings, or a lone string -- normalise all four, else a
    // shape drift would silently drop the harness's primary output to "no misread".
    const rawMisread = Array.isArray(o.termsMisread)
      ? o.termsMisread
      : o.termsMisread
        ? [o.termsMisread]
        : []
    return {
      completed: (['yes', 'no', 'partially'].includes(String(o.completed))
        ? o.completed
        : 'unknown') as Judgment['completed'],
      answer: typeof o.answer === 'string' ? o.answer : JSON.stringify(o.answer ?? ''),
      termsMisread: rawMisread
        .map((m) =>
          typeof m === 'string'
            ? { term: m, assumed: '' }
            : {
                term: String((m as Record<string, unknown>).term ?? ''),
                assumed: String((m as Record<string, unknown>).assumed ?? ''),
              },
        )
        .filter((m) => m.term),
      assumptions: (Array.isArray(o.assumptions) ? o.assumptions : []).map((a) => String(a)),
      stuckAt: o.stuckAt == null || o.stuckAt === '' ? null : String(o.stuckAt),
    }
  } catch {
    return fallback
  }
}
