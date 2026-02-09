"""
Database migration for blueprint storage with pgvector.

This script creates the blueprints table and HNSW index for
semantic similarity search.
"""
import asyncio
import sys
import os

# Fix for Windows: psycopg requires SelectorEventLoop on Windows
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


async def init_blueprints_table(database_url: str):
    """
    Initialize the blueprints table with pgvector HNSW index.
    
    Creates:
    - vector extension (if not exists)
    - blueprints table with embedding column
    - HNSW index for fast cosine similarity search
    
    Args:
        database_url: PostgreSQL connection string
    """
    from psycopg_pool import AsyncConnectionPool
    
    print("🔗 Connecting to database for blueprint schema...")
    
    async with AsyncConnectionPool(conninfo=database_url) as pool:
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                # Enable pgvector extension
                print("📦 Enabling pgvector extension...")
                await cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
                
                # Create blueprints table
                print("📋 Creating blueprints table...")
                await cur.execute("""
                    CREATE TABLE IF NOT EXISTS blueprints (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        task_query TEXT NOT NULL,
                        graph_spec JSONB NOT NULL,
                        embedding vector(1536),
                        metadata JSONB,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                
                # Create HNSW index for fast similarity search
                # Check if index already exists first
                await cur.execute("""
                    SELECT EXISTS (
                        SELECT 1 FROM pg_indexes 
                        WHERE indexname = 'blueprints_embedding_hnsw_idx'
                    );
                """)
                index_exists = (await cur.fetchone())[0]
                
                if not index_exists:
                    print("🔍 Creating HNSW index (this may take a moment)...")
                    await cur.execute("""
                        CREATE INDEX blueprints_embedding_hnsw_idx 
                        ON blueprints 
                        USING hnsw (embedding vector_cosine_ops);
                    """)
                else:
                    print("🔍 HNSW index already exists, skipping...")
                
                await conn.commit()
    
    print("✅ Blueprint schema initialized successfully")
    print("   Tables created/verified:")
    print("   - blueprints (with HNSW vector index)")


async def main():
    """Main entry point."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("❌ DATABASE_URL environment variable not set")
        print("Example: DATABASE_URL=postgresql://user:password@host:port/database")
        sys.exit(1)
    
    await init_blueprints_table(database_url)


if __name__ == "__main__":
    asyncio.run(main())
