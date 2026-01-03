/**
 * EasyPay Dashboard - Chart.js Integration
 */
const EasyPayDashboard = (function() {
    'use strict';

    let config = {
        apiUrl: '',
        initialRange: '7d',
        chartData: null,
        customStartDate: null,
        customEndDate: null,
        today: null,
        exportUrl: ''
    };

    let charts = {
        revenue: null,
        status: null,
        method: null,
        comparison: null
    };

    let calendarState = {
        currentMonth: new Date(),
        selectingStart: true,
        startDate: null,
        endDate: null
    };

    const CHART_COLORS = {
        primary: '#417690',
        primaryLight: 'rgba(65, 118, 144, 0.1)',
        success: '#4CAF50',
        warning: '#FFA500',
        danger: '#F44336',
        info: '#2196F3',
        gray: '#9E9E9E',
        previousPeriod: 'rgba(156, 163, 175, 0.7)'
    };

    function formatCurrency(value) {
        return '₩' + value.toLocaleString('ko-KR');
    }

    function formatDate(dateStr) {
        const date = new Date(dateStr);
        return (date.getMonth() + 1) + '/' + date.getDate();
    }

    function createRevenueChart(data) {
        const ctx = document.getElementById('revenueTrendChart');
        if (!ctx) return;

        if (charts.revenue) {
            charts.revenue.destroy();
        }

        const labels = data.map(d => formatDate(d.date));
        const revenues = data.map(d => d.revenue);
        const counts = data.map(d => d.count);

        const dates = data.map(d => new Date(d.date));
        const backgroundColors = dates.map(d => {
            const day = d.getDay();
            if (day === 0) return 'rgba(239, 68, 68, 0.15)';
            if (day === 6) return 'rgba(59, 130, 246, 0.15)';
            return CHART_COLORS.primaryLight;
        });

        charts.revenue = new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: '매출',
                        data: revenues,
                        borderColor: CHART_COLORS.primary,
                        backgroundColor: backgroundColors,
                        fill: true,
                        tension: 0.3,
                        yAxisID: 'y',
                        segment: {
                            borderColor: ctx => {
                                const idx = ctx.p0DataIndex;
                                const day = dates[idx].getDay();
                                if (day === 0) return '#EF4444';
                                if (day === 6) return '#3B82F6';
                                return CHART_COLORS.primary;
                            }
                        }
                    },
                    {
                        label: '건수',
                        data: counts,
                        borderColor: CHART_COLORS.success,
                        backgroundColor: 'transparent',
                        borderDash: [5, 5],
                        tension: 0.3,
                        yAxisID: 'y1'
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: {
                    mode: 'index',
                    intersect: false
                },
                plugins: {
                    legend: {
                        position: 'top',
                        align: 'end'
                    },
                    tooltip: {
                        callbacks: {
                            title: function(context) {
                                const idx = context[0].dataIndex;
                                const date = dates[idx];
                                const days = ['일', '월', '화', '수', '목', '금', '토'];
                                const day = days[date.getDay()];
                                const isWeekend = date.getDay() === 0 || date.getDay() === 6;
                                return `${date.getMonth() + 1}/${date.getDate()} (${day})${isWeekend ? ' 🔴' : ''}`;
                            },
                            label: function(context) {
                                if (context.datasetIndex === 0) {
                                    return '매출: ' + formatCurrency(context.raw);
                                }
                                return '건수: ' + context.raw + '건';
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        grid: {
                            display: false
                        }
                    },
                    y: {
                        type: 'linear',
                        display: true,
                        position: 'left',
                        ticks: {
                            callback: function(value) {
                                if (value >= 1000000) {
                                    return (value / 1000000).toFixed(1) + 'M';
                                }
                                if (value >= 1000) {
                                    return (value / 1000).toFixed(0) + 'K';
                                }
                                return value;
                            }
                        },
                        grid: {
                            color: 'rgba(0, 0, 0, 0.05)'
                        }
                    },
                    y1: {
                        type: 'linear',
                        display: true,
                        position: 'right',
                        grid: {
                            drawOnChartArea: false
                        },
                        ticks: {
                            stepSize: 1
                        }
                    }
                }
            }
        });
    }

    function createComparisonChart(data) {
        const ctx = document.getElementById('comparisonChart');
        if (!ctx || !data || data.length === 0) return;

        if (charts.comparison) {
            charts.comparison.destroy();
        }

        const labels = data.map(d => d.label);
        const currentValues = data.map(d => d.current);
        const previousValues = data.map(d => d.previous);

        charts.comparison = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: '현재 기간',
                        data: currentValues,
                        backgroundColor: CHART_COLORS.primary,
                        borderRadius: 4
                    },
                    {
                        label: '이전 기간',
                        data: previousValues,
                        backgroundColor: CHART_COLORS.previousPeriod,
                        borderRadius: 4
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'top',
                        align: 'end'
                    },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                const label = context.dataset.label;
                                const value = context.raw;
                                const dataIndex = context.dataIndex;
                                if (dataIndex === 0) {
                                    return label + ': ' + formatCurrency(value);
                                }
                                if (dataIndex === 2) {
                                    return label + ': ' + formatCurrency(value);
                                }
                                return label + ': ' + value.toLocaleString() + '건';
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        grid: {
                            display: false
                        }
                    },
                    y: {
                        beginAtZero: true,
                        grid: {
                            color: 'rgba(0, 0, 0, 0.05)'
                        }
                    }
                }
            }
        });
    }

    function createStatusChart(data) {
        const ctx = document.getElementById('statusChart');
        if (!ctx) return;

        if (charts.status) {
            charts.status.destroy();
        }

        const labels = data.map(d => d.label);
        const values = data.map(d => d.count);
        const colors = data.map(d => d.color);

        charts.status = new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: labels,
                datasets: [{
                    data: values,
                    backgroundColor: colors,
                    borderWidth: 2,
                    borderColor: '#fff'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'right'
                    },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                const total = context.dataset.data.reduce((a, b) => a + b, 0);
                                const percentage = ((context.raw / total) * 100).toFixed(1);
                                return context.label + ': ' + context.raw + '건 (' + percentage + '%)';
                            }
                        }
                    }
                }
            }
        });
    }

    function createMethodChart(data) {
        const ctx = document.getElementById('methodChart');
        if (!ctx) return;

        if (charts.method) {
            charts.method.destroy();
        }

        const labels = data.map(d => d.label);
        const revenues = data.map(d => d.revenue);
        const counts = data.map(d => d.count);

        const colors = [
            CHART_COLORS.primary,
            CHART_COLORS.success,
            CHART_COLORS.info,
            CHART_COLORS.warning
        ];

        charts.method = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [{
                    label: '매출',
                    data: revenues,
                    backgroundColor: colors.slice(0, labels.length),
                    borderRadius: 4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                indexAxis: 'y',
                plugins: {
                    legend: {
                        display: false
                    },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                const count = counts[context.dataIndex];
                                return formatCurrency(context.raw) + ' (' + count + '건)';
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        ticks: {
                            callback: function(value) {
                                if (value >= 1000000) {
                                    return (value / 1000000).toFixed(1) + 'M';
                                }
                                if (value >= 1000) {
                                    return (value / 1000).toFixed(0) + 'K';
                                }
                                return value;
                            }
                        },
                        grid: {
                            color: 'rgba(0, 0, 0, 0.05)'
                        }
                    },
                    y: {
                        grid: {
                            display: false
                        }
                    }
                }
            }
        });
    }

    function updateSummaryCards(summary) {
        const fields = ['total_revenue', 'transaction_count', 'average_value', 'refund_count'];
        const ids = ['totalRevenue', 'transactionCount', 'averageValue', 'refundCount'];

        fields.forEach((field, index) => {
            const element = document.getElementById(ids[index]);
            if (element && summary[field]) {
                element.textContent = summary[field].formatted;
            }
        });
    }

    function showLoading(show) {
        const dashboard = document.getElementById('easypay-dashboard');
        if (!dashboard) return;

        let overlay = dashboard.querySelector('.loading-overlay');

        if (show) {
            if (!overlay) {
                overlay = document.createElement('div');
                overlay.className = 'loading-overlay';
                overlay.innerHTML = '<div class="loading-spinner"></div>';
                dashboard.style.position = 'relative';
                dashboard.appendChild(overlay);
            }
            overlay.style.display = 'flex';
        } else if (overlay) {
            overlay.style.display = 'none';
        }
    }

    function loadData(dateRange, startDate, endDate) {
        showLoading(true);

        let url = config.apiUrl.replace(/range=[^&]+/, 'range=' + dateRange);
        if (dateRange === 'custom' && startDate && endDate) {
            url = 'api/?range=custom&start_date=' + startDate + '&end_date=' + endDate;
        }

        fetch(url)
            .then(response => response.json())
            .then(data => {
                updateSummaryCards(data.summary);
                createRevenueChart(data.charts.daily_trend);
                createComparisonChart(data.comparison);
                createStatusChart(data.charts.by_status);
                createMethodChart(data.charts.by_method);
                updateComparisonPeriodInfo(data.meta);
                showLoading(false);
            })
            .catch(error => {
                console.error('Dashboard data load error:', error);
                showLoading(false);
            });
    }

    function updateComparisonPeriodInfo(meta) {
        const info = document.querySelector('.comparison-period-info');
        if (info && meta) {
            info.textContent = `현재: ${meta.start_date} ~ ${meta.end_date} | 이전: ${meta.prev_start_date} ~ ${meta.prev_end_date}`;
        }
    }

    function renderCalendar() {
        const calendarDays = document.getElementById('calendarDays');
        const calendarMonth = document.getElementById('calendarMonth');
        if (!calendarDays || !calendarMonth) return;

        const year = calendarState.currentMonth.getFullYear();
        const month = calendarState.currentMonth.getMonth();

        calendarMonth.textContent = `${year}년 ${month + 1}월`;

        const firstDay = new Date(year, month, 1);
        const lastDay = new Date(year, month + 1, 0);
        const today = new Date(config.today);

        let dayOfWeek = firstDay.getDay();
        dayOfWeek = dayOfWeek === 0 ? 6 : dayOfWeek - 1;

        let html = '';

        for (let i = 0; i < dayOfWeek; i++) {
            html += '<span class="calendar-day empty"></span>';
        }

        for (let day = 1; day <= lastDay.getDate(); day++) {
            const date = new Date(year, month, day);
            const dateStr = date.toISOString().split('T')[0];
            const dow = date.getDay();
            const isWeekend = dow === 0 || dow === 6;
            const isSunday = dow === 0;
            const isSaturday = dow === 6;
            const isFuture = date > today;
            const isSelected = isDateInRange(date);
            const isStart = calendarState.startDate && dateStr === calendarState.startDate;
            const isEnd = calendarState.endDate && dateStr === calendarState.endDate;

            let classes = ['calendar-day'];
            if (isWeekend) classes.push('weekend');
            if (isSunday) classes.push('sunday');
            if (isSaturday) classes.push('saturday');
            if (isFuture) classes.push('future');
            if (isSelected) classes.push('selected');
            if (isStart) classes.push('range-start');
            if (isEnd) classes.push('range-end');

            html += `<span class="${classes.join(' ')}" data-date="${dateStr}"${isFuture ? ' disabled' : ''}>${day}</span>`;
        }

        calendarDays.innerHTML = html;

        calendarDays.querySelectorAll('.calendar-day:not(.empty):not(.future)').forEach(el => {
            el.addEventListener('click', function() {
                handleDateClick(this.dataset.date);
            });
        });
    }

    function isDateInRange(date) {
        if (!calendarState.startDate || !calendarState.endDate) return false;
        const start = new Date(calendarState.startDate);
        const end = new Date(calendarState.endDate);
        return date >= start && date <= end;
    }

    function handleDateClick(dateStr) {
        if (calendarState.selectingStart) {
            calendarState.startDate = dateStr;
            calendarState.endDate = null;
            calendarState.selectingStart = false;
            document.getElementById('startDate').value = dateStr;
            document.getElementById('endDate').value = '';
        } else {
            if (dateStr < calendarState.startDate) {
                calendarState.endDate = calendarState.startDate;
                calendarState.startDate = dateStr;
            } else {
                calendarState.endDate = dateStr;
            }
            calendarState.selectingStart = true;
            document.getElementById('startDate').value = calendarState.startDate;
            document.getElementById('endDate').value = calendarState.endDate;
        }
        renderCalendar();
    }

    function bindDateRangeButtons() {
        const buttons = document.querySelectorAll('.date-range-selector button');
        const customPicker = document.getElementById('customDatePicker');

        buttons.forEach(button => {
            button.addEventListener('click', function() {
                const range = this.dataset.range;

                buttons.forEach(b => b.classList.remove('active'));
                this.classList.add('active');

                if (range === 'custom') {
                    if (customPicker) customPicker.style.display = 'block';
                    renderCalendar();
                } else {
                    if (customPicker) customPicker.style.display = 'none';
                    const newUrl = window.location.pathname + '?range=' + range;
                    window.history.pushState({}, '', newUrl);
                    loadData(range);
                }
            });
        });
    }

    function bindCustomDatePicker() {
        const applyBtn = document.getElementById('applyDateRange');
        const exportBtn = document.getElementById('exportCsv');
        const prevMonth = document.getElementById('prevMonth');
        const nextMonth = document.getElementById('nextMonth');
        const startInput = document.getElementById('startDate');
        const endInput = document.getElementById('endDate');

        if (applyBtn) {
            applyBtn.addEventListener('click', function() {
                const startDate = startInput.value;
                const endDate = endInput.value;
                if (startDate && endDate) {
                    const newUrl = window.location.pathname + '?range=custom&start_date=' + startDate + '&end_date=' + endDate;
                    window.history.pushState({}, '', newUrl);
                    loadData('custom', startDate, endDate);
                }
            });
        }

        if (exportBtn) {
            exportBtn.addEventListener('click', function() {
                const range = document.querySelector('.date-range-selector button.active')?.dataset.range || '7d';
                let url = config.exportUrl + '?range=' + range;
                if (range === 'custom') {
                    const startDate = startInput.value;
                    const endDate = endInput.value;
                    if (startDate && endDate) {
                        url += '&start_date=' + startDate + '&end_date=' + endDate;
                    }
                }
                window.location.href = url;
            });
        }

        if (prevMonth) {
            prevMonth.addEventListener('click', function() {
                calendarState.currentMonth.setMonth(calendarState.currentMonth.getMonth() - 1);
                renderCalendar();
            });
        }

        if (nextMonth) {
            nextMonth.addEventListener('click', function() {
                calendarState.currentMonth.setMonth(calendarState.currentMonth.getMonth() + 1);
                renderCalendar();
            });
        }

        if (startInput) {
            startInput.addEventListener('change', function() {
                calendarState.startDate = this.value;
                calendarState.selectingStart = false;
                renderCalendar();
            });
        }

        if (endInput) {
            endInput.addEventListener('change', function() {
                calendarState.endDate = this.value;
                calendarState.selectingStart = true;
                renderCalendar();
            });
        }
    }

    function init(options) {
        config = Object.assign(config, options);

        if (config.customStartDate) {
            calendarState.startDate = config.customStartDate;
        }
        if (config.customEndDate) {
            calendarState.endDate = config.customEndDate;
        }

        if (config.chartData) {
            createRevenueChart(config.chartData.charts.daily_trend);
            createComparisonChart(config.chartData.comparison);
            createStatusChart(config.chartData.charts.by_status);
            createMethodChart(config.chartData.charts.by_method);
        }

        bindDateRangeButtons();
        bindCustomDatePicker();

        if (config.initialRange === 'custom') {
            renderCalendar();
        }
    }

    return {
        init: init,
        loadData: loadData
    };
})();
