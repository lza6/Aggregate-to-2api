# Project Constitution: imagefree-api

## Core Values

1. **Production-First**: Every line of code must be deployable, observable, and recoverable. No "it works on my machine" mentality.
2. **Complete Closure**: No half-implemented features. Every button must work, every API must return proper responses, every error must be handled.
3. **Defense in Depth**: Assume everything fails — upstream, network, database, filesystem. Graceful degradation at every layer.
4. **Developer Experience**: Clean code, clear docs, consistent patterns. A new contributor should be productive within 30 minutes.

## Technical Principles

### Architecture
- **Layered Separation**: API handler → Business logic → Data access. No circular imports.
- **Async-First**: All I/O operations use asyncio. Blocking operations go to thread pool.
- **Fail Fast, Recover Gracefully**: Validate inputs at boundaries. Circuit breakers for upstream failures.
- **Idempotency**: Mutating operations are idempotent where feasible.

### Code Quality
- **Type Safety**: Full type annotations on all function signatures. No `Any` without justification.
- **Error Handling**: Every `except` must specify the exception type. Never bare `except:`.
- **Test Coverage**: ≥80% coverage. Integration tests for all API endpoints. Chaos tests for resilience.
- **No Dead Code**: Unused imports, variables, commented-out blocks are removed on sight.

### Performance
- **Async Concurrency**: Non-blocking I/O for all external calls. Connection pooling for HTTP clients.
- **Resource Limits**: Memory bounds, connection limits, queue caps. System must survive traffic spikes.
- **Latency Budget**: API submission <50ms P99. Health check <100ms. Generate completion as fast as upstream allows.

### Security
- **No Secrets in Code**: All credentials via environment variables. `.env` never committed.
- **Input Validation**: All user input validated at the boundary. SSRF protection on URL parameters.
- **Rate Limiting**: Queue-based backpressure prevents abuse. No unbounded resource consumption.

## Decision Framework

When making decisions, prioritize:
1. **Production stability** over feature velocity
2. **Clear error messages** over silent fallbacks
3. **Simple, testable code** over clever abstractions
4. **Consistent patterns** over "better" approaches
5. **Observability** (logs + metrics) over "it should work"

## Quality Gates

Before any commit to main:
- [ ] All unit tests pass
- [ ] Integration tests pass (if applicable)
- [ ] No new TODO/FIXME/HACK comments
- [ ] Type annotations on all new/modified functions
- [ ] Error handling covers all known failure modes
- [ ] Documentation updated (README, deploy docs, API docs)