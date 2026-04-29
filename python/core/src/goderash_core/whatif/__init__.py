"""What-If counterfactual projector (scaffold).

Plan: take a tenant's history + an alternate policy bundle and emit a
counterfactual ledger so auditors can ask "what would have happened if?".
"""

from .projector import WhatIfPolicy, WhatIfProjector

__all__ = ["WhatIfPolicy", "WhatIfProjector"]
