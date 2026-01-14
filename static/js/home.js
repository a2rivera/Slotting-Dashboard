(function () {
  const initialData = window.__INITIAL_DATA__ || { rows: { result: [] }, email: "" };

  const el = {
    rows: document.getElementById('deviceRows'),
    total: document.getElementById('totalDevices'),
    kSlotted: document.getElementById('kpiSlotted'),
    kUnslotted: document.getElementById('kpiUnslotted'),
    filterComputer: document.getElementById('filterComputer'),
    filterIncident: document.getElementById('filterIncident'),
    filterPhone: document.getElementById('filterPhone'),
    clearFilters: document.getElementById('clearFilters'),
    refresh: document.getElementById('refreshData'),
    categoryBar: document.getElementById('categoryBar')
  };

  const state = {
    filter: 'all',      // 'computer' | 'incident' | 'phone' | 'all'
    category: 'all',    // 'elitebooks'|'zbooks'|'toughbooks'|'repaired'|'desktops'|'phones'|'all'
    idSeq: 0
  };

  // ---------- Utilities ----------
  function parseUcd(ucd) {
    // Return {date: Date|null, text: string}
    if (!ucd) return { date: null, text: '' };
    const trimmed = String(ucd).trim();
    // Try YYYY-MM-DD
    if (/^\d{4}-\d{2}-\d{2}$/.test(trimmed)) return { date: new Date(trimmed + 'T00:00:00'), text: trimmed };
    // Try M/D or MM/DD (handle year transition intelligently)
    if (/^\d{1,2}\/\d{1,2}$/.test(trimmed)) {
      const [m, d] = trimmed.split('/').map(x => parseInt(x, 10));
      const today = new Date();
      const currentYear = today.getFullYear();
      
      // Try current year first
      let date = new Date(currentYear, m - 1, d);
      date.setHours(0, 0, 0, 0);
      today.setHours(0, 0, 0, 0);
      
      // If the date is more than 30 days in the future, assume it's from the previous year
      // This handles year transitions (e.g., "12/26" in January should be Dec 26 of previous year)
      const daysDiff = (date.getTime() - today.getTime()) / (1000 * 60 * 60 * 24);
      if (daysDiff > 30) {
        date = new Date(currentYear - 1, m - 1, d);
        date.setHours(0, 0, 0, 0);
      }
      
      return { date: date, text: trimmed };
    }
    // Fallback Date parse
    const dt = new Date(trimmed);
    if (!isNaN(dt)) return { date: dt, text: trimmed };
    return { date: null, text: trimmed };
  }

  function classifyUcdBadge(date) {
    if (!date) return 'ucd-badge'; // neutral
    const today = new Date(); today.setHours(0, 0, 0, 0);
    const d = new Date(date); d.setHours(0, 0, 0, 0);
    if (d.getTime() < today.getTime()) return 'ucd-badge ucd-overdue';
    if (d.getTime() === today.getTime()) return 'ucd-badge ucd-today';
    return 'ucd-badge ucd-future';
  }

  function categoryFromSlot(slot) {
    const n = Number(slot);
    if (!Number.isFinite(n)) return 'unassigned';
    if (n >= 1 && n <= 36) return 'elitebooks';
    if (n >= 37 && n <= 56) return 'zbooks';
    if (n >= 57 && n <= 61) return 'toughbooks';
    if (n >= 62 && n <= 71) return 'repaired';
    if (n === 72) return 'desktops';
    if (n >= 100 && n <= 121) return 'phones';
    return 'unassigned';
  }

  function titleFromCategory(cat) {
    switch (cat) {
      case 'elitebooks': return 'Slots 1–36: Elitebooks';
      case 'zbooks': return 'Slots 37–56: ZBooks';
      case 'toughbooks': return 'Slots 57–61: Toughbooks';
      case 'repaired': return 'Slots 62–71: Repaired';
      case 'desktops': return 'Slot 72: Desktops';
      case 'phones': return 'Slots 100–121: Phones';
      default: return 'All';
    }
  }

  // ---------- Row factory ----------
  function addDeviceRow({ user, slot, ticket, ucd, configItem, type, incident = false, category, sys_id }) {
    const id = `row_${++state.idSeq}`;

    const tr = document.createElement('tr');
    tr.id = id;

    // Normalize & annotate
    const slotted = slot !== '' && slot !== null && slot !== undefined && String(slot).trim() !== '';
    const cat = category || (slotted ? categoryFromSlot(slot) : 'unassigned');
    const u = parseUcd(ucd);

    tr.dataset.type = (String(type || 'computer').toLowerCase() === 'phone') ? 'phone' : 'computer';
    tr.dataset.incident = incident ? 'true' : 'false';
    tr.dataset.category = cat;
    tr.dataset.slotted = slotted ? 'true' : 'false';
    tr.dataset.ticket = ticket || '';
    tr.dataset.slot = slotted ? String(slot) : '';

    // Cells
    // User
    const tdUser = document.createElement('td');
    tdUser.className = 'col-user';
    tdUser.textContent = user || '';
    tr.appendChild(tdUser);

    // Slot
    const tdSlot = document.createElement('td');
    tdSlot.textContent = slotted ? String(slot) : '';
    tr.appendChild(tdSlot);

    // Ticket
    const tdTicket = document.createElement('td');
    if (ticket) {
      // If your environment can link to tickets, replace '#' with your URL pattern.
      const a = document.createElement('a');
      a.href = '#';
      a.className = 'link';
      a.textContent = ticket;
      if (String(ticket).includes("INC")) {
        a.href = `https://srpnet.service-now.com/now/nav/ui/classic/params/target/incident.do?sys_id=${sys_id}&sysparm_stack=&sysparm_view=`;
      }
      else {
        a.href = `https://srpnet.service-now.com/now/nav/ui/classic/params/target/sc_task.do?sys_id=${sys_id}&sysparm_stack=&sysparm_view=`;
      }
      a.title = 'Open ticket';
      a.target = '_blank';
      a.rel = 'noopener noreferrer';
      tdTicket.appendChild(a);
    } else {
      tdTicket.innerHTML = '<span class="muted">—</span>';
    }
    tr.appendChild(tdTicket);

    // UCD
    const tdUcd = document.createElement('td');
    tdUcd.className = 'col-ucd';
    const badge = document.createElement('span');
    badge.className = classifyUcdBadge(u.date);
    badge.textContent = u.text || '';
    tdUcd.appendChild(badge);
    tr.appendChild(tdUcd);

    // Config Item
    const tdCfg = document.createElement('td');
    tdCfg.textContent = configItem || '';
    tr.appendChild(tdCfg);

    // Notify
    const tdNotify = document.createElement('td');
    if (slotted) {
      tdNotify.innerHTML = '<span class="muted">—</span>';
    } else {
      const btn = document.createElement('button');
      btn.className = 'notify';
      btn.textContent = 'Notify';
      btn.addEventListener('click', () => onNotify(tr));
      tdNotify.appendChild(btn);
    }
    tr.appendChild(tdNotify);

    el.rows.appendChild(tr);
    recount();
    applyFilters();
    return id;
  }

  function showPopup(content, onClose) {
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

    // Use requestAnimationFrame to ensure popup is rendered before calling onClose
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        if (onClose) onClose();
      });
    });

    document.getElementById('closePopup').addEventListener('click', () => {
      document.body.removeChild(modal);
    });
  }

  // Placeholder notify handler (unslotted only).
  // Replace body with your actual slotting+notification logic.

  function onNotify(tr) {
    const btn = tr.querySelector('.notify');
    btn.classList.add('loading'); // Start spinner
    btn.disabled = true; // Prevent multiple clicks

    const userEmail = initialData.email;
    const taskNumber = tr.dataset.ticket;
    const url = `${window.location.origin}/${taskNumber}/${userEmail}`;

    fetch(url)
      .then(res => res.json())
      .then(data => {
        // Check if slot is -1 (device doesn't require slotting, e.g., Mac)
        const isNoSlot = data.slotNumber === -1 || data.slotNumber === '-1' || data.slotNumber === null;

        if (isNoSlot) {
          // Device doesn't require slotting (e.g., Mac) - just send email notification
          // Don't update slot info, don't mark as slotted

          // Update UCD badge if UCD is provided
          if (data.UCD) {
            const badge = tr.children[3].querySelector('span');
            badge.className = classifyUcdBadge(new Date(data.UCD));
            badge.textContent = data.UCD;
          }

          // Show popup confirmation for email sent (no slotting)
          showPopup(`Customer: ${data.requestedFor}<br>Device: ${data.CI}<br>Email notification sent. Device does not require slotting.${data.UCD ? '<br>UCD: ' + data.UCD : ''}`, () => {
            // Stop loading animation after popup is shown
            btn.classList.remove('loading');
          });

          // Remove notify button since notification was sent
          tr.children[5].innerHTML = '<span class="muted">—</span>';
        } else {
          // Normal slotting flow - update row with slot info
          tr.dataset.slot = data.slotNumber;
          tr.dataset.slotted = 'true';
          tr.dataset.category = categoryFromSlot(data.slotNumber);

          tr.children[1].textContent = data.slotNumber;

          const badge = tr.children[3].querySelector('span');
          badge.className = classifyUcdBadge(new Date(data.UCD));
          badge.textContent = data.UCD;

          // Show popup confirmation
          showPopup(`Customer: ${data.requestedFor}<br>Device: ${data.CI}<br>Slot: ${data.slotNumber}<br>UCD: ${data.UCD}`, () => {
            // Stop loading animation after popup is shown
            btn.classList.remove('loading');
          });

          tr.children[5].innerHTML = '<span class="muted">—</span>';
        }

        recount();
        applyFilters();
      })
      .catch(err => {
        console.error('Notify failed:', err);
        btn.classList.remove('loading');
        btn.disabled = false; // Re-enable if error
      });
  }

  function suggestSlotForCategory(cat) {
    // Very simple suggester returning the *lowest* open slot in the category (if found).
    const ranges = {
      elitebooks: [1, 36], zbooks: [37, 56], toughbooks: [57, 61],
      repaired: [62, 71], desktops: [72, 72], phones: [100, 121]
    };
    if (!ranges[cat]) return null;

    const [start, end] = ranges[cat];
    const used = new Set(
      [...el.rows.querySelectorAll('tr[data-slotted="true"]')]
        .map(r => Number(r.dataset.slot))
        .filter(n => Number.isFinite(n))
    );
    for (let s = start; s <= end; s++) {
      if (!used.has(s)) return s;
    }
    return null; // no availability
  }

  // Programmatically slot a device row, update UI, and disable Notify
  function slotDevice(rowId, newSlot) {
    const tr = document.getElementById(rowId);
    if (!tr) return false;
    tr.dataset.slotted = 'true';
    tr.dataset.slot = String(newSlot);
    tr.dataset.category = categoryFromSlot(newSlot);

    // Update Slot cell (index 1)
    tr.children[1].textContent = String(newSlot);
    // Replace Notify cell with —
    const tdNotify = tr.children[5];
    tdNotify.innerHTML = '<span class="muted">—</span>';

    // Emit event for host script
    document.dispatchEvent(new CustomEvent('srp:slotted', {
      detail: {
        rowId, slot: newSlot, category: tr.dataset.category
      }
    }));

    recount();
    applyFilters();
    return true;
  }

  // ---------- Filtering ----------
  function applyFilters() {
    const rows = el.rows.querySelectorAll('tr');
    rows.forEach(tr => {
      const rowType = tr.dataset.type; // 'computer' | 'phone'
      const rowIncident = tr.dataset.incident === 'true';
      const rowCategory = tr.dataset.category;

      // Filter predicate
      let show = true;

      // Category filter
      if (state.category !== 'all') {
        show = show && (rowCategory === state.category);
      }

      // Type & incident filters
      if (state.filter === 'computer') {
        show = show && (rowType === 'computer');
      } else if (state.filter === 'phone') {
        show = show && (rowType === 'phone');
      } else if (state.filter === 'incident') {
        show = show && (rowType === 'computer') && rowIncident;
      }

      tr.style.display = show ? '' : 'none';
    });
  }

  function clearFilters() {
    state.filter = 'all'; state.category = 'all';
    [el.filterComputer, el.filterIncident, el.filterPhone].forEach(b => b.classList.remove('active'));
    [...el.categoryBar.querySelectorAll('.chip')].forEach(c => c.classList.remove('active'));
    applyFilters();
  }

  // ---------- Counters ----------
  function recount() {
    const all = el.rows.querySelectorAll('tr');
    const total = all.length;
    let slotted = 0;
    all.forEach(tr => { if (tr.dataset.slotted === 'true') slotted++; });
    const unslotted = total - slotted;

    el.total.textContent = String(total);
    el.kSlotted.textContent = String(slotted);
    el.kUnslotted.textContent = String(unslotted);
  }

  // Filter & category setters with persistence
  function setFilter(f) {
    state.filter = f;
    localStorage.setItem('filterPreference', f); // Save filter
    [el.filterComputer, el.filterIncident, el.filterPhone].forEach(b => b.classList.remove('active'));
    if (f === 'computer') el.filterComputer.classList.add('active');
    else if (f === 'incident') el.filterIncident.classList.add('active');
    else if (f === 'phone') el.filterPhone.classList.add('active');
    applyFilters();
  }

  function setCategory(cat) {
    state.category = cat;
    localStorage.setItem('categoryPreference', cat); // Save category
    [...el.categoryBar.querySelectorAll('.chip')].forEach(c => {
      c.classList.toggle('active', c.dataset.category === cat);
    });
    applyFilters();
  }

  // Wire UI
  el.filterComputer.addEventListener('click', () => setFilter(state.filter === 'computer' ? 'all' : 'computer'));
  el.filterIncident.addEventListener('click', () => setFilter(state.filter === 'incident' ? 'all' : 'incident'));
  el.filterPhone.addEventListener('click', () => setFilter(state.filter === 'phone' ? 'all' : 'phone'));
  el.clearFilters.addEventListener('click', clearFilters);
  el.categoryBar.addEventListener('click', (e) => {
    const chip = e.target.closest('.chip');
    if (!chip) return;
    const cat = chip.dataset.category;
    setCategory(chip.classList.contains('active') ? 'all' : cat);
  });

  // Manual refresh button to force a fresh pull from ServiceNow
  if (el.refresh) {
    el.refresh.addEventListener('click', () => {
      el.refresh.disabled = true;
      const originalText = el.refresh.textContent;
      el.refresh.textContent = 'Refreshing...';

      fetch(`${window.location.origin}/refresh-data`)
        .then(res => res.json())
        .then(json => {
          const rows = json.result || [];
          renderTable(rows);

          // If throttled, let the user know when they can refresh again
          if (json.throttled && typeof json.next_allowed_in === 'number') {
            const seconds = json.next_allowed_in;
            alert(`Please wait ${seconds} second${seconds === 1 ? '' : 's'} before refreshing again.`);
          }
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
    column: localStorage.getItem('sortColumn') || null,
    direction: localStorage.getItem('sortDirection') || 'asc'
  };

  function applySort(columnIndex, direction) {
    const rowsArray = Array.from(document.querySelectorAll('#deviceRows tr'));
    rowsArray.sort((a, b) => {
      const aText = a.children[columnIndex].textContent.trim().toLowerCase();
      const bText = b.children[columnIndex].textContent.trim().toLowerCase();

      // Numeric comparison if both are numbers
      const aNum = parseFloat(aText);
      const bNum = parseFloat(bText);
      if (!isNaN(aNum) && !isNaN(bNum)) {
        return direction === 'asc' ? aNum - bNum : bNum - aNum;
      }

      // String comparison
      return direction === 'asc' ? aText.localeCompare(bText) : bText.localeCompare(aText);
    });

    const tbody = document.getElementById('deviceRows');
    tbody.innerHTML = '';
    rowsArray.forEach(row => tbody.appendChild(row));
  }

  function updateIndicators() {
    document.querySelectorAll('thead th').forEach((th, i) => {
      th.textContent = th.textContent.replace(/ ▲| ▼/g, ''); // Remove old indicators
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

      // Save preference
      localStorage.setItem('sortColumn', index);
      localStorage.setItem('sortDirection', newDirection);

      applySort(index, newDirection);
      updateIndicators();
    });
  });

  // Initial indicator update
  updateIndicators();

  // Restore filter and category on load
  const savedFilter = localStorage.getItem('filterPreference');
  const savedCategory = localStorage.getItem('categoryPreference');
  if (savedFilter) setFilter(savedFilter);
  if (savedCategory) setCategory(savedCategory);

  function renderTable(data) {
    // Clear all current rows
    const tableBody = document.getElementById('deviceRows');
    tableBody.innerHTML = "";

    if (!Array.isArray(data)) {
      console.error("Expected array for data, got:", data);
      return;
    }

    data.forEach(item => {
      let type = "computer";
      let incident = false;
      if (String(item.number).includes("INC")) {
        type = "incident";
        incident = true;
      }
      else if (String(item.short_description).includes("Ready for Pickup")) {
        type = "phone";
      }
      addDeviceRow({
        user: item.requested_for || '', // maps to 'user'
        slot: item.slot || '',          // if you have slot info, otherwise ''
        ticket: item.number || '',      // maps to 'ticket'
        ucd: item.ucd || '',       // maps to 'ucd'
        configItem: item.cmdb_ci || '', // maps to 'configItem'
        type: type,               // or infer from your data if available
        incident: incident,                // or infer from your data if available
        category: '',                    // or infer from your data if available
        sys_id: item.sys_id || '' // sys_id for task to set link for task to serviceNow
      });
    });

    if (sortState.column !== null) {
      applySort(parseInt(sortState.column), sortState.direction);
      updateIndicators();
    }

  }

  setInterval(() => {
    fetch(`${window.location.origin}/get-data`)
      .then(res => res.json())
      .then(json => {
        if (json.result) {
          renderTable(json.result);
        } else {
          renderTable([]); // fallback to empty
        }
      });
  }, 5000);

  renderTable(initialData.rows.result);

  if (sortState.column !== null) {
    applySort(parseInt(sortState.column), sortState.direction);
    updateIndicators();
  }

  // Expose public API
  window.SRPSlotting = {
    addDeviceRow,
    clearFilters,
    filters: { set: setFilter },
    categories: { set: setCategory },
    slotDevice
  };
})();


