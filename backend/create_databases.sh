#!/bin/bash
# Create the 3 databases in each Postgres container

echo "Creating databases..."

# Database 1: user_info (port 5432)
docker exec postgres-pinpoint-pdf-user-info psql -U postgres -c "CREATE DATABASE user_info;" 2>/dev/null || echo "user_info already exists"

# Database 2: embedding_db (port 5433)
docker exec postgres-pinpoint-pdf-embedding-db psql -U postgres -c "CREATE DATABASE embedding_db;" 2>/dev/null || echo "embedding_db already exists"

# Database 3: chat_db (port 5434)
docker exec postgres-pinpoint-pdf-user-chats psql -U postgres -c "CREATE DATABASE chat_db;" 2>/dev/null || echo "chat_db already exists"

echo "✓ All databases created!"
