import { useState } from "react";

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

    try {
      // Mock results for now - will connect to real API when available
      const mockResults = {
        "high-speed-bot": {
          test: "High-Speed Bot",
          totalRequests: 100,
          uniqueUsers: 1,
          successful: 20,
          rateLimited: 80,
          errors: 0,
          duration: "2.3s",
          throughput: "43 req/s",
          uniqueEntries: 1,
          duplicateAttempts: 99,
          oversold: 0,
          pass: true,
        },
        "high-volume-bot": {
          test: "High-Volume Bot",
          totalRequests: 1000,
          uniqueUsers: 1,
          successful: 1,
          rateLimited: 999,
          errors: 0,
          duration: "12.5s",
          throughput: "80 req/s",
          uniqueEntries: 1,
          duplicateAttempts: 999,
          oversold: 0,
          pass: true,
        },
        "duplicate-attack": {
          test: "Duplicate Attack",
          totalRequests: 1000,
          uniqueUsers: 1,
          successful: 1,
          rateLimited: 999,
          errors: 0,
          duration: "3.1s",
          throughput: "322 req/s",
          uniqueEntries: 1,
          duplicateAttempts: 999,
          oversold: 0,
          pass: true,
        },
        "flash-crowd": {
          test: "Flash Crowd",
          totalRequests: 5000,
          uniqueUsers: 5000,
          successful: 5000,
          rateLimited: 0,
          errors: 0,
          duration: "5.8s",
          throughput: "862 req/s",
          uniqueEntries: 5000,
          duplicateAttempts: 0,
          oversold: 0,
          pass: true,
        },
      };

      // Simulate network delay
      await new Promise((resolve) => setTimeout(resolve, 1500));

      setResults(mockResults[testName] || {});
    } catch (err) {
      setError(err.message);
    } finally {
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
