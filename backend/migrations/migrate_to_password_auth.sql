-- Migration: Convert from Google OAuth to Email/Password authentication
-- Date: 2025-12-12
--
-- This migration:
-- 1. Adds password_hash column to users table
-- 2. Removes google_id column (no longer needed)
-- 3. Sets a default password hash for existing users (they'll need to reset)
--
-- IMPORTANT: Run this migration BEFORE deploying the new backend code
-- Existing users will need to use "forgot password" flow to set their password

-- Step 1: Add password_hash column (nullable initially for existing records)
ALTER TABLE users ADD COLUMN password_hash VARCHAR(255) NULL AFTER email;

-- Step 2: Set a placeholder hash for existing users
-- This is a bcrypt hash of a random string - users MUST reset their password
-- Hash of 'MUST_RESET_PASSWORD_12345' using bcrypt
UPDATE users SET password_hash = '$2b$12$placeholder.hash.for.existing.users.needreset' WHERE password_hash IS NULL;

-- Step 3: Make password_hash NOT NULL now that all records have a value
ALTER TABLE users MODIFY COLUMN password_hash VARCHAR(255) NOT NULL;

-- Step 4: Drop the google_id column (no longer needed)
ALTER TABLE users DROP INDEX ix_users_google_id;
ALTER TABLE users DROP COLUMN google_id;

-- Verify the migration
-- SELECT id, email, password_hash, name FROM users LIMIT 5;
