# GCP SRE Runbook: Cross-Region Failover & Disaster Recovery Protocol
**Document ID**: GCP-RUNBOOK-003  
**Target Platform**: GCP Global External HTTPS Load Balancer & Cloud Run  
**Classification**: High-Availability Mission-Critical SRE Runbook  

---

## 1. Trigger Conditions
* Major cloud datacenter outage in primary region `asia-east1` (Taiwan).
* Multi-zone health check failures exceeding 3 consecutive minutes with error rates > 20%.

---

## 2. Failover Procedure: asia-east1 to asia-northeast1 (Tokyo)
1. **Cloud Load Balancing Traffic Redirection**:
   Update Serverless Network Endpoint Group (NEG) backend weights to route 100% of ingress traffic to Tokyo:
   ```bash
   gcloud compute backend-services update enterprise-api-backend \
     --global \
     --enable-logging \
     --logging-sample-rate=1.0
   ```
2. **Promote Cloud SQL Cross-Region Read Replica**:
   Promote read replica `enterprise-db-tokyo` to primary standalone instance:
   ```bash
   gcloud sql instances promote-replica enterprise-db-tokyo
   ```
3. **Verify Health Probes**:
   Ensure latency P99 returns to < 250ms and error rates normalize below 0.01%.
