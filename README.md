# payment-service

A small Python payment API used to demo misconfiguration incidents on Kubernetes.
At startup it checks for required environment variables. The shipped Deployment
leaves **`PAYMENT_GATEWAY_URL` unset**, so the service logs an error and exits 1,
and the pod goes into `CrashLoopBackOff`.

- **No Dockerfile.** It runs on the public `python:3.12-slim` image. `app/main.py` is
  mounted from a ConfigMap that kustomize generates.
- **Stdlib only.** Nothing to `pip install`.

```
payment-service/
├── app/main.py            # the service
├── k8s/
│   ├── namespace.yaml     # namespace: payment
│   ├── deployment.yaml    # env, resources, probes, ConfigMap mount
│   └── service.yaml       # ClusterIP :80 -> :8080
├── kustomization.yaml     # builds the ConfigMap from app/main.py
└── Makefile
```

## Endpoints

| Method | Path        | Description                                                  |
|--------|-------------|--------------------------------------------------------------|
| POST   | `/payments` | `{"order_id":"abc","amount":39.98}` → `201` captured payment |
| GET    | `/healthz`  | Liveness                                                     |
| GET    | `/readyz`   | Readiness                                                    |
| GET    | `/metrics`  | Prometheus: payments, failed payments                        |

## Configuration

| Variable              | Required | In the manifest | Purpose                       |
|-----------------------|----------|-----------------|-------------------------------|
| `PAYMENT_GATEWAY_URL` | yes      | **no**          | Upstream payment gateway      |
| `PAYMENT_CURRENCY`    | yes      | `USD`           | Currency for captured amounts |
| `PORT`                | no       | `8080`          | Listen port                   |

## The failure

With the variable missing, the container logs this and exits 1:

```
{"ts":"...","level":"INFO","service":"payment-service","msg":"starting payment-service"}
{"ts":"...","level":"ERROR","service":"payment-service","msg":"required environment variable PAYMENT_GATEWAY_URL is not set"}
{"ts":"...","level":"ERROR","service":"payment-service","msg":"configuration invalid, missing=PAYMENT_GATEWAY_URL -- exiting with code 1"}
```

Kubernetes reports `Error` (exit code 1) as the last termination reason and
backs off restarts. The fix is to add `PAYMENT_GATEWAY_URL` to the Deployment env.

## Usage (local colima cluster)

```sh
make deploy        # PAYMENT_GATEWAY_URL missing: Error (exit 1), CrashLoopBackOff
make status        # restarts, exit code, last termination reason
make logs          # logs from the crashed container
make fix           # set PAYMENT_GATEWAY_URL on the live Deployment: 1/1 Running
make break         # re-apply the manifests, dropping the variable again
make delete        # tear down
```

Try the API after `make fix`:

```sh
make port-forward
curl -XPOST localhost:8081/payments -d '{"order_id":"abc","amount":39.98}'
```

Editing `app/main.py` and re-running `make deploy` rolls the pods. The
ConfigMap name carries a content hash.
