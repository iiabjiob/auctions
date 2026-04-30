-- Diagnostic: inspect top-rated active lots with score dimensions and cap reasons.
-- Intended for PostgreSQL. Adjust source/status filters for a specific marketplace run.

WITH top_lots AS (
    SELECT
        id,
        source_code,
        auction_number,
        lot_number,
        lot_name,
        status,
        rating_score,
        rating_level,
        scoring_version,
        scored_at,
        score_breakdown,
        datagrid_row
    FROM auction_lot_records
    WHERE rating_score >= 70
      AND lower(coalesce(status, '')) NOT LIKE '%отмен%'
      AND lower(coalesce(status, '')) NOT LIKE '%заверш%'
    ORDER BY rating_score DESC, scored_at DESC NULLS LAST, id DESC
    LIMIT 100
),
cap_reasons AS (
    SELECT
        top_lots.id,
        jsonb_agg(
            jsonb_build_object(
                'key', cap.value ->> 'key',
                'max_score', cap.value ->> 'max_score',
                'reason', cap.value ->> 'reason'
            )
            ORDER BY cap.value ->> 'key'
        ) FILTER (WHERE cap.value IS NOT NULL) AS caps
    FROM top_lots
    LEFT JOIN LATERAL jsonb_array_elements(coalesce(top_lots.score_breakdown -> 'caps', '[]'::jsonb)) AS cap(value) ON TRUE
    GROUP BY top_lots.id
)
SELECT
    top_lots.id,
    top_lots.source_code,
    top_lots.auction_number,
    top_lots.lot_number,
    top_lots.lot_name,
    top_lots.status,
    top_lots.rating_score,
    top_lots.rating_level,
    top_lots.scoring_version,
    top_lots.scored_at,
    top_lots.score_breakdown ->> 'raw_score' AS raw_score,
    top_lots.score_breakdown -> 'dimensions' -> 'economics' ->> 'weighted_score' AS economics_score,
    top_lots.score_breakdown -> 'dimensions' -> 'owner_fit' ->> 'weighted_score' AS owner_fit_score,
    top_lots.score_breakdown -> 'dimensions' -> 'risk' ->> 'weighted_score' AS risk_score,
    coalesce(cap_reasons.caps, '[]'::jsonb) AS caps,
    top_lots.datagrid_row -> 'analysis' ->> 'legal_risk' AS legal_risk,
    top_lots.datagrid_row -> 'analysis' ->> 'status' AS analysis_status,
    top_lots.datagrid_row -> 'rating' -> 'reasons' AS rating_reasons
FROM top_lots
LEFT JOIN cap_reasons ON cap_reasons.id = top_lots.id
ORDER BY top_lots.rating_score DESC, top_lots.id DESC;

-- Diagnostic: suspicious rows that are highly ranked despite risk/cap indicators.
SELECT
    id,
    source_code,
    auction_number,
    lot_number,
    lot_name,
    rating_score,
    rating_level,
    datagrid_row -> 'analysis' ->> 'legal_risk' AS legal_risk,
    score_breakdown -> 'caps' AS caps,
    score_breakdown -> 'dimensions' -> 'risk' AS risk_dimension
FROM auction_lot_records
WHERE rating_score >= 70
  AND (
      datagrid_row -> 'analysis' ->> 'legal_risk' = 'high'
      OR jsonb_array_length(coalesce(score_breakdown -> 'caps', '[]'::jsonb)) > 0
  )
ORDER BY rating_score DESC, id DESC
LIMIT 100;
