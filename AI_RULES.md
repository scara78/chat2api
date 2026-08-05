# AI_RULES.md

## Tech Stack

- Python 3.10+ is the implementation language; use type hints and async-compatible code where it matches the surrounding module.
- FastAPI provides the HTTP application, routing, request handling, OpenAPI documentation, and dependency injection.
- Uvicorn runs the ASGI application in local development and deployment.
- Pydantic v2 and pydantic-settings define request/response models and load validated configuration from environment variables.
- HTTPX with HTTP/2 is the standard general-purpose outbound HTTP client.
- `curl_cffi` is used for ChatGPT web requests that require browser-like TLS fingerprinting.
- `python-dotenv` supports loading local environment configuration during development.
- Docker and Docker Compose provide the optional containerized runtime; generated images persist through the `images_data` volume.

## Library And Architecture Rules

- Use FastAPI routers for HTTP endpoints. Keep chat endpoints in `routes_chat.py`, image endpoints in `routes_images.py`, and register routers in `main.py`.
- Use Pydantic models for external JSON input and output. Do not parse or validate API payloads with ad hoc dictionaries when a model is appropriate.
- Use `pydantic-settings` and the existing settings object for configuration. Read environment variables through `config.py`; do not hardcode tokens, proxy URLs, credentials, or deployment-specific values.
- Use `httpx` for ordinary outbound HTTP calls. Use `curl_cffi` only for requests to ChatGPT web endpoints that depend on Chrome TLS/browser fingerprint behavior, following the existing `http_client.py` boundary.
- Preserve asynchronous behavior in FastAPI request handlers and streaming paths. Do not introduce blocking network or CPU-heavy work directly into async handlers without an appropriate async implementation or offloading strategy.
- Use FastAPI/Starlette response classes for HTTP responses and streaming responses. Preserve the existing OpenAI-compatible response shapes and SSE behavior in `routes_chat.py`.
- Keep web protocol concerns isolated in `web_client.py`, `web_fingerprint.py`, `web_proof.py`, and `web_sse_parser.py`. Route modules should orchestrate requests and responses rather than duplicate browser headers, proof-of-work, or SSE parsing logic.
- Use the standard library for small utilities and filesystem work unless an existing dependency already owns the behavior. Use `image_utils.py` for image size and aspect-ratio mapping instead of duplicating mappings.
- Use `logging` for server diagnostics; never log access tokens, cookies, authorization headers, prompts containing secrets, or full upstream response bodies.
- Keep generated image files under the configured `images/` directory and expose them through the existing static mount. Do not add a second storage mechanism without an explicit requirement.
- Keep changes focused on the requested behavior. Match the existing module layout and avoid adding frameworks, dependencies, or abstractions without a concrete need.
- When adding or changing behavior, update the focused tests in `test_client.py` or add small unit tests for isolated logic. Verify changed Python files before considering the task complete.
