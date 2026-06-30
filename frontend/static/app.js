const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

let orgs = [];

function showLoading(on) {
  $('#loading').classList.toggle('hidden', !on);
}

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const msg = data.detail || res.statusText;
    if (res.status === 404) {
      throw new Error(`${msg} — 서버를 재시작해 주세요`);
    }
    throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg));
  }
  return data;
}

function escapeHtml(text) {
  return String(text ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function statusBadge(status) {
  const map = { '있음': 'badge-ok', '약함': 'badge-weak', '없음': 'badge-miss' };
  const cls = map[status] || 'badge-miss';
  return `<span class="badge ${cls}">${escapeHtml(status)}</span>`;
}

function heatmapClass(status) {
  if (status === '있음') return 'heatmap-ok';
  if (status === '약함') return 'heatmap-weak';
  return 'heatmap-miss';
}

let heatmapPopover = null;

function ensureHeatmapPopover() {
  if (!heatmapPopover) {
    heatmapPopover = document.createElement('div');
    heatmapPopover.id = 'heatmap-popover';
    heatmapPopover.className = 'heatmap-popover hidden';
    heatmapPopover.setAttribute('role', 'tooltip');
    document.body.appendChild(heatmapPopover);
  }
  return heatmapPopover;
}

function heatmapCiteAttr(status, article, score) {
  if (!article || status === '없음') return '';
  const payload = encodeURIComponent(JSON.stringify({
    org: article.org,
    label: article.label,
    excerpt: article.excerpt || '',
    score: score ?? null,
    status,
    matched_terms: article.matched_terms || [],
    match_source: article.match_source || null,
  }));
  return ` data-cite="${payload}" tabindex="0"`;
}

function showHeatmapPopover(cell) {
  const raw = cell.dataset.cite;
  if (!raw) return;
  let cite;
  try {
    cite = JSON.parse(decodeURIComponent(raw));
  } catch {
    return;
  }

  const pop = ensureHeatmapPopover();
  const terms = (cite.matched_terms || []).length
    ? cite.matched_terms.join(', ')
    : '-';
  const sourceLabel = cite.match_source === 'anchor'
    ? '키워드 확인'
    : cite.match_source === 'semantic'
      ? 'AI 유사도'
      : '-';
  pop.innerHTML = `
    <div class="heatmap-popover-header">
      <span class="heatmap-popover-org">${escapeHtml(cite.org)}</span>
      ${statusBadge(cite.status)}
    </div>
    <div class="heatmap-popover-label">${escapeHtml(cite.label)}</div>
    <p class="heatmap-popover-excerpt">${escapeHtml(cite.excerpt)}</p>
    <div class="heatmap-popover-meta">판정: ${escapeHtml(sourceLabel)} · ${escapeHtml(terms)}</div>`;
  pop.classList.remove('hidden');

  const rect = cell.getBoundingClientRect();
  pop.style.visibility = 'hidden';
  pop.style.left = '0';
  pop.style.top = '0';
  const popRect = pop.getBoundingClientRect();
  pop.style.visibility = '';

  const gap = 10;
  let left = rect.right + gap;
  let top = rect.top + rect.height / 2 - popRect.height / 2;

  if (left + popRect.width > window.innerWidth - 12) {
    left = rect.left - popRect.width - gap;
  }
  if (top < 12) top = 12;
  if (top + popRect.height > window.innerHeight - 12) {
    top = window.innerHeight - popRect.height - 12;
  }

  pop.style.left = `${left}px`;
  pop.style.top = `${top}px`;
}

function hideHeatmapPopover() {
  ensureHeatmapPopover().classList.add('hidden');
}

function bindHeatmapTooltips(table) {
  if (!table || table.dataset.citeBound) return;
  table.dataset.citeBound = '1';

  table.addEventListener('mouseover', (e) => {
    const cell = e.target.closest('[data-cite]');
    if (!cell || !table.contains(cell)) return;
    showHeatmapPopover(cell);
  });

  table.addEventListener('mouseout', (e) => {
    const from = e.target.closest('[data-cite]');
    const to = e.relatedTarget?.closest?.('[data-cite]');
    if (from && from === to) return;
    hideHeatmapPopover();
  });

  table.addEventListener('focusin', (e) => {
    const cell = e.target.closest('[data-cite]');
    if (cell) showHeatmapPopover(cell);
  });

  table.addEventListener('focusout', () => hideHeatmapPopover());
}

function heatmapStatusCell(status, article, score, extraClass = '') {
  const cls = `heatmap-cell ${extraClass} ${heatmapClass(status)}`.trim();
  const cite = heatmapCiteAttr(status, article, score);
  return `<td class="${cls}"${cite}>${status}</td>`;
}

function renderMarkdown(text) {
  if (!text) return '';
  const lines = text.split('\n');
  const parts = [];
  let inList = false;

  const flushList = () => {
    if (inList) { parts.push('</ul>'); inList = false; }
  };

  for (const raw of lines) {
    const line = raw.trimEnd();
    if (!line.trim()) { flushList(); continue; }

    if (/^#{1,3}\s/.test(line)) {
      flushList();
      const level = line.match(/^#+/)[0].length;
      const content = escapeHtml(line.replace(/^#+\s*/, ''));
      parts.push(`<h${Math.min(level, 3)}>${content}</h${Math.min(level, 3)}>`);
      continue;
    }

    if (/^[-*]\s/.test(line)) {
      if (!inList) { parts.push('<ul>'); inList = true; }
      parts.push(`<li>${formatInline(line.replace(/^[-*]\s*/, ''))}</li>`);
      continue;
    }

    flushList();
    parts.push(`<p>${formatInline(line)}</p>`);
  }
  flushList();
  return parts.join('\n');
}

function formatInline(text) {
  return escapeHtml(text)
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/_(.+?)_/g, '<em>$1</em>');
}

function setSummary(el, text) {
  el.innerHTML = renderMarkdown(text || '');
}

function highlightTopic(text, topic) {
  if (!text || !topic) return escapeHtml(text);
  const safe = escapeHtml(text);
  const keywords = topic.split(/\s+/).filter(Boolean);
  let result = safe;
  for (const kw of keywords) {
    if (kw.length < 2) continue;
    const re = new RegExp(`(${kw.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi');
    result = result.replace(re, '<span class="hl-keyword">$1</span>');
  }
  return result;
}

function renderCitation(c) {
  const score = c.score != null
    ? `<span class="score-badge">유사도 ${Math.round(c.score * 100)}%</span>` : '';
  return `
    <div class="citation-card">
      <div class="citation-title">${escapeHtml(c.org)} · ${escapeHtml(c.label || c.article_no)}${score}</div>
      <div class="citation-meta">출처: ${escapeHtml(c.source_file)}</div>
      <div class="citation-body">${escapeHtml(c.excerpt || '')}</div>
    </div>`;
}

function renderList(el, items, emptyMsg = '해당 항목 없음') {
  if (!items?.length) {
    el.innerHTML = `<li class="empty-msg">${emptyMsg}</li>`;
    return;
  }
  el.innerHTML = items.map(i => `<li>${formatInline(i)}</li>`).join('');
}

function renderCompareBanner(orgA, orgB, topic) {
  $('#compare-banner').innerHTML = `
    <div class="compare-banner-main">
      <span class="compare-org compare-org-a">${escapeHtml(orgA)}</span>
      <span class="compare-vs" aria-hidden="true">↔</span>
      <span class="compare-org compare-org-b">${escapeHtml(orgB)}</span>
    </div>
    <div class="compare-banner-topic">주제 · <strong>${escapeHtml(topic)}</strong></div>`;
}

function syncCompareChipActive() {
  const topic = ($('#compare-topic')?.value || '').trim();
  $$('.chip-compare').forEach(chip => {
    chip.classList.toggle('active', chip.dataset.sample === topic);
  });
}

function renderCompareTable(table, rows, orgA, orgB, topic) {
  if (!rows.length) {
    table.innerHTML = '<tbody><tr><td colspan="3" class="empty-msg">비교 데이터 없음</td></tr></tbody>';
    return;
  }

  table.innerHTML = `
    <thead>
      <tr>
        <th class="col-label">항목</th>
        <th class="th-org-a">${escapeHtml(orgA)}</th>
        <th class="th-org-b">${escapeHtml(orgB)}</th>
      </tr>
    </thead>
    <tbody>${rows.map(row => {
      const label = row['항목'] || '';
      const valA = row[orgA] ?? '-';
      const valB = row[orgB] ?? '-';
      const isDiff = valA !== valB && valA !== '-' && valB !== '-';
      const isEmptyA = !valA || valA === '-' || valA === '해당 없음';
      const isEmptyB = !valB || valB === '-' || valB === '해당 없음';
      const fmt = (v, empty) => {
        if (empty) return `<span class="cell-empty">${escapeHtml(v)}</span>`;
        if (label.includes('내용')) return `<div class="cell-content">${highlightTopic(v, topic)}</div>`;
        return highlightTopic(v, topic);
      };
      return `
        <tr>
          <th class="col-label">${escapeHtml(label)}</th>
          <td class="col-org-a ${isDiff ? 'cell-diff' : ''}">${fmt(valA, isEmptyA)}</td>
          <td class="col-org-b ${isDiff ? 'cell-diff' : ''}">${fmt(valB, isEmptyB)}</td>
        </tr>`;
    }).join('')}</tbody>`;
}

function renderGapMatrix(table, matrix, targetOrg) {
  table.innerHTML = `
    <thead><tr>
      <th>주제</th><th>${escapeHtml(targetOrg)}</th><th>상태</th>
      <th>타기관 보유</th><th>검토</th>
    </tr></thead>
    <tbody>${matrix.map(row => `
      <tr class="${row.review_needed ? 'review-row' : ''}">
        <td><strong>${escapeHtml(row.topic)}</strong><br>
          <span style="font-size:0.75rem;color:var(--gov-text-muted)">${escapeHtml(row.description)}</span></td>
        <td>${row.target_article
          ? `<span style="font-size:0.8125rem">${escapeHtml(row.target_article.label)}</span>`
          : '<span class="empty-msg">-</span>'}</td>
        <td>${statusBadge(row.target_status)}</td>
        <td><span class="badge badge-count">${row.others_have_count}개 기관</span></td>
        <td>${row.review_needed
          ? '<span class="badge badge-review">검토 권고</span>'
          : '-'}</td>
      </tr>`).join('')}</tbody>`;
}

function renderReportHero(targetOrg, generatedAt) {
  const date = generatedAt
    ? new Date(generatedAt).toLocaleString('ko-KR')
    : new Date().toLocaleString('ko-KR');
  $('#report-hero').innerHTML = `
    <h3>${escapeHtml(targetOrg)} 벤치마킹 분석 리포트</h3>
    <p>12개 체크리스트(전 기관 동일 기준) · ${date}</p>`;
}

function renderReportStats(st) {
  $('#report-stats').innerHTML = `
    <div class="stat-card stat-total"><div class="num">${st.total_topics}</div><div class="lbl">분석 주제</div></div>
    <div class="stat-card stat-ok"><div class="num">${st.ok}</div><div class="lbl">커버리지 충족</div></div>
    <div class="stat-card stat-warn"><div class="num">${st.missing + st.weak}</div><div class="lbl">미존재 / 약함</div></div>
    <div class="stat-card stat-alert"><div class="num">${st.review_count}</div><div class="lbl">검토 권고</div></div>`;
}

function renderReportProgress(st) {
  const total = st.total_topics || 1;
  const pctOk = (st.ok / total) * 100;
  const pctWeak = (st.weak / total) * 100;
  const pctMiss = (st.missing / total) * 100;
  $('#report-progress-wrap').innerHTML = `
    <h3 class="result-title">커버리지 현황</h3>
    <div class="progress-bar">
      <div class="progress-seg-ok"   style="width:${pctOk}%"   title="충족 ${st.ok}"></div>
      <div class="progress-seg-weak" style="width:${pctWeak}%" title="미흡 ${st.weak}"></div>
      <div class="progress-seg-miss" style="width:${pctMiss}%" title="미존재 ${st.missing}"></div>
    </div>
    <div class="progress-legend">
      <span><span class="legend-dot ok"></span>충족 ${st.ok} (${pctOk.toFixed(0)}%)</span>
      <span><span class="legend-dot weak"></span>미흡 ${st.weak} (${pctWeak.toFixed(0)}%)</span>
      <span><span class="legend-dot miss"></span>미존재 ${st.missing} (${pctMiss.toFixed(0)}%)</span>
    </div>`;
}

function renderReportReviewItems(items) {
  const el = $('#report-review-items');
  if (!items?.length) {
    el.innerHTML = '<p class="empty-msg">검토 권고 항목이 없습니다. 전반적 커버리지가 양호합니다.</p>';
    return;
  }
  el.innerHTML = items.map((r, i) => `
    <div class="review-card">
      <div class="review-card-header">
        <span class="review-card-title">${i + 1}. ${escapeHtml(r.topic)}</span>
        ${statusBadge(r.target_status)}
        <span class="badge badge-count">타 기관 ${r.others_have_count}개 보유</span>
      </div>
      <p style="color:var(--gov-text-sub);font-size:0.8125rem">${escapeHtml(r.description)}</p>
      ${r.target_article
        ? `<p style="font-size:0.75rem;color:var(--gov-text-muted);margin-top:0.25rem">현행 조문: ${escapeHtml(r.target_article.label)}</p>`
        : '<p style="font-size:0.75rem;color:var(--status-miss);margin-top:0.25rem">관련 조문 미발견</p>'}
    </div>`).join('');
}

function renderReportHeatmap(matrix, targetOrg, orgs) {
  const others = orgs.filter(o => o !== targetOrg);
  const table = $('#report-heatmap');
  if (!matrix?.length) { table.innerHTML = ''; return; }

  table.innerHTML = `
    <thead><tr>
      <th style="min-width:140px">주제</th>
      <th class="heatmap-target">${escapeHtml(targetOrg)}</th>
      ${others.map(o => `<th>${escapeHtml(o)}</th>`).join('')}
      <th>검토</th>
    </tr></thead>
    <tbody>${matrix.map(row => `
      <tr class="${row.review_needed ? 'review-row' : ''}">
        <td>
          <strong>${escapeHtml(row.topic)}</strong>
          <div style="font-size:0.75rem;color:var(--gov-text-muted);margin-top:0.15rem">${escapeHtml(row.description)}</div>
        </td>
        ${heatmapStatusCell(
          row.target_status,
          row.target_article,
          row.target_score,
          'heatmap-target',
        )}
        ${others.map(o => {
          const cell = row.by_org?.[o];
          const st = cell?.status || '없음';
          return heatmapStatusCell(st, cell?.article, cell?.score);
        }).join('')}
        <td style="text-align:center">${row.review_needed
          ? '<span class="badge badge-review">권고</span>'
          : '-'}</td>
      </tr>`).join('')}</tbody>`;

  bindHeatmapTooltips(table);
}

function renderReportSections(markdown) {
  const el = $('#report-sections');
  if (!markdown) { el.innerHTML = ''; return; }

  const parts = markdown.split(/(?=^## )/m);
  el.innerHTML = parts.map(part => {
    const trimmed = part.trim();
    if (!trimmed) return '';
    if (trimmed.startsWith('## ')) {
      const lines = trimmed.split('\n');
      const title = lines[0].replace(/^##\s*/, '');
      const body = lines.slice(1).join('\n');
      return `
        <div class="report-section">
          <h4>${escapeHtml(title)}</h4>
          <div class="prose">${renderMarkdown(body)}</div>
        </div>`;
    }
    return `<div class="report-section prose">${renderMarkdown(trimmed)}</div>`;
  }).join('');
}

async function loadStats() {
  const s = await api('/api/stats');
  orgs = s.orgs || [];
  $('#stat-orgs').textContent = s.org_count;
  $('#stat-articles').textContent = s.article_count;
  populateSelects();
  return s;
}

function populateSelects() {
  ['compare-a', 'compare-b', 'gap-org', 'report-org'].forEach((id) => {
    const el = $(`#${id}`);
    if (!el) return;
    el.innerHTML = orgs.map(o => `<option value="${o}">${o}</option>`).join('');
  });
  if (orgs.length >= 2) $('#compare-b').selectedIndex = 1;
  const kw = orgs.indexOf('한국수자원공사');
  if (kw >= 0) {
    $('#gap-org').selectedIndex = kw;
    $('#report-org').selectedIndex = kw;
  }
}

async function loadRegulations() {
  const list = await api('/api/regulations');
  const el = $('#regulation-list');
  if (!list.length) {
    el.innerHTML = '<p class="empty-msg">등록된 규정이 없습니다.</p>';
    return;
  }
  el.innerHTML = list.map(r => `
    <div class="regulation-item">
      <div>
        <div class="regulation-item-name">${escapeHtml(r.org)}</div>
        <div class="regulation-item-file">${escapeHtml(r.filename)}</div>
      </div>
      <span class="regulation-item-tag">${escapeHtml(r.regulation)}</span>
    </div>`).join('');
}

$$('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    if (btn.disabled) return;
    $$('.tab-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    $$('.panel').forEach(p => p.classList.add('hidden'));
    $(`#panel-${btn.dataset.tab}`).classList.remove('hidden');
    if (btn.dataset.tab === 'upload') loadRegulations();
  });
});

$$('.chip').forEach(chip => {
  chip.addEventListener('click', () => { $('#search-query').value = chip.dataset.sample; });
});
$$('.chip-similar').forEach(chip => {
  chip.addEventListener('click', () => { $('#similar-query').value = chip.dataset.sample; });
});
$$('.chip-compare').forEach(chip => {
  chip.addEventListener('click', () => {
    $('#compare-topic').value = chip.dataset.sample;
    syncCompareChipActive();
  });
});
$('#compare-topic')?.addEventListener('input', syncCompareChipActive);

$('#btn-search').addEventListener('click', async () => {
  const query = $('#search-query').value.trim();
  if (!query) return;
  showLoading(true);
  try {
    const data = await api('/api/search', { method: 'POST', body: JSON.stringify({ query }) });
    $('#search-result').classList.remove('hidden');
    setSummary($('#search-summary'), data.summary);
    $('#search-citations').innerHTML = data.citations.map(renderCitation).join('')
      || '<p class="empty-msg">관련 조문 없음</p>';
  } catch (e) { alert(e.message); }
  finally { showLoading(false); }
});

$('#btn-similar').addEventListener('click', async () => {
  const query = $('#similar-query').value.trim();
  if (!query) return;
  showLoading(true);
  try {
    const data = await api('/api/similar', { method: 'POST', body: JSON.stringify({ query }) });
    $('#similar-result').classList.remove('hidden');
    setSummary($('#similar-summary'), data.summary);
    const entries = Object.entries(data.by_org || {});
    $('#similar-by-org').innerHTML = entries.length
      ? entries.map(([, c]) => renderCitation(c)).join('')
      : '<p class="empty-msg">유사 조문 없음</p>';
  } catch (e) { alert(e.message); }
  finally { showLoading(false); }
});

$('#btn-compare').addEventListener('click', async () => {
  const org_a = $('#compare-a').value;
  const org_b = $('#compare-b').value;
  const topic = $('#compare-topic').value.trim();
  if (!topic) return alert('비교 주제를 입력하세요.');
  showLoading(true);
  try {
    const data = await api('/api/compare', {
      method: 'POST', body: JSON.stringify({ org_a, org_b, topic }),
    });
    $('#compare-result').classList.remove('hidden');
    renderCompareBanner(data.org_a, data.org_b, topic);
    setSummary($('#compare-summary'), data.summary);
    renderList($('#compare-common'), data.common_points, '공통 요소가 확인되지 않았습니다.');
    renderList($('#compare-diff'), data.differences, '뚜렷한 차이가 확인되지 않았습니다.');
    renderCompareTable($('#compare-table'), data.comparison_table || [], org_a, org_b, topic);
    $('#compare-title-a').textContent = `${data.org_a} — 근거 조문`;
    $('#compare-title-b').textContent = `${data.org_b} — 근거 조문`;
    $('#compare-citations-a').innerHTML = data.org_a_citations.map(renderCitation).join('')
      || '<p class="empty-msg">없음</p>';
    $('#compare-citations-b').innerHTML = data.org_b_citations.map(renderCitation).join('')
      || '<p class="empty-msg">없음</p>';
    $('#compare-result').scrollIntoView({ behavior: 'smooth', block: 'start' });
  } catch (e) { alert(e.message); }
  finally { showLoading(false); }
});

$('#btn-gap').addEventListener('click', async () => {
  const target_org = $('#gap-org').value;
  const topic = $('#gap-topic').value.trim();
  if (!topic) return alert('검토 주제를 입력하세요.');
  showLoading(true);
  try {
    const data = await api('/api/gap', {
      method: 'POST', body: JSON.stringify({ target_org, topic }),
    });
    $('#gap-result').classList.remove('hidden');
    $('#gap-matrix-wrap').classList.add('hidden');
    $('#gap-alert').innerHTML = data.review_needed
      ? `<div class="alert-warn"><strong>검토 권고</strong> — ${escapeHtml(target_org)}, 주제「${escapeHtml(topic)}」</div>`
      : '<div class="alert-info">체크리스트 기준 검토 권고 대상이 아닙니다. 기준 기관에도 관련 조문이 확인되었습니다.</div>';
    setSummary($('#gap-summary'), data.summary);
    const targetCard = data.target_citation
      ? renderCitation(data.target_citation)
      : '<p class="empty-msg">관련 조문 없음</p>';
    $('#gap-target').innerHTML = targetCard;
    $('#gap-target-wrap').classList.remove('hidden');
    const othersTitle = $('#gap-others-title');
    const othersDesc = $('#gap-others-desc');
    if (data.review_needed) {
      othersTitle.textContent = '타 기관 관련 조문';
      othersDesc.classList.add('hidden');
      $('#gap-others-wrap').classList.remove('hidden');
      const others = Object.entries(data.other_orgs || {});
      $('#gap-others').innerHTML = others.length
        ? others.map(([, c]) => renderCitation(c)).join('')
        : '<p class="empty-msg">없음</p>';
    } else {
      const refs = Object.entries(data.reference_orgs || {});
      if (refs.length) {
        othersTitle.textContent = '참고: 타 기관 조문';
        othersDesc.textContent = '검토 권고 대상이 아닙니다. 세부 비교가 필요할 때 참고하세요.';
        othersDesc.classList.remove('hidden');
        $('#gap-others-wrap').classList.remove('hidden');
        $('#gap-others').innerHTML = refs.map(([, c]) => renderCitation(c)).join('');
      } else {
        $('#gap-others-wrap').classList.add('hidden');
      }
    }
  } catch (e) { alert(e.message); }
  finally { showLoading(false); }
});

$('#btn-gap-scan').addEventListener('click', async () => {
  const target_org = $('#gap-org').value;
  showLoading(true);
  try {
    const data = await api('/api/gap/scan', {
      method: 'POST', body: JSON.stringify({ target_org }),
    });
    $('#gap-result').classList.remove('hidden');
    $('#gap-matrix-wrap').classList.remove('hidden');
    $('#gap-alert').innerHTML = data.review_count > 0
      ? `<div class="alert-warn"><strong>${data.review_count}개 주제</strong>에서 검토가 권고됩니다.</div>`
      : '<div class="alert-info">검토 권고 대상 주제가 없습니다. 체크리스트 기준으로 커버리지가 양호합니다.</div>';
    $('#gap-summary').innerHTML = `<strong>${escapeHtml(target_org)}</strong> — ${data.coverage_matrix?.length ?? 12}개 체크리스트 전체 스캔을 완료하였습니다.`;
    renderGapMatrix($('#gap-matrix'), data.coverage_matrix, target_org);
    $('#gap-target-wrap').classList.add('hidden');
    $('#gap-others-title').textContent = '검토 권고 항목';
    $('#gap-others-desc').classList.add('hidden');
    $('#gap-others-wrap').classList.remove('hidden');
    $('#gap-others').innerHTML = data.review_items.map(r => `
      <div class="review-card">
        <div class="review-card-header">
          <span class="review-card-title">${escapeHtml(r.topic)}</span>
          ${statusBadge(r.target_status)}
        </div>
        <p style="font-size:0.8125rem;color:var(--gov-text-sub)">${escapeHtml(r.description)}</p>
        <span style="font-size:0.75rem;color:var(--gov-text-muted)">타 기관 ${r.others_have_count}개 보유</span>
      </div>`).join('') || '<p class="empty-msg">검토 권고 대상 주제가 없습니다. 표의 「N개 기관」은 타 기관 보유 수이며, 기준 기관도 충족하면 권고하지 않습니다.</p>';
  } catch (e) { alert(e.message); }
  finally { showLoading(false); }
});

const btnReport = $('#btn-report');
if (btnReport) btnReport.addEventListener('click', async () => {
  const target_org = $('#report-org')?.value;
  if (!target_org) return alert('기준 기관을 선택하세요.');
  showLoading(true);
  try {
    const data = await api('/api/report', {
      method: 'POST', body: JSON.stringify({ target_org }),
    });
    $('#report-result')?.classList.remove('hidden');
    renderReportHero(data.target_org, data.generated_at);
    renderReportStats(data.stats);
    renderReportProgress(data.stats);
    setSummary($('#report-ai-summary'), data.ai_summary);
    renderReportReviewItems(data.review_items);
    renderReportHeatmap(data.coverage_matrix, data.target_org, data.orgs || orgs);
    renderReportSections(data.report_markdown);
    $('#report-result')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  } catch (e) { alert(e.message); }
  finally { showLoading(false); }
});

$('#btn-upload').addEventListener('click', async () => {
  const file = $('#file-input').files[0];
  if (!file) return alert('파일을 선택하세요.');
  showLoading(true);
  const fd = new FormData();
  fd.append('file', file);
  try {
    const res = await fetch('/api/regulations/upload', { method: 'POST', body: fd });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || '업로드 실패');
    const msg = $('#upload-msg');
    msg.classList.remove('hidden', 'error');
    msg.classList.add('success');
    msg.textContent = `[완료] ${data.org} — 조문 ${data.article_count}건 색인 완료`;
    await loadStats();
    await loadRegulations();
  } catch (e) {
    const msg = $('#upload-msg');
    msg.classList.remove('hidden', 'success');
    msg.classList.add('error');
    msg.textContent = e.message;
  } finally { showLoading(false); }
});

$('#btn-reindex').addEventListener('click', async () => {
  showLoading(true);
  try {
    const data = await api('/api/regulations/reindex', { method: 'POST' });
    alert(`재색인 완료 (${data.results.length}개 파일)`);
    await loadStats();
    await loadRegulations();
  } catch (e) { alert(e.message); }
  finally { showLoading(false); }
});

$('#search-query').addEventListener('keydown', e => { if (e.key === 'Enter') $('#btn-search').click(); });
$('#similar-query').addEventListener('keydown', e => { if (e.key === 'Enter') $('#btn-similar').click(); });

loadStats().catch(console.error);
