# March 1 incident

The billing-api started throwing elevated errors shortly after the 09:52 deployment.
The likely cause is connection pool exhaustion introduced by the new billing-api rollout.
Operations mitigated by reducing background reconciliation load.
