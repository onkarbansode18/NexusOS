# 🛡️ NEXUS — AI-Powered Self-Healing OS Resource Guardian
> **Comprehensive Master Documentation: Problem Statement, Technical Architecture, Features, Machine Learning Engines, Safety Guardrails, and Execution Guide**

---

## 📑 Table of Contents
1. [Executive Summary](#1-executive-summary)
2. [Problem Statement & Background](#2-problem-statement--background)
3. [The Solution: Nexus Architecture & Philosophy](#3-the-solution-nexus-architecture--philosophy)
4. [The 5-Step Autonomous Self-Healing Loop](#4-the-5-step-autonomous-self-healing-loop)
5. [Complete System Architecture](#5-complete-system-architecture)
6. [Machine Learning & Generative AI Engines](#6-machine-learning--generative-ai-engines)
7. [Comprehensive Features by Application Page](#7-comprehensive-features-by-application-page)
8. [Safety Guardrails & Fault Tolerance](#8-safety-guardrails--fault-tolerance)
9. [Complete Technology Stack](#9-complete-technology-stack)
10. [REST API & WebSocket Specifications](#10-rest-api--websocket-specifications)
11. [Step-by-Step Execution Walkthrough (Example Scenario)](#11-step-by-step-execution-walkthrough-example-scenario)
12. [Setup, Installation & Running Guide](#12-setup-installation--running-guide)
13. [Future Roadmap & Potential Extensions](#13-future-roadmap--potential-extensions)

---

## 1. Executive Summary

**Nexus** is an autonomous, AI-driven operating system resource guardian. It is engineered to bridge the critical gap between passive system monitoring tools and active, intelligent operating system remediation.

Traditional operating system monitors (such as Windows Task Manager, macOS Activity Monitor, Linux `top`/`htop`) are **purely passive and reactive**. They inform users of system degradation only after runaway processes or memory leaks have already degraded system responsiveness, frozen user interfaces, or triggered kernel panics and Out-Of-Memory (OOM) crashes.

**Nexus transforms resource management from reactive fire-fighting into proactive, self-healing governance.** Operating on a high-frequency polling interval (default: 2 seconds), Nexus continuously senses kernel vitals, applies **Unsupervised Machine Learning (Isolation Forest)** to detect abnormal process behavior, projects resource trajectories with **Time-Series Linear Forecasting**, evaluates decisions against strict safety guardrails, executes non-destructive or staged corrective actions, and provides human-readable explanations via **Google Gemini LLM**.

---

## 2. Problem Statement & Background

### 2.1 The Limitations of Existing Operating System Tools
Modern desktop and server environments run hundreds of background services, child processes, worker pools, and third-party applications concurrently. Despite hardware advancements, systems routinely suffer from performance degradation due to predictable software faults:

1. **Reactive Nature:** 
   - Users open Task Manager or Activity Monitor *after* the computer freezes or mouse inputs stutter. By then, critical business workflows or game sessions have already crashed.
2. **Runaway CPU Spikes & Thread Starvation:**
   - Poorly written background scripts, unbounded while loops, or corrupted threads consume 100% of multiple CPU cores. This starves the operating system's window manager and UI compositor, leading to system lockups.
3. **Slow Memory Leaks:**
   - Software bugs where heap allocations are never dereferenced or freed slowly degrade RAM over hours or days. Static threshold alarms (e.g., "alert at 90% RAM") fail to detect a leak until system swap thrashing has already begun.
4. **Catastrophic User Intervention (The "Taskkill" Danger):**
   - Non-technical or panicking users attempting to free up resources frequently terminate essential OS subsystems (such as `explorer.exe`, `svchost.exe`, `csrss.exe`, or `systemd`), resulting in immediate Blue Screens of Death (BSOD) or forced restarts with uncommitted data loss.
5. **No Built-in Auditability or Root-Cause Explanations:**
   - Traditional tools display raw numerical PIDs, thread counts, and memory byte figures without explaining *why* an anomaly occurred, *what* triggered it, or *how* to prevent recurrences.

---

## 3. The Solution: Nexus Architecture & Philosophy

Nexus introduces a paradigm shift: **Intelligent, Automated, and Safe OS Self-Healing**.

```
┌────────────────────────────────────────────────────────────────────────┐
│                        NEXUS AUTONOMOUS PARADIGM                       │
├──────────────────┬─────────────────────────────────────────────────────┤
│ Proactive        │ Detects anomalies and trends BEFORE system limits   │
│ Autonomous       │ Resolves runaway states without human panic clicks │
│ Safe by Default  │ Strict whitelisting, blacklisting, & simulation mode│
│ Transparent      │ Plain-English AI root-cause summaries via Gemini LLM│
│ Real-Time        │ Sub-second WebSocket telemetry to a modern dashboard│
└──────────────────┴─────────────────────────────────────────────────────┘
```

### Core Design Principles
* **Safety First (Zero Accidental Deaths):** Nexus guarantees that critical system processes and kernel threads can never be terminated or throttled.
* **Proportional Response (Graceful Degradation):** Nexus never kills a process if lowering its priority (`renice`) or throttling its thread rate resolves the CPU saturation.
* **Simulation Mode by Default:** Nexus boots in a completely safe, non-intrusive Simulation Mode where all detections, decisions, and simulated actions are logged and displayed without altering the actual operating system state. Live execution requires explicit operator authorization.
* **Plain-Language Explainability:** Rather than presenting opaque metric dumps, Nexus generates concise, human-readable explanations of every incident.

---

## 4. The 5-Step Autonomous Self-Healing Loop

Nexus executes a closed-loop control system that repeats every **2 seconds**:

```
┌───────────────────────────────────────────────────────────────────────────────────────┐
│                                NEXUS AUTONOMOUS LOOP                                  │
├───────────────┬───────────────┬────────────────┬───────────────────┬──────────────────┤
│   1. SENSE    │   2. THINK    │   3. DECIDE    │      4. ACT       │    5. RECORD     │
│  (Telemetry)  │ (ML & Anomaly)│ (Rules Engine) │    (Execution)    │ (Audit & Stream) │
├───────────────┼───────────────┼────────────────┼───────────────────┼──────────────────┤
│ psutil native │ Isolation     │ Whitelist &    │ Simulation mode or│ SQLite DB audit  │
│ kernel metrics│ Forest scoring│ Blacklist check│ Live OS action:   │ trail & real-time│
│ (CPU, RAM,    │ & linear trend│ Velocity cap   │ renice, throttle, │ WebSockets to    │
│ Disk, Network,│ forecasting   │ & cooldown     │ suspend, restart, │ React dashboard  │
│ Processes)    │               │ verification   │ kill              │ + Gemini summary │
└───────────────┴───────────────┴────────────────┴───────────────────┴──────────────────┘
```

1. **Sense:** 
   - Scans system vitals (overall CPU %, memory available, swap used, disk I/O, network read/write).
   - Enumerates top running processes (PID, name, memory RSS, CPU percentage, status, thread count).
2. **Think:** 
   - Evaluates process behavior with an **Isolation Forest ML model** trained on baseline process metrics.
   - Computes anomaly scores and applies **Linear Regression Time-Series Forecasting** to predict time-to-breach.
3. **Decide:** 
   - **Sustained Pressure Check:** Evaluates historical samples via the `SustainedPressureTracker`. Requires a minimum sustained duration (e.g. 30 seconds) of elevated CPU or memory before triggering actions, discarding single-sample transient spikes.
   - **Cross-Check Blacklists:** Verifies target process against hardcoded kernel blacklists (`SYSTEM_PROCESS_BLACKLIST` and `SYSTEM_PIDS` like PID 1 and PID 4) and user blacklists.
   - **Whitelist Enforcement:** In Live Mode, requires explicit presence in operator-approved whitelist.
   - **Rate Limiting & Cooldown:** Enforces per-process cooldown (e.g. 5 minutes between actions on the same PID) and global velocity caps (maximum 5 actions per 10-minute rolling window) via `ActionCooldownManager`.
   - **Emergency Stop:** Immediately blocks all automated interventions if the emergency stop circuit breaker is triggered.
   - **Tiered Optimization:** Selects the least aggressive corrective action (`renice` / `throttle` before `restart` or `kill`).
4. **Act:** 
   - If **Simulation Mode** is active: logs the action as simulated, calculating predicted resource recovery without altering OS state.
   - If **Live Mode** is active: executes native OS calls via `psutil` or platform APIs:
     * `renice` / `throttle`: Demote priority to `BELOW_NORMAL_PRIORITY_CLASS` / `IDLE_PRIORITY_CLASS` (or nice 10/19 on POSIX).
     * `restore_priority`: Revert a healed process back to normal operating priority.
     * `suspend`: Freeze execution threads (`NtSuspendProcess` / `SIGSTOP`).
     * `resume`: Unfreeze execution threads.
     * `restart`: Capture original process command line and argv, terminate, and relaunch via decoupled sub-process.
     * `kill`: Forceful termination (`SIGKILL` / `taskkill /F`) as last resort.
5. **Verify & Record:** 
   - **Incident Deduplication:** Re-uses open incidents within rolling windows to prevent database record explosion.
   - **Root-Cause Diagnosis (RCA):** Generates structured diagnosis with confidence rating, weighted causal factors chain, and actionable remediation steps.
   - **Post-Action Recovery Verification:** Observes the process for an observation window (e.g. 6-10s) and classifies recovery outcome into explicit verified states: `verified_improved`, `not_improved`, `verification_inconclusive`, or `simulated`.
   - **Disk Space Management:** Periodically scans system temporary folders, calculates reclaimable storage, and safely executes rule-governed cleanups.
   - **AI Explanation & Real-Time Broadcast:** Persists records to database, generates LLM summaries via Gemini, and pushes duplex WebSockets to connected dashboard clients.


---

## 5. Complete System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       NEXUS FRONTEND (React 18 + Vite)                      │
│   Overview · Monitoring · Processes · AI Insights · Incidents · Settings   │
└──────────────────────────────────────▲──────────────────────────────────────┘
                                       │ REST API (JSON) + WebSocket (ws://)
┌──────────────────────────────────────┴──────────────────────────────────────┐
│                        API GATEWAY (FastAPI / Uvicorn)                      │
├─────────────────┬─────────────────┬──────────────────┬──────────────────────┤
│ Monitoring      │ ML Engine       │ Decision Engine  │ Action Executor      │
│ Agent (psutil)  │ • Anomaly Det.  │ • Guardrails     │ • Simulated Actions  │
│ • System Vitals │ • Forecasting   │ • Blacklists     │ • Native Live Actions│
│ • Process Stats │ • Gemini LLM    │ • Whitelists     │ (Renice, Kill, etc.) │
└─────────────────┴─────────────────┴──────────────────┴──────────────────────┘
                                       │
                    ┌──────────────────┴──────────────────┐
                    │      SQLAlchemy 2.0 / SQLite        │
                    │  Vitals · Incidents · Action Logs   │
                    └─────────────────────────────────────┘
```

### Component Breakdown

1. **Frontend Client (`/frontend`):**
   - Built with React 18, TypeScript, and Vite.
   - Custom clean, high-contrast, professional light/dark design system with zero bloated UI libraries.
   - Real-time reactivity powered by Zustand global state management and persistent WebSocket synchronization.
   - Interactive SVG sparklines and multi-metric charts for dynamic resource visualization.

2. **Backend API Gateway (`/backend/app`):**
   - Built on FastAPI with asynchronous routing (`asyncio`).
   - Serves high-performance REST endpoints for processes, incidents, policies, and diagnostics.
   - Maintains real-time duplex WebSockets (`/ws`) broadcasting metric batches every 2 seconds.

3. **Telemetry Collector (`/backend/app/monitoring`):**
   - Uses native `psutil` bindings to interface with Linux, macOS, and Windows kernels.
   - Collects per-process CPU time, Resident Set Size (RSS), virtual memory, I/O counters, and process status flags.

4. **Machine Learning Pipeline (`/backend/app/ml`):**
   - Houses the Isolation Forest anomaly detector, velocity forecaster, and Google Gemini LLM summarizer.

5. **Decision & Policy Engine (`/backend/app/decision`):**
   - Enforces configurable safety policies, custom thresholds, whitelists, and autonomous action guardrails.

6. **Action Executor (`/backend/app/executor`):**
   - Safe dual-mode engine: handles virtual mock execution in Simulation Mode and direct OS API manipulation in Live Mode.

7. **Database Storage Layer (`/backend/app/db`):**
   - Asynchronous SQLite storage via `SQLAlchemy 2.0` and `aiosqlite`.
   - Stores telemetry history, incident lifecycles, action audit trails, and user configuration policies.

---

## 6. Machine Learning & Generative AI Engines

Nexus leverages three specialized artificial intelligence engines working in unison:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        NEXUS AI / ML TRIPLE ENGINE                     │
├──────────────────────────┬─────────────────────────┬───────────────────┤
│  1. ISOLATION FOREST     │  2. LINEAR REGRESSION   │  3. GEMINI LLM    │
│  Unsupervised Anomaly    │  Time-Series Resource   │  Plain-English    │
│  Detection               │  Exhaustion Forecast    │  Incident Summary │
└──────────────────────────┴─────────────────────────┴───────────────────┘
```

### 6.1 Engine 1: Isolation Forest (Unsupervised Anomaly Detection)
* **The Problem:** Static threshold rules (e.g., `CPU > 80%`) trigger false alarms during normal compilation jobs or fail entirely to catch subtle memory leaks that hover at 40% RAM.
* **The Algorithm:** Isolation Forest builds an ensemble of isolation trees (iTrees). Because anomalies have distinct attribute values, they require significantly fewer random splits to isolate from the rest of the dataset compared to nominal points.
* **Feature Vector:**
  $$\mathbf{x} = \begin{bmatrix} \text{CPU Percent} \\ \text{Memory Percent} \\ \text{Memory RSS (MB)} \end{bmatrix}$$
* **Anomaly Scoring:**
  - Standard processes yield scores near $+1.0$.
  - Deviant processes (e.g., sudden spikes or abnormal memory accumulation) yield scores dropping below $0.0$ to $-1.0$.
* **Continuous Auto-Tuning & Feedback Loop:**
  - Nexus tracks false positive rates based on operator feedback and dynamically adjusts the algorithm's `contamination` hyperparameter (default: 0.05).

### 6.2 Engine 2: Time-Series Linear Forecasting (Resource Exhaustion)
* **The Problem:** Knowing current memory usage is insufficient; operating systems need to know *when* memory will be fully exhausted.
* **The Algorithm:** Nexus maintains a rolling circular buffer of telemetry samples for active processes. It calculates growth velocity using Ordinary Least Squares (OLS) linear regression:
  $$y = mx + c$$
  Where $m$ represents the growth velocity in $\text{MB}/\text{minute}$. 
* **Time-to-Breach Estimation:**
  $$\text{Minutes to Breach} = \frac{\text{Warning Threshold (MB)} - \text{Current RSS (MB)}}{m}$$
* **Proactive Triggering:**
  - If $\text{Minutes to Breach} \le 5\text{ minutes}$ and velocity $m > 10\text{ MB/min}$, Nexus generates a predictive warning and initiates non-destructive throttling *before* the operating system runs out of memory.

### 6.3 Engine 3: Google Gemini Generative AI (LLM Root Cause Summarizer)
* **The Problem:** Multi-variable metric records (e.g., `PID 4821, RSS=1420MB, VMS=3100MB, CPU=94%, ctx_switches=184920`) are difficult for non-specialists to quickly diagnose.
* **The Algorithm:** Upon incident creation, Nexus formats the metric snapshot and process metadata into a structured prompt sent to Google Gemini Pro.
* **Generated Outputs:**
  1. **Plain-English Explanation:** Explains what occurred in clear terms (e.g., *"python3 experienced an uncontrolled recursion loop saturating Core 1. Nexus lowered its process priority to protect system UI responsiveness."*).
  2. **Confidence Score:** Assigns an explainability confidence rating (e.g., 94%).
  3. **Formatted Alert:** Generates structured Markdown and JSON alert payloads ready for Slack/Teams webhook distribution.

---

## 7. Comprehensive Features by Application Page

Nexus provides a cohesive, polished light/dark dashboard organized into 7 specialized views:

### 7.1 Overview / Dashboard (`/`)
* **Health Status Banner:** Instant visual indication of overall host health (`System is Healthy`, `Warning`, or `Critical Intervention Required`).
* **Vitals Grid:** Real-time numerical display and status badges for CPU Load %, Memory Usage %, Disk Utilization %, and Active Thread count.
* **System Resource Timeline:** Multi-metric SVG line chart displaying CPU and Memory trends over time with dynamic legends and axis markers.
* **Active Incidents Stream:** Card stack of unresolved anomalies with severity indicators (`Warning`, `Critical`).
* **Recent Healing Activity:** Live log of automated interventions showing time, target process, action taken, and recovery outcome.

### 7.2 Resource Monitoring (`/monitoring`)
* **2x2 Multi-Metric Telemetry Grid:**
  1. **CPU Usage:** Real-time utilization curve with core frequency and load averages.
  2. **Memory Usage:** Active RAM vs. cached buffers, tracking memory pressure.
  3. **Disk I/O & Storage:** Read/write throughput and storage partition capacity.
  4. **Network Throughput:** Inbound/outbound bandwidth transfer rates.
* **Configurable Sampling Controls:** Ability to select high-precision (1s), balanced (2s), or power-saver (5s/10s) intervals.

### 7.3 Process Explorer (`/processes`)
* **Live Process Table:** Paginated and sortable table of all running processes displaying PID, Process Name, User, CPU %, Memory (MB), Status, and Protection status.
* **Protection Badges:** Clear visual tags identifying whether a process is `Protected` (System Blacklist) or `Eligible` (User Whitelist).
* **Live Search & Filter:** Filter processes instantly by name or PID.
* **Detailed Process Drawer:** Clicking any process opens an inspection panel with command-line arguments, memory sparkline, and **7 manual intervention buttons**:
  - `Kill` (SIGKILL / TerminateProcess)
  - `Restart` (Graceful restart)
  - `Suspend` (Freeze execution threads)
  - `Resume` (Unfreeze suspended process)
  - `Throttle` (Limit CPU execution affinity)
  - `Renice` (Lower priority class)
  - `Observe Only` (Tag for telemetry tracking without remediation)
* **CSV Export:** One-click export of current process snapshots for offline reporting.

### 7.4 AI Insights (`/predictions`)
* **Plain-Language Anomaly Explanations:** Clean explanation cards highlighting observed anomalies without technical jargon.
* **Confidence Ratings:** Numerical confidence ratings (e.g., `94% confidence`) validating each AI deduction.
* **Next-Hour Forecast Panel:** Visual probability projections indicating expected utilization bounds for CPU (e.g., 22–35%), Memory (61–66%), and Disk (48–49%) alongside risk breach assessments (`Low risk of threshold breach`).
* **"How NEXUS Decides" Panel:** Interactive pedagogical guide detailing the 3-step decision flow:
  1. *Observe:* Compare telemetry readings with baseline metrics.
  2. *Explain:* Correlate anomalies with specific process activity.
  3. *Respond Safely:* Check safety policies before simulating or executing actions.

### 7.5 Incidents History (`/incidents`)
* **Incidents Stats Grid:** Aggregated 4-card KPI counter:
  - Total Incidents Recorded
  - High Severity / Critical Issues
  - Resolved Incidents
  - Mean Time to Resolution (MTTR)
* **Incident History Table:** Complete audit list showing Incident ID (`INC-001`), timestamp, trigger condition, affected process, severity badge, and resolution status.
* **Incident Detail Drawer & Timeline:** Detailed chronological breakdown showing exact telemetry at detection, policy evaluation, action dispatch, and post-action verification.

### 7.6 Healing Activity (`/maintenance`)
* **Action Summary KPIs:**
  - `Simulated actions today` (Counter of interventions)
  - `Successful` (Expected recovery achieved)
  - `Blocked by safety` (Actions intercepted by guardrails)
  - `Real OS interventions` (0 in Simulation Mode, counted in Live Mode)
* **Action Audit Log:** Detailed table tracking Action Name, Target Process & PID, Result Badge, Resource Delta (`CPU 91% → 24%`), and Timestamp.
* **Safety Checks Applied Panel:** Visual checklist validating that every action satisfies safety criteria:
  - Target is not on the process blacklist.
  - Resource threshold sustained for $\ge 60$ seconds.
  - 5-minute action cooldown is respected.
  - No destructive or privileged OS actions allowed without operator override.
* **Latest Result Verified Panel:** Deep-dive card validating post-healing recovery.
* **Maintenance Windows:** Suppress automated healing during scheduled database backups or OS updates.

### 7.7 Settings & Configuration (`/settings`)
* **Simulation Mode Master Toggle:** Primary switch enabling/disabling live OS interventions.
* **Monitoring Preferences:** Selectable dropdowns for Refresh Interval (`1s`, `2s`, `5s`, `10s`), Data Retention (`7d`, `30d`, `90d`), Time Zone (`UTC` or local), and Theme (`Light`/`Dark`).
* **Notification Channels:** Toggles for Incident notifications, Healing summaries, and Webhook/Email integrations.
* **Connected Host Summary:** System metadata display (Host name, OS version, CPU Cores, Total RAM, Agent version).
* **Demo Workspace Replay:** Button to reset sample readings, incidents, and logs to replay presentation scenarios.
* **Executive & SOC2 Report Generator:** Export system diagnostic and SOC2-style compliance reports in Markdown, JSON, or HTML.

---

## 8. Safety Guardrails & Fault Tolerance

To ensure that Nexus can never destabilize the operating system it protects, it enforces strict multi-layered safety guardrails:

```
                  ┌───────────────────────────────┐
                  │    ANOMALY DETECTED BY ML     │
                  └──────────────┬────────────────┘
                                 │
                                 ▼
                 [ Is Target in System Blacklist? ]
                 ├── YES ──► ABORT & LOG AS PROTECTED
                 └── NO
                                 │
                                 ▼
                 [ Is Target in Personal Whitelist? ]
                 ├── NO ───► ABORT (Action requires whitelist)
                 └── YES
                                 │
                                 ▼
                 [ Is 5-Minute Cooldown Respected? ]
                 ├── NO ───► ABORT (Cooldown active)
                 └── YES
                                 │
                                 ▼
                 [ Is Max Velocity Cap Reached? ]
                 ├── YES ──► ABORT (Cap: 5 actions/10 min)
                 └── NO
                                 │
                                 ▼
                 [ Is Simulation Mode Enabled? ]
                 ├── YES ──► RECORD SIMULATED AUDIT
                 └── NO  ──► EXECUTE GRACEFUL OS ACTION
```

### 8.1 Hardcoded System Blacklist
Nexus maintains a strict, unmodifiable blacklist of critical kernel threads, init processes, and core operating system daemons. These processes **can never be terminated, suspended, or throttled under any circumstances**:
- **Linux:** PID 1, `systemd`, `init`, `kthreadd`, `kworker/*`, `sshd`, `dbus-daemon`, `journald`, `udevd`.
- **Windows:** `System`, `System Idle Process`, `csrss.exe`, `smss.exe`, `svchost.exe`, `lsass.exe`, `services.exe`, `wininit.exe`, `winlogon.exe`, `explorer.exe`.
- **macOS:** `launchd`, `kernel_task`, `WindowServer`, `loginwindow`.

### 8.2 Strict Whitelisting Requirement
In Live Mode, Nexus will **only** take autonomous actions on processes that the system administrator has explicitly added to the **Permitted Whitelist** (e.g., `python3`, `node`, `chrome`, `worker_process`). Unlisted processes trigger notifications but are never touched.

### 8.3 Rate Limiting & Velocity Caps
To prevent cascade failures or infinite remediation loops:
- **Velocity Cap:** Maximum of 5 autonomous actions per 10-minute sliding window.
- **Per-Process Cooldown:** A 5-minute cool-off period is enforced before any process can be targeted a second time.

### 8.4 Graceful Degradation Hierarchy
Nexus follows a staged escalation policy:
1. **Stage 1 (Renice):** Lower process scheduling priority to idle/below-normal class.
2. **Stage 2 (Throttle):** Restrict process CPU affinity or thread time.
3. **Stage 3 (Suspend):** Temporarily freeze thread execution.
4. **Stage 4 (Restart):** Attempt graceful service restart.
5. **Stage 5 (Terminate/Kill):** Executed only as an absolute last resort when resource exhaustion is imminent and earlier stages fail.

---

## 9. Complete Technology Stack

| Layer | Technology | Version | Purpose |
| :--- | :--- | :--- | :--- |
| **Frontend Framework** | React | 18.2 | Component-based interactive UI |
| **Build Tool** | Vite | 5.x | Ultra-fast HMR and bundle compilation |
| **Language** | TypeScript | 5.x | End-to-end type safety |
| **Styling** | Vanilla CSS + Tailwind CSS | 3.4 | Clean custom design system |
| **Icons** | Lucide React | Latest | Crisp, modern vector iconography |
| **Global State** | Zustand | 4.5 | Lightweight reactive store without Redux boilerplate |
| **Real-Time Client** | WebSockets | Native | Sub-second bidirectional streaming |
| **Backend Framework**| FastAPI | 0.110+ | High-performance async Python web framework |
| **ASGI Web Server** | Uvicorn | 0.28+ | Asynchronous event loop server |
| **OS Telemetry** | `psutil` | 5.9+ | Cross-platform kernel and process telemetry |
| **Machine Learning** | `scikit-learn` | 1.4+ | Isolation Forest anomaly detection |
| **Forecasting** | `numpy` & `statsmodels` | Latest | OLS linear regression time-series forecasting |
| **Generative AI** | Google Gemini API | Pro | Plain-English incident root cause summaries |
| **Database** | SQLite + `aiosqlite` | 3.x | Lightweight, zero-config asynchronous relational storage |
| **ORM** | SQLAlchemy | 2.0+ | Modern async ORM data models |
| **Data Validation** | Pydantic | 2.x | Request/response schema validation |
| **Containerization** | Docker & Docker Compose | Latest | Reproducible containerized deployment |

---

## 10. REST API & WebSocket Specifications

### 10.1 WebSocket Stream
* **Endpoint:** `ws://localhost:8000/ws`
* **Broadcast Frequency:** Every 2,000 ms (2 seconds).
* **Payload Structure:**
```json
{
  "timestamp": "2026-10-24T23:15:00Z",
  "vitals": {
    "cpu_percent": 34.2,
    "memory_percent": 62.4,
    "memory_used_mb": 5112,
    "memory_total_mb": 8192,
    "disk_percent": 48.0,
    "network_sent_kbps": 124.5,
    "network_recv_kbps": 342.1
  },
  "top_processes": [
    {
      "pid": 4821,
      "name": "python3",
      "cpu_percent": 91.2,
      "memory_rss_mb": 420.5,
      "anomaly_score": -0.68,
      "status": "running",
      "is_protected": false,
      "is_whitelisted": true
    }
  ],
  "open_incidents": 0,
  "simulation_mode": true
}
```

### 10.2 REST Endpoints Reference

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/vitals` | Fetch current system vitals snapshot |
| `GET` | `/api/processes` | List top running processes with anomaly scores |
| `POST` | `/api/actions/execute` | Trigger manual action (`kill`, `renice`, `throttle`, `suspend`, `restart`, `restore_priority`) |
| `GET` | `/api/incidents` | Query incident history with filtering and pagination |
| `GET` | `/api/incidents/{id}` | Retrieve incident details with AI root-cause explanation |
| `GET` | `/api/policy` | Fetch current safety policies, thresholds, and whitelists |
| `POST` | `/api/policy` | Update resource thresholds and toggle Simulation Mode |
| `GET` | `/api/feedback/stats` | Retrieve ML false-positive feedback metrics |
| `POST` | `/api/feedback` | Submit operator feedback on anomaly accuracy |
| `POST` | `/api/reports/generate` | Generate diagnostic or SOC2 compliance summary report |
| `GET` | `/api/healing/cooldown/status` | Retrieve rate-limiting velocity and emergency stop status |
| `POST` | `/api/healing/emergency-stop` | Trigger emergency stop circuit breaker to halt all actions |
| `POST` | `/api/healing/emergency-stop/clear` | Clear emergency stop and resume autonomous healing |
| `GET` | `/api/healing/memory/findings` | Detect and list active memory leaks, spikes, and growth trends |
| `GET` | `/api/healing/memory/analysis/{pid}` | Inspect specific process memory trajectory and breach estimates |
| `POST` | `/api/healing/priority/restore` | Restore normal scheduling priority for a previously throttled process |
| `GET` | `/api/healing/disk/report` | Scan system temporary folders and estimate reclaimable disk space |
| `POST` | `/api/healing/disk/cleanup` | Execute safe automated cleanup of aged temp files with audit trail |
| `GET` | `/api/healing/disk/history` | Audit trail of past disk scan and cleanup operations |
| `GET` | `/api/healing/rca/recent` | List structured Root-Cause Diagnoses with causal chains |
| `GET` | `/api/healing/rca/{incident_id}` | Query structured Root-Cause Diagnosis for a specific incident |
| `GET` | `/api/healing/verifications` | Audit post-action recovery verification results and delta metrics |
| `GET` | `/api/healing/actions-history` | Comprehensive audit trail of all executed healing actions |


---

## 11. Step-by-Step Execution Walkthrough (Example Scenario)

To illustrate the entire system in action, consider a runaway worker script causing CPU saturation:

```powershell
# A background batch script encounters an infinite loop
python -c "while True: pass"
```

1. **Detection (0 – 2 seconds):**
   - Telemetry Agent reads CPU utilization for `python.exe` (PID 8384) at 100% on Core 1.
   - Isolation Forest receives the feature vector `[100.0, 3.2, 45.1]` and computes an Anomaly Score of `-0.74` (highly anomalous).
2. **Decision (2 – 3 seconds):**
   - Decision Engine verifies PID 8384 against the system blacklist: `python.exe` is **NOT** a protected kernel service.
   - Whitelist check confirms `python.exe` is registered on the permitted applications list.
   - Velocity check confirms 0 actions have occurred in the last 10 minutes (limit: 5).
   - Staged policy selects **Action: Renice** (demote process priority to `BELOW_NORMAL_PRIORITY_CLASS`).
3. **Execution (3 seconds):**
   - **Simulation Mode:** Logs the event, predicts CPU drop from 100% to 25%, and marks incident verified.
   - **Live Mode:** Calls `proc.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)`. Operating system scheduler immediately de-prioritizes the thread, restoring UI responsiveness.
4. **Recording & AI Explanation (3 – 4 seconds):**
   - Incident record `INC-003` is persisted in the database.
   - Google Gemini generates a concise summary: *"A Python worker saturated CPU Core 1 during batch processing. Priority was demoted to Below Normal; CPU dropped to 24%."*
   - Event is pushed over WebSockets; dashboard displays toast notification and updates the incident audit log.

---

## 12. Setup, Installation & Running Guide

### 12.1 Prerequisites
- **Python:** Version 3.12 or newer.
- **Node.js:** Version 20 LTS or newer with `npm`.
- **Git:** Standard git client.
- *(Optional)* **Docker & Docker Compose** for containerized execution.

---

### 12.2 Backend Setup (FastAPI)

```powershell
# 1. Navigate to backend directory
cd backend

# 2. Create and activate a Python virtual environment
python -m venv .venv
.\.venv\Scripts\activate      # Windows (PowerShell)
# source .venv/bin/activate   # macOS / Linux

# 3. Install Python dependencies
pip install -r requirements.txt

# 4. Configure environment variables
copy .env.example .env
# Edit .env to add your GOOGLE_GEMINI_API_KEY (optional)

# 5. Start the backend development server
uvicorn app.main:app --reload --port 8000
```
* **Backend API:** `http://localhost:8000`
* **Interactive Swagger Documentation:** `http://localhost:8000/docs`

---

### 12.3 Frontend Setup (React + Vite)

```powershell
# 1. Navigate to frontend directory
cd frontend

# 2. Install Node dependencies
npm install

# 3. Start Vite development server
npm run dev
```
* **Dashboard Interface:** `http://localhost:5173` (or port indicated in terminal, e.g. `5175`).

---

### 12.4 Single-Command Docker Deployment

To launch both the backend API and frontend dashboard simultaneously in isolated containers:

```powershell
# From the repository root
docker compose up --build
```

---

## 13. Future Roadmap & Potential Extensions

1. **eBPF Kernel Probing (Linux):**
   - Incorporate extended Berkeley Packet Filter (eBPF) bytecode programs for microsecond-level socket and system call tracing without user-space context switching overhead.
2. **Distributed Multi-Node Cluster Support:**
   - Extend the single-node agent into a distributed daemon that reports into a centralized Nexus Cloud control plane across Kubernetes clusters.
3. **Automated Memory Compaction:**
   - Trigger OS-level working set trimming (`EmptyWorkingSet` on Windows or `malloc_trim` on Linux) before resorting to process restarts.
4. **Predictive Energy & Thermal Throttling:**
   - Integrate battery and thermal sensors to throttle non-critical background jobs during high ambient temperature or low battery conditions on mobile/laptop workstations.

---

## 🏁 Conclusion

**Nexus** represents the future of operating system reliability. By fusing real-time kernel telemetry, unsupervised anomaly detection, proactive time-series forecasting, and generative AI explanations with strict, multi-layered safety guardrails, Nexus ensures host operating systems remain fast, resilient, and crash-free.
