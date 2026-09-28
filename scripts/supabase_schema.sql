-- ==============================================================================
-- Enterprise AI Telegram Assistant — Complete Supabase PostgreSQL Schema
-- ==============================================================================
-- Instructions:
-- 1. Open Supabase Dashboard: https://supabase.com/dashboard/project/yzffmlsvqcxqwrzttdhv
-- 2. Click "SQL Editor" in the left sidebar -> "New query"
-- 3. Paste and run this entire script.
-- ==============================================================================

-- 1. Enable pgvector Extension
CREATE EXTENSION IF NOT EXISTS vector;

-- 2. Organizations Table (Tenant Isolation Root)
CREATE TABLE IF NOT EXISTS public.organizations (
    id VARCHAR(64) PRIMARY KEY,
    name VARCHAR(255) NOT NULL UNIQUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL
);

-- 3. Users Table (Tenant Admins & Employees)
CREATE TABLE IF NOT EXISTS public.users (
    id VARCHAR(64) PRIMARY KEY,
    organization_id VARCHAR(64) NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    employee_id VARCHAR(64) NOT NULL,
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255) NOT NULL,
    role VARCHAR(32) DEFAULT 'employee' NOT NULL,  -- 'admin' | 'employee'
    status VARCHAR(32) DEFAULT 'active' NOT NULL,  -- 'active' | 'suspended'
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    CONSTRAINT ix_org_employee UNIQUE (organization_id, employee_id)
);
CREATE INDEX IF NOT EXISTS ix_users_org ON public.users(organization_id);
CREATE INDEX IF NOT EXISTS ix_users_employee ON public.users(employee_id);
CREATE INDEX IF NOT EXISTS ix_users_email ON public.users(email);

-- 4. Documents Table (Metadata for Ingested Files)
CREATE TABLE IF NOT EXISTS public.documents (
    id VARCHAR(64) PRIMARY KEY,
    organization_id VARCHAR(64) NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    filename VARCHAR(255) NOT NULL,
    storage_path VARCHAR(512) NOT NULL,
    file_size INTEGER DEFAULT 0 NOT NULL,
    chunk_count INTEGER DEFAULT 0 NOT NULL,
    uploaded_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_docs_org ON public.documents(organization_id);

-- 5. Document Chunks Table (pgvector 768-dim Embeddings for Gemini)
CREATE TABLE IF NOT EXISTS public.document_chunks (
    id VARCHAR(64) PRIMARY KEY,
    document_id VARCHAR(64) NOT NULL REFERENCES public.documents(id) ON DELETE CASCADE,
    organization_id VARCHAR(64) NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    embedding VECTOR(768),
    chunk_metadata JSONB
);
CREATE INDEX IF NOT EXISTS ix_chunks_org ON public.document_chunks(organization_id);
CREATE INDEX IF NOT EXISTS ix_chunks_doc ON public.document_chunks(document_id);

-- HNSW Vector Index for sub-millisecond Cosine Similarity search
CREATE INDEX IF NOT EXISTS ix_chunks_embedding_hnsw 
ON public.document_chunks 
USING hnsw (embedding vector_cosine_ops);

-- 6. Query Telemetry & Audit Logs
CREATE TABLE IF NOT EXISTS public.query_logs (
    id VARCHAR(64) PRIMARY KEY,
    user_id VARCHAR(64) REFERENCES public.users(id) ON DELETE SET NULL,
    organization_id VARCHAR(64) NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    question TEXT NOT NULL,
    model_used VARCHAR(64) NOT NULL,
    cache_hit BOOLEAN DEFAULT FALSE NOT NULL,
    input_tokens INTEGER DEFAULT 0 NOT NULL,
    output_tokens INTEGER DEFAULT 0 NOT NULL,
    estimated_cost FLOAT DEFAULT 0.0 NOT NULL,
    latency_ms FLOAT DEFAULT 0.0 NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_logs_org ON public.query_logs(organization_id);
CREATE INDEX IF NOT EXISTS ix_logs_user ON public.query_logs(user_id);
CREATE INDEX IF NOT EXISTS ix_logs_created ON public.query_logs(created_at DESC);

-- 7. Telegram User Sessions (Interactive Auth State Machine)
CREATE TABLE IF NOT EXISTS public.telegram_sessions (
    telegram_user_id BIGINT PRIMARY KEY,
    user_id VARCHAR(64) REFERENCES public.users(id) ON DELETE CASCADE,
    organization_id VARCHAR(64) REFERENCES public.organizations(id) ON DELETE CASCADE,
    role VARCHAR(32),
    auth_state VARCHAR(32) DEFAULT 'UNAUTHENTICATED' NOT NULL,
    auth_context JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_sessions_org ON public.telegram_sessions(organization_id);

-- ==============================================================================
-- 8. Supabase Storage Bucket & Permissions
-- ==============================================================================
-- Create the enterprise-documents bucket for raw PDF/DOCX storage
INSERT INTO storage.buckets (id, name, public)
VALUES ('enterprise-documents', 'enterprise-documents', false)
ON CONFLICT (id) DO NOTHING;

-- Policy: Allow service_role key full CRUD on the bucket
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies 
        WHERE tablename = 'objects' 
        AND schemaname = 'storage' 
        AND policyname = 'Service Role Full Storage Access'
    ) THEN
        CREATE POLICY "Service Role Full Storage Access"
        ON storage.objects
        FOR ALL
        TO service_role
        USING (bucket_id = 'enterprise-documents')
        WITH CHECK (bucket_id = 'enterprise-documents');
    END IF;
END $$;

-- ==============================================================================
-- 9. Vector Similarity Search Stored Function (Optional convenience RPC)
-- ==============================================================================
CREATE OR REPLACE FUNCTION match_document_chunks (
    query_embedding VECTOR(768),
    filter_org_id VARCHAR(64),
    match_threshold FLOAT DEFAULT 0.45,
    match_count INT DEFAULT 4
)
RETURNS TABLE (
    id VARCHAR(64),
    document_id VARCHAR(64),
    organization_id VARCHAR(64),
    content TEXT,
    chunk_metadata JSONB,
    similarity FLOAT
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        dc.id,
        dc.document_id,
        dc.organization_id,
        dc.content,
        dc.chunk_metadata,
        (1.0 - (dc.embedding <=> query_embedding))::FLOAT AS similarity
    FROM public.document_chunks dc
    WHERE dc.organization_id = filter_org_id
      AND (1.0 - (dc.embedding <=> query_embedding)) >= match_threshold
    ORDER BY dc.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;
