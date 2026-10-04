import { useState, useEffect } from "react";
import { useParams } from "react-router-dom";

function BotTestCard({ title, description, onRun, isRunning }) {
  return (
    <div className="bot-test-card">
      <h3>{title}</h3>
      <p>{description}</p>
      <button
        type="button"
        className="button button-secondary"
        onClick={onRun}
        disabled={isRunning}
      >
        {isRunning ? "Running..." : "Run Test"}
      </button>
    </div>
  );
}

export default function BotTesting() {
  const [results, setResults] = useState(null);
  const [error, setError] = useState("");
  const [running, setRunning] = useState(false);
  const { eventId } = useParams();

  const tests = [
    {
      name: "high-speed-bot",
      title: "High-Speed Bot",
      description: "Simulate a burst of automated JOIN requests.",
    },
    {
      name: "high-volume-bot",
      title: "High-Volume Bot",
      description: "Simulate repeated requests from the same user.",
    },
    {
      name: "duplicate-attack",
      title: "Duplicate Attack",
      description: "Simulate thousands of concurrent requests from one account.",
    },
    {
      name: "flash-crowd",
      title: "Flash Crowd",
      description: "Simulate a large concurrent registration spike.",
    },
  ];

  const runTest = async (testName) => {
    setRunning(true);
    setError("");
    setResults(null);
    const { eventId } = useParams(); // assumes route includes :eventId
    try {
      // Start bot test
      const startResp = await fetch(`/admin/events/${eventId}/bot-test/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ test_name: testName }),
        credentials: "include",
      });
      if (!startResp.ok) {
        const errText = await startResp.text();
        throw new Error(`Start failed: ${errText}`);
      }
      const { test_id } = await startResp.json();
      // Poll for status
      const poll = async () => {
        const statusResp = await fetch(`/admin/events/${eventId}/bot-test/${test_id}`, {
          method: "GET",
          credentials: "include",
        });
        if (!statusResp.ok) {
          const errText = await statusResp.text();
          throw new Error(`Status fetch failed: ${errText}`);
        }
        const data = await statusResp.json();
        if (data.status === "running") {
          setTimeout(poll, 2000);
        } else {
          setResults(data.result || {});
          setRunning(false);
        }
      };
      poll();
    } catch (err) {
      setError(err.message);
      setRunning(false);
    }
  };

  return (
    <div className="bot-testing-container">
      <div className="admin-section-heading">
        <div>
          <p className="eyebrow">Attack simulation</p>
          <h2>Bot injection testing</h2>
          <p className="intro-copy" style={{ marginTop: "8px" }}>
            Run controlled bot attack simulations to verify rate limiting and
            fraud detection.
          </p>
        </div>
      </div>

      <div className="bot-tests-grid">
        {tests.map((test) => (
          <BotTestCard
            key={test.name}
            title={test.title}
            description={test.description}
            onRun={() => runTest(test.name)}
            isRunning={running}
          />
        ))}
      </div>

      {error && <p className="admin-error">{error}</p>}

      {results && (
        <div className="bot-test-results">
          <div className="admin-section-heading">
            <div>
              <p className="eyebrow">Results</p>
              <h3>{results.test}</h3>
            </div>
            <span
              className={`lifecycle lifecycle-${results.pass ? "registration_open" : "registration_closed"}`}
            >
              {results.pass ? "PASS" : "FAIL"}
            </span>
          </div>

          <div className="results-grid">
            <div className="result-item">
              <span>Total requests</span>
              <strong>{results.totalRequests}</strong>
            </div>
            <div className="result-item">
              <span>Unique users</span>
              <strong>{results.uniqueUsers}</strong>
            </div>
            <div className="result-item">
              <span>Successful</span>
              <strong>{results.successful}</strong>
            </div>
            <div className="result-item">
              <span>Rate limited</span>
              <strong>{results.rateLimited}</strong>
            </div>
            <div className="result-item">
              <span>Errors</span>
              <strong>{results.errors}</strong>
            </div>
            <div className="result-item">
              <span>Duration</span>
              <strong>{results.duration}</strong>
            </div>
            <div className="result-item">
              <span>Throughput</span>
              <strong>{results.throughput}</strong>
            </div>
            <div className="result-item">
              <span>Unique entries</span>
              <strong>{results.uniqueEntries}</strong>
            </div>
            <div className="result-item">
              <span>Duplicate attempts</span>
              <strong>{results.duplicateAttempts}</strong>
            </div>
            <div className="result-item">
              <span>Oversold</span>
              <strong>{results.oversold}</strong>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
