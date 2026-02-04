-- Migration: Add multi-tenant support
-- Date: 2026-01-12
--
-- This migration adds:
-- 1. tenants table for organizations
-- 2. tenant_datasources table for org-wide OAuth connections
-- 3. New columns to users table: tenant_id, role, auth_provider, google_id

-- Step 1: Create tenants table
CREATE TABLE IF NOT EXISTS tenants (
    id VARCHAR(36) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    domain VARCHAR(255) UNIQUE NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_tenants_domain (domain)
);

-- Step 2: Create tenant_datasources table
CREATE TABLE IF NOT EXISTS tenant_datasources (
    id VARCHAR(36) PRIMARY KEY,
    tenant_id VARCHAR(36) NOT NULL,
    datasource VARCHAR(50) NOT NULL,
    encrypted_credentials TEXT NOT NULL,
    oauth_metadata JSON NULL,
    connected_by VARCHAR(36) NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_tenant_datasources_tenant (tenant_id),
    INDEX idx_tenant_datasources_datasource (datasource),
    UNIQUE INDEX idx_tenant_datasource (tenant_id, datasource),
    FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
);

-- Step 3: Add new columns to users table (if they don't exist)
-- Add tenant_id
ALTER TABLE users ADD COLUMN IF NOT EXISTS tenant_id VARCHAR(36) NULL;
ALTER TABLE users ADD INDEX IF NOT EXISTS idx_users_tenant (tenant_id);

-- Add role
ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(20) NOT NULL DEFAULT 'member';

-- Add auth_provider
ALTER TABLE users ADD COLUMN IF NOT EXISTS auth_provider VARCHAR(20) NOT NULL DEFAULT 'email';

-- Add google_id (for Google OAuth users)
ALTER TABLE users ADD COLUMN IF NOT EXISTS google_id VARCHAR(255) NULL;
ALTER TABLE users ADD UNIQUE INDEX IF NOT EXISTS ix_users_google_id (google_id);

-- Step 4: Add foreign key for tenant_id (after column exists)
-- Note: Only run if the constraint doesn't exist
-- ALTER TABLE users ADD FOREIGN KEY (tenant_id) REFERENCES tenants(id);

-- Step 5: Add foreign key for connected_by in tenant_datasources
-- Note: Only run after users table is updated
-- ALTER TABLE tenant_datasources ADD FOREIGN KEY (connected_by) REFERENCES users(id);

-- Verify the migration
-- DESCRIBE users;
-- DESCRIBE tenants;
-- DESCRIBE tenant_datasources;
