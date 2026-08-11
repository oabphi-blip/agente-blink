/* ============================================================
   EXTRAIR LEADS — 0-ENTRADA × CAMPANHA JULHO/2026
   ============================================================
   Como usar:
   1. Vá pra esta URL no Chrome (cole na barra):
      https://univeja.kommo.com/leads/list/pipeline/8601819/?filter[pipe][8601819][]=96441724&filter[cf][1260440][]=927043&useFilter=y
   2. Aguarde a lista carregar.
   3. Cmd+Opt+J abre o DevTools (aba Console).
   4. Se aparecer "allow pasting", digita: allow pasting + Enter.
   5. Cole TODO este arquivo e Enter.
   6. Aguarde ~1-2min (vai logando o progresso).
   7. JSON cai no clipboard + é salvo em window._LEADS_JULHO_JSON.
   8. Cole num arquivo .json e me mande o path, ou só cole no chat.
   ============================================================ */

(async () => {
  const PIPELINE = 8601819;
  const STATUS_ENTRADA = 96441724;
  const FIELD_CAMPANHAS = 1260440;
  const ENUM_JULHO = 927043;

  const sleep = (ms) => new Promise(r => setTimeout(r, ms));

  console.log('🚀 Buscando leads em 0-ENTRADA do pipeline ATENDE...');

  // 1) Lista todos leads do status 0-ENTRADA (com custom_fields embutido)
  let allLeads = [];
  let page = 1;
  while (true) {
    const url = `/api/v4/leads?filter[statuses][0][pipeline_id]=${PIPELINE}&filter[statuses][0][status_id]=${STATUS_ENTRADA}&with=contacts&limit=250&page=${page}`;
    const r = await fetch(url, { credentials: 'include' });
    if (!r.ok) {
      console.error(`❌ Page ${page} HTTP ${r.status}`);
      break;
    }
    if (r.status === 204) break;
    const j = await r.json();
    const leads = j?._embedded?.leads || [];
    if (!leads.length) break;
    allLeads = allLeads.concat(leads);
    console.log(`📄 Page ${page}: +${leads.length} (total ${allLeads.length})`);
    if (leads.length < 250) break;
    page++;
    await sleep(300);
  }
  console.log(`✅ Total em 0-ENTRADA: ${allLeads.length} leads`);

  // 2) Pra cada lead, buscar detalhe COM custom_fields_values
  console.log(`🔎 Buscando custom_fields de cada lead (rate-limited)...`);
  const julho = [];
  let i = 0;
  for (const ld of allLeads) {
    i++;
    try {
      const r2 = await fetch(`/api/v4/leads/${ld.id}?with=contacts`, { credentials: 'include' });
      if (!r2.ok) {
        console.warn(`  ⚠️ lead ${ld.id} HTTP ${r2.status}`);
        await sleep(500);
        continue;
      }
      const ld2 = await r2.json();
      const cfs = ld2.custom_fields_values || [];
      const camp = cfs.find(c => c.field_id === FIELD_CAMPANHAS);
      const tem_julho = camp?.values?.some(v => v.enum_id === ENUM_JULHO);
      if (tem_julho) {
        // Pegar telefone do contato principal
        const contact_id = ld2._embedded?.contacts?.[0]?.id;
        let telefone = null;
        let nome_contato = null;
        if (contact_id) {
          const r3 = await fetch(`/api/v4/contacts/${contact_id}`, { credentials: 'include' });
          if (r3.ok) {
            const ct = await r3.json();
            nome_contato = ct.name;
            const phoneField = (ct.custom_fields_values || []).find(c => c.field_code === 'PHONE');
            telefone = phoneField?.values?.[0]?.value || null;
          }
          await sleep(200);
        }
        // Resumo dos custom fields preenchidos (só field_id + valor)
        const cfs_resumo = cfs.map(c => ({
          field_id: c.field_id,
          field_name: c.field_name,
          values: c.values?.map(v => v.value ?? v.enum_id ?? v).slice(0, 3)
        }));
        julho.push({
          lead_id: ld2.id,
          lead_name: ld2.name,
          status_id: ld2.status_id,
          contact_id,
          nome_contato,
          telefone,
          campos_preenchidos: cfs_resumo,
          updated_at: ld2.updated_at,
          created_at: ld2.created_at,
        });
        console.log(`  ✅ [${i}/${allLeads.length}] ${ld2.id} ${ld2.name} — ${telefone || 'sem tel'}`);
      }
    } catch (e) {
      console.warn(`  ❌ lead ${ld.id} exception:`, e.message);
    }
    if (i % 30 === 0) await sleep(800); // throttle leve cada 30
    await sleep(150);
  }

  console.log(`\n🎯 RESULTADO: ${julho.length} leads em 0-ENTRADA × Julho/2026`);
  console.log(`📋 IDs:`, julho.map(l => l.lead_id).join(', '));

  // 3) Salva no window + copia pro clipboard
  window._LEADS_JULHO_JSON = julho;
  const json = JSON.stringify(julho, null, 2);
  try {
    await navigator.clipboard.writeText(json);
    console.log('📋 ✅ JSON copiado pro clipboard. Cole num arquivo .json no Mac.');
  } catch (e) {
    console.warn('Clipboard falhou:', e.message, '— acesse via window._LEADS_JULHO_JSON');
  }
  console.log('\n📊 RESUMO COMPACTO (use isso pra Claude):');
  console.log(JSON.stringify(julho.map(l => ({
    lead_id: l.lead_id,
    nome: l.lead_name,
    tel: l.telefone,
    contact_id: l.contact_id,
  })), null, 0));
})();
