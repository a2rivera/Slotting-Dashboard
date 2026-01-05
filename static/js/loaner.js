(function () {
  const initialData = window.__INITIAL_DATA__ || { loaners: [], email: "" };

  const el = {
    rows: document.getElementById('loanerRows'),
    total: document.getElementById('totalLoaners'),
    kInStock: document.getElementById('kpiInStock'),
    kInUse: document.getElementById('kpiInUse'),
    kReimaging: document.getElementById('kpiReimaging'),
    filterInStock: document.getElementById('filterInStock'),
    filterInUse: document.getElementById('filterInUse'),
    filterReimaging: document.getElementById('filterReimaging'),
    clearFilters: document.getElementById('clearFilters'),
    refresh: document.getElementById('refreshData')
  };

  const state = {
    filter: 'all',  // 'in_stock' | 'in_use' | 'reimaging' | 'all'
    idSeq: 0
  };

  // ---------- Utilities ----------
  function parseDate(dateStr) {
    if (!dateStr) return null;
    const trimmed = String(dateStr).trim();
    // Try YYYY-MM-DD
    if (/^\d{4}-\d{2}-\d{2}$/.test(trimmed)) return new Date(trimmed + 'T00:00:00');
    // Try M/D or MM/DD (assume current year)
    if (/^\d{1,2}\/\d{1,2}$/.test(trimmed)) {
      const [m, d] = trimmed.split('/').map(x => parseInt(x, 10));
      const y = new Date().getFullYear();
      return new Date(y, m - 1, d);
    }
    // Fallback Date parse
    const dt = new Date(trimmed);
    return isNaN(dt) ? null : dt;
  }

  function formatDate(date) {
    if (!date) return '';
    const d = new Date(date);
    if (isNaN(d)) return '';
    return d.toLocaleDateString('en-US', { year: 'numeric', month: '2-digit', day: '2-digit' });
  }

  function classifyDateBadge(date) {
    if (!date) return 'date-badge';
    const today = new Date(); today.setHours(0, 0, 0, 0);
    const d = new Date(date); d.setHours(0, 0, 0, 0);
    if (d.getTime() < today.getTime()) return 'date-badge date-overdue';
    if (d.getTime() === today.getTime()) return 'date-badge date-today';
    return 'date-badge date-future';
  }

  function getStatusClass(status) {
    const s = String(status).toLowerCase();
    if (s === 'in stock') return 'status-badge status-in-stock';
    if (s === 'in use') return 'status-badge status-in-use';
    if (s === 're-imaging' || s === 'reimaging') return 'status-badge status-reimaging';
    return 'status-badge';
  }

  // ---------- Row factory ----------
  function addLoanerRow({ name, status, dateOfReturn, userAssigned }) {
    const id = `row_${++state.idSeq}`;
    const tr = document.createElement('tr');
    tr.id = id;

    // Normalize status
    const normalizedStatus = String(status || '').toLowerCase();
    const isInStock = normalizedStatus === 'in stock';
    const isInUse = normalizedStatus === 'in use';
    const isReimaging = normalizedStatus === 're-imaging' || normalizedStatus === 'reimaging';

    tr.dataset.status = normalizedStatus;
    tr.dataset.name = name || '';

    // Cells
    // Loaner Name
    const tdName = document.createElement('td');
    tdName.className = 'col-name';
    tdName.textContent = name || '';
    tr.appendChild(tdName);

    // Status
    const tdStatus = document.createElement('td');
    tdStatus.className = 'col-status';
    const statusBadge = document.createElement('span');
    statusBadge.className = getStatusClass(status);
    statusBadge.textContent = status || '';
    tdStatus.appendChild(statusBadge);
    tr.appendChild(tdStatus);

    // Date of Return
    const tdDate = document.createElement('td');
    tdDate.className = 'col-date';
    const dateObj = parseDate(dateOfReturn);
    if (dateObj) {
      const badge = document.createElement('span');
      badge.className = classifyDateBadge(dateObj);
      badge.textContent = formatDate(dateObj);
      tdDate.appendChild(badge);
    } else {
      tdDate.innerHTML = '<span class="muted">—</span>';
    }
    tr.appendChild(tdDate);

    // User Assigned To
    const tdUser = document.createElement('td');
    tdUser.className = 'col-user';
    if (isInUse && userAssigned) {
      tdUser.textContent = userAssigned;
    } else {
      tdUser.innerHTML = '<span class="muted">—</span>';
    }
    tr.appendChild(tdUser);

    // Notify
    const tdNotify = document.createElement('td');
    tdNotify.className = 'col-notify';
    if (isInUse && userAssigned) {
      const btn = document.createElement('button');
      btn.className = 'notify';
      btn.textContent = 'Notify';
      btn.dataset.loanerName = name || '';
      btn.dataset.userEmail = userAssigned || '';
      btn.addEventListener('click', () => onNotify(tr, btn));
      tdNotify.appendChild(btn);
    } else {
      tdNotify.innerHTML = '<span class="muted">—</span>';
    }
    tr.appendChild(tdNotify);

    el.rows.appendChild(tr);
    recount();
    applyFilters();
    return id;
  }

  function showPopup(content) {
    const modal = document.createElement('div');
    modal.style.position = 'fixed';
    modal.style.top = '0';
    modal.style.left = '0';
    modal.style.width = '100%';
    modal.style.height = '100%';
    modal.style.backgroundColor = 'rgba(0,0,0,0.6)';
    modal.style.display = 'flex';
    modal.style.alignItems = 'center';
    modal.style.justifyContent = 'center';
    modal.style.zIndex = '9999';

    const box = document.createElement('div');
    box.style.backgroundColor = '#fff';
    box.style.color = '#333';
    box.style.padding = '20px';
    box.style.borderRadius = '10px';
    box.style.boxShadow = '0 4px 12px rgba(0,0,0,0.3)';
    box.style.width = '400px';
    box.style.fontFamily = 'Segoe UI, sans-serif';
    box.innerHTML = `
      <div>${content}</div>
      <button id="closePopup" style="
        margin-top:15px;
        padding:10px 15px;
        background:#3a82f6;
        color:#fff;
        border:none;
        border-radius:6px;
        cursor:pointer;
        font-weight:bold;
      ">Close</button>
    `;

    modal.appendChild(box);
    document.body.appendChild(modal);

    document.getElementById('closePopup').addEventListener('click', () => {
      document.body.removeChild(modal);
    });
  }

  function onNotify(tr, btn) {
    btn.classList.add('loading');
    btn.disabled = true;

    const loanerName = btn.dataset.loanerName;
    const userEmail = btn.dataset.userEmail;
    const url = `${window.location.origin}/notify-loaner-return`;

    fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        loanerName: loanerName,
        userEmail: userEmail
      })
    })
      .then(res => res.json())
      .then(data => {
        if (data.success) {
          showPopup(`Notification sent to ${userEmail} for loaner ${loanerName}.`);
        } else {
          showPopup(`Failed to send notification: ${data.error || 'Unknown error'}`);
        }
        btn.classList.remove('loading');
        btn.disabled = false;
      })
      .catch(err => {
        console.error('Notify failed:', err);
        showPopup(`Error sending notification: ${err.message}`);
        btn.classList.remove('loading');
        btn.disabled = false;
      });
  }

  // ---------- Filtering ----------
  function applyFilters() {
    const rows = el.rows.querySelectorAll('tr');
    rows.forEach(tr => {
      const rowStatus = tr.dataset.status;

      // Always hide "not found" status loaners
      if (rowStatus === 'not found') {
        tr.style.display = 'none';
        return;
      }

      let show = true;
      if (state.filter === 'in_stock') {
        show = rowStatus === 'in stock';
      } else if (state.filter === 'in_use') {
        show = rowStatus === 'in use';
      } else if (state.filter === 'reimaging') {
        show = rowStatus === 're-imaging' || rowStatus === 'reimaging';
      }

      tr.style.display = show ? '' : 'none';
    });
  }

  function clearFilters() {
    state.filter = 'all';
    [el.filterInStock, el.filterInUse, el.filterReimaging].forEach(b => b.classList.remove('active'));
    applyFilters();
  }

  // ---------- Counters ----------
  function recount() {
    const all = el.rows.querySelectorAll('tr');
    let total = 0;
    let inStock = 0;
    let inUse = 0;
    let reimaging = 0;

    all.forEach(tr => {
      const status = tr.dataset.status;
      // Exclude "not found" status from all counts
      if (status === 'not found') {
        return;
      }
      
      total++;
      if (status === 'in stock') inStock++;
      else if (status === 'in use') inUse++;
      else if (status === 're-imaging' || status === 'reimaging') reimaging++;
    });

    el.total.textContent = String(total);
    el.kInStock.textContent = String(inStock);
    el.kInUse.textContent = String(inUse);
    el.kReimaging.textContent = String(reimaging);
  }

  // Filter setters
  function setFilter(f) {
    state.filter = f;
    localStorage.setItem('loanerFilterPreference', f);
    [el.filterInStock, el.filterInUse, el.filterReimaging].forEach(b => b.classList.remove('active'));
    if (f === 'in_stock') el.filterInStock.classList.add('active');
    else if (f === 'in_use') el.filterInUse.classList.add('active');
    else if (f === 'reimaging') el.filterReimaging.classList.add('active');
    applyFilters();
  }

  // Wire UI
  el.filterInStock.addEventListener('click', () => setFilter(state.filter === 'in_stock' ? 'all' : 'in_stock'));
  el.filterInUse.addEventListener('click', () => setFilter(state.filter === 'in_use' ? 'all' : 'in_use'));
  el.filterReimaging.addEventListener('click', () => setFilter(state.filter === 'reimaging' ? 'all' : 'reimaging'));
  el.clearFilters.addEventListener('click', clearFilters);

  // Manual refresh button
  if (el.refresh) {
    el.refresh.addEventListener('click', () => {
      el.refresh.disabled = true;
      const originalText = el.refresh.textContent;
      el.refresh.textContent = 'Refreshing...';

      fetch(`${window.location.origin}/get-loaner-data`)
        .then(res => res.json())
        .then(json => {
          const loaners = json.loaners || [];
          renderTable(loaners);
        })
        .catch(err => {
          console.error('Refresh failed:', err);
        })
        .finally(() => {
          el.refresh.disabled = false;
          el.refresh.textContent = originalText;
        });
    });
  }

  // ---------- Sorting & Persistence ----------
  let sortState = {
    column: localStorage.getItem('loanerSortColumn') || null,
    direction: localStorage.getItem('loanerSortDirection') || 'asc'
  };

  function applySort(columnIndex, direction) {
    const rowsArray = Array.from(document.querySelectorAll('#loanerRows tr'));
    rowsArray.sort((a, b) => {
      const aText = a.children[columnIndex].textContent.trim().toLowerCase();
      const bText = b.children[columnIndex].textContent.trim().toLowerCase();

      // Date comparison for date column
      if (columnIndex === 2) {
        const aDate = parseDate(a.children[columnIndex].querySelector('span')?.textContent || '');
        const bDate = parseDate(b.children[columnIndex].querySelector('span')?.textContent || '');
        if (aDate && bDate) {
          return direction === 'asc' ? aDate - bDate : bDate - aDate;
        }
        if (aDate) return direction === 'asc' ? -1 : 1;
        if (bDate) return direction === 'asc' ? 1 : -1;
        return 0;
      }

      // Numeric comparison if both are numbers
      const aNum = parseFloat(aText);
      const bNum = parseFloat(bText);
      if (!isNaN(aNum) && !isNaN(bNum)) {
        return direction === 'asc' ? aNum - bNum : bNum - aNum;
      }

      // String comparison
      return direction === 'asc' ? aText.localeCompare(bText) : bText.localeCompare(aText);
    });

    const tbody = document.getElementById('loanerRows');
    tbody.innerHTML = '';
    rowsArray.forEach(row => tbody.appendChild(row));
  }

  function updateIndicators() {
    document.querySelectorAll('thead th').forEach((th, i) => {
      th.textContent = th.textContent.replace(/ ▲| ▼/g, '');
      if (sortState.column == i) {
        th.textContent += sortState.direction === 'asc' ? ' ▲' : ' ▼';
      }
    });
  }

  // Apply saved sort on load
  if (sortState.column !== null) {
    applySort(parseInt(sortState.column), sortState.direction);
  }

  // Add click listeners to headers
  document.querySelectorAll('thead th').forEach((th, index) => {
    th.style.cursor = 'pointer';
    th.addEventListener('click', () => {
      const newDirection = (sortState.column == index && sortState.direction === 'asc') ? 'desc' : 'asc';
      sortState = { column: index, direction: newDirection };

      localStorage.setItem('loanerSortColumn', index);
      localStorage.setItem('loanerSortDirection', newDirection);

      applySort(index, newDirection);
      updateIndicators();
    });
  });

  // Initial indicator update
  updateIndicators();

  // Restore filter on load
  const savedFilter = localStorage.getItem('loanerFilterPreference');
  if (savedFilter) setFilter(savedFilter);

  function renderTable(data) {
    const tableBody = document.getElementById('loanerRows');
    tableBody.innerHTML = "";

    if (!Array.isArray(data)) {
      console.error("Expected array for data, got:", data);
      return;
    }

    data.forEach(item => {
      addLoanerRow({
        name: item.name || item.loaner_name || '',
        status: item.status || '',
        dateOfReturn: item.date_of_return || item.dateOfReturn || '',
        userAssigned: item.user_assigned_to || item.userAssigned || ''
      });
    });

    if (sortState.column !== null) {
      applySort(parseInt(sortState.column), sortState.direction);
      updateIndicators();
    }
  }

  // Auto-refresh every 5 seconds
  setInterval(() => {
    fetch(`${window.location.origin}/get-loaner-data`)
      .then(res => res.json())
      .then(json => {
        if (json.loaners) {
          renderTable(json.loaners);
        } else {
          renderTable([]);
        }
      });
  }, 5000);

  // Initial render
  renderTable(initialData.loaners || []);

  if (sortState.column !== null) {
    applySort(parseInt(sortState.column), sortState.direction);
    updateIndicators();
  }
})();

