-- ============================================================================
-- DATABASE RECOVERY SCRIPT
-- Purpose: Reset all node labels to semantic_label and clear taxonomy data
-- Run this after the taxonomy pipeline corrupted node labels
-- ============================================================================

BEGIN;

-- ============================================================================
-- STEP 1: Reset all node labels to semantic_label
-- ============================================================================
-- For nodes where semantic_label exists and is different from label
UPDATE nodes
SET label = semantic_label
WHERE semantic_label IS NOT NULL
  AND semantic_label != ''
  AND label != semantic_label;

-- Log how many nodes were updated
DO $$
DECLARE
    updated_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO updated_count
    FROM nodes
    WHERE semantic_label IS NOT NULL
      AND semantic_label != ''
      AND label = semantic_label;  -- Now they match after update
    
    RAISE NOTICE 'Updated % node labels to match semantic_label', updated_count;
END $$;


-- ============================================================================
-- STEP 2: Delete all taxonomy classifications
-- ============================================================================
-- Delete all automated taxonomy links (keep manual if any exist)
DELETE FROM node_taxonomy_links 
WHERE source IN ('llm_guided', 'beam_search', 'probationary', 'placeholder', 'path_corrected', 'approved_suggestion');

-- Log how many links were deleted
DO $$
DECLARE
    deleted_count INTEGER;
BEGIN
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RAISE NOTICE 'Deleted % taxonomy links', deleted_count;
END $$;


-- ============================================================================
-- STEP 3: Clear pending suggestions
-- ============================================================================
-- Delete all pending suggestions
DELETE FROM taxonomy_suggestions_review 
WHERE status = 'pending';

-- Log how many suggestions were deleted
DO $$
DECLARE
    deleted_count INTEGER;
BEGIN
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RAISE NOTICE 'Deleted % pending suggestions', deleted_count;
END $$;


-- ============================================================================
-- STEP 4: Clear pending node reviews
-- ============================================================================
-- Delete all pending node reviews
DELETE FROM node_taxonomy_review_queue 
WHERE status = 'pending';

-- Log how many reviews were deleted
DO $$
DECLARE
    deleted_count INTEGER;
BEGIN
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RAISE NOTICE 'Deleted % pending reviews', deleted_count;
END $$;


-- ============================================================================
-- STEP 5: Verification queries
-- ============================================================================
-- Count remaining taxonomy links
SELECT 
    COUNT(*) as remaining_taxonomy_links,
    COUNT(DISTINCT node_id) as classified_nodes
FROM node_taxonomy_links;

-- Count nodes with different label vs semantic_label
SELECT 
    COUNT(*) as mismatched_labels
FROM nodes
WHERE semantic_label IS NOT NULL
  AND semantic_label != ''
  AND label != semantic_label;

-- Count pending items
SELECT 
    (SELECT COUNT(*) FROM taxonomy_suggestions_review WHERE status = 'pending') as pending_suggestions,
    (SELECT COUNT(*) FROM node_taxonomy_review_queue WHERE status = 'pending') as pending_reviews;

-- Show sample of nodes before/after
SELECT 
    id,
    label,
    semantic_label,
    node_type,
    LEFT(original_sentence, 50) as sentence_sample
FROM nodes
WHERE semantic_label IS NOT NULL
LIMIT 10;

COMMIT;

-- ============================================================================
-- DIAGNOSTIC: Check for nodes with NULL semantic_label
-- ============================================================================
-- Run this AFTER the main transaction to see if any nodes need special handling
SELECT 
    node_type,
    COUNT(*) as count_with_null_semantic_label,
    COUNT(*) FILTER (WHERE label = node_type) as count_where_label_is_type
FROM nodes
WHERE semantic_label IS NULL OR semantic_label = ''
GROUP BY node_type
ORDER BY count_with_null_semantic_label DESC;

