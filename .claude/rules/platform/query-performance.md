# Query Performance — Dashboard & Analytics Queries MUST NOT Block Operations

## The Problem
Dashboard widgets run aggregation queries (COUNT, SUM, GROUP BY, JOINs across millions of rows). These queries:
- Lock rows and pages, blocking CRUD operations
- Consume CPU and IO, starving API request handlers
- In Elastic Pool, steal shared DTUs from ALL tenants
- A single bad dashboard query can make the entire platform feel slow

## Architecture: Read Path vs Write Path (CQRS-Lite)

```
WRITE PATH (transactional):              READ PATH (analytics):
API requests, CRUD operations            Dashboard queries, reports, exports

Uses: Primary DB connection              Uses: Read-replica connection
Pattern: Small, fast queries             Pattern: Aggregations, JOINs, scans
Target: < 50ms per query                 Target: < 2 seconds per query
Indexes: Narrow, B-tree                  Indexes: Covering, filtered, columnstore
```

### Connection String Separation
```csharp
// In DapperDbContext — TWO connections
public IDbConnection CreateConnection()         // Primary — for writes + simple reads
public IDbConnection CreateReadConnection()     // Replica — for dashboards + reports

// Azure SQL: add ApplicationIntent=ReadOnly to read connection string
// "Data Source=sql-novara-prod;...;ApplicationIntent=ReadOnly"
// This routes to the read-scale replica automatically
```

### Rule: Which Connection to Use
- **Primary:** INSERT, UPDATE, DELETE, single-row SELECT by PK/FK
- **Read Replica:** Aggregations (COUNT, SUM, AVG), GROUP BY, multi-table JOINs, reports, dashboard data, exports, search

## Query Rules for Dashboard/Analytics SPs

### 1. NEVER Full Table Scan on Transactional Tables
```sql
-- BANNED: scans entire ErrorLog (could be millions of rows)
SELECT COUNT(*) FROM platform.ErrorLog WHERE Level = 'Error';

-- CORRECT: use pre-aggregated summary table
SELECT ErrorCount FROM platform.DailyMetricSummary 
WHERE MetricDate = CAST(GETUTCDATE() AS DATE) AND MetricKey = 'ErrorCount';
```

### 2. Always Use Pre-Aggregated Summary Tables
Dashboard widgets do NOT query raw transactional tables. They read from summary tables populated by background jobs.

```sql
-- Summary tables (populated hourly/daily by background service)
CREATE TABLE platform.HourlyMetricSummary (
    Id INT IDENTITY(1,1),
    TenantId INT NOT NULL,
    ProductId INT NULL,
    MetricKey NVARCHAR(100) NOT NULL,    -- 'error_count', 'request_count', 'p95_latency'
    MetricValue DECIMAL(18,4) NOT NULL,
    BucketHour DATETIME2 NOT NULL,        -- Rounded to hour
    DimensionKey NVARCHAR(100) NULL,      -- Optional grouping: 'feature:42', 'module:Issues'
    DimensionValue NVARCHAR(200) NULL,
    INDEX IX_HourlySummary (TenantId, MetricKey, BucketHour)
);

CREATE TABLE platform.DailyMetricSummary (
    Id INT IDENTITY(1,1),
    TenantId INT NOT NULL,
    ProductId INT NULL,
    MetricKey NVARCHAR(100) NOT NULL,
    MetricValue DECIMAL(18,4) NOT NULL,
    MetricDate DATE NOT NULL,
    DimensionKey NVARCHAR(100) NULL,
    DimensionValue NVARCHAR(200) NULL,
    INDEX IX_DailySummary (TenantId, MetricKey, MetricDate)
);
```

### 3. Aggregation Jobs Run on Read Replica
```csharp
// Background service runs hourly
public class MetricAggregationService : BackgroundService
{
    // READS from replica (heavy aggregation)
    var rawCounts = await _readDb.ExecuteProcedureAsync<MetricRow>(
        SpNames.AggregateHourlyMetrics, new { Hour = currentHour });

    // WRITES to primary (small upsert)
    await _writeDb.ExecuteProcedureAsync(
        SpNames.UpsertHourlyMetricSummary, new { Metrics = rawCounts });
}
```

### 4. Query Time Limits
```sql
-- Every dashboard SP MUST have a timeout
-- Set at connection level, not per-query
-- Dashboard queries: 5 second timeout (KILL if exceeded)
-- Report queries: 30 second timeout
-- Export queries: 60 second timeout

-- In C#:
using var conn = _db.CreateReadConnection();
conn.Open();
// CommandTimeout set per command
var result = await conn.QueryAsync<T>(sql, param, commandTimeout: 5);
```

### 5. Pagination on ALL List Queries
```sql
-- BANNED: return all rows
SELECT * FROM platform.ErrorLog WHERE TenantId = @TenantId;

-- CORRECT: always paginated
SELECT *, COUNT(*) OVER() AS TotalCount
FROM platform.ErrorLog 
WHERE TenantId = @TenantId
ORDER BY CreatedAtUtc DESC
OFFSET @Skip ROWS FETCH NEXT @PageSize ROWS ONLY;
```

### 6. Use Filtered Indexes for Hot Queries
```sql
-- Dashboard always queries recent + unresolved errors
-- Filtered index covers this without scanning resolved/old rows
CREATE NONCLUSTERED INDEX IX_ErrorLog_Unresolved_Recent
ON platform.ErrorLog (TenantId, CreatedAtUtc DESC)
INCLUDE (Level, Message, FeatureId, ErrorFingerprint)
WHERE IsResolved = 0 AND CreatedAtUtc >= '2026-01-01';
```

### 7. Columnstore Indexes for Analytics Tables
```sql
-- RequestTrace and LlmCallLog are write-heavy, read for analytics
-- Columnstore gives 10x compression and 100x faster aggregation
CREATE NONCLUSTERED COLUMNSTORE INDEX NCCI_RequestTrace_Analytics
ON platform.RequestTrace (TenantId, ProductId, Path, TotalMs, IsError, CreatedAtUtc);

-- Dashboard query on columnstore: scans 1M rows in <100ms
SELECT Path, AVG(TotalMs) AS AvgMs, COUNT(*) AS Requests
FROM platform.RequestTrace
WHERE TenantId = @TenantId AND CreatedAtUtc >= @Since
GROUP BY Path;
```

### 8. NOLOCK for Dashboard Reads (Acceptable Dirty Reads)
```sql
-- Dashboard queries can tolerate slightly stale data
-- Use WITH (NOLOCK) or READ UNCOMMITTED isolation
-- This prevents dashboard queries from blocking writes

SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED;
-- or
SELECT COUNT(*) FROM platform.ErrorLog WITH (NOLOCK) WHERE ...;
```

### 9. Query Complexity Budget
Every dashboard SP must declare its complexity:
- **Simple** (< 50ms): Single table, indexed lookup, small result
- **Medium** (< 500ms): 2-3 table join, aggregation with index
- **Heavy** (< 2s): Multi-table join, large aggregation → MUST use read replica
- **Export** (< 30s): Full data export → MUST use read replica + streaming

### 10. AI Query Review
Every new dashboard SP goes through AI review before deployment:
- Check for missing WHERE TenantId (security)
- Check for missing indexes on JOIN/WHERE columns
- Check for full table scans (estimated row count > 10K)
- Check for missing NOLOCK on read-only queries
- Suggest covering indexes if key lookup detected
- Reject if estimated cost > threshold

## Anti-Patterns — BANNED in Dashboard Queries

```sql
-- BANNED: Correlated subquery in SELECT (runs per row)
SELECT f.Title, 
  (SELECT COUNT(*) FROM product.FeatureTask WHERE FeatureId = f.Id) AS TaskCount
FROM product.Feature f;
-- FIX: LEFT JOIN with GROUP BY

-- BANNED: DISTINCT to hide bad JOIN
SELECT DISTINCT f.* FROM product.Feature f JOIN ...
-- FIX: Fix the JOIN logic

-- BANNED: Function on indexed column in WHERE
SELECT * FROM platform.ErrorLog WHERE YEAR(CreatedAtUtc) = 2026;
-- FIX: WHERE CreatedAtUtc >= '2026-01-01' AND CreatedAtUtc < '2027-01-01'

-- BANNED: Implicit conversion
SELECT * FROM product.Feature WHERE Id = @StringParam; -- Id is INT, param is NVARCHAR
-- FIX: Use INT parameter

-- BANNED: SELECT * in dashboard SP
SELECT * FROM platform.RequestTrace;
-- FIX: SELECT only the columns the widget needs

-- BANNED: No timeout on dashboard query
-- FIX: Always set CommandTimeout in C# caller

-- BANNED: Dashboard SP writes data (violates CQRS)
-- FIX: Read-only SPs for dashboards, separate SP for aggregation writes
```

## Monitoring Query Performance

```sql
-- Check for slow dashboard queries (run weekly)
SELECT TOP 20
    qs.total_elapsed_time / qs.execution_count AS AvgDurationMs,
    qs.execution_count,
    SUBSTRING(qt.text, qs.statement_start_offset/2 + 1, 100) AS QueryText
FROM sys.dm_exec_query_stats qs
CROSS APPLY sys.dm_exec_sql_text(qs.sql_handle) qt
WHERE qt.text LIKE '%novara.%Dashboard%' OR qt.text LIKE '%novara.%Summary%'
ORDER BY AvgDurationMs DESC;
```

## Summary: The 3-Layer Approach

```
Layer 1: Pre-Aggregation (Background Job)
  Raw tables → Summary tables (hourly/daily)
  Runs on read replica, writes small summaries to primary
  Dashboard never touches raw data

Layer 2: Read Replica (Connection Routing)
  Heavy queries routed to Azure SQL read-scale replica
  Primary stays fast for API operations
  ApplicationIntent=ReadOnly in connection string

Layer 3: Query Governance (Rules + Monitoring)
  5s timeout on dashboard queries
  NOLOCK for acceptable dirty reads
  AI reviews every new SP for performance
  Columnstore indexes on analytics-heavy tables
  Filtered indexes for hot query patterns
```
