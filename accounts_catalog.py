"""
Contas Twilio — ordem e nomes canónicos para CSV e consumo no front (Lovable).

Todos os extractors devem usar `accounts_from_env()` para a coluna `Conta`
ser consistente entre conf_usage_billing_*, conf_delivery_*, conf_*_marco e conf_saldos.
"""

from __future__ import annotations

import os
from typing import Any

# (SID_ENV, TOKEN_ENV, nome_curto, categoria_ui)
_DEFINITIONS: tuple[tuple[str, str, str, str], ...] = (
    ("RECUPERACAO_NS_SID", "RECUPERACAO_NS_TOKEN", "NS", "Recuperação"),
    ("BROADCAST_JOAO_SID", "BROADCAST_JOAO_TOKEN", "Joao", "Broadcast"),
    ("BROADCAST_BERNARDO_SID", "BROADCAST_BERNARDO_TOKEN", "Bernardo", "Broadcast"),
    ("BROADCAST_RAFA_SID", "BROADCAST_RAFA_TOKEN", "Rafa", "Broadcast"),
    ("STANDBY_HAVEN_SID", "STANDBY_HAVEN_TOKEN", "Havenmove", "Standby"),
    ("STANDBY_REHABLEAF_SID", "STANDBY_REHABLEAF_TOKEN", "Rehableaf", "Standby"),
    ("STANDBY_RICHARD_SID", "STANDBY_RICHARD_TOKEN", "Richard", "Standby"),
    ("STANDBY_NATUREMOVE_SID", "STANDBY_NATUREMOVE_TOKEN", "Naturemove", "Standby"),
)

CANONICAL_ACCOUNT_NAMES: tuple[str, ...] = tuple(d[2] for d in _DEFINITIONS)

ORG_SUM_ROW_ACCOUNT = "__ORG_SUM__"


def accounts_from_env() -> list[dict[str, Any]]:
    """Lista fixa em ordem; sid/token lidos do ambiente (.env / GitHub Secrets)."""
    return [
        {
            "sid": os.getenv(sk),
            "token": os.getenv(tk),
            "nome": nome,
            "categoria": cat,
        }
        for sk, tk, nome, cat in _DEFINITIONS
    ]
