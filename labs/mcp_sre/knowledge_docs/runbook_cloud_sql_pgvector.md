# GCP SRE Runbook: Cloud SQL PostgreSQL pgvector Vector Index Optimization
**Document ID**: GCP-RUNBOOK-002  
**Target Platform**: Google Cloud SQL for PostgreSQL 15+ with pgvector extension  
**Classification**: High-Performance RAG & AI Infrastructure  

---

## 1. Problem Statement
Vector similarity searches using standard `vector_cosine_ops` (`<=>`) degrade from 12ms to 450ms when knowledge chunks exceed 100,000 vectors without an index. Queries without HNSW indexing perform an exhaustive sequential scan (`Seq Scan`), consuming 100% vCPU on Cloud SQL instances.

---

## 2. Recommended Index Architecture: HNSW vs IVFFlat
* **HNSW (Hierarchical Navigable Small World)**:
  * Superior recall (> 95%) and query throughput under high concurrent load.
  * Recommended parameters: `m = 16`, `ef_construction = 64`.
* **IVFFlat**:
  * Lower memory footprint, but requires periodic rebuilds (`REINDEX`) when document count shifts.

---

## 3. Production Remediation Script
Execute via Cloud SQL Studio or secure Cloud SQL Auth Proxy:
```sql
-- 1. Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- 2. Build HNSW Index with zero-downtime maintenance work memory
SET maintenance_work_mem = '512MB';

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_knowledge_chunks_hnsw 
ON enterprise_knowledge_chunks 
USING hnsw (embedding vector_cosine_ops) 
WITH (m = 16, ef_construction = 64);

-- 3. Tune runtime search precision vs latency
SET hnsw.ef_search = 40;
```
