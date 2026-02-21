(function () {
  function extractCopyValue(target) {
    const code = target.closest(".tile-meta code");
    if (code) return code.textContent.trim();

    const span = target.closest(".tile-meta span");
    if (span) return span.textContent.trim();

    const meta = target.closest(".tile-meta");
    if (!meta) return "";
    const raw = meta.textContent.trim();
    const sep = raw.indexOf(":");
    if (sep === -1) return "";
    return raw.slice(sep + 1).trim();
  }

  async function copyText(value) {
    if (!value || value === "—") return false;
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(value);
        return true;
      }
    } catch (_) {}

    try {
      const ta = document.createElement("textarea");
      ta.value = value;
      ta.setAttribute("readonly", "");
      ta.style.position = "absolute";
      ta.style.left = "-9999px";
      document.body.appendChild(ta);
      ta.select();
      const ok = document.execCommand("copy");
      document.body.removeChild(ta);
      return ok;
    } catch (_) {
      return false;
    }
  }

  function showToast(text) {
    let toast = document.getElementById("copyToast");
    if (!toast) {
      toast = document.createElement("div");
      toast.id = "copyToast";
      toast.className = "copy-toast";
      document.body.appendChild(toast);
    }
    toast.textContent = text;
    toast.classList.add("show");
    clearTimeout(toast._hideTimer);
    toast._hideTimer = setTimeout(() => toast.classList.remove("show"), 1100);
  }

  document.addEventListener("click", async (e) => {
    const clickable = e.target.closest(".tile-meta");
    if (!clickable) return;
    const value = extractCopyValue(e.target);
    if (!value) return;
    const ok = await copyText(value);
    if (ok) showToast("Скопировано");
  });

  document.querySelectorAll(".tile-meta").forEach((el) => {
    el.classList.add("copy-enabled");
    el.title = "Кликните, чтобы скопировать значение";
  });
})();
