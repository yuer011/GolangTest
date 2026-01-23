# Copilot Instructions for GolangTest

## Project Overview
This is a multi-language test/sample project containing Python, Go, and SQL components. It primarily focuses on:
- **Python**: Flask-based file server with upload capabilities (app1.py)
- **Go**: Simple command-line utilities for URL formatting and time operations (day1.go)
- **SQL**: Database schema definitions for analytics/logging systems (init_ch.sql - ClickHouse)

## Architecture & Key Components

### Python Components (app1.py)
- Flask web application for file upload/download operations
- Static file serving from `uploads/` directory
- Endpoints: `/` (index), `/uploads/<filename>` (serve files), `/upload` (POST file upload)
- Configuration: Sets `UPLOAD_FOLDER` with automatic directory creation
- Content: Bilingual interface (Chinese responses)

### Go Components (day1.go)
- Standalone CLI utility for URL parameter formatting
- Uses `fmt.Sprintf()` for template-based URL construction
- Common pattern: Building query strings with stock codes and date parameters
- Example: `Code=%d&endDate=%s` string formatting

### Database Layer (init_ch.sql)
- ClickHouse schema definitions for analytics data
- Two primary tables: `agw_access_log` (gateway access logs) and `ai_chat_log` (chat analytics)
- ClickHouse-specific: Uses `MergeTree` engine, `PARTITION BY toDate()`, TTL-based retention (180 days)
- Comprehensive field tracking: user info (uid, email, mobile), request metadata, response metrics (duration, status, size)

## Developer Workflows

### Running Python Services
```bash
python app1.py
# Starts Flask dev server on http://localhost:5000
# Creates 'uploads' directory automatically
```

### Running Go Utilities
```bash
go run day1.go
# Outputs URL formatting examples and current timestamp
```

### Database Setup
Execute `init_ch.sql` against ClickHouse instance:
```bash
clickhouse-client < init_ch.sql
```

## Project Patterns & Conventions

### File Organization
- Root-level scripts for direct execution (app1.py, day1.go)
- SQL schemas in separate files (init_ch.sql)
- Data files use Chinese naming conventions (新加坡手机号* prefixes) - appears to be test data

### Code Style Notes
- Python: Uses Chinese comments and UI strings (bilingual support)
- Go: Minimal verbose patterns with `fmt.Sprintf()` for string templating
- SQL: ClickHouse dialect with comment annotations on each field

### Security Considerations
- File upload endpoint requires validation before production use
- No authentication layer in app1.py - Flask debug mode enabled
- SQL schema includes PII fields (email, mobile) - ensure proper access controls

## External Dependencies
- **Python**: Flask (web framework)
- **Go**: Standard library only (fmt, time packages)
- **SQL**: ClickHouse database engine (MergeTree tables, TTL policies)

## Common Development Tasks

1. **Adding new API endpoints**: Extend app1.py with new `@app.route()` decorators
2. **Adding database tables**: Follow ClickHouse pattern in init_ch.sql with `MergeTree` engine and appropriate partition/order keys
3. **URL formatting**: Use Go's `fmt.Sprintf()` pattern from day1.go for query string construction
