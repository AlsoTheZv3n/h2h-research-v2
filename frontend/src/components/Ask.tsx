import { useState, type FormEvent } from 'react'
import { ApiError, askDrug } from '../api/client'
import type { Answer, Citation } from '../api/types'

/**
 * Ask a question about this drug. The counterpart to Fact.tsx, one layer up.
 *
 * Fact renders three states distinctly because collapsing them is how an evidence
 * tool starts lying. This renders five, for exactly the same reason: "no model is
 * configured", "nobody has gathered evidence yet", "the model was down", and "the
 * model invented a citation so we withheld the answer" are four completely
 * different things to tell a reader, and the single generic error toast that every
 * other chat UI ships would erase all four.
 *
 * The last one is the point of the whole feature. When the backend catches a
 * fabricated citation it withholds the answer, and this is where the reader finds
 * out. It has to be visible, specific, and not dressed up as a network blip -- a
 * tool that quietly retried and showed the next answer would be hiding the single
 * most useful thing it ever learned.
 */

const PLACEHOLDER = 'e.g. What drives resistance to this drug?'

export function Ask({ chemblId, drugName }: { chemblId: string; drugName: string }) {
  const [question, setQuestion] = useState('')
  const [asking, setAsking] = useState(false)
  const [answer, setAnswer] = useState<Answer | null>(null)
  const [failed, setFailed] = useState<string | null>(null)

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    const asked = question.trim()
    if (asked.length < 3 || asking) return

    setAsking(true)
    setFailed(null)
    setAnswer(null)
    try {
      setAnswer(await askDrug(chemblId, asked))
    } catch (e) {
      // Something outside the API's five states. Kept separate rather than faked
      // into `unavailable`, which would be inventing a state the backend never
      // reported.
      //
      // Two different things land here and they need different words. An ApiError is
      // a non-2xx: the request DID reach a server, and it answered. Anything else is
      // the request never arriving. The first version called both "did not reach the
      // server", which sends a reader with a 500 to go check whether their backend
      // is running -- it is, and that is not the problem.
      setFailed(e instanceof ApiError ? `The server answered ${e.status}.` : 'unreachable')
    } finally {
      setAsking(false)
    }
  }

  return (
    <section data-testid="ask" className="flex flex-col gap-3">
      <form onSubmit={onSubmit} className="flex gap-2">
        <label htmlFor="ask-input" className="sr-only">
          Ask about {drugName}
        </label>
        <input
          id="ask-input"
          data-testid="ask-input"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder={PLACEHOLDER}
          maxLength={500}
          className="flex-1 rounded border border-line bg-surface px-3 py-2 text-sm text-ink
                     placeholder:text-ink-faint focus:border-accent focus:outline-none"
        />
        <button
          type="submit"
          data-testid="ask-submit"
          disabled={asking || question.trim().length < 3}
          className="rounded bg-accent px-3 py-2 text-sm font-medium text-white
                     disabled:cursor-not-allowed disabled:opacity-40"
        >
          {asking ? 'Asking…' : 'Ask'}
        </button>
      </form>

      {asking && (
        // Sets the expectation that a grounded answer is not instant. The harness read a still-
        // pending box as "the tool does not answer, it just shows a progress message" -- i.e.
        // broken. Naming the wait as normal keeps a slow answer reading as working, not stuck.
        <p data-testid="ask-pending" className="text-sm text-ink-faint italic">
          Reading this drug's facts and literature… a grounded answer can take a moment.
        </p>
      )}

      {failed && (
        <Notice testId="ask-transport-failed" tone="bad">
          {failed === 'unreachable'
            ? 'The request did not reach the server. Check that the backend is running, then try again.'
            : `${failed} That is not one of the answers this endpoint knows how to give, so something is wrong upstream of the model.`}
        </Notice>
      )}

      {answer && !asking && <AnswerView answer={answer} />}
    </section>
  )
}

function AnswerView({ answer }: { answer: Answer }) {
  switch (answer.state) {
    case 'ok':
      return (
        <div data-testid="answer-ok" className="flex flex-col gap-2">
          <p className="text-sm leading-relaxed whitespace-pre-wrap text-ink">{answer.text}</p>
          {answer.citations.length > 0 && <Citations citations={answer.citations} />}
        </div>
      )

    case 'ungrounded':
      // The loudest state, deliberately. Everything else here is a gap; this one is
      // a caught fabrication, and the reader learning that the tool checks -- and
      // tells them -- is worth more than the answer would have been.
      return (
        <Notice testId="answer-ungrounded" tone="bad">
          <strong className="font-medium">Answer withheld.</strong>{' '}
          {answer.detail ??
            'The model cited a source that was not in the retrieved evidence, so it invented it.'}
        </Notice>
      )

    case 'not_configured':
      return (
        <Notice testId="answer-not-configured" tone="neutral">
          {answer.detail ?? 'No language model is configured, so questions cannot be answered.'}
        </Notice>
      )

    case 'no_evidence':
      return (
        <Notice testId="answer-no-evidence" tone="neutral">
          {answer.detail ?? 'Nothing has been gathered about this drug yet.'}
        </Notice>
      )

    case 'enriching':
      // Async empty, not empty. The evidence is on its way; saying "nothing found"
      // here would be a lie about a job that is still running. Neutral, not an error.
      return (
        <Notice testId="answer-enriching" tone="neutral">
          {answer.detail ?? 'The evidence for this drug is still being gathered — ask again shortly.'}
        </Notice>
      )

    case 'withheld':
      // Neutral, not red. Nothing failed: the answer was accurate and the model
      // behaved. It quoted a paper, and that text is not ours to pass on. Rendering
      // this like an error would tell the reader something went wrong when what
      // actually happened is that a promise was kept.
      return (
        <Notice testId="answer-withheld" tone="neutral">
          {answer.detail ??
            'The answer quoted a paper directly, and that text is not ours to republish.'}
        </Notice>
      )

    case 'unavailable':
      return (
        <Notice testId="answer-unavailable" tone="bad">
          The model could not answer just now{answer.detail ? ` (${answer.detail})` : ''}. This
          is temporary — try again.
        </Notice>
      )
  }
}

function Citations({ citations }: { citations: Citation[] }) {
  return (
    <ul data-testid="answer-citations" className="flex flex-col gap-1 border-t border-line pt-2">
      {citations.map((c, i) => (
        <li key={`${i}-${c.pmid}`} className="text-xs">
          <a
            href={c.url}
            target="_blank"
            rel="noreferrer"
            className="text-accent hover:underline"
            data-testid="answer-citation"
          >
            PMID {c.pmid}
          </a>
          {c.title && <span className="text-ink-faint"> — {c.title}</span>}
        </li>
      ))}
    </ul>
  )
}

function Notice({
  testId,
  tone,
  children,
}: {
  testId: string
  tone: 'bad' | 'neutral'
  children: React.ReactNode
}) {
  const styles =
    tone === 'bad'
      ? 'border-unavailable/30 bg-unavailable-bg text-unavailable'
      : 'border-line bg-surface text-ink-faint'
  return (
    <p data-testid={testId} className={`rounded border px-3 py-2 text-sm ${styles}`}>
      {children}
    </p>
  )
}
