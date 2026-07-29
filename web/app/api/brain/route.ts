export const dynamic = "force-dynamic";

import { rows, runNeo4j } from "../../../lib/neo4j";

const statements = [
  {
    statement: `
      CALL {
        MATCH (d:Decision)
        RETURN count(d) AS decision_count,
          count(CASE WHEN d.status = 'live' THEN 1 END) AS live_count,
          count(CASE WHEN d.status = 'superseded' THEN 1 END) AS superseded_count,
          count(CASE WHEN EXISTS { MATCH (d)-[:GROUNDED_IN]->() }
            THEN 1 END) AS grounded_count
      }
      CALL { MATCH (e:Episodic) RETURN count(e) AS episode_count }
      CALL { MATCH (e:Entity) RETURN count(e) AS entity_count }
      CALL { MATCH ()-[r:RELATES_TO]->() RETURN count(r) AS fact_count }
      RETURN decision_count, live_count, superseded_count, grounded_count,
        episode_count, entity_count, fact_count
    `,
  },
  {
    statement: `
      MATCH (n)
      WHERE (n:Decision OR n:Episodic) AND n.group_id IS NOT NULL
      RETURN n.group_id AS group_id,
        count(CASE WHEN n:Decision THEN 1 END) AS decisions,
        count(CASE WHEN n:Episodic THEN 1 END) AS episodes
      ORDER BY decisions DESC, episodes DESC
    `,
  },
  {
    statement: `
      MATCH (d:Decision)
      RETURN properties(d) AS decision
      ORDER BY d.decided_at DESC
    `,
  },
  {
    statement: `
      MATCH (d:Decision)-[:GROUNDED_IN]->(e:Episodic)
      RETURN d.uuid AS decision_uuid,
        e.uuid AS episode_uuid,
        e.name AS name,
        e.group_id AS group_id,
        e.source_description AS source,
        toString(e.valid_at) AS valid_at,
        left(e.content, 1200) AS excerpt
      ORDER BY e.valid_at DESC
    `,
  },
  {
    statement: `
      MATCH (newer:Decision)-[:SUPERSEDES]->(older:Decision)
      RETURN newer.uuid AS newer_uuid, older.uuid AS older_uuid
    `,
  },
  {
    statement: `
      MATCH (a:Entity)-[r:RELATES_TO]->(b:Entity)
      RETURN a.uuid AS source_uuid, a.name AS source_name,
        b.uuid AS target_uuid, b.name AS target_name,
        r.uuid AS fact_uuid, r.fact AS fact, r.name AS relation,
        r.group_id AS group_id, toString(r.valid_at) AS valid_at
      ORDER BY r.valid_at DESC
      LIMIT 140
    `,
  },
  {
    statement: `
      MATCH (e:Episodic)
      RETURN e.uuid AS uuid, e.name AS name, e.group_id AS group_id,
        e.source_description AS source, toString(e.valid_at) AS valid_at,
        left(e.content, 700) AS excerpt
      ORDER BY e.valid_at DESC
      LIMIT 48
    `,
  },
  {
    statement: `
      MATCH (d:Decision)-[:HAS_REVISION]->(r:DecisionRevision)
      RETURN d.uuid AS decision_uuid, properties(r) AS revision
      ORDER BY r.edited_at DESC
    `,
  },
];

export async function GET() {
  try {
    const [
      statsResult,
      scopesResult,
      decisionsResult,
      groundingResult,
      supersedesResult,
      factsResult,
      episodesResult,
      revisionsResult,
    ] = await runNeo4j(statements);

    return Response.json(
      {
        connected: true,
        refreshedAt: new Date().toISOString(),
        stats: rows(statsResult)[0] ?? {},
        scopes: rows(scopesResult),
        decisions: rows(decisionsResult).map((row) => row.decision),
        grounding: rows(groundingResult),
        supersedes: rows(supersedesResult),
        facts: rows(factsResult),
        episodes: rows(episodesResult),
        revisions: rows(revisionsResult),
      },
      {
        headers: {
          "cache-control": "no-store",
        },
      },
    );
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Unknown Neo4j connection error";
    return Response.json(
      {
        connected: false,
        error: message,
        hint: "Start the local Neo4j container and reload this page.",
      },
      { status: 503, headers: { "cache-control": "no-store" } },
    );
  }
}
