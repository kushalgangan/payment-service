"""payment-service -- a demo payment API that refuses to start without its config.

Stdlib only, so it runs on the public python image with no Dockerfile or pip
install. Kubernetes mounts this file from a ConfigMap and runs it directly.

On startup the service validates REQUIRED_ENV. If any variable is missing it
logs an ERROR naming the variable and exits 1, so the pod goes into
CrashLoopBackOff. The shipped Deployment leaves PAYMENT_GATEWAY_URL unset.
"""

import json
import logging
import os
import signal
import sys
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("PORT", "8080"))

# Config the service cannot run without. There are no defaults on purpose.
REQUIRED_ENV = ["PAYMENT_GATEWAY_URL", "PAYMENT_CURRENCY"]

logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format='{"ts":"%(asctime)s","level":"%(levelname)s","service":"payment-service","msg":"%(message)s"}',
)
log = logging.getLogger("payment")

_stats = {"payments_total": 0, "payments_failed": 0}
_stats_lock = threading.Lock()


def load_config():
    """Read REQUIRED_ENV, or log every missing variable and exit 1."""
    missing = [name for name in REQUIRED_ENV if not os.environ.get(name)]
    if missing:
        for name in missing:
            log.error(f"required environment variable {name} is not set")
        log.error(f"configuration invalid, missing={','.join(missing)} -- exiting with code 1")
        sys.exit(1)
    config = {name: os.environ[name] for name in REQUIRED_ENV}
    log.info(f"config loaded gateway={config['PAYMENT_GATEWAY_URL']} currency={config['PAYMENT_CURRENCY']}")
    return config


class Handler(BaseHTTPRequestHandler):
    server_version = "payment-service/1.0"
    config = {}

    def _send(self, code, body, content_type="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/healthz":
            self._send(200, {"status": "ok"})
        elif self.path == "/readyz":
            self._send(200, {"status": "ready"})
        elif self.path == "/metrics":
            with _stats_lock:
                body = (
                    "# TYPE payment_payments_total counter\n"
                    f"payment_payments_total {_stats['payments_total']}\n"
                    "# TYPE payment_payments_failed_total counter\n"
                    f"payment_payments_failed_total {_stats['payments_failed']}\n"
                )
            self._send(200, body.encode(), "text/plain; version=0.0.4")
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/payments":
            self._send(404, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            payment = json.loads(self.rfile.read(length) or b"{}")
            amount = float(payment.get("amount", 0))
            order_id = payment.get("order_id")
            if not order_id:
                raise ValueError("payment has no order_id")
            if amount <= 0:
                raise ValueError("amount must be positive")
        except (ValueError, TypeError, AttributeError) as e:
            with _stats_lock:
                _stats["payments_failed"] += 1
            log.warning(f"payment rejected: {e}")
            self._send(400, {"error": str(e)})
            return

        payment_id = str(uuid.uuid4())
        currency = self.config["PAYMENT_CURRENCY"]
        with _stats_lock:
            _stats["payments_total"] += 1
        log.info(f"payment captured id={payment_id} order={order_id} amount={amount:.2f} {currency}")
        self._send(201, {"payment_id": payment_id, "order_id": order_id,
                         "amount": round(amount, 2), "currency": currency, "status": "captured"})

    def log_message(self, fmt, *args):
        # Skip probe and scrape noise; everything else goes through the JSON logger.
        if self.path not in ("/healthz", "/readyz", "/metrics"):
            log.info(f"{self.command} {self.path} {args[1] if len(args) > 1 else ''}")


def main():
    log.info("starting payment-service")
    Handler.config = load_config()

    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    signal.signal(signal.SIGTERM, lambda *_: threading.Thread(target=server.shutdown).start())

    log.info(f"listening on :{PORT}")
    server.serve_forever()
    log.info("shut down cleanly")


if __name__ == "__main__":
    main()
