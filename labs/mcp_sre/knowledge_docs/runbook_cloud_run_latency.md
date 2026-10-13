# GCP SRE Runbook: Cloud Run P99 Latency & Cold Start Troubleshooting
**Document ID**: GCP-RUNBOOK-001  
**Target Platform**: Google Cloud Run (Serverless Container Platform)  
**Classification**: Enterprise Production Standard  

---

## 1. Symptom Diagnosis & Trigger Conditions
* **Alert Trigger**: P99 HTTP latency exceeds 800ms over a 5-minute rolling window, or HTTP 504 Gateway Timeout rate exceeds 0.5%.
* **Root Cause 1 (Container Cold Starts)**: Cloud Run scaling instances down to 0 during traffic lulls, causing subsequent cold request initialization delays (1.2s - 3.5s for JVM/Python runtimes).
* **Root Cause 2 (Concurrency Saturation)**: `container-concurrency` limit set too high (> 80), resulting in CPU thread contention on single vCPU container allocations.
* **Root Cause 3 (Downstream Cloud SQL Exhaustion)**: Each Cloud Run replica opening unbounded database connections without PgBouncer.

---

## 2. Standard Remediation Protocol
1. **Immediate Scaling Adjustment (Stop the Bleeding)**:
   Increase `min-instances` to ensure warm container headroom:
   ```bash
   gcloud run services update <SERVICE_NAME> \
     --min-instances=3 \
     --max-instances=30 \
     --region=asia-east1
   ```
2. **Optimize Concurrency Budget**:
   For I/O-heavy Python FastAPI services, reduce container concurrency from 80 to 20:
   ```bash
   gcloud run services update <SERVICE_NAME> \
     --concurrency=20 \
     --cpu=2 \
     --memory=2Gi
   ```
3. **CPU Boost During Startup**:
   Enable CPU boost to allocate maximum CPU capacity during container initialization:
   ```bash
   gcloud run services update <SERVICE_NAME> --cpu-boost
   ```
