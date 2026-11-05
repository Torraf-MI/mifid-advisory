"use strict";
// Pagina dimostrativa: usa solo l'API REST, come farebbe qualunque altro front-end.

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const COLORI = ["--c1", "--c2", "--c3", "--c4", "--c5", "--c6", "--c7", "--c8", "--c9", "--c10"].map(
  (c) => getComputedStyle(document.documentElement).getPropertyValue(c).trim());
const STRUMENTI = { liquidita: "Liquidità e fondi monetari", obbligazioni: "Obbligazioni", fondi_etf: "Fondi ed ETF",
  azioni: "Azioni", certificati: "Certificati e strutturati", derivati: "Derivati e leva" };
const ESITI = { adeguato: "Adeguata", adeguato_con_avvertenze: "Adeguata con avvertenze", non_adeguato: "Non adeguata",
  adeguata: "Adeguata", non_adeguata: "Non adeguata", accettata: "Accettata", rifiutata: "Rifiutata",
  ok: "ok", attenzione: "attenzione", ko: "ko" };
const SERIE = { estr: "€STR", bce_depositi: "Tasso sui depositi BCE", inflazione_it: "Inflazione Italia (HICP)",
  inflazione_ea: "Inflazione area euro (HICP)" };

const stato = { token: null, utente: null, prodotti: {}, cliente: null, proposta: null };
const pct = (x, d = 1) => (x * 100).toFixed(d).replace(".", ",") + "%";
const eur = (x) => "€ " + Math.round(x).toLocaleString("it-IT");
const data = (s) => new Date(s).toLocaleDateString("it-IT");
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const etichetta = (e) => `<span class="etichetta e-${e}">${ESITI[e] || e}</span>`;

function memoria(chiave, valore) {
  try {
    if (valore === undefined) return sessionStorage.getItem(chiave);
    if (valore === null) sessionStorage.removeItem(chiave); else sessionStorage.setItem(chiave, valore);
  } catch { return null; }
}

async function api(percorso, opzioni = {}) {
  const r = await fetch(percorso, { ...opzioni, headers: { "Content-Type": "application/json",
    ...(stato.token ? { Authorization: "Bearer " + stato.token } : {}), ...(opzioni.headers || {}) } });
  if (r.status === 401 && stato.token) { esci(); throw new Error("Sessione scaduta"); }
  const tipo = r.headers.get("content-type") || "";
  const corpo = tipo.includes("json") ? await r.json() : await r.text();
  if (!r.ok) {
    const d = corpo.detail;
    throw new Error(Array.isArray(d) ? d.map((e) => `${e.loc.slice(1).join(".")}: ${e.msg}`).join("; ") : d || r.statusText);
  }
  return corpo;
}

// ------------------------------------------------------------------------------------------ accesso
async function accedi(email) {
  try {
    const r = await fetch("/auth/token", { method: "POST", body: new URLSearchParams({ username: email, password: "demo" }) });
    if (!r.ok) throw new Error((await r.json()).detail);
    stato.token = (await r.json()).access_token;
    memoria("token", stato.token);
    await avvia();
  } catch (e) { $("#errore-login").textContent = e.message; }
}

function esci() {
  stato.token = null; memoria("token", null);
  $("#nav").hidden = true; $("#utente").innerHTML = "";
  mostra("login");
}

async function avvia() {
  stato.utente = await api("/utenti/me");
  $("#utente").innerHTML = `${esc(stato.utente.nome)} · ${stato.utente.ruolo} <button class="secondario" id="b-esci">Esci</button>`;
  $("#b-esci").onclick = esci;
  $$("[data-ruoli]").forEach((el) => { el.hidden = !el.dataset.ruoli.split(" ").includes(stato.utente.ruolo); });
  $("#nav").hidden = false;
  for (const p of await api("/prodotti")) stato.prodotti[p.isin] = p;
  mostra("clienti");
}

function mostra(vista) {
  $$(".vista").forEach((v) => { v.hidden = v.id !== "v-" + vista; });
  $$("nav button").forEach((b) => b.classList.toggle("attivo", b.dataset.vista === vista));
  ({ clienti: caricaClienti, audit: caricaAudit, mercato: caricaMercato })[vista]?.();
}

// ------------------------------------------------------------------------------------------ clienti
async function caricaClienti(selezionato) {
  const clienti = await api("/clienti");
  $("#elenco").innerHTML = clienti.map((c) => `<li data-id="${c.id}"><span>${esc(c.cognome)} ${esc(c.nome)}</span><small>#${c.id}</small></li>`).join("")
    || `<li class="tenue">Nessun cliente</li>`;
  $$("#elenco li[data-id]").forEach((li) => { li.onclick = () => apriCliente(+li.dataset.id); });
  const id = selezionato || stato.cliente?.id || clienti[0]?.id;
  if (id) apriCliente(id);
}

async function apriCliente(id, propostaId) {
  $$("#elenco li").forEach((li) => li.classList.toggle("attivo", +li.dataset.id === id));
  const c = await api(`/clienti/${id}`);
  stato.cliente = c;
  const p = c.profilo, operativo = ["consulente", "admin"].includes(stato.utente.ruolo);
  const scaduto = p && new Date(p.valido_fino) < new Date();
  let html = `<div class="scheda"><div class="titolo-riga"><h2>${esc(c.nome)} ${esc(c.cognome)}</h2>
    ${operativo ? `<button class="secondario" id="b-questionario">${p ? "Aggiorna il questionario" : "Compila il questionario"}</button>` : ""}</div>
    <p class="tenue">${c.data_nascita ? "Nato/a il " + data(c.data_nascita) + " · " : ""}${esc(c.email || "")} · cliente dal ${data(c.creato_il)}</p>`;
  if (p) {
    const d = p.dettagli;
    html += `<div class="kpi">
      <div><span>Classe di rischio</span><strong>${d.classe} · ${d.nome}</strong></div>
      <div><span>Volatilità massima</span><strong>${pct(d.limiti.volatilita_max, 0)}</strong></div>
      <div><span>Perdita annua sostenibile</span><strong>${pct(Math.min(d.capacita_perdita, d.limiti.perdita_max), 0)}</strong></div>
      <div><span>Orizzonte</span><strong>${d.orizzonte_anni} anni</strong></div>
      <div><span>Profilo valido fino al</span><strong>${data(p.valido_fino)}</strong></div></div>
      <h3>Componenti del profilo</h3><div class="componenti">${Object.entries(d.componenti).map(([k, v]) => `
        <div class="componente"><span>${k}</span><div class="barra"><i class="${k === d.vincolo ? "vincolo" : ""}" style="width:${v * 20}%"></i></div>
        <span>classe ${v}${k === d.vincolo ? " ◂" : ""}</span></div>`).join("")}</div>
      <p class="tenue piccolo">La classe finale è la più prudente fra le componenti (◂ quella che la determina).
        Strumenti ammessi: ${d.classi_ammesse.map((x) => STRUMENTI[x]).join(", ")}.</p>
      ${d.incoerenze.map((i) => `<div class="nota">${esc(i)}</div>`).join("")}
      ${scaduto ? `<div class="nota">Il profilo è scaduto: aggiornare il questionario prima di una nuova proposta.</div>` : ""}`;
  } else {
    html += `<p class="tenue">Il cliente non ha ancora compilato il questionario MiFID.</p>`;
  }
  html += `</div>`;
  if (p && operativo && !scaduto) {
    html += `<div class="scheda"><div class="titolo-riga"><h2>Nuova proposta</h2></div>
      <div class="azioni" style="justify-content:flex-start;align-items:end">
        <label>Importo da investire (€) <input id="importo" type="number" min="1000" step="1000" value="50000"></label>
        <button id="b-proposta">Proposta ottimizzata</button></div><p id="errore-proposta" class="errore"></p></div>`;
  }
  if (c.proposte.length) {
    html += `<div class="scheda"><h2>Proposte</h2><table class="tabella"><thead><tr><th>#</th><th>Data</th><th class="n">Importo</th><th>Metodo</th><th>Stato</th></tr></thead><tbody>
      ${c.proposte.map((x) => `<tr data-id="${x.id}" style="cursor:pointer"><td>${x.id}</td><td>${data(x.creato_il)}</td><td class="n">${eur(x.importo)}</td>
        <td>${x.metodo}</td><td>${etichetta(x.stato)}</td></tr>`).join("")}</tbody></table></div><div id="proposta"></div>`;
  }
  $("#dettaglio").innerHTML = html;
  $("#b-questionario")?.addEventListener("click", () => apriQuestionario(c));
  $("#b-proposta")?.addEventListener("click", nuovaProposta);
  $$("#dettaglio tr[data-id]").forEach((tr) => { tr.onclick = () => apriProposta(+tr.dataset.id); });
  if (c.proposte.length) apriProposta(propostaId || c.proposte[0].id);
}

async function nuovaProposta() {
  const b = $("#b-proposta"); b.disabled = true; $("#errore-proposta").textContent = "";
  try {
    const p = await api(`/clienti/${stato.cliente.id}/proposte`, { method: "POST", body: JSON.stringify({ importo: +$("#importo").value }) });
    await apriCliente(stato.cliente.id, p.id);
  } catch (e) { $("#errore-proposta").textContent = e.message; b.disabled = false; }
}

async function apriProposta(id) {
  const p = await api(`/proposte/${id}`);
  stato.proposta = p;
  const m = p.verifica.metriche, operativo = ["consulente", "admin"].includes(stato.utente.ruolo);
  const decidibile = operativo && ["adeguata", "non_adeguata"].includes(p.stato);
  $$("#dettaglio tr[data-id]").forEach((tr) => tr.classList.toggle("attivo", +tr.dataset.id === id));
  const colore = (i) => COLORI[i % COLORI.length];
  $("#proposta").innerHTML = `<div class="scheda">
    <div class="titolo-riga"><h2>Proposta n. ${p.id} · ${eur(p.importo)}</h2><span>${etichetta(p.verifica.esito)}${["accettata", "rifiutata"].includes(p.stato) ? " " + etichetta(p.stato) : ""}</span></div>
    <div class="allocazione">${p.posizioni.map((x, i) => `<i style="width:${x.peso * 100}%;background:${colore(i)}" title="${esc(stato.prodotti[x.isin]?.nome)}"></i>`).join("")}</div>
    <table class="tabella"><thead><tr><th>Prodotto</th><th>Tipologia</th><th class="n">SRI</th><th class="n">Costi annui</th><th class="n">Peso</th><th class="n">Importo</th></tr></thead><tbody>
    ${p.posizioni.map((x, i) => { const q = stato.prodotti[x.isin] || { dati: {} }; return `<tr>
      <td><span class="pallino" style="background:${colore(i)}"></span>${esc(q.nome)} <span class="hash">${x.isin}</span></td>
      <td>${STRUMENTI[q.classe_strumento] || ""}</td><td class="n">${q.sri}</td><td class="n">${pct(q.dati.ter || 0, 2)}</td>
      <td class="n">${pct(x.peso, 0)}</td><td class="n">${eur(x.importo)}</td></tr>`; }).join("")}</tbody></table>
    <div class="kpi">
      <div><span>Rendimento atteso netto</span><strong>${pct(m.rendimento_atteso)}</strong></div>
      <div><span>Volatilità</span><strong>${pct(m.volatilita)}</strong></div>
      <div><span>Perdita media 5% peggiori</span><strong>${pct(m.es_95)}</strong></div>
      <div><span>Costi annui</span><strong>${pct(m.costo_annuo, 2)}</strong></div>
      <div><span>Scenario moderato a ${m.orizzonte_anni} anni</span><strong>${eur(m.scenari.moderato)}</strong></div>
      <div><span>Quota sostenibile</span><strong>${pct(m.quota_sostenibile, 0)}</strong></div></div>
    <h3>Verifica di adeguatezza</h3>
    <table class="tabella"><tbody>${rigaProdotti(p.verifica.controlli.filter((c) => c.area === "Prodotto"))}
      ${p.verifica.controlli.filter((c) => c.area !== "Prodotto").map((c) => `<tr><td>${esc(c.descrizione)}<br><span class="tenue piccolo">${esc(c.area)}${c.riferimento ? " · " + esc(c.riferimento) : ""}</span></td>
      <td>${etichetta(c.esito)}</td><td>${esc(c.dettaglio)}</td></tr>`).join("")}</tbody></table>
    <div class="azioni"><button class="secondario" id="b-dichiarazione">Dichiarazione di adeguatezza</button>
      ${decidibile ? `<button class="pericolo" id="b-rifiuta">Il cliente rifiuta</button>
      <button id="b-accetta" ${p.stato !== "adeguata" ? "disabled title='Una proposta non adeguata non può essere accettata'" : ""}>Il cliente accetta</button>` : ""}</div>
    <p id="errore-decisione" class="errore"></p></div>`;
  $("#b-dichiarazione").onclick = () => dichiarazione(p.id);
  $("#b-accetta")?.addEventListener("click", () => decidi(p.id, "accetta"));
  $("#b-rifiuta")?.addEventListener("click", () => decidi(p.id, "rifiuta"));
}

function rigaProdotti(cc) {
  if (!cc.length) return "";
  const peggiore = ["ko", "attenzione", "ok"].find((e) => cc.some((c) => c.esito === e));
  const ok = cc.filter((c) => c.esito === "ok").length;
  return `<tr><td colspan="3"><details><summary><strong>Adeguatezza dei singoli prodotti</strong> ${etichetta(peggiore)}
    <span class="tenue">${ok} su ${cc.length} adeguati: conoscenza ed esperienza, rischio (SRI), periodo di detenzione,
    mercato di riferimento, sostenibilità</span></summary><table class="tabella">${cc.map((c) => `<tr><td>${esc(c.descrizione)}</td>
    <td>${etichetta(c.esito)}</td><td>${esc(c.dettaglio)}</td></tr>`).join("")}</table></details></td></tr>`;
}

async function decidi(id, azione) {
  try { await api(`/proposte/${id}/${azione}`, { method: "POST", body: "{}" }); await apriCliente(stato.cliente.id, id); }
  catch (e) { $("#errore-decisione").textContent = e.message; }
}

async function dichiarazione(id) {
  const finestra = window.open("", "_blank");
  const html = await api(`/proposte/${id}/dichiarazione`);
  const url = URL.createObjectURL(new Blob([html], { type: "text/html" }));
  if (finestra) finestra.location = url; else location.href = url;
}

// ------------------------------------------------------------------------------------- questionario
function apriQuestionario(cliente) {
  const f = $("#f-questionario"), d = $("#d-questionario");
  f.reset(); $("#errore-questionario").textContent = "";
  f.dataset.cliente = cliente ? cliente.id : "";
  f.dataset.nascita = cliente?.data_nascita || "";
  $("#anagrafica").hidden = !!cliente;
  $$("#anagrafica input").forEach((i) => { i.required = !cliente && i.name !== "email"; });
  $("#titolo-questionario").textContent = cliente ? `Questionario MiFID · ${cliente.nome} ${cliente.cognome}` : "Nuovo cliente e questionario MiFID";
  $("#strumenti").innerHTML = Object.entries(STRUMENTI).map(([k, v], i) => `<tr><td>${v}</td>
    <td><input type="checkbox" name="conosce_${k}" ${i < 3 ? "checked" : ""}></td>
    <td><select name="operazioni_${k}"><option value="mai">mai</option><option value="occasionale" ${i < 3 ? "selected" : ""}>da 1 a 5</option><option value="frequente">più di 5</option></select></td></tr>`).join("");
  d.showModal();
}

function eta(nascita) {
  const n = new Date(nascita), o = new Date();
  return o.getFullYear() - n.getFullYear() - (o < new Date(o.getFullYear(), n.getMonth(), n.getDate()) ? 1 : 0);
}

function leggiQuestionario(f) {
  const v = (n) => f.elements[n].value, num = (n) => +f.elements[n].value, sp = (n) => f.elements[n].checked;
  return {
    eta: eta(f.dataset.nascita || v("data_nascita")),
    conoscenza: { titolo_studio: v("titolo_studio"), professione_finanziaria: sp("professione_finanziaria"),
      strumenti: Object.keys(STRUMENTI).map((k) => ({ classe: k, conosce: sp("conosce_" + k), operazioni_3_anni: v("operazioni_" + k) })),
      risposta_tassi_obbligazioni: v("risposta_tassi_obbligazioni"), risposta_diversificazione: v("risposta_diversificazione"),
      risposta_barriera: v("risposta_barriera") },
    finanze: { reddito_annuo_netto: num("reddito_annuo_netto"), spese_annue: num("spese_annue"),
      patrimonio_finanziario: num("patrimonio_finanziario"), patrimonio_immobiliare: num("patrimonio_immobiliare"),
      debiti: num("debiti"), reddito_stabile: sp("reddito_stabile"), persone_a_carico: num("persone_a_carico") },
    obiettivi: { obiettivo: v("obiettivo"), orizzonte_anni: num("orizzonte_anni"), quota_liquida_12_mesi: num("quota_liquida_12_mesi") / 100 },
    rischio: { reazione_ribasso_20: v("reazione_ribasso_20"), perdita_massima_annua: num("perdita_massima_annua") / 100,
      scenario_preferito: num("scenario_preferito") },
    sostenibilita: sp("ha_preferenze")
      ? { ha_preferenze: true, quota_minima_sostenibile: num("quota_minima_sostenibile") / 100,
          quota_minima_tassonomia: num("quota_minima_tassonomia") / 100, considera_pai: sp("considera_pai") }
      : { ha_preferenze: false },
  };
}

async function salvaQuestionario(ev) {
  const f = $("#f-questionario");
  if (ev.submitter?.value !== "salva") return;
  ev.preventDefault();
  if (!f.reportValidity()) return;
  try {
    const q = leggiQuestionario(f);
    let id = +f.dataset.cliente;
    if (!id) {
      const c = await api("/clienti", { method: "POST", body: JSON.stringify({ nome: f.elements.nome.value,
        cognome: f.elements.cognome.value, data_nascita: f.elements.data_nascita.value, email: f.elements.email.value || null }) });
      id = c.id; f.dataset.cliente = id;  // se il questionario è respinto, il cliente non viene ricreato
      f.dataset.nascita = c.data_nascita; $("#anagrafica").hidden = true;
    }
    await api(`/clienti/${id}/questionari`, { method: "POST", body: JSON.stringify(q) });
    $("#d-questionario").close();
    stato.cliente = { id };
    await caricaClienti(id);
  } catch (e) { $("#errore-questionario").textContent = e.message; }
}

// ---------------------------------------------------------------------------------------------- audit
async function caricaAudit() {
  const eventi = await api("/audit?limite=200");
  $("#eventi").innerHTML = eventi.map((e) => `<tr><td>${e.id}</td><td>${new Date(e.momento).toLocaleString("it-IT")}</td>
    <td>${esc(e.utente)}</td><td>${esc(e.azione.replaceAll("_", " "))}</td><td>${esc(e.entita)}${e.entita_id ? " #" + e.entita_id : ""}</td>
    <td class="hash" title="precedente: ${e.hash_precedente}">${e.hash.slice(0, 16)}…</td></tr>`).join("");
}

async function verificaCatena() {
  const r = await api("/audit/verifica");
  $("#esito-catena").innerHTML = r.integro
    ? `${etichetta("ok")} Catena integra: ${r.eventi} eventi verificati, nessuna modifica o cancellazione.`
    : `${etichetta("ko")} Catena interrotta all'evento n. ${r.primo_errore}: ${esc(r.motivo)}.`;
}

// -------------------------------------------------------------------------------------------- mercato
async function caricaMercato() {
  const dati = await api("/mercato?limite=36");
  const per = {};
  for (const d of dati) (per[d.serie] ||= []).push(d);
  $("#serie").innerHTML = Object.entries(SERIE).map(([k, nome]) => {
    const s = (per[k] || []).sort((a, b) => a.data.localeCompare(b.data));
    if (!s.length) return "";
    const v = s.map((x) => x.valore), min = Math.min(...v), max = Math.max(...v), r = max - min || 1;
    const punti = v.map((x, i) => `${(i / Math.max(v.length - 1, 1)) * 300},${62 - ((x - min) / r) * 54}`).join(" ");
    const u = s[s.length - 1];
    return `<div class="scheda"><span class="tenue">${nome}</span><div><strong style="font-size:22px">${pct(u.valore, 2)}</strong>
      <span class="tenue piccolo"> al ${data(u.data)}</span></div>
      <svg viewBox="0 0 300 70" preserveAspectRatio="none"><polyline points="${punti}" fill="none" stroke="${COLORI[1]}" stroke-width="2" vector-effect="non-scaling-stroke"/></svg>
      <span class="tenue piccolo">${u.fonte.startsWith("http") ? "Fonte: " + (u.fonte.includes("ecb") ? "BCE" : "Eurostat") : esc(u.fonte)}</span></div>`;
  }).join("");
}

async function aggiornaMercato() {
  const b = $("#b-aggiorna"); b.disabled = true;
  try { await api("/mercato/aggiorna", { method: "POST" }); await caricaMercato(); } finally { b.disabled = false; }
}

// ------------------------------------------------------------------------------------------------ avvio
$$(".ruoli button").forEach((b) => { b.onclick = () => accedi(b.dataset.email); });
$$("nav button").forEach((b) => { b.onclick = () => mostra(b.dataset.vista); });
$("#b-nuovo").onclick = () => apriQuestionario(null);
$("#f-questionario").addEventListener("submit", salvaQuestionario);
$("#b-verifica").onclick = verificaCatena;
$("#b-aggiorna").onclick = aggiornaMercato;
stato.token = memoria("token");
if (stato.token) avvia().catch(esci); else mostra("login");
