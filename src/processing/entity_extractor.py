"""Extract Kubernetes-specific entities from text using regex."""

from __future__ import annotations

import re
from typing import Any

# K8s API versions: v1, v1beta1, v2alpha1, etc.
API_VERSION_RE = re.compile(r"\b(v\d+(?:(?:alpha|beta)\d+)?)\b")

# CVE IDs: CVE-2024-12345
CVE_ID_RE = re.compile(r"\b(CVE-\d{4}-\d{4,})\b")

# K8s resource kinds (common ones)
K8S_KINDS = [
    "Deployment",
    "StatefulSet",
    "DaemonSet",
    "ReplicaSet",
    "Pod",
    "Service",
    "Ingress",
    "IngressClass",
    "ConfigMap",
    "Secret",
    "PersistentVolume",
    "PersistentVolumeClaim",
    "StorageClass",
    "NetworkPolicy",
    "ServiceAccount",
    "ClusterRole",
    "ClusterRoleBinding",
    "Role",
    "RoleBinding",
    "CustomResourceDefinition",
    "CRD",
    "HorizontalPodAutoscaler",
    "HPA",
    "PodDisruptionBudget",
    "PDB",
    "Gateway",
    "HTTPRoute",
    "GRPCRoute",
    "ClusterPolicy",
    "Policy",
    "VirtualService",
    "DestinationRule",
]
K8S_KIND_RE = re.compile(r"\b(" + "|".join(K8S_KINDS) + r")\b")

# Semantic version: 1.31.0, v1.31.0-rc.1
SEMVER_RE = re.compile(r"\bv?(\d+\.\d+(?:\.\d+)?(?:-[\w.]+)?)\b")


def extract_entities(text: str) -> dict[str, Any]:
    """Extract K8s-relevant entities from text.

    Returns:
        {
            "api_versions": ["v1beta1", ...],
            "cve_ids": ["CVE-2024-12345", ...],
            "k8s_kinds": ["Ingress", ...],
            "versions": ["1.31.0", ...],
        }
    """
    return {
        "api_versions": sorted(set(API_VERSION_RE.findall(text))),
        "cve_ids": sorted(set(CVE_ID_RE.findall(text))),
        "k8s_kinds": sorted(set(K8S_KIND_RE.findall(text))),
        "versions": sorted(set(SEMVER_RE.findall(text))),
    }
