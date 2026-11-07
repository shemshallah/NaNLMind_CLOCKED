# Clocked Koyeb deployment — retired

The standalone Clocked gateway deployment is retired. **Do not create or maintain a second Koyeb service.**

The authenticated gateway, scoped demo-token issuer, NANNET allocator integration, and NaNLMROUTER handoff are hosted inside the existing NaNLMind Koyeb service:

- Repository: https://github.com/shemshallah/NaNLMind
- HTTP entry point: `integrations/nannet/server.py`
- Gateway: `integrations/nannet/clocked_gateway.py`
- Router: `integrations/nannet/nannet_router/`
- Deployment image: repository-root `Dockerfile` in NaNLMind

Set `CLOCKED_API_KEY`, `CLOCKED_DEMO_ENROLLMENT_TOKEN`, `CLOCKED_GATEWAY_ADMIN_TOKEN`, `CLOCKED_TOKEN_PEPPER`, and `CLOCKED_RESULT_ENCRYPTION_KEY` on that existing Koyeb service. Set `NANNET_URL` and `NANLM_ROUTER_URL` to that same service origin. GitHub Actions uses `vars.NANNET_URL` or `vars.BSR0_PORTAL_API` for the live demo endpoint.

This repository remains the Clocked SDK integration, native demo, protocol schemas, fixtures, and offline/live test harness. It is not a deployable web service.
