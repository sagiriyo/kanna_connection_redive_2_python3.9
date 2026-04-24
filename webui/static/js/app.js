/**
 * 环奈连结R — Web UI 前端应用
 */
(function () {
  "use strict";

  /* ============================
     Config & State
     ============================ */
  const API_BASE = "";
  let currentGroupId = null;
  let currentUserId = null;
  let sseSource = null;

  /* ============================
     Helpers
     ============================ */
  function $(sel, ctx) { return (ctx || document).querySelector(sel); }
  function $$(sel, ctx) { return Array.from((ctx || document).querySelectorAll(sel)); }

  async function api(path, opts) {
    const url = API_BASE + path;
    const res = await fetch(url, {
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      ...opts,
    });
    if (res.status === 401) {
      showLogin();
      throw new Error("未登录或登录过期");
    }
    if (!res.ok) {
      const errText = await res.text();
      let msg;
      try { msg = JSON.parse(errText).detail; } catch { msg = errText; }
      throw new Error(msg || `请求失败 (${res.status})`);
    }
    const text = await res.text();
    if (!text) return null;
    try { return JSON.parse(text); } catch { return text; }
  }

  function qqAvatarUrl(qq, size) {
    return "https://q1.qlogo.cn/g?b=qq&nk=" + qq + "&s=" + (size || 640);
  }

  function setAvatar(imgEl, textEl, qq, name) {
    if (!imgEl || !textEl) return;
    var url = qqAvatarUrl(qq);
    imgEl.src = url;
    imgEl.alt = name || "";
    imgEl.style.display = "";
    textEl.style.display = "none";
    imgEl.onerror = function () {
      imgEl.style.display = "none";
      textEl.style.display = "";
      textEl.textContent = (name || "栞")[0];
    };
  }

  function formatNum(n) {
    if (n >= 100000000) return (n / 100000000).toFixed(2) + "亿";
    if (n >= 10000) return (n / 10000).toFixed(1) + "万";
    return n.toLocaleString();
  }

  function formatTime(ts) {
    if (!ts) return "--";
    const d = new Date(ts * 1000);
    const pad = (n) => String(n).padStart(2, "0");
    return `${pad(d.getMonth() + 1)}/${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
  }

  function toast(msg, type) {
    type = type || "info";
    const el = document.createElement("div");
    el.className = "toast toast-" + type;
    el.textContent = msg;
    $("#toast-container").appendChild(el);
    setTimeout(function () { el.remove(); }, 3500);
  }

  /* ============================
     Page Navigation
     ============================ */
  function showLogin() {
    closeSse();
    $$("#app > .page").forEach(function (p) { p.classList.remove("active"); });
    $("#page-login").classList.add("active");
  }

  function showMain() {
    $$("#app > .page").forEach(function (p) { p.classList.remove("active"); });
    $("#page-main").classList.add("active");
  }

  function switchView(name) {
    $$(".nav-item").forEach(function (n) { n.classList.remove("active"); });
    var item = $(`.nav-item[data-page="${name}"]`);
    if (item) item.classList.add("active");
    $$(".view").forEach(function (v) { v.classList.remove("active"); });
    var view = $("#view-" + name);
    if (view) view.classList.add("active");

    if (name === "dashboard" && currentGroupId) loadDashboard(currentGroupId);
    if (name === "report" && currentGroupId) loadReport(currentGroupId);
    if (name === "notice" && currentGroupId) loadNotice(currentGroupId);
    if (name === "settings") loadSettings();
  }

  /* ============================
     Login
     ============================ */
  function initLogin() {
    var form = $("#login-form");
    form.addEventListener("submit", async function (e) {
      e.preventDefault();
      var btn = $("#login-btn");
      btn.disabled = true;
      btn.textContent = "登录中...";
      try {
        await api("/login", {
          method: "POST",
          body: JSON.stringify({
            account: $("#login-account").value.trim(),
            password: $("#login-password").value.trim(),
          }),
        });
        toast("登录成功", "success");
        showMain();
        loadHome();
      } catch (err) {
        toast(err.message, "error");
      } finally {
        btn.disabled = false;
        btn.textContent = "登 录";
      }
    });

    // Auto-fill from URL params
    var params = new URLSearchParams(location.search);
    if (params.get("account")) $("#login-account").value = params.get("account");
    if (params.get("password")) $("#login-password").value = params.get("password");

    // Live QQ avatar preview on login page
    var loginAccountInput = $("#login-account");
    var avatarDebounce = null;
    function updateLoginAvatar() {
      var qq = loginAccountInput.value.trim();
      if (/^\d{5,11}$/.test(qq)) {
        var img = $("#login-avatar-img");
        img.src = qqAvatarUrl(qq, 100);
        img.onload = function () {
          $("#login-avatar-wrap").style.display = "";
          $("#login-logo").style.display = "none";
        };
        img.onerror = function () {
          $("#login-avatar-wrap").style.display = "none";
          $("#login-logo").style.display = "";
        };
      } else {
        $("#login-avatar-wrap").style.display = "none";
        $("#login-logo").style.display = "";
      }
    }
    loginAccountInput.addEventListener("input", function () {
      clearTimeout(avatarDebounce);
      avatarDebounce = setTimeout(updateLoginAvatar, 400);
    });
    // Trigger on load if pre-filled
    if (loginAccountInput.value.trim()) updateLoginAvatar();
  }

  /* ============================
     Home
     ============================ */
  async function loadHome() {
    try {
      var data = await api("/home");
      currentUserId = data.user_id;
      $("#welcome-name").textContent = "你好，" + data.name;
      $("#welcome-saying").textContent = data.saying;
      $("#user-name").textContent = data.name;
      var roleMap = { 0: "成员", 1: "管理员", 2: "超级管理" };
      $("#user-role").textContent = roleMap[data.priority] || "成员";

      // Set QQ avatar in sidebar
      setAvatar(
        $("#user-avatar-img"), $("#user-avatar-text"),
        data.user_id, data.name
      );
      // Set QQ avatar in welcome card
      setAvatar(
        $("#welcome-avatar-img"), $("#welcome-avatar-text"),
        data.user_id, data.name
      );

      var clanList = $("#clan-list");
      if (data.clan && data.clan.length) {
        clanList.innerHTML = data.clan.map(function (c) {
          var gid = c.group_id || c;
          return `<div class="clan-card" data-gid="${gid}">
            <span class="clan-card-arrow">→</span>
            <div class="clan-card-id">群号: ${gid}</div>
            <div class="clan-card-name">公会 ${gid}</div>
          </div>`;
        }).join("");
        $$(".clan-card").forEach(function (card) {
          card.addEventListener("click", function () {
            currentGroupId = parseInt(this.dataset.gid);
            switchView("dashboard");
          });
        });
      } else {
        clanList.innerHTML = '<div class="empty-state">暂无绑定公会，请在QQ群内发送「绑定本群公会」</div>';
      }
    } catch (err) {
      if (err.message === "未登录或登录过期") return;
      toast("加载首页失败: " + err.message, "error");
    }
  }

  /* ============================
     Dashboard
     ============================ */
  async function loadDashboard(gid) {
    try {
      var data = await api("/" + gid + "/dashboard");
      renderDashboard(data);
      subscribeSse(gid, "dashboard");
    } catch (err) {
      toast("加载仪表盘失败: " + err.message, "error");
    }
  }

  function renderDashboard(data) {
    $("#dashboard-clan-name").textContent = data.clan_name || "仪表盘";
    $("#dashboard-stage").textContent = data.stage || "--";
    $("#dashboard-rank").textContent = "排名 " + (data.rank || "--");
    var stateEl = $("#dashboard-state");
    stateEl.textContent = "监控: " + data.state;
    stateEl.className = "badge " + (data.state === "关闭" ? "badge-danger" : "badge-success");

    $("#stat-today-dao").textContent = data.dao || 0;
    $("#stat-yesterday-dao").textContent = data.yesterday_dao || 0;
    $("#stat-day-num").textContent = data.day_num || 0;

    // Boss cards
    var bossGrid = $("#boss-grid");
    if (data.boss && data.boss.length) {
      bossGrid.innerHTML = data.boss.map(function (b, i) {
        var pct = b.max_hp ? Math.round((b.current_hp / b.max_hp) * 100) : 0;
        return `<div class="boss-card boss-${i + 1}">
          <div class="boss-header">
            <span class="boss-name">${i + 1}王 ${b.name || "???"}</span>
            <span class="boss-lap">${b.lap ? b.lap + "周目" : ""}</span>
          </div>
          <div class="boss-hp-bar"><div class="boss-hp-fill" style="width:${pct}%"></div></div>
          <div class="boss-hp-text">${formatNum(b.current_hp)} / ${formatNum(b.max_hp)} (${pct}%)</div>
          <div class="boss-stats">
            <div class="boss-stat">⚔️ <span class="boss-stat-num">${b.fighter || 0}</span> 正在挑战</div>
            <div class="boss-stat">📌 <span class="boss-stat-num">${b.subscribe || 0}</span> 预约</div>
            <div class="boss-stat">🌳 <span class="boss-stat-num">${b.tree || 0}</span> 挂树</div>
          </div>
        </div>`;
      }).join("");
    } else {
      bossGrid.innerHTML = '<div class="loading-placeholder">暂无 Boss 信息，请先开启出刀监控</div>';
    }

    // Today dao report
    var daoReport = $("#dao-report");
    if (data.report && data.report.length) {
      daoReport.innerHTML = data.report.map(function (g) {
        var numClass = "dao-num-" + g.dao_num;
        return `<div class="dao-group">
          <div class="dao-group-header">
            <span class="dao-num-badge ${numClass}">${g.dao_num}</span>
            <span class="dao-group-label">${g.dao_num}刀 (${g.names.length}人)</span>
          </div>
          <div class="dao-names">${g.names.join("、")}</div>
        </div>`;
      }).join("");
    } else {
      daoReport.innerHTML = '<div class="loading-placeholder">暂无出刀数据</div>';
    }
  }

  /* ============================
     Report
     ============================ */
  async function loadReport(gid) {
    try {
      var data = await api("/" + gid + "/report");
      renderReport(data);
      subscribeSse(gid, "report");
    } catch (err) {
      toast("加载战报失败: " + err.message, "error");
    }
  }

  function renderReport(data) {
    // All report
    var allBody = $("#table-all tbody");
    if (data.all && data.all.length) {
      allBody.innerHTML = data.all.map(function (m, i) {
        return `<tr>
          <td>${i + 1}</td>
          <td>${m.name}</td>
          <td class="num">${m.dao}</td>
          <td class="num">${formatNum(m.damage)}</td>
          <td class="num">${formatNum(m.score)}</td>
          <td class="num">${m.damage_rate || "--"}</td>
          <td class="num">${m.score_rate || "--"}</td>
        </tr>`;
      }).join("");
    } else {
      allBody.innerHTML = '<tr><td colspan="7" style="text-align:center;color:var(--text-muted)">暂无数据</td></tr>';
    }

    // My report
    var myName = $("#my-report-name");
    myName.textContent = data.name ? "玩家: " + data.name : "";
    var meBody = $("#table-me tbody");
    if (data.me && data.me.length) {
      meBody.innerHTML = data.me.map(function (m) {
        return `<tr>
          <td>${m.dao}</td>
          <td>${m.type}</td>
          <td>${m.boss}王</td>
          <td>${m.lap}</td>
          <td class="num">${formatNum(m.damage)}</td>
          <td class="num">${formatNum(m.score)}</td>
          <td>${formatTime(m.date)}</td>
        </tr>`;
      }).join("");
    } else {
      meBody.innerHTML = '<tr><td colspan="7" style="text-align:center;color:var(--text-muted)">暂无个人出刀记录</td></tr>';
    }

    // Detail
    var detailBody = $("#table-detail tbody");
    if (data.detail && data.detail.length) {
      detailBody.innerHTML = data.detail.map(function (m) {
        return `<tr>
          <td>${m.dao_id}</td>
          <td>${m.name}</td>
          <td>${m.type}</td>
          <td>${m.boss}王</td>
          <td>${m.lap}</td>
          <td class="num">${formatNum(m.damage)}</td>
          <td class="num">${formatNum(m.score)}</td>
          <td>${formatTime(m.date)}</td>
          <td><button class="btn btn-sm btn-ghost btn-correct" data-id="${m.dao_id}">修正</button></td>
        </tr>`;
      }).join("");

      $$(".btn-correct").forEach(function (btn) {
        btn.addEventListener("click", function () {
          showCorrectModal(parseInt(this.dataset.id));
        });
      });
    } else {
      detailBody.innerHTML = '<tr><td colspan="9" style="text-align:center;color:var(--text-muted)">暂无出刀记录</td></tr>';
    }
  }

  /* ============================
     Notice
     ============================ */
  async function loadNotice(gid) {
    try {
      var data = await api("/" + gid + "/notice");
      renderNotice(data);
      subscribeSse(gid, "notice");
    } catch (err) {
      toast("加载通知失败: " + err.message, "error");
    }
  }

  function renderNotice(data) {
    renderNoticeList("subscribe-list", data.subscribe, 0);
    renderNoticeList("apply-list", data.apply, 2);
    renderNoticeList("tree-list", data.tree, 1);
  }

  function renderNoticeList(containerId, items, type) {
    var container = document.getElementById(containerId);
    if (!items || !items.length) {
      var typeNames = { 0: "预约", 1: "挂树", 2: "申请" };
      container.innerHTML = '<div class="empty-state">暂无' + (typeNames[type] || "") + '</div>';
      return;
    }
    container.innerHTML = items.map(function (item) {
      var lapText = item.lap ? item.lap + "周目" : "当前周目";
      var canDelete = item.user_id === currentUserId;
      return `<div class="notice-item">
        <div class="notice-item-info">
          <div class="notice-item-user">用户 ${item.user_id}</div>
          <div class="notice-item-detail">${item.boss}王 · ${lapText}${item.text ? " · " + item.text : ""}</div>
        </div>
        <div class="notice-item-actions">
          ${canDelete ? `<button class="btn btn-sm btn-danger btn-del-notice"
            data-type="${type}" data-boss="${item.boss}"
            data-lap="${item.lap || 0}" data-uid="${item.user_id}">取消</button>` : ""}
        </div>
      </div>`;
    }).join("");

    $$(".btn-del-notice", container).forEach(function (btn) {
      btn.addEventListener("click", function () {
        deleteNotice(
          parseInt(this.dataset.type),
          parseInt(this.dataset.boss),
          parseInt(this.dataset.lap),
          parseInt(this.dataset.uid)
        );
      });
    });
  }

  async function deleteNotice(type, boss, lap, uid) {
    if (!confirm("确认取消？")) return;
    try {
      if (uid !== currentUserId) {
        await api("/delete_notice_special", {
          method: "POST",
          body: JSON.stringify({
            group_id: String(currentGroupId),
            boss: boss,
            notice_type: type,
            lap: lap,
            user_id: uid,
          }),
        });
      } else {
        await api("/delete_notice", {
          method: "POST",
          body: JSON.stringify({
            group_id: currentGroupId,
            notice_type: type,
            user_id: uid,
            boss: boss,
            lap: lap,
            text: "",
          }),
        });
      }
      toast("取消成功", "success");
      loadNotice(currentGroupId);
    } catch (err) {
      toast(err.message, "error");
    }
  }

  async function addNotice(type) {
    var typeNames = { 0: "预约", 1: "挂树", 2: "申请出刀" };
    showModal(typeNames[type], `
      <div class="modal-form-group">
        <label>Boss 编号 (1-5)</label>
        <select id="modal-boss">
          <option value="1">1王</option>
          <option value="2">2王</option>
          <option value="3">3王</option>
          <option value="4">4王</option>
          <option value="5">5王</option>
        </select>
      </div>
      <div class="modal-form-group">
        <label>周目 (0=当前周目)</label>
        <input type="number" id="modal-lap" value="0" min="0">
      </div>
      <div class="modal-form-group">
        <label>留言 (可选)</label>
        <input type="text" id="modal-text" placeholder="输入留言...">
      </div>
    `, async function () {
      var boss = parseInt($("#modal-boss").value);
      var lap = parseInt($("#modal-lap").value) || 0;
      var text = $("#modal-text").value.trim();
      try {
        await api("/set_notice", {
          method: "POST",
          body: JSON.stringify({
            group_id: currentGroupId,
            notice_type: type,
            user_id: currentUserId,
            boss: boss,
            lap: lap,
            text: text,
          }),
        });
        toast("操作成功", "success");
        closeModal();
        loadNotice(currentGroupId);
      } catch (err) {
        toast(err.message, "error");
      }
    });
  }

  /* ============================
     Settings
     ============================ */
  async function loadSettings() {
    try {
      var data = await api("/account_info");
      $("#settings-qq").textContent = data.user_id || "--";

      // Account list
      loadAccountList();

      // Clan list
      var clanList = $("#settings-clan-list");
      if (data.clans && data.clans.length) {
        clanList.innerHTML = data.clans.map(function (c) {
          return '<div class="settings-clan-item">' +
            '<div class="settings-clan-item-info">' +
              '<span class="settings-clan-item-name">' + (c.group_name || "公会") + '</span>' +
              '<span class="settings-clan-item-id">群号: ' + c.group_id + '</span>' +
            '</div>' +
            '<button class="btn btn-sm btn-danger btn-unbind-clan" data-gid="' + c.group_id + '">解绑</button>' +
          '</div>';
        }).join("");
        $$(".btn-unbind-clan", clanList).forEach(function (btn) {
          btn.addEventListener("click", function () {
            unbindClan(parseInt(this.dataset.gid));
          });
        });
      } else {
        clanList.innerHTML = '<div class="empty-state">暂无绑定公会</div>';
      }

      // Monitor list
      var monitorList = $("#settings-monitor-list");
      if (data.monitors && data.monitors.length) {
        monitorList.innerHTML = data.monitors.map(function (m) {
          var statusClass = m.active ? "active" : "inactive";
          var statusText = m.active ? "运行中" : "已停止";
          var cancelBtn = m.active
            ? '<button class="btn btn-sm btn-danger btn-cancel-monitor" data-gid="' + m.group_id + '">取消监控</button>'
            : '<span class="monitor-status inactive">已停止</span>';
          return '<div class="monitor-item">' +
            '<div class="monitor-item-info">' +
              '<span class="monitor-item-name">' + (m.clan_name || "公会 " + m.group_id) + '</span>' +
              '<span class="monitor-item-detail">群号: ' + m.group_id + ' · 排名: ' + (m.rank || "--") + '</span>' +
            '</div>' +
            '<div class="monitor-item-actions">' +
              '<span class="monitor-status ' + statusClass + '">' + statusText + '</span>' +
              cancelBtn +
            '</div>' +
          '</div>';
        }).join("");
        $$(".btn-cancel-monitor", monitorList).forEach(function (btn) {
          btn.addEventListener("click", function () {
            cancelMonitor(parseInt(this.dataset.gid));
          });
        });
      } else {
        monitorList.innerHTML = '<div class="empty-state">暂无监控记录</div>';
      }
    } catch (err) {
      toast("加载设置失败: " + err.message, "error");
    }
  }

  async function loadAccountList() {
    try {
      var accounts = await api("/accounts");
      var accountList = $("#settings-account-list");
      if (accounts && accounts.length) {
        accountList.innerHTML = accounts.map(function (acc) {
          return '<div class="settings-account-item">' +
            '<div class="settings-account-item-info">' +
              '<span class="settings-account-item-name">' + (acc.name || "未设置昵称") + '</span>' +
              '<span class="settings-account-item-detail">' +
                '游戏ID: ' + (acc.viewer_id || "--") +
                ' · 服务器: ' + (acc.platform_name || "未知") +
              '</span>' +
            '</div>' +
            '<button class="btn btn-sm btn-danger btn-unbind-account" data-aid="' + acc.id + '" data-name="' + (acc.name || "该账号") + '">解绑</button>' +
          '</div>';
        }).join("");
        $$(".btn-unbind-account", accountList).forEach(function (btn) {
          btn.addEventListener("click", function () {
            unbindAccount(parseInt(this.dataset.aid), this.dataset.name);
          });
        });
      } else {
        accountList.innerHTML = '<div class="empty-state">暂无绑定账号，请点击下方按钮绑定</div>';
      }
    } catch (err) {
      toast("加载账号列表失败: " + err.message, "error");
    }
  }

  async function unbindAccount(accountId, name) {
    if (!confirm('确认解绑账号「' + name + '」？解绑后相关数据不会删除。')) return;
    try {
      await api("/unbind_account", {
        method: "POST",
        body: JSON.stringify({ account_id: accountId }),
      });
      toast("解绑账号成功", "success");
      loadAccountList();
    } catch (err) {
      toast(err.message, "error");
    }
  }

  function showBindAccountModal() {
    showModal("绑定游戏账号", '\
      <div class="modal-form-group">\
        <label>服务器类型</label>\
        <select id="modal-bind-platform">\
          <option value="b">B服（Bilibili）</option>\
          <option value="qu">渠道服</option>\
          <option value="tw">台服</option>\
        </select>\
      </div>\
      <div id="bind-fields-b" class="bind-platform-fields">\
        <div class="modal-form-group">\
          <label>B站账号</label>\
          <input type="text" id="modal-bili-account" placeholder="输入B站账号">\
        </div>\
        <div class="modal-form-group">\
          <label>B站密码</label>\
          <input type="password" id="modal-bili-password" placeholder="输入B站密码">\
        </div>\
      </div>\
      <div id="bind-fields-qu" class="bind-platform-fields" style="display:none">\
        <div class="modal-form-group">\
          <label>login_id</label>\
          <input type="text" id="modal-qu-login-id" placeholder="输入login_id">\
        </div>\
        <div class="modal-form-group">\
          <label>token</label>\
          <input type="text" id="modal-qu-token" placeholder="输入token">\
        </div>\
        <div class="modal-form-group">\
          <label>token2（可选，如果token被分成两段）</label>\
          <input type="text" id="modal-qu-token2" placeholder="可选">\
        </div>\
      </div>\
      <div id="bind-fields-tw" class="bind-platform-fields" style="display:none">\
        <div class="modal-form-group">\
          <label>short_udid</label>\
          <input type="text" id="modal-tw-short-udid" placeholder="输入short_udid">\
        </div>\
        <div class="modal-form-group">\
          <label>udid</label>\
          <input type="text" id="modal-tw-udid" placeholder="输入udid">\
        </div>\
        <div class="modal-form-group">\
          <label>viewer_id</label>\
          <input type="number" id="modal-tw-viewer-id" placeholder="输入viewer_id">\
        </div>\
      </div>\
      <p class="bind-hint">💡 绑定信息与QQ端「绑定账号」指令一致，绑定后将自动验证登录</p>\
    ', async function () {
      var platform = $("#modal-bind-platform").value;
      var payload = { platform: platform };
      if (platform === "b") {
        payload.bili_account = $("#modal-bili-account").value.trim();
        payload.bili_password = $("#modal-bili-password").value;
        if (!payload.bili_account || !payload.bili_password) {
          toast("请输入B站账号和密码", "error"); return;
        }
      } else if (platform === "qu") {
        payload.login_id = $("#modal-qu-login-id").value.trim();
        payload.token = $("#modal-qu-token").value.trim();
        payload.token2 = $("#modal-qu-token2").value.trim();
        if (!payload.login_id || !payload.token) {
          toast("请输入login_id和token", "error"); return;
        }
      } else if (platform === "tw") {
        payload.short_udid = $("#modal-tw-short-udid").value.trim();
        payload.udid = $("#modal-tw-udid").value.trim();
        payload.viewer_id = parseInt($("#modal-tw-viewer-id").value);
        if (!payload.short_udid || !payload.udid || !payload.viewer_id) {
          toast("请输入short_udid、udid和viewer_id", "error"); return;
        }
      }
      try {
        var res = await api("/bind_account", {
          method: "POST",
          body: JSON.stringify(payload),
        });
        var msg = "绑定成功";
        if (res && res.name) msg += "，游戏昵称: " + res.name;
        toast(msg, "success");
        closeModal();
        loadAccountList();
      } catch (err) {
        toast(err.message, "error");
      }
    });

    // Switch platform fields
    setTimeout(function () {
      var sel = $("#modal-bind-platform");
      if (sel) {
        sel.addEventListener("change", function () {
          var val = this.value;
          $$(".bind-platform-fields").forEach(function (el) { el.style.display = "none"; });
          var target = $("#bind-fields-" + val);
          if (target) target.style.display = "block";
        });
      }
    }, 100);
  }

  async function cancelMonitor(groupId) {
    if (!confirm("确认取消群 " + groupId + " 的出刀监控？")) return;
    try {
      await api("/cancel_monitor", {
        method: "POST",
        body: JSON.stringify({ group_id: groupId }),
      });
      toast("已取消出刀监控", "success");
      loadSettings();
    } catch (err) {
      toast(err.message, "error");
    }
  }

  async function unbindClan(groupId) {
    if (!confirm("确认解绑公会 " + groupId + "？")) return;
    try {
      await api("/unbind_clan", {
        method: "POST",
        body: JSON.stringify({ group_id: groupId }),
      });
      toast("解绑成功", "success");
      loadSettings();
      loadHome();
    } catch (err) {
      toast(err.message, "error");
    }
  }

  function showBindClanModal() {
    showModal("绑定公会", '\
      <div class="modal-form-group">\
        <label>群号</label>\
        <input type="number" id="modal-clan-gid" placeholder="输入QQ群号" required>\
      </div>\
      <div class="modal-form-group">\
        <label>公会名称 (可选)</label>\
        <input type="text" id="modal-clan-name" placeholder="输入公会名称" value="公会">\
      </div>\
    ', async function () {
      var gid = parseInt($("#modal-clan-gid").value);
      var name = $("#modal-clan-name").value.trim() || "公会";
      if (!gid) { toast("请输入群号", "error"); return; }
      try {
        await api("/bind_clan", {
          method: "POST",
          body: JSON.stringify({ group_id: gid, group_name: name }),
        });
        toast("绑定成功", "success");
        closeModal();
        loadSettings();
        loadHome();
      } catch (err) {
        toast(err.message, "error");
      }
    });
  }

  function initChangePassword() {
    var form = $("#change-password-form");
    form.addEventListener("submit", async function (e) {
      e.preventDefault();
      var newPwd = $("#new-password").value;
      var confirmPwd = $("#confirm-password").value;
      if (newPwd !== confirmPwd) {
        toast("两次密码不一致", "error");
        return;
      }
      if (newPwd.length < 4) {
        toast("密码长度不能小于4位", "error");
        return;
      }
      try {
        await api("/change_password", {
          method: "POST",
          body: JSON.stringify({
            new_password: newPwd,
            confirm_password: confirmPwd,
          }),
        });
        toast("密码修改成功", "success");
        form.reset();
      } catch (err) {
        toast(err.message, "error");
      }
    });
  }

  /* ============================
     Correct Dao Modal
     ============================ */
  function showCorrectModal(daoId) {
    showModal("修正出刀 #" + daoId, `
      <div class="modal-form-group">
        <label>修正类型</label>
        <select id="modal-correct-type">
          <option value="完整刀">完整刀</option>
          <option value="尾刀">尾刀</option>
          <option value="补偿">补偿</option>
        </select>
      </div>
    `, async function () {
      var type = $("#modal-correct-type").value;
      try {
        await api("/correct_dao", {
          method: "POST",
          body: JSON.stringify({
            type: type,
            dao_id: daoId,
            group_id: currentGroupId,
          }),
        });
        toast("修正成功", "success");
        closeModal();
        loadReport(currentGroupId);
      } catch (err) {
        toast(err.message, "error");
      }
    });
  }

  /* ============================
     SSE Real-time Updates
     ============================ */
  function closeSse() {
    if (sseSource) { sseSource.close(); sseSource = null; }
  }

  function subscribeSse(gid, type) {
    closeSse();
    var urlMap = {
      dashboard: "/" + gid + "/renew_dashboard",
      report: "/" + gid + "/renew_report",
      notice: "/" + gid + "/renew_notice",
    };
    var url = API_BASE + urlMap[type];
    sseSource = new EventSource(url, { withCredentials: true });
    sseSource.onmessage = function (ev) {
      try {
        var data = JSON.parse(ev.data);
        if (type === "dashboard") renderDashboard(data);
        else if (type === "report") renderReport(data);
        else if (type === "notice") renderNotice(data);
      } catch (e) { /* ignore parse errors */ }
    };
    sseSource.onerror = function () {
      // Reconnect is handled by browser automatically
    };
  }

  /* ============================
     Modal
     ============================ */
  function showModal(title, bodyHtml, onConfirm) {
    $("#modal-title").textContent = title;
    $("#modal-body").innerHTML = bodyHtml;
    var footer = $("#modal-footer");
    footer.innerHTML = "";
    var cancelBtn = document.createElement("button");
    cancelBtn.className = "btn btn-ghost";
    cancelBtn.textContent = "取消";
    cancelBtn.addEventListener("click", closeModal);
    footer.appendChild(cancelBtn);

    if (onConfirm) {
      var confirmBtn = document.createElement("button");
      confirmBtn.className = "btn btn-primary";
      confirmBtn.textContent = "确认";
      confirmBtn.addEventListener("click", onConfirm);
      footer.appendChild(confirmBtn);
    }
    $("#modal-overlay").classList.remove("hidden");
  }

  function closeModal() {
    $("#modal-overlay").classList.add("hidden");
  }

  /* ============================
     Init
     ============================ */
  function init() {
    initLogin();

    // Sidebar nav
    $$(".nav-item").forEach(function (item) {
      item.addEventListener("click", function () {
        var page = this.dataset.page;
        if (page !== "home" && page !== "help" && page !== "settings" && page !== "password" && !currentGroupId) {
          toast("请先在首页选择一个公会", "info");
          return;
        }
        switchView(page);
      });
    });

    // Sidebar toggle
    $("#sidebar-toggle").addEventListener("click", function () {
      $("#sidebar").classList.toggle("collapsed");
    });

    // Logout
    $("#btn-logout").addEventListener("click", function () {
      currentGroupId = null;
      currentUserId = null;
      closeSse();
      showLogin();
      toast("已退出登录", "info");
    });

    // Tab switching
    $$(".tab-btn").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var tabGroup = this.parentElement;
        var panel = this.dataset.tab;
        $$(".tab-btn", tabGroup).forEach(function (b) { b.classList.remove("active"); });
        this.classList.add("active");
        var container = this.closest(".view");
        $$(".tab-panel", container).forEach(function (p) { p.classList.remove("active"); });
        $("#" + panel, container).classList.add("active");
      });
    });

    // Modal close
    $("#modal-close").addEventListener("click", closeModal);
    $("#modal-overlay").addEventListener("click", function (e) {
      if (e.target === this) closeModal();
    });

    // Notice add buttons
    $("#btn-add-subscribe").addEventListener("click", function () { addNotice(0); });
    $("#btn-add-apply").addEventListener("click", function () { addNotice(2); });
    $("#btn-add-tree").addEventListener("click", function () { addNotice(1); });

    // Settings
    initChangePassword();
    $("#btn-bind-clan").addEventListener("click", showBindClanModal);
    $("#btn-bind-account").addEventListener("click", showBindAccountModal);

    // Try auto-login (check if cookie is still valid)
    autoLogin();
  }

  async function autoLogin() {
    try {
      var data = await api("/home");
      if (data && data.user_id) {
        currentUserId = data.user_id;
        showMain();
        loadHome();
      }
    } catch {
      // Not logged in — show login page
    }
  }

  // Auto-fill login from URL params
  document.addEventListener("DOMContentLoaded", init);
})();
