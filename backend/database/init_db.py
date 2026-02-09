"""
Database initialization script for PostgreSQL.

This script uses LangGraph's AsyncPostgresSaver.setup() method to create
all necessary tables for checkpoint persistence.
"""
import asyncio
import sys
import os
import argparse

# Fix for Windows: psycopg requires SelectorEventLoop on Windows
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver


async def init_database(database_url: str):
    """
    Initialize PostgreSQL database schema for LangGraph checkpointer.
    
    Uses AsyncPostgresSaver.setup() to create all required tables:
    - checkpoints: Main checkpoint storage
    - checkpoint_blobs: Binary data storage
    - checkpoint_writes: Per-channel delta writes
    
    Args:
        database_url: PostgreSQL connection string
    """
    print("🔗 Connecting to database...")
    
    try:
        # Use AsyncPostgresSaver's built-in setup method
        async with AsyncPostgresSaver.from_conn_string(database_url) as checkpointer:
            # The setup() method creates all necessary tables
            await checkpointer.setup()
            
        print("✅ Database schema initialized successfully")
        print("   Tables created:")
        print("   - checkpoints")
        print("   - checkpoint_blobs")
        print("   - checkpoint_writes")
        print("   - indexes")
        
    except Exception as e:
        print(f"❌ Database initialization failed: {e}")
        raise


def main():
    """Main entry point for database initialization."""
    parser = argparse.ArgumentParser(description="Initialize PostgreSQL database for LangGraph")
    parser.add_argument("--setup", action="store_true", help="Initialize database schema")
    args = parser.parse_args()
    
    if not args.setup:
        print("Usage: python -m database.init_db --setup")
        print("Set DATABASE_URL environment variable before running")
        return
    
    # Get database URL from environment
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("❌ DATABASE_URL environment variable not set")
        print("Example: DATABASE_URL=postgresql://user:password@host:port/database")
        sys.exit(1)
    
    # Run initialization
    asyncio.run(init_database(database_url))


if __name__ == "__main__":
    main()
