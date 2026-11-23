"""MLOps helpers: validated settings, reproducibility utilities, local MLflow wrapper.

Modules:
    settings         -- read and validate deliverables/config/project.yaml (Pydantic; unknown fields rejected).
    reproducibility  -- seed, environment record, git info, data fingerprint, safe JSON write.
    tracking         -- experiment naming rules, run contract, local MLflow wrapper (MLflow loads lazily).
"""
