import {
  Neo4jQueryError,
  rejectCrossOrigin,
  rows,
  runNeo4j,
} from "../../../../../lib/neo4j";

export const dynamic = "force-dynamic";

type Replacement = {
  statement?: unknown;
  rationale?: unknown;
  alternativesRejected?: unknown;
  decidedAt?: unknown;
  reason?: unknown;
};

function requiredText(value: unknown, name: string, max: number) {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} is required.`);
  }
  const cleaned = value.trim();
  if (cleaned.length > max) throw new Error(`${name} is too long.`);
  return cleaned;
}

function optionalText(value: unknown, name: string, max: number) {
  if (typeof value !== "string") throw new Error(`${name} must be text.`);
  const cleaned = value.trim();
  if (cleaned.length > max) throw new Error(`${name} is too long.`);
  return cleaned;
}

function timestamp(value: unknown) {
  const parsed = new Date(requiredText(value, "Decision time", 80));
  if (Number.isNaN(parsed.getTime())) {
    throw new Error("Decision time must be a valid date.");
  }
  return parsed.toISOString().replace(".000Z", "Z");
}

function alternatives(value: unknown) {
  if (!Array.isArray(value) || value.length > 30) {
    throw new Error("Rejected alternatives must be a list of at most 30 items.");
  }
  return value.map((item) =>
    requiredText(item, "Rejected alternative", 4_000),
  );
}

export async function POST(
  request: Request,
  context: { params: Promise<{ uuid: string }> },
) {
  const originError = rejectCrossOrigin(request);
  if (originError) return originError;

  try {
    const { uuid } = await context.params;
    const body = (await request.json()) as Replacement;
    const now = new Date().toISOString().replace(".000Z", "Z");
    const newUuid = crypto.randomUUID();
    const parameters = {
      oldUuid: uuid,
      newUuid,
      statement: requiredText(body.statement, "New ruling", 12_000),
      rationale: optionalText(body.rationale, "Rationale", 32_000),
      alternatives: alternatives(body.alternativesRejected),
      decidedAt: timestamp(body.decidedAt),
      reason: requiredText(body.reason, "Supersession reason", 2_000),
      confirmedBy: process.env.HIVE_MIND_ACTOR ?? "web-user",
      now,
    };
    const [result] = await runNeo4j([
      {
        statement: `
          MATCH (old:Decision {uuid: $oldUuid, status: 'live'})
          MATCH (topic:DecisionTopic {
            group_id: old.group_id,
            scope: old.scope,
            repo_key: coalesce(old.repo, ''),
            decision_key: old.decision_key
          })-[current:CURRENT]->(old)
          DELETE current
          CREATE (replacement:Decision {
            uuid: $newUuid,
            decision_key: old.decision_key,
            statement: $statement,
            rationale: $rationale,
            alternatives_rejected: $alternatives,
            scope: old.scope,
            group_id: old.group_id,
            repo: old.repo,
            status: 'live',
            decided_at: $decidedAt,
            recorded_at: $now,
            source: 'explicit',
            confirmed_by: $confirmedBy
          })
          SET old.status = 'superseded',
              old.superseded_at = $now
          CREATE (topic)-[:CURRENT]->(replacement)
          CREATE (replacement)-[edge:SUPERSEDES]->(old)
          SET edge.reason = $reason,
              edge.at = $now,
              edge.recorded_at = $now
          RETURN properties(replacement) AS decision
        `,
        parameters,
      },
    ]);
    const updated = rows(result)[0];
    if (!updated) {
      return Response.json(
        { error: "Decision is missing, already superseded, or not current." },
        { status: 409 },
      );
    }
    return Response.json(updated);
  } catch (error) {
    const status = error instanceof Neo4jQueryError ? 409 : 400;
    return Response.json(
      { error: error instanceof Error ? error.message : "Supersession failed." },
      { status },
    );
  }
}
