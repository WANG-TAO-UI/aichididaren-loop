/* Small interactions for StudyLoop. Keep dependency-free. */
(function () {
  "use strict";

  function getCookie(name) {
    var parts = document.cookie.split(";").map(function (item) {
      return item.trim();
    });
    for (var i = 0; i < parts.length; i++) {
      if (parts[i].indexOf(name + "=") === 0) {
        return decodeURIComponent(parts[i].slice(name.length + 1));
      }
    }
    return "";
  }

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function csrfToken(form) {
    var input = form.querySelector('input[name="csrfmiddlewaretoken"]');
    return input ? input.value : getCookie("csrftoken");
  }

  function setFeedback(form, message, isError) {
    var feedback = form.querySelector(".cheer-feedback");
    if (!feedback) return;
    feedback.textContent = message;
    feedback.classList.toggle("error", Boolean(isError));
  }

  function updateCheerCount(item, delta) {
    var label = item.querySelector(".cheer-label");
    if (!label) return;
    var match = label.textContent.match(/(\d+)/);
    var count = match ? parseInt(match[1], 10) : 0;
    label.textContent = "♥ " + Math.max(0, count + delta) + " 次鼓励";
  }

  function appendCheer(item, username, content) {
    if (!username) return;
    var cheers = item.querySelector(".checkin-cheers");
    if (!cheers) return;
    var empty = cheers.querySelector(".cheer-empty");
    if (empty) empty.remove();
    var line = document.createElement("span");
    line.className = "cheer-line";
    line.innerHTML = "<strong>" + escapeHtml(username) + "</strong>：" + escapeHtml(content);
    cheers.appendChild(line);
  }

  document.querySelectorAll(".cheer-form").forEach(function (form) {
    form.addEventListener("submit", async function (event) {
      event.preventDefault();
      var input = form.querySelector('input[name="content"]');
      var button = form.querySelector('button[type="submit"]');
      var content = input ? input.value.trim() : "";
      if (!content) {
        setFeedback(form, "写一句具体的鼓励吧。", true);
        if (input) input.focus();
        return;
      }
      if (button) {
        button.disabled = true;
        button.dataset.originalText = button.textContent;
        button.textContent = "发送中…";
      }
      setFeedback(form, "", false);

      try {
        var response = await fetch(form.dataset.url, {
          method: "POST",
          credentials: "same-origin",
          headers: {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-CSRFToken": csrfToken(form),
          },
          body: JSON.stringify({ content: content }),
        });
        var raw = await response.text();
        var data = {};
        try {
          data = raw ? JSON.parse(raw) : {};
        } catch (error) {
          data = { error: "服务器返回了非 JSON 响应。" };
        }

        if (response.ok) {
          var item = form.closest(".checkin-item");
          if (item) {
            updateCheerCount(item, 1);
            appendCheer(item, document.body.dataset.currentUser, content);
          }
          setFeedback(form, "鼓励已送达。", false);
          if (input) {
            input.value = "";
            input.disabled = true;
          }
          if (button) button.textContent = "已鼓励";
        } else if (response.status === 401) {
          setFeedback(form, "请先登录后再鼓励。", true);
          if (button) {
            button.disabled = false;
            button.textContent = button.dataset.originalText || "送鼓励";
          }
        } else if (response.status === 409) {
          setFeedback(form, "你已经鼓励过这条打卡了。", true);
          if (button) {
            button.disabled = false;
            button.textContent = "已鼓励";
          }
        } else {
          setFeedback(form, data.error || "发送失败，请稍后重试。", true);
          if (button) {
            button.disabled = false;
            button.textContent = button.dataset.originalText || "送鼓励";
          }
        }
      } catch (error) {
        setFeedback(form, "网络异常，请稍后重试。", true);
        if (button) {
          button.disabled = false;
          button.textContent = button.dataset.originalText || "送鼓励";
        }
      }
    });
  });

  document.querySelectorAll(".flash.success").forEach(function (flash) {
    window.setTimeout(function () {
      flash.style.transition = "opacity .35s ease, transform .35s ease";
      flash.style.opacity = "0";
      flash.style.transform = "translateY(-4px)";
      window.setTimeout(function () { flash.remove(); }, 360);
    }, 6000);
  });
})();

/* ---------- 夜间模式切换 ---------- */
(function () {
  var KEY = "studyloop-theme";
  var root = document.documentElement;
  var btn = document.getElementById("themeToggle");
  if (!btn) return;

  function sync() {
    btn.setAttribute("aria-pressed", root.getAttribute("data-theme") === "dark" ? "true" : "false");
  }

  btn.addEventListener("click", function () {
    if (root.getAttribute("data-theme") === "dark") {
      root.removeAttribute("data-theme");
      try { localStorage.setItem(KEY, "light"); } catch (e) {}
    } else {
      root.setAttribute("data-theme", "dark");
      try { localStorage.setItem(KEY, "dark"); } catch (e) {}
    }
    sync();
  });

  sync();
})();