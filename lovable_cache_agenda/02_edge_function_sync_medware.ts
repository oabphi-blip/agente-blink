// ============================================================
// EDGE FUNCTION — sync-medware-slots
// Projeto Blink Oftalmologia · esboço 02/07/2026
// ------------------------------------------------------------
// Roda em cron (a cada 10 min). Enquanto o Medware está NO AR, puxa
// os horários livres e grava o snapshot na tabela slots_disponiveis.
// Assim, quando o Medware CAI, a Lia lê esse cache (Fonte B) e nunca
// fica sem agenda pra oferecer.
//
// Espelha exatamente voice_agent/medware.py::listar_horarios_livres:
//   Auth:     POST {base}/Acesso/login  {identificacao, senha} -> {token}
//   Horários: GET  {base}/Medware/Horarios/Listar
//             params: dataInicio, dataFim (DD/MM/YYYY), horaInicio, horaFim,
//                     codMedico, codUnidade  (NÃO enviar params zerados!)
//   Slot:     { data:"YYYY-MM-DD", horario:"HH:MM", codAgenda, codUnidade, codMedico }
//
// Secrets (Supabase → Edge Functions → Secrets):
//   MEDWARE_BASE_URL, MEDWARE_USER, MEDWARE_PASS,
//   SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
// ============================================================

import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const BASE = Deno.env.get("MEDWARE_BASE_URL")!;   // https://medware.blinkoftalmologia.com.br/api
const USER = Deno.env.get("MEDWARE_USER")!;
const PASS = Deno.env.get("MEDWARE_PASS")!;

const supabase = createClient(
  Deno.env.get("SUPABASE_URL")!,
  Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
);

// Pares (médico, unidade) que a Lia oferta. Ajustar conforme escala.
const ALVOS = [
  { cod_medico: 12080, medico_nome: "Dra. Karla Delalíbera", cod_unidade: 5, unidade_nome: "Asa Norte" },
  { cod_medico: 12080, medico_nome: "Dra. Karla Delalíbera", cod_unidade: 3, unidade_nome: "Águas Claras" },
  { cod_medico: 12081, medico_nome: "Dr. Fabrício Freitas",  cod_unidade: 5, unidade_nome: "Asa Norte" },
  { cod_medico: 12081, medico_nome: "Dr. Fabrício Freitas",  cod_unidade: 3, unidade_nome: "Águas Claras" },
];

const DIAS_SEMANA = [
  "segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
  "sexta-feira", "sábado", "domingo",
];

const JANELA_DIAS = 15;  // olha os próximos 15 dias

function ddmmyyyy(d: Date): string {
  const p = (n: number) => String(n).padStart(2, "0");
  return `${p(d.getDate())}/${p(d.getMonth() + 1)}/${d.getFullYear()}`;
}

async function medwareToken(): Promise<string> {
  const r = await fetch(`${BASE}/Acesso/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ identificacao: USER, senha: PASS }),
  });
  if (!r.ok) throw new Error(`login Medware HTTP ${r.status}`);
  const j = await r.json();
  return j.token;
}

async function horariosLivres(
  token: string, cod_medico: number, cod_unidade: number,
  dataInicio: string, dataFim: string,
): Promise<any[]> {
  // NÃO mandar params zerados — a versão light do Medware devolve [] se enviar.
  const qs = new URLSearchParams({
    dataInicio, dataFim, horaInicio: "07:00", horaFim: "19:00",
    codMedico: String(cod_medico), codUnidade: String(cod_unidade),
  });
  const r = await fetch(`${BASE}/Medware/Horarios/Listar?${qs}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!r.ok) throw new Error(`Horarios/Listar HTTP ${r.status}`);
  const j = await r.json();
  return Array.isArray(j) ? j : (j.data ?? j.registros ?? []);
}

Deno.serve(async () => {
  const inicio = new Date();
  const fim = new Date(); fim.setDate(fim.getDate() + JANELA_DIAS);
  const token = await medwareToken();

  const resumo: Record<string, number> = {};
  const capturadoEm = new Date().toISOString();

  for (const alvo of ALVOS) {
    const chave = `${alvo.medico_nome} @ ${alvo.unidade_nome}`;
    let slotsBrutos: any[];
    try {
      slotsBrutos = await horariosLivres(
        token, alvo.cod_medico, alvo.cod_unidade,
        ddmmyyyy(inicio), ddmmyyyy(fim),
      );
    } catch (e) {
      // Medware instável PRA ESSE par → NÃO apaga o snapshot anterior.
      // Mantém o último bom; só registra a falha e segue.
      console.error(`[sync-medware] ${chave} falhou: ${e.message} — mantendo snapshot anterior`);
      resumo[chave] = -1;
      continue;
    }

    const linhas = slotsBrutos
      .map((s) => {
        const dataIso = String(s.data ?? "").slice(0, 10);
        const hora = String(s.horario ?? "").slice(0, 5);
        if (!dataIso || !hora) return null;
        const dt = new Date(`${dataIso}T00:00:00`);
        const wd = (dt.getDay() + 6) % 7; // JS: 0=domingo → nossa lista 0=segunda
        return {
          cod_agenda: s.codAgenda ?? 0,
          cod_medico: alvo.cod_medico,
          medico_nome: alvo.medico_nome,
          cod_unidade: alvo.cod_unidade,
          unidade_nome: alvo.unidade_nome,
          data: dataIso,
          hora,
          dia_semana: DIAS_SEMANA[wd],
          disponivel: true,
          capturado_em: capturadoEm,
        };
      })
      .filter((x) => x !== null);

    // 1) Marca as vagas FUTURAS desse par como indisponíveis (serão
    //    reativadas abaixo se ainda aparecerem no snapshot novo).
    await supabase.from("slots_disponiveis")
      .update({ disponivel: false })
      .eq("cod_medico", alvo.cod_medico)
      .eq("cod_unidade", alvo.cod_unidade)
      .gte("data", inicio.toISOString().slice(0, 10));

    // 2) Upsert das vagas realmente livres agora.
    if (linhas.length > 0) {
      await supabase.from("slots_disponiveis")
        .upsert(linhas, { onConflict: "cod_medico,cod_unidade,data,hora" });
    }
    resumo[chave] = linhas.length;
  }

  // 3) Higiene: remove vagas passadas.
  await supabase.from("slots_disponiveis")
    .delete().lt("data", inicio.toISOString().slice(0, 10));

  return new Response(JSON.stringify({ ok: true, capturado_em: capturadoEm, resumo }), {
    headers: { "Content-Type": "application/json" },
  });
});
