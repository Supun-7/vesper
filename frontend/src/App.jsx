import { useState, useRef, useEffect } from 'react'

const API_URL = 'http://localhost:8000'

function SourceRecords({ records }) {
  const [open, setOpen] = useState(false)
  if (!records || records.length === 0) return null

  const columns = Object.keys(records[0])

  return (
    <div className="sources">
      <button className="sources-toggle" onClick={() => setOpen(!open)}>
        {open ? 'Hide' : 'Show'} {records.length} source record{records.length !== 1 ? 's' : ''}
      </button>
      {open && (
        <div className="sources-table-wrap">
          <table className="sources-table">
            <thead>
              <tr>{columns.map((c) => <th key={c}>{c}</th>)}</tr>
            </thead>
            <tbody>
              {records.map((r, i) => (
                <tr key={i}>
                  {columns.map((c) => <td key={c}>{String(r[c] ?? '—')}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function AnswerCard({ entry }) {
  const routedLabel = entry.routed_to === 'forecasting' ? 'Forecasting Agent' : 'Query Agent'
  const routedClass = entry.routed_to === 'forecasting' ? 'dot-forecast' : 'dot-query'

  return (
    <div className="entry">
      <div className="entry-question">{entry.question}</div>
      <div className="entry-meta">
        <span className={`dot ${routedClass}`} />
        <span>{routedLabel}</span>
      </div>
      <div className="entry-answer">{entry.answer}</div>
      <SourceRecords records={entry.source_records} />
    </div>
  )
}

export default function App() {
  const [question, setQuestion] = useState('')
  const [entries, setEntries] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [entries, loading])

  async function handleSubmit(e) {
    e.preventDefault()
    const q = question.trim()
    if (!q || loading) return

    setLoading(true)
    setError(null)
    setQuestion('')

    try {
      const res = await fetch(`${API_URL}/ask`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: q }),
      })
      if (!res.ok) throw new Error(`Server responded with ${res.status}`)
      const data = await res.json()
      setEntries((prev) => [...prev, data])
    } catch (err) {
      setError(`Couldn't reach Vesper's backend — is it running at ${API_URL}? (${err.message})`)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="page">
      <header className="header">
        <h1>Vesper</h1>
        <p className="tagline">AI Your ERP Data Can Actually Believe In</p>
      </header>

      <main className="conversation">
        {entries.length === 0 && !loading && (
          <div className="empty-state">
            Ask something like <em>"which products are low on stock?"</em> or{' '}
            <em>"forecast demand for SEA-027 next month"</em>.
          </div>
        )}

        {entries.map((entry, i) => (
          <AnswerCard key={i} entry={entry} />
        ))}

        {loading && <div className="loading">Thinking…</div>}
        {error && <div className="error">{error}</div>}

        <div ref={bottomRef} />
      </main>

      <form className="input-bar" onSubmit={handleSubmit}>
        <input
          type="text"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask about your data…"
          disabled={loading}
        />
        <button type="submit" disabled={loading || !question.trim()}>
          Ask
        </button>
      </form>
    </div>
  )
}
