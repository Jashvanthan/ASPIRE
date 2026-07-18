let trendChart, deptChart, classChart;
let advancedDataCache = null;

let currentYear = null;
let currentDepartment = null;

document.addEventListener('DOMContentLoaded', () => {
    fetchDashboardStats();
    fetchAdvancedAnalytics();
    
    document.getElementById('trendSelect').addEventListener('change', (e) => {
        if (advancedDataCache) {
            updateTrendChart(advancedDataCache.trends[e.target.value]);
        }
    });

    const resetBtn = document.getElementById('resetFiltersBtn');
    if (resetBtn) {
        resetBtn.addEventListener('click', () => {
            currentYear = null;
            currentDepartment = null;
            fetchAdvancedAnalytics();
        });
    }
});

function updateBreadcrumbs() {
    const breadcrumbs = document.getElementById('filterBreadcrumbs');
    const activeText = document.getElementById('activeFilters');
    
    if (!currentYear && !currentDepartment) {
        breadcrumbs.classList.add('d-none');
        return;
    }
    
    breadcrumbs.classList.remove('d-none');
    
    let text = "Viewing: All Data";
    if (currentYear && currentDepartment) {
        text = `Viewing: Year ${currentYear} > ${currentDepartment}`;
    } else if (currentYear) {
        text = `Viewing: Year ${currentYear}`;
    } else if (currentDepartment) {
        text = `Viewing: ${currentDepartment}`;
    }
    activeText.textContent = text;
}

async function fetchDashboardStats() {
    try {
        const res = await fetch('/api/analytics/dashboard');
        const data = await res.json();
        
        if (data.success) {
            document.getElementById('statTotal').textContent = data.data.total_students;
            document.getElementById('statPresent').textContent = data.data.present_today;
            document.getElementById('statPct').textContent = data.data.attendance_percentage + '%';
            document.getElementById('statLate').textContent = data.data.late_arrivals;
        }
    } catch (err) {
        console.error("Failed to fetch dashboard stats", err);
    }
}

async function fetchAdvancedAnalytics() {
    try {
        let url = '/api/analytics/advanced?';
        if (currentYear) url += `year=${currentYear}&`;
        if (currentDepartment) url += `department=${currentDepartment}`;
        
        const res = await fetch(url);
        const data = await res.json();
        
        if (data.success) {
            advancedDataCache = data.data;
            updateBreadcrumbs();
            
            if (!trendChart) {
                initCharts(advancedDataCache);
            } else {
                updateAllCharts(advancedDataCache);
            }
        }
    } catch (err) {
        console.error("Failed to fetch advanced analytics", err);
    }
}

function initCharts(data) {
    Chart.defaults.color = '#adb5bd';
    Chart.defaults.scale.grid.color = 'rgba(255, 255, 255, 0.1)';

    const commonOptions = {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { 
            legend: { 
                position: 'bottom',
                labels: { color: '#adb5bd' }
            } 
        },
        scales: {
            x: { stacked: true },
            y: { stacked: true }
        }
    };

    // Trend Chart (Bar instead of Line to support stacked present/absent)
    const ctxTrend = document.getElementById('trendChart').getContext('2d');
    const defaultTrend = data.trends.day;
    
    trendChart = new Chart(ctxTrend, {
        type: 'bar',
        data: {
            labels: defaultTrend.map(d => d.label),
            datasets: [
                {
                    label: 'Present',
                    data: defaultTrend.map(d => d.present),
                    backgroundColor: '#198754', // success green
                },
                {
                    label: 'Absent',
                    data: defaultTrend.map(d => d.absent),
                    backgroundColor: '#dc3545', // danger red
                }
            ]
        },
        options: {
            ...commonOptions,
            onClick: (e, elements) => {
                if (elements.length > 0 && currentYear === null) {
                    const idx = elements[0].index;
                    const label = trendChart.data.labels[idx];
                    // If it's a year chart, we can drill down!
                    const trendType = document.getElementById('trendSelect').value;
                    if (trendType === 'year') {
                        currentYear = label;
                        fetchAdvancedAnalytics();
                    }
                }
            }
        }
    });

    // Department Chart
    const ctxDept = document.getElementById('deptChart').getContext('2d');
    deptChart = new Chart(ctxDept, {
        type: 'bar',
        data: {
            labels: data.department.map(d => d.label),
            datasets: [
                {
                    label: 'Present',
                    data: data.department.map(d => d.present),
                    backgroundColor: '#0d6efd',
                },
                {
                    label: 'Absent',
                    data: data.department.map(d => d.absent),
                    backgroundColor: '#dc3545',
                }
            ]
        },
        options: {
            ...commonOptions,
            onClick: (e, elements) => {
                if (elements.length > 0) {
                    const idx = elements[0].index;
                    currentDepartment = deptChart.data.labels[idx];
                    fetchAdvancedAnalytics();
                }
            }
        }
    });

    // Class Chart
    const ctxClass = document.getElementById('classChart').getContext('2d');
    classChart = new Chart(ctxClass, {
        type: 'bar',
        data: {
            labels: data.class_data.map(d => d.label),
            datasets: [
                {
                    label: 'Present',
                    data: data.class_data.map(d => d.present),
                    backgroundColor: '#0dcaf0',
                },
                {
                    label: 'Absent',
                    data: data.class_data.map(d => d.absent),
                    backgroundColor: '#dc3545',
                }
            ]
        },
        options: commonOptions
    });
}

function updateAllCharts(data) {
    const trendType = document.getElementById('trendSelect').value;
    updateTrendChart(data.trends[trendType]);
    
    deptChart.data.labels = data.department.map(d => d.label);
    deptChart.data.datasets[0].data = data.department.map(d => d.present);
    deptChart.data.datasets[1].data = data.department.map(d => d.absent);
    deptChart.update();
    
    classChart.data.labels = data.class_data.map(d => d.label);
    classChart.data.datasets[0].data = data.class_data.map(d => d.present);
    classChart.data.datasets[1].data = data.class_data.map(d => d.absent);
    classChart.update();
}

function updateTrendChart(trendData) {
    trendChart.data.labels = trendData.map(d => d.label);
    trendChart.data.datasets[0].data = trendData.map(d => d.present);
    trendChart.data.datasets[1].data = trendData.map(d => d.absent);
    trendChart.update();
}
