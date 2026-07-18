let dailyChart, monthlyChart;

document.addEventListener('DOMContentLoaded', () => {
    loadFilters();
    
    document.getElementById('filterBatch').addEventListener('change', onFilterChange);
    document.getElementById('filterYear').addEventListener('change', onFilterChange);
    document.getElementById('filterDept').addEventListener('change', onFilterChange);
    
    document.getElementById('resetBtn').addEventListener('click', () => {
        document.getElementById('filterBatch').value = "";
        document.getElementById('filterYear').value = "";
        document.getElementById('filterDept').value = "";
        onFilterChange();
    });

    // Initial load
    fetchDashboardData();
});

async function loadFilters() {
    try {
        const res = await fetch('/api/advanced-analytics/filters');
        const data = await res.json();
        
        if (data.success) {
            populateSelect('filterBatch', data.data.batches);
            populateSelect('filterYear', data.data.years);
            populateSelect('filterDept', data.data.departments);
        }
    } catch (err) {
        console.error("Error loading filters", err);
    }
}

function populateSelect(id, items) {
    const select = document.getElementById(id);
    // keep first option
    const first = select.options[0];
    select.innerHTML = '';
    select.appendChild(first);
    
    items.forEach(item => {
        const opt = document.createElement('option');
        opt.value = item;
        opt.textContent = item;
        select.appendChild(opt);
    });
}

function onFilterChange() {
    const batch = document.getElementById('filterBatch').value;
    const yearSelect = document.getElementById('filterYear');
    const deptSelect = document.getElementById('filterDept');
    
    yearSelect.disabled = !batch;
    if (!batch) yearSelect.value = "";
    
    deptSelect.disabled = !yearSelect.value;
    if (!yearSelect.value) deptSelect.value = "";
    
    updateExportLink();
    fetchDashboardData();
}

function updateExportLink() {
    const batch = document.getElementById('filterBatch').value;
    const year = document.getElementById('filterYear').value;
    const dept = document.getElementById('filterDept').value;
    
    let url = '/api/advanced-analytics/export?';
    if (batch) url += `batch=${batch}&`;
    if (year) url += `year=${year}&`;
    if (dept) url += `department=${dept}`;
    
    document.getElementById('exportBtn').href = url;
}

async function fetchDashboardData() {
    const batch = document.getElementById('filterBatch').value;
    const year = document.getElementById('filterYear').value;
    const dept = document.getElementById('filterDept').value;
    
    document.getElementById('loadingIndicator').classList.remove('d-none');
    document.getElementById('dashboardContent').classList.add('opacity-50');
    
    try {
        let url = '/api/advanced-analytics/dashboard?';
        if (batch) url += `batch=${batch}&`;
        if (year) url += `year=${year}&`;
        if (dept) url += `department=${dept}`;
        
        const res = await fetch(url);
        const data = await res.json();
        
        if (data.success) {
            renderDashboard(data.data);
        } else {
            console.error("Error from API:", data.message);
        }
    } catch (err) {
        console.error("Error fetching dashboard data", err);
    } finally {
        document.getElementById('loadingIndicator').classList.add('d-none');
        document.getElementById('dashboardContent').classList.remove('opacity-50');
    }
}

function renderDashboard(data) {
    // KPIs
    document.getElementById('kpiTotal').textContent = data.kpis.total_students;
    document.getElementById('kpiAttPct').textContent = data.kpis.overall_attendance_pct + '%';
    document.getElementById('kpiPresent').textContent = data.kpis.present_today;
    document.getElementById('kpiAbsent').textContent = data.kpis.absent_today;
    
    // Insights & Predictions
    renderList('insightsList', data.insights);
    renderList('predictionsList', data.predictions);
    
    // Tables
    renderClassTable(data.class_data);
    renderRiskTable(data.risk.students);
    
    // Charts
    renderCharts(data.trends);
}

function renderList(id, items) {
    const ul = document.getElementById(id);
    ul.innerHTML = '';
    if (items.length === 0) {
        ul.innerHTML = '<li>No significant data available.</li>';
        return;
    }
    items.forEach(i => {
        const li = document.createElement('li');
        li.textContent = i;
        li.className = "mb-2";
        ul.appendChild(li);
    });
}

function renderClassTable(classes) {
    const tbody = document.getElementById('classTableBody');
    tbody.innerHTML = '';
    classes.forEach(c => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${c.label}</td>
            <td>${c.total}</td>
            <td>${c.present_today}</td>
            <td>
                <div class="progress bg-dark" style="height: 15px;">
                  <div class="progress-bar ${c.attendance_pct > 75 ? 'bg-success' : 'bg-danger'}" 
                       role="progressbar" style="width: ${c.attendance_pct}%">
                       ${c.attendance_pct}%
                  </div>
                </div>
            </td>
        `;
        tbody.appendChild(tr);
    });
}

function renderRiskTable(students) {
    const tbody = document.getElementById('riskTableBody');
    tbody.innerHTML = '';
    students.forEach(s => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${s.name}</td>
            <td>${s.id}</td>
            <td>${s.pct}%</td>
            <td><span class="risk-${s.risk}">${s.risk.toUpperCase()}</span></td>
        `;
        tbody.appendChild(tr);
    });
}

function renderCharts(trends) {
    Chart.defaults.color = '#adb5bd';
    Chart.defaults.scale.grid.color = 'rgba(255, 255, 255, 0.1)';
    
    if (dailyChart) dailyChart.destroy();
    if (monthlyChart) monthlyChart.destroy();
    
    const ctxDaily = document.getElementById('dailyTrendChart').getContext('2d');
    dailyChart = new Chart(ctxDaily, {
        type: 'bar',
        data: {
            labels: trends.daily.map(d => d.date),
            datasets: [
                { label: 'Present', data: trends.daily.map(d => d.present), backgroundColor: '#198754' },
                { label: 'Absent', data: trends.daily.map(d => d.absent), backgroundColor: '#dc3545' }
            ]
        },
        options: {
            responsive: true, maintainAspectRatio: false,
            scales: { x: { stacked: true }, y: { stacked: true } }
        }
    });
    
    const ctxMonthly = document.getElementById('monthlyTrendChart').getContext('2d');
    monthlyChart = new Chart(ctxMonthly, {
        type: 'line',
        data: {
            labels: trends.monthly.map(d => d.month),
            datasets: [{
                label: 'Present Count',
                data: trends.monthly.map(d => d.present),
                borderColor: '#0dcaf0',
                fill: false,
                tension: 0.1
            }]
        },
        options: {
            responsive: true, maintainAspectRatio: false
        }
    });
}
