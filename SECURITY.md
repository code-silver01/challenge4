# Security Policy

## Supported Versions

Currently, only the latest version of this project is supported with security updates. 

| Version | Supported          |
| ------- | ------------------ |
| 1.x.x   | :white_check_mark: |
| < 1.0   | :x:                |

## Descoped for MVP / Proof of Concept

This project is currently structured as an MVP (Minimum Viable Product). For hackathon judging and testing purposes, several security measures have been explicitly descoped to favor speed of iteration. When moving to a production environment, the following areas must be hardened:

1. **Authentication and Authorization:**
   - Currently, user state is entirely managed via a stateless `session_id` generated on the client. 
   - There is no cryptographic verification of `session_id` (e.g., JWT signatures) or OAuth layer.
   - **Production Hardening:** Implement a robust identity provider (IdP) layer (e.g. Firebase Auth, Auth0) and validate bearer tokens on all backend routes.

2. **Rate Limiting:**
   - The current rate limiter (`RateLimiter` in `services/rate_limiter.py`) is strictly in-memory. In a multi-worker or multi-container environment, this limits its effectiveness.
   - **Production Hardening:** Migrate rate-limiting state to a distributed cache like Redis to ensure global enforcement across instances.

3. **CORS (Cross-Origin Resource Sharing):**
   - CORS is currently locked to `localhost:5173` for safe local development.
   - **Production Hardening:** Ensure environment variables in production strictly specify the actual deployed frontend origins and avoid wildcard (`*`) domains.

4. **Prompt Injection / Input Sanitization:**
   - Input length is capped to 500 characters, and basic regex-based stripping of prompt injection techniques is performed at the API boundary before hitting the LLM.
   - **Production Hardening:** Regex is insufficient for complex adversarial attacks on LLMs. Deploy a dedicated ML-based input filtering service (like Google Cloud Armor or dedicated LLM guardrails) for robust detection.

## Reporting a Vulnerability

If you discover a security vulnerability in this project, please report it via private email or direct message to the repository owners. Do not disclose it publicly via an issue tracker until it has been properly mitigated.
