type Neo4jResult = {
  columns: string[];
  data: Array<{ row: unknown[] }>;
};

type Neo4jResponse = {
  results: Neo4jResult[];
  errors: Array<{ code: string; message: string }>;
};

export type Neo4jStatement = {
  statement: string;
  parameters?: Record<string, unknown>;
};

export class Neo4jQueryError extends Error {
  code: string;

  constructor(code: string, message: string) {
    super(message);
    this.name = "Neo4jQueryError";
    this.code = code;
  }
}

export function rows(result: Neo4jResult): Record<string, unknown>[] {
  return result.data.map(({ row }) =>
    Object.fromEntries(result.columns.map((column, index) => [column, row[index]])),
  );
}

export async function runNeo4j(
  statements: Neo4jStatement[],
): Promise<Neo4jResult[]> {
  const endpoint =
    process.env.NEO4J_HTTP_URL ??
    "http://localhost:7474";
  const user = process.env.NEO4J_USER ?? "neo4j";
  const password = process.env.NEO4J_PASSWORD ?? "hive-mind-local-password";
  const token = btoa(`${user}:${password}`);

  const response = await fetch(`${endpoint}/db/neo4j/tx/commit`, {
    method: "POST",
    headers: {
      authorization: `Basic ${token}`,
      "content-type": "application/json",
    },
    body: JSON.stringify({
      statements: statements.map((entry) => ({
        ...entry,
        resultDataContents: ["row"],
      })),
    }),
    cache: "no-store",
    signal: AbortSignal.timeout(10_000),
  });

  if (!response.ok) {
    throw new Error(`Neo4j returned HTTP ${response.status}`);
  }

  const payload = (await response.json()) as Neo4jResponse;
  if (payload.errors.length > 0) {
    const error = payload.errors[0];
    throw new Neo4jQueryError(error.code, error.message);
  }
  return payload.results;
}

export function rejectCrossOrigin(request: Request): Response | null {
  const origin = request.headers.get("origin");
  if (!origin) return null;
  try {
    if (new URL(origin).host !== new URL(request.url).host) {
      return Response.json(
        { error: "Cross-origin memory writes are not allowed." },
        { status: 403 },
      );
    }
  } catch {
    return Response.json({ error: "Invalid request origin." }, { status: 403 });
  }
  return null;
}
