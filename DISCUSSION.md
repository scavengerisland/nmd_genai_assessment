# Discussion Questions

Answer the **Shared Questions** section plus the **one track section** specified in your email (Solutions Architect OR Data Engineer). 

Aim for 2-4 sentences per answer unless otherwise noted. We value clarity and depth over length.

---

## Shared Questions (everyone answers)

### 1. Troubleshooting

If you could not complete the assessment or got stuck at any point, what went wrong and what did you try to troubleshoot?

**Your answer:**

I didn't get blocked, but the starter had four defects that would have stopped a clean run. Extract never received `document_type`, `make update-lambdas` silently skipped every function, the first `terraform apply` needed the Docker image to exist, and `LOG_LEVEL` had no effect. I found them by running the real state machine locally against the real handlers, with S3 on moto and a fake Bedrock, then fixed each in its own commit. I deployed only after that local run passed, which is why my commits are older than the AWS activity.


### 2. Proof of Completion

Paste the S3 URI to one of your result files (e.g., `s3://nmd-genai-<your-name>-documents/results/<document-id>.json`).

**Your answer:**

`s3://nmd-genai-ethan-hutchinson-documents/results/drug-approval.json`

All four sample documents ran end to end on Claude Haiku 5.5 and wrote their results to the same prefix.


### 3. Prompt Engineering

How would you improve the classification prompt to handle ambiguous documents that could match multiple types? What techniques would you use to ensure consistent JSON output from the LLM?

**Your answer:**

For ambiguous documents, I'd define each type by its decisive cue (a CVE ID, an FAA AD number, an NDA number, a Form 8-K) and add near-miss examples. I'd also ask for a score per type and send the document to review when the top two are close, which makes ambiguity measurable instead of a forced guess. For consistent JSON, my code forces a tool call whose input schema is the output contract, with the labels as an enum. The code then checks every response: anything cut off, refused, or outside the enum becomes `unknown`, and in production I'd add one repair retry before that fallback.


### 4. Error Handling

How would you handle Bedrock throttling (429 errors) in a production pipeline? What retry strategy would you implement, and how would it interact with Step Functions' built-in error handling?

**Your answer:**

I layer the retries and keep them on a budget. The SDK absorbs short spikes with 2 adaptive attempts, then the Lambda raises a typed `BedrockThrottlingError` that Step Functions retries 5 times with backoff and full jitter, while bad input fails fast. Waiting in Step Functions costs no Lambda time, and the budget matters because retries multiply: 3 SDK attempts under 6 Step Functions attempts is 18 calls per document. In production I'd add a `Catch` to a dead-letter queue, an SQS buffer with reserved concurrency to shape the load, and alarms on throttles and queue depth.


### 5. Enterprise Readiness

Assume a CTO prototyped this pipeline over a weekend using AI code assistants. It works for demos but needs to go to production for a Fortune 500 client.

Write a prioritized list of changes organized by:
1. **Must-fix before production** — what would block a launch?
2. **Should-fix in the first sprint** — what's important but not blocking?
3. **Nice-to-have for long-term maintainability** — what would you plan for later?

Consider security, error handling, observability, testing, CI/CD, and infrastructure hardening.

**Your answer:**

**1. Must-fix before production**
- Error handling: `Retry` with backoff and a `Catch` on every state, sending failures to a DLQ, so no document is silently dropped.
- Security: one least-privilege IAM role per function, scoped to one model ARN and its own S3 prefix; SSE-KMS, a TLS-only bucket policy, and lifecycle rules.
- Pass S3 pointers through Step Functions instead of document text. That avoids the 256 KB payload limit and keeps document data out of execution history.
- Validate model output against a schema before anything is written to `results/`.
- Real tests and CI that gate every deploy, plus immutable image tags instead of `:latest`.

**2. Should-fix in the first sprint**
- Observability: structured logs with a correlation ID, alarms on failed executions, throttles and DLQ depth, and a dashboard. For the model calls, trace each one with its prompt version, model, tokens, cost and confidence, inside the client's AWS account if documents are sensitive.
- Record the model and prompt version on every result.
- Deduplicate uploads by content hash.
- Separate dev, stage and prod environments with their own Terraform state, deployed from CI through OIDC instead of laptop credentials.

**3. Nice-to-have for long-term maintainability**
- An eval harness with a labeled golden set, and regression gates on prompt changes.
- A confidence-driven model cascade to control cost.
- A human-review UI for low-confidence results.
- X-Ray tracing across the pipeline, and Bedrock batch inference for backlogs.


### 4. Terraform — Adding a Pipeline Step

A new "validate" Lambda needs to be added to the pipeline between Extract and Aggregate. It will validate the extracted fields against a schema before writing results. List every file you'd need to change and what you'd add to each.

**Your answer:**

| File | Change |
|---|---|
| `src/tasks/validate.py` | New `validate_fields()` with a schema per document type; returns `is_valid`, `errors` and the cleaned fields. |
| `src/lambdas/validate/handler.py` | New handler that calls the task. The Dockerfile already copies `src/`, so the image needs no change. |
| `terraform/modules/lambda/main.tf` | New `aws_cloudwatch_log_group.validate` and `aws_lambda_function.validate` with `command = ["lambdas.validate.handler.handler"]`. |
| `terraform/modules/lambda/outputs.tf` | `validate_arn` and `validate_name` outputs. |
| `terraform/modules/step-functions/variables.tf` | New `validate_lambda_arn` variable. |
| `terraform/modules/step-functions/main.tf` | Add the ARN to the `lambda:InvokeFunction` resources and to the `templatefile()` variables. |
| `terraform/modules/step-functions/state_machine.asl.json` | Point Extract's `Next` at `Validate`; add a Validate task with `ResultPath: $.validate_result`, then a Choice state: valid goes to Aggregate, invalid goes to review or a Fail state. |
| `terraform/live/candidate/main.tf` | Pass `validate_lambda_arn = module.lambda.validate_arn` to the step-functions module. |
| `terraform/live/candidate/outputs.tf` | `validate_lambda_name` output, so `make update-lambdas` finds it. |
| `src/tasks/aggregate.py` | Include the validation status and errors in the result. |
| `Makefile` | Add `validate` to the function list in `update-lambdas`. |
| `tests/` | Valid and invalid cases per document type, plus the state machine contract test. |

The Lambdas share one IAM role, so the new function needs no policy change. In production I'd give each function its own role.


---

## Solutions Architect Track

*Answer this section only if your email specified Solutions Architect.*

### SA-1. Model Selection & Cost Architecture

This assessment restricts you to Claude Haiku. In a production system processing thousands of documents daily, how would you decide which model to use for classification vs. extraction? What factors (cost, latency, accuracy, token limits) would drive that decision? How would you implement cost attribution per client?

**Your answer:**

I'd choose a model per task by measuring candidates on a labeled set of our own documents, then picking the cheapest one that clears the accuracy bar. Classification has a tiny output, so a small classifier or a small LLM like Haiku handles it cheaply; low-confidence documents escalate to a stronger model, or a vision model for scans. Extraction carries more risk, so it reaches the stronger model sooner, and document length, latency targets and data-retention requirements drive the rest of the cost. For per-client attribution, I'd give each client a tagged Bedrock application inference profile and log tokens with the client ID on every call, as the pipeline already logs tokens per call.


### SA-2. Security Review

A client wants to process PHI (protected health information) through this pipeline. What changes are needed to meet HIPAA requirements? Think about data at rest, data in transit, Bedrock's data handling policies, IAM scoping, and logging.

**Your answer:**

First, the client needs a signed AWS Business Associate Agreement and only HIPAA-eligible services; Bedrock qualifies and doesn't store prompts or train on them. The biggest code-specific fix is to pass S3 pointers instead of document text through Step Functions, because execution history keeps the full PHI for 90 days, readable by anyone with console access. I'd encrypt S3, CloudWatch Logs and Step Functions with customer-managed KMS keys, enforce TLS with a bucket policy, and expire PHI and old object versions on a defined schedule. I'd also give each function its own least-privilege role and turn on CloudTrail with S3 data events, keeping audit logs (never PHI) for the required period, usually 6 years.


### SA-3. Multi-Tenancy

A client wants to offer this pipeline as a SaaS feature where each of their customers uploads documents. How would you isolate tenants? Consider S3 partitioning, IAM scoping, cost attribution, and noisy-neighbor protection.

**Your answer:**

I'd default to a pooled model with tiers: one shared stack, with large or regulated tenants, such as anyone sending PHI, moved to a dedicated account with its own Bedrock quota. In the pool, each tenant's data lives under `tenants/{tenant_id}/`, and ABAC session tags plus a per-tenant KMS encryption context stop one tenant from reading another's prefix. Cost attribution comes from a tagged Bedrock application inference profile per tenant and token counts logged with the tenant ID. For noisy neighbors, an SQS buffer with per-tenant rate limits and concurrency caps keeps one tenant's bulk upload from using up the shared Bedrock quota.


### SA-4. Production Readiness Briefing

List the key points you'd convey to a client's VP of Engineering who approved this project but hasn't seen the implementation. What changes are needed before going to production, and how would you prioritize them?

**Your answer:**

The architecture is sound and the pipeline works end to end, but it's a prototype that isn't safe to scale yet. Here's the shortest path.

- **Launch blockers (lost documents, compliance, security):** retries with a dead-letter queue, so a throttle never silently drops a document; least-privilege IAM, KMS encryption, and S3 pointers instead of document text in Step Functions; schema validation on model output; CI with real tests gating every deploy.
- **First sprint (run it):** alarms and dashboards, separate dev, stage and prod environments, and model and prompt versions recorded on every result.
- **Later (tune it):** an eval set with accuracy targets, a model cascade for cost, and human review for low-confidence results.
- **Decisions I need from you:** accuracy targets and who signs off, whether any data is PHI, throughput and latency targets, and the Bedrock budget.


---

## Data Engineer Track

*Answer this section only if your email specified Data Engineer.*

### DE-1. Data Quality & Validation

The pipeline trusts the LLM's JSON output without validation. How would you validate extracted fields against a schema? How would you handle extraction failures — retry, dead-letter queue, or flag for human review? What's your strategy?

**Your answer:**

### DE-2. Pipeline at Scale

This processes one document per Step Functions execution. Design a batch pipeline that handles 100,000 documents per day. What changes to the Step Functions architecture? Where would you parallelize, and where are the bottlenecks?

**Your answer:**

### DE-3. Observability & Data Lineage

How would you monitor this pipeline in production? What metrics, alerts, and dashboards would you build? A downstream team also needs to know which model version and prompt version produced each extraction. How would you track that lineage?

**Your answer:**

### DE-4. Caching & Deduplication

If the same document is uploaded twice, the pipeline currently processes it again at full cost. How would you implement caching or deduplication? Consider where in the pipeline to check, what to use as a cache key, and the tradeoffs of different storage options (DynamoDB, S3 metadata, Elasticache).

**Your answer:**
