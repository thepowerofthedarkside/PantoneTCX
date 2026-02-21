(function () {
  let widgetCounter = 0;
  let activePollTimer = null;

  function ensureThankYouModal() {
    let modal = document.getElementById("donateThankYouModal");
    if (modal) return modal;

    modal = document.createElement("div");
    modal.id = "donateThankYouModal";
    modal.className = "donate-modal";
    modal.innerHTML = [
      '<div class="donate-modal-backdrop"></div>',
      '<div class="donate-modal-card" role="dialog" aria-modal="true" aria-labelledby="donate-modal-title">',
      '  <h3 id="donate-modal-title">Спасибо за поддержку!</h3>',
      "  <p>Платеж успешно выполнен. Ваш вклад помогает развивать проект.</p>",
      '  <button type="button" class="button donate-modal-close">Закрыть</button>',
      "</div>"
    ].join("");
    document.body.appendChild(modal);

    const closeBtn = modal.querySelector(".donate-modal-close");
    const backdrop = modal.querySelector(".donate-modal-backdrop");
    const close = function () {
      modal.classList.remove("show");
    };
    if (closeBtn) closeBtn.addEventListener("click", close);
    if (backdrop) backdrop.addEventListener("click", close);
    return modal;
  }

  function showThankYouModal() {
    const modal = ensureThankYouModal();
    modal.classList.add("show");
  }

  function initDonateWidget(root) {
    if (!root || root.dataset.donateBound === "1") return;
    root.dataset.donateBound = "1";

    const mount = root.querySelector(".donate-widget-mount");
    const status = root.querySelector(".donate-status");
    const buttons = root.querySelectorAll("[data-donate-amount]");
    const customAmountInput = root.querySelector(".donate-custom-amount");
    const customAmountButton = root.querySelector(".donate-custom-button");

    function setStatus(text) {
      if (status) status.textContent = text || "";
    }

    async function createPayment(amount) {
      const resp = await fetch("/api/donate/create-payment", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ amount: Number(amount).toFixed(2) })
      });
      if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        const detail = data && data.detail ? data.detail : "Ошибка создания платежа";
        throw new Error(typeof detail === "string" ? detail : "Ошибка создания платежа");
      }
      return resp.json();
    }

    async function fetchPaymentStatus(paymentId) {
      const resp = await fetch("/api/donate/payment-status/" + encodeURIComponent(paymentId));
      if (!resp.ok) {
        throw new Error("Не удалось проверить статус платежа");
      }
      return resp.json();
    }

    function stopPolling() {
      if (activePollTimer) {
        clearInterval(activePollTimer);
        activePollTimer = null;
      }
    }

    function startPolling(paymentId, returnUrl) {
      stopPolling();
      const startedAt = Date.now();
      activePollTimer = setInterval(async () => {
        if (Date.now() - startedAt > 10 * 60 * 1000) {
          stopPolling();
          setStatus("Ожидание подтверждения оплаты завершено. Проверьте статус в ЮKassa.");
          return;
        }
        try {
          const statusData = await fetchPaymentStatus(paymentId);
          if (statusData.status === "succeeded" || statusData.paid) {
            stopPolling();
            setStatus("Платеж подтвержден.");
            showThankYouModal();
            setTimeout(function () {
              window.location.replace(returnUrl || "/donate/success");
            }, 700);
            return;
          }
          if (statusData.status === "canceled") {
            stopPolling();
            setStatus("Платеж отменен.");
          }
        } catch (_) {}
      }, 2000);
    }

    async function openWidget(amount) {
      if (!window.YooMoneyCheckoutWidget) {
        setStatus("Виджет ЮKassa не загрузился");
        return;
      }
      if (!mount) {
        setStatus("Контейнер виджета не найден");
        return;
      }
      setStatus("Создаем платеж...");
      try {
        const data = await createPayment(amount);
        mount.innerHTML = "";
        if (!mount.id) {
          widgetCounter += 1;
          mount.id = "yookassa-widget-mount-" + widgetCounter;
        }

        const widget = new window.YooMoneyCheckoutWidget({
          confirmation_token: data.confirmation_token,
          return_url: data.return_url,
          error_callback: function (error) {
            setStatus("Ошибка оплаты: " + (error && error.message ? error.message : "неизвестно"));
          }
        });
        widget.render(mount.id);
        setStatus("Окно оплаты загружено. Сумма: " + Number(data.amount).toFixed(2) + " " + data.currency);
        startPolling(data.payment_id, data.return_url);
      } catch (e) {
        setStatus(e && e.message ? e.message : "Не удалось запустить виджет");
      }
    }

    buttons.forEach((btn) => {
      btn.addEventListener("click", () => {
        const amount = btn.getAttribute("data-donate-amount");
        if (!amount) return;
        openWidget(amount);
      });
    });

    if (customAmountButton && customAmountInput) {
      customAmountButton.addEventListener("click", () => {
        const value = Number((customAmountInput.value || "").replace(",", "."));
        if (!Number.isFinite(value) || value < 10) {
          setStatus("Введите сумму от 10 рублей");
          return;
        }
        openWidget(value);
      });
    }
  }

  function bootstrap() {
    const roots = document.querySelectorAll("[data-donate-widget]");
    if (roots.length > 0) {
      roots.forEach(initDonateWidget);
      return;
    }
    const fallbackRoot = document.getElementById("donate");
    if (fallbackRoot) {
      initDonateWidget(fallbackRoot);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bootstrap);
  } else {
    bootstrap();
  }
})();
