"""Integração com o Asaas — geração de LINKS DE PAGAMENTO da consulta.

O agente NÃO movimenta dinheiro: ele apenas cria um link de pagamento
(POST /v3/paymentLinks) e o envia ao paciente. Quem paga é o paciente,
na hora que quiser, escolhendo a forma dentro do link.

Doc oficial: https://docs.asaas.com/reference/criar-um-link-de-pagamentos

Segurança: a chave de API fica APENAS em variável de ambiente
(ASAAS_API_KEY no Easypanel) — nunca no código nem em log.
"""

from __future__ import annotations

import logging
from typing import Optional

import httpx

log = logging.getLogger(__name__)

BASE_PROD = "https://api.asaas.com/v3"
BASE_SANDBOX = "https://api-sandbox.asaas.com/v3"


# ---------------------------------------------------------------- valores
# Tabela de valores das consultas — espelha o artigo 19 da base de
# conhecimento. Usada como padrão quando o valor não é informado
# explicitamente. Se o médico não casar, o valor precisa vir do chamador.
def valor_consulta(
    medico: str, metodo: str = "cartao", parcelas: int = 3,
) -> Optional[float]:
    """Valor da CONSULTA conforme médico e forma de pagamento.

    - Dr. Fabrício: Pix R$ 445 | cartão 2x (R$ 460) ou 3x (R$ 480)
    - Dra. Karla (pediatria/rotina) e Dra. Kátia: Pix R$ 611 | cartão R$ 670
    Retorna None se o médico não for reconhecido (aí o valor é obrigatório
    no chamador).
    """
    m = (medico or "").lower()
    metodo = (metodo or "cartao").lower()
    eh_pix = metodo == "pix"
    if "fabr" in m:  # Fabrício / Fabricio
        if eh_pix:
            return 445.0
        return 480.0 if int(parcelas or 3) >= 3 else 460.0
    if "karla" in m:
        return 611.0 if eh_pix else 670.0
    if "kat" in m or "kát" in m:  # Kátia / Katia
        return 611.0 if eh_pix else 670.0
    return None


class AsaasClient:
    """Cliente mínimo da API do Asaas — só o que o agente precisa."""

    def __init__(
        self, api_key: str, env: str = "production", timeout: float = 30.0,
    ):
        self.api_key = api_key or ""
        self._base = BASE_SANDBOX if str(env).lower() == "sandbox" else BASE_PROD
        self.timeout = timeout

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    @property
    def _headers(self) -> dict:
        return {
            "access_token": self.api_key,
            "Content-Type": "application/json",
            "User-Agent": "BlinkAgent/1.0",
        }

    def criar_link_pagamento(
        self,
        nome: str,
        valor: float,
        metodo: str = "cartao",
        parcelas: int = 3,
        descricao: Optional[str] = None,
    ) -> Optional[dict]:
        """Cria um link de pagamento no Asaas.

        metodo: 'cartao' (parcelado), 'pix' (à vista) ou 'flexivel'
                (o paciente escolhe Pix/boleto/cartão dentro do link).
        Retorna {'url': ..., 'id': ...} ou None em caso de falha.
        """
        if not self.configured:
            log.warning("Asaas: ASAAS_API_KEY não configurada.")
            return None
        metodo = (metodo or "cartao").lower()
        if metodo == "pix":
            billing, charge = "PIX", "DETACHED"
        elif metodo in ("flexivel", "flex", "ambos", "undefined"):
            billing, charge = "UNDEFINED", "DETACHED"
        else:  # cartão parcelado
            billing, charge = "CREDIT_CARD", "INSTALLMENT"

        body: dict = {
            "name": (nome or "Consulta")[:200],
            "billingType": billing,
            "chargeType": charge,
            "value": round(float(valor), 2),
            "notificationEnabled": False,
            "dueDateLimitDays": 5,
        }
        if descricao:
            body["description"] = descricao[:500]
        if charge == "INSTALLMENT":
            body["maxInstallmentCount"] = max(1, int(parcelas or 1))

        try:
            with httpx.Client(timeout=self.timeout) as c:
                r = c.post(
                    f"{self._base}/paymentLinks",
                    json=body, headers=self._headers,
                )
            if r.status_code // 100 == 2:
                data = r.json() or {}
                url = data.get("url")
                if url:
                    log.info("Asaas: link de pagamento criado (id=%s)", data.get("id"))
                    return {"url": url, "id": data.get("id")}
                log.warning("Asaas: resposta sem url — %s", str(data)[:300])
            else:
                log.warning(
                    "Asaas link falhou: HTTP %d — %s",
                    r.status_code, (r.text or "")[:400],
                )
        except Exception as e:  # noqa: BLE001
            log.warning("Asaas erro ao criar link: %s", e)
        return None
