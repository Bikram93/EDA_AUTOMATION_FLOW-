
// ============================================================================
// EDA Flow Automation - Frontend Orchestrator & Cytoscape Graph Controller
// ============================================================================

document.addEventListener("DOMContentLoaded", () => {
    initHealthPolling();
    initCytoscapeGraph();
    initLiveLogViewer();
});

// 1. Real-time Telemetry Poller (DRMS CPU, RAM, Slots)
function initHealthPolling() {
    const cpuEl = document.getElementById("metric-cpu");
    const memEl = document.getElementById("metric-mem");
    const slotEl = document.getElementById("metric-slots");

    if (!cpuEl && !memEl) return;

    setInterval(async () => {
        try {
            const resp = await fetch("/api/health");
            if (!resp.ok) return;
            const data = await resp.json();

            if (cpuEl) cpuEl.innerText = `${data.cpu_utilization}%`;
            if (memEl) memEl.innerText = `${data.memory_utilization}%`;
            if (slotEl) slotEl.innerText = `${data.active_jobs} / ${data.max_jobs}`;
        } catch (err) {
            console.warn("Telemetry fetch error:", err);
        }
    }, 3000);
}

// 2. Interactive Cytoscape.js DAG Visualization
function initCytoscapeGraph() {
    const cyContainer = document.getElementById("cy");
    if (!cyContainer) return;

    const pipelineId = cyContainer.getAttribute("data-pipeline-id");
    if (!pipelineId) return;

    // Status to Color Mapping
    const statusColors = {
        PENDING: "#64748b",
        RUNNING: "#3b82f6",
        COMPLETED: "#10b981",
        FAILED: "#ef4444",
        SKIPPED: "#f59e0b"
    };

    fetch(`/api/pipeline/${pipelineId}/dag`)
        .then(res => res.json())
        .then(data => {
            if (typeof cytoscape === "undefined") {
                console.error("Cytoscape.js not loaded.");
                return;
            }

            const cy = cytoscape({
                container: cyContainer,
                elements: data,
                style: [
                    {
                        selector: "node",
                        style: {
                            "label": "data(name)",
                            "color": "#f8fafc",
                            "font-size": "12px",
                            "font-weight": "600",
                            "text-valign": "center",
                            "text-halign": "center",
                            "background-color": ele => statusColors[ele.data("status")] || "#64748b",
                            "width": "160px",
                            "height": "48px",
                            "shape": "round-rectangle",
                            "border-width": 2,
                            "border-color": "#334155"
                        }
                    },
                    {
                        selector: "edge",
                        style: {
                            "width": 3,
                            "line-color": "#475569",
                            "target-arrow-color": "#475569",
                            "target-arrow-shape": "triangle",
                            "curve-style": "bezier",
                            "arrow-scale": 1.2
                        }
                    },
                    {
                        selector: "node:selected",
                        style: {
                            "border-color": "#38bdf8",
                            "border-width": 4
                        }
                    }
                ],
                layout: {
                    name: "breadthfirst",
                    directed: true,
                    spacingFactor: 1.3,
                    padding: 40
                }
            });

            // Click node to view job log details
            cy.on("tap", "node", evt => {
                const taskId = evt.target.id();
                window.location.href = `/job/${taskId}`;
            });

            // Live status polling to update node colors
            setInterval(async () => {
                try {
                    const statusRes = await fetch(`/api/pipeline/${pipelineId}/status`);
                    if (!statusRes.ok) return;
                    const statusData = await statusRes.json();

                    statusData.tasks.forEach(t => {
                        const node = cy.$(`#${t.id}`);
                        if (node.length) {
                            node.data("status", t.status);
                            node.style("background-color", statusColors[t.status] || "#64748b");
                        }
                    });
                } catch (e) {
                    console.warn("DAG status polling error:", e);
                }
            }, 2500);
        })
        .catch(err => console.error("Failed to load DAG:", err));
}

// 3. Live Log Poller for Job Detail View
function initLiveLogViewer() {
    const logBox = document.getElementById("live-logs");
    if (!logBox) return;

    const taskId = logBox.getAttribute("data-task-id");
    const taskStatus = logBox.getAttribute("data-task-status");

    // Only poll continuously if stage is pending or currently running
    if (taskStatus === "COMPLETED" || taskStatus === "FAILED" || taskStatus === "SKIPPED") {
        logBox.scrollTop = logBox.scrollHeight;
        return;
    }

    const pollLogs = async () => {
        try {
            const resp = await fetch(`/api/job/${taskId}/logs`);
            if (resp.ok) {
                const data = await resp.json();
                if (data.logs) {
                    logBox.textContent = data.logs;
                    logBox.scrollTop = logBox.scrollHeight;
                }
            }
        } catch (e) {
            console.warn("Log polling error:", e);
        }
    };

    setInterval(pollLogs, 2000);
}