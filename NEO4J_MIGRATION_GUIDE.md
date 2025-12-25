# MiroFish - Neo4j Migration Testing Guide

## ✅ Migration Complete!

The application has been successfully migrated from **ZEP Cloud** to **Neo4j**.

## Quick Start

### 1. Start Neo4j

```bash
# From project root
docker-compose up -d

# Verify Neo4j is running
docker-compose ps
```

Neo4j Browser will be available at: **http://localhost:7474**
- Username: `neo4j`
- Password: `mirofish123`

### 2. Update Environment Variables

Make sure your `.env` file has Neo4j configuration:

```env
# Neo4j Configuration
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=mirofish123
NEO4J_DATABASE=neo4j

# LLM Configuration (required for entity extraction)
LLM_API_KEY=your_api_key
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_MODEL_NAME=qwen-plus
```

### 3. Install Dependencies

```bash
# Backend dependencies (neo4j driver is now included)
cd backend
uv sync
# or
pip install -r requirements.txt
```

### 4. Start the Application

```bash
# From project root
npm run dev
```

## Testing the Migration

### Test 1: Graph Building

1. Upload a test document through the frontend
2. Generate ontology definition
3. Click "Build Graph"
4. Monitor progress in the UI
5. Check Neo4j Browser to see created nodes and relationships

**Expected Results:**
- Graph build completes successfully
- Nodes visible in Neo4j Browser with correct labels
- Relationships created between entities
- No errors in backend logs

### Test 2: Entity Retrieval

1. After building a graph, navigate to "Environment Setup"
2. View extracted entities
3. Check entity details and relationships

**Expected Results:**
- Entities display correctly
- Entity types match ontology definition
- Relationships visible

### Test 3: Simulation with Memory Updates

1. Configure and start a simulation
2. Let it run for a few rounds
3. Check Neo4j Browser for new nodes/relationships from agent activities

**Expected Results:**
- Agent activities create new entities in graph
- Relationships update in real-time
- No duplicate entities

### Test 4: Report Generation

1. Complete a simulation
2. Generate a report
3. Verify report agent can query graph data

**Expected Results:**
- Report generated successfully
- Recommendations based on graph data
- No ZEP-related errors

## Troubleshooting

### Neo4j Connection Errors

**Problem:** `Neo4j connection not configured`

**Solution:**
1. Verify Neo4j is running: `docker-compose ps`
2. Check `.env` file has correct NEO4J_URI
3. Test connection in Neo4j Browser

### LLM Extraction Errors

**Problem:** Entity extraction fails

**Solution:**
1. Verify LLM_API_KEY is configured
2. Check LLM service is accessible
3. Review backend logs for API errors

### Graph Build Hangs

**Problem:** Graph build stuck at certain percentage

**Solution:**
1. Check backend logs for errors
2. Verify Neo4j has sufficient memory
3. Try smaller document/chunk size

## What Changed?

### Core Changes
- ✅ **ZEP Cloud** → **Neo4j** (self-hosted graph database)
- ✅ **ZEP automatic extraction** → **LLM-based extraction** (using your configured LLM)
- ✅ **ZEP API calls** → **Cypher queries**

### Files Migrated
- `graph_builder.py` - Now uses Neo4j + LLM extractor
- `neo4j_entity_reader.py` - Reads from Neo4j (formerly zep_entity_reader.py)
- `neo4j_graph_memory_updater.py` - Updates Neo4j during simulation (formerly zep_graph_memory_updater.py)
- `neo4j_service.py` - New: Core Neo4j connection/query service
- `llm_entity_extractor.py` - New: LLM-based entity extraction

### Backward Compatibility
All class names remain the same (e.g., `ZepEntityReader`, `ZepGraphMemoryManager`) 
through aliasing, so existing code works without changes.

## Neo4j Browser Queries

### View all nodes
```cypher
MATCH (n:GraphNode)
RETURN n
LIMIT 50
```

### View nodes by graph
```cypher
MATCH (n:GraphNode {graph_id: "mirofish_xxxxx"})
RETURN n
```

### View relationships
```cypher
MATCH (a:GraphNode)-[r]->(b:GraphNode)
RETURN a, r, b
LIMIT 50
```

### Count entities by type
```cypher
MATCH (n:GraphNode)
UNWIND labels(n) as label
WITH label, count(*) as count
WHERE label <> 'GraphNode'
RETURN label, count
ORDER BY count DESC
```

## Performance Notes

- **Graph building** may be slightly slower due to LLM extraction (API calls)
- **Query performance** should be similar or better (native Neo4j queries)
- **Memory updates** are batched for efficiency (5 activities per batch)

## Need Help?

Check the logs:
- Backend: `backend/logs/`
- Docker: `docker-compose logs neo4j`
