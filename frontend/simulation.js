/* ================================================================
   TierWise — simulation.js
   Six-step sequential flow:
   1 Upload → 2 Pricing Review → 3 Configure → 4 Simulation →
   5 KPI Dashboard → 6 Report & Recommendations
   ================================================================ */

const API = 'http://localhost:8000';

const ARCH_COLORS = {
  'Anxious Planner':    '#2D2420',
  'Social Follower':    '#4A3F38',
  'Spontaneous Mover':  '#6B5F56',
  'Authority Truster':  '#8A7F72',
  'Indifferent Drifter':'#B0A99E',
};

const TIER_COLORS = ['#6B5F56', '#2D2420', '#4A3F38', '#8A7F72'];

const SIGNAL_LABELS = {
  social_proof:  'Social Proof',
  loss_framing:  'Loss Framing',
  authority:     'Authority',
  scarcity:      'Scarcity',
  gain_framing:  'Gain Framing',
  simplicity:    'Simplicity',
};

// Behavioral ceiling = the theoretical max conversion rate for this archetype
// when pricing page framing is perfectly aligned with their psychology
const BEHAVIORAL_CEILINGS = {
  'Anxious Planner':    70,
  'Social Follower':    65,
  'Spontaneous Mover':  55,
  'Authority Truster':  60,
  'Indifferent Drifter': 20,
};

const ARCHETYPE_FRAMING_ADVICE = {
  'Anxious Planner':    'add scarcity or loss-framing language ("Don\'t lose access to X") near your upgrade button',
  'Social Follower':    'add social proof badges — a user count, "Most Popular" label, or customer testimonials',
  'Spontaneous Mover':  'simplify your pricing page to a single clear CTA and remove complex feature comparison tables',
  'Authority Truster':  'add expert endorsements, certifications, or a clear "Recommended" badge on your best-fit tier',
  'Indifferent Drifter':'create in-app usage-milestone prompts (e.g. "You\'ve hit 90% of your free limit this month")',
};

// Narration messages shown sequentially during simulation
const NARRATION_STEPS = [
  (n) => `Setting up ${n} virtual customers — each with a unique income bracket, price sensitivity, and behavioral profile…`,
  ()  => `Your customers are scanning your pricing page for the first time. Each one is bringing their own cognitive style and purchasing triggers…`,
  ()  => `Anxious Planners are checking whether the price feels safe. They're looking for urgency signals and fear of missing out…`,
  ()  => `Social Followers are looking for what other people are doing. Is there a "Most Popular" badge? How many users are on each plan?`,
  ()  => `Spontaneous Movers are making a snap judgment. Too many options and they'll bounce without converting…`,
  ()  => `Authority Trusters are scanning for expert signals and official recommendations. They need to feel upgrading is the "right" choice…`,
  ()  => `Running financial feasibility checks — comparing your prices against each customer's monthly spending threshold…`,
  ()  => `Calculating conversion decisions across all customers, factoring in cognitive load, price sensitivity, and behavioral signals…`,
  ()  => `Aggregating results and calculating your revenue projections…`,
];

// State
let _parsedPricing    = null;
let _simulationResult = null;
let _selectedFile     = null;
let _agentCount       = 500;
let _currentStep      = 1;

// ── Step navigation ───────────────────────────────────────────────────────

function goToStep(stepNum) {
  // Hide all step sections
  for (let i = 1; i <= 6; i++) {
    const el = document.getElementById(`section-step${i}`);
    if (el) {
      el.classList.add('step-hidden');
      el.classList.remove('step-visible');
    }
  }

  // Show target step
  const target = document.getElementById(`section-step${stepNum}`);
  if (target) {
    target.classList.remove('step-hidden');
    target.classList.add('step-visible');
    setTimeout(() => target.scrollIntoView({ behavior: 'smooth', block: 'start' }), 60);
  }

  // Update step nav indicators
  document.querySelectorAll('.step-item').forEach(item => {
    const n = parseInt(item.dataset.step);
    item.classList.remove('active', 'completed');
    if (n === stepNum) item.classList.add('active');
    if (n < stepNum)   item.classList.add('completed');
  });

  // Update connectors
  document.querySelectorAll('.step-connector').forEach((conn, i) => {
    conn.classList.toggle('filled', i < stepNum - 1);
  });

  _currentStep = stepNum;
}

// ── File upload handlers ──────────────────────────────────────────────────

function handleDragOver(e) {
  e.preventDefault();
  document.getElementById('drop-zone').classList.add('drag-over');
}

function handleDragLeave() {
  document.getElementById('drop-zone').classList.remove('drag-over');
}

function handleDrop(e) {
  e.preventDefault();
  document.getElementById('drop-zone').classList.remove('drag-over');
  const file = e.dataTransfer.files[0];
  if (file) setFile(file);
}

function handleFileSelect(e) {
  const file = e.target.files[0];
  if (file) setFile(file);
}

function setFile(file) {
  _selectedFile = file;
  document.getElementById('file-name').textContent = `📄 ${file.name} (${(file.size / 1024).toFixed(1)} KB)`;
  document.getElementById('paste-input').value = '';
}

// ── Agent count selection ─────────────────────────────────────────────────

function selectAgentCount(count, labelEl) {
  _agentCount = count;
  document.querySelectorAll('.agent-option').forEach(el => el.classList.remove('selected'));
  if (labelEl) labelEl.classList.add('selected');
}

// ── Step 1 → 2: Parse pricing ─────────────────────────────────────────────

async function parsePricing() {
  const pasteText = document.getElementById('paste-input').value.trim();
  const btn = document.getElementById('btn-parse');

  if (!_selectedFile && !pasteText) {
    alert('Please upload a file or paste pricing text first.');
    return;
  }

  btn.disabled = true;
  btn.textContent = 'Parsing…';
  setStatus('Parsing pricing structure…', 'active');

  // Show step 2 with loading state
  goToStep(2);
  const loadingRow = document.getElementById('parse-loading-row');
  const parsedResult = document.getElementById('parsed-result');
  loadingRow.style.display = 'flex';
  parsedResult.style.display = 'none';

  try {
    let result;

    if (_selectedFile) {
      document.getElementById('parse-status-text').textContent =
        `Claude is analyzing your document (${_selectedFile.name})…`;
      const formData = new FormData();
      formData.append('file', _selectedFile);
      const res = await fetch(`${API}/parse`, { method: 'POST', body: formData });
      if (!res.ok) throw new Error(await res.text());
      result = await res.json();

    } else {
      document.getElementById('parse-status-text').textContent =
        'Claude is parsing your pricing text and extracting framing signals…';
      const res = await fetch(`${API}/parse-text`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: pasteText }),
      });
      if (!res.ok) throw new Error(await res.text());
      result = await res.json();
    }

    _parsedPricing = result;
    loadingRow.style.display = 'none';
    renderParsedPricing(result);
    parsedResult.style.display = 'block';
    setStatus('Pricing parsed ✓', 'success');

  } catch (err) {
    console.error('[TierWise] Parse error:', err);
    loadingRow.style.display = 'none';
    setStatus('Parse error — check console', 'error');
    alert(`Parse failed: ${err.message}`);
    goToStep(1);
  } finally {
    btn.disabled = false;
    btn.textContent = 'Parse Pricing Document →';
  }
}

// ── Step 2 → 3 ────────────────────────────────────────────────────────────

function advanceToStep3() {
  goToStep(3);
}

// ── Render parsed pricing tier cards ─────────────────────────────────────

function renderParsedPricing(data) {
  document.getElementById('parsed-product-name').textContent = data.product_name || 'Your Product';

  const method = data.parse_method === 'claude' ? '✦ Claude AI' : '⚙ Regex Fallback';
  document.getElementById('parse-method-badge').textContent = method;

  const tiers = data.tiers || [];
  const meta = [
    `${tiers.length} tiers`,
    data.has_free_tier ? 'Free tier included' : 'Paid only',
    data.has_annual_option ? 'Monthly + Annual' : 'Monthly billing',
    `Complexity: ${Math.round((data.overall_complexity || 0.4) * 100)}%`,
  ].join(' · ');
  document.getElementById('parsed-meta').textContent = meta;

  const container = document.getElementById('tier-cards-container');
  container.innerHTML = tiers.map(tier => renderTierCard(tier)).join('');
}

function renderTierCard(tier) {
  const price = tier.price_monthly === 0 ? 'Free' : `$${tier.price_monthly}`;
  const priceSub = tier.price_monthly === 0 ? '' : '<span>/month</span>';
  const annualNote = tier.price_annual
    ? `<div class="tier-annual">$${tier.price_annual}/mo billed annually</div>`
    : '';

  const badge = tier.badge
    ? `<div class="tier-badge-chip">${esc(tier.badge)}</div>`
    : '';

  const features = (tier.features || []).slice(0, 5).map(f =>
    `<li>${esc(f)}</li>`
  ).join('');
  const moreFeats = tier.feature_count > 5
    ? `<li class="more">+${tier.feature_count - 5} more features</li>`
    : '';

  const signals = (tier.framing_signals || []).map(s =>
    `<span class="signal-chip ${s}" title="${esc(SIGNAL_LABELS[s] || s)}">${esc(SIGNAL_LABELS[s] || s)}</span>`
  ).join('');

  const complexity = tier.complexity_score || 0.3;
  const complexityLabel = complexity < 0.35 ? 'Simple' : complexity < 0.6 ? 'Moderate' : 'Complex';

  const propHtml = tier.value_proposition
    ? `<div class="tier-prop">"${esc(tier.value_proposition)}"</div>`
    : '';

  const targetHtml = tier.target_user
    ? `<div class="tier-target">For: ${esc(tier.target_user)}</div>`
    : '';

  return `
    <div class="tier-card ${tier.highlighted ? 'highlighted' : ''}">
      ${badge}
      <div class="tier-name">${esc(tier.name)}</div>
      <div class="tier-price">${price}${priceSub}</div>
      ${annualNote}
      ${propHtml}
      ${targetHtml}
      ${features || moreFeats ? `<ul class="tier-features">${features}${moreFeats}</ul>` : ''}
      ${signals ? `<div class="signals-row">${signals}</div>` : ''}
      <div class="complexity-bar-wrap">
        <span>${complexityLabel}</span>
        <div class="complexity-bar">
          <div class="complexity-fill" style="width:${Math.round(complexity * 100)}%"></div>
        </div>
        <span>${Math.round(complexity * 100)}%</span>
      </div>
    </div>
  `;
}

// ── Step 3 → 4: Run simulation ────────────────────────────────────────────

async function runSimulation() {
  if (!_parsedPricing) return;

  const btn = document.getElementById('btn-run-sim');
  btn.disabled = true;
  btn.textContent = 'Starting…';
  setStatus('Running simulation…', 'active');

  goToStep(4);
  startSimulationAnimation(_agentCount);

  try {
    const res = await fetch(`${API}/simulate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pricing_data: _parsedPricing, agent_count: _agentCount }),
    });

    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    _simulationResult = data;

    stopSimulationAnimation();
    renderDashboard(data.summary, data.summary.pricing_structure || []);
    goToStep(5);
    setStatus('Simulation complete ✓', 'success');

  } catch (err) {
    console.error('[TierWise] Simulation error:', err);
    stopSimulationAnimation();
    setStatus('Simulation error — check console', 'error');
    alert(`Simulation failed: ${err.message}`);
    goToStep(3);
  } finally {
    btn.disabled = false;
    btn.textContent = 'Run Simulation →';
  }
}

// ── Simulation animation (Step 4) ─────────────────────────────────────────

let _narrationTimer = null;
let _progressTimer  = null;
let _narrationIndex = 0;
let _simProgress    = 0;

function startSimulationAnimation(agentCount) {
  // Build dot grid
  const grid = document.getElementById('sim-dot-grid');
  const colors = Object.values(ARCH_COLORS);
  const dotCount = 180;
  grid.innerHTML = Array.from({ length: dotCount }, (_, i) => {
    const color = colors[i % colors.length];
    const delay = (Math.random() * 2).toFixed(2);
    const dur   = (1 + Math.random() * 1.5).toFixed(2);
    return `<div class="sim-dot" style="background:${color};animation-delay:${delay}s;animation-duration:${dur}s"></div>`;
  }).join('');

  // Reset progress
  _simProgress    = 0;
  _narrationIndex = 0;
  document.getElementById('sim-progress-fill').style.width = '0%';
  document.getElementById('sim-count-label').textContent   = '0 decisions made';
  document.getElementById('sim-narration').textContent     = NARRATION_STEPS[0](agentCount);

  // Progress bar ticks
  _progressTimer = setInterval(() => {
    _simProgress = Math.min(_simProgress + (Math.random() * 4 + 1), 92);
    document.getElementById('sim-progress-fill').style.width = `${_simProgress}%`;
    const done = Math.round((_simProgress / 100) * agentCount);
    document.getElementById('sim-count-label').textContent = `${done.toLocaleString()} decisions made`;
  }, 400);

  // Narration cycling
  _narrationIndex = 1;
  _narrationTimer = setInterval(() => {
    if (_narrationIndex < NARRATION_STEPS.length) {
      document.getElementById('sim-narration').textContent =
        NARRATION_STEPS[_narrationIndex](agentCount);
      _narrationIndex++;
    }
  }, 1800);
}

function stopSimulationAnimation() {
  clearInterval(_narrationTimer);
  clearInterval(_progressTimer);

  document.getElementById('sim-progress-fill').style.width = '100%';
  document.getElementById('sim-count-label').textContent =
    _simulationResult
      ? `${_simulationResult.summary.total_agents.toLocaleString()} decisions made`
      : 'Complete';
  document.getElementById('sim-narration').textContent =
    'Simulation complete. Here\'s what your pricing does to real customers.';
}

// ── Step 5: KPI Dashboard ─────────────────────────────────────────────────

function renderDashboard(summary, tiers) {
  const mrr      = summary.projected_mrr || 0;
  const convRate = summary.overall_conversion_rate || 0;
  const n        = summary.total_agents || 1;
  const byArch   = summary.by_archetype || {};

  // ── KPI 1: Projected Monthly Revenue
  document.getElementById('kpi-mrr').textContent     = `$${Math.round(mrr).toLocaleString()}`;
  document.getElementById('kpi-mrr-sub').textContent = `from ${n.toLocaleString()} simulated users`;

  // ── KPI 2: Paid Conversion Rate with benchmark
  document.getElementById('kpi-conv-rate').textContent = `${convRate.toFixed(1)}%`;
  const benchmarkDiff = (convRate - 5).toFixed(1);
  const benchmarkEl   = document.getElementById('kpi-conv-benchmark');
  if (convRate >= 5) {
    benchmarkEl.innerHTML = `<span class="benchmark-label">Industry avg:</span> <span class="benchmark-good">+${benchmarkDiff}pp above ~5% freemium avg</span>`;
  } else {
    benchmarkEl.innerHTML = `<span class="benchmark-label">Industry avg:</span> <span class="benchmark-bad">${benchmarkDiff}pp below ~5% freemium avg</span>`;
  }

  // ── KPI 3: Revenue Left on the Table
  const freeCount   = summary.tier_counts?.[summary.free_tier_name] || 0;
  const paidTiers   = tiers.filter(t => !t.is_free);
  const lowestPaid  = paidTiers.length > 0 ? Math.min(...paidTiers.map(t => t.price_monthly || 0)) : 0;
  const avgPaid     = paidTiers.length > 0
    ? paidTiers.reduce((s, t) => s + (t.price_monthly || 0), 0) / paidTiers.length
    : 0;

  // Weighted behavioral ceiling across all archetypes
  const weightedCeiling = Object.entries(byArch).reduce((sum, [arch, d]) => {
    return sum + (d.count / n) * (BEHAVIORAL_CEILINGS[arch] || 50);
  }, 0);
  const leftOnTable = Math.max(0, Math.round(freeCount * lowestPaid * (weightedCeiling - convRate) / 100));

  document.getElementById('kpi-left-on-table').textContent     = `$${leftOnTable.toLocaleString()}`;
  document.getElementById('kpi-left-on-table-sub').textContent =
    `${freeCount.toLocaleString()} free users not converting to their behavioral ceiling`;

  // ── KPI 4: Biggest Win Available
  const highPotential = Object.entries(byArch)
    .filter(([arch]) => (BEHAVIORAL_CEILINGS[arch] || 0) > 40)
    .map(([arch, d]) => ({
      arch,
      data: d,
      ceiling: BEHAVIORAL_CEILINGS[arch] || 50,
      gap: (BEHAVIORAL_CEILINGS[arch] || 50) - d.conversion_rate,
    }))
    .sort((a, b) => b.gap - a.gap);

  const biggestWinArch = highPotential[0] || null;
  const biggestWin     = biggestWinArch
    ? Math.round(biggestWinArch.data.count * lowestPaid * biggestWinArch.gap / 100)
    : 0;

  document.getElementById('kpi-biggest-win').textContent     = `$${biggestWin.toLocaleString()}`;
  document.getElementById('kpi-biggest-win-sub').textContent = biggestWinArch
    ? `if ${biggestWinArch.arch}s converted at their behavioral ceiling (${biggestWinArch.ceiling}%)`
    : 'optimize top opportunity archetype';

  // ── Archetype ranked list (replaces matrix table)
  renderArchRankedList(byArch, n, lowestPaid);

  // ── Tier funnel
  const funnelEl = document.getElementById('tier-funnel');
  const tierRows = tiers.map((t, i) => {
    const color   = TIER_COLORS[i] || '#8A7F72';
    const mrr_c   = t.mrr_contribution || 0;
    const tierPct = t.pct || 0;
    return `
      <div class="tier-funnel-row">
        <div class="tf-name">${esc(t.name)}</div>
        <div class="tf-price">${t.is_free ? 'Free' : `$${t.price_monthly}/mo`}</div>
        <div class="tf-bar-wrap">
          <div class="tf-bar" style="width:${tierPct}%; background:${color}"></div>
        </div>
        <div class="tf-pct" style="color:${color}">${tierPct}%</div>
        <div class="tf-count">${(t.count || 0).toLocaleString()} users</div>
        <div class="tf-mrr">${mrr_c > 0 ? '$' + Math.round(mrr_c).toLocaleString() : '—'}</div>
      </div>
    `;
  }).join('');

  const totalUsers = tiers.reduce((s, t) => s + (t.count || 0), 0);
  const totalMrrF  = tiers.reduce((s, t) => s + (t.mrr_contribution || 0), 0);
  const totalsRow  = `
    <div class="tier-funnel-totals">
      <div class="tf-name">Total</div>
      <div class="tf-price"></div>
      <div class="tf-bar-wrap"></div>
      <div class="tf-pct">100%</div>
      <div class="tf-count">${totalUsers.toLocaleString()} users</div>
      <div class="tf-mrr">${totalMrrF > 0 ? '$' + Math.round(totalMrrF).toLocaleString() : '—'}</div>
    </div>
  `;
  funnelEl.innerHTML = tierRows + totalsRow;

  // ── Signal effectiveness
  const sigs      = summary.signal_effectiveness || {};
  const sigArr    = Object.entries(sigs);
  if (sigArr.length > 0) {
    document.getElementById('signal-eff-card').style.display = 'block';
    document.getElementById('signal-eff-rows').innerHTML = sigArr
      .sort((a, b) => Math.abs(b[1].lift) - Math.abs(a[1].lift))
      .map(([signal, eff]) => {
        const liftClass = eff.lift >= 0 ? 'positive' : 'negative';
        const liftStr   = eff.lift >= 0 ? `+${eff.lift}%` : `${eff.lift}%`;
        return `
          <div class="signal-eff-row">
            <span class="signal-chip ${signal} se-name">${esc(SIGNAL_LABELS[signal] || signal)}</span>
            <span class="se-lift ${liftClass}">${liftStr} lift</span>
            <span class="se-detail">${eff.receptive_conversion}% conversion (receptive) vs ${eff.non_receptive_conversion}% (not receptive)</span>
          </div>
        `;
      }).join('');
  }
}

function renderArchRankedList(byArch, totalAgents, lowestPaidPrice) {
  const archOrder = ['Anxious Planner', 'Social Follower', 'Spontaneous Mover', 'Authority Truster', 'Indifferent Drifter'];
  const ranked = archOrder
    .filter(arch => byArch[arch] && byArch[arch].count > 0)
    .map(arch => ({ arch, data: byArch[arch] }))
    .sort((a, b) => b.data.conversion_rate - a.data.conversion_rate);

  const listEl = document.getElementById('arch-ranked-list');
  listEl.innerHTML = ranked.map((item, rank) => {
    const { arch, data } = item;
    const color   = ARCH_COLORS[arch] || '#64748B';
    const ceiling = BEHAVIORAL_CEILINGS[arch] || 50;
    const isUnder = data.conversion_rate < ceiling * 0.5;
    const pctOfTotal = Math.round((data.count / totalAgents) * 100);

    const warningHtml = isUnder
      ? `<div class="arch-warning">⚠ Converting at ${data.conversion_rate}% — ${ceiling - data.conversion_rate}pp below their ${ceiling}% ceiling. Add missing signals to close the gap.</div>`
      : '';

    const convClass = data.conversion_rate >= 40 ? 'conv-high'
                    : data.conversion_rate >= 20 ? 'conv-medium'
                    : 'conv-low';

    return `
      <div class="arch-rank-item ${isUnder ? 'underperforming' : ''}">
        <div class="arch-rank-header">
          <div class="arch-rank-left">
            <div class="arch-rank-num">${rank + 1}</div>
            <div class="arch-dot" style="background:${color}"></div>
            <div class="arch-rank-name">${esc(arch)}</div>
            <div class="arch-rank-pop">${pctOfTotal}% of users</div>
          </div>
          <div class="arch-rank-right">
            <span class="conv-rate ${convClass}">${data.conversion_rate}% paid</span>
            ${isUnder ? '<span class="arch-warn-badge">⚠ Underperforming</span>' : ''}
          </div>
        </div>
        <div class="arch-rank-bar-wrap">
          <div class="arch-rank-bar" style="width:${data.conversion_rate}%; background:${color}"></div>
          <div class="arch-rank-ceiling" style="left:${ceiling}%"></div>
        </div>
        <div class="arch-rank-legend">
          <span style="color:${color}">${data.conversion_rate}% actual</span>
          <span style="color:var(--faint)">·</span>
          <span style="color:var(--muted)">${ceiling}% behavioral ceiling</span>
        </div>
        ${warningHtml}
      </div>
    `;
  }).join('');
}

// ── Step 6: Generate AI report ────────────────────────────────────────────

async function runAnalysis() {
  if (!_simulationResult) return;

  const btn = document.getElementById('btn-analyze');
  btn.disabled = true;
  btn.textContent = 'Generating…';
  setStatus('Claude is analyzing…', 'warn');

  goToStep(6);
  document.getElementById('report-content').innerHTML = `
    <div class="report-loading fade-in">
      <div class="spinner"></div>
      <span>Claude is processing ${_simulationResult.summary.total_agents.toLocaleString()} agent decisions and generating your behavioral insight report…</span>
    </div>
  `;

  try {
    const res = await fetch(`${API}/analyze`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        summary: _simulationResult.summary,
        agents: [],
      }),
    });

    if (!res.ok) throw new Error(await res.text());
    const report = await res.json();

    renderReport(report, _simulationResult.summary);
    setStatus('Report ready ✓', 'success');

  } catch (err) {
    console.error('[TierWise] Analyze error:', err);
    setStatus('Analysis error — check console', 'error');
    document.getElementById('report-content').innerHTML =
      `<div style="color:var(--red);padding:16px;font-size:0.85rem;">⚠ Analysis error: ${esc(err.message)}</div>`;
  } finally {
    btn.disabled = false;
    btn.textContent = 'Generate Full Report →';
  }
}

// ── Render report (Step 6) — Tab layout ──────────────────────────────────

function renderReport(report, summary) {
  const { insight_report: ir, framing_guide: fg } = report;
  const tiers = summary.pricing_structure || [];

  const overviewHtml  = buildOverviewHtml(ir, summary, tiers);
  const archetypeHtml = buildArchetypesHtml(ir, summary);
  const framingHtml   = buildFramingHtml(fg, tiers);
  const actionsHtml   = buildActionsHtml(report.recommendations || null, summary, tiers);

  document.getElementById('report-content').innerHTML = `
    <div class="report-tabs-wrapper fade-in">
      <nav class="report-tab-nav">
        <button class="report-tab-btn active" data-tab="overview">Overview</button>
        <button class="report-tab-btn" data-tab="archetypes">Archetypes</button>
        <button class="report-tab-btn" data-tab="framing">Framing</button>
        <button class="report-tab-btn" data-tab="actions">Actions</button>
      </nav>
      <div class="report-tab-panels">
        <div class="report-tab-panel active" id="tab-overview">${overviewHtml}</div>
        <div class="report-tab-panel" id="tab-archetypes">${archetypeHtml}</div>
        <div class="report-tab-panel" id="tab-framing">${framingHtml}</div>
        <div class="report-tab-panel" id="tab-actions">${actionsHtml}</div>
      </div>
    </div>
  `;

  document.querySelectorAll('.report-tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.report-tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.report-tab-panel').forEach(p => p.classList.remove('active'));
      btn.classList.add('active');
      document.getElementById(`tab-${btn.dataset.tab}`).classList.add('active');
    });
  });

  document.getElementById('regen-trigger').style.display = 'block';
  document.getElementById('regen-output').style.display  = 'none';
}

// ── Tab 1: Overview ───────────────────────────────────────────────────────

function buildOverviewHtml(ir, summary, tiers) {
  if (!ir) return '<p style="color:var(--muted);font-size:0.85rem;">No data available.</p>';

  const pillsHtml = tiers.map((t, i) => `
    <div class="ov-rate-pill">
      <div class="ov-rate-val" style="color:${TIER_COLORS[i] || '#8A7F72'}">${summary.tier_pcts?.[t.name] ?? '—'}%</div>
      <div class="ov-rate-label">${esc(t.name)}</div>
    </div>
  `).join('');

  const kfHtml = ir.key_behavioral_finding
    ? `<div class="key-finding">💡 ${esc(ir.key_behavioral_finding)}</div>`
    : '';

  function bulletsOrPara(val) {
    if (!val) return '';
    if (Array.isArray(val))
      return `<ul class="insight-bullets">${val.map(b => `<li>${esc(b)}</li>`).join('')}</ul>`;
    return `<p class="insight-para">${esc(val)}</p>`;
  }

  const pm = ir.projected_mrr;
  let mrrHtml = '';
  if (pm) {
    if (typeof pm === 'object' && pm !== null) {
      mrrHtml = `<div class="ov-mrr-block">
        ${pm.mrr_commentary ? `<span class="ov-mrr-note">${esc(pm.mrr_commentary)}</span>` : ''}
        ${pm.top_lever ? `<span class="ov-mrr-lever">Top lever: ${esc(pm.top_lever)}</span>` : ''}
      </div>`;
    } else {
      mrrHtml = `<div class="ov-mrr-block"><span class="ov-mrr-note">${esc(pm)}</span></div>`;
    }
  }

  return `
    <div class="ov-pills-row">${pillsHtml}</div>
    ${kfHtml}
    <div class="ov-blocks">
      ${ir.why_converted ? `<div class="ov-block">
        <div class="ov-block-label">Why They Upgraded</div>
        ${bulletsOrPara(ir.why_converted)}
      </div>` : ''}
      ${ir.why_lost ? `<div class="ov-block">
        <div class="ov-block-label">Why They Stayed Free</div>
        ${bulletsOrPara(ir.why_lost)}
      </div>` : ''}
    </div>
    ${mrrHtml}
  `;
}

// ── Tab 2: Archetypes ─────────────────────────────────────────────────────

function buildArchetypesHtml(ir, summary) {
  const archByArch = ir?.conversion_by_archetype || {};
  const simByArch  = summary.by_archetype || {};
  const archOrder  = ['Anxious Planner', 'Social Follower', 'Spontaneous Mover', 'Authority Truster', 'Indifferent Drifter'];

  const cards = archOrder
    .filter(arch => archByArch[arch] || (simByArch[arch]?.count > 0))
    .map(arch => {
      const data    = archByArch[arch];
      const simData = simByArch[arch] || {};
      const color   = ARCH_COLORS[arch] || '#64748B';

      let rate, ceiling, gapPp, missingSig, missingTier, summaryText;

      if (data && typeof data === 'object' && !Array.isArray(data)) {
        rate        = typeof data.rate === 'number' ? data.rate : (simData.conversion_rate || 0);
        ceiling     = data.ceiling || BEHAVIORAL_CEILINGS[arch] || 50;
        gapPp       = data.gap_pp ?? (ceiling - rate);
        missingSig  = data.missing_signal || null;
        missingTier = data.missing_from_tier || null;
        summaryText = data.summary || '';
      } else {
        rate        = simData.conversion_rate || 0;
        ceiling     = BEHAVIORAL_CEILINGS[arch] || 50;
        gapPp       = ceiling - rate;
        missingSig  = null;
        missingTier = null;
        summaryText = typeof data === 'string' ? data : '';
      }

      const pctOfTotal = simData.pct || 0;
      const status      = gapPp > 40 ? 'critical' : gapPp > 15 ? 'low' : 'good';
      const statusLabel = { critical: 'Critical Gap', low: 'Underperforming', good: 'On Track' }[status];
      const badgeClass  = { critical: 'arch-badge-critical', low: 'arch-badge-warn', good: 'arch-badge-ok' }[status];

      const signalHtml = missingSig
        ? `<div class="arch-card-signal">⚠ ${missingTier ? `${esc(missingTier)} — ` : ''}missing <strong>${esc(missingSig)}</strong> signal</div>`
        : '';

      return `
        <div class="arch-card">
          <div class="arch-card-header">
            <div class="arch-card-name-row">
              <div class="arch-dot" style="background:${color}"></div>
              <span class="arch-card-name">${esc(arch)}</span>
              <span class="arch-card-pop">${pctOfTotal}% of users</span>
            </div>
            <span class="arch-badge ${badgeClass}">${statusLabel}</span>
          </div>
          <div class="arch-card-bar-wrap">
            <div class="arch-card-bar-fill" style="width:${Math.min(rate, 100)}%; background:${color}"></div>
            <div class="arch-card-ceiling-line" style="left:${Math.min(ceiling, 100)}%"></div>
          </div>
          <div class="arch-card-stats">
            <span class="arch-card-stat-main" style="color:${color}">${rate}%</span>
            <span class="arch-card-stat-sep">actual ·</span>
            <span class="arch-card-stat-ceiling">${ceiling}% ceiling</span>
            ${gapPp > 5 ? `<span class="arch-card-gap">−${Math.round(gapPp)}pp gap</span>` : ''}
          </div>
          ${signalHtml}
          ${summaryText ? `<div class="arch-card-summary">${esc(summaryText)}</div>` : ''}
        </div>
      `;
    }).join('');

  return `<div class="arch-cards-grid">${cards || '<p style="color:var(--muted)">No archetype data.</p>'}</div>`;
}

// ── Tab 3: Framing Guide ──────────────────────────────────────────────────

function buildFramingHtml(fg, tiers) {
  if (!fg) return '<p style="color:var(--muted);font-size:0.85rem;">No framing data.</p>';

  const FRAMING_PALETTE = {
    loss:         { bg: 'rgba(155,68,68,0.08)',   border: 'rgba(155,68,68,0.25)',   color: '#9B4444', label: 'Loss' },
    gain:         { bg: 'rgba(74,124,89,0.08)',   border: 'rgba(74,124,89,0.25)',   color: '#4A7C59', label: 'Gain' },
    social_proof: { bg: 'rgba(61,90,115,0.08)',   border: 'rgba(61,90,115,0.25)',   color: '#3D5A73', label: 'Social Proof' },
    authority:    { bg: 'rgba(92,82,72,0.08)',    border: 'rgba(92,82,72,0.25)',    color: '#5C5248', label: 'Authority' },
    simplicity:   { bg: 'rgba(138,127,114,0.08)', border: 'rgba(138,127,114,0.25)', color: '#6B6458', label: 'Simplicity' },
  };

  const cards = Object.entries(fg).map(([tierName, guide], i) => {
    const tierColor = TIER_COLORS[i] || '#8A7F72';
    const ftKey     = (guide.framing_type || '').toLowerCase().replace(/[\s+]/g, '_');
    const fp        = FRAMING_PALETTE[ftKey] || FRAMING_PALETTE.simplicity;

    return `
      <div class="framing-card-v2">
        <div class="framing-card-hdr" style="border-left:3px solid ${tierColor}">
          <span class="framing-card-tier" style="color:${tierColor}">${esc(tierName)}</span>
          <span class="framing-type-badge" style="background:${fp.bg};border:1px solid ${fp.border};color:${fp.color}">${esc(fp.label || guide.framing_type)}</span>
        </div>
        ${guide.copy_recommendation ? `<div class="framing-copy-block">
          <div class="framing-section-label">Recommended Copy</div>
          <div class="framing-copy-quote">"${esc(guide.copy_recommendation)}"</div>
        </div>` : ''}
        ${guide.information_architecture ? `<div class="framing-detail-row">
          <div class="framing-section-label">Information Architecture</div>
          <div class="framing-detail-val">${esc(guide.information_architecture)}</div>
        </div>` : ''}
        ${guide.messaging_for_unconverted ? `<div class="framing-detail-row">
          <div class="framing-section-label">For Unconverted Segment</div>
          <div class="framing-detail-val">${esc(guide.messaging_for_unconverted)}</div>
        </div>` : ''}
      </div>
    `;
  }).join('');

  return `<div class="framing-cards-grid">${cards}</div>`;
}

// ── Tab 4: Actions (Recommendations) ─────────────────────────────────────

function buildActionsHtml(claudeRecs, summary, tiers) {
  const recs = claudeRecs && claudeRecs.length >= 3
    ? claudeRecs
    : calculateRecommendations(summary, tiers);

  _lastRecommendations = recs;

  const mrr       = summary.projected_mrr || 0;
  const total     = recs.reduce((s, r) => s + (r.projected_monthly_impact || r.projected_impact || 0), 0);
  const newMrr    = Math.round(mrr + total);
  const improvPct = mrr > 0 ? Math.round((total / mrr) * 100) : 0;

  const recCards = recs.map((rec, i) => {
    const impact  = rec.projected_monthly_impact || rec.projected_impact || 0;
    const archStr = rec.target_archetype || '';
    return `
      <div class="rec-card">
        <div class="rec-number">${i + 1}</div>
        <div class="rec-body">
          <div class="rec-title">${esc(rec.title || rec.what_to_change || `Action ${i + 1}`)}</div>
          <div class="rec-description">${esc(rec.description || rec.reasoning || '')}</div>
          <div class="rec-meta">
            <span class="rec-arch-tag">Targets: ${esc(archStr)}</span>
            <span class="rec-impact">+$${Math.round(impact).toLocaleString()}/mo</span>
          </div>
        </div>
      </div>
    `;
  }).join('');

  return `
    <p class="rec-intro" style="margin-bottom:16px;">Specific changes to grow monthly revenue, based on simulation behavior.</p>
    <div class="rec-cards">${recCards}</div>
    <div class="rec-summary">
      <div class="rec-summary-block">
        <div class="rec-summary-label">Current MRR</div>
        <div class="rec-summary-val">${'$' + Math.round(mrr).toLocaleString()}</div>
      </div>
      <div class="rec-summary-arrow">→</div>
      <div class="rec-summary-block highlight">
        <div class="rec-summary-label">With All Actions</div>
        <div class="rec-summary-val accent">${'$' + newMrr.toLocaleString()}</div>
      </div>
      <div class="rec-summary-badge">+${improvPct}% improvement</div>
    </div>
  `;
}

function calculateRecommendations(summary, tiers) {
  const byArch  = summary.by_archetype || {};
  const n       = summary.total_agents || 1;
  const mrr     = summary.projected_mrr || 0;

  const paidTiers  = tiers.filter(t => !t.is_free);
  const lowestPaid = paidTiers.length > 0 ? Math.min(...paidTiers.map(t => t.price_monthly || 0)) : 10;

  // Rank archetypes by gap to behavioral ceiling (highest = most opportunity)
  const archGaps = Object.entries(byArch)
    .filter(([arch]) => byArch[arch].count > 0 && (BEHAVIORAL_CEILINGS[arch] || 0) > 25)
    .map(([arch, d]) => ({
      arch,
      data: d,
      ceiling: BEHAVIORAL_CEILINGS[arch] || 50,
      gap: (BEHAVIORAL_CEILINGS[arch] || 50) - d.conversion_rate,
    }))
    .sort((a, b) => b.gap - a.gap);

  const recs = [];

  // Rec 1: Fix the biggest underperformer (largest gap to ceiling)
  if (archGaps.length > 0) {
    const top = archGaps[0];
    // Conservative: capture 30% of the gap
    const liftPp = Math.min(top.gap * 0.30, 15);
    const impact = Math.round(top.data.count * lowestPaid * liftPp / 100);
    recs.push({
      title: `Reframe your pricing page for ${top.arch}s`,
      description: `${top.arch}s make up ${Math.round((top.data.count / n) * 100)}% of your users but are only converting at ${top.data.conversion_rate}% — well below their ${top.ceiling}% behavioral ceiling. To close this gap, ${ARCHETYPE_FRAMING_ADVICE[top.arch] || 'optimize messaging for this segment'}.`,
      target_archetype: top.arch,
      projected_impact: impact,
    });
  }

  // Rec 2: Second biggest gap (different archetype)
  const secondGap = archGaps.find(a => !recs.find(r => r.target_archetype === a.arch));
  if (secondGap) {
    const ARCH_SPECIFIC_ACTIONS = {
      'Anxious Planner':    'Create urgency with limited-time pricing or a "seats remaining" counter near your upgrade button. Anxious Planners respond strongly to loss-framing — show what they\'ll lose by staying free.',
      'Social Follower':    'Show how many users are on each plan. A simple "X teams joined this month" ticker on your pricing page can meaningfully lift conversions for Social Followers, who upgrade based on what others are doing.',
      'Spontaneous Mover':  'Remove feature comparison tables for mobile visitors. Spontaneous Movers make snap decisions — show one plan, one price, one bold benefit. Complexity is conversion-killer for this group.',
      'Authority Truster':  'Highlight industry certifications, press coverage, or a "Trusted by" logo wall near your Team plan CTA. Authority Trusters need expert validation before committing.',
      'Indifferent Drifter':'Trigger upgrade prompts inside your app when users hit a usage ceiling (e.g. "You have 3 exports left this month"). Drifters don\'t respond to pricing pages — they need in-context nudges.',
    };
    const liftPp = Math.min(secondGap.gap * 0.25, 12);
    const impact = Math.round(secondGap.data.count * lowestPaid * liftPp / 100);
    recs.push({
      title: `Activate ${secondGap.arch}s with targeted messaging`,
      description: ARCH_SPECIFIC_ACTIONS[secondGap.arch] || `Improve conversion for ${secondGap.arch}s by addressing their core behavioral drivers. This group is converting at ${secondGap.data.conversion_rate}% versus a ${secondGap.ceiling}% ceiling.`,
      target_archetype: secondGap.arch,
      projected_impact: impact,
    });
  }

  // Rec 3: Structural recommendation based on free tier size
  const freeCount = summary.tier_counts?.[summary.free_tier_name] || 0;
  const freePct   = (freeCount / n) * 100;

  if (freePct > 60) {
    const impact = Math.round(freeCount * lowestPaid * 8 / 100);
    recs.push({
      title: 'Reduce the value gap between your free and paid tiers',
      description: `${Math.round(freePct)}% of your simulated users stayed on the free tier. This signals that your free plan may be too generous, or your paid plan's value proposition isn't compelling enough at first glance. Consider identifying the one feature free users most want — then moving it exclusively to your lowest paid tier. This creates a clear, felt incentive to upgrade.`,
      target_archetype: 'All customer types',
      projected_impact: impact,
    });
  } else if (!tiers.some(t => t.price_annual)) {
    const impact = Math.round(mrr * 0.09);
    recs.push({
      title: 'Add an annual billing option with a prominent savings display',
      description: 'Your pricing currently leads with monthly billing. Adding an annual option with a clear savings percentage ("Save 20% — pay yearly") increases both conversion rate and revenue per user. Anxious Planners lock in to avoid future price changes. Authority Trusters view annual billing as the "serious" commitment level. This typically lifts effective MRR by 8–12% with minimal engineering work.',
      target_archetype: 'Anxious Planner, Authority Truster',
      projected_impact: impact,
    });
  } else {
    const impact = Math.round(mrr * 0.07);
    recs.push({
      title: 'Add an in-app upgrade prompt at the moment of peak value',
      description: 'The highest-converting upgrade moment is not your pricing page — it\'s when a user tries to do something they can\'t on the free tier. Triggering a contextual upgrade prompt at that exact moment (e.g. "Unlock this feature — upgrade for $X/mo") consistently outperforms email campaigns and pricing page visits.',
      target_archetype: 'Spontaneous Mover, Social Follower',
      projected_impact: impact,
    });
  }

  return recs;
}

// ── Regenerate pricing model ──────────────────────────────────────────────

// Cached recommendations from the last report render (set in buildRecommendationsHtml)
let _lastRecommendations = [];

async function regeneratePricing() {
  if (!_parsedPricing || !_simulationResult) return;

  const btn = document.getElementById('btn-regen');
  btn.disabled = true;
  btn.textContent = 'Generating…';
  setStatus('Claude is redesigning your pricing…', 'warn');

  const outputEl = document.getElementById('regen-output');
  outputEl.style.display = 'block';
  outputEl.innerHTML = `
    <div class="regen-loading fade-in">
      <div class="spinner"></div>
      <span>Claude is applying your recommendations and redesigning the pricing structure — this takes about 15 seconds…</span>
    </div>
  `;
  outputEl.scrollIntoView({ behavior: 'smooth', block: 'start' });

  try {
    const res = await fetch(`${API}/regenerate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        pricing_data: _parsedPricing,
        simulation_summary: _simulationResult.summary,
        recommendations: _lastRecommendations,
      }),
    });

    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();

    renderRegenModel(data.improved_pricing);
    btn.textContent = 'Regenerate Again →';
    btn.disabled = false;
    setStatus('Improved model ready ✓', 'success');

  } catch (err) {
    console.error('[TierWise] Regenerate error:', err);
    setStatus('Regeneration error — check console', 'error');
    outputEl.innerHTML = `<div style="color:var(--red);padding:16px;font-size:0.85rem;">⚠ Regeneration failed: ${esc(err.message)}</div>`;
    btn.disabled = false;
    btn.textContent = 'Try Again →';
  }
}

function renderRegenModel(improved) {
  if (!improved) return;

  const tiers    = improved.tiers || [];
  const origTiers = (_parsedPricing?.tiers || []);

  const tierCards = tiers.map((t, i) => {
    const color        = TIER_COLORS[i] || '#8A7F72';
    const isChanged    = t.price_changed_from != null;
    const priceLabel   = t.is_free ? 'Free' : `$${t.price_monthly}`;
    const priceSub     = t.is_free ? '' : '<span>/mo</span>';
    const wasLabel     = isChanged
      ? `<div class="regen-was">was $${t.price_changed_from}/mo</div>`
      : '';

    const add = (t.features_to_add || []).map(f =>
      `<li class="feat-add"><span class="feat-badge add">+</span>${esc(f)}</li>`
    ).join('');
    const remove = (t.features_to_remove || []).map(f =>
      `<li class="feat-remove"><span class="feat-badge remove">−</span>${esc(f)}</li>`
    ).join('');
    const keep = (t.features_to_keep || []).slice(0, 3).map(f =>
      `<li class="feat-keep">${esc(f)}</li>`
    ).join('');
    const moreKeep = (t.features_to_keep || []).length > 3
      ? `<li class="feat-keep more">+${(t.features_to_keep.length - 3)} more</li>`
      : '';

    const framingBadge = t.framing_type
      ? `<span class="signal-chip ${t.framing_type.replace(/\s/g,'_')}">${esc(t.framing_type)}</span>`
      : '';

    const nc = t.name_change || {};
    const nameChangeBadge = nc.suggested_name
      ? `<div class="regen-name-change">
           <span class="regen-name-change-label">Rename to</span>
           <span class="regen-name-change-value">${esc(nc.suggested_name)}</span>
           ${nc.reason ? `<div class="regen-name-change-reason">${esc(nc.reason)}</div>` : ''}
         </div>`
      : '';

    const ps = t.price_strategy || {};
    const priceStrategyBlock = ps.action
      ? `<div class="regen-price-strategy regen-price-strategy--${esc(ps.action)}">
           <span class="regen-price-strategy-action">${esc(ps.action === 'keep' ? 'Keep price' : ps.action === 'increase' ? 'Raise price' : 'Lower price')}</span>
           ${ps.reasoning ? `<span class="regen-price-strategy-reason">${esc(ps.reasoning)}</span>` : ''}
         </div>`
      : '';

    return `
      <div class="regen-tier-card ${isChanged ? 'price-changed' : ''}" style="--tier-color:${color}">
        <div class="regen-tier-top">
          <div class="regen-tier-name" style="color:${color}">${esc(t.name)}</div>
          ${framingBadge}
        </div>
        ${nameChangeBadge}
        <div class="regen-price-row">
          <div class="regen-price">${priceLabel}${priceSub}</div>
          ${wasLabel}
        </div>
        ${priceStrategyBlock}
        ${t.framing_headline ? `<div class="regen-headline">"${esc(t.framing_headline)}"</div>` : ''}
        <ul class="regen-features">
          ${add}${remove}${keep}${moreKeep}
        </ul>
        <div class="regen-rationale">
          <div class="regen-what">${esc(t.what_changed || '')}</div>
          <div class="regen-why">${esc(t.why || '')}</div>
        </div>
      </div>
    `;
  }).join('');

  document.getElementById('regen-output').innerHTML = `
    <div class="regen-model fade-in">
      <div class="regen-model-header">
        <h3>Improved Pricing Model</h3>
        <div class="regen-model-sub">Changes are highlighted. Green = add, red = remove.</div>
      </div>

      <div class="regen-overview">
        ${improved.summary_of_changes
          ? `<div class="regen-summary-block"><div class="regen-summary-label">What changed</div><p>${esc(improved.summary_of_changes)}</p></div>`
          : ''}
        ${improved.projected_mrr_lift
          ? `<div class="regen-summary-block"><div class="regen-summary-label">Expected impact</div><p>${esc(improved.projected_mrr_lift)}</p></div>`
          : ''}
      </div>

      <div class="regen-tier-grid">${tierCards}</div>
    </div>
  `;
}

// ── Helpers ───────────────────────────────────────────────────────────────

function setStatus(text, type = 'neutral') {
  const badge = document.getElementById('status-badge');
  badge.textContent = text;
  badge.className   = `pill pill-${type}`;
}

function esc(s) {
  if (typeof s !== 'string') return s == null ? '' : String(s);
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// ── Init ──────────────────────────────────────────────────────────────────

// Show Step 1 on load
goToStep(1);
