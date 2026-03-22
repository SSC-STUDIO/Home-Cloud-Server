document.addEventListener("DOMContentLoaded", () => {
    const chartElement = document.getElementById("resourceChart");
    const payloadElement = document.getElementById("resourceChartData");

    if (!chartElement || !payloadElement || !window.Chart) {
        return;
    }

    const payload = JSON.parse(payloadElement.textContent);
    const context = chartElement.getContext("2d");

    new Chart(context, {
        type: "line",
        data: {
            labels: payload.labels,
            datasets: [
                {
                    label: "CPU Usage (%)",
                    data: payload.cpu,
                    borderColor: "#e11d48",
                    backgroundColor: "rgba(225, 29, 72, 0.12)",
                    tension: 0.35,
                    fill: true,
                },
                {
                    label: "Memory Usage (%)",
                    data: payload.memory,
                    borderColor: "#2563eb",
                    backgroundColor: "rgba(37, 99, 235, 0.1)",
                    tension: 0.35,
                    fill: true,
                },
                {
                    label: "Disk Usage (%)",
                    data: payload.disk,
                    borderColor: "#d97706",
                    backgroundColor: "rgba(217, 119, 6, 0.1)",
                    tension: 0.35,
                    fill: true,
                },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: "top",
                },
                tooltip: {
                    mode: "index",
                    intersect: false,
                },
            },
            interaction: {
                mode: "nearest",
                axis: "x",
                intersect: false,
            },
            scales: {
                y: {
                    min: 0,
                    max: 100,
                    ticks: {
                        callback: (value) => `${value}%`,
                    },
                },
            },
        },
    });
});
