"""
Initialize all database schemas.
Run this script to create tables in all 3 Postgres databases.
"""
import os
import sys
import asyncio

# Ensure project root is in path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from db import init_all_dbs


async def main():
    print("Initializing database schemas...")
    print("- User DB (port 5432)")
    print("- Embedding DB (port 5433)")
    print("- Chat DB (port 5434)")
    
    try:
        await init_all_dbs()
        print("\n✓ All database schemas initialized successfully!")
    except Exception as e:
        print(f"\n✗ Error initializing databases: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
