import {
  Neo4jQueryError,
  rejectCrossOrigin,
  rows,
  runNeo4j,
} from "../../../../lib/neo4j";

export const dynamic = "force-dynamic";

type Correction = {
  statement?: unknown;
  rationale?: unknown;
  alternativesRejected?: unknown;
  decidedAt?: unknown;
  editNote?: unknown;
};

function text(value: unknown, name: string, max: number, required = true) {
  if (typeof value !== "string") {
    throw new Error(`${name} must be text.`);
  }
  const cleaned = value.trim();
  if (required && !cleaned) throw new Error(`${name} is required.`);
  if (cleaned.length > max) throw new Error(`${name} is too long.`);
  return cleaned;
}

function timestamp(value: unknown) {
  const cleaned = text(value, "Decision time", 80);
  const parsed = new Date(cleaned);
  if (Number.isNaN(parsed.getTime())) {
    throw new Error("Decision time must be a valid date.");
  }
  return parsed.toISOString().replace(".000Z", "Z");
}

function alternatives(value: unknown) {
  if (!Array.isArray(value) || value.length > 30) {
    throw new Error("Rejected alternatives must be a list of at most 30 items.");
  }
  return value.map((item) => text(item, "Rejected alternative", 4_000));
}

export async function PATCH(
  request: Request,
  context: { params: Promise<{ uuid: string }> },
) {
  const originError = rejectCrossOrigin(request);
  if (originError) return originError;

  try {
    const { uuid } = await context.params;
    const body = (await request.json()) as Correction;
    const now = new Date().toISOString().replace(".000Z", "Z");
    const parameters = {
      uuid,
      statement: text(body.statement, "Statement", 12_000),
      rationale: text(body.rationale, "Rationale", 32_000, false),
      alternatives: alternatives(body.alternativesRejected),
      decidedAt: timestamp(body.decidedAt),
      editNote: text(body.editNote, "Correction note", 2_000),
      now,
    };
    const [result] = await runNeo4j([
      {
        statement: `
          MATCH (d:Decision {uuid: $uuid})
          CREATE (r:DecisionRevision {
            uuid: randomUUID(),
            decision_uuid: d.uuid,
            group_id: d.group_id,
            scope: d.scope,
            repo: d.repo,
            decision_key: d.decision_key,
            statement: d.statement,
            rationale: d.rationale,
            alternatives_rejected: d.alternatives_rejected,
            decided_at: d.decided_at,
            status: d.status,
            edited_at: $now,
            edit_note: $editNote
          })
          CREATE (d)-[:HAS_REVISION]->(r)
          SET d.statement = $statement,
              d.rationale = $rationale,
              d.alternatives_rejected = $alternatives,
              d.decided_at = $decidedAt,
              d.updated_at = $now,
              d.revision_count = coalesce(d.revision_count, 0) + 1
          REMOVE d.grounding_attempted_at
          RETURN properties(d) AS decision, properties(r) AS revision
        `,
        parameters,
      },
    ]);
    const updated = rows(result)[0];
    if (!updated) {
      return Response.json({ error: "Decision not found." }, { status: 404 });
    }
    return Response.json(updated);
  } catch (error) {
    const status = error instanceof Neo4jQueryError ? 409 : 400;
    return Response.json(
      { error: error instanceof Error ? error.message : "Correction failed." },
      { status },
    );
  }
}
