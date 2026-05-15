/**
 * 技能奇遇 - 前端应用
 * 页面路由、API 通信、聊天界面、反馈展示
 */

// ── 状态管理 ───────────────────────────────

const state = {
    currentPage: "scene",
    scenes: [],
    sessionId: null,
    scene: null,
};

// ── DOM 引用 ───────────────────────────────

const $ = (sel) => document.querySelector(sel);
const pages = {
    scene: $("#scene-page"),
    practice: $("#practice-page"),
    feedback: $("#feedback-page"),
};

// ── 页面路由 ───────────────────────────────

function showPage(name) {
    Object.values(pages).forEach((p) => p.classList.remove("active"));
    pages[name].classList.add("active");
    state.currentPage = name;
}

// ── API 封装 ───────────────────────────────

async function api(path, options = {}) {
    const url = path.startsWith("http") ? path : path;
    const res = await fetch(url, {
        headers: { "Content-Type": "application/json" },
        ...options,
    });
    if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || `请求失败: ${res.status}`);
    }
    return res.json();
}

// ── 场景选择页 ─────────────────────────────

async function loadScenes() {
    const list = $("#scene-list");
    list.innerHTML = '<div class="loading">加载场景中</div>';

    try {
        const data = await api("/api/scenes");
        state.scenes = data.scenes;
        renderScenes(data.scenes);
    } catch (e) {
        list.innerHTML = `<div class="loading" style="color:var(--danger)">加载失败: ${e.message}</div>`;
    }
}

function renderScenes(scenes) {
    const list = $("#scene-list");

    if (scenes.length === 0) {
        list.innerHTML = '<div class="loading">暂无匹配场景</div>';
        return;
    }

    const categoryLabels = {
        interview: "面试模拟",
        speech: "即兴演讲",
        debate: "即兴辩论",
        negotiation: "谈判模拟",
    };

    const difficultyLabels = {
        beginner: "入门",
        intermediate: "进阶",
        advanced: "挑战",
    };

    list.innerHTML = scenes
        .map(
            (s) => `
        <div class="scene-card" data-scene-id="${s.id}" onclick="startPractice('${s.id}')">
            <span class="card-category ${s.category}">${categoryLabels[s.category] || s.category}</span>
            <h3>${s.title}</h3>
            <p>${s.description}</p>
            <div class="card-meta">
                <span class="difficulty-${s.difficulty}">${difficultyLabels[s.difficulty] || s.difficulty}</span>
                <span>⏱ ${s.duration_minutes} 分钟</span>
                <span>🎭 ${s.interviewer_role}</span>
                ${s.tags.map((t) => `<span>${t}</span>`).join("")}
            </div>
        </div>`
        )
        .join("");
}

// 筛选
$("#category-filter").addEventListener("change", filterScenes);
$("#difficulty-filter").addEventListener("change", filterScenes);

function filterScenes() {
    const category = $("#category-filter").value;
    const difficulty = $("#difficulty-filter").value;

    let filtered = state.scenes;
    if (category) filtered = filtered.filter((s) => s.category === category);
    if (difficulty) filtered = filtered.filter((s) => s.difficulty === difficulty);

    renderScenes(filtered);
}

// ── 练习会话 ───────────────────────────────

async function startPractice(sceneId) {
    try {
        const data = await api("/api/practice/start", {
            method: "POST",
            body: JSON.stringify({ scene_id: sceneId }),
        });

        state.sessionId = data.session_id;
        state.scene = data.scene;

        // 切换到练习页
        $("#practice-scene-title").textContent = data.scene.title;
        $("#practice-round").textContent = "第 1 轮";
        $("#chat-area").innerHTML = "";
        $("#chat-input").value = "";

        showPage("practice");

        // 显示开场白
        addMessage("assistant", data.opening_message);
    } catch (e) {
        alert("开始练习失败: " + e.message);
    }
}

function addMessage(role, content) {
    const area = $("#chat-area");
    const roleLabels = { assistant: "🎭 面试官", user: "👤 你", system: "系统" };

    const div = document.createElement("div");
    div.className = `chat-message ${role}`;
    div.innerHTML = `
        <div class="msg-role">${roleLabels[role] || role}</div>
        <div class="msg-content">${escapeHtml(content)}</div>
    `;

    area.appendChild(div);
    area.scrollTop = area.scrollHeight;
}

function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML.replace(/\n/g, "<br>");
}

// 发送消息
async function sendMessage() {
    const input = $("#chat-input");
    const message = input.value.trim();
    if (!message || !state.sessionId) return;

    // 禁用发送按钮
    const btn = $("#btn-send");
    btn.disabled = true;
    btn.textContent = "思考中...";

    // 显示用户消息
    addMessage("user", message);
    input.value = "";

    try {
        const data = await api("/api/practice/message", {
            method: "POST",
            body: JSON.stringify({
                session_id: state.sessionId,
                message: message,
            }),
        });

        // 显示 AI 回复
        addMessage("assistant", data.reply);
        $("#practice-round").textContent = `第 ${data.current_round} 轮`;
    } catch (e) {
        addMessage("assistant", "⚠️ 回复生成失败：" + e.message + "。请重试。");
    } finally {
        btn.disabled = false;
        btn.textContent = "发送";
        input.focus();
    }
}

// 结束练习
async function endPractice() {
    if (!state.sessionId) return;

    if (!confirm("确定要结束本次练习并查看反馈吗？")) return;

    try {
        const btnEnd = $("#btn-end");
        btnEnd.disabled = true;
        btnEnd.textContent = "评估中...";

        const data = await api("/api/practice/end", {
            method: "POST",
            body: JSON.stringify({ session_id: state.sessionId }),
        });

        state.sessionId = null;
        showFeedback(data.feedback);
    } catch (e) {
        alert("结束练习失败: " + e.message);
        const btnEnd = $("#btn-end");
        btnEnd.disabled = false;
        btnEnd.textContent = "结束练习";
    }
}

// ── 反馈展示 ───────────────────────────────

function showFeedback(feedback) {
    showPage("feedback");

    // 综合评分
    const score = feedback.overall_score;
    const scoreEl = $("#feedback-overall");
    scoreEl.textContent = score.toFixed(1);
    scoreEl.style.background =
        score >= 4
            ? "linear-gradient(135deg, #10b981, #34d399)"
            : score >= 3
            ? "linear-gradient(135deg, #f59e0b, #fbbf24)"
            : "linear-gradient(135deg, #ef4444, #f87171)";
    scoreEl.style.webkitBackgroundClip = "text";
    scoreEl.style.webkitTextFillColor = "transparent";
    scoreEl.style.backgroundClip = "text";

    // 维度评分
    const dimsEl = $("#feedback-dimensions");
    dimsEl.innerHTML = feedback.dimensions
        .map(
            (d) => `
        <div class="dimension-card">
            <div class="dim-name">${d.name}</div>
            <div class="dim-stars">${renderStars(d.score)}</div>
            <div class="dim-comment">${escapeHtml(d.comment)}</div>
        </div>`
        )
        .join("");

    // 亮点
    const strengthsList = $("#feedback-strengths-list");
    strengthsList.innerHTML = feedback.strengths
        .map((s) => `<li>${escapeHtml(s)}</li>`)
        .join("");

    // 改进建议
    const improvementsList = $("#feedback-improvements-list");
    improvementsList.innerHTML = feedback.improvements
        .map((s) => `<li>${escapeHtml(s)}</li>`)
        .join("");

    // 总结
    $("#feedback-summary").textContent = feedback.summary;
}

function renderStars(score) {
    const full = Math.floor(score);
    const half = score - full >= 0.5 ? 1 : 0;
    const empty = 5 - full - half;
    return "⭐".repeat(full) + (half ? "✨" : "") + "☆".repeat(empty);
}

// ── 事件绑定 ───────────────────────────────

$("#btn-send").addEventListener("click", sendMessage);
$("#btn-end").addEventListener("click", endPractice);
$("#btn-retry").addEventListener("click", () => {
    showPage("scene");
    loadScenes();
});
$("#btn-back").addEventListener("click", () => {
    if (state.sessionId) {
        if (confirm("返回将丢失当前练习进度，确定吗？")) {
            state.sessionId = null;
            showPage("scene");
        }
    } else {
        showPage("scene");
    }
});

// 回车发送（Shift+Enter 换行）
$("#chat-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
});

// ── 初始化 ─────────────────────────────────

loadScenes();
