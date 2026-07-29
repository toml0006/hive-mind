"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

type Decision = {
  uuid: string;
  decision_key: string;
  statement: string;
  rationale: string;
  alternatives_rejected?: string[];
  status: "live" | "superseded";
  group_id: string;
  scope: string;
  repo?: string;
  decided_at: string;
  recorded_at: string;
  superseded_at?: string;
  source?: string;
  confirmed_by?: string;
};

type Grounding = {
  decision_uuid: string;
  episode_uuid: string;
  name: string;
  group_id: string;
  source: string;
  valid_at: string;
  excerpt: string;
};

type Fact = {
  source_uuid: string;
  source_name: string;
  target_uuid: string;
  target_name: string;
  fact_uuid: string;
  fact: string;
  relation: string;
  group_id: string;
  valid_at: string;
};

type Episode = {
  uuid: string;
  name: string;
  group_id: string;
  source: string;
  valid_at: string;
  excerpt: string;
};

type Scope = {
  group_id: string;
  decisions: number;
  episodes: number;
};

type DecisionRevision = {
  uuid: string;
  decision_uuid: string;
  statement: string;
  rationale: string;
  alternatives_rejected?: string[];
  decided_at: string;
  status: string;
  edited_at: string;
  edit_note: string;
};

type BrainData = {
  connected: boolean;
  refreshedAt: string;
  stats: {
    decision_count: number;
    live_count: number;
    superseded_count: number;
    grounded_count: number;
    episode_count: number;
    entity_count: number;
    fact_count: number;
  };
  scopes: Scope[];
  decisions: Decision[];
  grounding: Grounding[];
  supersedes: Array<{ newer_uuid: string; older_uuid: string }>;
  facts: Fact[];
  episodes: Episode[];
  revisions: Array<{
    decision_uuid: string;
    revision: DecisionRevision;
  }>;
};

type View = "decisions" | "timeline" | "map" | "sources";

const NAV: Array<{ id: View; label: string; eyebrow: string }> = [
  { id: "decisions", label: "Decisions", eyebrow: "Canonical memory" },
  { id: "timeline", label: "Timeline", eyebrow: "What changed when" },
  { id: "map", label: "Knowledge map", eyebrow: "Relationships" },
  { id: "sources", label: "Sources", eyebrow: "Meetings & evidence" },
];

function shortDate(value?: string) {
  if (!value) return "Unknown";
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(new Date(value));
}

function relativeDate(value?: string) {
  if (!value) return "";
  const days = Math.round(
    (new Date(value).getTime() - Date.now()) / (1000 * 60 * 60 * 24),
  );
  if (Math.abs(days) < 1) return "today";
  if (days === -1) return "yesterday";
  if (days > -30) return `${Math.abs(days)} days ago`;
  return shortDate(value);
}

function clip(value: string, length: number) {
  return value.length > length ? `${value.slice(0, length).trim()}…` : value;
}

function datetimeLocal(value: string) {
  const date = new Date(value);
  const offset = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 16);
}

async function fetchBrain(): Promise<BrainData> {
  const response = await fetch("/api/brain", { cache: "no-store" });
  const payload = await response.json();
  if (!response.ok || !payload.connected) {
    throw new Error(payload.hint ?? payload.error ?? "Brain unavailable");
  }
  return payload;
}

function SearchMark({ text, query }: { text: string; query: string }) {
  if (!query.trim()) return text;
  const index = text.toLowerCase().indexOf(query.toLowerCase());
  if (index < 0) return text;
  return (
    <>
      {text.slice(0, index)}
      <mark>{text.slice(index, index + query.length)}</mark>
      {text.slice(index + query.length)}
    </>
  );
}

function EmptyState({
  title,
  copy,
}: {
  title: string;
  copy: string;
}) {
  return (
    <div className="empty-state">
      <span className="empty-orbit" aria-hidden="true" />
      <h3>{title}</h3>
      <p>{copy}</p>
    </div>
  );
}

function DecisionEditor({
  decision,
  mode,
  onClose,
  onSaved,
}: {
  decision: Decision;
  mode: "correct" | "supersede";
  onClose: () => void;
  onSaved: (uuid: string, message: string) => void;
}) {
  const [statement, setStatement] = useState(decision.statement);
  const [rationale, setRationale] = useState(decision.rationale);
  const [alternatives, setAlternatives] = useState(
    (decision.alternatives_rejected ?? []).join("\n"),
  );
  const [decidedAt, setDecidedAt] = useState(
    datetimeLocal(decision.decided_at),
  );
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const isCorrection = mode === "correct";

  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !saving) onClose();
    };
    document.addEventListener("keydown", closeOnEscape);
    return () => document.removeEventListener("keydown", closeOnEscape);
  }, [onClose, saving]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError("");
    const endpoint = isCorrection
      ? `/api/decisions/${decision.uuid}`
      : `/api/decisions/${decision.uuid}/supersede`;
    try {
      const payload = {
        statement,
        rationale,
        alternativesRejected: alternatives
          .split("\n")
          .map((item) => item.trim())
          .filter(Boolean),
        decidedAt: new Date(decidedAt).toISOString(),
        ...(isCorrection ? { editNote: note } : { reason: note }),
      };
      const response = await fetch(endpoint, {
        method: isCorrection ? "PATCH" : "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(payload),
      });
      const result = await response.json();
      if (!response.ok) {
        throw new Error(result.error ?? "The memory could not be saved.");
      }
      const updated = result.decision as Decision;
      onSaved(
        updated.uuid,
        isCorrection
          ? "Correction saved. The previous record remains in edit history."
          : "New ruling is current. The prior decision remains in its lineage.",
      );
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "The memory could not be saved.",
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="editor-backdrop" role="presentation">
      <section
        className="decision-editor"
        role="dialog"
        aria-modal="true"
        aria-labelledby="editor-title"
      >
        <header>
          <div>
            <span className="eyebrow">
              {isCorrection ? "Preserves a revision" : "Creates a lineage event"}
            </span>
            <h2 id="editor-title">
              {isCorrection ? "Correct this record" : "Supersede this decision"}
            </h2>
          </div>
          <button type="button" onClick={onClose} aria-label="Close editor">
            ×
          </button>
        </header>

        <div className="editor-context">
          <span>{decision.group_id}</span>
          <span>{decision.scope}</span>
          {decision.repo && <span>{decision.repo}</span>}
          <code>{decision.decision_key}</code>
        </div>

        <form onSubmit={submit}>
          <label className="field full">
            <span>{isCorrection ? "Canonical statement" : "New ruling"}</span>
            <textarea
              value={statement}
              onChange={(event) => setStatement(event.target.value)}
              rows={4}
              required
              autoFocus
            />
          </label>
          <label className="field full">
            <span>Rationale</span>
            <textarea
              value={rationale}
              onChange={(event) => setRationale(event.target.value)}
              rows={6}
            />
          </label>
          <label className="field full">
            <span>Rejected alternatives · one per line</span>
            <textarea
              value={alternatives}
              onChange={(event) => setAlternatives(event.target.value)}
              rows={4}
            />
          </label>
          <label className="field">
            <span>Decision time</span>
            <input
              type="datetime-local"
              value={decidedAt}
              onChange={(event) => setDecidedAt(event.target.value)}
              required
            />
          </label>
          <label className="field">
            <span>
              {isCorrection ? "Why is this being corrected?" : "Why is it changing?"}
            </span>
            <input
              value={note}
              onChange={(event) => setNote(event.target.value)}
              placeholder={
                isCorrection
                  ? "Fix typo, clarify rationale…"
                  : "New constraint, changed requirement…"
              }
              required
            />
          </label>

          <aside className={isCorrection ? "editor-note" : "editor-note warning"}>
            <strong>{isCorrection ? "Correction" : "Supersession"}</strong>
            <p>
              {isCorrection
                ? "The current node will be updated and its previous contents saved as an immutable revision."
                : "A new current decision will be created. This decision will remain searchable as superseded history."}
            </p>
          </aside>

          {error && <p className="editor-error">{error}</p>}

          <footer>
            <button type="button" className="button-quiet" onClick={onClose}>
              Cancel
            </button>
            <button
              type="submit"
              className={isCorrection ? "button-primary" : "button-supersede"}
              disabled={saving}
            >
              {saving
                ? "Writing memory…"
                : isCorrection
                  ? "Save correction"
                  : "Create new ruling"}
            </button>
          </footer>
        </form>
      </section>
    </div>
  );
}

type MapNode = {
  id: string;
  label: string;
  type: "decision" | "episode" | "entity";
  x: number;
  y: number;
  radius: number;
};

function hash(value: string) {
  let result = 0;
  for (let index = 0; index < value.length; index += 1) {
    result = (result * 31 + value.charCodeAt(index)) | 0;
  }
  return Math.abs(result);
}

function BrainMap({
  decisions,
  grounding,
  facts,
  group,
  onDecision,
}: {
  decisions: Decision[];
  grounding: Grounding[];
  facts: Fact[];
  group: string;
  onDecision: (uuid: string) => void;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const nodesRef = useRef<MapNode[]>([]);
  const [hovered, setHovered] = useState<MapNode | null>(null);

  const graph = useMemo(() => {
    const visibleFacts =
      group === "all" ? facts : facts.filter((fact) => fact.group_id === group);
    const visibleDecisions =
      group === "all"
        ? decisions
        : decisions.filter((decision) => decision.group_id === group);
    const visibleGrounding = grounding.filter(
      (item) =>
        visibleDecisions.some(
          (decision) => decision.uuid === item.decision_uuid,
        ) && (group === "all" || item.group_id === group),
    );
    return { visibleFacts, visibleDecisions, visibleGrounding };
  }, [decisions, facts, grounding, group]);

  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    const container = containerRef.current;
    if (!canvas || !container) return;
    const width = container.clientWidth;
    const height = Math.max(480, container.clientHeight);
    const ratio = window.devicePixelRatio || 1;
    canvas.width = width * ratio;
    canvas.height = height * ratio;
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;
    const context = canvas.getContext("2d");
    if (!context) return;
    context.scale(ratio, ratio);
    context.clearRect(0, 0, width, height);

    const nodeMap = new Map<string, MapNode>();
    const place = (
      id: string,
      label: string,
      type: MapNode["type"],
      column: number,
    ) => {
      if (nodeMap.has(id)) return;
      const seed = hash(id);
      const x =
        width * column +
        (((seed % 1000) / 1000) - 0.5) * Math.min(150, width * 0.16);
      const y = 58 + ((Math.floor(seed / 1000) % 1000) / 1000) * (height - 116);
      nodeMap.set(id, {
        id,
        label,
        type,
        x,
        y,
        radius: type === "decision" ? 8 : type === "episode" ? 5 : 3.5,
      });
    };

    graph.visibleDecisions.forEach((decision) =>
      place(decision.uuid, decision.decision_key, "decision", 0.18),
    );
    graph.visibleGrounding.forEach((item) =>
      place(item.episode_uuid, item.name, "episode", 0.49),
    );
    graph.visibleFacts.forEach((fact) => {
      place(fact.source_uuid, fact.source_name, "entity", 0.78);
      place(fact.target_uuid, fact.target_name, "entity", 0.78);
    });

    const edge = (sourceId: string, targetId: string, color: string) => {
      const source = nodeMap.get(sourceId);
      const target = nodeMap.get(targetId);
      if (!source || !target) return;
      context.beginPath();
      context.moveTo(source.x, source.y);
      context.lineTo(target.x, target.y);
      context.strokeStyle = color;
      context.lineWidth = 0.65;
      context.stroke();
    };

    graph.visibleGrounding.forEach((item) =>
      edge(item.decision_uuid, item.episode_uuid, "rgba(255, 194, 91, .25)"),
    );
    graph.visibleFacts.forEach((fact) =>
      edge(fact.source_uuid, fact.target_uuid, "rgba(126, 222, 182, .13)"),
    );

    const colors = {
      decision: "#d9ff66",
      episode: "#ffbf5b",
      entity: "#64d9b2",
    };
    nodeMap.forEach((node) => {
      const active = hovered?.id === node.id;
      context.beginPath();
      context.arc(node.x, node.y, active ? node.radius + 3 : node.radius, 0, Math.PI * 2);
      context.fillStyle = colors[node.type];
      context.shadowColor = colors[node.type];
      context.shadowBlur = active ? 18 : node.type === "decision" ? 9 : 4;
      context.fill();
      context.shadowBlur = 0;
    });
    nodesRef.current = Array.from(nodeMap.values());
  }, [graph, hovered]);

  useEffect(() => {
    draw();
    const observer = new ResizeObserver(draw);
    if (containerRef.current) observer.observe(containerRef.current);
    return () => observer.disconnect();
  }, [draw]);

  function findNode(event: React.PointerEvent<HTMLCanvasElement>) {
    const rect = event.currentTarget.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;
    return (
      nodesRef.current.find(
        (node) => Math.hypot(node.x - x, node.y - y) <= node.radius + 7,
      ) ?? null
    );
  }

  return (
    <div className="map-shell" ref={containerRef}>
      <canvas
        ref={canvasRef}
        aria-label="Knowledge graph showing decisions, source episodes, and entities"
        onPointerMove={(event) => setHovered(findNode(event))}
        onPointerLeave={() => setHovered(null)}
        onClick={(event) => {
          const node = findNode(event);
          if (node?.type === "decision") onDecision(node.id);
        }}
      />
      <div className="map-labels" aria-hidden="true">
        <span>Decisions</span>
        <span>Evidence</span>
        <span>Entities</span>
      </div>
      <div className="map-legend">
        <span><i className="legend-dot decision-dot" /> Decision</span>
        <span><i className="legend-dot evidence-dot" /> Episode</span>
        <span><i className="legend-dot entity-dot" /> Entity</span>
      </div>
      {hovered && (
        <div className="map-tooltip">
          <span>{hovered.type}</span>
          <strong>{clip(hovered.label, 54)}</strong>
        </div>
      )}
    </div>
  );
}

export function BrainDashboard() {
  const [data, setData] = useState<BrainData | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [view, setView] = useState<View>("decisions");
  const [query, setQuery] = useState("");
  const [group, setGroup] = useState("all");
  const [status, setStatus] = useState<"current" | "all">("current");
  const [asOf, setAsOf] = useState("");
  const [selectedUuid, setSelectedUuid] = useState("");
  const [editorMode, setEditorMode] = useState<
    "correct" | "supersede" | null
  >(null);
  const [toast, setToast] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const payload = await fetchBrain();
      setData(payload);
      setSelectedUuid((current) => current || payload.decisions[0]?.uuid || "");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Brain unavailable");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let active = true;
    fetchBrain()
      .then((payload) => {
        if (!active) return;
        setData(payload);
        setSelectedUuid(payload.decisions[0]?.uuid || "");
      })
      .catch((reason) => {
        if (!active) return;
        setError(reason instanceof Error ? reason.message : "Brain unavailable");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const filtered = useMemo(() => {
    if (!data) return [];
    const normalized = query.trim().toLowerCase();
    const cutoff = asOf ? new Date(`${asOf}T23:59:59`).getTime() : null;
    return data.decisions.filter((decision) => {
      if (group !== "all" && decision.group_id !== group) return false;
      if (status === "current" && !cutoff && decision.status !== "live") return false;
      if (cutoff && new Date(decision.decided_at).getTime() > cutoff) return false;
      if (
        cutoff &&
        decision.superseded_at &&
        new Date(decision.superseded_at).getTime() <= cutoff
      ) {
        return false;
      }
      if (!normalized) return true;
      return [
        decision.statement,
        decision.rationale,
        decision.decision_key,
        decision.repo,
        decision.group_id,
        ...(decision.alternatives_rejected ?? []),
      ].some((value) => value?.toLowerCase().includes(normalized));
    });
  }, [asOf, data, group, query, status]);

  const selected =
    filtered.find((decision) => decision.uuid === selectedUuid) ??
    data?.decisions.find((decision) => decision.uuid === selectedUuid) ??
    filtered[0];
  const evidence =
    data?.grounding.filter((item) => item.decision_uuid === selected?.uuid) ?? [];
  const older =
    data?.supersedes.find((item) => item.newer_uuid === selected?.uuid)?.older_uuid;
  const newer =
    data?.supersedes.find((item) => item.older_uuid === selected?.uuid)?.newer_uuid;
  const revisions =
    data?.revisions
      .filter((item) => item.decision_uuid === selected?.uuid)
      .map((item) => item.revision) ?? [];

  const selectDecision = (uuid: string) => {
    setSelectedUuid(uuid);
    setView("decisions");
  };

  const saved = async (uuid: string, message: string) => {
    setEditorMode(null);
    await load();
    setSelectedUuid(uuid);
    setStatus("all");
    setToast(message);
    window.setTimeout(() => setToast(""), 5_000);
  };

  return (
    <main className="brain-app">
      <aside className="rail">
        <a className="brand" href="#" aria-label="Hive Mind home">
          <span className="brand-mark" aria-hidden="true">
            <i />
            <i />
            <i />
          </span>
          <span>
            HIVE <b>/</b> MIND
          </span>
        </a>

        <nav aria-label="Brain sections">
          {NAV.map((item, index) => (
            <button
              key={item.id}
              className={view === item.id ? "nav-item active" : "nav-item"}
              onClick={() => setView(item.id)}
            >
              <span className="nav-index">0{index + 1}</span>
              <span>
                <strong>{item.label}</strong>
                <small>{item.eyebrow}</small>
              </span>
            </button>
          ))}
        </nav>

        <div className="rail-status">
          <span className={data?.connected ? "pulse live" : "pulse"} />
          <div>
            <strong>{data?.connected ? "Brain online" : "Brain offline"}</strong>
            <small>
              {data
                ? `Synced ${relativeDate(data.refreshedAt)}`
                : "Waiting for Neo4j"}
            </small>
          </div>
          <button onClick={load} aria-label="Refresh brain data">
            ↻
          </button>
        </div>
      </aside>

      <section className="workspace">
        <header className="topbar">
          <div className="mobile-brand">HIVE / MIND</div>
          <label className="search">
            <span aria-hidden="true">⌕</span>
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search decisions, rationale, rejected paths…"
              aria-label="Search project memory"
            />
            <kbd>⌘ K</kbd>
          </label>
          <button className="connection-pill" onClick={load}>
            <span className={data?.connected ? "pulse live" : "pulse"} />
            {data?.connected ? "Live graph" : "Disconnected"}
          </button>
        </header>

        {loading && (
          <div className="loading-state" role="status">
            <span className="loader" />
            <p>Reading the graph…</p>
          </div>
        )}

        {!loading && error && (
          <div className="connection-error">
            <div className="error-code">NO SIGNAL</div>
            <h1>The brain is there. The viewer can’t reach it.</h1>
            <p>{error}</p>
            <button onClick={load}>Try the connection again</button>
            <code>docker compose up -d</code>
          </div>
        )}

        {!loading && data && (
          <>
            <section className="hero">
              <div className="hero-copy">
                <span className="eyebrow">Long-term project memory</span>
                <h1>
                  Decisions,
                  <br />
                  <em>with receipts.</em>
                </h1>
                <p>
                  See what the team decided, when it changed, and which source
                  made it true.
                </p>
              </div>
              <div className="hero-vitals">
                <div className="vital primary">
                  <span>Canonical decisions</span>
                  <strong>{data.stats.decision_count.toLocaleString()}</strong>
                  <small>{data.stats.live_count} currently authoritative</small>
                </div>
                <div className="vital">
                  <span>Source episodes</span>
                  <strong>{data.stats.episode_count.toLocaleString()}</strong>
                  <small>Meetings and captured context</small>
                </div>
                <div className="vital">
                  <span>Known facts</span>
                  <strong>{data.stats.fact_count.toLocaleString()}</strong>
                  <small>Across {data.stats.entity_count.toLocaleString()} entities</small>
                </div>
              </div>
            </section>

            <section className="control-deck">
              <div className="view-heading">
                <span className="section-number">
                  0{NAV.findIndex((item) => item.id === view) + 1}
                </span>
                <div>
                  <h2>{NAV.find((item) => item.id === view)?.label}</h2>
                  <p>{NAV.find((item) => item.id === view)?.eyebrow}</p>
                </div>
              </div>
              <div className="filters">
                <label>
                  <span>Scope</span>
                  <select
                    value={group}
                    onChange={(event) => setGroup(event.target.value)}
                  >
                    <option value="all">All projects</option>
                    {data.scopes.map((scope) => (
                      <option value={scope.group_id} key={scope.group_id}>
                        {scope.group_id}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  <span>State</span>
                  <select
                    value={status}
                    onChange={(event) =>
                      setStatus(event.target.value as "current" | "all")
                    }
                  >
                    <option value="current">Current only</option>
                    <option value="all">All history</option>
                  </select>
                </label>
                <label>
                  <span>Memory as of</span>
                  <input
                    type="date"
                    value={asOf}
                    onChange={(event) => setAsOf(event.target.value)}
                  />
                </label>
                {asOf && (
                  <button className="clear-date" onClick={() => setAsOf("")}>
                    Return to now
                  </button>
                )}
              </div>
            </section>

            {view === "decisions" && (
              <section className="decision-layout">
                <div className="decision-list">
                  <div className="list-meta">
                    <span>{filtered.length} records</span>
                    <span>Newest first</span>
                  </div>
                  {filtered.map((decision) => (
                    <button
                      className={
                        decision.uuid === selected?.uuid
                          ? "decision-card selected"
                          : "decision-card"
                      }
                      key={decision.uuid}
                      onClick={() => setSelectedUuid(decision.uuid)}
                    >
                      <div className="decision-card-top">
                        <span className={`status ${decision.status}`}>
                          {decision.status === "live" ? "Current" : "Superseded"}
                        </span>
                        <time>{shortDate(decision.decided_at)}</time>
                      </div>
                      <h3>
                        <SearchMark text={decision.statement} query={query} />
                      </h3>
                      <div className="decision-tags">
                        <span>{decision.group_id}</span>
                        <span>{decision.scope}</span>
                        {decision.repo && <span>{decision.repo}</span>}
                      </div>
                    </button>
                  ))}
                  {filtered.length === 0 && (
                    <EmptyState
                      title="No memory at this coordinate"
                      copy="Try another scope, date, or search phrase."
                    />
                  )}
                </div>

                {selected && (
                  <article className="decision-detail">
                    <div className="detail-kicker">
                      <span>{selected.decision_key}</span>
                      <div>
                        <button onClick={() => setEditorMode("correct")}>
                          Correct record
                        </button>
                        <button
                          onClick={() =>
                            navigator.clipboard.writeText(selected.uuid)
                          }
                        >
                          Copy ID
                        </button>
                      </div>
                    </div>
                    <h2>{selected.statement}</h2>
                    <dl className="detail-facts">
                      <div>
                        <dt>Decided</dt>
                        <dd>{shortDate(selected.decided_at)}</dd>
                      </div>
                      <div>
                        <dt>Captured</dt>
                        <dd>{shortDate(selected.recorded_at)}</dd>
                      </div>
                      <div>
                        <dt>Authority</dt>
                        <dd>{selected.confirmed_by ?? "System record"}</dd>
                      </div>
                      <div>
                        <dt>Source</dt>
                        <dd>{selected.source ?? "Explicit"}</dd>
                      </div>
                    </dl>

                    <div className="memory-actions">
                      <div>
                        <strong>Manage canonical memory</strong>
                        <span>
                          Corrections preserve revisions. Changed rulings preserve
                          lineage.
                        </span>
                      </div>
                      <button onClick={() => setEditorMode("correct")}>
                        Correct record
                      </button>
                      {selected.status === "live" && (
                        <button
                          className="supersede-button"
                          onClick={() => setEditorMode("supersede")}
                        >
                          Supersede ruling
                        </button>
                      )}
                    </div>

                    <div className="detail-section">
                      <span className="detail-label">Why this won</span>
                      <p>{selected.rationale}</p>
                    </div>

                    <div className="detail-section">
                      <span className="detail-label">Paths not taken</span>
                      {selected.alternatives_rejected?.length ? (
                        <ol className="alternatives">
                          {selected.alternatives_rejected.map((alternative) => (
                            <li key={alternative}>{alternative}</li>
                          ))}
                        </ol>
                      ) : (
                        <p className="muted">No rejected alternatives recorded.</p>
                      )}
                    </div>

                    {(older || newer) && (
                      <div className="lineage-strip">
                        <span>Lineage</span>
                        {newer && (
                          <button onClick={() => setSelectedUuid(newer)}>
                            View newer ruling →
                          </button>
                        )}
                        {older && (
                          <button onClick={() => setSelectedUuid(older)}>
                            View decision this replaced →
                          </button>
                        )}
                      </div>
                    )}

                    {revisions.length > 0 && (
                      <div className="detail-section revision-section">
                        <span className="detail-label">
                          Edit history <b>{revisions.length}</b>
                        </span>
                        {revisions.map((revision) => (
                          <details className="revision-card" key={revision.uuid}>
                            <summary>
                              <span>
                                Corrected {shortDate(revision.edited_at)}
                              </span>
                              <strong>{revision.edit_note}</strong>
                              <i>View previous record</i>
                            </summary>
                            <div>
                              <h4>{revision.statement}</h4>
                              <p>{revision.rationale}</p>
                              <small>
                                Previously effective{" "}
                                {shortDate(revision.decided_at)}
                              </small>
                            </div>
                          </details>
                        ))}
                      </div>
                    )}

                    <div className="detail-section evidence-section">
                      <span className="detail-label">
                        Evidence <b>{evidence.length}</b>
                      </span>
                      {evidence.length ? (
                        evidence.map((item) => (
                          <div className="evidence-card" key={item.episode_uuid}>
                            <div>
                              <span>{item.group_id}</span>
                              <time>{shortDate(item.valid_at)}</time>
                            </div>
                            <strong>{item.name}</strong>
                            <p>{clip(item.excerpt, 280)}</p>
                            <small>{item.source}</small>
                          </div>
                        ))
                      ) : (
                        <div className="evidence-empty">
                          <span aria-hidden="true">◎</span>
                          <p>
                            This ruling is canonical, but no meeting episode is
                            linked as supporting evidence yet.
                          </p>
                        </div>
                      )}
                    </div>
                  </article>
                )}
              </section>
            )}

            {view === "timeline" && (
              <section className="timeline">
                {filtered.map((decision, index) => (
                  <article key={decision.uuid} className="timeline-row">
                    <div className="timeline-date">
                      <span>{shortDate(decision.decided_at).split(",")[0]}</span>
                      <small>{new Date(decision.decided_at).getFullYear()}</small>
                    </div>
                    <div className="timeline-axis">
                      <i />
                      {index < filtered.length - 1 && <b />}
                    </div>
                    <button onClick={() => selectDecision(decision.uuid)}>
                      <div>
                        <span className={`status ${decision.status}`}>
                          {decision.status}
                        </span>
                        <span>{decision.decision_key}</span>
                      </div>
                      <h3>{decision.statement}</h3>
                      <p>{clip(decision.rationale, 220)}</p>
                      <footer>
                        <span>{decision.group_id}</span>
                        {decision.recorded_at !== decision.decided_at && (
                          <span>
                            captured {relativeDate(decision.recorded_at)}
                          </span>
                        )}
                        <b>Inspect ruling →</b>
                      </footer>
                    </button>
                  </article>
                ))}
                {filtered.length === 0 && (
                  <EmptyState
                    title="No decisions existed then"
                    copy="Move the as-of date forward or clear the current filters."
                  />
                )}
              </section>
            )}

            {view === "map" && (
              <section className="map-view">
                <div className="map-intro">
                  <p>
                    A live sample of canonical decisions, meeting evidence, and
                    extracted entity relationships. Click a lime node to inspect
                    its ruling.
                  </p>
                  <div>
                    <strong>{data.stats.entity_count.toLocaleString()}</strong>
                    <span>entities in the full graph</span>
                  </div>
                </div>
                <BrainMap
                  decisions={data.decisions}
                  grounding={data.grounding}
                  facts={data.facts}
                  group={group}
                  onDecision={selectDecision}
                />
              </section>
            )}

            {view === "sources" && (
              <section className="sources-grid">
                {(group === "all"
                  ? data.episodes
                  : data.episodes.filter((episode) => episode.group_id === group)
                ).map((episode) => (
                  <article className="source-card" key={episode.uuid}>
                    <div className="source-card-top">
                      <span>{episode.group_id}</span>
                      <time>{shortDate(episode.valid_at)}</time>
                    </div>
                    <h3>{episode.name}</h3>
                    <p>{clip(episode.excerpt, 360)}</p>
                    <footer>
                      <span>{episode.source}</span>
                      <code>{episode.uuid.slice(0, 8)}</code>
                    </footer>
                  </article>
                ))}
              </section>
            )}

            <footer className="page-footer">
              <span>
                Temporal editor for the canonical Neo4j decision graph
              </span>
              <span>
                Last refresh {new Date(data.refreshedAt).toLocaleTimeString()}
              </span>
            </footer>
          </>
        )}
      </section>
      {selected && editorMode && (
        <DecisionEditor
          key={`${selected.uuid}:${editorMode}`}
          decision={selected}
          mode={editorMode}
          onClose={() => setEditorMode(null)}
          onSaved={saved}
        />
      )}
      {toast && (
        <div className="save-toast" role="status">
          <span>✓</span>
          {toast}
          <button onClick={() => setToast("")} aria-label="Dismiss notification">
            ×
          </button>
        </div>
      )}
    </main>
  );
}
