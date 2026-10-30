# payment-service -- deploy / break / fix on a local colima cluster.
# See README.md for usage.

SHELL := /bin/bash

NAMESPACE    ?= payment
DEPLOYMENT   ?= payment-service
KUBE_CONTEXT ?= colima
GATEWAY_URL  ?= https://gateway.sandbox.example.com/v1

KUBECTL := kubectl --context $(KUBE_CONTEXT)

.DEFAULT_GOAL := help

.PHONY: help
help: ## Show this help.
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage:\n  make \033[36m<target>\033[0m\n\nTargets:\n"} \
	      /^[a-zA-Z0-9_-]+:.*##/ { printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

.PHONY: deploy
deploy: ## Apply the manifests (PAYMENT_GATEWAY_URL missing -> CrashLoopBackOff).
	$(KUBECTL) apply -k .
	@echo "Watch it crash-loop: make status / make logs"

.PHONY: fix
fix: ## Set PAYMENT_GATEWAY_URL on the live Deployment so the pod starts.
	$(KUBECTL) -n $(NAMESPACE) set env deploy/$(DEPLOYMENT) PAYMENT_GATEWAY_URL=$(GATEWAY_URL)
	$(KUBECTL) -n $(NAMESPACE) rollout status deploy/$(DEPLOYMENT) --timeout=120s

.PHONY: break
break: deploy ## Re-apply the manifests, dropping PAYMENT_GATEWAY_URL again.

.PHONY: status
status: ## Show pods, restart counts, and last termination reason.
	@$(KUBECTL) -n $(NAMESPACE) get pods -l app=$(DEPLOYMENT) \
		-o custom-columns='NAME:.metadata.name,READY:.status.containerStatuses[0].ready,RESTARTS:.status.containerStatuses[0].restartCount,EXIT:.status.containerStatuses[0].lastState.terminated.exitCode,LAST_STATE:.status.containerStatuses[0].lastState.terminated.reason'

.PHONY: logs
logs: ## Show logs from the last crashed container.
	$(KUBECTL) -n $(NAMESPACE) logs deploy/$(DEPLOYMENT) --previous

.PHONY: port-forward
port-forward: ## Forward the service to localhost:8081.
	$(KUBECTL) -n $(NAMESPACE) port-forward svc/$(DEPLOYMENT) 8081:80

.PHONY: delete
delete: ## Remove everything, including the namespace.
	$(KUBECTL) delete -k .
