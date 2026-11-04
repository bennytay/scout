-- Switch to 384-d embeddings: local fastembed (BAAI/bge-small-en-v1.5) is the default provider, so the system
-- needs no embeddings API key. The OpenAI adapter requests 384 dims too (text-embedding-3 supports `dimensions`).
-- Existing vectors are dropped; run `scout reembed` to rebuild them.
drop index if exists items_emb_hnsw;
alter table items alter column embedding type vector(384) using null;
create index items_emb_hnsw on items using hnsw (embedding vector_cosine_ops);
