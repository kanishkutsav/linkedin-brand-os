# Processor / subprocessor register — QA

This is an implementation inventory, not a contractual certification. Exact plan terms, regions, retention, training use, subprocessors and DPAs must be verified for the production accounts before launch.

| Provider / system | Purpose | Data category potentially processed | Production verification |
|---|---|---|---|
| Vercel | Web/API hosting | Account/session/API traffic, product data handled by server | Verify plan DPA, region, retention |
| Supabase | PostgreSQL/database | Account, Brand DNA, content, learning, research, LinkedIn metadata | Verify DPA, region, backups/retention |
| LinkedIn | OAuth/profile/publishing | LinkedIn identity/profile and authorized publishing data | Verify current API/product terms and permissions |
| OpenRouter | AI routing | Minimized generation/research context | Verify model/provider retention and training policy |
| Groq | AI fallback | Minimized generation context | Verify current plan/API terms |
| Google Gemini | Research/embedding/AI fallback | Research prompts and minimized product context | Verify current API terms, retention and training policy |
| Monitoring/logging | Operational observability | Security events and infrastructure metadata | Identify exact provider before production |

Do not add a provider to production configuration unless it is explicitly approved for the data categories it receives and its contractual terms are recorded.
