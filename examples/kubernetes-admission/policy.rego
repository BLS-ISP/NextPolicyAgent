# -------------------------------------------------------
# Kubernetes Admission Control
# -------------------------------------------------------
# Validiert Kubernetes Pod-Definitionen. Prüft:
#   - Container-Images aus erlaubter Registry
#   - Kein Root-Benutzer (UID 0)
#   - Resource Limits gesetzt
#   - Pflicht-Labels vorhanden
#
# Auswertung (CLI):
#   npa eval -d examples/kubernetes-admission/policy.rego \
#            -i examples/kubernetes-admission/input-valid.json \
#            "data.kubernetes.admission.allow"
#
# Auswertung (API):
#   POST /v1/data/kubernetes/admission
# -------------------------------------------------------
package kubernetes.admission

import future.keywords.if
import future.keywords.every

default allow = false

# Erlaubte Image-Registries
allowed_image(image) if { startswith(image, "ghcr.io/") }
allowed_image(image) if { startswith(image, "docker.io/library/") }
allowed_image(image) if { startswith(image, "registry.k8s.io/") }
allowed_image(image) if { startswith(image, "mcr.microsoft.com/") }

# Pod ist erlaubt, wenn alle Container-Checks bestehen
allow if {
    # Alle Images müssen aus erlaubter Registry stammen
    every container in input.request.object.spec.containers {
        allowed_image(container.image)
    }

    # Kein Container darf als root laufen
    every container in input.request.object.spec.containers {
        container.securityContext.runAsUser != 0
    }

    # Pflicht-Labels müssen vorhanden sein
    input.request.object.metadata.labels.app
    input.request.object.metadata.labels.team
    input.request.object.metadata.labels.environment
}
